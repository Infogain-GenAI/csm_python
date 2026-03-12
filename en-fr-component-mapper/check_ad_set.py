import json

# Load both JSON files
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find ad_set_costco components
eng_ad_sets = [c for c in eng['entry']['page_composer'] 
               if 'row' in c and c['row']['row_composer'] 
               and 'ad_set_costco_block' in c['row']['row_composer'][0]]

fr_ad_sets = [c for c in fr['entry']['page_composer'] 
              if 'row' in c and c['row']['row_composer'] 
              and 'ad_set_costco_block' in c['row']['row_composer'][0]]

print(f'English ad_set_costco count: {len(eng_ad_sets)}')
print(f'French ad_set_costco count: {len(fr_ad_sets)}')

for i, (eng_set, fr_set) in enumerate(zip(eng_ad_sets, fr_ad_sets)):
    eng_entry = eng_set['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
    fr_entry = fr_set['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
    
    eng_ad_count = len(eng_entry['ad_content'])
    fr_ad_count = len(fr_entry['ad_content'])
    
    print(f'\n=== AD_SET {i+1} ===')
    print(f'English title: {eng_entry["title"]}')
    print(f'French title: {fr_entry["title"]}')
    print(f'English ad_content items: {eng_ad_count}')
    print(f'French ad_content items: {fr_ad_count}')
    
    if eng_ad_count != fr_ad_count:
        print(f'⚠️  MISMATCH! English has {eng_ad_count}, French has {fr_ad_count}')
