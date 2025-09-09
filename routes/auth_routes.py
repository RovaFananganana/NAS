from flask import Blueprint, request, jsonify
from models.user import User
from extensions import db
from flask_jwt_extended import create_access_token, jwt_required, get_jwt 



auth_bp = Blueprint("auth", __name__)

# Connexion
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    print("DEBUG data:", data) 
   
    if not isinstance(data, dict):
     if request.form:
        data = request.form.to_dict()
     elif request.args:
        data = request.args.to_dict()
     else:
        return jsonify({"error": "Payload JSON attendu (objet)"}), 400

    username = data.get("username")
    password = data.get("password")
    role = data.get("role")
    print("DEBUG username:", username)
    print("DEBUG password:", password)
    print("DEBUG role:", role)


    user = User.query.filter_by(username=username).first()
    print("DEBUG user:", user)
    if user and user.check_password(password):
        # Ajouter le rôle dans le token JWT
        additional_claims = {"role": user.role}
        access_token = create_access_token(
            identity=str(user.id),  # ⚠️ bien mettre en string
            additional_claims=additional_claims
        )
        return jsonify({
            "access_token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }), 200
    else:
        return jsonify({"msg": "Invalid credentials"}), 401

