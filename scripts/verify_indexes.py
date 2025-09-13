#!/usr/bin/env python3
"""
Index Verification Script for Database Optimization

This script verifies that all required database indexes exist and are optimal
for the permission system performance. It also provides recommendations for
missing or suboptimal indexes.

Requirements: 3.1, 3.2, 3.3
"""

import sys
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine


@dataclass
class IndexInfo:
    """Information about a database index"""
    name: str
    table: str
    columns: List[str]
    unique: bool = False
    exists: bool = False
    
    
@dataclass
class IndexRecommendation:
    """Recommendation for index optimization"""
    index_name: str
    table: str
    columns: List[str]
    reason: str
    priority: str  # 'high', 'medium', 'low'
    estimated_impact: str


class IndexVerifier:
    """Verifies database indexes for optimal permission query performance"""
    
    def __init__(self):
        self.engine: Engine = db.engine
        self.inspector = inspect(self.engine)
        
        # Define required indexes based on design document
        self.required_indexes = self._define_required_indexes()
        
    def _define_required_indexes(self) -> List[IndexInfo]:
        """Define all required indexes for optimal performance"""
        return [
            # File permissions indexes
            IndexInfo("idx_file_permissions_user_file", "file_permissions", ["user_id", "file_id"]),
            IndexInfo("idx_file_permissions_group_file", "file_permissions", ["group_id", "file_id"]),
            IndexInfo("idx_file_permissions_file_actions", "file_permissions", 
                     ["file_id", "can_read", "can_write", "can_delete", "can_share"]),
            
            # Folder permissions indexes
            IndexInfo("idx_folder_permissions_user_folder", "folder_permissions", ["user_id", "folder_id"]),
            IndexInfo("idx_folder_permissions_group_folder", "folder_permissions", ["group_id", "folder_id"]),
            IndexInfo("idx_folder_permissions_folder_actions", "folder_permissions",
                     ["folder_id", "can_read", "can_write", "can_delete", "can_share"]),
            
            # User-group relationship indexes
            IndexInfo("idx_user_group_user", "user_group", ["user_id"]),
            IndexInfo("idx_user_group_group", "user_group", ["group_id"]),
            
            # File hierarchy indexes
            IndexInfo("idx_files_folder_owner", "files", ["folder_id", "owner_id"]),
            IndexInfo("idx_files_owner", "files", ["owner_id"]),
            
            # Folder hierarchy indexes
            IndexInfo("idx_folders_parent_owner", "folders", ["parent_id", "owner_id"]),
            IndexInfo("idx_folders_owner", "folders", ["owner_id"]),
            IndexInfo("idx_folders_parent", "folders", ["parent_id"]),
            
            # Permission cache indexes (from model definition)
            IndexInfo("idx_perm_cache_user_resource", "permission_cache", 
                     ["user_id", "resource_type", "resource_id"]),
            IndexInfo("idx_perm_cache_expires", "permission_cache", ["expires_at"]),
            IndexInfo("idx_perm_cache_user_type", "permission_cache", ["user_id", "resource_type"]),
        ]
    
    def verify_all_indexes(self) -> Dict[str, any]:
        """
        Verify all required indexes exist and are optimal.
        
        Returns:
            Dictionary with verification results and recommendations
        """
        print("🔍 Starting database index verification...")
        print(f"📅 Verification time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_required': len(self.required_indexes),
            'existing_indexes': 0,
            'missing_indexes': 0,
            'missing_index_details': [],
            'existing_index_details': [],
            'recommendations': [],
            'database_info': self._get_database_info()
        }
        
        # Check each required index
        for required_index in self.required_indexes:
            exists = self._check_index_exists(required_index)
            required_index.exists = exists
            
            if exists:
                results['existing_indexes'] += 1
                results['existing_index_details'].append({
                    'name': required_index.name,
                    'table': required_index.table,
                    'columns': required_index.columns
                })
                print(f"✅ {required_index.name} on {required_index.table}")
            else:
                results['missing_indexes'] += 1
                results['missing_index_details'].append({
                    'name': required_index.name,
                    'table': required_index.table,
                    'columns': required_index.columns
                })
                print(f"❌ {required_index.name} on {required_index.table} - MISSING")
        
        # Generate recommendations
        recommendations = self._generate_recommendations()
        results['recommendations'] = [rec.__dict__ for rec in recommendations]
        
        # Print summary
        self._print_summary(results)
        
        # Print recommendations
        if recommendations:
            self._print_recommendations(recommendations)
        
        return results
    
    def _check_index_exists(self, required_index: IndexInfo) -> bool:
        """Check if a specific index exists in the database"""
        try:
            # Get all indexes for the table
            table_indexes = self.inspector.get_indexes(required_index.table)
            
            # Check if our required index exists
            for index in table_indexes:
                if index['name'] == required_index.name:
                    # Verify columns match
                    if set(index['column_names']) == set(required_index.columns):
                        return True
            
            return False
            
        except Exception as e:
            print(f"⚠️  Error checking index {required_index.name}: {str(e)}")
            return False
    
    def _get_database_info(self) -> Dict[str, any]:
        """Get general database information"""
        try:
            with self.engine.connect() as conn:
                # Get database size and table counts
                result = conn.execute(text("""
                    SELECT 
                        COUNT(*) as table_count
                    FROM information_schema.tables 
                    WHERE table_schema = DATABASE()
                """))
                table_count = result.fetchone()[0]
                
                # Get record counts for key tables
                table_stats = {}
                key_tables = ['users', 'files', 'folders', 'file_permissions', 'folder_permissions', 'permission_cache']
                
                for table in key_tables:
                    try:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        table_stats[table] = result.fetchone()[0]
                    except:
                        table_stats[table] = 0
                
                return {
                    'total_tables': table_count,
                    'table_record_counts': table_stats,
                    'database_engine': str(self.engine.dialect.name)
                }
        except Exception as e:
            return {'error': str(e)}
    
    def _generate_recommendations(self) -> List[IndexRecommendation]:
        """Generate optimization recommendations based on missing indexes and analysis"""
        recommendations = []
        
        # Check for missing critical indexes
        missing_critical = [idx for idx in self.required_indexes if not idx.exists]
        
        for missing_index in missing_critical:
            priority = self._determine_index_priority(missing_index)
            impact = self._estimate_performance_impact(missing_index)
            
            recommendations.append(IndexRecommendation(
                index_name=missing_index.name,
                table=missing_index.table,
                columns=missing_index.columns,
                reason=f"Missing required index for {missing_index.table} table",
                priority=priority,
                estimated_impact=impact
            ))
        
        # Check for additional optimization opportunities
        additional_recs = self._analyze_additional_optimizations()
        recommendations.extend(additional_recs)
        
        return recommendations
    
    def _determine_index_priority(self, index: IndexInfo) -> str:
        """Determine the priority level for a missing index"""
        # Permission-related indexes are high priority
        if 'permission' in index.table:
            return 'high'
        
        # User-group relationship indexes are high priority
        if index.table == 'user_group':
            return 'high'
        
        # File/folder hierarchy indexes are medium priority
        if index.table in ['files', 'folders']:
            return 'medium'
        
        return 'low'
    
    def _estimate_performance_impact(self, index: IndexInfo) -> str:
        """Estimate the performance impact of adding this index"""
        try:
            with self.engine.connect() as conn:
                # Get table size to estimate impact
                result = conn.execute(text(f"SELECT COUNT(*) FROM {index.table}"))
                row_count = result.fetchone()[0]
                
                if row_count > 10000:
                    return "High - Large table will benefit significantly from indexing"
                elif row_count > 1000:
                    return "Medium - Moderate table size will see noticeable improvement"
                else:
                    return "Low - Small table, minimal performance impact"
                    
        except Exception:
            return "Unknown - Unable to determine table size"
    
    def _analyze_additional_optimizations(self) -> List[IndexRecommendation]:
        """Analyze for additional optimization opportunities"""
        recommendations = []
        
        try:
            with self.engine.connect() as conn:
                # Check for tables without proper indexes on foreign keys
                # This is a simplified check - in production, you'd want more sophisticated analysis
                
                # Check if we need composite indexes for common query patterns
                recommendations.append(IndexRecommendation(
                    index_name="idx_files_created_owner",
                    table="files",
                    columns=["created_at", "owner_id"],
                    reason="Optimize file listing queries with date filtering",
                    priority="low",
                    estimated_impact="Medium - Improves file browsing with date filters"
                ))
                
                recommendations.append(IndexRecommendation(
                    index_name="idx_folders_created_parent",
                    table="folders", 
                    columns=["created_at", "parent_id"],
                    reason="Optimize folder listing queries with date filtering",
                    priority="low",
                    estimated_impact="Medium - Improves folder browsing with date filters"
                ))
        
        except Exception as e:
            print(f"⚠️  Error analyzing additional optimizations: {str(e)}")
        
        return recommendations
    
    def _print_summary(self, results: Dict[str, any]):
        """Print verification summary"""
        print("\n" + "=" * 60)
        print("📊 INDEX VERIFICATION SUMMARY")
        print("=" * 60)
        print(f"Total required indexes: {results['total_required']}")
        print(f"✅ Existing indexes: {results['existing_indexes']}")
        print(f"❌ Missing indexes: {results['missing_indexes']}")
        
        if results['database_info'].get('table_record_counts'):
            print(f"\n📈 Database Statistics:")
            for table, count in results['database_info']['table_record_counts'].items():
                print(f"   {table}: {count:,} records")
        
        # Calculate completion percentage
        completion_pct = (results['existing_indexes'] / results['total_required']) * 100
        print(f"\n🎯 Index Coverage: {completion_pct:.1f}%")
        
        if results['missing_indexes'] == 0:
            print("🎉 All required indexes are present!")
        else:
            print(f"⚠️  {results['missing_indexes']} indexes need attention")
    
    def _print_recommendations(self, recommendations: List[IndexRecommendation]):
        """Print optimization recommendations"""
        print("\n" + "=" * 60)
        print("💡 OPTIMIZATION RECOMMENDATIONS")
        print("=" * 60)
        
        # Group by priority
        high_priority = [r for r in recommendations if r.priority == 'high']
        medium_priority = [r for r in recommendations if r.priority == 'medium']
        low_priority = [r for r in recommendations if r.priority == 'low']
        
        for priority_group, title in [(high_priority, "🔴 HIGH PRIORITY"), 
                                     (medium_priority, "🟡 MEDIUM PRIORITY"),
                                     (low_priority, "🟢 LOW PRIORITY")]:
            if priority_group:
                print(f"\n{title}:")
                for rec in priority_group:
                    print(f"  • {rec.index_name}")
                    print(f"    Table: {rec.table}")
                    print(f"    Columns: {', '.join(rec.columns)}")
                    print(f"    Reason: {rec.reason}")
                    print(f"    Impact: {rec.estimated_impact}")
                    print()
    
    def generate_migration_script(self, output_file: Optional[str] = None) -> str:
        """
        Generate an Alembic migration script for missing indexes.
        
        Args:
            output_file: Optional file path to save the migration script
            
        Returns:
            Migration script content as string
        """
        missing_indexes = [idx for idx in self.required_indexes if not idx.exists]
        
        if not missing_indexes:
            print("✅ No missing indexes found. No migration needed.")
            return ""
        
        # Generate migration script content
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        migration_content = f'''"""Add missing performance indexes

Revision ID: auto_generated_{timestamp}
Revises: 
Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Auto-generated by index verification script
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'auto_generated_{timestamp}'
down_revision = None  # Update this with the latest revision
branch_labels = None
depends_on = None


def upgrade():
    """Add missing performance indexes"""
'''
        
        # Add create index statements
        for index in missing_indexes:
            columns_str = "', '".join(index.columns)
            migration_content += f"    op.create_index('{index.name}', '{index.table}', ['{columns_str}'])\n"
        
        migration_content += '''

def downgrade():
    """Remove performance indexes"""
'''
        
        # Add drop index statements
        for index in missing_indexes:
            migration_content += f"    op.drop_index('{index.name}', '{index.table}')\n"
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                f.write(migration_content)
            print(f"📝 Migration script saved to: {output_file}")
        
        return migration_content
    
    def check_index_usage(self) -> Dict[str, any]:
        """
        Check index usage statistics (MySQL/PostgreSQL specific).
        This provides insights into which indexes are actually being used.
        """
        usage_stats = {}
        
        try:
            with self.engine.connect() as conn:
                # MySQL-specific query for index usage
                if 'mysql' in str(self.engine.dialect.name).lower():
                    result = conn.execute(text("""
                        SELECT 
                            TABLE_NAME,
                            INDEX_NAME,
                            CARDINALITY
                        FROM information_schema.STATISTICS 
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND INDEX_NAME IN (
                            'idx_file_permissions_user_file',
                            'idx_file_permissions_group_file', 
                            'idx_folder_permissions_user_folder',
                            'idx_folder_permissions_group_folder',
                            'idx_user_group_user',
                            'idx_user_group_group'
                        )
                        ORDER BY TABLE_NAME, INDEX_NAME
                    """))
                    
                    for row in result:
                        table_name, index_name, cardinality = row
                        if table_name not in usage_stats:
                            usage_stats[table_name] = {}
                        usage_stats[table_name][index_name] = {
                            'cardinality': cardinality,
                            'status': 'exists'
                        }
        
        except Exception as e:
            usage_stats['error'] = f"Unable to retrieve index usage stats: {str(e)}"
        
        return usage_stats


def main():
    """Main function to run index verification"""
    print("🚀 Database Index Verification Tool")
    print("=" * 60)
    
    try:
        # Initialize the verifier
        verifier = IndexVerifier()
        
        # Run verification
        results = verifier.verify_all_indexes()
        
        # Check index usage if available
        print("\n" + "=" * 60)
        print("📈 INDEX USAGE ANALYSIS")
        print("=" * 60)
        usage_stats = verifier.check_index_usage()
        
        if 'error' in usage_stats:
            print(f"⚠️  {usage_stats['error']}")
        else:
            for table, indexes in usage_stats.items():
                print(f"\n📋 {table}:")
                for index_name, stats in indexes.items():
                    print(f"   {index_name}: cardinality={stats.get('cardinality', 'N/A')}")
        
        # Offer to generate migration script
        missing_count = results['missing_indexes']
        if missing_count > 0:
            print(f"\n🔧 Found {missing_count} missing indexes.")
            response = input("Generate Alembic migration script? (y/n): ").lower().strip()
            
            if response == 'y':
                migration_file = f"backend/migrations/versions/auto_add_missing_indexes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
                verifier.generate_migration_script(migration_file)
        
        # Return appropriate exit code
        return 0 if results['missing_indexes'] == 0 else 1
        
    except Exception as e:
        print(f"❌ Error during verification: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)