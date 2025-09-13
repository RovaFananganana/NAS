#!/usr/bin/env python3
"""
Database Maintenance Tools Suite

This script provides a unified interface for database maintenance operations:
- Index verification and optimization
- Performance analysis and bottleneck identification
- Automated maintenance recommendations
- Health check reports

Usage:
    python maintenance_tools.py --check-all        # Run all checks
    python maintenance_tools.py --indexes          # Check indexes only
    python maintenance_tools.py --performance      # Performance analysis only
    python maintenance_tools.py --health-check     # Quick health check
"""

import sys
import os
import argparse
from datetime import datetime
from typing import Dict, List, Any

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from verify_indexes import IndexVerifier
    from performance_analyzer import PerformanceAnalyzer
    INDEX_TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import maintenance tools: {e}")
    INDEX_TOOLS_AVAILABLE = False


class MaintenanceToolsSuite:
    """Unified database maintenance tools suite"""
    
    def __init__(self):
        if INDEX_TOOLS_AVAILABLE:
            self.index_verifier = IndexVerifier()
            self.performance_analyzer = PerformanceAnalyzer()
        else:
            self.index_verifier = None
            self.performance_analyzer = None
    
    def run_health_check(self) -> Dict[str, Any]:
        """
        Run a quick health check of the database performance.
        
        Returns:
            Dictionary with health check results
        """
        print("🏥 Running database health check...")
        print("=" * 50)
        
        health_status = {
            'timestamp': datetime.utcnow().isoformat(),
            'overall_status': 'unknown',
            'checks': {},
            'recommendations': [],
            'critical_issues': []
        }
        
        if not INDEX_TOOLS_AVAILABLE:
            health_status['overall_status'] = 'error'
            health_status['checks']['tools_available'] = {
                'status': 'failed',
                'message': 'Maintenance tools not available'
            }
            return health_status
        
        # Check 1: Index verification
        print("🔍 Checking database indexes...")
        try:
            index_results = self.index_verifier.verify_all_indexes()
            missing_count = index_results['missing_indexes']
            
            if missing_count == 0:
                health_status['checks']['indexes'] = {
                    'status': 'passed',
                    'message': 'All required indexes are present'
                }
                print("✅ Indexes: All required indexes present")
            else:
                health_status['checks']['indexes'] = {
                    'status': 'warning',
                    'message': f'{missing_count} indexes missing',
                    'details': index_results['missing_index_details']
                }
                health_status['recommendations'].append(
                    f"Add {missing_count} missing database indexes for optimal performance"
                )
                print(f"⚠️  Indexes: {missing_count} missing indexes")
        
        except Exception as e:
            health_status['checks']['indexes'] = {
                'status': 'failed',
                'message': f'Index check failed: {str(e)}'
            }
            print(f"❌ Indexes: Check failed - {str(e)}")
        
        # Check 2: Performance bottlenecks
        print("🚀 Checking for performance bottlenecks...")
        try:
            bottlenecks = self.performance_analyzer.identify_bottlenecks(15)  # Last 15 minutes
            critical_bottlenecks = [b for b in bottlenecks if b.severity == 'critical']
            
            if not bottlenecks:
                health_status['checks']['performance'] = {
                    'status': 'passed',
                    'message': 'No performance bottlenecks detected'
                }
                print("✅ Performance: No bottlenecks detected")
            elif critical_bottlenecks:
                health_status['checks']['performance'] = {
                    'status': 'critical',
                    'message': f'{len(critical_bottlenecks)} critical bottlenecks found',
                    'details': [b.description for b in critical_bottlenecks]
                }
                health_status['critical_issues'].extend([b.description for b in critical_bottlenecks])
                print(f"🔴 Performance: {len(critical_bottlenecks)} critical bottlenecks")
            else:
                health_status['checks']['performance'] = {
                    'status': 'warning',
                    'message': f'{len(bottlenecks)} performance issues found',
                    'details': [b.description for b in bottlenecks]
                }
                health_status['recommendations'].extend([b.recommendation for b in bottlenecks])
                print(f"⚠️  Performance: {len(bottlenecks)} issues found")
        
        except Exception as e:
            health_status['checks']['performance'] = {
                'status': 'failed',
                'message': f'Performance check failed: {str(e)}'
            }
            print(f"❌ Performance: Check failed - {str(e)}")
        
        # Check 3: Cache performance
        print("💾 Checking cache performance...")
        try:
            cache_stats = self.performance_analyzer.metrics.get_cache_statistics('permission_cache')
            hit_rate = cache_stats.get('hit_rate', 0)
            
            if hit_rate >= 80:
                health_status['checks']['cache'] = {
                    'status': 'passed',
                    'message': f'Cache hit rate: {hit_rate:.1f}%'
                }
                print(f"✅ Cache: Hit rate {hit_rate:.1f}%")
            elif hit_rate >= 60:
                health_status['checks']['cache'] = {
                    'status': 'warning',
                    'message': f'Cache hit rate low: {hit_rate:.1f}%'
                }
                health_status['recommendations'].append(
                    "Improve cache hit rate by optimizing cache TTL or warming strategies"
                )
                print(f"⚠️  Cache: Low hit rate {hit_rate:.1f}%")
            else:
                health_status['checks']['cache'] = {
                    'status': 'critical',
                    'message': f'Cache hit rate very low: {hit_rate:.1f}%'
                }
                health_status['critical_issues'].append(f"Cache hit rate critically low: {hit_rate:.1f}%")
                print(f"🔴 Cache: Very low hit rate {hit_rate:.1f}%")
        
        except Exception as e:
            health_status['checks']['cache'] = {
                'status': 'failed',
                'message': f'Cache check failed: {str(e)}'
            }
            print(f"❌ Cache: Check failed - {str(e)}")
        
        # Determine overall status
        check_statuses = [check['status'] for check in health_status['checks'].values()]
        
        if 'critical' in check_statuses or 'failed' in check_statuses:
            health_status['overall_status'] = 'critical'
        elif 'warning' in check_statuses:
            health_status['overall_status'] = 'warning'
        else:
            health_status['overall_status'] = 'healthy'
        
        # Print summary
        print("\n" + "=" * 50)
        print("🏥 HEALTH CHECK SUMMARY")
        print("=" * 50)
        
        status_colors = {
            'healthy': '🟢',
            'warning': '🟡',
            'critical': '🔴',
            'error': '💀'
        }
        
        color = status_colors.get(health_status['overall_status'], '⚪')
        print(f"Overall Status: {color} {health_status['overall_status'].upper()}")
        
        if health_status['critical_issues']:
            print(f"\n🔴 Critical Issues ({len(health_status['critical_issues'])}):")
            for issue in health_status['critical_issues']:
                print(f"  • {issue}")
        
        if health_status['recommendations']:
            print(f"\n💡 Recommendations ({len(health_status['recommendations'])}):")
            for rec in health_status['recommendations'][:5]:  # Show top 5
                print(f"  • {rec}")
            
            if len(health_status['recommendations']) > 5:
                print(f"  ... and {len(health_status['recommendations']) - 5} more")
        
        return health_status
    
    def run_full_maintenance(self, generate_reports: bool = True) -> Dict[str, Any]:
        """
        Run comprehensive maintenance including all checks and optimizations.
        
        Args:
            generate_reports: Whether to generate detailed reports
            
        Returns:
            Dictionary with maintenance results
        """
        print("🔧 Running comprehensive database maintenance...")
        print("=" * 60)
        
        maintenance_results = {
            'timestamp': datetime.utcnow().isoformat(),
            'index_verification': {},
            'performance_analysis': {},
            'maintenance_actions': [],
            'reports_generated': []
        }
        
        if not INDEX_TOOLS_AVAILABLE:
            print("❌ Maintenance tools not available")
            return maintenance_results
        
        # 1. Index verification and optimization
        print("\n🔍 Step 1: Index Verification")
        print("-" * 30)
        
        try:
            index_results = self.index_verifier.verify_all_indexes()
            maintenance_results['index_verification'] = index_results
            
            # Generate migration script if needed
            if index_results['missing_indexes'] > 0:
                migration_file = f"auto_maintenance_indexes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
                self.index_verifier.generate_migration_script(migration_file)
                maintenance_results['maintenance_actions'].append(f"Generated migration script: {migration_file}")
        
        except Exception as e:
            print(f"❌ Index verification failed: {str(e)}")
            maintenance_results['index_verification'] = {'error': str(e)}
        
        # 2. Performance analysis
        print("\n🚀 Step 2: Performance Analysis")
        print("-" * 30)
        
        try:
            performance_report = self.performance_analyzer.generate_performance_report(60)
            maintenance_results['performance_analysis'] = {
                'bottlenecks_count': len(performance_report.bottlenecks),
                'critical_bottlenecks': len([b for b in performance_report.bottlenecks if b.severity == 'critical']),
                'recommendations_count': len(performance_report.recommendations)
            }
            
            # Generate performance report if requested
            if generate_reports:
                report_file = f"maintenance_performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                self.performance_analyzer.export_report(performance_report, 'markdown', report_file)
                maintenance_results['reports_generated'].append(report_file)
        
        except Exception as e:
            print(f"❌ Performance analysis failed: {str(e)}")
            maintenance_results['performance_analysis'] = {'error': str(e)}
        
        # 3. Cache cleanup and optimization
        print("\n💾 Step 3: Cache Maintenance")
        print("-" * 30)
        
        try:
            # Clean up expired cache entries
            from models.permission_cache import PermissionCache
            expired_count = PermissionCache.cleanup_expired_cache()
            
            if expired_count > 0:
                print(f"🧹 Cleaned up {expired_count} expired cache entries")
                maintenance_results['maintenance_actions'].append(f"Cleaned {expired_count} expired cache entries")
            else:
                print("✅ No expired cache entries found")
        
        except Exception as e:
            print(f"⚠️  Cache cleanup failed: {str(e)}")
            maintenance_results['maintenance_actions'].append(f"Cache cleanup failed: {str(e)}")
        
        # 4. Generate maintenance summary
        print("\n📊 Step 4: Maintenance Summary")
        print("-" * 30)
        
        summary_file = f"maintenance_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            import json
            with open(summary_file, 'w') as f:
                json.dump(maintenance_results, f, indent=2)
            
            maintenance_results['reports_generated'].append(summary_file)
            print(f"📄 Maintenance summary saved to: {summary_file}")
        
        except Exception as e:
            print(f"⚠️  Could not save summary: {str(e)}")
        
        # Print final summary
        print("\n" + "=" * 60)
        print("🔧 MAINTENANCE COMPLETE")
        print("=" * 60)
        
        actions_count = len(maintenance_results['maintenance_actions'])
        reports_count = len(maintenance_results['reports_generated'])
        
        print(f"✅ Maintenance actions performed: {actions_count}")
        print(f"📄 Reports generated: {reports_count}")
        
        if maintenance_results['maintenance_actions']:
            print(f"\n🔧 Actions taken:")
            for action in maintenance_results['maintenance_actions']:
                print(f"  • {action}")
        
        if maintenance_results['reports_generated']:
            print(f"\n📄 Reports generated:")
            for report in maintenance_results['reports_generated']:
                print(f"  • {report}")
        
        return maintenance_results


def main():
    parser = argparse.ArgumentParser(
        description="Database Maintenance Tools Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python maintenance_tools.py --health-check        # Quick health check
  python maintenance_tools.py --check-all           # Full maintenance
  python maintenance_tools.py --indexes             # Index verification only
  python maintenance_tools.py --performance         # Performance analysis only
        """
    )
    
    parser.add_argument(
        '--health-check',
        action='store_true',
        help='Run quick health check'
    )
    
    parser.add_argument(
        '--check-all',
        action='store_true',
        help='Run comprehensive maintenance'
    )
    
    parser.add_argument(
        '--indexes',
        action='store_true',
        help='Run index verification only'
    )
    
    parser.add_argument(
        '--performance',
        action='store_true',
        help='Run performance analysis only'
    )
    
    parser.add_argument(
        '--no-reports',
        action='store_true',
        help='Skip generating detailed reports'
    )
    
    parser.add_argument(
        '--period',
        type=int,
        default=60,
        help='Analysis period in minutes (default: 60)'
    )
    
    args = parser.parse_args()
    
    # If no specific action is specified, default to health check
    if not any([args.health_check, args.check_all, args.indexes, args.performance]):
        args.health_check = True
    
    try:
        suite = MaintenanceToolsSuite()
        
        if args.health_check:
            health_results = suite.run_health_check()
            return 0 if health_results['overall_status'] in ['healthy', 'warning'] else 1
        
        elif args.check_all:
            maintenance_results = suite.run_full_maintenance(not args.no_reports)
            return 0
        
        elif args.indexes:
            if not INDEX_TOOLS_AVAILABLE:
                print("❌ Index verification tools not available")
                return 1
            
            print("🔍 Running index verification...")
            results = suite.index_verifier.verify_all_indexes()
            return 0 if results['missing_indexes'] == 0 else 1
        
        elif args.performance:
            if not INDEX_TOOLS_AVAILABLE:
                print("❌ Performance analysis tools not available")
                return 1
            
            print("🚀 Running performance analysis...")
            report = suite.performance_analyzer.generate_performance_report(args.period)
            
            # Save report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"performance_analysis_{timestamp}.md"
            suite.performance_analyzer.export_report(report, 'markdown', report_file)
            
            critical_count = len([b for b in report.bottlenecks if b.severity == 'critical'])
            return 0 if critical_count == 0 else 1
        
    except Exception as e:
        print(f"❌ Error during maintenance: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())