"""
Unit tests for activity API routes
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from models.user_activity import ActivityType
from services.activity_logger import ActivityLogError


class TestActivityRoutes:
    """Test cases for activity API routes"""
    
    def test_get_activities_success(self, client, auth_headers, sample_activities):
        """Test successful activities retrieval"""
        response = client.get('/api/activities', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'activities' in data
        assert 'pagination' in data
        assert len(data['activities']) == len(sample_activities)
        assert data['pagination']['total_count'] == len(sample_activities)
    
    def test_get_activities_with_pagination(self, client, auth_headers, sample_activities):
        """Test activities retrieval with pagination parameters"""
        response = client.get('/api/activities?page=1&limit=2', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert len(data['activities']) == 2
        assert data['pagination']['page'] == 1
        assert data['pagination']['limit'] == 2
        assert data['pagination']['has_next'] is True
    
    def test_get_activities_with_filters(self, client, auth_headers, sample_activities):
        """Test activities retrieval with filters"""
        response = client.get(
            f'/api/activities?action={ActivityType.FILE_DOWNLOAD.value}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert len(data['activities']) == 1
        assert data['activities'][0]['action'] == ActivityType.FILE_DOWNLOAD.value
    
    def test_get_activities_period_today(self, client, auth_headers, sample_activities):
        """Test activities retrieval with period filter"""
        response = client.get('/api/activities?period=today', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'activities' in data
        assert 'pagination' in data
    
    def test_get_activities_period_custom_valid(self, client, auth_headers, sample_activities):
        """Test activities retrieval with custom period"""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        response = client.get(
            f'/api/activities?period=custom&date={today}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'activities' in data
        assert 'pagination' in data
    
    def test_get_activities_period_custom_missing_date(self, client, auth_headers):
        """Test activities retrieval with custom period but missing date"""
        response = client.get('/api/activities?period=custom', headers=auth_headers)
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Custom date required' in data['error']
    
    def test_get_activities_invalid_page(self, client, auth_headers):
        """Test activities retrieval with invalid page parameter"""
        response = client.get('/api/activities?page=0', headers=auth_headers)
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Page must be >= 1' in data['error']
    
    def test_get_activities_invalid_limit(self, client, auth_headers):
        """Test activities retrieval with invalid limit parameter"""
        response = client.get('/api/activities?limit=0', headers=auth_headers)
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Limit must be >= 1' in data['error']
    
    def test_get_activities_unauthorized(self, client):
        """Test activities retrieval without authentication"""
        response = client.get('/api/activities')
        
        assert response.status_code == 401
    
    @patch('services.activity_logger.ActivityLogger.get_user_activities')
    def test_get_activities_service_error(self, mock_get_activities, client, auth_headers):
        """Test activities retrieval with service error"""
        mock_get_activities.side_effect = ActivityLogError(
            "Service error", 500, 'SERVICE_ERROR'
        )
        
        response = client.get('/api/activities', headers=auth_headers)
        
        assert response.status_code == 500
        data = response.get_json()
        
        assert data['error'] == "Service error"
        assert data['code'] == 'SERVICE_ERROR'
    
    def test_get_activity_stats_success(self, client, auth_headers, sample_activities):
        """Test successful activity statistics retrieval"""
        response = client.get('/api/activities/stats', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'total_activities' in data
        assert 'activities_by_type' in data
        assert 'success_rate' in data
        assert 'recent_activities' in data
        assert 'period_days' in data
    
    def test_get_activity_stats_custom_period(self, client, auth_headers, sample_activities):
        """Test activity statistics with custom period"""
        response = client.get('/api/activities/stats?period_days=7', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['period_days'] == 7
    
    def test_get_activity_stats_invalid_period(self, client, auth_headers):
        """Test activity statistics with invalid period"""
        response = client.get('/api/activities/stats?period_days=400', headers=auth_headers)
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Period days must be between 1 and 365' in data['error']
    
    def test_get_activity_types_success(self, client, auth_headers):
        """Test successful activity types retrieval"""
        response = client.get('/api/activities/types', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'activity_types' in data
        assert len(data['activity_types']) > 0
        
        # Check structure of activity types
        activity_type = data['activity_types'][0]
        assert 'value' in activity_type
        assert 'display_name' in activity_type
    
    def test_log_activity_success(self, client, auth_headers):
        """Test successful manual activity logging"""
        activity_data = {
            'action': ActivityType.NAVIGATION.value,
            'resource': '/test/path',
            'details': {'test': 'data'},
            'success': True
        }
        
        response = client.post(
            '/api/activities',
            headers=auth_headers,
            json=activity_data
        )
        
        assert response.status_code == 201
        data = response.get_json()
        
        assert 'message' in data
        assert 'activity' in data
        assert data['activity']['action'] == ActivityType.NAVIGATION.value
        assert data['activity']['resource'] == '/test/path'
    
    def test_log_activity_missing_action(self, client, auth_headers):
        """Test manual activity logging without action"""
        activity_data = {
            'resource': '/test/path'
        }
        
        response = client.post(
            '/api/activities',
            headers=auth_headers,
            json=activity_data
        )
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Action is required' in data['error']
    
    def test_log_activity_invalid_action(self, client, auth_headers):
        """Test manual activity logging with invalid action"""
        activity_data = {
            'action': 'invalid_action',
            'resource': '/test/path'
        }
        
        response = client.post(
            '/api/activities',
            headers=auth_headers,
            json=activity_data
        )
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Invalid action type' in data['error']
        assert 'valid_actions' in data
    
    def test_log_activity_no_json(self, client, auth_headers):
        """Test manual activity logging without JSON data"""
        response = client.post('/api/activities', headers=auth_headers)
        
        assert response.status_code == 400
        data = response.get_json()
        
        assert 'error' in data
        assert 'Action is required' in data['error']
    
    def test_get_activity_detail_success(self, client, auth_headers, sample_activities):
        """Test successful activity detail retrieval"""
        activity_id = sample_activities[0].id
        
        response = client.get(f'/api/activities/{activity_id}', headers=auth_headers)
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'activity' in data
        assert data['activity']['id'] == activity_id
    
    def test_get_activity_detail_not_found(self, client, auth_headers):
        """Test activity detail retrieval for non-existent activity"""
        response = client.get('/api/activities/99999', headers=auth_headers)
        
        assert response.status_code == 404
        data = response.get_json()
        
        assert 'error' in data
        assert 'Activity not found' in data['error']
    
    def test_get_activity_detail_other_user(self, client, auth_headers, admin_user, db_session):
        """Test activity detail retrieval for activity of another user"""
        from models.user_activity import UserActivity
        
        # Create activity for admin user
        admin_activity = UserActivity(
            user_id=admin_user.id,
            action=ActivityType.LOGIN.value
        )
        db_session.add(admin_activity)
        db_session.commit()
        
        # Try to access admin's activity with regular user auth
        response = client.get(f'/api/activities/{admin_activity.id}', headers=auth_headers)
        
        assert response.status_code == 404
        data = response.get_json()
        
        assert 'error' in data
        assert 'Activity not found' in data['error']
    
    @patch('services.activity_logger.ActivityLogger.log_activity')
    def test_log_activity_service_error(self, mock_log_activity, client, auth_headers):
        """Test manual activity logging with service error"""
        mock_log_activity.side_effect = ActivityLogError(
            "Logging failed", 500, 'LOG_FAILED'
        )
        
        activity_data = {
            'action': ActivityType.NAVIGATION.value,
            'resource': '/test/path'
        }
        
        response = client.post(
            '/api/activities',
            headers=auth_headers,
            json=activity_data
        )
        
        assert response.status_code == 500
        data = response.get_json()
        
        assert data['error'] == "Logging failed"
        assert data['code'] == 'LOG_FAILED'
    
    def test_activity_log_error_handler(self, client, auth_headers):
        """Test ActivityLogError exception handler"""
        with patch('routes.activity_routes.activity_logger.get_user_activities') as mock_get:
            mock_get.side_effect = ActivityLogError(
                "Test error", 400, 'TEST_ERROR'
            )
            
            response = client.get('/api/activities', headers=auth_headers)
            
            assert response.status_code == 400
            data = response.get_json()
            
            assert data['error'] == "Test error"
            assert data['code'] == 'TEST_ERROR'
            assert 'timestamp' in data


class TestActivityMiddleware:
    """Test cases for activity logging middleware"""
    
    def test_log_user_activity_decorator_success(self, app_context, test_user):
        """Test activity logging decorator with successful operation"""
        from routes.activity_routes import log_user_activity
        from flask_jwt_extended import create_access_token
        
        # Mock function to decorate
        @log_user_activity('test_action')
        def test_function():
            return MagicMock(status_code=200)
        
        with patch('flask_jwt_extended.get_jwt_identity', return_value=test_user.id):
            with patch('services.activity_logger.ActivityLogger.log_activity') as mock_log:
                result = test_function()
                
                assert result.status_code == 200
                mock_log.assert_called_once()
                
                # Check the call arguments
                call_args = mock_log.call_args
                assert call_args[1]['user_id'] == test_user.id
                assert call_args[1]['action'] == 'test_action'
                assert call_args[1]['success'] is True
    
    def test_log_user_activity_decorator_failure(self, app_context, test_user):
        """Test activity logging decorator with failed operation"""
        from routes.activity_routes import log_user_activity
        
        # Mock function that raises an exception
        @log_user_activity('test_action')
        def test_function():
            raise ValueError("Test error")
        
        with patch('flask_jwt_extended.get_jwt_identity', return_value=test_user.id):
            with patch('services.activity_logger.ActivityLogger.log_activity') as mock_log:
                with pytest.raises(ValueError):
                    test_function()
                
                # Should log the failed activity
                mock_log.assert_called()
                
                # Check the call arguments for failure logging
                call_args = mock_log.call_args
                assert call_args[1]['user_id'] == test_user.id
                assert call_args[1]['action'] == 'test_action'
                assert call_args[1]['success'] is False
                assert 'Test error' in str(call_args[1]['details'])
    
    def test_log_user_activity_decorator_no_auth(self, app_context):
        """Test activity logging decorator without authentication"""
        from routes.activity_routes import log_user_activity
        
        @log_user_activity('test_action')
        def test_function():
            return MagicMock(status_code=200)
        
        with patch('flask_jwt_extended.get_jwt_identity', return_value=None):
            with patch('services.activity_logger.ActivityLogger.log_activity') as mock_log:
                result = test_function()
                
                assert result.status_code == 200
                # Should not log activity if no user is authenticated
                mock_log.assert_not_called()
    
    def test_log_user_activity_decorator_with_resource_getter(self, app_context, test_user):
        """Test activity logging decorator with resource getter function"""
        from routes.activity_routes import log_user_activity
        
        def get_resource():
            return "/test/resource"
        
        def get_details():
            return {"test": "details"}
        
        @log_user_activity('test_action', get_resource=get_resource, get_details=get_details)
        def test_function():
            return MagicMock(status_code=200)
        
        with patch('flask_jwt_extended.get_jwt_identity', return_value=test_user.id):
            with patch('services.activity_logger.ActivityLogger.log_activity') as mock_log:
                result = test_function()
                
                assert result.status_code == 200
                mock_log.assert_called_once()
                
                # Check the call arguments
                call_args = mock_log.call_args
                assert call_args[1]['resource'] == "/test/resource"
                assert call_args[1]['details'] == {"test": "details"}
    
    def test_log_user_activity_decorator_logging_error(self, app_context, test_user):
        """Test activity logging decorator when logging itself fails"""
        from routes.activity_routes import log_user_activity
        
        @log_user_activity('test_action')
        def test_function():
            return MagicMock(status_code=200)
        
        with patch('flask_jwt_extended.get_jwt_identity', return_value=test_user.id):
            with patch('services.activity_logger.ActivityLogger.log_activity', side_effect=Exception("Log error")):
                # Should not raise exception even if logging fails
                result = test_function()
                assert result.status_code == 200