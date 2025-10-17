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
from utils.permission_middleware import require_resource_permission, get_user_accessible_resources, check_user_can_access_resource
from models.file_permission import FilePermission

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
        try:
         folder_id = int(folder_id)
        except ValueError:
            return jsonify({"error": "folder_id doit être un entier"}), 422
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

@user_bp.route('/accessible-resources', methods=['GET'])
@jwt_required()
def get_accessible_resources():
    """Récupère toutes les ressources accessibles par l'utilisateur connecté"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"msg": "Utilisateur non trouvé"}), 404
    
    resource_type = request.args.get('type', 'both')  # files, folders, both
    accessible = get_user_accessible_resources(user, resource_type)
    
    # Formater les données de retour
    files_data = []
    for file in accessible['files']:
        permission = file.get_effective_permissions(user)
        files_data.append({
            'id': file.id,
            'name': file.name,
            'path': file.path,
            'size_kb': file.size_kb,
            'owner': file.owner.username,
            'folder_name': file.folder.name if file.folder else 'Racine',
            'created_at': file.created_at.isoformat(),
            'is_owner': file.owner_id == user.id,
            'permissions': {
                'can_read': permission.can_read if permission else True,
                'can_write': permission.can_write if permission else (file.owner_id == user.id),
                'can_delete': permission.can_delete if permission else (file.owner_id == user.id),
                'can_share': permission.can_share if permission else (file.owner_id == user.id),
                'source': 'owner' if file.owner_id == user.id else ('user' if permission and permission.user_id else 'group')
            } if permission or file.owner_id == user.id else None
        })
    
    folders_data = []
    for folder in accessible['folders']:
        permission = folder.get_effective_permissions(user)
        folders_data.append({
            'id': folder.id,
            'name': folder.name,
            'owner': folder.owner.username,
            'parent_id': folder.parent_id,
            'created_at': folder.created_at.isoformat(),
            'is_owner': folder.owner_id == user.id,
            'children_count': len(folder.children),
            'files_count': len(folder.files),
            'permissions': {
                'can_read': permission.can_read if permission else True,
                'can_write': permission.can_write if permission else (folder.owner_id == user.id),
                'can_delete': permission.can_delete if permission else (folder.owner_id == user.id),
                'can_share': permission.can_share if permission else (folder.owner_id == user.id),
                'source': 'owner' if folder.owner_id == user.id else ('user' if permission and permission.user_id else 'group')
            } if permission or folder.owner_id == user.id else None
        })
    
    log_user_action('READ', 'accessible_resources')
    return jsonify({
        'files': files_data,
        'folders': folders_data,
        'stats': {
            'total_files': len(files_data),
            'total_folders': len(folders_data),
            'owned_files': len([f for f in files_data if f['is_owner']]),
            'owned_folders': len([f for f in folders_data if f['is_owner']]),
            'shared_files': len([f for f in files_data if not f['is_owner']]),
            'shared_folders': len([f for f in folders_data if not f['is_owner']])
        }
    }), 200

@user_bp.route('/log-activity', methods=['POST'])
@jwt_required()
def log_activity():
    """Enregistre une activité utilisateur dans les logs"""
    try:
        data = request.get_json()
        
        if not data or not data.get('action'):
            return jsonify({"msg": "Action requise"}), 400
        
        action = data.get('action')
        target = data.get('target', 'unknown')
        details = data.get('details', '')
        
        # Si target est vide ou None, utiliser 'unknown'
        if not target or target.strip() == '':
            target = 'unknown'
        
        # Nettoyer et limiter les détails
        if details:
            # Si details est un objet JSON, le convertir en string
            if isinstance(details, dict):
                details_str = str(details)
            else:
                details_str = str(details)
            
            # Limiter la taille et nettoyer
            if len(details_str) > 300:
                details_str = details_str[:297] + "..."
            
            # Construire le target avec les détails si différents
            if details_str != target and details_str.strip():
                log_target = f"{target} - {details_str}"
            else:
                log_target = target
        else:
            log_target = target
        
        # Limiter la taille totale du target
        if len(log_target) > 500:
            log_target = log_target[:497] + "..."
        
        # Nettoyer les caractères problématiques
        log_target = log_target.replace('\n', ' ').replace('\r', ' ').strip()
        
        # Enregistrer l'activité
        log_user_action(action, log_target)
        
        return jsonify({"msg": "Activité enregistrée avec succès"}), 200
        
    except Exception as e:
        print(f"Erreur lors de l'enregistrement de l'activité: {str(e)}")
        print(f"Données reçues: {data}")
        return jsonify({"msg": "Erreur lors de l'enregistrement"}), 500

@user_bp.route('/folders/<int:folder_id>/content', methods=['GET'])
@require_resource_permission('folder', 'read')
def get_folder_content(folder_id):
    """Récupère le contenu d'un dossier (sous-dossiers et fichiers)"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    folder = Folder.query.get_or_404(folder_id)
    
    # Récupérer les sous-dossiers accessibles
    subfolders = []
    for subfolder in folder.children:
        if check_user_can_access_resource(user, subfolder, 'read'):
            permission = subfolder.get_effective_permissions(user)
            subfolders.append({
                'id': subfolder.id,
                'name': subfolder.name,
                'owner': subfolder.owner.username,
                'created_at': subfolder.created_at.isoformat(),
                'is_owner': subfolder.owner_id == user.id,
                'children_count': len(subfolder.children),
                'files_count': len(subfolder.files),
                'permissions': {
                    'can_read': permission.can_read if permission else True,
                    'can_write': permission.can_write if permission else (subfolder.owner_id == user.id),
                    'can_delete': permission.can_delete if permission else (subfolder.owner_id == user.id),
                    'can_share': permission.can_share if permission else (subfolder.owner_id == user.id)
                } if permission or subfolder.owner_id == user.id else None
            })
    
    # Récupérer les fichiers accessibles
    files = []
    for file in folder.files:
        if check_user_can_access_resource(user, file, 'read'):
            permission = file.get_effective_permissions(user)
            files.append({
                'id': file.id,
                'name': file.name,
                'path': file.path,
                'size_kb': file.size_kb,
                'size_mb': round(file.size_kb / 1024, 2),
                'owner': file.owner.username,
                'created_at': file.created_at.isoformat(),
                'is_owner': file.owner_id == user.id,
                'permissions': {
                    'can_read': permission.can_read if permission else True,
                    'can_write': permission.can_write if permission else (file.owner_id == user.id),
                    'can_delete': permission.can_delete if permission else (file.owner_id == user.id),
                    'can_share': permission.can_share if permission else (file.owner_id == user.id)
                } if permission or file.owner_id == user.id else None
            })
    
    log_user_action('READ', f"folder_content:{folder.name}")
    return jsonify({
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'owner': folder.owner.username,
            'parent_id': folder.parent_id,
            'is_owner': folder.owner_id == user.id,
            'path': get_folder_path(folder)  # Vous devrez implémenter cette fonction
        },
        'subfolders': subfolders,
        'files': files,
        'stats': {
            'subfolders_count': len(subfolders),
            'files_count': len(files),
            'total_size_kb': sum(f['size_kb'] for f in files)
        }
    }), 200

@user_bp.route('/files/<int:file_id>/download', methods=['GET'])
@require_resource_permission('file', 'read')
def download_file(file_id):
    """Télécharge un fichier (placeholder)"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    file = File.query.get_or_404(file_id)
    
    log_user_action('DOWNLOAD', f"file:{file.name}")
    
    # Ici vous implémenteriez la logique de téléchargement
    return jsonify({
        "msg": "Téléchargement autorisé",
        "file": {
            "id": file.id,
            "name": file.name,
            "path": file.path,
            "size_kb": file.size_kb
        }
    }), 200

@user_bp.route('/files/<int:file_id>/share', methods=['POST'])
@require_resource_permission('file', 'share')
def share_file(file_id):
    """Partage un fichier avec un utilisateur ou groupe"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    file = File.query.get_or_404(file_id)
    data = request.get_json()
    
    target_type = data.get('target_type')  # 'user' ou 'group'
    target_id = data.get('target_id')
    permissions = data.get('permissions', {})
    
    if not target_type or not target_id:
        return jsonify({"msg": "Type et ID de destinataire requis"}), 400
    
    try:
        if target_type == 'user':
            target_user = User.query.get_or_404(target_id)
            # Vérifier si le partage existe déjà 
            existing = file.shared_with_users.filter_by(user_id=target_user.id).first()
            if existing:    
                return jsonify({"msg": "Le fichier est déjà partagé avec cet utilisateur"}), 409
            file.shared_with_users.append(target_user)
            db.session.flush()  # Pour obtenir l'ID de la relation
            file_perm = FilePermission(
                file_id=file.id,
                user_id=target_user.id,
                can_read=permissions.get('can_read', True),
                can_write=permissions.get('can_write', False),
                can_delete=permissions.get('can_delete', False),
                can_share=permissions.get('can_share', False)
            )
            db.session.add(file_perm)
        elif target_type == 'group':
            target_group = Group.query.get_or_404(target_id)
            # Vérifier si le partage existe déjà 
            existing = file.shared_with_groups.filter_by(group_id=target_group.id).first()
            if existing:    
                return jsonify({"msg": "Le fichier est déjà partagé avec ce groupe"}), 409
            file.shared_with_groups.append(target_group)
            db.session.flush()  # Pour obtenir l'ID de la relation
            file_perm = FilePermission(
                file_id=file.id,
                group_id=target_group.id,
                can_read=permissions.get('can_read', True),
                can_write=permissions.get('can_write', False),
                can_delete=permissions.get('can_delete', False),
                can_share=permissions.get('can_share', False)
            )
            db.session.add(file_perm)
        else:            
            return jsonify({"msg": "Type de destinataire invalide"}), 400
        db.session.commit()
        log_user_action('SHARE', f"file:{file.name} with {target_type   }:{target_id}")
        return jsonify({"msg": "Fichier partagé avec succès"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors du partage"}), 500            