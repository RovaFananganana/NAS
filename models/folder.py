from datetime import datetime
from extensions import db
from datetime import timezone

class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relations
    children = db.relationship("Folder", backref=db.backref("parent", remote_side=[id]), lazy=True)
    files = db.relationship("File", backref="folder", lazy=True)

    def __repr__(self):
        return f"<Folder {self.name}>"
