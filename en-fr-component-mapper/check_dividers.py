import json

# Load both JSON files
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find all content_divider components
def find_content_dividers(page_composer, label):
    dividers = []
    for i, component in enumerate(page_composer):
        if 'row' in component:
            for j, item in enumerate(component['row'].get('row_composer', [])):
                if 'content_divider_block' in item:
                    divider_entry = item['content_divider_block']['content_divider_ref'][0]['entry']
                    dividers.append({
                        'position': f'row[{i}].row_composer[{j}]',
                        'title': divider_entry.get('title', 'N/A'),
                        'direction': divider_entry.get('direction', 'N/A'),
                        'color': divider_entry.get('color', 'MISSING'),
                        'locale': divider_entry.get('locale', 'N/A'),
                        'full_entry': divider_entry
                    })
        elif 'column' in component:
            for col_type in ['left_column_composer', 'right_column_composer']:
                for j, item in enumerate(component['column'].get(col_type, [])):
                    if 'content_divider_block' in item:
                        divider_entry = item['content_divider_block']['content_divider_ref'][0]['entry']
                        dividers.append({
                            'position': f'column.{col_type}[{j}]',
                            'title': divider_entry.get('title', 'N/A'),
                            'direction': divider_entry.get('direction', 'N/A'),
                            'color': divider_entry.get('color', 'MISSING'),
                            'locale': divider_entry.get('locale', 'N/A'),
                            'full_entry': divider_entry
                        })
    
    return dividers

eng_dividers = find_content_dividers(eng['entry']['page_composer'], 'English')
fr_dividers = find_content_dividers(fr['entry']['page_composer'], 'French')

print('=== CONTENT_DIVIDER COMPARISON ===\n')
print(f'English content_dividers: {len(eng_dividers)}')
print(f'French content_dividers: {len(fr_dividers)}')
print()

print('=== ENGLISH DIVIDERS ===')
for i, div in enumerate(eng_dividers):
    color_status = 'MISSING' if div['color'] == 'MISSING' else ('NULL' if div['color'] is None else 'PRESENT')
    print(f"{i+1}. Position: {div['position']}")
    print(f"   Title: {div['title']}")
    print(f"   Direction: {div['direction']}")
    print(f"   Color: {color_status}")
    print(f"   Locale: {div['locale']}")
    if div['color'] not in ['MISSING', None]:
        print(f"   Color value: {div['color'].get('hex', 'N/A')}")
    print()

print('=== FRENCH DIVIDERS ===')
for i, div in enumerate(fr_dividers):
    color_status = 'MISSING' if div['color'] == 'MISSING' else ('NULL' if div['color'] is None else 'PRESENT')
    print(f"{i+1}. Position: {div['position']}")
    print(f"   Title: {div['title']}")
    print(f"   Direction: {div['direction']}")
    print(f"   Color: {color_status}")
    print(f"   Locale: {div['locale']}")
    if div['color'] not in ['MISSING', None]:
        print(f"   Color value: {div['color'].get('hex', 'N/A')}")
    print()

print('=== ISSUES FOUND ===')
for i, div in enumerate(fr_dividers):
    if div['color'] is None:
        print(f"⚠️  French divider #{i+1} ({div['title']}) has COLOR = NULL")
        print(f"   This will cause 'Something went wrong' error!")
        print(f"   Expected: color object with hex value")
        print()
    if 'platform_config_block' not in div['full_entry']:
        print(f"⚠️  French divider #{i+1} ({div['title']}) missing platform_config_block")
        print()
    elif not div['full_entry']['platform_config_block']:
        print(f"⚠️  French divider #{i+1} ({div['title']}) has EMPTY platform_config_block")
        print()
