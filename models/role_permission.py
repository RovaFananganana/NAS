from extensions import db

class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # ADMIN, MANAGER, SIMPLE_USER
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id"), nullable=False)

    # Relation avec Permission
    permission = db.relationship("Permission", back_populates="roles")

    def __repr__(self):
        return f"<RolePermission {self.role} -> {self.permission.resource}:{self.permission.action}>"
