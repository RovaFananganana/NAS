from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from services.activity_logger import ActivityLogger, ActivityLogError
from models.user_activity import ActivityType, UserActivity
from models.user import User

activity_bp = Blueprint('activity', __name__)
activity_logger = ActivityLogger()

@activity_bp.errorhandler(ActivityLogError)
def handle_activity_log_error(error):
    """Handle ActivityLogError exceptions"""
    return jsonify({
        'error': error.message,
        'code': error.code,
        'timestamp': ActivityLogger().db.func.now()
    }), error.status_code

@activity_bp.route('/activities', methods=['GET'])
@jwt_required()
def get_user_activities():
    """
    Get user activities with optional filtering and pagination
    
    Query parameters:
    - page: Page number (default: 1)
    - limit: Items per page (default: 20, max: 100)
    - period: Period filter ('today', 'week', 'month', 'custom')
    - date: Custom date for period filter (YYYY-MM-DD)
    - action: Filter by action type
    - success: Filter by success status (true/false)
    - start_date: Start date filter (YYYY-MM-DD)
    - end_date: End date filter (YYYY-MM-DD)
    - resource: Filter by resource (partial match)
    """
    try:
        current_user_id = get_jwt_identity()
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        limit = min(request.args.get('limit', 20, type=int), 100)  # Max 100 items per page
        period = request.args.get('period')
        custom_date = request.args.get('date')
        
        # Validate page and limit
        if page < 1:
            return jsonify({'error': 'Page must be >= 1'}), 400
        if limit < 1:
            return jsonify({'error': 'Limit must be >= 1'}), 400
        
        # Handle period-based filtering
        if period:
            if period == 'custom' and not custom_date:
                return jsonify({'error': 'Custom date required for custom period'}), 400
            
            activities = activity_logger.get_activities_by_period(
                user_id=current_user_id,
                period_type=period,
                custom_date=custom_date
            )
            
            # Apply pagination to period results
            total_count = len(activities)
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_activities = activities[start_idx:end_idx]
            
            total_pages = (total_count + limit - 1) // limit
            has_next = page < total_pages
            has_prev = page > 1
            
            return jsonify({
                'activities': [activity.to_dict() for activity in paginated_activities],
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total_count': total_count,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_prev': has_prev
                }
            })
        
        # Handle general filtering
        filters = {}
        
        # Add filters from query parameters
        if request.args.get('action'):
            filters['action'] = request.args.get('action')
        
        if request.args.get('success') is not None:
            filters['success'] = request.args.get('success').lower() == 'true'
        
        if request.args.get('start_date'):
            filters['start_date'] = request.args.get('start_date')
        
        if request.args.get('end_date'):
            filters['end_date'] = request.args.get('end_date')
        
        if request.args.get('resource'):
            filters['resource'] = request.args.get('resource')
        
        # Get activities with filters and pagination
        result = activity_logger.get_user_activities(
            user_id=current_user_id,
            filters=filters,
            page=page,
            limit=limit
        )
        
        return jsonify(result)

    except ActivityLogError as e:
        return jsonify({
            'error': e.message,
            'code': e.code
        }), e.status_code
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@activity_bp.route('/activities/stats', methods=['GET'])
@jwt_required()
def get_activity_stats():
    """
    Get activity statistics for dashboard
    
    Query parameters:
    - period_days: Number of days to include (default: 30)
    """
    try:
        current_user_id = get_jwt_identity()
        period_days = request.args.get('period_days', 30, type=int)
        
        # Validate period_days
        if period_days < 1 or period_days > 365:
            return jsonify({'error': 'Period days must be between 1 and 365'}), 400
        
        stats = activity_logger.get_activity_statistics(
            user_id=current_user_id,
            period_days=period_days
        )
        
        return jsonify(stats)

    except ActivityLogError as e:
        return jsonify({
            'error': e.message,
            'code': e.code
        }), e.status_code
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@activity_bp.route('/activities/types', methods=['GET'])
@jwt_required()
def get_activity_types():
    """Get available activity types"""
    try:
        activity_types = []
        for activity_type in ActivityType:
            activity_types.append({
                'value': activity_type.value,
                'display_name': UserActivity.get_activity_type_display(activity_type.value)
            })
        
        return jsonify({
            'activity_types': activity_types
        })

    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@activity_bp.route('/activities', methods=['POST'])
@jwt_required()
def log_activity():
    """
    Manually log an activity (for testing or special cases)
    
    Request body:
    {
        "action": "string",
        "resource": "string (optional)",
        "details": "object (optional)",
        "success": "boolean (optional, default: true)"
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        # Debug logging
        print(f"Activity log request data: {data}")
        
        if not data or 'action' not in data:
            return jsonify({'error': 'Action is required'}), 400
        
        # Validate action type
        valid_actions = [activity_type.value for activity_type in ActivityType]
        print(f"Valid actions: {valid_actions}")
        print(f"Received action: {data['action']}")
        
        if data['action'] not in valid_actions:
            return jsonify({
                'error': 'Invalid action type',
                'valid_actions': valid_actions
            }), 400
        
        activity = activity_logger.log_activity(
            user_id=current_user_id,
            action=data['action'],
            resource=data.get('resource'),
            details=data.get('details'),
            success=data.get('success', True)
        )
        
        return jsonify({
            'message': 'Activity logged successfully',
            'activity': activity.to_dict()
        }), 201

    except ActivityLogError as e:
        return jsonify({
            'error': e.message,
            'code': e.code
        }), e.status_code
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@activity_bp.route('/activities/<int:activity_id>', methods=['GET'])
@jwt_required()
def get_activity_detail(activity_id):
    """Get detailed information about a specific activity"""
    try:
        current_user_id = get_jwt_identity()
        
        activity = UserActivity.query.filter_by(
            id=activity_id,
            user_id=current_user_id
        ).first()
        
        if not activity:
            return jsonify({'error': 'Activity not found'}), 404
        
        return jsonify({
            'activity': activity.to_dict()
        })

    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@activity_bp.route('/activities/batch', methods=['POST'])
@jwt_required()
def log_activities_batch():
    """
    Log multiple activities in batch
    
    Request body:
    {
        "activities": [
            {
                "action": "string",
                "resource": "string (optional)",
                "details": "object (optional)",
                "success": "boolean (optional, default: true)"
            }
        ]
    }
    """
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or 'activities' not in data:
            return jsonify({
                'error': 'Activities array is required',
                'code': 'MISSING_ACTIVITIES'
            }), 400
        
        activities = data['activities']
        if not isinstance(activities, list):
            return jsonify({
                'error': 'Activities must be an array',
                'code': 'INVALID_ACTIVITIES_FORMAT'
            }), 400
        
        # Validate action types
        valid_actions = [activity_type.value for activity_type in ActivityType]
        logged_activities = []
        errors = []
        
        for i, activity_data in enumerate(activities):
            if not isinstance(activity_data, dict) or 'action' not in activity_data:
                errors.append(f"Activity {i}: Missing action field")
                continue
            
            if activity_data['action'] not in valid_actions:
                errors.append(f"Activity {i}: Invalid action type '{activity_data['action']}'")
                continue
            
            try:
                activity = activity_logger.log_activity(
                    user_id=current_user_id,
                    action=activity_data['action'],
                    resource=activity_data.get('resource'),
                    details=activity_data.get('details', {}),
                    success=activity_data.get('success', True)
                )
                logged_activities.append(activity.to_dict())
            except Exception as e:
                errors.append(f"Activity {i}: {str(e)}")
                continue
        
        response_data = {
            'message': f'Successfully logged {len(logged_activities)} activities',
            'logged_count': len(logged_activities),
            'activities': logged_activities
        }
        
        if errors:
            response_data['errors'] = errors
        
        return jsonify(response_data), 201

    except ActivityLogError as e:
        return jsonify({
            'error': e.message,
            'code': e.code
        }), e.status_code
    except Exception as e:
        return jsonify({
            'error': 'Failed to log batch activities',
            'code': 'BATCH_LOG_FAILED',
            'details': str(e)
        }), 500

# Middleware decorator for automatic activity logging
def log_user_activity(action: str, get_resource=None, get_details=None):
    """
    Decorator to automatically log user activities
    
    Args:
        action: Activity type (should match ActivityType enum)
        get_resource: Function to extract resource from request/response
        get_details: Function to extract details from request/response
    """
    def decorator(f):
        from functools import wraps
        
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                # Execute the original function
                result = f(*args, **kwargs)
                
                # Log the activity if user is authenticated
                try:
                    current_user_id = get_jwt_identity()
                    if current_user_id:
                        resource = get_resource() if get_resource else None
                        details = get_details() if get_details else None
                        
                        # Determine success based on result
                        success = True
                        if hasattr(result, 'status_code'):
                            success = 200 <= result.status_code < 400
                        
                        activity_logger.log_activity(
                            user_id=current_user_id,
                            action=action,
                            resource=resource,
                            details=details,
                            success=success
                        )
                except Exception as log_error:
                    # Don't fail the original request if logging fails
                    print(f"Failed to log activity: {log_error}")
                
                return result
                
            except Exception as e:
                # Log failed activity
                try:
                    current_user_id = get_jwt_identity()
                    if current_user_id:
                        activity_logger.log_activity(
                            user_id=current_user_id,
                            action=action,
                            resource=get_resource() if get_resource else None,
                            details={'error': str(e)},
                            success=False
                        )
                except Exception:
                    pass  # Ignore logging errors
                
                raise e
        
        return wrapper
    return decorator