#!/usr/bin/env python3
"""
Simple CLI wrapper for index verification

Usage:
    python check_indexes.py                    # Run verification
    python check_indexes.py --generate-migration  # Generate migration for missing indexes
    python check_indexes.py --help            # Show help
"""

import sys
import argparse
from verify_indexes import IndexVerifier, main as verify_main


def main():
    parser = argparse.ArgumentParser(
        description="Database Index Verification Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_indexes.py                     # Run full verification
  python check_indexes.py --generate-migration # Generate migration script
  python check_indexes.py --quiet             # Run with minimal output
        """
    )
    
    parser.add_argument(
        '--generate-migration', 
        action='store_true',
        help='Generate Alembic migration script for missing indexes'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true', 
        help='Minimal output mode'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='Output file for migration script'
    )
    
    args = parser.parse_args()
    
    try:
        verifier = IndexVerifier()
        
        if args.generate_migration:
            # Just generate migration script
            if not args.quiet:
                print("🔧 Generating migration script for missing indexes...")
            
            results = verifier.verify_all_indexes()
            if results['missing_indexes'] > 0:
                output_file = args.output or f"auto_add_missing_indexes.py"
                migration_content = verifier.generate_migration_script(output_file)
                
                if not args.quiet:
                    print(f"✅ Migration script generated: {output_file}")
                    print(f"📝 Found {results['missing_indexes']} missing indexes")
            else:
                if not args.quiet:
                    print("✅ No missing indexes found. No migration needed.")
        else:
            # Run full verification
            return verify_main()
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())