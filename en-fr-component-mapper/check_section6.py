import json

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find Droits humains text_builder
for component in fr['entry']['page_composer']:
    if 'column' in component:
        for item in component['column'].get('left_column_composer', []):
            if 'text_builder_block' in item:
                entry = item['text_builder_block']['text_builder_ref'][0]['entry']
                if 'Droits humains' in entry.get('title', ''):
                    sections = entry['multiple_text_section_group']
                    
                    # Get Section 6 (index 5)
                    section_6 = sections[5]
                    content = section_6.get('text_section_content', [])
                    
                    print(f'French Section 6 has {len(content)} items\n')
                    
                    for i, item in enumerate(content):
                        text = item.get('markdown_text', '')
                        print(f'Item {i+1}:')
                        print(f'Length: {len(text)} characters')
                        
                        # Split by paragraphs
                        paragraphs = text.split('\n\n')
                        print(f'Paragraphs: {len(paragraphs)}')
                        
                        for j, para in enumerate(paragraphs):
                            if para.strip():
                                print(f'  Para {j+1}: {para.strip()[:100]}...')
                        print()
                    
                    break
