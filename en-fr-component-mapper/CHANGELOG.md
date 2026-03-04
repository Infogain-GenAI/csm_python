# Changelog - Simple Localizer V2

## Version 2.1.0 (March 3, 2026) - Automation Improvements

### 🎯 Major Changes

#### 1. Auto-Load Environment UID from .env
**Before:**
```bash
python simple_localizer_v2.py <page_uid> input/french.json --publish --env-uids blt8c008d9e7dc9f3a8
```

**After:**
```bash
python simple_localizer_v2.py <english_uid> <french_uid> --publish
```

- ✅ Environment UID is now automatically loaded from `.env` file
- ✅ No need to pass `--env-uids` parameter
- ✅ Based on `--environment` flag (default: CABC)
- ✅ Reads from `CONTENTSTACK_ENVIRONMENT_UID_{ENVIRONMENT}` variable

#### 2. Auto-Fetch French Page from ContentStack
**Before:**
- Manually fetch French page JSON from ContentStack/Postman
- Run JSON cleanup script
- Save to `input/french.json`
- Pass file path to script

**After:**
- Just pass the French page UID directly
- Script automatically:
  - ✅ Fetches the French page from ContentStack
  - ✅ Cleans system fields
  - ✅ Saves to `input/` folder with timestamp
  - ✅ Uses cleaned JSON for localization

**Usage:**
```bash
# Option 1: Auto-fetch French page (Recommended)
python simple_localizer_v2.py blt39d47a6478c64206 blt7fa49cd0a59589d6 --publish

# Option 2: Use existing JSON file (Still supported)
python simple_localizer_v2.py blt39d47a6478c64206 input/french.json --publish
```

### 📝 Updated Parameters

**Old:**
```
python simple_localizer_v2.py <page_uid> <french_json> [options]
```

**New:**
```
python simple_localizer_v2.py <english_page_uid> <french_source> [options]
```

Where `french_source` can be:
- **French Page UID** (e.g., `blt7fa49cd0a59589d6`) - Auto-fetched
- **JSON File Path** (e.g., `input/french.json`) - Existing file

### 🔧 Technical Details

#### Auto-Detection Logic
```python
if os.path.exists(french_source):
    # It's a file path - use the existing file
    use_file(french_source)
elif french_source.startswith('blt'):
    # It's a UID - fetch from ContentStack
    fetch_and_clean(french_source)
else:
    # Invalid input
    show_error()
```

#### Environment UID Loading
```python
env_uid = os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{args.environment}')
# Example: CONTENTSTACK_ENVIRONMENT_UID_CABC=blt8c008d9e7dc9f3a8
```

#### French Page Fetch & Clean
```python
1. Fetch: api.get_entry('feature_page', french_uid, locale='fr-ca')
2. Clean: remove system fields (uid, _version, created_at, etc.)
3. Save: input/french_fetched_{uid}_{timestamp}.json
4. Use: cleaned JSON for component extraction
```

### ✅ Benefits

1. **Less Manual Work** - No more Postman/cleanup steps
2. **Fewer Parameters** - Environment UID auto-loaded
3. **More Flexible** - Accepts UID or file path
4. **Better UX** - Simpler command, fewer mistakes
5. **Audit Trail** - Auto-saved files with timestamps

### 🔄 Migration Guide

**If you have scripts with old syntax:**

```bash
# Old way (still works if you provide file)
python simple_localizer_v2.py blt123 input/french.json --publish --env-uids blt8c008d9e7dc9f3a8

# New way - Option 1 (simplest - auto-fetch)
python simple_localizer_v2.py blt123 blt456 --publish

# New way - Option 2 (with existing file)
python simple_localizer_v2.py blt123 input/french.json --publish

# New way - Option 3 (different environment)
python simple_localizer_v2.py blt123 blt456 --publish --environment USBC
```

### 📋 Examples

#### Before (Manual Process)
1. Open Postman → Fetch French page
2. Copy response to file
3. Run `json_cleanup_cli.py`
4. Move cleaned file to `input/`
5. Run: `python simple_localizer_v2.py blt123 input/french.json --publish --env-uids blt8c008d9e7dc9f3a8`

#### After (Automated)
1. Run: `python simple_localizer_v2.py blt123 blt456 --publish`

**Time saved: ~5 minutes per page** ⏱️

---

## Previous Versions

### Version 2.0.0 (Feb 27 - Mar 2, 2026) - Production Release
- ✅ 3-stage workflow (Draft → Review → Approved → Publish)
- ✅ Network retry logic (3 retries, exponential backoff)
- ✅ Array mismatch handling (all edge cases)
- ✅ Ad_builder intelligent splitting
- ✅ Layout preservation from English
- ✅ Content control flags from French
- ✅ Feature page localization & publishing
- ✅ Tags field enforcement
- ✅ Content types without workflow handling

### Version 1.0.0 - Initial Mapper CLI
- Basic component extraction
- Structure mapping
- AI translation (deprecated)
- Individual file outputs
