#!/usr/bin/env python3
"""
Simple test script for FileCacheService
Tests basic functionality without requiring full application context
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.file_session_cache_service import FileCacheService

def test_file_cache_service():
    """Test FileCacheService basic functionality"""
    
    print("=" * 60)
    print("Testing FileCacheService")
    print("=" * 60)
    
    # Create temporary directories for testing
    test_cache_dir = tempfile.mkdtemp(prefix='test_cache_')
    test_nas_dir = tempfile.mkdtemp(prefix='test_nas_')
    
    try:
        # Create a test file in "NAS"
        test_file_path = Path(test_nas_dir) / 'test_document.txt'
        test_content = b'This is a test document for cache service testing.'
        with open(test_file_path, 'wb') as f:
            f.write(test_content)
        
        print(f"\n✓ Created test file: {test_file_path}")
        
        # Initialize FileCacheService
        cache_service = FileCacheService(cache_base_dir=test_cache_dir, max_inactivity_minutes=5)
        print(f"✓ Initialized FileCacheService with cache dir: {test_cache_dir}")
        
        # Test 1: Create cache session
        print("\n--- Test 1: Create Cache Session ---")
        user_id = 1
        file_path = 'documents/test_document.txt'
        session_id = cache_service.create_cache_session(user_id, file_path, str(test_file_path))
        print(f"✓ Created session: {session_id}")
        
        # Test 2: Get cached file
        print("\n--- Test 2: Get Cached File ---")
        cached_file = cache_service.get_cached_file(session_id)
        print(f"✓ Retrieved cached file: {cached_file}")
        
        # Verify content
        with open(cached_file, 'rb') as f:
            cached_content = f.read()
        assert cached_content == test_content, "Cached content doesn't match original"
        print("✓ Content verification passed")
        
        # Test 3: Update cached file
        print("\n--- Test 3: Update Cached File ---")
        new_content = b'This is updated content.'
        success = cache_service.update_cached_file(session_id, new_content)
        assert success, "Failed to update cached file"
        print("✓ Updated cached file")
        
        # Verify update
        with open(cached_file, 'rb') as f:
            updated_content = f.read()
        assert updated_content == new_content, "Updated content doesn't match"
        print("✓ Update verification passed")
        
        # Test 4: Sync to NAS
        print("\n--- Test 4: Sync to NAS ---")
        success = cache_service.sync_to_nas(session_id)
        assert success, "Failed to sync to NAS"
        print("✓ Synced to NAS")
        
        # Verify sync
        with open(test_file_path, 'rb') as f:
            nas_content = f.read()
        assert nas_content == new_content, "NAS content doesn't match after sync"
        print("✓ Sync verification passed")
        
        # Test 5: Session metadata
        print("\n--- Test 5: Session Metadata ---")
        session_info = cache_service.get_session_info(session_id)
        assert session_info is not None, "Failed to get session info"
        assert session_info['user_id'] == user_id, "User ID mismatch"
        assert session_info['file_path'] == file_path, "File path mismatch"
        print(f"✓ Session metadata retrieved")
        print(f"  - User ID: {session_info['user_id']}")
        print(f"  - File Path: {session_info['file_path']}")
        print(f"  - Is Dirty: {session_info['is_dirty']}")
        
        # Test 6: File locking
        print("\n--- Test 6: File Locking ---")
        lock_acquired = cache_service.acquire_lock(session_id, user_id, file_path)
        assert lock_acquired, "Failed to acquire lock"
        print("✓ Lock acquired")
        
        is_locked, locked_by = cache_service.is_file_locked(file_path)
        assert is_locked, "File should be locked"
        assert locked_by == str(user_id), "Lock owner mismatch"
        print(f"✓ File is locked by user {locked_by}")
        
        lock_released = cache_service.release_lock(session_id)
        assert lock_released, "Failed to release lock"
        print("✓ Lock released")
        
        is_locked, _ = cache_service.is_file_locked(file_path)
        assert not is_locked, "File should not be locked"
        print("✓ File is no longer locked")
        
        # Test 7: Cache statistics
        print("\n--- Test 7: Cache Statistics ---")
        stats = cache_service.get_cache_statistics()
        print(f"✓ Cache statistics:")
        print(f"  - Total sessions: {stats['total_sessions']}")
        print(f"  - Active sessions: {stats['active_sessions']}")
        print(f"  - Total size: {stats['total_size_mb']} MB")
        
        # Test 8: Get all active sessions
        print("\n--- Test 8: Get All Active Sessions ---")
        active_sessions = cache_service.get_all_active_sessions()
        assert session_id in active_sessions, "Session should be in active sessions"
        print(f"✓ Found {len(active_sessions)} active session(s)")
        
        # Test 9: Cleanup session
        print("\n--- Test 9: Cleanup Session ---")
        success = cache_service.cleanup_session(session_id, sync_before_cleanup=True)
        assert success, "Failed to cleanup session"
        print("✓ Session cleaned up")
        
        # Verify cleanup
        session_dir = cache_service._get_session_dir(session_id)
        assert not session_dir.exists(), "Session directory should be removed"
        print("✓ Session directory removed")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup test directories
        shutil.rmtree(test_cache_dir, ignore_errors=True)
        shutil.rmtree(test_nas_dir, ignore_errors=True)
        print(f"\n✓ Cleaned up test directories")
    
    return True

if __name__ == '__main__':
    success = test_file_cache_service()
    sys.exit(0 if success else 1)
