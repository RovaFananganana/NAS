from datetime import datetime, timedelta
from extensions import db


class PermissionCache(db.Model):
    __tablename__ = "permission_cache"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    resource_type = db.Column(db.String(10), nullable=False)  # 'file' or 'folder'
    resource_id = db.Column(db.Integer, nullable=False)

    can_read = db.Column(db.Boolean, default=False)
    can_write = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_share = db.Column(db.Boolean, default=False)
    is_owner = db.Column(db.Boolean, default=False)

    permission_source = db.Column(db.String(20))  # 'direct', 'group', 'inherited', 'owner'
    cached_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship("User", backref="permission_cache")

    # Indexes for efficient cache lookups
    __table_args__ = (
        db.Index('idx_perm_cache_user_resource', 'user_id', 'resource_type', 'resource_id'),
        db.Index('idx_perm_cache_expires', 'expires_at'),
        db.Index('idx_perm_cache_user_type', 'user_id', 'resource_type'),
        db.UniqueConstraint('user_id', 'resource_type', 'resource_id', name='uq_user_resource_perm')
    )

    def __init__(self, user_id, resource_type, resource_id, **kwargs):
        super().__init__(**kwargs)
        self.user_id = user_id
        self.resource_type = resource_type
        self.resource_id = resource_id
        
        # Set default expiration to 1 hour from now
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(hours=1)

    @classmethod
    def get_cached_permission(cls, user_id, resource_type, resource_id):
        """
        Retrieve cached permission if it exists and hasn't expired.
        Returns None if cache miss or expired.
        """
        cache_entry = cls.query.filter_by(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id
        ).filter(
            cls.expires_at > datetime.utcnow()
        ).first()
        
        return cache_entry

    @classmethod
    def set_cached_permission(cls, user_id, resource_type, resource_id, permissions_dict, 
                            permission_source='direct', expiration_hours=1):
        """
        Cache permission data for a user-resource combination.
        Updates existing cache entry or creates new one.
        """
        # Try to find existing cache entry
        cache_entry = cls.query.filter_by(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id
        ).first()

        if cache_entry:
            # Update existing entry
            cache_entry.can_read = permissions_dict.get('can_read', False)
            cache_entry.can_write = permissions_dict.get('can_write', False)
            cache_entry.can_delete = permissions_dict.get('can_delete', False)
            cache_entry.can_share = permissions_dict.get('can_share', False)
            cache_entry.is_owner = permissions_dict.get('is_owner', False)
            cache_entry.permission_source = permission_source
            cache_entry.cached_at = datetime.utcnow()
            cache_entry.expires_at = datetime.utcnow() + timedelta(hours=expiration_hours)
        else:
            # Create new cache entry
            cache_entry = cls(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                can_read=permissions_dict.get('can_read', False),
                can_write=permissions_dict.get('can_write', False),
                can_delete=permissions_dict.get('can_delete', False),
                can_share=permissions_dict.get('can_share', False),
                is_owner=permissions_dict.get('is_owner', False),
                permission_source=permission_source,
                expires_at=datetime.utcnow() + timedelta(hours=expiration_hours)
            )
            db.session.add(cache_entry)

        return cache_entry

    @classmethod
    def invalidate_user_cache(cls, user_id):
        """
        Invalidate all cache entries for a specific user.
        """
        cls.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    @classmethod
    def invalidate_resource_cache(cls, resource_type, resource_id):
        """
        Invalidate all cache entries for a specific resource.
        """
        cls.query.filter_by(
            resource_type=resource_type,
            resource_id=resource_id
        ).delete()
        db.session.commit()

    @classmethod
    def cleanup_expired_cache(cls):
        """
        Remove all expired cache entries.
        Should be called periodically by a cleanup job.
        """
        expired_count = cls.query.filter(
            cls.expires_at <= datetime.utcnow()
        ).delete()
        db.session.commit()
        return expired_count

    @classmethod
    def get_cache_stats(cls):
        """
        Get cache statistics for monitoring.
        """
        total_entries = cls.query.count()
        expired_entries = cls.query.filter(
            cls.expires_at <= datetime.utcnow()
        ).count()
        active_entries = total_entries - expired_entries
        
        return {
            'total_entries': total_entries,
            'active_entries': active_entries,
            'expired_entries': expired_entries
        }

    def to_dict(self):
        """
        Convert cache entry to dictionary format.
        """
        return {
            'user_id': self.user_id,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'can_read': self.can_read,
            'can_write': self.can_write,
            'can_delete': self.can_delete,
            'can_share': self.can_share,
            'is_owner': self.is_owner,
            'permission_source': self.permission_source,
            'cached_at': self.cached_at.isoformat() if self.cached_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }

    def is_expired(self):
        """
        Check if this cache entry has expired.
        """
        return self.expires_at <= datetime.utcnow()

    def __repr__(self):
        return (f"<PermissionCache User:{self.user_id} {self.resource_type}:{self.resource_id} "
                f"R:{self.can_read} W:{self.can_write} D:{self.can_delete} S:{self.can_share} "
                f"Owner:{self.is_owner} Source:{self.permission_source}>")