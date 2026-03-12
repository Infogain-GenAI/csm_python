import json
import sys
sys.path.append('.')

from simple_localizer_v2 import SimpleLocalizerV2

# Load test data
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng_data = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr_data = json.load(f)

# Create minimal localizer instance (just for testing _replace_content)
class TestLocalizer:
    def __init__(self):
        # Import the method directly
        self._replace_content = SimpleLocalizerV2.__dict__['_replace_content'].__get__(self, SimpleLocalizerV2)
        self._create_french_component = SimpleLocalizerV2.__dict__['_create_french_component'].__get__(self, SimpleLocalizerV2)
        self._preserve_markdown_formatting = SimpleLocalizerV2.__dict__['_preserve_markdown_formatting'].__get__(self, SimpleLocalizerV2)
        self._strip_all_markdown = SimpleLocalizerV2.__dict__['_strip_all_markdown'].__get__(self, SimpleLocalizerV2)

localizer = TestLocalizer()

# Test content_divider mapping
print('=== TESTING CONTENT_DIVIDER MAPPING ===\n')

# Get first content_divider from each
eng_divider = None
fr_divider = None

for component in eng_data['entry']['page_composer']:
    if 'row' in component:
        for item in component['row'].get('row_composer', []):
            if 'content_divider_block' in item:
                eng_divider = item['content_divider_block']['content_divider_ref'][0]['entry']
                break
        if eng_divider:
            break

for component in fr_data['entry']['page_composer']:
    if 'row' in component:
        for item in component['row'].get('row_composer', []):
            if 'content_divider_block' in item:
                fr_divider = item['content_divider_block']['content_divider_ref'][0]['entry']
                break
        if fr_divider:
            break

print(f'English divider title: {eng_divider.get("title")}')
print(f'French divider title: {fr_divider.get("title")}')
print(f'English has color: {"color" in eng_divider}')
print(f'French has color: {"color" in fr_divider}')
print(f'English color value: {eng_divider.get("color", {}).get("hex") if eng_divider.get("color") else "N/A"}')
print(f'French color value: {fr_divider.get("color")}')
print()

print('=== APPLYING MAPPING ===\n')

result = localizer._replace_content(eng_divider, fr_divider)

print(f'Result title: {result.get("title")}')
print(f'Result direction: {result.get("direction")}')
print(f'Result has color: {"color" in result}')
print(f'Result color value: {result.get("color", {}).get("hex") if result.get("color") else "N/A"}')
print(f'Result has platform_config_block: {"platform_config_block" in result}')
print(f'Result platform_config_block: {result.get("platform_config_block")}')
print()

# Test the last divider with color: null
print('=== TESTING DIVIDER WITH color: null ===\n')

fr_divider_null = None
for component in fr_data['entry']['page_composer']:
    if 'column' in component:
        for item in component['column'].get('left_column_composer', []):
            if 'content_divider_block' in item:
                entry = item['content_divider_block']['content_divider_ref'][0]['entry']
                if entry.get('title') == 'Content Divider 14 - 1772733882143':
                    fr_divider_null = entry
                    break
        if fr_divider_null:
            break

eng_divider_for_null = eng_data['entry']['page_composer'][4]['column']['left_column_composer'][8]['content_divider_block']['content_divider_ref'][0]['entry']

print(f'English title: {eng_divider_for_null.get("title")}')
print(f'French title: {fr_divider_null.get("title")}')
print(f'French color value: {fr_divider_null.get("color")} (should be None/null)')
print()

print('=== APPLYING MAPPING TO NULL COLOR DIVIDER ===\n')

result_null = localizer._replace_content(eng_divider_for_null, fr_divider_null)

print(f'Result title: {result_null.get("title")}')
print(f'Result color: {result_null.get("color")}')
print(f'Result color hex: {result_null.get("color", {}).get("hex") if result_null.get("color") else "MISSING"}')
print()

if result_null.get('color') and result_null['color'].get('hex'):
    print('✅ SUCCESS: Color properly mapped from English!')
else:
    print('❌ FAIL: Color is still missing or null!')
