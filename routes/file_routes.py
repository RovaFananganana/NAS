from flask import Blueprint, jsonify
from utils.security import require_permission
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import File, User

file_bp = Blueprint("file", __name__)

@file_bp.route("/files", methods=["GET"])
@jwt_required()
@require_permission(resource="file", action="READ")
def list_files():
    # Ici tu récupères les fichiers de l'utilisateur
    return jsonify({"msg": "Accès aux fichiers autorisé"})


@file_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    # ici tu peux utiliser request.files['file'] pour gérer l’upload
    return jsonify({"msg": "Upload placeholder"})
