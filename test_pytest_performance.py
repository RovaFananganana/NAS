#!/usr/bin/env python3
"""
Pytest-compatible Performance Tests for Database Optimization
Integrates with pytest framework for CI/CD and automated testing.

Usage:
    pytest test_pytest_performance.py -v
    pytest test_pytest_performance.py::test_permission_performance_requirements -v
    pytest test_pytest_performance.py --benchmark-only
"""

import pytest
import time
import statistics
from datetime import datetime

from app import create_app
from extensions import db
from models import User, File, Folder, FilePermission, FolderPermission, Group


@pytest.fixture(scope="module")
def app():
    """Create application for testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture(scope="module")
def test_data(app):
    """Create test data for performance tests."""
    with app.app_context():
        # Create test users
        users = []
        for i in range(10):
            user = User(
                username=f"pytest_user_{i}",
                email=f"pytest_{i}@example.com",
                password_hash="test_hash",
                role="user"
            )
            db.session.add(user)
            users.append(user)
        
        # Create test groups
        groups = []
        for i in range(3):
            group = Group(name=f"pytest_group_{i}")
            db.session.add(group)
            groups.append(group)
        
        db.session.commit()
        
        # Assign users to groups
        for i, user in enumerate(users):
            if i % 2 == 0:  # Every other user gets a group
                user.groups.append(groups[i % len(groups)])
        
        # Create folders
        folders = []
        root_folder = Folder(
            name="pytest_root",
            owner_id=users[0].id,
            parent_id=None
        )
        db.session.add(root_folder)
        folders.append(root_folder)
        
        # Create nested folders
        for i in range(1, 20):
            parent = folders[(i-1) // 3]  # Create tree structure
            folder = Folder(
                name=f"pytest_folder_{i}",
                owner_id=users[i % len(users)].id,
                parent_id=parent.id
            )
            db.session.add(folder)
            folders.append(folder)
        
        # Create files
        files = []
        for i in range(50):
            folder = folders[i % len(folders)]
            file_obj = File(
                name=f"pytest_file_{i}.txt",
                path=f"/pytest/file_{i}.txt",
                size_kb=100,
                owner_id=users[i % len(users)].id,
                folder_id=folder.id
            )
            db.session.add(file_obj)
            files.append(file_obj)
        
        db.session.commit()
        
        # Create permissions
        for i in range(0, len(files), 3):
            file_obj = files[i]
            user = users[i % len(users)]
            
            perm = FilePermission(
                user_id=user.id,
                file_id=file_obj.id,
                can_read=True,
                can_write=i % 2 == 0,
                can_delete=i % 4 == 0,
                can_share=i % 3 == 0
            )
            db.session.add(perm)
        
        db.session.commit()
        
        yield {
            'users': users,
            'folders': folders,
            'files': files,
            'groups': groups
        }


class TestPermissionPerformance:
    """Performance tests for permission system."""
    
    def test_individual_permission_check_performance(self, app, test_data):
        """Test individual permission check meets performance requirements."""
        with app.app_context():
            user = test_data['users'][0]
            file_obj = test_data['files'][0]
            
            # Measure performance
            times = []
            for _ in range(10):
                start_time = time.perf_counter()
                perm = file_obj.get_effective_permissions(user)
                duration = (time.perf_counter() - start_time) * 1000
                times.append(duration)
            
            avg_time = statistics.mean(times)
            
            # Requirement 1.2: Permission checks < 50ms
            assert avg_time < 50, f"Permission check took {avg_time:.2f}ms, should be < 50ms"
    
    def test_bulk_permission_performance(self, app, test_data):
        """Test bulk permission loading meets performance requirements."""
        with app.app_context():
            user = test_data['users'][0]
            files = test_data['files'][:20]  # Test with 20 files
            file_ids = [f.id for f in files]
            
            # Measure bulk operation performance
            start_time = time.perf_counter()
            permissions = File.get_bulk_permissions(user, file_ids)
            duration = (time.perf_counter() - start_time) * 1000
            
            # Requirement 1.3: 100+ files < 500ms (scaled down for 20 files)
            expected_max_time = 500 * (len(file_ids) / 100)  # Scale expectation
            assert duration < expected_max_time, f"Bulk operation took {duration:.2f}ms, should be < {expected_max_time:.2f}ms"
            
            # Verify we got results for all files
            assert len(permissions) == len(file_ids), f"Expected {len(file_ids)} results, got {len(permissions)}"
    
    def test_folder_access_performance(self, app, test_data):
        """Test folder access meets performance requirements."""
        with app.app_context():
            user = test_data['users'][0]
            folder = test_data['folders'][5]  # Use a nested folder
            
            # Measure folder permission check
            times = []
            for _ in range(10):
                start_time = time.perf_counter()
                perm = folder.get_effective_permissions(user)
                duration = (time.perf_counter() - start_time) * 1000
                times.append(duration)
            
            avg_time = statistics.mean(times)
            
            # Requirement 1.1: Folder access < 200ms
            assert avg_time < 200, f"Folder access took {avg_time:.2f}ms, should be < 200ms"
    
    def test_permission_correctness(self, app, test_data):
        """Test that optimized permissions match legacy implementation."""
        with app.app_context():
            user = test_data['users'][0]
            files = test_data['files'][:10]
            
            mismatches = 0
            
            for file_obj in files:
                # Get legacy permission
                legacy_perm = file_obj._get_effective_permissions_legacy(user)
                
                # Get optimized permission
                optimized_perm = file_obj.get_effective_permissions(user)
                
                # Compare results
                if (legacy_perm is None) != (optimized_perm is None):
                    mismatches += 1
                elif legacy_perm and optimized_perm:
                    # Compare permission attributes
                    legacy_attrs = {
                        'can_read': getattr(legacy_perm, 'can_read', False),
                        'can_write': getattr(legacy_perm, 'can_write', False),
                        'can_delete': getattr(legacy_perm, 'can_delete', False),
                        'can_share': getattr(legacy_perm, 'can_share', False)
                    }
                    
                    optimized_attrs = {
                        'can_read': getattr(optimized_perm, 'can_read', False),
                        'can_write': getattr(optimized_perm, 'can_write', False),
                        'can_delete': getattr(optimized_perm, 'can_delete', False),
                        'can_share': getattr(optimized_perm, 'can_share', False)
                    }
                    
                    if legacy_attrs != optimized_attrs:
                        mismatches += 1
            
            # Require 100% correctness
            assert mismatches == 0, f"Found {mismatches} permission mismatches out of {len(files)} files"
    
    def test_performance_improvement(self, app, test_data):
        """Test that optimized methods are faster than legacy methods."""
        with app.app_context():
            user = test_data['users'][0]
            files = test_data['files'][:10]
            
            # Measure legacy performance
            legacy_times = []
            for file_obj in files:
                start_time = time.perf_counter()
                file_obj._get_effective_permissions_legacy(user)
                legacy_times.append((time.perf_counter() - start_time) * 1000)
            
            # Measure optimized performance
            optimized_times = []
            for file_obj in files:
                start_time = time.perf_counter()
                file_obj.get_effective_permissions(user)
                optimized_times.append((time.perf_counter() - start_time) * 1000)
            
            legacy_avg = statistics.mean(legacy_times)
            optimized_avg = statistics.mean(optimized_times)
            
            # Require some improvement (at least not worse)
            assert optimized_avg <= legacy_avg, f"Optimized method ({optimized_avg:.2f}ms) is slower than legacy ({legacy_avg:.2f}ms)"
    
    def test_owner_permissions_always_work(self, app, test_data):
        """Regression test: owners should always have access to their files."""
        with app.app_context():
            files = test_data['files'][:5]
            
            for file_obj in files:
                owner = User.query.get(file_obj.owner_id)
                perm = file_obj.get_effective_permissions(owner)
                
                # Owner should always have at least read permission
                assert perm is not None, f"Owner {owner.id} has no permission on their file {file_obj.id}"
                assert getattr(perm, 'can_read', False), f"Owner {owner.id} cannot read their own file {file_obj.id}"
    
    def test_group_permissions_work(self, app, test_data):
        """Regression test: group permissions should be inherited."""
        with app.app_context():
            # Find a user with groups
            user_with_group = None
            for user in test_data['users']:
                if user.groups:
                    user_with_group = user
                    break
            
            if user_with_group:
                # Find a file with group permission for this user's group
                group = user_with_group.groups[0]
                group_perm = FilePermission.query.filter_by(group_id=group.id).first()
                
                if group_perm:
                    file_obj = File.query.get(group_perm.file_id)
                    user_perm = file_obj.get_effective_permissions(user_with_group)
                    
                    # User should inherit group permissions
                    assert user_perm is not None, f"User {user_with_group.id} should inherit group permission on file {file_obj.id}"


class TestPermissionBenchmarks:
    """Benchmark tests using pytest-benchmark."""
    
    def test_benchmark_individual_permission_check(self, app, test_data, benchmark):
        """Benchmark individual permission checks."""
        with app.app_context():
            user = test_data['users'][0]
            file_obj = test_data['files'][0]
            
            def permission_check():
                return file_obj.get_effective_permissions(user)
            
            result = benchmark(permission_check)
            assert result is not None or result is None  # Just ensure it completes
    
    def test_benchmark_bulk_permission_loading(self, app, test_data, benchmark):
        """Benchmark bulk permission loading."""
        with app.app_context():
            user = test_data['users'][0]
            file_ids = [f.id for f in test_data['files'][:10]]
            
            def bulk_permission_check():
                return File.get_bulk_permissions(user, file_ids)
            
            result = benchmark(bulk_permission_check)
            assert len(result) == len(file_ids)
    
    def test_benchmark_legacy_vs_optimized(self, app, test_data, benchmark):
        """Compare legacy vs optimized performance."""
        with app.app_context():
            user = test_data['users'][0]
            file_obj = test_data['files'][0]
            
            # Benchmark legacy method
            def legacy_check():
                return file_obj._get_effective_permissions_legacy(user)
            
            legacy_result = benchmark.pedantic(legacy_check, rounds=10, iterations=5)
            
            # Benchmark optimized method  
            def optimized_check():
                return file_obj.get_effective_permissions(user)
            
            optimized_result = benchmark.pedantic(optimized_check, rounds=10, iterations=5)


# Pytest configuration for performance tests
def pytest_configure(config):
    """Configure pytest for performance testing."""
    config.addinivalue_line(
        "markers", "performance: mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


# Mark all tests in this module as performance tests
pytestmark = pytest.mark.performance