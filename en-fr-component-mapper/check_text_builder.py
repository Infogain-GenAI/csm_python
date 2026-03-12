import json

# Load both JSON files
with open('input/english.json', 'r', encoding='utf-8') as f:
    eng = json.load(f)

with open('input/french.json', 'r', encoding='utf-8') as f:
    fr = json.load(f)

# Find all text_builder components
def find_text_builders(page_composer, label):
    builders = []
    for i, component in enumerate(page_composer):
        if 'row' in component:
            for j, item in enumerate(component['row'].get('row_composer', [])):
                if 'text_builder_block' in item:
                    entry = item['text_builder_block']['text_builder_ref'][0]['entry']
                    builders.append({
                        'position': f'row[{i}].row_composer[{j}]',
                        'title': entry.get('title', 'N/A'),
                        'sections': len(entry.get('multiple_text_section_group', [])),
                        'entry': entry
                    })
        elif 'column' in component:
            for col_type in ['left_column_composer', 'right_column_composer']:
                for j, item in enumerate(component['column'].get(col_type, [])):
                    if 'text_builder_block' in item:
                        entry = item['text_builder_block']['text_builder_ref'][0]['entry']
                        builders.append({
                            'position': f'column.{col_type}[{j}]',
                            'title': entry.get('title', 'N/A'),
                            'sections': len(entry.get('multiple_text_section_group', [])),
                            'entry': entry
                        })
    
    return builders

eng_builders = find_text_builders(eng['entry']['page_composer'], 'English')
fr_builders = find_text_builders(fr['entry']['page_composer'], 'French')

print('=== TEXT_BUILDER COMPARISON ===\n')
print(f'English text_builders: {len(eng_builders)}')
print(f'French text_builders: {len(fr_builders)}')
print()

print('=== ENGLISH TEXT_BUILDERS ===')
for i, builder in enumerate(eng_builders):
    print(f"{i+1}. Position: {builder['position']}")
    print(f"   Title: {builder['title']}")
    print(f"   Sections: {builder['sections']}")
    print()

print('=== FRENCH TEXT_BUILDERS ===')
for i, builder in enumerate(fr_builders):
    print(f"{i+1}. Position: {builder['position']}")
    print(f"   Title: {builder['title']}")
    print(f"   Sections: {builder['sections']}")
    print()

# Find the main content text_builder in column
print('=== MAIN CONTENT TEXT_BUILDER COMPARISON ===\n')

eng_main = None
fr_main = None

for builder in eng_builders:
    if 'Human rights' in builder['title']:
        eng_main = builder
        break

for builder in fr_builders:
    if 'Droits humains' in builder['title']:
        fr_main = builder
        break

if eng_main and fr_main:
    print(f'English: {eng_main["title"]}')
    print(f'  Sections: {eng_main["sections"]}')
    
    print(f'\nFrench: {fr_main["title"]}')
    print(f'  Sections: {fr_main["sections"]}')
    
    print('\n=== DETAILED SECTION COMPARISON ===\n')
    
    eng_sections = eng_main['entry']['multiple_text_section_group']
    fr_sections = fr_main['entry']['multiple_text_section_group']
    
    max_sections = max(len(eng_sections), len(fr_sections))
    
    for i in range(max_sections):
        print(f'--- Section {i+1} ---')
        
        if i < len(eng_sections):
            eng_content = eng_sections[i].get('text_section_content', [])
            print(f'English: {len(eng_content)} text items')
            for j, text_item in enumerate(eng_content):
                text = text_item.get('markdown_text', 'N/A')
                if isinstance(text, str):
                    preview = text[:80].replace('\n', ' ')
                    print(f'  [{j}] {preview}...')
        else:
            print(f'English: MISSING')
        
        if i < len(fr_sections):
            fr_content = fr_sections[i].get('text_section_content', [])
            print(f'French: {len(fr_content)} text items')
            for j, text_item in enumerate(fr_content):
                text = text_item.get('markdown_text', 'N/A')
                if isinstance(text, str):
                    preview = text[:80].replace('\n', ' ')
                    print(f'  [{j}] {preview}...')
        else:
            print(f'French: MISSING')
        
        print()
    
    # Check if English has more sections
    if len(eng_sections) > len(fr_sections):
        print(f'⚠️  English has {len(eng_sections)} sections, French has {len(fr_sections)}')
        print(f'   Missing {len(eng_sections) - len(fr_sections)} sections in French!')
