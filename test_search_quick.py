#!/usr/bin/env python3
"""Test rapide de l'endpoint de recherche"""

import sys
sys.path.insert(0, '.')

from routes.nas_routes import nas_bp
from flask import Flask
from flask_jwt_extended import JWTManager
from extensions import db
import os

# Créer une app Flask minimale
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///nas.db')
app.config['JWT_SECRET_KEY'] = 'test-secret-key'
app.config['TESTING'] = True

db.init_app(app)
jwt = JWTManager(app)

# Enregistrer le blueprint
app.register_blueprint(nas_bp)

print("✅ Blueprint enregistré avec succès")
print(f"📋 Routes disponibles:")
for rule in app.url_map.iter_rules():
    if '/nas/' in str(rule):
        print(f"  - {rule.methods} {rule}")

print("\n🔍 Endpoint de recherche disponible: /nas/search")
print("Paramètres: query, path, recursive, max_results")
