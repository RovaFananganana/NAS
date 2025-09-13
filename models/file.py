from datetime import datetime, timezone
from extensions import db
from .file_permission import FilePermission
from utils.performance_logger import performance_monitor, PerformanceTracker, log_permission_query_stats

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


    @performance_monitor("File.get_effective_permissions", log_threshold_ms=50.0)
    def get_effective_permissions(self, user):
        """
        Get effective permissions for a user on this file.
        Uses optimized PermissionOptimizer for better performance.
        Falls back to legacy method if optimizer is not available.
        """
        try:
            # Import here to avoid circular imports
            from services.permission_optimizer import PermissionOptimizer
            
            with PerformanceTracker("File.get_effective_permissions_optimized") as tracker:
                optimizer = PermissionOptimizer()
                permissions = optimizer.get_bulk_file_permissions(user.id, [self.id])
                
                if self.id in permissions:
                    perm_set = permissions[self.id]
                    
                    # Log performance stats
                    log_permission_query_stats(
                        user_id=user.id,
                        resource_type="file",
                        resource_count=1,
                        duration_ms=tracker.duration_ms,
                        method="optimized"
                    )
                    
                    # Convert PermissionSet back to FilePermission-like object for backward compatibility
                    if perm_set.source != "none":
                        return self._create_permission_object(perm_set, user)
                    
                return None
                
        except ImportError:
            # Fallback to legacy method if PermissionOptimizer is not available
            return self._get_effective_permissions_legacy(user)
        except Exception as e:
            # Log error and fallback to legacy method
            from utils.performance_logger import performance_logger
            performance_logger.error(f"Error in optimized permission check for file {self.id}: {str(e)}")
            return self._get_effective_permissions_legacy(user)
    
    def _get_effective_permissions_legacy(self, user):
        """
        Legacy implementation of get_effective_permissions for backward compatibility.
        """
        with PerformanceTracker("File.get_effective_permissions_legacy") as tracker:
            # 🔹 Vérifier permissions directes user
            perm = FilePermission.query.filter_by(user_id=user.id, file_id=self.id).first()
            if perm:
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="file", 
                    resource_count=1,
                    duration_ms=tracker.duration_ms,
                    method="legacy"
                )
                return perm

            # 🔹 Vérifier permissions via groupes
            for group in user.groups:
                perm = FilePermission.query.filter_by(group_id=group.id, file_id=self.id).first()
                if perm:
                    log_permission_query_stats(
                        user_id=user.id,
                        resource_type="file",
                        resource_count=1, 
                        duration_ms=tracker.duration_ms,
                        method="legacy"
                    )
                    return perm

            # 🔹 Hériter du dossier parent
            if self.folder:
                parent_perm = self.folder.get_effective_permissions(user)
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="file",
                    resource_count=1,
                    duration_ms=tracker.duration_ms,
                    method="legacy"
                )
                return parent_perm

            log_permission_query_stats(
                user_id=user.id,
                resource_type="file",
                resource_count=1,
                duration_ms=tracker.duration_ms,
                method="legacy"
            )
            return None
    
    def _create_permission_object(self, perm_set, user):
        """
        Create a FilePermission-like object from PermissionSet for backward compatibility.
        """
        # Create a mock permission object that behaves like FilePermission
        class PermissionProxy:
            def __init__(self, perm_set, file_id, user_id):
                self.can_read = perm_set.can_read
                self.can_write = perm_set.can_write
                self.can_delete = perm_set.can_delete
                self.can_share = perm_set.can_share
                self.is_owner = perm_set.is_owner
                self.source = perm_set.source
                self.file_id = file_id
                self.user_id = user_id
                
            def __bool__(self):
                return any([self.can_read, self.can_write, self.can_delete, self.can_share, self.is_owner])
        
        return PermissionProxy(perm_set, self.id, user.id)
    
    @classmethod
    @performance_monitor("File.get_bulk_permissions", log_threshold_ms=100.0)
    def get_bulk_permissions(cls, user, file_ids):
        """
        Get permissions for multiple files efficiently.
        
        Args:
            user: User object
            file_ids: List of file IDs
            
        Returns:
            Dictionary mapping file_id to permission object
        """
        try:
            from services.permission_optimizer import PermissionOptimizer
            
            with PerformanceTracker("File.get_bulk_permissions_optimized") as tracker:
                optimizer = PermissionOptimizer()
                permissions = optimizer.get_bulk_file_permissions(user.id, file_ids)
                
                log_permission_query_stats(
                    user_id=user.id,
                    resource_type="file",
                    resource_count=len(file_ids),
                    duration_ms=tracker.duration_ms,
                    method="optimized_bulk"
                )
                
                # Convert to permission objects for backward compatibility
                result = {}
                for file_id, perm_set in permissions.items():
                    if perm_set.source != "none":
                        result[file_id] = cls._create_permission_object_static(perm_set, file_id, user.id)
                    else:
                        result[file_id] = None
                
                return result
                
        except Exception as e:
            from utils.performance_logger import performance_logger
            performance_logger.error(f"Error in bulk permission check for files: {str(e)}")
            
            # Fallback to individual checks
            result = {}
            for file_id in file_ids:
                file_obj = cls.query.get(file_id)
                if file_obj:
                    result[file_id] = file_obj.get_effective_permissions(user)
                else:
                    result[file_id] = None
            
            return result
    
    @staticmethod
    def _create_permission_object_static(perm_set, file_id, user_id):
        """Static version of _create_permission_object for bulk operations."""
        class PermissionProxy:
            def __init__(self, perm_set, file_id, user_id):
                self.can_read = perm_set.can_read
                self.can_write = perm_set.can_write
                self.can_delete = perm_set.can_delete
                self.can_share = perm_set.can_share
                self.is_owner = perm_set.is_owner
                self.source = perm_set.source
                self.file_id = file_id
                self.user_id = user_id
                
            def __bool__(self):
                return any([self.can_read, self.can_write, self.can_delete, self.can_share, self.is_owner])
        
        return PermissionProxy(perm_set, file_id, user_id)
