#!/usr/bin/env python3
"""
JSON Cleanup CLI
Usage: python json_cleanup_cli.py <input-file> <environment> [output-file]
"""

import sys
import json
import os
from dotenv import load_dotenv
from lib.json_cleanup import JSONCleanup
from lib.contentstack_api import ContentstackAPI


def main():
    """Main CLI function"""
    args = sys.argv[1:]
    
    if len(args) == 0 or '--help' in args or '-h' in args:
        print('JSON Cleanup CLI - Environment-Aware')
        print('=====================================')
        print('')
        print('Usage: python json_cleanup_cli.py <input-file> <environment> [output-file] [--locale <locale>]')
        print('')
        print('Arguments:')
        print('  input-file    Path to the JSON file to clean')
        print('  environment   Environment to use (dev, USBC, USBD, CABC, CABD)')
        print('  output-file   Optional output file path (defaults to input-file-cleaned.json)')
        print('  --locale      Optional locale for French content (use: --locale fr-ca)')
        print('                By default, ContentStack will fetch English content')
        print('')
        print('Examples:')
        print('  python json_cleanup_cli.py input-json/test.json USBC')
        print('  python json_cleanup_cli.py input-json/test.json dev output.json')
        print('  python json_cleanup_cli.py input-json/test.json CABC --locale fr-ca')
        print('  python json_cleanup_cli.py input-json/test.json CABC output-fr.json --locale fr-ca')
        sys.exit(1 if len(args) == 0 else 0)
    
    if len(args) < 2:
        print('Error: Both input file and environment are required')
        print('Usage: python json_cleanup_cli.py <input-file> <environment> [output-file] [--locale <locale>]')
        sys.exit(1)
    
    # Parse arguments
    input_file = args[0]
    environment = args[1]
    
    # Check for --locale flag (optional, only use when you need French content)
    locale = None  # Default: None (ContentStack will use English by default)
    if '--locale' in args:
        locale_index = args.index('--locale')
        if locale_index + 1 < len(args):
            locale = args[locale_index + 1]
            # Remove --locale and its value from args for output_file processing
            args = [arg for i, arg in enumerate(args) if i not in (locale_index, locale_index + 1)]
        else:
            print('Error: --locale flag requires a value (e.g., --locale fr-ca)')
            sys.exit(1)
    
    # Validate locale if provided
    if locale:
        valid_locales = ['fr-ca']  # Add more locales as needed
        if locale not in valid_locales:
            print(f'Warning: Locale "{locale}" is not in the validated list: {", ".join(valid_locales)}')
            print(f'Continuing anyway...')
    
    # Determine output file (after removing --locale from args)
    output_file = args[2] if len(args) > 2 else input_file.replace('.json', '-cleaned.json')
    
    # Validate environment parameter
    valid_environments = ['dev', 'USBC', 'USBD', 'CABC', 'CABD']
    if environment not in valid_environments:
        print(f'Error: Environment must be one of: {", ".join(valid_environments)}')
        sys.exit(1)
    
    try:
        # Load environment variables
        load_dotenv()
        
        print('\n=== INITIALIZING JSON CLEANUP UTILITY ===')
        print(f'Environment: {environment}')
        if locale:
            print(f'Locale: {locale}')
        else:
            print(f'Locale: Default (English)')
        print(f'Input file: {input_file}')
        print(f'Output file: {output_file}')
        
        # Validate required environment variables
        validate_environment_variables(environment)
        
        # Get environment-specific configuration
        env_config = get_environment_config(environment)
        
        # Initialize Contentstack API
        contentstack_api = ContentstackAPI(
            env_config['api_key'],
            env_config['management_token'],
            env_config['base_url'],
            env_config.get('auth_token'),
            env_config.get('environment_uid'),
            environment  # Pass the environment parameter
        )
        
        print(f'✅ Initialization completed successfully for environment: {environment}')
        
        # Check if input file exists
        if not os.path.exists(input_file):
            print(f"Error: Input file '{input_file}' does not exist.")
            sys.exit(1)
        
        print(f'\n📄 Reading input file: {input_file}')
        
        # Read and parse JSON
        with open(input_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        print('🧹 Cleaning JSON data...')
        
        # Clean the JSON data (locale is None by default, only set when --locale flag is used)
        cleanup = JSONCleanup(contentstack_api, locale=locale)
        cleaned_data = cleanup.cleanup_json(json_data)
        
        # Write cleaned data to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
        
        print(f'\n✅ Cleaned JSON written to: {output_file}')
        print(f'🌍 Environment used: {environment}')
        if locale:
            print(f'🌐 Locale used: {locale}')
        print('🎉 Cleanup completed successfully!')
        
    except Exception as error:
        print('\n💥 JSON CLEANUP FAILED')
        print('======================')
        print(f'Error: {str(error)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


def get_environment_config(environment: str) -> dict:
    """Get environment-specific configuration"""
    return {
        'api_key': os.getenv(f'CONTENTSTACK_API_KEY_{environment}'),
        'management_token': os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{environment}'),
        'base_url': os.getenv(f'CONTENTSTACK_BASE_URL_{environment}'),
        'environment_uid': os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{environment}'),
        'auth_token': os.getenv('CONTENTSTACK_AUTH_TOKEN')
    }


def validate_environment_variables(environment: str):
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
    
    print(f'✅ All required environment variables are present for {environment} environment')


if __name__ == '__main__':
    main()
