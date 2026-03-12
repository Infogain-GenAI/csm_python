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

# Get first ad_set
eng_entry = eng_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
fr_entry = fr_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']

print('=== FIRST AD_SET_COSTCO - TEXT BANNERS ===\n')

for i in range(len(eng_entry['ad_content'])):
    eng_ad = eng_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    fr_ad = fr_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    
    print(f'--- Ad Builder #{i+1} ---')
    
    # Check top_and_bottom_text_banner
    eng_banner = eng_ad.get('top_and_bottom_text_banner', [])
    fr_banner = fr_ad.get('top_and_bottom_text_banner', [])
    
    print(f'English banners: {len(eng_banner)}')
    if eng_banner:
        for banner in eng_banner:
            if 'add_text_banner' in banner:
                text = banner['add_text_banner'].get('text', '')
                banner_type = banner['add_text_banner'].get('text_banner_type', '')
                print(f'  [{banner_type}] "{text}"')
    
    print(f'French banners: {len(fr_banner)}')
    if fr_banner:
        for banner in fr_banner:
            if 'add_text_banner' in banner:
                text = banner['add_text_banner'].get('text', '')
                banner_type = banner['add_text_banner'].get('text_banner_type', '')
                print(f'  [{banner_type}] "{text}"')
    
    print()
