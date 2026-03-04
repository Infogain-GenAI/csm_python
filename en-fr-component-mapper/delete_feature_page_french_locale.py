"""
Delete the fr-ca locale from the English feature page
This fixes the issue where clicking French locale redirects to a different page
"""

import sys
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

# Add parent directory to path for shared libs
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir / 'lib'))

# Now try to import from local lib first, then fall back to parent
try:
    from lib.contentstack_api import ContentstackAPI
except ImportError:
    from contentstack_api import ContentstackAPI

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

def delete_locale(content_type_uid: str, entry_uid: str, locale: str, environment: str):
    """
    Delete a specific locale from an entry
    """
    print(f"\n{'='*80}")
    print(f"DELETE LOCALE FROM ENTRY")
    print(f"{'='*80}\n")
    print(f"Content Type: {content_type_uid}")
    print(f"Entry UID: {entry_uid}")
    print(f"Locale to delete: {locale}")
    print(f"Environment: {environment}")
    
    # Get environment variables
    api_key = os.getenv(f'CONTENTSTACK_API_KEY_{environment}')
    management_token = os.getenv(f'CONTENTSTACK_MANAGEMENT_TOKEN_{environment}')
    base_url = os.getenv(f'CONTENTSTACK_BASE_URL_{environment}')
    
    if not all([api_key, management_token, base_url]):
        print(f"❌ Missing environment variables for {environment}")
        return False
    
    # Build URL for unlocalize (ContentStack uses this to remove locales)
    url = f"{base_url.rstrip('/')}/content_types/{content_type_uid}/entries/{entry_uid}/unlocalize"
    
    headers = {
        'api_key': api_key,
        'authorization': management_token,
        'Content-Type': 'application/json'
    }
    
    # Request body to specify which locale to remove
    payload = {
        "entry": {
            "locales": [locale]
        }
    }
    
    print(f"\n🗑️  Unlocalizing (removing) {locale} locale from {entry_uid}...")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201, 204]:
            print(f"✅ Successfully removed {locale} locale from {entry_uid}")
            return True
        else:
            print(f"❌ Failed to remove locale: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == '__main__':
    # Delete fr-ca locale from English feature page
    result = delete_locale(
        content_type_uid='feature_page',
        entry_uid='blt808021fad03caaa2',
        locale='fr-ca',
        environment='CABC'
    )
    
    if result:
        print(f"\n{'='*80}")
        print(f"✅ CLEANUP COMPLETED")
        print(f"{'='*80}")
        print(f"\nThe English feature page now only has en-ca locale.")
        print(f"When you access it with ?locale=fr-ca, it will:")
        print(f"  1. Load the page in en-ca locale")
        print(f"  2. But load all components in fr-ca locale")
        print(f"  3. Show French content correctly!")
    else:
        print(f"\n{'='*80}")
        print(f"❌ CLEANUP FAILED")
        print(f"{'='*80}")
        sys.exit(1)
