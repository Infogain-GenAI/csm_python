"""
JSON Cleanup Utility
Removes specific keys and handles URL field based on regex pattern
Fetches content from Contentstack API when _content_type_uid and uid are present
"""

import re
from typing import Any, Dict, List


class JSONCleanup:
    def __init__(self, contentstack_api=None):
        """
        Initialize JSON Cleanup utility
        
        Args:
            contentstack_api: ContentstackAPI instance for fetching nested content
        """
        self.contentstack_api = contentstack_api
        
        # Keys to always remove
        self.keys_to_remove = [
            '_version', 'uid', '_in_progress', '_metadata', 'ACL', 
            'publish_details', 'created_at', 'createdAt', 'updatedAt',
            'created_by', 'updated_at', 'updated_by', 'supported',
            'mediaType', 'apiDto', 'isProcessing', 'assetId', 'sizeInBytes'
        ]
        
        # Regex pattern for URL removal
        self.url_removal_pattern = re.compile(r'blt[0-9a-z]+')

    def cleanup_json(self, data: Any) -> Any:
        """
        Clean JSON data by removing specific keys and handling URL field
        
        Args:
            data: The JSON data to clean
            
        Returns:
            The cleaned JSON data
        """
        return self._process_object(data)

    def _process_object(self, obj: Any) -> Any:
        """
        Recursively process object to clean data
        
        Args:
            obj: Object to process
            
        Returns:
            Cleaned object
        """
        if obj is None or not isinstance(obj, (dict, list)):
            return obj
        
        if isinstance(obj, list):
            processed_array = []
            for item in obj:
                processed_item = self._process_object(item)
                processed_array.append(processed_item)
            return processed_array
        
        # Check if this object needs content fetching from Contentstack
        if isinstance(obj, dict) and '_content_type_uid' in obj and 'uid' in obj:
            try:
                content_type_uid = obj['_content_type_uid']
                uid = obj['uid']
                
                print(f"Fetching content for {content_type_uid} with uid: {uid}")
                
                if self.contentstack_api:
                    fetched_content = self.contentstack_api.get_entry(content_type_uid, uid)
                    
                    if fetched_content and 'entry' in fetched_content:
                        # Clean the fetched content recursively
                        cleaned_fetched_content = self._process_object(fetched_content['entry'])
                        
                        # Create new object with _content_type_uid and entry
                        result = {
                            '_content_type_uid': content_type_uid,
                            'entry': cleaned_fetched_content
                        }
                        
                        print(f"Successfully fetched and processed content for {content_type_uid}")
                        return result
                        
            except Exception as error:
                print(f"Failed to fetch content for {obj.get('_content_type_uid')} with uid {obj.get('uid')}: {str(error)}")
                print(f"Complete error details: {error}")
                # Continue with normal processing if API call fails
        
        cleaned = {}
        
        for key, value in obj.items():
            # Skip keys that should always be removed
            if key in self.keys_to_remove:
                continue
            
            # Handle URL field with regex pattern
            if key == 'url' and isinstance(value, str) and self.url_removal_pattern.search(value):
                continue  # Remove URL if it matches the pattern
            
            # Recursively process nested objects and arrays
            processed_value = self._process_object(value)
            
            # For objects with _content_type_uid, keep the structure
            if isinstance(processed_value, dict) and '_content_type_uid' in processed_value and 'entry' in processed_value:
                cleaned[key] = processed_value
            else:
                cleaned[key] = processed_value
        
        # Check if this is an entry object that needs restructuring
        if '_content_type_uid' in obj and not ('entry' in cleaned):
            content_type_uid = obj['_content_type_uid']
            
            # Separate _content_type_uid from entry data
            entry_data = {}
            for key, value in cleaned.items():
                if key != '_content_type_uid':
                    entry_data[key] = value
            
            # Return restructured object
            return {
                '_content_type_uid': content_type_uid,
                'entry': entry_data
            }
        
        return cleaned
