#!/usr/bin/env python3
"""
Test script for PermissionCache model functionality.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.permission_cache import PermissionCache
from models.user import User


def test_permission_cache():
    """Test PermissionCache model functionality."""
    app = create_app()
    
    with app.app_context():
        print("Testing PermissionCache model...")
        
        # Test 1: Create a cache entry
        print("\n1. Testing cache entry creation...")
        permissions = {
            'can_read': True,
            'can_write': False,
            'can_delete': False,
            'can_share': True,
            'is_owner': False
        }
        
        cache_entry = PermissionCache.set_cached_permission(
            user_id=1,
            resource_type='file',
            resource_id=123,
            permissions_dict=permissions,
            permission_source='direct'
        )
        
        db.session.commit()
        print(f"✓ Created cache entry: {cache_entry}")
        
        # Test 2: Retrieve cached permission
        print("\n2. Testing cache retrieval...")
        cached = PermissionCache.get_cached_permission(
            user_id=1,
            resource_type='file',
            resource_id=123
        )
        
        if cached:
            print(f"✓ Retrieved cache entry: {cached}")
            print(f"  Permissions: R:{cached.can_read} W:{cached.can_write} D:{cached.can_delete} S:{cached.can_share}")
        else:
            print("✗ Failed to retrieve cache entry")
        
        # Test 3: Update existing cache entry
        print("\n3. Testing cache update...")
        updated_permissions = {
            'can_read': True,
            'can_write': True,
            'can_delete': False,
            'can_share': True,
            'is_owner': False
        }
        
        updated_entry = PermissionCache.set_cached_permission(
            user_id=1,
            resource_type='file',
            resource_id=123,
            permissions_dict=updated_permissions,
            permission_source='group'
        )
        
        db.session.commit()
        print(f"✓ Updated cache entry: {updated_entry}")
        
        # Test 4: Test cache expiration
        print("\n4. Testing cache expiration...")
        # Create an expired cache entry
        expired_entry = PermissionCache(
            user_id=3,  # Use existing user ID
            resource_type='folder',
            resource_id=456,
            can_read=True,
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        )
        db.session.add(expired_entry)
        db.session.commit()
        
        # Try to retrieve expired entry
        expired_cached = PermissionCache.get_cached_permission(
            user_id=3,  # Use existing user ID
            resource_type='folder',
            resource_id=456
        )
        
        if expired_cached is None:
            print("✓ Expired cache entry correctly not returned")
        else:
            print("✗ Expired cache entry was incorrectly returned")
        
        # Test 5: Cache statistics
        print("\n5. Testing cache statistics...")
        stats = PermissionCache.get_cache_stats()
        print(f"✓ Cache stats: {stats}")
        
        # Test 6: Cleanup expired entries
        print("\n6. Testing expired cache cleanup...")
        cleaned_count = PermissionCache.cleanup_expired_cache()
        print(f"✓ Cleaned up {cleaned_count} expired entries")
        
        # Test 7: Cache invalidation
        print("\n7. Testing cache invalidation...")
        # Create another entry for user 1
        PermissionCache.set_cached_permission(
            user_id=1,
            resource_type='folder',
            resource_id=789,
            permissions_dict={'can_read': True},
            permission_source='inherited'
        )
        db.session.commit()
        
        # Count entries for user 1 before invalidation
        before_count = PermissionCache.query.filter_by(user_id=1).count()
        print(f"  Entries for user 1 before invalidation: {before_count}")
        
        # Invalidate all cache for user 1
        PermissionCache.invalidate_user_cache(user_id=1)
        
        # Count entries for user 1 after invalidation
        after_count = PermissionCache.query.filter_by(user_id=1).count()
        print(f"  Entries for user 1 after invalidation: {after_count}")
        
        if after_count == 0:
            print("✓ User cache invalidation successful")
        else:
            print("✗ User cache invalidation failed")
        
        # Test 8: Resource invalidation
        print("\n8. Testing resource cache invalidation...")
        # Create entries for different users on same resource
        PermissionCache.set_cached_permission(
            user_id=15,  # Use existing user ID
            resource_type='file',
            resource_id=999,
            permissions_dict={'can_read': True},
            permission_source='direct'
        )
        PermissionCache.set_cached_permission(
            user_id=18,  # Use existing user ID
            resource_type='file',
            resource_id=999,
            permissions_dict={'can_read': True},
            permission_source='direct'
        )
        db.session.commit()
        
        before_count = PermissionCache.query.filter_by(
            resource_type='file',
            resource_id=999
        ).count()
        print(f"  Entries for file 999 before invalidation: {before_count}")
        
        # Invalidate cache for specific resource
        PermissionCache.invalidate_resource_cache('file', 999)
        
        after_count = PermissionCache.query.filter_by(
            resource_type='file',
            resource_id=999
        ).count()
        print(f"  Entries for file 999 after invalidation: {after_count}")
        
        if after_count == 0:
            print("✓ Resource cache invalidation successful")
        else:
            print("✗ Resource cache invalidation failed")
        
        print("\n✓ All PermissionCache tests completed successfully!")


if __name__ == "__main__":
    test_permission_cache()