#!/usr/bin/env python3
"""
Script pour initialiser la base de données
Crée toutes les tables définies dans les modèles SQLAlchemy
"""

from app import create_app
from extensions import db
from models import *  # Import tous les modèles

def init_database():
    """Initialise la base de données en créant toutes les tables"""
    app = create_app()
    
    with app.app_context():
        print("Création de toutes les tables...")
        
        # Créer toutes les tables
        db.create_all()
        
        print("✅ Toutes les tables ont été créées avec succès!")
        
        # Afficher les tables créées
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        print(f"\n📋 Tables créées ({len(tables)}):")
        for table in sorted(tables):
            print(f"  - {table}")

if __name__ == "__main__":
    init_database()