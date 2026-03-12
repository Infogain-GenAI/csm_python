import json

# Load test data
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng_data = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr_data = json.load(f)

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

def get_ad_builder_url(ad_item):
    """Extract URL from ad_builder item"""
    try:
        if 'ad_builder_block' in ad_item:
            ref = ad_item['ad_builder_block'].get('ad_builder_ref', [])
            if ref and len(ref) > 0:
                entry = ref[0].get('entry', {})
                url = entry.get('costco_url', {}).get('url', '')
                # Normalize URL
                if url.startswith('https://www.costco.ca'):
                    url = url.replace('https://www.costco.ca', '')
                return url
    except:
        pass
    return None

print("=== EXTRACTING URLs ===\n")

eng_urls = []
fr_urls = []

for i, item in enumerate(eng_ad_set['ad_content']):
    url = get_ad_builder_url(item)
    eng_urls.append(url)
    print(f"English [{i}]: {url}")

print()

for i, item in enumerate(fr_ad_set['ad_content']):
    url = get_ad_builder_url(item)
    fr_urls.append(url)
    print(f"French [{i}]: {url}")

print("\n=== BUILDING FRENCH URL MAP ===\n")

fr_by_url = {}
for i, item in enumerate(fr_ad_set['ad_content']):
    url = get_ad_builder_url(item)
    if url:
        fr_by_url[url] = (i, item)
        print(f"{url} → French position {i}")

print("\n=== MATCHING ENGLISH TO FRENCH ===\n")

for i, eng_item in enumerate(eng_ad_set['ad_content']):
    eng_url = get_ad_builder_url(eng_item)
    eng_banner = eng_item['ad_builder_block']['ad_builder_ref'][0]['entry']['top_and_bottom_text_banner'][0]['add_text_banner']['text']
    
    if eng_url in fr_by_url:
        fr_pos, fr_item = fr_by_url[eng_url]
        fr_banner = fr_item['ad_builder_block']['ad_builder_ref'][0]['entry']['top_and_bottom_text_banner'][0]['add_text_banner']['text']
        print(f"English [{i}] '{eng_banner}' → French [{fr_pos}] '{fr_banner}'")
        print(f"  URL: {eng_url}")
        print(f"  ✅ MATCHED")
    else:
        print(f"English [{i}] '{eng_banner}'")
        print(f"  URL: {eng_url}")
        print(f"  ⚠️  NO FRENCH MATCH")
    print()
