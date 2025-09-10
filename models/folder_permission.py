from extensions import db

class FolderPermission(db.Model):
    __tablename__ = "folder_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=False)

    can_read = db.Column(db.Boolean, default=False)
    can_write = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_share = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="folder_permissions")
    group = db.relationship("Group", backref="folder_permissions")
    folder = db.relationship("Folder", back_populates="permissions")

    def __repr__(self):
        return f"<FolderPermission Folder:{self.folder_id} User:{self.user_id} Group:{self.group_id} R:{self.can_read} W:{self.can_write} D:{self.can_delete}>"
