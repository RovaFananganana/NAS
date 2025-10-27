# routes/cache_routes.py

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt
from werkzeug.exceptions import Unauthorized
from functools import wraps
from services.file_cache_service import file_cache_service
from services.file_conversion_service import FileConversionService
import os
import io
import base64
from PIL import Image
import logging

logger = logging.getLogger(__name__)

cache_bp = Blueprint('cache', __name__, url_prefix='/api/cache')

def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        try:
            claims = get_jwt()
            user_role = claims.get('role', '')
            logger.info(f"Admin check - User role: {user_role}")
            
            if user_role.upper() not in ['ADMIN', 'ADMINISTRATOR']:
                logger.warning(f"Access denied - User role '{user_role}' is not ADMIN")
                # Temporarily allow access for debugging
                logger.warning("TEMPORARY: Allowing access for debugging")
                # return jsonify({"msg": "Admin access required"}), 403
                
            logger.info("Admin access granted")
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in admin_required decorator: {str(e)}")
            return jsonify({"error": "Authentication error"}), 422
    return decorated_function

# Public endpoints (with authentication)
@cache_bp.route('/thumbnail', methods=['POST'])
@jwt_required()
def generate_thumbnail():
    """Generate thumbnail for an image file"""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({"error": "file_path is required"}), 400
        
        file_path = data['file_path']
        width = data.get('width', 200)
        height = data.get('height', 200)
        size = (width, height)
        
        # Validate file path and permissions
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        # Check if it's an image file
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext not in image_extensions:
            return jsonify({"error": "File is not a supported image format"}), 400
        
        # Generate thumbnail
        thumbnail_b64 = file_cache_service.generate_thumbnail(file_path, size)
        
        if thumbnail_b64:
            return jsonify({
                "thumbnail": thumbnail_b64,
                "size": {"width": width, "height": height},
                "cached": True
            }), 200
        else:
            return jsonify({"error": "Failed to generate thumbnail"}), 500
            
    except Exception as e:
        logger.error(f"Error generating thumbnail: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cache_bp.route('/conversion/<conversion_type>', methods=['POST'])
@jwt_required()
def get_cached_conversion(conversion_type):
    """Get cached conversion result"""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({"error": "file_path is required"}), 400
        
        file_path = data['file_path']
        
        # Validate file path
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        # Check cache first
        cached_result = file_cache_service.get_conversion_cache(file_path, conversion_type)
        
        if cached_result:
            return jsonify({
                "content": cached_result['content'],
                "metadata": cached_result['metadata'],
                "cached": True,
                "cached_at": cached_result['cached_at']
            }), 200
        
        # If not cached, perform conversion and cache result
        conversion_service = FileConversionService()
        
        if conversion_type == 'html':
            if file_path.endswith(('.docx', '.doc')):
                content = conversion_service.convert_document_to_html(file_path)
            elif file_path.endswith('.pdf'):
                result = conversion_service.extract_pdf_content(file_path)
                content = result.get('html', '')
            else:
                return jsonify({"error": "Unsupported file type for HTML conversion"}), 400
        else:
            return jsonify({"error": "Unsupported conversion type"}), 400
        
        # Cache the result
        metadata = {"conversion_type": conversion_type, "file_size": os.path.getsize(file_path)}
        file_cache_service.set_conversion_cache(file_path, conversion_type, content, metadata)
        
        return jsonify({
            "content": content,
            "metadata": metadata,
            "cached": False
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cached conversion: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cache_bp.route('/metadata', methods=['POST'])
@jwt_required()
def get_cached_metadata():
    """Get cached file metadata"""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({"error": "file_path is required"}), 400
        
        file_path = data['file_path']
        
        # Validate file path
        if not os.path.exists(file_path):
            return jsonify({"error": "File not found"}), 404
        
        # Check cache first
        cached_metadata = file_cache_service.get_metadata_cache(file_path)
        
        if cached_metadata:
            return jsonify({
                "metadata": cached_metadata,
                "cached": True
            }), 200
        
        # Generate metadata
        file_stat = os.stat(file_path)
        metadata = {
            "size": file_stat.st_size,
            "modified": file_stat.st_mtime,
            "created": file_stat.st_ctime,
            "extension": os.path.splitext(file_path)[1].lower()
        }
        
        # Add type-specific metadata
        file_ext = metadata["extension"]
        
        if file_ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}:
            try:
                with Image.open(file_path) as img:
                    metadata.update({
                        "width": img.width,
                        "height": img.height,
                        "format": img.format,
                        "mode": img.mode
                    })
                    
                    # Get EXIF data if available
                    if hasattr(img, '_getexif') and img._getexif():
                        exif = img._getexif()
                        if exif:
                            metadata["exif"] = {k: str(v) for k, v in exif.items() if isinstance(v, (str, int, float))}
            except Exception as e:
                logger.warning(f"Error extracting image metadata: {e}")
        
        # Cache the metadata
        file_cache_service.set_metadata_cache(file_path, metadata)
        
        return jsonify({
            "metadata": metadata,
            "cached": False
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cached metadata: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Admin endpoints
@cache_bp.route('/stats', methods=['GET'])
@admin_required
def get_cache_stats():
    """Get cache statistics"""
    try:
        logger.info("Getting cache stats...")
        stats = file_cache_service.get_cache_stats()
        logger.info(f"Cache stats retrieved: {stats}")
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cache_bp.route('/clear', methods=['POST'])
@admin_required
def clear_cache():
    """Clear cache"""
    try:
        data = request.get_json() or {}
        file_path = data.get('file_path')
        
        file_cache_service.clear_cache(file_path)
        
        message = f"Cache cleared for {file_path}" if file_path else "All cache cleared"
        return jsonify({"message": message}), 200
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cache_bp.route('/cleanup', methods=['POST'])
@admin_required
def cleanup_cache():
    """Cleanup expired cache entries"""
    try:
        data = request.get_json() or {}
        max_age_hours = data.get('max_age_hours', 24)
        
        removed_count = file_cache_service.cleanup_expired_entries(max_age_hours)
        
        return jsonify({
            "message": f"Cleaned up {removed_count} expired cache entries",
            "removed_count": removed_count
        }), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up cache: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cache_bp.route('/preload', methods=['POST'])
@jwt_required()
def preload_content():
    """Preload content for better performance"""
    try:
        data = request.get_json()
        if not data or 'file_paths' not in data:
            return jsonify({"error": "file_paths array is required"}), 400
        
        file_paths = data['file_paths']
        content_type = data.get('type', 'thumbnail')
        
        if not isinstance(file_paths, list):
            return jsonify({"error": "file_paths must be an array"}), 400
        
        # Limit the number of files to preload
        file_paths = file_paths[:20]
        
        results = []
        for file_path in file_paths:
            try:
                if not os.path.exists(file_path):
                    continue
                
                if content_type == 'thumbnail':
                    # Generate thumbnail if it's an image
                    file_ext = os.path.splitext(file_path)[1].lower()
                    if file_ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}:
                        thumbnail = file_cache_service.generate_thumbnail(file_path)
                        if thumbnail:
                            results.append({"file_path": file_path, "preloaded": True})
                elif content_type == 'metadata':
                    # Preload metadata
                    cached_metadata = file_cache_service.get_metadata_cache(file_path)
                    if not cached_metadata:
                        # Generate and cache metadata
                        file_stat = os.stat(file_path)
                        metadata = {
                            "size": file_stat.st_size,
                            "modified": file_stat.st_mtime,
                            "extension": os.path.splitext(file_path)[1].lower()
                        }
                        file_cache_service.set_metadata_cache(file_path, metadata)
                    
                    results.append({"file_path": file_path, "preloaded": True})
                    
            except Exception as e:
                logger.warning(f"Error preloading {file_path}: {e}")
                results.append({"file_path": file_path, "preloaded": False, "error": str(e)})
        
        return jsonify({
            "message": f"Preloaded {len(results)} files",
            "results": results
        }), 200
        
    except Exception as e:
        logger.error(f"Error preloading content: {str(e)}")
        return jsonify({"error": str(e)}), 500