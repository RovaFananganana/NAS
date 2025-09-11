# routes/permission_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models.user import User
from models.group import Group
from models.folder import Folder
from models.file import File
from models.file_permission import FilePermission
from models.folder_permission import FolderPermission
from extensions import db
from functools import wraps

permission_bp = Blueprint('permission', __name__, url_prefix='/permissions')

# ===================== UTILITAIRES =====================

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role') != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
        return f(*args, **kwargs)
    return decorated_function

def bool_from_payload(data, key):
    """Convertit en bool et gère les valeurs manquantes"""
    val = data.get(key)
    return bool(val) if val is not None else False

# ===================== RESSOURCES =====================
@permission_bp.route('/resources', methods=['GET'])
def get_all_resources():
    folders = Folder.query.all()
    files = File.query.all()

    # Pour chaque dossier/fichier, récupérer les permissions
    folders_data = []
    for f in folders:
        folders_data.append({
            'id': f.id,
            'name': f.name,
            'permissions': [{'id': p.id, 'type': p.type, 'target_id': p.target_id, 'target_name': p.target_name, **p.permissions_dict()} for p in f.permissions]
        })

    files_data = []
    for file in files:
        files_data.append({
            'id': file.id,
            'name': file.name,
            'permissions': [{'id': p.id, 'type': p.type, 'target_id': p.target_id, 'target_name': p.target_name, **p.permissions_dict()} for p in file.permissions]
        })

    return jsonify({'folders': folders_data, 'files': files_data})
# ===================== DOSSIERS =====================

@permission_bp.route('/folders/<int:folder_id>', methods=['GET'])
@admin_required
def get_folder_permissions(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    permissions = FolderPermission.query.filter_by(folder_id=folder_id).all()

    result = []
    for perm in permissions:
        perm_data = {
            'id': perm.id,
            'folder_id': perm.folder_id,
            'can_read': perm.can_read,
            'can_write': perm.can_write,
            'can_delete': perm.can_delete,
            'can_share': perm.can_share,
            'type': 'user' if perm.user_id else 'group',
            'target_id': perm.user_id if perm.user_id else perm.group_id,
            'target_name': perm.user.username if perm.user_id else perm.group.name
        }
        result.append(perm_data)

    return jsonify({
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'owner': folder.owner.username
        },
        'permissions': result
    }), 200

def set_permission(entity, target_type, target_id, data):
    """Fonction interne pour créer ou mettre à jour une permission"""
    if target_type == 'user':
        user = User.query.get_or_404(target_id)
        perm = entity.permissions.filter_by(user_id=target_id).first()
        if not perm:
            perm = FolderPermission(folder_id=entity.id, user_id=target_id) if isinstance(entity, Folder) else FilePermission(file_id=entity.id, user_id=target_id)
            db.session.add(perm)
    else:  # group
        group = Group.query.get_or_404(target_id)
        perm = entity.permissions.filter_by(group_id=target_id).first()
        if not perm:
            perm = FolderPermission(folder_id=entity.id, group_id=target_id) if isinstance(entity, Folder) else FilePermission(file_id=entity.id, group_id=target_id)
            db.session.add(perm)

    perm.can_read = bool_from_payload(data, 'can_read')
    perm.can_write = bool_from_payload(data, 'can_write')
    perm.can_delete = bool_from_payload(data, 'can_delete')
    perm.can_share = bool_from_payload(data, 'can_share')

    return perm

@permission_bp.route('/folders/<int:folder_id>/<target_type>/<int:target_id>', methods=['POST'])
@admin_required
def set_folder_permission(folder_id, target_type, target_id):
    """Définir/modifier permissions dossier (user ou group)"""
    folder = Folder.query.get_or_404(folder_id)
    data = request.get_json()
    perm = set_permission(folder, target_type, target_id, data)

    try:
        db.session.commit()
        return jsonify({
            "msg": f"Permissions mises à jour pour {target_type} {target_id} sur le dossier {folder.name}",
            "permission": {
                'id': perm.id,
                'can_read': perm.can_read,
                'can_write': perm.can_write,
                'can_delete': perm.can_delete,
                'can_share': perm.can_share
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

@permission_bp.route('/folders/<int:folder_id>/permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def delete_folder_permission(folder_id, permission_id):
    perm = FolderPermission.query.filter_by(id=permission_id, folder_id=folder_id).first_or_404()
    try:
        db.session.delete(perm)
        db.session.commit()
        return jsonify({"msg": "Permission supprimée avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

# ===================== FICHIERS =====================

@permission_bp.route('/files/<int:file_id>', methods=['GET'])
@admin_required
def get_file_permissions(file_id):
    file = File.query.get_or_404(file_id)
    permissions = FilePermission.query.filter_by(file_id=file_id).all()

    result = []
    for perm in permissions:
        perm_data = {
            'id': perm.id,
            'file_id': perm.file_id,
            'can_read': perm.can_read,
            'can_write': perm.can_write,
            'can_delete': perm.can_delete,
            'can_share': perm.can_share,
            'type': 'user' if perm.user_id else 'group',
            'target_id': perm.user_id if perm.user_id else perm.group_id,
            'target_name': perm.user.username if perm.user_id else perm.group.name
        }
        result.append(perm_data)

    return jsonify({
        'file': {
            'id': file.id,
            'name': file.name,
            'owner': file.owner.username
        },
        'permissions': result
    }), 200

@permission_bp.route('/files/<int:file_id>/<target_type>/<int:target_id>', methods=['POST'])
@admin_required
def set_file_permission(file_id, target_type, target_id):
    """Définir/modifier permissions fichier (user ou group)"""
    file = File.query.get_or_404(file_id)
    data = request.get_json()
    perm = set_permission(file, target_type, target_id, data)

    try:
        db.session.commit()
        return jsonify({
            "msg": f"Permissions mises à jour pour {target_type} {target_id} sur le fichier {file.name}",
            "permission": {
                'id': perm.id,
                'can_read': perm.can_read,
                'can_write': perm.can_write,
                'can_delete': perm.can_delete,
                'can_share': perm.can_share
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

@permission_bp.route('/files/<int:file_id>/permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def delete_file_permission(file_id, permission_id):
    perm = FilePermission.query.filter_by(id=permission_id, file_id=file_id).first_or_404()
    try:
        db.session.delete(perm)
        db.session.commit()
        return jsonify({"msg": "Permission supprimée avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

# ===================== BATCH =====================

@permission_bp.route('/batch/<entity>', methods=['POST'])
@admin_required
def batch_set_permissions(entity):
    """
    Définir des permissions en lot sur plusieurs dossiers ou fichiers
    entity: 'folders' ou 'files'
    """
    data = request.get_json()
    ids = data.get('ids', [])
    target_type = data.get('target_type')
    target_id = data.get('target_id')
    perms = data.get('permissions', {})

    if not ids or not target_type or not target_id:
        return jsonify({"msg": "Données incomplètes"}), 400

    success_count = 0
    errors = []

    Model = Folder if entity == 'folders' else File

    for item_id in ids:
        try:
            obj = Model.query.get(item_id)
            if not obj:
                continue
            set_permission(obj, target_type, target_id, perms)
            success_count += 1
        except Exception as e:
            errors.append(f"{entity[:-1]} {item_id}: {str(e)}")

    try:
        db.session.commit()
        return jsonify({
            "msg": f"Permissions mises à jour sur {success_count} {entity}",
            "errors": errors
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

# ===================== EFFECTIVES =====================

@permission_bp.route('/effective/<int:user_id>', methods=['GET'])
@admin_required
def get_user_effective_permissions(user_id):
    user = User.query.get_or_404(user_id)

    effective = {'folders': [], 'files': []}

    for folder in Folder.query.all():
        perm = folder.get_effective_permissions(user)
        if perm:
            effective['folders'].append({
                'id': folder.id,
                'name': folder.name,
                'owner': folder.owner.username,
                'permission': {
                    'can_read': perm.can_read,
                    'can_write': perm.can_write,
                    'can_delete': perm.can_delete,
                    'can_share': perm.can_share,
                    'source': 'user' if perm.user_id else 'group'
                }
            })

    for file in File.query.all():
        perm = file.get_effective_permissions(user)
        if perm:
            effective['files'].append({
                'id': file.id,
                'name': file.name,
                'owner': file.owner.username,
                'folder_name': file.folder.name if file.folder else 'Racine',
                'permission': {
                    'can_read': perm.can_read,
                    'can_write': perm.can_write,
                    'can_delete': perm.can_delete,
                    'can_share': perm.can_share,
                    'source': 'user' if perm.user_id else 'group'
                }
            })

    return jsonify({
        'user': {
            'id': user.id,
            'username': user.username,
            'groups': [g.name for g in user.groups]
        },
        'permissions': effective
    }), 200
