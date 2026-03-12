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

print('=== CHECKING AD_BUILDER ORDER ===\n')

for i in range(4):
    eng_ad = eng_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    fr_ad = fr_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    
    # Get identifying info
    eng_url = eng_ad['costco_url'].get('url', '')
    fr_url = fr_ad['costco_url'].get('url', '')
    
    eng_banner = eng_ad['top_and_bottom_text_banner'][0]['add_text_banner']['text']
    fr_banner = fr_ad['top_and_bottom_text_banner'][0]['add_text_banner']['text']
    
    eng_text = eng_ad['text_content'][0]['markdown_text']['markdown_text']
    fr_text = fr_ad['text_content'][0]['markdown_text']['markdown_text']
    
    print(f'Position {i}:')
    print(f'  English: URL={eng_url.split("/")[-1][:30]}... Banner="{eng_banner}" Text="{eng_text}"')
    print(f'  French:  URL={fr_url.split("/")[-1][:30]}... Banner="{fr_banner}" Text="{fr_text}"')
    print(f'  ✅ URLs match: {eng_url == fr_url}')
    print()
