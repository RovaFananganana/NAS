from datetime import datetime, timezone
from extensions import db
from .file_permission import FilePermission

class File(db.Model):
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    size_kb = db.Column(db.Integer, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

# liens pour les permissions des utilisateurs
    permissions = db.relationship("FilePermission", back_populates="file", cascade="all, delete-orphan")    

    def __repr__(self):
        return f"<File {self.name}>"


    def get_effective_permissions(self, user):
        # 🔹 Vérifier permissions directes user
        perm = FilePermission.query.filter_by(user_id=user.id, file_id=self.id).first()
        if perm:
            return perm

        # 🔹 Vérifier permissions via groupes
        for group in user.groups:
            perm = FilePermission.query.filter_by(group_id=group.id, file_id=self.id).first()
            if perm:
                return perm

        # 🔹 Hériter du dossier parent
        if self.folder:
            return self.folder.get_effective_permissions(user)

        return None
