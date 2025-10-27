"""
File Validation and Security Service

This service handles file type validation, size limits, content sanitization,
and security checks for the File Viewer & Editor System.
"""

import os
import mimetypes
# import magic  # Temporarily disabled for Windows compatibility
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import bleach
import re

logger = logging.getLogger(__name__)


class FileValidationService:
    """Service for validating files and ensuring security"""
    
    def __init__(self):
        # Default file type configurations
        self.file_type_configs = {
            'documents': {
                'extensions': ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt'],
                'mime_types': [
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/msword',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/vnd.ms-excel',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'application/vnd.ms-powerpoint'
                ],
                'max_size': 100 * 1024 * 1024,  # 100MB
                'editable': True,
                'conversion_required': True
            },
            'pdf': {
                'extensions': ['.pdf'],
                'mime_types': ['application/pdf'],
                'max_size': 50 * 1024 * 1024,  # 50MB
                'editable': False,
                'conversion_required': True
            },
            'images': {
                'extensions': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'],
                'mime_types': [
                    'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
                    'image/tiff', 'image/webp', 'image/svg+xml'
                ],
                'max_size': 50 * 1024 * 1024,  # 50MB
                'editable': True,
                'conversion_required': False
            },
            'text': {
                'extensions': ['.txt', '.md', '.json', '.xml', '.csv', '.js', '.py', '.html', '.css', '.yaml', '.yml'],
                'mime_types': [
                    'text/plain', 'text/markdown', 'application/json', 'text/xml',
                    'text/csv', 'text/javascript', 'text/x-python', 'text/html',
                    'text/css', 'application/x-yaml'
                ],
                'max_size': 10 * 1024 * 1024,  # 10MB
                'editable': True,
                'conversion_required': False
            },
            'media': {
                'extensions': ['.mp4', '.avi', '.mkv', '.webm', '.mp3', '.wav', '.flac', '.ogg'],
                'mime_types': [
                    'video/mp4', 'video/x-msvideo', 'video/x-matroska', 'video/webm',
                    'audio/mpeg', 'audio/wav', 'audio/flac', 'audio/ogg'
                ],
                'max_size': 500 * 1024 * 1024,  # 500MB
                'editable': False,
                'conversion_required': False
            }
        }
        
        # Dangerous file extensions that should never be allowed
        self.dangerous_extensions = {
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar',
            '.app', '.deb', '.pkg', '.dmg', '.sh', '.ps1', '.msi', '.dll'
        }
        
        # HTML sanitization settings
        self.allowed_html_tags = [
            'p', 'br', 'strong', 'em', 'u', 'i', 'b', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'thead', 'tbody', 'tfoot',
            'div', 'span', 'img', 'a', 'blockquote', 'code', 'pre'
        ]
        
        self.allowed_html_attributes = {
            'img': ['src', 'alt', 'width', 'height', 'title'],
            'a': ['href', 'title', 'target'],
            'table': ['class', 'id'],
            'td': ['colspan', 'rowspan', 'class'],
            'th': ['colspan', 'rowspan', 'class'],
            'div': ['class', 'id'],
            'span': ['class', 'id'],
            'p': ['class'],
            'h1': ['class'], 'h2': ['class'], 'h3': ['class'],
            'h4': ['class'], 'h5': ['class'], 'h6': ['class']
        }
    
    def validate_file(self, file_path: str, user_permissions: Optional[List[str]] = None) -> Dict[str, any]:
        """
        Comprehensive file validation
        
        Args:
            file_path: Path to the file to validate
            user_permissions: List of user permissions for access control
            
        Returns:
            Dict with validation results and file info
        """
        result = {
            'valid': False,
            'errors': [],
            'warnings': [],
            'file_info': {},
            'security_checks': {}
        }
        
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                result['errors'].append("File does not exist")
                return result
            
            if not os.path.isfile(file_path):
                result['errors'].append("Path is not a file")
                return result
            
            # Get basic file info
            file_stat = os.stat(file_path)
            file_size = file_stat.st_size
            file_name = Path(file_path).name
            file_ext = Path(file_path).suffix.lower()
            
            result['file_info'] = {
                'name': file_name,
                'size': file_size,
                'extension': file_ext,
                'path': file_path
            }
            
            # Security check: dangerous extensions
            if file_ext in self.dangerous_extensions:
                result['errors'].append(f"File type '{file_ext}' is not allowed for security reasons")
                return result
            
            # Security check: path traversal
            if '..' in file_path or file_path.startswith('/'):
                result['errors'].append("Invalid file path detected")
                return result
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            
            # Try to get more accurate MIME type using python-magic if available
            try:
                import magic
                mime_type_magic = magic.from_file(file_path, mime=True)
                if mime_type_magic and mime_type_magic != 'application/octet-stream':
                    mime_type = mime_type_magic
            except ImportError:
                logger.warning("python-magic not available, using basic MIME type detection")
            except Exception as e:
                logger.warning(f"Error detecting MIME type with magic: {str(e)}")
            
            result['file_info']['mime_type'] = mime_type
            
            # Find matching file type configuration
            file_type_config = self._get_file_type_config(file_ext, mime_type)
            
            if not file_type_config:
                result['errors'].append(f"File type '{file_ext}' is not supported")
                return result
            
            result['file_info']['type_config'] = file_type_config
            
            # Validate file size
            if file_size > file_type_config['max_size']:
                max_size_mb = file_type_config['max_size'] / (1024 * 1024)
                current_size_mb = file_size / (1024 * 1024)
                result['errors'].append(
                    f"File size ({current_size_mb:.1f}MB) exceeds maximum allowed size ({max_size_mb:.1f}MB)"
                )
                return result
            
            # Content validation for specific file types
            content_validation = self._validate_file_content(file_path, file_ext, mime_type)
            result['security_checks'].update(content_validation)
            
            if content_validation.get('errors'):
                result['errors'].extend(content_validation['errors'])
                return result
            
            if content_validation.get('warnings'):
                result['warnings'].extend(content_validation['warnings'])
            
            # Permission checks
            if user_permissions:
                permission_check = self._check_file_permissions(file_path, user_permissions)
                result['security_checks']['permissions'] = permission_check
                
                if not permission_check['can_read']:
                    result['errors'].append("Insufficient permissions to read file")
                    return result
            
            # If we get here, file is valid
            result['valid'] = True
            
        except Exception as e:
            logger.error(f"Error validating file {file_path}: {str(e)}")
            result['errors'].append(f"Validation error: {str(e)}")
        
        return result
    
    def sanitize_html_content(self, html_content: str, strict: bool = True) -> str:
        """
        Sanitize HTML content to prevent XSS attacks
        
        Args:
            html_content: HTML content to sanitize
            strict: If True, use strict sanitization rules
            
        Returns:
            Sanitized HTML content
        """
        if not html_content:
            return ""
        
        # Use more restrictive settings for strict mode
        if strict:
            allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'table', 'tr', 'td', 'th']
            allowed_attributes = {
                'table': ['class'],
                'td': ['colspan', 'rowspan'],
                'th': ['colspan', 'rowspan']
            }
        else:
            allowed_tags = self.allowed_html_tags
            allowed_attributes = self.allowed_html_attributes
        
        # Clean the HTML
        cleaned_html = bleach.clean(
            html_content,
            tags=allowed_tags,
            attributes=allowed_attributes,
            strip=True,
            strip_comments=True
        )
        
        # Additional security checks
        # Remove any remaining script-like content
        script_patterns = [
            r'javascript:',
            r'vbscript:',
            r'data:text/html',
            r'on\w+\s*=',  # Event handlers like onclick, onload, etc.
        ]
        
        for pattern in script_patterns:
            cleaned_html = re.sub(pattern, '', cleaned_html, flags=re.IGNORECASE)
        
        return cleaned_html
    
    def validate_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Quick file size validation
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            file_size = os.path.getsize(file_path)
            file_ext = Path(file_path).suffix.lower()
            
            file_type_config = self._get_file_type_config(file_ext, None)
            
            if not file_type_config:
                return False, f"File type '{file_ext}' is not supported"
            
            if file_size > file_type_config['max_size']:
                max_size_mb = file_type_config['max_size'] / (1024 * 1024)
                return False, f"File size exceeds maximum allowed size ({max_size_mb:.1f}MB)"
            
            return True, None
            
        except Exception as e:
            return False, f"Error validating file size: {str(e)}"
    
    def _get_file_type_config(self, file_ext: str, mime_type: Optional[str]) -> Optional[Dict]:
        """Get file type configuration based on extension and MIME type"""
        for config_name, config in self.file_type_configs.items():
            if file_ext in config['extensions']:
                return config
            
            if mime_type and mime_type in config['mime_types']:
                return config
        
        return None
    
    def _validate_file_content(self, file_path: str, file_ext: str, mime_type: Optional[str]) -> Dict[str, any]:
        """Validate file content for security issues"""
        result = {
            'errors': [],
            'warnings': [],
            'content_type': 'unknown'
        }
        
        try:
            # For text files, check for suspicious content
            if mime_type and mime_type.startswith('text/') or file_ext in ['.txt', '.md', '.json', '.xml', '.csv']:
                result['content_type'] = 'text'
                
                # Read a sample of the file to check for suspicious content
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        sample_content = f.read(1024)  # Read first 1KB
                    
                    # Check for script tags or suspicious patterns
                    suspicious_patterns = [
                        r'<script[^>]*>',
                        r'javascript:',
                        r'vbscript:',
                        r'on\w+\s*=',
                    ]
                    
                    for pattern in suspicious_patterns:
                        if re.search(pattern, sample_content, re.IGNORECASE):
                            result['warnings'].append(f"Potentially suspicious content detected: {pattern}")
                
                except Exception as e:
                    result['warnings'].append(f"Could not validate text content: {str(e)}")
            
            # For binary files, basic checks
            elif file_ext in ['.docx', '.xlsx', '.pptx', '.pdf']:
                result['content_type'] = 'document'
                
                # Check if file is actually the expected type by reading magic bytes
                try:
                    with open(file_path, 'rb') as f:
                        magic_bytes = f.read(8)
                    
                    # Basic magic byte validation
                    if file_ext in ['.docx', '.xlsx', '.pptx']:
                        # Office files should start with PK (ZIP signature)
                        if not magic_bytes.startswith(b'PK'):
                            result['warnings'].append("File may not be a valid Office document")
                    
                    elif file_ext == '.pdf':
                        # PDF files should start with %PDF
                        if not magic_bytes.startswith(b'%PDF'):
                            result['errors'].append("File is not a valid PDF document")
                
                except Exception as e:
                    result['warnings'].append(f"Could not validate file format: {str(e)}")
            
            # For image files
            elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                result['content_type'] = 'image'
                
                # Basic image validation using PIL if available
                try:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        # Just opening and getting format validates the image
                        result['image_format'] = img.format
                        result['image_size'] = img.size
                
                except ImportError:
                    result['warnings'].append("PIL not available for image validation")
                except Exception as e:
                    result['errors'].append(f"Invalid image file: {str(e)}")
        
        except Exception as e:
            result['warnings'].append(f"Content validation error: {str(e)}")
        
        return result
    
    def _check_file_permissions(self, file_path: str, user_permissions: List[str]) -> Dict[str, bool]:
        """Check if user has required permissions for file operations"""
        # This is a basic implementation - should be enhanced based on your permission system
        return {
            'can_read': 'file:READ' in user_permissions or 'file:*' in user_permissions,
            'can_write': 'file:WRITE' in user_permissions or 'file:*' in user_permissions,
            'can_delete': 'file:DELETE' in user_permissions or 'file:*' in user_permissions
        }
    
    def get_supported_file_types(self) -> Dict[str, List[str]]:
        """Get list of supported file types"""
        result = {}
        for type_name, config in self.file_type_configs.items():
            result[type_name] = {
                'extensions': config['extensions'],
                'max_size_mb': config['max_size'] / (1024 * 1024),
                'editable': config['editable']
            }
        return result