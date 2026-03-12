# Quick Start Guide - Batch JSON Processor

## 🚀 Get Started in 3 Steps

### Step 1: Prepare Your CSV File

Create a CSV file (e.g., `my_batch.csv`) with your entries:

```csv
uid,component_type,locale,mapping
blt7c3tfzrczg59rp6t,ad_builder,en-ca,false
blt98f6t7ktgc8chrx,text_builder,en-ca,true
blt456def789ghi012,link_list_simple,fr-ca,false
```

**CSV Column Guide:**
- `uid`: The entry UID from Contentstack (e.g., from URL or entry details)
- `component_type`: Content type name (e.g., ad_builder, text_builder, link_list_simple)
- `locale`: Either `en-ca` (English) or `fr-ca` (French)
- `mapping`: `true` or `false` (affects output filename)

### Step 2: Run the Processor

```bash
python batch_json_processor.py my_batch.csv CABC
```

Replace `CABC` with your environment: `dev`, `USBC`, `USBD`, `CABC`, or `CABD`

### Step 3: Check Your Output

Look in the `output_batch/` folder:

```
output_batch/
├── ad_builder/
│   └── english_input_1.json
├── text_builder/
│   └── mapped_output_1.json
└── link_list_simple/
    └── french_input_1.json
```

## 📋 File Naming Rules

| Locale | Mapping | Output Filename |
|--------|---------|-----------------|
| en-ca  | false   | english_input_N.json |
| fr-ca  | true    | mapped_output_N.json |
| fr-ca  | false   | french_input_N.json |

Where `N` = 1, 2, 3, etc. (auto-incrementing)

## ✅ Example Use Cases

### Use Case 1: Process English Inputs
```csv
uid,component_type,locale,mapping
blt123,ad_builder,en-ca,false
blt456,text_builder,en-ca,false
```
**Output:** `english_input_1.json`, `english_input_2.json`

### Use Case 2: Process Mapped Outputs
```csv
uid,component_type,locale,mapping
blt789,ad_builder,fr-ca,true
blt012,link_list,fr-ca,true
```
**Output:** `mapped_output_1.json`, `mapped_output_2.json`

### Use Case 3: Process French Content
```csv
uid,component_type,locale,mapping
blt345,ad_builder,fr-ca,false
blt678,text_builder,fr-ca,false
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
**Output:**
```
output_batch/
├── ad_builder/
│   ├── english_input_1.json
│   ├── mapped_output_1.json
│   └── french_input_1.json
└── text_builder/
    └── english_input_1.json
```

## 🔧 Common Commands

### Show Help
```bash
python batch_json_processor.py --help
```

### Process Different Environments
```bash
# CABC Environment
python batch_json_processor.py entries.csv CABC

# USBC Environment
python batch_json_processor.py entries.csv USBC

# Dev Environment
python batch_json_processor.py entries.csv dev
```

## 💡 Tips

1. **Start Small**: Test with 2-3 entries first
2. **Use Sample File**: Modify `sample_batch_input.csv` as a template
3. **Check UIDs**: Verify UIDs are correct before running
4. **Environment Setup**: Ensure `.env` file has correct credentials
5. **Clean Output**: Delete `output_batch/` folder between runs to avoid confusion

## ⚠️ Important Notes

- Each run resets counters (starts from 1 again)
- Files with same name will be overwritten
- Invalid entries are skipped (processing continues)
- All output goes to `output_batch/` (not `output/` or other folders)

## 🎯 What Gets Processed?

For each CSV row, the tool:
1. ✅ Fetches entry from Contentstack API
2. ✅ Cleans JSON (removes metadata, UIDs, etc.)
3. ✅ Creates component-type subfolder
4. ✅ Saves with correct filename pattern

## 📊 Progress Tracking

You'll see output like this:

```
[1/3] Processing:
  - UID: blt123abc
  - Component Type: ad_builder
  - Locale: en-ca
  - Mapping: false
  📥 Fetching entry from Contentstack...
  🧹 Cleaning JSON data...
  💾 Writing to: output_batch\ad_builder\english_input_1.json
  ✅ Successfully processed!

[2/3] Processing:
  ...
```

## 🆘 Troubleshooting

**Problem**: "CSV file not found"  
**Solution**: Check file path, use full path if needed

**Problem**: "Missing environment variables"  
**Solution**: Check `.env` file has credentials for your environment

**Problem**: "Invalid locale"  
**Solution**: Use only `en-ca` or `fr-ca` in CSV

**Problem**: API errors  
**Solution**: Verify UID and component_type are correct

## 📞 Need More Help?

Read the full documentation: `BATCH_PROCESSOR_README.md`
