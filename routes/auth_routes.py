# routes/auth_routes.py

from flask import Blueprint, request, jsonify
from models.user import User
from extensions import db
from flask_jwt_extended import create_access_token

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        if request.form:
            data = request.form.to_dict()
        elif request.args:
            data = request.args.to_dict()
        else:
            return jsonify({"error": "Payload JSON attendu"}), 400

    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        additional_claims = {"role": user.role.upper()}
        access_token = create_access_token(identity=str(user.id), additional_claims=additional_claims)
        return jsonify({
            "access_token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role.upper()
            }
        }), 200
    else:
        return jsonify({"msg": "Identifiants invalides"}), 401
