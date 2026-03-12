"""
Simple Component Localizer V2
Takes ONE French JSON + English page UID → Localizes all components
"""

import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from dotenv import load_dotenv
import time
import requests

# Add parent lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from contentstack_api import ContentstackAPI
from json_cleanup import JSONCleanup

# Import LLM-based mapping retriever
try:
    from mapping_data_retriever import MappingDataRetriever
    LLM_MAPPING_AVAILABLE = True
except ImportError:
    LLM_MAPPING_AVAILABLE = False
    print("⚠️  Warning: mapping_data_retriever not found. LLM-based mapping disabled.")

# Load environment
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class SimpleLocalizerV2:
    def __init__(self, environment: str, use_llm_mapping: bool = True):
        """
        Initialize with ContentStack API
        
        Args:
            environment: ContentStack environment (CABC, USBC, etc.)
            use_llm_mapping: Enable LLM-based mapping for mismatched structures (default: True)
        """
        self.environment = environment
        self.locale = 'fr-ca'
        self.use_llm_mapping = use_llm_mapping and LLM_MAPPING_AVAILABLE
        
        # Get credentials
        api_key = os.getenv(f'CONTENTSTACK_API_KEY_{environment}')
        management_token = os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{environment}')
        base_url = os.getenv(f'CONTENTSTACK_BASE_URL_{environment}')
        auth_token = os.getenv('CONTENTSTACK_AUTH_TOKEN')
        environment_uid = os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{environment}')
        
        if not all([api_key, management_token, base_url]):
            raise ValueError(f"Missing credentials for {environment}")
        
        # Initialize API
        self.api = ContentstackAPI(
            api_key=api_key,
            management_token=management_token,
            base_url=base_url,
            auth_token=auth_token,
            environment_uid=environment_uid,
            environment=environment
        )
        
        # Initialize LLM-based mapping retriever if enabled
        self.mapping_retriever = None
        if self.use_llm_mapping:
            try:
                openai_key = os.getenv("OPENAI_API_KEY")
                pinecone_key = os.getenv("PINECONE_API_KEY")
                anthropic_key = os.getenv("ANTHROPIC_API_KEY")
                
                if all([openai_key, pinecone_key, anthropic_key]):
                    self.mapping_retriever = MappingDataRetriever(
                        openai_api_key=openai_key,
                        pinecone_api_key=pinecone_key,
                        anthropic_api_key=anthropic_key
                    )
                    print(f"✅ LLM-based mapping enabled (Claude Sonnet 4)")
                else:
                    print(f"⚠️  LLM mapping disabled: Missing API keys (OPENAI/PINECONE/ANTHROPIC)")
                    self.use_llm_mapping = False
            except Exception as e:
                print(f"⚠️  Failed to initialize LLM mapping: {str(e)}")
                self.use_llm_mapping = False
        
        print(f"✅ Connected to ContentStack ({environment})")
    
    def extract_components_from_english_page(self, page_uid: str) -> List[Dict]:
        """
        Extract component UIDs from English page
        Returns list of {content_type, uid, index}
        """
        print(f"\n📥 Fetching English page: {page_uid}")
        
        response = self.api.get_entry('feature_page', page_uid)
        if not response or 'entry' not in response:
            raise Exception(f"Failed to fetch page {page_uid}")
        
        entry = response['entry']
        page_composer = entry.get('page_composer', [])
        
        # DEBUG: Print structure
        print(f"\n🔍 DEBUG: page_composer has {len(page_composer)} items")
        if page_composer:
            print(f"🔍 DEBUG: First item keys: {list(page_composer[0].keys())}")
            print(f"🔍 DEBUG: First item structure:")
            print(json.dumps(page_composer[0], indent=2)[:500])
        
        components = []
        self._extract_from_composer(page_composer, components)
        
        print(f"✅ Found {len(components)} components in English page")
        return components
    
    def _extract_from_composer(self, data, components: List, index=[0]):
        """Recursively extract component references with their order"""
        if isinstance(data, dict):
            # CASE 1: Direct reference with uid and _content_type_uid (English page format)
            if 'uid' in data and '_content_type_uid' in data:
                content_type = data['_content_type_uid']
                uid = data['uid']
                
                components.append({
                    'content_type': content_type,
                    'uid': uid,
                    'index': index[0],
                    'ref_data': data
                })
                index[0] += 1
                print(f"   🔍 Found: {content_type}/{uid} at index {index[0]-1}")
            
            # CASE 2: Check if this has entry with nested component (French JSON format)
            elif 'entry' in data and '_content_type_uid' in data:
                entry_data = data['entry']
                content_type = data['_content_type_uid']
                uid = entry_data.get('uid') or data.get('uid')
                
                if uid:
                    components.append({
                        'content_type': content_type,
                        'uid': uid,
                        'index': index[0],
                        'ref_data': data
                    })
                    index[0] += 1
                    print(f"   🔍 Found: {content_type}/{uid} at index {index[0]-1}")
                
                # Recurse into entry for nested components
                for value in entry_data.values():
                    self._extract_from_composer(value, components, index)
            
            # CASE 3: Regular dict, recurse
            else:
                for value in data.values():
                    self._extract_from_composer(value, components, index)
        
        elif isinstance(data, list):
            for item in data:
                self._extract_from_composer(item, components, index)
    
    def extract_components_from_french_json(self, french_json_path: str) -> List[Dict]:
        """
        Extract ALL component data from French JSON in order
        Returns list of {content_type, french_data, index}
        """
        print(f"\n📥 Loading French JSON: {french_json_path}")
        
        with open(french_json_path, 'r', encoding='utf-8') as f:
            french_data = json.load(f)
        
        entry = french_data.get('entry', {})
        page_composer = entry.get('page_composer', [])
        
        components = []
        self._extract_french_components(page_composer, components)
        
        print(f"✅ Found {len(components)} components in French JSON")
        return components
    
    def _extract_french_components(self, data, components: List, index=[0]):
        """Extract French component data in order - ONLY TOP-LEVEL, no recursion into nested entries"""
        if isinstance(data, dict):
            # Check if this has entry with component data
            if 'entry' in data and '_content_type_uid' in data:
                entry_data = data['entry']
                content_type = data['_content_type_uid']
                
                components.append({
                    'content_type': content_type,
                    'index': index[0],
                    'french_data': entry_data  # Full French component data (includes nested components)
                })
                index[0] += 1
                print(f"   🔍 French: {content_type} at index {index[0]-1}")
                
                # DO NOT recurse into entry - nested components should stay with parent
                
            else:
                # Only recurse if this is NOT a component entry
                for value in data.values():
                    self._extract_french_components(value, components, index)
        
        elif isinstance(data, list):
            for item in data:
                self._extract_french_components(item, components, index)
    
    def match_components(self, english_refs: List[Dict], french_comps: List[Dict]) -> List[Dict]:
        """
        Match English references to French data by position and content_type
        Returns list of {content_type, english_uid, french_data}
        """
        print(f"\n🔗 Matching {len(english_refs)} English refs with {len(french_comps)} French components")
        
        matched = []
        
        for eng in english_refs:
            # Find French component at same index and content_type
            fr_match = None
            for fr in french_comps:
                if fr['index'] == eng['index'] and fr['content_type'] == eng['content_type']:
                    fr_match = fr
                    break
            
            if not fr_match:
                print(f"   ⚠️  No French match for {eng['content_type']} at index {eng['index']}")
                continue
            
            # English UID is already extracted
            eng_uid = eng['uid']
            
            matched.append({
                'content_type': eng['content_type'],
                'english_uid': eng_uid,
                'french_data': fr_match['french_data'],
                'index': eng['index']
            })
            
            print(f"   ✅ Matched: {eng['content_type']}/{eng_uid}")
        
        return matched
    
    def extract_nested_components(self, english_data: Dict, french_data: Dict, parent_type: str = "") -> List[Dict]:
        """
        Extract nested component UIDs from English and French data - goes DEEP!
        For components like:
        - ad_set_costco (with ad_builder refs)
        - link_list_with_flyout_references (with link_flyout refs)
        - link_flyout (with link_list_simple refs inside flyout_scaffolding) ← THE DEEP ONE!
        
        Returns list of {content_type, english_uid, french_data, depth} sorted by depth (deepest first)
        """
        nested = []
        processed_uids = set()  # Avoid duplicates
        MAX_DEPTH = 10  # Prevent infinite recursion
        
        def find_nested_refs(eng, fr, path="", depth=0):
            """Recursively find nested component references at all levels"""
            # Safety check: prevent infinite recursion
            if depth > MAX_DEPTH:
                print(f"         ⚠️  Max recursion depth ({MAX_DEPTH}) reached at {path}")
                return
            
            if isinstance(eng, dict) and isinstance(fr, dict):
                # Check if this is a nested component reference
                if '_content_type_uid' in eng:
                    content_type = eng['_content_type_uid']
                    
                    # CASE 1: Component reference with UID (normal case)
                    if 'uid' in eng:
                        uid = eng['uid']
                        
                        # Skip if already processed
                        if uid in processed_uids:
                            return
                        processed_uids.add(uid)
                        
                        # Get corresponding French entry data
                        fr_entry = None
                        if 'entry' in fr and '_content_type_uid' in fr:
                            fr_entry = fr['entry']
                        
                        if fr_entry:
                            # Extract French UID from the French entry data
                            french_uid = fr_entry.get('uid') if isinstance(fr_entry, dict) else None
                            
                            nested.append({
                                'content_type': content_type,
                                'english_uid': uid,
                                'french_uid': french_uid,
                                'french_data': fr_entry,
                                'path': path,
                                'depth': depth
                            })
                            print(f"      🔍 Found nested: {content_type}/{uid} at {path} (depth {depth})")
                            
                            # CRITICAL: To find DEEPER nesting (like link_list_simple inside link_flyout),
                            # we need to FETCH the English entry and look inside it!
                            try:
                                print(f"         🔄 Fetching {content_type}/{uid} for deep nesting check (depth {depth})...", flush=True)
                                eng_entry_response = self.api.get_entry(content_type, uid)
                                
                                # ContentStack returns {"entry": {...}}, so unwrap it
                                if 'entry' in eng_entry_response:
                                    eng_entry_data = eng_entry_response['entry']
                                else:
                                    eng_entry_data = eng_entry_response
                                
                                # Now recurse into the UNWRAPPED entry to find deeper references
                                find_nested_refs(eng_entry_data, fr_entry, f"{path}.entry", depth + 1)
                            except requests.exceptions.Timeout:
                                print(f"         ⏱️  Timeout fetching {content_type}/{uid} - skipping deeper nesting check")
                            except Exception as e:
                                print(f"         ⚠️  Could not fetch {content_type}/{uid} for deep nesting check: {e}")
                        
                        # IMPORTANT: Return here to avoid recursing into the reference object
                        # We've already fetched and recursed into the actual entry above
                        return
                    
                    # CASE 2: Embedded entry without UID (ad_builder inside ad_set_costco)
                    # Structure: {"_content_type_uid": "ad_builder", "entry": {...full entry...}}
                    elif 'entry' in eng and isinstance(eng['entry'], dict):
                        eng_entry = eng['entry']
                        
                        # Get the UID from inside the entry
                        if 'uid' in eng_entry:
                            uid = eng_entry['uid']
                            
                            # Skip if already processed
                            if uid in processed_uids:
                                return
                            processed_uids.add(uid)
                            
                            # Get corresponding French entry
                            fr_entry = None
                            if 'entry' in fr and isinstance(fr['entry'], dict):
                                fr_entry = fr['entry']
                            
                            if fr_entry:
                                nested.append({
                                    'content_type': content_type,
                                    'english_uid': uid,
                                    'french_data': fr_entry,
                                    'path': path,
                                    'depth': depth
                                })
                                print(f"      🔍 Found embedded nested: {content_type}/{uid} at {path} (depth {depth})")
                                
                                # Recurse into the entry to find deeper references
                                find_nested_refs(eng_entry, fr_entry, f"{path}.entry", depth + 1)
                            
                            # Return to avoid recursing into the wrapper
                            return
                
                # Recurse into dict values (only if not a component reference)
                for key in eng.keys():
                    if key in fr:
                        find_nested_refs(eng[key], fr[key], f"{path}.{key}", depth)
            
            elif isinstance(eng, list) and isinstance(fr, list):
                # Recurse into lists
                min_len = min(len(eng), len(fr))
                for i in range(min_len):
                    find_nested_refs(eng[i], fr[i], f"{path}[{i}]", depth)
        
        find_nested_refs(english_data, french_data)
        
        # Sort by depth (deepest first) so we localize from bottom up
        nested.sort(key=lambda x: x['depth'], reverse=True)
        
        return nested
    
    def map_structure(self, english_uid: str, content_type: str, french_data: Dict) -> Dict:
        """
        Fetch English component structure, map with French content.
        
        LLM Mapping (FORCED - 100% accuracy):
        - text_builder: Complex nested structures with style-aware content
        - ad_builder: Complex text_content arrays with formatting
        - ad_set_costco: Multiple ad_builders with complex nesting
        - link_list_with_flyout_references: Nested references with flyouts
        
        Rule-Based Mapping:
        - All other content types use traditional field replacement
        """
        print(f"\n🔄 Mapping {content_type}/{english_uid}")
        
        # CRITICAL: Fix common typos in French JSON field names before processing
        # These typos cause 422 errors because ContentStack doesn't recognize the fields
        french_data = self._fix_field_name_typos(french_data)
        
        # Fetch English structure
        response = self.api.get_entry(content_type, english_uid)
        if not response or 'entry' not in response:
            print(f"   ❌ Failed to fetch English component")
            return None
        
        english_data = response['entry']
        
        # ========================================================================
        # LLM-BASED MAPPING: ALWAYS use for these components (forced)
        # - text_builder: Complex nested structures with style-aware content
        # - ad_builder: Complex text_content arrays with formatting
        # - ad_set_costco: Multiple ad_builders with complex nesting
        # - link_list_with_flyout_references: Nested references with flyouts
        # ========================================================================
        
        # Components that ALWAYS use LLM mapping (100% accuracy)
        LLM_FORCED_COMPONENTS = [
            'text_builder', 
            'ad_builder', 
            'ad_set_costco',
            'link_list_with_flyout_references'
        ]
        
        if content_type in LLM_FORCED_COMPONENTS and self.use_llm_mapping and self.mapping_retriever:
            print(f"   🤖 FORCING LLM-based mapping for {content_type} (always enabled)")
            
            try:
                # Prepare input for LLM retriever
                english_input = {'entry': english_data}
                french_input = {'entry': french_data}
                
                # Call LLM mapping with RAG examples from Pinecone
                result = self.mapping_retriever.process_mapping(
                    english_data=english_input,
                    french_data=french_input,
                    component_type=content_type,
                    n_examples=3  # Retrieve 3 similar examples from vectorDB
                )
                
                print(f"      ✅ LLM mapping complete (confidence: {result.confidence_score:.3f})")
                print(f"      Reasoning: {result.reasoning}")
                
                # Return the mapped structure
                return result.mapped_json.get('entry', result.mapped_json)
                
            except Exception as e:
                print(f"      ⚠️  LLM mapping failed: {str(e)}")
                print(f"      → Falling back to rule-based mapping...")
        
        # ========================================================================
        # FALLBACK: Rule-based mapping (existing logic)
        # ========================================================================
        
        # DEBUG: Check what we got from English
        if content_type == 'ad_builder':
            print(f"   🔍 DEBUG: English ad_builder top-level keys: {list(english_data.keys())[:10]}")
            if 'text_content' in english_data and isinstance(english_data['text_content'], list):
                print(f"   🔍 DEBUG: English has text_content array with {len(english_data['text_content'])} items")
                if len(english_data['text_content']) > 0:
                    print(f"   🔍 DEBUG: English text_content[0] keys: {list(english_data['text_content'][0].keys())}")
                    print(f"   🔍 DEBUG: English text_content[0] FULL ITEM: {english_data['text_content'][0]}")
            if 'ad_builder_block' in english_data:
                print(f"   🔍 DEBUG: English has ad_builder_block")
                block = english_data['ad_builder_block']
                if isinstance(block, dict) and 'text_content' in block:
                    print(f"   🔍 DEBUG: ad_builder_block.text_content exists with {len(block['text_content'])} items")
                    if len(block['text_content']) > 0:
                        print(f"   🔍 DEBUG: ad_builder_block.text_content[0] keys: {list(block['text_content'][0].keys())}")
        
        # SPECIAL FIX: If ad_builder and French text_content length doesn't match English,
        # rebuild French text_content using English structure + extracted French text
        # SAFETY: Only do this if the mismatch is significant (not just off by 1)
        if content_type == 'ad_builder' and 'text_content' in french_data and 'text_content' in english_data:
            eng_len = len(english_data.get('text_content', []))
            fr_len = len(french_data.get('text_content', []))
            
            # CRITICAL: Check if this is LLM-generated data (from split scenario)
            # If so, DO NOT rebuild - use as-is
            is_llm_generated = french_data.get('_llm_generated', False)
            
            if is_llm_generated:
                print(f"   ℹ️  Skipping rebuild for LLM-generated data (using as-is)")
            elif eng_len != fr_len and eng_len > 0:
                print(f"   🔧 REBUILD: ad_builder text_content mismatch (English: {eng_len}, French: {fr_len})")
                print(f"      → Extracting French text and rebuilding with English structure...")
                print(f"      ⚠️  WARNING: This may cause data corruption if your JSON already has correct structure!")
                
                # Extract all French text
                french_texts = []
                self._extract_texts(french_data.get('text_content', []), french_texts)
                print(f"      → Extracted {len(french_texts)} French text items")
                
                # DEBUG: Show what we extracted
                for idx, text in enumerate(french_texts[:3]):
                    preview = text[:60] + '...' if len(text) > 60 else text
                    print(f"         Extracted[{idx}]: {preview}")
                
                # Deduplicate and take unique texts
                unique_texts = []
                seen = set()
                for text in french_texts:
                    if text and text.strip() and text.strip() not in seen:
                        unique_texts.append(text)
                        seen.add(text.strip())
                
                if len(unique_texts) != len(french_texts):
                    print(f"      🔧 Deduplicated: {len(french_texts)} → {len(unique_texts)} unique texts")
                
                # CRITICAL: Separate different types of text:
                # 1. Caption text: "Recette et photo gracieusetés de..." → goes to 'caption' field
                # 2. Author attribution: "—Charles Chum" → goes to 'disclaimer' field OR stays at end of markdown_text
                # 3. Regular content: stays in markdown_text
                caption_text = None
                author_attribution = None
                regular_texts = []
                
                for text in unique_texts:
                    if self._is_caption_text(text):
                        if caption_text is None:  # Only keep first caption found
                            caption_text = text
                            print(f"      📝 Detected caption text: {text[:60]}...")
                    elif self._is_author_attribution(text):
                        if author_attribution is None:  # Only keep first author attribution
                            author_attribution = text
                            print(f"      ✍️  Detected author attribution: {text[:60]}...")
                    else:
                        regular_texts.append(text)
                
                # IMPORTANT: Keep author attribution with regular texts (at the end)
                # Author bylines typically appear at the end of the description
                if author_attribution:
                    regular_texts.append(author_attribution)
                
                # Use regular texts (including author attribution) for markdown_text mapping
                unique_texts = regular_texts
                
                # Rebuild French text_content array using English structure
                rebuilt_text_content = []
                for i, eng_item in enumerate(english_data['text_content']):
                    if i < len(unique_texts):
                        # Use English structure, replace only markdown_text with French
                        rebuilt_item = self._deep_copy(eng_item)
                        # Navigate to markdown_text and replace
                        if 'markdown_text' in rebuilt_item:
                            if isinstance(rebuilt_item['markdown_text'], dict) and 'markdown_text' in rebuilt_item['markdown_text']:
                                rebuilt_item['markdown_text']['markdown_text'] = unique_texts[i]
                            elif isinstance(rebuilt_item['markdown_text'], str):
                                rebuilt_item['markdown_text'] = unique_texts[i]
                        rebuilt_text_content.append(rebuilt_item)
                    else:
                        # No French text for this position, use empty
                        rebuilt_text_content.append(self._deep_copy(eng_item))
                
                # Replace French text_content with rebuilt version
                french_data['text_content'] = rebuilt_text_content
                print(f"      ✅ Rebuilt text_content: {len(rebuilt_text_content)} items matching English")
                
                # If we detected a caption, add it to the ad_builder
                if caption_text:
                    if 'ad_builder_block' in french_data:
                        french_data['ad_builder_block']['caption'] = caption_text
                        print(f"      ✅ Added caption to ad_builder_block: {caption_text[:60]}...")
                    elif 'caption' not in french_data:
                        french_data['caption'] = caption_text
                        print(f"      ✅ Added caption to ad_builder: {caption_text[:60]}...")
        
        # SPECIAL FIX: If text_builder and French multiple_text_section_group doesn't match English,
        # rebuild using English structure + extracted French text with style-aware splitting
        # SAFETY: Only do this if explicitly needed (not for LLM-mapped data)
        if content_type == 'text_builder' and 'multiple_text_section_group' in french_data and 'multiple_text_section_group' in english_data:
            eng_sections = english_data.get('multiple_text_section_group', [])
            fr_sections = french_data.get('multiple_text_section_group', [])
            
            # CRITICAL: Check if this is LLM-generated data
            is_llm_generated = french_data.get('_llm_generated', False)
            
            if len(eng_sections) != len(fr_sections) and len(eng_sections) > 0 and not is_llm_generated:
                print(f"   🔧 REBUILD: text_builder section mismatch (English: {len(eng_sections)}, French: {len(fr_sections)})")
                print(f"      ⚠️  WARNING: This rebuild may cause wrong French text if your JSON is already correct!")
                print(f"      → Extracting French text and rebuilding with English structure...")
                
                # DEBUG: Show French sections BEFORE extraction
                print(f"      🔍 DEBUG: French sections BEFORE extraction:")
                for i, section in enumerate(fr_sections):
                    text_items = section.get('text_section_content', [])
                    if text_items:
                        text = text_items[0].get('markdown_text', '')[:80]
                        print(f"         FR Section {i+1}: {text}...")
                
                # Extract all French text from sections
                french_texts = []
                for section in fr_sections:
                    text_items = section.get('text_section_content', [])
                    for item in text_items:
                        text = item.get('markdown_text', '')
                        if text:
                            # Deduplicate inline
                            deduplicated = self._deduplicate_text(text)
                            french_texts.append(deduplicated)
                
                print(f"      → Extracted {len(french_texts)} French text items from {len(fr_sections)} sections")
                
                # DEBUG: Show what we extracted
                print(f"      🔍 DEBUG: Extracted texts:")
                for idx, text in enumerate(french_texts[:5]):
                    preview = text[:80] + '...' if len(text) > 80 else text
                    print(f"         Extracted[{idx}]: {preview}")
                
                # Try style-aware splitting if we have 1 French text but multiple English sections
                if len(french_texts) == 1 and len(eng_sections) > 1:
                    print(f"      → Attempting style-aware split: 1 French text → {len(eng_sections)} sections")
                    split_texts = self._split_by_style_boundaries(eng_sections, french_texts)
                    if len(split_texts) > len(french_texts):
                        print(f"      ✅ Style-aware split successful: {len(french_texts)} → {len(split_texts)} texts")
                        french_texts = split_texts
                
                # Rebuild French sections using English structure
                rebuilt_sections = []
                for i, eng_section in enumerate(eng_sections):
                    if i < len(french_texts):
                        # Use English section structure, replace only text
                        rebuilt_section = self._deep_copy(eng_section)
                        # Update text in first text_section_content item
                        if 'text_section_content' in rebuilt_section and len(rebuilt_section['text_section_content']) > 0:
                            rebuilt_section['text_section_content'][0]['markdown_text'] = french_texts[i]
                        rebuilt_sections.append(rebuilt_section)
                    else:
                        # No French text, use English section as-is (will need manual translation)
                        rebuilt_sections.append(self._deep_copy(eng_section))
                
                # Replace French sections with rebuilt version
                french_data['multiple_text_section_group'] = rebuilt_sections
                print(f"      ✅ Rebuilt sections: {len(rebuilt_sections)} sections matching English")
                print(f"      🔍 DEBUG: Rebuilt section texts:")
                for i, section in enumerate(rebuilt_sections):
                    text_items = section.get('text_section_content', [])
                    if text_items:
                        text = text_items[0].get('markdown_text', '')[:80]
                        print(f"         Section {i+1}: {text}...")
            elif is_llm_generated:
                print(f"   ℹ️  Skipping rebuild for LLM-generated text_builder (using as-is)")
                
                # This tells _replace_content to do simple replacement only
                french_data['_rebuilt'] = True
        
        # Map: English structure + French content
        # If we already rebuilt the structure above, this will do simple text replacement only
        mapped = self._replace_content(english_data, french_data)
        
        # Clean up temporary marker
        if '_rebuilt' in mapped:
            del mapped['_rebuilt']
        
        # CRITICAL: ENFORCE STYLING PRESERVATION (for rule-based fallback)
        # This ensures colors/styles are ALWAYS copied from English, even in rule-based mapping
        if content_type in LLM_FORCED_COMPONENTS and self.use_llm_mapping and self.mapping_retriever:
            print(f"   🎨 ENFORCING English styling (rule-based fallback)")
            try:
                # Use the same enforcement as LLM mapping
                english_input = {'entry': english_data}
                mapped_with_entry = {'entry': mapped}
                
                # Call enforcement
                enforced = self.mapping_retriever.enforce_styling_preservation(
                    english_data=english_input,
                    mapped_json=mapped_with_entry,
                    component_type=content_type
                )
                
                # Extract the enforced entry
                mapped = enforced.get('entry', enforced)
                print(f"   ✅ Styling enforcement complete (rule-based path)")
            except Exception as e:
                print(f"   ⚠️  Styling enforcement failed: {str(e)}")
                # Continue with un-enforced mapping (better than failing completely)
        
        # CRITICAL POST-PROCESSING: Deduplicate related arrays
        # If we deduplicated text_content, we must also deduplicate related style arrays
        # ContentStack enforces matching array lengths between related arrays
        mapped = self._deduplicate_related_arrays(mapped, content_type)
        
        # CRITICAL: Always ensure tags field is set
        # All components must have "migrated-from-cms" tag
        if 'tags' not in mapped or not mapped['tags']:
            mapped['tags'] = ["migrated-from-cms"]
        elif "migrated-from-cms" not in mapped['tags']:
            mapped['tags'].append("migrated-from-cms")
        
        return mapped
    
    def _fix_field_name_typos(self, data: Dict) -> Dict:
        """
        Fix common typos in French JSON field names that cause 422 errors.
        
        Common typos from AI-generated or manually edited JSON:
        - text_section_conttent → text_section_content (double 't')
        - text_aliggnment → text_alignment (double 'g')
        - color_coonfig → color_config (double 'o')
        - select_ttext_type → select_text_type (double 't')
        - markddown_text → markdown_text (double 'd')
        - text_contennt → text_content (double 'n')
        - link_lisst → link_list (double 's')
        - hhas → has (double 'h')
        """
        typo_corrections = {
            # Content field typos
            'text_section_conttent': 'text_section_content',
            'textt_section_content': 'text_section_content',
            'conttent': 'content',
            'text_contennt': 'text_content',
            'text_content': 'text_content',  # Already correct
            # Alignment field typos
            'text_aliggnment': 'text_alignment',
            'text_alignnment': 'text_alignment',
            'aliggnment': 'alignment',
            # Config field typos
            'color_coonfig': 'color_config',
            'color_connfig': 'color_config',
            'coonfig': 'config',
            # Type field typos
            'select_ttext_type': 'select_text_type',
            'select_textt_type': 'select_text_type',
            'ttext_type': 'text_type',
            # Markdown field typos
            'markddown_text': 'markdown_text',
            'markdownn_text': 'markdown_text',
            'markdowwn_text': 'markdown_text',
            # Semantic field typos
            'semantics_ttype': 'semantics_type',
            'select_semantics_ttype': 'select_semantics_type',
            # Link list typos
            'link_lisst': 'link_list',
            'link_liist': 'link_list',
            'linklist': 'link_list',
            # Generic double letter typos
            'hhas': 'has',
            'haas': 'has',
            'iss': 'is',
            'annd': 'and'
        }
        
        def fix_recursive(obj):
            """Recursively fix typos in all dict keys"""
            if isinstance(obj, dict):
                fixed = {}
                for k, v in obj.items():
                    # Check if key needs correction
                    corrected_key = typo_corrections.get(k, k)
                    if corrected_key != k:
                        print(f"      🔧 Fixed typo: '{k}' → '{corrected_key}'")
                    # Recursively fix nested structures
                    fixed[corrected_key] = fix_recursive(v)
                return fixed
            elif isinstance(obj, list):
                # Recursively fix each item in the list
                return [fix_recursive(item) for item in obj]
            else:
                # Return primitive values as-is
                return obj
        
        return fix_recursive(data)
    
    def _deep_copy(self, obj):
        """Deep copy an object (dict, list, or primitive)"""
        import copy
        return copy.deepcopy(obj)
    
    def _create_french_component(self, english_component):
        """
        Create a French component from English structure.
        - Keeps COMPLETE structure from English (arrays, objects, layouts)
        - Only clears actual text VALUES inside markdown_text fields
        - Preserves ALL structural elements, counts, placements
        - Sets locale to 'en-ca' (will be localized to fr-ca)
        """
        import copy
        
        # Deep copy to avoid modifying original
        french_comp = copy.deepcopy(english_component)
        
        # Fields that contain the actual text to clear
        TEXT_VALUE_FIELDS = {'markdown_text', 'text', 'description'}
        
        # Fields to clear completely (not structural)
        SIMPLE_CLEAR_FIELDS = {
            'caption', 'alt_text', 'image_alt_text', 'mobile_image_alt_text', 
            'icon_alt_text', 'disclaimer', 'disclaimer_markdown', 
            'entry_title', 'link_text', 'meta_title', 'meta_description',
            'page_title', 'breadcrumb_title'
        }
        
        def clear_text_values(obj, parent_key=None):
            """Recursively clear only text values, preserve structure"""
            if isinstance(obj, dict):
                for key, value in list(obj.items()):
                    if key in SIMPLE_CLEAR_FIELDS:
                        # Simple fields: just clear to empty string
                        obj[key] = ""
                    elif key in TEXT_VALUE_FIELDS and isinstance(value, str):
                        # Clear text values (like markdown_text: "some text")
                        obj[key] = ""
                    elif key == 'locale':
                        # Keep locale as en-ca
                        obj[key] = 'en-ca'
                    elif isinstance(value, (dict, list)):
                        # Recurse into nested structures
                        clear_text_values(value, key)
            elif isinstance(obj, list):
                # IMPORTANT: Keep array structure intact, recurse into each item
                for item in obj:
                    clear_text_values(item, parent_key)
        
        clear_text_values(french_comp)
        return french_comp
    
    def _deduplicate_related_arrays(self, mapped_data, content_type):
        """
        Deduplicate related arrays when main array is deduplicated.
        
        For ad_builder: if text_content has N items, these arrays must match:
        - text_content_above_below_the_ad_styles
        - text_content_overlay_styles
        
        ContentStack enforces matching lengths between related arrays.
        """
        if content_type != 'ad_builder':
            return mapped_data
        
        # Check if text_content exists
        if 'text_content' not in mapped_data:
            return mapped_data
        
        text_content = mapped_data['text_content']
        target_length = len(text_content)
        
        # Related arrays that must match text_content length
        related_arrays = [
            'text_content_above_below_the_ad_styles',
            'text_content_overlay_styles'
        ]
        
        for array_name in related_arrays:
            if array_name in mapped_data and isinstance(mapped_data[array_name], list):
                current_length = len(mapped_data[array_name])
                
                if current_length != target_length:
                    print(f"      ⚠️  {array_name} has {current_length} items but text_content has {target_length}")
                    
                    if current_length > target_length:
                        # Truncate to match
                        print(f"         → Truncating {array_name} from {current_length} to {target_length} items")
                        mapped_data[array_name] = mapped_data[array_name][:target_length]
                    elif current_length == 0 and target_length > 0:
                        # Empty array but we need items - this is invalid, just leave it empty
                        # ContentStack might not require this array if it's empty
                        print(f"         → {array_name} is empty, leaving as empty array (optional field)")
                    elif current_length < target_length and current_length > 0:
                        # Duplicate last item to match length
                        print(f"         → Extending {array_name} from {current_length} to {target_length} items (repeating last)")
                        last_item = mapped_data[array_name][-1]
                        while len(mapped_data[array_name]) < target_length:
                            mapped_data[array_name].append(last_item)
        
        return mapped_data
    
    def _is_ad_builder_array(self, arr):
        """Check if array contains ad_builder entries"""
        if not isinstance(arr, list) or len(arr) == 0:
            return False
        
        # Check if first item has ad_builder structure
        first_item = arr[0]
        if isinstance(first_item, dict):
            # Check for ad_builder_block -> ad_builder_ref structure
            if 'ad_builder_block' in first_item:
                return True
        
        return False
    
    def _split_french_ad_builder(self, english_ads, french_ads):
        """
        Split single French ad_builder (with image+text) into two English ad_builders.
        English structure: [ad_builder_0: image only, ad_builder_1: text only]
        French input: [ad_builder_0: image + text]
        
        Strategy:
        1. Map French image → English ad_builder[0]
        2. Map French text → English ad_builder[1]
        """
        french_ad = french_ads[0]  # Single French ad_builder
        
        # Extract French content
        french_entry = french_ad.get('ad_builder_block', {}).get('ad_builder_ref', [{}])[0].get('entry', {})
        
        # Create result array
        result = []
        
        # ===== AD_BUILDER[0]: Image from French =====
        english_ad_0 = english_ads[0]
        
        # Create ad_builder[0] with French image data
        french_ad_0_data = {
            'ad_builder_block': {
                'ad_builder_ref': [{
                    '_content_type_uid': 'ad_builder',
                    'entry': {
                        'title': french_entry.get('title', ''),
                        'image': french_entry.get('image', []),
                        'image_alt_text': french_entry.get('image_alt_text', ''),
                        'costco_url': french_entry.get('costco_url', {}),
                        'background_group': french_entry.get('background_group', {}),
                        'enable_custom_background': french_entry.get('enable_custom_background', False),
                        'enable_text_content': False,  # Image only - no text
                        'text_content': [],
                        'text_content_placement': french_entry.get('text_content_placement', 'below_the_ad'),
                        'locale': 'en-ca'
                    }
                }]
            }
        }
        
        mapped_ad_0 = self._replace_content(english_ad_0, french_ad_0_data)
        result.append(mapped_ad_0)
        print(f"         ✅ ad_builder[0]: Mapped French image → English image-only ad_builder")
        
        # ===== AD_BUILDER[1]: Text from French =====
        english_ad_1 = english_ads[1]
        
        # Create ad_builder[1] with French text data
        french_ad_1_data = {
            'ad_builder_block': {
                'ad_builder_ref': [{
                    '_content_type_uid': 'ad_builder',
                    'entry': {
                        'title': french_entry.get('title', ''),
                        'image': {},  # No image for text-only
                        'image_alt_text': '',
                        'enable_text_content': True,  # Text enabled
                        'text_content': french_entry.get('text_content', []),
                        'text_content_placement': 'overlay',  # Follow English structure
                        'text_content_overlay_styles': english_ads[1].get('ad_builder_block', {}).get('ad_builder_ref', [{}])[0].get('entry', {}).get('text_content_overlay_styles', []),
                        'locale': 'en-ca'
                    }
                }]
            }
        }
        
        mapped_ad_1 = self._replace_content(english_ad_1, french_ad_1_data)
        result.append(mapped_ad_1)
        print(f"         ✅ ad_builder[1]: Mapped French text → English text-overlay ad_builder")
        
        return result
    
    def _preserve_markdown_formatting(self, english_text: str, french_text: str) -> str:
        """
        Preserve markdown formatting AND HTML/CSS styling from English while using French text
        
        Examples:
            English: "**COVER STORY**" → French: "La une" → Result: "**La une**"
            English: "*Welcome*" → French: "Bienvenue" → Result: "*Bienvenue*"
            English: "# Title" → French: "Titre" → Result: "# Titre"
            English: "- Item 1\n- Item 2" → French: "• Item 1\n• Item 2" → Result: "- Item 1\n- Item 2"
            English: "Text\n<div style='...'>...</div>" → French: "Texte" → Result: "Texte\n<div style='...'>...</div>"
        """
        import re
        
        # Debug output
        print(f"      🔍 Markdown preservation: '{english_text[:50]}...' → '{french_text[:50]}...'", end="")
        
        # CRITICAL: Check if English has HTML tags (inline styling)
        # Extract HTML tags from the end of English text (common pattern: text + HTML dividers)
        html_tag_pattern = r'(<(?:div|span|p|br|hr)[^>]*>.*?</(?:div|span|p)>|<(?:br|hr)[^>]*/>)$'
        html_match = re.search(html_tag_pattern, english_text, re.IGNORECASE | re.DOTALL)
        
        if html_match:
            # English has HTML tags - must preserve them
            html_tags = html_match.group(0)
            english_text_without_html = english_text[:html_match.start()].rstrip()
            
            # Process the text portion (without HTML) for markdown formatting
            # Then append the HTML tags at the end
            print(f" → preserving HTML tags", end="")
            
            # Continue with markdown processing on the text portion
            processed_text = self._process_markdown_on_text(english_text_without_html, french_text)
            
            # Append HTML tags to the processed French text
            result = processed_text + "\n" + html_tags if processed_text.strip() else html_tags
            print(f" + HTML ✅")
            return result
        
        # No HTML tags, process normally for markdown
        return self._process_markdown_on_text(english_text, french_text)
    
    def _process_markdown_on_text(self, english_text: str, french_text: str) -> str:
        """Helper to process markdown formatting (extracted from _preserve_markdown_formatting)"""
        import re
        
        # CRITICAL: Check if English has bullet list format
        eng_has_bullets = bool(re.search(r'^[\s]*[-*+]\s+', english_text, re.MULTILINE))
        
        if eng_has_bullets:
            # English uses markdown bullets, ensure French does too
            # Convert common bullet characters to markdown format
            fr_text_with_bullets = self._normalize_bullet_format(french_text)
            print(f" → normalized bullets ✅")
            return fr_text_with_bullets
        
        # IMPORTANT: Strip any existing markdown from French text first
        # French AI might have already added markdown, but we want English structure only
        french_text_clean = self._strip_all_markdown(french_text)
        
        # Detect markdown patterns in English text and apply to clean French text
        # Bold: **text** or __text__
        if re.match(r'^\*\*(.+?)\*\*$', english_text, re.DOTALL):
            result = f"**{french_text_clean}**"
            print(f" → bold ✅")
            return result
        if re.match(r'^__(.+?)__$', english_text, re.DOTALL):
            result = f"__{french_text_clean}__"
            print(f" → bold ✅")
            return result
        
        # Italic: *text* or _text_
        if re.match(r'^\*(.+?)\*$', english_text, re.DOTALL):
            result = f"*{french_text_clean}*"
            print(f" → italic ✅")
            return result
        if re.match(r'^_(.+?)_$', english_text, re.DOTALL):
            result = f"_{french_text_clean}_"
            print(f" → italic ✅")
            return result
        
        # Bold + Italic: ***text*** or ___text___
        if re.match(r'^\*\*\*(.+?)\*\*\*$', english_text, re.DOTALL):
            result = f"***{french_text_clean}***"
            print(f" → bold+italic ✅")
            return result
        if re.match(r'^___(.+?)___$', english_text, re.DOTALL):
            result = f"___{french_text_clean}___"
            print(f" → bold+italic ✅")
            return result
        
        # Headings: # text, ## text, etc.
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', english_text)
        if heading_match:
            result = f"{heading_match.group(1)} {french_text_clean}"
            print(f" → heading ✅")
            return result
        
        # No markdown pattern detected in English
        # BUT: Always strip horizontal rules from French text even if no other markdown detected
        # This ensures French AI's unwanted --- separators are always removed
        if '---' in french_text or '***' in french_text or '___' in french_text:
            # French has horizontal rules that need to be removed
            print(f" → removing horizontal rules ✅")
            return french_text_clean
        
        # No markdown detected in English, return French text as-is (keep its own markdown if any)
        print(f" → no change")
        return french_text
    
    def _normalize_bullet_format(self, text: str) -> str:
        """
        Convert various bullet characters to markdown format.
        
        Converts:
            • Item → - Item
            · Item → - Item  
            ◦ Item → - Item
            ○ Item → - Item
            ● Item → - Item
        
        Preserves:
            - Item (already markdown)
            * Item (already markdown)
            + Item (already markdown)
        """
        import re
        
        # Common bullet characters to convert to markdown
        bullet_chars = ['•', '·', '◦', '○', '●', '–', '—']
        
        # Replace bullet characters at start of lines with markdown dash
        for bullet in bullet_chars:
            # Match bullet character followed by optional space at start of line
            pattern = r'^(\s*)' + re.escape(bullet) + r'\s*'
            text = re.sub(pattern, r'\1- ', text, flags=re.MULTILINE)
        
        return text
    
    def _strip_all_markdown(self, text: str) -> str:
        """Remove all markdown formatting from text"""
        import re
        
        # Remove horizontal rules: ---, ***, ___ (at start of line)
        text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        
        # Remove bold: **text** or __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # Remove italic: *text* or _text_ (but not in URLs or special cases)
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        
        # Remove headings: # text, ## text, etc.
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Clean up multiple blank lines left by removed horizontal rules
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def _looks_like_combined_text(self, text: str) -> bool:
        """
        Check if a text looks like it contains multiple logical sections combined.
        
        Indicators of combined text:
        - Has author byline pattern (BY NAME or just NAME at start)
        - Multiple distinct paragraphs (double newlines)
        - Mix of short intro and long body
        """
        import re
        
        if not text or len(text) < 100:
            return False
        
        # Check for author byline pattern at the start
        # Pattern: "NAME\n\n" or "by NAME\n\n" or "PAR NAME\n\n"
        author_patterns = [
            r'^[A-ZÀ-Ÿ][A-ZÀ-Ÿ\s\-]+\n\n',  # ALL CAPS NAME at start
            r'^by\s+[A-ZÀ-Ÿ][a-zà-ÿ\s]+\n\n',  # "by Author Name"
            r'^par\s+[A-ZÀ-Ÿ][a-zà-ÿ\s]+\n\n',  # "par Author Name" (French)
            r'^[A-ZÀ-Ÿ][a-zà-ÿ\s]+\n\n',  # "Author Name" at start
        ]
        
        for pattern in author_patterns:
            if re.match(pattern, text):
                print(f"         ℹ️  Detected author byline pattern in text")
                return True
        
        # Check for multiple distinct paragraphs (more than 2 double-newlines)
        paragraph_breaks = text.count('\n\n')
        if paragraph_breaks >= 3:
            # Check if first paragraph is short (likely intro/byline)
            first_para = text.split('\n\n')[0]
            if len(first_para) < 200:  # Short first section
                print(f"         ℹ️  Detected short intro + long body pattern")
                return True
        
        return False
    
    def _split_author_from_body(self, combined_text: str) -> list:
        """
        Split author byline from body text, keeping ALL body paragraphs together.
        
        Examples:
            "SHARON CHISVIN\n\nParagraph1\n\nParagraph2\n\nParagraph3"
            -> ["SHARON CHISVIN", "Paragraph1\n\nParagraph2\n\nParagraph3"]
        
        Returns list with 2 items: [author, full_body_text]
        """
        import re
        
        # Pattern: ALL CAPS NAME or "by Author" at start followed by \n\n
        author_patterns = [
            (r'^([A-ZÀ-Ÿ][A-ZÀ-Ÿ\s\-]+)\n\n(.+)$', 1),  # ALL CAPS NAME
            (r'^(by\s+[A-ZÀ-Ÿ][a-zà-ÿ\s]+)\n\n(.+)$', 1),  # "by Author"
            (r'^(par\s+[A-ZÀ-Ÿ][a-zà-ÿ\s]+)\n\n(.+)$', 1),  # "par Author" (French)
        ]
        
        for pattern, flags in author_patterns:
            match = re.match(pattern, combined_text, re.DOTALL)
            if match:
                author = match.group(1).strip()
                body = match.group(2).strip()
                print(f"         ✂️  Split author '{author[:30]}...' from body ({len(body)} chars)")
                return [author, body]
        
        # No author pattern found, return as single item
        return [combined_text]
    
    def _deduplicate_text(self, text):
        """
        Remove line-by-line duplication within text.
        
        Handles TWO patterns:
        1. CONSECUTIVE PAIRS: Every line duplicated (line 0 = line 1, line 2 = line 3, etc.)
           Example: "© Author\n© Author\n**Title**\n**Title**\nBody\nBody"
           
        2. SELECTIVE DUPLICATION: Some lines duplicated consecutively
           Example: "© Author\n**Title**\n**Title**\n[Link](/url)\n[Link](/url)"
        """
        if not text or not isinstance(text, str):
            return text
        
        lines = text.split('\n')
        if len(lines) <= 1:
            return text
        
        # ========================================================================
        # PATTERN 1: Check for CONSECUTIVE PAIRS (every even line = previous line)
        # ========================================================================
        is_consecutive_pairs = True
        for i in range(0, len(lines) - 1, 2):
            if i + 1 < len(lines):
                if lines[i].strip() != lines[i + 1].strip():
                    is_consecutive_pairs = False
                    break
        
        if is_consecutive_pairs and len(lines) % 2 == 0:
            # Every line is duplicated in pairs, keep only first of each pair
            deduplicated_lines = [lines[i] for i in range(0, len(lines), 2)]
            result = '\n'.join(deduplicated_lines)
            print(f"         🔧 Deduplicated (consecutive pairs): {len(lines)} lines → {len(deduplicated_lines)} lines")
            return result
        
        # ========================================================================
        # PATTERN 2: SELECTIVE DUPLICATION (consecutive identical lines)
        # Remove any line that is identical to the previous line
        # ========================================================================
        deduplicated_lines = []
        for i, line in enumerate(lines):
            # Keep line if:
            # - It's the first line, OR
            # - It's different from the previous line
            if i == 0 or line.strip() != lines[i - 1].strip():
                deduplicated_lines.append(line)
        
        if len(deduplicated_lines) < len(lines):
            result = '\n'.join(deduplicated_lines)
            print(f"         🔧 Deduplicated (selective): {len(lines)} lines → {len(deduplicated_lines)} lines")
            return result
        
        return text
    
    def _is_caption_text(self, text):
        """Check if text looks like an image caption/attribution"""
        if not isinstance(text, str):
            return False
        text_lower = text.lower().strip()
        # Check for common caption patterns
        caption_patterns = [
            'recette et photo',
            'photo gracieuseté',
            'crédit photo',
            'photo courtesy',
            '© ',
            'courtesy of',
            'gracieusetés de'
        ]
        return any(pattern in text_lower for pattern in caption_patterns)
    
    def _is_author_attribution(self, text):
        """
        Check if text looks like an author byline/attribution.
        
        Examples:
            —Charles Chum
            —Christos Zourdos
            — Name Here
            *—Name Here*
        """
        if not isinstance(text, str):
            return False
        text_stripped = text.strip()
        # Author attributions typically start with em dash (—) or hyphen-dash
        # and are short (just a name, possibly italicized with *)
        if text_stripped.startswith('—') or text_stripped.startswith('*—'):
            # Check if it's relatively short (author names are typically < 50 chars)
            clean_text = text_stripped.replace('*', '').replace('—', '').strip()
            if len(clean_text) < 50:
                return True
        return False
    
    def _extract_texts(self, data, texts_list):
        """Recursively extract all markdown_text values from data structure"""
        if isinstance(data, dict):
            # Check if this dict has markdown_text
            if 'markdown_text' in data:
                md_text = data['markdown_text']
                # Handle nested markdown_text (like in ad_builder text_content)
                if isinstance(md_text, dict) and 'markdown_text' in md_text:
                    if md_text['markdown_text']:  # Only add if not empty
                        # Deduplicate text before adding
                        deduplicated = self._deduplicate_text(md_text['markdown_text'])
                        texts_list.append(deduplicated)
                # Handle direct string
                elif isinstance(md_text, str) and md_text:
                    # Deduplicate text before adding
                    deduplicated = self._deduplicate_text(md_text)
                    texts_list.append(deduplicated)
            # Recurse into nested dicts
            for value in data.values():
                if isinstance(value, (dict, list)):
                    self._extract_texts(value, texts_list)
        elif isinstance(data, list):
            # Recurse into each list item
            for item in data:
                self._extract_texts(item, texts_list)
    
    def _is_image_markdown(self, text):
        """Check if text is image markdown (![alt](url))"""
        if not isinstance(text, str):
            return False
        text_stripped = text.strip()
        return text_stripped.startswith('![') and '](' in text_stripped and ')' in text_stripped
    
    def _get_markdown_text_from_item(self, item):
        """Extract markdown_text value from text_content item"""
        if isinstance(item, dict):
            md_field = item.get('markdown_text')
            if isinstance(md_field, dict):
                return md_field.get('markdown_text', '')
            elif isinstance(md_field, str):
                return md_field
        return ''
    
    def _handle_text_content_mismatch(self, eng, fr):
        """
        Special handling for text_content arrays where English has image markdown
        but French doesn't (French AI put image in different location).
        
        Example:
        English text_content: [
            {markdown_text: "![image](url)", select_text_type: "title_with_xl_v2"},
            {markdown_text: "© CAPTION", select_text_type: "caption_v2"}
        ]
        French text_content: [
            {markdown_text: "© CAPTION FR", select_text_type: "caption_v2"}
        ]
        (French image is in 'image' array instead)
        
        Solution: Keep English image markdown, map French caption to English caption
        """
        if len(eng) <= len(fr):
            # Not a mismatch - French has same or more items
            return None
        
        # Check if first English item has image markdown
        first_eng_text = self._get_markdown_text_from_item(eng[0])
        if not self._is_image_markdown(first_eng_text):
            # Not an image markdown case
            return None
        
        print(f"      🖼️  Detected image markdown in English text_content[0]")
        print(f"         English: {len(eng)} items (image + {len(eng)-1} text)")
        print(f"         French: {len(fr)} items (text only, image elsewhere)")
        
        # Map French texts to English non-image items
        result = []
        
        # Keep first English item (image markdown) as-is
        result.append(eng[0])
        print(f"         → Kept English image markdown: '{first_eng_text[:50]}...'")
        
        # Map remaining French items to remaining English items
        for i in range(1, len(eng)):
            fr_index = i - 1  # Offset by 1 because French doesn't have image
            if fr_index < len(fr):
                # Map French item to English structure
                mapped = self._replace_content(eng[i], fr[fr_index])
                result.append(mapped)
                print(f"         → Mapped French[{fr_index}] to English[{i}]")
            else:
                # No French item, keep English structure
                result.append(eng[i])
                print(f"         → No French text for English[{i}], kept English")
        
        return result
    
    def _split_by_style_boundaries(self, eng_sections, french_texts):
        """
        Content-based matching: Extract French chunks and match to English sections.
        
        Instead of trying to split by style (which fails when French structure is wrong),
        this extracts all chunks from French text and matches them to English sections
        based on content type and word count similarity.
        
        Args:
            eng_sections: English section array with styling info
            french_texts: List of French text strings (single merged text)
            
        Returns:
            List of French texts matched to English section order
        """
        if len(french_texts) >= len(eng_sections):
            # Already have enough texts
            return french_texts
        
        if len(french_texts) != 1:
            # Can only process single merged text
            return french_texts
        
        french_blob = french_texts[0]
        if not french_blob or not french_blob.strip():
            return french_texts
        
        print(f"      → Attempting content-based split: {len(french_texts)} French text → {len(eng_sections)} sections")
        
        # Analyze English sections
        eng_info = []
        for section in eng_sections:
            text_items = section.get('text_section_content', [])
            if not text_items:
                eng_info.append({'style': 'empty', 'word_count': 0, 'text': '', 'is_bullets': False, 'is_heading': False})
                continue
            
            eng_text = text_items[0].get('markdown_text', '')
            style = self._analyze_section_style(section)
            word_count = len(eng_text.split())
            is_bullets = style.get('is_bullets', False)
            is_heading = eng_text.strip().startswith('#')
            
            eng_info.append({
                'style': style.get('style', 'plain'),
                'word_count': word_count,
                'text': eng_text,
                'is_bullets': is_bullets,
                'is_heading': is_heading,
                'is_product_list': style.get('is_product_list', False)
            })
        
        # Extract French chunks (split smartly to keep related content together)
        french_chunks = []
        remaining = french_blob.strip()
        
        # Split into paragraphs first
        paragraphs = []
        current = []
        
        for line in remaining.split('\n'):
            line_stripped = line.strip()
            
            # Empty line = paragraph boundary
            if not line_stripped:
                if current:
                    paragraphs.append('\n'.join(current))
                    current = []
            else:
                current.append(line)
        
        # Add last paragraph
        if current:
            paragraphs.append('\n'.join(current))
        
        # Now group paragraphs into chunks based on content type
        i = 0
        while i < len(paragraphs):
            para = paragraphs[i].strip()
            if not para:
                i += 1
                continue
            
            # Check if this is a heading
            if para.startswith('#'):
                # Check if next paragraph is also heading or body text
                if i + 1 < len(paragraphs):
                    next_para = paragraphs[i + 1].strip()
                    # If next is NOT bullets and NOT another heading, merge them (heading + body)
                    if not next_para.startswith(('- ', '• ', '* ', '#')):
                        # Heading + body paragraph
                        french_chunks.append(para + '\n\n' + next_para)
                        i += 2
                        continue
                
                # Just heading alone
                french_chunks.append(para)
                i += 1
                
            # Check if this is bullets
            elif para.startswith(('- ', '• ', '* ')) or all(l.strip().startswith(('- ', '• ', '* ')) for l in para.split('\n') if l.strip()):
                french_chunks.append(para)
                i += 1
                
            # Regular text
            else:
                french_chunks.append(para)
                i += 1
        
        print(f"         📊 Content extraction:")
        print(f"            English sections: {len(eng_sections)}")
        print(f"            French chunks extracted: {len(french_chunks)}")
        for i, info in enumerate(eng_info):
            markers = []
            if info['is_heading']: markers.append('heading')
            if info['is_bullets']: markers.append('bullets')
            if info['is_product_list']: markers.append('product-list')
            print(f"            English {i+1}: {info['word_count']} words, {', '.join(markers) if markers else 'plain'}")
        for i, chunk in enumerate(french_chunks):
            words = len(chunk.split())
            chunk_type = []
            if chunk.strip().startswith('#'): chunk_type.append('heading')
            if chunk.strip().startswith(('- ', '• ', '* ')): chunk_type.append('bullets')
            print(f"            French {i+1}: {words} words, {', '.join(chunk_type) if chunk_type else 'text'}")
        
        # Match French chunks to English sections
        result_texts = []
        used_chunks = set()
        
        for i, eng in enumerate(eng_info):
            if eng['style'] == 'empty':
                result_texts.append("")
                continue
            
            # Find best matching French chunk
            best_match = None
            best_score = -1
            
            for j, chunk in enumerate(french_chunks):
                if j in used_chunks:
                    continue
                
                score = 0
                chunk_stripped = chunk.strip()
                chunk_words = len(chunk.split())
                
                # Check if chunk is bullets (with or without italic markers)
                is_chunk_bullets = (chunk_stripped.startswith(('- ', '• ', '* ')) or
                                   (chunk_stripped.startswith('*') and 
                                    chunk_stripped.endswith('*') and 
                                    ('• ' in chunk_stripped or '- ' in chunk_stripped)))
                is_chunk_heading = chunk_stripped.startswith('#')
                
                # STRICT TYPE MATCHING: Skip if types don't match
                # Don't assign bullets to non-bullet sections and vice versa
                if eng['is_bullets'] != is_chunk_bullets:
                    # Type mismatch - skip this chunk
                    continue
                
                if eng['is_heading'] != is_chunk_heading:
                    # Heading mismatch - skip
                    continue
                
                # Type matching (same types confirmed by above checks)
                if eng['is_bullets'] and is_chunk_bullets:
                    score += 200  # Very strong match for bullets
                if eng['is_heading'] and is_chunk_heading:
                    score += 100
                else:
                    score += 50  # Plain text matching plain text
                
                # Word count similarity (closer is better)
                word_diff = abs(eng['word_count'] - chunk_words)
                if word_diff < 10:
                    score += 50
                elif word_diff < 50:
                    score += 30
                elif word_diff < 100:
                    score += 10
                
                # Position preference (prefer chunks in order)
                if j == len(result_texts):
                    score += 10
                
                if score > best_score:
                    best_score = score
                    best_match = j
            
            if best_match is not None:
                matched_chunk = french_chunks[best_match]
                
                # If English expects bullets but French chunk is wrapped in italic markers, strip them
                if eng['is_bullets']:
                    chunk_stripped = matched_chunk.strip()
                    if chunk_stripped.startswith('*') and chunk_stripped.endswith('*'):
                        # Remove outer italic markers
                        matched_chunk = chunk_stripped[1:-1].strip()
                        print(f"            → Stripped italic markers from bullet section")
                
                result_texts.append(matched_chunk)
                used_chunks.add(best_match)
                print(f"            → Matched French chunk {best_match+1} to English section {i+1} (score: {best_score})")
            else:
                # No good match, use empty
                result_texts.append("")
                print(f"            → No French chunk matched for English section {i+1}")
        
        if len(result_texts) == len(eng_sections):
            print(f"      ✅ Content-based split successful: {len(french_texts)} → {len(result_texts)} texts")
            return result_texts
        else:
            print(f"      ⚠️  Content-based split produced {len(result_texts)} texts, expected {len(eng_sections)}")
            # Pad or trim
            while len(result_texts) < len(eng_sections):
                result_texts.append("")
            return result_texts[:len(eng_sections)]
    
    def _analyze_section_style(self, section):
        """
        Analyze a section to determine its style characteristics.
        
        Returns:
            dict with: is_italic, is_bullets, alignment, text, is_product_list
        """
        style_info = {
            'is_italic': False,
            'is_bullets': False,
            'alignment': 'left',
            'text': '',
            'is_product_list': False  # NEW: Product list (italic, no bullets, semicolon-separated)
        }
        
        # Extract text from section
        if isinstance(section, dict):
            # Check for text_section_content array
            if 'text_section_content' in section and isinstance(section['text_section_content'], list):
                if len(section['text_section_content']) > 0:
                    content = section['text_section_content'][0]
                    if isinstance(content, dict):
                        text = content.get('markdown_text', '')
                        style_info['text'] = text
                        style_info['alignment'] = content.get('text_alignment', 'left')
                        
                        # Check if italic (wrapped in * or starts with *)
                        if isinstance(text, str):
                            is_italic = text.strip().startswith('*') and text.strip().endswith('*')
                            style_info['is_italic'] = is_italic
                            
                            # Check if bullets (starts with -, •, or multiple lines with bullets)
                            lines = text.split('\n')
                            bullet_lines = [l for l in lines if l.strip() and (l.strip().startswith('-') or l.strip().startswith('•'))]
                            has_bullets = len(bullet_lines) >= 2  # At least 2 bullet points
                            style_info['is_bullets'] = has_bullets
                            
                            # NEW: Detect product list (italic, center-aligned, semicolon-separated, NO bullets)
                            # Example: "*Product 1 Item 123; Product 2 Item 456; Product 3 Item 789*"
                            if is_italic and not has_bullets and style_info['alignment'] == 'center':
                                # Check for semicolons (common in product lists)
                                if ';' in text or 'Item ' in text:
                                    style_info['is_product_list'] = True
                                    print(f"            🏷️  Detected product list: center-aligned italic with semicolons")
        
        return style_info
    
    def _extract_small_chunk(self, text, max_words=50):
        """Extract a small chunk of text (for product lists or short sections)"""
        if not text or not text.strip():
            return None
        
        words = text.split()
        if len(words) <= max_words:
            return text.strip()
        
        # Take first max_words words
        chunk = ' '.join(words[:max_words])
        # Try to end at a sentence boundary
        if '.' in chunk:
            last_period = chunk.rfind('.')
            if last_period > len(chunk) // 2:  # Only if period is in second half
                chunk = chunk[:last_period + 1]
        
        return chunk.strip()
    
    def _extract_italic_section(self, french_blob, eng_style):
        """
        Extract the italic section from French text blob.
        Usually the first paragraph or product list.
        """
        if not french_blob:
            return None
        
        # Italic sections are usually short (product lists, captions)
        # Take first paragraph or first line
        lines = french_blob.split('\n')
        
        # Look for a short section at the start (likely product list)
        first_para = []
        for line in lines:
            line = line.strip()
            if not line:
                if first_para:
                    break
            else:
                first_para.append(line)
                # If it's getting long (>100 words), it's probably not an italic section
                if len(' '.join(first_para).split()) > 100:
                    # Take just the first line instead
                    return lines[0].strip() if lines else None
        
        return '\n'.join(first_para) if first_para else None
    
    def _extract_bullet_section(self, french_blob, eng_style):
        """
        Extract bullet list section from French text blob.
        Also normalizes bullet characters to proper markdown list format.
        Ensures each bullet is on its own line.
        
        Handles multiple patterns:
        1. Each line starts with bullet: "• Item1\n• Item2"
        2. First line has bullet, rest are sentences: "• Item1\nSentence2\nSentence3"
        3. Inline bullets: "• Item1 • Item2 • Item3"
        """
        if not french_blob:
            return None
        
        lines = french_blob.split('\n')
        
        # Pattern 1: Check if we have multiple lines starting with bullets
        bullet_lines = [l for l in lines if l.strip() and (l.strip().startswith('•') or l.strip().startswith('-'))]
        
        if len(bullet_lines) >= 2:
            # Multiple bullet lines found - extract them and their continuations
            bullet_section = []
            in_bullets = False
            
            for line in lines:
                line_stripped = line.strip()
                if line_stripped.startswith('•') or line_stripped.startswith('-'):
                    in_bullets = True
                    bullet_section.append(line)
                elif in_bullets and line_stripped:
                    # Continuation or new paragraph
                    if not line_stripped[0].isupper() or len(line_stripped) < 50:
                        bullet_section.append(line)
                    else:
                        break
                elif in_bullets and not line_stripped:
                    bullet_section.append(line)
            
            # Normalize bullets
            return self._normalize_bullets_in_lines(bullet_section)
        
        # Pattern 2: Check if first line has bullet and rest are sentences
        # This means AI translated bullet list as a paragraph
        if lines and (lines[0].strip().startswith('•') or lines[0].strip().startswith('-')):
            # First line has bullet, rest might be separate items
            # Check if we have sentence-like structures that should be bullets
            all_text = french_blob
            
            # Look for patterns that indicate separate bullet items:
            # - Starting with capital letter after period
            # - Each sentence is substantial (>30 chars)
            import re
            
            # Split by periods followed by capital letters or newlines
            # This converts: "• Item1. Item2. Item3." → ["• Item1", "Item2", "Item3"]
            sentences = re.split(r'\.[\s\n]+(?=[A-ZÀ-Ÿ])', all_text)
            
            if len(sentences) >= 2:
                # Format each sentence as a bullet
                formatted_bullets = []
                for i, sentence in enumerate(sentences):
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    # Remove existing bullet from first sentence
                    sentence = re.sub(r'^[•\-]\s*', '', sentence)
                    
                    # Add markdown bullet
                    if sentence:
                        formatted_bullets.append(f"- {sentence}")
                
                if len(formatted_bullets) >= 2:
                    return '\n'.join(formatted_bullets)
        
        # Pattern 3: Inline bullets within text
        if '•' in french_blob and '\n' not in french_blob:
            return self._extract_and_format_inline_bullets(french_blob)
        
        return None
    
    def _normalize_bullets_in_lines(self, lines):
        """Normalize bullet characters in a list of lines"""
        import re
        normalized = []
        for line in lines:
            if '•' in line:
                line = re.sub(r'^(\s*)•\s*', r'\1- ', line)
            normalized.append(line)
        return '\n'.join(normalized)
    
    def _extract_and_format_inline_bullets(self, text):
        """
        Extract bullets that might be within paragraphs and format as proper list.
        Example: "Text. • Item 1 • Item 2" → "- Item 1\n- Item 2"
        """
        import re
        
        # Check if text contains bullet points
        if '•' not in text:
            return None
        
        # Split by bullet points
        parts = re.split(r'[•]', text)
        
        # First part might be non-bullet text (intro)
        result_lines = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            
            if i == 0 and not any(part.lower().startswith(word) for word in ['par', 'l\'', 'le', 'la', 'les', 'un', 'une', 'des']):
                # First part might be intro text, skip if too long
                if len(part) < 100:
                    # Keep as intro
                    result_lines.append(part)
                continue
            
            # This is a bullet item
            result_lines.append(f"- {part}")
        
        return '\n'.join(result_lines) if len(result_lines) >= 2 else None
    
    def _split_combined_text(self, combined_text, num_parts):
        """
        Split a combined French text into multiple parts based on patterns.
        
        Strategies:
        1. Split by bold headers and separate content after them
        2. Split by double newlines
        3. If still one chunk, return it
        
        Args:
            combined_text: Single combined French text
            num_parts: Expected number of parts (from English structure)
        
        Returns:
            List of text parts (normalized with proper formatting)
        """
        if not combined_text or num_parts <= 1:
            return [combined_text] if combined_text else []
        
        import re
        
        # Strategy 1: Split by bold markdown headers, keeping headers separate from content
        # Pattern: **TEXT** (bold headers like **CROÛTE**, **GARNITURE**)
        bold_pattern = r'(\*\*[A-ZÀ-ÿ][^*]*\*\*)'
        
        # Split by bold headers but keep them in the results
        parts = re.split(bold_pattern, combined_text)
        
        # Filter out empty parts and normalize formatting
        normalized_parts = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            
            # Check if this is a bold header (don't modify headers)
            if p.startswith('**') and p.endswith('**'):
                # This is a header - keep as-is, don't wrap in <br>
                normalized_parts.append(p)
                continue
            
            # Normalize list formatting to match English style
            # English uses: " - item\n - item\n - item" with consistent leading space
            # Ensure all list items have consistent formatting
            if ' -' in p or '\n-' in p or '•' in p:
                # This looks like a list - normalize it
                lines = p.split('\n')
                normalized_lines = []
                for line in lines:
                    line_stripped = line.strip()
                    if line_stripped:
                        # If line starts with dash, bullet, or other list marker, normalize to " - "
                        if (line_stripped.startswith('- ') or line_stripped.startswith('-') or 
                            line_stripped.startswith('• ') or line_stripped.startswith('•')):
                            # Remove any list marker and normalize to " - content  "
                            content = line_stripped.lstrip('•-').strip()
                            line_normalized = ' - ' + content + '  '  # Add double space at end for markdown line break
                            normalized_lines.append(line_normalized)
                        else:
                            normalized_lines.append(line_stripped)
                
                # Wrap list in <br> tags to match English format
                p = '<br>\n' + '\n'.join(normalized_lines) + '\n<br>'
            
            normalized_parts.append(p)
        
        parts = normalized_parts
        
        if len(parts) >= num_parts:
            # We have enough parts
            print(f"         → Split by bold headers: {len(parts)} parts")
            return parts[:num_parts]
        elif len(parts) > 1:
            print(f"         → Split by bold headers: {len(parts)} parts (less than expected {num_parts})")
            # We have some parts - better than nothing
            # If we need more parts, try to further split the non-header parts
            if len(parts) < num_parts:
                expanded_parts = []
                for part in parts:
                    # Check if this is a header (starts with **)
                    if part.startswith('**'):
                        expanded_parts.append(part)
                    else:
                        # This is content - try to split it further by double newlines
                        sub_parts = [p.strip() for p in re.split(r'\n\s*\n', part) if p.strip()]
                        if len(sub_parts) > 1:
                            expanded_parts.extend(sub_parts)
                        else:
                            expanded_parts.append(part)
                
                if len(expanded_parts) >= num_parts:
                    print(f"         → Further split to {len(expanded_parts)} parts")
                    return expanded_parts[:num_parts]
                elif len(expanded_parts) > len(parts):
                    return expanded_parts
            
            return parts
        
        # Strategy 2: Split by multiple newlines (paragraph breaks)
        parts = [p.strip() for p in re.split(r'\n\s*\n', combined_text) if p.strip()]
        
        if len(parts) >= num_parts:
            print(f"         → Split by paragraphs: {len(parts)} parts")
            return parts[:num_parts]
        elif len(parts) > 1:
            print(f"         → Split by paragraphs: {len(parts)} parts")
            return parts
        
        # Strategy 3: Can't split meaningfully - return the whole text
        print(f"         → Could not split into {num_parts} parts, returning as single part")
        return [combined_text]
    
    def _map_item_with_texts(self, eng_item, french_texts):
        """
        Map English item structure with French texts, preserving ALL English styling.
        
        Args:
            eng_item: English item structure (e.g., text_content[0])
            french_texts: List of French text strings to insert
            
        Returns:
            Mapped item with French text but English structure/styling
        """
        import copy
        
        # Start with deep copy of English structure
        result = copy.deepcopy(eng_item)
        
        print(f"            🔍 Mapping item with {len(french_texts)} French texts")
        print(f"            📝 English item keys: {list(eng_item.keys()) if isinstance(eng_item, dict) else type(eng_item)}")
        
        # NOTE: We do NOT add any fields that weren't in English
        # If English only has markdown_text, we only send markdown_text
        # ContentStack will use its schema defaults for missing fields
        
        # Find all markdown_text positions in this item
        positions = []
        self._find_text_positions(result, positions, [])
        
        print(f"            📍 Found {len(positions)} text positions: {positions}")
        
        # Replace markdown_text at each position with French text
        for idx, position in enumerate(positions):
            if idx >= len(french_texts):
                # Not enough French texts, repeat the last one
                fr_text = french_texts[-1] if french_texts else ""
                print(f"            ⚠️  Position {idx}: No French text available, using last: '{fr_text[:50]}...'")
            else:
                fr_text = french_texts[idx]
                print(f"            ✅ Position {idx}: Using French text: '{fr_text[:50]}...'")
            
            # Navigate to position and set French text
            # We need to navigate to the PARENT of the final key
            current = result
            eng_current = eng_item
            
            # Navigate through all but the last key
            for key in position[:-1]:
                current = current[key]
                eng_current = eng_current[key]
            
            # Get the final key
            final_key = position[-1]
            
            # Get English text for markdown preservation
            if isinstance(eng_current, dict):
                eng_text = eng_current.get(final_key, "")
            else:
                eng_text = ""
            
            # Apply markdown formatting preservation
            if isinstance(eng_text, str) and isinstance(fr_text, str):
                preserved_text = self._preserve_markdown_formatting(eng_text, fr_text)
            else:
                preserved_text = fr_text
            
            # Set the value in the result
            if isinstance(current, dict):
                current[final_key] = preserved_text
                print(f"            ✅ Set {final_key} = '{preserved_text[:50]}...'")
            elif isinstance(current, list) and isinstance(final_key, int):
                current[final_key] = preserved_text
                print(f"            ✅ Set [{final_key}] = '{preserved_text[:50]}...'")
            else:
                print(f"            ⚠️  Cannot set value at position {position}, current is {type(current)}")
        
        print(f"            📤 Result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        return result
    
    def _map_with_french_texts(self, eng_item, french_texts, depth=0):
        """
        Map English item with French texts, returning (mapped_item, num_texts_used)
        
        CRITICAL: This function must preserve English structure (styling, semantics, layout)
        while only replacing text content. It uses the same KEEP_ENGLISH logic as _replace_content.
        
        Args:
            eng_item: English structure item
            french_texts: List of French texts to map from
            depth: Recursion depth for logging
        
        Returns:
            (mapped_item, num_texts_used)
        """
        if not french_texts:
            return eng_item, 0
        
        # Count how many markdown_text fields this English item has
        eng_text_positions = []
        self._find_text_positions(eng_item, eng_text_positions, [])
        
        num_texts_needed = len(eng_text_positions)
        num_texts_available = min(num_texts_needed, len(french_texts))
        
        if num_texts_needed == 0:
            # English item has no text fields, return as-is
            return eng_item, 0
        
        # FIXED: Create mapped item by replacing texts WHILE preserving English structure
        # Use _replace_texts_with_structure_preservation instead of simple replacement
        mapped_item = self._replace_texts_with_structure_preservation(
            eng_item, eng_text_positions, french_texts[:num_texts_available]
        )
        
        return mapped_item, num_texts_available
    
    def _find_text_positions(self, data, positions, path):
        """Find all markdown_text positions in data structure"""
        if isinstance(data, dict):
            if 'markdown_text' in data:
                markdown_value = data['markdown_text']
                
                # Check if markdown_text is itself a dict (nested structure)
                if isinstance(markdown_value, dict):
                    # Recurse INTO markdown_text to find the actual text field
                    self._find_text_positions(markdown_value, positions, path + ['markdown_text'])
                else:
                    # markdown_text is a string - this is the actual text position
                    positions.append(path + ['markdown_text'])
                
                # Recurse into OTHER keys only (skip markdown_text since we handled it)
                for key, value in data.items():
                    if key != 'markdown_text' and isinstance(value, (dict, list)):
                        self._find_text_positions(value, positions, path + [key])
            else:
                # No markdown_text at this level, recurse normally
                for key, value in data.items():
                    if isinstance(value, (dict, list)):
                        self._find_text_positions(value, positions, path + [key])
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._find_text_positions(item, positions, path + [i])
    
    def _replace_texts_at_positions(self, data, positions, french_texts):
        """Replace texts at specified positions with French texts"""
        import copy
        result = copy.deepcopy(data)
        
        for pos_idx, position in enumerate(positions):
            if pos_idx >= len(french_texts):
                break
            
            # Navigate to the position
            current = result
            for i, key in enumerate(position[:-1]):
                current = current[key]
            
            # Set the French text
            final_key = position[-1]
            if isinstance(current[final_key], dict) and 'markdown_text' in current[final_key]:
                # Nested structure
                current[final_key]['markdown_text'] = french_texts[pos_idx]
            else:
                # Direct string
                current[final_key] = french_texts[pos_idx]
        
        return result
    
    def _replace_texts_with_structure_preservation(self, eng_data, positions, french_texts):
        """
        Replace texts at specified positions while preserving English structure.
        
        This is the CORRECT way to map French texts - it preserves all English styling,
        semantics, and layout fields (select_text_type, select_semantics_type, etc.)
        while only replacing the markdown_text content.
        
        Args:
            eng_data: English data structure
            positions: List of paths to markdown_text fields
            french_texts: List of French text values to insert
            
        Returns:
            Result with French text but English structure preserved
        """
        import copy
        
        # Fields that must ALWAYS keep English value (structural/layout/style)
        KEEP_ENGLISH = {
            'title',
            'text_content_placement', 'text_content_overlay_styles',
            'text_content_above_below_the_ad_styles',
            'ad_type', 'display_style', 'layout', 'alignment', 'direction',
            'overlay_position', 'overlay_fill_type', 'overlay_fill_',
            # CRITICAL: These control text styling and semantics
            'select_text_type', 'select_semantics_type',
            'platform_config_block', 'privacy_toggle',
            'tags', 'uid', '_version', '_content_type_uid', 'locale',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'publish_details', '_metadata', 'ACL',
            # Add text alignment and formatting
            'text_alignment',
            # IMPORTANT: Keep background colors and styling from English
            'background_group', 'background_color', 'text_color', 'border_color',
            'color', 'color_config'
        }
        
        def merge_with_preservation(eng, fr_text_map):
            """
            Merge English structure with French texts, preserving English styling.
            
            Args:
                eng: English structure
                fr_text_map: Dict mapping paths to French text values
                
            Returns:
                Merged result with English structure + French content
            """
            if isinstance(eng, dict):
                result = {}
                for key, eng_value in eng.items():
                    # Always keep English styling/structure fields
                    if key in KEEP_ENGLISH:
                        result[key] = eng_value
                    # Special handling for markdown_text - replace with French
                    elif key == 'markdown_text':
                        # This text might be in our replacement map
                        result[key] = eng_value  # Will be replaced later by path lookup
                    # Recurse into nested structures
                    elif isinstance(eng_value, (dict, list)):
                        result[key] = merge_with_preservation(eng_value, fr_text_map)
                    else:
                        # Keep English value for unknown fields (safer)
                        result[key] = eng_value
                return result
            
            elif isinstance(eng, list):
                return [merge_with_preservation(item, fr_text_map) for item in eng]
            
            else:
                return eng
        
        # Start with English structure
        result = copy.deepcopy(eng_data)
        
        # Now replace only the markdown_text fields at specified positions
        for pos_idx, position in enumerate(positions):
            if pos_idx >= len(french_texts):
                break
            
            # Navigate to the position and replace the text
            current = result
            for i, key in enumerate(position[:-1]):
                current = current[key]
            
            final_key = position[-1]
            if isinstance(current, dict) and final_key in current:
                # Apply markdown formatting preservation
                eng_text = self._get_text_at_position(eng_data, position)
                if eng_text and isinstance(eng_text, str) and isinstance(french_texts[pos_idx], str):
                    current[final_key] = self._preserve_markdown_formatting(eng_text, french_texts[pos_idx])
                else:
                    current[final_key] = french_texts[pos_idx]
        
        return result
    
    def _get_text_at_position(self, data, position):
        """Get text value at a specific position path"""
        current = data
        for key in position:
            if isinstance(current, (dict, list)):
                current = current[key]
            else:
                return None
        return current
    
    def _get_ad_builder_url(self, ad_item):
        """Extract URL from ad_builder item for matching"""
        try:
            # CASE 1: Normal ad_builder with ad_builder_block at top level
            if 'ad_builder_block' in ad_item:
                ref = ad_item['ad_builder_block'].get('ad_builder_ref', [])
                if ref and len(ref) > 0:
                    entry = ref[0].get('entry', {})
                    url = entry.get('costco_url', {}).get('url', '')
                    # Normalize URL (remove https://www.costco.ca prefix if present)
                    if url.startswith('https://www.costco.ca'):
                        url = url.replace('https://www.costco.ca', '')
                    if url:
                        print(f"            🔗 Extracted URL (CASE 1 - top level): {url}")
                    return url
            
            # CASE 2: Embedded ad_builder (inside ad_set_costco)
            # Structure: {_content_type_uid: "ad_builder", entry: {ad_builder_block: {...}}}
            elif 'entry' in ad_item and isinstance(ad_item['entry'], dict):
                entry_data = ad_item['entry']
                if 'ad_builder_block' in entry_data:
                    ref = entry_data['ad_builder_block'].get('ad_builder_ref', [])
                    if ref and len(ref) > 0:
                        entry = ref[0].get('entry', {})
                        url = entry.get('costco_url', {}).get('url', '')
                        # Normalize URL
                        if url.startswith('https://www.costco.ca'):
                            url = url.replace('https://www.costco.ca', '')
                        if url:
                            print(f"            🔗 Extracted URL (CASE 2 - embedded): {url}")
                        return url
            
            # CASE 3: Reference structure {uid, _content_type_uid} - need to fetch the entry
            elif '_content_type_uid' in ad_item and ad_item['_content_type_uid'] == 'ad_builder' and 'uid' in ad_item:
                print(f"            ⚠️  Found reference structure, cannot extract URL without fetching entry")
                return None
                
        except Exception as e:
            print(f"            ❌ Error extracting URL: {e}")
            pass
        
        print(f"            ⚠️  Could not extract URL from ad_item (keys: {list(ad_item.keys()) if isinstance(ad_item, dict) else 'not a dict'})")
        return None
    
    def _match_arrays_by_url(self, eng_array, fr_array):
        """Match arrays of ad_builders by URL, return list of (eng_item, fr_item_or_None) tuples"""
        print(f"         🔗 Matching {len(eng_array)} English ad_builders with {len(fr_array)} French ad_builders by URL...")
        
        # Build a mapping of URL -> French item
        fr_by_url = {}
        for fr_idx, fr_item in enumerate(fr_array):
            print(f"            → French ad_builder {fr_idx + 1}:")
            url = self._get_ad_builder_url(fr_item)
            if url:
                fr_by_url[url] = fr_item
                print(f"               ✅ Mapped to URL: {url}")
            else:
                print(f"               ⚠️  No URL found")
        
        # Match English items to French by URL
        result = []
        for eng_idx, eng_item in enumerate(eng_array):
            print(f"            → English ad_builder {eng_idx + 1}:")
            eng_url = self._get_ad_builder_url(eng_item)
            if eng_url:
                fr_item = fr_by_url.get(eng_url)
                if fr_item:
                    print(f"               ✅ Matched to French ad_builder with URL: {eng_url}")
                else:
                    print(f"               ⚠️  No French match for URL: {eng_url}")
                result.append((eng_item, fr_item))
            else:
                print(f"               ⚠️  Could not extract URL from English item")
                result.append((eng_item, None))
        
        return result
    
    def _append_texts_to_item(self, eng_item, texts_to_append):
        """Append texts to the last text field in English item, formatting as headings if appropriate"""
        import copy
        import re
        result = copy.deepcopy(eng_item)
        
        # Find the last text position
        positions = []
        self._find_text_positions(result, positions, [])
        
        if not positions:
            # No text fields to append to, just return as-is
            return result
        
        # Navigate to last position
        last_position = positions[-1]
        current = result
        for key in last_position[:-1]:
            current = current[key]
        
        final_key = last_position[-1]
        
        # Get existing text
        if isinstance(current[final_key], dict) and 'markdown_text' in current[final_key]:
            existing_text = current[final_key]['markdown_text']
        else:
            existing_text = current[final_key]
        
        # Analyze existing English text to detect heading pattern
        has_heading = bool(re.search(r'\n\s*#{1,6}\s*\*\*', existing_text))
        
        # Append new texts with line breaks
        combined_text = existing_text
        for text in texts_to_append:
            # Detect if this text looks like a heading:
            # - Short text (< 50 chars)
            # - Wrapped in **bold** 
            # - No paragraph breaks
            text_stripped = text.strip()
            is_short = len(text_stripped) < 50
            is_bold = bool(re.match(r'^\*\*(.+?)\*\*$', text_stripped, re.DOTALL))
            has_newlines = '\n' in text_stripped
            
            looks_like_heading = is_short and is_bold and not has_newlines
            
            if looks_like_heading and has_heading:
                # Format as heading to match English structure
                # Remove the bold markers and re-add with heading marker
                heading_text = re.sub(r'^\*\*(.*?)\*\*$', r'\1', text_stripped)
                formatted_text = f'\n\n#**{heading_text}**\n\n'
                combined_text += formatted_text
                print(f"      🔖 Formatted as heading: {text_stripped[:30]}...")
            else:
                # Regular text, just append with line break
                combined_text += '  \n' + text
        
        # Set combined text
        if isinstance(current[final_key], dict) and 'markdown_text' in current[final_key]:
            current[final_key]['markdown_text'] = combined_text
        else:
            current[final_key] = combined_text
        
        return result
    
    def _create_french_component(self, eng_item):
        """Create a French component with English structure but empty content fields"""
        result = {}
        
        # Content fields to clear
        CONTENT_FIELDS = {
            'markdown_text', 'text', 'description', 'caption',
            'meta_title', 'meta_description', 'page_title', 'breadcrumb_title',
            'alt_text', 'image_alt_text', 'mobile_image_alt_text', 'icon_alt_text',
            'disclaimer', 'disclaimer_markdown', 'entry_title', 'link_text'
        }
        
        for key, value in eng_item.items():
            if key in CONTENT_FIELDS:
                # Clear content fields - use empty string for text
                if isinstance(value, str):
                    result[key] = ""
                elif isinstance(value, dict) and 'markdown_text' in value:
                    result[key] = {"markdown_text": ""}
                else:
                    result[key] = value  # Keep structure for other types
            elif isinstance(value, dict):
                # Recurse into nested dicts
                result[key] = self._create_french_component(value)
            elif isinstance(value, list):
                # Recurse into lists
                result[key] = [self._create_french_component(item) if isinstance(item, dict) else item for item in value]
            else:
                # Keep English value for structural fields
                result[key] = value
        
        return result
    
    def _replace_content(self, eng, fr):
        """Recursively replace content fields from French to English structure"""
        # Content fields that should be replaced
        CONTENT_FIELDS = {
            'markdown_text', 'text', 'description', 'caption',
            'meta_title', 'meta_description', 'page_title', 'breadcrumb_title',
            'alt_text', 'image_alt_text', 'mobile_image_alt_text', 'icon_alt_text',
            'disclaimer', 'disclaimer_markdown', 'entry_title', 'link_text',
            'rich_text_editor'  # For custom_rich_text components
        }
        
        # CRITICAL: 'title' is NOT in CONTENT_FIELDS - must keep English title!
        # If title changes, ContentStack creates NEW entry instead of adding locale
        
        # Fields to fully replace (images, assets, links, and content-related flags)
        FULL_REPLACE = {
            'image', 'mobile_image', 'icon_image', 'background_image',
            'logo', 'thumbnail', 'asset', 'file', 'media',
            'costco_url', 'link', 'url',
            # Content control flags - should follow French version
            'enable_text_content', 'enable_caption', 'enable_disclaimer',
            'enable_custom_background', 'enable_sponsored', 'enable_mobile_image_variation'
        }
        
        # Fields that must ALWAYS keep English value (structural/layout/metadata)
        KEEP_ENGLISH = {
            'title',  # Component title must remain same for localization to work
            # Layout and positioning fields - follow English structure
            'text_content_placement', 'text_content_overlay_styles',
            'text_content_above_below_the_ad_styles',
            'ad_type', 'display_style', 'layout', 'alignment', 'direction',
            'overlay_position', 'overlay_fill_type', 'overlay_fill_',
            # Style and formatting - keep English text style types ONLY
            'select_text_type', 'select_semantics_type',
            # Platform and system configuration
            'platform_config_block', 'privacy_toggle',
            # Metadata and system fields - must preserve from English
            'tags', 'uid', '_version', '_content_type_uid', 'locale',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'publish_details', '_metadata', 'ACL'
        }
        
        # Color/styling fields - use French if present AND valid, otherwise keep English
        # CRITICAL: These fields control visual appearance and MUST be preserved from English if French doesn't have them!
        # This allows French AI to override colors while falling back to English styling if missing
        STYLE_FIELDS = {
            'color', 'color_config', 
            'background_color', 'text_color', 'border_color',
            'background_group'  # Background styling configuration
        }
        
        if isinstance(eng, dict) and isinstance(fr, dict):
            result = {}
            for key in eng.keys():
                # ALWAYS keep English value for certain fields
                if key in KEEP_ENGLISH:
                    result[key] = eng[key]
                elif key in fr:
                    # French has this key
                    if key in STYLE_FIELDS:
                        # Style fields: Use French if it has valid content, otherwise keep English
                        # Check if French value is meaningful (not empty dict/list/null)
                        fr_value = fr[key]
                        is_empty_or_null = (
                            fr_value is None or
                            (isinstance(fr_value, dict) and not fr_value) or
                            (isinstance(fr_value, list) and not fr_value) or
                            (isinstance(fr_value, str) and not fr_value.strip())  # Empty string
                        )
                        if is_empty_or_null:
                            # French style field is empty/null, keep English
                            print(f"      ⚠️  French '{key}' is empty/null, using English styling")
                            result[key] = eng[key]
                        else:
                            # French has valid style config, use it
                            result[key] = fr_value
                    elif key in CONTENT_FIELDS:
                        # Special handling for markdown_text: preserve English markdown formatting
                        if key == 'markdown_text' and isinstance(eng[key], str) and isinstance(fr[key], str):
                            # FIRST: Deduplicate French text if it has line-by-line duplication
                            deduplicated_fr_text = self._deduplicate_text(fr[key])
                            # THEN: Preserve markdown formatting from English
                            result[key] = self._preserve_markdown_formatting(eng[key], deduplicated_fr_text)
                        elif isinstance(eng[key], (dict, list)):
                            # Content field is nested (e.g., markdown_text object) - recurse
                            result[key] = self._replace_content(eng[key], fr[key])
                        else:
                            # Replace text content as-is
                            result[key] = fr[key]
                    elif key in FULL_REPLACE:
                        # Fully replace (images, links)
                        result[key] = fr[key]
                    elif isinstance(eng[key], (dict, list)):
                        # Recurse
                        result[key] = self._replace_content(eng[key], fr[key])
                    else:
                        # Keep English structure
                        result[key] = eng[key]
                else:
                    # French doesn't have this key
                    if key in STYLE_FIELDS:
                        # Style field missing in French - keep English styling
                        print(f"      ℹ️  French missing '{key}', using English styling")
                        result[key] = eng[key]
                    else:
                        # Keep English value
                        result[key] = eng[key]
            
            # SPECIAL FIX: Check if text_content has image markdown
            # If English text_content[0] has image markdown and French doesn't,
            # we kept the English image markdown, so we need to clear French image array
            # to avoid showing two images (one from markdown, one from image array)
            if 'text_content' in result and isinstance(result['text_content'], list):
                if len(result['text_content']) > 0:
                    first_item_text = self._get_markdown_text_from_item(result['text_content'][0])
                    if self._is_image_markdown(first_item_text):
                        # text_content has image markdown, clear image arrays to avoid duplication
                        if 'image' in result and result['image']:
                            print(f"      🖼️  Clearing 'image' array (image is in text_content markdown)")
                            result['image'] = []
                        if 'mobile_image' in result and result['mobile_image']:
                            print(f"      🖼️  Clearing 'mobile_image' array (image is in text_content markdown)")
                            result['mobile_image'] = []
            
            return result
        
        elif isinstance(eng, list) and isinstance(fr, list):
            # Handle array length mismatches
            if len(eng) != len(fr):
                # Check if this looks like text_section_group by looking for text_section_content
                looks_like_section_groups = (
                    len(fr) > 0 and len(eng) > 0 and
                    isinstance(fr[0], dict) and isinstance(eng[0], dict) and
                    'text_section_content' in fr[0] and 'text_section_content' in eng[0]
                )
                
                if looks_like_section_groups:
                    print(f"      📊 Text section group detected: English {len(eng)} sections | French {len(fr)} sections")
                    
                    # STEP 1: First, split French sections that have multiple text_section_content items
                    # This handles cases where French combines heading+body in one section
                    print(f"      → Step 1: Splitting French sections with multiple items...")
                    expanded_fr = []
                    for fr_section in fr:
                        text_items = fr_section.get('text_section_content', [])
                        if len(text_items) > 1:
                            # Split this section into multiple sections (one per text item)
                            print(f"         → Splitting section with {len(text_items)} items")
                            for text_item in text_items:
                                new_section = fr_section.copy()
                                new_section['text_section_content'] = [text_item]
                                expanded_fr.append(new_section)
                        else:
                            # Keep as-is
                            expanded_fr.append(fr_section)
                    
                    if len(expanded_fr) != len(fr):
                        print(f"         → Expanded from {len(fr)} to {len(expanded_fr)} French sections")
                        fr = expanded_fr
                    
                    # STEP 2: Now use word-count based alignment to combine/match sections
                    print(f"      → Step 2: Word-count based alignment...")
                    # STEP 2: Now use word-count based alignment to combine/match sections
                    print(f"      → Step 2: Word-count based alignment...")
                    
                    # Helper function to count words in a section
                    def count_section_words(section):
                        """Count total words in all text_section_content items"""
                        if not isinstance(section, dict):
                            return 0
                        text_items = section.get('text_section_content', [])
                        total_words = 0
                        for item in text_items:
                            if isinstance(item, dict):
                                text = item.get('markdown_text', '')
                                # Remove markdown formatting and count words
                                clean_text = text.replace('**', '').replace('*', '').replace('\n', ' ')
                                words = len([w for w in clean_text.split() if w.strip()])
                                total_words += words
                        return total_words
                    
                    # Get word counts for all sections
                    eng_word_counts = [count_section_words(s) for s in eng]
                    fr_word_counts = [count_section_words(s) for s in fr]
                    
                    print(f"         English word counts: {eng_word_counts}")
                    print(f"         French word counts:  {fr_word_counts}")
                    
                    # Try to align French sections with English sections based on word counts
                    aligned_fr = []
                    fr_idx = 0
                    tolerance = 0.20  # 20% tolerance (French translations are often 10-15% different)
                    
                    for eng_idx, eng_section in enumerate(eng):
                        eng_words = eng_word_counts[eng_idx]
                        
                        if fr_idx >= len(fr):
                            # No more French sections left
                            print(f"         → Section {eng_idx + 1}: ⚠️ No French section available!")
                            break
                        
                        # Start with current French section
                        combined_words = 0
                        sections_to_combine = []
                        
                        # Try to find French sections that match this English section's word count
                        temp_idx = fr_idx
                        while temp_idx < len(fr):
                            test_words = combined_words + fr_word_counts[temp_idx]
                            
                            # Check if adding this section gets us closer to target
                            if combined_words == 0:
                                # First section, always include
                                sections_to_combine.append(fr[temp_idx])
                                combined_words = test_words
                                temp_idx += 1
                                
                                # If word count is close enough, stop here
                                if eng_words > 0:
                                    ratio = combined_words / eng_words
                                    if 1.0 - tolerance <= ratio <= 1.0 + tolerance:
                                        break
                            else:
                                # Check if adding this section overshoots too much
                                current_ratio = combined_words / eng_words if eng_words > 0 else 1.0
                                new_ratio = test_words / eng_words if eng_words > 0 else 1.0
                                
                                # If we're already within tolerance, stop
                                if 1.0 - tolerance <= current_ratio <= 1.0 + tolerance:
                                    break
                                
                                # If adding this section gets us closer, include it
                                if abs(new_ratio - 1.0) < abs(current_ratio - 1.0):
                                    sections_to_combine.append(fr[temp_idx])
                                    combined_words = test_words
                                    temp_idx += 1
                                else:
                                    # Would overshoot, stop here
                                    break
                        
                        # Combine the selected French sections
                        if len(sections_to_combine) == 1:
                            combined_section = sections_to_combine[0]
                            print(f"         → Section {eng_idx + 1}: 1 French section ({combined_words} words ≈ {eng_words} words)")
                        elif len(sections_to_combine) > 1:
                            # Combine multiple French sections into one
                            print(f"         → Section {eng_idx + 1}: Combining {len(sections_to_combine)} French sections ({combined_words} words ≈ {eng_words} words)")
                            combined_section = sections_to_combine[0].copy()
                            all_text_items = []
                            for sec in sections_to_combine:
                                all_text_items.extend(sec.get('text_section_content', []))
                            
                            # Merge text items - combine their markdown_text with \n\n
                            combined_text = '\n\n'.join([
                                item.get('markdown_text', '') for item in all_text_items if item.get('markdown_text')
                            ])
                            combined_section['text_section_content'] = [all_text_items[0].copy()]
                            combined_section['text_section_content'][0]['markdown_text'] = combined_text
                        else:
                            # No sections to combine (shouldn't happen)
                            print(f"         → Section {eng_idx + 1}: ⚠️ No French sections matched!")
                            break
                        
                        aligned_fr.append(combined_section)
                        fr_idx = temp_idx
                    
                    # Check if alignment was successful
                    if len(aligned_fr) == len(eng):
                        print(f"      ✅ Successfully aligned {len(aligned_fr)} French sections to {len(eng)} English sections")
                        fr = aligned_fr
                    else:
                        print(f"      ⚠️ Alignment incomplete: {len(aligned_fr)} sections (expected {len(eng)})")
                        
                        # SPECIAL CASE: If we have fewer French sections than needed, try splitting large French sections
                        if len(aligned_fr) < len(eng) and len(aligned_fr) > 0:
                            print(f"         → Attempting to split large French sections to reach {len(eng)} sections...")
                            
                            # Find sections that are much larger than their English counterparts
                            sections_to_split = []
                            for i, fr_sec in enumerate(aligned_fr):
                                if i >= len(eng):
                                    break
                                eng_words = eng_word_counts[i]
                                fr_words = count_section_words(fr_sec)
                                
                                # If French section is 2x+ larger, it likely contains multiple English sections
                                if fr_words > eng_words * 1.8:
                                    sections_needed = int((fr_words / eng_words) + 0.5)  # Round
                                    sections_to_split.append((i, fr_sec, sections_needed))
                                    print(f"            → French section {i+1} has {fr_words} words (expected ~{eng_words}), should split into ~{sections_needed} parts")
                            
                            if sections_to_split:
                                # Split the large French sections
                                new_aligned_fr = []
                                sections_added = 0
                                
                                for fr_idx, fr_sec in enumerate(aligned_fr):
                                    # Check if this section should be split
                                    should_split = False
                                    split_count = 1
                                    for split_idx, split_sec, split_n in sections_to_split:
                                        if split_idx == fr_idx:
                                            should_split = True
                                            split_count = min(split_n, len(eng) - len(new_aligned_fr))  # Don't create too many
                                            break
                                    
                                    if should_split and split_count > 1:
                                        # Extract text from this section
                                        text_items = fr_sec.get('text_section_content', [])
                                        if text_items:
                                            combined_text = '\n\n'.join([
                                                item.get('markdown_text', '') for item in text_items if item.get('markdown_text')
                                            ])
                                            
                                            print(f"            → Splitting French section {fr_idx+1} with text: {combined_text[:100]}...")
                                            
                                            # SMART SPLITTING LOGIC:
                                            # 1. First check if we have a bullet list that should stay together
                                            # 2. Detect distinct content types (title, subtitle, body with bullets)
                                            # 3. Split accordingly
                                            
                                            # Split by paragraphs (double newlines) first
                                            paragraphs = [p.strip() for p in combined_text.split('\n\n') if p.strip()]
                                            
                                            print(f"            → Found {len(paragraphs)} paragraph blocks")
                                            
                                            # Check if any paragraph is a bullet list (contains multiple lines starting with bullet markers)
                                            bullet_markers = ['•', '-', '*', '–', '—']
                                            processed_paras = []
                                            
                                            for para in paragraphs:
                                                lines = para.split('\n')
                                                # Check if this is a bullet list (multiple lines with bullet markers)
                                                bullet_lines = [l.strip() for l in lines if any(l.strip().startswith(m) for m in bullet_markers)]
                                                
                                                if len(bullet_lines) >= 2:
                                                    # This is a bullet list - treat as single unit
                                                    print(f"               → Detected bullet list with {len(bullet_lines)} items")
                                                    processed_paras.append(para)
                                                elif len(lines) > 1:
                                                    # Multiple lines but not bullets - might be title + subtitle combined
                                                    # Check if first line is much shorter (likely title/heading)
                                                    first_line_words = len(lines[0].split())
                                                    rest_words = sum(len(l.split()) for l in lines[1:])
                                                    
                                                    if first_line_words < 10 and rest_words > 20:
                                                        # First line is short (title/heading), rest is body
                                                        print(f"               → Detected heading + body, splitting into 2 parts")
                                                        processed_paras.append(lines[0].strip())
                                                        processed_paras.append('\n'.join(lines[1:]).strip())
                                                    else:
                                                        # Treat as single paragraph
                                                        processed_paras.append(para)
                                                else:
                                                    # Single line paragraph
                                                    processed_paras.append(para)
                                            
                                            paragraphs = processed_paras
                                            print(f"            → After smart processing: {len(paragraphs)} sections to distribute into {split_count} target sections")
                                            
                                            if len(paragraphs) >= split_count:
                                                # Distribute paragraphs across sections
                                                paras_per_section = len(paragraphs) // split_count
                                                remainder = len(paragraphs) % split_count
                                                
                                                para_idx = 0
                                                for split_i in range(split_count):
                                                    # Calculate how many paragraphs for this section
                                                    paras_this_section = paras_per_section + (1 if split_i < remainder else 0)
                                                    section_paras = paragraphs[para_idx:para_idx + paras_this_section]
                                                    para_idx += paras_this_section
                                                    
                                                    # Create new section with these paragraphs
                                                    new_section = fr_sec.copy()
                                                    
                                                    # Get corresponding English section for styling
                                                    eng_section_idx = len(new_aligned_fr) + split_i
                                                    if eng_section_idx < len(eng):
                                                        eng_text_items = eng[eng_section_idx].get('text_section_content', [])
                                                        if eng_text_items:
                                                            # Copy styling from English section
                                                            new_text_item = eng_text_items[0].copy()
                                                            # Replace only the markdown_text with French content
                                                            new_text_item['markdown_text'] = '\n\n'.join(section_paras)
                                                            new_section['text_section_content'] = [new_text_item]
                                                        else:
                                                            # Fallback: use French styling
                                                            new_section['text_section_content'] = [text_items[0].copy()]
                                                            new_section['text_section_content'][0]['markdown_text'] = '\n\n'.join(section_paras)
                                                    else:
                                                        # No English section to match, use French styling
                                                        new_section['text_section_content'] = [text_items[0].copy()]
                                                        new_section['text_section_content'][0]['markdown_text'] = '\n\n'.join(section_paras)
                                                    
                                                    new_aligned_fr.append(new_section)
                                                    sections_added += 1
                                                
                                                print(f"            → Split French section {fr_idx+1} into {split_count} parts ({paras_per_section}-{paras_per_section+1} paragraphs each)")
                                            else:
                                                # Not enough paragraphs, use as-is
                                                new_aligned_fr.append(fr_sec)
                                                sections_added += 1
                                        else:
                                            new_aligned_fr.append(fr_sec)
                                            sections_added += 1
                                    else:
                                        new_aligned_fr.append(fr_sec)
                                        sections_added += 1
                                
                                if len(new_aligned_fr) >= len(eng):
                                    print(f"         ✅ Successfully split into {len(new_aligned_fr)} sections (target: {len(eng)})")
                                    aligned_fr = new_aligned_fr[:len(eng)]  # Trim if we created too many
                                    # IMPORTANT: Update fr to point to aligned_fr to prevent duplication
                                    # and mark all sections as processed
                                    fr = aligned_fr
                                    fr_idx = len(aligned_fr)  # Mark all as processed
                                else:
                                    print(f"         ⚠️  Split produced {len(new_aligned_fr)} sections (target: {len(eng)}), keeping as-is")
                                    # Split didn't produce enough sections, keep what we have
                                    aligned_fr = new_aligned_fr
                                    fr = aligned_fr  # Update fr reference
                                    fr_idx = len(aligned_fr)  # Mark current sections as processed
                        
                        # Only add remaining sections if we didn't successfully split AND have more original sections
                        # Check against ORIGINAL fr array that was passed in (before we reassigned it)
                        if len(aligned_fr) < len(eng):
                            print(f"         Keeping partial alignment + remaining French sections")
                            # Note: fr_idx and fr might have been updated by split logic above
                            # Only add remaining if there are actually more sections
                            original_fr_count = len(expanded_fr) if 'expanded_fr' in locals() else len(fr)
                            if fr_idx < original_fr_count:
                                print(f"         → Adding {original_fr_count - fr_idx} remaining sections")
                                # This should rarely happen now that we have split logic
                        
                        fr = aligned_fr
            
            # After alignment, array length mismatches
            if len(eng) != len(fr):
                # Special case: English has fewer items than French
                # Strategy: Follow English structure, extract French text in order, map sequentially
                if len(eng) < len(fr):
                    # Edge case: English is empty, French has items - just return French
                    if len(eng) == 0:
                        print(f"      ℹ️  English array is empty, using French array as-is")
                        return fr
                    
                    print(f"      ⚠️  Array mismatch: English has {len(eng)} items, French has {len(fr)} items")
                    print(f"      → Strategy: Follow English structure, map French text in order")
                    
                    # Extract all markdown_text from French in order (flatten)
                    french_texts = []
                    self._extract_texts(fr, french_texts)
                    print(f"      → Extracted {len(french_texts)} text items from French")
                    
                    # Map French texts to English structure in order
                    result = []
                    text_index = 0
                    for eng_item in eng:
                        if text_index >= len(french_texts):
                            # No more French texts - create empty French item instead of keeping English
                            print(f"      ⚠️  No more French texts for English item {len(result)}, creating empty item")
                            empty_item = self._create_french_component(eng_item)
                            result.append(empty_item)
                        else:
                            # Map with next French text(s)
                            mapped_item, texts_used = self._map_with_french_texts(
                                eng_item, french_texts[text_index:], 0
                            )
                            result.append(mapped_item)
                            text_index += texts_used
                    
                    # If there are leftover French texts, append them to the last English item
                    if text_index < len(french_texts):
                        leftover_texts = french_texts[text_index:]
                        print(f"      → {len(leftover_texts)} leftover French texts - appending to last English item")
                        result[-1] = self._append_texts_to_item(result[-1], leftover_texts)
                    
                    return result
                
                # If English has more items than French, intelligently split or create
                else:
                    # Edge case: French is empty - keep English structure as-is
                    if len(fr) == 0:
                        print(f"      ℹ️  French array is empty, keeping English structure")
                        return eng
                    
                    # SPECIAL CASE: text_content with image markdown
                    # English has image markdown in first item, but French doesn't (image elsewhere)
                    # Keep English image markdown, map French text to remaining English items
                    image_markdown_result = self._handle_text_content_mismatch(eng, fr)
                    if image_markdown_result is not None:
                        print(f"      ✅ Handled text_content image markdown mismatch")
                        return image_markdown_result
                    
                    # SPECIAL CASE: ad_builder splitting
                    # If English has 2 ad_builders (image-only + text-only) and French has 1 (image+text)
                    # Split the French ad_builder content between the two English ad_builders
                    if (len(eng) == 2 and len(fr) == 1 and 
                        self._is_ad_builder_array(eng) and self._is_ad_builder_array(fr)):
                        
                        print(f"      🔀 Special case: Splitting French ad_builder into 2 English ad_builders")
                        return self._split_french_ad_builder(eng, fr)
                    
                    # SMART HANDLING: Check if this looks like text_section_content with combined French text
                    # Detect: English has multiple items, French has fewer (often 1) with combined text
                    # Solution: Flatten French texts and remap to English structure
                    print(f"      ⚠️  Array length mismatch: English={len(eng)}, French={len(fr)}")
                    
                    # DEBUG: Show English structure
                    if len(eng) > 0:
                        print(f"      🔍 DEBUG: English item[0] keys: {list(eng[0].keys()) if isinstance(eng[0], dict) else type(eng[0])}")
                        if isinstance(eng[0], dict) and len(eng[0].keys()) > 5:
                            print(f"      🔍 DEBUG: English item[0] has {len(eng[0].keys())} fields (full structure)")
                        elif isinstance(eng[0], dict):
                            print(f"      🔍 DEBUG: English item[0] only has: {eng[0].keys()}")
                    
                    # DEBUG: Extract English texts first to see what was sent for translation
                    english_texts = []
                    self._extract_texts(eng, english_texts)
                    print(f"      🔍 DEBUG: English has {len(english_texts)} texts:")
                    for idx, eng_text in enumerate(english_texts[:3]):  # Show first 3
                        print(f"         [{idx}]: '{eng_text[:80]}...'")
                    
                    # Extract all French texts (might be combined in fewer items)
                    french_texts = []
                    self._extract_texts(fr, french_texts)
                    
                    print(f"      🔍 DEBUG: French has {len(french_texts)} texts:")
                    for idx, fr_text in enumerate(french_texts[:3]):  # Show first 3
                        print(f"         [{idx}]: '{fr_text[:80]}...'")
                    
                    # SMART GROUPING: Combine heading + body patterns in French texts
                    # When French has [heading, body, heading, body...] and English has [heading+body, heading+body...]
                    # we should combine them before mapping
                    print(f"      → Extracted {len(french_texts)} French texts, checking for heading+body patterns...")
                    grouped_texts = []
                    i = 0
                    while i < len(french_texts):
                        text = french_texts[i]
                        # Check if this looks like a heading (short, bold, no newlines)
                        is_heading = (
                            len(text) < 100 and
                            text.strip().startswith('**') and
                            text.strip().endswith('**') and
                            '\n' not in text.strip()
                        )
                        
                        # If heading and there's a next text, combine them
                        if is_heading and i + 1 < len(french_texts):
                            next_text = french_texts[i + 1]
                            # Combine heading with body
                            combined = f"{text}\n\n{next_text}"
                            grouped_texts.append(combined)
                            print(f"         → Combined heading+body: '{text[:30]}...' + body")
                            i += 2  # Skip both texts
                        else:
                            grouped_texts.append(text)
                            i += 1
                    
                    if len(grouped_texts) < len(french_texts):
                        print(f"      → Grouped into {len(grouped_texts)} texts (combined heading+body patterns)")
                        french_texts = grouped_texts
                    
                    # Extract all English text positions  
                    eng_text_count = 0
                    for eng_item in eng:
                        positions = []
                        self._find_text_positions(eng_item, positions, [])
                        eng_text_count += len(positions)
                    
                    print(f"      → English has {len(eng)} items with {eng_text_count} text fields")
                    print(f"      → French has {len(fr)} items with {len(french_texts)} text values")
                    
                    # Special case: French has 1 combined text and English has multiple items
                    # Try to split the French text intelligently
                    if len(french_texts) == 1 and len(eng) > 1 and eng_text_count > 1:
                        print(f"      → Detected combined French text - attempting to split into {eng_text_count} parts")
                        split_texts = self._split_combined_text(french_texts[0], eng_text_count)
                        if len(split_texts) > 1:
                            print(f"      → Successfully split into {len(split_texts)} parts")
                            french_texts = split_texts
                        else:
                            print(f"      → Could not split text, will use as-is")
                    
                    # NEW: Check if we have fewer French texts than English and they might need splitting
                    # This handles cases like: French has 3 texts but one of them is actually 2 combined (author + body)
                    elif len(french_texts) < eng_text_count:
                        print(f"      → French has {len(french_texts)} texts but English needs {eng_text_count}")
                        print(f"      → Checking if any French texts contain multiple sections...")
                        
                        # Calculate how many more texts we need
                        texts_needed = eng_text_count - len(french_texts)
                        print(f"      → Need {texts_needed} more text(s) to match English")
                        
                        # Try to split each French text that looks combined
                        expanded_texts = []
                        texts_added = 0
                        
                        for idx, french_text in enumerate(french_texts):
                            # Check if this text looks like it contains multiple sections
                            # Indicators: author byline, multiple paragraphs, etc.
                            if self._looks_like_combined_text(french_text):
                                # Use special author-body splitter that keeps all body paragraphs together
                                split_texts = self._split_author_from_body(french_text)
                                if len(split_texts) > 1:
                                    print(f"         → Split text into {len(split_texts)} parts (author + body)")
                                    expanded_texts.extend(split_texts)
                                    texts_added += len(split_texts) - 1
                                else:
                                    expanded_texts.append(french_text)
                            # ENHANCED: Also split texts with multiple paragraphs
                            # BUT: Only if we still need more texts and this split would help
                            elif '\n\n' in french_text and len(french_text) > 300 and texts_added < texts_needed:
                                # Text has paragraph breaks and is substantial
                                paragraphs = [p.strip() for p in french_text.split('\n\n') if p.strip()]
                                
                                # Smart decision: Only split if it gets us closer to the target
                                # and the paragraphs are substantial (not just short fragments)
                                min_paragraph_length = 100  # Avoid splitting into tiny fragments
                                substantial_paragraphs = [p for p in paragraphs if len(p) >= min_paragraph_length]
                                
                                if len(substantial_paragraphs) >= 2 and texts_added + len(substantial_paragraphs) - 1 <= texts_needed:
                                    # Split makes sense
                                    print(f"         → Split text[{idx}] into {len(substantial_paragraphs)} substantial paragraphs")
                                    expanded_texts.extend(substantial_paragraphs)
                                    texts_added += len(substantial_paragraphs) - 1
                                elif len(paragraphs) >= 2 and texts_added < texts_needed:
                                    # Need more texts, split anyway (even if paragraphs are short)
                                    print(f"         → Split text[{idx}] into {len(paragraphs)} paragraphs (needed more texts)")
                                    expanded_texts.extend(paragraphs)
                                    texts_added += len(paragraphs) - 1
                                else:
                                    # Don't split - would overshoot or paragraphs too small
                                    print(f"         → Kept text[{idx}] together ({len(paragraphs)} paragraphs, but better as one)")
                                    expanded_texts.append(french_text)
                            else:
                                expanded_texts.append(french_text)
                        
                        if len(expanded_texts) > len(french_texts):
                            print(f"      → Expanded from {len(french_texts)} to {len(expanded_texts)} texts (added {texts_added})")
                            french_texts = expanded_texts
                        else:
                            print(f"      → No expansion needed, keeping {len(french_texts)} texts")
                    
                    # CRITICAL: Before flatten-remap, check if English has style boundaries
                    # If yes, split French text at corresponding boundaries
                    if len(french_texts) < len(eng) and len(french_texts) > 0:
                        style_aware_texts = self._split_by_style_boundaries(eng, french_texts)
                        if len(style_aware_texts) > len(french_texts):
                            print(f"      → Style-aware split: {len(french_texts)} → {len(style_aware_texts)} texts")
                            french_texts = style_aware_texts
                    
                    # If French has fewer items but similar or more text content, use flatten-remap strategy
                    if len(french_texts) >= eng_text_count * 0.5:  # At least 50% of English text count
                        print(f"      → Using flatten-remap strategy")
                        result = []
                        text_index = 0
                        
                        # CRITICAL: Must create same number of items as English to maintain structure
                        for item_idx, eng_item in enumerate(eng):
                            # Count how many text fields this English item needs
                            eng_positions = []
                            self._find_text_positions(eng_item, eng_positions, [])
                            texts_needed = len(eng_positions)
                            
                            if texts_needed == 0:
                                # No text fields in this item, keep English structure
                                result.append(eng_item)
                                continue
                            
                            # Get French texts for this item
                            if text_index < len(french_texts):
                                # Calculate how many French texts to use for this item
                                # Strategy: Distribute remaining texts proportionally
                                remaining_eng_items = len(eng) - item_idx
                                remaining_fr_texts = len(french_texts) - text_index
                                
                                # Average texts per remaining item
                                avg_texts_per_item = max(1, remaining_fr_texts // remaining_eng_items)
                                texts_to_use = min(texts_needed, avg_texts_per_item, remaining_fr_texts)
                                
                                # If this is the last item, use all remaining texts
                                if item_idx == len(eng) - 1:
                                    texts_to_use = remaining_fr_texts
                                
                                # Map with available French texts
                                fr_texts_for_item = french_texts[text_index:text_index + texts_to_use]
                                mapped_item = self._map_item_with_texts(eng_item, fr_texts_for_item)
                                result.append(mapped_item)
                                text_index += texts_to_use
                            else:
                                # No more French texts, but we MUST include this item to maintain array length
                                # Use last French text as placeholder to avoid empty content
                                print(f"         ⚠️  Item {item_idx + 1}: No French texts remaining, using last text as placeholder")
                                if french_texts:
                                    last_text = french_texts[-1]
                                    mapped_item = self._map_item_with_texts(eng_item, [last_text])
                                    result.append(mapped_item)
                                else:
                                    # Shouldn't happen, but keep English as fallback
                                    result.append(eng_item)
                        
                        print(f"         → Created {len(result)} items (same as English) using {len(french_texts)} French texts")
                        
                        # CRITICAL FIX: Check for duplicate items in result array
                        # ContentStack rejects arrays with identical items (422 error)
                        # If all items are identical, only keep the first one
                        if len(result) > 1:
                            # Check if all items have the same markdown_text
                            # Handle both flat and nested markdown_text structures
                            texts_in_result = []
                            for item in result:
                                if isinstance(item, dict) and 'markdown_text' in item:
                                    md_value = item['markdown_text']
                                    # If markdown_text is nested (dict), extract the actual text
                                    if isinstance(md_value, dict) and 'markdown_text' in md_value:
                                        texts_in_result.append(md_value['markdown_text'])
                                    elif isinstance(md_value, str):
                                        texts_in_result.append(md_value)
                            
                            # If all texts are identical, we have duplicates
                            if len(texts_in_result) == len(result) and len(texts_in_result) > 0:
                                # Check if all are the same
                                first_text = texts_in_result[0]
                                all_same = all(t == first_text for t in texts_in_result)
                                
                                if all_same:
                                    print(f"         ⚠️  WARNING: All {len(result)} items have identical content!")
                                    print(f"         ⚠️  ContentStack will reject duplicate items with 422 error")
                                    print(f"         → Keeping only 1 item (removing {len(result)-1} duplicates)")
                                    result = [result[0]]  # Keep only first item
                        
                        return result
                    else:
                        # Default case: Map what we have, create empty items for the rest
                        print(f"      → Mapping {len(fr)} items, creating {len(eng)-len(fr)} empty items")
                        result = []
                        
                        # Map first len(fr) items with French content
                        for i in range(len(fr)):
                            result.append(self._replace_content(eng[i], fr[i]))
                        
                        # Create missing French components based on English structure
                        for i in range(len(fr), len(eng)):
                            print(f"         ✨ Creating French item [{i}] from English structure")
                            french_component = self._create_french_component(eng[i])
                            result.append(french_component)
                        
                        return result
            
            # Match list items by index (same length)
            print(f"      ℹ️  Arrays have equal length ({len(eng)} items)")
            
            # Special case: If this looks like ad_builder array, match by URL instead of position
            if len(eng) > 0 and self._get_ad_builder_url(eng[0]) is not None:
                print(f"      🔗 Detected ad_builder array - matching by URL instead of position")
                matched = self._match_arrays_by_url(eng, fr)
                result = []
                for eng_item, fr_item in matched:
                    if fr_item is not None:
                        eng_url = self._get_ad_builder_url(eng_item)
                        fr_url = self._get_ad_builder_url(fr_item)
                        print(f"         ✅ Matched: {eng_url} = {fr_url}")
                        
                        # CRITICAL FIX: For embedded component references, KEEP the English structure!
                        # These nested components have been localized separately, so we just need
                        # to keep the reference to the same UID, and ContentStack will load fr-ca locale
                        if '_content_type_uid' in eng_item and 'entry' in eng_item:
                            print(f"            → Keeping English reference structure (nested component was localized separately)")
                            result.append(eng_item)  # Keep English reference!
                        else:
                            # Normal ad_builder item, replace content
                            result.append(self._replace_content(eng_item, fr_item))
                    else:
                        eng_url = self._get_ad_builder_url(eng_item)
                        print(f"         ⚠️  No French match for: {eng_url}")
                        # For embedded references, keep English structure; otherwise create French component
                        if '_content_type_uid' in eng_item and 'entry' in eng_item:
                            print(f"            → Keeping English reference structure (no French match)")
                            result.append(eng_item)
                        else:
                            result.append(self._create_french_component(eng_item))
                return result
            
            # Default: Match by position
            print(f"      → Mapping by position (1-to-1)")
            
            # CRITICAL FIX: Use FRENCH array length, not English!
            # If French has fewer items, we should ONLY output those items (not fill with English)
            # This prevents showing English menu items when French has fewer options
            result = []
            
            if len(fr) < len(eng):
                print(f"      ⚠️  French has fewer items ({len(fr)}) than English ({len(eng)})")
                print(f"      → Will use French length (not add English items)")
            
            # Use the SHORTER length (typically French)
            output_length = min(len(eng), len(fr))
            
            for i in range(output_length):
                result.append(self._replace_content(eng[i], fr[i]))
            
            # If French has MORE items than English (rare), append extras
            if len(fr) > len(eng):
                print(f"      ℹ️  French has MORE items ({len(fr)}) than English ({len(eng)})")
                print(f"      → Appending {len(fr) - len(eng)} extra French items")
                for i in range(len(eng), len(fr)):
                    result.append(fr[i])
            
            return result
        
        else:
            # For primitives, keep English structure
            return eng
    
    def localize_component(self, content_type: str, uid: str, french_data: Dict, dry_run=False) -> bool:
        """Localize a single component to fr-ca with better error handling"""
        print(f"\n📤 Localizing {content_type}/{uid}")
        
        if dry_run:
            print(f"   🔍 DRY-RUN: Would update with {len(json.dumps(french_data))} bytes")
            return True
        
        try:
            # Clean data (remove system fields)
            cleaned = self._clean_data(french_data)
            
            # Validate cleaned data has content
            if not cleaned or len(cleaned) == 0:
                print(f"   ⚠️  WARNING: Cleaned data is empty - skipping localization")
                return False
            
            # Validate structure before sending
            validation_errors = self._validate_structure(content_type, cleaned)
            if validation_errors:
                print(f"   ⚠️  VALIDATION ERRORS found:")
                for error in validation_errors:
                    print(f"      ❌ {error}")
                print(f"   💾 Saving invalid payload to debug file...")
                self._save_debug_payload(content_type, uid, cleaned, validation_errors)
                return False
            
            # CRITICAL: Check if entry exists in French locale
            # If not, we need to create it first (not update)
            print(f"   🔍 Checking if entry exists in fr-ca locale...")
            check_response = self.api.get_entry(content_type, uid, locale=self.locale)
            entry_exists = check_response and 'entry' in check_response
            
            # Determine if we need to unlocalize first (for re-localized entries with stale cache)
            needs_unlocalize = False
            if entry_exists:
                existing_entry = check_response.get('entry', {})
                
                # FIXED: Check if ANY substantial field exists (not just page_components)
                # This works for ALL component types (link_list, ad_builder, text_builder, etc.)
                has_data = False
                found_fields = []
                
                # Check for common fields that indicate localized content
                check_fields = [
                    'page_components',  # feature_page
                    'title',            # all entries
                    'color_config',     # link_list
                    'text_content',     # ad_builder, text_builder
                    'background_group', # ad_builder
                    'link_list_items',  # link_list
                    'flyout_references' # link_list_with_flyout_references
                ]
                
                for field in check_fields:
                    if field in existing_entry and existing_entry[field]:
                        has_data = True
                        found_fields.append(field)
                
                if has_data:
                    print(f"   🔄 Detected RE-LOCALIZATION (entry already has fr-ca data)")
                    print(f"      Found existing fields: {', '.join(found_fields)}")
                    print(f"   🗑️  Will DELETE French locale data first to clear ContentStack cache")
                    needs_unlocalize = True
                else:
                    print(f"   ℹ️  Entry exists but has no substantial data (first-time localization)")

            
            if not entry_exists:
                print(f"   ⚠️  Entry does not exist in fr-ca locale - ContentStack may auto-create it on update")
                # ContentStack usually auto-creates the locale when you update
                # But if this fails, it means the entry itself doesn't exist (not just the locale)
            
            # AGGRESSIVE FIX: For re-localizations, delete French locale completely first
            if needs_unlocalize:
                try:
                    print(f"   🗑️  Step 1/2: Deleting existing French locale data...")
                    unlocalize_result = self.api.unlocalize_entry(content_type, uid, locale=self.locale)
                    if unlocalize_result.get('success'):
                        print(f"   ✅ French locale data deleted successfully")
                        # Small delay to ensure ContentStack processes the deletion
                        import time
                        time.sleep(0.5)
                    else:
                        print(f"   ⚠️  Warning: Unlocalize returned non-success, continuing anyway")
                except Exception as unlocalize_error:
                    print(f"   ⚠️  Warning: Unlocalize failed ({str(unlocalize_error)}), will try update anyway")
            
            # Update entry with fr-ca locale (creates new if we just deleted it)
            print(f"   📝 {'Step 2/2: Creating' if needs_unlocalize else 'Updating'} French locale data...")
            response = self.api.update_entry(
                content_type, 
                uid, 
                cleaned, 
                locale=self.locale,
                force_clear_cache=False  # No longer needed with unlocalize approach
            )
            
            if response and response.get('success'):
                print(f"   ✅ Localized successfully")
                
                # Verify the update by fetching back
                verify_response = self.api.get_entry(content_type, uid, locale=self.locale)
                if verify_response and 'entry' in verify_response:
                    print(f"   ✅ Verified: French locale exists")
                    return True
                else:
                    print(f"   ⚠️  WARNING: Could not verify French locale after update")
                    return False
            else:
                print(f"   ❌ Localization failed: No success response")
                return False
                
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Localization failed with error: {error_msg}")
            
            # If 422 error, save the payload for debugging
            if '422' in error_msg:
                print(f"   💾 Saving failed payload to debug file...")
                self._save_debug_payload(content_type, uid, cleaned, [error_msg])
            
            import traceback
            traceback.print_exc()
            return False
    
    def _clean_data(self, data: Dict) -> Dict:
        """
        Remove system fields recursively (but keep tags - it's user-editable metadata).
        CRITICAL: 
        - Preserve uid when it appears with _content_type_uid (ContentStack references).
        - Preserve url when it appears in image objects (needed for image display).
        """
        system_fields = {
            '_version', 'ACL', '_in_progress', 'locale',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'publish_details', '_workflow', '_metadata'
            # NOTE: 'url' NOT in system_fields anymore!
            # It's conditionally removed only from top-level entries, not from image objects
        }
        
        def clean_recursive(obj, is_top_level=False):
            """Recursively clean system fields from nested structures"""
            if isinstance(obj, dict):
                # CRITICAL: Check if this is a ContentStack reference
                # References have both 'uid' and '_content_type_uid' - we MUST keep both!
                is_reference = ('uid' in obj and '_content_type_uid' in obj)
                
                # CRITICAL: Check if this is an image object
                # Image objects have 'url', 'uid', 'filename', 'content_type' (MIME type)
                # We MUST keep 'url' in images for display!
                is_image = ('uid' in obj and 'url' in obj and 'filename' in obj)
                
                # Remove system fields and recursively clean remaining values
                cleaned = {}
                for k, v in obj.items():
                    # Keep field if:
                    # 1. It's not a system field, OR
                    # 2. It's 'uid' and this is a reference object, OR
                    # 3. It's 'url' and this is an image object (not top-level entry)
                    should_keep = (
                        (k not in system_fields) or 
                        (k == 'uid' and is_reference) or
                        (k == 'url' and is_image and not is_top_level)
                    )
                    
                    # Special case: Remove 'url' from top-level entries (it's a system field there)
                    if k == 'url' and is_top_level:
                        should_keep = False
                    
                    if should_keep:
                        cleaned[k] = clean_recursive(v, is_top_level=False)
                return cleaned
            elif isinstance(obj, list):
                # Recursively clean each item in the list
                return [clean_recursive(item, is_top_level=False) for item in obj]
            else:
                # Return primitive values as-is
                return obj
        
        return clean_recursive(data, is_top_level=True)
    
    def _validate_structure(self, content_type: str, data: Dict) -> List[str]:
        """Validate structure before sending to ContentStack"""
        errors = []
        
        # Check for empty required arrays
        if content_type == 'ad_builder':
            # ad_builder requires text_content array
            if 'ad_builder_block' in data:
                block = data['ad_builder_block']
                if 'text_content' in block:
                    text_content = block['text_content']
                    if isinstance(text_content, list):
                        if len(text_content) == 0:
                            errors.append("ad_builder_block.text_content is empty array")
                        else:
                            # Check each text_content item
                            for idx, item in enumerate(text_content):
                                if not isinstance(item, dict):
                                    errors.append(f"text_content[{idx}] is not a dict")
                                elif 'markdown_text' not in item:
                                    errors.append(f"text_content[{idx}] missing markdown_text")
                                elif item.get('markdown_text') == '':
                                    errors.append(f"text_content[{idx}].markdown_text is empty")
        
        return errors
    
    def _save_debug_payload(self, content_type: str, uid: str, payload: Dict, errors: List[str]):
        """Save failed payload to debug file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            filename = f"debug_{content_type}_{uid}_{timestamp}.json"
            filepath = Path(__file__).parent.parent / 'logs' / filename
            
            debug_data = {
                'content_type': content_type,
                'uid': uid,
                'errors': errors,
                'payload': payload
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, indent=2, ensure_ascii=False)
            
            print(f"   💾 Debug payload saved to: {filepath}")
        except Exception as e:
            print(f"   ⚠️  Could not save debug file: {e}")
    
    def move_to_review_stage(self, content_type: str, uid: str, review_stage_uid: str = 'blt17e0c5c565fa65c3', dry_run=False) -> bool:
        """
        Move component to Review workflow stage (Draft → Review)
        
        Args:
            content_type: Component content type
            uid: Component UID
            review_stage_uid: Review stage UID (default: blt17e0c5c565fa65c3 for CABC)
            dry_run: If True, skip actual API call
        
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            print(f"      🔍 DRY-RUN: Would move to Review stage {content_type}/{uid}")
            return True
        
        try:
            self.api.update_workflow_stage(content_type, uid, review_stage_uid, locale=self.locale)
            print(f"      ✅ Moved to Review stage")
            time.sleep(0.2)  # Brief delay between workflow stages
            return True
        except Exception as e:
            print(f"      ❌ Review stage failed: {e}")
            return False
    
    def move_to_approved_stage(self, content_type: str, uid: str, approved_stage_uid: str = 'blt0915ab57da3d0af1', dry_run=False) -> bool:
        """
        Move component to Approved workflow stage (Review → Approved)
        
        Args:
            content_type: Component content type
            uid: Component UID
            approved_stage_uid: Approved stage UID (default: blt0915ab57da3d0af1)
            dry_run: If True, skip actual API call
        
        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            print(f"      🔍 DRY-RUN: Would move to Approved stage {content_type}/{uid}")
            return True
        
        try:
            self.api.update_workflow_stage(content_type, uid, approved_stage_uid, locale=self.locale)
            print(f"      ✅ Moved to Approved stage")
            time.sleep(0.2)  # Brief delay before publishing
            return True
        except Exception as e:
            print(f"      ❌ Approved stage failed: {e}")
            return False
    
    def publish_component(self, content_type: str, uid: str, environments: List[str] = None, dry_run=False, raise_on_error=False) -> bool:
        """
        Publish localized component (Approved → Published)
        
        Args:
            content_type: Component content type
            uid: Component UID
            environments: Environment UIDs to publish to
            dry_run: If True, skip actual API call
            raise_on_error: If True, raise exception instead of returning False
        
        Returns:
            True if successful, False otherwise (or raises exception if raise_on_error=True)
        """
        if dry_run:
            print(f"      🔍 DRY-RUN: Would publish {content_type}/{uid}")
            return True
        
        try:
            # Use standard publish API
            self.api.publish_entry(
                content_type, 
                uid, 
                environments=environments,
                locales=[self.locale],
                locale=self.locale
            )
            print(f"      ✅ Published successfully")
            time.sleep(0.5)  # Delay between publishes
            return True
        except Exception as e:
            if raise_on_error:
                raise  # Re-raise the exception
            print(f"      ❌ Publishing failed: {e}")
            return False
    
    def process_workflow_and_publish(self, content_type: str, uid: str, title: str, environments: List[str] = None, dry_run=False) -> bool:
        """
        Smart workflow: Check current stage → Move to Approved → Publish
        Only moves forward, never backwards
        """
        print(f"   📋 Processing workflow for: {title}")
        
        # Stage UIDs for CABC
        REVIEW_STAGE_UID = 'blt17e0c5c565fa65c3'
        APPROVED_STAGE_UID = 'blt0915ab57da3d0af1'
        
        # Get current entry to check workflow stage
        try:
            entry_response = self.api.get_entry(content_type, uid, locale=self.locale)
            if entry_response and 'entry' in entry_response:
                current_workflow = entry_response['entry'].get('_workflow', {})
                current_stage_uid = current_workflow.get('workflow_stage', {}).get('uid')
                
                if current_stage_uid:
                    print(f"      ℹ️  Current stage: {current_stage_uid}")
                    
                    # If already at Approved, skip to publish
                    if current_stage_uid == APPROVED_STAGE_UID:
                        print(f"      ✅ Already at Approved stage - skipping workflow updates")
                        print(f"      [1/1] Publishing...")
                        if not self.publish_component(content_type, uid, environments, dry_run=dry_run, raise_on_error=False):
                            return False
                        print(f"      ✅ Workflow and publish complete")
                        return True
                    
                    # If at Review, only move to Approved
                    elif current_stage_uid == REVIEW_STAGE_UID:
                        print(f"      ℹ️  At Review stage - moving to Approved only")
                        print(f"      [1/2] Moving Review → Approved...")
                        if not self.move_to_approved_stage(content_type, uid, APPROVED_STAGE_UID, dry_run=dry_run):
                            print(f"      ❌ Approved stage failed - stopping workflow")
                            return False
                        
                        print(f"      [2/2] Publishing...")
                        if not self.publish_component(content_type, uid, environments, dry_run=dry_run, raise_on_error=False):
                            return False
                        print(f"      ✅ Workflow and publish complete")
                        return True
        except Exception as e:
            print(f"      ⚠️  Could not check current stage: {e}")
            print(f"      ℹ️  Proceeding with full workflow...")
        
        # Default: Full workflow Draft → Review → Approved → Publish
        print(f"      [1/3] Moving Draft → Review...")
        if not self.move_to_review_stage(content_type, uid, REVIEW_STAGE_UID, dry_run=dry_run):
            print(f"      ❌ Review stage failed - stopping workflow")
            return False
        
        print(f"      [2/3] Moving Review → Approved...")
        if not self.move_to_approved_stage(content_type, uid, APPROVED_STAGE_UID, dry_run=dry_run):
            print(f"      ❌ Approved stage failed - stopping workflow")
            return False
        
        print(f"      [3/3] Publishing...")
        if not self.publish_component(content_type, uid, environments, dry_run=dry_run, raise_on_error=False):
            return False
        
        print(f"      ✅ Complete workflow finished successfully")
        return True


def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Localize components from French page UID or JSON file',
        epilog='Examples:\n'
               '  python simple_localizer_v2.py blt123... blt456... --publish\n'
               '  python simple_localizer_v2.py blt123... input/french.json --publish',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('english_page_uid', help='English feature page UID')
    parser.add_argument('french_source', help='French feature page UID OR path to French JSON file')
    parser.add_argument('--environment', default='CABC', help='Environment (default: CABC)')
    parser.add_argument('--dry-run', action='store_true', help='Test without updates')
    parser.add_argument('--approve', action='store_true', help='Set workflow to Approved after localization')
    parser.add_argument('--publish', action='store_true', help='Publish components after localization')
    parser.add_argument('--disable-llm', action='store_true', help='Disable LLM-based mapping for mismatches')
    
    args = parser.parse_args()
    
    print("="*80)
    print("SIMPLE COMPONENT LOCALIZER V2")
    print("="*80)
    print(f"English Page: {args.english_page_uid}")
    print(f"French Source: {args.french_source}")
    print(f"Environment: {args.environment}")
    print(f"Dry Run: {args.dry_run}")
    print(f"Approve Workflow: {args.approve}")
    print(f"Publish: {args.publish}")
    print(f"LLM Mapping: {'Disabled' if args.disable_llm else 'Enabled'}")
    
    # Auto-load environment UID from .env
    env_uid = os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{args.environment}')
    if not env_uid:
        print(f"❌ Environment UID not found in .env for {args.environment}")
        sys.exit(1)
    
    print(f"Environment UID: {env_uid} (from .env)")
    
    # Store env_uid in args for later use
    args.env_uids = [env_uid]
    
    # Initialize with LLM mapping preference
    localizer = SimpleLocalizerV2(args.environment, use_llm_mapping=not args.disable_llm)
    
    # ========================================================================
    # Determine if french_source is a UID or file path
    # ========================================================================
    french_json_path = None
    
    # Check if it's a file path
    if os.path.exists(args.french_source):
        print(f"\n✅ Using provided French JSON file: {args.french_source}")
        french_json_path = args.french_source
    
    # Check if it's a UID (starts with 'blt')
    elif args.french_source.startswith('blt'):
        print(f"\n📥 Fetching French page from ContentStack: {args.french_source}")
        print(f"   ℹ️  This will fetch ALL nested components recursively...")
        
        try:
            # Fetch the French page (shallow - just UIDs)
            response = localizer.api.get_entry('feature_page', args.french_source, locale='fr-ca')
            
            if not response or 'entry' not in response:
                print(f"❌ Failed to fetch French page {args.french_source}")
                sys.exit(1)
            
            french_entry = response['entry']
            print(f"✅ Fetched French page: {french_entry.get('title', 'N/A')}")
            
            # Use JSONCleanup to fetch nested content and clean
            print(f"🔍 Fetching all nested components (this may take a moment)...")
            cleanup = JSONCleanup(localizer.api)
            
            # Wrap in entry object for cleanup
            full_response = {'entry': french_entry}
            cleaned_data = cleanup.cleanup_json(full_response)
            
            print(f"✅ Successfully fetched and cleaned all nested content")
            
            # Save to input folder
            input_dir = Path(__file__).parent / 'input'
            input_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            french_json_path = input_dir / f'french_fetched_{args.french_source}_{timestamp}.json'
            
            with open(french_json_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Saved complete French JSON to: {french_json_path}")
            
        except Exception as e:
            print(f"❌ Error fetching French page: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    else:
        print(f"❌ Invalid french_source: must be either a file path or a UID starting with 'blt'")
        sys.exit(1)
    
    # ========================================================================
    # Continue with localization
    # ========================================================================
    
    # Step 1: Extract English component references
    english_refs = localizer.extract_components_from_english_page(args.english_page_uid)
    
    # Step 2: Extract French component data
    french_comps = localizer.extract_components_from_french_json(french_json_path)
    
    # Step 3: Match them by position and content_type
    matched = localizer.match_components(english_refs, french_comps)
    
    if not matched:
        print("\n❌ No components matched! Check your JSON structure.")
        sys.exit(1)
    
    # Step 4: For each match, fetch English structure, extract nested, localize nested first, then parent
    print(f"\n{'='*80}")
    print(f"LOCALIZING {len(matched)} COMPONENTS")
    print(f"{'='*80}")
    
    success_count = 0
    failed = []
    nested_components_for_workflow = []  # Track nested components for workflow processing
    parent_components_for_workflow = []  # Track parent components for workflow processing
    
    # ========================================================================
    # PHASE 1: LOCALIZE ALL COMPONENTS (nested + parent)
    # ========================================================================
    print(f"\n{'='*80}")
    print(f"PHASE 1: LOCALIZING COMPONENTS")
    print(f"{'='*80}")
    
    for idx, match in enumerate(matched, 1):
        content_type = match['content_type']
        english_uid = match['english_uid']
        french_data = match['french_data']
        
        print(f"\n{'='*60}")
        print(f"Processing [{idx}/{len(matched)}]: {content_type}/{english_uid}")
        print(f"{'='*60}")
        
        # Fetch English structure
        print(f"📥 Fetching English structure...", flush=True)
        response = localizer.api.get_entry(content_type, english_uid)
        if not response or 'entry' not in response:
            print(f"   ❌ Failed to fetch English component")
            failed.append(f"{content_type}/{english_uid}")
            continue
        
        english_structure = response['entry']
        
        # Check for nested components (ad_set_costco, link_list_with_flyout_references, content_divider)
        if content_type in ['ad_set_costco', 'link_list_with_flyout_references', 'content_divider']:
            print(f"   🔍 Checking for nested components in {content_type}...")
            nested_components = localizer.extract_nested_components(english_structure, french_data)
            
            if nested_components:
                print(f"   📦 Found {len(nested_components)} nested components - localizing them first...")
                
                # Localize nested components FIRST
                nested_success = 0
                nested_failed = []
                skipped_for_split = []  # Track skipped ad_builders for post-split localization
                
                for n_idx, nested in enumerate(nested_components, 1):
                    nested_ct = nested['content_type']
                    nested_uid = nested['english_uid']
                    nested_fr = nested['french_data']
                    nested_depth = nested.get('depth', 0)
                    nested_fr_uid = nested.get('french_uid')  # French UID for this nested component
                    
                    print(f"      → Nested [{n_idx}/{len(nested_components)}]: {nested_ct}/{nested_uid} (depth: {nested_depth})", flush=True)
                    
                    # SPECIAL: Skip ad_builders nested in ad_set_costco if parent will split them
                    # Check if this is an ad_builder inside ad_set_costco that has 2 English but 1 French
                    skip_localization = False
                    if content_type == 'ad_set_costco' and nested_ct == 'ad_builder':
                        # Check if parent has split scenario (2 English ad_builders, 1 French)
                        ad_content = english_structure.get('ad_content', [])
                        eng_ad_builders = []
                        for item in ad_content:
                            refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                            eng_ad_builders.extend(refs)
                        
                        # Count French ad_builders
                        fr_ad_content = french_data.get('ad_content', [])
                        fr_ad_builders = []
                        for item in fr_ad_content:
                            refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                            fr_ad_builders.extend(refs)
                        
                        if len(eng_ad_builders) == 2 and len(fr_ad_builders) == 1:
                            print(f"         ⚠️  Parent will split 1 French ad_builder → 2 English")
                            print(f"         → Skipping nested localization (will be handled by parent split)")
                            skip_localization = True
                            # Track the French UID for post-split
                            skipped_for_split.append({
                                'english_uid': nested_uid,
                                'french_uid': nested_fr_uid,
                                'french_data': nested_fr
                            })
                    
                    if skip_localization:
                        continue
                    
                    # Map nested component
                    nested_mapped = localizer.map_structure(nested_uid, nested_ct, nested_fr)
                    if not nested_mapped:
                        print(f"      ❌ Failed to map nested {nested_ct}/{nested_uid}")
                        nested_failed.append(f"{nested_ct}/{nested_uid}")
                        continue
                    
                    # Localize nested
                    if localizer.localize_component(nested_ct, nested_uid, nested_mapped, dry_run=args.dry_run):
                        nested_success += 1
                        print(f"      ✅ Nested {nested_ct}/{nested_uid} localized successfully")
                        
                        # Track for workflow processing (if requested)
                        if (args.approve or args.publish) and not args.dry_run:
                            nested_components_for_workflow.append({
                                'content_type': nested_ct,
                                'uid': nested_uid,
                                'depth': nested_depth,
                                'title': f"{nested_ct}/{nested_uid}"
                            })
                    else:
                        print(f"      ❌ Nested {nested_ct}/{nested_uid} localization FAILED")
                        nested_failed.append(f"{nested_ct}/{nested_uid}")
                
                print(f"   ✅ Localized {nested_success}/{len(nested_components)} nested components")
                if nested_failed:
                    print(f"   ⚠️  Failed nested: {', '.join(nested_failed)}")
            else:
                print(f"   ℹ️  No nested components found in {content_type}")
        
        # Now map and localize parent component
        mapped = localizer.map_structure(english_uid, content_type, french_data)
        
        if not mapped:
            failed.append(f"{content_type}/{english_uid}")
            continue
        
        # SPECIAL: If this was ad_set_costco with split scenario, extract and localize nested ad_builders FIRST
        if content_type == 'ad_set_costco' and skipped_for_split:
            print(f"   🔧 Pre-parent: Extracting and localizing {len(skipped_for_split)} nested ad_builders from LLM output...")
            
            # CRITICAL: First, inject English UIDs into the LLM-generated structure
            # Claude doesn't know the UIDs, so we need to add them from the English structure
            print(f"      → Injecting English UIDs into LLM-generated structure...")
            
            # Get English ad_builder UIDs
            eng_ad_content = english_structure.get('ad_content', [])
            eng_ad_uids = []
            for item in eng_ad_content:
                refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                for ref in refs:
                    eng_ad_uids.append(ref.get('uid'))
            
            print(f"      → English ad_builder UIDs: {eng_ad_uids}")
            
            # Inject UIDs into LLM-generated structure
            mapped_ad_content = mapped.get('ad_content', [])
            uid_idx = 0
            for item in mapped_ad_content:
                refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                for ref in refs:
                    if uid_idx < len(eng_ad_uids):
                        eng_uid = eng_ad_uids[uid_idx]
                        # Set UID on ref
                        ref['uid'] = eng_uid
                        # Also set UID in entry if present
                        if 'entry' in ref:
                            ref['entry']['uid'] = eng_uid
                            print(f"      → Injected UID {eng_uid} into ad_builder[{uid_idx}]")
                        uid_idx += 1
            
            print(f"      → Found {len(mapped_ad_content)} items in ad_content")
            
            # Collect all ad_builder entries (with full structure if LLM included them)
            ad_builders_to_localize = []
            for item in mapped_ad_content:
                refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                for ref in refs:
                    # Try to get UID from ref first, then from entry
                    uid = ref.get('uid')
                    if not uid and 'entry' in ref:
                        uid = ref.get('entry', {}).get('uid')
                    
                    if not uid:
                        print(f"      ⚠️  Skipping ref without UID")
                        continue
                    
                    # Check if LLM provided full entry structure
                    if 'entry' in ref:
                        print(f"      ✅ Found complete ad_builder entry for UID: {uid}")
                        ad_builders_to_localize.append({
                            'uid': uid,
                            'entry': ref['entry'],
                            'has_full_data': True
                        })
                    else:
                        print(f"      ⚠️  Only reference found for UID: {uid} (will need to fetch+map)")
                        ad_builders_to_localize.append({
                            'uid': uid,
                            'entry': None,
                            'has_full_data': False
                        })
            
            print(f"      → Extracted {len(ad_builders_to_localize)} ad_builders to localize")
            
            # Get French ad_builder data for fallback mapping
            french_ad_uid = skipped_for_split[0].get('french_uid')
            french_ad_data = skipped_for_split[0].get('french_data')
            
            if french_ad_uid:
                print(f"      → French ad_builder UID: {french_ad_uid}")
            
            # Localize each ad_builder
            for i, ad_info in enumerate(ad_builders_to_localize):
                eng_ad_uid = ad_info['uid']
                print(f"      → Localizing ad_builder[{i}]: {eng_ad_uid}")
                
                # Always fetch English structure for validation/refinement
                eng_ad_response = localizer.api.get_entry('ad_builder', eng_ad_uid, locale='en-ca')
                if not eng_ad_response or 'entry' not in eng_ad_response:
                    print(f"         ❌ Failed to fetch English ad_builder: {eng_ad_uid}")
                    continue
                
                eng_ad_structure = eng_ad_response['entry']
                
                if ad_info['has_full_data']:
                    # Use LLM-generated structure DIRECTLY - DO NOT apply rule-based refinement
                    # Claude already split and mapped the content perfectly
                    print(f"         ✅ Using LLM-generated ad_builder structure AS-IS (no refinement)")
                    llm_generated = ad_info['entry']
                    
                    # Debug: Check what LLM generated
                    llm_text_content = llm_generated.get('text_content', [])
                    print(f"         🔍 LLM generated {len(llm_text_content)} text_content items")
                    for idx, item in enumerate(llm_text_content[:3]):  # Show first 3
                        md_text = item.get('markdown_text', {}).get('markdown_text', 'N/A')
                        preview = md_text[:60] + '...' if len(md_text) > 60 else md_text
                        print(f"            [{idx}]: {preview}")
                    
                    # Use LLM output directly - it's already perfect for split scenarios
                    mapped_ad = llm_generated
                    
                    # Localize this ad_builder
                    if localizer.localize_component('ad_builder', eng_ad_uid, mapped_ad, dry_run=args.dry_run):
                        print(f"         ✅ ad_builder localized successfully")
                    else:
                        print(f"         ❌ ad_builder localization FAILED")
                else:
                    # Fallback: fetch English, map with French data
                    if french_ad_data:
                        print(f"         ⚠️  Using fallback: fetching English and mapping with French data")
                        mapped_ad = localizer.map_structure(eng_ad_uid, 'ad_builder', french_ad_data)
                        if mapped_ad and localizer.localize_component('ad_builder', eng_ad_uid, mapped_ad, dry_run=args.dry_run):
                            print(f"         ✅ ad_builder localized successfully (fallback)")
                        else:
                            print(f"         ❌ ad_builder localization FAILED (fallback)")
                    else:
                        print(f"         ❌ No French data available for fallback mapping")
            
            # CRITICAL: Now clean up the mapped structure - remove 'entry' objects from ad_builder_ref
            # ContentStack only accepts references (UIDs), not full entry objects
            print(f"      🧹 Cleaning up ad_set_costco structure - removing nested entry objects...")
            for item in mapped.get('ad_content', []):
                refs = item.get('ad_builder_block', {}).get('ad_builder_ref', [])
                for ref in refs:
                    if 'entry' in ref:
                        # Extract the UID from the entry before removing it
                        entry_uid = ref.get('entry', {}).get('uid')
                        if entry_uid:
                            # Set the UID on the ref itself (if not already set)
                            if 'uid' not in ref:
                                ref['uid'] = entry_uid
                        # Remove the full entry structure, keep only reference
                        del ref['entry']
                        print(f"         ✅ Removed entry object for {ref.get('uid', 'unknown')}, kept UID reference")
        
        # Localize parent
        if localizer.localize_component(content_type, english_uid, mapped, dry_run=args.dry_run):
            success_count += 1
            print(f"   ✅ Parent component localized successfully")
            
            # Track for workflow processing (if requested)
            if (args.approve or args.publish) and not args.dry_run:
                parent_components_for_workflow.append({
                    'content_type': content_type,
                    'uid': english_uid,
                    'title': f"{content_type}/{english_uid}"
                })
        else:
            failed.append(f"{content_type}/{english_uid}")
    
    # ========================================================================
    # PHASE 2: WORKFLOW PROCESSING (Review → Approved → Published)
    # Process nested components FIRST (deepest to shallowest), then parents
    # Same workflow as English pages
    # ========================================================================
    if (args.approve or args.publish) and not args.dry_run:
        print(f"\n{'='*80}")
        print(f"PHASE 2: WORKFLOW PROCESSING (Review → Approved → Publish)")
        print(f"{'='*80}")
        
        total_workflow_count = len(nested_components_for_workflow) + len(parent_components_for_workflow)
        
        if total_workflow_count == 0:
            print("⚠️  No components to process workflow")
        else:
            workflow_success = 0
            workflow_failed = []
            
            # Sort nested by depth (deepest first - link_list_simple before link_flyout)
            nested_components_for_workflow.sort(key=lambda x: x.get('depth', 0), reverse=True)
            
            # Process nested components first
            if nested_components_for_workflow:
                print(f"\n� Processing {len(nested_components_for_workflow)} nested components...")
                print(f"{'='*60}")
                
                for i, comp in enumerate(nested_components_for_workflow, 1):
                    print(f"\n[{i}/{len(nested_components_for_workflow)}] {comp['title']} (depth: {comp.get('depth', 0)})", flush=True)
                    
                    if localizer.process_workflow_and_publish(
                        comp['content_type'],
                        comp['uid'],
                        comp['title'],
                        environments=args.env_uids,
                        dry_run=args.dry_run
                    ):
                        workflow_success += 1
                    else:
                        workflow_failed.append(comp['title'])
            
            # Process parent components
            if parent_components_for_workflow:
                print(f"\n� Processing {len(parent_components_for_workflow)} parent components...")
                print(f"{'='*60}")
                
                for i, comp in enumerate(parent_components_for_workflow, 1):
                    print(f"\n[{i}/{len(parent_components_for_workflow)}] {comp['title']}")
                    
                    if localizer.process_workflow_and_publish(
                        comp['content_type'],
                        comp['uid'],
                        comp['title'],
                        environments=args.env_uids,
                        dry_run=args.dry_run
                    ):
                        workflow_success += 1
                    else:
                        workflow_failed.append(comp['title'])
            
            print(f"\n{'='*60}")
            print(f"Workflow Summary:")
            print(f"   Total: {total_workflow_count}")
            print(f"   Success: {workflow_success}")
            print(f"   Failed: {len(workflow_failed)}")
            if workflow_failed:
                print(f"\n   ⚠️  Failed workflow updates:")
                for comp_title in workflow_failed:
                    print(f"      - {comp_title}")
    
    # ========================================================================
    # PHASE 3: LOCALIZE & PUBLISH FEATURE PAGE (if --publish flag)
    # ========================================================================
    if args.publish and not args.dry_run:
        print(f"\n{'='*80}")
        print(f"PHASE 3: LOCALIZING & PUBLISHING FEATURE PAGE")
        print(f"{'='*80}")
        print(f"\n📄 Processing feature page: {args.english_page_uid}")
        
        # Load French JSON to get title and meta_title
        with open(french_json_path, 'r', encoding='utf-8') as f:
            french_page_data = json.load(f)
        
        french_entry = french_page_data.get('entry', {})
        french_title = french_entry.get('title')
        french_seo_metadata = french_entry.get('seo_metadata', {})
        french_meta_title = french_seo_metadata.get('meta_title')
        
        # Fetch the English feature page
        page_response = localizer.api.get_entry('feature_page', args.english_page_uid)
        if page_response and 'entry' in page_response:
            page_title = page_response['entry'].get('title', args.english_page_uid)
            english_page_data = page_response['entry']
            
            print(f"   📋 English Feature page: {page_title}")
            if french_title:
                print(f"   📋 French title: {french_title}")
            if french_meta_title:
                print(f"   📋 French meta_title: {french_meta_title}")
            
            # STEP 1: Localize the feature page
            print(f"   📤 Localizing feature page to French...")
            print(f"   ℹ️  Feature page references {len(matched)} localized components")
            
            # CRITICAL: Use French title and meta_title instead of English
            if french_title:
                english_page_data['title'] = french_title
                print(f"   ✅ Using French title: {french_title}")
            
            if french_meta_title:
                # Ensure seo_metadata exists
                if 'seo_metadata' not in english_page_data:
                    english_page_data['seo_metadata'] = {}
                english_page_data['seo_metadata']['meta_title'] = french_meta_title
                print(f"   ✅ Using French meta_title: {french_meta_title}")
            
            # CRITICAL: Ensure tags field is set for feature page
            if 'tags' not in english_page_data or not english_page_data['tags']:
                english_page_data['tags'] = ["migrated-from-cms"]
            elif "migrated-from-cms" not in english_page_data['tags']:
                english_page_data['tags'].append("migrated-from-cms")
            
            localization_success = False
            try:
                localization_success = localizer.localize_component('feature_page', args.english_page_uid, english_page_data, dry_run=False)
                if localization_success:
                    print(f"   ✅ Feature page localized successfully")
                    
                    # Wait a moment for ContentStack to process the update
                    time.sleep(2)
                else:
                    print(f"   ⚠️  Feature page localization returned False")
            except Exception as e:
                print(f"   ⚠️  Feature page localization error: {e}")
            
            # STEP 2: Move feature page through workflow and publish (only if localization succeeded)
            if localization_success:
                print(f"   📤 Processing workflow and publish for feature page...")
                
                try:
                    # Use the same workflow process as components
                    if localizer.process_workflow_and_publish(
                        'feature_page',
                        args.english_page_uid,
                        page_title,  # Pass title, not env_uids
                        args.env_uids,  # Pass env_uids here
                        dry_run=False
                    ):
                        print(f"   ✅ Feature page workflow and publish completed successfully")
                    else:
                        print(f"   ⚠️  Feature page workflow/publish returned False")
                except Exception as e:
                    error_msg = str(e)
                    if '422' in error_msg and 'workflow' in error_msg.lower():
                        print(f"   ℹ️  Feature page requires workflow approval")
                        print(f"   ℹ️  Please manually approve and publish the feature page in ContentStack")
                        print(f"   ℹ️  All components are already published - page just needs approval")
                    else:
                        print(f"   ⚠️  Feature page workflow/publish failed: {e}")
            else:
                print(f"   ⚠️  Skipping workflow/publish - localization failed")
        else:
            print(f"   ⚠️  Could not fetch feature page")
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print(f"\n{'='*80}")
    print(f"✅ COMPLETED!" if not args.dry_run else "✅ DRY-RUN COMPLETED!")
    print(f"{'='*80}")
    print(f"Components localized: {success_count}/{len(matched)}")
    
    if args.approve and not args.dry_run:
        print(f"   ✅ Workflow set to Approved")
    
    if args.publish and not args.dry_run:
        print(f"   ✅ Components published")
    
    if failed:
        print(f"\n⚠️  Failed:")
        for item in failed:
            print(f"   - {item}")
    
    if args.dry_run:
        print(f"\n📋 Next Steps:")
        print(f"   1. Run without --dry-run to perform actual localization")
        if not args.approve:
            print(f"   2. Add --approve flag to set workflow to Approved")
        if not args.publish:
            print(f"   3. Add --publish flag to publish components")
    else:
        print(f"\n{'='*80}")
        print(f"✅ LOCALIZATION COMPLETE")
        print(f"{'='*80}")
        print(f"\n📝 Verify in ContentStack:")
        print(f"   1. Go to ContentStack UI and switch to fr-ca locale")
        print(f"   2. Check that components are localized and published")
        print(f"   3. Test the live site with ?locale=fr-ca parameter")


if __name__ == '__main__':
    main()

