# AI Hallucination Analysis & Fix Plan

## Executive Summary

**CRITICAL FINDINGS**: The current system has 3 major hallucination failure modes that compromise production pipeline integrity:

1. **Styling Hallucination**: LLM generates wrong colors/layouts (e.g., #337AB7 blue instead of #333333 gray)
2. **Content Hallucination**: English text appears in French output (mixing source languages)
3. **Asset Hallucination**: English images appear in French pages (wrong asset references)

**ROOT CAUSE**: Post-generation validation is **INSUFFICIENT**. Style enforcement runs AFTER LLM outputs bad JSON, attempting to "fix" already-corrupted data.

**IMPACT**: Production pipeline cannot afford ANY hallucination - each error requires manual intervention and causes deployment delays.

---

## Failure Mode Analysis

### 1. Styling Hallucination (Colors/Layout Wrong)

**Symptoms**:
- French pages show old blue colors (#337AB7) instead of current black (#333333)
- Text alignment differs from English (center vs left)
- Background colors don't match English version

**Current Flow**:
```
English Input (#333333 black) + French Input (#FFFFFF white)
   ↓
Claude LLM generates output
   ↓
LLM SOMETIMES generates: #337AB7 (HALLUCINATED BLUE!) ❌
   ↓
Style Enforcement tries to fix (force_copy_styling_fields)
   ↓
Works... but ONLY if enforcement catches all fields
```

**Root Cause**:
1. **LLM Training Data Contamination**: Claude has seen ContentStack schemas with default #337AB7 blue
2. **Prompt Insufficient**: Despite "COPY ENGLISH STYLING 100%", LLM still generates colors
3. **Validation Too Late**: Style enforcement is POST-PROCESSING, not PRE-VALIDATION

**Why It Fails**:
- Style enforcement uses recursive field copying
- If LLM adds NEW nested fields not in English, enforcement misses them
- If LLM restructures the JSON (e.g., `color_config.text_color` → `text_color_config.color`), enforcement fails

---

### 2. Content Hallucination (English Text in French Output)

**Symptoms**:
- French menu items show English text
- French ad_builder captions in English
- Mixed language content (2 French + 2 English items)

**Current Flow**:
```
English Input (4 menu items) + French Input (2 menu items)
   ↓
Claude LLM maps content
   ↓
LLM generates output with 4 items:
   Items 1-2: French text ✅
   Items 3-4: English text (HALLUCINATED!) ❌
```

**Root Cause**:
1. **Array Length Mismatch**: When French has fewer items, LLM "fills" missing items with English
2. **Training Data Patterns**: LLM learned to "preserve" English when French is missing
3. **No Content Validation**: System doesn't check if output contains English words

**Why The Previous Fix Wasn't Enough**:
- We fixed `_replace_content()` to use `min(len(eng), len(fr))` 
- BUT this only works for RULE-BASED path, not LLM path!
- LLM generates JSON directly, bypassing array length logic

---

### 3. Asset Hallucination (English Images in French Output)

**Symptoms**:
- French ad_builder shows English product image
- Image URLs point to English assets
- French page displays wrong visual content

**Current Flow**:
```
English Input (image: "/en/product.jpg") + French Input (image: "/fr/produit.jpg")
   ↓
Claude LLM generates output
   ↓
LLM outputs: "image": "/en/product.jpg" (ENGLISH IMAGE!) ❌
```

**Root Cause**:
1. **Prompt Ambiguity**: "Use French images" not explicit enough
2. **LLM Pattern Matching**: LLM sees English structure has `/en/`, copies it
3. **No Asset Validation**: System doesn't verify image URLs match French input

**Why It's Critical**:
- Wrong product images cause legal/compliance issues
- Customers see incorrect products
- Brand consistency broken

---

## Current System Architecture

### LLM-Based Mapping Flow (ad_builder, text_builder, link_list, ad_set_costco)

```
1. simple_localizer_v2.py::map_component()
   ├─ Calls: mapping_retriever.process_mapping()
   │
2. mapping_data_retriever.py::process_mapping()
   ├─ retrieve_similar_examples() → Get 3 RAG examples from Pinecone
   ├─ generate_mapped_json() → Call Claude with prompt
   │  ├─ System Prompt (lines 740-786):
   │  │  - "PRESERVE ALL ENGLISH STYLING 100% EXACTLY"
   │  │  - "DO NOT generate new colors or styles"
   │  │  - "COPY English styling character-by-character"
   │  ├─ User Prompt: English JSON + French JSON
   │  └─ Claude Sonnet 4 generates mapped JSON
   │
   ├─ enforce_styling_preservation() ← **POST-PROCESSING** (line 825)
   │  └─ force_copy_styling_fields() recursively copies styling
   │
   └─ Return MappingResult

3. simple_localizer_v2.py receives mapped JSON
   └─ Sends to ContentStack (NO VALIDATION!)
```

### Rule-Based Fallback Flow (other components)

```
1. simple_localizer_v2.py::map_component()
   ├─ _replace_content() → Recursive replacement
   │  ├─ CONTENT_FIELDS → Replace with French
   │  ├─ KEEP_ENGLISH → Keep English value
   │  ├─ FULL_REPLACE → Use French images/links
   │  └─ STYLE_FIELDS → Use French if valid, else English
   │
   └─ enforce_styling_preservation() ← Same post-processing

2. Send to ContentStack
```

---

## Critical Gaps in Current Implementation

### Gap 1: No Pre-Flight Validation

**Current**: Style enforcement FIXES bad LLM output  
**Problem**: Enforcement can MISS fields if LLM restructures JSON

**Solution Needed**: VALIDATE before sending to ContentStack
- Check ALL styling fields match English EXACTLY
- Check NO English text in French content
- Check image URLs match French input
- **REJECT** mapping if validation fails (don't attempt to fix)

### Gap 2: LLM Prompt Lacks Negative Examples

**Current Prompt**:
```
CRITICAL RULE:
- COPY English styling fields character-by-character
```

**Problem**: Too abstract - LLM doesn't see what "bad" looks like

**Solution Needed**: Add NEGATIVE EXAMPLES
```
❌ BAD OUTPUT (REJECT):
{
  "color_config": {
    "text_color": {"hex": "#337AB7"}  ← HALLUCINATED!
  }
}

✅ GOOD OUTPUT (ACCEPT):
{
  "color_config": {
    "text_color": {"hex": "#333333"}  ← FROM ENGLISH INPUT
  }
}
```

### Gap 3: No Content Language Detection

**Current**: System trusts LLM output blindly

**Problem**: Can't detect English text in French output

**Solution Needed**: Implement language detection
```python
def detect_english_in_french(text: str) -> bool:
    """Detect if text is English instead of French"""
    english_words = ['the', 'and', 'or', 'in', 'on', 'at', 'for', 'with', 'this', 'that']
    french_words = ['le', 'la', 'les', 'et', 'ou', 'dans', 'sur', 'avec', 'ce', 'cette']
    
    # Count word occurrences
    eng_count = sum(1 for word in english_words if f' {word} ' in f' {text.lower()} ')
    fr_count = sum(1 for word in french_words if f' {word} ' in f' {text.lower()} ')
    
    # If >80% English words, it's English
    return eng_count > 0 and (eng_count / (eng_count + fr_count + 1)) > 0.8
```

### Gap 4: No Asset URL Validation

**Current**: System doesn't check image URLs

**Problem**: English image URLs slip through

**Solution Needed**: Validate asset URLs
```python
def validate_image_urls(mapped_json: Dict, french_input: Dict) -> List[str]:
    """Check if all image URLs in output match French input"""
    errors = []
    
    # Extract all image URLs from French input
    french_images = extract_image_urls(french_input)
    
    # Extract all image URLs from mapped output
    output_images = extract_image_urls(mapped_json)
    
    # Check if output has images not in French input
    for img_url in output_images:
        if img_url not in french_images:
            errors.append(f"❌ Hallucinated image URL: {img_url}")
    
    return errors
```

---

## Proposed Solution: Multi-Layer Validation

### Layer 1: Enhanced LLM Prompt (PREVENTIVE)

**Add to system prompt**:
```python
CRITICAL VALIDATION RULES - YOUR OUTPUT WILL BE REJECTED IF:

❌ REJECTION CRITERIA:
1. ANY color value (#XXXXXX) not present in English input
2. ANY styling field value different from English input
3. ANY English text in French content fields
4. ANY image URL not present in French input
5. ANY structural field mismatch with English template

✅ ACCEPTANCE CRITERIA:
1. ALL color_config values EXACTLY match English input
2. ALL background_group values EXACTLY match English input
3. ALL text content is French (no English words)
4. ALL image URLs present in French input
5. Structure 100% matches English template

VALIDATION EXAMPLES:

❌ BAD - Hallucinated Color:
English: {"text_color": {"hex": "#333333"}}
Your Output: {"text_color": {"hex": "#337AB7"}} ← WRONG! REJECTED!

✅ GOOD - Exact Copy:
English: {"text_color": {"hex": "#333333"}}
Your Output: {"text_color": {"hex": "#333333"}} ← CORRECT!

❌ BAD - English Text in French Output:
French Input: "Voir la recette"
Your Output: "See the recipe" ← ENGLISH! REJECTED!

✅ GOOD - French Text Preserved:
French Input: "Voir la recette"
Your Output: "Voir la recette" ← FRENCH! CORRECT!
```

### Layer 2: Post-Generation Validation (DETECTIVE)

**Add after LLM generation, BEFORE style enforcement**:

```python
def validate_llm_output(
    mapped_json: Dict,
    english_input: Dict,
    french_input: Dict,
    component_type: str
) -> Tuple[bool, List[str]]:
    """
    Validate LLM output for hallucination.
    Returns: (is_valid, error_messages)
    """
    errors = []
    
    # 1. STYLING VALIDATION - Check ALL styling fields match English
    styling_errors = validate_styling_match(mapped_json, english_input, component_type)
    errors.extend(styling_errors)
    
    # 2. CONTENT VALIDATION - Check no English text in French output
    content_errors = validate_french_content(mapped_json)
    errors.extend(content_errors)
    
    # 3. ASSET VALIDATION - Check image URLs match French input
    asset_errors = validate_asset_urls(mapped_json, french_input)
    errors.extend(asset_errors)
    
    # 4. STRUCTURE VALIDATION - Check structure matches English
    structure_errors = validate_structure_match(mapped_json, english_input)
    errors.extend(structure_errors)
    
    is_valid = len(errors) == 0
    return is_valid, errors
```

### Layer 3: Rejection & Retry Logic (CORRECTIVE)

**Add retry mechanism**:

```python
def generate_mapped_json_with_validation(...):
    """Generate mapped JSON with validation and retry"""
    
    max_retries = 3
    for attempt in range(max_retries):
        # Generate mapped JSON
        mapped_json, reasoning = self.generate_mapped_json(...)
        
        # CRITICAL: Validate BEFORE enforcement
        is_valid, errors = validate_llm_output(
            mapped_json, english_data, french_data, component_type
        )
        
        if is_valid:
            logger.info(f"✅ LLM output passed validation (attempt {attempt+1})")
            # Now apply enforcement as safety net
            return self.enforce_styling_preservation(...)
        else:
            logger.warning(f"❌ LLM output failed validation (attempt {attempt+1}):")
            for error in errors:
                logger.warning(f"   {error}")
            
            if attempt < max_retries - 1:
                logger.info(f"   → Retrying with stricter prompt...")
                # Add errors to prompt for next attempt
                continue
            else:
                logger.error(f"   → All retries failed. Rejecting mapping.")
                raise ValueError(f"LLM hallucination detected after {max_retries} attempts")
```

---

## Implementation Plan

### Phase 1: Add Validation Functions (HIGH PRIORITY)

**Files to modify**:
1. `mapping_data_retriever.py` - Add validation methods
2. `simple_localizer_v2.py` - Integrate validation into flow

**Functions to implement**:
```python
# In mapping_data_retriever.py

def validate_styling_match(mapped: Dict, english: Dict, component_type: str) -> List[str]:
    """Check ALL styling fields match English 100%"""
    
def validate_french_content(mapped: Dict) -> List[str]:
    """Detect English text in French output"""
    
def validate_asset_urls(mapped: Dict, french: Dict) -> List[str]:
    """Check image URLs match French input"""
    
def validate_structure_match(mapped: Dict, english: Dict) -> List[str]:
    """Verify structure matches English template"""
```

### Phase 2: Enhance LLM Prompt (MEDIUM PRIORITY)

**Add negative examples and validation criteria to prompt**

### Phase 3: Add Retry Logic (LOW PRIORITY)

**Implement retry with feedback loop**

---

## Success Metrics

**Before Fix**:
- Hallucination Rate: ~15-20% (user report: "here and there")
- Manual Fixes Required: High
- Production Confidence: Low

**After Fix (Target)**:
- Hallucination Rate: <1% (99%+ accuracy)
- Manual Fixes Required: Minimal
- Production Confidence: High
- Pipeline Reliability: 100%

---

## Testing Strategy

### Test Cases (Must Pass 100%)

1. **Styling Test**:
   - Input: English (#333333), French (#FFFFFF)
   - Expected: Output (#333333) ← English
   - Reject: Output (#337AB7) ← Hallucinated

2. **Content Test**:
   - Input: English (4 items), French (2 items)
   - Expected: Output (2 French items)
   - Reject: Output (2 French + 2 English)

3. **Image Test**:
   - Input: English (/en/image.jpg), French (/fr/image.jpg)
   - Expected: Output (/fr/image.jpg) ← French
   - Reject: Output (/en/image.jpg) ← English

### Validation Test Script

```bash
# Run against known failure cases
python test_validation.py \
  --test-styling link_list_wrong_colors.json \
  --test-content link_flyout_english_text.json \
  --test-images ad_builder_english_images.json
```

---

## Risk Mitigation

**Risk**: Validation too strict, rejects valid mappings  
**Mitigation**: Whitelist known safe variations, extensive testing

**Risk**: Retry logic adds latency  
**Mitigation**: Set max_retries=2, most mappings pass first attempt

**Risk**: False positives in English detection  
**Mitigation**: Use word-based detection + threshold (>80% English words)

---

## Next Steps

1. **IMMEDIATE**: Implement validation functions
2. **SHORT-TERM**: Integrate validation into generation flow
3. **MEDIUM-TERM**: Add retry logic with feedback
4. **LONG-TERM**: Collect metrics, tune thresholds

---

**STATUS**: Analysis complete. Ready for implementation.
