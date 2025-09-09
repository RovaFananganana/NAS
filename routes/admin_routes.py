# routes/admin_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models.user import User
from models.group import Group
from models.folder import Folder
from models.file import File
from models.access_log import AccessLog
from extensions import db
from functools import wraps
import os
from datetime import datetime, timezone

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        current_user_id = get_jwt_identity()
        claims = get_jwt()
        
        if claims.get('role') != 'admin':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
            
        return f(*args, **kwargs)
    return decorated_function

def log_admin_action(action, target):
    """Enregistre les actions admin dans les logs"""
    current_user_id = get_jwt_identity()
    log = AccessLog(
        user_id=current_user_id,
        action=action,
        target=target,
        timestamp=datetime.now(timezone.utc)
    )
    db.session.add(log)
    db.session.commit()

# ========== GESTION DES UTILISATEURS ==========

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    """Récupère tous les utilisateurs"""
    users = User.query.all()
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'quota_mb': user.quota_mb,
            'created_at': user.created_at.isoformat(),
            'groups': [group.name for group in user.groups]
        })
    return jsonify(users_data), 200

@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Créer un nouvel utilisateur"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"msg": "Username et password requis"}), 400
    
    # Vérifier si l'utilisateur existe déjà
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"msg": "Cet utilisateur existe déjà"}), 409
    
    if data.get('email') and User.query.filter_by(email=data['email']).first():
        return jsonify({"msg": "Cet email est déjà utilisé"}), 409
    
    user = User(
        username=data['username'],
        email=data.get('email'),
        role=data.get('role', 'SIMPLE_USER'),
        quota_mb=data.get('quota_mb', 2048)
    )
    user.set_password(data['password'])
    
    try:
        db.session.add(user)
        db.session.commit()
        log_admin_action('CREATE_USER', f"user:{user.username}")
        return jsonify({
            "msg": "Utilisateur créé avec succès",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la création"}), 500

@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Modifier un utilisateur"""
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if data.get('username') and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"msg": "Ce nom d'utilisateur existe déjà"}), 409
        user.username = data['username']
    
    if data.get('email') and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({"msg": "Cet email est déjà utilisé"}), 409
        user.email = data['email']
    
    if data.get('role'):
        user.role = data['role']
    
    if data.get('quota_mb'):
        user.quota_mb = data['quota_mb']
    
    if data.get('password'):
        user.set_password(data['password'])
    
    try:
        db.session.commit()
        log_admin_action('UPDATE_USER', f"user:{user.username}")
        return jsonify({"msg": "Utilisateur modifié avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la modification"}), 500

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Supprimer un utilisateur"""
    user = User.query.get_or_404(user_id)
    username = user.username
    
    try:
        db.session.delete(user)
        db.session.commit()
        log_admin_action('DELETE_USER', f"user:{username}")
        return jsonify({"msg": "Utilisateur supprimé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

# ========== GESTION DES GROUPES ==========

@admin_bp.route('/groups', methods=['GET'])
@admin_required
def get_all_groups():
    """Récupère tous les groupes"""
    groups = Group.query.all()
    groups_data = []
    for group in groups:
        groups_data.append({
            'id': group.id,
            'name': group.name,
            'users': [{'id': user.id, 'username': user.username} for user in group.users]
        })
    return jsonify(groups_data), 200

@admin_bp.route('/groups', methods=['POST'])
@admin_required
def create_group():
    """Créer un nouveau groupe"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({"msg": "Nom du groupe requis"}), 400
    
    if Group.query.filter_by(name=data['name']).first():
        return jsonify({"msg": "Ce groupe existe déjà"}), 409
    
    group = Group(name=data['name'])
    
    try:
        db.session.add(group)
        db.session.commit()
        log_admin_action('CREATE_GROUP', f"group:{group.name}")
        return jsonify({
            "msg": "Groupe créé avec succès",
            "group": {"id": group.id, "name": group.name}
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la création"}), 500

@admin_bp.route('/groups/<int:group_id>', methods=['PUT'])
@admin_required
def update_group(group_id):
    """Modifier un groupe"""
    group = Group.query.get_or_404(group_id)
    data = request.get_json()
    
    if data.get('name') and data['name'] != group.name:
        if Group.query.filter_by(name=data['name']).first():
            return jsonify({"msg": "Ce nom de groupe existe déjà"}), 409
        group.name = data['name']
    
    try:
        db.session.commit()
        log_admin_action('UPDATE_GROUP', f"group:{group.name}")
        return jsonify({"msg": "Groupe modifié avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la modification"}), 500

@admin_bp.route('/groups/<int:group_id>', methods=['DELETE'])
@admin_required
def delete_group(group_id):
    """Supprimer un groupe"""
    group = Group.query.get_or_404(group_id)
    group_name = group.name
    
    try:
        db.session.delete(group)
        db.session.commit()
        log_admin_action('DELETE_GROUP', f"group:{group_name}")
        return jsonify({"msg": "Groupe supprimé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@admin_bp.route('/groups/<int:group_id>/users', methods=['POST'])
@admin_required
def add_user_to_group(group_id):
    """Ajouter un utilisateur à un groupe"""
    group = Group.query.get_or_404(group_id)
    data = request.get_json()
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"msg": "ID utilisateur requis"}), 400
    
    user = User.query.get_or_404(user_id)
    
    if user in group.users:
        return jsonify({"msg": "L'utilisateur est déjà dans ce groupe"}), 409
    
    try:
        group.users.append(user)
        db.session.commit()
        log_admin_action('ADD_USER_TO_GROUP', f"user:{user.username} -> group:{group.name}")
        return jsonify({"msg": "Utilisateur ajouté au groupe avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de l'ajout"}), 500

@admin_bp.route('/groups/<int:group_id>/users/<int:user_id>', methods=['DELETE'])
@admin_required
def remove_user_from_group(group_id, user_id):
    """Retirer un utilisateur d'un groupe"""
    group = Group.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    
    if user not in group.users:
        return jsonify({"msg": "L'utilisateur n'est pas dans ce groupe"}), 404
    
    try:
        group.users.remove(user)
        db.session.commit()
        log_admin_action('REMOVE_USER_FROM_GROUP', f"user:{user.username} <- group:{group.name}")
        return jsonify({"msg": "Utilisateur retiré du groupe avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

# ========== GESTION DES DOSSIERS ET FICHIERS ==========

@admin_bp.route('/folders', methods=['GET'])
@admin_required
def get_all_folders():
    """Récupère tous les dossiers"""
    folders = Folder.query.all()
    folders_data = []
    for folder in folders:
        folders_data.append({
            'id': folder.id,
            'name': folder.name,
            'owner': folder.owner.username,
            'parent_id': folder.parent_id,
            'created_at': folder.created_at.isoformat()
        })
    return jsonify(folders_data), 200

@admin_bp.route('/folders', methods=['POST'])
@admin_required
def create_folder():
    """Créer un dossier (à la racine ou dans un dossier parent)"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({"msg": "Nom du dossier requis"}), 400
    
    # Vérifier si le dossier existe déjà au même niveau
    existing_folder = Folder.query.filter_by(
        name=data['name'], 
        parent_id=data.get('parent_id')
    ).first()
    
    if existing_folder:
        return jsonify({"msg": "Un dossier avec ce nom existe déjà à cet emplacement"}), 409
    
    # L'admin peut créer des dossiers pour n'importe quel utilisateur
    owner_id = data.get('owner_id', get_jwt_identity())
    owner = User.query.get_or_404(owner_id)
    
    folder = Folder(
        name=data['name'],
        owner_id=owner_id,
        parent_id=data.get('parent_id')
    )
    
    try:
        db.session.add(folder)
        db.session.commit()
        log_admin_action('CREATE_FOLDER', f"folder:{folder.name} for user:{owner.username}")
        return jsonify({
            "msg": "Dossier créé avec succès",
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "owner": owner.username,
                "parent_id": folder.parent_id
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la création"}), 500

@admin_bp.route('/folders/<int:folder_id>', methods=['DELETE'])
@admin_required
def delete_folder(folder_id):
    """Supprimer un dossier"""
    folder = Folder.query.get_or_404(folder_id)
    folder_name = folder.name
    
    try:
        db.session.delete(folder)
        db.session.commit()
        log_admin_action('DELETE_FOLDER', f"folder:{folder_name}")
        return jsonify({"msg": "Dossier supprimé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@admin_bp.route('/files', methods=['GET'])
@admin_required
def get_all_files():
    """Récupère tous les fichiers"""
    files = File.query.all()
    files_data = []
    for file in files:
        files_data.append({
            'id': file.id,
            'name': file.name,
            'path': file.path,
            'size_kb': file.size_kb,
            'owner': file.owner.username,
            'folder': file.folder.name if file.folder else None,
            'created_at': file.created_at.isoformat()
        })
    return jsonify(files_data), 200

# ========== LOGS ET STATISTIQUES ==========

@admin_bp.route('/logs', methods=['GET'])
@admin_required
def get_access_logs():
    """Récupère les logs d'accès avec pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    logs_data = []
    for log in logs.items:
        logs_data.append({
            'id': log.id,
            'user': log.user.username,
            'action': log.action,
            'target': log.target,
            'timestamp': log.timestamp.isoformat()
        })
    
    return jsonify({
        'logs': logs_data,
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page
    }), 200

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_statistics():
    """Récupère des statistiques générales"""
    stats = {
        'total_users': User.query.count(),
        'total_groups': Group.query.count(),
        'total_folders': Folder.query.count(),
        'total_files': File.query.count(),
        'admin_users': User.query.filter_by(role='ADMIN').count(),
        'simple_users': User.query.filter_by(role='SIMPLE_USER').count()
    }
    
    return jsonify(stats), 200