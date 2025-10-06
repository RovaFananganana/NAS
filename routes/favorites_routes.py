from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db
from models import User, Favorite, AccessLog
import os
from datetime import datetime, timezone

favorites_bp = Blueprint('favorites', __name__)

def log_action(user_id, action, target):
    """Helper function to log user actions"""
    try:
        log_entry = AccessLog(
            user_id=user_id,
            action=action,
            target=target,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        print(f"Error logging action: {e}")

@favorites_bp.route('/add', methods=['POST'])
@jwt_required()
def add_favorite():
    """Add an item to user's favorites"""
    try:
        jwt_identity = get_jwt_identity()
        
        if jwt_identity is None:
            return jsonify({'error': 'Token JWT invalide - identity manquante'}), 401
            
        try:
            current_user_id = int(jwt_identity)
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Token JWT invalide - ID utilisateur non valide: {str(e)}'}), 401
            
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        item_path = data.get('item_path')
        item_type = data.get('item_type')  # 'file' or 'folder'
        item_name = data.get('item_name')
        
        if not all([item_path, item_type, item_name]):
            return jsonify({'error': 'Missing required fields: item_path, item_type, item_name'}), 400
            
        if item_type not in ['file', 'folder']:
            return jsonify({'error': 'item_type must be "file" or "folder"'}), 400
        
        # Check if favorite already exists
        existing_favorite = Favorite.query.filter_by(
            user_id=current_user_id,
            item_path=item_path
        ).first()
        
        if existing_favorite:
            return jsonify({'error': 'Item is already in favorites'}), 409
        
        # Verify the file/folder exists on the NAS
        storage_root = os.getenv('STORAGE_ROOT', '/volume1/homes')
        full_path = os.path.join(storage_root, item_path.lstrip('/'))
        
        if not os.path.exists(full_path):
            return jsonify({'error': 'Item does not exist on the NAS'}), 404
        
        # Create new favorite
        favorite = Favorite(
            user_id=current_user_id,
            item_path=item_path,
            item_type=item_type,
            item_name=item_name
        )
        
        db.session.add(favorite)
        db.session.commit()
        
        # Log the action
        log_action(current_user_id, 'ADD_FAVORITE', item_path)
        
        return jsonify({
            'message': 'Item added to favorites successfully',
            'favorite': favorite.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to add favorite: {str(e)}'}), 500

@favorites_bp.route('/remove', methods=['DELETE'])
@jwt_required()
def remove_favorite():
    """Remove an item from user's favorites"""
    try:
        jwt_identity = get_jwt_identity()
        
        if jwt_identity is None:
            return jsonify({'error': 'Token JWT invalide - identity manquante'}), 401
            
        try:
            current_user_id = int(jwt_identity)
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Token JWT invalide - ID utilisateur non valide: {str(e)}'}), 401
            
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        item_path = data.get('item_path')
        
        if not item_path:
            return jsonify({'error': 'Missing required field: item_path'}), 400
        
        # Find and remove the favorite
        favorite = Favorite.query.filter_by(
            user_id=current_user_id,
            item_path=item_path
        ).first()
        
        if not favorite:
            return jsonify({'error': 'Item not found in favorites'}), 404
        
        db.session.delete(favorite)
        db.session.commit()
        
        # Log the action
        log_action(current_user_id, 'REMOVE_FAVORITE', item_path)
        
        return jsonify({'message': 'Item removed from favorites successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to remove favorite: {str(e)}'}), 500

@favorites_bp.route('/list', methods=['GET'])
@jwt_required()
def list_favorites():
    """List all favorites for the current user"""
    try:
        jwt_identity = get_jwt_identity()
        print(f"🔍 JWT Identity type: {type(jwt_identity)}, value: {jwt_identity}")
        
        # Ensure it's an integer - JWT identity is always a string
        if jwt_identity is None:
            return jsonify({'error': 'Token JWT invalide - identity manquante'}), 401
            
        try:
            current_user_id = int(jwt_identity)
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Token JWT invalide - ID utilisateur non valide: {str(e)}'}), 401
        
        # Get all favorites for the user
        favorites = Favorite.query.filter_by(user_id=current_user_id).order_by(Favorite.created_at.desc()).all()
        
        # Verify each favorite still exists and clean up orphans
        valid_favorites = []
        storage_root = os.getenv('STORAGE_ROOT', '/volume1/homes')
        
        for favorite in favorites:
            full_path = os.path.join(storage_root, favorite.item_path.lstrip('/'))
            
            if os.path.exists(full_path):
                valid_favorites.append(favorite.to_dict())
            else:
                # Remove orphaned favorite
                db.session.delete(favorite)
        
        # Commit any orphan cleanup
        if len(valid_favorites) < len(favorites):
            db.session.commit()
        
        return jsonify({
            'favorites': valid_favorites,
            'count': len(valid_favorites)
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to list favorites: {str(e)}'}), 500

@favorites_bp.route('/cleanup', methods=['POST'])
@jwt_required()
def cleanup_orphaned_favorites():
    """Clean up orphaned favorites (items that no longer exist on NAS)"""
    try:
        jwt_identity = get_jwt_identity()
        
        if jwt_identity is None:
            return jsonify({'error': 'Token JWT invalide - identity manquante'}), 401
            
        try:
            current_user_id = int(jwt_identity)
        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Token JWT invalide - ID utilisateur non valide: {str(e)}'}), 401
        
        # Get current user to check if admin (optional - could be admin-only endpoint)
        user = User.query.get(current_user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        storage_root = os.getenv('STORAGE_ROOT', '/volume1/homes')
        
        # Get all favorites for cleanup
        if user.role == 'ADMIN':
            # Admin can clean up all orphaned favorites
            favorites = Favorite.query.all()
        else:
            # Regular users can only clean up their own favorites
            favorites = Favorite.query.filter_by(user_id=current_user_id).all()
        
        orphaned_count = 0
        
        for favorite in favorites:
            full_path = os.path.join(storage_root, favorite.item_path.lstrip('/'))
            
            if not os.path.exists(full_path):
                db.session.delete(favorite)
                orphaned_count += 1
        
        db.session.commit()
        
        return jsonify({
            'message': f'Cleaned up {orphaned_count} orphaned favorites',
            'orphaned_count': orphaned_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to cleanup favorites: {str(e)}'}), 500