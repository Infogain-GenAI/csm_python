# Quick Start Guide

Get started with the Python CSM Content Creation Utility in 5 minutes!

## Prerequisites Check

```bash
# Check Python version (need 3.8+)
python --version

# Check pip
pip --version
```

## Setup (One Time)

### 1. Navigate to Project
```bash
cd csm-content-creation-python
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Verify Installation
```bash
python json_cleanup_cli.py --help
python delete_entry_utility.py --help
```

You should see help text for both commands.

## Configuration (Already Done!)

Your `.env` file is already configured with your credentials:
- ✅ dev environment (source)
- ✅ USBC environment  
- ✅ USBD environment
- ✅ CABC environment
- ✅ CABD environment

## Your 3 Main Tasks

### Task 1: Clean JSON File ✅

```bash
# Clean a JSON file using USBC environment
python json_cleanup_cli.py input-json/test.json USBC

# Output will be: input-json/test-cleaned.json
```

**What it does:**
- Removes system metadata
- Fetches nested content from Contentstack
- Cleans URLs
- Outputs ready-to-use JSON

---

### Task 2: Delete Entry ✅

```bash
# STEP 1: Always dry-run first! (shows what would be deleted)
python delete_entry_utility.py blt603b3998575a580e USBC --dry-run

# STEP 2: If dry-run looks good, actually delete
python delete_entry_utility.py blt603b3998575a580e USBC
```

**What it does:**
- Creates automatic backup in `temp/` folder
- Recursively deletes entry and all nested entries
- Provides deletion summary

**⚠️ IMPORTANT:** Always run with `--dry-run` first!

---

### Task 3: Create Content 🚧

```bash
# Coming soon! Core infrastructure is ready.
# Will be: python index.py input-json/test.json --env USBC
```

**Status:** Infrastructure complete, implementation in progress

---

## Common Usage Patterns

### Clean JSON for Different Environments

```bash
# Dev environment
python json_cleanup_cli.py input-json/my-content.json dev

# USBC environment
python json_cleanup_cli.py input-json/my-content.json USBC

# USBD environment
python json_cleanup_cli.py input-json/my-content.json USBD

# CABC environment
python json_cleanup_cli.py input-json/my-content.json CABC

# CABD environment
python json_cleanup_cli.py input-json/my-content.json CABD
```

### Delete Entries Safely

```bash
# 1. Always dry-run first
python delete_entry_utility.py <ENTRY_UID> <ENV> --dry-run

# 2. Review the output carefully

# 3. If everything looks good, delete
python delete_entry_utility.py <ENTRY_UID> <ENV>

# 4. Backup is automatically in temp/ folder
```

### Specify Custom Output

```bash
# Custom output filename for cleanup
python json_cleanup_cli.py input-json/test.json USBC custom-output.json

# Custom content type for deletion
python delete_entry_utility.py blt603b3998575a580e USBC feature_page
```

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│  TASK 1: JSON Cleanup                                   │
├─────────────────────────────────────────────────────────┤
│  python json_cleanup_cli.py <file> <env>                │
│                                                          │
│  Example:                                               │
│  python json_cleanup_cli.py input-json/test.json USBC   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TASK 2: Delete Entry                                   │
├─────────────────────────────────────────────────────────┤
│  python delete_entry_utility.py <uid> <env> [--dry-run] │
│                                                          │
│  Example (dry-run):                                     │
│  python delete_entry_utility.py blt123... USBC --dry-run│
│                                                          │
│  Example (actual):                                      │
│  python delete_entry_utility.py blt123... USBC          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  TASK 3: Create Content (Coming Soon)                   │
├─────────────────────────────────────────────────────────┤
│  python index.py <file> --env <env>                     │
│                                                          │
│  Example:                                               │
│  python index.py input-json/test.json --env USBC        │
│                                                          │
│  Status: 🚧 In Development                              │
└─────────────────────────────────────────────────────────┘
```

## Environment Reference

| Code | Description | Use For |
|------|-------------|---------|
| `dev` | Development | Testing, experiments |
| `USBC` | US Business Center | US business content |
| `USBD` | US Business Delivery | US delivery content |
| `CABC` | Canada Business Center | Canada business content |
| `CABD` | Canada Business Delivery | Canada delivery content |

## File Locations

```
csm-content-creation-python/
├── input-json/          ← Put your input JSON files here
├── temp/                ← Backup files go here (automatic)
│   └── backup_*.json    ← Deletion backups
├── json_cleanup_cli.py  ← Task 1 script
└── delete_entry_utility.py  ← Task 2 script
```

## Troubleshooting Quick Fixes

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Missing environment variable"
Check your `.env` file exists and has the required variables for your environment.

### "Permission denied"
```bash
# On Linux/Mac, make scripts executable
chmod +x json_cleanup_cli.py
chmod +x delete_entry_utility.py
```

### "File not found"
Make sure you're in the `csm-content-creation-python` directory:
```bash
cd csm-content-creation-python
```

## Safety Tips

1. **Always use --dry-run** before deleting entries
2. **Check backup files** in `temp/` folder after deletions
3. **Test on dev first** before running on production environments
4. **Keep backup files** - they're your safety net!
5. **Review dry-run output** carefully before proceeding

## Next Steps

Now you're ready! Try:

1. **Clean a test JSON file:**
   ```bash
   python json_cleanup_cli.py input-json/test.json dev
   ```

2. **Practice with dry-run:**
   ```bash
   python delete_entry_utility.py blt_test_entry dev --dry-run
   ```

3. **Check the README** for more detailed examples

## Getting Help

```bash
# Show help for any command
python json_cleanup_cli.py --help
python delete_entry_utility.py --help
```

---

**You're all set! Start with Task 1 (JSON cleanup) to get familiar with the tools.**
