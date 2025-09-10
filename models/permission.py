from extensions import db

class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(50), nullable=False)  # ex: "file", "folder", "user"
    action = db.Column(db.String(20), nullable=False)    # ex: "CREATE", "READ", "UPDATE", "DELETE", "SHARE"

    # Relation pivot
    roles = db.relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Permission {self.action} on {self.resource}>"

