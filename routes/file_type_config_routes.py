# routes/file_type_config_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.exceptions import Unauthorized
from functools import wraps
from services.file_type_config_service import FileTypeConfigService
from models.file_type_config import FileTypeConfig
from extensions import db

file_type_config_bp = Blueprint('file_type_config', __name__, url_prefix='/api/file-type-config')

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role', '').upper() != 'ADMIN':
            return jsonify({"msg": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

# Public endpoints (for file validation)
@file_type_config_bp.route('/supported-types', methods=['GET'])
def get_supported_types():
    """Get summary of supported file types (public endpoint)"""
    try:
        summary = FileTypeConfigService.get_supported_types_summary()
        return jsonify(summary), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/validate', methods=['POST'])
def validate_file():
    """Validate a file against configuration rules (public endpoint)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data required"}), 400
        
        file_size = data.get('file_size', 0)
        mime_type = data.get('mime_type')
        extension = data.get('extension')
        file_path = data.get('file_path', '')
        
        if not mime_type and not extension:
            return jsonify({"error": "Either mime_type or extension is required"}), 400
        
        result = FileTypeConfigService.validate_file(
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            extension=extension
        )
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/config-for-type', methods=['GET'])
def get_config_for_type():
    """Get configuration for a specific file type (public endpoint)"""
    try:
        mime_type = request.args.get('mime_type')
        extension = request.args.get('extension')
        
        if not mime_type and not extension:
            return jsonify({"error": "Either mime_type or extension parameter is required"}), 400
        
        config = None
        if mime_type:
            config = FileTypeConfig.get_config_for_mime_type(mime_type)
        elif extension:
            config = FileTypeConfig.get_config_for_extension(extension)
        
        if not config:
            return jsonify({"error": "File type not supported"}), 404
        
        return jsonify(config.to_dict()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Admin endpoints
@file_type_config_bp.route('/', methods=['GET'])
@admin_required
def get_all_configs():
    """Get all file type configurations"""
    try:
        include_disabled = request.args.get('include_disabled', 'true').lower() == 'true'
        
        if include_disabled:
            configs = FileTypeConfigService.get_all_configs()
        else:
            configs = FileTypeConfigService.get_enabled_configs()
        
        return jsonify([config.to_dict() for config in configs]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/', methods=['POST'])
@admin_required
def create_config():
    """Create a new file type configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data required"}), 400
        
        # Validate required fields
        required_fields = ['type_name', 'display_name', 'handler_name', 'mime_types', 'extensions']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Check if type_name already exists
        existing_config = FileTypeConfigService.get_config_by_type(data['type_name'])
        if existing_config:
            return jsonify({"error": "File type configuration already exists"}), 409
        
        config = FileTypeConfigService.create_config(data)
        return jsonify(config.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/<int:config_id>', methods=['GET'])
@admin_required
def get_config(config_id):
    """Get a specific file type configuration"""
    try:
        config = FileTypeConfigService.get_config_by_id(config_id)
        if not config:
            return jsonify({"error": "Configuration not found"}), 404
        
        return jsonify(config.to_dict()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/<int:config_id>', methods=['PUT'])
@admin_required
def update_config(config_id):
    """Update a file type configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request data required"}), 400
        
        config = FileTypeConfigService.update_config(config_id, data)
        if not config:
            return jsonify({"error": "Configuration not found"}), 404
        
        return jsonify(config.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/<int:config_id>', methods=['DELETE'])
@admin_required
def delete_config(config_id):
    """Delete a file type configuration"""
    try:
        success = FileTypeConfigService.delete_config(config_id)
        if not success:
            return jsonify({"error": "Configuration not found"}), 404
        
        return jsonify({"message": "Configuration deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/<int:config_id>/toggle', methods=['POST'])
@admin_required
def toggle_config(config_id):
    """Toggle enabled/disabled status of a configuration"""
    try:
        config = FileTypeConfigService.toggle_config(config_id)
        if not config:
            return jsonify({"error": "Configuration not found"}), 404
        
        return jsonify({
            "message": f"Configuration {'enabled' if config.is_enabled else 'disabled'} successfully",
            "config": config.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/initialize-defaults', methods=['POST'])
@admin_required
def initialize_defaults():
    """Initialize default file type configurations"""
    try:
        FileTypeConfigService.initialize_default_configs()
        return jsonify({"message": "Default configurations initialized successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@file_type_config_bp.route('/bulk-update', methods=['POST'])
@admin_required
def bulk_update_configs():
    """Bulk update multiple configurations"""
    try:
        data = request.get_json()
        if not data or 'configs' not in data:
            return jsonify({"error": "Request data with 'configs' array required"}), 400
        
        updated_configs = []
        errors = []
        
        for config_data in data['configs']:
            if 'id' not in config_data:
                errors.append("Missing 'id' in config data")
                continue
            
            try:
                config = FileTypeConfigService.update_config(config_data['id'], config_data)
                if config:
                    updated_configs.append(config.to_dict())
                else:
                    errors.append(f"Configuration with id {config_data['id']} not found")
            except Exception as e:
                errors.append(f"Error updating config {config_data['id']}: {str(e)}")
        
        return jsonify({
            "updated_configs": updated_configs,
            "errors": errors,
            "success_count": len(updated_configs),
            "error_count": len(errors)
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500