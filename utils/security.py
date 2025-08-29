from functools import wraps
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask import jsonify
from models.user import User
from utils.permissions import has_permission 

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

            if not has_permission(user, resource, action):
                return jsonify({"msg": "Permission refusée"}), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator
