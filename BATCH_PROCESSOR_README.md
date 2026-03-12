# Batch JSON Processor

An automated tool to fetch entries from Contentstack, clean them, and organize output files based on component type, locale, and mapping configuration.

## Overview

This tool automates the manual process of:
1. Fetching entries from Contentstack API using UIDs
2. Running JSON cleanup on the fetched data
3. Organizing output files in a structured folder hierarchy

## Features

- ✅ **Batch Processing**: Process multiple entries from a CSV file
- ✅ **Automatic Folder Organization**: Creates component-type subfolders
- ✅ **Smart File Naming**: Automatically names files based on locale and mapping status
- ✅ **Multi-locale Support**: Handles English (en-ca) and French (fr-ca)
- ✅ **Environment Aware**: Works with dev, USBC, USBD, CABC, CABD environments
- ✅ **Error Handling**: Continues processing even if individual entries fail

## Installation

No additional dependencies are required beyond what's already in the project's `requirements.txt`.

```bash
pip install -r requirements.txt
```

## Usage

### Basic Command

```bash
python batch_json_processor.py <csv-file> <environment>
```

### Arguments

- `csv-file`: Path to the CSV file containing entries to process
- `environment`: Target environment (dev, USBC, USBD, CABC, CABD)

### Examples

```bash
# Process entries for CABC environment
python batch_json_processor.py sample_batch_input.csv CABC

# Process entries for USBC environment
python batch_json_processor.py my_entries.csv USBC
```

### Help

```bash
python batch_json_processor.py --help
```

## CSV File Format

The CSV file must have the following columns:

```csv
uid,component_type,locale,mapping
blt123abc456def789,ad_builder,en-ca,false
blt987zyx654wvu321,text_builder,en-ca,true
blt456def789ghi012,link_list_simple,fr-ca,false
```

### Column Descriptions

| Column | Description | Valid Values | Example |
|--------|-------------|--------------|---------|
| `uid` | Entry UID from Contentstack | Any valid UID | `blt123abc456def789` |
| `component_type` | Content type in Contentstack | Any content type | `ad_builder`, `text_builder` |
| `locale` | Language locale | `en-ca`, `fr-ca` | `en-ca` |
| `mapping` | Whether mapping is enabled | `true`, `false` | `false` |

## Output File Naming Convention

The tool automatically names output files based on locale and mapping status:

| Locale | Mapping | Output Filename Pattern |
|--------|---------|------------------------|
| `en-ca` | `false` | `english_input_N.json` |
| `fr-ca` | `true` | `mapped_output_N.json` |
| `fr-ca` | `false` | `french_input_N.json` |

Where `N` is an auto-incrementing counter (1, 2, 3, ...).

## Output Folder Structure

The tool creates a structured output directory:

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
├── link_list_simple/
│   └── french_input_1.json
└── ...
```

Each component type gets its own subfolder with appropriately named JSON files.

## Workflow

1. **Read CSV**: Parses the input CSV file
2. **Fetch Entry**: Calls Contentstack API to get entry data
3. **Clean JSON**: Runs JSON cleanup (same as `json_cleanup_cli.py`)
4. **Organize Output**: Saves to appropriate folder with correct filename

## Example Workflow

### Step 1: Create CSV File

Create a file `my_entries.csv`:

```csv
uid,component_type,locale,mapping
blt7c3tfzrczg59rp6t,ad_builder,en-ca,false
blt98f6t7ktgc8chrx,ad_builder,fr-ca,true
blt456def789ghi012,text_builder,fr-ca,false
```

### Step 2: Run Processor

```bash
python batch_json_processor.py my_entries.csv CABC
```

### Step 3: Check Output

The tool will create:
```
output_batch/
├── ad_builder/
│   ├── english_input_1.json
│   └── mapped_output_1.json
└── text_builder/
    └── french_input_1.json
```

## Output Summary

After processing, you'll see a summary:

```
============================================================
BATCH PROCESSING SUMMARY
============================================================
Total Entries: 3
Successful: 3
Failed: 0
Output Directory: C:\Users\...\output_batch
============================================================
```

## Error Handling

- **Invalid Locale**: Entries with invalid locales (not en-ca or fr-ca) are skipped
- **API Errors**: Failed API calls are logged but don't stop the batch
- **Missing UIDs**: Entries with missing UIDs are skipped
- **Continue on Error**: Processing continues even if individual entries fail

## Environment Variables

Ensure your `.env` file contains the required Contentstack credentials:

```env
CONTENTSTACK_API_KEY_CABC=your_api_key
CONTENTSTACK_MANAGEMENT_TOKEN_CABC=your_token
CONTENTSTACK_BASE_URL_CABC=https://api.contentstack.io/v3
CONTENTSTACK_ENVIRONMENT_UID_CABC=your_env_uid
CONTENTSTACK_AUTH_TOKEN=your_auth_token
```

Replace `CABC` with your target environment name.

## Differences from json_cleanup_cli.py

| Feature | json_cleanup_cli.py | batch_json_processor.py |
|---------|---------------------|-------------------------|
| Input | Single JSON file | CSV with multiple UIDs |
| API Call | Manual (via Postman) | Automatic |
| Output | Single file | Multiple organized files |
| Batch Support | No | Yes |
| Folder Organization | No | Yes (by component type) |
| File Naming | Manual | Automatic (based on rules) |

## Troubleshooting

### Issue: "Missing required environment variables"

**Solution**: Ensure your `.env` file contains all required credentials for the specified environment.

### Issue: "CSV file not found"

**Solution**: Check the path to your CSV file. Use relative or absolute paths.

### Issue: "Invalid locale"

**Solution**: Ensure locale values in CSV are either `en-ca` or `fr-ca`.

### Issue: API connection errors

**Solution**: Verify your Contentstack credentials and network connectivity.

## Notes

- The script does NOT modify any existing code files
- It uses the same `lib/contentstack_api.py` and `lib/json_cleanup.py` as other tools
- Output is written to a separate `output_batch/` directory
- Counters are maintained per component_type + locale + mapping combination
- Each run resets counters (starting from 1)

## Advanced Usage

### Processing Large Batches

For large CSV files (100+ entries), the script will:
- Show progress for each entry
- Continue even if some entries fail
- Provide a summary at the end

### Multiple Runs

If you run the script multiple times with the same CSV:
- Files will be overwritten if they have the same counter value
- To avoid conflicts, clear the `output_batch/` folder between runs

## Support

For issues or questions, refer to:
- Main project README
- `json_cleanup_cli.py` documentation
- Contentstack API documentation

## License

Same as the parent project.
