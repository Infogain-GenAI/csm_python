# EN-FR Component Mapper - Quick Start Guide

## 🚀 Quick Start (3 Minutes)

### Step 1: Verify Environment Setup
Make sure your `.env` file (in parent directory) has the required credentials:
```bash
# Check if .env exists
cd ..
type .env  # Windows
# or: cat .env  # Unix/Mac
```

Required variables:
- `CONTENTSTACK_API_KEY_CABC`
- `CONTENTSTACK_MANAGEMENT_TOKEN_CABC`
- `CONTENTSTACK_AUTH_TOKEN`
- `CONTENTSTACK_ENVIRONMENT_UID_CABC` (auto-loaded, no need to pass)

### Step 2: Run Localization

**Option 1: Using French Page UID (Recommended - Fully Automated)**
```bash
python simple_localizer_v2.py <english_page_uid> <french_page_uid> --publish
```

**Option 2: Using French JSON File (Manual)**
```bash
python simple_localizer_v2.py <english_page_uid> input/french.json --publish
```

### Step 3: Watch the Magic ✨
The script will:
1. ✅ Fetch English page structure
2. ✅ Fetch & clean French page (if UID provided) OR use JSON file
3. ✅ Localize all components (nested first, then parent)
4. ✅ Move components through workflow (Draft → Review → Approved)
5. ✅ Publish all components
6. ✅ Localize & publish feature page

## 📋 Common Commands

### Full Localization with Publishing (Auto-fetch French)
```bash
python simple_localizer_v2.py blt39d47a6478c64206 blt7fa49cd0a59589d6 --publish
```

### Dry Run (Test Without Changes)
```bash
python simple_localizer_v2.py blt39d47a6478c64206 blt7fa49cd0a59589d6 --dry-run
```

### Using JSON File Instead of UID
```bash
python simple_localizer_v2.py blt39d47a6478c64206 input/french.json --publish
```

### Different Environment
```bash
python simple_localizer_v2.py blt123... blt456... --publish --environment USBC
```

## 📂 Where Files Are Saved

- **Input:** `input/` - French JSON files (auto-saved if using UID)
- **Logs:** `logs/` - Execution logs
- **Output:** `output/` - Old output files from mapper_cli (legacy)

## 🎯 What Happens

### Phase 1: Localization
- Fetches English page and extracts all component references
- Fetches/loads French page and extracts component data
- Matches components by position and content type
- Maps French content to English structure
- Localizes nested components first (depth-first)
- Then localizes parent components

### Phase 2: Workflow & Publishing
- Moves each component: Draft → Review → Approved
- Publishes components with proper workflow stage
- Handles content types without workflow (direct publish)

### Phase 3: Feature Page
- Localizes the feature page container
- Moves through workflow stages
- Publishes with all localized components

## ⚠️ Important Notes

- **Environment UID is auto-loaded from .env** - no need to pass `--env-uids`
- **French source can be UID or file path** - script detects automatically
- **Tags field is always set** to `["migrated-from-cms"]`
- **Workflow is automatic** - 3-stage process with retry logic
- **Network errors are handled** - 3 retries with exponential backoff

## 🆘 Need Help?

```bash
python simple_localizer_v2.py --help
```

## 💡 Pro Tips

- **Use French UID directly** - no need to manually fetch/clean JSON
- **Environment UID is auto-loaded** - one less parameter to pass
- **Dry run first** to verify structure: `--dry-run`
- **Check console output** for real-time progress and any issues

---

**Ready to start?** 

```bash
python simple_localizer_v2.py <english_uid> <french_uid> --publish
```

Example:
```bash
python simple_localizer_v2.py blt39d47a6478c64206 blt7fa49cd0a59589d6 --publish
```
