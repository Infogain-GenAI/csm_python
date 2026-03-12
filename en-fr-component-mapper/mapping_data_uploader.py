"""
Mapping Data Uploader for English-French Component Mapping
Uploads English-French-Mapped triplets to Pinecone for RAG-based structure mapping.

Dataset Structure:
component_data/
  ├── text_builder/
  │   ├── english_input_1.json
  │   ├── french_input_1.json
  │   ├── mapped_output_1.json
  │   └── ... (pairs 2, 3, etc.)
  ├── ad_set_costco/
  │   ├── english_input_1.json
  │   ├── french_input_1.json
  │   ├── mapped_output_1.json
  │   └── ...
  ├── ad_builder/
  │   ├── english_input_1.json
  │   ├── french_input_1.json
  │   ├── mapped_output_1.json
  │   └── ...
  └── link_list_with_flyout_references/
      ├── english_input_1.json
      ├── french_input_1.json
      ├── mapped_output_1.json
      └── ...
"""

import os
import sys
import json
import hashlib
import logging
import argparse
import traceback
from typing import Dict, List, Optional
from pathlib import Path
from openai import OpenAI
import httpx
import dotenv
from pinecone import Pinecone, ServerlessSpec
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
    "supported_components": [
        "text_builder", 
        "ad_set_costco", 
        "ad_builder",
        "link_list_with_flyout_references"
    ],
    "embedding_dimension": 1536
}


class MappingDataUploader:
    """
    Uploads English-French-Mapped JSON triplets to Pinecone.
    
    Each triplet consists of:
    - English input JSON (structure to map FROM)
    - French input JSON (mismatched AI-generated structure)
    - Mapped output JSON (correct structure we want)
    """
    
    def __init__(
        self,
        openai_api_key: str,
        pinecone_api_key: str,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimension: int = 1536,
        cloud: str = "aws",
        region: str = "us-east-1"
    ):
        """Initialize the uploader."""
        # Initialize OpenAI client
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            http_client=httpx.Client(verify=False)
        )
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        
        # Initialize Pinecone
        self.pc = Pinecone(
            api_key=pinecone_api_key,
            pool_threads=4,
            timeout=30
        )
        
        self.index_name = COLLECTION_CONFIG["index_name"]
        
        # Create storage directory for large JSONs
        self.storage_dir = Path(__file__).parent / "vectordb_json_storage"
        self.storage_dir.mkdir(exist_ok=True)
        logger.info(f"JSON storage directory: {self.storage_dir}")
        
        # Check if index exists, create if not
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]
        
        if self.index_name not in existing_indexes:
            logger.info(f"Creating new Pinecone index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=embedding_dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=cloud,
                    region=region
                )
            )
            logger.info(f"✓ Index '{self.index_name}' created successfully")
        else:
            logger.info(f"✓ Using existing index: {self.index_name}")
        
        # Connect to the index
        self.index = self.pc.Index(self.index_name)
        
        logger.info(f"="*70)
        logger.info(f"MappingDataUploader Initialized")
        logger.info(f"="*70)
        logger.info(f"Index: {self.index_name}")
        logger.info(f"Description: {COLLECTION_CONFIG['description']}")
        logger.info(f"Supported components: {COLLECTION_CONFIG['supported_components']}")
        logger.info(f"Embedding model: {embedding_model} (dim: {embedding_dimension})")
        logger.info(f"="*70)
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI."""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def read_json_file(self, file_path: str) -> Dict:
        """Read and parse JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {file_path}: {str(e)}")
            raise
    
    def create_embedding_text(
        self,
        english_data: Dict,
        french_data: Dict,
        component_type: str
    ) -> str:
        """
        Create embedding text from English and French structures.
        Focuses on the mismatch patterns between structures.
        """
        # Extract relevant structural information
        if component_type == "text_builder":
            eng_sections = english_data.get("entry", {}).get("multiple_text_section_group", [])
            fr_sections = french_data.get("entry", {}).get("multiple_text_section_group", [])
            
            # Count text_section_content in each section
            eng_counts = [len(section.get("text_section_content", [])) for section in eng_sections]
            fr_counts = [len(section.get("text_section_content", [])) for section in fr_sections]
            
            # Extract text types
            eng_types = []
            for section in eng_sections:
                for content in section.get("text_section_content", []):
                    eng_types.append(content.get("select_text_type", "unknown"))
            
            fr_types = []
            for section in fr_sections:
                for content in section.get("text_section_content", []):
                    fr_types.append(content.get("select_text_type", "unknown"))
            
            embedding_text = f"""Component: text_builder
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
            
            # Count text_content in each ad_builder
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
            
            embedding_text = f"""Component: ad_set_costco
English ad_builders: {len(eng_text_counts)}
English text_content counts: {eng_text_counts}

French ad_builders: {len(fr_text_counts)}
French text_content counts: {fr_text_counts}

Mismatch pattern: {len(eng_text_counts)} English ad_builders vs {len(fr_text_counts)} French ad_builders
"""
        
        elif component_type == "ad_builder":
            # Extract text_content structure from ad_builder
            eng_entry = english_data.get("entry", {})
            fr_entry = french_data.get("entry", {})
            
            eng_block = eng_entry.get("ad_builder_block", {})
            fr_block = fr_entry.get("ad_builder_block", {})
            
            eng_text_content = eng_block.get("text_content", [])
            fr_text_content = fr_block.get("text_content", [])
            
            # Extract text types
            eng_types = [item.get("select_text_type", "unknown") for item in eng_text_content]
            fr_types = [item.get("select_text_type", "unknown") for item in fr_text_content]
            
            # Check for image presence
            eng_has_image = bool(eng_entry.get("image", []))
            fr_has_image = bool(fr_entry.get("image", []))
            
            embedding_text = f"""Component: ad_builder
English text_content items: {len(eng_text_content)}
English text types: {', '.join(eng_types)}
English has image: {eng_has_image}

French text_content items: {len(fr_text_content)}
French text types: {', '.join(fr_types)}
French has image: {fr_has_image}

Mismatch pattern: {len(eng_text_content)} English items vs {len(fr_text_content)} French items
"""
        
        elif component_type == "link_list_with_flyout_references":
            # Extract link_list structure
            eng_entry = english_data.get("entry", {})
            fr_entry = french_data.get("entry", {})
            
            eng_links = eng_entry.get("link_list", [])
            fr_links = fr_entry.get("link_list", [])
            
            # Count flyout references
            eng_flyout_count = sum(1 for link in eng_links if link.get("link_flyout_ref"))
            fr_flyout_count = sum(1 for link in fr_links if link.get("link_flyout_ref"))
            
            # Check for nested structures
            eng_has_nested = any(
                link.get("link_flyout_ref", [{}])[0].get("entry", {}).get("link_list_simple_ref")
                for link in eng_links
            )
            fr_has_nested = any(
                link.get("link_flyout_ref", [{}])[0].get("entry", {}).get("link_list_simple_ref")
                for link in fr_links
            )
            
            embedding_text = f"""Component: link_list_with_flyout_references
English link_list items: {len(eng_links)}
English flyout references: {eng_flyout_count}
English has nested link_list_simple: {eng_has_nested}

French link_list items: {len(fr_links)}
French flyout references: {fr_flyout_count}
French has nested link_list_simple: {fr_has_nested}

Mismatch pattern: {len(eng_links)} English links vs {len(fr_links)} French links
"""
        
        else:
            # Fallback: use entire JSON as text
            embedding_text = f"Component: {component_type}\nEnglish: {json.dumps(english_data)}\nFrench: {json.dumps(french_data)}"
        
        return embedding_text
    
    def calculate_metadata_size(self, metadata: Dict) -> int:
        """Calculate metadata size in bytes."""
        return len(json.dumps(metadata, ensure_ascii=False).encode('utf-8'))
    
    def save_large_json(self, example_id: str, english_data: Dict, french_data: Dict, mapped_data: Dict) -> str:
        """
        Save large JSONs to external file and return file path.
        
        Args:
            example_id: Unique example ID
            english_data: English input JSON
            french_data: French input JSON  
            mapped_data: Mapped output JSON
            
        Returns:
            Relative file path for storage
        """
        filename = f"{example_id}.json"
        filepath = self.storage_dir / filename
        
        storage_data = {
            "example_id": example_id,
            "english_json": english_data,
            "french_json": french_data,
            "mapped_json": mapped_data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(storage_data, f, indent=2, ensure_ascii=False)
        
        # Return relative path for portability
        return f"vectordb_json_storage/{filename}"
    
    def load_large_json(self, storage_path: str) -> Dict:
        """
        Load large JSONs from external file.
        
        Args:
            storage_path: Relative file path
            
        Returns:
            Dict with english_json, french_json, mapped_json
        """
        filepath = Path(__file__).parent / storage_path
        
        if not filepath.exists():
            logger.error(f"Storage file not found: {filepath}")
            return {}
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def create_compact_metadata(
        self, 
        example_id: str, 
        component_type: str, 
        english_data: Dict, 
        french_data: Dict,
        storage_path: str
    ) -> Dict:
        """
        Create compact metadata that fits under 40KB limit.
        Stores only essential info + file reference, not full JSONs.
        
        Args:
            example_id: Unique example ID
            component_type: Component type
            english_data: English input (for statistics only)
            french_data: French input (for statistics only)
            storage_path: Path to external JSON file
            
        Returns:
            Compact metadata dict
        """
        metadata = {
            "component_type": component_type,
            "example_id": example_id,
            "storage_path": storage_path,  # Reference to external file
            "storage_version": "v1"  # For future compatibility
        }
        
        # Add component-specific statistics (lightweight)
        if component_type == "text_builder":
            metadata["english_sections"] = len(english_data.get("entry", {}).get("multiple_text_section_group", []))
            metadata["french_sections"] = len(french_data.get("entry", {}).get("multiple_text_section_group", []))
        elif component_type == "ad_builder":
            eng_text_content = english_data.get("entry", {}).get("ad_builder_block", {}).get("text_content", [])
            fr_text_content = french_data.get("entry", {}).get("ad_builder_block", {}).get("text_content", [])
            metadata["english_text_items"] = len(eng_text_content)
            metadata["french_text_items"] = len(fr_text_content)
        elif component_type == "link_list_with_flyout_references":
            eng_links = english_data.get("entry", {}).get("link_list", [])
            fr_links = french_data.get("entry", {}).get("link_list", [])
            metadata["english_links"] = len(eng_links)
            metadata["french_links"] = len(fr_links)
        elif component_type == "ad_set_costco":
            eng_ad_content = english_data.get("entry", {}).get("ad_content", [])
            fr_ad_content = french_data.get("entry", {}).get("ad_content", [])
            metadata["english_ad_items"] = len(eng_ad_content)
            metadata["french_ad_items"] = len(fr_ad_content)
        
        return metadata
    
    def chunk_large_json(self, data: Dict, component_type: str, max_items: int = None) -> List[Dict]:
        """
        Split large JSON into chunks based on component type.
        
        Args:
            data: JSON data to chunk
            component_type: Component type
            max_items: Maximum items per chunk (auto-calculated if None)
        
        Returns:
            List of chunks (each chunk is a dict with subset of data)
        """
        if component_type == "link_list_with_flyout_references":
            # Split by link_list array
            entry = data.get("entry", {})
            link_list = entry.get("link_list", [])
            
            if not link_list:
                return [data]
            
            # Auto-calculate chunk size if not specified
            if max_items is None:
                # Start with half the items and adjust if needed
                max_items = max(1, len(link_list) // 2)
            
            chunks = []
            for i in range(0, len(link_list), max_items):
                chunk_data = {
                    "entry": {
                        **entry,
                        "link_list": link_list[i:i + max_items]
                    }
                }
                chunks.append(chunk_data)
            
            return chunks
        
        elif component_type == "ad_builder":
            # Split by text_content array
            entry = data.get("entry", {})
            ad_builder_block = entry.get("ad_builder_block", {})
            text_content = ad_builder_block.get("text_content", [])
            
            if not text_content:
                return [data]
            
            if max_items is None:
                max_items = max(1, len(text_content) // 2)
            
            chunks = []
            for i in range(0, len(text_content), max_items):
                chunk_data = {
                    "entry": {
                        **entry,
                        "ad_builder_block": {
                            **ad_builder_block,
                            "text_content": text_content[i:i + max_items]
                        }
                    }
                }
                chunks.append(chunk_data)
            
            return chunks
        
        elif component_type == "text_builder":
            # Split by multiple_text_section_group array
            entry = data.get("entry", {})
            sections = entry.get("multiple_text_section_group", [])
            
            if not sections:
                return [data]
            
            if max_items is None:
                max_items = max(1, len(sections) // 2)
            
            chunks = []
            for i in range(0, len(sections), max_items):
                chunk_data = {
                    "entry": {
                        **entry,
                        "multiple_text_section_group": sections[i:i + max_items]
                    }
                }
                chunks.append(chunk_data)
            
            return chunks
        
        else:
            # For other types, return as single chunk
            return [data]
    
    def upload_triplet(
        self,
        english_path: str,
        french_path: str,
        mapped_path: str,
        component_type: str,
        example_id: str
    ) -> bool:
        """
        Upload a single English-French-Mapped triplet to Pinecone.
        Uses external JSON storage for large components to avoid 40KB metadata limit.
        
        Args:
            english_path: Path to English input JSON
            french_path: Path to French input JSON
            mapped_path: Path to mapped output JSON
            component_type: Component type (text_builder, ad_set_costco)
            example_id: Unique example ID (e.g., "text_builder_1")
        """
        try:
            # Read all three JSON files
            english_data = self.read_json_file(english_path)
            french_data = self.read_json_file(french_path)
            mapped_data = self.read_json_file(mapped_path)
            
            # ALWAYS use external storage for large components
            # This avoids the 40KB metadata limit entirely
            logger.info(f"   → Saving JSONs to external storage...")
            storage_path = self.save_large_json(example_id, english_data, french_data, mapped_data)
            
            # Create compact metadata (just statistics + file reference)
            metadata = self.create_compact_metadata(
                example_id,
                component_type,
                english_data,
                french_data,
                storage_path
            )
            
            # Verify metadata is small
            metadata_size = self.calculate_metadata_size(metadata)
            logger.info(f"   → Compact metadata: {metadata_size:,} bytes")
            
            if metadata_size > 38960:  # Still too large (shouldn't happen with compact metadata)
                logger.error(f"   ✗ Even compact metadata is too large ({metadata_size:,} bytes)")
                return False
            
            # Create embedding text from English and French structures
            embedding_text = self.create_embedding_text(
                english_data,
                french_data,
                component_type
            )
            
            # Generate embedding
            embedding = self.generate_embedding(embedding_text)
            
            # Store in Pinecone (metadata is now small)
            self.index.upsert(
                vectors=[
                    {
                        "id": example_id,
                        "values": embedding,
                        "metadata": metadata
                    }
                ]
            )
            
            logger.info(f"✓ Uploaded: {example_id} (metadata: {metadata_size:,} bytes, JSON storage: {storage_path})")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to upload {example_id}: {str(e)}")
            traceback.print_exc()
            return False
    
    def upload_dataset(self, data_directory: str) -> Dict[str, int]:
        """
        Upload entire dataset from component_data directory.
        
        Expected structure:
        data_directory/
          ├── text_builder/
          │   ├── english_input_1.json
          │   ├── french_input_1.json
          │   ├── mapped_output_1.json
          │   └── ...
          └── ad_set_costco/
              ├── english_input_1.json
              ├── french_input_1.json
              ├── mapped_output_1.json
              └── ...
        """
        results = {"success": 0, "failed": 0}
        data_path = Path(data_directory)
        
        if not data_path.exists():
            logger.error(f"Data directory not found: {data_directory}")
            return results
        
        # Process each component type
        for component_type in COLLECTION_CONFIG["supported_components"]:
            component_dir = data_path / component_type
            
            if not component_dir.exists():
                logger.warning(f"Component directory not found: {component_dir}")
                continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing component: {component_type}")
            logger.info(f"{'='*60}")
            
            # Find all triplets by looking for english_input_*.json files
            english_files = sorted(component_dir.glob("english_input_*.json"))
            
            for english_file in english_files:
                # Extract the number from filename (e.g., "1" from "english_input_1.json")
                filename = english_file.stem
                number = filename.replace("english_input_", "")
                
                # Build corresponding file paths
                french_file = component_dir / f"french_input_{number}.json"
                mapped_file = component_dir / f"mapped_output_{number}.json"
                
                # Check if all three files exist
                if not french_file.exists():
                    logger.warning(f"Missing french_input_{number}.json, skipping")
                    continue
                
                if not mapped_file.exists():
                    logger.warning(f"Missing mapped_output_{number}.json, skipping")
                    continue
                
                # Upload the triplet
                example_id = f"{component_type}_{number}"
                success = self.upload_triplet(
                    str(english_file),
                    str(french_file),
                    str(mapped_file),
                    component_type,
                    example_id
                )
                
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
        
        return results
    
    def get_index_stats(self) -> Dict:
        """Get Pinecone index statistics."""
        try:
            stats = self.index.describe_index_stats()
            return {
                "index_name": self.index_name,
                "total_vectors": stats.total_vector_count,
                "dimension": stats.dimension,
                "namespaces": stats.namespaces
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {str(e)}")
            return {}


def main():
    parser = argparse.ArgumentParser(
        description="Upload English-French-Mapped triplets to Pinecone"
    )
    parser.add_argument(
        "--data-dir",
        default="component_data",
        help="Directory containing component data (default: component_data)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show index statistics and exit"
    )
    parser.add_argument(
        "--cloud",
        default="aws",
        choices=["aws", "gcp", "azure"],
        help="Cloud provider"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="Cloud region"
    )
    
    args = parser.parse_args()
    
    try:
        # Load environment variables
        dotenv.load_dotenv()
        openai_key = os.getenv("OPENAI_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")
        
        if not openai_key:
            logger.error("OPENAI_API_KEY not found in environment")
            return 1
        
        if not pinecone_key:
            logger.error("PINECONE_API_KEY not found in environment")
            return 1
        
        # Initialize uploader
        uploader = MappingDataUploader(
            openai_api_key=openai_key,
            pinecone_api_key=pinecone_key,
            cloud=args.cloud,
            region=args.region
        )
        
        # Show stats if requested
        if args.stats:
            stats = uploader.get_index_stats()
            print(f"\n{'='*60}")
            print(f"Pinecone Index Statistics:")
            print(f"{'='*60}")
            print(f"Index: {stats.get('index_name', 'N/A')}")
            print(f"Total vectors: {stats.get('total_vectors', 0)}")
            print(f"Dimension: {stats.get('dimension', 0)}")
            print(f"{'='*60}\n")
            return 0
        
        # Upload dataset
        logger.info(f"Starting dataset upload from: {args.data_dir}")
        results = uploader.upload_dataset(args.data_dir)
        
        print(f"\n{'='*60}")
        print(f"Upload Results:")
        print(f"{'='*60}")
        print(f"Successfully uploaded: {results['success']}")
        print(f"Failed: {results['failed']}")
        
        # Show final stats
        stats = uploader.get_index_stats()
        print(f"\n{'='*60}")
        print(f"Final Index Statistics:")
        print(f"{'='*60}")
        print(f"Index: {stats.get('index_name', 'N/A')}")
        print(f"Total vectors: {stats.get('total_vectors', 0)}")
        print(f"Dimension: {stats.get('dimension', 0)}")
        print(f"{'='*60}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
