# scripts/seed_permissions.py
import os
import sys

# Ensure the backend package root is on sys.path so top-level imports resolve
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from extensions import db
from models.permission import Permission
from models.role_permission import RolePermission
from app import create_app


def seed_permissions():
    app = create_app()
    with app.app_context():
        # Définition des ressources et actions
        resources = ["file", "folder", "user"]
        actions = ["CREATE", "READ", "UPDATE", "DELETE", "MANAGE", "SHARE"]

        # Ensure Permission entries exist (one per resource/action)
        created = 0
        for resource in resources:
            for action in actions:
                perm = Permission.query.filter_by(resource=resource, action=action).first()
                if not perm:
                    perm = Permission(resource=resource, action=action)
                    db.session.add(perm)
                    created += 1

        db.session.commit()
        print(f"✅ Ensured permission table entries exist (created: {created})")

        # Roles we want to wire permissions for
        # ADMIN should get all permissions
        roles_to_grant = {
            "ADMIN": "all",
            "SIMPLE_USER": [
                ("file", "READ"),
                ("folder", "READ"),
                ("file", "CREATE"),
                ("folder", "CREATE")
            ]
        }

        # Create RolePermission mappings
        rp_created = 0
        for role_name, perms in roles_to_grant.items():
            if perms == "all":
                all_perms = Permission.query.all()
                for p in all_perms:
                    exists = RolePermission.query.filter_by(role=role_name, permission_id=p.id).first()
                    if not exists:
                        rp = RolePermission(role=role_name, permission_id=p.id)
                        db.session.add(rp)
                        rp_created += 1
            else:
                for resource, action in perms:
                    p = Permission.query.filter_by(resource=resource, action=action).first()
                    if p:
                        exists = RolePermission.query.filter_by(role=role_name, permission_id=p.id).first()
                        if not exists:
                            rp = RolePermission(role=role_name, permission_id=p.id)
                            db.session.add(rp)
                            rp_created += 1

        db.session.commit()
        print(f"✅ RolePermission mappings created/ensured: {rp_created}")


if __name__ == "__main__":
    seed_permissions()
