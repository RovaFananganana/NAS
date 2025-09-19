from datetime import datetime
from extensions import db
from datetime import timezone
from .folder_permission import FolderPermission
from utils.performance_logger import performance_monitor, PerformanceTracker, log_permission_query_stats

class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    path = db.Column(db.String(500), nullable=True, unique=True)  # Full path for Windows-like navigation
    parent_path = db.Column(db.String(500), nullable=True)  # Parent folder path
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Relations
    children = db.relationship("Folder", backref=db.backref("parent", remote_side=[id]), lazy=True)
    files = db.relationship("File", backref="folder", lazy=True)
    permissions = db.relationship("FolderPermission", back_populates="folder", cascade="all, delete-orphan")


    def __repr__(self):
        return f"<Folder {self.name}>"

    @performance_monitor("Folder.get_effective_permissions", log_threshold_ms=50.0)
    def get_effective_permissions(self, user):
        """
        Get effective permissions for a user on this folder.
        Uses optimized PermissionOptimizer for better performance.
        Falls back to legacy method if optimizer is not available.
        """
        try:
            # Import here to avoid circular imports
            from services.permission_optimizer import PermissionOptimizer
            
            with PerformanceTracker("Folder.get_effective_permissions_optimized") as tracker:
                optimizer = PermissionOptimizer()
                permissions = optimizer.get_bulk_folder_permissions(user.id, [self.id])
                
                if self.id in permissions:
                    perm_set = permissions[self.id]
                    
                    # Log performance stats
                    log_permission_query_stats(
                        user_id=user.id,
                        resource_type="folder",
                        resource_count=1,
                        duration_ms=tracker.duration_ms,
                        method="optimized"
                    )
                    
                    # Convert PermissionSet back to FolderPermission-like object for backward compatibility
                    if perm_set.source != "none":
                        return self._create_permission_object(perm_set, user)
                    
                return None
                
        except ImportError:
            # Fallback to legacy method if PermissionOptimizer is not available
            return self._get_effective_permissions_legacy(user)
        except Exception as e:
            # Log error and fallback to legacy method
            from utils.performance_logger import performance_logger
            performance_logger.error(f"Error in optimized permission check for folder {self.id}: {str(e)}")
            return self._get_effective_permissions_legacy(user)
    
    def _get_effective_permissions_legacy(self, user):
        """
        Legacy implementation of get_effective_permissions for backward compatibility.
        """
        with PerformanceTracker("Folder.get_effective_permissions_legacy") as tracker:
            # 🔹 Vérifier permissions directes user
            perm = FolderPermission.query.filter_by(user_id=user.id, folder_id=self.id).first()
            if perm:
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="folder",
                    resource_count=1,
                    duration_ms=tracker.duration_ms,
                    method="legacy"
                )
                return perm

            # 🔹 Vérifier permissions via groupes
            for group in user.groups:
                perm = FolderPermission.query.filter_by(group_id=group.id, folder_id=self.id).first()
                if perm:
                    log_permission_query_stats(
                        user_id=user.id,
                        resource_type="folder",
                        resource_count=1,
                        duration_ms=tracker.duration_ms,
                        method="legacy"
                    )
                    return perm

            # 🔹 Hériter du dossier parent récursivement
            if self.parent:
                parent_perm = self.parent.get_effective_permissions(user)
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="folder",
                    resource_count=1,
                    duration_ms=tracker.duration_ms,
                    method="legacy"
                )
                return parent_perm

            log_permission_query_stats(
                user_id=user.id,
                resource_type="folder",
                resource_count=1,
                duration_ms=tracker.duration_ms,
                method="legacy"
            )
            return None
    
    def _create_permission_object(self, perm_set, user):
        """
        Create a FolderPermission-like object from PermissionSet for backward compatibility.
        """
        # Create a mock permission object that behaves like FolderPermission
        class PermissionProxy:
            def __init__(self, perm_set, folder_id, user_id):
                self.can_read = perm_set.can_read
                self.can_write = perm_set.can_write
                self.can_delete = perm_set.can_delete
                self.can_share = perm_set.can_share
                self.is_owner = perm_set.is_owner
                self.source = perm_set.source
                self.folder_id = folder_id
                self.user_id = user_id
                
            def __bool__(self):
                return any([self.can_read, self.can_write, self.can_delete, self.can_share, self.is_owner])
        
        return PermissionProxy(perm_set, self.id, user.id)
    
    @classmethod
    @performance_monitor("Folder.get_bulk_permissions", log_threshold_ms=100.0)
    def get_bulk_permissions(cls, user, folder_ids):
        """
        Get permissions for multiple folders efficiently.
        
        Args:
            user: User object
            folder_ids: List of folder IDs
            
        Returns:
            Dictionary mapping folder_id to permission object
        """
        try:
            from services.permission_optimizer import PermissionOptimizer
            
            with PerformanceTracker("Folder.get_bulk_permissions_optimized") as tracker:
                optimizer = PermissionOptimizer()
                permissions = optimizer.get_bulk_folder_permissions(user.id, folder_ids)
                
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="folder",
                    resource_count=len(folder_ids),
                    duration_ms=tracker.duration_ms,
                    method="optimized_bulk"
                )
                
                # Convert to permission objects for backward compatibility
                result = {}
                for folder_id, perm_set in permissions.items():
                    if perm_set.source != "none":
                        result[folder_id] = cls._create_permission_object_static(perm_set, folder_id, user.id)
                    else:
                        result[folder_id] = None
                
                return result
                
        except Exception as e:
            from utils.performance_logger import performance_logger
            performance_logger.error(f"Error in bulk permission check for folders: {str(e)}")
            
            # Fallback to individual checks
            result = {}
            for folder_id in folder_ids:
                folder_obj = cls.query.get(folder_id)
                if folder_obj:
                    result[folder_id] = folder_obj.get_effective_permissions(user)
                else:
                    result[folder_id] = None
            
            return result
    
    @classmethod
    @performance_monitor("Folder.get_tree_permissions", log_threshold_ms=200.0)
    def get_tree_permissions(cls, user, root_folder_id, depth=3):
        """
        Get permissions for an entire folder tree efficiently.
        
        Args:
            user: User object
            root_folder_id: Root folder ID to start traversal
            depth: Maximum depth to traverse
            
        Returns:
            Dictionary mapping folder_id to permission object
        """
        try:
            from services.permission_optimizer import PermissionOptimizer
            
            with PerformanceTracker("Folder.get_tree_permissions_optimized") as tracker:
                optimizer = PermissionOptimizer()
                permissions = optimizer.get_folder_tree_permissions(user.id, root_folder_id, depth)
                
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="folder_tree",
                    resource_count=len(permissions),
                    duration_ms=tracker.duration_ms,
                    method="optimized_tree"
                )
                
                # Convert to permission objects for backward compatibility
                result = {}
                for folder_id, perm_set in permissions.items():
                    if perm_set.source != "none":
                        result[folder_id] = cls._create_permission_object_static(perm_set, folder_id, user.id)
                    else:
                        result[folder_id] = None
                
                return result
                
        except Exception as e:
            from utils.performance_logger import performance_logger
            performance_logger.error(f"Error in tree permission check: {str(e)}")
            return {}
    
    @staticmethod
    def _create_permission_object_static(perm_set, folder_id, user_id):
        """Static version of _create_permission_object for bulk operations."""
        class PermissionProxy:
            def __init__(self, perm_set, folder_id, user_id):
                self.can_read = perm_set.can_read
                self.can_write = perm_set.can_write
                self.can_delete = perm_set.can_delete
                self.can_share = perm_set.can_share
                self.is_owner = perm_set.is_owner
                self.source = perm_set.source
                self.folder_id = folder_id
                self.user_id = user_id
                
            def __bool__(self):
                return any([self.can_read, self.can_write, self.can_delete, self.can_share, self.is_owner])
        
        return PermissionProxy(perm_set, folder_id, user_id)
