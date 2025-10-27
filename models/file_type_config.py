# models/file_type_config.py

from extensions import db
from datetime import datetime, timezone
import json

class FileTypeConfig(db.Model):
    """Model for file type configuration settings"""
    __tablename__ = 'file_type_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(50), unique=True, nullable=False)  # e.g., 'text', 'image', 'pdf'
    display_name = db.Column(db.String(100), nullable=False)  # e.g., 'Text Files', 'Images'
    mime_types = db.Column(db.Text, nullable=False)  # JSON array of MIME types
    extensions = db.Column(db.Text, nullable=False)  # JSON array of extensions
    handler_name = db.Column(db.String(100), nullable=False)  # Handler class name
    icon_class = db.Column(db.String(100), default='fas fa-file')
    is_viewable = db.Column(db.Boolean, default=True)
    is_editable = db.Column(db.Boolean, default=False)
    max_size_mb = db.Column(db.Integer, default=100)  # Maximum file size in MB
    settings = db.Column(db.Text)  # JSON object for additional settings
    is_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<FileTypeConfig {self.type_name}>'
    
    @property
    def mime_types_list(self):
        """Get MIME types as a list"""
        try:
            return json.loads(self.mime_types) if self.mime_types else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    @mime_types_list.setter
    def mime_types_list(self, value):
        """Set MIME types from a list"""
        self.mime_types = json.dumps(value) if value else '[]'
    
    @property
    def extensions_list(self):
        """Get extensions as a list"""
        try:
            return json.loads(self.extensions) if self.extensions else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    @extensions_list.setter
    def extensions_list(self, value):
        """Set extensions from a list"""
        self.extensions = json.dumps(value) if value else '[]'
    
    @property
    def settings_dict(self):
        """Get settings as a dictionary"""
        try:
            return json.loads(self.settings) if self.settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    @settings_dict.setter
    def settings_dict(self, value):
        """Set settings from a dictionary"""
        self.settings = json.dumps(value) if value else '{}'
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'type_name': self.type_name,
            'display_name': self.display_name,
            'mime_types': self.mime_types_list,
            'extensions': self.extensions_list,
            'handler_name': self.handler_name,
            'icon_class': self.icon_class,
            'is_viewable': self.is_viewable,
            'is_editable': self.is_editable,
            'max_size_mb': self.max_size_mb,
            'settings': self.settings_dict,
            'is_enabled': self.is_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def get_config_for_mime_type(cls, mime_type):
        """Get configuration for a specific MIME type"""
        configs = cls.query.filter_by(is_enabled=True).all()
        for config in configs:
            if mime_type in config.mime_types_list:
                return config
        return None
    
    @classmethod
    def get_config_for_extension(cls, extension):
        """Get configuration for a specific file extension"""
        clean_extension = extension.lower().lstrip('.')
        configs = cls.query.filter_by(is_enabled=True).all()
        for config in configs:
            if clean_extension in config.extensions_list:
                return config
        return None
    
    @classmethod
    def is_file_type_supported(cls, mime_type=None, extension=None):
        """Check if a file type is supported"""
        if mime_type:
            return cls.get_config_for_mime_type(mime_type) is not None
        elif extension:
            return cls.get_config_for_extension(extension) is not None
        return False
    
    @classmethod
    def get_max_file_size(cls, mime_type=None, extension=None):
        """Get maximum file size for a file type"""
        config = None
        if mime_type:
            config = cls.get_config_for_mime_type(mime_type)
        elif extension:
            config = cls.get_config_for_extension(extension)
        
        return config.max_size_mb * 1024 * 1024 if config else 0  # Convert MB to bytes