# English-French Component Mapping System

RAG-based system for intelligent structure mapping between mismatched English and French ContentStack components.

## Overview

This system uses Pinecone VectorDB + Claude LLM to learn from examples and intelligently map French content to English component structures when AI-generated French components have different section counts or structures.

## Dataset Structure

```
component_data/
├── text_builder/
│   ├── english_input_1.json    # English structure (target)
│   ├── french_input_1.json     # French AI output (mismatched)
│   ├── mapped_output_1.json    # Correct mapped structure
│   ├── english_input_2.json
│   ├── french_input_2.json
│   ├── mapped_output_2.json
│   └── ... (more examples)
└── ad_set_costco/
    ├── english_input_1.json
    ├── french_input_1.json
    ├── mapped_output_1.json
    └── ... (more examples)
```

## Components

### 1. `mapping_data_uploader.py`

Uploads English-French-Mapped triplets to Pinecone for RAG retrieval.

**Features:**
- Creates embeddings based on structure mismatch patterns
- Stores complete triplets (English, French, Mapped) as metadata
- Supports `text_builder` and `ad_set_costco` components
- Uses Pinecone index: `en-fr-component-mapping`

**Usage:**

```bash
# Upload entire dataset
python mapping_data_uploader.py --data-dir component_data

# Show index statistics
python mapping_data_uploader.py --stats

# Custom cloud/region
python mapping_data_uploader.py --data-dir component_data --cloud aws --region us-east-1
```

**Environment Variables Required:**
```bash
OPENAI_API_KEY=sk-...           # For embeddings
PINECONE_API_KEY=pcsk_...       # For vector storage
```

### 2. `mapping_data_retriever.py`

Retrieves similar examples and generates mapped JSON using Claude + RAG.

**Features:**
- Finds similar mismatch patterns from Pinecone
- Uses Claude 3.5 Sonnet to generate mapped structure
- Provides confidence scores and reasoning
- Returns complete mapped JSON

**Usage:**

```bash
# Generate mapped JSON
python mapping_data_retriever.py \
    --english-file path/to/english_input.json \
    --french-file path/to/french_input.json \
    --component-type text_builder \
    --output-file output_mapped.json \
    --n-examples 3

# Show index statistics
python mapping_data_retriever.py --stats
```

**Environment Variables Required:**
```bash
OPENAI_API_KEY=sk-...           # For embeddings
PINECONE_API_KEY=pcsk_...       # For vector retrieval
ANTHROPIC_API_KEY=sk-ant-...    # For Claude LLM
```

## How It Works

### 1. Uploading Examples

The uploader:
1. Reads triplets from `component_data/` directory
2. Analyzes structure mismatches (section counts, text types)
3. Creates embeddings capturing mismatch patterns
4. Stores in Pinecone with complete JSON metadata

**Embedding Text Example (text_builder):**
```
Component: text_builder
English sections: 2
English content counts per section: [1, 1]
English text types: title_v2, body_copy_v2

French sections: 3
French content counts per section: [1, 1, 1]
French text types: title_with_xl_v2, body_copy_v2, subheading_v2

Mismatch pattern: 2 English sections vs 3 French sections
```

### 2. Retrieving & Mapping

The retriever:
1. Analyzes current English-French mismatch
2. Finds top-N similar examples from Pinecone
3. Provides examples to Claude as RAG context
4. Claude generates correct mapped structure

**Example Flow:**
```python
# Current problem: 2 English sections, 3 French sections
# Retriever finds: Similar example with 2→3 mapping
# Claude learns: How to merge French section 2+3 into English section 2
# Output: Correct mapped JSON matching English structure
```

## Integration with `simple_localizer_v2.py`

### Mismatch Detection

In `map_structure()` method, detect mismatches:

```python
# For text_builder
eng_sections = english_data.get("entry", {}).get("multiple_text_section_group", [])
fr_sections = french_data.get("entry", {}).get("multiple_text_section_group", [])

if len(eng_sections) != len(fr_sections):
    # Use RAG-based mapping instead of rule-based
    use_llm_mapping = True

# For ad_set_costco
eng_ad_builders = extract_ad_builders(english_data)
fr_ad_builders = extract_ad_builders(french_data)

# Count text_content in each
eng_text_counts = [count_text_content(ab) for ab in eng_ad_builders]
fr_text_counts = [count_text_content(ab) for ab in fr_ad_builders]

if eng_text_counts != fr_text_counts:
    # Use RAG-based mapping
    use_llm_mapping = True
```

### LLM Call Integration

```python
from mapping_data_retriever import MappingDataRetriever

# Initialize retriever (once per session)
retriever = MappingDataRetriever(
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    pinecone_api_key=os.getenv("PINECONE_API_KEY"),
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
)

# When mismatch detected
if use_llm_mapping:
    result = retriever.process_mapping(
        english_data=english_structure,
        french_data=french_data,
        component_type="text_builder",  # or "ad_set_costco"
        n_examples=3
    )
    
    mapped_data = result.mapped_json
    confidence = result.confidence_score
    
    logger.info(f"✓ LLM-based mapping completed (confidence: {confidence:.3f})")
    logger.info(f"  Reasoning: {result.reasoning}")
    
    return mapped_data
else:
    # Use existing rule-based mapping
    return existing_map_logic(...)
```

## Example: Complete Workflow

### Step 1: Prepare Dataset

```bash
# Add new examples to component_data/
component_data/text_builder/
├── english_input_18.json   # New problem case
├── french_input_18.json    # AI output with mismatch
└── mapped_output_18.json   # Manually corrected structure
```

### Step 2: Upload to Pinecone

```bash
python mapping_data_uploader.py --data-dir component_data

# Output:
# ✓ Uploaded: text_builder_18
# Successfully uploaded: 26/26
# Total vectors: 26
```

### Step 3: Test Retrieval

```bash
python mapping_data_retriever.py \
    --english-file component_data/text_builder/english_input_1.json \
    --french-file component_data/text_builder/french_input_1.json \
    --component-type text_builder \
    --output-file test_mapped.json \
    --n-examples 3

# Output:
# ✓ Retrieved 3 similar examples
#   - text_builder_5: similarity = 0.8723
#   - text_builder_12: similarity = 0.8456
#   - text_builder_18: similarity = 0.8234
# ✓ Successfully generated mapped JSON
# Confidence Score: 0.845
```

### Step 4: Integrate into Pipeline

Update `simple_localizer_v2.py`:

```python
# In map_structure() method for text_builder
if self.use_llm_for_mismatches and len(eng_sections) != len(fr_sections):
    logger.info(f"   🤖 Section count mismatch detected, using LLM-based mapping")
    
    result = self.mapping_retriever.process_mapping(
        english_data=english_structure,
        french_data=french_data,
        component_type="text_builder",
        n_examples=3
    )
    
    logger.info(f"   ✓ LLM mapping complete (confidence: {result.confidence_score:.3f})")
    return result.mapped_json
```

## Dataset Growth

As you encounter new mismatch patterns:

1. **Manual Fix**: Create correct mapping manually
2. **Save Triplet**: Save as `english_input_N.json`, `french_input_N.json`, `mapped_output_N.json`
3. **Upload**: Run uploader to add to Pinecone
4. **Auto-Learn**: Future similar cases will use this example

The system learns and improves with each new example added!

## Confidence Scoring

Confidence score (0.0 to 1.0) based on:
- **Similarity**: How similar retrieved examples are (cosine similarity)
- **Example Count**: More examples = higher confidence
- **Pattern Match**: Exact mismatch pattern match gets bonus

**Score Interpretation:**
- `> 0.8`: High confidence, likely accurate
- `0.6 - 0.8`: Medium confidence, review output
- `< 0.6`: Low confidence, manual review recommended

## Troubleshooting

### No Similar Examples Found

```bash
# Check index stats
python mapping_data_retriever.py --stats

# If total_vectors = 0, upload dataset
python mapping_data_uploader.py --data-dir component_data
```

### Low Confidence Scores

- Add more examples with similar mismatch patterns
- Increase `--n-examples` parameter (default: 3)
- Verify dataset quality (mapped outputs should be correct)

### API Errors

```bash
# Check environment variables
echo $OPENAI_API_KEY
echo $PINECONE_API_KEY
echo $ANTHROPIC_API_KEY

# Test with --stats flag first
python mapping_data_retriever.py --stats
```

## Performance Optimization

### Batch Processing

For multiple pages, reuse retriever instance:

```python
# Initialize once
retriever = MappingDataRetriever(...)

# Process multiple pages
for page in pages:
    result = retriever.process_mapping(...)
    # Process result...
```

### Caching

Cache retrieved examples for identical mismatch patterns:

```python
cache = {}
pattern_key = f"{len(eng_sections)}_{len(fr_sections)}"

if pattern_key in cache:
    examples = cache[pattern_key]
else:
    examples = retriever.retrieve_similar_examples(...)
    cache[pattern_key] = examples
```

## Future Enhancements

- [ ] Add support for more component types
- [ ] Implement confidence-based fallback strategies
- [ ] Add validation checks for generated mappings
- [ ] Create web UI for dataset management
- [ ] Add A/B testing for mapping quality metrics

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify dataset structure matches expected format
3. Test with `--stats` flag to confirm connectivity
4. Review similar examples to understand retrieval patterns
