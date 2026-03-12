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

# Check first ad_set_costco
eng_entry = eng_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']
fr_entry = fr_ad_sets[0]['row']['row_composer'][0]['ad_set_costco_block']['ad_set_costco_ref'][0]['entry']

print('=== FIRST AD_SET_COSTCO ===')
print(f'English: {eng_entry["title"]}')
print(f'French: {fr_entry["title"]}')
print()

for i in range(len(eng_entry['ad_content'])):
    eng_ad = eng_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    fr_ad = fr_entry['ad_content'][i]['ad_builder_block']['ad_builder_ref'][0]['entry']
    
    print(f'\n--- Ad Builder #{i+1} ---')
    print(f'English title: {eng_ad["title"]}')
    print(f'French title: {fr_ad["title"]}')
    
    # Get text_content markdown_text
    if eng_ad.get('text_content') and len(eng_ad['text_content']) > 0:
        eng_text = eng_ad['text_content'][0].get('markdown_text', {}).get('markdown_text', 'N/A')
        print(f'English text: {eng_text}')
    else:
        print('English text: [NO TEXT_CONTENT]')
    
    if fr_ad.get('text_content') and len(fr_ad['text_content']) > 0:
        fr_text = fr_ad['text_content'][0].get('markdown_text', {}).get('markdown_text', 'N/A')
        print(f'French text: {fr_text}')
    else:
        print('French text: [NO TEXT_CONTENT]')
