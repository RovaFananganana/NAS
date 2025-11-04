from datetime import datetime, timezone, timedelta
from extensions import db
from sqlalchemy import Index

class FileLock(db.Model):
    """Model for tracking file locks to prevent concurrent editing"""
    __tablename__ = "file_locks"

    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String(1024), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.String(64), nullable=False, unique=True)
    locked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_activity_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user = db.relationship("User", backref="file_locks")

    # Indexes for performance
    __table_args__ = (
        Index('idx_file_path_active', 'file_path', 'is_active'),
        Index('idx_session_id', 'session_id'),
        Index('idx_expires_at', 'expires_at'),
    )

    def __repr__(self):
        return f"<FileLock {self.file_path} by user {self.user_id}>"

    @classmethod
    def acquire_lock(cls, user_id: int, file_path: str, session_id: str, 
                     lock_duration_minutes: int = 30) -> tuple[bool, str, 'FileLock']:
        """
        Attempt to acquire a lock on a file
        
        Args:
            user_id: ID of the user requesting the lock
            file_path: Path to the file to lock
            session_id: Unique session identifier
            lock_duration_minutes: Duration of the lock in minutes
            
        Returns:
            Tuple of (success, message, lock_object)
        """
        # First, release any expired locks
        cls.release_expired_locks()
        
        # Check if file is already locked by another user
        existing_lock = cls.query.filter_by(
            file_path=file_path,
            is_active=True
        ).first()
        
        if existing_lock:
            # Check if it's the same user
            if existing_lock.user_id == user_id:
                # Update the existing lock
                existing_lock.session_id = session_id
                existing_lock.expires_at = datetime.now(timezone.utc) + timedelta(minutes=lock_duration_minutes)
                existing_lock.last_activity_at = datetime.now(timezone.utc)
                db.session.commit()
                return True, "Lock renewed", existing_lock
            else:
                # File is locked by another user
                from models import User
                locking_user = User.query.get(existing_lock.user_id)
                username = locking_user.username if locking_user else "Unknown"
                return False, f"File is locked by {username}", existing_lock
        
        # Create new lock
        new_lock = cls(
            file_path=file_path,
            user_id=user_id,
            session_id=session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=lock_duration_minutes),
            is_active=True
        )
        
        db.session.add(new_lock)
        db.session.commit()
        
        return True, "Lock acquired", new_lock

    @classmethod
    def release_lock(cls, session_id: str = None, file_path: str = None, user_id: int = None) -> bool:
        """
        Release a lock on a file
        
        Args:
            session_id: Session ID to release
            file_path: File path to release (with user_id)
            user_id: User ID (used with file_path)
            
        Returns:
            True if lock was released, False otherwise
        """
        query = cls.query.filter_by(is_active=True)
        
        if session_id:
            query = query.filter_by(session_id=session_id)
        elif file_path and user_id:
            query = query.filter_by(file_path=file_path, user_id=user_id)
        else:
            return False
        
        lock = query.first()
        
        if lock:
            lock.is_active = False
            db.session.commit()
            return True
        
        return False

    @classmethod
    def release_expired_locks(cls) -> int:
        """
        Release all expired locks
        
        Returns:
            Number of locks released
        """
        now = datetime.now(timezone.utc)
        expired_locks = cls.query.filter(
            cls.is_active == True,
            cls.expires_at < now
        ).all()
        
        count = 0
        for lock in expired_locks:
            lock.is_active = False
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count

    @classmethod
    def release_inactive_locks(cls, inactivity_minutes: int = 15) -> int:
        """
        Release locks that have been inactive for too long
        
        Args:
            inactivity_minutes: Minutes of inactivity before releasing lock
            
        Returns:
            Number of locks released
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=inactivity_minutes)
        inactive_locks = cls.query.filter(
            cls.is_active == True,
            cls.last_activity_at < threshold
        ).all()
        
        count = 0
        for lock in inactive_locks:
            lock.is_active = False
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count

    @classmethod
    def check_lock_status(cls, file_path: str) -> dict:
        """
        Check if a file is locked and get lock information
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary with lock status information
        """
        # Release expired locks first
        cls.release_expired_locks()
        
        lock = cls.query.filter_by(
            file_path=file_path,
            is_active=True
        ).first()
        
        if lock:
            from models import User
            user = User.query.get(lock.user_id)
            return {
                'is_locked': True,
                'locked_by_user_id': lock.user_id,
                'locked_by_username': user.username if user else 'Unknown',
                'locked_at': lock.locked_at.isoformat(),
                'expires_at': lock.expires_at.isoformat(),
                'session_id': lock.session_id
            }
        
        return {
            'is_locked': False,
            'locked_by_user_id': None,
            'locked_by_username': None,
            'locked_at': None,
            'expires_at': None,
            'session_id': None
        }

    @classmethod
    def update_activity(cls, session_id: str) -> bool:
        """
        Update the last activity timestamp for a lock
        
        Args:
            session_id: Session ID of the lock
            
        Returns:
            True if updated, False otherwise
        """
        lock = cls.query.filter_by(
            session_id=session_id,
            is_active=True
        ).first()
        
        if lock:
            lock.last_activity_at = datetime.now(timezone.utc)
            db.session.commit()
            return True
        
        return False

    @classmethod
    def get_user_locks(cls, user_id: int, active_only: bool = True) -> list:
        """
        Get all locks for a specific user
        
        Args:
            user_id: User ID
            active_only: Only return active locks
            
        Returns:
            List of FileLock objects
        """
        query = cls.query.filter_by(user_id=user_id)
        
        if active_only:
            query = query.filter_by(is_active=True)
        
        return query.all()

    @classmethod
    def release_all_user_locks(cls, user_id: int) -> int:
        """
        Release all locks for a specific user (e.g., on logout)
        
        Args:
            user_id: User ID
            
        Returns:
            Number of locks released
        """
        locks = cls.query.filter_by(
            user_id=user_id,
            is_active=True
        ).all()
        
        count = 0
        for lock in locks:
            lock.is_active = False
            count += 1
        
        if count > 0:
            db.session.commit()
        
        return count
