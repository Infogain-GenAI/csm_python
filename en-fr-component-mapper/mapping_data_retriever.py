"""
Mapping Data Retriever for English-French Component Mapping
Retrieves similar examples and generates mapped JSON using LLM + RAG.

This retriever finds similar English-French mismatch patterns from Pinecone
and uses them to guide LLM in generating the correct mapped structure.
"""

import os
import sys
import json
import logging
import argparse
import traceback
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI
import httpx
import dotenv
from pinecone import Pinecone
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
import urllib3
import warnings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)


# ============================================================================
# CONFIGURATION
# ============================================================================
COLLECTION_CONFIG = {
    "index_name": "en-fr-component-mapping",
    "description": "English-French component structure mapping examples",
    "supported_components": ["text_builder", "ad_set_costco"],
    "embedding_dimension": 1536
}


@dataclass
class MappingResult:
    """Data class to hold mapping results."""
    mapped_json: Dict
    similar_examples: List[Dict]
    confidence_score: float
    reasoning: str


class MappingDataRetriever:
    """
    Retrieves similar mapping examples and generates mapped JSON.
    
    This retriever:
    1. Analyzes English and French structure mismatches
    2. Finds similar examples from Pinecone
    3. Uses Claude to generate correct mapped structure
    """
    
    def __init__(
        self,
        openai_api_key: str,
        pinecone_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimension: int = 1536
    ):
        """Initialize the retriever."""
        # Initialize OpenAI client for embeddings
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            http_client=httpx.Client(verify=False)
        )
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        
        # Initialize Pinecone
        if pinecone_api_key is None:
            pinecone_api_key = os.getenv("PINECONE_API_KEY")
            if not pinecone_api_key:
                raise ValueError("PINECONE_API_KEY not found in environment")
        
        self.pc = Pinecone(
            api_key=pinecone_api_key,
            pool_threads=4,
            timeout=30
        )
        
        self.index_name = COLLECTION_CONFIG["index_name"]
        
        try:
            self.index = self.pc.Index(self.index_name)
            logger.info(f"✓ Connected to Pinecone index: {self.index_name}")
        except Exception as e:
            logger.error(f"✗ Error connecting to index '{self.index_name}': {str(e)}")
            raise
        
        # Initialize Claude for JSON generation
        if anthropic_api_key is None:
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment")
        
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=anthropic_api_key,
            temperature=0.0,
            max_tokens=62000
        )
        
        logger.info(f"="*70)
        logger.info(f"MappingDataRetriever Initialized")
        logger.info(f"="*70)
        logger.info(f"Index: {self.index_name}")
        logger.info(f"Description: {COLLECTION_CONFIG['description']}")
        logger.info(f"Embedding model: {embedding_model}")
        logger.info(f"LLM: Claude Sonnet 4 (claude-sonnet-4-20250514)")
        logger.info(f"="*70)
        
        # Storage directory for large JSONs
        self.storage_dir = Path(__file__).parent / "vectordb_json_storage"
    
    def load_json_from_storage(self, storage_path: str) -> Dict:
        """
        Load JSONs from external storage file.
        
        Args:
            storage_path: Relative path to storage file
            
        Returns:
            Dict with english_json, french_json, mapped_json
        """
        try:
            filepath = Path(__file__).parent / storage_path
            
            if not filepath.exists():
                logger.error(f"Storage file not found: {filepath}")
                return {
                    "english_json": {},
                    "french_json": {},
                    "mapped_json": {}
                }
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    "english_json": data.get("english_json", {}),
                    "french_json": data.get("french_json", {}),
                    "mapped_json": data.get("mapped_json", {})
                }
        except Exception as e:
            logger.error(f"Error loading from storage {storage_path}: {e}")
            return {
                "english_json": {},
                "french_json": {},
                "mapped_json": {}
            }
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text using OpenAI.
        Truncates text to fit within 8192 token limit.
        """
        try:
            # CRITICAL FIX: OpenAI embedding model has 8192 token limit
            # Real issue: The API counts TOKENS (not characters) and rejects if >8192
            # Rough estimate: 1 token ≈ 4 characters
            # So 8192 tokens ≈ 32,768 characters
            # BUT we need to be VERY conservative because:
            # 1. Some characters use multiple tokens (unicode, special chars)
            # 2. JSON formatting adds extra tokens
            # 3. Better to truncate more than hit the limit
            # 
            # SOLUTION: Use 20,000 chars max (≈ 5,000 tokens, well under 8,192 limit)
            MAX_CHARS = 20000
            
            if len(text) > MAX_CHARS:
                logger.warning(f"Query text too long ({len(text)} chars), truncating to {MAX_CHARS} chars")
                logger.info(f"   → This prevents OpenAI token limit errors (max 8192 tokens)")
                text = text[:MAX_CHARS]
            
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def create_query_text(
        self,
        english_data: Dict,
        french_data: Dict,
        component_type: str
    ) -> str:
        """
        Create query text to find similar mismatch patterns.
        Same format as embedding text in uploader.
        """
        if component_type == "text_builder":
            eng_sections = english_data.get("entry", {}).get("multiple_text_section_group", [])
            fr_sections = french_data.get("entry", {}).get("multiple_text_section_group", [])
            
            eng_counts = [len(section.get("text_section_content", [])) for section in eng_sections]
            fr_counts = [len(section.get("text_section_content", [])) for section in fr_sections]
            
            eng_types = []
            for section in eng_sections:
                for content in section.get("text_section_content", []):
                    eng_types.append(content.get("select_text_type", "unknown"))
            
            fr_types = []
            for section in fr_sections:
                for content in section.get("text_section_content", []):
                    fr_types.append(content.get("select_text_type", "unknown"))
            
            query_text = f"""Component: text_builder
English sections: {len(eng_sections)}
English content counts per section: {eng_counts}
English text types: {', '.join(eng_types)}

French sections: {len(fr_sections)}
French content counts per section: {fr_counts}
French text types: {', '.join(fr_types)}

Mismatch pattern: {len(eng_sections)} English sections vs {len(fr_sections)} French sections
"""
        
        elif component_type == "ad_set_costco":
            eng_ad_content = english_data.get("entry", {}).get("ad_content", [])
            fr_ad_content = french_data.get("entry", {}).get("ad_content", [])
            
            eng_text_counts = []
            for ad_item in eng_ad_content:
                ad_refs = ad_item.get("ad_builder_block", {}).get("ad_builder_ref", [])
                for ref in ad_refs:
                    entry = ref.get("entry", {})
                    text_content = entry.get("ad_builder_block", {}).get("text_content", [])
                    eng_text_counts.append(len(text_content))
            
            fr_text_counts = []
            for ad_item in fr_ad_content:
                ad_refs = ad_item.get("ad_builder_block", {}).get("ad_builder_ref", [])
                for ref in ad_refs:
                    entry = ref.get("entry", {})
                    text_content = entry.get("ad_builder_block", {}).get("text_content", [])
                    fr_text_counts.append(len(text_content))
            
            query_text = f"""Component: ad_set_costco
English ad_builders: {len(eng_text_counts)}
English text_content counts: {eng_text_counts}

French ad_builders: {len(fr_text_counts)}
French text_content counts: {fr_text_counts}

Mismatch pattern: {len(eng_text_counts)} English ad_builders vs {len(fr_text_counts)} French ad_builders
"""
        
        else:
            query_text = f"Component: {component_type}\nEnglish: {json.dumps(english_data)}\nFrench: {json.dumps(french_data)}"
        
        return query_text
    
    def merge_chunks(self, chunk_examples: List[Dict], component_type: str) -> Dict:
        """
        Merge chunked examples back into single complete example.
        
        Args:
            chunk_examples: List of chunk results with same example_id
            component_type: Component type
            
        Returns:
            Merged example dict
        """
        if not chunk_examples:
            return {}
        
        # Sort by chunk_index
        sorted_chunks = sorted(chunk_examples, key=lambda x: x.get("chunk_index", 0))
        
        # Start with first chunk
        merged_english = sorted_chunks[0]["english_json"]
        merged_french = sorted_chunks[0]["french_json"]
        merged_mapped = sorted_chunks[0]["mapped_json"]
        
        # Merge arrays based on component type
        if component_type == "link_list_with_flyout_references":
            # Merge link_list arrays
            english_links = merged_english.get("entry", {}).get("link_list", [])
            french_links = merged_french.get("entry", {}).get("link_list", [])
            mapped_links = merged_mapped.get("entry", {}).get("link_list", [])
            
            for chunk in sorted_chunks[1:]:
                english_links.extend(chunk["english_json"].get("entry", {}).get("link_list", []))
                french_links.extend(chunk["french_json"].get("entry", {}).get("link_list", []))
                mapped_links.extend(chunk["mapped_json"].get("entry", {}).get("link_list", []))
            
            merged_english["entry"]["link_list"] = english_links
            merged_french["entry"]["link_list"] = french_links
            merged_mapped["entry"]["link_list"] = mapped_links
        
        elif component_type == "ad_builder":
            # Merge text_content arrays
            eng_block = merged_english.get("entry", {}).get("ad_builder_block", {})
            fr_block = merged_french.get("entry", {}).get("ad_builder_block", {})
            map_block = merged_mapped.get("entry", {}).get("ad_builder_block", {})
            
            english_text = eng_block.get("text_content", [])
            french_text = fr_block.get("text_content", [])
            mapped_text = map_block.get("text_content", [])
            
            for chunk in sorted_chunks[1:]:
                chunk_eng = chunk["english_json"].get("entry", {}).get("ad_builder_block", {})
                chunk_fr = chunk["french_json"].get("entry", {}).get("ad_builder_block", {})
                chunk_map = chunk["mapped_json"].get("entry", {}).get("ad_builder_block", {})
                
                english_text.extend(chunk_eng.get("text_content", []))
                french_text.extend(chunk_fr.get("text_content", []))
                mapped_text.extend(chunk_map.get("text_content", []))
            
            eng_block["text_content"] = english_text
            fr_block["text_content"] = french_text
            map_block["text_content"] = mapped_text
        
        elif component_type == "text_builder":
            # Merge multiple_text_section_group arrays
            english_sections = merged_english.get("entry", {}).get("multiple_text_section_group", [])
            french_sections = merged_french.get("entry", {}).get("multiple_text_section_group", [])
            mapped_sections = merged_mapped.get("entry", {}).get("multiple_text_section_group", [])
            
            for chunk in sorted_chunks[1:]:
                english_sections.extend(chunk["english_json"].get("entry", {}).get("multiple_text_section_group", []))
                french_sections.extend(chunk["french_json"].get("entry", {}).get("multiple_text_section_group", []))
                mapped_sections.extend(chunk["mapped_json"].get("entry", {}).get("multiple_text_section_group", []))
            
            merged_english["entry"]["multiple_text_section_group"] = english_sections
            merged_french["entry"]["multiple_text_section_group"] = french_sections
            merged_mapped["entry"]["multiple_text_section_group"] = mapped_sections
        
        return {
            "example_id": sorted_chunks[0]["example_id"],
            "similarity_score": max(c["similarity_score"] for c in sorted_chunks),
            "component_type": component_type,
            "english_json": merged_english,
            "french_json": merged_french,
            "mapped_json": merged_mapped,
            "is_merged": True,
            "num_chunks": len(sorted_chunks)
        }
    
    def retrieve_similar_examples(
        self,
        english_data: Dict,
        french_data: Dict,
        component_type: str,
        n_results: int = 3
    ) -> List[Dict]:
        """
        Retrieve similar mapping examples from Pinecone.
        Handles both inline JSON (old format) and external storage (new format).
        
        Args:
            english_data: English input JSON
            french_data: French input JSON
            component_type: Component type (text_builder, ad_set_costco)
            n_results: Number of similar examples to retrieve
            
        Returns:
            List of similar examples with their metadata
        """
        try:
            # Create query text
            query_text = self.create_query_text(
                english_data,
                french_data,
                component_type
            )
            
            # Generate embedding
            query_embedding = self.generate_embedding(query_text)
            
            # Query Pinecone with higher top_k to account for chunks
            query_top_k = n_results * 5
            
            results = self.index.query(
                vector=query_embedding,
                top_k=query_top_k,
                filter={"component_type": component_type},
                include_metadata=True
            )
            
            # Group results by example_id (to merge chunks)
            examples_by_id = {}
            
            for match in results.matches:
                metadata = match.metadata
                example_id = metadata.get("example_id")
                is_chunked = metadata.get("is_chunked", False)
                storage_path = metadata.get("storage_path")  # New format
                
                # Create example dict
                example = {
                    "example_id": match.id if not is_chunked else example_id,
                    "similarity_score": float(match.score),
                    "component_type": metadata.get("component_type"),
                    "is_chunked": is_chunked
                }
                
                # Load JSONs based on format
                if storage_path:
                    # NEW FORMAT: Load from external storage
                    logger.info(f"      → Loading from external storage: {storage_path}")
                    json_data = self.load_json_from_storage(storage_path)
                    example["english_json"] = json_data["english_json"]
                    example["french_json"] = json_data["french_json"]
                    example["mapped_json"] = json_data["mapped_json"]
                else:
                    # OLD FORMAT: Load from inline metadata
                    example["english_json"] = json.loads(metadata.get("english_json", "{}"))
                    example["french_json"] = json.loads(metadata.get("french_json", "{}"))
                    example["mapped_json"] = json.loads(metadata.get("mapped_json", "{}"))
                
                if is_chunked:
                    # Add chunk-specific info
                    example["chunk_index"] = metadata.get("chunk_index", 0)
                    example["total_chunks"] = metadata.get("total_chunks", 1)
                    
                    # Group by example_id for merging
                    if example_id not in examples_by_id:
                        examples_by_id[example_id] = []
                    examples_by_id[example_id].append(example)
                else:
                    # Not chunked - add directly
                    if match.id not in examples_by_id:
                        examples_by_id[match.id] = [example]
            
            # Merge chunks and collect final examples
            similar_examples = []
            
            for example_id, chunks in examples_by_id.items():
                if len(chunks) > 1 and chunks[0].get("is_chunked"):
                    # Multiple chunks - merge them
                    logger.info(f"   → Merging {len(chunks)} chunks for {example_id}")
                    merged = self.merge_chunks(chunks, component_type)
                    similar_examples.append(merged)
                else:
                    # Single example or single chunk
                    similar_examples.append(chunks[0])
            
            # Sort by similarity score
            similar_examples.sort(key=lambda x: x["similarity_score"], reverse=True)
            
            # Return top N
            similar_examples = similar_examples[:n_results]
            
            logger.info(f"✓ Retrieved {len(similar_examples)} similar examples")
            for ex in similar_examples:
                storage_info = " [external storage]" if "storage_path" in ex else ""
                chunk_info = f" (merged from {ex.get('num_chunks', 1)} chunks)" if ex.get('is_merged') else ""
                logger.info(f"  - {ex['example_id']}: similarity = {ex['similarity_score']:.4f}{chunk_info}{storage_info}")
            
            return similar_examples
            
        except Exception as e:
            logger.error(f"Error retrieving similar examples: {str(e)}")
            traceback.print_exc()
            return []
    
    def generate_mapped_json(
        self,
        english_data: Dict,
        french_data: Dict,
        similar_examples: List[Dict],
        component_type: str
    ) -> Tuple[Dict, str]:
        """
        Generate mapped JSON using Claude with RAG context.
        
        Args:
            english_data: English input JSON
            french_data: French input JSON
            similar_examples: Similar mapping examples
            component_type: Component type
            
        Returns:
            Tuple of (mapped_json_dict, reasoning_string)
        """
        try:
            # Build examples context
            examples_context = ""
            for i, example in enumerate(similar_examples, 1):
                examples_context += f"""
Example {i} (similarity: {example['similarity_score']:.4f}):
---
English Input:
{json.dumps(example['english_json'], indent=2, ensure_ascii=False)}

French Input:
{json.dumps(example['french_json'], indent=2, ensure_ascii=False)}

Correct Mapped Output:
{json.dumps(example['mapped_json'], indent=2, ensure_ascii=False)}
---

"""
            
            # Build system prompt - customize based on component type
            if component_type == "text_builder":
                component_rules = """
COMPONENT-SPECIFIC RULES FOR TEXT_BUILDER:
1. PRESERVE ALL ENGLISH FORMATTING AND STYLING:
   - Keep newlines (\\n), line breaks, paragraph breaks
   - Keep bold markers (**text**), italic markers (*text*)
   - Keep bullet point formatting (•, -, *, numbered lists)
   - Keep ANY HTML tags (<br>, <p>, <div>, <span>, etc.)
   - Keep ALL inline CSS styles (style="..." attributes)
   - Keep spacing and indentation
   
2. PRESERVE INLINE HTML/CSS STYLING:
   - If English has HTML tags like <div style="background-color: #004A80; margin: 15px 0px 15px 0px">&nbsp;</div>
   - These tags are STYLING/STRUCTURAL elements (not text content)
   - You MUST include them in the French output
   - Process:
     a) Extract the text content from English (without HTML tags)
     b) Find the corresponding French text
     c) Combine: French text + English HTML tags
   
3. Example with inline HTML/CSS:
   English:
   "Watch for the poll at Facebook.com/Costco Canada or Instagram: *@costco_canada*  
   <div style="background-color: #004A80; margin: 15px 0px 15px 0px; padding: 0px 0px 0px 0px">&nbsp;</div>"
   
   French text (content only, no HTML in French JSON):
   "Ne manquez pas la prochaine question sur Facebook.com/CostcoCanada ou sur Instagram : @costco_canada."
   
   CRITICAL MAPPING LOGIC:
   - Identify text portion: "Watch for the poll..." (English text)
   - Identify HTML portion: "<div style=...>...</div>" (Styling - language-agnostic)
   - Replace ONLY the text portion with French
   - KEEP the HTML portion exactly as-is from English
   
   Correct French output (French text + English HTML styling):
   "Ne manquez pas la prochaine question sur Facebook.com/CostcoCanada ou sur Instagram : *@costco_canada*  
   <div style="background-color: #004A80; margin: 15px 0px 15px 0px; padding: 0px 0px 0px 0px">&nbsp;</div>"
   
   IMPORTANT: Even though French JSON doesn't have the <div>, you MUST include it because:
   - It's a STYLING element from English
   - Styling is language-agnostic (works for both EN and FR)
   - The visual layout must match English
   
4. ONLY REPLACE THE ACTUAL TEXT CONTENT - preserve everything else:
   - Replace: "Watch for the poll" → "Ne manquez pas la prochaine question"
   - Keep: *@costco_canada* (italic markers)
   - Keep: <div style="...">...</div> (HTML/CSS styling)

5. Match the formatting structure of English text exactly, word-for-word translation with same styling

CRITICAL - HANDLING MISSING FRENCH SECTIONS:
If French has FEWER sections than English (e.g., French has 2 sections, English has 3):
- The English version was manually updated by authors (new section added)
- You MUST map existing French content to the correct English sections
- For sections WITHOUT French content:
  * DO NOT generate/hallucinate French text
  * DO NOT use text from RAG examples
  * DO NOT duplicate existing French text
  * LEAVE THE ENGLISH TEXT AS-IS (it will be manually translated later)
  
Example:
English has 3 sections, French has 2 sections:
- Section 1: Use French text from French section 1
- Section 2: Use French text from French section 2  
- Section 3: KEEP ENGLISH TEXT (no French available)

This ensures data integrity - we only use the French text YOU provided in the JSON.
"""
            elif component_type == "ad_builder":
                component_rules = """
COMPONENT-SPECIFIC RULES FOR AD_BUILDER:

🚨 CRITICAL - PREVENT HALLUCINATION 🚨

1. TEXT CONTENT - USE ONLY FRENCH INPUT:
   - For text_content array, ONLY use text from French JSON
   - DO NOT copy English text into French output
   - DO NOT generate or invent new text
   - If French has text "Voir la recette", output MUST have "Voir la recette"
   - If French has text "Recettes", output MUST have "Recettes"
   - NEVER put "See recipe" or "Recipes" in French output

2. IMAGE URLs - USE ONLY FRENCH INPUT:
   - For image array, ONLY use image URLs from French JSON
   - DO NOT copy English image URLs
   - DO NOT use images from English JSON
   - If French has url: "/fr/produit.jpg", output MUST have "/fr/produit.jpg"
   - NEVER use "/en/product.jpg" or English Brandfolder URLs

3. STYLING PRESERVATION (100% MANDATORY):
   Copy these styling fields EXACTLY from English to French output:
   - background_group (entire object with all hex colors)
   - background_color.hex (e.g., "#D3D3D3")
   - text_color.hex
   - border_color.solid.hex (e.g., "#FFFFFF")
   - text_content_placement (e.g., "below_the_ad", "overlay")
   - text_alignment (e.g., "center", "left", "right")

CRITICAL RULE:
- CONTENT (text, images) → from FRENCH input ONLY
- STYLING (colors, alignment) → from ENGLISH input ONLY

Example:
English: image url="/en/product.jpg", text="See recipe", color="#D3D3D3"
French: image url="/fr/produit.jpg", text="Voir la recette", color="#FFFFFF"
OUTPUT: image url="/fr/produit.jpg", text="Voir la recette", color="#D3D3D3"
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^^^^^  ^^^^^^^^^^^^^
         FROM FRENCH                    FROM FRENCH        FROM ENGLISH
"""
            elif component_type == "link_list_with_flyout_references":
                component_rules = """
COMPONENT-SPECIFIC RULES FOR LINK_LIST_WITH_FLYOUT_REFERENCES:

CRITICAL - STYLING PRESERVATION (100% MANDATORY):
You MUST copy these styling fields EXACTLY from English to French output:
1. color_config (entire object):
   - text_color.hex (e.g., "#333333" NOT "#337AB7")
   - link_color.hex
   - hover_color.hex
   - active_color.hex

2. background_color (if present):
   - hex value

3. layout settings:
   - columns
   - spacing
   - alignment

CRITICAL RULE:
French AI may generate incorrect colors like #337AB7 (blue). You MUST:
- IGNORE French color_config completely
- COPY English color_config 100% exactly
- DO NOT use default blue colors
- DO NOT generate new color values

Example:
English has: text_color.hex = "#333333" (dark gray)
French has: text_color.hex = "#337AB7" (blue)
OUTPUT MUST HAVE: text_color.hex = "#333333" (English wins!)

CONTENT MAPPING:
1. Map French link_list items to English structure
2. Replace link text content with French translations
3. Preserve all English styling, UIDs, and structure
4. Keep flyout_references exactly as in English
"""
            elif component_type == "ad_set_costco":
                component_rules = """
COMPONENT-SPECIFIC RULES FOR AD_SET_COSTCO:

CRITICAL UNDERSTANDING:
When splitting 1 French ad_builder → 2 English ad_builders, you MUST analyze the ENGLISH structure first to understand HOW to split.

STEP 1: ANALYZE ENGLISH STRUCTURE
Look at English ad_builder[0] and ad_builder[1]:
- Does ad_builder[0] have an image AND text_content? → It's IMAGE+CAPTION
- Does ad_builder[1] have NO image but has text_content? → It's TEXT-ONLY

STEP 2: UNDERSTAND THE PATTERN
The author manually split the French ad_builder like this:
- English ad_builder[0] = French image + French text_content[0] (the caption that goes with the image)
- English ad_builder[1] = No image + French text_content[1,2,3,...] (remaining text items)

STEP 3: APPLY THE SPLIT

Example with French having 4 text_content items:
```
French ad_builder (combined):
- image: [French image]
- text_content: [
    0: "© Brent Hofacker / stock.adobe.com" (caption_v2),
    1: "**Trempette à l'oignon à la française**" (subheading_v2),
    2: "Envie de trempette? Cette recette..." (body_copy_v2),
    3: "[Voir la recette](/link)" (body_copy_v2)
  ]

Split into:

English ad_builder[0] (IMAGE+CAPTION):
- image: [French image]
- text_content: [
    0: "© Brent Hofacker / stock.adobe.com" (caption_v2)
  ]

English ad_builder[1] (TEXT-ONLY):
- image: [] (empty or null)
- text_content: [
    0: "**Trempette à l'oignon à la française**" (subheading_v2),
    1: "Envie de trempette? Cette recette..." (body_copy_v2),
    2: "[Voir la recette](/link)" (body_copy_v2)
  ]
```

CRITICAL RULES:
1. FIRST text_content item (usually caption_v2) stays with the image in ad_builder[0]
2. REMAINING text_content items go to ad_builder[1] WITHOUT the image
3. Preserve exact structure (select_text_type, select_semantics_type, color, etc.)
4. Include COMPLETE ad_builder structures with nested "entry" objects
5. DO NOT drop, merge, or modify any text items

STRUCTURE FORMAT:
Return complete ad_builder entries with all fields populated from English template.
"""
            else:
                component_rules = ""
            
            system_prompt = f"""You are an expert at mapping French component structures to match English component structures in ContentStack CMS.

SCENARIO:
- English version was manually updated by authors (sections added/removed/reorganized)
- French version is now OUTDATED and doesn't match the new English structure
- Your task: Adapt the French content to fit the updated English structure

Your task is to generate a MAPPED OUTPUT JSON that:
1. Uses the ENGLISH structure as the template (maintains English sections/ordering)
2. Maps existing FRENCH content to the appropriate English sections
3. Handles structural mismatches caused by manual English updates

Component Type: {component_type}

Below are similar examples showing how to map structures correctly:

{examples_context}

CRITICAL GENERAL RULES:
1. Output MUST match English structure exactly (same number of sections, same ordering, same UIDs)
2. Map French content to corresponding English sections based on semantic similarity
3. **PRESERVE ALL ENGLISH STYLING 100% EXACTLY** - This is MANDATORY:
   - background_color, text_color, border_color (all hex values)
   - text_alignment, layout, spacing
   - color_config (entire object)
   - Any field with "color", "style", "alignment" in the name
   - DO NOT generate new colors or styles
   - DO NOT use French styling values
   - COPY English styling fields character-by-character
4. Set locale to "fr-ca" in the output
5. DO NOT duplicate or reuse French content inappropriately
6. Replace ONLY text content (markdown_text, titles, descriptions)
7. Keep ALL structural, styling, and configuration fields from English

{component_rules}

STYLING PRESERVATION EXAMPLE (MANDATORY PATTERN):
All styling fields (background_color, text_color, border_color, text_alignment, etc.) 
MUST be copied from English input, regardless of what French input has.
Only text content (markdown_text, titles, descriptions) should be replaced with French.

Return ONLY the mapped JSON structure. No explanations or reasoning.
"""
            
            # Build user prompt
            user_prompt = f"""Map the following French input to match the English structure:

ENGLISH INPUT (target structure):
{json.dumps(english_data, indent=2, ensure_ascii=False)}

FRENCH INPUT (content to use):
{json.dumps(french_data, indent=2, ensure_ascii=False)}

Generate the mapped output following the examples provided.
"""
            
            # Call Claude
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            logger.info("Calling Claude to generate mapped JSON...")
            response = self.llm.invoke(messages)
            response_text = response.content
            
            # Parse response
            # Try to extract JSON from response
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text.strip()
            
            # Parse JSON - expecting just the mapped structure, not wrapped in an object
            mapped_json = json.loads(json_text)
            reasoning = "LLM-based structural adaptation"
            
            logger.info("✓ Successfully generated mapped JSON")
            
            # CRITICAL: VALIDATE BEFORE ENFORCEMENT (detect hallucination)
            
            # CRITICAL: Validate and enforce styling preservation
            logger.info("🔍 Enforcing styling preservation...")
            mapped_json = self.enforce_styling_preservation(english_data, mapped_json, component_type)
            
            return mapped_json, reasoning
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
            logger.error(f"Response text: {response_text[:500]}...")
            raise
        except Exception as e:
            logger.error(f"Error generating mapped JSON: {str(e)}")
            traceback.print_exc()
            raise
    
    def enforce_styling_preservation(self, english_data: Dict, mapped_json: Dict, component_type: str) -> Dict:
        """
        BRUTALLY FORCE-COPY all styling from English to mapped output.
        Training examples are just REFERENCE - the ACTUAL English JSON must be preserved 100%.
        
        Args:
            english_data: Original English structure being localized
            mapped_json: LLM-generated output
            component_type: Component type
            
        Returns:
            Corrected mapped_json with ALL English styling enforced
        """
        import copy
        result = copy.deepcopy(mapped_json)
        
        logger.info("🔍 FORCE-COPYING ALL STYLING FROM ENGLISH (Training data ignored)...")
        
        # Get entry objects
        eng_entry = english_data.get("entry", english_data)
        mapped_entry = result.get("entry", result)
        
        if not mapped_entry:
            result["entry"] = {}
            mapped_entry = result["entry"]
        
        # ============================================================
        # COMPONENT-SPECIFIC BRUTAL FORCE-COPY (NO MERCY!)
        # ============================================================
        
        if component_type == "ad_builder":
            logger.info("   🎨 ad_builder: FORCE-COPYING ALL STYLING...")
            
            # 1. Force background_group (ALL background/border colors)
            if "background_group" in eng_entry:
                mapped_entry["background_group"] = copy.deepcopy(eng_entry["background_group"])
                bg = eng_entry["background_group"]
                logger.info(f"   ✓ FORCED: background_group")
                if "background_color" in bg:
                    logger.info(f"      → background_color.hex = {bg.get('background_color', {}).get('hex', 'N/A')}")
                if "text_color" in bg:
                    logger.info(f"      → text_color.hex = {bg.get('text_color', {}).get('hex', 'N/A')}")
                if "border_color" in bg:
                    logger.info(f"      → border_color.solid.hex = {bg.get('border_color', {}).get('solid', {}).get('hex', 'N/A')}")
            
            # 2. Force enable_custom_background
            if "enable_custom_background" in eng_entry:
                mapped_entry["enable_custom_background"] = eng_entry["enable_custom_background"]
                logger.info(f"   ✓ FORCED: enable_custom_background = {eng_entry['enable_custom_background']}")
            
            # 3. Force text_alignment
            if "text_content_above_below_the_ad_styles" in eng_entry:
                mapped_entry["text_content_above_below_the_ad_styles"] = copy.deepcopy(
                    eng_entry["text_content_above_below_the_ad_styles"]
                )
                logger.info(f"   ✓ FORCED: text_content_above_below_the_ad_styles = {eng_entry['text_content_above_below_the_ad_styles']}")
            
            # 4. Force text_content_placement
            if "text_content_placement" in eng_entry:
                mapped_entry["text_content_placement"] = eng_entry["text_content_placement"]
                logger.info(f"   ✓ FORCED: text_content_placement = {eng_entry['text_content_placement']}")
            
            # 5. Force color in EACH text_content item
            if "text_content" in eng_entry and "text_content" in mapped_entry:
                for i in range(min(len(eng_entry["text_content"]), len(mapped_entry["text_content"]))):
                    eng_item = eng_entry["text_content"][i]
                    mapped_item = mapped_entry["text_content"][i]
                    
                    if "markdown_text" in eng_item and "markdown_text" in mapped_item:
                        if "color" in eng_item["markdown_text"]:
                            mapped_item["markdown_text"]["color"] = copy.deepcopy(eng_item["markdown_text"]["color"])
                            logger.info(f"   ✓ FORCED: text_content[{i}].markdown_text.color = {eng_item['markdown_text']['color']}")
        
        elif component_type == "link_list_with_flyout_references":
            logger.info("   🎨 link_list: FORCE-COPYING ALL STYLING...")
            
            # 1. Force color_config (THE CRITICAL ONE!)
            if "color_config" in eng_entry:
                mapped_entry["color_config"] = copy.deepcopy(eng_entry["color_config"])
                cc = eng_entry["color_config"]
                logger.info(f"   ✓ FORCED: color_config")
                if "text_color" in cc:
                    logger.info(f"      → text_color.hex = {cc.get('text_color', {}).get('hex', 'N/A')}")
                if "background_color" in cc:
                    logger.info(f"      → background_color.hex = {cc.get('background_color', {}).get('hex', 'N/A')}")
                if "border_color" in cc:
                    logger.info(f"      → border_color.solid.hex = {cc.get('border_color', {}).get('solid', {}).get('hex', 'N/A')}")
            
            # 2. Force layout/spacing
            if "layout" in eng_entry:
                mapped_entry["layout"] = eng_entry["layout"]
                logger.info(f"   ✓ FORCED: layout = {eng_entry['layout']}")
            
            if "spacing" in eng_entry:
                mapped_entry["spacing"] = eng_entry["spacing"]
                logger.info(f"   ✓ FORCED: spacing = {eng_entry['spacing']}")
        
        elif component_type == "ad_set_costco":
            logger.info("   🎨 ad_set_costco: FORCE-COPYING ALL STYLING...")
            
            # Force-copy styling for EACH ad_builder in the set
            if "ad_builder" in eng_entry and "ad_builder" in mapped_entry:
                for i in range(min(len(eng_entry["ad_builder"]), len(mapped_entry["ad_builder"]))):
                    eng_ad = eng_entry["ad_builder"][i]
                    mapped_ad = mapped_entry["ad_builder"][i]
                    
                    logger.info(f"   🎨 ad_set_costco[{i}]: FORCE-COPYING styling...")
                    
                    # Force background_group
                    if "background_group" in eng_ad:
                        mapped_ad["background_group"] = copy.deepcopy(eng_ad["background_group"])
                        logger.info(f"      ✓ FORCED: ad_builder[{i}].background_group")
                    
                    # Force enable_custom_background
                    if "enable_custom_background" in eng_ad:
                        mapped_ad["enable_custom_background"] = eng_ad["enable_custom_background"]
                        logger.info(f"      ✓ FORCED: ad_builder[{i}].enable_custom_background = {eng_ad['enable_custom_background']}")
                    
                    # Force text_alignment
                    if "text_content_above_below_the_ad_styles" in eng_ad:
                        mapped_ad["text_content_above_below_the_ad_styles"] = copy.deepcopy(
                            eng_ad["text_content_above_below_the_ad_styles"]
                        )
                        logger.info(f"      ✓ FORCED: ad_builder[{i}].text_content_above_below_the_ad_styles")
                    
                    # Force text_content_placement
                    if "text_content_placement" in eng_ad:
                        mapped_ad["text_content_placement"] = eng_ad["text_content_placement"]
                        logger.info(f"      ✓ FORCED: ad_builder[{i}].text_content_placement = {eng_ad['text_content_placement']}")
                    
                    # Force color in EACH text_content item
                    if "text_content" in eng_ad and "text_content" in mapped_ad:
                        for j in range(min(len(eng_ad["text_content"]), len(mapped_ad["text_content"]))):
                            eng_item = eng_ad["text_content"][j]
                            mapped_item = mapped_ad["text_content"][j]
                            
                            if "markdown_text" in eng_item and "markdown_text" in mapped_item:
                                if "color" in eng_item["markdown_text"]:
                                    mapped_item["markdown_text"]["color"] = copy.deepcopy(eng_item["markdown_text"]["color"])
                                    logger.info(f"      ✓ FORCED: ad_builder[{i}].text_content[{j}].color")
        
        else:
            # GENERIC FALLBACK: Copy ALL fields with "color", "style", "alignment", "background" in name
            logger.info("   🎨 Generic component: FORCE-COPYING common styling fields...")
            
            def force_copy_styling_fields(eng_obj, mapped_obj, path=""):
                """Recursively copy ANY field with styling keywords"""
                if isinstance(eng_obj, dict) and isinstance(mapped_obj, dict):
                    for key, value in eng_obj.items():
                        is_styling = any(keyword in key.lower() for keyword in 
                                        ['color', 'style', 'alignment', 'background', 'border', 'layout', 'spacing'])
                        
                        if is_styling:
                            mapped_obj[key] = copy.deepcopy(value)
                            logger.info(f"   ✓ FORCED: {path}.{key}")
                        elif key in mapped_obj and isinstance(value, dict):
                            force_copy_styling_fields(value, mapped_obj[key], f"{path}.{key}")
            
            force_copy_styling_fields(eng_entry, mapped_entry, "entry")
        
        logger.info("✅ STYLING ENFORCEMENT COMPLETE - English styling 100% preserved!")
        return result
    
    def calculate_confidence_score(
        self,
        similar_examples: List[Dict],
        mapped_json: Dict
    ) -> float:
        """Calculate confidence score for the mapping."""
        if not similar_examples:
            return 0.3
        
        # Average similarity of examples
        avg_similarity = sum(ex['similarity_score'] for ex in similar_examples) / len(similar_examples)
        
        # Bonus for having more examples
        example_bonus = min(len(similar_examples) * 0.1, 0.2)
        
        confidence = avg_similarity + example_bonus
        return max(0.1, min(1.0, confidence))
    
    def process_mapping(
        self,
        english_data: Dict,
        french_data: Dict,
        component_type: str,
        n_examples: int = 3
    ) -> MappingResult:
        """
        Main method to process mapping request.
        
        Args:
            english_data: English input JSON
            french_data: French input JSON
            component_type: Component type (text_builder, ad_set_costco)
            n_examples: Number of similar examples to retrieve
            
        Returns:
            MappingResult containing mapped JSON and metadata
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {component_type} mapping")
            logger.info(f"{'='*60}")
            
            # Retrieve similar examples
            similar_examples = self.retrieve_similar_examples(
                english_data,
                french_data,
                component_type,
                n_examples
            )
            
            if not similar_examples:
                raise ValueError(f"No similar examples found for {component_type}")
            
            # Generate mapped JSON
            mapped_json, reasoning = self.generate_mapped_json(
                english_data,
                french_data,
                similar_examples,
                component_type
            )
            
            # Calculate confidence
            confidence = self.calculate_confidence_score(
                similar_examples,
                mapped_json
            )
            
            logger.info(f"✓ Mapping completed with confidence: {confidence:.3f}")
            
            return MappingResult(
                mapped_json=mapped_json,
                similar_examples=similar_examples,
                confidence_score=confidence,
                reasoning=reasoning
            )
            
        except Exception as e:
            logger.error(f"Error in process_mapping: {str(e)}")
            traceback.print_exc()
            raise
    
    def get_index_stats(self) -> Dict:
        """Get Pinecone index statistics."""
        try:
            stats = self.index.describe_index_stats()
            return {
                "index_name": self.index_name,
                "total_vectors": stats.total_vector_count,
                "dimension": stats.dimension
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {str(e)}")
            return {}


def main():
    parser = argparse.ArgumentParser(
        description="Generate mapped JSON using RAG-based structure mapping"
    )
    parser.add_argument(
        "--english-file",
        required=True,
        help="Path to English input JSON file"
    )
    parser.add_argument(
        "--french-file",
        required=True,
        help="Path to French input JSON file"
    )
    parser.add_argument(
        "--component-type",
        required=True,
        choices=COLLECTION_CONFIG["supported_components"],
        help="Component type"
    )
    parser.add_argument(
        "--output-file",
        default="mapped_output.json",
        help="Path to save mapped output JSON"
    )
    parser.add_argument(
        "--n-examples",
        type=int,
        default=3,
        help="Number of similar examples to retrieve"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show index statistics and exit"
    )
    
    args = parser.parse_args()
    
    try:
        # Load environment variables
        dotenv.load_dotenv()
        openai_key = os.getenv("OPENAI_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        
        if not openai_key:
            logger.error("OPENAI_API_KEY not found in environment")
            return 1
        
        if not pinecone_key:
            logger.error("PINECONE_API_KEY not found in environment")
            return 1
        
        if not anthropic_key:
            logger.error("ANTHROPIC_API_KEY not found in environment")
            return 1
        
        # Initialize retriever
        retriever = MappingDataRetriever(
            openai_api_key=openai_key,
            pinecone_api_key=pinecone_key,
            anthropic_api_key=anthropic_key
        )
        
        # Show stats if requested
        if args.stats:
            stats = retriever.get_index_stats()
            print(f"\n{'='*60}")
            print(f"Pinecone Index Statistics:")
            print(f"{'='*60}")
            print(f"Index: {stats.get('index_name', 'N/A')}")
            print(f"Total vectors: {stats.get('total_vectors', 0)}")
            print(f"Dimension: {stats.get('dimension', 0)}")
            print(f"{'='*60}\n")
            return 0
        
        # Read input files
        with open(args.english_file, 'r', encoding='utf-8') as f:
            english_data = json.load(f)
        
        with open(args.french_file, 'r', encoding='utf-8') as f:
            french_data = json.load(f)
        
        # Process mapping
        result = retriever.process_mapping(
            english_data,
            french_data,
            args.component_type,
            args.n_examples
        )
        
        # Save output
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(result.mapped_json, f, indent=2, ensure_ascii=False)
        
        # Display results
        print(f"\n{'='*60}")
        print(f"Mapping Results:")
        print(f"{'='*60}")
        print(f"Confidence Score: {result.confidence_score:.3f}")
        print(f"Number of Similar Examples: {len(result.similar_examples)}")
        print(f"\nReasoning:")
        print(result.reasoning)
        
        if result.similar_examples:
            print(f"\nSimilar Examples Used:")
            for ex in result.similar_examples:
                print(f"  - {ex['example_id']}: similarity = {ex['similarity_score']:.4f}")
        
        print(f"\nMapped JSON saved to: {args.output_file}")
        print(f"{'='*60}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
