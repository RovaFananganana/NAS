from flask import Blueprint, request, jsonify
from models.user import User
from extensions import db
from flask_jwt_extended import create_access_token



auth_bp = Blueprint("auth", __name__)

# Créer un utilisateur
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if data is None:
     return {"error": "No JSON received"}, 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if User.query.filter((User.username==username)|(User.email==email)).first():
        return jsonify({"msg": "Utilisateur déjà existant"}), 400

    user = User(username=username, email=email)
    user.set_password(password)  # hash le mot de passe
    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "Utilisateur enregistré avec succès", "user_id": user.id}), 201

# Connexion
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json
    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()
    if not user or not User.check_password(password):
        return jsonify({"msg": "Nom d'utilisateur ou mot de passe incorrect"}), 401

    access_token = create_access_token(identity=user.id)
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

