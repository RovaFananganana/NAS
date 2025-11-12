from functools import wraps
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask import jsonify
from models.user import User
from utils.permissions import has_permission 
import logging

logger = logging.getLogger(__name__)

def require_permission(resource, action):
    """
    Décorateur Flask pour protéger une route avec une permission.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            if not user:
                return jsonify({"msg": "Utilisateur non trouvé"}), 404

            permitted = has_permission(user, resource, action)
            # Debug log to help diagnose 403s — logs the user id, role and the permission check
            try:
                logger.debug(f"Permission check for user_id={user_id} role={getattr(user, 'role', None)} resource={resource} action={action} -> {permitted}")
            except Exception:
                logger.debug(f"Permission check for user_id={user_id} resource={resource} action={action} -> {permitted}")

            if not permitted:
                logger.warning(f"Permission refused for user_id={user_id} role={getattr(user, 'role', None)} resource={resource} action={action}")
                return jsonify({"msg": "Permission refusée"}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator
