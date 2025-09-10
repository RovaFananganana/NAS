from datetime import datetime
from extensions import db
from datetime import timezone
from .folder_permission import FolderPermission

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
    permissions = db.relationship("FolderPermission", back_populates="folder", cascade="all, delete-orphan")


    def __repr__(self):
        return f"<Folder {self.name}>"

    def get_effective_permissions(self, user):
        # 🔹 Vérifier permissions directes user
        perm = FolderPermission.query.filter_by(user_id=user.id, folder_id=self.id).first()
        if perm:
            return perm

        # 🔹 Vérifier permissions via groupes
        for group in user.groups:
            perm = FolderPermission.query.filter_by(group_id=group.id, folder_id=self.id).first()
            if perm:
                return perm

        # 🔹 Hériter du dossier parent récursivement
        if self.parent:
            return self.parent.get_effective_permissions(user)

        return None
