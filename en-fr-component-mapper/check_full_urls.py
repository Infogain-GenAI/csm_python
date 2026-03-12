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

eng_entry = eng_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
fr_entry = fr_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']

print('=== FULL URLS ===\n')

for i in range(4):
    eng_ad = eng_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    fr_ad = fr_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    
    eng_url = eng_ad['costco_url'].get('url', '')
    fr_url = fr_ad['costco_url'].get('url', '')
    
    eng_banner = eng_ad['top_and_bottom_text_banner'][0]['add_text_banner']['text']
    fr_banner = fr_ad['top_and_bottom_text_banner'][0]['add_text_banner']['text']
    
    print(f'Position {i}:')
    print(f'  English URL: {eng_url}')
    print(f'  French URL:  {fr_url}')
    print(f'  English Banner: "{eng_banner}"')
    print(f'  French Banner:  "{fr_banner}"')
    print(f'  Match: {eng_url == fr_url}')
    print()
