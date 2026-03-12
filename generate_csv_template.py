#!/usr/bin/env python3
"""
CSV Template Generator for Batch JSON Processor

Quickly generate CSV templates with different scenarios
Usage: python generate_csv_template.py [template_type]
"""

import sys
import csv
from datetime import datetime


def create_basic_template(filename='template_basic.csv'):
    """Create a basic template with sample UIDs"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        writer.writerow(['blt_your_uid_here_1', 'ad_builder', 'en-ca', 'false'])
        writer.writerow(['blt_your_uid_here_2', 'text_builder', 'fr-ca', 'true'])
        writer.writerow(['blt_your_uid_here_3', 'link_list_simple', 'fr-ca', 'false'])
    print(f'✅ Created: {filename}')


def create_english_only_template(filename='template_english_only.csv'):
    """Create template for English content only"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        for i in range(1, 6):
            writer.writerow([f'blt_english_uid_{i}', 'ad_builder', 'en-ca', 'false'])
    print(f'✅ Created: {filename}')


def create_french_only_template(filename='template_french_only.csv'):
    """Create template for French content only"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        for i in range(1, 6):
            writer.writerow([f'blt_french_uid_{i}', 'text_builder', 'fr-ca', 'false'])
    print(f'✅ Created: {filename}')


def create_mapped_only_template(filename='template_mapped_only.csv'):
    """Create template for mapped outputs only"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        for i in range(1, 6):
            writer.writerow([f'blt_mapped_uid_{i}', 'ad_builder', 'fr-ca', 'true'])
    print(f'✅ Created: {filename}')


def create_mixed_template(filename='template_mixed.csv'):
    """Create template with mixed scenarios"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        
        # English inputs
        writer.writerow(['blt_en_input_1', 'ad_builder', 'en-ca', 'false'])
        writer.writerow(['blt_en_input_2', 'text_builder', 'en-ca', 'false'])
        
        # Mapped outputs
        writer.writerow(['blt_mapped_1', 'ad_builder', 'fr-ca', 'true'])
        writer.writerow(['blt_mapped_2', 'link_list_simple', 'fr-ca', 'true'])
        
        # French inputs
        writer.writerow(['blt_fr_input_1', 'ad_builder', 'fr-ca', 'false'])
        writer.writerow(['blt_fr_input_2', 'text_builder', 'fr-ca', 'false'])
    
    print(f'✅ Created: {filename}')


def create_large_batch_template(filename='template_large_batch.csv', count=50):
    """Create template for large batch processing"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
        
        component_types = ['ad_builder', 'text_builder', 'link_list_simple']
        locales = ['en-ca', 'fr-ca']
        mappings = ['true', 'false']
        
        for i in range(1, count + 1):
            component = component_types[i % len(component_types)]
            locale = locales[i % len(locales)]
            mapping = mappings[i % len(mappings)]
            writer.writerow([f'blt_uid_{i:03d}', component, locale, mapping])
    
    print(f'✅ Created: {filename} with {count} entries')


def create_empty_template(filename='template_empty.csv'):
    """Create empty template with headers only"""
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['uid', 'component_type', 'locale', 'mapping'])
    print(f'✅ Created: {filename} (headers only)')


def print_help():
    """Print help message"""
    print('CSV Template Generator for Batch JSON Processor')
    print('=' * 60)
    print('')
    print('Usage: python generate_csv_template.py [template_type]')
    print('')
    print('Template Types:')
    print('  basic          - Basic template with 3 sample entries (default)')
    print('  english        - English content only (5 entries)')
    print('  french         - French content only (5 entries)')
    print('  mapped         - Mapped outputs only (5 entries)')
    print('  mixed          - Mixed scenarios (6 entries)')
    print('  large          - Large batch template (50 entries)')
    print('  empty          - Empty template (headers only)')
    print('  all            - Generate all templates')
    print('')
    print('Examples:')
    print('  python generate_csv_template.py')
    print('  python generate_csv_template.py basic')
    print('  python generate_csv_template.py mixed')
    print('  python generate_csv_template.py all')
    print('')
    print('After generating, edit the CSV file to add your actual UIDs!')


def main():
    """Main function"""
    args = sys.argv[1:]
    
    if '--help' in args or '-h' in args:
        print_help()
        sys.exit(0)
    
    template_type = args[0] if len(args) > 0 else 'basic'
    
    print('\n🔧 CSV Template Generator')
    print(f'Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
    
    if template_type == 'all':
        create_basic_template()
        create_english_only_template()
        create_french_only_template()
        create_mapped_only_template()
        create_mixed_template()
        create_large_batch_template()
        create_empty_template()
        print('\n✅ All templates created!')
    elif template_type == 'basic':
        create_basic_template()
    elif template_type == 'english':
        create_english_only_template()
    elif template_type == 'french':
        create_french_only_template()
    elif template_type == 'mapped':
        create_mapped_only_template()
    elif template_type == 'mixed':
        create_mixed_template()
    elif template_type == 'large':
        create_large_batch_template()
    elif template_type == 'empty':
        create_empty_template()
    else:
        print(f'❌ Unknown template type: {template_type}')
        print('Run with --help to see available options')
        sys.exit(1)
    
    print('\n📝 Next Steps:')
    print('1. Open the generated CSV file')
    print('2. Replace placeholder UIDs with actual UIDs from Contentstack')
    print('3. Adjust component_type, locale, and mapping as needed')
    print('4. Run: python batch_json_processor.py <csv-file> <environment>')
    print('')


if __name__ == '__main__':
    main()
