from flask import Blueprint, jsonify, request, send_file
from utils.security import require_permission
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import File, User
from services.file_conversion_service import FileConversionService
from services.file_validation_service import FileValidationService
import os
import mimetypes
from pathlib import Path
import logging
import urllib.parse

logger = logging.getLogger(__name__)

file_bp = Blueprint("file", __name__)

@file_bp.route("/", methods=["GET"])
@jwt_required()
@require_permission(resource="file", action="READ")
def list_files():
    # Ici tu récupères les fichiers de l'utilisateur
    return jsonify({"msg": "Accès aux fichiers autorisé"})


@file_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    # ici tu peux utiliser request.files['file'] pour gérer l’upload
    return jsonify({"msg": "Upload placeholder"})

@file_bp.route('/<path:file_path>/content', methods=['GET'])
@jwt_required(optional=True)
def get_file_content(file_path):
    """
    Get file content for viewing in the file viewer
    Returns raw content or converted content based on file type
    """
    try:
        # Handle authentication - either from header or query parameter
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, decode_token
        
        current_user = None
        
        # Try header authentication first
        try:
            verify_jwt_in_request()
            current_user = get_jwt_identity()
        except:
            # Try token from query parameter
            token = request.args.get('token')
            if token:
                try:
                    decoded_token = decode_token(token)
                    current_user = decoded_token['sub']
                    
                    # Verify this is a temp token
                    if decoded_token.get('temp_access'):
                        # Valid temp token
                        pass
                    else:
                        return jsonify({"error": "Invalid temporary token"}), 401
                except Exception as e:
                    return jsonify({"error": "Invalid token"}), 401
            else:
                return jsonify({"error": "Authentication required"}), 401
        
        # Check permissions manually since we're using optional JWT
        from utils.security import check_permission
        if not check_permission(current_user, "file", "READ"):
            return jsonify({"error": "Insufficient permissions"}), 403
        
        # Validate file path and existence
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        # Get NAS storage root from environment
        storage_root = os.getenv('STORAGE_ROOT', '//10.61.17.33/NAS')
        
        # For SMB storage, return SMB path information instead of trying to access file directly
        if storage_root.startswith('//'):
            # Get NAS configuration
            nas_server = os.getenv('NAS_SERVER', '10.61.17.33')
            nas_share = os.getenv('NAS_SHARE', 'NAS')
            
            # Clean file path
            clean_path = file_path.lstrip('/')
            smb_path = f"smb://{nas_server}/{nas_share}/{clean_path}"
            
            # Get file extension for type detection
            file_ext = Path(file_path).suffix.lower()
            
            return jsonify({
                'type': 'smb_file',
                'smb_path': smb_path,
                'file_info': {
                    'name': Path(file_path).name,
                    'extension': file_ext,
                    'path': file_path
                },
                'actions': {
                    'download_url': f'/files/download?path={urllib.parse.quote(file_path)}',
                    'smb_url': smb_path
                },
                'message': 'File available via SMB network share'
            })
        else:
            # Local path
            full_path = os.path.join(storage_root, file_path.lstrip('/'))
        
        # Initialize validation service
        validation_service = FileValidationService()
        
        # Get user permissions (this should come from your auth system)
        current_user = get_jwt_identity()
        user_permissions = ['file:READ']  # This should be fetched from user's actual permissions
        
        # Validate file
        validation_result = validation_service.validate_file(full_path, user_permissions)
        
        if not validation_result['valid']:
            return jsonify({
                "error": "File validation failed",
                "details": validation_result['errors']
            }), 400
        
        # Log warnings if any
        if validation_result['warnings']:
            for warning in validation_result['warnings']:
                logger.warning(f"File validation warning for {file_path}: {warning}")
        
        # Get file info
        file_size = os.path.getsize(full_path)
        mime_type, _ = mimetypes.guess_type(full_path)
        file_ext = Path(full_path).suffix.lower()
        
        # Check if conversion is requested
        convert_format = request.args.get('convert')
        
        if convert_format or file_ext in ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.pdf']:
            # Use conversion service for supported document types
            conversion_service = FileConversionService()
            
            if conversion_service.can_convert(full_path):
                try:
                    if file_ext == '.pdf':
                        result = conversion_service.extract_pdf_content(full_path)
                    elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                        result = conversion_service.get_image_metadata(full_path)
                        # For images, also return the file for display
                        result['file_url'] = f'/api/files/{file_path}/raw'
                    else:
                        result = conversion_service.convert_document_to_html(full_path)
                    
                    result['file_info'] = {
                        'name': Path(full_path).name,
                        'size': file_size,
                        'mime_type': mime_type,
                        'extension': file_ext
                    }
                    
                    return jsonify(result)
                    
                except Exception as e:
                    logger.error(f"Conversion failed for {file_path}: {str(e)}")
                    return jsonify({"error": f"Conversion failed: {str(e)}"}), 500
        
        # For text files and other simple formats, return raw content
        if mime_type and mime_type.startswith('text/') or file_ext in ['.txt', '.md', '.json', '.xml', '.csv', '.js', '.py', '.html', '.css']:
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return jsonify({
                    'type': 'text',
                    'content': content,
                    'file_info': {
                        'name': Path(full_path).name,
                        'size': file_size,
                        'mime_type': mime_type,
                        'extension': file_ext
                    }
                })
            except UnicodeDecodeError:
                # Try with different encoding
                try:
                    with open(full_path, 'r', encoding='latin-1') as f:
                        content = f.read()
                    
                    return jsonify({
                        'type': 'text',
                        'content': content,
                        'encoding': 'latin-1',
                        'file_info': {
                            'name': Path(full_path).name,
                            'size': file_size,
                            'mime_type': mime_type,
                            'extension': file_ext
                        }
                    })
                except Exception as e:
                    return jsonify({"error": f"Could not read file: {str(e)}"}), 500
        
        # For binary files, return file info and download URL
        return jsonify({
            'type': 'binary',
            'file_info': {
                'name': Path(full_path).name,
                'size': file_size,
                'mime_type': mime_type,
                'extension': file_ext
            },
            'download_url': f'/files/download?path={urllib.parse.quote(file_path)}'
        })
        
    except Exception as e:
        logger.error(f"Error getting file content for {file_path}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route('/<path:file_path>/raw', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def get_raw_file(file_path):
    """
    Get raw file for download or direct display (images, videos, etc.)
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        full_path = os.path.join('uploads', file_path)
        
        if not os.path.exists(full_path):
            return jsonify({"error": "File not found"}), 404
        
        if not os.path.isfile(full_path):
            return jsonify({"error": "Path is not a file"}), 400
        
        return send_file(full_path)
        
    except Exception as e:
        logger.error(f"Error serving raw file {file_path}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route('/<path:file_path>/content', methods=['PUT'])
@jwt_required()
@require_permission(resource="file", action="WRITE")
def update_file_content(file_path):
    """
    Update file content for supported editable file types
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        full_path = os.path.join('uploads', file_path)
        
        # Initialize validation service
        validation_service = FileValidationService()
        
        # Get user permissions
        current_user = get_jwt_identity()
        user_permissions = ['file:READ', 'file:WRITE']  # This should be fetched from user's actual permissions
        
        # Validate file
        validation_result = validation_service.validate_file(full_path, user_permissions)
        
        if not validation_result['valid']:
            return jsonify({
                "error": "File validation failed",
                "details": validation_result['errors']
            }), 400
        
        # Check if file is editable
        if not validation_result['file_info']['type_config']['editable']:
            return jsonify({"error": "File type is not editable"}), 400
        
        # Get request data
        data = request.get_json()
        if not data or 'content' not in data:
            return jsonify({"error": "Content is required"}), 400
        
        content = data['content']
        encoding = data.get('encoding', 'utf-8')
        
        # Get file info from validation result
        file_ext = validation_result['file_info']['extension']
        mime_type = validation_result['file_info']['mime_type']
        
        # Sanitize content if it's HTML or potentially contains HTML
        if file_ext in ['.html', '.htm'] or (isinstance(content, str) and '<' in content and '>' in content):
            content = validation_service.sanitize_html_content(content, strict=True)
            logger.info(f"Sanitized HTML content for file {file_path}")
        
        # Additional content validation for specific file types
        if file_ext == '.json':
            try:
                import json
                json.loads(content)  # Validate JSON syntax
            except json.JSONDecodeError as e:
                return jsonify({"error": f"Invalid JSON content: {str(e)}"}), 400
        
        elif file_ext in ['.xml']:
            try:
                import xml.etree.ElementTree as ET
                ET.fromstring(content)  # Validate XML syntax
            except ET.ParseError as e:
                return jsonify({"error": f"Invalid XML content: {str(e)}"}), 400
        
        # Create backup of original file
        backup_path = full_path + '.backup'
        try:
            import shutil
            shutil.copy2(full_path, backup_path)
        except Exception as e:
            logger.warning(f"Could not create backup for {file_path}: {str(e)}")
        
        # Write new content
        try:
            with open(full_path, 'w', encoding=encoding) as f:
                f.write(content)
            
            # Remove backup if write was successful
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            return jsonify({
                "message": "File updated successfully",
                "file_info": {
                    'name': Path(full_path).name,
                    'size': os.path.getsize(full_path),
                    'mime_type': mime_type,
                    'extension': file_ext
                }
            })
            
        except Exception as e:
            # Restore backup if write failed
            if os.path.exists(backup_path):
                import shutil
                shutil.move(backup_path, full_path)
            
            logger.error(f"Error writing file {file_path}: {str(e)}")
            return jsonify({"error": f"Could not write file: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Error updating file content for {file_path}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route('/<path:file_path>/convert/<format>', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def convert_file_content(file_path, format):
    """
    Convert file to specified format
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        full_path = os.path.join('uploads', file_path)
        
        # Initialize validation service
        validation_service = FileValidationService()
        
        # Get user permissions
        current_user = get_jwt_identity()
        user_permissions = ['file:READ']  # This should be fetched from user's actual permissions
        
        # Validate file
        validation_result = validation_service.validate_file(full_path, user_permissions)
        
        if not validation_result['valid']:
            return jsonify({
                "error": "File validation failed",
                "details": validation_result['errors']
            }), 400
        
        # Initialize conversion service
        conversion_service = FileConversionService()
        
        if not conversion_service.can_convert(full_path):
            return jsonify({"error": "File type not supported for conversion"}), 400
        
        # Perform conversion based on requested format
        try:
            if format.lower() == 'html':
                result = conversion_service.convert_document_to_html(full_path)
                # Sanitize HTML output
                if 'html' in result:
                    if isinstance(result['html'], str):
                        result['html'] = validation_service.sanitize_html_content(result['html'])
                    elif isinstance(result['html'], dict):
                        # For Excel sheets
                        for sheet_name, sheet_html in result['html'].items():
                            result['html'][sheet_name] = validation_service.sanitize_html_content(sheet_html)
                    elif isinstance(result['html'], list):
                        # For PowerPoint slides
                        for slide in result['html']:
                            if 'html' in slide:
                                slide['html'] = validation_service.sanitize_html_content(slide['html'])
            elif format.lower() == 'text' and Path(full_path).suffix.lower() == '.pdf':
                result = conversion_service.extract_pdf_content(full_path)
            elif format.lower() == 'metadata':
                file_ext = Path(full_path).suffix.lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                    result = conversion_service.get_image_metadata(full_path)
                else:
                    return jsonify({"error": "Metadata extraction not supported for this file type"}), 400
            else:
                return jsonify({"error": f"Conversion format '{format}' not supported"}), 400
            
            result['file_info'] = {
                'name': Path(full_path).name,
                'size': os.path.getsize(full_path),
                'mime_type': mimetypes.guess_type(full_path)[0],
                'extension': Path(full_path).suffix.lower()
            }
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Conversion failed for {file_path} to {format}: {str(e)}")
            return jsonify({"error": f"Conversion failed: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Error converting file {file_path} to {format}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route('/supported-types', methods=['GET'])
@jwt_required()
def get_supported_file_types():
    """
    Get list of supported file types and their configurations
    """
    try:
        validation_service = FileValidationService()
        supported_types = validation_service.get_supported_file_types()
        
        return jsonify({
            "supported_types": supported_types,
            "message": "File type configurations retrieved successfully"
        })
        
    except Exception as e:
        logger.error(f"Error getting supported file types: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@file_bp.route('/<path:file_path>/validate', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def validate_file_endpoint(file_path):
    """
    Validate a file without opening it
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        full_path = os.path.join('uploads', file_path)
        
        # Initialize validation service
        validation_service = FileValidationService()
        
        # Get user permissions
        current_user = get_jwt_identity()
        user_permissions = ['file:READ']  # This should be fetched from user's actual permissions
        
        # Validate file
        validation_result = validation_service.validate_file(full_path, user_permissions)
        
        return jsonify(validation_result)
        
    except Exception as e:
        logger.error(f"Error validating file {file_path}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@file_bp.route('/<path:file_path>/smb-path', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def get_file_smb_path(file_path):
    """
    Get SMB path for opening file in local application
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        # Get NAS configuration from environment
        nas_server = os.getenv('NAS_SERVER', '10.61.17.33')
        nas_share = os.getenv('NAS_SHARE', 'NAS')
        
        # Clean file path (remove leading slash if present)
        clean_path = file_path.lstrip('/')
        
        # Construct SMB path
        smb_path = f"smb://{nas_server}/{nas_share}/{clean_path}"
        
        return jsonify({
            "smb_path": smb_path,
            "nas_server": nas_server,
            "nas_share": nas_share,
            "file_path": clean_path,
            "full_path": file_path
        })
        
    except Exception as e:
        logger.error(f"Error getting SMB path for {file_path}: {str(e)}")
        return jsonify({"error": f"Failed to get SMB path: {str(e)}"}), 500

@file_bp.route('/temp-url', methods=['GET', 'POST'])
@jwt_required()
@require_permission(resource="file", action="READ")
def get_temp_file_url():
    """
    Generate a temporary URL for file access that can be used in window.open
    """
    try:
        # Get file path from query parameter or POST body
        if request.method == 'POST':
            data = request.get_json()
            file_path = data.get('path') if data else None
        else:
            file_path = request.args.get('path')
        logger.info(f"Temp URL request for file: {file_path}")
        
        if not file_path:
            logger.error("No file path provided")
            return jsonify({"error": "File path is required"}), 400
            
        if '..' in file_path:
            logger.error(f"Invalid file path contains '..': {file_path}")
            return jsonify({"error": "Invalid file path"}), 400
        
        # Generate a temporary token (valid for 5 minutes)
        from flask_jwt_extended import create_access_token, get_jwt_identity
        from datetime import timedelta
        
        current_user = get_jwt_identity()
        logger.info(f"Creating temp token for user: {current_user}")
        
        try:
            temp_token = create_access_token(
                identity=current_user,
                expires_delta=timedelta(minutes=5),
                additional_claims={"temp_access": True}
            )
            logger.info("Temp token created successfully")
        except Exception as token_error:
            logger.error(f"Error creating temp token: {str(token_error)}")
            return jsonify({"error": "Failed to create temporary token"}), 500
        
        # Return the temporary URL with encoded path
        import urllib.parse
        encoded_path = urllib.parse.quote(file_path, safe='')
        temp_url = f"/files/{encoded_path}/content?token={temp_token}"
        
        return jsonify({
            "temp_url": temp_url,
            "expires_in": 300,  # 5 minutes
            "file_path": file_path
        })
        
    except Exception as e:
        logger.error(f"Error generating temp URL for {file_path}: {str(e)}")
        return jsonify({"error": f"Failed to generate temp URL: {str(e)}"}), 500

@file_bp.route('/download', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def download_file():
    """
    Download file directly
    """
    try:
        # Get file path from query parameter
        file_path = request.args.get('path')
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        # Get NAS storage root from environment
        storage_root = os.getenv('STORAGE_ROOT', '//10.61.17.33/NAS')
        
        # Construct full path
        if storage_root.startswith('//'):
            # SMB path
            full_path = os.path.join(storage_root, file_path.lstrip('/'))
        else:
            # Local path
            full_path = os.path.join(storage_root, file_path.lstrip('/'))
        
        # For SMB paths, we need to handle differently
        if storage_root.startswith('//'):
            # For now, return the SMB path for client-side handling
            return jsonify({
                "download_url": f"/files/download?path={urllib.parse.quote(file_path)}",
                "smb_path": f"smb://10.61.17.33/NAS/{file_path.lstrip('/')}",
                "message": "Use SMB path to access file directly"
            })
        
        # For local files, use send_file
        if os.path.exists(full_path):
            return send_file(full_path, as_attachment=True)
        else:
            return jsonify({"error": "File not found"}), 404
            
    except Exception as e:
        logger.error(f"Error downloading file {file_path}: {str(e)}")
        return jsonify({"error": f"Failed to download file: {str(e)}"}), 500

@file_bp.route('/<path:file_path>', methods=['GET'])
@jwt_required()
@require_permission(resource="file", action="READ")
def serve_file_direct(file_path):
    """
    Serve file directly for viewing in browser
    """
    try:
        # Validate file path
        if not file_path or '..' in file_path:
            return jsonify({"error": "Invalid file path"}), 400
        
        # Get NAS storage root from environment
        storage_root = os.getenv('STORAGE_ROOT', '//10.61.17.33/NAS')
        
        # Construct full path
        if storage_root.startswith('//'):
            # SMB path - redirect to SMB
            smb_path = f"smb://10.61.17.33/NAS/{file_path.lstrip('/')}"
            return jsonify({
                "smb_path": smb_path,
                "message": "File available via SMB",
                "redirect": smb_path
            })
        else:
            # Local path
            full_path = os.path.join(storage_root, file_path.lstrip('/'))
            
            if os.path.exists(full_path):
                # Detect MIME type
                mime_type = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'
                return send_file(full_path, mimetype=mime_type)
            else:
                return jsonify({"error": "File not found"}), 404
                
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {str(e)}")
        return jsonify({"error": f"Failed to serve file: {str(e)}"}), 500