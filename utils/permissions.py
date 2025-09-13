from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Union
import json
from models.role_permission import RolePermission
from models.permission import Permission
from extensions import db


@dataclass
class PermissionSet:
    """
    Data structure representing a complete set of permissions for a user on a resource.
    
    This class encapsulates all permission types and provides utility methods for
    serialization, comparison, and merging of permissions.
    """
    can_read: bool = False
    can_write: bool = False
    can_delete: bool = False
    can_share: bool = False
    is_owner: bool = False
    source: str = "none"  # "direct", "group", "inherited", "owner"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert PermissionSet to dictionary for serialization.
        
        Returns:
            Dict containing all permission fields
        """
        return asdict(self)
    
    def to_json(self) -> str:
        """
        Convert PermissionSet to JSON string for caching.
        
        Returns:
            JSON string representation of permissions
        """
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PermissionSet':
        """
        Create PermissionSet from dictionary.
        
        Args:
            data: Dictionary containing permission fields
            
        Returns:
            PermissionSet instance
        """
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PermissionSet':
        """
        Create PermissionSet from JSON string.
        
        Args:
            json_str: JSON string representation of permissions
            
        Returns:
            PermissionSet instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    def has_any_permission(self) -> bool:
        """
        Check if this permission set grants any access.
        
        Returns:
            True if any permission is granted
        """
        return any([self.can_read, self.can_write, self.can_delete, self.can_share, self.is_owner])
    
    def has_write_access(self) -> bool:
        """
        Check if this permission set allows write operations.
        
        Returns:
            True if write, delete, or owner permissions are granted
        """
        return self.can_write or self.can_delete or self.is_owner
    
    def has_full_access(self) -> bool:
        """
        Check if this permission set grants full access.
        
        Returns:
            True if all permissions are granted or user is owner
        """
        return self.is_owner or (self.can_read and self.can_write and self.can_delete and self.can_share)
    
    def merge_with(self, other: 'PermissionSet', prefer_higher: bool = True) -> 'PermissionSet':
        """
        Merge this permission set with another, taking the most permissive values.
        
        Args:
            other: Another PermissionSet to merge with
            prefer_higher: If True, takes the more permissive permission for each field
            
        Returns:
            New PermissionSet with merged permissions
        """
        if prefer_higher:
            merged = PermissionSet(
                can_read=self.can_read or other.can_read,
                can_write=self.can_write or other.can_write,
                can_delete=self.can_delete or other.can_delete,
                can_share=self.can_share or other.can_share,
                is_owner=self.is_owner or other.is_owner,
                source=self._get_priority_source(self.source, other.source)
            )
        else:
            # Take permissions from other, fallback to self only if other doesn't have the permission
            merged = PermissionSet(
                can_read=other.can_read or self.can_read,
                can_write=other.can_write or self.can_write,
                can_delete=other.can_delete or self.can_delete,
                can_share=other.can_share or self.can_share,
                is_owner=other.is_owner or self.is_owner,
                source=other.source if other.source != "none" else self.source
            )
        
        return merged
    
    def is_equal_to(self, other: 'PermissionSet', ignore_source: bool = False) -> bool:
        """
        Compare this permission set with another for equality.
        
        Args:
            other: Another PermissionSet to compare with
            ignore_source: If True, ignores the source field in comparison
            
        Returns:
            True if permission sets are equal
        """
        if not isinstance(other, PermissionSet):
            return False
        
        permissions_equal = (
            self.can_read == other.can_read and
            self.can_write == other.can_write and
            self.can_delete == other.can_delete and
            self.can_share == other.can_share and
            self.is_owner == other.is_owner
        )
        
        if ignore_source:
            return permissions_equal
        
        return permissions_equal and self.source == other.source
    
    def is_more_permissive_than(self, other: 'PermissionSet') -> bool:
        """
        Check if this permission set is more permissive than another.
        
        Args:
            other: Another PermissionSet to compare with
            
        Returns:
            True if this permission set grants more access
        """
        if not isinstance(other, PermissionSet):
            return False
        
        # Count granted permissions
        self_count = sum([self.can_read, self.can_write, self.can_delete, self.can_share])
        other_count = sum([other.can_read, other.can_write, other.can_delete, other.can_share])
        
        # Owner always wins
        if self.is_owner and not other.is_owner:
            return True
        if other.is_owner and not self.is_owner:
            return False
        
        return self_count > other_count
    
    def _get_priority_source(self, source1: str, source2: str) -> str:
        """
        Determine which source has higher priority for merged permissions.
        
        Priority order: owner > direct > group > inherited > none
        
        Args:
            source1: First source string
            source2: Second source string
            
        Returns:
            Source string with higher priority
        """
        priority_order = {
            "owner": 4,
            "direct": 3,
            "group": 2,
            "inherited": 1,
            "none": 0
        }
        
        priority1 = priority_order.get(source1, 0)
        priority2 = priority_order.get(source2, 0)
        
        return source1 if priority1 >= priority2 else source2
    
    @classmethod
    def create_owner_permissions(cls) -> 'PermissionSet':
        """
        Create a PermissionSet with full owner permissions.
        
        Returns:
            PermissionSet with all permissions granted and owner source
        """
        return cls(
            can_read=True,
            can_write=True,
            can_delete=True,
            can_share=True,
            is_owner=True,
            source="owner"
        )
    
    @classmethod
    def create_no_permissions(cls) -> 'PermissionSet':
        """
        Create a PermissionSet with no permissions.
        
        Returns:
            PermissionSet with all permissions denied
        """
        return cls(
            can_read=False,
            can_write=False,
            can_delete=False,
            can_share=False,
            is_owner=False,
            source="none"
        )
    
    @classmethod
    def create_read_only(cls, source: str = "direct") -> 'PermissionSet':
        """
        Create a PermissionSet with read-only permissions.
        
        Args:
            source: Source of the permission
            
        Returns:
            PermissionSet with only read permission granted
        """
        return cls(
            can_read=True,
            can_write=False,
            can_delete=False,
            can_share=False,
            is_owner=False,
            source=source
        )
    
    def __str__(self) -> str:
        """String representation of PermissionSet."""
        permissions = []
        if self.is_owner:
            permissions.append("OWNER")
        if self.can_read:
            permissions.append("READ")
        if self.can_write:
            permissions.append("WRITE")
        if self.can_delete:
            permissions.append("DELETE")
        if self.can_share:
            permissions.append("SHARE")
        
        perm_str = "|".join(permissions) if permissions else "NONE"
        return f"PermissionSet({perm_str}, source={self.source})"


def has_permission(user, resource, action):
    """
    Vérifie si un utilisateur a la permission d'exécuter une action sur une ressource
    """
    q = (
        db.session.query(RolePermission)
        .join(Permission)
        .filter(
            RolePermission.role == user.role,
            Permission.resource == resource,
            Permission.action == action
        )
        .first()
    )
    return q is not None
