import time
import logging
from functools import wraps
from typing import Callable, Any, Dict, Optional
from datetime import datetime
import os

# Performance thresholds configuration
PERFORMANCE_CONFIG = {
    'SLOW_QUERY_THRESHOLD_MS': float(os.getenv('SLOW_QUERY_THRESHOLD_MS', '100')),
    'PERMISSION_QUERY_THRESHOLD_MS': float(os.getenv('PERMISSION_QUERY_THRESHOLD_MS', '50')),
    'BULK_OPERATION_THRESHOLD_MS': float(os.getenv('BULK_OPERATION_THRESHOLD_MS', '200')),
    'ENABLE_DEBUG_LOGGING': os.getenv('ENABLE_PERFORMANCE_DEBUG', 'false').lower() == 'true'
}

# Configure performance logger
performance_logger = logging.getLogger('performance')
performance_logger.setLevel(logging.DEBUG if PERFORMANCE_CONFIG['ENABLE_DEBUG_LOGGING'] else logging.INFO)

# Configure permission-specific logger
permission_logger = logging.getLogger('performance.permissions')
permission_logger.setLevel(logging.INFO)

# Create handlers if not exist
if not performance_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    performance_logger.addHandler(handler)

if not permission_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - PERMISSION_PERF - %(message)s'
    )
    handler.setFormatter(formatter)
    permission_logger.addHandler(handler)


def performance_monitor(operation_name: str = None, 
                      log_threshold_ms: Optional[float] = None,
                      operation_type: str = "general"):
    """
    Decorator to monitor and log performance of database operations.
    
    Args:
        operation_name: Name of the operation being monitored
        log_threshold_ms: Threshold in milliseconds above which to log performance
        operation_type: Type of operation ('permission', 'query', 'bulk', 'general')
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            
            # Determine threshold based on operation type
            if log_threshold_ms is None:
                if operation_type == "permission":
                    threshold = PERFORMANCE_CONFIG['PERMISSION_QUERY_THRESHOLD_MS']
                elif operation_type == "bulk":
                    threshold = PERFORMANCE_CONFIG['BULK_OPERATION_THRESHOLD_MS']
                else:
                    threshold = PERFORMANCE_CONFIG['SLOW_QUERY_THRESHOLD_MS']
            else:
                threshold = log_threshold_ms
            
            try:
                result = func(*args, **kwargs)
                
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                op_name = operation_name or f"{func.__module__}.{func.__name__}"
                
                # Choose appropriate logger
                logger = permission_logger if operation_type == "permission" else performance_logger
                
                # Log if above threshold
                if duration_ms >= threshold:
                    logger.warning(
                        f"SLOW_{operation_type.upper()} - {op_name} took {duration_ms:.2f}ms "
                        f"(threshold: {threshold}ms) - args: {len(args)}, kwargs: {list(kwargs.keys())}"
                    )
                elif PERFORMANCE_CONFIG['ENABLE_DEBUG_LOGGING']:
                    logger.debug(
                        f"{op_name} took {duration_ms:.2f}ms (threshold: {threshold}ms)"
                    )
                
                return result
                
            except Exception as e:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                op_name = operation_name or f"{func.__module__}.{func.__name__}"
                logger = permission_logger if operation_type == "permission" else performance_logger
                logger.error(
                    f"ERROR - {op_name} failed after {duration_ms:.2f}ms - {str(e)}"
                )
                raise
                
        return wrapper
    return decorator


class PerformanceTracker:
    """Context manager for tracking performance of code blocks."""
    
    def __init__(self, operation_name: str, log_threshold_ms: float = 50.0):
        self.operation_name = operation_name
        self.log_threshold_ms = log_threshold_ms
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        if exc_type is not None:
            performance_logger.error(
                f"ERROR - {self.operation_name} failed after {duration_ms:.2f}ms - {str(exc_val)}"
            )
        elif duration_ms >= self.log_threshold_ms:
            performance_logger.info(
                f"SLOW_OPERATION - {self.operation_name} took {duration_ms:.2f}ms "
                f"(threshold: {self.log_threshold_ms}ms)"
            )
        else:
            performance_logger.debug(
                f"{self.operation_name} took {duration_ms:.2f}ms"
            )
    
    @property
    def duration_ms(self) -> float:
        """Get the duration in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


def log_permission_query_stats(user_id: int, resource_type: str, resource_count: int, 
                              duration_ms: float, method: str = "optimized", 
                              cache_hit: bool = False, query_type: str = "single"):
    """
    Log statistics about permission queries for analysis.
    
    Args:
        user_id: ID of the user
        resource_type: Type of resource ('file' or 'folder')
        resource_count: Number of resources queried
        duration_ms: Duration of the query in milliseconds
        method: Method used ('optimized' or 'legacy')
        cache_hit: Whether the query hit cache
        query_type: Type of query ('single', 'bulk', 'tree')
    """
    threshold = PERFORMANCE_CONFIG['PERMISSION_QUERY_THRESHOLD_MS']
    cache_status = "HIT" if cache_hit else "MISS"
    
    log_message = (
        f"PERMISSION_QUERY - user_id: {user_id}, type: {resource_type}, "
        f"count: {resource_count}, duration: {duration_ms:.2f}ms, "
        f"method: {method}, cache: {cache_status}, query_type: {query_type}"
    )
    
    if duration_ms >= threshold:
        permission_logger.warning(f"SLOW - {log_message}")
    else:
        permission_logger.info(log_message)


def log_permission_cache_stats(operation: str, user_id: int, resource_type: str, 
                              hit_count: int, miss_count: int, duration_ms: float):
    """
    Log permission cache statistics.
    
    Args:
        operation: Cache operation ('lookup', 'invalidate', 'warm')
        user_id: ID of the user
        resource_type: Type of resource
        hit_count: Number of cache hits
        miss_count: Number of cache misses
        duration_ms: Duration of the operation
    """
    total_requests = hit_count + miss_count
    hit_rate = (hit_count / total_requests * 100) if total_requests > 0 else 0
    
    permission_logger.info(
        f"CACHE_{operation.upper()} - user_id: {user_id}, type: {resource_type}, "
        f"hits: {hit_count}, misses: {miss_count}, hit_rate: {hit_rate:.1f}%, "
        f"duration: {duration_ms:.2f}ms"
    )


def log_bulk_permission_query(user_id: int, resource_type: str, resource_ids: list,
                             duration_ms: float, method: str = "bulk_optimized"):
    """
    Log bulk permission query performance.
    
    Args:
        user_id: ID of the user
        resource_type: Type of resource
        resource_ids: List of resource IDs queried
        duration_ms: Duration of the query
        method: Method used for bulk query
    """
    resource_count = len(resource_ids)
    avg_per_resource = duration_ms / resource_count if resource_count > 0 else 0
    threshold = PERFORMANCE_CONFIG['BULK_OPERATION_THRESHOLD_MS']
    
    log_message = (
        f"BULK_PERMISSION_QUERY - user_id: {user_id}, type: {resource_type}, "
        f"count: {resource_count}, total_duration: {duration_ms:.2f}ms, "
        f"avg_per_resource: {avg_per_resource:.2f}ms, method: {method}"
    )
    
    if duration_ms >= threshold:
        permission_logger.warning(f"SLOW - {log_message}")
    else:
        permission_logger.info(log_message)


def compare_performance(legacy_duration_ms: float, optimized_duration_ms: float, 
                       operation: str, resource_count: int = 1):
    """
    Log performance comparison between legacy and optimized methods.
    
    Args:
        legacy_duration_ms: Duration of legacy method
        optimized_duration_ms: Duration of optimized method
        operation: Name of the operation
        resource_count: Number of resources processed
    """
    improvement_ratio = legacy_duration_ms / optimized_duration_ms if optimized_duration_ms > 0 else 0
    improvement_percent = ((legacy_duration_ms - optimized_duration_ms) / legacy_duration_ms * 100) if legacy_duration_ms > 0 else 0
    
    performance_logger.info(
        f"PERFORMANCE_COMPARISON - {operation} - "
        f"legacy: {legacy_duration_ms:.2f}ms, optimized: {optimized_duration_ms:.2f}ms, "
        f"improvement: {improvement_percent:.1f}% ({improvement_ratio:.1f}x faster), "
        f"resources: {resource_count}"
    )

# Import performance metrics service
try:
    from backend.services.performance_metrics import get_performance_metrics, MetricType
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


def metrics_monitor(operation_name: str = None, 
                   metric_type: str = "general",
                   log_threshold_ms: Optional[float] = None):
    """
    Decorator that combines performance logging with metrics collection.
    
    Args:
        operation_name: Name of the operation being monitored
        metric_type: Type of metric ('permission', 'query', 'bulk', 'general')
        log_threshold_ms: Threshold in milliseconds above which to log performance
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            
            # Determine threshold based on operation type
            if log_threshold_ms is None:
                if metric_type == "permission":
                    threshold = PERFORMANCE_CONFIG['PERMISSION_QUERY_THRESHOLD_MS']
                elif metric_type == "bulk":
                    threshold = PERFORMANCE_CONFIG['BULK_OPERATION_THRESHOLD_MS']
                else:
                    threshold = PERFORMANCE_CONFIG['SLOW_QUERY_THRESHOLD_MS']
            else:
                threshold = log_threshold_ms
            
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            try:
                result = func(*args, **kwargs)
                
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                # Record metrics if available
                if METRICS_AVAILABLE:
                    metrics = get_performance_metrics()
                    
                    # Determine metric type enum
                    if metric_type == "permission":
                        mt = MetricType.PERMISSION_CHECK
                    elif metric_type == "bulk":
                        mt = MetricType.BULK_OPERATION
                    elif metric_type == "query":
                        mt = MetricType.DATABASE_QUERY
                    else:
                        mt = MetricType.API_REQUEST
                    
                    # Extract user_id from args/kwargs if available
                    user_id = None
                    if args and hasattr(args[0], 'id'):
                        user_id = args[0].id
                    elif 'user_id' in kwargs:
                        user_id = kwargs['user_id']
                    
                    metrics.record_metric(
                        metric_type=mt,
                        operation=op_name,
                        duration_ms=duration_ms,
                        user_id=user_id,
                        metadata={'threshold_ms': threshold}
                    )
                
                # Choose appropriate logger
                logger = permission_logger if metric_type == "permission" else performance_logger
                
                # Log if above threshold
                if duration_ms >= threshold:
                    logger.warning(
                        f"SLOW_{metric_type.upper()} - {op_name} took {duration_ms:.2f}ms "
                        f"(threshold: {threshold}ms) - args: {len(args)}, kwargs: {list(kwargs.keys())}"
                    )
                elif PERFORMANCE_CONFIG['ENABLE_DEBUG_LOGGING']:
                    logger.debug(
                        f"{op_name} took {duration_ms:.2f}ms (threshold: {threshold}ms)"
                    )
                
                return result
                
            except Exception as e:
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000
                
                # Record error metric
                if METRICS_AVAILABLE:
                    metrics = get_performance_metrics()
                    metrics.record_metric(
                        metric_type=MetricType.API_REQUEST,
                        operation=f"{op_name}_ERROR",
                        duration_ms=duration_ms,
                        metadata={'error': str(e), 'threshold_ms': threshold}
                    )
                
                logger = permission_logger if metric_type == "permission" else performance_logger
                logger.error(
                    f"ERROR - {op_name} failed after {duration_ms:.2f}ms - {str(e)}"
                )
                raise
                
        return wrapper
    return decorator


class MetricsTracker:
    """Context manager for tracking performance metrics of code blocks."""
    
    def __init__(self, operation_name: str, metric_type: str = "general", 
                 user_id: Optional[int] = None, resource_type: Optional[str] = None,
                 resource_count: int = 1):
        self.operation_name = operation_name
        self.metric_type = metric_type
        self.user_id = user_id
        self.resource_type = resource_type
        self.resource_count = resource_count
        self.start_time = None
        self.end_time = None
        self.duration_ms = 0.0
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        
        # Record metrics if available
        if METRICS_AVAILABLE:
            metrics = get_performance_metrics()
            
            # Determine metric type enum
            if self.metric_type == "permission":
                mt = MetricType.PERMISSION_CHECK
            elif self.metric_type == "bulk":
                mt = MetricType.BULK_OPERATION
            elif self.metric_type == "query":
                mt = MetricType.DATABASE_QUERY
            else:
                mt = MetricType.API_REQUEST
            
            metadata = {'resource_count': self.resource_count}
            if exc_type is not None:
                metadata['error'] = str(exc_val)
            
            metrics.record_metric(
                metric_type=mt,
                operation=self.operation_name,
                duration_ms=self.duration_ms,
                user_id=self.user_id,
                resource_type=self.resource_type,
                resource_count=self.resource_count,
                **metadata
            )
        
        # Log performance
        threshold = PERFORMANCE_CONFIG.get('PERMISSION_QUERY_THRESHOLD_MS', 50.0)
        if self.metric_type == "permission":
            logger = permission_logger
        else:
            logger = performance_logger
            threshold = PERFORMANCE_CONFIG.get('SLOW_QUERY_THRESHOLD_MS', 100.0)
        
        if exc_type is not None:
            logger.error(
                f"ERROR - {self.operation_name} failed after {self.duration_ms:.2f}ms - {str(exc_val)}"
            )
        elif self.duration_ms >= threshold:
            logger.warning(
                f"SLOW_{self.metric_type.upper()} - {self.operation_name} took {self.duration_ms:.2f}ms "
                f"(threshold: {threshold}ms)"
            )
        elif PERFORMANCE_CONFIG.get('ENABLE_DEBUG_LOGGING', False):
            logger.debug(
                f"{self.operation_name} took {self.duration_ms:.2f}ms"
            )