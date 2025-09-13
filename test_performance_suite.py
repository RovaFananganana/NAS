#!/usr/bin/env python3
"""
Comprehensive Performance Testing Suite Runner
Orchestrates load testing and validation testing for database optimization.

This script runs both load tests and validation tests, providing a complete
performance testing suite for the database optimization implementation.
"""

import sys
import os
import argparse
import time
from datetime import datetime

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from test_performance_load import PermissionLoadTester
from test_performance_validation import PermissionValidationTester


class PerformanceTestSuite:
    """Main test suite orchestrator."""
    
    def __init__(self):
        self.app = create_app()
        self.load_tester = PermissionLoadTester(self.app)
        self.validation_tester = PermissionValidationTester(self.app)
        
    def run_quick_test(self):
        """Run a quick subset of tests for development."""
        print("🚀 Running Quick Performance Test Suite...")
        print("=" * 60)
        
        start_time = time.time()
        
        try:
            # Quick validation test
            print("\n1️⃣  Quick Validation Tests")
            users, folders, files = self.validation_tester.create_validation_test_data()
            
            # Run just file validation
            file_validation = self.validation_tester.validate_file_permissions(users[:5], files[:20])
            self.validation_tester.validation_results.append(file_validation)
            
            # Quick benchmark
            benchmark = self.validation_tester.benchmark_query_performance(users[:3], files[:10])
            self.validation_tester.benchmark_results.append(benchmark)
            
            self.validation_tester.cleanup_validation_test_data()
            
            # Quick load test
            print("\n2️⃣  Quick Load Test")
            test_users, test_folders, test_files = self.load_tester.create_test_data(
                num_users=20, num_folders=100, num_files=500, max_depth=5
            )
            
            # Single concurrent test
            result = self.load_tester.run_concurrent_permission_test(
                concurrent_users=10,
                operations_per_user=10,
                test_users=test_users,
                files=test_files,
                folders=test_folders
            )
            self.load_tester.results.append(result)
            
            self.load_tester.cleanup_test_data()
            
        except Exception as e:
            print(f"❌ Quick test failed: {str(e)}")
            # Cleanup on error
            try:
                self.validation_tester.cleanup_validation_test_data()
                self.load_tester.cleanup_test_data()
            except:
                pass
            raise
        
        end_time = time.time()
        
        # Print results
        self.validation_tester.print_validation_results()
        self.validation_tester.print_benchmark_results()
        self.load_tester.print_results()
        
        print(f"\n⏱️  Quick test completed in {end_time - start_time:.2f} seconds")
    
    def run_full_test_suite(self):
        """Run the complete test suite."""
        print("🎯 Running Full Performance Test Suite...")
        print("=" * 60)
        
        start_time = time.time()
        
        try:
            # Full validation tests
            print("\n1️⃣  Validation & Regression Tests")
            self.validation_tester.run_all_validation_tests()
            
            print("\n2️⃣  Load & Performance Tests")  
            self.load_tester.run_all_load_tests()
            
        except Exception as e:
            print(f"❌ Full test suite failed: {str(e)}")
            raise
        
        end_time = time.time()
        
        # Generate summary report
        self.generate_summary_report(end_time - start_time)
    
    def run_load_tests_only(self):
        """Run only load tests."""
        print("⚡ Running Load Tests Only...")
        self.load_tester.run_all_load_tests()
    
    def run_validation_tests_only(self):
        """Run only validation tests."""
        print("🔍 Running Validation Tests Only...")
        self.validation_tester.run_all_validation_tests()
    
    def generate_summary_report(self, total_duration: float):
        """Generate a comprehensive summary report."""
        print("\n" + "=" * 80)
        print("📋 COMPREHENSIVE TEST SUITE SUMMARY")
        print("=" * 80)
        
        print(f"Total Test Duration: {total_duration:.2f} seconds")
        print(f"Test Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Validation summary
        if self.validation_tester.validation_results:
            print("\n🔍 Validation Results Summary:")
            total_comparisons = sum(r.total_comparisons for r in self.validation_tester.validation_results)
            total_matches = sum(r.matches for r in self.validation_tester.validation_results)
            total_mismatches = sum(r.mismatches for r in self.validation_tester.validation_results)
            
            print(f"   Total Comparisons: {total_comparisons}")
            print(f"   Total Matches: {total_matches}")
            print(f"   Total Mismatches: {total_mismatches}")
            print(f"   Overall Match Rate: {(total_matches / total_comparisons * 100):.1f}%" if total_comparisons > 0 else "N/A")
            
            avg_improvement = sum(r.performance_improvement_percent for r in self.validation_tester.validation_results) / len(self.validation_tester.validation_results)
            print(f"   Average Performance Improvement: {avg_improvement:.1f}%")
        
        # Load test summary
        if self.load_tester.results:
            print("\n⚡ Load Test Results Summary:")
            total_operations = sum(r.total_operations for r in self.load_tester.results)
            avg_response_time = sum(r.avg_response_time_ms for r in self.load_tester.results) / len(self.load_tester.results)
            avg_success_rate = sum(r.success_rate for r in self.load_tester.results) / len(self.load_tester.results)
            
            print(f"   Total Operations Tested: {total_operations}")
            print(f"   Average Response Time: {avg_response_time:.2f}ms")
            print(f"   Average Success Rate: {avg_success_rate:.1%}")
        
        # Requirements compliance summary
        print("\n📋 Requirements Compliance Summary:")
        self.check_overall_compliance()
        
        # Recommendations
        print("\n💡 Recommendations:")
        self.generate_recommendations()
    
    def check_overall_compliance(self):
        """Check overall compliance with requirements."""
        
        # Check load test results against requirements
        if self.load_tester.results:
            folder_access_compliant = any(
                r.avg_response_time_ms < 200 for r in self.load_tester.results 
                if "Concurrent" in r.test_name
            )
            
            permission_check_compliant = any(
                r.avg_response_time_ms < 50 for r in self.load_tester.results
            )
            
            bulk_operation_compliant = any(
                r.avg_response_time_ms < 500 for r in self.load_tester.results
                if "Bulk" in r.test_name
            )
            
            print(f"   Req 1.1 (Folder access < 200ms): {'✅ PASS' if folder_access_compliant else '❌ FAIL'}")
            print(f"   Req 1.2 (Permission checks < 50ms): {'✅ PASS' if permission_check_compliant else '❌ FAIL'}")
            print(f"   Req 1.3 (100+ files < 500ms): {'✅ PASS' if bulk_operation_compliant else '❌ FAIL'}")
        
        # Check validation results against requirements
        if self.validation_tester.validation_results:
            optimization_compliant = all(
                r.performance_improvement_percent > 0 for r in self.validation_tester.validation_results
            )
            
            correctness_compliant = all(
                (r.matches / r.total_comparisons) >= 0.99 for r in self.validation_tester.validation_results
                if r.total_comparisons > 0
            )
            
            print(f"   Req 2.1-2.3 (Query optimization): {'✅ PASS' if optimization_compliant else '❌ FAIL'}")
            print(f"   Correctness (99%+ match rate): {'✅ PASS' if correctness_compliant else '❌ FAIL'}")
    
    def generate_recommendations(self):
        """Generate optimization recommendations based on test results."""
        
        recommendations = []
        
        # Analyze load test results
        if self.load_tester.results:
            slow_operations = [r for r in self.load_tester.results if r.avg_response_time_ms > 100]
            if slow_operations:
                recommendations.append("Consider further index optimization for slow operations")
            
            high_error_rate = [r for r in self.load_tester.results if r.success_rate < 0.95]
            if high_error_rate:
                recommendations.append("Investigate error causes in operations with low success rates")
        
        # Analyze validation results
        if self.validation_tester.validation_results:
            low_improvement = [r for r in self.validation_tester.validation_results if r.performance_improvement_percent < 20]
            if low_improvement:
                recommendations.append("Some operations show minimal improvement - consider additional optimization")
            
            mismatches = [r for r in self.validation_tester.validation_results if r.mismatches > 0]
            if mismatches:
                recommendations.append("Address permission logic mismatches between legacy and optimized methods")
        
        if not recommendations:
            recommendations.append("All tests passed successfully - optimization is working well!")
        
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")


def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(description="Database Optimization Performance Test Suite")
    parser.add_argument(
        "--mode", 
        choices=["quick", "full", "load", "validation"],
        default="quick",
        help="Test mode to run (default: quick)"
    )
    
    args = parser.parse_args()
    
    suite = PerformanceTestSuite()
    
    try:
        if args.mode == "quick":
            suite.run_quick_test()
        elif args.mode == "full":
            suite.run_full_test_suite()
        elif args.mode == "load":
            suite.run_load_tests_only()
        elif args.mode == "validation":
            suite.run_validation_tests_only()
            
        print("\n🎉 Performance test suite completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️  Test suite interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()