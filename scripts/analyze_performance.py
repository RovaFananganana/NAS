#!/usr/bin/env python3
"""
Simple CLI wrapper for performance analysis

Usage:
    python analyze_performance.py                    # Full performance report
    python analyze_performance.py --bottlenecks      # Show bottlenecks only
    python analyze_performance.py --queries          # Query analysis only
    python analyze_performance.py --help             # Show help
"""

import sys
import argparse
from datetime import datetime
from performance_analyzer import PerformanceAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="Database Performance Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_performance.py                     # Full report (markdown)
  python analyze_performance.py --bottlenecks       # Show bottlenecks only
  python analyze_performance.py --queries           # Query analysis only
  python analyze_performance.py -f json -o report.json  # JSON report to file
  python analyze_performance.py -p 120              # Analyze last 2 hours
        """
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
        help='Output file path (auto-generated if not specified)'
    )
    
    parser.add_argument(
        '--bottlenecks', '-b',
        action='store_true',
        help='Show only bottleneck analysis'
    )
    
    parser.add_argument(
        '--queries', '-q',
        action='store_true',
        help='Run detailed query analysis only'
    )
    
    parser.add_argument(
        '--live', '-l',
        action='store_true',
        help='Live monitoring mode (continuous analysis)'
    )
    
    parser.add_argument(
        '--threshold',
        type=float,
        default=100.0,
        help='Slow query threshold in milliseconds (default: 100)'
    )
    
    args = parser.parse_args()
    
    try:
        analyzer = PerformanceAnalyzer()
        
        # Update thresholds if specified
        if args.threshold != 100.0:
            analyzer.thresholds['slow_query_ms'] = args.threshold
        
        if args.live:
            # Live monitoring mode
            print("🔄 Starting live performance monitoring...")
            print("Press Ctrl+C to stop")
            
            import time
            try:
                while True:
                    print(f"\n📊 Analysis at {datetime.now().strftime('%H:%M:%S')}")
                    
                    # Quick bottleneck check
                    bottlenecks = analyzer.identify_bottlenecks(5)  # Last 5 minutes
                    critical = [b for b in bottlenecks if b.severity == 'critical']
                    
                    if critical:
                        print(f"🔴 {len(critical)} critical bottlenecks detected!")
                        for b in critical:
                            print(f"   - {b.description}")
                    else:
                        print("✅ No critical bottlenecks detected")
                    
                    # Cache stats
                    cache_stats = analyzer.metrics.get_cache_statistics('permission_cache')
                    print(f"💾 Cache hit rate: {cache_stats['hit_rate']:.1f}%")
                    
                    time.sleep(30)  # Check every 30 seconds
                    
            except KeyboardInterrupt:
                print("\n👋 Monitoring stopped")
                return 0
        
        elif args.queries:
            # Query analysis only
            print("🔍 Running detailed query analysis...")
            query_performance = analyzer.analyze_permission_queries()
            
            print("\n📊 Query Performance Results:")
            print("=" * 60)
            
            for query_name, stats in query_performance.items():
                rating = stats.get('performance_rating', 'unknown')
                time_ms = stats.get('actual_execution_time_ms', 0)
                cost = stats.get('estimated_cost', 0)
                
                # Color coding for ratings
                rating_colors = {
                    'excellent': '🟢',
                    'good': '🟡', 
                    'acceptable': '🟠',
                    'poor': '🔴',
                    'critical': '💀',
                    'unknown': '⚪'
                }
                
                color = rating_colors.get(rating, '⚪')
                print(f"{color} {query_name}")
                print(f"   Performance: {rating} ({time_ms:.1f}ms)")
                if cost > 0:
                    print(f"   Estimated cost: {cost:.2f}")
                
                if 'error' in stats:
                    print(f"   ❌ Error: {stats['error']}")
                print()
        
        elif args.bottlenecks:
            # Bottleneck analysis only
            print("🔍 Identifying performance bottlenecks...")
            bottlenecks = analyzer.identify_bottlenecks(args.period)
            
            if not bottlenecks:
                print("✅ No performance bottlenecks detected!")
                return 0
            
            print(f"\n🚨 Found {len(bottlenecks)} bottlenecks:")
            print("=" * 60)
            
            # Group by severity
            by_severity = {'critical': [], 'high': [], 'medium': [], 'low': []}
            for b in bottlenecks:
                by_severity[b.severity].append(b)
            
            for severity in ['critical', 'high', 'medium', 'low']:
                items = by_severity[severity]
                if items:
                    severity_colors = {
                        'critical': '🔴 CRITICAL',
                        'high': '🟠 HIGH',
                        'medium': '🟡 MEDIUM',
                        'low': '🟢 LOW'
                    }
                    
                    print(f"\n{severity_colors[severity]} PRIORITY:")
                    for b in items:
                        print(f"  • {b.type.replace('_', ' ').title()}")
                        print(f"    {b.description}")
                        print(f"    💡 {b.recommendation}")
                        print(f"    📊 {b.estimated_impact}")
                        print()
        
        else:
            # Generate full report
            print("📊 Generating comprehensive performance report...")
            report = analyzer.generate_performance_report(args.period)
            
            # Determine output file
            output_file = args.output
            if not output_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = f"performance_report_{timestamp}.{args.format}"
            
            # Export report
            content = analyzer.export_report(report, args.format, output_file)
            
            # Print summary
            print("\n📊 Performance Report Summary:")
            print("=" * 40)
            print(f"📅 Analysis Period: {args.period} minutes")
            print(f"🚨 Total Bottlenecks: {len(report.bottlenecks)}")
            
            critical_count = len([b for b in report.bottlenecks if b.severity == 'critical'])
            if critical_count > 0:
                print(f"🔴 Critical Issues: {critical_count}")
            
            print(f"💡 Recommendations: {len(report.recommendations)}")
            
            # Cache performance
            perm_cache = report.cache_performance.get('permission_cache', {})
            if perm_cache:
                print(f"💾 Permission Cache Hit Rate: {perm_cache.get('hit_rate', 0):.1f}%")
            
            print(f"📄 Report saved to: {output_file}")
            
            # Show top recommendations
            if report.recommendations:
                print(f"\n💡 Top Recommendations:")
                for i, rec in enumerate(report.recommendations[:3], 1):
                    print(f"  {i}. {rec}")
                
                if len(report.recommendations) > 3:
                    print(f"  ... and {len(report.recommendations) - 3} more (see full report)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())