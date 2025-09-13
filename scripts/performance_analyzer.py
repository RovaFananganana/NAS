#!/usr/bin/env python3
"""
Performance Analysis Tools for Database Optimization

This script provides comprehensive performance analysis capabilities including:
- Query execution plan analysis
- Performance reports with optimization recommendations
- Bottleneck identification for permission queries
- Database performance profiling

Requirements: 6.1, 6.2, 6.3
"""

import sys
import os
import json
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine
from services.performance_metrics import get_performance_metrics, MetricType


@dataclass
class QueryPlan:
    """Query execution plan information"""
    query: str
    plan: List[Dict[str, Any]]
    estimated_cost: float
    actual_rows: Optional[int] = None
    execution_time_ms: Optional[float] = None
    
    
@dataclass
class PerformanceBottleneck:
    """Identified performance bottleneck"""
    type: str  # 'slow_query', 'missing_index', 'inefficient_join', 'cache_miss'
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    affected_operations: List[str]
    recommendation: str
    estimated_impact: str
    

@dataclass
class PerformanceReport:
    """Comprehensive performance analysis report"""
    timestamp: datetime
    analysis_period_minutes: int
    database_info: Dict[str, Any]
    query_performance: Dict[str, Any]
    permission_performance: Dict[str, Any]
    cache_performance: Dict[str, Any]
    bottlenecks: List[PerformanceBottleneck]
    recommendations: List[str]
    

class PerformanceAnalyzer:
    """Comprehensive performance analysis tool for database optimization"""
    
    def __init__(self):
        self.engine: Engine = db.engine
        self.inspector = inspect(self.engine)
        self.metrics = get_performance_metrics()
        
        # Performance thresholds
        self.thresholds = {
            'slow_query_ms': 100.0,
            'permission_check_ms': 50.0,
            'bulk_operation_ms': 200.0,
            'cache_hit_rate_min': 80.0,
            'critical_bottleneck_ms': 500.0
        }
    
    def analyze_query_execution_plan(self, query: str, params: Optional[Dict] = None) -> QueryPlan:
        """
        Analyze the execution plan for a specific query.
        
        Args:
            query: SQL query to analyze
            params: Query parameters
            
        Returns:
            QueryPlan object with execution plan details
        """
        print(f"🔍 Analyzing execution plan for query...")
        
        try:
            with self.engine.connect() as conn:
                # Get execution plan (MySQL EXPLAIN)
                if 'mysql' in str(self.engine.dialect.name).lower():
                    explain_query = f"EXPLAIN FORMAT=JSON {query}"
                    result = conn.execute(text(explain_query), params or {})
                    plan_json = result.fetchone()[0]
                    plan_data = json.loads(plan_json)
                    
                    # Extract cost information
                    estimated_cost = self._extract_mysql_cost(plan_data)
                    
                    return QueryPlan(
                        query=query,
                        plan=[plan_data],
                        estimated_cost=estimated_cost
                    )
                
                # For other databases, use basic EXPLAIN
                else:
                    explain_query = f"EXPLAIN {query}"
                    result = conn.execute(text(explain_query), params or {})
                    plan_rows = result.fetchall()
                    
                    plan_data = [dict(row._mapping) for row in plan_rows]
                    
                    return QueryPlan(
                        query=query,
                        plan=plan_data,
                        estimated_cost=0.0  # Not available for all databases
                    )
                    
        except Exception as e:
            print(f"❌ Error analyzing query plan: {str(e)}")
            return QueryPlan(
                query=query,
                plan=[{"error": str(e)}],
                estimated_cost=0.0
            )
    
    def _extract_mysql_cost(self, plan_data: Dict) -> float:
        """Extract cost information from MySQL execution plan"""
        try:
            query_block = plan_data.get('query_block', {})
            cost_info = query_block.get('cost_info', {})
            return float(cost_info.get('query_cost', 0.0))
        except:
            return 0.0
    
    def analyze_permission_queries(self) -> Dict[str, Any]:
        """Analyze performance of permission-related queries"""
        print("🔐 Analyzing permission query performance...")
        
        # Define critical permission queries to analyze
        permission_queries = {
            'file_permission_check': """
                SELECT fp.can_read, fp.can_write, fp.can_delete, fp.can_share
                FROM file_permissions fp
                WHERE fp.file_id = :file_id 
                AND (fp.user_id = :user_id OR fp.group_id IN (
                    SELECT ug.group_id FROM user_group ug WHERE ug.user_id = :user_id
                ))
            """,
            'folder_permission_check': """
                SELECT fp.can_read, fp.can_write, fp.can_delete, fp.can_share
                FROM folder_permissions fp
                WHERE fp.folder_id = :folder_id
                AND (fp.user_id = :user_id OR fp.group_id IN (
                    SELECT ug.group_id FROM user_group ug WHERE ug.user_id = :user_id
                ))
            """,
            'bulk_file_permissions': """
                WITH user_groups AS (
                    SELECT group_id FROM user_group WHERE user_id = :user_id
                )
                SELECT f.id, fp.can_read, fp.can_write, fp.can_delete, fp.can_share
                FROM files f
                LEFT JOIN file_permissions fp ON f.id = fp.file_id
                WHERE f.id IN :file_ids
                AND (fp.user_id = :user_id OR fp.group_id IN (SELECT group_id FROM user_groups))
            """,
            'folder_hierarchy_permissions': """
                WITH RECURSIVE folder_tree AS (
                    SELECT id, parent_id, 0 as depth FROM folders WHERE id = :root_folder_id
                    UNION ALL
                    SELECT f.id, f.parent_id, ft.depth + 1
                    FROM folders f
                    JOIN folder_tree ft ON f.parent_id = ft.id
                    WHERE ft.depth < 5
                )
                SELECT ft.id, fp.can_read, fp.can_write, fp.can_delete, fp.can_share
                FROM folder_tree ft
                LEFT JOIN folder_permissions fp ON ft.id = fp.folder_id
                WHERE fp.user_id = :user_id OR fp.group_id IN (
                    SELECT group_id FROM user_group WHERE user_id = :user_id
                )
            """
        }
        
        analysis_results = {}
        
        for query_name, query in permission_queries.items():
            try:
                # Analyze execution plan
                plan = self.analyze_query_execution_plan(query, {
                    'user_id': 1,
                    'file_id': 1,
                    'folder_id': 1,
                    'root_folder_id': 1,
                    'file_ids': [1, 2, 3]
                })
                
                # Measure actual execution time
                execution_time = self._measure_query_performance(query, {
                    'user_id': 1,
                    'file_id': 1,
                    'folder_id': 1,
                    'root_folder_id': 1,
                    'file_ids': [1, 2, 3]
                })
                
                analysis_results[query_name] = {
                    'execution_plan': plan.plan,
                    'estimated_cost': plan.estimated_cost,
                    'actual_execution_time_ms': execution_time,
                    'performance_rating': self._rate_query_performance(execution_time)
                }
                
            except Exception as e:
                analysis_results[query_name] = {
                    'error': str(e),
                    'performance_rating': 'unknown'
                }
        
        return analysis_results
    
    def _measure_query_performance(self, query: str, params: Dict) -> float:
        """Measure actual query execution time"""
        try:
            with self.engine.connect() as conn:
                start_time = time.perf_counter()
                conn.execute(text(query), params)
                end_time = time.perf_counter()
                return (end_time - start_time) * 1000
        except:
            return 0.0
    
    def _rate_query_performance(self, execution_time_ms: float) -> str:
        """Rate query performance based on execution time"""
        if execution_time_ms <= 10:
            return 'excellent'
        elif execution_time_ms <= 50:
            return 'good'
        elif execution_time_ms <= 100:
            return 'acceptable'
        elif execution_time_ms <= 500:
            return 'poor'
        else:
            return 'critical'
    
    def identify_bottlenecks(self, analysis_period_minutes: int = 60) -> List[PerformanceBottleneck]:
        """
        Identify performance bottlenecks in the system.
        
        Args:
            analysis_period_minutes: Time period to analyze
            
        Returns:
            List of identified bottlenecks
        """
        print("🔍 Identifying performance bottlenecks...")
        
        bottlenecks = []
        
        # Analyze slow operations
        slow_operations = self.metrics.get_slow_operations(
            threshold_ms=self.thresholds['slow_query_ms'],
            time_window_minutes=analysis_period_minutes
        )
        
        if slow_operations:
            # Group by operation type
            operation_groups = defaultdict(list)
            for op in slow_operations:
                operation_groups[op['operation']].append(op)
            
            for operation, ops in operation_groups.items():
                avg_duration = sum(op['duration_ms'] for op in ops) / len(ops)
                
                severity = 'critical' if avg_duration > self.thresholds['critical_bottleneck_ms'] else 'high'
                
                bottlenecks.append(PerformanceBottleneck(
                    type='slow_query',
                    severity=severity,
                    description=f"Operation '{operation}' is consistently slow (avg: {avg_duration:.1f}ms)",
                    affected_operations=[operation],
                    recommendation=self._get_slow_query_recommendation(operation, avg_duration),
                    estimated_impact=f"Affects {len(ops)} operations in the last {analysis_period_minutes} minutes"
                ))
        
        # Analyze cache performance
        cache_stats = self.metrics.get_cache_statistics('permission_cache')
        if cache_stats['hit_rate'] < self.thresholds['cache_hit_rate_min']:
            bottlenecks.append(PerformanceBottleneck(
                type='cache_miss',
                severity='medium',
                description=f"Permission cache hit rate is low ({cache_stats['hit_rate']:.1f}%)",
                affected_operations=['permission_check'],
                recommendation="Increase cache TTL, warm cache for frequently accessed resources, or review cache invalidation strategy",
                estimated_impact=f"Cache misses: {cache_stats['misses']}, potential for significant performance improvement"
            ))
        
        # Check for missing indexes (integrate with index verification)
        try:
            from verify_indexes import IndexVerifier
            verifier = IndexVerifier()
            missing_indexes = [idx for idx in verifier.required_indexes if not verifier._check_index_exists(idx)]
            
            if missing_indexes:
                bottlenecks.append(PerformanceBottleneck(
                    type='missing_index',
                    severity='high',
                    description=f"Found {len(missing_indexes)} missing database indexes",
                    affected_operations=['permission_check', 'bulk_operations'],
                    recommendation="Run index verification script and apply missing indexes",
                    estimated_impact="Significant performance improvement for permission queries"
                ))
        except ImportError:
            pass
        
        # Analyze permission-specific bottlenecks
        permission_bottlenecks = self._analyze_permission_bottlenecks(analysis_period_minutes)
        bottlenecks.extend(permission_bottlenecks)
        
        return bottlenecks
    
    def _get_slow_query_recommendation(self, operation: str, avg_duration_ms: float) -> str:
        """Get recommendation for slow query optimization"""
        if 'permission' in operation.lower():
            return "Consider using bulk permission loading, check for missing indexes on permission tables, or implement permission caching"
        elif 'bulk' in operation.lower():
            return "Optimize bulk operations with batch processing, use CTEs for complex queries, or implement pagination"
        else:
            return "Analyze query execution plan, add appropriate indexes, or optimize query structure"
    
    def _analyze_permission_bottlenecks(self, analysis_period_minutes: int) -> List[PerformanceBottleneck]:
        """Analyze permission-specific performance bottlenecks"""
        bottlenecks = []
        
        # Check for N+1 query patterns in permissions
        permission_ops = ['File.get_effective_permissions', 'Folder.get_effective_permissions']
        
        for operation in permission_ops:
            stats = self.metrics.get_operation_statistics(operation, analysis_period_minutes)
            
            if stats['count'] > 100 and stats['avg_duration_ms'] > self.thresholds['permission_check_ms']:
                bottlenecks.append(PerformanceBottleneck(
                    type='inefficient_permission_check',
                    severity='medium',
                    description=f"High frequency of individual permission checks for {operation}",
                    affected_operations=[operation],
                    recommendation="Implement bulk permission loading to reduce N+1 query patterns",
                    estimated_impact=f"Could reduce {stats['count']} individual queries to batch operations"
                ))
        
        return bottlenecks
    
    def generate_performance_report(self, analysis_period_minutes: int = 60) -> PerformanceReport:
        """
        Generate comprehensive performance analysis report.
        
        Args:
            analysis_period_minutes: Time period to analyze
            
        Returns:
            PerformanceReport with complete analysis
        """
        print("📊 Generating comprehensive performance report...")
        print(f"📅 Analysis period: {analysis_period_minutes} minutes")
        print("=" * 60)
        
        # Gather database information
        database_info = self._get_database_performance_info()
        
        # Analyze query performance
        query_performance = self.analyze_permission_queries()
        
        # Get permission performance metrics
        permission_performance = self._get_permission_performance_metrics(analysis_period_minutes)
        
        # Get cache performance
        cache_performance = {
            'permission_cache': self.metrics.get_cache_statistics('permission_cache'),
            'metadata_cache': self.metrics.get_cache_statistics('metadata_cache')
        }
        
        # Identify bottlenecks
        bottlenecks = self.identify_bottlenecks(analysis_period_minutes)
        
        # Generate recommendations
        recommendations = self._generate_optimization_recommendations(
            query_performance, permission_performance, cache_performance, bottlenecks
        )
        
        report = PerformanceReport(
            timestamp=datetime.utcnow(),
            analysis_period_minutes=analysis_period_minutes,
            database_info=database_info,
            query_performance=query_performance,
            permission_performance=permission_performance,
            cache_performance=cache_performance,
            bottlenecks=bottlenecks,
            recommendations=recommendations
        )
        
        return report
    
    def _get_database_performance_info(self) -> Dict[str, Any]:
        """Get general database performance information"""
        try:
            with self.engine.connect() as conn:
                # Get table sizes and row counts
                table_info = {}
                key_tables = ['users', 'files', 'folders', 'file_permissions', 'folder_permissions', 'permission_cache']
                
                for table in key_tables:
                    try:
                        # Get row count
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        row_count = result.fetchone()[0]
                        
                        # Get table size (MySQL specific)
                        if 'mysql' in str(self.engine.dialect.name).lower():
                            size_query = """
                                SELECT 
                                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                                FROM information_schema.TABLES 
                                WHERE table_schema = DATABASE() AND table_name = :table_name
                            """
                            result = conn.execute(text(size_query), {'table_name': table})
                            size_mb = result.fetchone()[0] or 0
                        else:
                            size_mb = 0
                        
                        table_info[table] = {
                            'row_count': row_count,
                            'size_mb': size_mb
                        }
                    except Exception as e:
                        table_info[table] = {'error': str(e)}
                
                return {
                    'database_engine': str(self.engine.dialect.name),
                    'table_info': table_info,
                    'connection_pool_size': getattr(self.engine.pool, 'size', 'unknown')
                }
        except Exception as e:
            return {'error': str(e)}
    
    def _get_permission_performance_metrics(self, analysis_period_minutes: int) -> Dict[str, Any]:
        """Get permission-specific performance metrics"""
        permission_operations = [
            'File.get_effective_permissions',
            'Folder.get_effective_permissions',
            'File.get_bulk_permissions',
            'Folder.get_bulk_permissions'
        ]
        
        metrics = {}
        for operation in permission_operations:
            stats = self.metrics.get_operation_statistics(operation, analysis_period_minutes)
            metrics[operation] = stats
        
        return metrics
    
    def _generate_optimization_recommendations(self, query_performance: Dict, 
                                            permission_performance: Dict,
                                            cache_performance: Dict,
                                            bottlenecks: List[PerformanceBottleneck]) -> List[str]:
        """Generate optimization recommendations based on analysis"""
        recommendations = []
        
        # Query performance recommendations
        for query_name, stats in query_performance.items():
            if stats.get('performance_rating') in ['poor', 'critical']:
                recommendations.append(
                    f"Optimize {query_name}: execution time {stats.get('actual_execution_time_ms', 0):.1f}ms "
                    f"exceeds acceptable threshold"
                )
        
        # Cache recommendations
        for cache_type, stats in cache_performance.items():
            if stats['hit_rate'] < self.thresholds['cache_hit_rate_min']:
                recommendations.append(
                    f"Improve {cache_type} hit rate: currently {stats['hit_rate']:.1f}%, "
                    f"target >{self.thresholds['cache_hit_rate_min']:.1f}%"
                )
        
        # Bottleneck recommendations
        critical_bottlenecks = [b for b in bottlenecks if b.severity == 'critical']
        if critical_bottlenecks:
            recommendations.append(
                f"Address {len(critical_bottlenecks)} critical performance bottlenecks immediately"
            )
        
        # Permission-specific recommendations
        for operation, stats in permission_performance.items():
            if stats['avg_duration_ms'] > self.thresholds['permission_check_ms']:
                recommendations.append(
                    f"Optimize {operation}: average {stats['avg_duration_ms']:.1f}ms "
                    f"exceeds {self.thresholds['permission_check_ms']}ms threshold"
                )
        
        return recommendations
    
    def export_report(self, report: PerformanceReport, format_type: str = 'json', 
                     output_file: Optional[str] = None) -> str:
        """
        Export performance report in specified format.
        
        Args:
            report: PerformanceReport to export
            format_type: Export format ('json', 'html', 'markdown')
            output_file: Optional file path to save report
            
        Returns:
            Formatted report string
        """
        if format_type == 'json':
            content = self._export_json_report(report)
        elif format_type == 'html':
            content = self._export_html_report(report)
        elif format_type == 'markdown':
            content = self._export_markdown_report(report)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(content)
            print(f"📝 Report saved to: {output_file}")
        
        return content
    
    def _export_json_report(self, report: PerformanceReport) -> str:
        """Export report as JSON"""
        # Convert dataclasses to dict
        report_dict = asdict(report)
        
        # Convert datetime to ISO string
        report_dict['timestamp'] = report.timestamp.isoformat()
        
        return json.dumps(report_dict, indent=2)
    
    def _export_markdown_report(self, report: PerformanceReport) -> str:
        """Export report as Markdown"""
        md_content = f"""# Database Performance Analysis Report

**Generated:** {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Analysis Period:** {report.analysis_period_minutes} minutes

## Executive Summary

- **Total Bottlenecks:** {len(report.bottlenecks)}
- **Critical Issues:** {len([b for b in report.bottlenecks if b.severity == 'critical'])}
- **Recommendations:** {len(report.recommendations)}

## Database Information

| Metric | Value |
|--------|-------|
| Database Engine | {report.database_info.get('database_engine', 'Unknown')} |
| Connection Pool Size | {report.database_info.get('connection_pool_size', 'Unknown')} |

### Table Statistics

| Table | Row Count | Size (MB) |
|-------|-----------|-----------|
"""
        
        for table, info in report.database_info.get('table_info', {}).items():
            if isinstance(info, dict) and 'row_count' in info:
                md_content += f"| {table} | {info['row_count']:,} | {info.get('size_mb', 0):.2f} |\n"
        
        md_content += f"""
## Cache Performance

| Cache Type | Hit Rate | Total Requests | Hits | Misses |
|------------|----------|----------------|------|--------|
"""
        
        for cache_type, stats in report.cache_performance.items():
            md_content += f"| {cache_type} | {stats['hit_rate']:.1f}% | {stats['total_requests']:,} | {stats['hits']:,} | {stats['misses']:,} |\n"
        
        md_content += f"""
## Performance Bottlenecks

"""
        
        for bottleneck in report.bottlenecks:
            severity_emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(bottleneck.severity, '⚪')
            md_content += f"""### {severity_emoji} {bottleneck.type.replace('_', ' ').title()} ({bottleneck.severity.upper()})

**Description:** {bottleneck.description}

**Affected Operations:** {', '.join(bottleneck.affected_operations)}

**Recommendation:** {bottleneck.recommendation}

**Estimated Impact:** {bottleneck.estimated_impact}

---

"""
        
        md_content += f"""
## Optimization Recommendations

"""
        
        for i, recommendation in enumerate(report.recommendations, 1):
            md_content += f"{i}. {recommendation}\n"
        
        return md_content
    
    def _export_html_report(self, report: PerformanceReport) -> str:
        """Export report as HTML"""
        # Basic HTML template - could be enhanced with CSS styling
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Database Performance Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; }}
        .bottleneck {{ border-left: 4px solid #ff6b6b; padding: 10px; margin: 10px 0; background-color: #fff5f5; }}
        .bottleneck.critical {{ border-color: #ff0000; }}
        .bottleneck.high {{ border-color: #ff6b00; }}
        .bottleneck.medium {{ border-color: #ffaa00; }}
        .bottleneck.low {{ border-color: #00aa00; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Database Performance Analysis Report</h1>
        <p><strong>Generated:</strong> {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        <p><strong>Analysis Period:</strong> {report.analysis_period_minutes} minutes</p>
    </div>
    
    <div class="section">
        <h2>Performance Bottlenecks</h2>
"""
        
        for bottleneck in report.bottlenecks:
            html_content += f"""
        <div class="bottleneck {bottleneck.severity}">
            <h3>{bottleneck.type.replace('_', ' ').title()} ({bottleneck.severity.upper()})</h3>
            <p><strong>Description:</strong> {bottleneck.description}</p>
            <p><strong>Recommendation:</strong> {bottleneck.recommendation}</p>
            <p><strong>Impact:</strong> {bottleneck.estimated_impact}</p>
        </div>
"""
        
        html_content += """
    </div>
    
    <div class="section">
        <h2>Recommendations</h2>
        <ol>
"""
        
        for recommendation in report.recommendations:
            html_content += f"            <li>{recommendation}</li>\n"
        
        html_content += """
        </ol>
    </div>
</body>
</html>"""
        
        return html_content


def main():
    """Main function to run performance analysis"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Database Performance Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--period', '-p',
        type=int,
        default=60,
        help='Analysis period in minutes (default: 60)'
    )
    
    parser.add_argument(
        '--format', '-f',
        choices=['json', 'html', 'markdown'],
        default='markdown',
        help='Report format (default: markdown)'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output file path'
    )
    
    parser.add_argument(
        '--query-analysis',
        action='store_true',
        help='Run detailed query analysis only'
    )
    
    parser.add_argument(
        '--bottlenecks-only',
        action='store_true',
        help='Show only bottleneck analysis'
    )
    
    args = parser.parse_args()
    
    try:
        analyzer = PerformanceAnalyzer()
        
        if args.query_analysis:
            # Run query analysis only
            print("🔍 Running query analysis...")
            query_performance = analyzer.analyze_permission_queries()
            
            print("\n📊 Query Performance Results:")
            for query_name, stats in query_performance.items():
                rating = stats.get('performance_rating', 'unknown')
                time_ms = stats.get('actual_execution_time_ms', 0)
                print(f"  {query_name}: {rating} ({time_ms:.1f}ms)")
            
        elif args.bottlenecks_only:
            # Run bottleneck analysis only
            print("🔍 Identifying bottlenecks...")
            bottlenecks = analyzer.identify_bottlenecks(args.period)
            
            print(f"\n🚨 Found {len(bottlenecks)} bottlenecks:")
            for bottleneck in bottlenecks:
                severity_emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(bottleneck.severity, '⚪')
                print(f"  {severity_emoji} {bottleneck.type}: {bottleneck.description}")
            
        else:
            # Generate full report
            report = analyzer.generate_performance_report(args.period)
            
            # Export report
            output_file = args.output
            if not output_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"performance_report_{timestamp}.{args.format}"
            
            content = analyzer.export_report(report, args.format, output_file)
            
            # Print summary
            print(f"\n📊 Performance Report Summary:")
            print(f"   Bottlenecks: {len(report.bottlenecks)}")
            print(f"   Critical: {len([b for b in report.bottlenecks if b.severity == 'critical'])}")
            print(f"   Recommendations: {len(report.recommendations)}")
            
            if not args.output:
                print(f"\n📄 Report content:\n")
                print(content[:1000] + "..." if len(content) > 1000 else content)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())