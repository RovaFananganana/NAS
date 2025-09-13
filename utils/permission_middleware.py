# utils/permission_middleware.py

from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from models.user import User
from models.file import File
from models.folder import Folder
from services.permission_optimizer import PermissionOptimizer
from typing import List, Dict, Union

# Initialize permission optimizer with caching enabled
permission_optimizer = PermissionOptimizer(enable_cache=True)

def require_resource_permission(resource_type, action):
    """
    Décorateur optimisé pour vérifier les permissions sur une ressource spécifique.
    Utilise le cache de permissions pour des performances améliorées.
    
    Args:
        resource_type: 'file' ou 'folder'
        action: 'read', 'write', 'delete', 'share'
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(resource_id, *args, **kwargs):
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            user = User.query.get(user_id)
            
            if not user:
                return jsonify({"msg": "Utilisateur non trouvé"}), 404

            # Les admins ont tous les droits
            if user.role == 'admin':
                return f(resource_id, *args, **kwargs)

            # Vérifier que la ressource existe
            if resource_type == 'file':
                resource = File.query.get_or_404(resource_id)
                # Le propriétaire a tous les droits
                if resource.owner_id == user_id:
                    return f(resource_id, *args, **kwargs)
            elif resource_type == 'folder':
                resource = Folder.query.get_or_404(resource_id)
                # Le propriétaire a tous les droits
                if resource.owner_id == user_id:
                    return f(resource_id, *args, **kwargs)
            else:
                return jsonify({"msg": "Type de ressource invalide"}), 400

            # Utiliser l'optimiseur de permissions avec cache
            if resource_type == 'file':
                permissions = permission_optimizer.get_bulk_file_permissions(user_id, [resource_id])
            else:
                permissions = permission_optimizer.get_bulk_folder_permissions(user_id, [resource_id])
            
            effective_perm = permissions.get(resource_id)
            if not effective_perm:
                return jsonify({"msg": "Accès refusé"}), 403

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
    Vérifie si un utilisateur peut accéder à une ressource en utilisant le cache optimisé.
    
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
    
    # Déterminer le type de ressource
    resource_type = 'file' if isinstance(resource, File) else 'folder'
    
    # Utiliser l'optimiseur de permissions avec cache
    if resource_type == 'file':
        permissions = permission_optimizer.get_bulk_file_permissions(user.id, [resource.id])
    else:
        permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [resource.id])
    
    effective_perm = permissions.get(resource.id)
    if not effective_perm:
        return False
        
    permission_map = {
        'read': 'can_read',
        'write': 'can_write',
        'delete': 'can_delete', 
        'share': 'can_share'
    }
    
    return getattr(effective_perm, permission_map.get(action, 'can_read'), False)

def get_user_accessible_resources(user, resource_type='both', limit=None):
    """
    Récupère toutes les ressources accessibles par un utilisateur en utilisant le chargement optimisé.
    
    Args:
        user: Instance User
        resource_type: 'files', 'folders', ou 'both'
        limit: Limite optionnelle du nombre de ressources à retourner par type
    
    Returns:
        dict: {'files': [...], 'folders': [...]}
    """
    accessible = {'files': [], 'folders': []}
    
    if user.role == 'admin':
        # Admin voit tout
        if resource_type in ['files', 'both']:
            query = File.query
            if limit:
                query = query.limit(limit)
            accessible['files'] = query.all()
        if resource_type in ['folders', 'both']:
            query = Folder.query
            if limit:
                query = query.limit(limit)
            accessible['folders'] = query.all()
        return accessible
    
    # Pour les utilisateurs non-admin, utiliser le chargement optimisé
    if resource_type in ['files', 'both']:
        accessible['files'] = get_user_accessible_files_optimized(user, limit)
    
    if resource_type in ['folders', 'both']:
        accessible['folders'] = get_user_accessible_folders_optimized(user, limit)
    
    return accessible

def get_user_accessible_files_optimized(user, limit=None):
    """
    Récupère les fichiers accessibles par un utilisateur de manière optimisée.
    
    Args:
        user: Instance User
        limit: Limite optionnelle du nombre de fichiers
    
    Returns:
        List[File]: Liste des fichiers accessibles
    """
    from sqlalchemy import text
    from extensions import db
    
    # Requête optimisée pour obtenir les IDs des fichiers potentiellement accessibles
    query = text("""
        SELECT DISTINCT f.id
        FROM files f
        LEFT JOIN file_permissions fp_user ON f.id = fp_user.file_id AND fp_user.user_id = :user_id
        LEFT JOIN file_permissions fp_group ON f.id = fp_group.file_id 
        LEFT JOIN user_group ug ON fp_group.group_id = ug.group_id AND ug.user_id = :user_id
        LEFT JOIN folders fold ON f.folder_id = fold.id
        LEFT JOIN folder_permissions folp_user ON fold.id = folp_user.folder_id AND folp_user.user_id = :user_id
        LEFT JOIN folder_permissions folp_group ON fold.id = folp_group.folder_id
        LEFT JOIN user_group ug2 ON folp_group.group_id = ug2.group_id AND ug2.user_id = :user_id
        WHERE f.owner_id = :user_id
           OR fp_user.can_read = true
           OR fp_group.can_read = true
           OR folp_user.can_read = true
           OR folp_group.can_read = true
        ORDER BY f.id
        """ + (f"LIMIT {limit}" if limit else ""))
    
    result = db.session.execute(query, {'user_id': user.id})
    candidate_file_ids = [row[0] for row in result]
    
    if not candidate_file_ids:
        return []
    
    # Utiliser le chargement en lot pour vérifier les permissions réelles
    file_permissions = permission_optimizer.get_bulk_file_permissions(user.id, candidate_file_ids)
    
    # Filtrer les fichiers avec permissions de lecture
    accessible_file_ids = [
        file_id for file_id, perm in file_permissions.items() 
        if perm and perm.can_read
    ]
    
    if not accessible_file_ids:
        return []
    
    # Récupérer les objets File
    return File.query.filter(File.id.in_(accessible_file_ids)).all()

def get_user_accessible_folders_optimized(user, limit=None):
    """
    Récupère les dossiers accessibles par un utilisateur de manière optimisée.
    
    Args:
        user: Instance User
        limit: Limite optionnelle du nombre de dossiers
    
    Returns:
        List[Folder]: Liste des dossiers accessibles
    """
    from sqlalchemy import text
    from extensions import db
    
    # Requête optimisée pour obtenir les IDs des dossiers potentiellement accessibles
    query = text("""
        SELECT DISTINCT f.id
        FROM folders f
        LEFT JOIN folder_permissions fp_user ON f.id = fp_user.folder_id AND fp_user.user_id = :user_id
        LEFT JOIN folder_permissions fp_group ON f.id = fp_group.folder_id
        LEFT JOIN user_group ug ON fp_group.group_id = ug.group_id AND ug.user_id = :user_id
        WHERE f.owner_id = :user_id
           OR fp_user.can_read = true
           OR fp_group.can_read = true
        ORDER BY f.id
        """ + (f"LIMIT {limit}" if limit else ""))
    
    result = db.session.execute(query, {'user_id': user.id})
    candidate_folder_ids = [row[0] for row in result]
    
    if not candidate_folder_ids:
        return []
    
    # Utiliser le chargement en lot pour vérifier les permissions réelles
    folder_permissions = permission_optimizer.get_bulk_folder_permissions(user.id, candidate_folder_ids)
    
    # Filtrer les dossiers avec permissions de lecture
    accessible_folder_ids = [
        folder_id for folder_id, perm in folder_permissions.items() 
        if perm and perm.can_read
    ]
    
    if not accessible_folder_ids:
        return []
    
    # Récupérer les objets Folder
    return Folder.query.filter(Folder.id.in_(accessible_folder_ids)).all()

def check_batch_resource_permissions(user_id: int, resources: List[Dict], action: str = 'read') -> Dict[int, bool]:
    """
    Vérifie les permissions pour plusieurs ressources en une seule opération optimisée.
    
    Args:
        user_id: ID de l'utilisateur
        resources: Liste de dictionnaires avec 'id', 'type' ('file' ou 'folder')
        action: Action à vérifier ('read', 'write', 'delete', 'share')
    
    Returns:
        Dict[int, bool]: Dictionnaire mapping resource_id -> permission accordée
    """
    user = User.query.get(user_id)
    if not user:
        return {}
    
    # Admin a tous les droits
    if user.role == 'admin':
        return {res['id']: True for res in resources}
    
    # Séparer les fichiers et dossiers
    file_ids = [res['id'] for res in resources if res['type'] == 'file']
    folder_ids = [res['id'] for res in resources if res['type'] == 'folder']
    
    results = {}
    
    # Vérifier les permissions des fichiers en lot
    if file_ids:
        file_permissions = permission_optimizer.get_bulk_file_permissions(user_id, file_ids)
        for file_id in file_ids:
            perm = file_permissions.get(file_id)
            results[file_id] = perm and getattr(perm, f'can_{action}', False) if perm else False
    
    # Vérifier les permissions des dossiers en lot
    if folder_ids:
        folder_permissions = permission_optimizer.get_bulk_folder_permissions(user_id, folder_ids)
        for folder_id in folder_ids:
            perm = folder_permissions.get(folder_id)
            results[folder_id] = perm and getattr(perm, f'can_{action}', False) if perm else False
    
    return results

def require_batch_resource_permissions(resources_param: str = 'resources', action: str = 'read'):
    """
    Décorateur pour vérifier les permissions sur plusieurs ressources en une seule opération.
    
    Args:
        resources_param: Nom du paramètre contenant la liste des ressources
        action: Action à vérifier
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            verify_jwt_in_request()
            user_id = int(get_jwt_identity())
            user = User.query.get(user_id)
            
            if not user:
                return jsonify({"msg": "Utilisateur non trouvé"}), 404

            # Admin a tous les droits
            if user.role == 'admin':
                return f(*args, **kwargs)

            # Récupérer la liste des ressources depuis les arguments
            from flask import request
            resources = request.json.get(resources_param, []) if request.json else []
            
            if not resources:
                return jsonify({"msg": "Aucune ressource spécifiée"}), 400

            # Vérifier les permissions en lot
            permission_results = check_batch_resource_permissions(user_id, resources, action)
            
            # Vérifier que toutes les ressources sont autorisées
            unauthorized_resources = [
                res['id'] for res in resources 
                if not permission_results.get(res['id'], False)
            ]
            
            if unauthorized_resources:
                return jsonify({
                    "msg": f"Permission '{action}' refusée",
                    "unauthorized_resources": unauthorized_resources
                }), 403

            # Ajouter les résultats des permissions aux kwargs pour utilisation dans la fonction
            kwargs['permission_results'] = permission_results
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def invalidate_permission_cache_on_change(resource_type: str, resource_id: int, user_ids: List[int] = None):
    """
    Invalide le cache de permissions lors de changements de permissions.
    
    Args:
        resource_type: 'file' ou 'folder'
        resource_id: ID de la ressource
        user_ids: Liste optionnelle des IDs utilisateurs affectés
    """
    if resource_type == 'file':
        permission_optimizer.on_file_permission_changed(resource_id, user_ids)
    elif resource_type == 'folder':
        permission_optimizer.on_folder_permission_changed(resource_id, user_ids)

def invalidate_user_cache_on_group_change(user_id: int):
    """
    Invalide le cache d'un utilisateur lors de changements de groupes.
    
    Args:
        user_id: ID de l'utilisateur
    """
    permission_optimizer.on_user_group_changed(user_id)

def warm_user_permission_cache(user_id: int, resource_type: str = None, limit: int = 100):
    """
    Préchauffe le cache de permissions pour un utilisateur.
    
    Args:
        user_id: ID de l'utilisateur
        resource_type: Type de ressource à préchauffer ('file', 'folder', ou None pour les deux)
        limit: Nombre maximum de ressources à préchauffer par type
    
    Returns:
        Dict: Statistiques du préchauffage
    """
    return permission_optimizer.warm_cache_for_user(user_id, resource_type, limit)

def get_permission_cache_stats():
    """
    Récupère les statistiques du cache de permissions.
    
    Returns:
        Dict: Statistiques du cache
    """
    return permission_optimizer.get_cache_statistics()

def optimize_inherited_permissions(user_id: int, folder_id: int, max_depth: int = 3):
    """
    Optimise la résolution des permissions héritées pour une arborescence de dossiers.
    
    Args:
        user_id: ID de l'utilisateur
        folder_id: ID du dossier racine
        max_depth: Profondeur maximale à traiter
    
    Returns:
        Dict[int, PermissionSet]: Permissions pour tous les dossiers de l'arborescence
    """
    return permission_optimizer.get_folder_tree_permissions(user_id, folder_id, max_depth)

class PermissionMiddlewareConfig:
    """Configuration pour le middleware de permissions."""
    
    def __init__(self):
        self.cache_enabled = True
        self.cache_expiration_hours = 1
        self.batch_size_limit = 100
        self.tree_depth_limit = 5
        self.performance_logging = True
    
    def update_optimizer_config(self):
        """Met à jour la configuration de l'optimiseur de permissions."""
        global permission_optimizer
        permission_optimizer = PermissionOptimizer(
            enable_cache=self.cache_enabled,
            cache_expiration_hours=self.cache_expiration_hours
        )

# Configuration globale par défaut
middleware_config = PermissionMiddlewareConfig()