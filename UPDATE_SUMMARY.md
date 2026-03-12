# 🔄 Update Summary - File Naming Rules Changed

## Changes Made

The file naming conditions have been updated as follows:

### Previous Rules ❌
- `en-ca` + `mapping=false` → `english_input_N.json`
- `en-ca` + `mapping=true` → `mapped_output_N.json` ❌
- `fr-ca` + `mapping=false` → `french_input_N.json`

### New Rules ✅
- `en-ca` + `mapping=false` → `english_input_N.json`
- `fr-ca` + `mapping=true` → `mapped_output_N.json` ✅
- `fr-ca` + `mapping=false` → `french_input_N.json`

**Key Change:** `mapped_output_N.json` is now generated for **French content with mapping=true** instead of English content with mapping=true.

## Files Updated

### 1. Core Script
- ✅ **`batch_json_processor.py`**
  - Updated `_get_output_filename()` method logic
  - Updated help text examples
  - Updated output file naming documentation

### 2. Documentation Files
- ✅ **`BATCH_PROCESSOR_README.md`**
  - Updated file naming convention table
  - Updated example CSV
  
- ✅ **`QUICK_START_BATCH.md`**
  - Updated file naming rules table
  - Updated Use Case 2 example
  - Updated Use Case 4 example
  
- ✅ **`BATCH_ARCHITECTURE.md`**
  - Updated naming rules matrix
  - Updated counter management example
  - Updated output structure diagram
  
- ✅ **`BATCH_PACKAGE_SUMMARY.md`**
  - Updated output file naming table
  - Updated Use Case 2 example
  - Updated Use Case 4 example

### 3. Template Generator
- ✅ **`generate_csv_template.py`**
  - Updated basic template
  - Updated mapped_only template
  - Updated mixed template

### 4. Sample File
- ✅ **`sample_batch_input.csv`** (already had correct format)

## Impact

### What Changed
- `mapped_output_N.json` files are now created from **French entries with mapping=true**
- CSV files should now use `fr-ca` locale when `mapping=true` for mapped outputs

### What Stayed the Same
- `english_input_N.json` → still `en-ca` + `mapping=false`
- `french_input_N.json` → still `fr-ca` + `mapping=false`
- All folder organization logic
- All counter management
- API fetching and JSON cleanup logic

## Updated Examples

### Example 1: Basic CSV
```csv
uid,component_type,locale,mapping
blt001,ad_builder,en-ca,false      # → english_input_1.json
blt002,text_builder,fr-ca,true     # → mapped_output_1.json
blt003,link_list,fr-ca,false       # → french_input_1.json
```

### Example 2: Mixed Batch
```csv
uid,component_type,locale,mapping
blt001,ad_builder,en-ca,false      # → english_input_1.json
blt002,ad_builder,fr-ca,true       # → mapped_output_1.json
blt003,ad_builder,fr-ca,false      # → french_input_1.json
blt004,text_builder,en-ca,false    # → english_input_1.json
```

**Output Structure:**
```
output_batch/
├── ad_builder/
│   ├── english_input_1.json
│   ├── mapped_output_1.json
│   └── french_input_1.json
└── text_builder/
    └── english_input_1.json
```

## Testing Recommendation

To verify the changes work correctly:

1. **Generate a test CSV:**
   ```bash
   python generate_csv_template.py basic
   ```

2. **Edit with real UIDs:**
   ```csv
   uid,component_type,locale,mapping
   blt_real_uid_1,ad_builder,en-ca,false
   blt_real_uid_2,text_builder,fr-ca,true
   blt_real_uid_3,link_list,fr-ca,false
   ```

3. **Run the processor:**
   ```bash
   python batch_json_processor.py template_basic.csv CABC
   ```

4. **Verify output:**
   - Check `output_batch/` folder
   - Confirm file names match new rules
   - Verify French content in `mapped_output_N.json`

## Backward Compatibility

⚠️ **Breaking Change Notice:**

If you have existing CSV files with `en-ca,true` expecting `mapped_output_N.json`, you need to:
1. Change those rows to `fr-ca,true`
2. Or update your expectations for output filenames

This is a **breaking change** for the naming convention but does not affect the core processing logic.

## Quick Reference Card

```
┌─────────────────────────────────────────────────────┐
│         FILE NAMING QUICK REFERENCE                  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  en-ca + false  →  english_input_N.json             │
│  fr-ca + true   →  mapped_output_N.json             │
│  fr-ca + false  →  french_input_N.json              │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Date of Change
March 11, 2026

---

**All files have been updated and are consistent with the new naming rules!** ✅
