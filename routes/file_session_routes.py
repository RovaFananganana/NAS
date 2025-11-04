from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.file_session_service import file_session_service
from models import File, User, FileLock
from extensions import db
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

file_session_bp = Blueprint("file_session", __name__)


@file_session_bp.route('/open', methods=['POST'])
@jwt_required()
def open_file():
    """
    Open a file for editing - creates a cache session
    
    Request body:
    {
        "file_path": "/path/to/file.txt",
        "mode": "edit"  # or "view"
    }
    
    Returns:
    {
        "success": true,
        "session_id": "uuid",
        "file_name": "file.txt",
        "file_size": 1024,
        "lock_acquired": true/false,
        "lock_info": {...}
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or not data.get('file_path'):
            return jsonify({'error': 'file_path is required'}), 400
        
        file_path = data['file_path']
        mode = data.get('mode', 'view')
        
        # Get file from database
        file_record = File.query.filter_by(path=file_path).first()
        if not file_record:
            return jsonify({'error': 'File not found in database'}), 404
        
        # Check if user has permission to access the file
        # TODO: Add permission check here
        
        # Get NAS path
        nas_root = os.getenv('STORAGE_ROOT', '//10.61.17.33/NAS')
        # Convert to Windows UNC path format
        nas_root_win = nas_root.replace('//', '\\\\').replace('/', '\\')
        file_path_win = file_path.lstrip('/').replace('/', '\\')
        nas_path = nas_root_win + '\\' + file_path_win
        
        # Note: We trust the database - if the file is in DB, it should exist on NAS
        # Checking os.path.exists() on Windows UNC paths can be unreliable
        
        # Try to acquire lock if in edit mode
        lock_acquired = False
        lock_info = None
        
        if mode == 'edit':
            import uuid
            session_id_temp = str(uuid.uuid4())
            
            success, message, lock = FileLock.acquire_lock(
                user_id=current_user_id,
                file_path=file_path,
                session_id=session_id_temp,
                lock_duration_minutes=60
            )
            
            lock_acquired = success
            
            if lock:
                user = User.query.get(lock.user_id)
                lock_info = {
                    'is_locked': not success,
                    'locked_by_user_id': lock.user_id,
                    'locked_by_username': user.username if user else 'Unknown',
                    'locked_at': lock.locked_at.isoformat(),
                    'expires_at': lock.expires_at.isoformat()
                }
            
            # If file is locked by another user, return error
            if not lock_acquired:
                return jsonify({
                    'success': False,
                    'error': message,
                    'lock_info': lock_info
                }), 409
        
        # Create file session
        session_result = file_session_service.create_session(
            file_path=file_path,
            user_id=current_user_id,
            nas_path=nas_path
        )
        
        if not session_result['success']:
            # Release lock if we acquired it
            if lock_acquired and session_id_temp:
                FileLock.release_lock(session_id=session_id_temp)
            
            return jsonify({
                'success': False,
                'error': session_result.get('error', 'Failed to create session')
            }), 500
        
        # Update lock with actual session ID if we acquired it
        if lock_acquired:
            FileLock.release_lock(session_id=session_id_temp)
            FileLock.acquire_lock(
                user_id=current_user_id,
                file_path=file_path,
                session_id=session_result['session_id'],
                lock_duration_minutes=60
            )
        
        return jsonify({
            'success': True,
            'session_id': session_result['session_id'],
            'file_name': session_result['file_name'],
            'file_size': session_result['file_size'],
            'created_at': session_result['created_at'],
            'mode': mode,
            'lock_acquired': lock_acquired,
            'lock_info': lock_info
        }), 200
        
    except Exception as e:
        logger.error(f"Error opening file: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/session/<session_id>/content', methods=['GET'])
@jwt_required()
def get_file_content(session_id):
    """
    Get file content from cache session
    
    Returns:
        File content as binary data
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get session
        session = file_session_service.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Verify session belongs to current user
        if session['user_id'] != current_user_id:
            return jsonify({'error': 'Unauthorized access to session'}), 403
        
        # Read file content
        content = file_session_service.read_file_content(session_id)
        if content is None:
            return jsonify({'error': 'Failed to read file content'}), 500
        
        # Return file content
        cached_file_path = Path(session['cached_file_path'])
        return send_file(
            cached_file_path,
            mimetype='application/octet-stream',
            as_attachment=False,
            download_name=session['file_name']
        )
        
    except Exception as e:
        logger.error(f"Error getting file content: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/session/<session_id>/content', methods=['PUT'])
@jwt_required()
def update_file_content(session_id):
    """
    Update file content in cache session
    
    Request body: Binary file content
    
    Returns:
    {
        "success": true,
        "message": "Content updated",
        "last_modified": "2024-01-01T00:00:00Z"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get session
        session = file_session_service.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Verify session belongs to current user
        if session['user_id'] != current_user_id:
            return jsonify({'error': 'Unauthorized access to session'}), 403
        
        # Get content from request
        content = request.get_data()
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Write content to cache
        success = file_session_service.write_file_content(session_id, content)
        if not success:
            return jsonify({'error': 'Failed to update file content'}), 500
        
        # Update lock activity
        FileLock.update_activity(session_id)
        
        # Get updated session
        updated_session = file_session_service.get_session(session_id)
        
        return jsonify({
            'success': True,
            'message': 'Content updated',
            'last_modified': updated_session['last_modified'],
            'sync_pending': updated_session['sync_pending']
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating file content: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/session/<session_id>/sync', methods=['POST'])
@jwt_required()
def sync_to_nas(session_id):
    """
    Manually sync file from cache to NAS
    
    Returns:
    {
        "success": true,
        "message": "File synced to NAS",
        "synced_at": "2024-01-01T00:00:00Z"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get session
        session = file_session_service.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Verify session belongs to current user
        if session['user_id'] != current_user_id:
            return jsonify({'error': 'Unauthorized access to session'}), 403
        
        # Sync to NAS
        result = file_session_service.sync_to_nas(session_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
        
    except Exception as e:
        logger.error(f"Error syncing to NAS: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/session/<session_id>/close', methods=['POST'])
@jwt_required()
def close_session(session_id):
    """
    Close file editing session
    
    Request body (optional):
    {
        "sync_before_close": true  # default: true
    }
    
    Returns:
    {
        "success": true,
        "message": "Session closed",
        "sync_result": {...}
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get session
        session = file_session_service.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Verify session belongs to current user
        if session['user_id'] != current_user_id:
            return jsonify({'error': 'Unauthorized access to session'}), 403
        
        # Get options
        data = request.get_json() or {}
        sync_before_close = data.get('sync_before_close', True)
        
        # Close session
        result = file_session_service.close_session(session_id, sync_before_close)
        
        # Release file lock
        FileLock.release_lock(session_id=session_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 500
        
    except Exception as e:
        logger.error(f"Error closing session: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/session/<session_id>/info', methods=['GET'])
@jwt_required()
def get_session_info(session_id):
    """
    Get session information
    
    Returns:
    {
        "session_id": "uuid",
        "file_name": "file.txt",
        "file_path": "/path/to/file.txt",
        "is_modified": true,
        "sync_pending": true,
        "last_modified": "2024-01-01T00:00:00Z",
        "last_synced": "2024-01-01T00:00:00Z"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get session
        session = file_session_service.get_session(session_id)
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        
        # Verify session belongs to current user
        if session['user_id'] != current_user_id:
            return jsonify({'error': 'Unauthorized access to session'}), 403
        
        # Return session info
        return jsonify({
            'session_id': session['session_id'],
            'file_name': session['file_name'],
            'file_path': session['original_path'],
            'file_size': session['file_size'],
            'is_modified': session['is_modified'],
            'sync_pending': session['sync_pending'],
            'is_active': session['is_active'],
            'created_at': session['created_at'],
            'last_accessed': session['last_accessed'],
            'last_modified': session['last_modified'],
            'last_synced': session['last_synced']
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/sessions', methods=['GET'])
@jwt_required()
def get_user_sessions():
    """
    Get all sessions for current user
    
    Query parameters:
    - active_only: true/false (default: true)
    
    Returns:
    {
        "sessions": [...]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        sessions = file_session_service.get_user_sessions(current_user_id, active_only)
        
        return jsonify({
            'sessions': sessions
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting user sessions: {e}")
        return jsonify({'error': str(e)}), 500


@file_session_bp.route('/cleanup', methods=['POST'])
@jwt_required()
def cleanup_sessions():
    """
    Cleanup inactive sessions (admin endpoint)
    
    Request body:
    {
        "inactivity_minutes": 60  # optional, default: 60
    }
    
    Returns:
    {
        "success": true,
        "cleaned_count": 5
    }
    """
    try:
        # TODO: Add admin check
        
        data = request.get_json() or {}
        inactivity_minutes = data.get('inactivity_minutes', 60)
        
        cleaned_count = file_session_service.cleanup_inactive_sessions(inactivity_minutes)
        
        return jsonify({
            'success': True,
            'cleaned_count': cleaned_count
        }), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up sessions: {e}")
        return jsonify({'error': str(e)}), 500
