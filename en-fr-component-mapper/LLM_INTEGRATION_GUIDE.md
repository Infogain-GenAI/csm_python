# LLM-Based Mapping Integration Guide

## Overview

The `simple_localizer_v2.py` now includes intelligent LLM-based mapping for `text_builder` and `ad_set_costco` components when structure mismatches are detected.

## How It Works

### Automatic Detection

The system automatically detects mismatches:

**For text_builder:**
- Compares `text_section_content` counts in each section
- If counts differ between English and French → Uses LLM mapping

**For ad_set_costco:**
- Counts total number of `ad_builder` components
- If counts differ between English and French → Uses LLM mapping

### Workflow

```
1. User runs localization command
2. System fetches English and French structures
3. DETECTION: Check if counts match
   ├─ MATCH → Use rule-based mapping (fast, existing logic)
   └─ MISMATCH → Use LLM-based mapping (RAG + Claude)
4. LLM retrieves similar examples from Pinecone
5. Claude generates correct mapped structure
6. System continues with normal workflow (approve, publish)
```

## Prerequisites

### 1. Upload Dataset to Pinecone

First, upload your examples:

```bash
cd en-fr-component-mapper
python mapping_data_uploader.py --data-dir component_data
```

**Expected output:**
```
✓ Uploaded: text_builder_1
✓ Uploaded: text_builder_2
...
✓ Uploaded: ad_set_costco_1
...
Successfully uploaded: 25/25
Total vectors: 25
```

### 2. Verify Environment Variables

Ensure your `.env` file has:

```bash
# Existing keys
CONTENTSTACK_API_KEY_CABC=...
CONTENTSTACK_MANAGEMENT_TOKEN_CABC=...
CONTENTSTACK_BASE_URL_CABC=...
CONTENTSTACK_ENVIRONMENT_UID_CABC=...
CONTENTSTACK_AUTH_TOKEN=...

# New keys for LLM mapping
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pcsk_...
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Standard Usage (LLM Enabled by Default)

```bash
python simple_localizer_v2.py \
    blt5f41ab9edbbeaea3 \
    input/french_fetched_blt369fccbaddccb4f6_20260307-013008.json \
    --environment CABC \
    --approve \
    --publish
```

**Output when mismatch detected:**
```
🔄 Mapping text_builder/blt1085d2ff95c38ff2
   🤖 MISMATCH DETECTED: text_section_content counts differ
      English: [1, 1, 1, 1]
      French: [1, 1, 1]
      → Using LLM-based mapping with RAG...
      ✅ LLM mapping complete (confidence: 0.845)
      Reasoning: Merged French sections 2+3 into English section 2 to match structure
```

### Disable LLM Mapping

Use rule-based mapping only:

```bash
python simple_localizer_v2.py \
    blt5f41ab9edbbeaea3 \
    input/french_fetched.json \
    --environment CABC \
    --disable-llm
```

## Testing

### Test LLM Mapping Standalone

```bash
# Test with your dataset examples
python test_llm_mapping.py
```

This will:
1. Load `text_builder` example 2 (4 English sections, 3 French sections)
2. Load `ad_set_costco` example 1 (2 English ad_builders, 2 French ad_builders)
3. Run LLM mapping
4. Save outputs to `test_output_*.json`

### Test Individual Retrieval

```bash
# Test retrieval for text_builder
python mapping_data_retriever.py \
    --english-file component_data/text_builder/english_input_2.json \
    --french-file component_data/text_builder/french_input_2.json \
    --component-type text_builder \
    --output-file test_mapped.json \
    --n-examples 3
```

## Example Scenarios

### Scenario 1: text_builder - 4 English Sections, 3 French Sections

**English Structure:**
- Section 1: Title ("Home health")
- Section 2: Subheading ("Mike Holmes...")
- Section 3: Author ("by SHARON CHISVIN")
- Section 4: Body (long article)

**French Structure:**
- Section 1: Title ("Maison soignée")
- Section 2: Subheading ("Sérénité assurée...")
- Section 3: Body (author + article merged)

**LLM Decision:**
- Keep sections 1-2 mapped 1:1
- Map French section 3 → English section 4
- Leave English section 3 empty or use placeholder

### Scenario 2: ad_set_costco - 2 English, 2 French

**English Structure:**
- ad_builder[0]: Image-only card
- ad_builder[1]: Image + text card

**French Structure:**
- ad_builder[0]: Combined image + text
- ad_builder[1]: Combined image + text

**LLM Decision:**
- Split French content across both English ad_builders
- Maintain English structure (image-only vs text-overlay)

## Confidence Scores

The system provides confidence scores for each LLM mapping:

| Score | Interpretation | Action |
|-------|---------------|---------|
| > 0.8 | High confidence | Auto-proceed |
| 0.6-0.8 | Medium confidence | Review recommended |
| < 0.6 | Low confidence | Manual review required |

**Low confidence usually means:**
- No similar examples in dataset
- Complex structural differences
- Need to add more training examples

## Adding New Examples

When you encounter a new mismatch pattern:

### 1. Manual Fix First

Manually create the correct mapping and save it.

### 2. Save as Dataset Example

```
component_data/text_builder/
├── english_input_18.json    # New English structure
├── french_input_18.json     # AI-generated French (mismatched)
└── mapped_output_18.json    # Your correct manual mapping
```

### 3. Upload to Pinecone

```bash
python mapping_data_uploader.py --data-dir component_data
```

### 4. Future Cases Auto-Learn

Similar mismatch patterns will now use this example!

## Troubleshooting

### LLM Mapping Not Triggering

**Check logs:**
```
✅ LLM-based mapping enabled (Claude Sonnet 4)
```

If you see:
```
⚠️  LLM mapping disabled: Missing API keys
```

Verify `.env` has all three keys: OPENAI, PINECONE, ANTHROPIC

### Low Quality Mappings

**Solutions:**
1. Add more similar examples to dataset
2. Increase `--n-examples` in retriever (default: 3)
3. Check if examples in Pinecone are correct

**Verify dataset:**
```bash
python mapping_data_uploader.py --stats
```

### Fallback to Rule-Based

If LLM fails, system automatically falls back to rule-based mapping:

```
⚠️  LLM mapping failed: Connection timeout
→ Falling back to rule-based mapping...
```

## Performance

### Speed Comparison

| Method | Time | Use Case |
|--------|------|----------|
| Rule-based | ~1-2s | Structures match perfectly |
| LLM-based | ~5-10s | Structures mismatch |

### Best Practices

1. **Let Auto-Detection Work**: Don't force LLM for matched structures
2. **Cache Results**: System reuses retriever instance across components
3. **Batch Processing**: Process multiple pages in one run

## Integration Summary

```python
# In simple_localizer_v2.py

def map_structure(self, english_uid, content_type, french_data):
    # Fetch English structure
    english_data = self.api.get_entry(content_type, english_uid)
    
    # AUTO-DETECTION
    if content_type == 'text_builder':
        eng_counts = [count text_section_content]
        fr_counts = [count text_section_content]
        
        if eng_counts != fr_counts:
            # USE LLM MAPPING
            result = self.mapping_retriever.process_mapping(
                english_data, 
                french_data, 
                'text_builder'
            )
            return result.mapped_json
    
    # FALLBACK: Rule-based mapping
    return existing_mapping_logic(...)
```

## Next Steps

1. ✅ Upload dataset: `python mapping_data_uploader.py --data-dir component_data`
2. ✅ Test standalone: `python test_llm_mapping.py`
3. ✅ Run full localization with LLM enabled
4. ✅ Monitor confidence scores
5. ✅ Add new examples as you encounter them

The system learns and improves with every example you add! 🚀
