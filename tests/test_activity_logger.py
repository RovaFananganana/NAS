"""
Unit tests for ActivityLogger service
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from services.activity_logger import ActivityLogger, ActivityLogError
from models.user_activity import UserActivity, ActivityType
from models.user import User


class TestActivityLogger:
    """Test cases for ActivityLogger service"""
    
    def test_init(self, app_context):
        """Test ActivityLogger initialization"""
        logger = ActivityLogger()
        assert logger.db is not None
    
    def test_log_activity_success(self, db_session, test_user):
        """Test successful activity logging"""
        logger = ActivityLogger()
        
        activity = logger.log_activity(
            user_id=test_user.id,
            action=ActivityType.FILE_DOWNLOAD.value,
            resource='/test/file.txt',
            details={'file_size': 1024},
            success=True,
            ip_address='192.168.1.1',
            user_agent='Test Browser'
        )
        
        assert activity is not None
        assert activity.user_id == test_user.id
        assert activity.action == ActivityType.FILE_DOWNLOAD.value
        assert activity.resource == '/test/file.txt'
        assert activity.details == {'file_size': 1024}
        assert activity.success is True
        assert activity.ip_address == '192.168.1.1'
        assert activity.user_agent == 'Test Browser'
        assert activity.created_at is not None
    
    def test_log_activity_invalid_action(self, db_session, test_user):
        """Test logging activity with invalid action type"""
        logger = ActivityLogger()
        
        with pytest.raises(ActivityLogError) as exc_info:
            logger.log_activity(
                user_id=test_user.id,
                action='invalid_action',
                resource='/test/file.txt'
            )
        
        assert exc_info.value.code == 'INVALID_ACTION_TYPE'
        assert exc_info.value.status_code == 400
    
    @patch('flask.request')
    def test_log_activity_auto_detect_request_info(self, mock_request, db_session, test_user):
        """Test auto-detection of IP and user agent from request"""
        mock_request.remote_addr = '10.0.0.1'
        mock_request.headers = {'User-Agent': 'Auto-detected Browser'}
        
        logger = ActivityLogger()
        
        activity = logger.log_activity(
            user_id=test_user.id,
            action=ActivityType.NAVIGATION.value,
            resource='/dashboard'
        )
        
        assert activity.ip_address == '10.0.0.1'
        assert activity.user_agent == 'Auto-detected Browser'
    
    def test_log_activity_database_error(self, db_session, test_user):
        """Test handling of database errors during logging"""
        logger = ActivityLogger()
        
        # Mock database session to raise an exception
        with patch.object(logger.db.session, 'add', side_effect=Exception('DB Error')):
            with pytest.raises(ActivityLogError) as exc_info:
                logger.log_activity(
                    user_id=test_user.id,
                    action=ActivityType.LOGIN.value
                )
            
            assert exc_info.value.code == 'LOG_ACTIVITY_FAILED'
            assert 'DB Error' in exc_info.value.message
    
    def test_get_user_activities_basic(self, db_session, test_user, sample_activities):
        """Test basic user activities retrieval"""
        logger = ActivityLogger()
        
        result = logger.get_user_activities(user_id=test_user.id)
        
        assert 'activities' in result
        assert 'pagination' in result
        assert len(result['activities']) == len(sample_activities)
        assert result['pagination']['total_count'] == len(sample_activities)
        assert result['pagination']['page'] == 1
        assert result['pagination']['limit'] == 20
    
    def test_get_user_activities_pagination(self, db_session, test_user, sample_activities):
        """Test activities retrieval with pagination"""
        logger = ActivityLogger()
        
        # Test first page with limit 2
        result = logger.get_user_activities(
            user_id=test_user.id,
            page=1,
            limit=2
        )
        
        assert len(result['activities']) == 2
        assert result['pagination']['page'] == 1
        assert result['pagination']['limit'] == 2
        assert result['pagination']['total_count'] == len(sample_activities)
        assert result['pagination']['has_next'] is True
        assert result['pagination']['has_prev'] is False
        
        # Test second page
        result = logger.get_user_activities(
            user_id=test_user.id,
            page=2,
            limit=2
        )
        
        assert len(result['activities']) == 2
        assert result['pagination']['page'] == 2
        assert result['pagination']['has_prev'] is True
    
    def test_get_user_activities_with_filters(self, db_session, test_user, sample_activities):
        """Test activities retrieval with filters"""
        logger = ActivityLogger()
        
        # Filter by action type
        result = logger.get_user_activities(
            user_id=test_user.id,
            filters={'action': ActivityType.FILE_DOWNLOAD.value}
        )
        
        assert len(result['activities']) == 1
        assert result['activities'][0]['action'] == ActivityType.FILE_DOWNLOAD.value
        
        # Filter by success status
        result = logger.get_user_activities(
            user_id=test_user.id,
            filters={'success': False}
        )
        
        assert len(result['activities']) == 1
        assert result['activities'][0]['success'] is False
    
    def test_get_activities_by_period_today(self, db_session, test_user, sample_activities):
        """Test getting activities for today"""
        logger = ActivityLogger()
        
        activities = logger.get_activities_by_period(
            user_id=test_user.id,
            period_type='today'
        )
        
        # All sample activities should be from today
        assert len(activities) == len(sample_activities)
    
    def test_get_activities_by_period_week(self, db_session, test_user, sample_activities):
        """Test getting activities for the past week"""
        logger = ActivityLogger()
        
        activities = logger.get_activities_by_period(
            user_id=test_user.id,
            period_type='week'
        )
        
        assert len(activities) == len(sample_activities)
    
    def test_get_activities_by_period_custom(self, db_session, test_user, sample_activities):
        """Test getting activities for a custom date"""
        logger = ActivityLogger()
        
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        activities = logger.get_activities_by_period(
            user_id=test_user.id,
            period_type='custom',
            custom_date=today
        )
        
        assert len(activities) == len(sample_activities)
    
    def test_get_activities_by_period_invalid_date(self, db_session, test_user):
        """Test getting activities with invalid custom date"""
        logger = ActivityLogger()
        
        with pytest.raises(ActivityLogError) as exc_info:
            logger.get_activities_by_period(
                user_id=test_user.id,
                period_type='custom',
                custom_date='invalid-date'
            )
        
        assert exc_info.value.code == 'INVALID_DATE_FORMAT'
        assert exc_info.value.status_code == 400
    
    def test_get_activities_by_period_invalid_type(self, db_session, test_user):
        """Test getting activities with invalid period type"""
        logger = ActivityLogger()
        
        with pytest.raises(ActivityLogError) as exc_info:
            logger.get_activities_by_period(
                user_id=test_user.id,
                period_type='invalid_period'
            )
        
        assert exc_info.value.code == 'INVALID_PERIOD_TYPE'
        assert exc_info.value.status_code == 400
    
    def test_get_activity_statistics(self, db_session, test_user, sample_activities):
        """Test getting activity statistics"""
        logger = ActivityLogger()
        
        stats = logger.get_activity_statistics(user_id=test_user.id)
        
        assert 'total_activities' in stats
        assert 'activities_by_type' in stats
        assert 'success_rate' in stats
        assert 'recent_activities' in stats
        assert 'period_days' in stats
        
        assert stats['total_activities'] == len(sample_activities)
        assert stats['success_rate'] == 80.0  # 4 out of 5 successful
        assert len(stats['recent_activities']) <= 5
    
    def test_apply_filters_action(self, db_session, test_user, sample_activities):
        """Test _apply_filters method with action filter"""
        logger = ActivityLogger()
        
        query = UserActivity.query.filter(UserActivity.user_id == test_user.id)
        filtered_query = logger._apply_filters(query, {'action': ActivityType.LOGIN.value})
        
        results = filtered_query.all()
        assert len(results) == 1
        assert results[0].action == ActivityType.LOGIN.value
    
    def test_apply_filters_success(self, db_session, test_user, sample_activities):
        """Test _apply_filters method with success filter"""
        logger = ActivityLogger()
        
        query = UserActivity.query.filter(UserActivity.user_id == test_user.id)
        filtered_query = logger._apply_filters(query, {'success': False})
        
        results = filtered_query.all()
        assert len(results) == 1
        assert results[0].success is False
    
    def test_apply_filters_date_range(self, db_session, test_user, sample_activities):
        """Test _apply_filters method with date range"""
        logger = ActivityLogger()
        
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d')
        
        query = UserActivity.query.filter(UserActivity.user_id == test_user.id)
        filtered_query = logger._apply_filters(query, {
            'start_date': today,
            'end_date': tomorrow
        })
        
        results = filtered_query.all()
        assert len(results) == len(sample_activities)
    
    def test_apply_filters_resource(self, db_session, test_user, sample_activities):
        """Test _apply_filters method with resource filter"""
        logger = ActivityLogger()
        
        query = UserActivity.query.filter(UserActivity.user_id == test_user.id)
        filtered_query = logger._apply_filters(query, {'resource': 'documents'})
        
        results = filtered_query.all()
        assert len(results) == 2  # Navigation and download in documents
    
    def test_cleanup_old_activities(self, db_session, test_user):
        """Test cleanup of old activities"""
        logger = ActivityLogger()
        
        # Create old activity (100 days ago)
        old_date = datetime.now(timezone.utc) - timedelta(days=100)
        old_activity = UserActivity(
            user_id=test_user.id,
            action=ActivityType.LOGIN.value,
            created_at=old_date
        )
        db_session.add(old_activity)
        db_session.commit()
        
        # Create recent activity
        recent_activity = UserActivity(
            user_id=test_user.id,
            action=ActivityType.LOGOUT.value,
            created_at=datetime.now(timezone.utc)
        )
        db_session.add(recent_activity)
        db_session.commit()
        
        # Cleanup activities older than 90 days
        deleted_count = logger.cleanup_old_activities(days_to_keep=90)
        
        assert deleted_count == 1
        
        # Verify only recent activity remains
        remaining_activities = UserActivity.query.filter_by(user_id=test_user.id).all()
        assert len(remaining_activities) == 1
        assert remaining_activities[0].action == ActivityType.LOGOUT.value
    
    def test_cleanup_old_activities_database_error(self, db_session, test_user):
        """Test cleanup handling database errors"""
        logger = ActivityLogger()
        
        with patch.object(logger.db.session, 'commit', side_effect=Exception('DB Error')):
            with pytest.raises(ActivityLogError) as exc_info:
                logger.cleanup_old_activities()
            
            assert exc_info.value.code == 'CLEANUP_FAILED'
            assert 'DB Error' in exc_info.value.message


class TestActivityLogError:
    """Test cases for ActivityLogError exception"""
    
    def test_activity_log_error_default(self):
        """Test ActivityLogError with default values"""
        error = ActivityLogError("Test error")
        
        assert error.message == "Test error"
        assert error.status_code == 500
        assert error.code == 'ACTIVITY_LOG_ERROR'
        assert str(error) == "Test error"
    
    def test_activity_log_error_custom(self):
        """Test ActivityLogError with custom values"""
        error = ActivityLogError("Custom error", 400, 'CUSTOM_ERROR')
        
        assert error.message == "Custom error"
        assert error.status_code == 400
        assert error.code == 'CUSTOM_ERROR'
        assert str(error) == "Custom error"