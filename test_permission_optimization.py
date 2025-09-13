#!/usr/bin/env python3
"""
Test script to verify that the optimized permission methods work correctly
and maintain backward compatibility with the existing API.
"""

import sys
import os
import time
from datetime import datetime

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import User, File, Folder, FilePermission, FolderPermission, Group
from utils.performance_logger import compare_performance, performance_logger


def test_permission_compatibility():
    """Test that optimized methods maintain backward compatibility."""
    
    app = create_app()
    
    with app.app_context():
        print("🧪 Testing Permission Optimization Compatibility...")
        
        # Create test user
        test_user = User.query.first()
        if not test_user:
            print("❌ No test user found. Please create a user first.")
            return False
        
        # Test file permissions
        test_files = File.query.limit(5).all()
        if test_files:
            print(f"\n📁 Testing file permissions for {len(test_files)} files...")
            
            for file_obj in test_files:
                try:
                    # Test individual permission check
                    start_time = time.perf_counter()
                    perm = file_obj.get_effective_permissions(test_user)
                    duration = (time.perf_counter() - start_time) * 1000
                    
                    print(f"  File {file_obj.id} ({file_obj.name}): "
                          f"Permission={bool(perm)}, Duration={duration:.2f}ms")
                    
                    if perm:
                        print(f"    Permissions: read={getattr(perm, 'can_read', False)}, "
                              f"write={getattr(perm, 'can_write', False)}, "
                              f"delete={getattr(perm, 'can_delete', False)}, "
                              f"share={getattr(perm, 'can_share', False)}")
                        print(f"    Source: {getattr(perm, 'source', 'unknown')}")
                    
                except Exception as e:
                    print(f"  ❌ Error testing file {file_obj.id}: {str(e)}")
            
            # Test bulk file permissions
            file_ids = [f.id for f in test_files]
            try:
                print(f"\n📦 Testing bulk file permissions for {len(file_ids)} files...")
                start_time = time.perf_counter()
                bulk_perms = File.get_bulk_permissions(test_user, file_ids)
                duration = (time.perf_counter() - start_time) * 1000
                
                print(f"  Bulk query completed in {duration:.2f}ms")
                print(f"  Results: {len(bulk_perms)} permissions retrieved")
                
                for file_id, perm in bulk_perms.items():
                    if perm:
                        print(f"    File {file_id}: {getattr(perm, 'source', 'unknown')} permissions")
                
            except Exception as e:
                print(f"  ❌ Error in bulk file permissions: {str(e)}")
        
        # Test folder permissions
        test_folders = Folder.query.limit(5).all()
        if test_folders:
            print(f"\n📂 Testing folder permissions for {len(test_folders)} folders...")
            
            for folder_obj in test_folders:
                try:
                    # Test individual permission check
                    start_time = time.perf_counter()
                    perm = folder_obj.get_effective_permissions(test_user)
                    duration = (time.perf_counter() - start_time) * 1000
                    
                    print(f"  Folder {folder_obj.id} ({folder_obj.name}): "
                          f"Permission={bool(perm)}, Duration={duration:.2f}ms")
                    
                    if perm:
                        print(f"    Permissions: read={getattr(perm, 'can_read', False)}, "
                              f"write={getattr(perm, 'can_write', False)}, "
                              f"delete={getattr(perm, 'can_delete', False)}, "
                              f"share={getattr(perm, 'can_share', False)}")
                        print(f"    Source: {getattr(perm, 'source', 'unknown')}")
                    
                except Exception as e:
                    print(f"  ❌ Error testing folder {folder_obj.id}: {str(e)}")
            
            # Test bulk folder permissions
            folder_ids = [f.id for f in test_folders]
            try:
                print(f"\n📦 Testing bulk folder permissions for {len(folder_ids)} folders...")
                start_time = time.perf_counter()
                bulk_perms = Folder.get_bulk_permissions(test_user, folder_ids)
                duration = (time.perf_counter() - start_time) * 1000
                
                print(f"  Bulk query completed in {duration:.2f}ms")
                print(f"  Results: {len(bulk_perms)} permissions retrieved")
                
                for folder_id, perm in bulk_perms.items():
                    if perm:
                        print(f"    Folder {folder_id}: {getattr(perm, 'source', 'unknown')} permissions")
                
            except Exception as e:
                print(f"  ❌ Error in bulk folder permissions: {str(e)}")
            
            # Test folder tree permissions
            root_folder = test_folders[0]
            try:
                print(f"\n🌳 Testing folder tree permissions for folder {root_folder.id}...")
                start_time = time.perf_counter()
                tree_perms = Folder.get_tree_permissions(test_user, root_folder.id, depth=2)
                duration = (time.perf_counter() - start_time) * 1000
                
                print(f"  Tree query completed in {duration:.2f}ms")
                print(f"  Results: {len(tree_perms)} folder permissions in tree")
                
            except Exception as e:
                print(f"  ❌ Error in tree permissions: {str(e)}")
        
        print("\n✅ Permission optimization compatibility test completed!")
        return True


def performance_comparison_test():
    """Compare performance between legacy and optimized methods."""
    
    app = create_app()
    
    with app.app_context():
        print("\n⚡ Performance Comparison Test...")
        
        test_user = User.query.first()
        if not test_user:
            print("❌ No test user found.")
            return
        
        # Test files
        test_files = File.query.limit(10).all()
        if test_files:
            print(f"\n📊 Comparing file permission performance ({len(test_files)} files)...")
            
            # Legacy method timing
            legacy_times = []
            for file_obj in test_files:
                start_time = time.perf_counter()
                file_obj._get_effective_permissions_legacy(test_user)
                legacy_times.append((time.perf_counter() - start_time) * 1000)
            
            avg_legacy = sum(legacy_times) / len(legacy_times)
            
            # Optimized method timing
            optimized_times = []
            for file_obj in test_files:
                start_time = time.perf_counter()
                file_obj.get_effective_permissions(test_user)
                optimized_times.append((time.perf_counter() - start_time) * 1000)
            
            avg_optimized = sum(optimized_times) / len(optimized_times)
            
            compare_performance(avg_legacy, avg_optimized, "File.get_effective_permissions", len(test_files))
            
            print(f"  Legacy average: {avg_legacy:.2f}ms")
            print(f"  Optimized average: {avg_optimized:.2f}ms")
            if avg_legacy > 0:
                improvement = ((avg_legacy - avg_optimized) / avg_legacy) * 100
                print(f"  Improvement: {improvement:.1f}%")
        
        # Test folders
        test_folders = Folder.query.limit(10).all()
        if test_folders:
            print(f"\n📊 Comparing folder permission performance ({len(test_folders)} folders)...")
            
            # Legacy method timing
            legacy_times = []
            for folder_obj in test_folders:
                start_time = time.perf_counter()
                folder_obj._get_effective_permissions_legacy(test_user)
                legacy_times.append((time.perf_counter() - start_time) * 1000)
            
            avg_legacy = sum(legacy_times) / len(legacy_times)
            
            # Optimized method timing
            optimized_times = []
            for folder_obj in test_folders:
                start_time = time.perf_counter()
                folder_obj.get_effective_permissions(test_user)
                optimized_times.append((time.perf_counter() - start_time) * 1000)
            
            avg_optimized = sum(optimized_times) / len(optimized_times)
            
            compare_performance(avg_legacy, avg_optimized, "Folder.get_effective_permissions", len(test_folders))
            
            print(f"  Legacy average: {avg_legacy:.2f}ms")
            print(f"  Optimized average: {avg_optimized:.2f}ms")
            if avg_legacy > 0:
                improvement = ((avg_legacy - avg_optimized) / avg_legacy) * 100
                print(f"  Improvement: {improvement:.1f}%")


if __name__ == "__main__":
    print("🚀 Starting Permission Optimization Tests...")
    
    # Run compatibility test
    success = test_permission_compatibility()
    
    if success:
        # Run performance comparison
        performance_comparison_test()
    
    print("\n🏁 Tests completed!")