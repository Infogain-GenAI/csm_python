"""
Fix corrupt training data - Replace #337AB7 with correct colors from English
"""
import json
import os
from pathlib import Path

def fix_training_data():
    """Fix all mapped_output files with wrong colors"""
    base_dir = Path(__file__).parent / "component_data"
    
    fixed_count = 0
    total_files = 0
    
    for component_type in ["ad_builder", "ad_set_costco", "link_list_with_flyout_references"]:
        component_dir = base_dir / component_type
        if not component_dir.exists():
            continue
            
        # Find all mapped_output files
        mapped_files = sorted(component_dir.glob("mapped_output_*.json"))
        
        for mapped_file in mapped_files:
            total_files += 1
            file_num = mapped_file.stem.split("_")[-1]
            english_file = component_dir / f"english_input_{file_num}.json"
            
            if not english_file.exists():
                print(f"⚠️  No English file for {mapped_file.name}")
                continue
            
            # Load files
            with open(english_file, 'r', encoding='utf-8') as f:
                english_data = json.load(f)
            
            with open(mapped_file, 'r', encoding='utf-8') as f:
                mapped_data = json.load(f)
            
            # Check if this file has #337AB7
            mapped_str = json.dumps(mapped_data)
            if "#337ab7" not in mapped_str.lower():
                print(f"✅ {mapped_file.name} - Already correct")
                continue
            
            print(f"\n🔧 Fixing {mapped_file.name}...")
            
            # Fix colors recursively
            def fix_colors(eng_obj, mapped_obj, path=""):
                if isinstance(eng_obj, dict) and isinstance(mapped_obj, dict):
                    for key in mapped_obj.keys():
                        if key in eng_obj:
                            # Check if this is a color field with wrong value
                            if key == "hex" and isinstance(mapped_obj[key], str):
                                if mapped_obj[key].lower() == "#337ab7":
                                    print(f"   Found #337AB7 at {path}.{key}")
                                    mapped_obj[key] = eng_obj[key]
                                    print(f"   → Fixed to: {eng_obj[key]}")
                            # Check if this is text_color field
                            elif key == "text_color" and isinstance(mapped_obj[key], dict):
                                if "hex" in mapped_obj[key] and mapped_obj[key]["hex"].lower() == "#337ab7":
                                    if "hex" in eng_obj[key]:
                                        print(f"   Found #337AB7 at {path}.text_color.hex")
                                        mapped_obj[key]["hex"] = eng_obj[key]["hex"]
                                        print(f"   → Fixed to: {eng_obj[key]['hex']}")
                            # Recurse into nested objects
                            elif isinstance(eng_obj[key], (dict, list)):
                                fix_colors(eng_obj[key], mapped_obj[key], f"{path}.{key}")
                
                elif isinstance(eng_obj, list) and isinstance(mapped_obj, list):
                    for i in range(min(len(eng_obj), len(mapped_obj))):
                        if isinstance(eng_obj[i], (dict, list)):
                            fix_colors(eng_obj[i], mapped_obj[i], f"{path}[{i}]")
            
            # Fix the data
            fix_colors(english_data.get("entry", english_data), 
                      mapped_data.get("entry", mapped_data))
            
            # Save fixed file
            with open(mapped_file, 'w', encoding='utf-8') as f:
                json.dump(mapped_data, f, indent=2, ensure_ascii=False)
            
            print(f"   ✅ Fixed and saved {mapped_file.name}")
            fixed_count += 1
    
    print(f"\n{'='*60}")
    print(f"📊 Summary:")
    print(f"   Total files checked: {total_files}")
    print(f"   Files fixed: {fixed_count}")
    print(f"   Files already correct: {total_files - fixed_count}")
    print(f"{'='*60}")
    print(f"\n⚠️  IMPORTANT: You MUST re-upload the training data to Pinecone:")
    print(f"   python mapping_data_uploader.py")

if __name__ == "__main__":
    fix_training_data()
