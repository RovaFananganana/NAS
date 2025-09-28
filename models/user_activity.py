from datetime import datetime, timezone
from extensions import db
from enum import Enum
import json

class ActivityType(Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    FILE_DOWNLOAD = "file_download"
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    FILE_MOVE = "file_move"
    FILE_COPY = "file_copy"
    FOLDER_CREATE = "folder_create"
    FOLDER_DELETE = "folder_delete"
    NAVIGATION = "navigation"
    FAVORITE_ADD = "favorite_add"
    FAVORITE_REMOVE = "favorite_remove"
    ERROR = "error"
    USER_INTERACTION = "user_interaction"
    PERFORMANCE_METRIC = "performance_metric"
    SEARCH = "search"
    DEMO_ACTION = "demo_action"

class UserActivity(db.Model):
    __tablename__ = "user_activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    resource = db.Column(db.String(500), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    success = db.Column(db.Boolean, default=True, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 compatible
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Indexes for performance
    __table_args__ = (
        db.Index('idx_user_activities_user_id', 'user_id'),
        db.Index('idx_user_activities_created_at', 'created_at'),
        db.Index('idx_user_activities_action', 'action'),
        db.Index('idx_user_activities_user_period', 'user_id', 'created_at'),
    )

    # Relationship
    user = db.relationship("User", backref="activities", lazy=True)

    def __repr__(self):
        return f"<UserActivity {self.id}: {self.action} by user {self.user_id}>"

    def to_dict(self):
        """Convert activity to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource': self.resource,
            'details': self.details,
            'success': self.success,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user': {
                'username': self.user.username if self.user else None
            }
        }

    @classmethod
    def get_activity_type_display(cls, action):
        """Get human-readable display name for activity type"""
        display_names = {
            ActivityType.LOGIN.value: "Connexion",
            ActivityType.LOGOUT.value: "Déconnexion",
            ActivityType.FILE_DOWNLOAD.value: "Téléchargement de fichier",
            ActivityType.FILE_UPLOAD.value: "Upload de fichier",
            ActivityType.FILE_DELETE.value: "Suppression de fichier",
            ActivityType.FILE_RENAME.value: "Renommage de fichier",
            ActivityType.FILE_MOVE.value: "Déplacement de fichier",
            ActivityType.FILE_COPY.value: "Copie de fichier",
            ActivityType.FOLDER_CREATE.value: "Création de dossier",
            ActivityType.FOLDER_DELETE.value: "Suppression de dossier",
            ActivityType.NAVIGATION.value: "Navigation",
            ActivityType.FAVORITE_ADD.value: "Ajout aux favoris",
            ActivityType.FAVORITE_REMOVE.value: "Suppression des favoris",
            ActivityType.ERROR.value: "Erreur",
            ActivityType.USER_INTERACTION.value: "Interaction utilisateur",
            ActivityType.PERFORMANCE_METRIC.value: "Métrique de performance",
            ActivityType.SEARCH.value: "Recherche",
            ActivityType.DEMO_ACTION.value: "Action de démonstration",
        }
        return display_names.get(action, action)