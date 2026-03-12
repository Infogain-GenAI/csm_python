import json

with open('input/english.json', 'r', encoding='utf-8') as f:
    eng = json.load(f)

# Find the Human rights text_builder
eng_builder = None
for component in eng['entry']['page_composer']:
    if 'column' in component:
        for item in component['column'].get('left_column_composer', []):
            if 'text_builder_block' in item:
                entry = item['text_builder_block']['text_builder_ref'][0]['entry']
                if 'Human rights' in entry.get('title', ''):
                    eng_builder = entry
                    break
        if eng_builder:
            break

if eng_builder:
    sections = eng_builder['multiple_text_section_group']
    
    print('=== ENGLISH SECTION 7 (MISSING IN FRENCH) ===\n')
    
    if len(sections) >= 7:
        section_7 = sections[6]  # 0-indexed
        content = section_7.get('text_section_content', [])
        
        for i, text_item in enumerate(content):
            text = text_item.get('markdown_text', 'N/A')
            print(f'Text item {i+1}:')
            print(text)
            print()
