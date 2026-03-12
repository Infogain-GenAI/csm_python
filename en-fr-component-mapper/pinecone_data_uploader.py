import os
import json
import logging
import warnings
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from openai import OpenAI
import hashlib
from datetime import datetime
import argparse
import dotenv
import tiktoken
import traceback
import httpx
from pinecone import Pinecone, ServerlessSpec
import time
import urllib3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress SSL warnings from urllib3 (Pinecone connection retries are expected)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Reduce urllib3 logging level to suppress retry warnings
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)


# ============================================================================
# COLLECTION CONFIGURATIONS
# Each collection maps to a separate Pinecone index
# ============================================================================
COLLECTION_CONFIGS = {
    "html_json_mappings": {
        "description": "HTML to JSON schema mappings for RAG",
        "index_name": "html-json-mappings",  # Dedicated Pinecone index
        "supported_file_types": [
            "text_builder",
            "ad_builder", 
            "feature_highlight_card_v2",
            "ad_set_costco",
            "link_list_with_flyout_references",
            "button_set",
            "ad_with_popup",
            "accordion_set",
            "bullet_detail_accordion",
            "content_divider",
            "link_list_simple",
            "custom_rich_text",
            "program_card"
        ],
        "html_extension": ".html",
        "json_extension": ".json"
    },
    "content_layout_architecture": {
        "description": "Content layout architecture HTML to JSON mappings",
        "index_name": "content-layout-architecture",  # Dedicated Pinecone index
        "supported_file_types": ["content_layout"],  # Single flat directory
        "html_extension": ".html",
        "json_extension": ".json",
        "auto_detect_types": False,  # Files are in flat directory structure
        "flat_directory": True  # Files are directly in data_dir without subdirectories
    }
}


class TextSplitter:
    """Handles intelligent text splitting for embeddings with token limit management."""
    
    OPENAI_TOKEN_LIMIT = 8191
    
    def __init__(self, model_name: str = "text-embedding-3-small", max_tokens: int = 6000):
        self.model_name = model_name
        self.max_tokens = min(max_tokens, self.OPENAI_TOKEN_LIMIT - 500)
        
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            logger.warning(f"Model {model_name} not found, using cl100k_base encoding")
        
        logger.info(f"TextSplitter initialized with max_tokens={self.max_tokens}")
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        return len(self.encoding.encode(text)) 
    
    def validate_token_count(self, text: str, context: str = "") -> None:
        """Validate that text doesn't exceed token limit."""
        token_count = self.count_tokens(text)
        if token_count > self.OPENAI_TOKEN_LIMIT:
            raise ValueError(
                f"{context}Text has {token_count} tokens, exceeds OpenAI limit of {self.OPENAI_TOKEN_LIMIT}. "
                f"This should have been chunked properly."
            )
    
    def split_text_by_tokens(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = 100
    ) -> List[str]:
        """Split text by token count with overlap."""
        if chunk_size is None:
            chunk_size = self.max_tokens
        
        chunk_size = min(chunk_size, self.OPENAI_TOKEN_LIMIT - 500)
        
        tokens = self.encoding.encode(text)
        total_tokens = len(tokens)
        
        if total_tokens <= chunk_size:
            return [text]
        
        chunks = []
        start_idx = 0
        
        while start_idx < total_tokens:
            end_idx = min(start_idx + chunk_size, total_tokens)
            chunk_tokens = tokens[start_idx:end_idx]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            if end_idx >= total_tokens:
                break
            
            start_idx = end_idx - chunk_overlap
        
        logger.info(f"Split text into {len(chunks)} chunks (total tokens: {total_tokens})")
        return chunks
    
    def split_with_semantic_boundaries(
        self,
        text: str,
        chunk_size: int = None,
        chunk_overlap: int = 100
    ) -> List[str]:
        """Split text respecting semantic boundaries (paragraphs)."""
        if chunk_size is None:
            chunk_size = self.max_tokens
        
        chunk_size = min(chunk_size, self.OPENAI_TOKEN_LIMIT - 500)
        
        if self.count_tokens(text) <= chunk_size:
            return [text]
        
        paragraphs = text.split('\n\n')
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for paragraph in paragraphs:
            para_tokens = self.count_tokens(paragraph)
            
            if para_tokens > chunk_size:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                para_chunks = self.split_text_by_tokens(paragraph, chunk_size, chunk_overlap)
                chunks.extend(para_chunks)
            
            elif current_tokens + para_tokens <= chunk_size:
                current_chunk.append(paragraph)
                current_tokens += para_tokens
            else:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_tokens = para_tokens
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        logger.info(f"Split text into {len(chunks)} chunks with semantic boundaries")
        
        validated_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_tokens = self.count_tokens(chunk)
            if chunk_tokens > chunk_size:
                logger.warning(
                    f"Chunk {i} still has {chunk_tokens} tokens after semantic split. "
                    f"Applying token-based split..."
                )
                sub_chunks = self.split_text_by_tokens(chunk, chunk_size, chunk_overlap)
                validated_chunks.extend(sub_chunks)
            else:
                validated_chunks.append(chunk)
        
        return validated_chunks


class PineconeDataUploader:
    """Uploads HTML-JSON pairs to Pinecone with intelligent text splitting.
    
    Each collection uses a dedicated Pinecone index:
    - html_json_mappings → html-json-mappings index
    - content_layout_architecture → content-layout-architecture index
    """
    
    def __init__(
        self,
        openai_api_key: str,
        pinecone_api_key: str,
        collection_name: str = "html_json_mappings",
        embedding_model: str = "text-embedding-3-small",
        embedding_dimension: int = 1536,
        max_tokens_per_chunk: int = 6000,
        enable_chunking: bool = True,
        cloud: str = "aws",
        region: str = "us-east-1"
    ):
        """
        Initialize Pinecone Data Uploader.
        
        Args:
            openai_api_key: OpenAI API key for embeddings
            pinecone_api_key: Pinecone API key
            collection_name: Collection name (maps to dedicated Pinecone index)
                           - "html_json_mappings" → uses "html-json-mappings" index
                           - "content_layout_architecture" → uses "content-layout-architecture" index
            embedding_model: OpenAI embedding model name
            embedding_dimension: Embedding vector dimension (1536 for text-embedding-3-small)
            max_tokens_per_chunk: Maximum tokens per chunk
            enable_chunking: Whether to enable text chunking
            cloud: Cloud provider (aws, gcp, azure)
            region: Cloud region
        """
        # Initialize OpenAI client
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            http_client=httpx.Client(verify=False)
        )
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.enable_chunking = enable_chunking
        self.collection_name = collection_name
        
        # Load collection configuration
        if collection_name not in COLLECTION_CONFIGS:
            raise ValueError(
                f"Unknown collection: {collection_name}. "
                f"Available: {list(COLLECTION_CONFIGS.keys())}"
            )
        
        self.config = COLLECTION_CONFIGS[collection_name]
        
        # Get index name from config (each collection has its own index)
        self.index_name = self.config["index_name"]
        
        self.supported_file_types = self.config["supported_file_types"]
        self.html_extension = self.config["html_extension"]
        self.json_extension = self.config["json_extension"]
        self.auto_detect_types = self.config.get("auto_detect_types", False)
        self.flat_directory = self.config.get("flat_directory", False)
        
        # Initialize text splitter
        self.text_splitter = TextSplitter(
            model_name=embedding_model,
            max_tokens=max_tokens_per_chunk
        )
        
        # Initialize Pinecone with optimized connection settings
        self.pc = Pinecone(
            api_key=pinecone_api_key,
            pool_threads=4,  # Optimize connection pooling
            timeout=30  # Increase timeout to reduce connection errors
        )
        
        # Check if index exists, if not create it
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
            # Wait for index to be ready
            logger.info("Waiting for index to be ready...")
            time.sleep(10)
        else:
            logger.info(f"Using existing Pinecone index: {self.index_name}")
        
        # Connect to the index
        self.index = self.pc.Index(self.index_name)
        
        logger.info(f"="*70)
        logger.info(f"PineconeDataUploader Initialized")
        logger.info(f"="*70)
        logger.info(f"Collection: {collection_name}")
        logger.info(f"Pinecone Index: {self.index_name}")
        logger.info(f"Description: {self.config['description']}")
        logger.info(f"Text chunking: {'enabled' if enable_chunking else 'disabled'}")
        logger.info(f"Max tokens per chunk: {max_tokens_per_chunk}")
        logger.info(f"Embedding model: {embedding_model} (dim: {embedding_dimension})")
        logger.info(f"Directory structure: {'flat (files in data_dir)' if self.flat_directory else 'subdirectories (files in type folders)'}")
        if not self.flat_directory:
            logger.info(f"Auto-detect file types: {self.auto_detect_types}")
        logger.info(f"="*70)
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI."""
        try:
            self.text_splitter.validate_token_count(text, "Single embedding: ")
            
            response = self.openai_client.embeddings.create(
                input=text,
                model=self.embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch."""
        try:
            # Validate all texts first
            for i, text in enumerate(texts):
                token_count = self.text_splitter.count_tokens(text)
                if token_count > TextSplitter.OPENAI_TOKEN_LIMIT:
                    raise ValueError(
                        f"Chunk {i} has {token_count} tokens, exceeds OpenAI limit of "
                        f"{TextSplitter.OPENAI_TOKEN_LIMIT}. This chunk needs further splitting."
                    )
                logger.debug(f"Chunk {i}: {token_count} tokens (OK)")
            
            batch_size = 100
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                logger.info(f"Sending batch {i//batch_size + 1} with {len(batch)} texts to OpenAI...")
                
                response = self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                logger.info(f"Successfully generated {len(batch_embeddings)} embeddings")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {str(e)}")
            logger.error("Token counts for failed batch:")
            for i, text in enumerate(texts):
                token_count = self.text_splitter.count_tokens(text)
                logger.error(f"  Chunk {i}: {token_count} tokens")
            raise
    
    def generate_document_id(self, html_path: str, file_type: str) -> str:
        """Generate a unique document ID."""
        hash_input = f"{file_type}_{Path(html_path).stem}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def read_file_content(self, file_path: str) -> str:
        """Read file content with error handling."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            raise
    
    def process_html_content(self, html_content: str, doc_id: str) -> List[Tuple[str, Dict]]:
        """Process HTML content and split into chunks if needed."""
        try:
            token_count = self.text_splitter.count_tokens(html_content)
            logger.info(f"HTML content token count: {token_count}")
            
            if not self.enable_chunking or token_count <= self.text_splitter.max_tokens:
                return [(html_content, {
                    "is_chunked": False,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "chunk_tokens": token_count
                })]
            
            chunks = self.text_splitter.split_with_semantic_boundaries(html_content)
            
            chunks_with_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_metadata = {
                    "is_chunked": True,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_tokens": self.text_splitter.count_tokens(chunk)
                }
                chunks_with_metadata.append((chunk, chunk_metadata))
            
            logger.info(f"✓ Split into {len(chunks)} chunks for doc_id: {doc_id}")
            return chunks_with_metadata
            
        except Exception as e:
            logger.error(f"Error processing HTML content: {str(e)}")
            raise
    
    def upload_file_pair(
        self,
        html_path: str,
        json_path: str,
        file_type: str
    ) -> bool:
        """Upload a single HTML-JSON file pair to Pinecone."""
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {Path(html_path).name}")
            logger.info(f"File type: {file_type}")
            
            # Read files
            html_content = self.read_file_content(html_path)
            json_content = self.read_file_content(json_path)
            
            # Validate JSON
            try:
                json_schema = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {json_path}: {str(e)}")
                return False
            
            # Generate document ID
            doc_id = self.generate_document_id(html_path, file_type)
            
            # Process HTML content into chunks
            chunks_with_metadata = self.process_html_content(html_content, doc_id)
            
            # Prepare vectors for batch upsert
            vectors_to_upsert = []
            
            for chunk_content, chunk_metadata in chunks_with_metadata:
                chunk_embedding = self.generate_embedding(chunk_content)
                
                chunk_id = f"{doc_id}_chunk_{chunk_metadata['chunk_index']}"
                
                # Prepare metadata for Pinecone (must be flat key-value pairs)
                pinecone_metadata = {
                    "document_id": doc_id,
                    "file_type": file_type,
                    "filename": Path(html_path).name,
                    "upload_timestamp": datetime.now().isoformat(),
                    "is_chunked": chunk_metadata["is_chunked"],
                    "chunk_index": chunk_metadata["chunk_index"],
                    "total_chunks": chunk_metadata["total_chunks"],
                    "chunk_tokens": chunk_metadata.get("chunk_tokens", 0),
                    "content": chunk_content[:1000],  # Store first 1000 chars for preview
                    "data_type": "html_content"  # Tag to differentiate from JSON schemas
                }
                
                vectors_to_upsert.append({
                    "id": chunk_id,
                    "values": chunk_embedding,
                    "metadata": pinecone_metadata
                })
                
                logger.info(
                    f"✓ Prepared chunk {chunk_metadata['chunk_index'] + 1}/"
                    f"{chunk_metadata['total_chunks']} "
                    f"({chunk_metadata.get('chunk_tokens', 'N/A')} tokens) - ID: {chunk_id}"
                )
            
            # Batch upsert to Pinecone (no namespace needed - dedicated index)
            if vectors_to_upsert:
                self.index.upsert(vectors=vectors_to_upsert)
                logger.info(f"✓ Upserted {len(vectors_to_upsert)} vectors to Pinecone")
            
            # Store JSON schema
            self._store_json_schema(doc_id, file_type, json_content, json_schema)
            
            logger.info(f"✓ Successfully processed {Path(html_path).name}")
            return True
            
        except Exception as e:
            logger.error(f"Error uploading file pair: {str(e)}")
            traceback.print_exc()
            return False
    
    def _store_json_schema(
        self,
        doc_id: str,
        file_type: str,
        json_content: str,
        json_schema: Dict
    ):
        """Store JSON schema in same index with data_type tag.
        Handles large JSON files by chunking if they exceed Pinecone's metadata limit.
        """
        try:
            # Pinecone metadata limit is 40KB (40960 bytes)
            PINECONE_METADATA_LIMIT = 40960
            SAFE_METADATA_SIZE = 35000  # Leave buffer for other metadata fields
            
            json_size = len(json_content.encode('utf-8'))
            
            # Check if JSON content fits in metadata
            if json_size <= SAFE_METADATA_SIZE:
                # Store directly in metadata (small JSON)
                json_doc_id = f"{doc_id}_json_schema"
                
                json_metadata = {
                    "document_id": doc_id,
                    "file_type": file_type,
                    "upload_timestamp": datetime.now().isoformat(),
                    "json_keys": ",".join(json_schema.keys()) if isinstance(json_schema, dict) else "",
                    "json_size": json_size,
                    "json_content": json_content,  # Store full JSON in metadata
                    "data_type": "json_schema",
                    "is_chunked": False,
                    "chunk_index": 0,
                    "total_chunks": 1
                }
                
                # Create a simple embedding for the JSON schema
                simple_embed_text = f"JSON schema for {file_type}: {json_content[:500]}"
                simple_embedding = self.generate_embedding(simple_embed_text)
                
                # Upsert to Pinecone
                self.index.upsert(
                    vectors=[{
                        "id": json_doc_id,
                        "values": simple_embedding,
                        "metadata": json_metadata
                    }]
                )
                
                logger.info(f"✓ Stored JSON schema: {json_doc_id} ({json_size} bytes)")
                
            else:
                # JSON is too large - chunk it
                logger.info(f"JSON is large ({json_size} bytes), chunking for storage...")
                
                # Split JSON content into chunks
                json_chunks = []
                current_pos = 0
                chunk_index = 0
                
                while current_pos < len(json_content):
                    # Calculate chunk size in characters (approximate)
                    chunk_end = min(current_pos + SAFE_METADATA_SIZE, len(json_content))
                    chunk = json_content[current_pos:chunk_end]
                    json_chunks.append(chunk)
                    current_pos = chunk_end
                
                # Store each chunk as a separate vector
                vectors_to_upsert = []
                for i, chunk in enumerate(json_chunks):
                    chunk_id = f"{doc_id}_json_schema_chunk_{i}"
                    chunk_size = len(chunk.encode('utf-8'))
                    
                    chunk_metadata = {
                        "document_id": doc_id,
                        "file_type": file_type,
                        "upload_timestamp": datetime.now().isoformat(),
                        "json_keys": ",".join(json_schema.keys()) if isinstance(json_schema, dict) else "",
                        "json_size": json_size,  # Total size
                        "json_content": chunk,  # This chunk's content
                        "data_type": "json_schema",
                        "is_chunked": True,
                        "chunk_index": i,
                        "total_chunks": len(json_chunks),
                        "chunk_size": chunk_size
                    }
                    
                    # Create embedding from chunk content
                    embed_text = f"JSON schema for {file_type} (part {i+1}/{len(json_chunks)}): {chunk[:500]}"
                    chunk_embedding = self.generate_embedding(embed_text)
                    
                    vectors_to_upsert.append({
                        "id": chunk_id,
                        "values": chunk_embedding,
                        "metadata": chunk_metadata
                    })
                
                # Batch upsert all chunks
                if vectors_to_upsert:
                    self.index.upsert(vectors=vectors_to_upsert)
                    logger.info(
                        f"✓ Stored JSON schema in {len(json_chunks)} chunks "
                        f"({json_size} bytes total)"
                    )
            
            # Verify storage
            try:
                if json_size <= SAFE_METADATA_SIZE:
                    json_doc_id = f"{doc_id}_json_schema"
                    fetch_result = self.index.fetch(ids=[json_doc_id])
                    if json_doc_id in fetch_result.vectors:
                        logger.info(f"✓ Verified JSON storage for {json_doc_id}")
                else:
                    # Verify first chunk
                    first_chunk_id = f"{doc_id}_json_schema_chunk_0"
                    fetch_result = self.index.fetch(ids=[first_chunk_id])
                    if first_chunk_id in fetch_result.vectors:
                        logger.info(f"✓ Verified JSON storage (first chunk)")
            except Exception as verify_error:
                logger.warning(f"Could not verify JSON storage: {str(verify_error)}")
            
        except Exception as e:
            logger.error(f"Error storing JSON schema for {doc_id}: {str(e)}")
            traceback.print_exc()
    
    def _discover_file_types(self, data_directory: str) -> List[str]:
        """Auto-discover file types from directory structure."""
        data_path = Path(data_directory)
        discovered_types = []
        
        if not data_path.exists():
            logger.warning(f"Data directory does not exist: {data_directory}")
            return discovered_types
        
        # Look for subdirectories that contain HTML files
        for item in data_path.iterdir():
            if item.is_dir():
                html_files = list(item.glob(f"*{self.html_extension}"))
                if html_files:
                    discovered_types.append(item.name)
        
        return discovered_types
    
    def upload_batch(
        self,
        data_directory: str,
        html_extension: str = None,
        json_extension: str = None
    ) -> Dict[str, bool]:
        """Upload batch of HTML-JSON file pairs."""
        results = {}
        data_path = Path(data_directory)
        
        # Use extensions from config if not provided
        if html_extension is None:
            html_extension = self.html_extension
        if json_extension is None:
            json_extension = self.json_extension
        
        if not data_path.exists():
            logger.error(f"Data directory does not exist: {data_directory}")
            return results
        
        # Handle flat directory structure (files directly in data_directory)
        if self.flat_directory:
            logger.info("Processing flat directory structure (files directly in data_dir)")
            
            # Get the file type from supported_file_types (should have exactly one entry)
            if not self.supported_file_types or len(self.supported_file_types) != 1:
                logger.error("Flat directory mode requires exactly one file_type in supported_file_types")
                return results
            
            file_type = self.supported_file_types[0]
            html_files = list(data_path.glob(f"*{html_extension}"))
            
            logger.info(f"Found {len(html_files)} HTML files in {data_directory}")
            
            for html_file in html_files:
                json_file = html_file.with_suffix(json_extension)
                
                if not json_file.exists():
                    logger.warning(f"JSON file not found for {html_file}: {json_file}")
                    continue
                
                file_key = html_file.name
                success = self.upload_file_pair(
                    str(html_file),
                    str(json_file),
                    file_type
                )
                results[file_key] = success
            
            return results
        
        # Handle subdirectory structure (original behavior)
        # Determine file types to process
        if self.auto_detect_types:
            file_types_to_process = self._discover_file_types(data_directory)
            if not file_types_to_process:
                logger.warning("No file types discovered in auto-detect mode")
                return results
        else:
            file_types_to_process = self.supported_file_types
        
        logger.info(f"Processing file types: {file_types_to_process}")
        
        for file_type in file_types_to_process:
            type_dir = data_path / file_type
            
            if not type_dir.exists():
                logger.warning(f"Directory not found for {file_type}: {type_dir}")
                continue
            
            html_files = list(type_dir.glob(f"*{html_extension}"))
            
            for html_file in html_files:
                json_file = html_file.with_suffix(json_extension)
                
                if not json_file.exists():
                    logger.warning(f"JSON file not found for {html_file}: {json_file}")
                    continue
                
                file_key = f"{file_type}/{html_file.name}"
                success = self.upload_file_pair(
                    str(html_file),
                    str(json_file),
                    file_type
                )
                results[file_key] = success
        
        return results
    
    def get_index_stats(self) -> Dict:
        """Get Pinecone index statistics."""
        try:
            stats = self.index.describe_index_stats()
            
            # Count vectors by data_type (html_content vs json_schema)
            # Since we're using a dedicated index per collection, we can query for counts
            html_count = 0
            json_count = 0
            
            # Try to get counts by data_type if available
            if hasattr(stats, 'namespaces') and stats.namespaces:
                # If namespaces exist, count from there
                total_vectors = stats.total_vector_count
            else:
                total_vectors = stats.total_vector_count
            
            return {
                "collection_name": self.collection_name,
                "index_name": self.index_name,
                "total_vector_count": total_vectors,
                "dimension": stats.dimension,
                "description": self.config["description"],
                "note": "This index is dedicated to the collection. HTML content and JSON schemas are stored together with 'data_type' metadata tag."
            }
            
        except Exception as e:
            logger.error(f"Error getting index stats: {str(e)}")
            return {"error": str(e)}
    
    def search_similar(
        self,
        query: str,
        n_results: int = 5,
        file_type: Optional[str] = None,
        data_type: str = "html_content"
    ) -> Dict:
        """Search for similar documents in Pinecone.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            file_type: Optional filter by file_type (e.g., "text_builder")
            data_type: Filter by data_type ("html_content" or "json_schema")
        """
        try:
            query_embedding = self.generate_embedding(query)
            
            # Prepare filter
            filter_dict = {"data_type": {"$eq": data_type}}
            
            if file_type:
                filter_dict["file_type"] = {"$eq": file_type}
            
            # Query Pinecone (no namespace needed - dedicated index)
            results = self.index.query(
                vector=query_embedding,
                top_k=n_results,
                filter=filter_dict,
                include_metadata=True
            )
            
            return {
                "matches": [
                    {
                        "id": match.id,
                        "score": match.score,
                        "metadata": match.metadata
                    }
                    for match in results.matches
                ]
            }
            
        except Exception as e:
            logger.error(f"Error searching index: {str(e)}")
            return {"error": str(e)}
    
    def delete_all_vectors(self):
        """Delete all vectors from the index (use with caution!)."""
        try:
            logger.warning(f"Deleting all vectors from index: {self.index_name}...")
            self.index.delete(delete_all=True)
            logger.info("✓ All vectors deleted")
        except Exception as e:
            logger.error(f"Error deleting vectors: {str(e)}")
    
    def get_json_schema(self, doc_id: str) -> Optional[Dict]:
        """Retrieve JSON schema for a specific document ID.
        Handles both single-vector and chunked JSON schemas.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Dictionary containing JSON schema or None if not found
        """
        try:
            # First, try to fetch as single vector
            json_id = f"{doc_id}_json_schema"
            result = self.index.fetch(ids=[json_id])
            
            if json_id in result.vectors:
                metadata = result.vectors[json_id].metadata
                json_content = metadata.get('json_content')
                
                if json_content:
                    return json.loads(json_content)
            
            # If not found, try chunked format
            # Query for all chunks with this doc_id
            chunk_results = self.index.query(
                vector=[0.0] * self.embedding_dimension,  # Dummy vector
                top_k=100,  # Get up to 100 chunks
                filter={
                    "document_id": {"$eq": doc_id},
                    "data_type": {"$eq": "json_schema"},
                    "is_chunked": {"$eq": True}
                },
                include_metadata=True
            )
            
            if chunk_results.matches:
                # Sort chunks by chunk_index
                chunks = sorted(
                    chunk_results.matches,
                    key=lambda x: x.metadata.get('chunk_index', 0)
                )
                
                # Reconstruct JSON from chunks
                json_content = ''.join([
                    chunk.metadata.get('json_content', '')
                    for chunk in chunks
                ])
                
                if json_content:
                    logger.info(f"Reconstructed JSON from {len(chunks)} chunks")
                    return json.loads(json_content)
            
            logger.warning(f"JSON schema not found for doc_id: {doc_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving JSON schema: {str(e)}")
            traceback.print_exc()
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Upload HTML-JSON pairs to Pinecone with intelligent chunking"
    )
    parser.add_argument(
        "--data-dir",
        required=False,  # Not required if just listing collections
        help="Directory containing the data"
    )
    parser.add_argument(
        "--collection-name",
        default="html_json_mappings",
        choices=list(COLLECTION_CONFIGS.keys()),
        help=f"Collection name (maps to dedicated index). Available: {list(COLLECTION_CONFIGS.keys())}"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=5500,
        help="Maximum tokens per chunk (recommended: 5000-6000)"
    )
    parser.add_argument(
        "--disable-chunking",
        action="store_true",
        help="Disable automatic text chunking"
    )
    parser.add_argument(
        "--list-collections",
        action="store_true",
        help="List available collections and their configurations"
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
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=1536,
        help="Embedding dimension (1536 for text-embedding-3-small)"
    )
    
    args = parser.parse_args()
    
    # List collections if requested
    if args.list_collections:
        print("\n" + "="*60)
        print("Available Collections and Their Pinecone Indexes:")
        print("="*60)
        for name, config in COLLECTION_CONFIGS.items():
            print(f"\nCollection: {name}")
            print(f"  Pinecone Index: {config['index_name']}")
            print(f"  Description: {config['description']}")
            print(f"  Flat Directory: {config.get('flat_directory', False)}")
            if config['supported_file_types']:
                print(f"  Supported types: {', '.join(config['supported_file_types'][:5])}")
                if len(config['supported_file_types']) > 5:
                    print(f"    ... and {len(config['supported_file_types']) - 5} more")
        print("\n")
        return 0
    
    # Check that data-dir is provided for actual uploads
    if not args.data_dir:
        parser.error("--data-dir is required for uploads. Use --list-collections to see available collections.")
     
    try:
        # Load environment variables
        dotenv.load_dotenv()
        openai_key = os.getenv("OPENAI_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")
        
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        if not pinecone_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        # Initialize uploader
        uploader = PineconeDataUploader(
            openai_api_key=openai_key,
            pinecone_api_key=pinecone_key,
            collection_name=args.collection_name,
            embedding_dimension=args.embedding_dimension,
            max_tokens_per_chunk=args.max_tokens,
            enable_chunking=not args.disable_chunking,
            cloud=args.cloud,
            region=args.region
        )
        
        logger.info("Starting batch upload...")
        results = uploader.upload_batch(args.data_dir)
        
        successful = sum(1 for success in results.values() if success)
        total = len(results)
        
        print(f"\n{'='*60}")
        print(f"Upload Results:")
        print(f"{'='*60}")
        print(f"Successfully uploaded: {successful}/{total}")
        
        if total > 0:
            print(f"\nDetailed results:")
            for file_path, success in results.items():
                status = "✓" if success else "✗"
                print(f"  {status} {file_path}")
        
        stats = uploader.get_index_stats()
        print(f"\n{'='*60}")
        print(f"Pinecone Index Statistics:")
        print(f"{'='*60}")
        print(f"Collection: {stats.get('collection_name', 'N/A')}")
        print(f"Index: {stats.get('index_name', 'N/A')}")
        print(f"Description: {stats.get('description', 'N/A')}")
        print(f"Total vectors: {stats.get('total_vector_count', 0)}")
        print(f"Dimension: {stats.get('dimension', 0)}")
        print(f"\nNote: {stats.get('note', 'N/A')}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
