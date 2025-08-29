from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')

def admin_required(fn):
    """Décorateur pour restreindre aux admins"""
    from functools import wraps
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or not user.is_admin:
            return jsonify({"msg": "Accès interdit"}), 403
        return fn(*args, **kwargs)
    return wrapper

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    users = User.query.all()
    return jsonify([{"id": u.id, "username": u.username, "email": u.email} for u in users])

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    user.delete()
    return jsonify({"msg": "Utilisateur supprimé"})
