"""
Contentstack API Client
Handles all Contentstack API operations including entry creation, publishing, and workflow management
"""

import requests
import time
import json
from typing import Dict, List, Optional, Any


class ContentstackAPI:
    def __init__(self, api_key: str, management_token: str, base_url: str, auth_token: str = None, environment_uid: str = None):
        """
        Initialize Contentstack API client
        
        Args:
            api_key: Contentstack API key
            management_token: Contentstack management token
            base_url: Contentstack API base URL
            auth_token: Optional auth token
            environment_uid: Environment UID for publishing
        """
        self.api_key = api_key
        self.management_token = management_token
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.environment_uid = environment_uid
        
        if not self.base_url or self.base_url.strip() == '':
            raise ValueError('ContentstackAPI base_url is required and cannot be empty')
        
        print(f"[CONTENTSTACK] Initializing with baseURL: {self.base_url}")
        
        self.headers = {
            'api_key': self.api_key,
            'authorization': self.management_token,
            'Content-Type': 'application/json'
        }
        
        # Rate limiting - optimized for performance
        self.max_retries = 0  # Changed from 5 to 0 - no retries
        self.retry_delay = 2
        self.rate_limit_delay = 0.1  # Reduced from 1s to 0.1s for faster execution

    def _make_request(self, method: str, url: str, data: Dict = None, params: Dict = None, retries: int = 0) -> Dict:
        """
        Make HTTP request with retry logic
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL for the request
            data: Request payload
            params: Query parameters
            retries: Current retry count
            
        Returns:
            Response data as dictionary
        """
        try:
            time.sleep(self.rate_limit_delay)
            
            if method == 'GET':
                response = requests.get(url, headers=self.headers, params=params)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data, params=params)
            elif method == 'PUT':
                response = requests.put(url, headers=self.headers, json=data, params=params)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                if retries < self.max_retries:
                    wait_time = self.retry_delay * (retries + 1)
                    print(f"Rate limited. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    return self._make_request(method, url, data, params, retries + 1)
                else:
                    raise Exception(f"Max retries exceeded for rate limiting")
            
            response.raise_for_status()
            return response.json() if response.text else {}
            
        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                print(f"Request failed. Retrying... ({retries + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                return self._make_request(method, url, data, params, retries + 1)
            else:
                # Preserve error structure for better error handling
                error_response = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_response = e.response.json()
                    except:
                        error_response = {'message': e.response.text}
                
                raise Exception(f"Request failed after {self.max_retries} retries: {str(e)}") from e

    def create_entry(self, content_type_uid: str, entry_data: Dict, entry_reuse_enabled: bool = True, locale: str = 'en-us') -> Dict:
        """
        Create a new entry
        
        Args:
            content_type_uid: Content type UID
            entry_data: Entry data
            entry_reuse_enabled: Whether to append timestamp to title
            locale: Locale (default: en-us)
            
        Returns:
            Created entry data with UID
        """
        # Append current timestamp to title field if it exists and reuse is disabled
        if 'title' in entry_data and not entry_reuse_enabled:
            timestamp = int(time.time() * 1000)
            entry_data['title'] = f"{entry_data['title']} - {timestamp}"
            print(f"[CONTENTSTACK] Updated title with timestamp: {entry_data['title']}")
        
        payload = {'entry': entry_data}
        
        url = f"{self.base_url}/content_types/{content_type_uid}/entries"
        params = {'locale': locale}
        
        print(f"[CONTENTSTACK] Creating entry for content type: {content_type_uid}")
        print(f"[CONTENTSTACK] Request payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = self._make_request('POST', url, payload, params)
            
            entry_uid = response.get('entry', {}).get('uid')
            print(f"[CONTENTSTACK] Entry created successfully with UID: {entry_uid}")
            
            return {
                'success': True,
                'entry_uid': entry_uid,
                'data': response
            }
        except Exception as error:
            print(f"[CONTENTSTACK] Error creating entry: {str(error)}")
            print(f"[CONTENTSTACK] Complete error details:")
            print(f"Error: {str(error)}")
            
            # Preserve error structure for duplicate detection
            if hasattr(error, '__cause__') and hasattr(error.__cause__, 'response'):
                try:
                    error_data = error.__cause__.response.json()
                    raise Exception(f"Failed to create entry in Contentstack: {error_data.get('error_message', str(error))}")
                except:
                    pass
            
            raise Exception(f"Failed to create entry in Contentstack: {str(error)}")

    def get_entry(self, content_type_uid: str, entry_uid: str, locale: str = 'en-us') -> Dict:
        """
        Get entry by UID
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            locale: Locale (default: en-us)
            
        Returns:
            Entry data
        """
        url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}"
        params = {'locale': locale}
        
        print(f"[CONTENTSTACK] Getting entry: {content_type_uid}/{entry_uid}")
        response = self._make_request('GET', url, params=params)
        return response

    def update_entry(self, content_type_uid: str, entry_uid: str, entry_data: Dict, locale: str = 'en-us') -> Dict:
        """
        Update an existing entry
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            entry_data: Updated entry data
            locale: Locale (default: en-us)
            
        Returns:
            Updated entry data
        """
        url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}"
        params = {'locale': locale}
        
        payload = {'entry': entry_data}
        
        print(f"[CONTENTSTACK] Updating entry: {content_type_uid}/{entry_uid}")
        response = self._make_request('PUT', url, payload, params)
        
        return {
            'success': True,
            'data': response
        }

    def delete_entry(self, content_type_uid: str, entry_uid: str, locale: str = 'en-us') -> Dict:
        """
        Delete an entry (with unpublish if needed)
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            locale: Locale (default: en-us)
            
        Returns:
            Deletion response with success status
        """
        url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}"
        params = {'locale': locale}
        
        print(f"[CONTENTSTACK] Deleting entry: {content_type_uid}/{entry_uid}")
        
        try:
            # Attempt to delete the entry
            time.sleep(self.rate_limit_delay)
            response = requests.delete(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            print(f"[CONTENTSTACK] ✅ Entry deleted successfully")
            return {
                'success': True,
                'data': response.json() if response.text else {}
            }
            
        except requests.exceptions.HTTPError as e:
            # Check if it's a 422 error (entry is published or in workflow)
            if e.response.status_code == 422:
                print(f"[CONTENTSTACK] ⚠️ Entry deletion blocked (422) - entry may be published or in workflow")
                
                # Try to unpublish first, then delete
                try:
                    print(f"[CONTENTSTACK] Step 1: Attempting to unpublish entry...")
                    unpublish_url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}/unpublish"
                    
                    # Get entry to check if it has environment info
                    try:
                        get_response = requests.get(url, headers=self.headers, params=params)
                        entry_data = get_response.json().get('entry', {})
                        
                        # Prepare unpublish payload
                        unpublish_payload = {
                            'entry': {
                                'locales': [locale],
                                'environments': [self.environment_uid] if self.environment_uid else []
                            }
                        }
                        
                        # CRITICAL: Use authtoken for unpublish operation
                        unpublish_headers = self.headers.copy()
                        if self.auth_token:
                            unpublish_headers['authtoken'] = self.auth_token
                            del unpublish_headers['authorization']
                        
                        # Attempt unpublish
                        unpublish_response = requests.post(unpublish_url, headers=unpublish_headers, json=unpublish_payload, params=params)
                        if unpublish_response.status_code in [200, 201]:
                            print(f"[CONTENTSTACK] ✅ Entry unpublished successfully")
                            time.sleep(0.2)  # Reduced from 1s to 0.2s
                        else:
                            print(f"[CONTENTSTACK] ℹ️ Unpublish status: {unpublish_response.status_code}")
                    except Exception as unpublish_error:
                        print(f"[CONTENTSTACK] ℹ️ Unpublish attempt: {str(unpublish_error)}")
                    
                    # Step 2: Try to remove from workflow
                    print(f"[CONTENTSTACK] Step 2: Attempting to remove from workflow...")
                    workflow_url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}/workflow"
                    
                    try:
                        workflow_delete = requests.delete(workflow_url, headers=self.headers, params=params)
                        if workflow_delete.status_code in [200, 201, 204]:
                            print(f"[CONTENTSTACK] ✅ Removed from workflow")
                            time.sleep(0.1)  # Reduced from 0.5s to 0.1s
                    except Exception as workflow_error:
                        print(f"[CONTENTSTACK] ℹ️ Workflow removal: {str(workflow_error)}")
                    
                    # Step 3: Retry deletion
                    print(f"[CONTENTSTACK] Step 3: Retrying deletion...")
                    time.sleep(0.2)  # Reduced from 1s to 0.2s
                    response = requests.delete(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    
                    print(f"[CONTENTSTACK] ✅ Entry deleted successfully after unpublish")
                    return {
                        'success': True,
                        'data': response.json() if response.text else {}
                    }
                    
                except Exception as retry_error:
                    # Check if entry is actually deleted (404)
                    if hasattr(retry_error, 'response') and retry_error.response is not None:
                        if retry_error.response.status_code == 404:
                            print(f"[CONTENTSTACK] ✅ Entry appears to be already deleted (404)")
                            return {'success': True, 'already_deleted': True}
                    
                    # If still failing, mark as success if error suggests it's already deleted
                    error_msg = str(retry_error).lower()
                    if 'not found' in error_msg or '404' in error_msg:
                        print(f"[CONTENTSTACK] ✅ Entry not found - already deleted")
                        return {'success': True, 'already_deleted': True}
                    
                    print(f"[CONTENTSTACK] ⚠️ Could not delete entry after unpublish/workflow removal")
                    print(f"[CONTENTSTACK] ℹ️ Entry may require manual deletion or is in a protected state")
                    return {'success': False, 'error': str(e), 'protected': True}
            
            # For 404, entry is already deleted (success)
            elif e.response.status_code == 404:
                print(f"[CONTENTSTACK] ℹ️ Entry not found (404) - already deleted")
                return {'success': True, 'already_deleted': True}
            
            else:
                print(f"[CONTENTSTACK] ❌ Error deleting entry: {str(e)}")
                return {'success': False, 'error': str(e)}
                
        except Exception as error:
            print(f"[CONTENTSTACK] ❌ Error deleting entry: {str(error)}")
            return {'success': False, 'error': str(error)}

    def search_entries(self, content_type_uid: str, query: Dict, locale: str = 'en-us') -> List[Dict]:
        """
        Search entries by query
        
        Args:
            content_type_uid: Content type UID
            query: Search query parameters
            locale: Locale (default: en-us)
            
        Returns:
            List of matching entries
        """
        url = f"{self.base_url}/content_types/{content_type_uid}/entries"
        
        params = {'locale': locale}
        for key, value in query.items():
            params[f'query[{key}]'] = value
        
        print(f"[CONTENTSTACK] Searching entries: {content_type_uid}")
        response = self._make_request('GET', url, params=params)
        return response.get('entries', [])

    def update_workflow_stage(self, content_type_uid: str, entry_uid: str, stage_uid: str, locale: str = 'en-us') -> Dict:
        """
        Update workflow stage of an entry
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            stage_uid: Target stage UID
            locale: Locale (default: en-us)
            
        Returns:
            Workflow update response
        """
        # Skip workflow for content_divider
        if content_type_uid == 'content_divider':
            print(f"[CONTENTSTACK] Skipping workflow update for content_divider")
            return {'success': True}
        
        url = f"{self.base_url}/content_types/{content_type_uid}/entries/{entry_uid}/workflow"
        params = {'locale': locale}
        
        payload = {
            'workflow': {
                'workflow_stage': {
                    'uid': stage_uid
                }
            }
        }
        
        print(f"[CONTENTSTACK] Updating workflow stage for entry: {content_type_uid}/{entry_uid} to stage: {stage_uid}")
        
        # CRITICAL: Use authtoken for Approved stage (blt0915ab57da3d0af1)
        # This is required by Contentstack for final approval
        headers = self.headers.copy()
        if stage_uid == 'blt0915ab57da3d0af1' and self.auth_token:
            print(f"[CONTENTSTACK] Using authtoken for Approved stage")
            headers['authtoken'] = self.auth_token
            del headers['authorization']
        
        # Make request with custom headers
        try:
            time.sleep(self.rate_limit_delay)
            response = requests.post(url, headers=headers, json=payload, params=params)
            response.raise_for_status()
            
            print(f"[CONTENTSTACK] ✅ Workflow stage updated successfully")
            return {
                'success': True,
                'data': response.json() if response.text else {}
            }
        except requests.exceptions.RequestException as e:
            print(f"[CONTENTSTACK] ❌ Error updating workflow: {str(e)}")
            raise Exception(f"Failed to update workflow stage: {str(e)}")
    
    def create_asset_reference(self, asset_id: str, cdn_url: str, filename: str, 
                               extension: str, dimensions: Dict = None, 
                               mimetype: str = None, thumbnail_url: str = None) -> Dict:
        """
        Create an asset reference object for Contentstack entries
        
        Args:
            asset_id: The Brandfolder asset ID
            cdn_url: The CDN URL of the asset
            filename: The filename of the asset
            extension: The file extension
            dimensions: Optional dimensions dict with 'width' and 'height'
            mimetype: Optional MIME type (will be auto-detected if not provided)
            thumbnail_url: Optional thumbnail URL
            
        Returns:
            Asset reference object ready for Contentstack
        """
        asset_reference = {
            'id': asset_id,
            'url': cdn_url,
            'filename': filename,
            'extension': extension,
            'dimensions': dimensions or {}
        }
        
        # Add mimetype if provided, otherwise generate from extension
        if mimetype:
            asset_reference['mimetype'] = mimetype
        elif extension:
            asset_reference['mimetype'] = self.get_mime_type(extension)
        
        # Add thumbnailUrl if provided
        if thumbnail_url:
            asset_reference['thumbnail_url'] = thumbnail_url
        
        return asset_reference
    
    def get_mime_type(self, extension: str) -> str:
        """
        Get MIME type from file extension
        
        Args:
            extension: File extension
            
        Returns:
            MIME type string
        """
        mime_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'bmp': 'image/bmp',
            'webp': 'image/webp',
            'svg': 'image/svg+xml',
            'mp4': 'video/mp4',
            'mov': 'video/quicktime',
            'avi': 'video/x-msvideo',
            'wmv': 'video/x-ms-wmv',
            'flv': 'video/x-flv',
            'mkv': 'video/x-matroska',
            'webm': 'video/webm',
            'pdf': 'application/pdf',
            'vtt': 'text/vtt'
        }
        return mime_types.get(extension.lower(), 'application/octet-stream')

    def publish_entry_with_deep_publish(self, content_type_uid: str, entry_uid: str, 
                                       environments: List[str] = None, locales: List[str] = None,
                                       locale: str = 'en-us') -> Dict:
        """
        Publish an entry with deep publish using bulk publish API
        Uses authtoken authentication for bulk publish endpoint
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            environments: Environment UIDs to publish to (e.g., ['bltabc123...'])
            locales: Locales to publish (default: ['en-us'])
            locale: Locale (default: en-us)
            
        Returns:
            Publish response
        """
        if locales is None:
            locales = ['en-us']
        
        # CRITICAL FIX: Use actual environment UID, not string "production"
        if environments is None or environments == ['production']:
            if self.environment_uid:
                environments = [self.environment_uid]
                print(f"[CONTENTSTACK] ⚠️ Using environment UID from config: {self.environment_uid}")
            else:
                raise ValueError("Environment UID is required for publishing. Pass environments parameter or set environment_uid in config.")
        
        print(f"[CONTENTSTACK] Publishing entry: {content_type_uid}/{entry_uid}")
        print(f"[CONTENTSTACK] Deep publish: enabled (bulk API)")
        print(f"[CONTENTSTACK] Environment UIDs: {environments}")
        print(f"[CONTENTSTACK] Locales: {locales}")
        
        # Validate authtoken is present
        if not self.auth_token or not self.auth_token.strip():
            raise ValueError("auth_token is required for bulk publish. Please set CONTENTSTACK_AUTH_TOKEN in .env")
        
        # Bulk publish payload format
        payload = {
            "entries": [
                {
                    "uid": entry_uid,
                    "content_type": content_type_uid,
                    "locale": locales[0],
                    "version": 1
                }
            ],
            "locales": locales,
            "environments": environments,
            "rules": {"approvals": True},
            "publish_with_reference": True,  # Enable deep publish
            "skip_workflow_stage_check": True
        }
        
        # Create special headers with authtoken for bulk publish
        import random
        cache_buster = random.random()
        
        publish_headers = {
            "api_key": self.api_key,
            "Content-Type": "application/json",
            "authtoken": self.auth_token,  # CRITICAL: Use authtoken, not authorization
            "api_version": "3.2"
        }
        
        # Bulk publish endpoint
        url = f"{self.base_url}/bulk/publish"
        params = {
            "x-bulk-action": "publish",
            "approvals": "true",
            "skip_workflow_stage_check": "true",
            "publish_all_localized": "true",
            "r": str(cache_buster)
        }
        
        print(f"[CONTENTSTACK] Using bulk publish endpoint with authtoken")
        print(f"[CONTENTSTACK] Payload: {json.dumps(payload, indent=2)}")
        
        try:
            # Reduced delay for faster execution
            time.sleep(0.2)  # Reduced from 1s to 0.2s
            response = requests.post(url, headers=publish_headers, json=payload, params=params)
            response.raise_for_status()
            
            print(f"[CONTENTSTACK] ✅ Entry published successfully with deep publish")
            return {
                'success': True,
                'data': response.json() if response.text else {}
            }
        except Exception as error:
            print(f"[CONTENTSTACK] ❌ Error publishing entry: {str(error)}")
            raise Exception(f"Failed to publish entry: {str(error)}")

    def get_workflow_details(self, content_type_uid: str, entry_uid: str) -> Dict:
        """
        Get workflow details for an entry
        
        Args:
            content_type_uid: Content type UID
            entry_uid: Entry UID
            
        Returns:
            Workflow details
        """
        entry_data = self.get_entry(content_type_uid, entry_uid)
        return entry_data.get('entry', {}).get('_workflow', {})

    def get_all_entries(self, content_type_uid: str, locale: str = 'en-us', 
                       skip: int = 0, limit: int = 100) -> List[Dict]:
        """
        Get all entries of a content type with pagination
        
        Args:
            content_type_uid: Content type UID
            locale: Locale (default: en-us)
            skip: Number of entries to skip
            limit: Number of entries to fetch
            
        Returns:
            List of entries
        """
        url = f"{self.base_url}/content_types/{content_type_uid}/entries"
        params = {'locale': locale, 'skip': skip, 'limit': limit}
        
        print(f"[CONTENTSTACK] Getting all entries: {content_type_uid} (skip={skip}, limit={limit})")
        response = self._make_request('GET', url, params=params)
        return response.get('entries', [])
    
    def search_entry_by_title(self, content_type_uid: str, title: str, locale: str = 'en-us') -> Dict:
        """
        Search for an entry by title with migration tag
        
        Args:
            content_type_uid: Content type UID
            title: Entry title to search for
            locale: Locale (default: en-us)
            
        Returns:
            Dictionary with search results
        """
        print(f"[CONTENTSTACK] Searching for entry with title: \"{title}\"")
        print(f"[CONTENTSTACK] Content type: {content_type_uid}")
        
        url = f"{self.base_url}/content_types/{content_type_uid}/entries"
        params = {
            'locale': locale,
            'query': json.dumps({'title': title}),
            'limit': 10  # Limit results to avoid large responses
        }
        
        try:
            response = self._make_request('GET', url, params=params)
            print(f"[CONTENTSTACK] Entry search response: {json.dumps(response, indent=2)}")
            
            entries = response.get('entries', [])
            
            # Look for exact title match AND presence of "migrated-from-cms" tag
            exact_match = None
            for entry in entries:
                title_matches = entry.get('title') == title
                has_migration_tag = (
                    'tags' in entry and 
                    isinstance(entry['tags'], list) and 
                    'migrated-from-cms' in entry['tags']
                )
                
                print(f"[CONTENTSTACK] Entry {entry.get('uid')} - Title match: {title_matches}, Migration tag: {'✅' if has_migration_tag else '❌'}")
                print(f"[CONTENTSTACK] Entry tags: {json.dumps(entry.get('tags', [])) if entry.get('tags') else 'No tags'}")
                
                if title_matches and has_migration_tag:
                    exact_match = entry
                    break
            
            if exact_match:
                print(f"[CONTENTSTACK] Found existing entry with UID: {exact_match.get('uid')} (title + migration tag match)")
                return {
                    'success': True,
                    'found': True,
                    'entry': exact_match,
                    'entry_uid': exact_match.get('uid')
                }
            else:
                print(f"[CONTENTSTACK] No existing entry found with title \"{title}\" AND \"migrated-from-cms\" tag")
                title_only_matches = len([e for e in entries if e.get('title') == title])
                if title_only_matches > 0:
                    print(f"[CONTENTSTACK] Found {title_only_matches} entries with matching title but without migration tag - will create new entry")
                return {
                    'success': True,
                    'found': False,
                    'entries': entries
                }
        except Exception as error:
            print(f"[CONTENTSTACK] Error searching for entry: {str(error)}")
            # Don't throw error for search failures, just return not found
            print(f"[CONTENTSTACK] Search failed, will proceed with entry creation")
            return {
                'success': False,
                'found': False,
                'error': str(error)
            }
    
    # Async wrapper methods using run_in_executor
    async def create_entry_async(self, content_type_uid: str, entry_data: Dict, entry_reuse_enabled: bool = True, locale: str = 'en-us') -> Dict:
        """Async wrapper for create_entry"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.create_entry(content_type_uid, entry_data, entry_reuse_enabled, locale))
    
    async def delete_entry_async(self, content_type_uid: str, entry_uid: str, locale: str = 'en-us') -> Dict:
        """Async wrapper for delete_entry"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.delete_entry(content_type_uid, entry_uid, locale))
    
    async def update_workflow_stage_async(self, content_type_uid: str, entry_uid: str, workflow_stage_uid: str, locale: str = 'en-us') -> Dict:
        """Async wrapper for update_workflow_stage"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.update_workflow_stage(content_type_uid, entry_uid, workflow_stage_uid, locale))
    
    async def publish_entry_with_deep_publish_async(self, content_type_uid: str, entry_uid: str, environments: List[str], locales: List[str], locale: str = 'en-us') -> Dict:
        """Async wrapper for publish_entry_with_deep_publish"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.publish_entry_with_deep_publish(content_type_uid, entry_uid, environments, locales, locale))
    
    async def search_entry_by_title_async(self, content_type_uid: str, title: str, locale: str = 'en-us') -> Dict:
        """Async wrapper for search_entry_by_title"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.search_entry_by_title(content_type_uid, title, locale))
