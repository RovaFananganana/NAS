#!/usr/bin/env python3
"""
Script pour créer un utilisateur administrateur
"""

from app import create_app
from extensions import db
from models.user import User

def create_admin_user():
    """Crée un utilisateur administrateur par défaut"""
    app = create_app()
    
    with app.app_context():
        # Vérifier si un admin existe déjà
        existing_admin = User.query.filter_by(role='ADMIN').first()
        if existing_admin:
            print(f"✅ Un administrateur existe déjà: {existing_admin.username}")
            return existing_admin
        
        # Créer l'utilisateur admin
        admin_user = User(
            username='admin',
            email='admin@nas.local',
            role='ADMIN',
            quota_mb=10240  # 10GB pour l'admin
        )
        admin_user.set_password('admin123')  # Mot de passe par défaut
        
        db.session.add(admin_user)
        db.session.commit()
        
        print(f"✅ Utilisateur administrateur créé:")
        print(f"   Username: {admin_user.username}")
        print(f"   Email: {admin_user.email}")
        print(f"   Password: admin123")
        print(f"   Role: {admin_user.role}")
        print(f"   ID: {admin_user.id}")
        
        return admin_user

if __name__ == "__main__":
    create_admin_user()