"""
Diagnostic script to check link_flyout English vs French content mapping.
"""
import sys
import os
import json
from pathlib import Path

# Add parent lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from contentstack_api import ContentstackAPI

def extract_text_content(entry_data, path=""):
    """Recursively extract all text content fields from entry."""
    texts = []
    
    if isinstance(entry_data, dict):
        for key, value in entry_data.items():
            current_path = f"{path}.{key}" if path else key
            
            # Check if this is a text content field
            if key in ['title', 'text', 'markdown_text', 'description', 'link_text']:
                if isinstance(value, str) and value.strip():
                    texts.append((current_path, value[:100]))  # Truncate for display
            
            # Recurse
            if isinstance(value, (dict, list)):
                texts.extend(extract_text_content(value, current_path))
    
    elif isinstance(entry_data, list):
        for i, item in enumerate(entry_data):
            current_path = f"{path}[{i}]"
            texts.extend(extract_text_content(item, current_path))
    
    return texts

def main():
    # Get API credentials from environment
    api_key = os.getenv('CONTENTSTACK_API_KEY')
    management_token = os.getenv('CONTENTSTACK_MANAGEMENT_TOKEN')
    
    if not api_key or not management_token:
        print("❌ Error: CONTENTSTACK_API_KEY and CONTENTSTACK_MANAGEMENT_TOKEN environment variables required")
        return
    
    # Initialize API
    api = ContentstackAPI(api_key, management_token, 'CABC')
    
    # The problematic link_flyout
    flyout_uid = 'bltdfc3c815bf07a94d'
    
    print(f"\n{'='*70}")
    print(f"🔍 DIAGNOSING link_flyout/{flyout_uid}")
    print(f"{'='*70}\n")
    
    # Fetch English version
    print("📥 Fetching ENGLISH version...")
    eng_response = api.get_entry('link_flyout', flyout_uid, locale='en-ca')
    eng_entry = eng_response.get('entry', {})
    
    # Fetch French version
    print("📥 Fetching FRENCH version...")
    fr_response = api.get_entry('link_flyout', flyout_uid, locale='fr-ca')
    fr_entry = fr_response.get('entry', {})
    
    # Extract text content
    print("\n" + "="*70)
    print("📝 ENGLISH TEXT CONTENT:")
    print("="*70)
    eng_texts = extract_text_content(eng_entry)
    for path, text in eng_texts:
        print(f"  {path}")
        print(f"    → {text}")
        print()
    
    print("="*70)
    print("📝 FRENCH TEXT CONTENT:")
    print("="*70)
    fr_texts = extract_text_content(fr_entry)
    for path, text in fr_texts:
        print(f"  {path}")
        print(f"    → {text}")
        print()
    
    # Compare
    print("="*70)
    print("⚖️  COMPARISON:")
    print("="*70)
    
    if len(eng_texts) != len(fr_texts):
        print(f"⚠️  MISMATCH: English has {len(eng_texts)} text fields, French has {len(fr_texts)}")
    
    # Check if any French text is actually English
    eng_text_values = {text for _, text in eng_texts}
    fr_text_values = {text for _, text in fr_texts}
    
    english_in_french = eng_text_values & fr_text_values
    if english_in_french:
        print(f"\n❌ PROBLEM FOUND: French version contains English text!")
        print(f"   {len(english_in_french)} identical text(s) found:")
        for text in list(english_in_french)[:3]:
            print(f"     • {text}")
    else:
        print(f"\n✅ No identical text found (French content appears different from English)")
    
    # Save full JSONs for manual inspection
    output_dir = Path(__file__).parent / "diagnostic_output"
    output_dir.mkdir(exist_ok=True)
    
    eng_file = output_dir / f"link_flyout_{flyout_uid}_en-ca.json"
    fr_file = output_dir / f"link_flyout_{flyout_uid}_fr-ca.json"
    
    with open(eng_file, 'w', encoding='utf-8') as f:
        json.dump(eng_entry, f, indent=2, ensure_ascii=False)
    
    with open(fr_file, 'w', encoding='utf-8') as f:
        json.dump(fr_entry, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Full JSON dumps saved:")
    print(f"   English: {eng_file}")
    print(f"   French:  {fr_file}")
    print(f"\n🔍 Review these files to see exact content differences")

if __name__ == "__main__":
    main()
