# routes/user_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models.user import User
from models.folder import Folder
from models.file import File
from models.access_log import AccessLog
from extensions import db
from functools import wraps
from datetime import datetime, timezone

user_bp = Blueprint('user_bp', __name__, url_prefix='/users')

def log_user_action(action, target):
    """Enregistre les actions utilisateur dans les logs"""
    current_user_id = get_jwt_identity()
    log = AccessLog(
        user_id=current_user_id,
        action=action,
        target=target,
        timestamp=datetime.now(timezone.utc)
    )
    db.session.add(log)
    db.session.commit()

@user_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Récupère les informations de l'utilisateur connecté"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    
    # Calculer l'espace utilisé
    total_size = db.session.query(db.func.sum(File.size_kb)).filter_by(owner_id=user.id).scalar() or 0
    
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "quota_mb": user.quota_mb,
        "used_kb": total_size,
        "used_mb": round(total_size / 1024, 2),
        "groups": [{"id": g.id, "name": g.name} for g in user.groups],
        "created_at": user.created_at.isoformat()
    })

@user_bp.route('/me', methods=['PUT'])
@jwt_required()
def update_profile():
    """Met à jour le profil de l'utilisateur connecté"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    
    data = request.get_json()
    
    # Vérification des données
    if data.get('username') and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"msg": "Ce nom d'utilisateur existe déjà"}), 409
        user.username = data['username']
    
    if data.get('email') and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({"msg": "Cet email est déjà utilisé"}), 409
        user.email = data['email']
    
    if data.get('password'):
        user.set_password(data['password'])
    
    try:
        db.session.commit()
        log_user_action('UPDATE_PROFILE', f"user:{user.username}")
        return jsonify({"msg": "Profil mis à jour avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la mise à jour"}), 500

@user_bp.route('/my-folders', methods=['GET'])
@jwt_required()
def get_my_folders():
    """Récupère les dossiers de l'utilisateur connecté"""
    user_id = get_jwt_identity()
    
    # Paramètres de filtre optionnels
    parent_id = request.args.get('parent_id', type=int)
    
    query = Folder.query.filter_by(owner_id=user_id)
    
    if parent_id is not None:
        query = query.filter_by(parent_id=parent_id)
    elif request.args.get('root_only') == 'true':
        query = query.filter_by(parent_id=None)
    
    folders = query.all()
    folders_data = []
    
    for folder in folders:
        folders_data.append({
            'id': folder.id,
            'name': folder.name,
            'parent_id': folder.parent_id,
            'created_at': folder.created_at.isoformat(),
            'children_count': len(folder.children),
            'files_count': len(folder.files)
        })
    
    log_user_action('READ', 'folders')
    return jsonify(folders_data), 200

@user_bp.route('/folders', methods=['POST'])
@jwt_required()
def create_folder():
    """Créer un nouveau dossier"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({"msg": "Nom du dossier requis"}), 400
    
    # Vérifier si le dossier existe déjà au même niveau
    existing_folder = Folder.query.filter_by(
        name=data['name'],
        owner_id=user_id,
        parent_id=data.get('parent_id')
    ).first()
    
    if existing_folder:
        return jsonify({"msg": "Un dossier avec ce nom existe déjà à cet emplacement"}), 409
    
    # Vérifier que le dossier parent appartient à l'utilisateur (si spécifié)
    if data.get('parent_id'):
        parent_folder = Folder.query.filter_by(
            id=data['parent_id'],
            owner_id=user_id
        ).first()
        if not parent_folder:
            return jsonify({"msg": "Dossier parent non trouvé ou accès refusé"}), 404
    
    folder = Folder(
        name=data['name'],
        owner_id=user_id,
        parent_id=data.get('parent_id')
    )
    
    try:
        db.session.add(folder)
        db.session.commit()
        log_user_action('CREATE', f"folder:{folder.name}")
        return jsonify({
            "msg": "Dossier créé avec succès",
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "parent_id": folder.parent_id,
                "created_at": folder.created_at.isoformat()
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la création"}), 500

@user_bp.route('/folders/<int:folder_id>', methods=['PUT'])
@jwt_required()
def update_folder(folder_id):
    """Renommer un dossier"""
    user_id = get_jwt_identity()
    folder = Folder.query.filter_by(id=folder_id, owner_id=user_id).first()
    
    if not folder:
        return jsonify({"msg": "Dossier non trouvé ou accès refusé"}), 404
    
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"msg": "Nouveau nom requis"}), 400
    
    # Vérifier si le nouveau nom n'existe pas déjà
    existing_folder = Folder.query.filter_by(
        name=data['name'],
        owner_id=user_id,
        parent_id=folder.parent_id
    ).filter(Folder.id != folder_id).first()
    
    if existing_folder:
        return jsonify({"msg": "Un dossier avec ce nom existe déjà"}), 409
    
    old_name = folder.name
    folder.name = data['name']
    
    try:
        db.session.commit()
        log_user_action('UPDATE', f"folder:{old_name} -> {folder.name}")
        return jsonify({"msg": "Dossier renommé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la modification"}), 500

@user_bp.route('/folders/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
    """Supprimer un dossier"""
    user_id = get_jwt_identity()
    folder = Folder.query.filter_by(id=folder_id, owner_id=user_id).first()
    
    if not folder:
        return jsonify({"msg": "Dossier non trouvé ou accès refusé"}), 404
    
    # Vérifier si le dossier est vide (pas de sous-dossiers ni de fichiers)
    if folder.children or folder.files:
        return jsonify({"msg": "Impossible de supprimer un dossier non vide"}), 409
    
    folder_name = folder.name
    
    try:
        db.session.delete(folder)
        db.session.commit()
        log_user_action('DELETE', f"folder:{folder_name}")
        return jsonify({"msg": "Dossier supprimé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@user_bp.route('/my-files', methods=['GET'])
@jwt_required()
def get_my_files():
    """Récupère les fichiers de l'utilisateur connecté"""
    user_id = get_jwt_identity()
    
    # Paramètres de filtre optionnels
    folder_id = request.args.get('folder_id', type=int)
    
    query = File.query.filter_by(owner_id=user_id)
    
    if folder_id is not None:
        query = query.filter_by(folder_id=folder_id)
    elif request.args.get('root_only') == 'true':
        query = query.filter_by(folder_id=None)
    
    files = query.all()
    files_data = []
    
    for file in files:
        files_data.append({
            'id': file.id,
            'name': file.name,
            'path': file.path,
            'size_kb': file.size_kb,
            'size_mb': round(file.size_kb / 1024, 2),
            'folder_id': file.folder_id,
            'folder_name': file.folder.name if file.folder else None,
            'created_at': file.created_at.isoformat()
        })
    
    log_user_action('READ', 'files')
    return jsonify(files_data), 200

@user_bp.route('/files/<int:file_id>', methods=['DELETE'])
@jwt_required()
def delete_file(file_id):
    """Supprimer un fichier"""
    user_id = get_jwt_identity()
    file = File.query.filter_by(id=file_id, owner_id=user_id).first()
    
    if not file:
        return jsonify({"msg": "Fichier non trouvé ou accès refusé"}), 404
    
    file_name = file.name
    
    try:
        # Supprimer le fichier physique si nécessaire
        # os.remove(file.path)  # Décommentez si vous voulez supprimer le fichier physique
        
        db.session.delete(file)
        db.session.commit()
        log_user_action('DELETE', f"file:{file_name}")
        return jsonify({"msg": "Fichier supprimé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@user_bp.route('/storage-info', methods=['GET'])
@jwt_required()
def get_storage_info():
    """Récupère les informations de stockage de l'utilisateur"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    
    # Calculer l'espace utilisé
    total_size_kb = db.session.query(db.func.sum(File.size_kb)).filter_by(owner_id=user.id).scalar() or 0
    total_size_mb = round(total_size_kb / 1024, 2)
    
    # Statistiques par type de fichier (basé sur l'extension)
    files = File.query.filter_by(owner_id=user_id).all()
    file_types = {}
    for file in files:
        ext = file.name.split('.')[-1].lower() if '.' in file.name else 'no_extension'
        if ext not in file_types:
            file_types[ext] = {'count': 0, 'size_kb': 0}
        file_types[ext]['count'] += 1
        file_types[ext]['size_kb'] += file.size_kb
    
    return jsonify({
        'quota_mb': user.quota_mb,
        'used_kb': total_size_kb,
        'used_mb': total_size_mb,
        'available_mb': max(0, user.quota_mb - total_size_mb),
        'usage_percentage': round((total_size_mb / user.quota_mb * 100), 2) if user.quota_mb > 0 else 0,
        'total_files': len(files),
        'total_folders': Folder.query.filter_by(owner_id=user_id).count(),
        'file_types': file_types
    }), 200

@user_bp.route('/my-logs', methods=['GET'])
@jwt_required()
def get_my_logs():
    """Récupère les logs d'activité de l'utilisateur connecté"""
    user_id = get_jwt_identity()
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    logs = AccessLog.query.filter_by(user_id=user_id).order_by(
        AccessLog.timestamp.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    logs_data = []
    for log in logs.items:
        logs_data.append({
            'id': log.id,
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

@user_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_dashboard():
    """Récupère les données pour le tableau de bord utilisateur"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    
    # Statistiques générales
    total_files = File.query.filter_by(owner_id=user_id).count()
    total_folders = Folder.query.filter_by(owner_id=user_id).count()
    total_size_kb = db.session.query(db.func.sum(File.size_kb)).filter_by(owner_id=user_id).scalar() or 0
    
    # Fichiers récents (derniers 5)
    recent_files = File.query.filter_by(owner_id=user_id).order_by(
        File.created_at.desc()
    ).limit(5).all()
    
    recent_files_data = []
    for file in recent_files:
        recent_files_data.append({
            'id': file.id,
            'name': file.name,
            'size_kb': file.size_kb,
            'created_at': file.created_at.isoformat(),
            'folder_name': file.folder.name if file.folder else 'Racine'
        })
    
    # Activité récente (derniers 10 logs)
    recent_logs = AccessLog.query.filter_by(user_id=user_id).order_by(
        AccessLog.timestamp.desc()
    ).limit(10).all()
    
    recent_activity = []
    for log in recent_logs:
        recent_activity.append({
            'action': log.action,
            'target': log.target,
            'timestamp': log.timestamp.isoformat()
        })
    
    return jsonify({
        'user': {
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'quota_mb': user.quota_mb,
            'groups': [g.name for g in user.groups]
        },
        'statistics': {
            'total_files': total_files,
            'total_folders': total_folders,
            'used_mb': round(total_size_kb / 1024, 2),
            'available_mb': max(0, user.quota_mb - round(total_size_kb / 1024, 2)),
            'usage_percentage': round((total_size_kb / 1024 / user.quota_mb * 100), 2) if user.quota_mb > 0 else 0
        },
        'recent_files': recent_files_data,
        'recent_activity': recent_activity
    }), 200