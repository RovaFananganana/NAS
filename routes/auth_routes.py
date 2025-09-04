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
    print("DEBUG username:", username)
    print("DEBUG password:", password)


    user = User.query.filter_by(username=username).first()
    print("DEBUG user:", user)
    if not user or not user.check_password(password):
        return jsonify({"msg": "Nom d'utilisateur ou mot de passe incorrect"}), 401

    access_token = create_access_token(
       identity=user.id,
       additional_claims={'role': user.role}
       )
    return jsonify({
        "msg": "Connexion réussie",
        "access_token": access_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }), 200

