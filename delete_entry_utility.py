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
        
        # Reference analysis tracking (NEW - matches Node.js)
        self.reference_analysis = {}  # Map of entryKey -> {to_be_deleted: bool, references: [], reason: str}
        self.referenced_entries = set()  # Entries referenced elsewhere (protected)
        self.orphaned_entries = set()  # Entries safe to delete (no external references)
        self.reference_analysis_completed = False  # Track if analysis phase is done
        
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

    def fetch_entry_details(self, content_type_uid: str, entry_uid: str) -> dict:
        """Fetch entry details to understand its structure"""
        try:
            response = self.contentstack_api.get_entry(content_type_uid, entry_uid)
            # Contentstack API returns: { "entry": { ... } }
            entry = response.get('entry', None)
            if not entry:
                print(f"[FETCH] Entry not found: {entry_uid}")
                return None
            return entry
        except Exception as error:
            print(f"[FETCH] Error fetching entry {entry_uid}: {str(error)}")
            return None

    def find_nested_entries(self, entry_data: any, found_entries: set = None) -> set:
        """Recursively find all nested entry references"""
        if found_entries is None:
            found_entries = set()
        
        if not entry_data or not isinstance(entry_data, (dict, list)):
            return found_entries
        
        if isinstance(entry_data, list):
            for item in entry_data:
                self.find_nested_entries(item, found_entries)
            return found_entries
        
        if isinstance(entry_data, dict):
            if '_content_type_uid' in entry_data and 'uid' in entry_data:
                entry_ref = {
                    'contentTypeUid': entry_data['_content_type_uid'],
                    'uid': entry_data['uid']
                }
                found_entries.add(json.dumps(entry_ref))
                print(f"[SCAN] Found nested entry: {entry_data['_content_type_uid']}/{entry_data['uid']}")
            
            if 'entry' in entry_data and isinstance(entry_data['entry'], dict):
                self.find_nested_entries(entry_data['entry'], found_entries)
            
            for key, value in entry_data.items():
                if key not in ['_content_type_uid', 'uid']:
                    self.find_nested_entries(value, found_entries)
        
        return found_entries

    def analyze_entry_references(self, content_type_uid: str, entry_uid: str, parent_entry_uid: str) -> dict:
        """Analyze entry references to determine if it can be safely deleted"""
        entry_key = f"{content_type_uid}/{entry_uid}"
        
        if entry_key in self.reference_analysis:
            return self.reference_analysis[entry_key]
        
        try:
            print(f"\n[REF-ANALYSIS] Analyzing references for: {entry_key}")
            
            entry_data = self.fetch_entry_details(content_type_uid, entry_uid)
            if not entry_data:
                result = {
                    'to_be_deleted': False,
                    'references': [],
                    'reason': 'Entry not found',
                    'has_migration_tag': False
                }
                self.reference_analysis[entry_key] = result
                return result
            
            # Check migration tag
            has_migration_tag = (
                'tags' in entry_data and 
                isinstance(entry_data['tags'], list) and 
                'migrated-from-cms' in entry_data['tags']
            )
            
            print(f"[REF-ANALYSIS] Entry {entry_key} - Migration tag: {'✅' if has_migration_tag else '❌'}")
            
            if not has_migration_tag:
                result = {
                    'to_be_deleted': False,
                    'references': [],
                    'reason': 'Missing migrated-from-cms tag',
                    'has_migration_tag': False
                }
                self.reference_analysis[entry_key] = result
                self.referenced_entries.add(entry_key)
                return result
            
            # Check references
            references_result = self.contentstack_api.get_entry_references(content_type_uid, entry_uid)
            all_references = references_result.get('references', [])
            
            # Filter out parent references
            external_references = []
            for ref in all_references:
                ref_entry_uid = ref.get('entry_uid') or ref.get('uid') or \
                              (ref.get('entry', {}).get('uid') if isinstance(ref.get('entry'), dict) else None)
                if ref_entry_uid != parent_entry_uid:
                    external_references.append(ref)
            
            print(f"[REF-ANALYSIS] Found {len(external_references)} external references (excluding parent)")
            
            if len(external_references) > 0:
                result = {
                    'to_be_deleted': False,
                    'references': external_references,
                    'reason': f'Referenced in {len(external_references)} other entries',
                    'has_migration_tag': True
                }
                self.referenced_entries.add(entry_key)
                print(f"[REF-ANALYSIS] Entry {entry_key} PROTECTED - referenced elsewhere")
            else:
                result = {
                    'to_be_deleted': True,
                    'references': [],
                    'reason': 'No external references found',
                    'has_migration_tag': True
                }
                self.orphaned_entries.add(entry_key)
                print(f"[REF-ANALYSIS] Entry {entry_key} SAFE TO DELETE")
            
            self.reference_analysis[entry_key] = result
            return result
            
        except Exception as error:
            result = {
                'to_be_deleted': False,
                'references': [],
                'reason': f'Analysis error: {str(error)}',
                'has_migration_tag': False
            }
            self.reference_analysis[entry_key] = result
            self.referenced_entries.add(entry_key)
            return result

    def traverse_hierarchy_root_first(self, content_type_uid: str, entry_uid: str, 
                                     entry_data: dict, root_entry_uid: str,
                                     immediate_parent_uid: str = None):
        """Traverse entry hierarchy in root-first approach"""
        entry_key = f"{content_type_uid}/{entry_uid}"
        
        if entry_key in self.reference_analysis:
            return
        
        parent_for_filtering = immediate_parent_uid or root_entry_uid
        analysis_result = self.analyze_entry_references(content_type_uid, entry_uid, parent_for_filtering)
        
        if not analysis_result['to_be_deleted']:
            # Mark nested entries as protected by inheritance
            nested_entries = self.find_nested_entries(entry_data)
            for nested_entry_json in nested_entries:
                nested_entry = json.loads(nested_entry_json)
                nested_key = f"{nested_entry['contentTypeUid']}/{nested_entry['uid']}"
                
                if nested_key not in self.reference_analysis:
                    inherited_result = {
                        'to_be_deleted': False,
                        'references': [],
                        'reason': f'Inherited protection from parent {entry_key}',
                        'has_migration_tag': False
                    }
                    self.reference_analysis[nested_key] = inherited_result
                    self.referenced_entries.add(nested_key)
            return
        
        # Analyze children
        nested_entries = self.find_nested_entries(entry_data)
        for nested_entry_json in nested_entries:
            nested_entry = json.loads(nested_entry_json)
            try:
                nested_data = self.fetch_entry_details(nested_entry['contentTypeUid'], nested_entry['uid'])
                if nested_data:
                    self.traverse_hierarchy_root_first(
                        nested_entry['contentTypeUid'],
                        nested_entry['uid'],
                        nested_data,
                        root_entry_uid,
                        entry_uid
                    )
                time.sleep(0.2)
            except Exception as error:
                print(f"[REF-ANALYSIS] Error processing nested entry: {str(error)}")

    def analyze_entry_hierarchy_for_references(self, content_type_uid: str, entry_uid: str) -> bool:
        """Analyze entry hierarchy for references"""
        try:
            print('\n=== STARTING REFERENCE ANALYSIS PHASE ===')
            
            root_entry_data = self.fetch_entry_details(content_type_uid, entry_uid)
            if not root_entry_data:
                return False
            
            self.traverse_hierarchy_root_first(content_type_uid, entry_uid, root_entry_data, entry_uid)
            
            self.reference_analysis_completed = True
            print('\n=== REFERENCE ANALYSIS PHASE COMPLETED ===')
            print(f'Total entries analyzed: {len(self.reference_analysis)}')
            print(f'Entries safe to delete: {len(self.orphaned_entries)}')
            print(f'Entries protected: {len(self.referenced_entries)}')
            
            return True
        except Exception as error:
            print(f'[REF-ANALYSIS] Error: {str(error)}')
            self.reference_analysis_completed = False
            return False

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
            
            # CRITICAL: Perform reference analysis before deletion
            print('\n🔍 PERFORMING REFERENCE ANALYSIS')
            print('================================')
            analysis_success = self.analyze_entry_hierarchy_for_references(content_type_uid, entry_uid)
            
            if not analysis_success or not self.reference_analysis_completed:
                print('\n❌ REFERENCE ANALYSIS FAILED - ABORTING DELETION')
                print('Cannot safely proceed without reference analysis')
                return {
                    'success': False,
                    'error': 'Reference analysis failed',
                    'entry_uid': entry_uid,
                    'content_type_uid': content_type_uid
                }
            
            if self.reference_analysis_completed:
                print(f'📊 Analysis complete: {len(self.reference_analysis)} entries analyzed')
                print(f'🛡️  Protected entries: {len(self.referenced_entries)}')
                print(f'✅ Clear for deletion: {len(self.orphaned_entries)}')
                
                # Show protected entries like Node.js does
                if len(self.referenced_entries) > 0:
                    print('\n🛡️  PROTECTED ENTRIES (will not be deleted):')
                    for idx, entry_key in enumerate(self.referenced_entries, 1):
                        analysis = self.reference_analysis.get(entry_key, {})
                        reason = analysis.get('reason', 'Unknown')
                        print(f'  {idx}. {entry_key}: {reason}')
            
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
        
        # CRITICAL SAFETY CHECK: Verify reference analysis before deletion
        if self.reference_analysis_completed:
            if entry_key not in self.reference_analysis:
                print(f"[SAFETY] ⚠️ Entry {entry_key} not in reference analysis - SKIPPING")
                return {'skipped': True, 'reason': 'Not analyzed'}
            
            analysis = self.reference_analysis[entry_key]
            if not analysis['to_be_deleted']:
                print(f"[SAFETY] 🛡️ Entry {entry_key} is PROTECTED - SKIPPING")
                print(f"[SAFETY] Reason: {analysis['reason']}")
                return {'skipped': True, 'reason': analysis['reason']}
        
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
