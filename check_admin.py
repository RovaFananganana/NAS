#!/usr/bin/env python3
"""
Script pour vérifier l'utilisateur admin
"""

from app import create_app
from extensions import db
from models.user import User
from werkzeug.security import check_password_hash

def check_admin():
    """Vérifie l'utilisateur administrateur"""
    app = create_app()
    
    with app.app_context():
        # Vérifier si un admin existe
        admin = User.query.filter_by(username='admin').first()
        
        if not admin:
            print("❌ Admin user NOT found in database")
            return
        
        print(f"✅ Admin user found:")
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   Role: {admin.role}")
        print(f"   Password hash: {admin.password_hash}")
        print()
        
        # Test password
        test_password = 'admin123'
        is_valid = admin.check_password(test_password)
        print(f"Testing password '{test_password}': {is_valid}")
        
        if not is_valid:
            print("❌ Password check failed! Resetting password...")
            admin.set_password('admin123')
            db.session.commit()
            print("✅ Password reset to 'admin123'")

if __name__ == "__main__":
    check_admin()
