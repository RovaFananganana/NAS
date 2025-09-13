"""
Performance Metrics Collection Service

This service collects and aggregates performance metrics for database queries,
permission checks, cache operations, and other system operations.
"""

import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import json
import os


class MetricType(Enum):
    """Types of metrics collected."""
    PERMISSION_CHECK = "permission_check"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    DATABASE_QUERY = "database_query"
    BULK_OPERATION = "bulk_operation"
    API_REQUEST = "api_request"


@dataclass
class MetricEntry:
    """Individual metric entry."""
    timestamp: datetime
    metric_type: MetricType
    operation: str
    duration_ms: float
    user_id: Optional[int] = None
    resource_type: Optional[str] = None
    resource_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregatedMetrics:
    """Aggregated metrics for a time period."""
    total_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    
    def update(self, duration_ms: float):
        """Update aggregated metrics with new duration."""
        self.total_count += 1
        self.total_duration_ms += duration_ms
        self.avg_duration_ms = self.total_duration_ms / self.total_count
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)


class PerformanceMetrics:
    """
    Service for collecting and analyzing performance metrics.
    
    This service provides:
    - Real-time metric collection
    - Aggregated statistics
    - Export capabilities for external monitoring
    - Cache hit/miss tracking
    - Query performance analysis
    """
    
    def __init__(self, max_entries: int = 10000, aggregation_window_minutes: int = 5):
        self.max_entries = max_entries
        self.aggregation_window = timedelta(minutes=aggregation_window_minutes)
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self._metrics: deque = deque(maxlen=max_entries)
        
        # Aggregated metrics by operation and time window
        self._aggregated_metrics: Dict[str, Dict[datetime, AggregatedMetrics]] = defaultdict(
            lambda: defaultdict(AggregatedMetrics)
        )
        
        # Cache statistics
        self._cache_stats = {
            'permission_cache': {'hits': 0, 'misses': 0, 'total_requests': 0},
            'metadata_cache': {'hits': 0, 'misses': 0, 'total_requests': 0}
        }
        
        # Performance counters
        self._counters = defaultdict(int)
        
        # Recent durations for percentile calculations
        self._recent_durations: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
    
    def record_metric(self, metric_type: MetricType, operation: str, duration_ms: float,
                     user_id: Optional[int] = None, resource_type: Optional[str] = None,
                     resource_count: int = 1, **metadata):
        """
        Record a performance metric.
        
        Args:
            metric_type: Type of metric
            operation: Name of the operation
            duration_ms: Duration in milliseconds
            user_id: User ID if applicable
            resource_type: Type of resource if applicable
            resource_count: Number of resources processed
            **metadata: Additional metadata
        """
        with self._lock:
            timestamp = datetime.utcnow()
            
            # Create metric entry
            entry = MetricEntry(
                timestamp=timestamp,
                metric_type=metric_type,
                operation=operation,
                duration_ms=duration_ms,
                user_id=user_id,
                resource_type=resource_type,
                resource_count=resource_count,
                metadata=metadata
            )
            
            # Store metric
            self._metrics.append(entry)
            
            # Update aggregated metrics
            window_key = self._get_window_key(timestamp)
            self._aggregated_metrics[operation][window_key].update(duration_ms)
            
            # Update recent durations for percentiles
            self._recent_durations[operation].append(duration_ms)
            
            # Update counters
            self._counters[f"{metric_type.value}_count"] += 1
            self._counters[f"{operation}_count"] += 1
    
    def record_permission_check(self, operation: str, duration_ms: float, user_id: int,
                              resource_type: str, resource_count: int = 1, 
                              cache_hit: bool = False, **metadata):
        """Record a permission check metric."""
        metadata.update({
            'cache_hit': cache_hit
        })
        
        self.record_metric(
            MetricType.PERMISSION_CHECK,
            operation,
            duration_ms,
            user_id=user_id,
            resource_type=resource_type,
            resource_count=resource_count,
            **metadata
        )
        
        # Update cache statistics
        if cache_hit:
            self.record_cache_hit('permission_cache')
        else:
            self.record_cache_miss('permission_cache')
    
    def record_cache_hit(self, cache_type: str = 'permission_cache'):
        """Record a cache hit."""
        with self._lock:
            self._cache_stats[cache_type]['hits'] += 1
            self._cache_stats[cache_type]['total_requests'] += 1
            self._counters[f"{cache_type}_hits"] += 1
    
    def record_cache_miss(self, cache_type: str = 'permission_cache'):
        """Record a cache miss."""
        with self._lock:
            self._cache_stats[cache_type]['misses'] += 1
            self._cache_stats[cache_type]['total_requests'] += 1
            self._counters[f"{cache_type}_misses"] += 1
    
    def record_database_query(self, query_type: str, duration_ms: float, 
                            table_name: Optional[str] = None, **metadata):
        """Record a database query metric."""
        metadata.update({'table_name': table_name})
        
        self.record_metric(
            MetricType.DATABASE_QUERY,
            query_type,
            duration_ms,
            **metadata
        )
    
    def get_cache_statistics(self, cache_type: str = 'permission_cache') -> Dict[str, Any]:
        """Get cache hit/miss statistics."""
        with self._lock:
            stats = self._cache_stats.get(cache_type, {})
            total = stats.get('total_requests', 0)
            hits = stats.get('hits', 0)
            misses = stats.get('misses', 0)
            
            return {
                'cache_type': cache_type,
                'total_requests': total,
                'hits': hits,
                'misses': misses,
                'hit_rate': (hits / total * 100) if total > 0 else 0.0,
                'miss_rate': (misses / total * 100) if total > 0 else 0.0
            }
    
    def get_operation_statistics(self, operation: str, 
                               time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get statistics for a specific operation."""
        with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
            
            # Filter recent metrics for this operation
            recent_metrics = [
                m for m in self._metrics 
                if m.operation == operation and m.timestamp >= cutoff_time
            ]
            
            if not recent_metrics:
                return {
                    'operation': operation,
                    'count': 0,
                    'avg_duration_ms': 0.0,
                    'min_duration_ms': 0.0,
                    'max_duration_ms': 0.0,
                    'p95_duration_ms': 0.0,
                    'p99_duration_ms': 0.0
                }
            
            durations = [m.duration_ms for m in recent_metrics]
            durations.sort()
            
            count = len(durations)
            p95_index = int(count * 0.95)
            p99_index = int(count * 0.99)
            
            return {
                'operation': operation,
                'count': count,
                'avg_duration_ms': sum(durations) / count,
                'min_duration_ms': min(durations),
                'max_duration_ms': max(durations),
                'p95_duration_ms': durations[p95_index] if p95_index < count else durations[-1],
                'p99_duration_ms': durations[p99_index] if p99_index < count else durations[-1],
                'time_window_minutes': time_window_minutes
            }
    
    def get_slow_operations(self, threshold_ms: float = 100.0, 
                          time_window_minutes: int = 60) -> List[Dict[str, Any]]:
        """Get operations that exceeded the threshold."""
        with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
            
            slow_operations = [
                {
                    'timestamp': m.timestamp.isoformat(),
                    'operation': m.operation,
                    'duration_ms': m.duration_ms,
                    'metric_type': m.metric_type.value,
                    'user_id': m.user_id,
                    'resource_type': m.resource_type,
                    'resource_count': m.resource_count,
                    'metadata': m.metadata
                }
                for m in self._metrics
                if m.timestamp >= cutoff_time and m.duration_ms >= threshold_ms
            ]
            
            # Sort by duration descending
            slow_operations.sort(key=lambda x: x['duration_ms'], reverse=True)
            
            return slow_operations
    
    def export_metrics(self, format_type: str = 'json', 
                      time_window_minutes: int = 60) -> str:
        """
        Export metrics in specified format for external monitoring systems.
        
        Args:
            format_type: Export format ('json', 'prometheus')
            time_window_minutes: Time window for metrics
            
        Returns:
            Formatted metrics string
        """
        if format_type == 'json':
            return self._export_json(time_window_minutes)
        elif format_type == 'prometheus':
            return self._export_prometheus(time_window_minutes)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def _export_json(self, time_window_minutes: int) -> str:
        """Export metrics as JSON."""
        with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
            
            # Get unique operations
            operations = set(m.operation for m in self._metrics if m.timestamp >= cutoff_time)
            
            export_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'time_window_minutes': time_window_minutes,
                'cache_statistics': {
                    cache_type: self.get_cache_statistics(cache_type)
                    for cache_type in self._cache_stats.keys()
                },
                'operation_statistics': {
                    op: self.get_operation_statistics(op, time_window_minutes)
                    for op in operations
                },
                'counters': dict(self._counters),
                'slow_operations': self.get_slow_operations(100.0, time_window_minutes)
            }
            
            return json.dumps(export_data, indent=2)
    
    def _export_prometheus(self, time_window_minutes: int) -> str:
        """Export metrics in Prometheus format."""
        lines = []
        timestamp = int(time.time() * 1000)
        
        with self._lock:
            # Cache hit rates
            for cache_type, stats in self._cache_stats.items():
                total = stats.get('total_requests', 0)
                hits = stats.get('hits', 0)
                hit_rate = (hits / total) if total > 0 else 0.0
                
                lines.append(f'cache_hit_rate{{cache_type="{cache_type}"}} {hit_rate} {timestamp}')
                lines.append(f'cache_total_requests{{cache_type="{cache_type}"}} {total} {timestamp}')
            
            # Operation metrics
            cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
            operations = set(m.operation for m in self._metrics if m.timestamp >= cutoff_time)
            
            for operation in operations:
                stats = self.get_operation_statistics(operation, time_window_minutes)
                lines.append(f'operation_avg_duration_ms{{operation="{operation}"}} {stats["avg_duration_ms"]} {timestamp}')
                lines.append(f'operation_count{{operation="{operation}"}} {stats["count"]} {timestamp}')
                lines.append(f'operation_p95_duration_ms{{operation="{operation}"}} {stats["p95_duration_ms"]} {timestamp}')
        
        return '\n'.join(lines)
    
    def _get_window_key(self, timestamp: datetime) -> datetime:
        """Get the aggregation window key for a timestamp."""
        minutes = (timestamp.minute // self.aggregation_window.seconds) * self.aggregation_window.seconds
        return timestamp.replace(minute=minutes, second=0, microsecond=0)
    
    def cleanup_old_metrics(self, max_age_hours: int = 24):
        """Clean up old metrics to prevent memory bloat."""
        with self._lock:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            # Clean up raw metrics (deque handles this automatically with maxlen)
            
            # Clean up aggregated metrics
            for operation in list(self._aggregated_metrics.keys()):
                windows_to_remove = [
                    window for window in self._aggregated_metrics[operation].keys()
                    if window < cutoff_time
                ]
                for window in windows_to_remove:
                    del self._aggregated_metrics[operation][window]
                
                # Remove empty operations
                if not self._aggregated_metrics[operation]:
                    del self._aggregated_metrics[operation]


# Global instance
performance_metrics = PerformanceMetrics()


def get_performance_metrics() -> PerformanceMetrics:
    """Get the global performance metrics instance."""
    return performance_metrics