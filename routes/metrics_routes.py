"""
Metrics API Routes

Provides endpoints for accessing performance metrics and statistics.
These endpoints are typically used by monitoring systems and administrators.
"""

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.performance_metrics import get_performance_metrics
from utils.performance_logger import metrics_monitor
from models.user import User

metrics_bp = Blueprint('metrics', __name__, url_prefix='/api/metrics')


@metrics_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring systems."""
    return jsonify({
        'status': 'healthy',
        'service': 'performance_metrics',
        'timestamp': get_performance_metrics()._get_window_key(
            get_performance_metrics()._metrics[-1].timestamp if get_performance_metrics()._metrics else None
        ).isoformat() if get_performance_metrics()._metrics else None
    })


@metrics_bp.route('/cache-stats', methods=['GET'])
@jwt_required()
@metrics_monitor(operation_name="get_cache_stats", metric_type="query")
def get_cache_stats():
    """Get cache hit/miss statistics."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    metrics = get_performance_metrics()
    
    cache_type = request.args.get('cache_type', 'permission_cache')
    stats = metrics.get_cache_statistics(cache_type)
    
    return jsonify(stats)


@metrics_bp.route('/operation-stats', methods=['GET'])
@jwt_required()
@metrics_monitor(operation_name="get_operation_stats", metric_type="query")
def get_operation_stats():
    """Get statistics for a specific operation."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    operation = request.args.get('operation')
    if not operation:
        return jsonify({'error': 'operation parameter required'}), 400
    
    time_window = int(request.args.get('time_window_minutes', 60))
    
    metrics = get_performance_metrics()
    stats = metrics.get_operation_statistics(operation, time_window)
    
    return jsonify(stats)


@metrics_bp.route('/slow-operations', methods=['GET'])
@jwt_required()
@metrics_monitor(operation_name="get_slow_operations", metric_type="query")
def get_slow_operations():
    """Get operations that exceeded performance thresholds."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    threshold_ms = float(request.args.get('threshold_ms', 100.0))
    time_window = int(request.args.get('time_window_minutes', 60))
    limit = int(request.args.get('limit', 50))
    
    metrics = get_performance_metrics()
    slow_ops = metrics.get_slow_operations(threshold_ms, time_window)
    
    # Limit results
    if limit > 0:
        slow_ops = slow_ops[:limit]
    
    return jsonify({
        'slow_operations': slow_ops,
        'threshold_ms': threshold_ms,
        'time_window_minutes': time_window,
        'total_count': len(slow_ops)
    })


@metrics_bp.route('/export', methods=['GET'])
@jwt_required()
@metrics_monitor(operation_name="export_metrics", metric_type="query")
def export_metrics():
    """Export metrics in various formats for external monitoring."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    format_type = request.args.get('format', 'json')
    time_window = int(request.args.get('time_window_minutes', 60))
    
    metrics = get_performance_metrics()
    
    try:
        exported_data = metrics.export_metrics(format_type, time_window)
        
        if format_type == 'prometheus':
            return exported_data, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return exported_data, 200, {'Content-Type': 'application/json'}
            
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@metrics_bp.route('/summary', methods=['GET'])
@jwt_required()
@metrics_monitor(operation_name="get_metrics_summary", metric_type="query")
def get_metrics_summary():
    """Get a summary of all performance metrics."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    time_window = int(request.args.get('time_window_minutes', 60))
    
    metrics = get_performance_metrics()
    
    # Get cache stats for all cache types
    cache_stats = {}
    for cache_type in ['permission_cache', 'metadata_cache']:
        cache_stats[cache_type] = metrics.get_cache_statistics(cache_type)
    
    # Get recent operations
    cutoff_time = metrics._get_window_key(
        metrics._metrics[-1].timestamp if metrics._metrics else None
    ) if metrics._metrics else None
    
    recent_operations = set()
    if cutoff_time:
        recent_operations = set(
            m.operation for m in metrics._metrics 
            if m.timestamp >= cutoff_time
        )
    
    # Get stats for top operations
    operation_stats = {}
    for operation in list(recent_operations)[:10]:  # Limit to top 10
        operation_stats[operation] = metrics.get_operation_statistics(operation, time_window)
    
    # Get slow operations
    slow_operations = metrics.get_slow_operations(100.0, time_window)[:10]  # Top 10 slow
    
    return jsonify({
        'summary': {
            'time_window_minutes': time_window,
            'total_metrics_collected': len(metrics._metrics),
            'cache_statistics': cache_stats,
            'operation_statistics': operation_stats,
            'slow_operations_count': len(slow_operations),
            'slow_operations': slow_operations
        }
    })


@metrics_bp.route('/cleanup', methods=['POST'])
@jwt_required()
@metrics_monitor(operation_name="cleanup_metrics", metric_type="query")
def cleanup_metrics():
    """Manually trigger cleanup of old metrics."""
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user or not user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    max_age_hours = int(request.json.get('max_age_hours', 24))
    
    metrics = get_performance_metrics()
    old_count = len(metrics._metrics)
    
    metrics.cleanup_old_metrics(max_age_hours)
    
    new_count = len(metrics._metrics)
    cleaned_count = old_count - new_count
    
    return jsonify({
        'message': 'Metrics cleanup completed',
        'metrics_before': old_count,
        'metrics_after': new_count,
        'metrics_cleaned': cleaned_count,
        'max_age_hours': max_age_hours
    })