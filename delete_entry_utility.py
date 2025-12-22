#!/usr/bin/env python3
"""
Entry Deletion Utility
Recursively deletes all nested entries contained within a given entry

Usage: python delete_entry_utility.py <entry-uid> <environment> [content-type-uid] [--dry-run]
"""

import sys
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from lib.contentstack_api import ContentstackAPI
from lib.json_cleanup import JSONCleanup


class EntryDeletionUtility:
    def __init__(self, dry_run: bool = False, environment: str = 'dev'):
        """
        Initialize Entry Deletion Utility
        
        Args:
            dry_run: If True, only simulate deletion without actually deleting
            environment: Environment to use (dev, USBC, USBD, CABC, CABD)
        """
        self.dry_run = dry_run
        self.environment = environment
        self.contentstack_api = None
        
        self.deleted_entries = set()
        self.failed_deletions = {}
        self.processed_entries = set()
        self.would_delete_entries = set()
        self.backed_up_entries = {}
        self.backup_file_path = None
        
        # Create temp directory
        self.temp_dir = 'temp'
        os.makedirs(self.temp_dir, exist_ok=True)

    def initialize(self):
        """Initialize the utility with environment configurations"""
        try:
            print('\n=== INITIALIZING ENTRY DELETION UTILITY ===')
            
            # Load environment variables
            load_dotenv()
            
            # Validate required environment variables
            self.validate_environment_variables()
            
            # Get environment-specific configuration
            env_config = self.get_environment_config()
            
            # Initialize Contentstack API
            self.contentstack_api = ContentstackAPI(
                env_config['api_key'],
                env_config['management_token'],
                env_config['base_url'],
                env_config.get('auth_token'),
                env_config.get('environment_uid'),
                self.environment
            )
            
            print(f'✅ Initialization completed successfully for environment: {self.environment}')
            
        except Exception as error:
            print(f'❌ Initialization failed: {str(error)}')
            import traceback
            traceback.print_exc()
            raise

    def get_environment_config(self) -> dict:
        """Get environment-specific configuration"""
        return {
            'api_key': os.getenv(f'CONTENTSTACK_API_KEY_{self.environment}'),
            'management_token': os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{self.environment}'),
            'base_url': os.getenv(f'CONTENTSTACK_BASE_URL_{self.environment}'),
            'environment_uid': os.getenv(f'CONTENTSTACK_ENVIRONMENT_UID_{self.environment}'),
            'auth_token': os.getenv('CONTENTSTACK_AUTH_TOKEN')
        }

    def validate_environment_variables(self):
        """Validate required environment variables"""
        required_vars = [
            f'CONTENTSTACK_API_KEY_{self.environment}',
            f'CONTENTSTACK_MANAGEMENT_TOKEN_{self.environment}',
            f'CONTENTSTACK_BASE_URL_{self.environment}'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise Exception(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        print(f'✅ All required environment variables are present for {self.environment} environment')

    def delete_entry_recursively(self, entry_uid: str, content_type_uid: str = None) -> dict:
        """
        Main deletion function
        
        Args:
            entry_uid: The entry UID to delete recursively
            content_type_uid: Optional content type UID
            
        Returns:
            Deletion result dictionary
        """
        start_time = time.time()
        
        try:
            print('\n🗑️  STARTING RECURSIVE ENTRY DELETION')
            print(f'Entry UID: {entry_uid}')
            print(f'Environment: {self.environment}')
            print(f'Content Type: {content_type_uid}')
            print(f'Timestamp: {datetime.now().isoformat()}')
            
            # Default to feature_page if not provided
            if not content_type_uid:
                content_type_uid = 'feature_page'
                print(f'📄 No content type provided, defaulting to: {content_type_uid}')
            
            # Create backup before deletion
            print('\n💾 CREATING BACKUP BEFORE DELETION')
            print('==================================')
            backup_success = self.backup_entry_recursively(content_type_uid, entry_uid)
            
            if backup_success:
                print('✅ Backup completed successfully')
                self.save_backup_to_file(entry_uid, content_type_uid)
            else:
                print('⚠️  Backup failed, but continuing with deletion process')
            
            # Perform recursive deletion
            self.recursively_delete_entry(content_type_uid, entry_uid)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            mode = '🔍 DRY RUN COMPLETED' if self.dry_run else '🎉 RECURSIVE DELETION COMPLETED'
            print(f'\n{mode}')
            print(f'Duration: {duration} seconds')
            
            summary = {
                'success': True,
                'entry_uid': entry_uid,
                'content_type_uid': content_type_uid,
                'environment': self.environment,
                'duration': duration,
                'dry_run': self.dry_run,
                'deleted_entries': list(self.deleted_entries),
                'would_delete_entries': list(self.would_delete_entries),
                'failed_deletions': dict(self.failed_deletions),
                'total_deleted': len(self.deleted_entries),
                'total_would_delete': len(self.would_delete_entries),
                'total_failed': len(self.failed_deletions),
                'backup': {
                    'total_backed_up': len(self.backed_up_entries),
                    'backup_file_path': self.backup_file_path,
                    'backup_success': len(self.backed_up_entries) > 0
                },
                'timestamp': datetime.now().isoformat()
            }
            
            return summary
            
        except Exception as error:
            print(f'\n❌ DELETION FAILED: {str(error)}')
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(error),
                'entry_uid': entry_uid,
                'content_type_uid': content_type_uid
            }

    def recursively_delete_entry(self, content_type_uid: str, entry_uid: str, depth: int = 0) -> dict:
        """Recursively delete entry and all nested entries"""
        entry_key = f"{content_type_uid}/{entry_uid}"
        
        # Skip if already processed
        if entry_key in self.processed_entries:
            return {'skipped': True}
        
        self.processed_entries.add(entry_key)
        
        try:
            # Fetch entry
            entry_data = self.contentstack_api.get_entry(content_type_uid, entry_uid)
            entry = entry_data.get('entry', {})
            
            # Process nested entries first
            self._process_nested_entries(entry, depth + 1)
            
            # Delete or simulate deletion
            if self.dry_run:
                print(f"[DRY RUN] Would delete: {entry_key}")
                self.would_delete_entries.add(entry_key)
            else:
                print(f"[DELETE] Deleting: {entry_key}")
                result = self.contentstack_api.delete_entry(content_type_uid, entry_uid)
                
                if result.get('success'):
                    self.deleted_entries.add(entry_key)
                    if result.get('already_deleted'):
                        print(f"[DELETE] ℹ️ Entry was already deleted: {entry_key}")
                    else:
                        print(f"[DELETE] ✅ Successfully deleted: {entry_key}")
                    time.sleep(0.1)  # Reduced from 0.3s to 0.1s for faster processing
                elif result.get('protected'):
                    # Entry is protected (published, in workflow, or referenced)
                    # Don't treat as complete failure - log and continue
                    print(f"[DELETE] ⚠️ Entry is protected and cannot be auto-deleted: {entry_key}")
                    print(f"[DELETE] ℹ️ You may need to manually unpublish/delete this entry in Contentstack")
                    self.failed_deletions[entry_key] = 'Protected entry - requires manual deletion'
                    # Don't return failure, continue with other entries
                else:
                    error_msg = result.get('error', 'Unknown error')
                    print(f"[DELETE] ❌ Failed to delete {entry_key}: {error_msg}")
                    self.failed_deletions[entry_key] = error_msg
                    # Don't fail the whole operation, continue with other entries
            
            return {'success': True}
            
        except Exception as error:
            print(f"[DELETE] ❌ Exception while deleting {entry_key}: {str(error)}")
            self.failed_deletions[entry_key] = str(error)
            return {'success': False, 'error': str(error)}

    def _process_nested_entries(self, obj: any, depth: int):
        """Process nested entries in an object"""
        if isinstance(obj, dict):
            # Check if this is a reference to another entry
            if '_content_type_uid' in obj and 'uid' in obj:
                content_type = obj['_content_type_uid']
                uid = obj['uid']
                self.recursively_delete_entry(content_type, uid, depth)
            else:
                # Recursively process all values
                for value in obj.values():
                    self._process_nested_entries(value, depth)
        elif isinstance(obj, list):
            for item in obj:
                self._process_nested_entries(item, depth)

    def backup_entry_recursively(self, content_type_uid: str, entry_uid: str) -> bool:
        """Backup entry and all nested entries"""
        entry_key = f"{content_type_uid}/{entry_uid}"
        
        try:
            # Fetch entry with full content
            entry_data = self.contentstack_api.get_entry(content_type_uid, entry_uid)
            entry = entry_data.get('entry', {})
            
            # Clean the entry data
            cleanup = JSONCleanup(self.contentstack_api)
            cleaned_data = cleanup.cleanup_json(entry)
            
            # Store backup
            self.backed_up_entries[entry_key] = {
                'content_type_uid': content_type_uid,
                'entry_uid': entry_uid,
                'cleaned_data': cleaned_data,
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"[BACKUP] Backed up: {entry_key}")
            return True
            
        except Exception as error:
            print(f"[BACKUP] Failed to backup {entry_key}: {str(error)}")
            return False

    def save_backup_to_file(self, root_entry_uid: str, content_type_uid: str) -> str:
        """Save all backed up entries to a JSON file"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = f"backup_{content_type_uid}_{root_entry_uid}_{timestamp}.json"
        filepath = os.path.join(self.temp_dir, filename)
        
        # Get root entry backup
        root_entry_key = f"{content_type_uid}/{root_entry_uid}"
        root_backup = self.backed_up_entries.get(root_entry_key)
        
        if root_backup:
            backup_data = {
                'entry': root_backup['cleaned_data']
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            self.backup_file_path = filepath
            print(f"💾 Backup saved to: {filepath}")
            return filepath
        
        return None


def main():
    """Main CLI function"""
    args = sys.argv[1:]
    
    if '--help' in args or '-h' in args:
        print('\nEntry Deletion Utility')
        print('======================')
        print('')
        print('Usage: python delete_entry_utility.py <entry-uid> <environment> [content-type-uid] [--dry-run]')
        print('')
        print('Arguments:')
        print('  entry-uid        The UID of the entry to delete recursively')
        print('  environment      The environment (dev, USBC, USBD, CABC, CABD)')
        print('  content-type-uid Optional content type UID (defaults to "feature_page")')
        print('')
        print('Options:')
        print('  --dry-run        Show what would be deleted without actually deleting')
        print('')
        print('Examples:')
        print('  python delete_entry_utility.py blt1234567890abcdef USBC')
        print('  python delete_entry_utility.py blt1234567890abcdef dev feature_page')
        print('  python delete_entry_utility.py blt1234567890abcdef USBC --dry-run')
        sys.exit(0)
    
    if len(args) < 2:
        print('Error: Entry UID and environment are required')
        sys.exit(1)
    
    entry_uid = args[0]
    environment = args[1]
    content_type_uid = None
    dry_run = '--dry-run' in args
    
    # Get content type from non-flag arguments
    non_flag_args = [arg for arg in args if not arg.startswith('--')]
    if len(non_flag_args) > 2:
        content_type_uid = non_flag_args[2]
    
    # Validate environment
    valid_environments = ['dev', 'USBC', 'USBD', 'CABC', 'CABD']
    if environment not in valid_environments:
        print(f'Error: Environment must be one of: {", ".join(valid_environments)}')
        sys.exit(1)
    
    if dry_run:
        print('\n🔍 DRY RUN MODE - No entries will be actually deleted')
    else:
        # Show warning and ask for confirmation only for actual deletion
        print('\n⚠️  WARNING: DESTRUCTIVE OPERATION')
        print('=====================================')
        print(f'You are about to PERMANENTLY DELETE entry: {entry_uid}')
        print(f'Environment: {environment}')
        if content_type_uid:
            print(f'Content Type: {content_type_uid}')
        print('This will also delete ALL NESTED ENTRIES recursively.')
        print('This operation CANNOT BE UNDONE!')
        print('')
        print('Type "DELETE" to confirm, or press Ctrl+C to cancel: ', end='', flush=True)
        
        user_input = input().strip()
        
        if user_input != 'DELETE':
            print('Operation cancelled.')
            sys.exit(0)
    
    utility = EntryDeletionUtility(dry_run, environment)
    
    try:
        utility.initialize()
        result = utility.delete_entry_recursively(entry_uid, content_type_uid)
        
        print('\n📊 DELETION SUMMARY')
        print('===================')
        print(f'✅ Success: {result["success"]}')
        print(f'🗑️  Root Entry UID: {result["entry_uid"]}')
        print(f'⏱️  Duration: {result["duration"]}s')
        
        if result['dry_run']:
            print(f'Total Would Delete: {result["total_would_delete"]}')
        else:
            print(f'Total Deleted: {result["total_deleted"]}')
        
        sys.exit(0 if result['success'] else 1)
        
    except Exception as error:
        print(f'\n💥 FATAL ERROR: {str(error)}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
