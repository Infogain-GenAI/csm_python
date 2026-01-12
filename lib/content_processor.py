"""
Content Processor Module

This module handles the complete content processing workflow including:
- Asset processing and migration to Brandfolder
- Entry creation with nested content types
- Workflow processing (Review → Approved stages)
- Publishing with deep publish for all nested entries
- Rollback protection for created entries
"""

import re
import json
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import markdown_it

from .brandfolder_api import BrandfolderAPI
from .contentstack_api import ContentstackAPI


class ContentProcessor:
    """
    Main content processor class that orchestrates the entire content creation workflow
    """
    
    def __init__(
        self,
        brandfolder_config: Dict[str, Any],
        contentstack_config: Dict[str, Any],
        brandfolder_collection_id: str,
        options: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the content processor
        
        Args:
            brandfolder_config: Brandfolder API configuration
            contentstack_config: Contentstack API configuration
            brandfolder_collection_id: Brandfolder collection ID for asset storage
            options: Additional configuration options (entry_reuse_enabled, etc.)
        """
        options = options or {}
        
        # Store configuration
        self.brandfolder_config = brandfolder_config
        self.contentstack_config = contentstack_config
        self.brandfolder_collection_id = brandfolder_collection_id
        
        # Initialize APIs (will be set based on environment)
        self.brandfolder_api = None
        self.contentstack_api = None
        
        # Allowed file extensions for assets
        self.allowed_extensions = [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
            'mp4', 'mov', 'avi', 'wmv', 'flv', 'mkv', 'webm', 'pdf'
        ]
        
        # Caches for processed assets and entries
        self.asset_cache = {}  # Dict[str, Dict] - key: filename, value: processed asset info
        self.entry_cache = {}  # Dict[str, Dict] - key: content_type:uid, value: entry info
        
        # Track created entries for rollback (only new entries, not existing ones)
        self.created_entries = []  # List[Dict] - {uid, content_type, title}
        
        # Configuration options
        self.entry_reuse_enabled = options.get('entry_reuse_enabled', True)
        
        print(f"[CONFIG] Content processor initialized")
        print(f"[CONFIG] Entry reuse: {'ENABLED' if self.entry_reuse_enabled else 'DISABLED'}")
    
    def initialize_apis_for_environment(self, environment: str):
        """
        Initialize APIs for the specified environment
        
        Args:
            environment: Environment name (e.g., 'dev', 'USBC', 'USBD', etc.)
        """
        print(f"\n[CONFIG] Initializing APIs for environment: {environment}")
        
        # Get configuration for this environment
        bf_config = self.brandfolder_config.get(environment, {})
        cs_config = self.contentstack_config.get(environment, {})
        collection_id = self.brandfolder_collection_id.get(environment, '')
        
        if not bf_config or not cs_config:
            raise ValueError(f"Configuration not found for environment: {environment}")
        
        # Initialize Brandfolder API
        self.brandfolder_api = BrandfolderAPI(
            api_key=bf_config['api_key'],
            organization_id=bf_config['organization_id'],
            section_key=bf_config.get('section_key', '')
        )
        
        # Initialize Contentstack API
        self.contentstack_api = ContentstackAPI(
            api_key=cs_config['api_key'],
            management_token=cs_config['management_token'],
            base_url=cs_config.get('base_url', 'https://api.contentstack.io'),
            auth_token=cs_config.get('auth_token'),
            environment_uid=cs_config.get('environment_uid'),
            environment=cs_config.get('environment', 'dev')
        )
        
        # Set collection ID
        self.brandfolder_collection_id = collection_id
        
        print(f"[CONFIG] APIs initialized successfully")
        print(f"[CONFIG] Brandfolder Collection ID: {self.brandfolder_collection_id}")
    
    async def process_content(self, input_json: Dict, environment: str = 'dev') -> Dict:
        """
        Process the entire JSON input and create content in Brandfolder and Contentstack
        
        Args:
            input_json: The input JSON data
            environment: Environment to use
            
        Returns:
            Processing result with created entry UID
        """
        try:
            print('\n=== STARTING CONTENT PROCESSING ===')
            print(f"Environment: {environment}")
            
            # Initialize APIs based on environment
            self.initialize_apis_for_environment(environment)
            
            # Step 1: Extract and process all assets first
            print('\n=== STEP 1: PROCESSING ASSETS ===')
            await self.process_all_assets(input_json, None)
            
            # Step 2: Process entries from leaf to root
            print('\n=== STEP 2: PROCESSING ENTRIES ===')
            root_entry_uid = await self.process_entry(input_json['entry'], 'feature_page')
            
            print('\n=== CONTENT PROCESSING COMPLETED ===')
            print(f"Root entry created with UID: {root_entry_uid}")
            
            return {
                'success': True,
                'root_entry_uid': root_entry_uid,
                'processed_assets': list(self.asset_cache.keys()),
                'processed_entries': list(self.entry_cache.keys()),
                'created_entries': len(self.created_entries)
            }
            
        except Exception as error:
            print('\n=== CONTENT PROCESSING FAILED ===')
            print(f"Error: {str(error)}")
            print(f"\n📋 COMPLETE ERROR DETAILS:")
            print(f"Error Type: {type(error).__name__}")
            print(f"Error Message: {str(error)}")
            
            # Perform rollback - delete only created entries, not existing ones
            await self.rollback_created_entries()
            
            raise
    
    async def rollback_created_entries(self):
        """
        Rollback all created entries in case of error
        This will delete only entries that were newly created during this run,
        not existing entries that were reused
        
        IMPORTANT: Includes reference checking to avoid deleting entries 
        that are referenced by other entries (matching delete_entry_utility.py logic)
        """
        if not self.created_entries:
            print('\n[ROLLBACK] No entries to rollback - no new entries were created')
            return
        
        print(f'\n=== STARTING ROLLBACK ===')
        print(f"[ROLLBACK] Rolling back {len(self.created_entries)} created entries...")
        print(f"[ROLLBACK] NOTE: Brandfolder assets will NOT be deleted")
        print(f"[ROLLBACK] Checking references to avoid deleting referenced entries...")
        
        # Step 1: Analyze references for all created entries
        reference_analysis = await self._analyze_rollback_references()
        
        # Step 2: Separate entries into safe-to-delete and protected
        safe_to_delete = []
        protected_entries = []
        
        for entry in self.created_entries:
            entry_key = f"{entry['content_type']}/{entry['uid']}"
            analysis = reference_analysis.get(entry_key, {'to_be_deleted': False, 'reason': 'Unknown'})
            
            if analysis['to_be_deleted']:
                safe_to_delete.append(entry)
            else:
                protected_entries.append({
                    'entry': entry,
                    'reason': analysis['reason']
                })
        
        print(f"\n[ROLLBACK] Reference analysis completed:")
        print(f"  ✅ Safe to delete: {len(safe_to_delete)} entries")
        print(f"  🛡️ Protected (referenced elsewhere): {len(protected_entries)} entries")
        
        # Show protected entries
        if protected_entries:
            print(f"\n[ROLLBACK] 🛡️ PROTECTED ENTRIES (will NOT be deleted):")
            for i, item in enumerate(protected_entries, 1):
                entry = item['entry']
                reason = item['reason']
                print(f"  {i}. {entry['content_type']}/{entry['uid']} - {entry['title']}")
                print(f"     Reason: {reason}")
        
        deleted_count = 0
        failed_count = 0
        skipped_count = len(protected_entries)
        
        # Step 3: Delete only safe entries (in reverse order - child to parent)
        for i in range(len(safe_to_delete) - 1, -1, -1):
            entry = safe_to_delete[i]
            
            try:
                print(f"\n[ROLLBACK] Deleting entry {len(safe_to_delete) - i}/{len(safe_to_delete)}: {entry['title']} ({entry['uid']})")
                
                delete_result = await self.contentstack_api.delete_entry_async(
                    entry['content_type'],
                    entry['uid']
                )
                
                if delete_result.get('success'):
                    deleted_count += 1
                    print(f"[ROLLBACK] ✅ Successfully deleted entry: {entry['uid']}")
                else:
                    failed_count += 1
                    print(f"[ROLLBACK] ❌ Failed to delete entry: {entry['uid']} - {delete_result.get('error')}")
                    
            except Exception as error:
                failed_count += 1
                print(f"[ROLLBACK] ❌ Error deleting entry {entry['uid']}: {str(error)}")
        
        print(f'\n=== ROLLBACK COMPLETED ===')
        print(f"[ROLLBACK] Summary:")
        print(f"  ✅ Deleted: {deleted_count}")
        print(f"  ❌ Failed: {failed_count}")
        print(f"  🛡️ Protected (skipped): {skipped_count}")
        
        if deleted_count > 0:
            print(f"[ROLLBACK] ✅ Successfully cleaned up {deleted_count} created entries")
        
        if failed_count > 0:
            print(f"[ROLLBACK] ⚠️ Failed to delete {failed_count} entries - these may need manual cleanup")
        
        if skipped_count > 0:
            print(f"[ROLLBACK] 🛡️ Skipped {skipped_count} protected entries (referenced elsewhere)")
            print(f"[ROLLBACK] ℹ️ Protected entries will remain in Contentstack as they are still referenced")
        
        # Clear the created entries list
        self.created_entries = []
    
    async def _analyze_rollback_references(self) -> dict:
        """
        Analyze references for entries to be rolled back
        Similar to delete_entry_utility.py's analyze_entry_references logic
        
        Returns:
            Dictionary mapping entry_key -> {to_be_deleted: bool, references: [], reason: str}
        """
        reference_analysis = {}
        
        print(f"\n[ROLLBACK-ANALYSIS] Analyzing references for {len(self.created_entries)} entries...")
        
        for entry in self.created_entries:
            entry_key = f"{entry['content_type']}/{entry['uid']}"
            
            try:
                # Get all references for this entry
                references_result = self.contentstack_api.get_entry_references(
                    entry['content_type'],
                    entry['uid']
                )
                
                all_references = references_result.get('references', [])
                
                # Filter out self-references and references from entries created in this batch
                created_entry_uids = {e['uid'] for e in self.created_entries}
                external_references = []
                
                for ref in all_references:
                    # Extract referring entry UID
                    ref_entry_uid = (
                        ref.get('entry_uid') or 
                        ref.get('uid') or 
                        (ref.get('entry', {}).get('uid') if isinstance(ref.get('entry'), dict) else None)
                    )
                    
                    # Skip if reference is from another entry in the created batch
                    # (those will also be deleted, so they don't count as external references)
                    if ref_entry_uid and ref_entry_uid not in created_entry_uids:
                        external_references.append(ref)
                
                # Determine if entry can be deleted
                if len(external_references) > 0:
                    reference_analysis[entry_key] = {
                        'to_be_deleted': False,
                        'references': external_references,
                        'reason': f'Referenced in {len(external_references)} external entries (not created in this batch)'
                    }
                    print(f"[ROLLBACK-ANALYSIS] 🛡️ {entry_key} - PROTECTED (external references: {len(external_references)})")
                else:
                    reference_analysis[entry_key] = {
                        'to_be_deleted': True,
                        'references': [],
                        'reason': 'No external references found - safe to delete'
                    }
                    print(f"[ROLLBACK-ANALYSIS] ✅ {entry_key} - SAFE TO DELETE")
                
            except Exception as error:
                # If we can't check references, err on the side of caution - don't delete
                print(f"[ROLLBACK-ANALYSIS] ⚠️ Error checking references for {entry_key}: {str(error)}")
                reference_analysis[entry_key] = {
                    'to_be_deleted': False,
                    'references': [],
                    'reason': f'Reference check failed: {str(error)} - assuming protected for safety'
                }
        
        return reference_analysis
    
    def extract_links_from_markdown(self, markdown_text: str) -> List[Dict]:
        """
        Extract all links (images and regular links) from markdown text
        
        Args:
            markdown_text: The markdown text to parse
            
        Returns:
            Array of link objects with url, text, and type properties
        """
        if not markdown_text or not isinstance(markdown_text, str):
            return []
        
        md = markdown_it.MarkdownIt()
        links = []
        seen_links = set()
        
        try:
            # Parse the markdown and get tokens
            tokens = md.parse(markdown_text)
            
            def extract_from_tokens(token_list):
                for token in token_list:
                    if token.type == 'image':
                        # Handle image tokens
                        src = token.attrGet('src') if hasattr(token, 'attrGet') else None
                        alt = token.content or ''
                        if src:
                            link_key = f"image:{src}:{alt}"
                            if link_key not in seen_links:
                                seen_links.add(link_key)
                                links.append({
                                    'url': src,
                                    'text': alt,
                                    'type': 'image'
                                })
                    elif token.type == 'link_open':
                        # Handle link tokens
                        href = token.attrGet('href') if hasattr(token, 'attrGet') else None
                        if href:
                            link_key = f"link:{href}:"
                            if link_key not in seen_links:
                                seen_links.add(link_key)
                                links.append({
                                    'url': href,
                                    'text': '',
                                    'type': 'link'
                                })
                    
                    # Recursively process children tokens
                    if hasattr(token, 'children') and token.children:
                        extract_from_tokens(token.children)
            
            extract_from_tokens(tokens)
            
        except Exception as error:
            print(f"[MARKDOWN] Error parsing markdown: {str(error)}")
            print(f"[MARKDOWN] Falling back to regex-based parsing")
            
            # Fallback: regex-based parsing
            # 1. Find all reference definitions
            references = {}
            reference_regex = r'^\s*\[([^\]]+)\]:\s*(.+)$'
            for match in re.finditer(reference_regex, markdown_text, re.MULTILINE):
                ref_id = match.group(1).lower().strip()
                ref_url = match.group(2).strip()
                references[ref_id] = ref_url
            
            # 2. Find inline links [text](url)
            inline_link_regex = r'(!?)\[([^\]]*)\]\(([^)]+)\)'
            for match in re.finditer(inline_link_regex, markdown_text):
                is_image = match.group(1) == '!'
                text = match.group(2)
                url = match.group(3)
                link_key = f"{'image' if is_image else 'link'}:{url}:{text}"
                
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    links.append({
                        'url': url,
                        'text': text,
                        'type': 'image' if is_image else 'link'
                    })
            
            # 3. Find reference-style links [text][ref]
            ref_usage_regex = r'(!?)\[([^\]]*)\]\[([^\]]+)\]'
            for match in re.finditer(ref_usage_regex, markdown_text):
                is_image = match.group(1) == '!'
                text = match.group(2)
                ref_id = match.group(3).lower().strip()
                
                if ref_id in references:
                    link_key = f"{'image' if is_image else 'link'}:{references[ref_id]}:{text}"
                    if link_key not in seen_links:
                        seen_links.add(link_key)
                        links.append({
                            'url': references[ref_id],
                            'text': text,
                            'type': 'image' if is_image else 'link'
                        })
        
        return links
    
    async def process_image_asset(self, image_obj: dict, parent_obj: Any):
        """
        Process a single image asset object
        
        Args:
            image_obj: Image object with url, filename, extension
            parent_obj: Parent array or object containing this image
        """
        # Check if obj.url ends with one of the allowed extensions
        url_lower = image_obj['url'].lower()
        # Remove url query parameters for extension check
        url_without_query = url_lower.split('?')[0]
        ends_with_allowed_extension = any(url_without_query.endswith('.' + ext) for ext in self.allowed_extensions)
        
        # Allow URLs from known image hosting domains even without extensions
        is_known_image_domain = (url_lower.startswith('https://cdn.bfldr.com/') or 
                                'mobilecontent.costco.com' in url_lower or
                                'www.costco.com/wcsstore' in url_lower)
        
        if not ends_with_allowed_extension and not is_known_image_domain:
            print(f"\n[ASSET] Skipping non-asset URL: {image_obj['url']}")
            return
        
        # Normalize relative URLs to absolute
        if image_obj['url'].startswith('/'):
            image_obj['url'] = "https://www.costco.com" + image_obj['url']
        elif image_obj['url'].startswith('wcsstore'):
            image_obj['url'] = "https://www.costco.com/" + image_obj['url']
        
        print(f"\n[ASSET] Found asset URL: {image_obj['url']}")
        
        # Extract filename and extension from URL string (not using URL object)
        parts = url_without_query.split('/')
        filename = parts[-1]
        extension = filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Handle missing extensions - default to jpg for images
        if not extension or extension == '':
            print(f"[ASSET] URL missing file extension: {image_obj['url']}")
            extension = 'jpg'
            filename = f"{filename}.{extension}"
            print(f"[ASSET] Added default extension: {filename}")
        
        # Preserve original filename if it exists (but update if empty), otherwise use extracted filename
        if 'filename' not in image_obj or not image_obj.get('filename'):
            image_obj['filename'] = filename
        elif '.' not in image_obj.get('filename', '') and extension:
            # If filename exists but has no extension, append it
            image_obj['filename'] = f"{image_obj['filename']}.{extension}"
            print(f"[ASSET] Updated filename with extension: {image_obj['filename']}")
        
        # Update extension if it's missing or empty
        if 'extension' not in image_obj or not image_obj.get('extension'):
            image_obj['extension'] = extension
            print(f"[ASSET] Set extension to: {image_obj['extension']}")
        
        # Ensure mimetype is set if not already present
        if 'mimetype' not in image_obj or not image_obj.get('mimetype'):
            image_obj['mimetype'] = f"image/{extension}"
            print(f"[ASSET] Set mimetype to: {image_obj['mimetype']}")
        
        # Check if this is a video asset sourced from production (array has multiple items)
        if isinstance(parent_obj, list) and len(parent_obj) > 1:
            print(f"[ASSET] Skipping video/subtitle/thumbnail which is sourced from prod: {image_obj['url']}")
            return
        
        # Only process if extension is an image or video type, or URL is from known image domains
        if extension in self.allowed_extensions or ends_with_allowed_extension or is_known_image_domain:
            try:
                await self.process_asset(image_obj)
            except Exception as error:
                print(f"[ASSET] ⚠️  Failed to process asset, keeping original URL: {image_obj['url']}")
                print(f"[ASSET] Error: {str(error)}")
                # Keep the original object intact - don't let it become null
                # The error is already handled in process_asset, so we just log here
        else:
            print(f"[ASSET] Skipping asset with unrecognized extension: {image_obj['url']}")
    
    async def process_all_assets(self, obj: Any, parent_obj: Any):
        """
        Recursively find and process all assets in the JSON
        
        Args:
            obj: Object to search for assets
            parent_obj: Parent object for context
        """
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                # Skip null or undefined entries
                if item is None:
                    print(f"[ASSET] Skipping null/undefined element at index {i}")
                    continue
                
                # Special handling for image arrays - process directly
                # Check if this looks like an image object with url property
                if item and isinstance(item, dict) and 'url' in item:
                    print(f"\n[ASSET] Processing image array element: {item.get('filename', item.get('url'))}")
                    await self.process_image_asset(item, obj)
                else:
                    # Recurse into array elements
                    await self.process_all_assets(item, obj)
                
        elif isinstance(obj, dict):
            # Check if this is an asset (has url)
            if 'url' in obj and not re.search(r'\.html?$', obj['url'], re.IGNORECASE) and not obj['url'].startswith('#'):
                await self.process_image_asset(obj, parent_obj)
                    
            elif 'rich_text_editor' in obj:
                await self.handle_rich_text_images(obj['rich_text_editor'])
            
            # Recursively process all properties
            for key, value in obj.items():
                await self.process_all_assets(value, obj)
                
        elif isinstance(obj, str):
            # Handle string fields that may contain markdown with image URLs
            links = self.extract_links_from_markdown(obj)
            
            for link in links:
                link_url = link['url']
                
                if not link_url or re.search(r'\.html?$', link_url, re.IGNORECASE) or link_url.startswith('#'):
                    print(f"\n[ASSET] Skipping non-asset URL inside markdown: {link_url}")
                    continue
                
                if link_url.startswith('/'):
                    link_url = "https://www.costco.com" + link_url
                
                link_url_without_query = link_url.split('?')[0]
                md_link_extension = link_url_without_query.split('.')[-1].lower() if '.' in link_url_without_query else ''
                
                if md_link_extension not in self.allowed_extensions and not link_url.startswith('https://cdn.bfldr.com/'):
                    print(f"\n[ASSET] Skipping non-asset URL inside markdown: {link_url}")
                    continue
                
                print(f"\n[ASSET] Found asset URL inside markdown ({link['type']}): {link_url}")
                
                # Extract filename and extension
                parts = link_url_without_query.split('/')
                filename = parts[-1]
                extension = filename.split('.')[-1].lower() if '.' in filename else ''
                
                asset_obj = {'url': link_url, 'filename': filename, 'extension': extension}
                await self.process_asset(asset_obj)
    
    def extract_brandfolder_attachment_id(self, url: str) -> Optional[str]:
        """
        Extract Brandfolder attachment ID from CDN URL using regex
        
        Args:
            url: The Brandfolder CDN URL
            
        Returns:
            The extracted attachment ID or None if not found
        """
        # Example: https://cdn.bfldr.com/56O3HXZ9/at/5bk5nnkbtx9v8wsrgfjx44/filename.jpg
        match = re.search(r'/at/([a-zA-Z0-9]+)/', url)
        return match.group(1) if match else None
    
    def extract_filename_from_url(self, url: str) -> Optional[str]:
        """
        Extract filename from URL
        
        Args:
            url: The URL
            
        Returns:
            The extracted filename or None
        """
        match = re.search(r'/([^\/?#]+)(?:\?|#|$)', url)
        return match.group(1) if match else None
    
    async def process_asset(self, asset: Dict) -> Dict:
        """
        Process a single asset
        
        Args:
            asset: Asset object with url, filename, extension
            
        Returns:
            Processed asset with Brandfolder details
        """
        print(f"\n[ASSET] Starting processing for asset: {asset['url']}")
        asset_key = asset['filename']
        
        if 'extension' not in asset:
            asset['extension'] = Path(asset['filename']).suffix.replace('.', '')
        
        # Check if asset already processed
        if asset_key in self.asset_cache:
            print(f"[ASSET] Asset already processed: {asset_key}")
            return self.asset_cache[asset_key]
        
        try:
            if asset['url'].startswith('/'):
                asset['url'] = "https://www.costco.com" + asset['url']
            
            print(f"\n[ASSET] Processing asset: {asset_key}")
            print(f"[ASSET] Source URL: {asset['url']}")
            
            is_existing = False
            
            # Handle brandfolder assets
            if asset['url'].startswith('https://cdn.bfldr.com/') and '/at/' in asset['url']:
                attachment_id = self.extract_brandfolder_attachment_id(asset['url'])
                filename_from_url = self.extract_filename_from_url(asset['url'])
                print(f"[ASSET] Extracted filename from URL: {filename_from_url}")
                
                if attachment_id:
                    print(f"[ASSET] Detected Brandfolder URL, extracting attachment ID: {attachment_id}")
                    asset_details = await self.brandfolder_api.get_asset_details_from_attachment(attachment_id)
                    
                    if asset_details and asset_details.get('subtitle_reference', {}).get('id') and asset_details.get('thumbnail_reference', {}).get('id'):
                        print(f"[ASSET] Detected Brandfolder Video, attaching thumbnail and caption file")
                        
                        processed_asset = {
                            'original_url': asset['url'],
                            'brandfolder_asset_id': asset_details['asset_id'],
                            'cdn_url': asset_details['cdn_url'],
                            'filename': asset['filename'],
                            'extension': asset['extension'],
                            'is_existing': is_existing,
                            'mimetype': asset.get('mimetype'),
                            'thumbnail_url': asset.get('thumbnail_url'),
                            'contentstack_reference': self.contentstack_api.create_asset_reference(
                                asset_details['asset_id'],
                                asset_details['cdn_url'],
                                asset_details['filename'],
                                asset_details['extension'],
                                asset_details.get('dimensions'),
                                asset_details.get('mimetype'),
                                asset['url']
                            ),
                            'subtitle_reference': asset_details.get('subtitle_reference'),
                            'thumbnail_reference': asset_details.get('thumbnail_reference')
                        }
                        
                        self.asset_cache[filename_from_url] = processed_asset
                        # CRITICAL: Update the original asset URL with the CDN URL
                        asset['url'] = processed_asset['cdn_url']
                        print(f"[ASSET] Cached asset with key: {filename_from_url}")
                        print(f"[ASSET] Updated asset URL to Brandfolder CDN URL: {asset['url']}")
                        print(f"[ASSET] Asset processed successfully: {filename_from_url} ({'existing' if is_existing else 'new'})")
                        return processed_asset
                    else:
                        print(f"[ASSET] Detected Brandfolder Image, processing normally")
                        processed_asset = await self.process_external_asset(asset, asset_key)
                        # CRITICAL: Update the original asset URL with the CDN URL
                        asset['url'] = processed_asset['cdn_url']
                        print(f"[ASSET] Updated asset URL to Brandfolder CDN URL: {asset['url']}")
                        return processed_asset
            else:
                # Handle other external URLs
                processed_asset = await self.process_external_asset(asset, asset_key)
                # CRITICAL: Update the original asset URL with the CDN URL
                asset['url'] = processed_asset['cdn_url']
                print(f"[ASSET] Updated asset URL to Brandfolder CDN URL: {asset['url']}")
                return processed_asset
                
        except Exception as error:
            error_str = str(error)
            print(f"\n[ASSET ERROR] ===== ASSET PROCESSING FAILED =====")
            print(f"[ASSET ERROR] Asset Key: {asset_key}")
            print(f"[ASSET ERROR] URL: {asset['url']}")
            print(f"[ASSET ERROR] Filename: {asset['filename']}")
            print(f"[ASSET ERROR] Extension: {asset.get('extension', 'N/A')}")
            print(f"[ASSET ERROR] Error Type: {type(error).__name__}")
            print(f"[ASSET ERROR] Error Message: {error_str}")
            print(f"[ASSET ERROR] =====================================\n")
            
            # Check if this is a 404 error (file not found)
            if '404' in error_str and 'CLIENT_ERROR' in error_str:
                print(f"[ASSET] Asset not found (404), skipping: {asset_key}")
                
                # Return a placeholder asset object
                skipped_asset = {
                    'original_url': asset['url'],
                    'brandfolder_asset_id': None,
                    'cdn_url': None,
                    'filename': asset['filename'],
                    'extension': asset['extension'],
                    'is_existing': False,
                    'is_skipped': True,
                    'skip_reason': f'404 - File not found: {error_str}',
                    'mimetype': asset.get('mimetype'),
                    'thumbnail_url': asset.get('thumbnail_url'),
                    'contentstack_reference': None
                }
                
                self.asset_cache[asset_key] = skipped_asset
                return skipped_asset
            
            print(f"[ASSET] Failed to process asset: {asset_key} - {error_str}")
            raise
    
    async def process_external_asset(self, asset: Dict, asset_key: str) -> Dict:
        """
        Process an external asset (not from Brandfolder CDN)
        
        Args:
            asset: Asset object
            asset_key: Cache key for the asset
            
        Returns:
            Processed asset details
        """
        print(f"\n[ASSET] ===== PROCESSING EXTERNAL ASSET =====")
        print(f"[ASSET] Asset Key: {asset_key}")
        print(f"[ASSET] Filename: {asset['filename']}")
        print(f"[ASSET] URL: {asset['url']}")
        print(f"[ASSET] Extension: {asset.get('extension', 'N/A')}")
        print(f"[ASSET] Collection ID: {self.brandfolder_collection_id}")
        
        # Store original URL before any modifications
        original_url = asset['url']
        
        search_result = await self.brandfolder_api.search_asset_by_filename(
            asset['filename'],
            self.brandfolder_collection_id
        )
        
        is_existing = False
        
        if search_result['found']:
            # Use existing asset
            asset_id = search_result['asset_id']
            # Update URL to CDN URL from search result
            asset['url'] = search_result['asset']['attributes']['cdn_url']
            is_existing = True
            print(f"[ASSET] ✓ Using existing asset with ID: {asset_id}")
            print(f"[ASSET] ✓ Updated URL to CDN: {asset['url']}")
        else:
            # Create new asset in Brandfolder using 3-step upload with HTTP download
            print(f"[ASSET] Asset not found, creating new asset using 3-step upload")
            try:
                create_result = await self.brandfolder_api.create_asset_from_http(
                    asset['url'],
                    asset['filename'],
                    self.brandfolder_collection_id
                )
                asset_id = create_result['asset_id']
                print(f"[ASSET] ✓ New asset created with ID: {asset_id}")
            except Exception as e:
                print(f"[ASSET] ✗ Failed to create asset in Brandfolder")
                raise
        
        # Get asset details including CDN URL
        print(f"[ASSET] Fetching asset details for ID: {asset_id}")
        asset_details = await self.brandfolder_api.get_asset_details(asset_id)
        print(f"[ASSET] CDN URL from asset details: {asset_details['cdn_url']}")
        
        # Ensure filename includes extension
        final_filename = asset['filename']
        if asset['extension'] and not final_filename.endswith(f".{asset['extension']}"):
            final_filename = f"{final_filename}.{asset['extension']}"
            print(f"[ASSET] Ensured filename has extension: {final_filename}")
        
        # Log what we're about to create
        print(f"[ASSET] Creating asset reference with:")
        print(f"  - Filename: {final_filename}")
        print(f"  - Extension: {asset['extension']}")
        print(f"  - CDN URL: {asset_details['cdn_url']}")
        print(f"  - Mimetype: {asset.get('mimetype')}")
        
        processed_asset = {
            'original_url': original_url,
            'brandfolder_asset_id': asset_details['asset_id'],
            'cdn_url': asset_details['cdn_url'],
            'filename': final_filename,
            'extension': asset['extension'],
            'is_existing': is_existing,
            'mimetype': asset.get('mimetype'),
            'thumbnail_url': asset.get('thumbnail_url'),
            'contentstack_reference': self.contentstack_api.create_asset_reference(
                asset_details['asset_id'],
                asset_details['cdn_url'],
                final_filename,
                asset['extension'],
                asset_details.get('dimensions'),
                asset.get('mimetype'),
                asset.get('thumbnail_url')
            )
        }
        
        self.asset_cache[asset_key] = processed_asset
        print(f"[ASSET] ✓ Asset processed successfully: {asset_key} ({'existing' if is_existing else 'new'})")
        print(f"[ASSET] ==========================================\n")
        return processed_asset
    
    async def process_entry(self, entry_data: Dict, content_type_uid: str) -> str:
        """
        Process an entry and its nested references
        
        Args:
            entry_data: Entry data
            content_type_uid: Content type UID
            
        Returns:
            Created entry UID
        """
        try:
            print(f"\n[ENTRY] Processing entry for content type: {content_type_uid}")
            print(f"[ENTRY] Entry title: {entry_data.get('title', 'No title')}")
            
            if 'url' in entry_data:
                del entry_data['url']
            
            # Create a deep copy of entry data
            processed_entry_data = json.loads(json.dumps(entry_data))
            
            # Process nested entries first (leaf to root approach)
            await self.process_nested_entries(processed_entry_data)
            
            # Replace asset references
            self.replace_asset_references(processed_entry_data)
            
            # Create entry in Contentstack with retry logic
            create_result = await self.create_entry_with_retry(content_type_uid, processed_entry_data)
            
            # Cache the created entry
            entry_key = f"{content_type_uid}:{create_result['entry_uid']}"
            self.entry_cache[entry_key] = {
                'uid': create_result['entry_uid'],
                'content_type': content_type_uid,
                'title': entry_data.get('title', 'No title'),
                'is_existing': create_result.get('is_existing', False)
            }
            
            print(f"[ENTRY] Entry created successfully: {create_result['entry_uid']}")
            return create_result['entry_uid']
            
        except Exception as error:
            print(f"[ENTRY] Failed to process entry for content type: {content_type_uid} - {str(error)}")
            raise
    
    async def create_entry_with_retry(self, content_type_uid: str, entry_data: Dict) -> Dict:
        """
        Create entry with search and retry logic
        
        Args:
            content_type_uid: Content type UID
            entry_data: Entry data
            
        Returns:
            Entry creation result
        """
        import os
        
        # Check if entry reuse is enabled
        if self.entry_reuse_enabled and entry_data.get('title'):
            print(f"[ENTRY] Entry reuse is enabled, searching for existing entry with title: \"{entry_data['title']}\"")
            search_result = await self.contentstack_api.search_entry_by_title_async(content_type_uid, entry_data['title'])
            
            if search_result['found']:
                print(f"[ENTRY] Using existing entry with UID: {search_result['entry_uid']}")
                return {
                    'success': True,
                    'entry_uid': search_result['entry_uid'],
                    'data': {'entry': search_result['entry']},
                    'is_existing': True
                }
            else:
                print(f"[ENTRY] No existing entry found, creating new entry")
        elif not self.entry_reuse_enabled:
            print(f"[ENTRY] Entry reuse is disabled, creating new entry without checking")
        
        try:
            # First attempt - try with original data
            if content_type_uid == 'ad_builder':
                # Fix overlay_position if needed
                if (entry_data.get('text_content_overlay_styles') and 
                    isinstance(entry_data['text_content_overlay_styles'], list) and
                    len(entry_data['text_content_overlay_styles']) > 0 and
                    entry_data['text_content_overlay_styles'][0].get('overlay_style', {}).get('overlay_position') == 'center'):
                    entry_data['text_content_overlay_styles'][0]['overlay_style']['overlay_position'] = 'top'
            
            # Add migration tag
            if 'tags' not in entry_data or not isinstance(entry_data['tags'], list):
                entry_data['tags'] = []
            if 'migrated-from-cms' not in entry_data['tags']:
                entry_data['tags'].append('migrated-from-cms')
            
            result = await self.contentstack_api.create_entry_async(content_type_uid, entry_data, self.entry_reuse_enabled)
            
            # Track this newly created entry for potential rollback
            self.created_entries.append({
                'uid': result['entry_uid'],
                'content_type': content_type_uid,
                'title': entry_data.get('title', 'No title')
            })
            print(f"[ENTRY] Added entry {result['entry_uid']} to rollback tracking ({len(self.created_entries)} total)")
            
            return {
                **result,
                'is_existing': False
            }
            
        except Exception as error:
            # Check if this is a duplicate page_id error
            if self.is_duplicate_page_id_error(error):
                handle_duplicate = os.getenv('HANDLE_DUPLICATE_PAGE_ID', 'false').lower() == 'true'
                
                if handle_duplicate:
                    print(f"[ENTRY] Duplicate page_id detected and HANDLE_DUPLICATE_PAGE_ID is enabled, retrying with timestamp suffix")
                    
                    retry_entry_data = json.loads(json.dumps(entry_data))
                    timestamp = int(time.time() * 1000)
                    
                    if 'page_id' in retry_entry_data:
                        original_page_id = retry_entry_data['page_id']
                        retry_entry_data['page_id'] = f"{original_page_id}-{timestamp}"
                        print(f"[ENTRY] Updated page_id from \"{original_page_id}\" to \"{retry_entry_data['page_id']}\"")
                    else:
                        retry_entry_data['page_id'] = f"entry-{timestamp}"
                        print(f"[ENTRY] Added new page_id: \"{retry_entry_data['page_id']}\"")
                    
                    try:
                        result = await self.contentstack_api.create_entry(content_type_uid, retry_entry_data)
                        print(f"[ENTRY] Successfully created entry with modified page_id")
                        
                        self.created_entries.append({
                            'uid': result['entry_uid'],
                            'content_type': content_type_uid,
                            'title': retry_entry_data.get('title', 'No title')
                        })
                        print(f"[ENTRY] Added entry {result['entry_uid']} to rollback tracking ({len(self.created_entries)} total)")
                        
                        return {
                            **result,
                            'is_existing': False
                        }
                    except Exception as retry_error:
                        print(f"[ENTRY] Retry failed even with modified page_id: {str(retry_error)}")
                        raise retry_error
                else:
                    print(f"[ENTRY] Duplicate page_id detected but HANDLE_DUPLICATE_PAGE_ID is disabled, throwing original error")
                    raise
            else:
                raise
    
    def is_duplicate_page_id_error(self, error: Exception) -> bool:
        """
        Check if the error is a duplicate page_id error
        
        Args:
            error: The error to check
            
        Returns:
            True if it's a duplicate page_id error
        """
        error_str = str(error).lower()
        
        is_duplicate = (
            'is not unique' in error_str or
            'page_id' in error_str or
            'duplicate' in error_str
        )
        
        if is_duplicate:
            print(f"[ENTRY] ✅ Detected duplicate page_id error pattern")
        else:
            print(f"[ENTRY] ❌ No duplicate page_id error pattern detected")
        
        return is_duplicate
    
    async def process_nested_entries(self, obj: Any):
        """
        Process nested entries within an entry
        
        Args:
            obj: Object to search for nested entries
        """
        if isinstance(obj, list):
            for item in obj:
                await self.process_nested_entries(item)
                
        elif isinstance(obj, dict):
            # Check if this is a nested entry
            if ('_content_type_uid' in obj and 'entry' in obj) or (obj.get('_content_type_uid') == 'link_flyout'):
                print(f"[NESTED] Found nested entry of type: {obj['_content_type_uid']}")
                
                # Process the nested entry
                nested_entry_uid = await self.process_entry(obj['entry'], obj['_content_type_uid'])
                
                # Replace with reference
                obj['uid'] = nested_entry_uid
                obj['_content_type_uid'] = obj['_content_type_uid']
                if 'entry' in obj:
                    del obj['entry']
                
                print(f"[NESTED] Nested entry processed, UID: {nested_entry_uid}")
            else:
                # Recursively process all properties
                for key, value in obj.items():
                    await self.process_nested_entries(value)
    
    def replace_asset_references(self, obj: Any):
        """
        Replace asset references with Contentstack asset references
        
        Args:
            obj: Object to search for asset references
        """
        if isinstance(obj, list):
            for i in range(len(obj)):
                if obj[i] and isinstance(obj[i], dict) and 'url' in obj[i] and 'filename' in obj[i]:
                    if len(obj) > 1:
                        print(f"[ASSET REF] Skipping video/subtitle/thumbnail from prod: {obj[i]['url']}")
                        continue
                    
                    asset_key = obj[i]['filename']
                    processed_asset = self.asset_cache.get(asset_key)
                    
                    if processed_asset:
                        if processed_asset.get('is_skipped'):
                            print(f"[ASSET REF] Asset was skipped ({processed_asset['skip_reason']}), removing reference: {asset_key}")
                            obj[i] = None
                        else:
                            print(f"[ASSET REF] Replacing asset reference: {asset_key}")
                            obj[i] = processed_asset['contentstack_reference']
                            
                            if processed_asset['contentstack_reference'].get('extension') == 'mp4':
                                if processed_asset.get('subtitle_reference', {}).get('id'):
                                    obj.insert(i + 1, processed_asset['subtitle_reference'])
                                if processed_asset.get('thumbnail_reference', {}).get('id'):
                                    obj.insert(i + 2, processed_asset['thumbnail_reference'])
                    else:
                        print(f"[ASSET REF] Asset not found in cache: {asset_key}")
                else:
                    self.replace_asset_references(obj[i])
                    
        elif isinstance(obj, dict):
            if 'rich_text_editor' in obj:
                obj['rich_text_editor'] = self.replace_image_src_in_html(obj['rich_text_editor'])
            elif 'markdown_text' in obj and isinstance(obj['markdown_text'], str):
                obj['markdown_text'] = self.replace_image_markdown(obj['markdown_text'])
                print(f"[MARKDOWN] Processed markdown text: {obj['markdown_text']}")
            else:
                for key, value in obj.items():
                    self.replace_asset_references(value)
    
    def replace_image_markdown(self, text: str) -> str:
        """
        Replace image URLs in markdown text with processed asset URLs
        
        Args:
            text: Markdown text
            
        Returns:
            Updated markdown text
        """
        if not text or not isinstance(text, str):
            return text
        
        output_text = text
        links = self.extract_links_from_markdown(text)
        
        for link in links:
            link_url = link['url'].split('?')[0]
            parts = link_url.split('/')
            filename = parts[-1]
            
            if filename not in self.asset_cache:
                print(f"[MARKDOWN] Asset not found in cache for filename: {filename}, skipping")
                continue
            
            processed_asset = self.asset_cache[filename]
            if processed_asset and processed_asset.get('cdn_url'):
                output_text = re.sub(re.escape(link_url), processed_asset['cdn_url'], output_text)
                print(f"[MARKDOWN] Replaced {link_url} with {processed_asset['cdn_url']}")
        
        print(f"[MARKDOWN] Processed text for markdown image replacement")
        return output_text
    
    def replace_image_src_in_html(self, html_text: str) -> str:
        """
        Replace image src attributes in HTML with processed asset URLs
        
        Args:
            html_text: HTML content
            
        Returns:
            Updated HTML content
        """
        if not html_text or not isinstance(html_text, str):
            return html_text
        
        print(f"[IMG REPLACEMENT] Processing HTML content for image src replacement")
        
        img_regex = r'<img([^>]*?)src=["\']([^"\']+)["\']([^>]*?)>'
        replaced_count = 0
        
        def replace_match(match):
            nonlocal replaced_count
            before_src = match.group(1)
            src_url = match.group(2)
            after_src = match.group(3)
            
            print(f"[IMG REPLACEMENT] Found image src: {src_url}")
            
            if not src_url or src_url.startswith('#') or src_url.startswith('data:'):
                print(f"[IMG REPLACEMENT] Skipping invalid/data URL: {src_url}")
                return match.group(0)
            
            try:
                full_url = src_url
                if src_url.startswith('/'):
                    full_url = "https://www.costco.com" + src_url
                
                parts = full_url.split('/')
                filename = parts[-1]
                clean_filename = filename.split('?')[0] if '?' in filename else filename
                extension = clean_filename.split('.')[-1].lower() if '.' in clean_filename else ''
                
                if extension not in self.allowed_extensions:
                    print(f"[IMG REPLACEMENT] Skipping non-allowed extension: {extension}")
                    return match.group(0)
                
                asset_key = clean_filename
                processed_asset = self.asset_cache.get(asset_key)
                
                if processed_asset and not processed_asset.get('is_skipped') and processed_asset.get('cdn_url'):
                    print(f"[IMG REPLACEMENT] Replacing {src_url} with {processed_asset['cdn_url']}")
                    replaced_count += 1
                    return f'<img{before_src}src="{processed_asset["cdn_url"]}"{after_src}>'
                else:
                    if processed_asset and processed_asset.get('is_skipped'):
                        print(f"[IMG REPLACEMENT] Asset skipped, keeping original: {src_url}")
                    else:
                        print(f"[IMG REPLACEMENT] Asset not found in cache: {clean_filename}")
                    return match.group(0)
                    
            except Exception as error:
                print(f"[IMG REPLACEMENT] Error processing: {str(error)}")
                return match.group(0)
        
        updated_html = re.sub(img_regex, replace_match, html_text)
        
        if replaced_count > 0:
            print(f"[IMG REPLACEMENT] Successfully replaced {replaced_count} image src attributes")
        else:
            print(f"[IMG REPLACEMENT] No image src attributes were replaced")
        
        return updated_html
    
    async def handle_rich_text_images(self, html_text: str):
        """
        Handle images in rich text editor content
        
        Args:
            html_text: HTML content
        """
        if not html_text or not isinstance(html_text, str):
            return
        
        print(f"[RICH TEXT] Processing rich text content for images")
        
        img_regex = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>'
        image_count = 0
        
        for match in re.finditer(img_regex, html_text):
            src_url = match.group(1)
            image_count += 1
            
            print(f"[RICH TEXT] Found image {image_count}: {src_url}")
            
            if not src_url or src_url.startswith('#') or src_url.startswith('data:'):
                print(f"[RICH TEXT] Skipping invalid/relative URL: {src_url}")
                continue
            
            try:
                full_url = src_url
                if src_url.startswith('/'):
                    full_url = "https://www.costco.com" + src_url
                
                parts = full_url.split('/')
                filename = parts[-1]
                filename = filename.split('?')[0] if '?' in filename else filename
                extension = filename.split('.')[-1].lower() if '.' in filename else ''
                
                if extension not in self.allowed_extensions:
                    print(f"[RICH TEXT] Skipping non-allowed extension: {extension}")
                    continue
                
                asset_obj = {
                    'url': full_url,
                    'filename': filename,
                    'extension': extension
                }
                
                print(f"[RICH TEXT] Processing asset: {filename}")
                await self.process_asset(asset_obj)
                print(f"[RICH TEXT] Successfully processed asset: {filename}")
                
            except Exception as error:
                print(f"[RICH TEXT] Error processing image {src_url}: {str(error)}")
                # Continue processing other images
        
        if image_count == 0:
            print(f"[RICH TEXT] No images found in rich text content")
        else:
            print(f"[RICH TEXT] Completed processing {image_count} images")
    
    def get_processing_summary(self) -> Dict:
        """
        Get processing summary
        
        Returns:
            Summary of processed content
        """
        assets = [
            {
                'key': key,
                'brandfolder_asset_id': value.get('brandfolder_asset_id'),
                'cdn_url': value.get('cdn_url'),
                'is_existing': value.get('is_existing', False),
                'is_skipped': value.get('is_skipped', False),
                'skip_reason': value.get('skip_reason'),
                'mimetype': value.get('mimetype'),
                'thumbnail_url': value.get('thumbnail_url')
            }
            for key, value in self.asset_cache.items()
        ]
        
        entries = [
            {
                'key': key,
                'uid': value['uid'],
                'content_type': value['content_type'],
                'title': value['title'],
                'is_existing': value.get('is_existing', False)
            }
            for key, value in self.entry_cache.items()
        ]
        
        existing_assets = sum(1 for a in assets if a['is_existing'] and not a['is_skipped'])
        new_assets = sum(1 for a in assets if not a['is_existing'] and not a['is_skipped'])
        skipped_assets = sum(1 for a in assets if a['is_skipped'])
        existing_entries = sum(1 for e in entries if e['is_existing'])
        new_entries = sum(1 for e in entries if not e['is_existing'])
        
        return {
            'assets_processed': len(self.asset_cache),
            'existing_assets': existing_assets,
            'new_assets': new_assets,
            'skipped_assets': skipped_assets,
            'entries_processed': len(self.entry_cache),
            'existing_entries': existing_entries,
            'new_entries': new_entries,
            'created_entries_for_rollback': len(self.created_entries),
            'assets': assets,
            'entries': entries,
            'created_entries': self.created_entries
        }
    
    async def process_workflow_for_all_entries(
        self,
        root_entry_uid: str,
        root_content_type: str = 'feature_page'
    ) -> Dict:
        """
        Process workflow for all entries (nested and root)
        Moves entries through workflow stages: Review -> Approved
        
        Args:
            root_entry_uid: The root entry UID
            root_content_type: The root entry content type
            
        Returns:
            Workflow processing result
        """
        try:
            print('\n=== STARTING WORKFLOW PROCESSING ===')
            print(f"Root entry UID: {root_entry_uid}")
            print(f"Root content type: {root_content_type}")
            
            # Workflow stage UIDs
            REVIEW_STAGE_UID = 'blt17e0c5c565fa65c3'
            APPROVED_STAGE_UID = 'blt0915ab57da3d0af1'
            
            # Separate nested entries and root entry
            nested_entries = [
                {
                    'uid': value['uid'],
                    'content_type': value['content_type'],
                    'title': value['title'],
                    'is_root': False
                }
                for key, value in self.entry_cache.items()
                if value['uid'] != root_entry_uid
            ]
            
            root_entry = {'uid': root_entry_uid, 'content_type': root_content_type, 'is_root': True}
            
            print(f"\n[WORKFLOW] Processing workflow for {len(nested_entries)} nested entries + 1 root entry")
            print(f"[WORKFLOW] Strategy: Nested entries first (Review → Approved), then root entry")
            
            processed_count = 0
            failed_count = 0
            failed_entries = []
            
            # PHASE 1: Process nested entries
            print(f"\n[WORKFLOW] === PHASE 1: PROCESSING {len(nested_entries)} NESTED ENTRIES ===")
            
            for i, entry in enumerate(nested_entries, 1):
                print(f"\n[WORKFLOW] Processing nested entry {i}/{len(nested_entries)}: {entry['uid']} ({entry['content_type']})")
                
                # Step 1: Move to Review stage
                review_stage_success = False
                try:
                    print(f"[WORKFLOW] Moving to Review stage: {REVIEW_STAGE_UID}")
                    await self.contentstack_api.update_workflow_stage_async(
                        entry['content_type'],
                        entry['uid'],
                        REVIEW_STAGE_UID
                    )
                    print(f"[WORKFLOW] ✅ Moved to Review stage successfully")
                    review_stage_success = True
                    await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s
                    
                except Exception as review_error:
                    print(f"[WORKFLOW] ⚠️ Failed to move to Review stage: {str(review_error)}")
                    print(f"[WORKFLOW] ⚠️ Ignoring Review stage error and skipping Approved stage")
                    failed_count += 1
                    failed_entries.append({
                        'uid': entry['uid'],
                        'content_type': entry['content_type'],
                        'error': f"Review stage failed: {str(review_error)}",
                        'phase': 'nested',
                        'stage': 'review'
                    })
                    continue
                
                # Step 2: Move to Approved stage (only if Review succeeded)
                if review_stage_success:
                    # Wait briefly for Review stage to be processed
                    await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s
                    
                    try:
                        print(f"[WORKFLOW] Moving to Approved stage: {APPROVED_STAGE_UID}")
                        await self.contentstack_api.update_workflow_stage_async(
                            entry['content_type'],
                            entry['uid'],
                            APPROVED_STAGE_UID
                        )
                        print(f"[WORKFLOW] ✅ Moved to Approved stage successfully")
                        processed_count += 1
                        await asyncio.sleep(0.1)  # Reduced from 0.3s to 0.1s
                        
                    except Exception as approved_error:
                        failed_count += 1
                        failed_entries.append({
                            'uid': entry['uid'],
                            'content_type': entry['content_type'],
                            'error': f"Approved stage failed: {str(approved_error)}",
                            'phase': 'nested',
                            'stage': 'approved'
                        })
                        print(f"[WORKFLOW] ❌ Failed to move to Approved stage: {str(approved_error)}")
            
            print(f"\n[WORKFLOW] Phase 1 completed: {processed_count - failed_count}/{len(nested_entries)} nested entries processed successfully")
            
            if failed_count > 0:
                print(f"[WORKFLOW] ⚠️ {failed_count} nested entries failed workflow processing")
                print(f"[WORKFLOW] Proceeding with root entry processing despite failures")
            
            # PHASE 2: Process root entry
            print(f"\n[WORKFLOW] === PHASE 2: PROCESSING ROOT ENTRY ===")
            print(f"\n[WORKFLOW] Processing root entry: {root_entry['uid']} ({root_entry['content_type']})")
            
            # Step 1: Move root to Review stage
            root_review_success = False
            try:
                print(f"[WORKFLOW] Moving root entry to Review stage: {REVIEW_STAGE_UID}")
                await self.contentstack_api.update_workflow_stage_async(
                    root_entry['content_type'],
                    root_entry['uid'],
                    REVIEW_STAGE_UID
                )
                print(f"[WORKFLOW] ✅ Root entry moved to Review stage successfully")
                root_review_success = True
                await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s
                
            except Exception as review_error:
                print(f"[WORKFLOW] ⚠️ Failed to move root entry to Review stage: {str(review_error)}")
                failed_count += 1
                failed_entries.append({
                    'uid': root_entry['uid'],
                    'content_type': root_entry['content_type'],
                    'error': f"Review stage failed: {str(review_error)}",
                    'phase': 'root',
                    'stage': 'review'
                })
            
            # Step 2: Move root to Approved stage
            if root_review_success:
                # Wait briefly for Review stage to be processed
                await asyncio.sleep(0.1)  # Reduced from 0.5s to 0.1s
                
                try:
                    print(f"[WORKFLOW] Moving root entry to Approved stage: {APPROVED_STAGE_UID}")
                    await self.contentstack_api.update_workflow_stage_async(
                        root_entry['content_type'],
                        root_entry['uid'],
                        APPROVED_STAGE_UID
                    )
                    print(f"[WORKFLOW] ✅ Root entry moved to Approved stage successfully")
                    processed_count += 1
                    
                except Exception as approved_error:
                    failed_count += 1
                    failed_entries.append({
                        'uid': root_entry['uid'],
                        'content_type': root_entry['content_type'],
                        'error': f"Approved stage failed: {str(approved_error)}",
                        'phase': 'root',
                        'stage': 'approved'
                    })
                    print(f"[WORKFLOW] ❌ Failed to move root entry to Approved stage: {str(approved_error)}")
            
            total_entries = len(nested_entries) + 1
            print(f"\n[WORKFLOW] === WORKFLOW PROCESSING COMPLETED ===")
            print(f"[WORKFLOW] Total processed: {processed_count}/{total_entries}")
            print(f"[WORKFLOW] Successful: {processed_count - failed_count}")
            print(f"[WORKFLOW] Failed: {failed_count}")
            
            nested_failures = [e for e in failed_entries if e['phase'] == 'nested']
            root_failures = [e for e in failed_entries if e['phase'] == 'root']
            
            if failed_entries:
                print(f"\n[WORKFLOW] Failed entries breakdown:")
                if nested_failures:
                    print(f"  Nested entries failed ({len(nested_failures)}):")
                    for i, failed in enumerate(nested_failures, 1):
                        print(f"    {i}. {failed['uid']} ({failed['content_type']}): {failed['error']}")
                if root_failures:
                    print(f"  Root entry failed ({len(root_failures)}):")
                    for i, failed in enumerate(root_failures, 1):
                        print(f"    {i}. {failed['uid']} ({failed['content_type']}): {failed['error']}")
            
            return {
                'success': failed_count == 0,
                'total_entries': total_entries,
                'nested_entries_count': len(nested_entries),
                'processed_count': processed_count,
                'failed_count': failed_count,
                'failed_entries': failed_entries,
                'nested_entries_processed': len(nested_entries) - len(nested_failures),
                'root_entry_processed': len(root_failures) == 0
            }
            
        except Exception as error:
            print(f"\n[WORKFLOW] ❌ Workflow processing failed: {str(error)}")
            raise
    
    async def publish_root_entry_with_deep_publish(
        self,
        root_entry_uid: str,
        root_content_type: str = 'feature_page',
        environments: List[str] = None,
        locales: List[str] = None
    ) -> Dict:
        """
        Publish root entry with deep publish for all nested entries
        
        Args:
            root_entry_uid: The root entry UID
            root_content_type: The root entry content type
            environments: Environments to publish to
            locales: Locales to publish to
            
        Returns:
            Publishing result
        """
        if environments is None:
            environments = ['production']
        if locales is None:
            # Use environment-specific locale from ContentStack API
            locales = [self.contentstack_api.locale]
        
        try:
            print('\n=== STARTING DEEP PUBLISH ===')
            print(f"Root entry UID: {root_entry_uid}")
            print(f"Root content type: {root_content_type}")
            print(f"Environments: {', '.join(environments)}")
            print(f"Locales: {', '.join(locales)}")
            
            # Publish the root entry with deep publish enabled
            publish_result = await self.contentstack_api.publish_entry_with_deep_publish_async(
                root_content_type,
                root_entry_uid,
                environments,
                locales
            )
            
            if publish_result.get('success'):
                print('\n[PUBLISH] ✅ Root entry published successfully with deep publish')
                print(f"[PUBLISH] All nested entries should be published automatically")
                
                return {
                    'success': True,
                    'root_entry_uid': root_entry_uid,
                    'published_environments': environments,
                    'published_locales': locales,
                    'publish_data': publish_result.get('data')
                }
            else:
                raise Exception('Publishing failed - no success response received')
                
        except Exception as error:
            print(f"\n[PUBLISH] ❌ Deep publish failed: {str(error)}")
            raise
    
    def generate_published_page_url(self, page_id: str, base_url: str = None) -> str:
        """
        Generate published page URL
        
        Args:
            page_id: The page_id of the root entry
            base_url: Base URL for published pages (optional, uses default if not provided)
            
        Returns:
            The published page URL
        """
        if base_url is None:
            base_url = 'https://web-prd.pd.gdx.cc-costco.com/consumer-web/browse/prd/homepage-usbc/f/-/'
        
        published_url = base_url + page_id
        print(f"\n[URL] Generated published page URL: {published_url}")
        return published_url
    
    async def flush_cache(self, page_id: str, cache_flush_base_url: str = None) -> Dict:
        """
        Initiate cache flush for a page ID
        
        Args:
            page_id: Page ID to flush cache for
            cache_flush_base_url: Base URL for cache flush (optional)
            
        Returns:
            Cache flush result
        """
        import requests
        
        try:
            if not page_id:
                raise Exception('Page ID is required for cache flush')
            
            if not cache_flush_base_url:
                print("[CACHE] ⚠️ Cache flush base URL not configured - skipping cache flush")
                return {
                    'success': False,
                    'skipped': True,
                    'reason': 'Cache flush base URL not configured'
                }
            
            cache_flush_url = f"{cache_flush_base_url}{page_id}"
            print(f"[CACHE] Initiating cache flush: {cache_flush_url}")
            
            response = requests.get(cache_flush_url, timeout=30, headers={'User-Agent': 'ContentProcessor/1.0'})
            response.raise_for_status()
            
            print(f"[CACHE] ✅ Cache flush initiated successfully")
            print(f"[CACHE] Response status: {response.status_code}")
            
            return {
                'success': True,
                'status': response.status_code,
                'data': response.text,
                'url': cache_flush_url
            }
            
        except Exception as error:
            error_msg = str(error)
            # Check if it's a 403 Forbidden error
            if '403' in error_msg or 'Forbidden' in error_msg:
                print(f"[CACHE] ⚠️ Cache flush failed: {error_msg}")
                print(f"[CACHE] This may be due to authentication/permissions - verify cache flush URL and credentials")
            else:
                print(f"[CACHE] ❌ Cache flush failed: {error_msg}")
            
            return {
                'success': False,
                'error': error_msg,
                'url': cache_flush_url if 'cache_flush_url' in locals() else None
            }
    
    async def complete_workflow_and_publish(
        self,
        root_entry_uid: str,
        page_id: str,
        root_content_type: str = 'feature_page',
        published_page_base_url: str = None,
        cache_flush_base_url: str = None
    ) -> Dict:
        """
        Complete workflow and publishing process
        
        Args:
            root_entry_uid: The root entry UID
            page_id: The page_id for URL generation
            root_content_type: The root entry content type
            published_page_base_url: Base URL for published pages (environment-specific)
            cache_flush_base_url: Base URL for cache flush (environment-specific)
            
        Returns:
            Complete process result
        """
        import asyncio
        start_time = time.time()
        
        try:
            print('\n🚀 STARTING COMPLETE WORKFLOW AND PUBLISH PROCESS')
            print(f"Root entry UID: {root_entry_uid}")
            print(f"Page ID: {page_id}")
            print(f"Root content type: {root_content_type}")
            
            # Step 1: Process workflow for all entries
            print('\n--- STEP 1: WORKFLOW PROCESSING ---')
            workflow_result = await self.process_workflow_for_all_entries(root_entry_uid, root_content_type)
            
            if not workflow_result['success']:
                print(f"\n⚠️ Workflow processing completed with {workflow_result['failed_count']} failed entries, proceeding to publish root entry")
            else:
                print('\n✅ Workflow processing completed successfully for all entries')
            
            # Step 2: Publish root entry with deep publish
            print('\n--- STEP 2: DEEP PUBLISHING ---')
            publish_result = await self.publish_root_entry_with_deep_publish(root_entry_uid, root_content_type)
            
            if not publish_result['success']:
                raise Exception('Publishing failed')
            
            print('\n✅ Root entry and all nested entries published successfully')
            
            # Step 3: Generate published page URL
            print('\n--- STEP 3: URL GENERATION ---')
            published_url = self.generate_published_page_url(page_id, published_page_base_url)
            
            # Step 4: Wait before cache flush to ensure publish is propagated
            print('\n--- STEP 4: CACHE FLUSH ---')
            print('[DELAY] ⏳ Waiting 2 seconds before cache flush...')
            await asyncio.sleep(2)
            
            # Initiate cache flush
            cache_flush_result = await self.flush_cache(page_id, cache_flush_base_url)
            
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            print('\n🎉 WORKFLOW AND PUBLISH PROCESS COMPLETED SUCCESSFULLY')
            print(f"Duration: {duration} seconds")
            print(f"Published URL: {published_url}")
            if cache_flush_result.get('success'):
                print(f"Cache Flush: ✅ Success")
            elif cache_flush_result.get('skipped'):
                print(f"Cache Flush: ⚠️ Skipped ({cache_flush_result.get('reason', 'unknown reason')})")
            else:
                print(f"Cache Flush: ❌ Failed")
            
            return {
                'success': True,
                'root_entry_uid': root_entry_uid,
                'page_id': page_id,
                'published_url': published_url,
                'duration': duration,
                'workflow_result': workflow_result,
                'publish_result': publish_result,
                'cache_flush_result': cache_flush_result
            }
            
        except Exception as error:
            end_time = time.time()
            duration = round(end_time - start_time, 2)
            
            print('\n💥 WORKFLOW AND PUBLISH PROCESS FAILED')
            print(f"Duration: {duration} seconds")
            print(f"Error: {str(error)}")
            
            raise


# Import asyncio at the top level for async operations
import asyncio
