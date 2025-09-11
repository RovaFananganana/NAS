# routes/folder_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import Folder, User, FolderPermission
from extensions import db
from services.file_service import create_folder

folder_bp = Blueprint('folder_bp', __name__, url_prefix='/folders')

@folder_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    folders = Folder.query.all()
    accessible = []
    for f in folders:
        perm = f.get_effective_permissions(user)
        if perm and perm.can_read:
            accessible.append({"id": f.id, "name": f.name, "path": f.path})
    return jsonify(accessible)

@folder_bp.route('/create', methods=['POST'])
@jwt_required()
def create_folder_route():
    data = request.json
    user_id =int(get_jwt_identity())
    user = User.query.get(user_id)

    if not data.get('name'):
        return jsonify({"msg": "Le nom du dossier est requis"}), 400

    parent_id = data.get('parent_id')
    relative_path = data['name']

    if parent_id:
        parent_folder = Folder.query.get(parent_id)
        if not parent_folder:
            return jsonify({"msg": "Dossier parent introuvable"}), 404
        perm = parent_folder.get_effective_permissions(user)
        if not perm or not perm.can_write:
            return jsonify({"msg": "Permission refusée"}), 403
        relative_path = f"{parent_folder.path}/{data['name']}"

    physical_path = create_folder(relative_path)

    folder = Folder(
        name=data['name'],
        owner_id=user.id,
        parent_id=parent_id,
        path=relative_path
    )
    db.session.add(folder)
    db.session.commit()

    return jsonify({
        "msg": "Dossier créé",
        "id": folder.id,
        "path": folder.path,
        "physical_path": physical_path
    })
