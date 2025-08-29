from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User

user_bp = Blueprint('user_bp', __name__, url_prefix='/users')

@user_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin
    })

@user_bp.route('/me', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    data = request.json
    user.username = data.get('username', user.username)
    user.email = data.get('email', user.email)
    # ici tu peux ajouter update du password etc.
    user.save()
    return jsonify({"msg": "Profil mis à jour"})
