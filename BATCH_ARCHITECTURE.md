# Batch JSON Processor - Architecture & Flow

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    BATCH JSON PROCESSOR                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Read CSV File   │
                    │  (uid, type,      │
                    │   locale, map)    │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  For Each Entry  │
                    │   in CSV File    │
                    └──────────────────┘
                              │
                              ▼
            ┌─────────────────────────────────┐
            │   Fetch from Contentstack API   │
            │  GET /entries/{uid}?locale=...  │
            └─────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Clean JSON     │
                    │  (Remove UIDs,   │
                    │   metadata, etc) │
                    └──────────────────┘
                              │
                              ▼
            ┌─────────────────────────────────┐
            │  Determine Output Path & Name   │
            │  - Create component folder      │
            │  - Apply naming rules          │
            └─────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Save JSON to   │
                    │  output_batch/   │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Show Summary    │
                    │ (Success/Failed) │
                    └──────────────────┘
```

## 🔄 Data Flow

```
INPUT (CSV)                    PROCESSING                    OUTPUT
───────────                    ──────────                    ──────

uid: blt123abc          →     API Fetch              →      output_batch/
type: ad_builder        →     JSON Cleanup           →        ad_builder/
locale: en-ca           →     Apply Rules            →          english_input_1.json
mapping: false          →     Counter Management     →

uid: blt456def          →     API Fetch              →      output_batch/
type: ad_builder        →     JSON Cleanup           →        ad_builder/
locale: en-ca           →     Apply Rules            →          mapped_output_1.json
mapping: true           →     Counter Management     →

uid: blt789ghi          →     API Fetch              →      output_batch/
type: text_builder      →     JSON Cleanup           →        text_builder/
locale: fr-ca           →     Apply Rules            →          french_input_1.json
mapping: false          →     Counter Management     →
```

## 🗂️ File Naming Decision Tree

```
                        ┌─────────────────┐
                        │   Input Entry   │
                        └────────┬────────┘
                                 │
                    ┌────────────┴────────────┐
                    │     Check Locale        │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                ┌───▼────┐              ┌────▼────┐
                │ en-ca  │              │  fr-ca  │
                └───┬────┘              └────┬────┘
                    │                        │
        ┌───────────┴───────────┐            │
        │                       │            │
    ┌───▼────┐            ┌────▼───┐        │
    │mapping │            │mapping │        │
    │= false │            │= true  │        │
    └───┬────┘            └────┬───┘        │
        │                      │            │
        ▼                      ▼            ▼
┌──────────────┐      ┌──────────────┐   ┌──────────────┐
│english_input │      │mapped_output │   │french_input  │
│    _N.json   │      │   _N.json    │   │   _N.json    │
└──────────────┘      └──────────────┘   └──────────────┘
```

## 📦 Output Structure Example

```
csm-content-creation-python/
│
├── batch_json_processor.py          ← Main script
├── sample_batch_input.csv           ← Sample CSV template
├── BATCH_PROCESSOR_README.md        ← Full documentation
├── QUICK_START_BATCH.md             ← Quick start guide
│
├── lib/                              ← Existing libraries (reused)
│   ├── contentstack_api.py          ← API client
│   └── json_cleanup.py              ← JSON cleaner
│
└── output_batch/                     ← Created by script
    │
    ├── ad_builder/                   ← Component type folder
    │   ├── english_input_1.json     ← en-ca, mapping=false
    │   ├── english_input_2.json     ← en-ca, mapping=false
    │   ├── mapped_output_1.json     ← fr-ca, mapping=true
    │   └── french_input_1.json      ← fr-ca, mapping=false
    │
    ├── text_builder/                 ← Component type folder
    │   ├── english_input_1.json
    │   ├── mapped_output_1.json
    │   ├── mapped_output_2.json
    │   └── french_input_1.json
    │
    └── link_list_simple/             ← Component type folder
        ├── english_input_1.json
        └── french_input_1.json
```

## 🎯 Key Features

### 1. Counter Management
```python
# Per-component, per-locale, per-mapping counter
counters = {
  "ad_builder_en-ca_false": 2,    # english_input_1, english_input_2
  "ad_builder_fr-ca_true": 1,     # mapped_output_1
  "ad_builder_fr-ca_false": 1,    # french_input_1
  "text_builder_en-ca_false": 1,  # english_input_1
  ...
}
```

### 2. Naming Rules Matrix

| Condition | Output Pattern | Example |
|-----------|---------------|---------|
| locale=en-ca AND mapping=false | `english_input_{N}.json` | `english_input_1.json` |
| locale=fr-ca AND mapping=true | `mapped_output_{N}.json` | `mapped_output_1.json` |
| locale=fr-ca AND mapping=false | `french_input_{N}.json` | `french_input_1.json` |

### 3. Folder Organization
```python
output_path = output_batch / component_type / filename
# Example:
# output_batch/ad_builder/english_input_1.json
```

## 🔌 Integration Points

### Uses Existing Code
- ✅ `lib/contentstack_api.py` - API client (no changes)
- ✅ `lib/json_cleanup.py` - JSON cleaner (no changes)
- ✅ `.env` - Environment variables (same credentials)

### New Components
- 🆕 `batch_json_processor.py` - Main script
- 🆕 `sample_batch_input.csv` - Sample CSV
- 🆕 `output_batch/` - Output directory
- 🆕 Documentation files

## 📊 Comparison: Manual vs Automated

### Manual Process (Before)
```
1. Open Postman
2. Set up POST request with UID
3. Copy response JSON
4. Paste into test.json
5. Run: python json_cleanup_cli.py input-json/test.json CABC --locale en-ca
6. Find test-cleaned.json
7. Rename and move file manually
8. Repeat for each entry (N times)
```
⏱️ **Time per entry: ~2-3 minutes**

### Automated Process (After)
```
1. Create CSV with all UIDs
2. Run: python batch_json_processor.py entries.csv CABC
3. Done! All files in organized folders
```
⏱️ **Time per entry: ~5-10 seconds**

## 🛡️ Error Handling Strategy

```
For each entry in CSV:
    Try:
        ✓ Fetch from API
        ✓ Clean JSON
        ✓ Save file
        ✓ Increment counter
        ✓ Mark as success
    Except error:
        ✗ Log error
        ✗ Mark as failed
        ✓ Continue to next entry
    
Final summary:
    - Total entries processed
    - Success count
    - Failed count
```

## 🔍 Example Processing Log

```
=== BATCH JSON PROCESSOR ===
Environment: CABC
CSV File: entries.csv
Timestamp: 2026-03-11 14:30:00

✅ Batch processor initialized for environment: CABC

📄 Reading CSV file: entries.csv
📊 Found 5 entries to process

[1/5] Processing:
  - UID: blt123abc
  - Component Type: ad_builder
  - Locale: en-ca
  - Mapping: false
  📥 Fetching entry from Contentstack...
  🧹 Cleaning JSON data...
  💾 Writing to: output_batch\ad_builder\english_input_1.json
  ✅ Successfully processed!

[2/5] Processing:
  - UID: blt456def
  - Component Type: ad_builder
  - Locale: en-ca
  - Mapping: true
  📥 Fetching entry from Contentstack...
  🧹 Cleaning JSON data...
  💾 Writing to: output_batch\ad_builder\mapped_output_1.json
  ✅ Successfully processed!

[3/5] Processing:
  - UID: blt789ghi
  - Component Type: text_builder
  - Locale: fr-ca
  - Mapping: false
  📥 Fetching entry from Contentstack...
  🧹 Cleaning JSON data...
  💾 Writing to: output_batch\text_builder\french_input_1.json
  ✅ Successfully processed!

============================================================
BATCH PROCESSING SUMMARY
============================================================
Total Entries: 5
Successful: 5
Failed: 0
Output Directory: C:\...\output_batch
============================================================

🎉 Batch processing completed successfully!
```

## 🎓 Learning Path

1. **Beginner**: Start with `QUICK_START_BATCH.md`
2. **Intermediate**: Read `BATCH_PROCESSOR_README.md`
3. **Advanced**: Study this architecture document
4. **Expert**: Modify `batch_json_processor.py` for custom needs

## 🔗 Related Files

- `json_cleanup_cli.py` - Original manual cleanup script
- `lib/contentstack_api.py` - API client library
- `lib/json_cleanup.py` - JSON cleaning logic
- `.env` - Environment configuration
- `requirements.txt` - Python dependencies

## 📝 Notes

- **Non-destructive**: Does not modify existing code
- **Standalone**: Can be used independently
- **Reusable**: Uses existing libraries
- **Extensible**: Easy to add new naming rules or locales
