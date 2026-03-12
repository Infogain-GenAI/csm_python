import json
import sys
sys.path.append('.')

from simple_localizer_v2 import SimpleLocalizerV2

# Load test data
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng_data = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr_data = json.load(f)

# Create localizer (dummy environment)
localizer = SimpleLocalizerV2(environment={'uid': 'test'})

# Find first ad_set_costco in both
eng_page_composer = eng_data['entry']['page_composer']
fr_page_composer = fr_data['entry']['page_composer']

eng_ad_set = None
fr_ad_set = None

for component in eng_page_composer:
    if 'row' in component:
        for item in component['row'].get('row_composer', []):
            if 'ad_set_costco_block' in item:
                eng_ad_set = item['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
                break
        if eng_ad_set:
            break

for component in fr_page_composer:
    if 'row' in component:
        for item in component['row'].get('row_composer', []):
            if 'ad_set_costco_block' in item:
                fr_ad_set = item['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
                break
        if fr_ad_set:
            break

print("=== TESTING AD_BUILDER URL MATCHING ===\n")
print(f"English ad_content items: {len(eng_ad_set['ad_content'])}")
print(f"French ad_content items: {len(fr_ad_set['ad_content'])}")
print()

# Test URL extraction
for i, item in enumerate(eng_ad_set['ad_content']):
    url = localizer._get_ad_builder_url(item)
    print(f"English [{i}]: {url}")

print()

for i, item in enumerate(fr_ad_set['ad_content']):
    url = localizer._get_ad_builder_url(item)
    print(f"French [{i}]: {url}")

print("\n=== TESTING MATCHING FUNCTION ===\n")

matched = localizer._match_arrays_by_url(eng_ad_set['ad_content'], fr_ad_set['ad_content'])

for i, (eng_item, fr_item) in enumerate(matched):
    eng_url = localizer._get_ad_builder_url(eng_item)
    if fr_item:
        fr_url = localizer._get_ad_builder_url(fr_item)
        eng_banner = eng_item['ad_builder_block']['ad_builder_ref'][0]['entry']['top_and_bottom_text_banner'][0]['add_text_banner']['text']
        fr_banner = fr_item['ad_builder_block']['ad_builder_ref'][0]['entry']['top_and_bottom_text_banner'][0]['add_text_banner']['text']
        print(f"[{i}] {eng_url}")
        print(f"    English Banner: {eng_banner}")
        print(f"    French Banner:  {fr_banner}")
        print(f"    ✅ MATCHED")
    else:
        print(f"[{i}] {eng_url}")
        print(f"    ⚠️  NO MATCH")
    print()
