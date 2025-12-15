"""
Brandfolder API Client
Handles asset uploads and management in Brandfolder DAM
"""

import requests
import time
import asyncio
from typing import Dict, Optional, List
from urllib.parse import urlparse


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
        
        # Rate limiting
        self.max_retries = 5
        self.retry_delay = 2
        self.rate_limit_delay = 1

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
            
            # Get CDN URL from asset or first attachment
            cdn_url = asset.get('attributes', {}).get('cdn_url')
            
            if not cdn_url and attachments:
                # Fallback to first attachment URL
                first_attachment = attachments[0]
                cdn_url = first_attachment.get('attributes', {}).get('url')
            
            # Get primary attachment details
            primary_attachment = attachments[0] if attachments else {}
            
            print(f"[BRANDFOLDER] Asset details retrieved successfully")
            print(f"[BRANDFOLDER] CDN URL: {cdn_url}")
            
            return {
                'success': True,
                'asset_id': asset_id,
                'cdn_url': cdn_url,
                'extension': primary_attachment.get('attributes', {}).get('extension'),
                'mimetype': primary_attachment.get('attributes', {}).get('mimetype'),
                'filename': primary_attachment.get('attributes', {}).get('filename'),
                'thumbnail_url': asset.get('attributes', {}).get('thumbnail_url'),
                'data': response
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
                'assetId': asset ID (if found),
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
        return response
