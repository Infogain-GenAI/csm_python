import json

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find the Droits humains text_builder
fr_builder = None
for component in fr['entry']['page_composer']:
    if 'column' in component:
        for item in component['column'].get('left_column_composer', []):
            if 'text_builder_block' in item:
                entry = item['text_builder_block']['text_builder_ref'][0]['entry']
                if 'Droits humains' in entry.get('title', ''):
                    fr_builder = entry
                    break
        if fr_builder:
            break

if fr_builder:
    sections = fr_builder['multiple_text_section_group']
    
    print('=== ALL FRENCH TEXT CONTENT ===\n')
    
    for i, section in enumerate(sections):
        print(f'--- Section {i+1} ---')
        content = section.get('text_section_content', [])
        
        for j, text_item in enumerate(content):
            text = text_item.get('markdown_text', 'N/A')
            print(f'Item {j+1}:')
            if len(text) > 200:
                print(text[:200] + '...')
            else:
                print(text)
            print()
