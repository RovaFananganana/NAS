"""
Test script for performance metrics functionality.
"""

import time
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.performance_metrics import PerformanceMetrics, MetricType
from utils.performance_logger import metrics_monitor, MetricsTracker


def test_performance_metrics():
    """Test the performance metrics collection."""
    print("Testing Performance Metrics...")
    
    # Create a test metrics instance
    metrics = PerformanceMetrics(max_entries=100)
    
    # Test basic metric recording
    print("\n1. Testing basic metric recording...")
    metrics.record_metric(
        MetricType.PERMISSION_CHECK,
        "test_permission_check",
        45.5,
        user_id=123,
        resource_type="file",
        resource_count=1
    )
    
    metrics.record_metric(
        MetricType.DATABASE_QUERY,
        "test_db_query",
        120.0,
        metadata={"table": "files"}
    )
    
    print(f"Recorded {len(metrics._metrics)} metrics")
    
    # Test cache statistics
    print("\n2. Testing cache statistics...")
    metrics.record_cache_hit('permission_cache')
    metrics.record_cache_hit('permission_cache')
    metrics.record_cache_miss('permission_cache')
    
    cache_stats = metrics.get_cache_statistics('permission_cache')
    print(f"Cache stats: {cache_stats}")
    
    # Test operation statistics
    print("\n3. Testing operation statistics...")
    
    # Record multiple metrics for the same operation
    for i in range(5):
        duration = 50 + (i * 10)  # 50, 60, 70, 80, 90 ms
        metrics.record_permission_check(
            "bulk_permission_check",
            duration,
            user_id=123,
            resource_type="file",
            resource_count=10 + i
        )
    
    op_stats = metrics.get_operation_statistics("bulk_permission_check")
    print(f"Operation stats: {op_stats}")
    
    # Test slow operations detection
    print("\n4. Testing slow operations detection...")
    slow_ops = metrics.get_slow_operations(threshold_ms=60.0)
    print(f"Found {len(slow_ops)} slow operations")
    for op in slow_ops:
        print(f"  - {op['operation']}: {op['duration_ms']:.1f}ms")
    
    # Test export functionality
    print("\n5. Testing export functionality...")
    json_export = metrics.export_metrics('json', time_window_minutes=60)
    print(f"JSON export length: {len(json_export)} characters")
    
    prometheus_export = metrics.export_metrics('prometheus', time_window_minutes=60)
    print(f"Prometheus export lines: {len(prometheus_export.split('\\n'))}")
    
    print("\n✅ Performance metrics tests completed successfully!")


def test_decorators():
    """Test the performance monitoring decorators."""
    print("\nTesting Performance Decorators...")
    
    @metrics_monitor(operation_name="test_function", metric_type="permission")
    def slow_function(delay_ms=100):
        """Simulate a slow function."""
        time.sleep(delay_ms / 1000.0)
        return f"Completed after {delay_ms}ms"
    
    print("\n1. Testing metrics_monitor decorator...")
    result = slow_function(75)
    print(f"Function result: {result}")
    
    print("\n2. Testing MetricsTracker context manager...")
    with MetricsTracker("test_context_operation", "bulk", user_id=456, resource_count=25) as tracker:
        time.sleep(0.05)  # 50ms delay
        print(f"Operation duration: {tracker.duration_ms:.1f}ms")
    
    print("\n✅ Decorator tests completed successfully!")


if __name__ == "__main__":
    try:
        test_performance_metrics()
        test_decorators()
        print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()