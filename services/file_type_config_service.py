# services/file_type_config_service.py

from models.file_type_config import FileTypeConfig
from extensions import db
from datetime import datetime, timezone
import json

class FileTypeConfigService:
    """Service for managing file type configurations"""
    
    @staticmethod
    def get_all_configs():
        """Get all file type configurations"""
        return FileTypeConfig.query.order_by(FileTypeConfig.type_name).all()
    
    @staticmethod
    def get_enabled_configs():
        """Get only enabled file type configurations"""
        return FileTypeConfig.query.filter_by(is_enabled=True).order_by(FileTypeConfig.type_name).all()
    
    @staticmethod
    def get_config_by_id(config_id):
        """Get configuration by ID"""
        return FileTypeConfig.query.get(config_id)
    
    @staticmethod
    def get_config_by_type(type_name):
        """Get configuration by type name"""
        return FileTypeConfig.query.filter_by(type_name=type_name).first()
    
    @staticmethod
    def create_config(data):
        """Create a new file type configuration"""
        config = FileTypeConfig(
            type_name=data['type_name'],
            display_name=data['display_name'],
            handler_name=data['handler_name'],
            icon_class=data.get('icon_class', 'fas fa-file'),
            is_viewable=data.get('is_viewable', True),
            is_editable=data.get('is_editable', False),
            max_size_mb=data.get('max_size_mb', 100),
            is_enabled=data.get('is_enabled', True)
        )
        
        # Set MIME types and extensions
        config.mime_types_list = data.get('mime_types', [])
        config.extensions_list = data.get('extensions', [])
        config.settings_dict = data.get('settings', {})
        
        db.session.add(config)
        db.session.commit()
        return config
    
    @staticmethod
    def update_config(config_id, data):
        """Update an existing file type configuration"""
        config = FileTypeConfig.query.get(config_id)
        if not config:
            return None
        
        # Update basic fields
        if 'display_name' in data:
            config.display_name = data['display_name']
        if 'handler_name' in data:
            config.handler_name = data['handler_name']
        if 'icon_class' in data:
            config.icon_class = data['icon_class']
        if 'is_viewable' in data:
            config.is_viewable = data['is_viewable']
        if 'is_editable' in data:
            config.is_editable = data['is_editable']
        if 'max_size_mb' in data:
            config.max_size_mb = data['max_size_mb']
        if 'is_enabled' in data:
            config.is_enabled = data['is_enabled']
        
        # Update arrays and objects
        if 'mime_types' in data:
            config.mime_types_list = data['mime_types']
        if 'extensions' in data:
            config.extensions_list = data['extensions']
        if 'settings' in data:
            config.settings_dict = data['settings']
        
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return config
    
    @staticmethod
    def delete_config(config_id):
        """Delete a file type configuration"""
        config = FileTypeConfig.query.get(config_id)
        if not config:
            return False
        
        db.session.delete(config)
        db.session.commit()
        return True
    
    @staticmethod
    def toggle_config(config_id):
        """Toggle enabled/disabled status of a configuration"""
        config = FileTypeConfig.query.get(config_id)
        if not config:
            return None
        
        config.is_enabled = not config.is_enabled
        config.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return config
    
    @staticmethod
    def validate_file(file_path, file_size, mime_type=None, extension=None):
        """Validate a file against configuration rules"""
        # Determine file type
        config = None
        if mime_type:
            config = FileTypeConfig.get_config_for_mime_type(mime_type)
        elif extension:
            config = FileTypeConfig.get_config_for_extension(extension)
        
        if not config:
            return {
                'valid': False,
                'error': 'File type not supported',
                'config': None
            }
        
        if not config.is_enabled:
            return {
                'valid': False,
                'error': 'File type is disabled',
                'config': config.to_dict()
            }
        
        # Check file size
        max_size_bytes = config.max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            return {
                'valid': False,
                'error': f'File size exceeds maximum allowed size of {config.max_size_mb}MB',
                'config': config.to_dict()
            }
        
        return {
            'valid': True,
            'error': None,
            'config': config.to_dict()
        }
    
    @staticmethod
    def get_supported_types_summary():
        """Get a summary of all supported file types"""
        configs = FileTypeConfigService.get_enabled_configs()
        
        summary = {
            'total_types': len(configs),
            'viewable_types': len([c for c in configs if c.is_viewable]),
            'editable_types': len([c for c in configs if c.is_editable]),
            'mime_types': [],
            'extensions': [],
            'handlers': set()
        }
        
        for config in configs:
            summary['mime_types'].extend(config.mime_types_list)
            summary['extensions'].extend(config.extensions_list)
            summary['handlers'].add(config.handler_name)
        
        summary['handlers'] = list(summary['handlers'])
        return summary
    
    @staticmethod
    def initialize_default_configs():
        """Initialize default file type configurations if none exist"""
        if FileTypeConfig.query.count() > 0:
            return  # Already initialized
        
        default_configs = [
            {
                'type_name': 'text',
                'display_name': 'Text Files',
                'mime_types': [
                    'text/plain', 'text/markdown', 'application/json',
                    'text/javascript', 'text/css', 'text/html', 'text/xml',
                    'text/csv', 'text/yaml'
                ],
                'extensions': [
                    'txt', 'md', 'json', 'js', 'css', 'html', 'htm',
                    'xml', 'csv', 'log', 'ini', 'conf', 'cfg', 'yml', 'yaml'
                ],
                'handler_name': 'TextHandler',
                'icon_class': 'fas fa-file-alt',
                'is_viewable': True,
                'is_editable': True,
                'max_size_mb': 10,
                'settings': {
                    'encoding': 'utf-8',
                    'line_numbers': True,
                    'word_wrap': True
                }
            },
            {
                'type_name': 'image',
                'display_name': 'Images',
                'mime_types': [
                    'image/jpeg', 'image/png', 'image/gif', 'image/bmp',
                    'image/webp', 'image/svg+xml', 'image/x-icon'
                ],
                'extensions': [
                    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico'
                ],
                'handler_name': 'ImageHandler',
                'icon_class': 'fas fa-file-image',
                'is_viewable': True,
                'is_editable': True,
                'max_size_mb': 50,
                'settings': {
                    'thumbnail_size': 200,
                    'zoom_enabled': True,
                    'rotation_enabled': True
                }
            },
            {
                'type_name': 'video',
                'display_name': 'Videos',
                'mime_types': [
                    'video/mp4', 'video/x-msvideo', 'video/quicktime',
                    'video/x-ms-wmv', 'video/x-flv', 'video/webm', 'video/x-matroska'
                ],
                'extensions': [
                    'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'
                ],
                'handler_name': 'VideoHandler',
                'icon_class': 'fas fa-file-video',
                'is_viewable': True,
                'is_editable': False,
                'max_size_mb': 500,
                'settings': {
                    'autoplay': False,
                    'controls': True,
                    'preload': 'metadata'
                }
            },
            {
                'type_name': 'audio',
                'display_name': 'Audio Files',
                'mime_types': [
                    'audio/mpeg', 'audio/wav', 'audio/ogg',
                    'audio/flac', 'audio/aac', 'audio/mp4'
                ],
                'extensions': [
                    'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a'
                ],
                'handler_name': 'AudioHandler',
                'icon_class': 'fas fa-file-audio',
                'is_viewable': True,
                'is_editable': False,
                'max_size_mb': 100,
                'settings': {
                    'autoplay': False,
                    'controls': True,
                    'preload': 'metadata'
                }
            },
            {
                'type_name': 'pdf',
                'display_name': 'PDF Documents',
                'mime_types': ['application/pdf'],
                'extensions': ['pdf'],
                'handler_name': 'PDFHandler',
                'icon_class': 'fas fa-file-pdf',
                'is_viewable': True,
                'is_editable': False,
                'max_size_mb': 100,
                'settings': {
                    'page_navigation': True,
                    'zoom': True,
                    'search': True
                }
            },
            {
                'type_name': 'word',
                'display_name': 'Word Documents',
                'mime_types': [
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/msword'
                ],
                'extensions': ['docx', 'doc'],
                'handler_name': 'DocumentHandler',
                'icon_class': 'fas fa-file-word',
                'is_viewable': True,
                'is_editable': True,
                'max_size_mb': 100,
                'settings': {
                    'preserve_formatting': True,
                    'enable_editing': True,
                    'zoom': True
                }
            },
            {
                'type_name': 'excel',
                'display_name': 'Excel Spreadsheets',
                'mime_types': [
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/vnd.ms-excel'
                ],
                'extensions': ['xlsx', 'xls'],
                'handler_name': 'DocumentHandler',
                'icon_class': 'fas fa-file-excel',
                'is_viewable': True,
                'is_editable': True,
                'max_size_mb': 100,
                'settings': {
                    'sheet_navigation': True,
                    'formula_support': True,
                    'enable_editing': True,
                    'zoom': True
                }
            },
            {
                'type_name': 'powerpoint',
                'display_name': 'PowerPoint Presentations',
                'mime_types': [
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    'application/vnd.ms-powerpoint'
                ],
                'extensions': ['pptx', 'ppt'],
                'handler_name': 'DocumentHandler',
                'icon_class': 'fas fa-file-powerpoint',
                'is_viewable': True,
                'is_editable': True,
                'max_size_mb': 100,
                'settings': {
                    'slide_navigation': True,
                    'fullscreen_mode': True,
                    'notes_display': True,
                    'zoom': True,
                    'enable_editing': True
                }
            }
        ]
        
        for config_data in default_configs:
            FileTypeConfigService.create_config(config_data)