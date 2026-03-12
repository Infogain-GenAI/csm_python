"""
Test to verify text_content image markdown handling fix

This test simulates the exact issue you reported:
- English has 2 items in text_content: [image markdown, caption]
- French has 1 item in text_content: [caption only]
- French image is in different location (image array)

Expected result:
- French text_content should have 2 items matching English structure
- Item 0: English image markdown (preserved)
- Item 1: French caption with English styling (select_text_type, select_semantics_type)
"""

import sys
import json
sys.path.append('.')

from simple_localizer_v2 import SimpleLocalizerV2

# Your exact English ad_builder text_content
english_text_content = [
    {
        "markdown_text": {
            "select_text_type": "title_with_xl_v2",
            "select_semantics_type": None,
            "markdown_text": "![enter image description here](https://bfasset.costco-static.com/56O3HXZ9/at/h8q7ftxtr4bjw3fn7bvtjftg/Sheri_Flies_Headshot.jpg?auto=webp&format=jpg&width=320)",
            "_metadata": {"uid": "cs7dc47588c034134f"},
            "color": {}
        }
    },
    {
        "markdown_text": {
            "select_text_type": "caption_v2",
            "select_semantics_type": None,  # ← Should be null, not h3!
            "markdown_text": "© COSTCO PHOTO STUDIO",
            "_metadata": {"uid": "cscdf698f54fa4ba03"},
            "color": {}
        }
    }
]

# Your exact French ad_builder text_content (WRONG - missing image, wrong semantic)
french_text_content = [
    {
        "markdown_text": {
            "select_text_type": "caption_v2",
            "select_semantics_type": "h3",  # ← WRONG! Should be null
            "markdown_text": "© STUDIO PHOTO DE COSTCO",
            "color": {
                "background_gradient_style": "solid",
                "background_color": {"hex": "#FFFFFF"},
                "text_color": {"hex": "#333333"}
            },
            "_metadata": {"uid": "cs907cca206b266ba1"}
        }
    }
]

print("=" * 80)
print("TEXT_CONTENT IMAGE MARKDOWN FIX TEST")
print("=" * 80)

print("\n📋 ENGLISH text_content:")
print(f"   Length: {len(english_text_content)} items")
print(f"   Item 0: {english_text_content[0]['markdown_text']['select_text_type']}")
print(f"           Text: {english_text_content[0]['markdown_text']['markdown_text'][:50]}...")
print(f"   Item 1: {english_text_content[1]['markdown_text']['select_text_type']}")
print(f"           Semantic: {english_text_content[1]['markdown_text']['select_semantics_type']}")
print(f"           Text: {english_text_content[1]['markdown_text']['markdown_text']}")

print("\n📋 FRENCH text_content (BEFORE Fix):")
print(f"   Length: {len(french_text_content)} items (WRONG - should be 2!)")
print(f"   Item 0: {french_text_content[0]['markdown_text']['select_text_type']}")
print(f"           Semantic: {french_text_content[0]['markdown_text']['select_semantics_type']} (WRONG - should be null!)")
print(f"           Text: {french_text_content[0]['markdown_text']['markdown_text']}")

# Test the fix
localizer = SimpleLocalizerV2(environment='CABC')

print("\n" + "=" * 80)
print("RUNNING FIX...")
print("=" * 80)

result = localizer._replace_content(english_text_content, french_text_content)

print("\n✅ RESULT (AFTER Fix):")
print(f"   Length: {len(result)} items")

if len(result) >= 1:
    print(f"\n   Item 0:")
    print(f"      Type: {result[0]['markdown_text']['select_text_type']}")
    print(f"      Semantic: {result[0]['markdown_text']['select_semantics_type']}")
    print(f"      Text: {result[0]['markdown_text']['markdown_text'][:80]}...")
    
if len(result) >= 2:
    print(f"\n   Item 1:")
    print(f"      Type: {result[1]['markdown_text']['select_text_type']}")
    print(f"      Semantic: {result[1]['markdown_text']['select_semantics_type']}")
    print(f"      Text: {result[1]['markdown_text']['markdown_text']}")

print("\n" + "=" * 80)
print("VERIFICATION:")
print("=" * 80)

# Verify Item 0 (image markdown)
if len(result) >= 1:
    item0 = result[0]['markdown_text']
    if item0['select_text_type'] == 'title_with_xl_v2':
        print("✅ Item 0: select_text_type CORRECT (title_with_xl_v2)")
    else:
        print(f"❌ Item 0: select_text_type WRONG ({item0['select_text_type']})")
    
    if '![' in item0['markdown_text'] and 'Sheri_Flies_Headshot' in item0['markdown_text']:
        print("✅ Item 0: Image markdown PRESERVED")
    else:
        print("❌ Item 0: Image markdown MISSING")

# Verify Item 1 (caption)
if len(result) >= 2:
    item1 = result[1]['markdown_text']
    if item1['select_text_type'] == 'caption_v2':
        print("✅ Item 1: select_text_type CORRECT (caption_v2)")
    else:
        print(f"❌ Item 1: select_text_type WRONG ({item1['select_text_type']})")
    
    if item1['select_semantics_type'] is None:
        print("✅ Item 1: select_semantics_type CORRECT (null)")
    else:
        print(f"❌ Item 1: select_semantics_type WRONG ({item1['select_semantics_type']} - should be null)")
    
    if 'STUDIO PHOTO DE COSTCO' in item1['markdown_text']:
        print("✅ Item 1: French caption text CORRECT")
    else:
        print("❌ Item 1: French caption text MISSING")

if len(result) == 2:
    print("\n✅ Array length CORRECT (2 items)")
else:
    print(f"\n❌ Array length WRONG ({len(result)} items - should be 2)")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
