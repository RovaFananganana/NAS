from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from sqlalchemy import text
from extensions import db
from models import User, Group, File, Folder, FilePermission, FolderPermission, PermissionCache


@dataclass
class PermissionSet:
    """Data structure representing a user's permissions on a resource."""
    can_read: bool = False
    can_write: bool = False
    can_delete: bool = False
    can_share: bool = False
    is_owner: bool = False
    source: str = "none"  # "direct", "group", "inherited", "owner"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'can_read': self.can_read,
            'can_write': self.can_write,
            'can_delete': self.can_delete,
            'can_share': self.can_share,
            'is_owner': self.is_owner,
            'source': self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PermissionSet':
        """Create from dictionary for deserialization."""
        return cls(**data)
    
    def merge_with(self, other: 'PermissionSet') -> 'PermissionSet':
        """Merge with another permission set, taking the most permissive values."""
        return PermissionSet(
            can_read=self.can_read or other.can_read,
            can_write=self.can_write or other.can_write,
            can_delete=self.can_delete or other.can_delete,
            can_share=self.can_share or other.can_share,
            is_owner=self.is_owner or other.is_owner,
            source=self.source if self.source != "none" else other.source
        )


class PermissionOptimizer:
    """Service for optimized permission loading and caching."""
    
    def __init__(self, enable_cache: bool = True, cache_expiration_hours: int = 1):
        self.enable_cache = enable_cache
        self.cache_expiration_hours = cache_expiration_hours
    
    def _get_cached_permissions(self, user_id: int, resource_type: str, 
                              resource_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Get cached permissions for multiple resources.
        
        Args:
            user_id: ID of the user
            resource_type: 'file' or 'folder'
            resource_ids: List of resource IDs to check cache for
            
        Returns:
            Dictionary mapping resource_id to PermissionSet for cached entries
        """
        if not self.enable_cache or not resource_ids:
            return {}
        
        cached_permissions = {}
        
        for resource_id in resource_ids:
            cache_entry = PermissionCache.get_cached_permission(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            if cache_entry:
                cached_permissions[resource_id] = PermissionSet(
                    can_read=cache_entry.can_read,
                    can_write=cache_entry.can_write,
                    can_delete=cache_entry.can_delete,
                    can_share=cache_entry.can_share,
                    is_owner=cache_entry.is_owner,
                    source=cache_entry.permission_source
                )
        
        return cached_permissions
    
    def _cache_permissions(self, user_id: int, resource_type: str, 
                          permissions: Dict[int, PermissionSet]) -> None:
        """
        Cache permissions for multiple resources.
        
        Args:
            user_id: ID of the user
            resource_type: 'file' or 'folder'
            permissions: Dictionary mapping resource_id to PermissionSet
        """
        if not self.enable_cache or not permissions:
            return
        
        for resource_id, perm_set in permissions.items():
            permissions_dict = {
                'can_read': perm_set.can_read,
                'can_write': perm_set.can_write,
                'can_delete': perm_set.can_delete,
                'can_share': perm_set.can_share,
                'is_owner': perm_set.is_owner
            }
            
            PermissionCache.set_cached_permission(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                permissions_dict=permissions_dict,
                permission_source=perm_set.source,
                expiration_hours=self.cache_expiration_hours
            )
        
        # Commit the cache entries
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Log error but don't fail the operation
            print(f"Warning: Failed to cache permissions: {e}")
    
    def invalidate_user_permissions(self, user_id: int) -> None:
        """
        Invalidate all cached permissions for a specific user.
        
        Args:
            user_id: ID of the user whose cache should be invalidated
        """
        if not self.enable_cache:
            return
        
        PermissionCache.invalidate_user_cache(user_id)
    
    def invalidate_resource_permissions(self, resource_type: str, resource_id: int) -> None:
        """
        Invalidate cached permissions for a specific resource.
        
        Args:
            resource_type: 'file' or 'folder'
            resource_id: ID of the resource whose cache should be invalidated
        """
        if not self.enable_cache:
            return
        
        PermissionCache.invalidate_resource_cache(resource_type, resource_id)
    
    def warm_cache_for_user(self, user_id: int, resource_type: str = None, 
                           limit: int = 100) -> Dict[str, int]:
        """
        Pre-warm the cache for frequently accessed resources by a user.
        
        Args:
            user_id: ID of the user
            resource_type: Optional filter for 'file' or 'folder', None for both
            limit: Maximum number of resources to warm per type
            
        Returns:
            Dictionary with cache warming statistics
        """
        if not self.enable_cache:
            return {'files_warmed': 0, 'folders_warmed': 0}
        
        stats = {'files_warmed': 0, 'folders_warmed': 0}
        
        # Warm file cache
        if resource_type is None or resource_type == 'file':
            # Get recently accessed files by the user (you might want to add access logging)
            # For now, get files owned by the user or in folders they have access to
            file_query = text("""
                SELECT DISTINCT f.id
                FROM files f
                LEFT JOIN folders fold ON f.folder_id = fold.id
                WHERE f.owner_id = :user_id 
                   OR fold.owner_id = :user_id
                   OR EXISTS (
                       SELECT 1 FROM file_permissions fp 
                       WHERE fp.file_id = f.id AND fp.user_id = :user_id
                   )
                   OR EXISTS (
                       SELECT 1 FROM folder_permissions folp 
                       WHERE folp.folder_id = f.folder_id AND folp.user_id = :user_id
                   )
                ORDER BY f.id
                LIMIT :limit
            """)
            
            file_result = db.session.execute(file_query, {'user_id': user_id, 'limit': limit})
            file_ids = [row[0] for row in file_result]
            
            if file_ids:
                # Get permissions and cache them
                file_permissions = self.get_bulk_file_permissions(user_id, file_ids)
                stats['files_warmed'] = len(file_permissions)
        
        # Warm folder cache
        if resource_type is None or resource_type == 'folder':
            folder_query = text("""
                SELECT DISTINCT f.id
                FROM folders f
                WHERE f.owner_id = :user_id 
                   OR EXISTS (
                       SELECT 1 FROM folder_permissions fp 
                       WHERE fp.folder_id = f.id AND fp.user_id = :user_id
                   )
                ORDER BY f.id
                LIMIT :limit
            """)
            
            folder_result = db.session.execute(folder_query, {'user_id': user_id, 'limit': limit})
            folder_ids = [row[0] for row in folder_result]
            
            if folder_ids:
                # Get permissions and cache them
                folder_permissions = self.get_bulk_folder_permissions(user_id, folder_ids)
                stats['folders_warmed'] = len(folder_permissions)
        
        return stats
    
    def on_file_permission_changed(self, file_id: int, user_ids: List[int] = None) -> None:
        """
        Handle cache invalidation when file permissions change.
        
        Args:
            file_id: ID of the file whose permissions changed
            user_ids: Optional list of specific user IDs to invalidate, None for all users
        """
        if not self.enable_cache:
            return
        
        if user_ids:
            # Invalidate cache for specific users
            for user_id in user_ids:
                cache_entries = PermissionCache.query.filter_by(
                    user_id=user_id,
                    resource_type='file',
                    resource_id=file_id
                ).all()
                for entry in cache_entries:
                    db.session.delete(entry)
        else:
            # Invalidate cache for all users on this file
            self.invalidate_resource_permissions('file', file_id)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Warning: Failed to invalidate file permission cache: {e}")
    
    def on_folder_permission_changed(self, folder_id: int, user_ids: List[int] = None) -> None:
        """
        Handle cache invalidation when folder permissions change.
        Also invalidates cache for all files in the folder due to inheritance.
        
        Args:
            folder_id: ID of the folder whose permissions changed
            user_ids: Optional list of specific user IDs to invalidate, None for all users
        """
        if not self.enable_cache:
            return
        
        # Invalidate folder cache
        if user_ids:
            for user_id in user_ids:
                cache_entries = PermissionCache.query.filter_by(
                    user_id=user_id,
                    resource_type='folder',
                    resource_id=folder_id
                ).all()
                for entry in cache_entries:
                    db.session.delete(entry)
        else:
            self.invalidate_resource_permissions('folder', folder_id)
        
        # Invalidate cache for files in this folder (due to inheritance)
        file_query = text("""
            SELECT id FROM files WHERE folder_id = :folder_id
        """)
        file_result = db.session.execute(file_query, {'folder_id': folder_id})
        file_ids = [row[0] for row in file_result]
        
        for file_id in file_ids:
            if user_ids:
                for user_id in user_ids:
                    cache_entries = PermissionCache.query.filter_by(
                        user_id=user_id,
                        resource_type='file',
                        resource_id=file_id
                    ).all()
                    for entry in cache_entries:
                        db.session.delete(entry)
            else:
                self.invalidate_resource_permissions('file', file_id)
        
        # Also invalidate cache for subfolders (recursive inheritance)
        subfolder_query = text("""
            WITH RECURSIVE subfolder_tree AS (
                SELECT id FROM folders WHERE parent_id = :folder_id
                UNION ALL
                SELECT f.id FROM folders f
                INNER JOIN subfolder_tree st ON f.parent_id = st.id
            )
            SELECT id FROM subfolder_tree
        """)
        subfolder_result = db.session.execute(subfolder_query, {'folder_id': folder_id})
        subfolder_ids = [row[0] for row in subfolder_result]
        
        for subfolder_id in subfolder_ids:
            if user_ids:
                for user_id in user_ids:
                    cache_entries = PermissionCache.query.filter_by(
                        user_id=user_id,
                        resource_type='folder',
                        resource_id=subfolder_id
                    ).all()
                    for entry in cache_entries:
                        db.session.delete(entry)
            else:
                self.invalidate_resource_permissions('folder', subfolder_id)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Warning: Failed to invalidate folder permission cache: {e}")
    
    def on_user_group_changed(self, user_id: int) -> None:
        """
        Handle cache invalidation when a user's group membership changes.
        
        Args:
            user_id: ID of the user whose group membership changed
        """
        if not self.enable_cache:
            return
        
        # Invalidate all permissions for this user since group membership affects all permissions
        self.invalidate_user_permissions(user_id)
    
    def get_cache_statistics(self) -> Dict:
        """
        Get cache performance statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enable_cache:
            return {
                'cache_enabled': False,
                'total_entries': 0,
                'active_entries': 0,
                'expired_entries': 0
            }
        
        stats = PermissionCache.get_cache_stats()
        stats['cache_enabled'] = True
        return stats
    
    def get_bulk_file_permissions(self, user_id: int, file_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Get permissions for multiple files in a single optimized query with caching.
        
        Args:
            user_id: ID of the user to check permissions for
            file_ids: List of file IDs to check permissions for
            
        Returns:
            Dictionary mapping file_id to PermissionSet
        """
        if not file_ids:
            return {}
        
        # Step 1: Check cache first
        cached_permissions = self._get_cached_permissions(user_id, 'file', file_ids)
        
        # Step 2: Identify files that need to be loaded from database
        uncached_file_ids = [fid for fid in file_ids if fid not in cached_permissions]
        
        # Step 3: Load uncached permissions from database
        db_permissions = {}
        if uncached_file_ids:
            db_permissions = self._load_file_permissions_from_db(user_id, uncached_file_ids)
            
            # Step 4: Cache the newly loaded permissions
            self._cache_permissions(user_id, 'file', db_permissions)
        
        # Step 5: Combine cached and database results
        all_permissions = {**cached_permissions, **db_permissions}
        
        return all_permissions
    
    def _load_file_permissions_from_db(self, user_id: int, file_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Load file permissions from database (original implementation).
        
        Args:
            user_id: ID of the user to check permissions for
            file_ids: List of file IDs to check permissions for
            
        Returns:
            Dictionary mapping file_id to PermissionSet
        """
        # Get user's group IDs for group permission checks
        user_groups_query = text("""
            SELECT group_id FROM user_group WHERE user_id = :user_id
        """)
        user_groups_result = db.session.execute(user_groups_query, {'user_id': user_id})
        user_group_ids = [row[0] for row in user_groups_result]
        
        # Main query using CTE for optimized permission loading
        query = text("""
            WITH user_groups AS (
                SELECT unnest(ARRAY[:group_ids]) as group_id
            ),
            file_direct_perms AS (
                SELECT 
                    f.id as file_id,
                    f.owner_id,
                    f.folder_id,
                    fp_user.can_read as user_can_read,
                    fp_user.can_write as user_can_write,
                    fp_user.can_delete as user_can_delete,
                    fp_user.can_share as user_can_share,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_read THEN 1 ELSE 0 END), 0
                    ) as group_can_read,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_write THEN 1 ELSE 0 END), 0
                    ) as group_can_write,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_delete THEN 1 ELSE 0 END), 0
                    ) as group_can_delete,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_share THEN 1 ELSE 0 END), 0
                    ) as group_can_share
                FROM files f
                LEFT JOIN file_permissions fp_user ON f.id = fp_user.file_id AND fp_user.user_id = :user_id
                LEFT JOIN file_permissions fp_group ON f.id = fp_group.file_id 
                    AND fp_group.group_id = ANY(ARRAY[:group_ids])
                WHERE f.id = ANY(ARRAY[:file_ids])
                GROUP BY f.id, f.owner_id, f.folder_id, fp_user.can_read, fp_user.can_write, 
                         fp_user.can_delete, fp_user.can_share
            )
            SELECT 
                file_id,
                owner_id,
                folder_id,
                COALESCE(user_can_read, false) as user_can_read,
                COALESCE(user_can_write, false) as user_can_write,
                COALESCE(user_can_delete, false) as user_can_delete,
                COALESCE(user_can_share, false) as user_can_share,
                (group_can_read = 1) as group_can_read,
                (group_can_write = 1) as group_can_write,
                (group_can_delete = 1) as group_can_delete,
                (group_can_share = 1) as group_can_share,
                (owner_id = :user_id) as is_owner
            FROM file_direct_perms
        """)
        
        params = {
            'user_id': user_id,
            'file_ids': file_ids,
            'group_ids': user_group_ids if user_group_ids else [0]  # Use dummy value if no groups
        }
        
        result = db.session.execute(query, params)
        permissions = {}
        
        for row in result:
            file_id = row.file_id
            
            # Determine the most permissive permissions and their source
            can_read = row.user_can_read or row.group_can_read or row.is_owner
            can_write = row.user_can_write or row.group_can_write or row.is_owner
            can_delete = row.user_can_delete or row.group_can_delete or row.is_owner
            can_share = row.user_can_share or row.group_can_share or row.is_owner
            
            # Determine permission source
            source = "none"
            if row.is_owner:
                source = "owner"
            elif row.user_can_read or row.user_can_write or row.user_can_delete or row.user_can_share:
                source = "direct"
            elif row.group_can_read or row.group_can_write or row.group_can_delete or row.group_can_share:
                source = "group"
            
            permissions[file_id] = PermissionSet(
                can_read=can_read,
                can_write=can_write,
                can_delete=can_delete,
                can_share=can_share,
                is_owner=row.is_owner,
                source=source
            )
        
        # Handle files that need inherited permissions from folders
        files_needing_inheritance = []
        for file_id in file_ids:
            if file_id not in permissions or permissions[file_id].source == "none":
                files_needing_inheritance.append(file_id)
        
        if files_needing_inheritance:
            inherited_perms = self._get_inherited_file_permissions(user_id, files_needing_inheritance)
            for file_id, perm_set in inherited_perms.items():
                if file_id in permissions:
                    permissions[file_id] = permissions[file_id].merge_with(perm_set)
                else:
                    permissions[file_id] = perm_set
        
        return permissions
    
    def get_bulk_folder_permissions(self, user_id: int, folder_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Get permissions for multiple folders in a single optimized query with inheritance resolution and caching.
        
        Args:
            user_id: ID of the user to check permissions for
            folder_ids: List of folder IDs to check permissions for
            
        Returns:
            Dictionary mapping folder_id to PermissionSet
        """
        if not folder_ids:
            return {}
        
        # Step 1: Check cache first
        cached_permissions = self._get_cached_permissions(user_id, 'folder', folder_ids)
        
        # Step 2: Identify folders that need to be loaded from database
        uncached_folder_ids = [fid for fid in folder_ids if fid not in cached_permissions]
        
        # Step 3: Load uncached permissions from database
        db_permissions = {}
        if uncached_folder_ids:
            db_permissions = self._load_folder_permissions_from_db(user_id, uncached_folder_ids)
            
            # Step 4: Cache the newly loaded permissions
            self._cache_permissions(user_id, 'folder', db_permissions)
        
        # Step 5: Combine cached and database results
        all_permissions = {**cached_permissions, **db_permissions}
        
        return all_permissions
    
    def _load_folder_permissions_from_db(self, user_id: int, folder_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Load folder permissions from database (original implementation).
        
        Args:
            user_id: ID of the user to check permissions for
            folder_ids: List of folder IDs to check permissions for
            
        Returns:
            Dictionary mapping folder_id to PermissionSet
        """
        # Get user's group IDs
        user_groups_query = text("""
            SELECT group_id FROM user_group WHERE user_id = :user_id
        """)
        user_groups_result = db.session.execute(user_groups_query, {'user_id': user_id})
        user_group_ids = [row[0] for row in user_groups_result]
        
        # Recursive CTE to get folder hierarchy and permissions
        query = text("""
            WITH RECURSIVE folder_hierarchy AS (
                -- Base case: requested folders
                SELECT 
                    f.id as folder_id,
                    f.parent_id,
                    f.owner_id,
                    0 as depth,
                    ARRAY[f.id] as path
                FROM folders f
                WHERE f.id = ANY(ARRAY[:folder_ids])
                
                UNION ALL
                
                -- Recursive case: parent folders
                SELECT 
                    f.id as folder_id,
                    f.parent_id,
                    f.owner_id,
                    fh.depth + 1 as depth,
                    f.id || fh.path as path
                FROM folders f
                INNER JOIN folder_hierarchy fh ON f.id = fh.parent_id
                WHERE fh.depth < 10  -- Prevent infinite recursion
            ),
            folder_permissions_agg AS (
                SELECT 
                    fh.folder_id,
                    fh.depth,
                    fh.owner_id,
                    fp_user.can_read as user_can_read,
                    fp_user.can_write as user_can_write,
                    fp_user.can_delete as user_can_delete,
                    fp_user.can_share as user_can_share,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_read THEN 1 ELSE 0 END), 0
                    ) as group_can_read,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_write THEN 1 ELSE 0 END), 0
                    ) as group_can_write,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_delete THEN 1 ELSE 0 END), 0
                    ) as group_can_delete,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_share THEN 1 ELSE 0 END), 0
                    ) as group_can_share,
                    (fh.owner_id = :user_id) as is_owner
                FROM folder_hierarchy fh
                LEFT JOIN folder_permissions fp_user ON fh.folder_id = fp_user.folder_id 
                    AND fp_user.user_id = :user_id
                LEFT JOIN folder_permissions fp_group ON fh.folder_id = fp_group.folder_id 
                    AND fp_group.group_id = ANY(ARRAY[:group_ids])
                GROUP BY fh.folder_id, fh.depth, fh.owner_id, fp_user.can_read, 
                         fp_user.can_write, fp_user.can_delete, fp_user.can_share
            )
            SELECT 
                folder_id,
                depth,
                owner_id,
                COALESCE(user_can_read, false) as user_can_read,
                COALESCE(user_can_write, false) as user_can_write,
                COALESCE(user_can_delete, false) as user_can_delete,
                COALESCE(user_can_share, false) as user_can_share,
                (group_can_read = 1) as group_can_read,
                (group_can_write = 1) as group_can_write,
                (group_can_delete = 1) as group_can_delete,
                (group_can_share = 1) as group_can_share,
                is_owner
            FROM folder_permissions_agg
            ORDER BY folder_id, depth
        """)
        
        params = {
            'user_id': user_id,
            'folder_ids': folder_ids,
            'group_ids': user_group_ids if user_group_ids else [0]
        }
        
        result = db.session.execute(query, params)
        
        # Process results to resolve inheritance
        folder_perms_by_depth = {}
        for row in result:
            folder_id = row.folder_id
            depth = row.depth
            
            if folder_id not in folder_perms_by_depth:
                folder_perms_by_depth[folder_id] = []
            
            # Calculate effective permissions for this level
            can_read = row.user_can_read or row.group_can_read or row.is_owner
            can_write = row.user_can_write or row.group_can_write or row.is_owner
            can_delete = row.user_can_delete or row.group_can_delete or row.is_owner
            can_share = row.user_can_share or row.group_can_share or row.is_owner
            
            # Determine source
            source = "none"
            if row.is_owner:
                source = "owner"
            elif row.user_can_read or row.user_can_write or row.user_can_delete or row.user_can_share:
                source = "direct" if depth == 0 else "inherited"
            elif row.group_can_read or row.group_can_write or row.group_can_delete or row.group_can_share:
                source = "group" if depth == 0 else "inherited"
            
            perm_set = PermissionSet(
                can_read=can_read,
                can_write=can_write,
                can_delete=can_delete,
                can_share=can_share,
                is_owner=row.is_owner,
                source=source
            )
            
            folder_perms_by_depth[folder_id].append((depth, perm_set))
        
        # Resolve final permissions by taking the most specific (lowest depth) non-none permissions
        final_permissions = {}
        for folder_id in folder_ids:
            if folder_id in folder_perms_by_depth:
                perms_list = sorted(folder_perms_by_depth[folder_id], key=lambda x: x[0])
                
                # Find the first permission set that grants any access
                final_perm = PermissionSet()
                for depth, perm_set in perms_list:
                    if perm_set.source != "none":
                        final_perm = perm_set
                        break
                
                final_permissions[folder_id] = final_perm
            else:
                # No permissions found
                final_permissions[folder_id] = PermissionSet()
        
        return final_permissions
    
    def _get_inherited_file_permissions(self, user_id: int, file_ids: List[int]) -> Dict[int, PermissionSet]:
        """
        Get inherited permissions for files from their parent folders.
        
        Args:
            user_id: ID of the user to check permissions for
            file_ids: List of file IDs that need inherited permissions
            
        Returns:
            Dictionary mapping file_id to inherited PermissionSet
        """
        if not file_ids:
            return {}
        
        # Get folder IDs for the files
        folder_query = text("""
            SELECT id, folder_id FROM files WHERE id = ANY(ARRAY[:file_ids]) AND folder_id IS NOT NULL
        """)
        folder_result = db.session.execute(folder_query, {'file_ids': file_ids})
        
        file_to_folder = {}
        folder_ids = set()
        for row in folder_result:
            file_to_folder[row.id] = row.folder_id
            folder_ids.add(row.folder_id)
        
        if not folder_ids:
            return {file_id: PermissionSet() for file_id in file_ids}
        
        # Get folder permissions
        folder_permissions = self.get_bulk_folder_permissions(user_id, list(folder_ids))
        
        # Map file permissions from folder permissions
        file_permissions = {}
        for file_id in file_ids:
            if file_id in file_to_folder:
                folder_id = file_to_folder[file_id]
                if folder_id in folder_permissions:
                    folder_perm = folder_permissions[folder_id]
                    # Create inherited permission set
                    file_permissions[file_id] = PermissionSet(
                        can_read=folder_perm.can_read,
                        can_write=folder_perm.can_write,
                        can_delete=folder_perm.can_delete,
                        can_share=folder_perm.can_share,
                        is_owner=folder_perm.is_owner,
                        source="inherited"
                    )
                else:
                    file_permissions[file_id] = PermissionSet()
            else:
                file_permissions[file_id] = PermissionSet()
        
        return file_permissions
    
    def get_folder_tree_permissions(self, user_id: int, folder_id: int, depth: int = 3, 
                                   limit: int = 1000, offset: int = 0) -> Dict[int, PermissionSet]:
        """
        Get permissions for an entire folder subtree in a single optimized query.
        
        Args:
            user_id: ID of the user to check permissions for
            folder_id: Root folder ID to start the tree traversal
            depth: Maximum depth to traverse (default: 3)
            limit: Maximum number of folders to return for pagination (default: 1000)
            offset: Offset for pagination (default: 0)
            
        Returns:
            Dictionary mapping folder_id to PermissionSet for all folders in the subtree
        """
        # Get user's group IDs
        user_groups_query = text("""
            SELECT group_id FROM user_group WHERE user_id = :user_id
        """)
        user_groups_result = db.session.execute(user_groups_query, {'user_id': user_id})
        user_group_ids = [row[0] for row in user_groups_result]
        
        # Recursive CTE to traverse folder tree and collect permissions
        query = text("""
            WITH RECURSIVE folder_tree AS (
                -- Base case: root folder
                SELECT 
                    f.id as folder_id,
                    f.parent_id,
                    f.owner_id,
                    f.name,
                    0 as depth,
                    ARRAY[f.id] as path,
                    f.id::text as sort_path
                FROM folders f
                WHERE f.id = :root_folder_id
                
                UNION ALL
                
                -- Recursive case: child folders
                SELECT 
                    f.id as folder_id,
                    f.parent_id,
                    f.owner_id,
                    f.name,
                    ft.depth + 1 as depth,
                    ft.path || f.id as path,
                    ft.sort_path || '/' || f.id::text as sort_path
                FROM folders f
                INNER JOIN folder_tree ft ON f.parent_id = ft.folder_id
                WHERE ft.depth < :max_depth
            ),
            folder_tree_with_permissions AS (
                SELECT 
                    ft.folder_id,
                    ft.parent_id,
                    ft.owner_id,
                    ft.name,
                    ft.depth,
                    ft.path,
                    ft.sort_path,
                    fp_user.can_read as user_can_read,
                    fp_user.can_write as user_can_write,
                    fp_user.can_delete as user_can_delete,
                    fp_user.can_share as user_can_share,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_read THEN 1 ELSE 0 END), 0
                    ) as group_can_read,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_write THEN 1 ELSE 0 END), 0
                    ) as group_can_write,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_delete THEN 1 ELSE 0 END), 0
                    ) as group_can_delete,
                    COALESCE(
                        MAX(CASE WHEN fp_group.can_share THEN 1 ELSE 0 END), 0
                    ) as group_can_share,
                    (ft.owner_id = :user_id) as is_owner
                FROM folder_tree ft
                LEFT JOIN folder_permissions fp_user ON ft.folder_id = fp_user.folder_id 
                    AND fp_user.user_id = :user_id
                LEFT JOIN folder_permissions fp_group ON ft.folder_id = fp_group.folder_id 
                    AND fp_group.group_id = ANY(ARRAY[:group_ids])
                GROUP BY ft.folder_id, ft.parent_id, ft.owner_id, ft.name, ft.depth, 
                         ft.path, ft.sort_path, fp_user.can_read, fp_user.can_write, 
                         fp_user.can_delete, fp_user.can_share
            )
            SELECT 
                folder_id,
                parent_id,
                owner_id,
                name,
                depth,
                path,
                COALESCE(user_can_read, false) as user_can_read,
                COALESCE(user_can_write, false) as user_can_write,
                COALESCE(user_can_delete, false) as user_can_delete,
                COALESCE(user_can_share, false) as user_can_share,
                (group_can_read = 1) as group_can_read,
                (group_can_write = 1) as group_can_write,
                (group_can_delete = 1) as group_can_delete,
                (group_can_share = 1) as group_can_share,
                is_owner
            FROM folder_tree_with_permissions
            ORDER BY sort_path
            LIMIT :limit OFFSET :offset
        """)
        
        params = {
            'user_id': user_id,
            'root_folder_id': folder_id,
            'max_depth': depth,
            'group_ids': user_group_ids if user_group_ids else [0],
            'limit': limit,
            'offset': offset
        }
        
        result = db.session.execute(query, params)
        
        # Process results and resolve inheritance
        folders_by_id = {}
        folders_by_path = {}
        
        for row in result:
            folder_data = {
                'id': row.folder_id,
                'parent_id': row.parent_id,
                'owner_id': row.owner_id,
                'name': row.name,
                'depth': row.depth,
                'path': row.path,
                'user_perms': {
                    'can_read': row.user_can_read,
                    'can_write': row.user_can_write,
                    'can_delete': row.user_can_delete,
                    'can_share': row.user_can_share
                },
                'group_perms': {
                    'can_read': row.group_can_read,
                    'can_write': row.group_can_write,
                    'can_delete': row.group_can_delete,
                    'can_share': row.group_can_share
                },
                'is_owner': row.is_owner
            }
            
            folders_by_id[row.folder_id] = folder_data
            folders_by_path[tuple(row.path)] = folder_data
        
        # Resolve permissions with inheritance
        permissions = {}
        
        for folder_data in folders_by_id.values():
            folder_id = folder_data['id']
            path = folder_data['path']
            
            # Start with direct permissions
            effective_perms = self._calculate_direct_permissions(folder_data)
            
            # If no direct permissions, inherit from ancestors
            if effective_perms.source == "none":
                effective_perms = self._resolve_inherited_permissions(
                    folder_data, folders_by_path, user_id
                )
            
            permissions[folder_id] = effective_perms
        
        return permissions
    
    def _calculate_direct_permissions(self, folder_data: Dict) -> PermissionSet:
        """Calculate direct permissions for a folder (user, group, or owner)."""
        user_perms = folder_data['user_perms']
        group_perms = folder_data['group_perms']
        is_owner = folder_data['is_owner']
        
        # Owner has all permissions
        if is_owner:
            return PermissionSet(
                can_read=True,
                can_write=True,
                can_delete=True,
                can_share=True,
                is_owner=True,
                source="owner"
            )
        
        # Check direct user permissions
        if any(user_perms.values()):
            return PermissionSet(
                can_read=user_perms['can_read'],
                can_write=user_perms['can_write'],
                can_delete=user_perms['can_delete'],
                can_share=user_perms['can_share'],
                is_owner=False,
                source="direct"
            )
        
        # Check group permissions
        if any(group_perms.values()):
            return PermissionSet(
                can_read=group_perms['can_read'],
                can_write=group_perms['can_write'],
                can_delete=group_perms['can_delete'],
                can_share=group_perms['can_share'],
                is_owner=False,
                source="group"
            )
        
        return PermissionSet(source="none")
    
    def _resolve_inherited_permissions(self, folder_data: Dict, folders_by_path: Dict, 
                                     user_id: int) -> PermissionSet:
        """Resolve inherited permissions by traversing up the folder hierarchy."""
        path = folder_data['path']
        
        # Traverse up the path to find inherited permissions
        for i in range(len(path) - 1, 0, -1):  # Start from parent, go up
            parent_path = tuple(path[:i])
            if parent_path in folders_by_path:
                parent_data = folders_by_path[parent_path]
                parent_perms = self._calculate_direct_permissions(parent_data)
                
                if parent_perms.source != "none":
                    # Return inherited permissions
                    return PermissionSet(
                        can_read=parent_perms.can_read,
                        can_write=parent_perms.can_write,
                        can_delete=parent_perms.can_delete,
                        can_share=parent_perms.can_share,
                        is_owner=parent_perms.is_owner,
                        source="inherited"
                    )
        
        return PermissionSet(source="none")
    
    def get_folder_tree_metadata(self, folder_id: int, depth: int = 3) -> Dict:
        """
        Get metadata about a folder tree including counts and structure.
        
        Args:
            folder_id: Root folder ID
            depth: Maximum depth to traverse
            
        Returns:
            Dictionary with tree metadata
        """
        query = text("""
            WITH RECURSIVE folder_tree AS (
                SELECT 
                    f.id,
                    f.parent_id,
                    f.name,
                    0 as depth,
                    ARRAY[f.id] as path
                FROM folders f
                WHERE f.id = :folder_id
                
                UNION ALL
                
                SELECT 
                    f.id,
                    f.parent_id,
                    f.name,
                    ft.depth + 1,
                    ft.path || f.id
                FROM folders f
                INNER JOIN folder_tree ft ON f.parent_id = ft.id
                WHERE ft.depth < :max_depth
            ),
            tree_stats AS (
                SELECT 
                    COUNT(*) as total_folders,
                    MAX(depth) as max_depth,
                    COUNT(CASE WHEN depth = 0 THEN 1 END) as root_count,
                    COUNT(CASE WHEN depth = 1 THEN 1 END) as level_1_count,
                    COUNT(CASE WHEN depth = 2 THEN 1 END) as level_2_count,
                    COUNT(CASE WHEN depth = 3 THEN 1 END) as level_3_count
                FROM folder_tree
            ),
            file_stats AS (
                SELECT COUNT(*) as total_files
                FROM files f
                WHERE f.folder_id IN (SELECT id FROM folder_tree)
            )
            SELECT 
                ts.total_folders,
                ts.max_depth,
                ts.root_count,
                ts.level_1_count,
                ts.level_2_count,
                ts.level_3_count,
                fs.total_files
            FROM tree_stats ts
            CROSS JOIN file_stats fs
        """)
        
        result = db.session.execute(query, {
            'folder_id': folder_id,
            'max_depth': depth
        }).fetchone()
        
        if result:
            return {
                'total_folders': result.total_folders,
                'total_files': result.total_files,
                'max_depth': result.max_depth,
                'folders_by_level': {
                    0: result.root_count,
                    1: result.level_1_count,
                    2: result.level_2_count,
                    3: result.level_3_count
                }
            }
        
        return {
            'total_folders': 0,
            'total_files': 0,
            'max_depth': 0,
            'folders_by_level': {}
        }