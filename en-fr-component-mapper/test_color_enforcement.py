"""
Quick test to verify color enforcement works
"""
import json
from mapping_data_retriever import MappingDataRetriever

# Simulate English and LLM-generated (bad) French
english_data = {
    "entry": {
        "locale": "en-ca",
        "color_config": {
            "background_gradient_style": "solid",
            "background_color": {"hex": "#FFFFFF"},
            "background_gradient_color": {
                "color1": {"hex": ""},
                "color2": {"hex": ""}
            },
            "text_color": {"hex": "#333333"},  # ← CORRECT COLOR (dark gray)
            "border_color_type": "no-border",
            "border_color": {
                "solid": {"hex": ""},
                "shadow": {"hex": ""}
            }
        },
        "link_list": []
    }
}

# Simulate LLM output with WRONG color
llm_output = {
    "entry": {
        "locale": "fr-ca",
        "color_config": {
            "background_gradient_style": "solid",
            "background_color": {"hex": "#FFFFFF"},
            "background_gradient_color": {
                "color1": {"hex": ""},
                "color2": {"hex": ""}
            },
            "text_color": {"hex": "#337AB7"},  # ← WRONG COLOR (blue)
            "border_color_type": "no-border",
            "border_color": {
                "solid": {"hex": ""},
                "shadow": {"hex": ""}
            }
        },
        "link_list": []
    }
}

print("🧪 Testing color enforcement...")
print(f"\n📊 BEFORE enforcement:")
print(f"   English text_color: {english_data['entry']['color_config']['text_color']['hex']}")
print(f"   LLM output text_color: {llm_output['entry']['color_config']['text_color']['hex']}")

# Create retriever and test enforcement
retriever = MappingDataRetriever(
    index_name="en-fr-component-mapping",
    pinecone_api_key="dummy",  # Not needed for this test
    openai_api_key="dummy",
    anthropic_api_key="dummy"
)

# Call the enforcement method
corrected = retriever.enforce_styling_preservation(
    english_data=english_data,
    mapped_json=llm_output,
    component_type="link_list_with_flyout_references"
)

print(f"\n✅ AFTER enforcement:")
print(f"   Corrected text_color: {corrected['entry']['color_config']['text_color']['hex']}")

if corrected['entry']['color_config']['text_color']['hex'] == "#333333":
    print(f"\n🎉 SUCCESS! Color was corrected from #337AB7 to #333333")
else:
    print(f"\n❌ FAILED! Color is still wrong: {corrected['entry']['color_config']['text_color']['hex']}")

print(f"\n📋 Full corrected color_config:")
print(json.dumps(corrected['entry']['color_config'], indent=2))
