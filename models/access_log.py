from datetime import datetime, timezone
from extensions import db

class AccessLog(db.Model):
    __tablename__ = "access_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # CREATE, READ, UPDATE, DELETE, SHARE
    target = db.Column(db.String(255), nullable=False) # file/folder name or path
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<AccessLog user={self.user_id} action={self.action} target={self.target}>"
