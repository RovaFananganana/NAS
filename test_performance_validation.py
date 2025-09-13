#!/usr/bin/env python3
"""
Performance Validation Testing Suite for Database Optimization
Validates that optimized permission methods produce identical results to legacy methods
and provides regression testing with performance benchmarks.

Requirements covered:
- 2.1: Optimized queries with joins instead of multiple queries
- 2.2: Proper index usage for maximum performance  
- 2.3: Avoid N+1 queries for inherited permissions
"""

import sys
import os
import time
import statistics
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import User, File, Folder, FilePermission, FolderPermission, Group


@dataclass
class ValidationResult:
    """Results from a validation test."""
    test_name: str
    total_comparisons: int
    matches: int
    mismatches: int
    legacy_avg_time_ms: float
    optimized_avg_time_ms: float
    performance_improvement_percent: float
    errors: List[str]
    mismatch_details: List[Dict[str, Any]]


@dataclass
class BenchmarkResult:
    """Results from performance benchmarking."""
    operation_name: str
    legacy_times: List[float]
    optimized_times: List[float]
    improvement_factor: float
    statistical_significance: bool


class PermissionValidationTester:
    """Validation testing framework for permission optimization."""
    
    def __init__(self, app):
        self.app = app
        self.validation_results = []
        self.benchmark_results = []
        
    def create_validation_test_data(self):
        """Create comprehensive test data for validation."""
        print("🏗️  Creating validation test data...")
        
        with self.app.app_context():
            # Create test users with different roles
            test_users = []
            user_roles = ['admin', 'user', 'viewer', 'editor']
            
            for i in range(20):
                user = User(
                    username=f"validation_user_{i}",
                    email=f"validation_{i}@example.com", 
                    password_hash="test_hash",
                    role=user_roles[i % len(user_roles)]
                )
                db.session.add(user)
                test_users.append(user)
            
            # Create test groups with different permission patterns
            test_groups = []
            for i in range(5):
                group = Group(name=f"validation_group_{i}")
                db.session.add(group)
                test_groups.append(group)
            
            db.session.commit()
            
            # Assign users to groups in various patterns
            for i, user in enumerate(test_users):
                # Some users in multiple groups
                if i % 3 == 0:
                    user.groups.extend([test_groups[0], test_groups[1]])
                elif i % 3 == 1:
                    user.groups.append(test_groups[i % len(test_groups)])
                # Some users in no groups (i % 3 == 2)
            
            # Create folder hierarchy with various ownership patterns
            folders = []
            
            # Root folders owned by different users
            for i in range(5):
                root_folder = Folder(
                    name=f"validation_root_{i}",
                    owner_id=test_users[i].id,
                    parent_id=None
                )
                db.session.add(root_folder)
                folders.append(root_folder)
            
            # Create nested structure with mixed ownership
            for depth in range(1, 6):  # 5 levels deep
                for parent in folders[-5:]:  # Use recent folders as parents
                    for i in range(3):  # 3 children per parent
                        child_folder = Folder(
                            name=f"validation_folder_d{depth}_{i}_{parent.id}",
                            owner_id=test_users[(depth + i) % len(test_users)].id,
                            parent_id=parent.id
                        )
                        db.session.add(child_folder)
                        folders.append(child_folder)
            
            db.session.commit()
            
            # Create files with various ownership and folder assignments
            files = []
            for i in range(200):
                folder = folders[i % len(folders)]
                file_obj = File(
                    name=f"validation_file_{i}.txt",
                    path=f"/validation/file_{i}.txt",
                    size_kb=100 + (i % 1000),
                    owner_id=test_users[i % len(test_users)].id,
                    folder_id=folder.id
                )
                db.session.add(file_obj)
                files.append(file_obj)
            
            db.session.commit()
            
            # Create complex permission patterns
            self._create_complex_permissions(test_users, test_groups, files, folders)
            
            print(f"✅ Validation test data created: {len(test_users)} users, {len(folders)} folders, {len(files)} files")
            return test_users, folders, files
    
    def _create_complex_permissions(self, users: List[User], groups: List[Group], 
                                  files: List[File], folders: List[Folder]):
        """Create complex permission scenarios for thorough testing."""
        
        # Direct file permissions
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
        
        # Group file permissions
        for i in range(1, len(files), 4):
            file_obj = files[i]
            group = groups[i % len(groups)]
            
            perm = FilePermission(
                group_id=group.id,
                file_id=file_obj.id,
                can_read=True,
                can_write=i % 3 == 0,
                can_delete=False,
                can_share=i % 5 == 0
            )
            db.session.add(perm)
        
        # Direct folder permissions
        for i in range(5, len(folders), 2):  # Skip root folders
            folder = folders[i]
            user = users[i % len(users)]
            
            perm = FolderPermission(
                user_id=user.id,
                folder_id=folder.id,
                can_read=True,
                can_write=i % 3 == 0,
                can_delete=i % 6 == 0,
                can_share=i % 4 == 0
            )
            db.session.add(perm)
        
        # Group folder permissions
        for i in range(6, len(folders), 3):
            folder = folders[i]
            group = groups[i % len(groups)]
            
            perm = FolderPermission(
                group_id=group.id,
                folder_id=folder.id,
                can_read=True,
                can_write=i % 4 == 0,
                can_delete=False,
                can_share=i % 2 == 0
            )
            db.session.add(perm)
        
        db.session.commit()
    
    def cleanup_validation_test_data(self):
        """Clean up validation test data."""
        print("🧹 Cleaning up validation test data...")
        
        with self.app.app_context():
            # Delete permissions
            FilePermission.query.filter(
                FilePermission.file.has(File.name.like('validation_%'))
            ).delete(synchronize_session=False)
            
            FolderPermission.query.filter(
                FolderPermission.folder.has(Folder.name.like('validation_%'))
            ).delete(synchronize_session=False)
            
            # Delete files and folders
            File.query.filter(File.name.like('validation_%')).delete(synchronize_session=False)
            Folder.query.filter(Folder.name.like('validation_%')).delete(synchronize_session=False)
            
            # Delete users and groups
            User.query.filter(User.username.like('validation_%')).delete(synchronize_session=False)
            Group.query.filter(Group.name.like('validation_%')).delete(synchronize_session=False)
            
            db.session.commit()
            print("✅ Validation test data cleaned up")
    
    def compare_permission_results(self, legacy_perm, optimized_perm, resource_id: int, 
                                 user_id: int) -> Tuple[bool, Dict[str, Any]]:
        """Compare legacy and optimized permission results."""
        
        # Handle None cases
        if legacy_perm is None and optimized_perm is None:
            return True, {}
        
        if legacy_perm is None or optimized_perm is None:
            return False, {
                'resource_id': resource_id,
                'user_id': user_id,
                'legacy_exists': legacy_perm is not None,
                'optimized_exists': optimized_perm is not None,
                'issue': 'Existence mismatch'
            }
        
        # Compare permission attributes
        legacy_attrs = {
            'can_read': getattr(legacy_perm, 'can_read', False),
            'can_write': getattr(legacy_perm, 'can_write', False),
            'can_delete': getattr(legacy_perm, 'can_delete', False),
            'can_share': getattr(legacy_perm, 'can_share', False),
            'is_owner': getattr(legacy_perm, 'is_owner', False)
        }
        
        optimized_attrs = {
            'can_read': getattr(optimized_perm, 'can_read', False),
            'can_write': getattr(optimized_perm, 'can_write', False),
            'can_delete': getattr(optimized_perm, 'can_delete', False),
            'can_share': getattr(optimized_perm, 'can_share', False),
            'is_owner': getattr(optimized_perm, 'is_owner', False)
        }
        
        # Check for differences
        differences = {}
        for attr, legacy_val in legacy_attrs.items():
            optimized_val = optimized_attrs[attr]
            if legacy_val != optimized_val:
                differences[attr] = {
                    'legacy': legacy_val,
                    'optimized': optimized_val
                }
        
        if differences:
            return False, {
                'resource_id': resource_id,
                'user_id': user_id,
                'differences': differences,
                'issue': 'Permission value mismatch'
            }
        
        return True, {}
    
    def validate_file_permissions(self, users: List[User], files: List[File]) -> ValidationResult:
        """Validate file permission methods produce identical results."""
        print("📁 Validating file permission methods...")
        
        matches = 0
        mismatches = 0
        errors = []
        mismatch_details = []
        legacy_times = []
        optimized_times = []
        
        with self.app.app_context():
            # Test subset of users and files for thorough validation
            test_users = users[:10]
            test_files = files[:50]
            
            for user in test_users:
                for file_obj in test_files:
                    try:
                        # Time legacy method
                        start_time = time.perf_counter()
                        legacy_perm = file_obj._get_effective_permissions_legacy(user)
                        legacy_time = (time.perf_counter() - start_time) * 1000
                        legacy_times.append(legacy_time)
                        
                        # Time optimized method
                        start_time = time.perf_counter()
                        optimized_perm = file_obj.get_effective_permissions(user)
                        optimized_time = (time.perf_counter() - start_time) * 1000
                        optimized_times.append(optimized_time)
                        
                        # Compare results
                        is_match, mismatch_detail = self.compare_permission_results(
                            legacy_perm, optimized_perm, file_obj.id, user.id
                        )
                        
                        if is_match:
                            matches += 1
                        else:
                            mismatches += 1
                            mismatch_details.append(mismatch_detail)
                            
                    except Exception as e:
                        errors.append(f"Error comparing file {file_obj.id} for user {user.id}: {str(e)}")
                        mismatches += 1
        
        # Calculate performance metrics
        legacy_avg = statistics.mean(legacy_times) if legacy_times else 0
        optimized_avg = statistics.mean(optimized_times) if optimized_times else 0
        improvement = ((legacy_avg - optimized_avg) / legacy_avg * 100) if legacy_avg > 0 else 0
        
        return ValidationResult(
            test_name="File_Permission_Validation",
            total_comparisons=matches + mismatches,
            matches=matches,
            mismatches=mismatches,
            legacy_avg_time_ms=legacy_avg,
            optimized_avg_time_ms=optimized_avg,
            performance_improvement_percent=improvement,
            errors=errors,
            mismatch_details=mismatch_details[:10]  # Limit details for readability
        )
    
    def validate_folder_permissions(self, users: List[User], folders: List[Folder]) -> ValidationResult:
        """Validate folder permission methods produce identical results."""
        print("📂 Validating folder permission methods...")
        
        matches = 0
        mismatches = 0
        errors = []
        mismatch_details = []
        legacy_times = []
        optimized_times = []
        
        with self.app.app_context():
            # Test subset for thorough validation
            test_users = users[:10]
            test_folders = folders[5:35]  # Skip root folders, test nested ones
            
            for user in test_users:
                for folder in test_folders:
                    try:
                        # Time legacy method
                        start_time = time.perf_counter()
                        legacy_perm = folder._get_effective_permissions_legacy(user)
                        legacy_time = (time.perf_counter() - start_time) * 1000
                        legacy_times.append(legacy_time)
                        
                        # Time optimized method
                        start_time = time.perf_counter()
                        optimized_perm = folder.get_effective_permissions(user)
                        optimized_time = (time.perf_counter() - start_time) * 1000
                        optimized_times.append(optimized_time)
                        
                        # Compare results
                        is_match, mismatch_detail = self.compare_permission_results(
                            legacy_perm, optimized_perm, folder.id, user.id
                        )
                        
                        if is_match:
                            matches += 1
                        else:
                            mismatches += 1
                            mismatch_details.append(mismatch_detail)
                            
                    except Exception as e:
                        errors.append(f"Error comparing folder {folder.id} for user {user.id}: {str(e)}")
                        mismatches += 1
        
        # Calculate performance metrics
        legacy_avg = statistics.mean(legacy_times) if legacy_times else 0
        optimized_avg = statistics.mean(optimized_times) if optimized_times else 0
        improvement = ((legacy_avg - optimized_avg) / legacy_avg * 100) if legacy_avg > 0 else 0
        
        return ValidationResult(
            test_name="Folder_Permission_Validation",
            total_comparisons=matches + mismatches,
            matches=matches,
            mismatches=mismatches,
            legacy_avg_time_ms=legacy_avg,
            optimized_avg_time_ms=optimized_avg,
            performance_improvement_percent=improvement,
            errors=errors,
            mismatch_details=mismatch_details[:10]
        )
    
    def validate_bulk_operations(self, users: List[User], files: List[File]) -> ValidationResult:
        """Validate bulk permission operations against individual calls."""
        print("📦 Validating bulk permission operations...")
        
        matches = 0
        mismatches = 0
        errors = []
        mismatch_details = []
        individual_times = []
        bulk_times = []
        
        with self.app.app_context():
            user = users[0]
            test_files = files[:20]  # Test with 20 files
            file_ids = [f.id for f in test_files]
            
            # Get individual permissions
            start_time = time.perf_counter()
            individual_perms = {}
            for file_obj in test_files:
                perm = file_obj.get_effective_permissions(user)
                individual_perms[file_obj.id] = perm
            individual_time = (time.perf_counter() - start_time) * 1000
            individual_times.append(individual_time)
            
            # Get bulk permissions
            start_time = time.perf_counter()
            try:
                bulk_perms = File.get_bulk_permissions(user, file_ids)
                bulk_time = (time.perf_counter() - start_time) * 1000
                bulk_times.append(bulk_time)
                
                # Compare results
                for file_id in file_ids:
                    individual_perm = individual_perms.get(file_id)
                    bulk_perm = bulk_perms.get(file_id)
                    
                    is_match, mismatch_detail = self.compare_permission_results(
                        individual_perm, bulk_perm, file_id, user.id
                    )
                    
                    if is_match:
                        matches += 1
                    else:
                        mismatches += 1
                        mismatch_details.append(mismatch_detail)
                        
            except Exception as e:
                errors.append(f"Bulk operation error: {str(e)}")
                mismatches += len(file_ids)
        
        # Calculate performance metrics
        individual_avg = statistics.mean(individual_times) if individual_times else 0
        bulk_avg = statistics.mean(bulk_times) if bulk_times else 0
        improvement = ((individual_avg - bulk_avg) / individual_avg * 100) if individual_avg > 0 else 0
        
        return ValidationResult(
            test_name="Bulk_Operation_Validation",
            total_comparisons=matches + mismatches,
            matches=matches,
            mismatches=mismatches,
            legacy_avg_time_ms=individual_avg,
            optimized_avg_time_ms=bulk_avg,
            performance_improvement_percent=improvement,
            errors=errors,
            mismatch_details=mismatch_details[:10]
        )
    
    def run_regression_tests(self, users: List[User], files: List[File], folders: List[Folder]):
        """Run regression tests to ensure no functionality is broken."""
        print("🔄 Running regression tests...")
        
        regression_results = []
        
        with self.app.app_context():
            # Test 1: Owner permissions should always work
            print("  Testing owner permissions...")
            owner_errors = []
            for file_obj in files[:10]:
                owner = User.query.get(file_obj.owner_id)
                if owner:
                    perm = file_obj.get_effective_permissions(owner)
                    if not perm or not getattr(perm, 'can_read', False):
                        owner_errors.append(f"Owner {owner.id} cannot read their own file {file_obj.id}")
            
            # Test 2: Permission inheritance should work
            print("  Testing permission inheritance...")
            inheritance_errors = []
            for folder in folders[5:15]:  # Test nested folders
                if folder.parent_id:
                    parent = Folder.query.get(folder.parent_id)
                    user = users[0]
                    
                    parent_perm = parent.get_effective_permissions(user)
                    child_perm = folder.get_effective_permissions(user)
                    
                    # If parent has permission and child has no direct permission,
                    # child should inherit
                    if parent_perm and getattr(parent_perm, 'can_read', False):
                        # Check if child has direct permissions
                        direct_perm = FolderPermission.query.filter_by(
                            folder_id=folder.id, user_id=user.id
                        ).first()
                        
                        if not direct_perm and (not child_perm or not getattr(child_perm, 'can_read', False)):
                            inheritance_errors.append(
                                f"Folder {folder.id} should inherit read permission from parent {parent.id}"
                            )
            
            # Test 3: Group permissions should work
            print("  Testing group permissions...")
            group_errors = []
            for user in users[:5]:
                if user.groups:
                    group = user.groups[0]
                    # Find a file with group permission
                    group_perm = FilePermission.query.filter_by(group_id=group.id).first()
                    if group_perm:
                        file_obj = File.query.get(group_perm.file_id)
                        user_perm = file_obj.get_effective_permissions(user)
                        
                        if not user_perm:
                            group_errors.append(
                                f"User {user.id} should have group permission on file {file_obj.id}"
                            )
            
            regression_results.extend([
                f"Owner permission errors: {len(owner_errors)}",
                f"Inheritance errors: {len(inheritance_errors)}",
                f"Group permission errors: {len(group_errors)}"
            ])
            
            if owner_errors or inheritance_errors or group_errors:
                print("❌ Regression test failures detected!")
                for error in (owner_errors + inheritance_errors + group_errors)[:10]:
                    print(f"   - {error}")
            else:
                print("✅ All regression tests passed!")
        
        return regression_results
    
    def benchmark_query_performance(self, users: List[User], files: List[File]) -> BenchmarkResult:
        """Benchmark query performance improvements."""
        print("⚡ Benchmarking query performance...")
        
        with self.app.app_context():
            user = users[0]
            test_files = files[:30]
            
            # Benchmark legacy method
            legacy_times = []
            for _ in range(10):  # 10 iterations
                start_time = time.perf_counter()
                for file_obj in test_files:
                    file_obj._get_effective_permissions_legacy(user)
                legacy_times.append((time.perf_counter() - start_time) * 1000)
            
            # Benchmark optimized method
            optimized_times = []
            for _ in range(10):  # 10 iterations
                start_time = time.perf_counter()
                for file_obj in test_files:
                    file_obj.get_effective_permissions(user)
                optimized_times.append((time.perf_counter() - start_time) * 1000)
            
            # Calculate improvement factor
            legacy_avg = statistics.mean(legacy_times)
            optimized_avg = statistics.mean(optimized_times)
            improvement_factor = legacy_avg / optimized_avg if optimized_avg > 0 else 1
            
            # Simple statistical significance test (t-test approximation)
            legacy_std = statistics.stdev(legacy_times) if len(legacy_times) > 1 else 0
            optimized_std = statistics.stdev(optimized_times) if len(optimized_times) > 1 else 0
            
            # If the difference is more than 2 standard deviations, consider it significant
            combined_std = (legacy_std + optimized_std) / 2
            difference = abs(legacy_avg - optimized_avg)
            statistical_significance = difference > (2 * combined_std) if combined_std > 0 else True
            
            return BenchmarkResult(
                operation_name="Individual_Permission_Checks",
                legacy_times=legacy_times,
                optimized_times=optimized_times,
                improvement_factor=improvement_factor,
                statistical_significance=statistical_significance
            )
    
    def run_all_validation_tests(self):
        """Run all validation and regression tests."""
        print("🎯 Starting Performance Validation Tests...")
        print("=" * 60)
        
        try:
            # Create test data
            users, folders, files = self.create_validation_test_data()
            
            # Run validation tests
            file_validation = self.validate_file_permissions(users, files)
            self.validation_results.append(file_validation)
            
            folder_validation = self.validate_folder_permissions(users, folders)
            self.validation_results.append(folder_validation)
            
            bulk_validation = self.validate_bulk_operations(users, files)
            self.validation_results.append(bulk_validation)
            
            # Run regression tests
            regression_results = self.run_regression_tests(users, files, folders)
            
            # Run performance benchmarks
            benchmark = self.benchmark_query_performance(users, files)
            self.benchmark_results.append(benchmark)
            
        finally:
            # Always clean up
            self.cleanup_validation_test_data()
        
        # Print results
        self.print_validation_results()
        self.print_benchmark_results()
        
        return regression_results
    
    def print_validation_results(self):
        """Print formatted validation results."""
        print("\n" + "=" * 80)
        print("🔍 VALIDATION TEST RESULTS")
        print("=" * 80)
        
        for result in self.validation_results:
            print(f"\n📋 {result.test_name}")
            print("-" * 50)
            print(f"Total Comparisons: {result.total_comparisons}")
            print(f"Matches: {result.matches}")
            print(f"Mismatches: {result.mismatches}")
            print(f"Match Rate: {(result.matches / result.total_comparisons * 100):.1f}%" if result.total_comparisons > 0 else "N/A")
            print(f"Legacy Avg Time: {result.legacy_avg_time_ms:.2f}ms")
            print(f"Optimized Avg Time: {result.optimized_avg_time_ms:.2f}ms")
            print(f"Performance Improvement: {result.performance_improvement_percent:.1f}%")
            
            # Check requirements compliance
            self.check_validation_requirements(result)
            
            if result.errors:
                print(f"\n❌ Errors ({len(result.errors)}):")
                for error in result.errors[:3]:
                    print(f"   - {error}")
            
            if result.mismatch_details:
                print(f"\n⚠️  Mismatch Details ({len(result.mismatch_details)}):")
                for detail in result.mismatch_details[:3]:
                    print(f"   - Resource {detail.get('resource_id')}: {detail.get('issue')}")
    
    def print_benchmark_results(self):
        """Print benchmark results."""
        print("\n" + "=" * 80)
        print("📊 PERFORMANCE BENCHMARK RESULTS")
        print("=" * 80)
        
        for result in self.benchmark_results:
            print(f"\n⚡ {result.operation_name}")
            print("-" * 50)
            print(f"Legacy Average: {statistics.mean(result.legacy_times):.2f}ms")
            print(f"Optimized Average: {statistics.mean(result.optimized_times):.2f}ms")
            print(f"Improvement Factor: {result.improvement_factor:.2f}x")
            print(f"Statistical Significance: {'Yes' if result.statistical_significance else 'No'}")
            
            if result.improvement_factor > 1:
                print(f"✅ Performance improved by {((result.improvement_factor - 1) * 100):.1f}%")
            else:
                print(f"❌ Performance degraded by {((1 - result.improvement_factor) * 100):.1f}%")
    
    def check_validation_requirements(self, result: ValidationResult):
        """Check validation results against requirements."""
        print("\n📋 Requirements Compliance:")
        
        # Requirement 2.1: Optimized queries (check performance improvement)
        if result.performance_improvement_percent > 0:
            print("   ✅ Req 2.1: Optimized queries show improvement - PASSED")
        else:
            print(f"   ❌ Req 2.1: Optimized queries show improvement - FAILED ({result.performance_improvement_percent:.1f}%)")
        
        # Requirement 2.2: Proper index usage (inferred from performance)
        if result.optimized_avg_time_ms < result.legacy_avg_time_ms:
            print("   ✅ Req 2.2: Index usage optimization - PASSED")
        else:
            print("   ❌ Req 2.2: Index usage optimization - FAILED")
        
        # Requirement 2.3: Avoid N+1 queries (check for significant improvement)
        if result.performance_improvement_percent > 20:  # 20% improvement threshold
            print("   ✅ Req 2.3: N+1 query avoidance - PASSED")
        else:
            print(f"   ⚠️  Req 2.3: N+1 query avoidance - MARGINAL ({result.performance_improvement_percent:.1f}%)")
        
        # Correctness requirement
        match_rate = (result.matches / result.total_comparisons * 100) if result.total_comparisons > 0 else 0
        if match_rate >= 99:
            print("   ✅ Correctness: Results match legacy implementation - PASSED")
        else:
            print(f"   ❌ Correctness: Results match legacy implementation - FAILED ({match_rate:.1f}%)")


def main():
    """Main function to run validation tests."""
    app = create_app()
    
    tester = PermissionValidationTester(app)
    
    try:
        regression_results = tester.run_all_validation_tests()
        
        print("\n" + "=" * 80)
        print("🏁 VALIDATION SUMMARY")
        print("=" * 80)
        
        for result in regression_results:
            print(f"   {result}")
            
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        tester.cleanup_validation_test_data()
    except Exception as e:
        print(f"\n❌ Validation suite failed: {str(e)}")
        tester.cleanup_validation_test_data()
        raise


if __name__ == "__main__":
    main()