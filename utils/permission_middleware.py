# utils/permission_middleware.py

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from models.user import User
from models.file import File
from models.folder import Folder

def require_resource_permission(resource_type, action):
    """
    Décorateur pour vérifier les permissions sur une ressource spécifique
    
    Args:
        resource_type: 'file' ou 'folder'
        action: 'read', 'write', 'delete', 'share'
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(resource_id, *args, **kwargs):
            verify_jwt_in_request()
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            
            if not user:
                return jsonify({"msg": "Utilisateur non trouvé"}), 404

            # Les admins ont tous les droits
            if user.role == 'admin':
                return f(resource_id, *args, **kwargs)

            # Vérifier les permissions sur la ressource
            if resource_type == 'file':
                resource = File.query.get_or_404(resource_id)
                # Le propriétaire a tous les droits
                if resource.owner_id == user.id:
                    return f(resource_id, *args, **kwargs)
                
                # Vérifier les permissions effectives
                effective_perm = resource.get_effective_permissions(user)
                if not effective_perm:
                    return jsonify({"msg": "Accès refusé"}), 403
                    
            elif resource_type == 'folder':
                resource = Folder.query.get_or_404(resource_id)
                # Le propriétaire a tous les droits
                if resource.owner_id == user.id:
                    return f(resource_id, *args, **kwargs)
                
                # Vérifier les permissions effectives
                effective_perm = resource.get_effective_permissions(user)
                if not effective_perm:
                    return jsonify({"msg": "Accès refusé"}), 403
            else:
                return jsonify({"msg": "Type de ressource invalide"}), 400

            # Vérifier l'action spécifique
            permission_map = {
                'read': 'can_read',
                'write': 'can_write', 
                'delete': 'can_delete',
                'share': 'can_share'
            }
            
            if action not in permission_map:
                return jsonify({"msg": "Action invalide"}), 400
                
            if not getattr(effective_perm, permission_map[action], False):
                return jsonify({"msg": f"Permission '{action}' refusée"}), 403

            return f(resource_id, *args, **kwargs)
        return decorated_function
    return decorator

def check_user_can_access_resource(user, resource, action='read'):
    """
    Vérifie si un utilisateur peut accéder à une ressource
    
    Args:
        user: Instance User
        resource: Instance File ou Folder
        action: 'read', 'write', 'delete', 'share'
    
    Returns:
        bool: True si l'accès est autorisé
    """
    # Admin a tous les droits
    if user.role == 'admin':
        return True
        
    # Propriétaire a tous les droits
    if resource.owner_id == user.id:
        return True
    
    # Vérifier permissions effectives
    effective_perm = resource.get_effective_permissions(user)
    if not effective_perm:
        return False
        
    permission_map = {
        'read': 'can_read',
        'write': 'can_write',
        'delete': 'can_delete', 
        'share': 'can_share'
    }
    
    return getattr(effective_perm, permission_map.get(action, 'can_read'), False)

def get_user_accessible_resources(user, resource_type='both'):
    """
    Récupère toutes les ressources accessibles par un utilisateur
    
    Args:
        user: Instance User
        resource_type: 'files', 'folders', ou 'both'
    
    Returns:
        dict: {'files': [...], 'folders': [...]}
    """
    accessible = {'files': [], 'folders': []}
    
    if user.role == 'admin':
        # Admin voit tout
        if resource_type in ['files', 'both']:
            accessible['files'] = File.query.all()
        if resource_type in ['folders', 'both']:
            accessible['folders'] = Folder.query.all()
        return accessible
    
    # Ressources possédées
    if resource_type in ['files', 'both']:
        accessible['files'].extend(File.query.filter_by(owner_id=user.id).all())
    if resource_type in ['folders', 'both']:
        accessible['folders'].extend(Folder.query.filter_by(owner_id=user.id).all())
    
    # Ressources partagées via permissions directes
    for file_perm in user.file_permissions:
        if file_perm.can_read and file_perm.file not in accessible['files']:
            accessible['files'].append(file_perm.file)
            
    for folder_perm in user.folder_permissions:
        if folder_perm.can_read and folder_perm.folder not in accessible['folders']:
            accessible['folders'].append(folder_perm.folder)
    
    # Ressources partagées via groupes
    for group in user.groups:
        for file_perm in group.file_permissions:
            if file_perm.can_read and file_perm.file not in accessible['files']:
                accessible['files'].append(file_perm.file)
                
        for folder_perm in group.folder_permissions:
            if folder_perm.can_read and folder_perm.folder not in accessible['folders']:
                accessible['folders'].append(folder_perm.folder)
    
    return accessible