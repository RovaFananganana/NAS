from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Folder, User

folder_bp = Blueprint('folder_bp', __name__, url_prefix='/folders')

@folder_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    folders = Folder.query.filter_by(user_id=user.id).all()
    return jsonify([{"id": f.id, "name": f.name} for f in folders])

@folder_bp.route('/create', methods=['POST'])
@jwt_required()
def create_folder():
    data = request.json
    user_id = get_jwt_identity()
    folder = Folder(name=data['name'], user_id=user_id, path=data.get('path', '/'))
    folder.save()
    return jsonify({"msg": "Dossier créé", "id": folder.id})
