# LLM Mapping System - Improvements Log

## Date: March 9, 2026

### Issue 1: Text Styling Not Preserved (text_builder)

**Problem:**
- English version had manual formatting: `\n` (newlines), `**bold**`, bullet points
- French content was being mapped but losing all formatting
- Example: English "**Key benefits:**\n• Benefit 1" → French "Avantages principaux: Avantage 1" (lost bold, newlines, bullets)

**Root Cause:**
- LLM was treating French content as plain text and not preserving English formatting structure

**Solution:**
Added component-specific rules for `text_builder`:

```
PRESERVE ALL ENGLISH FORMATTING AND STYLING:
- Keep newlines (\n), line breaks, paragraph breaks
- Keep bold markers (**text**), italic markers (*text*)
- Keep bullet point formatting (•, -, *, numbered lists)
- Keep any HTML tags (<br>, <p>, etc.)
- Keep spacing and indentation
- ONLY REPLACE THE ACTUAL TEXT CONTENT with French equivalents
```

**Example:**
```
English:  "**Key benefits:**\n• Benefit 1\n• Benefit 2"
French:   "Avantages principaux: Avantage 1, Avantage 2"
Output:   "**Avantages principaux:**\n• Avantage 1\n• Avantage 2"
```

### Issue 2: Ad_builder Split Strategy (ad_set_costco)

**Problem:**
- English: 2 ad_builders (image-only + text-only) - manually separated by author
- French: 1 ad_builder (image+text combined) - AI translation
- System couldn't localize 2nd English ad_builder because French only had 1
- Error: 422 Unprocessable Entity (missing required ad_builder)

**Root Cause:**
- LLM was trying to merge/distribute content instead of creating separate ad_builders
- French structure wasn't being split to match English structure

**Solution:**
Added component-specific rules for `ad_set_costco`:

```
If French has FEWER ad_builders than English (e.g., 1 French → 2 English):
- French combined image+text into single ad_builder
- English has them separated (image-only + text-only)
- SPLIT the French ad_builder to match English structure:
  * Create FIRST ad_builder: Copy English structure, map French image content
  * Create SECOND ad_builder: Copy English structure, map French text content
- Each ad_builder must have its own UID from English
- Maintain all English metadata, structure, configuration per ad_builder
```

**Expected Behavior:**
```
Input:
  English: [ad_builder_1: image-only, ad_builder_2: text-only]
  French:  [ad_builder_1: image+text combined]

Output (LLM generates):
  [
    {uid: blt123..., image: <from French>, text_content: []},
    {uid: blt456..., image: null, text_content: [<from French>]}
  ]
```

### Technical Changes Made

**File:** `mapping_data_retriever.py`

1. **Added component-specific rule system**
   - Lines 316-348: Dynamic rules based on component_type
   - `text_builder`: Formatting preservation rules
   - `ad_set_costco`: Split strategy rules

2. **Enhanced system prompt**
   - Clear scenario explanation (English manually updated, French outdated)
   - Component-specific rules injection
   - Emphasis on UID preservation and structure matching

3. **Key Instructions Added:**
   - "Output MUST match English structure exactly (same number of sections, same ordering, same UIDs)"
   - "PRESERVE ALL ENGLISH FORMATTING AND STYLING"
   - "SPLIT the French ad_builder to match English structure"

### Testing Checklist

- [ ] **text_builder**: Verify formatting preserved
  - Test with bold text: `**text**`
  - Test with newlines: `\n`
  - Test with bullet points: `• item`
  - Test with numbered lists: `1. item`

- [ ] **ad_set_costco**: Verify split strategy
  - Test 1 French → 2 English split
  - Verify both ad_builders have UIDs from English
  - Verify image goes to first, text to second
  - Verify both can be localized (no 422 errors)

### Expected Improvements

1. **Text Quality**: French content will maintain professional formatting matching English
2. **Localization Success**: All ad_builders will localize successfully (no 422 errors)
3. **Structural Accuracy**: Output structure exactly matches English (same UIDs, same count)

### Monitoring

Watch for these in logs:
```
✅ Good signs:
- "LLM mapping complete (confidence: X.XXX)"
- "✅ Localized successfully"
- No 422 errors

⚠️  Warning signs:
- Low confidence scores (< 0.7)
- 422 errors (means structure still mismatched)
- Missing ad_builders in output
```

### Next Steps

1. Test with actual pages that have:
   - text_builder with formatting (bold, bullets, newlines)
   - ad_set_costco with 1 French → 2 English mismatch

2. Monitor confidence scores and error rates

3. If issues persist:
   - Add more examples to vectorDB showing correct splits
   - Adjust temperature (currently 0.0 for deterministic output)
   - Review Claude's output for pattern analysis

---

**Status:** ✅ Implementation complete - Ready for testing
