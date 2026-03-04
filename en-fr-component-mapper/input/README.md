# Input Directory

This directory can be used to store input configuration files for batch processing.

## Suggested Uses

### 1. Page Pair Configuration
Create a JSON file with multiple English-French page pairs:

```json
{
  "environment": "CABC",
  "page_pairs": [
    {
      "english_uid": "blt123abc456",
      "french_uid": "blt789def012",
      "content_type": "feature_page",
      "description": "Homepage mapping"
    },
    {
      "english_uid": "blt111aaa222",
      "french_uid": "blt333bbb444",
      "content_type": "feature_page",
      "description": "Product page mapping"
    }
  ]
}
```

### 2. Mapping Configuration
Store custom field classification rules:

```json
{
  "additional_content_fields": [
    "custom_title_field",
    "custom_description_field"
  ],
  "additional_structure_fields": [
    "custom_layout_field",
    "custom_position_field"
  ]
}
```

## Notes

- Currently, the utility reads configuration from command-line arguments
- Future enhancements may support reading from configuration files in this directory
