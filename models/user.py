from datetime import datetime, timezone
from extensions import db
from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)
    quota_mb = db.Column(db.Integer, default=2054)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relations
    files = db.relationship("File", backref="owner", lazy=True)
    folders = db.relationship("Folder", backref="owner", lazy=True)
    access_logs = db.relationship("AccessLog", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        return self.password_hash

    def check_password(self, password: str) -> bool:
        print(password, self.password_hash)
        return check_password_hash(self.password_hash, password)
    
 