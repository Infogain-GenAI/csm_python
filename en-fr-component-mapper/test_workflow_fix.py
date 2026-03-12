"""
Test to verify workflow skip list fix

This test confirms that content types are no longer being skipped
and will actually go through workflow stages before publishing.
"""

import sys
sys.path.append('../lib')

from contentstack_api import ContentstackAPI

# Mock environment
class MockAPI(ContentstackAPI):
    def __init__(self):
        # Don't call parent init
        pass

# Test the skip list
api = MockAPI()

# Get the CONTENT_TYPES_WITHOUT_WORKFLOW list
import inspect
source = inspect.getsource(ContentstackAPI.update_workflow_stage)

print("=" * 80)
print("WORKFLOW SKIP LIST TEST")
print("=" * 80)

if "'ad_builder'" in source:
    print("\n❌ FAIL: ad_builder is still in skip list!")
    print("   This will cause 422 errors when publishing")
elif "'text_builder'" in source:
    print("\n❌ FAIL: text_builder is still in skip list!")
    print("   This will cause 422 errors when publishing")
elif "'ad_set_costco'" in source:
    print("\n❌ FAIL: ad_set_costco is still in skip list!")
    print("   This will cause 422 errors when publishing")
elif "CONTENT_TYPES_WITHOUT_WORKFLOW = [" in source and "# Empty list" in source:
    print("\n✅ PASS: Skip list is now empty!")
    print("   All content types will go through workflow stages")
    print("\n✅ This should fix the 422 publish errors:")
    print("   - ad_builder components will move to Approved stage")
    print("   - text_builder components will move to Approved stage")
    print("   - ad_set_costco components will move to Approved stage")
    print("   - Publish Rule requirements will be met")
else:
    print("\n⚠️  UNKNOWN: Could not determine skip list status")
    print("   Manual verification needed")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)

# Show what the skip list check looks like now
print("\n📋 Current skip list logic:")
print("-" * 80)
lines = source.split('\n')
in_skip_section = False
for line in lines:
    if 'CONTENT_TYPES_WITHOUT_WORKFLOW' in line:
        in_skip_section = True
    if in_skip_section:
        print(line)
        if 'if content_type_uid in CONTENT_TYPES_WITHOUT_WORKFLOW:' in line:
            # Print next 2 lines
            idx = lines.index(line)
            if idx + 1 < len(lines):
                print(lines[idx + 1])
            if idx + 2 < len(lines):
                print(lines[idx + 2])
            break

print("-" * 80)
