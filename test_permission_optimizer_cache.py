#!/usr/bin/env python3
"""
Test script for PermissionOptimizer caching functionality.
"""

import sys
import os
from datetime import datetime, timedelta

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from services.permission_optimizer import PermissionOptimizer, PermissionSet
from models.permission_cache import PermissionCache
from models.user import User
from models.file import File
from models.folder import Folder


def test_permission_optimizer_caching():
    """Test PermissionOptimizer caching functionality."""
    app = create_app()
    
    with app.app_context():
        print("Testing PermissionOptimizer caching functionality...")
        
        # Initialize optimizer with caching enabled
        optimizer = PermissionOptimizer(enable_cache=True, cache_expiration_hours=1)
        
        # Test 1: Cache miss and cache population
        print("\n1. Testing cache miss and population...")
        
        # Clear any existing cache
        PermissionCache.query.delete()
        db.session.commit()
        
        # Get some file IDs from the database
        files = File.query.limit(3).all()
        if not files:
            print("No files found in database. Creating test files...")
            # You might need to create test files here
            return
        
        file_ids = [f.id for f in files]
        user_id = 1  # Use existing user
        
        print(f"Testing with file IDs: {file_ids} for user {user_id}")
        
        # First call should miss cache and populate it
        start_time = datetime.now()
        permissions1 = optimizer.get_bulk_file_permissions(user_id, file_ids)
        first_call_time = (datetime.now() - start_time).total_seconds()
        
        print(f"✓ First call completed in {first_call_time:.3f}s (cache miss)")
        print(f"  Permissions loaded: {len(permissions1)}")
        
        # Check that cache was populated
        cache_count = PermissionCache.query.filter_by(
            user_id=user_id,
            resource_type='file'
        ).count()
        print(f"  Cache entries created: {cache_count}")
        
        # Test 2: Cache hit
        print("\n2. Testing cache hit...")
        
        start_time = datetime.now()
        permissions2 = optimizer.get_bulk_file_permissions(user_id, file_ids)
        second_call_time = (datetime.now() - start_time).total_seconds()
        
        print(f"✓ Second call completed in {second_call_time:.3f}s (cache hit)")
        
        # Verify results are the same
        if permissions1.keys() == permissions2.keys():
            print("✓ Cache hit returned same results as cache miss")
        else:
            print("✗ Cache hit returned different results")
        
        # Performance improvement check
        if second_call_time < first_call_time:
            improvement = ((first_call_time - second_call_time) / first_call_time) * 100
            print(f"✓ Performance improvement: {improvement:.1f}%")
        else:
            print("⚠ No performance improvement detected (might be due to small dataset)")
        
        # Test 3: Partial cache hit
        print("\n3. Testing partial cache hit...")
        
        # Add one more file ID that's not cached
        additional_files = File.query.filter(~File.id.in_(file_ids)).limit(1).all()
        if additional_files:
            mixed_file_ids = file_ids + [additional_files[0].id]
            
            start_time = datetime.now()
            permissions3 = optimizer.get_bulk_file_permissions(user_id, mixed_file_ids)
            mixed_call_time = (datetime.now() - start_time).total_seconds()
            
            print(f"✓ Mixed call completed in {mixed_call_time:.3f}s (partial cache hit)")
            print(f"  Total permissions: {len(permissions3)}")
        
        # Test 4: Folder permissions caching
        print("\n4. Testing folder permissions caching...")
        
        folders = Folder.query.limit(2).all()
        if folders:
            folder_ids = [f.id for f in folders]
            
            # First call (cache miss)
            start_time = datetime.now()
            folder_perms1 = optimizer.get_bulk_folder_permissions(user_id, folder_ids)
            folder_first_time = (datetime.now() - start_time).total_seconds()
            
            # Second call (cache hit)
            start_time = datetime.now()
            folder_perms2 = optimizer.get_bulk_folder_permissions(user_id, folder_ids)
            folder_second_time = (datetime.now() - start_time).total_seconds()
            
            print(f"✓ Folder cache miss: {folder_first_time:.3f}s")
            print(f"✓ Folder cache hit: {folder_second_time:.3f}s")
            
            if folder_perms1.keys() == folder_perms2.keys():
                print("✓ Folder cache results consistent")
        
        # Test 5: Cache invalidation
        print("\n5. Testing cache invalidation...")
        
        # Count cache entries before invalidation
        before_count = PermissionCache.query.filter_by(user_id=user_id).count()
        print(f"  Cache entries before invalidation: {before_count}")
        
        # Invalidate user cache
        optimizer.invalidate_user_permissions(user_id)
        
        # Count cache entries after invalidation
        after_count = PermissionCache.query.filter_by(user_id=user_id).count()
        print(f"  Cache entries after invalidation: {after_count}")
        
        if after_count == 0:
            print("✓ User cache invalidation successful")
        else:
            print("✗ User cache invalidation failed")
        
        # Test 6: Resource-specific invalidation
        print("\n6. Testing resource-specific cache invalidation...")
        
        # Repopulate cache
        optimizer.get_bulk_file_permissions(user_id, file_ids[:1])
        
        before_count = PermissionCache.query.filter_by(
            user_id=user_id,
            resource_type='file',
            resource_id=file_ids[0]
        ).count()
        
        # Invalidate specific file
        optimizer.invalidate_resource_permissions('file', file_ids[0])
        
        after_count = PermissionCache.query.filter_by(
            user_id=user_id,
            resource_type='file',
            resource_id=file_ids[0]
        ).count()
        
        print(f"  File cache entries before: {before_count}, after: {after_count}")
        
        if before_count > 0 and after_count == 0:
            print("✓ Resource-specific cache invalidation successful")
        
        # Test 7: Cache warming
        print("\n7. Testing cache warming...")
        
        # Clear cache first
        PermissionCache.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        # Warm cache
        warm_stats = optimizer.warm_cache_for_user(user_id, limit=5)
        print(f"✓ Cache warming completed: {warm_stats}")
        
        # Verify cache was warmed
        warmed_count = PermissionCache.query.filter_by(user_id=user_id).count()
        print(f"  Cache entries after warming: {warmed_count}")
        
        # Test 8: Cache statistics
        print("\n8. Testing cache statistics...")
        
        stats = optimizer.get_cache_statistics()
        print(f"✓ Cache statistics: {stats}")
        
        # Test 9: Permission change hooks
        print("\n9. Testing permission change hooks...")
        
        if files:
            # Populate cache for a file
            optimizer.get_bulk_file_permissions(user_id, [files[0].id])
            
            before_count = PermissionCache.query.filter_by(
                resource_type='file',
                resource_id=files[0].id
            ).count()
            
            # Simulate permission change
            optimizer.on_file_permission_changed(files[0].id)
            
            after_count = PermissionCache.query.filter_by(
                resource_type='file',
                resource_id=files[0].id
            ).count()
            
            print(f"  File permission change: before={before_count}, after={after_count}")
            
            if before_count > 0 and after_count == 0:
                print("✓ File permission change hook successful")
        
        # Test 10: Disabled cache
        print("\n10. Testing disabled cache...")
        
        optimizer_no_cache = PermissionOptimizer(enable_cache=False)
        
        # This should not use cache
        permissions_no_cache = optimizer_no_cache.get_bulk_file_permissions(user_id, file_ids[:1])
        
        # Check that no new cache entries were created
        cache_count_before = PermissionCache.query.count()
        optimizer_no_cache.get_bulk_file_permissions(user_id, file_ids[:1])
        cache_count_after = PermissionCache.query.count()
        
        if cache_count_before == cache_count_after:
            print("✓ Disabled cache correctly bypassed caching")
        else:
            print("✗ Disabled cache still created cache entries")
        
        print("\n✓ All PermissionOptimizer caching tests completed!")


if __name__ == "__main__":
    test_permission_optimizer_caching()