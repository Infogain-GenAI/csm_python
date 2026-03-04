# EN-FR Component Mapper Utility

A sophisticated Python utility for mapping English component structures to French components in ContentStack while preserving French language content. This tool helps authors by automatically syncing structure, layout, and configuration from already-authored English pages to AI-generated French pages.

## Overview

When content authors work on bilingual websites (English/French), they often need to:
1. Author English version pages completely with all components configured
2. Generate French version pages with translated content using AI
3. Ensure both versions have identical structure, layout, and styling

This utility automates step 3 by:
- Extracting all components from both English and French pages
- Mapping non-content fields (structure, layout, configuration) from English to French
- Preserving all French content (text, titles, descriptions, etc.)
- Generating updated JSON data ready for ContentStack entry updates

## Features

- ✅ **Smart Component Extraction**: Recursively extracts all nested components from feature pages
- ✅ **Intelligent Field Mapping**: Distinguishes between content fields (French preserved) and structure fields (English mapped)
- ✅ **Multi-Environment Support**: Works with dev, USBC, USBD, CABC, CABD environments
- ✅ **Comprehensive Logging**: Detailed progress tracking and statistics
- ✅ **JSON Output**: Generates ready-to-use JSON files for updating entries
- ✅ **Extract-Only Mode**: Option to only extract data without mapping
- ✅ **Individual Component Export**: Save each mapped component separately

## Installation

### Prerequisites

- Python 3.8 or higher
- Access to ContentStack API credentials
- Parent project dependencies installed

### Setup

1. **Navigate to the utility directory**:
```bash
cd csm-content-creation-python/en-fr-component-mapper
```

2. **Ensure parent dependencies are installed**:
The utility uses shared libraries from the parent project. Make sure dependencies are installed:
```bash
cd ..
pip install -r requirements.txt
cd en-fr-component-mapper
```

3. **Configure environment variables**:
This utility uses the same `.env` file as the parent project. Ensure your `.env` file (in the parent directory) contains:

```env
# For each environment you plan to use (CABC, CABD, USBC, USBD, dev)
CONTENTSTACK_API_KEY_CABC=your_cabc_api_key
CONTENTSTACK_MANAGEMENT_TOKEN_CABC=your_cabc_management_token
CONTENTSTACK_BASE_URL_CABC=https://azure-na-api.contentstack.com/v3
CONTENTSTACK_ENVIRONMENT_UID_CABC=your_cabc_environment_uid

# Auth Token (shared)
CONTENTSTACK_AUTH_TOKEN=your_auth_token
```

## Usage

### Basic Usage

Map structure from English page to French page:

```bash
python mapper_cli.py <english-page-uid> <french-page-uid> <environment>
```

### Examples

**1. Map English structure to French (Canada English to Canada French)**:
```bash
python mapper_cli.py blt123abc456 blt789def012 CABC
```

**2. Use custom content type**:
```bash
python mapper_cli.py blt123abc456 blt789def012 USBC --content-type=landing_page
```

**3. Extract only (no mapping)**:
```bash
python mapper_cli.py blt123abc456 blt789def012 dev --extract-only
```

**4. Map and save individual component files**:
```bash
python mapper_cli.py blt123abc456 blt789def012 CABD --save-individual
```

**5. Show help**:
```bash
python mapper_cli.py --help
```

### Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `english-page-uid` | Yes | UID of the English version feature page (already authored) |
| `french-page-uid` | Yes | UID of the French version feature page (AI-generated) |
| `environment` | Yes | Environment to use (dev, USBC, USBD, CABC, CABD) |

### Command Line Options

| Option | Description |
|--------|-------------|
| `--content-type=TYPE` | Content type of the pages (default: `feature_page`) |
| `--extract-only` | Only extract components, skip structure mapping |
| `--save-individual` | Save each mapped component as individual JSON file |
| `--output-format=FORMAT` | Output format: json (default) |
| `--help`, `-h` | Show help message |

## How It Works

### Process Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Extract English Page Components                     │
│ - Fetch feature page by UID                                  │
│ - Recursively find all component references                  │
│ - Fetch full JSON data for each component                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Extract French Page Components                      │
│ - Same process as Step 1 for French page                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Map Component Structures                            │
│ - Match components by content type and order                │
│ - For each component pair:                                   │
│   • Preserve French CONTENT fields (text, titles, etc.)     │
│   • Map English STRUCTURE fields (layout, config, etc.)     │
│   • Generate updated JSON for French component              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STEP 4: Save Results                                         │
│ - Save mapped components with statistics                    │
│ - Optionally save individual component files                │
│ - Generate summary report                                    │
└─────────────────────────────────────────────────────────────┘
```

### Field Classification

The utility intelligently classifies fields into three categories:

**Content Fields (Preserved from French)**:
- `title`, `description`, `text`, `content`, `label`, `name`
- `heading`, `subheading`, `button_text`, `link_text`
- `caption`, `disclaimer`, `tooltip`, `placeholder`
- Any field containing keywords: text, title, description, label, content, message

**Structure Fields (Mapped from English)**:
- `layout`, `display_type`, `variant`, `position`, `alignment`
- `order`, `priority`, `visibility`, `enabled`, `style`, `theme`
- `width`, `height`, `spacing`, `margin`, `padding`, `columns`
- `configuration`, `settings`, `options`, `parameters`
- Any field containing keywords: layout, style, display, position, align, config

**System Fields (Excluded)**:
- `uid`, `_version`, `_metadata`, `ACL`, `publish_details`
- `created_at`, `updated_at`, `created_by`, `updated_by`, `locale`

## Output Files

The utility generates several output files in the `output/` directory:

### 1. English Extraction File
**Filename**: `english_extracted_<uid>_<timestamp>.json`

Contains all extracted components from the English page with full JSON data.

### 2. French Extraction File
**Filename**: `french_extracted_<uid>_<timestamp>.json`

Contains all extracted components from the French page with full JSON data.

### 3. Mapped Result File
**Filename**: `mapped_result_<uid>_<timestamp>.json`

Contains the final mapped components ready for ContentStack updates:

```json
{
  "metadata": {
    "timestamp": "20260226-143022",
    "environment": "CABC",
    "english_page_uid": "blt123abc456",
    "french_page_uid": "blt789def012",
    "english_page_title": "English Page Title",
    "french_page_title": "Titre de la page française",
    "total_components_mapped": 15
  },
  "mapped_components": [
    {
      "content_type_uid": "link_list_flyout_reference",
      "original_french_uid": "blt111aaa222",
      "english_reference_uid": "blt333bbb444",
      "mapped_data": {
        // Updated JSON with English structure + French content
      },
      "mapping_stats": {
        "total_fields_processed": 45,
        "content_fields_preserved": 12,
        "structure_fields_mapped": 28,
        "system_fields_excluded": 5
      }
    }
    // ... more components
  ]
}
```

### 4. Individual Component Files (Optional)
**Directory**: `output/components_<timestamp>/`

When using `--save-individual`, each component is saved as:
`<content_type_uid>_<uid>.json`

## Architecture

### Project Structure

```
en-fr-component-mapper/
├── mapper_cli.py                 # Main CLI entry point
├── lib/
│   ├── __init__.py              # Package initialization
│   ├── component_extractor.py   # Component extraction logic
│   └── structure_mapper.py      # Structure mapping logic
├── input/                        # Input files (optional)
├── output/                       # Generated output files
├── logs/                         # Log files (if needed)
└── README.md                     # This file
```

### Module Overview

**`component_extractor.py`**:
- Extracts component UIDs from feature pages
- Recursively finds nested component references
- Fetches full JSON data for each component
- Provides caching for performance

**`structure_mapper.py`**:
- Maps structure from English to French
- Classifies fields (content vs structure)
- Preserves French content
- Provides detailed mapping statistics

**`mapper_cli.py`**:
- Command-line interface
- Orchestrates the extraction and mapping process
- Handles environment configuration
- Generates output files and reports

## Best Practices

### 1. Environment Selection
- Use **CABC** for Canada English to Canada French mappings
- Use **USBC** for US English pages
- Use **dev** for testing before production

### 2. Content Type Specification
- Default is `feature_page`
- Use `--content-type` if working with other page types
- Ensure both English and French pages are of the same content type

### 3. Validation Workflow
1. Run with `--extract-only` first to verify component extraction
2. Review extracted data in output files
3. Run full mapping
4. Review mapped results before updating ContentStack
5. Test updated French page thoroughly

### 4. Error Handling
- Check console output for warnings about mismatched components
- Review mapping statistics to ensure proper field classification
- Save logs for troubleshooting

## Troubleshooting

### Common Issues

**1. Missing Environment Variables**
```
Error: Missing required environment variables: CONTENTSTACK_API_KEY_CABC
```
**Solution**: Add missing variables to `.env` file in parent directory

**2. Component Count Mismatch**
```
Warning: English has 10 components, French has 8 components
```
**Solution**: Review page structure; pages may have intentionally different components

**3. Content Type Mismatch**
```
WARNING: Content type mismatch!
English: link_list_flyout_reference
French: ad_builder
```
**Solution**: Component order differs; review component structure manually

**4. API Rate Limiting**
```
Rate limited. Waiting 2 seconds before retry...
```
**Solution**: Automatic retry; no action needed. Reduce concurrent requests if persistent.

## Advanced Usage

### Using Mapped Data to Update ContentStack

After generating mapped results, you can use the ContentStack API to update French entries:

```python
from lib.contentstack_api import ContentstackAPI

# Initialize API
api = ContentstackAPI(...)

# Load mapped results
with open('output/mapped_result_<uid>_<timestamp>.json', 'r') as f:
    results = json.load(f)

# Update each component
for component in results['mapped_components']:
    api.update_entry(
        component['content_type_uid'],
        component['original_french_uid'],
        component['mapped_data']
    )
```

### Batch Processing Multiple Pages

Create a script to process multiple page pairs:

```python
page_pairs = [
    ('blt_en_1', 'blt_fr_1'),
    ('blt_en_2', 'blt_fr_2'),
    # ...
]

for en_uid, fr_uid in page_pairs:
    os.system(f'python mapper_cli.py {en_uid} {fr_uid} CABC')
```

## Contributing

When adding new features:
1. Follow existing code structure and patterns
2. Add comprehensive docstrings
3. Update README with new functionality
4. Test with multiple environments

## License

Internal utility for ContentStack content management.

## Support

For issues or questions:
1. Check console output for detailed error messages
2. Review generated output files
3. Verify environment configuration
4. Contact development team

---

**Version**: 1.0.0  
**Last Updated**: February 26, 2026  
**Maintained By**: CSM Python Team
