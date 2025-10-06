from datetime import datetime, timezone
from extensions import db

class AccessLog(db.Model):
    __tablename__ = "access_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # CREATE, READ, UPDATE, DELETE, SHARE, ADD_FAVORITE, REMOVE_FAVORITE, DOWNLOAD_FILE, CREATE_FILE, CREATE_FOLDER, DELETE_FILE, DELETE_FOLDER, RENAME_FILE, RENAME_FOLDER, MOVE_FILE, MOVE_FOLDER
    target = db.Column(db.String(255), nullable=False) # file/folder name or path
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Action types constants
    ACTION_TYPES = [
        'LOGIN', 'LOGOUT', 'ACCESS_FOLDER', 'ACCESS_FILE',
        'DOWNLOAD_FILE', 'ADD_FAVORITE', 'REMOVE_FAVORITE',
        'CREATE_FILE', 'CREATE_FOLDER', 'DELETE_FILE', 'DELETE_FOLDER',
        'RENAME_FILE', 'RENAME_FOLDER', 'MOVE_FILE', 'MOVE_FOLDER',
        'CREATE', 'READ', 'UPDATE', 'DELETE', 'SHARE'  # Legacy actions
    ]

    def __repr__(self):
        return f"<AccessLog user={self.user_id} action={self.action} target={self.target}>"
