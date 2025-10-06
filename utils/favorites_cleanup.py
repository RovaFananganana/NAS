"""
Utility functions for favorites system maintenance
"""

import os
from extensions import db
from models import Favorite

def cleanup_orphaned_favorites(storage_root=None):
    """
    Clean up orphaned favorites (items that no longer exist on NAS)
    
    Args:
        storage_root (str): Root path of the NAS storage. If None, uses environment variable.
    
    Returns:
        int: Number of orphaned favorites cleaned up
    """
    if storage_root is None:
        storage_root = os.getenv('STORAGE_ROOT', '/volume1/homes')
    
    orphaned_count = 0
    favorites = Favorite.query.all()
    
    for favorite in favorites:
        full_path = os.path.join(storage_root, favorite.item_path.lstrip('/'))
        
        if not os.path.exists(full_path):
            db.session.delete(favorite)
            orphaned_count += 1
    
    if orphaned_count > 0:
        db.session.commit()
    
    return orphaned_count

def get_user_favorites_count(user_id):
    """
    Get the count of favorites for a specific user
    
    Args:
        user_id (int): The user ID
    
    Returns:
        int: Number of favorites for the user
    """
    return Favorite.query.filter_by(user_id=user_id).count()

def is_item_favorited(user_id, item_path):
    """
    Check if an item is already in user's favorites
    
    Args:
        user_id (int): The user ID
        item_path (str): The path of the item
    
    Returns:
        bool: True if item is favorited, False otherwise
    """
    favorite = Favorite.query.filter_by(
        user_id=user_id,
        item_path=item_path
    ).first()
    
    return favorite is not None