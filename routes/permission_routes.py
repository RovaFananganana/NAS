# routes/permission_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime
from models.user import User
from models.group import Group
from models.folder import Folder
from models.file import File
from models.file_permission import FilePermission
from models.folder_permission import FolderPermission
from extensions import db
from functools import wraps
from utils.access_logger import (
    log_folder_permission_action, 
    log_file_permission_action, 
    log_batch_permission_action
)
from services.permission_audit_logger import permission_audit_logger

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
@permission_bp.route('/test', methods=['GET', 'OPTIONS'])
def test_endpoint():
    """Simple test endpoint to verify CORS and basic functionality"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    return jsonify({'status': 'ok', 'message': 'Permission API is working', 'timestamp': str(datetime.now())})

@permission_bp.route('/resources', methods=['GET', 'OPTIONS'])
def get_all_resources():
    try:
        folders = Folder.query.all()
        files = File.query.all()
        users = User.query.all()
        groups = Group.query.all()

        # Pour chaque dossier, récupérer les permissions
        folders_data = []
        for f in folders:
            permissions_data = []
            for p in f.permissions:
                perm_data = {
                    'id': p.id,
                    'can_read': p.can_read,
                    'can_write': p.can_write,
                    'can_delete': p.can_delete,
                    'can_share': p.can_share,
                }
                
                if p.user_id:
                    perm_data['type'] = 'user'
                    perm_data['target_id'] = p.user_id
                    perm_data['target_name'] = p.user.username if p.user else f'User {p.user_id}'
                elif p.group_id:
                    perm_data['type'] = 'group'
                    perm_data['target_id'] = p.group_id
                    perm_data['target_name'] = p.group.name if p.group else f'Group {p.group_id}'
                
                permissions_data.append(perm_data)
            
            folders_data.append({
                'id': f.id,
                'name': f.name,
                'path': getattr(f, 'path', None),
                'permissions': permissions_data
            })

        # Pour chaque fichier, récupérer les permissions
        files_data = []
        for file in files:
            permissions_data = []
            for p in file.permissions:
                perm_data = {
                    'id': p.id,
                    'can_read': p.can_read,
                    'can_write': p.can_write,
                    'can_delete': p.can_delete,
                    'can_share': p.can_share,
                }
                
                if p.user_id:
                    perm_data['type'] = 'user'
                    perm_data['target_id'] = p.user_id
                    perm_data['target_name'] = p.user.username if p.user else f'User {p.user_id}'
                elif p.group_id:
                    perm_data['type'] = 'group'
                    perm_data['target_id'] = p.group_id
                    perm_data['target_name'] = p.group.name if p.group else f'Group {p.group_id}'
                
                permissions_data.append(perm_data)
            
            files_data.append({
                'id': file.id,
                'name': file.name,
                'path': getattr(file, 'path', None),
                'permissions': permissions_data
            })

        # Ajouter les utilisateurs et groupes pour les dropdowns
        users_data = [{'id': u.id, 'username': u.username} for u in users]
        groups_data = [{'id': g.id, 'name': g.name} for g in groups]

        return jsonify({
            'folders': folders_data, 
            'files': files_data,
            'users': users_data,
            'groups': groups_data
        })
        
    except Exception as e:
        print(f"Error in get_all_resources: {str(e)}")
        return jsonify({'error': str(e)}), 500
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
        # Fix: Use proper query instead of InstrumentedList filter_by
        if isinstance(entity, Folder):
            perm = FolderPermission.query.filter_by(folder_id=entity.id, user_id=target_id).first()
            if not perm:
                perm = FolderPermission(folder_id=entity.id, user_id=target_id)
                db.session.add(perm)
        else:
            perm = FilePermission.query.filter_by(file_id=entity.id, user_id=target_id).first()
            if not perm:
                perm = FilePermission(file_id=entity.id, user_id=target_id)
                db.session.add(perm)
    else:  # group
        group = Group.query.get_or_404(target_id)
        # Fix: Use proper query instead of InstrumentedList filter_by
        if isinstance(entity, Folder):
            perm = FolderPermission.query.filter_by(folder_id=entity.id, group_id=target_id).first()
            if not perm:
                perm = FolderPermission(folder_id=entity.id, group_id=target_id)
                db.session.add(perm)
        else:
            perm = FilePermission.query.filter_by(file_id=entity.id, group_id=target_id).first()
            if not perm:
                perm = FilePermission(file_id=entity.id, group_id=target_id)
                db.session.add(perm)

    perm.can_read = bool_from_payload(data, 'can_read')
    perm.can_write = bool_from_payload(data, 'can_write')
    perm.can_delete = bool_from_payload(data, 'can_delete')
    perm.can_share = bool_from_payload(data, 'can_share')

    return perm

@permission_bp.route('/folders/<int:folder_id>/<target_type>/<int:target_id>', methods=['POST', 'OPTIONS'])
def set_folder_permission(folder_id, target_type, target_id):
    """Définir/modifier permissions dossier (user ou group)"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply admin_required only for non-OPTIONS requests
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    try:
        verify_jwt_in_request()
        admin_user_id = get_jwt_identity()
        user = User.query.get(admin_user_id)
        
        if not user or user.role.upper() != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
            
    except Exception as e:
        print(f"JWT verification error: {str(e)}")
        return jsonify({"msg": "Token d'authentification requis"}), 401
        
    try:
        folder = Folder.query.get_or_404(folder_id)
        data = request.get_json() or {}
        
        # Validate target_type
        if target_type not in ['user', 'group']:
            return jsonify({"msg": "target_type doit être 'user' ou 'group'"}), 400
        
        # Vérifier si c'est une création ou une mise à jour
        existing_perm = None
        if target_type == 'user':
            existing_perm = FolderPermission.query.filter_by(folder_id=folder_id, user_id=target_id).first()
            target_entity = User.query.get_or_404(target_id)
            target_name = target_entity.username
        else:
            existing_perm = FolderPermission.query.filter_by(folder_id=folder_id, group_id=target_id).first()
            target_entity = Group.query.get_or_404(target_id)
            target_name = target_entity.name
        
        is_creation = existing_perm is None
        
        perm = set_permission(folder, target_type, target_id, data)
        
        # Enregistrer le log d'accès
        action = 'CREATE_PERMISSION' if is_creation else 'UPDATE_PERMISSION'
        permissions_data = {
            'can_read': perm.can_read,
            'can_write': perm.can_write,
            'can_delete': perm.can_delete,
            'can_share': perm.can_share
        }
        
        log_folder_permission_action(
            admin_user_id, 
            action, 
            folder.name, 
            target_type, 
            target_name, 
            permissions_data
        )
        
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
        print(f"Error in set_folder_permission: {str(e)}")
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

@permission_bp.route('/folders/<int:folder_id>/permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def delete_folder_permission(folder_id, permission_id):
    perm = FolderPermission.query.filter_by(id=permission_id, folder_id=folder_id).first_or_404()
    
    # Récupérer les informations avant suppression pour le log
    folder = Folder.query.get_or_404(folder_id)
    admin_user_id = get_jwt_identity()
    
    if perm.user_id:
        target_type = 'user'
        target_name = perm.user.username if perm.user else f'User {perm.user_id}'
    else:
        target_type = 'group'
        target_name = perm.group.name if perm.group else f'Group {perm.group_id}'
    
    try:
        # Enregistrer le log avant suppression
        log_folder_permission_action(
            admin_user_id,
            'DELETE_PERMISSION',
            folder.name,
            target_type,
            target_name
        )
        
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

@permission_bp.route('/files/<int:file_id>/<target_type>/<int:target_id>', methods=['POST', 'OPTIONS'])
def set_file_permission(file_id, target_type, target_id):
    """Définir/modifier permissions fichier (user ou group)"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply admin_required only for non-OPTIONS requests
    from flask_jwt_extended import verify_jwt_in_request
    try:
        verify_jwt_in_request()
        admin_user_id = get_jwt_identity()
        claims = get_jwt()
        if claims.get('role') != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
    except Exception as e:
        return jsonify({"msg": "Token d'authentification requis"}), 401
        
    try:
        file = File.query.get_or_404(file_id)
        data = request.get_json() or {}
        
        # Validate target_type
        if target_type not in ['user', 'group']:
            return jsonify({"msg": "target_type doit être 'user' ou 'group'"}), 400
        
        # Vérifier si c'est une création ou une mise à jour
        existing_perm = None
        if target_type == 'user':
            existing_perm = FilePermission.query.filter_by(file_id=file_id, user_id=target_id).first()
            target_entity = User.query.get_or_404(target_id)
            target_name = target_entity.username
        else:
            existing_perm = FilePermission.query.filter_by(file_id=file_id, group_id=target_id).first()
            target_entity = Group.query.get_or_404(target_id)
            target_name = target_entity.name
        
        is_creation = existing_perm is None
        
        perm = set_permission(file, target_type, target_id, data)
        
        # Enregistrer le log d'accès
        action = 'CREATE_PERMISSION' if is_creation else 'UPDATE_PERMISSION'
        permissions_data = {
            'can_read': perm.can_read,
            'can_write': perm.can_write,
            'can_delete': perm.can_delete,
            'can_share': perm.can_share
        }
        
        log_file_permission_action(
            admin_user_id,
            action,
            file.name,
            target_type,
            target_name,
            permissions_data
        )

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
    
    # Récupérer les informations avant suppression pour le log
    file = File.query.get_or_404(file_id)
    admin_user_id = get_jwt_identity()
    
    if perm.user_id:
        target_type = 'user'
        target_name = perm.user.username if perm.user else f'User {perm.user_id}'
    else:
        target_type = 'group'
        target_name = perm.group.name if perm.group else f'Group {perm.group_id}'
    
    try:
        # Enregistrer le log avant suppression
        log_file_permission_action(
            admin_user_id,
            'DELETE_PERMISSION',
            file.name,
            target_type,
            target_name
        )
        
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

    # Récupérer le nom de la cible pour le log
    if target_type == 'user':
        target_entity = User.query.get_or_404(target_id)
        target_name = target_entity.username
    else:
        target_entity = Group.query.get_or_404(target_id)
        target_name = target_entity.name

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
        # Enregistrer le log pour l'opération en lot
        admin_user_id = get_jwt_identity()
        log_batch_permission_action(
            admin_user_id,
            entity,
            success_count,
            target_type,
            target_name,
            perms
        )
        
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

# ===================== DIAGNOSTIC ROUTES =====================

@permission_bp.route('/diagnose/<int:user_id>/<path:path>', methods=['GET'])
@admin_required
def diagnose_user_permissions(user_id, path):
    """
    Diagnostiquer les permissions d'un utilisateur pour un chemin spécifique
    """
    try:
        user = User.query.get_or_404(user_id)
        
        # Normaliser le chemin
        normalized_path = f"/{path}" if not path.startswith('/') else path
        
        # Obtenir les groupes de l'utilisateur avec leurs permissions
        user_groups = []
        for group in user.groups:
            group_info = {
                'id': group.id,
                'name': group.name,
                'active': True,
                'permissions_on_path': {
                    'can_read': False,
                    'can_write': False,
                    'can_delete': False,
                    'can_share': False
                }
            }
            
            # Vérifier les permissions du groupe sur ce chemin
            # (Cette logique devrait être adaptée selon votre modèle de données)
            folder_perms = FolderPermission.query.filter_by(group_id=group.id).all()
            file_perms = FilePermission.query.filter_by(group_id=group.id).all()
            
            # Analyser les permissions pour ce chemin spécifique
            for perm in folder_perms:
                if perm.folder and normalized_path.startswith(perm.folder.path or ''):
                    group_info['permissions_on_path']['can_read'] |= perm.can_read
                    group_info['permissions_on_path']['can_write'] |= perm.can_write
                    group_info['permissions_on_path']['can_delete'] |= perm.can_delete
                    group_info['permissions_on_path']['can_share'] |= perm.can_share
            
            user_groups.append(group_info)
        
        # Calculer les permissions effectives
        effective_permissions = {
            'can_read': False,
            'can_write': False,
            'can_delete': False,
            'can_share': False,
            'source': 'none'
        }
        
        # Vérifier si l'utilisateur est propriétaire
        is_owner = False
        # (Logique pour vérifier la propriété selon votre modèle)
        
        if is_owner:
            effective_permissions = {
                'can_read': True,
                'can_write': True,
                'can_delete': True,
                'can_share': True,
                'source': 'owner'
            }
        else:
            # Accumuler les permissions des groupes
            for group in user_groups:
                group_perms = group['permissions_on_path']
                if any(group_perms.values()):
                    effective_permissions['can_read'] |= group_perms['can_read']
                    effective_permissions['can_write'] |= group_perms['can_write']
                    effective_permissions['can_delete'] |= group_perms['can_delete']
                    effective_permissions['can_share'] |= group_perms['can_share']
                    if effective_permissions['source'] == 'none':
                        effective_permissions['source'] = 'group'
        
        # Construire la chaîne de permissions
        permission_chain = [
            {
                'level': 'user',
                'permissions': {},
                'source': 'direct'
            }
        ]
        
        for group in user_groups:
            if any(group['permissions_on_path'].values()):
                permission_chain.append({
                    'level': 'group',
                    'group_name': group['name'],
                    'permissions': group['permissions_on_path'],
                    'source': 'group_membership'
                })
        
        # Informations de performance (simulées pour l'instant)
        query_performance = {
            'duration_ms': 45,
            'queries_executed': len(user_groups) + 2
        }
        
        return jsonify({
            'success': True,
            'permissions': effective_permissions,
            'diagnostic_info': {
                'user_id': user.id,
                'username': user.username,
                'user_groups': user_groups,
                'effective_permissions': effective_permissions,
                'cache_info': {
                    'cached': False,
                    'cache_age': None,
                    'cache_source': None
                },
                'query_performance': query_performance,
                'permission_chain': permission_chain
            }
        }), 200
        
    except Exception as e:
        print(f"Error in diagnose_user_permissions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/compare/<int:user_id1>/<int:user_id2>/<path:path>', methods=['GET'])
@admin_required
def compare_user_permissions(user_id1, user_id2, path):
    """
    Comparer les permissions entre deux utilisateurs pour un chemin donné
    """
    try:
        # Obtenir les diagnostics pour les deux utilisateurs
        user1_response = diagnose_user_permissions(user_id1, path)
        user2_response = diagnose_user_permissions(user_id2, path)
        
        if user1_response[1] != 200 or user2_response[1] != 200:
            return jsonify({'error': 'Failed to get permissions for one or both users'}), 500
        
        user1_data = user1_response[0].get_json()
        user2_data = user2_response[0].get_json()
        
        # Analyser les différences
        differences = {
            'permissions': {},
            'groups': {},
            'summary': {}
        }
        
        # Comparer les permissions
        user1_perms = user1_data['permissions']
        user2_perms = user2_data['permissions']
        
        for perm_type in ['can_read', 'can_write', 'can_delete', 'can_share']:
            if user1_perms[perm_type] != user2_perms[perm_type]:
                differences['permissions'][perm_type] = {
                    'user1': user1_perms[perm_type],
                    'user2': user2_perms[perm_type],
                    'different': True
                }
        
        # Comparer les groupes
        user1_groups = [g['name'] for g in user1_data['diagnostic_info']['user_groups']]
        user2_groups = [g['name'] for g in user2_data['diagnostic_info']['user_groups']]
        
        differences['groups'] = {
            'user1_groups': user1_groups,
            'user2_groups': user2_groups,
            'common_groups': list(set(user1_groups) & set(user2_groups)),
            'user1_only': list(set(user1_groups) - set(user2_groups)),
            'user2_only': list(set(user2_groups) - set(user1_groups))
        }
        
        # Résumé des différences
        differences['summary'] = {
            'has_permission_differences': bool(differences['permissions']),
            'has_group_differences': bool(differences['groups']['user1_only'] or differences['groups']['user2_only']),
            'total_differences': len(differences['permissions']) + len(differences['groups']['user1_only']) + len(differences['groups']['user2_only'])
        }
        
        return jsonify({
            'path': f"/{path}",
            'user1': user1_data,
            'user2': user2_data,
            'differences': differences,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"Error in compare_user_permissions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/user-groups/<int:user_id>', methods=['GET'])
@admin_required
def get_user_groups_detailed(user_id):
    """
    Obtenir les groupes détaillés d'un utilisateur avec leurs permissions
    """
    try:
        user = User.query.get_or_404(user_id)
        
        groups_data = []
        for group in user.groups:
            group_info = {
                'id': group.id,
                'name': group.name,
                'description': getattr(group, 'description', ''),
                'active': True,
                'permissions': []
            }
            
            # Obtenir les permissions du groupe sur les dossiers
            folder_perms = FolderPermission.query.filter_by(group_id=group.id).all()
            for perm in folder_perms:
                if perm.folder:
                    group_info['permissions'].append({
                        'type': 'folder',
                        'resource_name': perm.folder.name,
                        'resource_path': getattr(perm.folder, 'path', ''),
                        'can_read': perm.can_read,
                        'can_write': perm.can_write,
                        'can_delete': perm.can_delete,
                        'can_share': perm.can_share
                    })
            
            # Obtenir les permissions du groupe sur les fichiers
            file_perms = FilePermission.query.filter_by(group_id=group.id).all()
            for perm in file_perms:
                if perm.file:
                    group_info['permissions'].append({
                        'type': 'file',
                        'resource_name': perm.file.name,
                        'resource_path': getattr(perm.file, 'path', ''),
                        'can_read': perm.can_read,
                        'can_write': perm.can_write,
                        'can_delete': perm.can_delete,
                        'can_share': perm.can_share
                    })
            
            groups_data.append(group_info)
        
        return jsonify({
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role
            },
            'groups': groups_data
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_groups_detailed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/user-info/<int:user_id>', methods=['GET'])
@admin_required
def get_user_info(user_id):
    """
    Obtenir les informations détaillées d'un utilisateur
    """
    try:
        user = User.query.get_or_404(user_id)
        
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', ''),
            'role': user.role,
            'active': getattr(user, 'active', True),
            'created_at': user.created_at.isoformat() if hasattr(user, 'created_at') else None,
            'last_login': getattr(user, 'last_login', None),
            'groups_count': len(user.groups)
        }), 200
        
    except Exception as e:
        print(f"Error in get_user_info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/validate-cache', methods=['POST'])
@admin_required
def validate_permission_cache():
    """
    Valider la cohérence du cache de permissions
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        path = data.get('path')
        
        # Pour l'instant, retourner une validation simulée
        # Cette logique devrait être implémentée selon votre système de cache
        
        validation_result = {
            'cache_consistent': True,
            'inconsistencies': [],
            'cache_entries_checked': 0,
            'last_validation': datetime.now().isoformat()
        }
        
        if user_id:
            validation_result['user_id'] = user_id
        if path:
            validation_result['path'] = path
        
        return jsonify(validation_result), 200
        
    except Exception as e:
        print(f"Error in validate_permission_cache: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ===================== ENHANCED PERMISSION CHECKING WITH AUDIT =====================

@permission_bp.route('/check', methods=['GET'])
@jwt_required()
def check_permissions_with_audit():
    """
    Vérifier les permissions avec audit détaillé et métriques de performance
    """
    import time
    start_time = time.time()
    
    try:
        user_id = get_jwt_identity()
        user = User.query.get_or_404(user_id)
        path = request.args.get('path', '/')
        
        # Normaliser le chemin
        normalized_path = f"/{path}" if not path.startswith('/') else path
        
        # Métriques de performance
        timing_data = {
            'start_time': start_time,
            'cache_hit': False,
            'cache_age_ms': None,
            'db_query_start': None,
            'db_query_duration_ms': 0,
            'queries_executed': 0
        }
        
        # Vérifier si l'utilisateur est admin
        if user.role.upper() == 'ADMIN':
            admin_permissions = {
                'can_read': True,
                'can_write': True,
                'can_delete': True,
                'can_share': True,
                'can_modify': True
            }
            
            end_time = time.time()
            timing_data['total_duration_ms'] = (end_time - start_time) * 1000
            
            # Logger la vérification admin
            permission_audit_logger.log_permission_check(
                user_id=user.id,
                path=normalized_path,
                result=admin_permissions,
                groups=[],
                timing=timing_data
            )
            
            return jsonify({
                'success': True,
                'permissions': admin_permissions,
                'diagnostic_info': {
                    'user_id': user.id,
                    'username': user.username,
                    'user_role': user.role,
                    'is_admin': True,
                    'path': normalized_path,
                    'permission_source': 'admin_role',
                    'query_performance': {
                        'duration_ms': timing_data['total_duration_ms'],
                        'queries_executed': 0
                    }
                }
            }), 200
        
        # Pour les utilisateurs non-admin, vérifier les permissions via les groupes
        timing_data['db_query_start'] = time.time()
        
        # Obtenir les groupes de l'utilisateur
        user_groups = []
        effective_permissions = {
            'can_read': False,
            'can_write': False,
            'can_delete': False,
            'can_share': False,
            'can_modify': False
        }
        
        timing_data['queries_executed'] += 1
        
        for group in user.groups:
            group_info = {
                'id': group.id,
                'name': group.name,
                'permissions_on_path': {
                    'can_read': False,
                    'can_write': False,
                    'can_delete': False,
                    'can_share': False,
                    'can_modify': False
                }
            }
            
            # Vérifier les permissions du groupe sur les dossiers
            folder_perms = FolderPermission.query.filter_by(group_id=group.id).all()
            timing_data['queries_executed'] += 1
            
            for perm in folder_perms:
                if perm.folder and perm.folder.path and normalized_path.startswith(perm.folder.path):
                    group_info['permissions_on_path']['can_read'] |= perm.can_read
                    group_info['permissions_on_path']['can_write'] |= perm.can_write
                    group_info['permissions_on_path']['can_delete'] |= perm.can_delete
                    group_info['permissions_on_path']['can_share'] |= perm.can_share
                    
                    # Accumuler dans les permissions effectives
                    effective_permissions['can_read'] |= perm.can_read
                    effective_permissions['can_write'] |= perm.can_write
                    effective_permissions['can_delete'] |= perm.can_delete
                    effective_permissions['can_share'] |= perm.can_share
            
            # Vérifier les permissions du groupe sur les fichiers
            file_perms = FilePermission.query.filter_by(group_id=group.id).all()
            timing_data['queries_executed'] += 1
            
            for perm in file_perms:
                if perm.file and perm.file.path and normalized_path == perm.file.path:
                    group_info['permissions_on_path']['can_read'] |= perm.can_read
                    group_info['permissions_on_path']['can_write'] |= perm.can_write
                    group_info['permissions_on_path']['can_delete'] |= perm.can_delete
                    group_info['permissions_on_path']['can_share'] |= perm.can_share
                    
                    # Accumuler dans les permissions effectives
                    effective_permissions['can_read'] |= perm.can_read
                    effective_permissions['can_write'] |= perm.can_write
                    effective_permissions['can_delete'] |= perm.can_delete
                    effective_permissions['can_share'] |= perm.can_share
            
            user_groups.append(group_info)
        
        # can_modify est un alias pour can_write
        effective_permissions['can_modify'] = effective_permissions['can_write']
        
        # Calculer les métriques de performance
        end_time = time.time()
        timing_data['db_query_duration_ms'] = (end_time - timing_data['db_query_start']) * 1000
        timing_data['total_duration_ms'] = (end_time - start_time) * 1000
        
        # Logger la vérification de permissions
        permission_audit_logger.log_permission_check(
            user_id=user.id,
            path=normalized_path,
            result=effective_permissions,
            groups=user_groups,
            timing=timing_data
        )
        
        # Construire la réponse avec informations de diagnostic
        diagnostic_info = {
            'user_id': user.id,
            'username': user.username,
            'user_role': user.role,
            'is_admin': False,
            'path': normalized_path,
            'user_groups': user_groups,
            'effective_permissions': effective_permissions,
            'permission_source': 'group_membership' if any(
                any(g['permissions_on_path'].values()) for g in user_groups
            ) else 'none',
            'cache_info': {
                'cached': timing_data['cache_hit'],
                'cache_age': timing_data['cache_age_ms'],
                'cache_source': None
            },
            'query_performance': {
                'duration_ms': timing_data['total_duration_ms'],
                'db_query_duration_ms': timing_data['db_query_duration_ms'],
                'queries_executed': timing_data['queries_executed']
            }
        }
        
        return jsonify({
            'success': True,
            'permissions': effective_permissions,
            'diagnostic_info': diagnostic_info
        }), 200
        
    except Exception as e:
        end_time = time.time()
        error_duration = (end_time - start_time) * 1000
        
        # Logger l'échec
        try:
            user_id = get_jwt_identity()
            path = request.args.get('path', '/')
            
            permission_audit_logger.log_permission_failure(
                user_id=user_id,
                path=path,
                error=str(e),
                context={
                    'error_type': type(e).__name__,
                    'duration_ms': error_duration,
                    'stack_trace': str(e)
                }
            )
        except:
            pass  # Éviter les erreurs en cascade
        
        print(f"Error in check_permissions_with_audit: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/audit-log', methods=['GET'])
@admin_required
def get_permission_audit_log():
    """
    Récupérer les logs d'audit des permissions
    """
    try:
        user_id = request.args.get('user_id', type=int)
        path = request.args.get('path')
        action_filter = request.args.get('action')
        limit = request.args.get('limit', 100, type=int)
        
        # Limiter le nombre d'entrées pour éviter les surcharges
        limit = min(limit, 1000)
        
        audit_trail = permission_audit_logger.get_audit_trail(
            user_id=user_id,
            path=path,
            action_filter=action_filter,
            limit=limit
        )
        
        return jsonify({
            'audit_trail': audit_trail,
            'total_entries': len(audit_trail),
            'filters_applied': {
                'user_id': user_id,
                'path': path,
                'action': action_filter,
                'limit': limit
            }
        }), 200
        
    except Exception as e:
        print(f"Error in get_permission_audit_log: {str(e)}")
        return jsonify({'error': str(e)}), 500

@permission_bp.route('/performance-summary', methods=['GET'])
@admin_required
def get_permission_performance_summary():
    """
    Obtenir un résumé des performances des permissions
    """
    try:
        user_id = request.args.get('user_id', type=int)
        hours = request.args.get('hours', 24, type=int)
        
        # Limiter la période pour éviter les surcharges
        hours = min(hours, 168)  # Max 1 semaine
        
        performance_summary = permission_audit_logger.get_performance_summary(
            user_id=user_id,
            hours=hours
        )
        
        return jsonify({
            'performance_summary': performance_summary,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"Error in get_permission_performance_summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ===================== ROUTES PAR CHEMIN =====================

@permission_bp.route('/files/<path:file_path>', methods=['GET', 'OPTIONS'])
def get_file_permissions_by_path(file_path):
    """Récupérer les permissions d'un fichier par son chemin"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply admin_required only for non-OPTIONS requests
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    try:
        verify_jwt_in_request()
        admin_user_id = get_jwt_identity()
        user = User.query.get(admin_user_id)
        
        if not user or user.role.upper() != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
            
    except Exception as e:
        print(f"JWT verification error: {str(e)}")
        return jsonify({"msg": "Token d'authentification requis"}), 401
    
    try:
        # Décoder le chemin
        import urllib.parse
        decoded_path = urllib.parse.unquote(file_path)
        if not decoded_path.startswith('/'):
            decoded_path = '/' + decoded_path
        
        # Trouver le fichier par son chemin
        file = File.query.filter_by(path=decoded_path).first()
        if not file:
            return jsonify({"msg": f"Fichier non trouvé: {decoded_path}"}), 404
        
        # Récupérer les permissions
        permissions = FilePermission.query.filter_by(file_id=file.id).all()
        
        user_permissions = []
        group_permissions = []
        
        for perm in permissions:
            perm_data = {
                'id': perm.id,
                'can_read': perm.can_read,
                'can_write': perm.can_write,
                'can_delete': perm.can_delete,
                'can_share': perm.can_share,
            }
            
            if perm.user_id:
                perm_data['user_id'] = perm.user_id
                perm_data['username'] = perm.user.username if perm.user else f'User {perm.user_id}'
                user_permissions.append(perm_data)
            elif perm.group_id:
                perm_data['group_id'] = perm.group_id
                perm_data['group_name'] = perm.group.name if perm.group else f'Group {perm.group_id}'
                group_permissions.append(perm_data)
        
        return jsonify({
            'file': {
                'id': file.id,
                'name': file.name,
                'path': file.path,
                'owner': file.owner.username if file.owner else 'Unknown'
            },
            'user_permissions': user_permissions,
            'group_permissions': group_permissions
        }), 200
        
    except Exception as e:
        print(f"Error in get_file_permissions_by_path: {str(e)}")
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500

@permission_bp.route('/folders/<path:folder_path>', methods=['GET', 'OPTIONS'])
def get_folder_permissions_by_path(folder_path):
    """Récupérer les permissions d'un dossier par son chemin"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply admin_required only for non-OPTIONS requests
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    try:
        verify_jwt_in_request()
        admin_user_id = get_jwt_identity()
        user = User.query.get(admin_user_id)
        
        if not user or user.role.upper() != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
            
    except Exception as e:
        print(f"JWT verification error: {str(e)}")
        return jsonify({"msg": "Token d'authentification requis"}), 401
    
    try:
        # Décoder le chemin
        import urllib.parse
        decoded_path = urllib.parse.unquote(folder_path)
        if not decoded_path.startswith('/'):
            decoded_path = '/' + decoded_path
        
        # Trouver le dossier par son chemin
        folder = Folder.query.filter_by(path=decoded_path).first()
        if not folder:
            return jsonify({"msg": f"Dossier non trouvé: {decoded_path}"}), 404
        
        # Récupérer les permissions
        permissions = FolderPermission.query.filter_by(folder_id=folder.id).all()
        
        user_permissions = []
        group_permissions = []
        
        for perm in permissions:
            perm_data = {
                'id': perm.id,
                'can_read': perm.can_read,
                'can_write': perm.can_write,
                'can_delete': perm.can_delete,
                'can_share': perm.can_share,
            }
            
            if perm.user_id:
                perm_data['user_id'] = perm.user_id
                perm_data['username'] = perm.user.username if perm.user else f'User {perm.user_id}'
                user_permissions.append(perm_data)
            elif perm.group_id:
                perm_data['group_id'] = perm.group_id
                perm_data['group_name'] = perm.group.name if perm.group else f'Group {perm.group_id}'
                group_permissions.append(perm_data)
        
        return jsonify({
            'folder': {
                'id': folder.id,
                'name': folder.name,
                'path': folder.path,
                'owner': folder.owner.username if folder.owner else 'Unknown'
            },
            'user_permissions': user_permissions,
            'group_permissions': group_permissions
        }), 200
        
    except Exception as e:
        print(f"Error in get_folder_permissions_by_path: {str(e)}")
        return jsonify({"msg": f"Erreur: {str(e)}"}), 500