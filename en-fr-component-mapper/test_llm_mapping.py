"""
Test LLM-based Mapping Integration
Quick test to verify the LLM mapping works with actual dataset
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from mapping_data_retriever import MappingDataRetriever

def test_text_builder():
    """Test text_builder mapping"""
    print("\n" + "="*60)
    print("TEST 1: text_builder Mapping")
    print("="*60)
    
    # Load test data
    data_dir = Path(__file__).parent / "component_data" / "text_builder"
    
    with open(data_dir / "english_input_2.json", 'r', encoding='utf-8') as f:
        english_data = json.load(f)
    
    with open(data_dir / "french_input_2.json", 'r', encoding='utf-8') as f:
        french_data = json.load(f)
    
    # Initialize retriever
    retriever = MappingDataRetriever(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
    )
    
    # Process mapping
    result = retriever.process_mapping(
        english_data=english_data,
        french_data=french_data,
        component_type="text_builder",
        n_examples=3
    )
    
    print(f"\n✅ Mapping completed!")
    print(f"Confidence: {result.confidence_score:.3f}")
    print(f"Similar examples used: {len(result.similar_examples)}")
    print(f"\nReasoning:")
    print(result.reasoning)
    
    # Save output
    output_file = Path(__file__).parent / "test_output_text_builder.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result.mapped_json, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Output saved to: {output_file}")
    
    return result


def test_ad_set_costco():
    """Test ad_set_costco mapping"""
    print("\n" + "="*60)
    print("TEST 2: ad_set_costco Mapping")
    print("="*60)
    
    # Load test data
    data_dir = Path(__file__).parent / "component_data" / "ad_set_costco"
    
    with open(data_dir / "english_input_1.json", 'r', encoding='utf-8') as f:
        english_data = json.load(f)
    
    with open(data_dir / "french_input_1.json", 'r', encoding='utf-8') as f:
        french_data = json.load(f)
    
    # Initialize retriever
    retriever = MappingDataRetriever(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY")
    )
    
    # Process mapping
    result = retriever.process_mapping(
        english_data=english_data,
        french_data=french_data,
        component_type="ad_set_costco",
        n_examples=3
    )
    
    print(f"\n✅ Mapping completed!")
    print(f"Confidence: {result.confidence_score:.3f}")
    print(f"Similar examples used: {len(result.similar_examples)}")
    print(f"\nReasoning:")
    print(result.reasoning)
    
    # Save output
    output_file = Path(__file__).parent / "test_output_ad_set_costco.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result.mapped_json, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Output saved to: {output_file}")
    
    return result


def main():
    # Load environment
    load_dotenv()
    
    # Check API keys
    required_keys = ["OPENAI_API_KEY", "PINECONE_API_KEY", "ANTHROPIC_API_KEY"]
    missing_keys = [key for key in required_keys if not os.getenv(key)]
    
    if missing_keys:
        print(f"❌ Missing API keys: {', '.join(missing_keys)}")
        print("Please set them in .env file")
        return 1
    
    print("\n" + "="*60)
    print("LLM-BASED MAPPING TEST SUITE")
    print("="*60)
    print("\nThis will test the mapping system with actual examples")
    print("from your component_data directory.")
    
    try:
        # Test text_builder
        test_text_builder()
        
        # Test ad_set_costco
        test_ad_set_costco()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
