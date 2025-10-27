#!/usr/bin/env python3
"""
Initialize default file type configurations in the database
"""

import os
import sys
from flask import Flask
from extensions import db
from config import Config
from services.file_type_config_service import FileTypeConfigService

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app

def init_file_type_configs():
    """Initialize default file type configurations"""
    app = create_app()
    
    with app.app_context():
        try:
            print("Initializing default file type configurations...")
            FileTypeConfigService.initialize_default_configs()
            print("✅ Default file type configurations initialized successfully!")
            
            # Display summary
            configs = FileTypeConfigService.get_all_configs()
            print(f"\n📊 Summary:")
            print(f"   Total configurations: {len(configs)}")
            print(f"   Viewable types: {len([c for c in configs if c.is_viewable])}")
            print(f"   Editable types: {len([c for c in configs if c.is_editable])}")
            
            print(f"\n📋 Configured file types:")
            for config in configs:
                status = "✅" if config.is_enabled else "❌"
                capabilities = []
                if config.is_viewable:
                    capabilities.append("View")
                if config.is_editable:
                    capabilities.append("Edit")
                
                print(f"   {status} {config.display_name} ({config.type_name})")
                print(f"      Extensions: {', '.join(config.extensions_list)}")
                print(f"      Max size: {config.max_size_mb}MB")
                print(f"      Capabilities: {', '.join(capabilities) if capabilities else 'None'}")
                print()
            
        except Exception as e:
            print(f"❌ Error initializing file type configurations: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    init_file_type_configs()