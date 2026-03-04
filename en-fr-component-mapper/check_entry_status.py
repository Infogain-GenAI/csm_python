"""
Check the current state of a French locale entry
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

from dotenv import load_dotenv
from contentstack_api import ContentstackAPI

# Load environment
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# Initialize API
api = ContentstackAPI(
    api_key=os.getenv('CONTENTSTACK_API_KEY_CABC'),
    management_token=os.getenv('CONTENTSTACK_MANAGEMENT_TOKEN_CABC'),
    base_url=os.getenv('CONTENTSTACK_BASE_URL_CABC'),
    auth_token=os.getenv('CONTENTSTACK_AUTH_TOKEN'),
    environment_uid=os.getenv('CONTENTSTACK_ENVIRONMENT_UID_CABC'),
    environment='CABC'
)

# Test component
test_content_type = 'link_list_simple'
test_uid = 'blt88da09515bbb6c8a'

print("="*80)
print(f"CHECKING ENTRY STATUS")
print("="*80)
print(f"Component: {test_content_type}/{test_uid}")
print(f"Checking both en-ca and fr-ca locales...")

# Check English locale
print(f"\n{'='*60}")
print(f"ENGLISH (en-ca) LOCALE")
print(f"{'='*60}")

try:
    response = api.get_entry(test_content_type, test_uid, locale='en-ca')
    if response and 'entry' in response:
        entry = response['entry']
        print(f"✅ Entry exists")
        print(f"   Title: {entry.get('title', 'N/A')}")
        print(f"   Publish Details: {entry.get('publish_details', 'N/A')}")
        
        if '_workflow' in entry:
            print(f"   Workflow: {entry['_workflow']}")
        else:
            print(f"   Workflow: No workflow assigned")
            
except Exception as e:
    print(f"❌ Error: {e}")

# Check French locale  
print(f"\n{'='*60}")
print(f"FRENCH (fr-ca) LOCALE")
print(f"{'='*60}")

try:
    response = api.get_entry(test_content_type, test_uid, locale='fr-ca')
    if response and 'entry' in response:
        entry = response['entry']
        print(f"✅ Entry exists")
        print(f"   Title: {entry.get('title', 'N/A')}")
        print(f"   Publish Details: {entry.get('publish_details', 'N/A')}")
        
        if '_workflow' in entry:
            print(f"   Workflow: {entry['_workflow']}")
        else:
            print(f"   Workflow: No workflow assigned")
            
        # Show full entry structure
        print(f"\n   Full Entry Structure:")
        import json
        print(json.dumps(entry, indent=2, ensure_ascii=False))
            
except Exception as e:
    print(f"❌ Error: {e}")
