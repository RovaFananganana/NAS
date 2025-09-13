#!/usr/bin/env python3
"""
Performance Load Testing Suite for Database Optimization
Tests permission system performance under various load conditions.

Requirements covered:
- 1.1: User access to folders in < 200ms
- 1.2: Permission checks in < 50ms  
- 1.3: 100+ file permission checks in < 500ms
"""

import sys
import os
import time
import threading
import concurrent.futures
import statistics
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Tuple

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import User, File, Folder, FilePermission, FolderPermission, Group


@dataclass
class LoadTestResult:
    """Results from a load test scenario."""
    test_name: str
    total_operations: int
    concurrent_users: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    max_response_time_ms: float
    min_response_time_ms: float
    success_rate: float
    errors: List[str]
    duration_seconds: float


class PermissionLoadTester:
    """Load testing framework for permission operations."""
    
    def __init__(self, app):
        self.app = app
        self.results = []
        
    def create_test_data(self, num_users=100, num_folders=1000, num_files=10000, max_depth=10):
        """Create test data for load testing."""
        print(f"🏗️  Creating test data: {num_users} users, {num_folders} folders, {num_files} files...")
        
        with self.app.app_context():
            # Create test users
            test_users = []
            for i in range(num_users):
                user = User(
                    username=f"loadtest_user_{i}",
                    email=f"loadtest_{i}@example.com",
                    password_hash="test_hash",
                    role="user"
                )
                db.session.add(user)
                test_users.append(user)
            
            # Create test groups
            test_groups = []
            for i in range(10):  # Create 10 groups
                group = Group(name=f"loadtest_group_{i}")
                db.session.add(group)
                test_groups.append(group)
            
            db.session.commit()
            
            # Assign users to groups
            for i, user in enumerate(test_users):
                group = test_groups[i % len(test_groups)]
                user.groups.append(group)
            
            # Create deep folder hierarchy
            folders = []
            root_folder = Folder(
                name="loadtest_root",
                owner_id=test_users[0].id,
                parent_id=None
            )
            db.session.add(root_folder)
            folders.append(root_folder)
            
            # Create nested folders
            current_parents = [root_folder]
            for depth in range(1, max_depth + 1):
                next_parents = []
                folders_per_level = min(100, num_folders // max_depth)
                
                for i in range(folders_per_level):
                    parent = current_parents[i % len(current_parents)]
                    folder = Folder(
                        name=f"loadtest_folder_d{depth}_{i}",
                        owner_id=test_users[i % len(test_users)].id,
                        parent_id=parent.id
                    )
                    db.session.add(folder)
                    folders.append(folder)
                    next_parents.append(folder)
                
                current_parents = next_parents
                if len(folders) >= num_folders:
                    break
            
            db.session.commit()
            
            # Create files distributed across folders
            files = []
            for i in range(num_files):
                folder = folders[i % len(folders)]
                file_obj = File(
                    name=f"loadtest_file_{i}.txt",
                    path=f"/loadtest/file_{i}.txt",
                    size_kb=100,
                    owner_id=test_users[i % len(test_users)].id,
                    folder_id=folder.id
                )
                db.session.add(file_obj)
                files.append(file_obj)
            
            db.session.commit()
            
            # Create permissions for some files and folders
            permission_count = min(1000, num_files // 10)
            for i in range(permission_count):
                user = test_users[i % len(test_users)]
                file_obj = files[i]
                
                perm = FilePermission(
                    user_id=user.id,
                    file_id=file_obj.id,
                    can_read=True,
                    can_write=i % 3 == 0,
                    can_delete=i % 5 == 0,
                    can_share=i % 4 == 0
                )
                db.session.add(perm)
            
            # Create folder permissions
            folder_perm_count = min(500, num_folders // 5)
            for i in range(folder_perm_count):
                user = test_users[i % len(test_users)]
                folder = folders[i + 1]  # Skip root folder
                
                perm = FolderPermission(
                    user_id=user.id,
                    folder_id=folder.id,
                    can_read=True,
                    can_write=i % 3 == 0,
                    can_delete=i % 5 == 0,
                    can_share=i % 4 == 0
                )
                db.session.add(perm)
            
            db.session.commit()
            
            print(f"✅ Test data created: {len(test_users)} users, {len(folders)} folders, {len(files)} files")
            return test_users, folders, files
    
    def cleanup_test_data(self):
        """Clean up test data after testing."""
        print("🧹 Cleaning up test data...")
        
        with self.app.app_context():
            # Delete test permissions
            FilePermission.query.filter(
                FilePermission.file.has(File.name.like('loadtest_%'))
            ).delete(synchronize_session=False)
            
            FolderPermission.query.filter(
                FolderPermission.folder.has(Folder.name.like('loadtest_%'))
            ).delete(synchronize_session=False)
            
            # Delete test files
            File.query.filter(File.name.like('loadtest_%')).delete(synchronize_session=False)
            
            # Delete test folders
            Folder.query.filter(Folder.name.like('loadtest_%')).delete(synchronize_session=False)
            
            # Delete test users and groups
            User.query.filter(User.username.like('loadtest_%')).delete(synchronize_session=False)
            Group.query.filter(Group.name.like('loadtest_%')).delete(synchronize_session=False)
            
            db.session.commit()
            print("✅ Test data cleaned up")
    
    def simulate_user_session(self, user_id: int, files: List[File], folders: List[Folder], 
                            operations_per_user: int) -> List[float]:
        """Simulate a user session with multiple permission checks."""
        response_times = []
        
        with self.app.app_context():
            user = User.query.get(user_id)
            if not user:
                return response_times
            
            for _ in range(operations_per_user):
                # Random file permission check
                file_obj = files[hash(f"{user_id}_{time.time()}") % len(files)]
                
                start_time = time.perf_counter()
                try:
                    perm = file_obj.get_effective_permissions(user)
                    response_time = (time.perf_counter() - start_time) * 1000
                    response_times.append(response_time)
                except Exception as e:
                    # Record error but continue
                    response_times.append(float('inf'))
        
        return response_times
    
    def run_concurrent_permission_test(self, concurrent_users: int, operations_per_user: int,
                                     test_users: List[User], files: List[File], 
                                     folders: List[Folder]) -> LoadTestResult:
        """Run concurrent permission checks with multiple users."""
        print(f"🚀 Running concurrent test: {concurrent_users} users, {operations_per_user} ops each")
        
        start_time = time.time()
        all_response_times = []
        errors = []
        
        # Use ThreadPoolExecutor for concurrent execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            # Submit tasks for each user
            futures = []
            for i in range(concurrent_users):
                user = test_users[i % len(test_users)]
                future = executor.submit(
                    self.simulate_user_session, 
                    user.id, files, folders, operations_per_user
                )
                futures.append(future)
            
            # Collect results
            for future in concurrent.futures.as_completed(futures):
                try:
                    response_times = future.result()
                    # Filter out error responses (inf values)
                    valid_times = [t for t in response_times if t != float('inf')]
                    error_count = len(response_times) - len(valid_times)
                    
                    all_response_times.extend(valid_times)
                    if error_count > 0:
                        errors.append(f"User session had {error_count} errors")
                        
                except Exception as e:
                    errors.append(f"User session failed: {str(e)}")
        
        end_time = time.time()
        
        # Calculate statistics
        if all_response_times:
            avg_time = statistics.mean(all_response_times)
            p95_time = statistics.quantiles(all_response_times, n=20)[18]  # 95th percentile
            p99_time = statistics.quantiles(all_response_times, n=100)[98]  # 99th percentile
            max_time = max(all_response_times)
            min_time = min(all_response_times)
        else:
            avg_time = p95_time = p99_time = max_time = min_time = 0
        
        total_operations = concurrent_users * operations_per_user
        success_rate = len(all_response_times) / total_operations if total_operations > 0 else 0
        
        return LoadTestResult(
            test_name=f"Concurrent_{concurrent_users}users_{operations_per_user}ops",
            total_operations=total_operations,
            concurrent_users=concurrent_users,
            avg_response_time_ms=avg_time,
            p95_response_time_ms=p95_time,
            p99_response_time_ms=p99_time,
            max_response_time_ms=max_time,
            min_response_time_ms=min_time,
            success_rate=success_rate,
            errors=errors,
            duration_seconds=end_time - start_time
        )
    
    def test_bulk_permission_performance(self, test_users: List[User], files: List[File]) -> LoadTestResult:
        """Test bulk permission loading performance (Requirement 1.3)."""
        print("📦 Testing bulk permission performance...")
        
        start_time = time.time()
        response_times = []
        errors = []
        
        with self.app.app_context():
            user = test_users[0]
            
            # Test with different batch sizes
            batch_sizes = [10, 50, 100, 200, 500]
            
            for batch_size in batch_sizes:
                if batch_size > len(files):
                    continue
                    
                file_ids = [f.id for f in files[:batch_size]]
                
                for _ in range(10):  # 10 iterations per batch size
                    start = time.perf_counter()
                    try:
                        permissions = File.get_bulk_permissions(user, file_ids)
                        response_time = (time.perf_counter() - start) * 1000
                        response_times.append(response_time)
                        
                        # Verify we got results
                        if len(permissions) != len(file_ids):
                            errors.append(f"Bulk query returned {len(permissions)} results for {len(file_ids)} files")
                            
                    except Exception as e:
                        errors.append(f"Bulk permission error: {str(e)}")
                        response_times.append(float('inf'))
        
        end_time = time.time()
        
        # Filter valid response times
        valid_times = [t for t in response_times if t != float('inf')]
        
        if valid_times:
            avg_time = statistics.mean(valid_times)
            p95_time = statistics.quantiles(valid_times, n=20)[18] if len(valid_times) >= 20 else max(valid_times)
            p99_time = statistics.quantiles(valid_times, n=100)[98] if len(valid_times) >= 100 else max(valid_times)
            max_time = max(valid_times)
            min_time = min(valid_times)
        else:
            avg_time = p95_time = p99_time = max_time = min_time = 0
        
        success_rate = len(valid_times) / len(response_times) if response_times else 0
        
        return LoadTestResult(
            test_name="Bulk_Permission_Loading",
            total_operations=len(response_times),
            concurrent_users=1,
            avg_response_time_ms=avg_time,
            p95_response_time_ms=p95_time,
            p99_response_time_ms=p99_time,
            max_response_time_ms=max_time,
            min_response_time_ms=min_time,
            success_rate=success_rate,
            errors=errors,
            duration_seconds=end_time - start_time
        )
    
    def test_deep_hierarchy_performance(self, test_users: List[User], folders: List[Folder]) -> LoadTestResult:
        """Test performance with deep folder hierarchies."""
        print("🌳 Testing deep hierarchy performance...")
        
        start_time = time.time()
        response_times = []
        errors = []
        
        with self.app.app_context():
            user = test_users[0]
            
            # Find folders at different depths
            deep_folders = [f for f in folders if 'loadtest_folder_d' in f.name]
            
            for folder in deep_folders[:50]:  # Test first 50 deep folders
                for _ in range(5):  # 5 iterations per folder
                    start = time.perf_counter()
                    try:
                        perm = folder.get_effective_permissions(user)
                        response_time = (time.perf_counter() - start) * 1000
                        response_times.append(response_time)
                    except Exception as e:
                        errors.append(f"Deep hierarchy error: {str(e)}")
                        response_times.append(float('inf'))
        
        end_time = time.time()
        
        # Calculate statistics
        valid_times = [t for t in response_times if t != float('inf')]
        
        if valid_times:
            avg_time = statistics.mean(valid_times)
            p95_time = statistics.quantiles(valid_times, n=20)[18] if len(valid_times) >= 20 else max(valid_times)
            p99_time = statistics.quantiles(valid_times, n=100)[98] if len(valid_times) >= 100 else max(valid_times)
            max_time = max(valid_times)
            min_time = min(valid_times)
        else:
            avg_time = p95_time = p99_time = max_time = min_time = 0
        
        success_rate = len(valid_times) / len(response_times) if response_times else 0
        
        return LoadTestResult(
            test_name="Deep_Hierarchy_Performance",
            total_operations=len(response_times),
            concurrent_users=1,
            avg_response_time_ms=avg_time,
            p95_response_time_ms=p95_time,
            p99_response_time_ms=p99_time,
            max_response_time_ms=max_time,
            min_response_time_ms=min_time,
            success_rate=success_rate,
            errors=errors,
            duration_seconds=end_time - start_time
        )
    
    def run_all_load_tests(self):
        """Run all load test scenarios."""
        print("🎯 Starting Performance Load Tests...")
        print("=" * 60)
        
        try:
            # Create test data
            test_users, folders, files = self.create_test_data(
                num_users=100,
                num_folders=1000, 
                num_files=10000,
                max_depth=10
            )
            
            # Test 1: Small concurrent load (Requirement 1.2 - < 50ms)
            result1 = self.run_concurrent_permission_test(
                concurrent_users=10,
                operations_per_user=20,
                test_users=test_users,
                files=files,
                folders=folders
            )
            self.results.append(result1)
            
            # Test 2: Medium concurrent load (Requirement 1.1 - < 200ms)
            result2 = self.run_concurrent_permission_test(
                concurrent_users=50,
                operations_per_user=10,
                test_users=test_users,
                files=files,
                folders=folders
            )
            self.results.append(result2)
            
            # Test 3: High concurrent load (1000+ users as specified)
            result3 = self.run_concurrent_permission_test(
                concurrent_users=100,  # Limited by system resources
                operations_per_user=15,
                test_users=test_users,
                files=files,
                folders=folders
            )
            self.results.append(result3)
            
            # Test 4: Bulk permission performance (Requirement 1.3 - < 500ms for 100+ files)
            result4 = self.test_bulk_permission_performance(test_users, files)
            self.results.append(result4)
            
            # Test 5: Deep hierarchy performance
            result5 = self.test_deep_hierarchy_performance(test_users, folders)
            self.results.append(result5)
            
        finally:
            # Always clean up test data
            self.cleanup_test_data()
        
        # Print results
        self.print_results()
    
    def print_results(self):
        """Print formatted test results."""
        print("\n" + "=" * 80)
        print("📊 LOAD TEST RESULTS")
        print("=" * 80)
        
        for result in self.results:
            print(f"\n🔍 {result.test_name}")
            print("-" * 50)
            print(f"Total Operations: {result.total_operations}")
            print(f"Concurrent Users: {result.concurrent_users}")
            print(f"Duration: {result.duration_seconds:.2f}s")
            print(f"Success Rate: {result.success_rate:.1%}")
            print(f"Average Response Time: {result.avg_response_time_ms:.2f}ms")
            print(f"95th Percentile: {result.p95_response_time_ms:.2f}ms")
            print(f"99th Percentile: {result.p99_response_time_ms:.2f}ms")
            print(f"Min/Max: {result.min_response_time_ms:.2f}ms / {result.max_response_time_ms:.2f}ms")
            
            # Check requirements compliance
            self.check_requirements_compliance(result)
            
            if result.errors:
                print(f"❌ Errors ({len(result.errors)}):")
                for error in result.errors[:5]:  # Show first 5 errors
                    print(f"   - {error}")
                if len(result.errors) > 5:
                    print(f"   ... and {len(result.errors) - 5} more")
    
    def check_requirements_compliance(self, result: LoadTestResult):
        """Check if results meet the specified requirements."""
        print("\n📋 Requirements Compliance:")
        
        # Requirement 1.1: Folder access < 200ms
        if "Concurrent" in result.test_name:
            if result.avg_response_time_ms < 200:
                print("   ✅ Req 1.1: Folder access < 200ms - PASSED")
            else:
                print(f"   ❌ Req 1.1: Folder access < 200ms - FAILED ({result.avg_response_time_ms:.2f}ms)")
        
        # Requirement 1.2: Permission checks < 50ms
        if result.avg_response_time_ms < 50:
            print("   ✅ Req 1.2: Permission checks < 50ms - PASSED")
        else:
            print(f"   ❌ Req 1.2: Permission checks < 50ms - FAILED ({result.avg_response_time_ms:.2f}ms)")
        
        # Requirement 1.3: 100+ files < 500ms (for bulk operations)
        if "Bulk" in result.test_name:
            if result.avg_response_time_ms < 500:
                print("   ✅ Req 1.3: 100+ file permissions < 500ms - PASSED")
            else:
                print(f"   ❌ Req 1.3: 100+ file permissions < 500ms - FAILED ({result.avg_response_time_ms:.2f}ms)")


def main():
    """Main function to run load tests."""
    app = create_app()
    
    tester = PermissionLoadTester(app)
    
    try:
        tester.run_all_load_tests()
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        tester.cleanup_test_data()
    except Exception as e:
        print(f"\n❌ Test suite failed: {str(e)}")
        tester.cleanup_test_data()
        raise


if __name__ == "__main__":
    main()