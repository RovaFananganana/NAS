from datetime import datetime, timezone
from extensions import db

class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_path = db.Column(db.String(500), nullable=False)
    item_type = db.Column(db.String(10), nullable=False)  # 'file' ou 'folder'
    item_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    
    # Relation avec User
    user = db.relationship('User', backref='favorites')
    
    # Index pour optimiser les requêtes
    __table_args__ = (
        db.Index('idx_user_path', 'user_id', 'item_path'),
        db.UniqueConstraint('user_id', 'item_path', name='unique_user_favorite'),
    )

    def __repr__(self):
        return f"<Favorite user={self.user_id} path={self.item_path} type={self.item_type}>"

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'item_path': self.item_path,
            'item_type': self.item_type,
            'item_name': self.item_name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }