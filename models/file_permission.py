from extensions import db

class FilePermission(db.Model):
    __tablename__ = "file_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable=True)
    file_id = db.Column(db.Integer, db.ForeignKey("files.id"), nullable=False)

    can_read = db.Column(db.Boolean, default=False)
    can_write = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_share = db.Column(db.Boolean, default=False)

    user = db.relationship("User", back_populates="file_permissions")
    group = db.relationship("Group", backref="file_permissions")
    file = db.relationship("File", back_populates="permissions")

    def __repr__(self):
        return f"<FilePermission File:{self.file_id} User:{self.user_id} Group:{self.group_id} R:{self.can_read} W:{self.can_write} D:{self.can_delete}>"
