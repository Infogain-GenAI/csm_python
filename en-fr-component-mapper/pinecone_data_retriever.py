"""
Pinecone Data Retriever
Retrieves similar examples from Pinecone and generates JSON schemas using RAG approach.

This module provides a DataRetriever class that:
1. Connects to Pinecone indexes (replacing ChromaDB)
2. Generates embeddings using OpenAI
3. Queries Pinecone for similar HTML examples
4. Retrieves associated JSON schemas (handles chunked data)
5. Uses Claude to generate new JSON schemas based on similar examples
"""

import os
import re
import json
import logging
import warnings
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import argparse
from dataclasses import dataclass
import tiktoken
import dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
import httpx
from pinecone import Pinecone
import traceback
import urllib3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Suppress SSL warnings from urllib3 (Pinecone connection retries are expected)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# Reduce urllib3 logging level to suppress retry warnings
logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)


# ============================================================================
# COLLECTION CONFIGURATIONS (Must match uploader configurations)
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
            "custom_rich_text",
            "ad_with_popup",
            "accordion_set",
            "bullet_detail_accordion",
            "content_divider",
            "link_list_simple",
            "program_card"
        ]
    },
    "content_layout_architecture": {
        "description": "Content layout architecture HTML to JSON mappings",
        "index_name": "content-layout-architecture",  # Dedicated Pinecone index
        "supported_file_types": ["content_layout"],  # Single type for flat structure
        "flat_directory": True
    }
}


@dataclass
class RetrievalResult:
    """Data class to hold retrieval results."""
    generated_json: Dict
    similar_examples: List[Dict]
    confidence_score: float


class TextValidator:
    """Validates and manages text token counts for embeddings."""
    
    OPENAI_TOKEN_LIMIT = 8191
    
    def __init__(self, model_name: str = "text-embedding-3-small"):
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            logger.warning(f"Model {model_name} not found, using cl100k_base encoding")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))
    
    def truncate_to_token_limit(self, text: str, max_tokens: int = 7500) -> str:
        """Truncate text to specified token limit."""
        tokens = self.encoding.encode(text)
        
        if len(tokens) <= max_tokens:
            return text
        
        logger.warning(f"Truncating text from {len(tokens)} to {max_tokens} tokens")
        truncated_tokens = tokens[:max_tokens]
        return self.encoding.decode(truncated_tokens)
    
    def validate_token_count(self, text: str, context: str = "") -> None:
        """Validate that text doesn't exceed token limit."""
        token_count = self.count_tokens(text)
        if token_count > self.OPENAI_TOKEN_LIMIT:
            raise ValueError(
                f"{context}Text has {token_count} tokens, exceeds limit of {self.OPENAI_TOKEN_LIMIT}"
            )


class DataRetriever:
    """
    Pinecone-based data retriever for HTML-to-JSON RAG pipeline.
    
    This class replaces ChromaDB with Pinecone while maintaining exact same interface.
    It handles:
    - Embedding generation via OpenAI
    - Similar example retrieval from Pinecone
    - JSON schema reconstruction (including chunked JSONs)
    - LLM-based JSON generation using Claude
    """
    
    def __init__(
        self,
        openai_api_key: str,
        pinecone_api_key: Optional[str] = None,
        collection_name: str = "html_json_mappings",
        embedding_model: str = "text-embedding-3-small",
        llm_model: str = "gpt-4o-mini",
        embedding_dimension: int = 1536
    ):
        """
        Initialize Pinecone data retriever.
        
        Args:
            openai_api_key: OpenAI API key for embeddings
            pinecone_api_key: Pinecone API key (optional, will use env var)
            collection_name: Collection name (maps to Pinecone index)
            embedding_model: OpenAI embedding model
            llm_model: LLM model name (not used with Claude, kept for compatibility)
            embedding_dimension: Embedding vector dimension
        """
        # Initialize OpenAI client
        self.openai_client = OpenAI(
            api_key=openai_api_key,
            http_client=httpx.Client(verify=False)
        )
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.collection_name = collection_name
        self.embedding_dimension = embedding_dimension
        
        # Load collection configuration
        if collection_name not in COLLECTION_CONFIGS:
            raise ValueError(
                f"Collection '{collection_name}' not found in COLLECTION_CONFIGS. "
                f"Available collections: {list(COLLECTION_CONFIGS.keys())}"
            )
        
        self.config = COLLECTION_CONFIGS[collection_name]
        self.index_name = self.config["index_name"]
        self.supported_file_types = self.config["supported_file_types"]
        
        # Initialize token validator
        self.token_validator = TextValidator(model_name=embedding_model)
        
        # Initialize Pinecone
        if pinecone_api_key is None:
            pinecone_api_key = os.getenv("PINECONE_API_KEY")
            if not pinecone_api_key:
                raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        # Configure Pinecone with better connection pooling and timeout settings
        self.pc = Pinecone(
            api_key=pinecone_api_key,
            pool_threads=4,  # Optimize connection pooling
            timeout=30  # Increase timeout to reduce connection errors
        )
        
        # Connect to Pinecone index
        try:
            self.index = self.pc.Index(self.index_name)
            logger.info(f"✓ Connected to Pinecone index: {self.index_name}")
            logger.info(f"  Description: {self.config['description']}")
            logger.info(f"  Supported file types: {self.supported_file_types}")
            
            # Verify index stats (with retry logic to avoid initial connection errors)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    stats = self.index.describe_index_stats()
                    logger.info(f"  Index stats: {stats.total_vector_count} vectors")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"Retry {attempt + 1}/{max_retries} for index stats...")
                        continue
                    else:
                        logger.warning(f"Could not get index stats: {str(e)}")
            
        except Exception as e:
            logger.error(f"✗ Error connecting to Pinecone index '{self.index_name}': {str(e)}")
            logger.error(f"  Make sure the index exists and PINECONE_API_KEY is set correctly")
            raise
        
        logger.info(f"DataRetriever initialized successfully with Pinecone backend")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text with token validation and truncation.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            token_count = self.token_validator.count_tokens(text)
            
            if token_count > TextValidator.OPENAI_TOKEN_LIMIT:
                logger.warning(
                    f"Text has {token_count} tokens, truncating to stay within limit"
                )
                text = self.token_validator.truncate_to_token_limit(text, max_tokens=7500)
                token_count = self.token_validator.count_tokens(text)
                logger.info(f"Truncated to {token_count} tokens")
            
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def clean_html_content(self, html_content: str) -> str:
        """
        Clean HTML content for embedding generation.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Cleaned HTML content
        """
        cleaned = ' '.join(html_content.split())
        cleaned = cleaned.replace('\n', ' ').replace('\t', ' ')
        return cleaned.strip()
    
    def _get_json_schema_from_pinecone(self, doc_id: str) -> Optional[Dict]:
        """
        Retrieve JSON schema from Pinecone for a specific document ID.
        Handles both single-vector and chunked JSON schemas.
        
        Args:
            doc_id: Document ID (without _json_schema suffix)
            
        Returns:
            Dictionary containing JSON schema or None if not found
        """
        try:
            # Remove any chunk suffix from doc_id to get base doc_id
            if '_chunk_' in doc_id:
                base_doc_id = doc_id.rsplit('_chunk_', 1)[0]
            else:
                base_doc_id = doc_id
            
            # Try single vector first (standard format)
            json_id = f"{base_doc_id}_json_schema"
            logger.debug(f"Fetching JSON with ID: {json_id}")
            
            result = self.index.fetch(ids=[json_id])
            
            if json_id in result.vectors:
                metadata = result.vectors[json_id].metadata
                json_content = metadata.get('json_content')
                
                if json_content:
                    logger.debug(f"✓ Found single-vector JSON for {base_doc_id}")
                    return json.loads(json_content)
            
            # If not found as single vector, try chunked format
            logger.debug(f"Single vector not found, trying chunked format for {base_doc_id}")
            
            # Create a dummy vector for filtering query
            dummy_vector = [0.0] * self.embedding_dimension
            
            # Query for all chunks with this doc_id
            chunk_results = self.index.query(
                vector=dummy_vector,
                top_k=100,  # Get up to 100 chunks
                filter={
                    "document_id": base_doc_id,
                    "data_type": "json_schema",
                    "is_chunked": True
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
                    logger.info(f"✓ Reconstructed JSON from {len(chunks)} chunks for {base_doc_id}")
                    return json.loads(json_content)
            
            logger.warning(f"✗ JSON schema not found for doc_id: {base_doc_id}")
            return None
            
        except json.JSONDecodeError as je:
            logger.error(f"✗ Failed to parse JSON for {doc_id}: {str(je)}")
            return None
        except Exception as e:
            logger.error(f"✗ Error retrieving JSON schema for {doc_id}: {str(e)}")
            traceback.print_exc()
            return None
    
    def retrieve_similar_examples(
        self,
        html_content: str,
        file_type: Optional[str] = None,
        n_results: int = 5
    ) -> List[Dict]:
        """
        Retrieve similar HTML examples from Pinecone with their JSON schemas.
        
        Args:
            html_content: HTML content to find similar examples for
            file_type: Optional file type for filtering
            n_results: Number of similar examples to retrieve
            
        Returns:
            List of dictionaries containing similar examples with metadata
        """
        try:
            cleaned_html = self.clean_html_content(html_content)
            logger.info(f"File type for retrieval: {file_type}")
            
            # Prepare embedding text (add file type prefix if provided)
            if file_type:
                embedding_text = f"Type: {file_type}\n\n{cleaned_html}"
            else:
                embedding_text = cleaned_html
            
            token_count = self.token_validator.count_tokens(embedding_text)
            logger.info(f"Query text has {token_count} tokens")
            
            # Truncate if needed
            if token_count > 7500:
                logger.warning("Query text too long, truncating...")
                embedding_text = self.token_validator.truncate_to_token_limit(
                    embedding_text, 
                    max_tokens=7500
                )
            
            # Generate query embedding
            query_embedding = self.generate_embedding(embedding_text)
            
            # Build filter for Pinecone query
            filter_dict = {"data_type": "html_content"}  # Only query HTML vectors (matches uploader)
            
            if file_type and file_type in self.supported_file_types:
                filter_dict["file_type"] = file_type
            
            # Query Pinecone
            logger.info(f"Querying Pinecone with filter: {filter_dict}")
            results = self.index.query(
                vector=query_embedding,
                top_k=n_results,
                filter=filter_dict,
                include_metadata=True,
                include_values=False  # Don't need the embedding vectors back
            )
            
            if not results.matches:
                logger.warning("No similar documents found in Pinecone")
                return []
            
            logger.info(f"Found {len(results.matches)} similar documents")
            
            similar_examples = []
            
            # Process each match and fetch its JSON schema
            for i, match in enumerate(results.matches):
                try:
                    doc_id = match.id
                    metadata = match.metadata
                    score = match.score
                    
                    # Get HTML content from metadata (stored as 'content' in uploader)
                    html_content_result = metadata.get('content', '')
                    
                    # Get the base document ID (remove _chunk_X suffix if present)
                    if '_chunk_' in doc_id:
                        base_doc_id = doc_id.rsplit('_chunk_', 1)[0]
                    else:
                        base_doc_id = doc_id
                    
                    logger.info(f"Processing match {i+1}: doc_id={doc_id}, base_doc_id={base_doc_id}, score={score:.4f}")
                    
                    # Retrieve JSON schema from Pinecone
                    json_schema = self._get_json_schema_from_pinecone(base_doc_id)
                    
                    if json_schema:
                        logger.info(f"  ✓ Retrieved JSON schema with {len(json_schema)} keys: {list(json_schema.keys())[:5]}")
                    else:
                        logger.warning(f"  ✗ No JSON schema found for {base_doc_id}")
                        json_schema = {}
                    
                    # Build example structure (matching ChromaDB format)
                    example = {
                        "document_id": doc_id,
                        "html_content": html_content_result,
                        "json_schema": json_schema,
                        "metadata": metadata,
                        "similarity_score": score,  # Pinecone returns cosine similarity directly
                    }
                    similar_examples.append(example)
                    
                except Exception as e:
                    logger.error(f"Error processing document {doc_id}: {str(e)}")
                    traceback.print_exc()
                    continue
            
            logger.info(f"Retrieved {len(similar_examples)} similar examples")
            
            # Validation: Check if we got valid JSON schemas
            valid_json_count = sum(1 for ex in similar_examples if ex['json_schema'])
            logger.info(f"Valid JSON schemas retrieved: {valid_json_count}/{len(similar_examples)}")
            
            if valid_json_count == 0:
                logger.error("WARNING: No valid JSON schemas found in any similar examples!")
            
            return similar_examples
            
        except Exception as e:
            logger.error(f"Error retrieving similar examples: {str(e)}")
            traceback.print_exc()
            return []
    
    def generate_json_schema(
        self,
        html_content: str,
        similar_examples: List[Dict],
        file_type: Optional[str] = None,
        model_definition: Optional[str] = None
    ) -> Tuple[Dict, str]:
        """
        Generate JSON schema for given HTML using Claude LLM and similar examples.
        
        Args:
            html_content: HTML content to generate JSON for
            similar_examples: List of similar examples with JSON schemas
            file_type: Optional file type
            model_definition: Optional model definition/instructions
            
        Returns:
            Tuple of (generated_json_dict, reasoning_string)
        """
        
        def robust_json_cleaner(text: str) -> str:
            """Comprehensive JSON cleaning function."""
            
            patterns = [
                r'```(?:json)?\s*(\{.*?\})\s*```',
                r'`(\{.*?\})`',
                r'(\{.*\})',
            ]
            
            json_text = text.strip()
            for pattern in patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    json_text = match.group(1)
                    break
            
            # Remove comments
            json_text = re.sub(r'//.*$', '', json_text, flags=re.MULTILINE)
            json_text = re.sub(r'/\*.*?\*/', '', json_text, flags=re.DOTALL)
            json_text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_text)
            
            # Fix line-by-line issues
            lines = json_text.split('\n')
            cleaned_lines = []
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Remove trailing commas
                line = re.sub(r',(\s*[}\]])', r'\1', line)
                
                # Add missing commas between properties
                if (line.endswith('"') and 
                    i + 1 < len(lines) and 
                    lines[i + 1].strip().startswith('"') and 
                    ':' in lines[i + 1] and
                    not line.endswith('",') and
                    not line.endswith('}') and
                    not line.endswith(']')):
                    line += ','
                
                cleaned_lines.append(line)
            
            return '\n'.join(cleaned_lines)
        
        def validate_and_parse_json(text: str, max_attempts: int = 5) -> dict:
            """Attempt to parse JSON with progressive cleaning."""
            
            for attempt in range(max_attempts):
                try:
                    if attempt == 0:
                        return json.loads(text)
                    elif attempt == 1:
                        cleaned = robust_json_cleaner(text)
                        return json.loads(cleaned)
                    elif attempt == 2:
                        cleaned = robust_json_cleaner(text)
                        cleaned = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', cleaned)
                        return json.loads(cleaned)
                    elif attempt == 3:
                        cleaned = robust_json_cleaner(text)
                        open_braces = cleaned.count('{')
                        close_braces = cleaned.count('}')
                        
                        if open_braces > close_braces:
                            cleaned += '}' * (open_braces - close_braces)
                        
                        return json.loads(cleaned)
                    else:
                        logger.warning("Using fallback JSON from first example")
                        if similar_examples and similar_examples[0].get('json_schema'):
                            return similar_examples[0]['json_schema']
                        return {}
                            
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"JSON parse attempt {attempt + 1} failed: {str(e)}")
                    if attempt == max_attempts - 1:
                        logger.error(f"All JSON parsing attempts failed")
                        if similar_examples and similar_examples[0].get('json_schema'):
                            return similar_examples[0]['json_schema']
                        return {}
                    continue
            
            return {}
        
        def post_process_json(generated_json: dict, examples: List[Dict]) -> dict:
            """Ensure generated JSON matches expected structure."""
            if not examples or not generated_json:
                return generated_json
            
            example_json = examples[0].get('json_schema', {})
            if not example_json:
                return generated_json
            
            # Validate that all required keys are present
            for key in example_json:
                if key not in generated_json:
                    logger.warning(f"Missing key '{key}' in generated JSON")
            
            return generated_json
        
        try:
            # Filter valid examples (with JSON schemas)
            valid_examples = [ex for ex in similar_examples if ex.get('json_schema')]
            
            if not valid_examples:
                logger.error("No valid JSON schemas in similar examples - cannot generate!")
                return {}, "No valid examples with JSON schemas found"
            
            logger.info(f"Using {len(valid_examples)} valid examples with JSON schemas")
            
            # Prepare examples for prompt
            examples_text = ""
            max_examples = min(5, len(valid_examples))
            
            for i, example in enumerate(valid_examples[:max_examples], 1):
                html_preview = example['html_content']
                
                examples_text += f"\nExample {i}:\n"
                examples_text += f"Type: {example['metadata'].get('file_type', 'unknown')}\n"
                examples_text += f"HTML:  ```html{html_preview}```\n"
                examples_text += f"JSON: ```json{json.dumps(example['json_schema'], indent=2)}```\n"
                examples_text += f"Similarity: {example['similarity_score']:.3f}\n"
                examples_text += "-" * 50
            
            html_for_prompt = html_content
            
            # Build system prompt
            system_prompt = f"""You are an expert at converting HTML to JSON precisely. You MUST return valid, parseable JSON.

CRITICAL REQUIREMENTS:
1. Return ONLY valid JSON - no markdown, comments, or explanations
2. All strings must be properly quoted and closed
3. All property names must be in double quotes
4. Use proper comma placement (no trailing commas)
5. Ensure all brackets and braces are balanced
6. Follow the EXACT structure from examples
7. Include ALL required properties from examples
8. Do NOT invent or omit any fields ex: if the example has "title", you must have "title". If you add "category_title", it will result in schema validation error.
9. Adhere to the data types of the attributes provided in the example. If the example shows a field as an array, do not change it to an object.

Your response must be parseable by json.loads() without preprocessing.


# Additional Instructions: CRITICAL
{model_definition}
"""

            # Build user prompt
            user_prompt = f"""REFERENCE STRUCTURE (DO NOT copy data from here - ONLY use this to understand the JSON key names and structure):
{examples_text}

NEW HTML INPUT (Extract ALL data from here):```html
{html_for_prompt}```

CRITICAL INSTRUCTIONS:
1. Review the DATA MODEL DEFINITION to understand what each field represents and any constraints
2. Examine the REFERENCE STRUCTURE to understand the exact key names and JSON hierarchy
3. Extract ALL actual data values from the NEW HTML INPUT - never use data from the reference examples
4. Copy text EXACTLY as written in the NEW HTML INPUT without modifications, paraphrasing, or rewording
5. Map extracted data to the correct fields based on the DATA MODEL DEFINITION
6. If the NEW HTML INPUT doesn't contain data for a field, use null or empty string - do NOT use example data
7. Ensure data types match the DATA MODEL DEFINITION (strings, numbers, booleans, arrays, etc.)
8. Copy URLs and other content exactly as they appear in the NEW HTML INPUT

VALIDATION CHECKLIST:
- Does the output conform to the DATA MODEL DEFINITION?
- Are you using the correct key names from the REFERENCE STRUCTURE?
- Is every text value copied exactly from the NEW HTML INPUT?
- Did you avoid using ANY data from the reference examples?
- Are data types correct per the model definition?
- Is the JSON properly formatted and valid?
- Are all additional instructions followed?
- Are the urls and image links matching with those present in NEW HTML INPUT?

Return ONLY valid JSON with no explanations, code blocks, or additional text:"""

            total_prompt = system_prompt + "\n" + user_prompt
            prompt_tokens = self.token_validator.count_tokens(total_prompt)
            logger.info(f"Prompt token count: {prompt_tokens}")
             
            # Generate with retries
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    # Use Claude for JSON generation
                    claude_key = os.getenv("ANTHROPIC_API_KEY")
                    
                    if not claude_key:
                        raise ValueError("ANTHROPIC_API_KEY not found in environment")

                    llm = ChatAnthropic(
                        model="claude-sonnet-4-20250514",
                        temperature=0.1, 
                        max_tokens=62000,
                        api_key=claude_key
                    )

                    # Create messages
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_prompt)
                    ]

                    # Get response
                    response = llm.invoke(messages)

                    # Extract the generated text
                    generated_text = response.content.strip()
                    
                    # Parse and validate JSON
                    parsed_json = validate_and_parse_json(generated_text)
                    
                    # Post-process to ensure structure matches
                    final_json = post_process_json(parsed_json, valid_examples)
                    
                    if not isinstance(final_json, dict):
                        raise ValueError(f"Result is not a dictionary: {type(final_json)}")
                    
                    reasoning = f"Successfully generated JSON on attempt {attempt + 1}"
                    logger.info(reasoning)
                    return final_json, reasoning
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    
                    if attempt < max_retries - 1:
                        system_prompt += f"\n\nPREVIOUS ATTEMPT FAILED: {str(e)}\nBe extra careful with JSON syntax."
                    else:
                        logger.error("All attempts failed, using fallback")
                        if valid_examples and valid_examples[0].get('json_schema'):
                            return valid_examples[0]['json_schema'], "Used fallback from similar example"
                        return {}, "All attempts failed"
            
            return {}, "Failed to generate JSON"
            
        except Exception as e:
            logger.error(f"Unexpected error in generate_json_schema: {str(e)}")
            traceback.print_exc()
            if similar_examples and similar_examples[0].get('json_schema'):
                return similar_examples[0]['json_schema'], f"Error fallback: {str(e)}"
            return {}, f"Unexpected error: {str(e)}"
    
    def calculate_confidence_score(
        self,
        similar_examples: List[Dict],
        generated_json: Dict
    ) -> float:
        """
        Calculate confidence score for generated JSON.
        
        Args:
            similar_examples: List of similar examples used
            generated_json: Generated JSON dictionary
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not similar_examples:
            return 0.1
        
        # Average similarity of examples
        avg_similarity = sum(ex['similarity_score'] for ex in similar_examples) / len(similar_examples)
        
        # Penalty for JSON complexity
        json_complexity = len(str(generated_json)) / 1000
        complexity_penalty = min(json_complexity * 0.1, 0.3)
        
        # Bonus for having more examples
        example_bonus = min(len(similar_examples) * 0.1, 0.2)
        
        confidence = avg_similarity + example_bonus - complexity_penalty
        return max(0.1, min(1.0, confidence))
    
    def process_html(
        self,
        html_content: str,
        file_type: Optional[str] = None,
        n_examples: int = 5,
        model_definition: Optional[str] = None
    ) -> RetrievalResult:
        """
        Main method to process HTML and generate JSON schema.
        
        This is the primary entry point that orchestrates the entire RAG pipeline:
        1. Retrieve similar examples from Pinecone
        2. Generate JSON schema using Claude with RAG context
        3. Calculate confidence score
        
        Args:
            html_content: HTML content to process
            file_type: Optional file type for filtering
            n_examples: Number of similar examples to retrieve
            model_definition: Optional model definition/instructions
            
        Returns:
            RetrievalResult containing generated JSON, examples, and confidence
        """
        try:
            logger.info(f"Processing HTML content (length: {len(html_content)} chars)")
            
            # Step 1: Retrieve similar examples from Pinecone
            similar_examples = self.retrieve_similar_examples(
                html_content=html_content,
                file_type=file_type,
                n_results=n_examples
            )
            
            if not similar_examples:
                logger.warning("No similar examples found")
                return RetrievalResult(
                    generated_json={},
                    similar_examples=[],
                    confidence_score=0.1,
                )
            
            # Step 2: Generate JSON schema using LLM
            generated_json, reasoning = self.generate_json_schema(
                html_content=html_content,
                similar_examples=similar_examples,
                file_type=file_type,
                model_definition=model_definition
            )
            
            # Step 3: Calculate confidence score
            confidence_score = self.calculate_confidence_score(
                similar_examples=similar_examples,
                generated_json=generated_json
            )
            
            logger.info(f"Generated JSON schema with confidence: {confidence_score:.3f}")
            
            return RetrievalResult(
                generated_json=generated_json,
                similar_examples=similar_examples,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            logger.error(f"Error processing HTML: {str(e)}")
            traceback.print_exc()
            return RetrievalResult(
                generated_json={},
                similar_examples=[],
                confidence_score=0.0
            )
    
    def get_database_info(self) -> Dict:
        """
        Get information about the Pinecone index contents.
        
        Returns:
            Dictionary with index statistics and metadata
        """
        try:
            stats = self.index.describe_index_stats()
            
            # Get sample of vectors to determine file type distribution
            # Create a dummy vector for sampling
            dummy_vector = [0.0] * self.embedding_dimension
            
            sample_results = self.index.query(
                vector=dummy_vector,
                top_k=100,
                filter={"data_type": "html_content"},  # Only HTML vectors (matches uploader)
                include_metadata=True
            )
            
            file_type_counts = {}
            for match in sample_results.matches:
                file_type = match.metadata.get('file_type', 'unknown')
                file_type_counts[file_type] = file_type_counts.get(file_type, 0) + 1
            
            return {
                "total_vectors": stats.total_vector_count,
                "index_name": self.index_name,
                "collection_name": self.collection_name,
                "file_type_distribution_sample": file_type_counts,
                "supported_file_types": self.supported_file_types,
                "namespaces": list(stats.namespaces.keys()) if stats.namespaces else [],
                "dimension": self.embedding_dimension
            }
                
        except Exception as e:
            logger.error(f"Error getting database info: {str(e)}")
            return {"error": str(e)}


def main():
    """Main function to run the Pinecone data retriever from command line."""
    parser = argparse.ArgumentParser(
        description="Generate JSON from HTML using Pinecone RAG"
    )
    parser.add_argument("--html-content", help="HTML content as string")
    parser.add_argument("--html-file", help="Path to HTML file")
    parser.add_argument("--file-type", help="File type hint (optional)")
    parser.add_argument(
        "--collection-name", 
        default="html_json_mappings",
        choices=list(COLLECTION_CONFIGS.keys()),
        help=f"Collection name. Available: {list(COLLECTION_CONFIGS.keys())}"
    )
    parser.add_argument("--n-examples", type=int, default=5, help="Number of similar examples")
    parser.add_argument("--output-file", help="Path to save output JSON")
    parser.add_argument("--info", action="store_true", help="Show database info and exit")
    parser.add_argument(
        "--list-collections",
        action="store_true",
        help="List available collections and exit"
    )
    
    args = parser.parse_args()
    
    # List collections if requested
    if args.list_collections:
        print("\n" + "="*60)
        print("Available Collections (Pinecone Backend):")
        print("="*60)
        for name, config in COLLECTION_CONFIGS.items():
            print(f"\nCollection: {name}")
            print(f"  Pinecone Index: {config['index_name']}")
            print(f"  Description: {config['description']}")
            print(f"  Supported types: {', '.join(config['supported_file_types'][:5])}")
            if len(config['supported_file_types']) > 5:
                print(f"    ... and {len(config['supported_file_types']) - 5} more")
        print("\n")
        return 0
    
    try:
        # Load environment variables
        dotenv.load_dotenv()
        
        openai_key = os.getenv("OPENAI_API_KEY")
        pinecone_key = os.getenv("PINECONE_API_KEY")
        
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        if not pinecone_key:
            raise ValueError("PINECONE_API_KEY not found in environment")

        # Initialize retriever
        retriever = DataRetriever(
            openai_api_key=openai_key,
            pinecone_api_key=pinecone_key,
            collection_name=args.collection_name,
        )
        
        # Show database info if requested
        if args.info:
            db_info = retriever.get_database_info()
            print("\n" + "="*60)
            print("Pinecone Database Information:")
            print("="*60)
            print(f"Collection: {args.collection_name}")
            print(f"Index name: {db_info.get('index_name', 'N/A')}")
            print(f"Total vectors: {db_info.get('total_vectors', 0)}")
            print(f"Dimension: {db_info.get('dimension', 0)}")
            print(f"Namespaces: {db_info.get('namespaces', [])}")
            print(f"File type distribution (sample): {db_info.get('file_type_distribution_sample', {})}")
            print(f"Supported file types: {db_info.get('supported_file_types', [])}")
            print("\n")
            return 0
        
        # Get HTML content
        html_content = ""
        
        if args.html_file:
            with open(args.html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
        elif args.html_content:
            html_content = args.html_content
        else:
            print("Error: Please provide either --html-file or --html-content")
            return 1
        
        if not html_content.strip():
            print("Error: HTML content is empty")
            return 1
        
        # Process HTML
        logger.info("Processing HTML content...")
        result = retriever.process_html(
            html_content=html_content,
            file_type=args.file_type,
            n_examples=args.n_examples,
            model_definition="Generate accurate JSON from HTML"
        )
        
        # Display results
        print(f"\n{'='*60}")
        print(f"Generation Results:")
        print(f"{'='*60}")
        print(f"Confidence Score: {result.confidence_score:.3f}")
        print(f"Number of Similar Examples: {len(result.similar_examples)}")
        
        if result.similar_examples:
            print(f"\nSimilar Examples Used:")
            for i, example in enumerate(result.similar_examples, 1):
                json_keys = list(example['json_schema'].keys()) if example['json_schema'] else []
                print(f"  {i}. Type: {example['metadata'].get('file_type', 'unknown')}")
                print(f"     Similarity: {example['similarity_score']:.3f}")
                print(f"     HTML Length: {len(example['html_content'])} chars")
                print(f"     JSON Keys: {json_keys[:5] if json_keys else 'EMPTY'}")
        
        # Save output
        output_file = args.output_file or "./vectordb_output/output.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        output_data = result.generated_json
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
        print("\n" + "="*60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
