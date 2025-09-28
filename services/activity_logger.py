from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from flask import request
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import joinedload
from extensions import db
from models.user_activity import UserActivity, ActivityType
from models.user import User

class ActivityLogError(Exception):
    """Custom exception for activity logging errors"""
    def __init__(self, message: str, status_code: int = 500, code: str = 'ACTIVITY_LOG_ERROR'):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(self.message)

class ActivityLogger:
    """Service class for logging and retrieving user activities"""
    
    def __init__(self):
        self.db = db

    def log_activity(self, user_id: int, action: str, resource: str = None, 
                    details: Dict[str, Any] = None, success: bool = True,
                    ip_address: str = None, user_agent: str = None) -> UserActivity:
        """
        Log user activity with timestamp and metadata
        
        Args:
            user_id: ID of the user performing the action
            action: Type of action (should match ActivityType enum values)
            resource: Resource being acted upon (file path, folder name, etc.)
            details: Additional metadata as dictionary
            success: Whether the action was successful
            ip_address: IP address of the user (auto-detected if not provided)
            user_agent: User agent string (auto-detected if not provided)
            
        Returns:
            UserActivity: The created activity record
            
        Raises:
            ActivityLogError: If logging fails
        """
        try:
            # Auto-detect IP and user agent from request context if not provided
            if ip_address is None and request:
                ip_address = request.remote_addr
            if user_agent is None and request:
                user_agent = request.headers.get('User-Agent')

            # Validate action type
            valid_actions = [activity_type.value for activity_type in ActivityType]
            if action not in valid_actions:
                raise ActivityLogError(f"Invalid action type: {action}", 400, 'INVALID_ACTION_TYPE')

            # Create activity record
            activity = UserActivity(
                user_id=user_id,
                action=action,
                resource=resource,
                details=details,
                success=success,
                ip_address=ip_address,
                user_agent=user_agent
            )

            self.db.session.add(activity)
            self.db.session.commit()
            
            return activity

        except Exception as e:
            self.db.session.rollback()
            if isinstance(e, ActivityLogError):
                raise
            raise ActivityLogError(f"Failed to log activity: {str(e)}", 500, 'LOG_ACTIVITY_FAILED')

    def get_user_activities(self, user_id: int, filters: Dict[str, Any] = None, 
                           page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """
        Retrieve paginated user activities with optional filters
        
        Args:
            user_id: ID of the user
            filters: Dictionary of filters (period, action, success, etc.)
            page: Page number (1-based)
            limit: Number of items per page
            
        Returns:
            Dictionary containing activities and pagination info
            
        Raises:
            ActivityLogError: If retrieval fails
        """
        try:
            if filters is None:
                filters = {}

            # Build base query
            query = UserActivity.query.filter(UserActivity.user_id == user_id)
            
            # Apply filters
            query = self._apply_filters(query, filters)
            
            # Order by created_at descending (most recent first)
            query = query.order_by(desc(UserActivity.created_at))
            
            # Apply pagination
            offset = (page - 1) * limit
            total_count = query.count()
            activities = query.offset(offset).limit(limit).options(joinedload(UserActivity.user)).all()
            
            # Calculate pagination info
            total_pages = (total_count + limit - 1) // limit
            has_next = page < total_pages
            has_prev = page > 1
            
            return {
                'activities': [activity.to_dict() for activity in activities],
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_prev': has_prev
                }
            }

        except Exception as e:
            if isinstance(e, ActivityLogError):
                raise
            raise ActivityLogError(f"Failed to retrieve activities: {str(e)}", 500, 'GET_ACTIVITIES_FAILED')

    def get_activities_by_period(self, user_id: int, period_type: str, 
                                custom_date: str = None) -> List[UserActivity]:
        """
        Get activities filtered by time period
        
        Args:
            user_id: ID of the user
            period_type: Type of period ('today', 'week', 'month', 'custom')
            custom_date: Specific date for custom period (YYYY-MM-DD format)
            
        Returns:
            List of UserActivity objects
            
        Raises:
            ActivityLogError: If retrieval fails
        """
        try:
            now = datetime.now(timezone.utc)
            
            if period_type == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif period_type == 'week':
                start_date = now - timedelta(days=7)
                end_date = now
            elif period_type == 'month':
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            elif period_type == 'custom' and custom_date:
                try:
                    custom_datetime = datetime.strptime(custom_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    start_date = custom_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = custom_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                except ValueError:
                    raise ActivityLogError("Invalid date format. Use YYYY-MM-DD", 400, 'INVALID_DATE_FORMAT')
            else:
                raise ActivityLogError(f"Invalid period type: {period_type}", 400, 'INVALID_PERIOD_TYPE')

            activities = UserActivity.query.filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.created_at >= start_date,
                    UserActivity.created_at <= end_date
                )
            ).order_by(desc(UserActivity.created_at)).options(joinedload(UserActivity.user)).all()

            return activities

        except Exception as e:
            if isinstance(e, ActivityLogError):
                raise
            raise ActivityLogError(f"Failed to get activities by period: {str(e)}", 500, 'GET_PERIOD_ACTIVITIES_FAILED')

    def get_activity_statistics(self, user_id: int, period_days: int = 30) -> Dict[str, Any]:
        """
        Get activity statistics for dashboard
        
        Args:
            user_id: ID of the user
            period_days: Number of days to include in statistics
            
        Returns:
            Dictionary containing activity statistics
        """
        try:
            start_date = datetime.now(timezone.utc) - timedelta(days=period_days)
            
            # Total activities count
            total_activities = UserActivity.query.filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.created_at >= start_date
                )
            ).count()
            
            # Activities by type
            activities_by_type = db.session.query(
                UserActivity.action,
                func.count(UserActivity.id).label('count')
            ).filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.created_at >= start_date
                )
            ).group_by(UserActivity.action).all()
            
            # Success rate
            success_count = UserActivity.query.filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.created_at >= start_date,
                    UserActivity.success == True
                )
            ).count()
            
            success_rate = (success_count / total_activities * 100) if total_activities > 0 else 0
            
            # Recent activities (last 5)
            recent_activities = UserActivity.query.filter(
                UserActivity.user_id == user_id
            ).order_by(desc(UserActivity.created_at)).limit(5).options(joinedload(UserActivity.user)).all()
            
            return {
                'total_activities': total_activities,
                'activities_by_type': {action: count for action, count in activities_by_type},
                'success_rate': round(success_rate, 2),
                'recent_activities': [activity.to_dict() for activity in recent_activities],
                'period_days': period_days
            }

        except Exception as e:
            raise ActivityLogError(f"Failed to get activity statistics: {str(e)}", 500, 'GET_STATISTICS_FAILED')

    def _apply_filters(self, query, filters: Dict[str, Any]):
        """Apply filters to the query"""
        
        # Filter by action type
        if 'action' in filters and filters['action']:
            query = query.filter(UserActivity.action == filters['action'])
        
        # Filter by success status
        if 'success' in filters and filters['success'] is not None:
            query = query.filter(UserActivity.success == filters['success'])
        
        # Filter by date range
        if 'start_date' in filters and filters['start_date']:
            try:
                start_date = datetime.strptime(filters['start_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                query = query.filter(UserActivity.created_at >= start_date)
            except ValueError:
                pass  # Ignore invalid date format
        
        if 'end_date' in filters and filters['end_date']:
            try:
                end_date = datetime.strptime(filters['end_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                query = query.filter(UserActivity.created_at <= end_date)
            except ValueError:
                pass  # Ignore invalid date format
        
        # Filter by resource (partial match)
        if 'resource' in filters and filters['resource']:
            query = query.filter(UserActivity.resource.ilike(f"%{filters['resource']}%"))
        
        return query

    def cleanup_old_activities(self, days_to_keep: int = 90) -> int:
        """
        Clean up old activity records to maintain database performance
        
        Args:
            days_to_keep: Number of days of activities to keep
            
        Returns:
            Number of deleted records
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            deleted_count = UserActivity.query.filter(
                UserActivity.created_at < cutoff_date
            ).delete()
            
            self.db.session.commit()
            
            return deleted_count

        except Exception as e:
            self.db.session.rollback()
            raise ActivityLogError(f"Failed to cleanup old activities: {str(e)}", 500, 'CLEANUP_FAILED')