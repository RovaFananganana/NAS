# scripts/seed_permissions.py
from extensions import db
from models.permission import Permission
from app import create_app

def seed_permissions():
    app = create_app()
    with app.app_context():
        permissions = []

        # Définition des ressources et actions
        resources = ["file", "folder", "user"]
        actions = ["CREATE", "READ", "UPDATE", "DELETE", "MANAGE", "SHARE"]

        # Rôles
        roles = ["ADMIN", "SIMPLE_USER"]

        for role in roles:
            for resource in resources:
                for action in actions:
                    # Pour SIMPLE_USER, limiter certaines actions sur "user"
                    if role == "user" and resource == "user" and action != "READ":
                        continue
                    perm = Permission(role=role, resource=resource, action=action)
                    permissions.append(perm)

        # Ajouter en DB
        db.session.bulk_save_objects(permissions)
        db.session.commit()
        print(f"{len(permissions)} permissions créées pour les rôles {roles}")

if __name__ == "__main__":
    seed_permissions()
