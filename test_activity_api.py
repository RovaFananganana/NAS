#!/usr/bin/env python3
"""
Test script for activity logging API endpoints
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models.user import User
from models.user_activity import UserActivity, ActivityType
from services.activity_logger import ActivityLogger

def test_activity_api():
    """Test the activity API endpoints"""
    
    app = create_app()
    
    with app.test_client() as client:
        with app.app_context():
            # Create test user if not exists
            test_user = User.query.filter_by(username='test_user').first()
            if not test_user:
                test_user = User(
                    username='test_user',
                    email='test@example.com',
                    role='user'
                )
                test_user.set_password('test_password')
                db.session.add(test_user)
                db.session.commit()
            
            # Login to get token
            login_response = client.post('/auth/login', 
                json={'username': 'test_user', 'password': 'test_password'})
            
            if login_response.status_code != 200:
                print(f"Login failed: {login_response.get_json()}")
                return False
            
            token = login_response.get_json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}
            
            # Test creating some activities
            activity_logger = ActivityLogger()
            
            # Create test activities
            test_activities = [
                {
                    'action': ActivityType.NAVIGATION.value,
                    'resource': '/documents',
                    'details': {'folder': 'documents'}
                },
                {
                    'action': ActivityType.FILE_DOWNLOAD.value,
                    'resource': '/documents/test.pdf',
                    'details': {'file_size': 1024}
                },
                {
                    'action': ActivityType.FILE_UPLOAD.value,
                    'resource': '/uploads/new_file.txt',
                    'details': {'file_size': 512}
                }
            ]
            
            for activity_data in test_activities:
                activity_logger.log_activity(
                    user_id=test_user.id,
                    **activity_data
                )
            
            print("✅ Test activities created")
            
            # Test GET /api/activities
            response = client.get('/api/activities', headers=headers)
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ GET /api/activities: Found {len(data['activities'])} activities")
                print(f"   Pagination: {data['pagination']}")
            else:
                print(f"❌ GET /api/activities failed: {response.get_json()}")
                return False
            
            # Test GET /api/activities with filters
            response = client.get('/api/activities?action=file_download&limit=5', headers=headers)
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ GET /api/activities with filters: Found {len(data['activities'])} activities")
            else:
                print(f"❌ GET /api/activities with filters failed: {response.get_json()}")
            
            # Test GET /api/activities/stats
            response = client.get('/api/activities/stats', headers=headers)
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ GET /api/activities/stats: {data['total_activities']} total activities")
                print(f"   Success rate: {data['success_rate']}%")
                print(f"   Activities by type: {data['activities_by_type']}")
            else:
                print(f"❌ GET /api/activities/stats failed: {response.get_json()}")
                return False
            
            # Test GET /api/activities/types
            response = client.get('/api/activities/types', headers=headers)
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ GET /api/activities/types: Found {len(data['activity_types'])} activity types")
            else:
                print(f"❌ GET /api/activities/types failed: {response.get_json()}")
            
            # Test period filtering
            response = client.get('/api/activities?period=today', headers=headers)
            if response.status_code == 200:
                data = response.get_json()
                print(f"✅ Period filter (today): Found {len(data['activities'])} activities")
            else:
                print(f"❌ Period filter failed: {response.get_json()}")
            
            # Test POST /api/activities (manual logging)
            response = client.post('/api/activities', 
                headers=headers,
                json={
                    'action': ActivityType.FAVORITE_ADD.value,
                    'resource': '/documents/important',
                    'details': {'folder_name': 'important'}
                })
            if response.status_code == 201:
                print("✅ POST /api/activities: Manual activity logged successfully")
            else:
                print(f"❌ POST /api/activities failed: {response.get_json()}")
            
            print("\n🎉 All activity API tests completed successfully!")
            return True

if __name__ == "__main__":
    test_activity_api()