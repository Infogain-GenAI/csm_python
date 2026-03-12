# 📦 Batch JSON Processor - Complete Package Summary

## What's Been Created

A complete automation solution for batch processing Contentstack entries with organized output structure.

### 📄 New Files Created

1. **`batch_json_processor.py`** (Main Script)
   - Core automation script
   - Handles CSV parsing, API calls, JSON cleanup, and file organization
   - ~350 lines of production-ready code

2. **`sample_batch_input.csv`** (Sample Data)
   - Example CSV with correct format
   - Ready to modify with your UIDs

3. **`generate_csv_template.py`** (Helper Utility)
   - Quickly generate CSV templates
   - Multiple template types (basic, english, french, mapped, mixed, large)

4. **`BATCH_PROCESSOR_README.md`** (Full Documentation)
   - Complete documentation
   - All features, configuration, troubleshooting

5. **`QUICK_START_BATCH.md`** (Quick Start Guide)
   - 3-step quick start
   - Common use cases and examples

6. **`BATCH_ARCHITECTURE.md`** (Technical Documentation)
   - System architecture diagrams
   - Data flow visualization
   - Integration details

### ♻️ Modified Files

- **`.gitignore`** - Added `output_batch/` to ignore generated files

### 📁 New Directory (Auto-created)

- **`output_batch/`** - Created automatically when script runs
  - Organized by component type
  - Auto-numbered files

## 🎯 What Problem Does This Solve?

### Before (Manual Process)
```
For each entry:
1. Open Postman → 2-3 min
2. Configure POST request
3. Copy JSON response
4. Paste into test.json
5. Run json_cleanup_cli.py
6. Rename output file manually
7. Move to correct folder manually

Total: ~2-3 minutes per entry × N entries
```

### After (Automated Process)
```
One time:
1. Create CSV with all UIDs → 2-5 min
2. Run batch_json_processor.py → 5-10 seconds per entry
3. All files automatically organized

Total: ~5-10 seconds per entry × N entries
```

**Time Saved: 90-95% reduction in processing time!**

## 🚀 How to Use

### Method 1: Using Sample CSV
```bash
# Edit sample file with your UIDs
notepad sample_batch_input.csv

# Run processor
python batch_json_processor.py sample_batch_input.csv CABC
```

### Method 2: Generate New Template
```bash
# Generate template
python generate_csv_template.py mixed

# Edit template with your UIDs
notepad template_mixed.csv

# Run processor
python batch_json_processor.py template_mixed.csv CABC
```

### Method 3: Create Custom CSV
```bash
# Create your own CSV with format:
# uid,component_type,locale,mapping

# Run processor
python batch_json_processor.py my_entries.csv CABC
```

## 📋 CSV Format

```csv
uid,component_type,locale,mapping
blt123abc456def789,ad_builder,en-ca,false
blt987zyx654wvu321,text_builder,en-ca,true
blt456def789ghi012,link_list_simple,fr-ca,false
```

### Column Definitions

| Column | Required | Valid Values | Description |
|--------|----------|--------------|-------------|
| uid | Yes | blt... | Entry UID from Contentstack |
| component_type | Yes | Any content type | Component/model name |
| locale | Yes | en-ca, fr-ca | Language code |
| mapping | Yes | true, false | Affects output filename |

## 📂 Output File Naming

| Locale | Mapping | Output Filename |
|--------|---------|-----------------|
| en-ca  | false   | `english_input_N.json` |
| fr-ca  | true    | `mapped_output_N.json` |
| fr-ca  | false   | `french_input_N.json` |

Where `N` is auto-incrementing: 1, 2, 3, ...

## 🗂️ Output Structure

```
output_batch/
├── ad_builder/
│   ├── english_input_1.json
│   ├── english_input_2.json
│   ├── mapped_output_1.json
│   └── french_input_1.json
├── text_builder/
│   ├── english_input_1.json
│   └── mapped_output_1.json
└── link_list_simple/
    └── french_input_1.json
```

## ✅ Key Features

- ✅ **Batch Processing** - Process multiple entries in one run
- ✅ **Automatic API Calls** - No manual Postman requests
- ✅ **JSON Cleanup** - Uses existing json_cleanup.py logic
- ✅ **Organized Output** - Folders per component type
- ✅ **Smart Naming** - Automatic filename based on locale/mapping
- ✅ **Error Handling** - Continues processing even if some entries fail
- ✅ **Progress Tracking** - Shows status for each entry
- ✅ **Summary Report** - Success/failure counts at the end
- ✅ **Non-destructive** - Does not modify existing code

## 🔧 Environment Support

Works with all environments:
- ✅ dev
- ✅ USBC (US Business Center)
- ✅ USBD (US Business Development)
- ✅ CABC (Canada Business Center)
- ✅ CABD (Canada Business Development)

## 📖 Documentation

| Document | Purpose | When to Read |
|----------|---------|--------------|
| `QUICK_START_BATCH.md` | Get started quickly | **Start here** |
| `BATCH_PROCESSOR_README.md` | Full documentation | Need details |
| `BATCH_ARCHITECTURE.md` | Technical deep dive | Want to understand internals |
| This file | Overview & summary | Quick reference |

## 🎓 Learning Path

1. **Beginner** → Read `QUICK_START_BATCH.md`
2. **Try It** → Run with `sample_batch_input.csv`
3. **Customize** → Generate templates with `generate_csv_template.py`
4. **Production** → Create your own CSVs
5. **Advanced** → Read `BATCH_ARCHITECTURE.md`

## 🛠️ Dependencies

Uses existing project dependencies:
- ✅ Python 3.7+
- ✅ requests
- ✅ python-dotenv
- ✅ Existing lib/contentstack_api.py
- ✅ Existing lib/json_cleanup.py

**No new dependencies required!**

## 🔒 What's NOT Changed

- ✅ `json_cleanup_cli.py` - Still works as before
- ✅ `lib/contentstack_api.py` - No modifications
- ✅ `lib/json_cleanup.py` - No modifications
- ✅ All other existing scripts - Unchanged
- ✅ `.env` file - Same credentials used

**100% backward compatible!**

## 🎯 Use Cases

### Use Case 1: Bulk English Content
```csv
uid,component_type,locale,mapping
blt001,ad_builder,en-ca,false
blt002,ad_builder,en-ca,false
blt003,ad_builder,en-ca,false
```
**Output:** `english_input_1.json`, `english_input_2.json`, `english_input_3.json`

### Use Case 2: Mapped Outputs
```csv
uid,component_type,locale,mapping
blt001,text_builder,fr-ca,true
blt002,text_builder,fr-ca,true
```
**Output:** `mapped_output_1.json`, `mapped_output_2.json`

### Use Case 3: French Content
```csv
uid,component_type,locale,mapping
blt001,ad_builder,fr-ca,false
blt002,text_builder,fr-ca,false
```
**Output:** `french_input_1.json`, `french_input_2.json`

### Use Case 4: Mixed Batch
```csv
uid,component_type,locale,mapping
blt001,ad_builder,en-ca,false
blt002,ad_builder,fr-ca,true
blt003,ad_builder,fr-ca,false
blt004,text_builder,en-ca,false
```
**Output:** Organized in respective component folders with correct names

## 🚨 Important Notes

1. **Counter Reset**: Each run starts counter from 1
2. **File Overwrite**: Files with same name will be overwritten
3. **Clean Start**: Delete `output_batch/` between runs if needed
4. **Valid Locales**: Only `en-ca` and `fr-ca` supported
5. **Environment Variables**: Must be set in `.env` file

## 📊 Example Run

```bash
$ python batch_json_processor.py sample_batch_input.csv CABC

=== BATCH JSON PROCESSOR ===
Environment: CABC
CSV File: sample_batch_input.csv

✅ Batch processor initialized for environment: CABC

📄 Reading CSV file: sample_batch_input.csv
📊 Found 3 entries to process

[1/3] Processing:
  - UID: blt123abc456def789
  - Component Type: ad_builder
  - Locale: en-ca
  - Mapping: false
  📥 Fetching entry from Contentstack...
  🧹 Cleaning JSON data...
  💾 Writing to: output_batch\ad_builder\english_input_1.json
  ✅ Successfully processed!

[2/3] Processing:
  ...

============================================================
BATCH PROCESSING SUMMARY
============================================================
Total Entries: 3
Successful: 3
Failed: 0
Output Directory: C:\...\output_batch
============================================================

🎉 Batch processing completed successfully!
```

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| CSV not found | Check file path |
| Missing env vars | Check `.env` file |
| Invalid locale | Use `en-ca` or `fr-ca` only |
| API errors | Verify UID and component_type |
| No output | Check `output_batch/` folder |

## 🎁 Bonus: Template Generator

Quick template generation:

```bash
# Generate basic template
python generate_csv_template.py basic

# Generate all templates
python generate_csv_template.py all

# Available: basic, english, french, mapped, mixed, large, empty
```

## 🔗 Related Scripts

This script complements existing tools:
- `json_cleanup_cli.py` - Single file cleanup
- `index.py` - Main index script
- `bulk_asset_upload.py` - Asset uploads

## 💡 Tips for Success

1. **Start Small** - Test with 2-3 entries first
2. **Verify UIDs** - Double-check UIDs before running
3. **Check Environment** - Ensure correct environment selected
4. **Clean Output** - Delete `output_batch/` between batches
5. **Use Templates** - Generate templates for consistency

## 🎯 Success Metrics

After using this tool, you should see:
- ✅ 90-95% time reduction per entry
- ✅ Zero manual file organization
- ✅ Consistent file naming
- ✅ Organized output structure
- ✅ Batch processing capability

## 📞 Support

If you need help:
1. Check `QUICK_START_BATCH.md` for basics
2. Read `BATCH_PROCESSOR_README.md` for details
3. Review error messages carefully
4. Verify CSV format matches examples

## 🎉 You're Ready!

Everything you need is set up:
- ✅ Scripts created
- ✅ Documentation written
- ✅ Sample files provided
- ✅ Templates available
- ✅ Helper utilities included

**Next Step:** Run your first batch!

```bash
python batch_json_processor.py sample_batch_input.csv CABC
```

Good luck! 🚀
