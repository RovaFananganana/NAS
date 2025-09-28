#!/usr/bin/env python3
"""
Script to create monthly partitions for user_activities table.
This should be run monthly or can be automated via cron job.
"""

import sys
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
from extensions import db

def create_partition_for_month(year, month):
    """Create a partition for the specified year and month"""
    
    # Calculate start and end dates for the partition
    start_date = datetime(year, month, 1)
    end_date = start_date + relativedelta(months=1)
    
    partition_name = f"user_activities_{year:04d}_{month:02d}"
    
    # Check if partition already exists
    check_query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = %s
        );
    """
    
    result = db.session.execute(check_query, (partition_name,)).fetchone()
    
    if result[0]:
        print(f"Partition {partition_name} already exists, skipping...")
        return False
    
    # Create the partition
    create_partition_sql = f"""
        CREATE TABLE {partition_name} PARTITION OF user_activities
        FOR VALUES FROM ('{start_date.strftime('%Y-%m-%d')}') TO ('{end_date.strftime('%Y-%m-%d')}');
    """
    
    try:
        db.session.execute(create_partition_sql)
        db.session.commit()
        print(f"Created partition {partition_name} for period {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error creating partition {partition_name}: {str(e)}")
        return False

def create_future_partitions(months_ahead=6):
    """Create partitions for the next N months"""
    
    current_date = datetime.now()
    created_count = 0
    
    for i in range(months_ahead):
        future_date = current_date + relativedelta(months=i)
        if create_partition_for_month(future_date.year, future_date.month):
            created_count += 1
    
    print(f"Created {created_count} new partitions")
    return created_count

def cleanup_old_partitions(months_to_keep=12):
    """Remove partitions older than specified months (optional cleanup)"""
    
    cutoff_date = datetime.now() - relativedelta(months=months_to_keep)
    
    # Get list of existing partitions
    query = """
        SELECT schemaname, tablename 
        FROM pg_tables 
        WHERE tablename LIKE 'user_activities_____%%'
        ORDER BY tablename;
    """
    
    partitions = db.session.execute(query).fetchall()
    dropped_count = 0
    
    for partition in partitions:
        table_name = partition[1]
        
        # Extract year and month from table name (format: user_activities_YYYY_MM)
        try:
            parts = table_name.split('_')
            if len(parts) >= 4:
                year = int(parts[2])
                month = int(parts[3])
                partition_date = datetime(year, month, 1)
                
                if partition_date < cutoff_date:
                    drop_sql = f"DROP TABLE {table_name};"
                    try:
                        db.session.execute(drop_sql)
                        db.session.commit()
                        print(f"Dropped old partition {table_name}")
                        dropped_count += 1
                    except Exception as e:
                        db.session.rollback()
                        print(f"Error dropping partition {table_name}: {str(e)}")
        except (ValueError, IndexError):
            print(f"Skipping partition with unexpected name format: {table_name}")
    
    print(f"Dropped {dropped_count} old partitions")
    return dropped_count

if __name__ == "__main__":
    with app.app_context():
        print("Creating future partitions for user_activities table...")
        
        # Create partitions for the next 6 months
        create_future_partitions(6)
        
        # Optionally cleanup old partitions (uncomment if needed)
        # cleanup_old_partitions(12)
        
        print("Partition management completed.")