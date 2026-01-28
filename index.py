"""
CSM Content Creation Utility - Main Entry Point (Task 3)

Complete Python migration of the Node.js content creation utility.
Handles the full content creation workflow including:
- Asset processing and migration to Brandfolder
- Entry creation with nested content types  
- Workflow processing (Review → Approved stages)
- Publishing with deep publish for all nested entries
- Rollback protection for created entries

Usage:
    python index.py <input-file.json> --env <environment>
    python index.py input-json/test.json --env USBC
    python index.py --help
"""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from lib.content_processor import ContentProcessor


class ContentCreationUtility:
    """
    Main content creation utility class
    """
    
    def __init__(self):
        """Initialize the utility"""
        # Load environment variables
        load_dotenv()
        
        # Validate environment variables
        self.validate_environment_variables()
        
        # Parse command line arguments
        self.args = self.parse_arguments()
        
        # Get environment from args
        self.environment = self.args.env
        
        # Get input file path
        self.input_json_path = self.args.input or os.getenv('INPUT_JSON_PATH', 'input-json/connection-at-your-service-concierge-page.json.json')
        
        # Entry reuse configuration
        self.entry_reuse_enabled = os.getenv('ENTRY_REUSE_ENABLED', 'true').lower() != 'false'
        
        # Build configuration for all environments
        self.brandfolder_config = {}
        self.contentstack_config = {}
        self.brandfolder_collection_id = {}
        
        # Load configurations for each environment
        environments = ['dev', 'USBC', 'USBD', 'CABC', 'CABD']
        for env in environments:
            # Brandfolder configuration
            self.brandfolder_config[env] = {
                'api_key': os.getenv(f'BRANDFOLDER_API_KEY_{env}'),
                'organization_id': os.getenv(f'BRANDFOLDER_ORGANIZATION_ID_{env}'),
                'section_key': os.getenv(f'BRANDFOLDER_SECTION_KEY_{env}', '')
            }
            
            # Contentstack configuration
            self.contentstack_config[env] = {
                'api_key': os.getenv(f'CONTENTSTACK_API_KEY_{env}'),
                'management_token': os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{env}'),
                'base_url': os.getenv(f'CONTENTSTACK_BASE_URL_{env}', 'https://api.contentstack.io'),
                'auth_token': os.getenv('CONTENTSTACK_AUTH_TOKEN'),  # Auth token for Approved stage
                'environment_uid': os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{env}'),
                'environment': env,  # Add environment name for locale determination
                'app_url': os.getenv(f'CONTENTSTACK_APP_URL_{env}', 'https://azure-na-app.contentstack.com'),
                'published_page_base_url': os.getenv(f'PUBLISHED_PAGE_BASE_URL_{env}', 'https://web-prd.pd.gdx.cc-costco.com/consumer-web/browse/prd/homepage-usbc/f/-/'),
                'cache_flush_base_url': os.getenv(f'CACHE_FLUSH_BASE_URL_{env}', '')
            }
            
            # Brandfolder collection ID
            self.brandfolder_collection_id[env] = os.getenv(f'BRANDFOLDER_COLLECTION_ID_{env}', '')
        
        print(f"✅ Configuration loaded for {len(environments)} environments")
    
    def validate_environment_variables(self):
        """Validate that required environment variables are set"""
        # Check for at least one complete environment configuration
        required_prefixes = [
            'CONTENTSTACK_API_KEY_',
            'CONTENTSTACK_MANAGEMENT_TOKEN_',
            'BRANDFOLDER_API_KEY_',
            'BRANDFOLDER_ORGANIZATION_ID_'
        ]
        
        # Check if we have at least one environment configured
        env_names = ['dev', 'USBC', 'USBD', 'CABC', 'CABD']
        has_valid_env = False
        
        for env in env_names:
            all_present = all(
                os.getenv(f"{prefix}{env}") 
                for prefix in required_prefixes
            )
            if all_present:
                has_valid_env = True
                break
        
        if not has_valid_env:
            print("\n❌ ERROR: No complete environment configuration found")
            print("\nRequired environment variables for at least one environment:")
            for prefix in required_prefixes:
                print(f"  - {prefix}<ENV>  (where <ENV> is dev, USBC, USBD, CABC, or CABD)")
            print("\nPlease check your .env file and ensure it has complete configuration.")
            sys.exit(1)
        
        print('✅ Environment variables validated')
    
    def parse_arguments(self):
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(
            description='CSM Content Creation Utility - Create content in Contentstack from JSON',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  python index.py input-json/my-content.json --env USBC
  python index.py --input input-json/costco-concierge-page.json --env dev
  python index.py -i input-json/feature-page.json --environment USBD

Features:
  ✅ Asset processing and migration to Brandfolder
  ✅ Entry creation with nested content types
  ✅ Workflow processing (Review → Approved stages)
  ✅ Publishing with deep publish for all nested entries
  ✅ Published URL generation
  ✅ Rollback protection for created entries

Environments:
  dev, USBC, USBD, CABC, CABD
            """
        )
        
        parser.add_argument(
            'input',
            nargs='?',
            help='Input JSON file path (default: from INPUT_JSON_PATH env var)'
        )
        
        parser.add_argument(
            '--env', '--environment',
            dest='env',
            default='dev',
            choices=['dev', 'USBC', 'USBD', 'CABC', 'CABD'],
            help='Environment to use (default: dev)'
        )
        
        parser.add_argument(
            '-i', '--input',
            dest='input',
            help='Input JSON file path (alternative flag)'
        )
        
        return parser.parse_args()
    
    async def load_input_json(self):
        """Load and parse the input JSON file"""
        try:
            print(f"\n📁 Loading input JSON from: {self.input_json_path}")
            
            absolute_path = Path(self.input_json_path).resolve()
            
            # Check if file exists
            if not absolute_path.exists():
                raise FileNotFoundError(f"Input file not found: {absolute_path}")
            
            with open(absolute_path, 'r', encoding='utf-8') as f:
                parsed_json = json.load(f)
            
            print('✅ Input JSON loaded successfully')
            print(f"📊 JSON structure preview:")
            print(f"  - Root entry title: {parsed_json.get('entry', {}).get('title', 'No title')}")
            print(f"  - Page ID: {parsed_json.get('entry', {}).get('page_id', 'No page ID')}")
            print(f"  - Locale: {parsed_json.get('entry', {}).get('locale', 'No locale')}")
            
            return parsed_json
            
        except FileNotFoundError as error:
            print(f"\n❌ ERROR: {str(error)}")
            print('\n💡 Suggestions:')
            print('  - Check if the file path is correct')
            print('  - Ensure the file exists in the specified location')
            print('  - Try using an absolute path')
            raise
            
        except json.JSONDecodeError as error:
            print(f"\n❌ ERROR: Invalid JSON in file {self.input_json_path}")
            print(f"Error details: {str(error)}")
            print('\n💡 Suggestions:')
            print('  - Validate the JSON syntax using a JSON validator')
            print('  - Check for missing commas, brackets, or quotes')
            raise
            
        except Exception as error:
            print(f"\n❌ ERROR: Failed to load input JSON")
            print(f"Error: {str(error)}")
            raise
    
    async def run(self):
        """Run the content creation process"""
        start_time = datetime.now()
        
        try:
            print('\n🚀 STARTING CSM CONTENT CREATION UTILITY')
            print('=' * 80)
            
            # Load input JSON
            input_json = await self.load_input_json()
            
            # Initialize content processor
            print('\n🔧 Initializing content processor...')
            
            processor_options = {
                'entry_reuse_enabled': self.entry_reuse_enabled
            }
            
            processor = ContentProcessor(
                self.brandfolder_config,
                self.contentstack_config,
                self.brandfolder_collection_id,
                processor_options
            )
            
            print(f"🔄 Entry reuse is {'ENABLED' if self.entry_reuse_enabled else 'DISABLED'}")
            if self.entry_reuse_enabled:
                print('   - Existing entries with matching titles will be reused')
            else:
                print('   - New entries will always be created')
            
            # Process content
            print('\n⚡ Starting content processing...')
            print(f"🌍 Using environment: {self.environment}")
            
            result = await processor.process_content(input_json, self.environment)
            
            # Extract page_id for URL generation
            page_id = input_json.get('entry', {}).get('page_id')
            if page_id:
                print(f"\nExtracted page_id: {page_id}")
            else:
                print('\n⚠️ page_id not found in entry data - URL generation will be skipped')
            
            # Process workflow and publish
            print('\n=== STARTING WORKFLOW AND PUBLISHING PROCESS ===')
            
            workflow_and_publish_result = None
            try:
                if page_id:
                    # Get environment-specific URLs
                    cs_config = self.contentstack_config[self.environment]
                    published_page_base_url = cs_config['published_page_base_url']
                    cache_flush_base_url = cs_config['cache_flush_base_url']
                    
                    workflow_and_publish_result = await processor.complete_workflow_and_publish(
                        result['root_entry_uid'],
                        page_id,
                        'feature_page',
                        published_page_base_url,
                        cache_flush_base_url
                    )
                    
                    print('✅ Workflow and publishing completed successfully')
                    print(f"📄 Published page URL: {workflow_and_publish_result['published_url']}")
                else:
                    print('⚠️ Skipping workflow and publishing due to missing page_id')
                    
            except Exception as workflow_error:
                print(f"❌ Workflow and publishing failed: {str(workflow_error)}")
                print('Content creation was successful, but workflow/publishing failed')
                print(f"\n📋 WORKFLOW/PUBLISH ERROR DETAILS:")
                print(f"Error Type: {type(workflow_error).__name__}")
                print(f"Error Message: {str(workflow_error)}")
            
            # Get processing summary
            summary = processor.get_processing_summary()
            
            # Display results
            self.display_results(result, summary, start_time, page_id, workflow_and_publish_result)
            
        except Exception as error:
            print('\n💥 CONTENT CREATION FAILED')
            print('=' * 80)
            print(f"Error: {str(error)}")
            
            print(f"\n📋 COMPLETE ERROR DETAILS:")
            print(f"Error Type: {type(error).__name__}")
            print(f"Error Message: {str(error)}")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            print(f"\n⏱️  Total execution time: {duration:.2f} seconds")
            
            raise
    
    def display_results(self, result, summary, start_time, page_id=None, workflow_and_publish_result=None):
        """Display the processing results"""
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print('\n🎉 CONTENT CREATION COMPLETED SUCCESSFULLY')
        print('=' * 80)
        
        print('\n📈 PROCESSING SUMMARY:')
        print(f"  ✅ Root entry UID: {result['root_entry_uid']}")
        print(f"  📸 Assets processed: {summary['assets_processed']} ({summary['existing_assets']} existing, {summary['new_assets']} new{f', {summary["skipped_assets"]} skipped' if summary['skipped_assets'] > 0 else ''})")
        print(f"  📄 Entries processed: {summary['entries_processed']} ({summary['existing_entries']} existing, {summary['new_entries']} new)")
        print(f"  🔄 Rollback tracking: {summary['created_entries_for_rollback']} new entries tracked")
        print(f"  ⏱️  Total execution time: {duration:.2f} seconds")
        
        # Workflow and Publishing Summary
        print('\n🔄 WORKFLOW & PUBLISHING')
        print('=' * 80)
        if page_id:
            print(f"📋 Page ID: {page_id}")
        else:
            print(f"📋 Page ID: Not found")
        
        if workflow_and_publish_result and workflow_and_publish_result.get('success'):
            print(f"🔀 Workflow: ✅ Completed (Review → Approved)")
            print(f"📤 Publishing: ✅ Published with deep publish")
            print(f"🌐 Published URL: {workflow_and_publish_result['published_url']}")
            
            # Generate dynamic ContentStack URL with environment-specific locale
            cs_config = self.contentstack_config[self.environment]
            locale = 'en-ca' if self.environment in ['CABC', 'CABD'] else 'en-us'
            contentstack_url = f"{cs_config['app_url']}/content-type/feature_page/{locale}/entry/{result['root_entry_uid']}/edit?branch=main"
            print(f"ContentStack URL: {contentstack_url}")
        elif workflow_and_publish_result is None and not page_id:
            print(f"🔀 Workflow: ⚠️ Skipped (missing page_id)")
            print(f"📤 Publishing: ⚠️ Skipped (missing page_id)")
            print(f"🌐 Published URL: Not available")
        else:
            print(f"🔀 Workflow: ❌ Failed")
            print(f"📤 Publishing: ❌ Failed")
            print(f"🌐 Published URL: Not available")
        
        print('\n🏁 Process completed successfully!')


async def async_main():
    """Async main entry point"""
    utility = ContentCreationUtility()
    await utility.run()


def main():
    """Main entry point"""
    # Check for help flag first
    if '--help' in sys.argv or '-h' in sys.argv:
        parser = argparse.ArgumentParser(
            description='CSM Content Creation Utility',
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        parser.print_help()
        return 0
    
    try:
        # Run the async main function
        asyncio.run(async_main())
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️ Process interrupted by user")
        return 1
    except Exception as error:
        print(f"\n💥 Fatal error: {str(error)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())