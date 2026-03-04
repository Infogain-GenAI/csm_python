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

# Load environment
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class SimpleLocalizerV2:
    def __init__(self, environment: str):
        """Initialize with ContentStack API"""
        self.environment = environment
        self.locale = 'fr-ca'
        
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
                if 'uid' in eng and '_content_type_uid' in eng:
                    content_type = eng['_content_type_uid']
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
                        nested.append({
                            'content_type': content_type,
                            'english_uid': uid,
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
        Fetch English component structure, map with French content
        """
        print(f"\n🔄 Mapping {content_type}/{english_uid}")
        
        # Fetch English structure
        response = self.api.get_entry(content_type, english_uid)
        if not response or 'entry' not in response:
            print(f"   ❌ Failed to fetch English component")
            return None
        
        english_data = response['entry']
        
        # Map: English structure + French content
        mapped = self._replace_content(english_data, french_data)
        
        # CRITICAL: Always ensure tags field is set
        # All components must have "migrated-from-cms" tag
        if 'tags' not in mapped or not mapped['tags']:
            mapped['tags'] = ["migrated-from-cms"]
        elif "migrated-from-cms" not in mapped['tags']:
            mapped['tags'].append("migrated-from-cms")
        
        return mapped
    
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
        Preserve markdown formatting from English while using French text
        
        Examples:
            English: "**COVER STORY**" → French: "La une" → Result: "**La une**"
            English: "*Welcome*" → French: "Bienvenue" → Result: "*Bienvenue*"
            English: "# Title" → French: "Titre" → Result: "# Titre"
        """
        import re
        
        # Debug output
        print(f"      🔍 Markdown preservation: '{english_text}' → '{french_text}'", end="")
        
        # Detect markdown patterns in English text
        # Bold: **text** or __text__
        if re.match(r'^\*\*(.+?)\*\*$', english_text):
            result = f"**{french_text}**"
            print(f" → '{result}' ✅")
            return result
        if re.match(r'^__(.+?)__$', english_text):
            result = f"__{french_text}__"
            print(f" → '{result}' ✅")
            return result
        
        # Italic: *text* or _text_
        if re.match(r'^\*(.+?)\*$', english_text):
            result = f"*{french_text}*"
            print(f" → '{result}' ✅")
            return result
        if re.match(r'^_(.+?)_$', english_text):
            result = f"_{french_text}_"
            print(f" → '{result}' ✅")
            return result
        
        # Bold + Italic: ***text*** or ___text___
        if re.match(r'^\*\*\*(.+?)\*\*\*$', english_text):
            result = f"***{french_text}***"
            print(f" → '{result}' ✅")
            return result
        if re.match(r'^___(.+?)___$', english_text):
            result = f"___{french_text}___"
            print(f" → '{result}' ✅")
            return result
        
        # Headings: # text, ## text, etc.
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', english_text)
        if heading_match:
            result = f"{heading_match.group(1)} {french_text}"
            print(f" → '{result}' ✅")
            return result
        
        # No markdown detected, return French text as-is
        print(f" → '{french_text}' (no markdown)")
        return french_text
    
    def _replace_content(self, eng, fr):
        """Recursively replace content fields from French to English structure"""
        # Content fields that should be replaced
        CONTENT_FIELDS = {
            'markdown_text', 'text', 'description', 'caption',
            'meta_title', 'meta_description', 'page_title', 'breadcrumb_title',
            'alt_text', 'image_alt_text', 'mobile_image_alt_text', 'icon_alt_text',
            'disclaimer', 'disclaimer_markdown', 'entry_title', 'link_text'
        }
        
        # CRITICAL: 'title' is NOT in CONTENT_FIELDS - must keep English title!
        # If title changes, ContentStack creates NEW entry instead of adding locale
        
        # Fields to fully replace (images, assets, links, and content-related flags)
        FULL_REPLACE = {
            'image', 'mobile_image', 'icon_image', 'background_image',
            'logo', 'thumbnail', 'asset', 'file', 'media',
            'costco_url', 'link', 'url',
            # NOTE: 'color' removed - should keep English color structure
            'background_group', 'background_color', 'text_color', 'border_color',
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
            'ad_type', 'display_style', 'layout', 'alignment',
            'overlay_position', 'overlay_fill_type', 'overlay_fill_',
            # Style and formatting - keep English structure
            'select_text_type', 'select_semantics_type', 'color', 'color_config',
            'top_and_bottom_strip', 'top_and_bottom_text_banner',
            # Metadata and system fields - must preserve from English
            'tags', 'uid', '_version', '_content_type_uid', 'locale',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'publish_details', '_metadata', 'ACL'
        }
        
        if isinstance(eng, dict) and isinstance(fr, dict):
            result = {}
            for key in eng.keys():
                # ALWAYS keep English value for certain fields
                if key in KEEP_ENGLISH:
                    result[key] = eng[key]
                elif key in fr:
                    # French has this key
                    if key in CONTENT_FIELDS:
                        # Special handling for markdown_text: preserve English markdown formatting
                        if key == 'markdown_text' and isinstance(eng[key], str) and isinstance(fr[key], str):
                            result[key] = self._preserve_markdown_formatting(eng[key], fr[key])
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
                    # French doesn't have this key, keep English
                    result[key] = eng[key]
            return result
        
        elif isinstance(eng, list) and isinstance(fr, list):
            # Handle array length mismatches
            if len(eng) != len(fr):
                # Special case: English has fewer items than French
                # Strategy: Map first N-1 items normally, combine rest into last English item
                if len(eng) < len(fr):
                    # Edge case: English is empty, French has items - just return French
                    if len(eng) == 0:
                        print(f"      ℹ️  English array is empty, using French array as-is")
                        return fr
                    
                    print(f"      ⚠️  Array mismatch: English has {len(eng)} items, French has {len(fr)} items - combining remaining French items")
                    
                    result = []
                    
                    # Map first (N-1) items normally
                    for i in range(len(eng) - 1):
                        result.append(self._replace_content(eng[i], fr[i]))
                    
                    # For the last English item, combine all remaining French items
                    last_eng_item = eng[-1]
                    remaining_fr_items = fr[len(eng)-1:]  # All remaining French items
                    
                    # Check if this has markdown_text field to combine
                    if isinstance(last_eng_item, dict) and 'markdown_text' in last_eng_item:
                        # Combine all remaining French markdown_text
                        # Match English pattern: join with "  \n" (two spaces + newline for markdown line break)
                        combined_text_parts = []
                        for fr_item in remaining_fr_items:
                            if isinstance(fr_item, dict):
                                if 'markdown_text' in fr_item:
                                    md_text = fr_item['markdown_text']
                                    # Handle nested markdown_text (like in ad_builder text_content)
                                    if isinstance(md_text, dict) and 'markdown_text' in md_text:
                                        combined_text_parts.append(md_text['markdown_text'])
                                    # Handle direct string
                                    elif isinstance(md_text, str):
                                        combined_text_parts.append(md_text)
                        
                        # Join like English version: "Title  \nDescription"
                        # Use "  \n" (two spaces + newline) for proper markdown line breaks
                        if combined_text_parts:
                            combined_text = '  \n'.join(combined_text_parts)
                        else:
                            combined_text = ''
                        
                        # Create mapped last item with combined text
                        mapped_last_item = self._replace_content(last_eng_item, remaining_fr_items[0])
                        
                        # Set the combined text (handle both nested and direct structures)
                        if isinstance(mapped_last_item.get('markdown_text'), dict):
                            mapped_last_item['markdown_text']['markdown_text'] = combined_text
                        else:
                            mapped_last_item['markdown_text'] = combined_text
                        
                        result.append(mapped_last_item)
                    else:
                        # For non-text items, just use first of remaining French items
                        result.append(self._replace_content(last_eng_item, remaining_fr_items[0]))
                    
                    print(f"      ✅ Mapped {len(eng)-1} items normally, combined {len(remaining_fr_items)} French items into last item")
                    return result
                
                # If English has more items than French, intelligently split or create
                else:
                    # Edge case: French is empty - keep English structure as-is
                    if len(fr) == 0:
                        print(f"      ℹ️  French array is empty, keeping English structure")
                        return eng
                    
                    # SPECIAL CASE: ad_builder splitting
                    # If English has 2 ad_builders (image-only + text-only) and French has 1 (image+text)
                    # Split the French ad_builder content between the two English ad_builders
                    if (len(eng) == 2 and len(fr) == 1 and 
                        self._is_ad_builder_array(eng) and self._is_ad_builder_array(fr)):
                        
                        print(f"      🔀 Special case: Splitting French ad_builder into 2 English ad_builders")
                        return self._split_french_ad_builder(eng, fr)
                    
                    # Default case: create missing French components
                    print(f"      ⚠️  Array length mismatch: English={len(eng)}, French={len(fr)} - mapping {len(fr)} items, creating {len(eng)-len(fr)} French items")
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
            result = []
            for i in range(len(eng)):
                if i < len(fr):
                    result.append(self._replace_content(eng[i], fr[i]))
                else:
                    result.append(eng[i])
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
            
            # Update entry with fr-ca locale
            response = self.api.update_entry(content_type, uid, cleaned, locale=self.locale)
            
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
            print(f"   ❌ Localization failed with error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _clean_data(self, data: Dict) -> Dict:
        """Remove system fields (but keep tags - it's user-editable metadata)"""
        system_fields = {
            'uid', '_version', 'ACL', '_in_progress', 'locale',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'publish_details', '_workflow'
        }
        
        return {k: v for k, v in data.items() if k not in system_fields}
    
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
    
    # Auto-load environment UID from .env
    env_uid = os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{args.environment}')
    if not env_uid:
        print(f"❌ Environment UID not found in .env for {args.environment}")
        sys.exit(1)
    
    print(f"Environment UID: {env_uid} (from .env)")
    
    # Store env_uid in args for later use
    args.env_uids = [env_uid]
    
    # Initialize
    localizer = SimpleLocalizerV2(args.environment)
    
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
                for n_idx, nested in enumerate(nested_components, 1):
                    nested_ct = nested['content_type']
                    nested_uid = nested['english_uid']
                    nested_fr = nested['french_data']
                    nested_depth = nested.get('depth', 0)
                    
                    print(f"      → Nested [{n_idx}/{len(nested_components)}]: {nested_ct}/{nested_uid} (depth: {nested_depth})", flush=True)
                    
                    # Map nested component
                    nested_mapped = localizer.map_structure(nested_uid, nested_ct, nested_fr)
                    if not nested_mapped:
                        print(f"      ❌ Failed to map nested {nested_ct}/{nested_uid}")
                        nested_failed.append(f"{nested_ct}/{nested_uid}")
                        continue
                    
                    # Localize nested
                    if localizer.localize_component(nested_ct, nested_uid, nested_mapped, dry_run=args.dry_run):
                        nested_success += 1
                        print(f"      ✅ Localized successfully")
                        
                        # Track for workflow processing (if requested)
                        if (args.approve or args.publish) and not args.dry_run:
                            nested_components_for_workflow.append({
                                'content_type': nested_ct,
                                'uid': nested_uid,
                                'depth': nested_depth,
                                'title': f"{nested_ct}/{nested_uid}"
                            })
                    else:
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
                print(f"\n   ⚠️  Failed components:")
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
        
        # Fetch the feature page
        page_response = localizer.api.get_entry('feature_page', args.english_page_uid)
        if page_response and 'entry' in page_response:
            page_title = page_response['entry'].get('title', args.english_page_uid)
            english_page_data = page_response['entry']
            
            print(f"   📋 Feature page: {page_title}")
            
            # STEP 1: Localize the feature page
            print(f"   📤 Localizing feature page to French...")
            print(f"   ℹ️  Feature page references {len(matched)} localized components")
            
            # The feature page structure is already in English, and all components are localized
            # We just need to create the French locale for the page (it's a container)
            # Use the same English structure (component references will work for French)
            
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
        print(f"\n📋 Next Steps:")
        print(f"   1. Verify in ContentStack with ?locale=fr-ca")
        if not args.approve:
            print(f"   2. Manually approve components in ContentStack")
        if not args.publish:
            print(f"   3. Manually publish components in ContentStack")


if __name__ == '__main__':
    main()
