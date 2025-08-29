from models.role_permission import RolePermission
from models.permission import Permission
from extensions import db

def has_permission(user, resource, action):
    """
    Vérifie si un utilisateur a la permission d'exécuter une action sur une ressource
    """
    q = (
        db.session.query(RolePermission)
        .join(Permission)
        .filter(
            RolePermission.role == user.role,
            Permission.resource == resource,
            Permission.action == action
        )
        .first()
    )
    return q is not None
