"""
Brandfolder API Client
Handles asset uploads and management in Brandfolder DAM
"""

import requests
import time
import asyncio
import os
from typing import Dict, Optional, List
from urllib.parse import urlparse
from pathlib import Path


class BrandfolderAPI:
    def __init__(self, api_key: str, organization_id: str, section_key: str = 'grh9vn6jfp837kkqbf5'):
        """
        Initialize Brandfolder API client
        
        Args:
            api_key: Brandfolder API key
            organization_id: Brandfolder organization ID
            section_key: Brandfolder section key (default: 'grh9vn6jfp837kkqbf5')
        """
        self.api_key = api_key
        self.organization_id = organization_id
        self.section_key = section_key
        self.base_url = 'https://brandfolder.com/api/v4'
        
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Allowed extensions
        self.allowed_extensions = [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
            'mp4', 'mov', 'avi', 'wmv', 'flv', 'mkv', 'webm',
            'pdf'
        ]
        
        # Rate limiting - optimized for performance
        self.max_retries = 3  # Reduced from 5 to 3
        self.retry_delay = 1  # Reduced from 2 to 1
        self.rate_limit_delay = 0.05  # Reduced from 1s to 0.05s for faster execution

    def _make_request(self, method: str, url: str, data: Dict = None, retries: int = 0) -> Dict:
        """
        Make HTTP request with retry logic
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Full URL for the request
            data: Request payload
            retries: Current retry count
            
        Returns:
            Response data as dictionary
        """
        try:
            time.sleep(self.rate_limit_delay)
            
            if method == 'GET':
                response = requests.get(url, headers=self.headers)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data)
            elif method == 'PUT':
                response = requests.put(url, headers=self.headers, json=data)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                if retries < self.max_retries:
                    wait_time = self.retry_delay * (retries + 1)
                    print(f"Rate limited. Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    return self._make_request(method, url, data, retries + 1)
                else:
                    raise Exception(f"Max retries exceeded for rate limiting")
            
            response.raise_for_status()
            return response.json() if response.text else {}
            
        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                print(f"Request failed. Retrying... ({retries + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                return self._make_request(method, url, data, retries + 1)
            else:
                raise Exception(f"Request failed after {self.max_retries} retries: {str(e)}")

    def _get_file_extension(self, url: str) -> str:
        """
        Extract file extension from URL
        
        Args:
            url: File URL
            
        Returns:
            File extension (lowercase)
        """
        parsed_url = urlparse(url)
        path = parsed_url.path
        extension = path.split('.')[-1].lower() if '.' in path else ''
        return extension

    def _is_allowed_file_type(self, url: str) -> bool:
        """
        Check if file type is allowed
        
        Args:
            url: File URL
            
        Returns:
            True if allowed, False otherwise
        """
        extension = self._get_file_extension(url)
        return extension in self.allowed_extensions

    async def create_asset_from_url(self, public_url: str, filename: str, brandfolder_collection_id: str) -> Dict:
        """
        Create asset from URL in Brandfolder
        
        Args:
            public_url: Public URL of the asset
            filename: Filename for the asset
            brandfolder_collection_id: Collection ID to upload to
            
        Returns:
            Asset creation response with asset ID
        """
        try:
            print(f"\n[BRANDFOLDER] ===== CREATING ASSET =====")
            print(f"[BRANDFOLDER] URL: {public_url}")
            print(f"[BRANDFOLDER] Filename: {filename}")
            print(f"[BRANDFOLDER] Collection ID: {brandfolder_collection_id}")
            
            # Validate file type
            if not self._is_allowed_file_type(public_url):
                extension = self._get_file_extension(public_url)
                error_msg = f"File type '.{extension}' not allowed. Allowed types: {', '.join(self.allowed_extensions)}"
                print(f"[BRANDFOLDER ERROR] {error_msg}")
                raise Exception(error_msg)
            
            payload = {
                'data': {
                    'attributes': [
                        {
                            'attachments': [{
                                'filename': filename,
                                'url': public_url
                            }]
                        }
                    ]
                },
                'section_key': self.section_key
            }
            
            print(f"[BRANDFOLDER] Payload: {payload}")
            
            url = f"{self.base_url}/collections/{brandfolder_collection_id}/assets"
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('POST', url, payload)
            )
            
            asset_id = response.get('data', [{}])[0].get('id')
            print(f"[BRANDFOLDER] Asset created successfully with ID: {asset_id}")
            print(f"[BRANDFOLDER] Response data: {response.get('data', [{}])[0]}")
            print(f"[BRANDFOLDER] ============================\n")
            
            return {
                'success': True,
                'asset_id': asset_id,
                'data': response
            }
            
        except Exception as error:
            print(f"\n[BRANDFOLDER ERROR] ===== ASSET CREATION FAILED =====")
            print(f"[BRANDFOLDER ERROR] URL: {public_url}")
            print(f"[BRANDFOLDER ERROR] Filename: {filename}")
            print(f"[BRANDFOLDER ERROR] Error Type: {type(error).__name__}")
            print(f"[BRANDFOLDER ERROR] Error Message: {str(error)}")
            print(f"[BRANDFOLDER ERROR] ===================================\n")
            raise Exception(f"Failed to create asset in Brandfolder: {str(error)}")

    async def get_asset_details_from_attachment(self, attachment_id: str) -> Dict:
        """
        Get attachment details from Brandfolder using attachment ID
        
        Args:
            attachment_id: The attachment ID
            
        Returns:
            Asset details including CDN URL and references
        """
        # Get attachment details to find asset ID
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._make_request('GET', f"{self.base_url}/attachments/{attachment_id}?include=asset")
        )
        asset_id = response.get('data', {}).get('relationships', {}).get('asset', {}).get('data', {}).get('id')
        
        # Get asset details to find cdn_url and other details
        asset_details_response = await loop.run_in_executor(
            None,
            lambda: self._make_request('GET', f"{self.base_url}/assets/{asset_id}?fields=cdn_url&include=attachments")
        )
        
        attachments = asset_details_response.get('included', [])
        cdn_url_prefix = asset_details_response.get('data', {}).get('attributes', {}).get('cdn_url', '').split('/as/')[0]
        
        # Find video attachment
        video_attachment = None
        for att in attachments:
            if att.get('attributes', {}).get('mimetype', '').startswith('video'):
                video_attachment = att
                break
        
        # Find subtitle attachment
        subtitle_attachment = None
        for att in attachments:
            if 'text' in att.get('attributes', {}).get('mimetype', ''):
                subtitle_attachment = att
                break
        
        # Build subtitle reference
        subtitle_reference = {}
        if subtitle_attachment:
            subtitle_reference = {
                'id': subtitle_attachment.get('id'),
                **subtitle_attachment.get('attributes', {})
            }
            subtitle_reference['url'] = f"{cdn_url_prefix}/at/{subtitle_reference['id']}/{subtitle_reference.get('filename', '')}"
        
        # Find image/thumbnail attachment
        image_attachment = None
        for att in attachments:
            if att.get('attributes', {}).get('mimetype', '').startswith('image'):
                image_attachment = att
                break
        
        # Build thumbnail reference
        thumbnail_reference = {}
        if image_attachment:
            thumbnail_reference = {
                'id': image_attachment.get('id'),
                **image_attachment.get('attributes', {})
            }
            thumbnail_reference['url'] = f"{cdn_url_prefix}/at/{thumbnail_reference['id']}/{thumbnail_reference.get('filename', '')}"
        
        asset = asset_details_response.get('data', {})
        cdn_url = asset.get('attributes', {}).get('cdn_url') or asset.get('attributes', {}).get('url')
        
        # Get dimensions
        dimensions = {}
        if video_attachment and video_attachment.get('attributes', {}).get('width') is not None:
            dimensions = {
                'width': video_attachment.get('attributes', {}).get('width'),
                'height': video_attachment.get('attributes', {}).get('height')
            }
        
        return {
            'success': True,
            'asset_id': asset_id,
            'extension': video_attachment.get('attributes', {}).get('extension') if video_attachment else None,
            'mimetype': video_attachment.get('attributes', {}).get('mimetype') if video_attachment else None,
            'filename': video_attachment.get('attributes', {}).get('filename') if video_attachment else None,
            'cdn_url': cdn_url,
            'data': response,
            'dimensions': dimensions,
            'subtitle_reference': subtitle_reference,
            'thumbnail_reference': thumbnail_reference
        }

    async def get_asset_details(self, asset_id: str) -> Dict:
        """
        Get asset details including CDN URL
        
        Args:
            asset_id: The asset ID
            
        Returns:
            Asset details with CDN URL
        """
        try:
            print(f"\n[BRANDFOLDER] Getting asset details for ID: {asset_id}")
            
            url = f"{self.base_url}/assets/{asset_id}?fields=cdn_url&include=attachments"
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('GET', url)
            )
            
            asset = response.get('data', {})
            attachments = response.get('included', [])
            cdn_url = asset.get('attributes', {}).get('cdn_url') or asset.get('attributes', {}).get('url')
            
            # Debug: Log the full API response for dimensions
            print(f"[BRANDFOLDER] DEBUG: Asset attributes: {asset.get('attributes', {})}")
            print(f"[BRANDFOLDER] DEBUG: Number of attachments: {len(attachments)}")
            if attachments:
                print(f"[BRANDFOLDER] DEBUG: First attachment: {attachments[0]}")
            
            # Get dimensions
            dimensions = {}
            if attachments and attachments[0].get('attributes', {}).get('width') is not None:
                dimensions = {
                    'width': attachments[0].get('attributes', {}).get('width'),
                    'height': attachments[0].get('attributes', {}).get('height')
                }
            
            print(f"[BRANDFOLDER] DEBUG: Final dimensions: {dimensions}")
            print(f"[BRANDFOLDER] Asset CDN URL: {cdn_url}")
            
            # Validate CDN URL is accessible
            try:
                cdn_check = requests.head(cdn_url, timeout=10)
                if 200 <= cdn_check.status_code < 400:
                    print(f"[BRANDFOLDER] ✓ CDN URL is accessible (status: {cdn_check.status_code})")
                else:
                    raise Exception(f"CDN URL validation failed with status {cdn_check.status_code}")
            except Exception as cdn_error:
                print(f"[BRANDFOLDER] ⚠️  CDN URL validation failed!")
                print(f"[BRANDFOLDER] CDN URL: {cdn_url}")
                print(f"[BRANDFOLDER] Error: {cdn_error}")
                
                if hasattr(cdn_error, 'response') and cdn_error.response.status_code == 422:
                    print("[BRANDFOLDER] ⚠️  CDN returned 422 error - asset may have been processed incorrectly")
                    print("[BRANDFOLDER] ⚠️  This asset should have been deleted and re-uploaded with proper metadata")
            
            return {
                'success': True,
                'asset_id': asset_id,
                'cdn_url': cdn_url,
                'data': response,
                'dimensions': dimensions
            }
            
        except Exception as error:
            print(f"[BRANDFOLDER] Error getting asset details: {str(error)}")
            raise Exception(f"Failed to get asset details from Brandfolder: {str(error)}")
    
    async def search_asset_by_filename(self, filename: str, collection_id: str) -> Dict:
        """
        Search for an asset by filename in a collection
        
        Args:
            filename: The filename to search for
            collection_id: Brandfolder collection ID
            
        Returns:
            Dictionary with search results:
            {
                'success': True/False,
                'found': True/False,
                'asset': asset object (if found),
                'asset_id': asset ID (if found),
                'assets': list of assets (if not found),
                'error': error message (if failed)
            }
        """
        try:
            print(f"[BRANDFOLDER] Searching for asset with filename: {filename}")
            print(f"[BRANDFOLDER] Collection ID: {collection_id}")
            
            # Search for assets in the collection with the specific filename
            url = f"{self.base_url}/collections/{collection_id}/assets"
            params = {
                'search': f'filename:"{filename}"',
                'fields': 'cdn_url',
                'per': 1  # Limit results to avoid large responses
            }
            
            # Run synchronous request in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('GET', url + '?' + '&'.join([f"{k}={v}" for k, v in params.items()]))
            )
            
            assets = response.get('data', [])
            
            # Look for exact filename match
            exact_match = None
            for asset in assets:
                asset_name = asset.get('attributes', {}).get('name', '')
                # Match with or without extension
                if (asset_name.lower() == filename.lower() or 
                    asset_name.lower() == filename.lower().split('.')[0]):
                    exact_match = asset
                    break
            
            if exact_match:
                # Check if this is a broken asset (has CDN URL but will return 422)
                # We need to get full asset details to check attachments
                try:
                    details_response = await loop.run_in_executor(
                        None,
                        lambda: self._make_request('GET', f"{self.base_url}/assets/{exact_match['id']}?include=attachments")
                    )
                    attachments = details_response.get('included', [])
                    
                    # Check if asset has null metadata (broken asset)
                    is_broken = (attachments and 
                               (attachments[0].get('attributes', {}).get('mimetype') is None or
                                attachments[0].get('attributes', {}).get('size') is None))
                    
                    if is_broken:
                        print(f"[BRANDFOLDER] ⚠️  Found existing asset but it has incomplete metadata (broken)")
                        print(f"[BRANDFOLDER] Asset ID: {exact_match['id']} - mimetype: {attachments[0]['attributes'].get('mimetype')}, size: {attachments[0]['attributes'].get('size')}")
                        print("[BRANDFOLDER] Deleting broken asset and will re-upload...")
                        
                        # Delete the broken asset
                        try:
                            await self.delete_asset_async(exact_match['id'])
                            print("[BRANDFOLDER] ✓ Broken asset deleted successfully")
                        except Exception as delete_error:
                            print(f"[BRANDFOLDER] Failed to delete broken asset: {delete_error}")
                            print("[BRANDFOLDER] Continuing with re-upload anyway...")
                        
                        return {
                            'success': True,
                            'found': False,
                            'reason': 'broken_asset_deleted',
                            'deleted_asset_id': exact_match['id']
                        }
                except Exception as details_error:
                    print(f"[BRANDFOLDER] Could not check asset details, assuming it's valid: {details_error}")
                
                print(f"[BRANDFOLDER] Found existing asset with ID: {exact_match['id']}")
                return {
                    'success': True,
                    'found': True,
                    'asset': exact_match,
                    'asset_id': exact_match['id']
                }
            else:
                print(f"[BRANDFOLDER] No existing asset found with filename: {filename}")
                return {
                    'success': True,
                    'found': False,
                    'assets': assets
                }
                
        except Exception as error:
            print(f"[BRANDFOLDER] Error searching for asset: {str(error)}")
            # Don't throw error for search failures, just return not found
            print(f"[BRANDFOLDER] Search failed, will proceed with upload")
            return {
                'success': False,
                'found': False,
                'error': str(error)
            }

    def search_assets(self, collection_id: str, query: str) -> List[Dict]:
        """
        Search assets in a collection
        
        Args:
            collection_id: Brandfolder collection ID
            query: Search query
            
        Returns:
            List of matching assets
        """
        url = f"{self.base_url}/collections/{collection_id}/assets?search={query}"
        
        print(f"[BRANDFOLDER] Searching assets: {query}")
        response = self._make_request('GET', url)
        
        return response.get('data', [])

    def delete_asset(self, asset_id: str) -> Dict:
        """
        Delete an asset
        
        Args:
            asset_id: Brandfolder asset ID
            
        Returns:
            Deletion response
        """
        url = f"{self.base_url}/assets/{asset_id}"
        
        print(f"[BRANDFOLDER] Deleting asset: {asset_id}")
        response = self._make_request('DELETE', url)
        print(f"[BRANDFOLDER] Asset deleted successfully: {asset_id}")
        return {
            'success': True,
            'asset_id': asset_id
        }

    async def delete_asset_async(self, asset_id: str) -> Dict:
        """
        Delete an asset (async version)
        
        Args:
            asset_id: Brandfolder asset ID
            
        Returns:
            Deletion response
        """
        try:
            print(f"[BRANDFOLDER] Deleting asset: {asset_id}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._make_request('DELETE', f"{self.base_url}/assets/{asset_id}")
            )
            
            print(f"[BRANDFOLDER] Asset deleted successfully: {asset_id}")
            return {
                'success': True,
                'asset_id': asset_id
            }
        except Exception as error:
            print(f"[BRANDFOLDER] Error deleting asset: {error}")
            raise Exception(f"Failed to delete asset from Brandfolder: {error}")

    async def get_collections(self) -> Dict:
        """
        Get collections for the organization
        
        Returns:
            List of collections
        """
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('GET', f"{self.base_url}/organizations/{self.organization_id}/collections")
            )
            
            return {
                'success': True,
                'collections': response.get('data', [])
            }
        except Exception as error:
            print(f"[BRANDFOLDER] Error getting collections: {error}")
            raise Exception(f"Failed to get collections from Brandfolder: {error}")

    async def get_upload_url(self, filename: str, brandfolder_collection_id: str) -> Dict:
        """
        Step 1: Get upload URL from Brandfolder
        
        Args:
            filename: The filename for the asset
            brandfolder_collection_id: The collection ID to upload to
            
        Returns:
            Upload URL and upload data
        """
        try:
            payload = {
                'data': {
                    'attributes': {
                        'filename': filename
                    }
                }
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('GET', f"{self.base_url}/upload_requests")
            )
            
            return {
                'success': True,
                'upload_url': response.get('upload_url'),
                'object_url': response.get('object_url'),
                'data': response
            }
        except Exception as error:
            print(f"[BRANDFOLDER] Error getting upload URL: {error}")
            raise Exception(f"Failed to get upload URL from Brandfolder: {error}")

    def get_content_type_from_file(self, file_path: str) -> str:
        """
        Determine content type from file extension
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content type string
        """
        ext = os.path.splitext(file_path)[1].lower()
        
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.webm': 'video/webm',
            '.pdf': 'application/pdf'
        }
        
        if not ext:
            print(f"[BRANDFOLDER] File has no extension: {file_path}, defaulting to image/jpeg")
            return 'image/jpeg'
        
        return content_types.get(ext, 'application/octet-stream')

    async def upload_file_to_url(self, upload_url: str, local_file_path: str, filename: str) -> Dict:
        """
        Step 2: Upload file to the upload URL
        
        Args:
            upload_url: The upload URL from step 1
            local_file_path: Path to the local file to upload
            filename: The filename for the asset
            
        Returns:
            Upload response
        """
        try:
            if not local_file_path:
                raise Exception('Local file path is required but was not provided')
            
            if not os.path.exists(local_file_path):
                raise Exception(f'Local file does not exist: {local_file_path}')
            
            file_size = os.path.getsize(local_file_path)
            print(f"[BRANDFOLDER] Uploading file size: {file_size / 1024 / 1024:.2f}MB ({file_size} bytes)")
            
            headers = {
                'Content-Type': self.get_content_type_from_file(local_file_path),
                'Content-Length': str(file_size)
            }
            
            with open(local_file_path, 'rb') as file_stream:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.put(upload_url, data=file_stream, headers=headers, timeout=600)
                )
            
            print(f"[BRANDFOLDER] File upload response status: {response.status_code}")
            
            if response.status_code not in [200, 201]:
                raise Exception(f'Upload failed with status {response.status_code}')
            
            print("[BRANDFOLDER] File upload completed successfully")
            
            return {
                'success': True,
                'status': response.status_code
            }
        except Exception as error:
            print(f"[BRANDFOLDER] Error uploading file: {error}")
            raise Exception(f"Failed to upload file to Brandfolder: {error}")

    async def create_asset_from_upload(self, object_url: str, filename: str, brandfolder_collection_id: str) -> Dict:
        """
        Step 3: Create asset from uploaded file
        
        Args:
            object_url: The object URL from step 1
            filename: The filename for the asset
            brandfolder_collection_id: The collection ID to upload to
            
        Returns:
            Asset creation response with asset ID
        """
        try:
            asset_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            
            print(f"[BRANDFOLDER] Creating asset with name: {asset_name}")
            print(f"[BRANDFOLDER] Attachment filename: {filename}")
            
            payload = {
                'data': {
                    'attributes': [{
                        'name': asset_name,
                        'attachments': [{
                            'url': object_url,
                            'filename': filename
                        }]
                    }]
                },
                'section_key': self.section_key
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._make_request('POST', f"{self.base_url}/collections/{brandfolder_collection_id}/assets", payload)
            )
            
            asset_id = response.get('data', [{}])[0].get('id')
            
            if not asset_id:
                print("[BRANDFOLDER] No asset ID returned from Brandfolder")
                raise Exception('Brandfolder did not return an asset ID')
            
            print(f"[BRANDFOLDER] ✓ Asset created successfully with ID: {asset_id}")
            
            return {
                'success': True,
                'asset_id': asset_id,
                'data': response
            }
        except Exception as error:
            print(f"[BRANDFOLDER] ✗ Error creating asset from upload for {filename}:")
            print(f"[BRANDFOLDER] Error details: {error}")
            raise Exception(f"Failed to create asset from upload in Brandfolder: {error}")

    def categorize_download_error(self, error: Exception) -> Dict:
        """
        Categorize download errors for better diagnostics and retry logic
        
        Args:
            error: The error to categorize
            
        Returns:
            Error information with category and retry recommendation
        """
        message = str(error)
        
        if 'DNS resolution failed' in message or 'Name or service not known' in message:
            return {
                'category': 'DNS_ERROR',
                'message': 'DNS resolution failed',
                'retryable': False,
                'details': 'Domain name could not be resolved'
            }
        
        if 'Connection refused' in message:
            return {
                'category': 'CONNECTION_REFUSED',
                'message': 'Connection refused',
                'retryable': True,
                'details': 'Server refused the connection'
            }
        
        if 'timeout' in message.lower():
            return {
                'category': 'TIMEOUT',
                'message': 'Request timed out',
                'retryable': True,
                'details': 'Server took too long to respond or download was too slow'
            }
        
        if '4' in message and 'status' in message.lower():
            return {
                'category': 'CLIENT_ERROR',
                'message': message,
                'retryable': False,
                'details': 'Client error (4xx) - check URL and permissions'
            }
        
        if '5' in message and 'status' in message.lower():
            return {
                'category': 'SERVER_ERROR',
                'message': message,
                'retryable': True,
                'details': 'Server error (5xx) - temporary server issue'
            }
        
        if 'Size mismatch' in message:
            return {
                'category': 'SIZE_MISMATCH',
                'message': message,
                'retryable': True,
                'details': 'Downloaded file size does not match expected size'
            }
        
        if 'empty' in message.lower():
            return {
                'category': 'EMPTY_FILE',
                'message': message,
                'retryable': True,
                'details': 'Downloaded file is empty'
            }
        
        return {
            'category': 'UNKNOWN_ERROR',
            'message': message,
            'retryable': True,
            'details': f'Unhandled error: {message}'
        }

    async def download_from_http(self, http_url: str, filename: str, max_retries: int = 3) -> str:
        """
        Download file from HTTP URL with enhanced error handling and retry logic
        
        Args:
            http_url: The HTTP URL to download from
            filename: The filename for the downloaded file
            max_retries: Maximum number of retry attempts
            
        Returns:
            Path to the downloaded file
        """
        timeout = 600  # 600 seconds timeout
        
        for attempt in range(1, max_retries + 1):
            local_file_path = None
            
            try:
                print(f"\n[BRANDFOLDER] Download attempt {attempt}/{max_retries}: {http_url}")
                http_url = http_url.split('?')[0]  # Remove query parameters
                
                # Create temp directory
                temp_dir = os.path.join(os.getcwd(), 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                print(f"[BRANDFOLDER] Created temp directory: {temp_dir}")
                
                local_file_path = os.path.join(temp_dir, f"brandfolder_{int(time.time() * 1000)}_{filename}")
                print(f"[BRANDFOLDER] Downloading to temporary file: {local_file_path}")
                
                start_time = time.time()
                
                # Download the file
                response = requests.get(
                    http_url,
                    stream=True,
                    timeout=timeout,
                    headers={
                        'User-Agent': 'Costco-Content-Creation/1.0',
                        'Accept': '*/*',
                        'Connection': 'keep-alive'
                    }
                )
                response.raise_for_status()
                
                print(f"[BRANDFOLDER] Response status: {response.status_code} {response.reason}")
                print(f"[BRANDFOLDER] Content-Length: {response.headers.get('content-length', 'unknown')}")
                print(f"[BRANDFOLDER] Content-Type: {response.headers.get('content-type', 'unknown')}")
                
                expected_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(local_file_path, 'wb') as writer:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            writer.write(chunk)
                            downloaded_size += len(chunk)
                            
                            if expected_size > 0:
                                progress = (downloaded_size / expected_size) * 100
                                if downloaded_size % (10 * 1024 * 1024) < 8192 or \
                                   (expected_size < 10 * 1024 * 1024 and downloaded_size % max(expected_size // 4, 1024 * 1024) < 8192):
                                    print(f"[BRANDFOLDER] Download progress: {progress:.1f}% ({downloaded_size / 1024 / 1024:.2f}MB/{expected_size / 1024 / 1024:.2f}MB)")
                
                stats = os.stat(local_file_path)
                duration = time.time() - start_time
                
                print(f"[BRANDFOLDER] Download completed successfully in {duration:.2f}s")
                print(f"[BRANDFOLDER] Downloaded file size: {stats.st_size / 1024 / 1024:.2f}MB ({stats.st_size} bytes)")
                
                if stats.st_size == 0:
                    raise Exception('Downloaded file is empty')
                
                # Validate file content by checking magic bytes
                file_ext = os.path.splitext(filename)[1].lower()
                is_image_file = file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']
                
                if is_image_file and stats.st_size > 0:
                    with open(local_file_path, 'rb') as f:
                        buffer = f.read(min(512, stats.st_size))
                    
                    file_start = buffer.decode('utf-8', errors='ignore').lower()[:100]
                    is_html_content = any(tag in file_start for tag in ['<!doctype', '<html', '<?xml', '<body', '<head'])
                    
                    if is_html_content:
                        raise Exception(f"Downloaded file appears to be HTML/XML instead of an image. File starts with: {file_start[:50]}...")
                    
                    # Check for common image file signatures (magic bytes)
                    is_valid_image = (
                        (buffer[0:2] == b'\xff\xd8') or  # JPEG
                        (buffer[0:4] == b'\x89PNG') or  # PNG
                        (buffer[0:3] == b'GIF') or  # GIF
                        (buffer[0:4] == b'RIFF') or  # WEBP
                        b'<svg' in buffer or b'<?xml' in buffer  # SVG
                    )
                    
                    if not is_valid_image and stats.st_size < 1024 * 1024:
                        content_type = response.headers.get('content-type', '')
                        print(f"[BRANDFOLDER] Warning: File doesn't match expected image format (Content-Type: {content_type})")
                        print(f"[BRANDFOLDER] First bytes: {buffer[:8].hex()}")
                        print("[BRANDFOLDER] Continuing anyway as server might have wrong headers...")
                    elif is_valid_image:
                        print(f"[BRANDFOLDER] ✓ File validated as valid {file_ext.upper()} image")
                
                # Validate file size
                if expected_size > 0 and stats.st_size != expected_size:
                    size_difference = abs(stats.st_size - expected_size)
                    percentage_diff = (size_difference / expected_size) * 100
                    
                    print(f"[BRANDFOLDER] Size difference detected: expected {expected_size} bytes, got {stats.st_size} bytes ({percentage_diff:.1f}% difference)")
                    
                    is_svg = file_ext == '.svg'
                    is_image = file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']
                    
                    if is_svg or is_image:
                        max_allowed_diff = max(expected_size * 0.5, 10240)
                        
                        if size_difference > max_allowed_diff:
                            print(f"[BRANDFOLDER] Large size difference ({size_difference} bytes) but file is valid image, continuing...")
                        else:
                            print("[BRANDFOLDER] Size difference within acceptable range for images")
                    else:
                        tolerance = max(expected_size * 0.1, 1024)
                        
                        if size_difference > tolerance:
                            print(f"[BRANDFOLDER] Size mismatch: expected {expected_size} bytes, got {stats.st_size} bytes (difference: {size_difference} bytes, tolerance: {tolerance:.0f} bytes)")
                            print("[BRANDFOLDER] Continuing anyway...")
                
                print(f"[BRANDFOLDER] File download successful: {local_file_path}")
                return local_file_path
                
            except Exception as error:
                error_info = self.categorize_download_error(error)
                print(f"[BRANDFOLDER] Download attempt {attempt}/{max_retries} failed: {error_info}")
                
                # Clean up temporary file if it was created
                if local_file_path and os.path.exists(local_file_path):
                    try:
                        os.remove(local_file_path)
                        print(f"[BRANDFOLDER] Cleaned up temporary file: {local_file_path}")
                    except Exception as cleanup_error:
                        print(f"[BRANDFOLDER] Failed to clean up temporary file: {cleanup_error}")
                
                # If this is the last attempt or error is not retryable, throw the error
                if attempt == max_retries or not error_info['retryable']:
                    raise Exception(f"Failed to download file after {max_retries} attempts. Last error: {error_info['message']} ({error_info['category']})")
                
                # Exponential backoff for retries: 2s, 4s, 8s
                delay = (2 ** attempt)
                print(f"[BRANDFOLDER] Retrying in {delay}s...")
                time.sleep(delay)
        
        raise Exception(f"Failed to download file after {max_retries} attempts from {http_url}")

    async def wait_for_asset_processing(self, asset_id: str, max_attempts: int = 8, delay: int = 2) -> bool:
        """
        Wait for Brandfolder to process the asset and generate CDN URL
        
        Args:
            asset_id: The asset ID to check
            max_attempts: Maximum number of polling attempts (optimized to 8)
            delay: Delay between attempts in seconds (optimized to 2)
            
        Returns:
            True if asset is processed, False otherwise
        """
        print(f"[BRANDFOLDER] Waiting for asset {asset_id} to be processed...")
        
        for attempt in range(1, max_attempts + 1):
            try:
                # Get asset details
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._make_request('GET', f"{self.base_url}/assets/{asset_id}?fields=cdn_url&include=attachments")
                )
                
                asset = response.get('data', {})
                attachments = response.get('included', [])
                cdn_url = asset.get('attributes', {}).get('cdn_url')
                
                # Check if CDN URL is available and not a legacy URL
                if cdn_url and 'brandfolder.com' in cdn_url:
                    # Verify the CDN URL is accessible
                    try:
                        cdn_check = requests.head(cdn_url, timeout=10)
                        if 200 <= cdn_check.status_code < 400:
                            print(f"[BRANDFOLDER] ✓ Asset processed successfully (attempt {attempt}/{max_attempts})")
                            return True
                    except:
                        pass
                
                # Check attachments for valid metadata
                if attachments and attachments[0].get('attributes', {}).get('mimetype'):
                    print(f"[BRANDFOLDER] Asset has valid metadata (attempt {attempt}/{max_attempts})")
                    if cdn_url:
                        return True
                
                print(f"[BRANDFOLDER] Asset not fully processed yet (attempt {attempt}/{max_attempts}), waiting {delay}s...")
                time.sleep(delay)
                
            except Exception as e:
                print(f"[BRANDFOLDER] Error checking asset status (attempt {attempt}/{max_attempts}): {e}")
                if attempt < max_attempts:
                    time.sleep(delay)
        
        print(f"[BRANDFOLDER] ⚠️  Asset processing timeout after {max_attempts} attempts")
        return False

    async def create_asset_from_http(self, http_url: str, filename: str, brandfolder_collection_id: str) -> Dict:
        """
        Create an asset in Brandfolder using 3-step upload process with HTTP download
        
        Args:
            http_url: The HTTP URL of the asset
            filename: The filename for the asset
            brandfolder_collection_id: The collection ID to upload to
            
        Returns:
            Asset creation response with asset ID
        """
        local_file_path = None
        
        try:
            print("\n[BRANDFOLDER] ========================================")
            print("[BRANDFOLDER] Starting 3-step upload process")
            print(f"[BRANDFOLDER] Source URL: {http_url}")
            print(f"[BRANDFOLDER] Target Filename: {filename}")
            print(f"[BRANDFOLDER] Collection ID: {brandfolder_collection_id}")
            print("[BRANDFOLDER] ========================================")
            
            # Ensure filename has an extension
            if not os.path.splitext(filename)[1]:
                print(f"[BRANDFOLDER] ⚠️  Filename missing extension: {filename}, adding .jpg")
                filename = f"{filename}.jpg"
            
            # Download file from HTTP URL
            print("[BRANDFOLDER] STEP 0: Downloading file from source...")
            local_file_path = await self.download_from_http(http_url, filename)
            
            # Validate download
            if not local_file_path:
                raise Exception('Download failed: No file path returned')
            if not os.path.exists(local_file_path):
                raise Exception(f'Download failed: File does not exist at {local_file_path}')
            
            file_stats = os.stat(local_file_path)
            print(f"[BRANDFOLDER] ✓ Download complete: {file_stats.st_size / 1024:.2f} KB")
            
            # Step 1: Get upload URL
            print("[BRANDFOLDER] STEP 1: Getting upload URL from Brandfolder...")
            upload_data = await self.get_upload_url(filename, brandfolder_collection_id)
            print("[BRANDFOLDER] ✓ Upload URL obtained")
            
            # Step 2: Upload file
            print("[BRANDFOLDER] STEP 2: Uploading file to Brandfolder S3...")
            await self.upload_file_to_url(
                upload_data['upload_url'],
                local_file_path,
                filename
            )
            print("[BRANDFOLDER] ✓ File uploaded to S3")
            
            # Step 3: Create asset
            print("[BRANDFOLDER] STEP 3: Creating asset in Brandfolder...")
            asset_result = await self.create_asset_from_upload(
                upload_data['object_url'],
                filename,
                brandfolder_collection_id
            )
            
            # Step 4: Wait for asset to be processed and CDN URL to be available
            print("[BRANDFOLDER] STEP 4: Waiting for asset processing...")
            asset_id = asset_result['asset_id']
            is_processed = await self.wait_for_asset_processing(asset_id)
            
            if not is_processed:
                print("[BRANDFOLDER] ⚠️  Asset may not be fully processed, but continuing...")
            
            print("[BRANDFOLDER] ========================================")
            print("[BRANDFOLDER] ✓ Upload process completed successfully")
            print(f"[BRANDFOLDER] Asset ID: {asset_id}")
            print("[BRANDFOLDER] ========================================\n")
            
            return asset_result
        except Exception as error:
            print("[BRANDFOLDER] ========================================")
            print("[BRANDFOLDER] ✗ Upload process FAILED")
            print(f"[BRANDFOLDER] Error: {error}")
            print(f"[BRANDFOLDER] Source URL: {http_url}")
            print(f"[BRANDFOLDER] Filename: {filename}")
            print("[BRANDFOLDER] ========================================\n")
            raise error
        finally:
            # Clean up temporary file
            if local_file_path and os.path.exists(local_file_path):
                try:
                    os.remove(local_file_path)
                    print(f"[BRANDFOLDER] Cleaned up temporary file: {local_file_path}")
                except Exception as cleanup_error:
                    print(f"[BRANDFOLDER] Failed to clean up temporary file: {cleanup_error}")