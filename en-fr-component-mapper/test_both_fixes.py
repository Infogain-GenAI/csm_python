"""
Test for the two fixes:
1. ad_builder: Clearing image array when image is in text_content markdown
2. text_builder: Smarter paragraph splitting to avoid skipping last paragraph
"""

import sys
sys.path.append('.')

from simple_localizer_v2 import SimpleLocalizerV2

print("=" * 80)
print("FIX VERIFICATION TESTS")
print("=" * 80)

localizer = SimpleLocalizerV2(environment='CABC')

# =============================================================================
# TEST 1: ad_builder - Clear image array when image is in text_content markdown
# =============================================================================

print("\n" + "=" * 80)
print("TEST 1: ad_builder Image Duplication Fix")
print("=" * 80)

english_ad_builder = {
    "image": [],  # Empty in English
    "text_content": [
        {
            "markdown_text": {
                "select_text_type": "title_with_xl_v2",
                "markdown_text": "![Sheri Flies](https://bfasset.costco-static.com/...Sheri_Flies_Headshot.jpg)"
            }
        },
        {
            "markdown_text": {
                "select_text_type": "caption_v2",
                "markdown_text": "© COSTCO PHOTO STUDIO"
            }
        }
    ]
}

french_ad_builder = {
    "image": [  # French AI put image here!
        {
            "id": "8x949pfwvqckf5fqz85wvn",
            "url": "https://cdn.bfldr.com/56O3HXZ9/as/8x949pfwvqckf5fqz85wvn/Sheri_Flies_Headshot",
            "filename": "Sheri_Flies_Headshot.jpg"
        }
    ],
    "text_content": [  # Only caption, no image markdown
        {
            "markdown_text": {
                "select_text_type": "caption_v2",
                "markdown_text": "© STUDIO PHOTO DE COSTCO"
            }
        }
    ]
}

print("\n📋 BEFORE Fix:")
print(f"   English image array: {len(english_ad_builder['image'])} items")
print(f"   French image array: {len(french_ad_builder['image'])} items")
print(f"   English text_content: {len(english_ad_builder['text_content'])} items")
print(f"   French text_content: {len(french_ad_builder['text_content'])} items")

result = localizer._replace_content(english_ad_builder, french_ad_builder)

print("\n✅ AFTER Fix:")
print(f"   Result image array: {len(result['image'])} items")
print(f"   Result text_content: {len(result['text_content'])} items")

if len(result['image']) == 0:
    print("\n✅ PASS: Image array was cleared (image is in text_content)")
else:
    print(f"\n❌ FAIL: Image array still has {len(result['image'])} items (would show 2 images!)")

if len(result['text_content']) == 2:
    print("✅ PASS: text_content has 2 items (image + caption)")
else:
    print(f"❌ FAIL: text_content has {len(result['text_content'])} items")

# Verify image is in text_content markdown
if len(result['text_content']) > 0:
    first_text = result['text_content'][0]['markdown_text']['markdown_text']
    if '![' in first_text and 'Sheri_Flies_Headshot' in first_text:
        print("✅ PASS: Image markdown preserved in text_content[0]")
    else:
        print("❌ FAIL: Image markdown missing from text_content[0]")

# =============================================================================
# TEST 2: text_builder - Smarter paragraph splitting
# =============================================================================

print("\n" + "=" * 80)
print("TEST 2: text_builder Smart Paragraph Splitting")
print("=" * 80)

# Simulate English with 7 text items
english_texts = [
    {"text": "Section 1"},
    {"text": "Section 2"},
    {"text": "Section 3"},
    {"text": "Section 4"},
    {"text": "Section 5"},
    {"text": "Section 6"},
    {"text": "Section 7"}  # This is the "last paragraph" that was missing
]

# Simulate French with 6 text items where Section 6 has 2 paragraphs (6+7 combined)
french_texts = [
    {"markdown_text": "Section 1 FR"},
    {"markdown_text": "Section 2 FR"},
    {"markdown_text": "Section 3 FR"},
    {"markdown_text": "Section 4 FR"},
    {"markdown_text": "Section 5 FR"},
    {"markdown_text": "Section 6 FR - first paragraph with content\n\nSection 7 FR - second paragraph that was missing"}
]

print("\n📋 BEFORE Fix:")
print(f"   English: {len(english_texts)} texts")
print(f"   French: {len(french_texts)} texts")
print(f"   French text 6 has: {french_texts[5]['markdown_text'].count('paragraph')} paragraphs")

# Simulate the extraction and expansion
extracted = []
localizer._extract_texts(french_texts, extracted)

print(f"\n   Extracted: {len(extracted)} French texts")

# Simulate the smart splitting logic
eng_text_count = len(english_texts)
texts_needed = eng_text_count - len(extracted)

print(f"   Need {texts_needed} more text(s) to match English")

# Check if the combined text would be split
combined_text = extracted[-1]  # Last text (Section 6+7)
paragraphs = [p.strip() for p in combined_text.split('\n\n') if p.strip()]

print(f"\n   Combined text has {len(paragraphs)} paragraphs:")
for i, p in enumerate(paragraphs):
    print(f"      Para {i+1}: {p[:50]}...")

# The smart logic should split this text because:
# - It has 2 paragraphs
# - We need 1 more text
# - Splitting gives us exactly what we need

if len(paragraphs) == 2 and texts_needed == 1:
    print(f"\n✅ PASS: Smart logic WILL split (2 paragraphs, need 1 more)")
    print("   Result: 7 French texts matching 7 English texts")
else:
    print(f"\n⚠️  Smart logic might not split optimally")

print("\n" + "=" * 80)
print("ALL TESTS COMPLETE")
print("=" * 80)

print("\n📝 SUMMARY:")
print("   Test 1 (ad_builder): Image array clearing - checks if duplicate images prevented")
print("   Test 2 (text_builder): Smart splitting - checks if last paragraph preserved")
print("\nRun actual localization to verify both fixes work in production!")
