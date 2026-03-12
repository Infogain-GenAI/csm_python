"""
Test to verify horizontal rule (---) removal is working

This test simulates the exact issue:
- English text has no --- horizontal rules
- French text has --- at beginning and end
- After localization, French should NOT have ---
"""

import sys
sys.path.append('.')

from simple_localizer_v2 import SimpleLocalizerV2

# Your exact case
english_text = '<span style="color: #b01c33;">**COSTCO CONNECTION:**</span> Apples, honey and other ingredients can be found in Costco warehouses.'

french_text_with_hr = '---\n\n<span style="color: #b01c33;">**CONTACT COSTCO:**</span> Des pommes, du miel et d\'autres ingrédients sont offerts en entrepôt et sur Costco.ca.\n\n---'

print("=" * 80)
print("HORIZONTAL RULE (---) REMOVAL TEST")
print("=" * 80)

print("\n📋 ENGLISH text:")
print(f"   '{english_text}'")
print(f"   Has ---? {('---' in english_text)}")

print("\n📋 FRENCH text (BEFORE Fix):")
print(f"   '{french_text_with_hr}'")
print(f"   Has ---? {('---' in french_text_with_hr)} ❌")

# Test the fix
localizer = SimpleLocalizerV2(environment='CABC')

print("\n" + "=" * 80)
print("RUNNING FIX...")
print("=" * 80)

result = localizer._preserve_markdown_formatting(english_text, french_text_with_hr)

print("\n✅ RESULT (AFTER Fix):")
print(f"   '{result}'")
print(f"   Has ---? {('---' in result)}")

print("\n" + "=" * 80)
print("VERIFICATION:")
print("=" * 80)

if '---' not in result:
    print("✅ PASS: Horizontal rules (---) were removed")
else:
    print("❌ FAIL: Horizontal rules (---) still present")

if '***' not in result:
    print("✅ PASS: No *** horizontal rules")
else:
    print("❌ FAIL: *** horizontal rules still present")

if '___' not in result:
    print("✅ PASS: No ___ horizontal rules")
else:
    print("❌ FAIL: ___ horizontal rules still present")

if 'CONTACT COSTCO' in result or 'Des pommes' in result:
    print("✅ PASS: French text content preserved")
else:
    print("❌ FAIL: French text content missing")

if '<span style="color: #b01c33;">' in result:
    print("✅ PASS: HTML styling preserved")
else:
    print("❌ FAIL: HTML styling missing")

# Test with different horizontal rule styles
print("\n" + "=" * 80)
print("TESTING OTHER HORIZONTAL RULE STYLES:")
print("=" * 80)

test_cases = [
    ("English text", "---\nFrench text\n---", "---"),
    ("English text", "***\nFrench text\n***", "***"),
    ("English text", "___\nFrench text\n___", "___"),
    ("English text", "-----\nFrench text\n-----", "-----"),
]

all_passed = True
for eng, fr, separator in test_cases:
    result = localizer._preserve_markdown_formatting(eng, fr)
    if separator in result:
        print(f"❌ FAIL: '{separator}' still in result")
        all_passed = False
    else:
        print(f"✅ PASS: '{separator}' removed")

if all_passed:
    print("\n✅ ALL TESTS PASSED!")
else:
    print("\n❌ SOME TESTS FAILED")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
