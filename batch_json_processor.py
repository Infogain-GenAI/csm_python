#!/usr/bin/env python3
"""
Batch JSON Processor
Automates fetching entries from Contentstack, cleaning them, and organizing output files

Usage: python batch_json_processor.py <csv-file> <environment>

CSV Format:
uid,component_type,locale,mapping
blt123abc,ad_builder,en-ca,false
blt456def,text_builder,en-ca,true
blt789ghi,link_list_simple,fr-ca,false
"""

import sys
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from lib.contentstack_api import ContentstackAPI
from lib.json_cleanup import JSONCleanup


class BatchJSONProcessor:
    def __init__(self, environment: str):
        """
        Initialize Batch JSON Processor
        
        Args:
            environment: Environment to use (dev, USBC, USBD, CABC, CABD)
        """
        self.environment = environment
        self.output_base_dir = Path('output_batch')
        
        # Load environment variables
        load_dotenv()
        
        # Validate and get environment configuration
        env_config = self._get_environment_config(environment)
        self._validate_environment_variables(environment)
        
        # Initialize Contentstack API
        self.contentstack_api = ContentstackAPI(
            env_config['api_key'],
            env_config['management_token'],
            env_config['base_url'],
            env_config.get('auth_token'),
            env_config.get('environment_uid'),
            environment
        )
        
        # Counter for file naming
        self.counters = {}
        
        print(f'✅ Batch processor initialized for environment: {environment}')
    
    def _get_environment_config(self, environment: str) -> dict:
        """Get environment-specific configuration"""
        return {
            'api_key': os.getenv(f'CONTENTSTACK_API_KEY_{environment}'),
            'management_token': os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{environment}'),
            'base_url': os.getenv(f'CONTENTSTACK_BASE_URL_{environment}'),
            'environment_uid': os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{environment}'),
            'auth_token': os.getenv('CONTENTSTACK_AUTH_TOKEN')
        }
    
    def _validate_environment_variables(self, environment: str):
        """Validate required environment variables"""
        required_vars = [
            f'CONTENTSTACK_API_KEY_{environment}',
            f'CONTENTSTACK_MANAGEMENT_TOKEN_{environment}',
            f'CONTENTSTACK_BASE_URL_{environment}',
            f'CONTENTSTACK_ENVIRONMENT_UID_{environment}'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise Exception(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def _get_counter_key(self, component_type: str, locale: str, mapping: bool) -> str:
        """Get unique counter key for file naming"""
        return f"{component_type}_{locale}_{mapping}"
    
    def _get_next_counter(self, component_type: str, locale: str, mapping: bool) -> int:
        """Get next counter value for file naming"""
        key = self._get_counter_key(component_type, locale, mapping)
        if key not in self.counters:
            self.counters[key] = 0
        self.counters[key] += 1
        return self.counters[key]
    
    def _get_output_filename(self, component_type: str, locale: str, mapping: bool) -> str:
        """
        Generate output filename based on locale and mapping
        
        Args:
            component_type: Component type name
            locale: Locale (en-ca or fr-ca)
            mapping: Whether mapping is enabled (true/false)
            
        Returns:
            Filename for the output
        """
        counter = self._get_next_counter(component_type, locale, mapping)
        
        # Determine file name based on conditions
        if locale == 'en-ca' and not mapping:
            return f'english_input_{counter}.json'
        elif locale == 'fr-ca' and mapping:
            return f'mapped_output_{counter}.json'
        elif locale == 'fr-ca' and not mapping:
            return f'french_input_{counter}.json'
        else:
            # This should not happen based on requirements, but handle gracefully
            return f'unknown_{locale}_{mapping}_{counter}.json'
    
    def _ensure_output_directory(self, component_type: str) -> Path:
        """
        Ensure output directory exists for component type
        
        Args:
            component_type: Component type name
            
        Returns:
            Path to the output directory
        """
        output_dir = self.output_base_dir / component_type
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def process_csv(self, csv_file: str):
        """
        Process CSV file with batch entries
        
        Args:
            csv_file: Path to CSV file
        """
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        print(f'\n📄 Reading CSV file: {csv_file}')
        
        # Read CSV file
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        total_rows = len(rows)
        print(f'📊 Found {total_rows} entries to process\n')
        
        # Process each row
        success_count = 0
        error_count = 0
        
        for idx, row in enumerate(rows, 1):
            try:
                uid = row['uid'].strip()
                component_type = row['component_type'].strip()
                locale = row['locale'].strip().lower()
                mapping = row['mapping'].strip().lower() == 'true'
                
                print(f'[{idx}/{total_rows}] Processing:')
                print(f'  - UID: {uid}')
                print(f'  - Component Type: {component_type}')
                print(f'  - Locale: {locale}')
                print(f'  - Mapping: {mapping}')
                
                # Validate locale
                if locale not in ['en-ca', 'fr-ca']:
                    print(f'  ❌ Invalid locale: {locale}. Skipping...\n')
                    error_count += 1
                    continue
                
                # Process the entry
                self._process_entry(uid, component_type, locale, mapping)
                
                success_count += 1
                print(f'  ✅ Successfully processed!\n')
                
            except Exception as error:
                error_count += 1
                print(f'  ❌ Error processing entry: {str(error)}\n')
                continue
        
        # Summary
        print('\n' + '='*60)
        print('BATCH PROCESSING SUMMARY')
        print('='*60)
        print(f'Total Entries: {total_rows}')
        print(f'Successful: {success_count}')
        print(f'Failed: {error_count}')
        print(f'Output Directory: {self.output_base_dir.absolute()}')
        print('='*60 + '\n')
    
    def _process_entry(self, uid: str, component_type: str, locale: str, mapping: bool):
        """
        Process a single entry: fetch, clean, and save
        
        Args:
            uid: Entry UID
            component_type: Component type
            locale: Locale (en-ca or fr-ca)
            mapping: Whether mapping is enabled
        """
        # Fetch entry from Contentstack
        print(f'  📥 Fetching entry from Contentstack...')
        response = self.contentstack_api.get_entry(component_type, uid, locale)
        
        # Extract entry data
        entry_data = response.get('entry', {})
        if not entry_data:
            raise Exception('No entry data returned from Contentstack')
        
        # Clean the JSON data
        print(f'  🧹 Cleaning JSON data...')
        cleanup_locale = locale if locale == 'fr-ca' else None  # Only set locale for French
        cleanup = JSONCleanup(self.contentstack_api, locale=cleanup_locale)
        cleaned_data = cleanup.cleanup_json({'entry': entry_data})
        
        # Determine output path
        output_dir = self._ensure_output_directory(component_type)
        output_filename = self._get_output_filename(component_type, locale, mapping)
        output_path = output_dir / output_filename
        
        # Write cleaned data to output file
        print(f'  💾 Writing to: {output_path}')
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)


def main():
    """Main CLI function"""
    args = sys.argv[1:]
    
    if len(args) == 0 or '--help' in args or '-h' in args:
        print('Batch JSON Processor - Automated Entry Processing')
        print('=' * 60)
        print('')
        print('Usage: python batch_json_processor.py <csv-file> <environment>')
        print('')
        print('Arguments:')
        print('  csv-file      Path to CSV file with entries to process')
        print('  environment   Environment to use (dev, USBC, USBD, CABC, CABD)')
        print('')
        print('CSV Format:')
        print('  uid,component_type,locale,mapping')
        print('  blt123abc,ad_builder,en-ca,false')
        print('  blt456def,text_builder,fr-ca,true')
        print('  blt789ghi,link_list_simple,fr-ca,false')
        print('')
        print('Output File Naming:')
        print('  - locale=en-ca, mapping=false → english_input_N.json')
        print('  - locale=fr-ca, mapping=true  → mapped_output_N.json')
        print('  - locale=fr-ca, mapping=false → french_input_N.json')
        print('')
        print('Output Structure:')
        print('  output_batch/')
        print('    ├── ad_builder/')
        print('    │   ├── english_input_1.json')
        print('    │   ├── mapped_output_1.json')
        print('    │   └── french_input_1.json')
        print('    ├── text_builder/')
        print('    │   └── ...')
        print('    └── ...')
        print('')
        print('Examples:')
        print('  python batch_json_processor.py entries.csv CABC')
        print('  python batch_json_processor.py batch_input.csv USBC')
        sys.exit(1 if len(args) == 0 else 0)
    
    if len(args) < 2:
        print('Error: Both CSV file and environment are required')
        print('Usage: python batch_json_processor.py <csv-file> <environment>')
        sys.exit(1)
    
    csv_file = args[0]
    environment = args[1]
    
    # Validate environment parameter
    valid_environments = ['dev', 'USBC', 'USBD', 'CABC', 'CABD']
    if environment not in valid_environments:
        print(f'Error: Environment must be one of: {", ".join(valid_environments)}')
        sys.exit(1)
    
    try:
        print('\n=== BATCH JSON PROCESSOR ===')
        print(f'Environment: {environment}')
        print(f'CSV File: {csv_file}')
        print(f'Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print('')
        
        # Initialize processor
        processor = BatchJSONProcessor(environment)
        
        # Process CSV file
        processor.process_csv(csv_file)
        
        print('🎉 Batch processing completed successfully!')
        
    except Exception as error:
        print('\n💥 BATCH PROCESSING FAILED')
        print('=' * 60)
        print(f'Error: {str(error)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
