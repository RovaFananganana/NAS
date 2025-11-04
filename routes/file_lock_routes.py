from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import FileLock, User
from extensions import db
import logging

logger = logging.getLogger(__name__)

file_lock_bp = Blueprint("file_lock", __name__)


@file_lock_bp.route('/acquire', methods=['POST'])
@jwt_required()
def acquire_lock():
    """
    Acquire a lock on a file
    
    Request body:
    {
        "file_path": "/path/to/file",
        "session_id": "unique-session-id",
        "lock_duration_minutes": 30  # optional, defaults to 30
    }
    
    Returns:
    {
        "success": true/false,
        "message": "Lock acquired/File is locked by username",
        "lock": {
            "id": 1,
            "file_path": "/path/to/file",
            "locked_by_user_id": 1,
            "locked_by_username": "username",
            "locked_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-01T00:30:00Z",
            "session_id": "unique-session-id"
        }
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        file_path = data.get('file_path')
        session_id = data.get('session_id')
        lock_duration_minutes = data.get('lock_duration_minutes', 30)
        
        if not file_path or not session_id:
            return jsonify({'error': 'file_path and session_id are required'}), 400
        
        # Attempt to acquire lock
        success, message, lock = FileLock.acquire_lock(
            user_id=current_user_id,
            file_path=file_path,
            session_id=session_id,
            lock_duration_minutes=lock_duration_minutes
        )
        
        if success:
            user = User.query.get(lock.user_id)
            return jsonify({
                'success': True,
                'message': message,
                'lock': {
                    'id': lock.id,
                    'file_path': lock.file_path,
                    'locked_by_user_id': lock.user_id,
                    'locked_by_username': user.username if user else 'Unknown',
                    'locked_at': lock.locked_at.isoformat(),
                    'expires_at': lock.expires_at.isoformat(),
                    'session_id': lock.session_id,
                    'is_active': lock.is_active
                }
            }), 200
        else:
            # Lock failed - file is locked by another user
            user = User.query.get(lock.user_id)
            return jsonify({
                'success': False,
                'message': message,
                'lock': {
                    'id': lock.id,
                    'file_path': lock.file_path,
                    'locked_by_user_id': lock.user_id,
                    'locked_by_username': user.username if user else 'Unknown',
                    'locked_at': lock.locked_at.isoformat(),
                    'expires_at': lock.expires_at.isoformat(),
                    'session_id': lock.session_id,
                    'is_active': lock.is_active
                }
            }), 409  # Conflict
            
    except Exception as e:
        logger.error(f"Error acquiring lock: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/release', methods=['POST'])
@jwt_required()
def release_lock():
    """
    Release a lock on a file
    
    Request body:
    {
        "session_id": "unique-session-id"
    }
    OR
    {
        "file_path": "/path/to/file"
    }
    
    Returns:
    {
        "success": true/false,
        "message": "Lock released/No active lock found"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        session_id = data.get('session_id')
        file_path = data.get('file_path')
        
        if not session_id and not file_path:
            return jsonify({'error': 'session_id or file_path is required'}), 400
        
        # Release lock
        if session_id:
            success = FileLock.release_lock(session_id=session_id)
        else:
            success = FileLock.release_lock(file_path=file_path, user_id=current_user_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Lock released successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'No active lock found'
            }), 404
            
    except Exception as e:
        logger.error(f"Error releasing lock: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/status/<path:file_path>', methods=['GET'])
@jwt_required()
def check_lock_status(file_path):
    """
    Check the lock status of a file
    
    Returns:
    {
        "is_locked": true/false,
        "locked_by_user_id": 1,
        "locked_by_username": "username",
        "locked_at": "2024-01-01T00:00:00Z",
        "expires_at": "2024-01-01T00:30:00Z",
        "session_id": "unique-session-id"
    }
    """
    try:
        status = FileLock.check_lock_status(file_path)
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Error checking lock status: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/update-activity', methods=['POST'])
@jwt_required()
def update_lock_activity():
    """
    Update the last activity timestamp for a lock (keep-alive)
    
    Request body:
    {
        "session_id": "unique-session-id"
    }
    
    Returns:
    {
        "success": true/false,
        "message": "Activity updated/Lock not found"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'session_id is required'}), 400
        
        success = FileLock.update_activity(session_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Activity updated successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Lock not found or inactive'
            }), 404
            
    except Exception as e:
        logger.error(f"Error updating lock activity: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/user-locks', methods=['GET'])
@jwt_required()
def get_user_locks():
    """
    Get all locks for the current user
    
    Query parameters:
    - active_only: true/false (default: true)
    
    Returns:
    {
        "locks": [
            {
                "id": 1,
                "file_path": "/path/to/file",
                "locked_at": "2024-01-01T00:00:00Z",
                "expires_at": "2024-01-01T00:30:00Z",
                "session_id": "unique-session-id",
                "is_active": true
            }
        ]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        locks = FileLock.get_user_locks(current_user_id, active_only)
        
        locks_data = []
        for lock in locks:
            locks_data.append({
                'id': lock.id,
                'file_path': lock.file_path,
                'locked_at': lock.locked_at.isoformat(),
                'expires_at': lock.expires_at.isoformat(),
                'session_id': lock.session_id,
                'is_active': lock.is_active,
                'last_activity_at': lock.last_activity_at.isoformat()
            })
        
        return jsonify({'locks': locks_data}), 200
        
    except Exception as e:
        logger.error(f"Error getting user locks: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/release-all', methods=['POST'])
@jwt_required()
def release_all_user_locks():
    """
    Release all locks for the current user
    
    Returns:
    {
        "success": true,
        "message": "Released X locks",
        "count": X
    }
    """
    try:
        current_user_id = get_jwt_identity()
        count = FileLock.release_all_user_locks(current_user_id)
        
        return jsonify({
            'success': True,
            'message': f'Released {count} locks',
            'count': count
        }), 200
        
    except Exception as e:
        logger.error(f"Error releasing all user locks: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/cleanup-expired', methods=['POST'])
@jwt_required()
def cleanup_expired_locks():
    """
    Cleanup expired locks (admin/maintenance endpoint)
    
    Returns:
    {
        "success": true,
        "message": "Released X expired locks",
        "count": X
    }
    """
    try:
        # This could be restricted to admin users only
        count = FileLock.release_expired_locks()
        
        return jsonify({
            'success': True,
            'message': f'Released {count} expired locks',
            'count': count
        }), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up expired locks: {e}")
        return jsonify({'error': str(e)}), 500


@file_lock_bp.route('/cleanup-inactive', methods=['POST'])
@jwt_required()
def cleanup_inactive_locks():
    """
    Cleanup inactive locks (admin/maintenance endpoint)
    
    Request body:
    {
        "inactivity_minutes": 15  # optional, defaults to 15
    }
    
    Returns:
    {
        "success": true,
        "message": "Released X inactive locks",
        "count": X
    }
    """
    try:
        data = request.get_json() or {}
        inactivity_minutes = data.get('inactivity_minutes', 15)
        
        count = FileLock.release_inactive_locks(inactivity_minutes)
        
        return jsonify({
            'success': True,
            'message': f'Released {count} inactive locks',
            'count': count
        }), 200
        
    except Exception as e:
        logger.error(f"Error cleaning up inactive locks: {e}")
        return jsonify({'error': str(e)}), 500
