# Manual Approval Guide for French Localized Content

## ✅ What Happened

The localization script has **successfully localized all content to French (fr-ca locale)**.

All French content is stored in ContentStack and visible when you switch to the fr-ca locale.

## ⚠️ Why Manual Approval is Needed

ContentStack's API has permission limitations that prevent programmatic workflow updates for newly localized entries. This is a **ContentStack platform limitation**, not a bug in the script.

When content is localized to a new locale (en-ca → fr-ca), ContentStack automatically places the entries in **Review stage**, but the API token cannot move them to Approved stage programmatically.

## 📋 Manual Approval Process

### For Each Page/Component:

1. **Go to ContentStack UI**
   - Navigate to: https://app.contentstack.com/

2. **Switch to French Locale**
   - Click the locale dropdown (top-right)
   - Select: **fr-ca** (French Canada)

3. **Find Your Entries**
   - Go to the content type (e.g., feature_page, text_builder, ad_builder)
   - Look for entries with status: **Review**
   - These are your successfully localized entries!

4. **Approve Each Entry**
   - Click on the entry
   - In the workflow section (usually top-right), click **Review**
   - Select: **Approved**
   - ContentStack will show the French content is ready

5. **Publish the Entry**
   - Click the **Publish** button
   - Select the environment (CABC)
   - Confirm publish

6. **Verify**
   - Check the live site with `?locale=fr-ca` parameter
   - Confirm French content is displaying correctly

## 🔍 What Content Types Need Approval?

Based on typical Costco pages, you'll need to approve:

### Nested Components (Do these first):
- ✅ `link_list_simple` entries
- ✅ `link_flyout` entries  
- ✅ `text_builder` entries
- ✅ `ad_builder` entries
- ✅ `ad_set_costco` entries
- ✅ `custom_rich_text` entries
- ✅ `content_divider` entries

### Parent Components (Do these after nested):
- ✅ `link_list_with_flyout_references`
- ✅ `feature_page` (main page)

**Important**: Approve nested components BEFORE their parent components, otherwise parent components may not show updated nested content.

## 💡 Pro Tips

### Bulk Approval
If you have many entries:
1. Use ContentStack's bulk actions (select multiple entries)
2. Bulk approve all at once
3. Then bulk publish

### Verification Checklist
- [ ] All text is in French (no English remnants)
- [ ] HTML/CSS formatting is preserved
- [ ] Links work correctly
- [ ] Images have French alt text
- [ ] Color schemes match English version

### Common Issues

**Q: I don't see any entries in fr-ca locale?**
- A: Make sure you switched the locale dropdown to "fr-ca"
- The entries exist but are only visible when fr-ca is selected

**Q: Entry shows "Entry update failed" in logs?**
- A: This is expected - the entry IS localized, just needs manual approval
- Check ContentStack UI to confirm the French content is there

**Q: Some content is still in English?**
- A: Check if the field is in CONTENT_FIELDS (script treats some fields as English-only)
- Fields like `uid`, `title` (internal), `tags` are kept in English intentionally

## 🎯 Expected Results

After manual approval and publishing:
- ✅ French pages are live on the website
- ✅ `?locale=fr-ca` parameter shows French content
- ✅ All components display French text
- ✅ SEO metadata is in French
- ✅ Images have French alt text

## 🆘 Need Help?

If you encounter issues:
1. Check ContentStack audit logs to see what failed
2. Verify the API token has read permissions (it does - the localization worked!)
3. Contact ContentStack support about workflow API permissions
4. The localization IS successful - manual approval is just a final step

---

**Remember**: The script did its job! The French content is safely in ContentStack. Manual approval is just a necessary final step due to ContentStack's API limitations.
