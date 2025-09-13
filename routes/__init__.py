    # routes/__init__.py
from flask import Blueprint
from .auth_routes import auth_bp
from .user_routes import user_bp
from .file_routes import file_bp
from .admin_routes import admin_bp
from .folder_routes import folder_bp
from .permission_routes import permission_bp
from .metrics_routes import metrics_bp

def register_blueprints(app):
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(user_bp, url_prefix="/users")
    app.register_blueprint(file_bp, url_prefix="/files")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(folder_bp, url_prefix="/folders")
    app.register_blueprint(permission_bp, url_prefix="/permissions")
    app.register_blueprint(metrics_bp, url_prefix="/metrics")