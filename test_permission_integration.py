#!/usr/bin/env python3
"""
Test script for permission integration
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.user import User
from routes.nas_routes import check_folder_permission

def test_permission_integration():
    """Test the permission integration system"""
    app = create_app()
    
    with app.app_context():
        print("🧪 Testing Permission Integration System")
        print("=" * 50)
        
        # Test 1: Admin user permissions
        print("\n1. Testing Admin User Permissions")
        admin_user = User.query.filter_by(role='ADMIN').first()
        if admin_user:
            print(f"   Admin user found: {admin_user.username}")
            
            # Test various permissions for admin
            test_path = "/"
            permissions = {
                'read': check_folder_permission(admin_user, test_path, 'read'),
                'write': check_folder_permission(admin_user, test_path, 'write'),
                'delete': check_folder_permission(admin_user, test_path, 'delete'),
                'share': check_folder_permission(admin_user, test_path, 'share')
            }
            
            print(f"   Permissions for path '{test_path}':")
            for action, allowed in permissions.items():
                status = "✅ ALLOWED" if allowed else "❌ DENIED"
                print(f"     {action}: {status}")
                
            # Admin should have all permissions
            if all(permissions.values()):
                print("   ✅ Admin permissions test PASSED")
            else:
                print("   ❌ Admin permissions test FAILED")
        else:
            print("   ⚠️  No admin user found in database")
        
        # Test 2: Regular user permissions
        print("\n2. Testing Regular User Permissions")
        regular_user = User.query.filter_by(role='USER').first()
        if regular_user:
            print(f"   Regular user found: {regular_user.username}")
            
            # Test various permissions for regular user
            test_path = "/"
            permissions = {
                'read': check_folder_permission(regular_user, test_path, 'read'),
                'write': check_folder_permission(regular_user, test_path, 'write'),
                'delete': check_folder_permission(regular_user, test_path, 'delete'),
                'share': check_folder_permission(regular_user, test_path, 'share')
            }
            
            print(f"   Permissions for path '{test_path}':")
            for action, allowed in permissions.items():
                status = "✅ ALLOWED" if allowed else "❌ DENIED"
                print(f"     {action}: {status}")
                
            print("   ✅ Regular user permissions test completed")
        else:
            print("   ⚠️  No regular user found in database")
        
        # Test 3: Permission function validation
        print("\n3. Testing Permission Function Validation")
        try:
            # Test with invalid path
            result = check_folder_permission(admin_user, "", 'read')
            print(f"   Empty path test: {result}")
            
            # Test with invalid action
            result = check_folder_permission(admin_user, "/", 'invalid_action')
            print(f"   Invalid action test: {result}")
            
            print("   ✅ Permission function validation completed")
        except Exception as e:
            print(f"   ❌ Permission function validation failed: {str(e)}")
        
        print("\n" + "=" * 50)
        print("🎉 Permission Integration Test Completed!")
        print("\nNext steps:")
        print("1. Start the backend server: python app.py")
        print("2. Test the frontend at http://localhost:5173")
        print("3. Try right-clicking on files/folders to see permission-based context menus")

if __name__ == "__main__":
    test_permission_integration()