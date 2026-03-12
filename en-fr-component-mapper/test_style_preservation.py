"""
Test that styling fields are properly preserved from English structure
when using flatten-remap strategy with text_section_content
"""

import json

# Simulate the issue you reported
english_section_1 = {
    "color_config": {},
    "_metadata": {"uid": "cs61a1ae133fb09fae"},
    "text_section_icon": {"icon_image": [], "icon_alt_text": ""},
    "text_section_content": [
        {
            "select_text_type": "title_with_xl_v2",      # ← Must be preserved!
            "select_semantics_type": "h1",                # ← Must be preserved!
            "text_alignment": "left",                     # ← Must be preserved!
            "markdown_text": "Human rights",
            "_metadata": {"uid": "cs00cec1eb154b69af"},
            "color": {}
        }
    ]
}

french_section_1 = {
    "color_config": {},
    "text_section_icon": {"icon_image": [], "icon_alt_text": ""},
    "text_section_content": [
        {
            "select_text_type": "title_v2",               # ← WRONG! Should be title_with_xl_v2
            "select_semantics_type": None,                # ← WRONG! Should be h1
            "text_alignment": "left",
            "markdown_text": "Droits humains",
            "color": {},
            "_metadata": {"uid": "cs1c5c1f061c502a4a"},
            "enable_custom_tag_parsing": False
        }
    ],
    "_metadata": {"uid": "cs22f899002f727462"}
}

print("=" * 80)
print("TESTING STYLE PRESERVATION FIX")
print("=" * 80)

print("\n📋 ENGLISH Section 1:")
print(f"   select_text_type: {english_section_1['text_section_content'][0]['select_text_type']}")
print(f"   select_semantics_type: {english_section_1['text_section_content'][0]['select_semantics_type']}")
print(f"   markdown_text: {english_section_1['text_section_content'][0]['markdown_text']}")

print("\n📋 FRENCH Section 1 (BEFORE Fix):")
print(f"   select_text_type: {french_section_1['text_section_content'][0]['select_text_type']}")
print(f"   select_semantics_type: {french_section_1['text_section_content'][0]['select_semantics_type']}")
print(f"   markdown_text: {french_section_1['text_section_content'][0]['markdown_text']}")

# Now test with the localizer
from simple_localizer_v2 import SimpleLocalizerV2

localizer = SimpleLocalizerV2(environment='CABC')

# Test the _replace_content function (should preserve English structure)
print("\n" + "=" * 80)
print("TESTING _replace_content (normal case)")
print("=" * 80)

result = localizer._replace_content(english_section_1, french_section_1)

print("\n✅ RESULT After _replace_content:")
print(f"   select_text_type: {result['text_section_content'][0]['select_text_type']}")
print(f"   select_semantics_type: {result['text_section_content'][0]['select_semantics_type']}")
print(f"   markdown_text: {result['text_section_content'][0]['markdown_text']}")

# Verify preservation
expected_type = "title_with_xl_v2"
expected_semantic = "h1"
expected_text = "Droits humains"

actual_type = result['text_section_content'][0]['select_text_type']
actual_semantic = result['text_section_content'][0]['select_semantics_type']
actual_text = result['text_section_content'][0]['markdown_text']

print("\n🔍 VERIFICATION:")
if actual_type == expected_type:
    print(f"   ✅ select_text_type CORRECT: {actual_type}")
else:
    print(f"   ❌ select_text_type WRONG: {actual_type} (expected {expected_type})")

if actual_semantic == expected_semantic:
    print(f"   ✅ select_semantics_type CORRECT: {actual_semantic}")
else:
    print(f"   ❌ select_semantics_type WRONG: {actual_semantic} (expected {expected_semantic})")

if actual_text == expected_text:
    print(f"   ✅ markdown_text CORRECT: {actual_text}")
else:
    print(f"   ❌ markdown_text WRONG: {actual_text} (expected {expected_text})")

# Now test the flatten-remap scenario (the problematic case)
print("\n" + "=" * 80)
print("TESTING FLATTEN-REMAP SCENARIO (text mismatch case)")
print("=" * 80)

# Simulate English with multiple sections
eng_sections = [
    {
        "text_section_content": [{
            "select_text_type": "title_with_xl_v2",
            "select_semantics_type": "h1",
            "text_alignment": "left",
            "markdown_text": "Human rights",
            "color": {}
        }]
    },
    {
        "text_section_content": [{
            "select_text_type": "subheading_v2",
            "select_semantics_type": "h2",
            "text_alignment": "left",
            "markdown_text": "People are critical",
            "color": {}
        }]
    },
    {
        "text_section_content": [{
            "select_text_type": "body_copy_v2",
            "select_semantics_type": None,
            "text_alignment": "left",
            "markdown_text": "by SHERI FLIES\n\nWhile our sustainability...",
            "color": {}
        }]
    }
]

# Simulate French with different structure (heading split from body)
fr_sections = [
    {
        "text_section_content": [{
            "select_text_type": "title_v2",        # ← WRONG type
            "select_semantics_type": None,          # ← WRONG semantic
            "markdown_text": "Droits humains",
            "color": {}
        }]
    },
    {
        "text_section_content": [{
            "select_text_type": "subheading_v2",
            "markdown_text": "Les personnes",
            "color": {}
        }]
    },
    {
        "text_section_content": [{
            "select_text_type": "body_copy_v2",
            "markdown_text": "SHERI FLIES",
            "color": {}
        }]
    },
    {
        "text_section_content": [{
            "select_text_type": "body_copy_v2",
            "markdown_text": "Si nos pratiques...",
            "color": {}
        }]
    }
]

print(f"\n📊 English: {len(eng_sections)} sections, 3 texts")
print(f"📊 French: {len(fr_sections)} sections, 4 texts")
print("\n🔧 Testing if flatten-remap preserves English styling...")

# Test _map_with_french_texts (the new fixed function)
french_texts = ["Droits humains", "Les personnes", "SHERI FLIES"]

mapped_section, texts_used = localizer._map_with_french_texts(
    eng_sections[0], french_texts, 0
)

print(f"\n✅ Mapped Section 1 (used {texts_used} text(s)):")
print(f"   select_text_type: {mapped_section['text_section_content'][0]['select_text_type']}")
print(f"   select_semantics_type: {mapped_section['text_section_content'][0]['select_semantics_type']}")
print(f"   markdown_text: {mapped_section['text_section_content'][0]['markdown_text']}")

# Verify
actual_type = mapped_section['text_section_content'][0]['select_text_type']
actual_semantic = mapped_section['text_section_content'][0]['select_semantics_type']

print("\n🔍 FLATTEN-REMAP VERIFICATION:")
if actual_type == "title_with_xl_v2":
    print(f"   ✅ select_text_type PRESERVED: {actual_type}")
else:
    print(f"   ❌ select_text_type NOT PRESERVED: {actual_type}")

if actual_semantic == "h1":
    print(f"   ✅ select_semantics_type PRESERVED: {actual_semantic}")
else:
    print(f"   ❌ select_semantics_type NOT PRESERVED: {actual_semantic}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
