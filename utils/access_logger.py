# utils/access_logger.py

from models.access_log import AccessLog
from extensions import db
from datetime import datetime, timezone

def log_permission_action(user_id, action, target, details=None):
    """
    Enregistre une action de permission dans les logs d'accès
    
    Args:
        user_id (int): ID de l'utilisateur qui effectue l'action
        action (str): Type d'action (CREATE_PERMISSION, UPDATE_PERMISSION, DELETE_PERMISSION, etc.)
        target (str): Cible de l'action (nom du dossier/fichier + utilisateur/groupe)
        details (str, optional): Détails supplémentaires sur l'action
    """
    try:
        # Construire le message de log avec les détails si fournis
        log_target = target
        if details:
            log_target = f"{target} - {details}"
        
        # Créer l'entrée de log
        log_entry = AccessLog(
            user_id=user_id,
            action=action,
            target=log_target,
            timestamp=datetime.now(timezone.utc)
        )
        
        db.session.add(log_entry)
        # Note: Le commit sera fait par la fonction appelante
        
        print(f"📝 Log enregistré: User {user_id} - {action} - {log_target}")
        
    except Exception as e:
        print(f"❌ Erreur lors de l'enregistrement du log: {str(e)}")
        # Ne pas faire échouer l'opération principale si le log échoue

def log_folder_permission_action(user_id, action, folder_name, target_type, target_name, permissions=None):
    """
    Enregistre spécifiquement les actions sur les permissions de dossiers
    
    Args:
        user_id (int): ID de l'utilisateur admin qui effectue l'action
        action (str): CREATE_PERMISSION, UPDATE_PERMISSION, DELETE_PERMISSION
        folder_name (str): Nom du dossier
        target_type (str): 'user' ou 'group'
        target_name (str): Nom de l'utilisateur ou du groupe
        permissions (dict, optional): Détails des permissions accordées
    """
    target = f"Dossier '{folder_name}' pour {target_type} '{target_name}'"
    
    details = None
    if permissions and action in ['CREATE_PERMISSION', 'UPDATE_PERMISSION']:
        perms_list = []
        if permissions.get('can_read'): perms_list.append('lecture')
        if permissions.get('can_write'): perms_list.append('écriture')
        if permissions.get('can_delete'): perms_list.append('suppression')
        if permissions.get('can_share'): perms_list.append('partage')
        
        if perms_list:
            details = f"Permissions: {', '.join(perms_list)}"
        else:
            details = "Toutes permissions révoquées"
    
    log_permission_action(user_id, action, target, details)

def log_file_permission_action(user_id, action, file_name, target_type, target_name, permissions=None):
    """
    Enregistre spécifiquement les actions sur les permissions de fichiers
    
    Args:
        user_id (int): ID de l'utilisateur admin qui effectue l'action
        action (str): CREATE_PERMISSION, UPDATE_PERMISSION, DELETE_PERMISSION
        file_name (str): Nom du fichier
        target_type (str): 'user' ou 'group'
        target_name (str): Nom de l'utilisateur ou du groupe
        permissions (dict, optional): Détails des permissions accordées
    """
    target = f"Fichier '{file_name}' pour {target_type} '{target_name}'"
    
    details = None
    if permissions and action in ['CREATE_PERMISSION', 'UPDATE_PERMISSION']:
        perms_list = []
        if permissions.get('can_read'): perms_list.append('lecture')
        if permissions.get('can_write'): perms_list.append('écriture')
        if permissions.get('can_delete'): perms_list.append('suppression')
        if permissions.get('can_share'): perms_list.append('partage')
        
        if perms_list:
            details = f"Permissions: {', '.join(perms_list)}"
        else:
            details = "Toutes permissions révoquées"
    
    log_permission_action(user_id, action, target, details)

def log_batch_permission_action(user_id, entity_type, count, target_type, target_name, permissions=None):
    """
    Enregistre les actions de permissions en lot
    
    Args:
        user_id (int): ID de l'utilisateur admin
        entity_type (str): 'folders' ou 'files'
        count (int): Nombre d'éléments modifiés
        target_type (str): 'user' ou 'group'
        target_name (str): Nom de l'utilisateur ou du groupe
        permissions (dict, optional): Détails des permissions
    """
    entity_label = "dossiers" if entity_type == "folders" else "fichiers"
    target = f"{count} {entity_label} pour {target_type} '{target_name}'"
    
    details = None
    if permissions:
        perms_list = []
        if permissions.get('can_read'): perms_list.append('lecture')
        if permissions.get('can_write'): perms_list.append('écriture')
        if permissions.get('can_delete'): perms_list.append('suppression')
        if permissions.get('can_share'): perms_list.append('partage')
        
        if perms_list:
            details = f"Permissions: {', '.join(perms_list)}"
    
    log_permission_action(user_id, 'BATCH_PERMISSION_UPDATE', target, details)

def log_file_operation(user_id, action, target, details=None):
    """
    Enregistre les opérations sur les fichiers et dossiers
    
    Args:
        user_id (int): ID de l'utilisateur qui effectue l'action
        action (str): CREATE, READ, UPDATE, DELETE, UPLOAD, DOWNLOAD, MOVE, COPY, RENAME
        target (str): Nom/chemin du fichier ou dossier
        details (str, optional): Détails supplémentaires
    """
    log_permission_action(user_id, action, target, details)