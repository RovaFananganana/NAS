from extensions import db

class Quota(db.Model):
    __tablename__ = "quotas"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    used_mb = db.Column(db.Integer, default=0)
    limit_mb = db.Column(db.Integer, default=100)

    def __repr__(self):
        return f"<Quota user={self.user_id} used={self.used_mb}/{self.limit_mb} MB>"
