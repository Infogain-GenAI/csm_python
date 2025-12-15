# CSM Content Creation Utility - Python Version

A comprehensive Python utility suite for content management that creates content in Brandfolder and Contentstack, processes JSON files, and provides flexible content creation workflows with dynamic multi-environment support.

## Features

- **JSON Cleanup**: Clean and optimize JSON files with automatic nested content fetching
- **Entry Deletion**: Recursively delete entries with automatic backup functionality
- **Content Creation**: Create complete feature pages with nested components (Coming soon - see note below)
- **Asset Management**: Upload assets to Brandfolder DAM from URLs
- **Multi-Environment Support**: Dynamic environment configuration (dev, USBC, USBD, CABC, CABD)

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Environment Configuration

1. Copy the `.env.example` file to `.env`:
```bash
copy .env.example .env
```

2. Edit `.env` and fill in your environment-specific credentials for each environment you want to use:

```env
# Dev Environment
CONTENTSTACK_API_KEY_dev=your_dev_api_key
CONTENTSTACK_MANAGEMENT_TOKEN_dev=your_dev_token
CONTENTSTACK_BASE_URL_dev=https://azure-na-api.contentstack.com/v3
CONTENTSTACK_ENVIRONMENT_UID_dev=your_dev_environment_uid
BRANDFOLDER_API_KEY_dev=your_dev_brandfolder_key
BRANDFOLDER_ORGANIZATION_ID_dev=your_dev_org_id
BRANDFOLDER_COLLECTION_ID_dev=your_dev_collection_id
BRANDFOLDER_SECTION_KEY_dev=your_dev_section_key

# USBC Environment (similar structure)
# USBD Environment (similar structure)
# CABC Environment (similar structure)
# CABD Environment (similar structure)

# Auth Token
CONTENTSTACK_AUTH_TOKEN=your_auth_token

# Processing Configuration
ENTRY_REUSE_ENABLED=false
INPUT_JSON_PATH=input-json/test.json
NODE_TLS_REJECT_UNAUTHORIZED=0
HANDLE_DUPLICATE_PAGE_ID=false
```

## Usage

### Task 1: JSON Cleanup Utility

Clean JSON files and fetch nested content from Contentstack.

**Node.js equivalent:**
```bash
node json-cleanup-cli.js input-json/test.json target
```

**Python command:**
```bash
# Basic usage with environment
python json_cleanup_cli.py input-json/test.json USBC

# With custom output file
python json_cleanup_cli.py input-json/test.json dev output-cleaned.json

# Using different environments
python json_cleanup_cli.py input-json/test.json USBD
python json_cleanup_cli.py input-json/test.json CABC
python json_cleanup_cli.py input-json/test.json CABD

# Show help
python json_cleanup_cli.py --help
```

**What it does:**
- Removes system metadata fields (_version, uid, ACL, publish_details, etc.)
- Fetches full content for nested entries from Contentstack
- Removes Contentstack asset URLs matching pattern `blt[0-9a-z]+`
- Restructures JSON for content creation
- Outputs cleaned JSON to specified file or default (`input-file-cleaned.json`)

**Arguments:**
- `input-file`: Path to the JSON file to clean
- `environment`: Environment to use (dev, USBC, USBD, CABC, CABD)
- `output-file` (optional): Output file path (defaults to input-file-cleaned.json)

---

### Task 2: Entry Deletion Utility

Recursively delete entries with automatic backup.

**Node.js equivalent:**
```bash
node delete-entry-utility.js blt603b3998575a580e target
```

**Python command:**
```bash
# Delete entry from USBC environment
python delete_entry_utility.py blt603b3998575a580e USBC

# Delete with specific content type
python delete_entry_utility.py blt603b3998575a580e dev feature_page

# Dry run (preview what would be deleted) - RECOMMENDED FIRST
python delete_entry_utility.py blt603b3998575a580e USBC --dry-run

# Using different environments
python delete_entry_utility.py blt603b3998575a580e USBD
python delete_entry_utility.py blt603b3998575a580e CABC --dry-run

# Show help
python delete_entry_utility.py --help
```

**What it does:**
- Creates automatic backup in `temp/` directory before deletion
- Recursively deletes all nested entries (from leaf to root)
- Supports dry-run mode for safety
- Provides detailed deletion summary
- Backup files are timestamped and include full entry data

**Arguments:**
- `entry-uid`: The UID of the entry to delete recursively
- `environment`: The environment (dev, USBC, USBD, CABC, CABD)
- `content-type-uid` (optional): Content type UID (defaults to "feature_page")

**Options:**
- `--dry-run`: Show what would be deleted without actually deleting

**Important Notes:**
- **ALWAYS run with `--dry-run` first** to preview what will be deleted
- Backups are automatically created in the `temp/` directory
- Backup filename format: `backup_{content_type}_{entry_uid}_{timestamp}.json`
- Keep backups safe for potential recovery

---

### Task 3: Content Creation Utility (index.py)

Create complete feature pages with nested components.

**Node.js equivalent:**
```bash
node index.js input-json/test.json --env target
```

**Python command:**
```bash
# ✅ READY TO USE - Full Python implementation
python index.py input-json/test.json --env USBC
python index.py --help
```

**What it does:**
- ✅ Process hierarchical content structures
- ✅ Upload assets to Brandfolder
- ✅ Create entries in Contentstack from leaf to root
- ✅ Handle workflow progression (Review → Approved)
- ✅ Publish entries with deep publish
- ✅ Generate published URLs
- ✅ Rollback protection on errors

**Current Status:** 
- ✅ `index.py` - Fully functional
- ✅ `content_processor.py` - Complete implementation
- ✅ Core API clients ready (contentstack_api.py, brandfolder_api.py)
- ✅ Environment configuration ready
- ✅ **READY FOR PRODUCTION USE**

---

## Environment Support

The utility supports dynamic environment configuration for different Contentstack and Brandfolder environments:

| Environment | Description |
|------------|-------------|
| **dev** | Development environment |
| **USBC** | US Business Center |
| **USBD** | US Business Delivery |
| **CABC** | Canada Business Center |
| **CABD** | Canada Business Delivery |

Each environment has its own:
- Contentstack API credentials (API key, management token, base URL)
- Brandfolder credentials (API key, organization ID, collection ID, section key)
- Environment-specific configurations

## Project Structure

```
csm-content-creation-python/
├── lib/
│   ├── contentstack_api.py      # Contentstack API client ✅
│   ├── brandfolder_api.py       # Brandfolder API client ✅
│   ├── json_cleanup.py          # JSON cleanup functionality ✅
│   └── __init__.py              # Package initialization
├── input-json/                  # Input JSON files
├── temp/                        # Temporary files and backups
├── json_cleanup_cli.py          # Task 1: JSON cleanup CLI ✅
├── delete_entry_utility.py      # Task 2: Entry deletion CLI ✅
├── index.py                     # Task 3: Content creation CLI ✅
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment configuration template
├── .env                         # Your actual environment config (not in git)
├── .gitignore                   # Git ignore file
├── README.md                    # This file
├── QUICK_START.md               # Quick start guide
└── MIGRATION_GUIDE.md           # Migration from Node.js guide
```

## Migration from Node.js

This Python version is a complete migration of the Node.js codebase with the following improvements:

### Key Differences:

1. **Environment Configuration**: 
   - Node.js used `source` and `target` naming
   - Python uses explicit environment names (dev, USBC, USBD, CABC, CABD)
   
2. **Command Syntax**:
   ```bash
   # Node.js
   node json-cleanup-cli.js input-json/test.json target
   
   # Python
   python json_cleanup_cli.py input-json/test.json USBC
   ```

3. **Benefits**:
   - ✅ More explicit environment naming
   - ✅ Support for multiple environments (not just source/target)
   - ✅ Cleaner configuration management
   - ✅ Better error handling and logging
   - ✅ Type hints for better code clarity

## Error Handling

All utilities include comprehensive error handling:
- Automatic retry logic for API calls
- Rate limiting protection
- Detailed error messages with stack traces
- Graceful degradation on failures

## Best Practices

1. **Always test with dry-run first** when deleting entries
2. **Keep backups** of important content before deletion
3. **Use dev environment** for testing before production
4. **Monitor API rate limits** during batch operations
5. **Verify .env configuration** before running utilities
6. **Check backup files** in `temp/` directory after deletions

## Troubleshooting

### Missing Environment Variables
If you see errors about missing environment variables:
1. Ensure your `.env` file exists in the project root
2. Check that all required variables for your target environment are set
3. Verify variable names match the pattern: `CONTENTSTACK_API_KEY_{environment}`

### API Rate Limiting
The utilities include automatic rate limiting and retry logic. If you encounter persistent rate limit errors:
1. The system will automatically retry with exponential backoff
2. Check Contentstack/Brandfolder API quotas
3. Consider adding delays between operations

### Backup Files
- Backup files are stored in `temp/` directory
- Filename format: `backup_{content_type}_{entry_uid}_{timestamp}.json`
- Keep these files safe for potential recovery
- Backups include cleaned JSON data ready for re-import

## Dependencies

- `requests==2.31.0` - HTTP library for API calls
- `python-dotenv==1.0.0` - Environment variable management

## Support

For issues or questions:
1. Check this README for usage examples
2. Review error messages carefully
3. Ensure environment variables are correctly set
4. Test with `--dry-run` for deletion operations

## License

MIT License

---

## Quick Reference

```bash
# Task 1: Clean JSON
python json_cleanup_cli.py input-json/test.json USBC

# Task 2: Delete Entry (with dry-run first!)
python delete_entry_utility.py blt603b3998575a580e USBC --dry-run
python delete_entry_utility.py blt603b3998575a580e USBC

# Task 3: Create Content (✅ READY)
python index.py input-json/test.json --env USBC
```

**Remember**: Always use `--dry-run` before actually deleting entries!
