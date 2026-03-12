import json

# Load both JSON files
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find first ad_set_costco
eng_ad_sets = [c for c in eng['entry']['page_composer'] 
               if 'row' in c and c['row']['row_composer'] 
               and 'ad_set_costco_block' in c['row']['row_composer'][0]]

fr_ad_sets = [c for c in fr['entry']['page_composer'] 
              if 'row' in c and c['row']['row_composer'] 
              and 'ad_set_costco_block' in c['row']['row_composer'][0]]

# Get first ad_builder from each
eng_entry = eng_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
fr_entry = fr_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']

eng_ad = eng_entry['ad_content'][0]['ad_builder_block']['ad_builder_ref'][0]['entry']
fr_ad = fr_entry['ad_content'][0]['ad_builder_block']['ad_builder_ref'][0]['entry']

print('=== COMPARING FIRST AD_BUILDER KEYS ===\n')
print(f'English keys: {sorted(eng_ad.keys())}')
print(f'\nFrench keys: {sorted(fr_ad.keys())}')

eng_only = set(eng_ad.keys()) - set(fr_ad.keys())
fr_only = set(fr_ad.keys()) - set(eng_ad.keys())

if eng_only:
    print(f'\n⚠️  Keys ONLY in English: {eng_only}')
if fr_only:
    print(f'\n✅ Keys ONLY in French: {fr_only}')

# Check banner structure specifically
print('\n=== BANNER STRUCTURE ===')
print(f'\nEnglish has top_and_bottom_text_banner: {"top_and_bottom_text_banner" in eng_ad}')
print(f'French has top_and_bottom_text_banner: {"top_and_bottom_text_banner" in fr_ad}')

if 'top_and_bottom_text_banner' in eng_ad and 'top_and_bottom_text_banner' in fr_ad:
    eng_banner = eng_ad['top_and_bottom_text_banner'][0]
    fr_banner = fr_ad['top_and_bottom_text_banner'][0]
    
    print(f'\nEnglish banner keys: {sorted(eng_banner.keys())}')
    print(f'French banner keys: {sorted(fr_banner.keys())}')
    
    eng_text_banner_keys = sorted(eng_banner['add_text_banner'].keys())
    fr_text_banner_keys = sorted(fr_banner['add_text_banner'].keys())
    
    print(f'\nEnglish add_text_banner keys: {eng_text_banner_keys}')
    print(f'French add_text_banner keys: {fr_text_banner_keys}')
    
    eng_banner_only = set(eng_text_banner_keys) - set(fr_text_banner_keys)
    fr_banner_only = set(fr_text_banner_keys) - set(eng_text_banner_keys)
    
    if eng_banner_only:
        print(f'\n⚠️  Keys ONLY in English banner: {eng_banner_only}')
    if fr_banner_only:
        print(f'\n✅ Keys ONLY in French banner: {fr_banner_only}')
