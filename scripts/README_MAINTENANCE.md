# Database Maintenance Tools

This directory contains comprehensive database maintenance and performance analysis tools for the database optimization project.

## Overview

The maintenance tools provide:

- **Index Verification**: Verify all required database indexes exist and are optimal
- **Performance Analysis**: Analyze query performance and identify bottlenecks  
- **Automated Recommendations**: Generate optimization recommendations
- **Health Monitoring**: Quick health checks and continuous monitoring
- **Report Generation**: Detailed reports in multiple formats (JSON, HTML, Markdown)

## Tools

### 1. Index Verification (`verify_indexes.py`)

Verifies that all required database indexes exist for optimal permission query performance.

**Features:**
- Checks all required indexes from the design document
- Detects missing or suboptimal indexes
- Generates automatic optimization recommendations
- Creates Alembic migration scripts for missing indexes
- Provides database statistics and index usage analysis

**Usage:**
```bash
# Run full index verification
python verify_indexes.py

# Generate migration script for missing indexes
python check_indexes.py --generate-migration

# Quiet mode with minimal output
python check_indexes.py --quiet
```

**Required Indexes Checked:**
- File permissions: `idx_file_permissions_user_file`, `idx_file_permissions_group_file`, etc.
- Folder permissions: `idx_folder_permissions_user_folder`, `idx_folder_permissions_group_folder`, etc.
- User-group relationships: `idx_user_group_user`, `idx_user_group_group`
- File/folder hierarchy: `idx_files_folder_owner`, `idx_folders_parent_owner`, etc.
- Permission cache: `idx_perm_cache_user_resource`, `idx_perm_cache_expires`, etc.

### 2. Performance Analysis (`performance_analyzer.py`)

Comprehensive performance analysis tool that identifies bottlenecks and provides optimization recommendations.

**Features:**
- Query execution plan analysis
- Permission query performance profiling
- Bottleneck identification (slow queries, cache misses, missing indexes)
- Performance metrics collection and analysis
- Multi-format report generation (JSON, HTML, Markdown)

**Usage:**
```bash
# Generate full performance report
python performance_analyzer.py

# Analyze specific time period (2 hours)
python performance_analyzer.py --period 120

# Query analysis only
python analyze_performance.py --queries

# Bottleneck identification only
python analyze_performance.py --bottlenecks

# Live monitoring mode
python analyze_performance.py --live

# Generate HTML report
python performance_analyzer.py --format html --output report.html
```

**Analysis Includes:**
- Permission query execution plans
- Cache hit/miss rates
- Slow operation identification
- Database table statistics
- Performance trend analysis

### 3. Unified Maintenance Suite (`maintenance_tools.py`)

Combines all maintenance tools into a unified interface for comprehensive database health monitoring.

**Features:**
- Quick health checks
- Full maintenance workflows
- Automated cache cleanup
- Comprehensive reporting
- Maintenance action logging

**Usage:**
```bash
# Quick health check
python maintenance_tools.py --health-check

# Full comprehensive maintenance
python maintenance_tools.py --check-all

# Index verification only
python maintenance_tools.py --indexes

# Performance analysis only  
python maintenance_tools.py --performance

# Skip detailed report generation
python maintenance_tools.py --check-all --no-reports
```

## Performance Thresholds

The tools use the following performance thresholds:

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Slow Query | 100ms | General database queries |
| Permission Check | 50ms | Individual permission checks |
| Bulk Operation | 200ms | Bulk permission operations |
| Cache Hit Rate | 80% | Minimum acceptable cache hit rate |
| Critical Bottleneck | 500ms | Operations requiring immediate attention |

## Report Formats

### JSON Reports
Structured data suitable for external monitoring systems and automated processing.

### HTML Reports  
Web-friendly reports with styling and interactive elements.

### Markdown Reports
Human-readable reports suitable for documentation and sharing.

## Integration with Monitoring

### Prometheus Metrics
The performance analyzer can export metrics in Prometheus format:

```bash
python performance_analyzer.py --format prometheus
```

### External Monitoring
JSON reports can be consumed by external monitoring systems:

```bash
# Export for monitoring system
python performance_analyzer.py --format json --output /monitoring/db_performance.json
```

## Automated Maintenance

### Scheduled Health Checks
Set up cron jobs for regular health monitoring:

```bash
# Daily health check at 2 AM
0 2 * * * cd /path/to/backend/scripts && python maintenance_tools.py --health-check

# Weekly full maintenance on Sundays at 3 AM  
0 3 * * 0 cd /path/to/backend/scripts && python maintenance_tools.py --check-all
```

### CI/CD Integration
Include performance checks in your deployment pipeline:

```bash
# In your CI/CD script
python maintenance_tools.py --health-check
if [ $? -ne 0 ]; then
    echo "Database health check failed!"
    exit 1
fi
```

## Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Ensure you're in the backend directory
cd backend
python scripts/verify_indexes.py
```

**2. Database Connection Issues**
- Verify database configuration in `config.py`
- Ensure database is running and accessible
- Check database credentials

**3. Missing Dependencies**
```bash
# Install required packages
pip install -r requirements.txt
```

**4. Permission Issues**
- Ensure database user has SELECT permissions on `information_schema`
- For MySQL: `GRANT SELECT ON information_schema.* TO 'user'@'host';`

### Performance Issues

**Slow Analysis**
- Reduce analysis period: `--period 30`
- Skip detailed reports: `--no-reports`
- Use specific analysis modes: `--bottlenecks` or `--queries`

**Memory Usage**
- The tools maintain in-memory metrics with configurable limits
- Adjust `max_entries` in `PerformanceMetrics` if needed
- Regular cleanup prevents memory bloat

## Best Practices

### Regular Maintenance Schedule

1. **Daily**: Quick health checks
2. **Weekly**: Full performance analysis
3. **Monthly**: Comprehensive maintenance with report generation
4. **After deployments**: Index verification and performance validation

### Performance Monitoring

1. **Baseline Establishment**: Run initial analysis to establish performance baselines
2. **Trend Monitoring**: Regular analysis to identify performance trends
3. **Alert Thresholds**: Set up alerts based on critical bottlenecks
4. **Capacity Planning**: Use reports for database capacity planning

### Index Management

1. **Pre-deployment**: Always verify indexes before deploying schema changes
2. **Post-migration**: Run index verification after database migrations
3. **Performance Testing**: Include index verification in performance test suites
4. **Documentation**: Keep index documentation updated with verification results

## Requirements Mapping

These tools fulfill the following requirements from the database optimization specification:

- **Requirement 3.1**: Index verification for tables with 10,000+ records
- **Requirement 3.2**: Optimized index usage for user_id lookups  
- **Requirement 3.3**: Composite indexes for file_id/folder_id searches
- **Requirement 6.1**: Performance logging for queries >100ms
- **Requirement 6.2**: Query execution time metrics collection
- **Requirement 6.3**: Diagnostic information for slow queries

## Support

For issues or questions about the maintenance tools:

1. Check the troubleshooting section above
2. Review the generated reports for specific recommendations
3. Examine the performance logs for detailed error information
4. Consult the database optimization design document for context