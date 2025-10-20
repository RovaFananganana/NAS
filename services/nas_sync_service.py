# services/nas_sync_service.py

from datetime import datetime, timezone
from models.folder import Folder
from models.file import File
from models.user import User
from extensions import db
# Import différé pour éviter l'import circulaire
from utils.nas_utils import normalize_smb_path, get_file_mime_type
import os
from typing import Dict, List, Set, Tuple

class NasSyncService:
    """Service for synchronizing database with actual NAS content"""
    
    def __init__(self):
        self.smb_client = None
        self.sync_stats = {
            'folders_scanned': 0,
            'files_scanned': 0,
            'folders_added': 0,
            'files_added': 0,
            'folders_removed': 0,
            'files_removed': 0,
            'folders_updated': 0,
            'files_updated': 0,
            'errors': []
        }
    
    def _get_smb_client(self):
        """Get SMB client instance"""
        if self.smb_client is None:
            # Import différé pour éviter l'import circulaire
            from routes.nas_routes import get_smb_client
            self.smb_client = get_smb_client()
        return self.smb_client
    
    def test_nas_connection(self) -> bool:
        """Test if NAS is accessible"""
        try:
            client = self._get_smb_client()
            result = client.test_connection()
            return result.get('success', False)
        except Exception as e:
            error_msg = f"NAS connection test failed: {str(e)}"
            self.sync_stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
            return False
    
    def scan_nas_recursive(self, path: str = "/", max_depth: int = 10, current_depth: int = 0) -> Dict:
        """
        Recursively scan NAS directory structure
        Returns: {
            'folders': {path: folder_info},
            'files': {path: file_info}
        }
        """
        if current_depth >= max_depth:
            return {'folders': {}, 'files': {}}
        
        folders = {}
        files = {}
        
        try:
            client = self._get_smb_client()
            items = client.list_files(path)
            
            for item in items:
                item_path = normalize_smb_path(item['path'])
                
                if item['is_directory']:
                    # Add folder
                    folders[item_path] = {
                        'name': item['name'],
                        'path': item_path,
                        'parent_path': path if path != "/" else None,
                        'modified': item.get('modified'),
                        'created': item.get('created')
                    }
                    self.sync_stats['folders_scanned'] += 1
                    
                    # Recursively scan subdirectories
                    sub_result = self.scan_nas_recursive(item_path, max_depth, current_depth + 1)
                    folders.update(sub_result['folders'])
                    files.update(sub_result['files'])
                    
                else:
                    # Add file
                    files[item_path] = {
                        'name': item['name'],
                        'path': item_path,
                        'parent_path': path,
                        'size': item.get('size', 0),
                        'modified': item.get('modified'),
                        'created': item.get('created'),
                        'mime_type': get_file_mime_type(item['name'])
                    }
                    self.sync_stats['files_scanned'] += 1
                    
        except Exception as e:
            error_msg = f"Error scanning {path}: {str(e)}"
            self.sync_stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
        
        return {'folders': folders, 'files': files}
    
    def get_database_structure(self) -> Dict:
        """
        Get current database folder/file structure
        Returns: {
            'folders': {path: folder_record},
            'files': {path: file_record}
        }
        """
        folders = {}
        files = {}
        
        try:
            # Get all folders from database
            db_folders = Folder.query.all()
            for folder in db_folders:
                if folder.path:  # Only include folders with paths
                    folders[folder.path] = folder
            
            # Get all files from database
            db_files = File.query.all()
            for file in db_files:
                if hasattr(file, 'path') and file.path:  # Only include files with paths
                    files[file.path] = file
                elif hasattr(file, 'file_path') and file.file_path:  # Check alternative path field
                    files[file.file_path] = file
                    
        except Exception as e:
            error_msg = f"Error reading database structure: {str(e)}"
            self.sync_stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
        
        return {'folders': folders, 'files': files}
    
    def find_orphaned_entries(self, nas_structure: Dict, db_structure: Dict) -> Dict:
        """
        Find database entries that don't exist on NAS
        Returns: {
            'orphaned_folders': [folder_records],
            'orphaned_files': [file_records]
        }
        """
        nas_folders = set(nas_structure['folders'].keys())
        nas_files = set(nas_structure['files'].keys())
        
        db_folders = set(db_structure['folders'].keys())
        db_files = set(db_structure['files'].keys())
        
        # Find orphaned entries
        orphaned_folder_paths = db_folders - nas_folders
        orphaned_file_paths = db_files - nas_files
        
        orphaned_folders = [db_structure['folders'][path] for path in orphaned_folder_paths]
        orphaned_files = [db_structure['files'][path] for path in orphaned_file_paths]
        
        return {
            'orphaned_folders': orphaned_folders,
            'orphaned_files': orphaned_files
        }
    
    def find_missing_entries(self, nas_structure: Dict, db_structure: Dict) -> Dict:
        """
        Find NAS entries that don't exist in database
        Returns: {
            'missing_folders': [folder_info],
            'missing_files': [file_info]
        }
        """
        nas_folders = set(nas_structure['folders'].keys())
        nas_files = set(nas_structure['files'].keys())
        
        db_folders = set(db_structure['folders'].keys())
        db_files = set(db_structure['files'].keys())
        
        # Find missing entries
        missing_folder_paths = nas_folders - db_folders
        missing_file_paths = nas_files - db_files
        
        missing_folders = [nas_structure['folders'][path] for path in missing_folder_paths]
        missing_files = [nas_structure['files'][path] for path in missing_file_paths]
        
        return {
            'missing_folders': missing_folders,
            'missing_files': missing_files
        }
    
    def remove_orphaned_entries(self, orphaned_entries: Dict, dry_run: bool = False) -> bool:
        """
        Remove orphaned database entries with proper foreign key handling
        """
        try:
            # Remove orphaned files first (to avoid foreign key issues)
            for file_record in orphaned_entries['orphaned_files']:
                if not dry_run:
                    db.session.delete(file_record)
                self.sync_stats['files_removed'] += 1
                print(f"🗑️  Removed orphaned file: {getattr(file_record, 'path', getattr(file_record, 'file_path', 'unknown'))}")
            
            # Remove orphaned folders (start with deepest first to avoid parent-child issues)
            orphaned_folders = sorted(
                orphaned_entries['orphaned_folders'], 
                key=lambda f: f.path.count('/'), 
                reverse=True
            )
            
            for folder_record in orphaned_folders:
                if not dry_run:
                    try:
                        # Step 1: Remove associated permissions first (foreign key constraint)
                        from models.folder_permission import FolderPermission
                        permissions_deleted = FolderPermission.query.filter_by(folder_id=folder_record.id).delete()
                        if permissions_deleted > 0:
                            print(f"🗑️  Removed {permissions_deleted} permission(s) for folder: {folder_record.path}")
                        
                        # Step 2: Remove any child files that might still reference this folder
                        child_files = File.query.filter_by(folder_id=folder_record.id).all()
                        for child_file in child_files:
                            db.session.delete(child_file)
                            print(f"🗑️  Removed child file: {getattr(child_file, 'path', getattr(child_file, 'file_path', 'unknown'))}")
                        
                        # Step 3: Remove the folder itself
                        db.session.delete(folder_record)
                        
                    except Exception as folder_error:
                        print(f"❌ Error removing folder {folder_record.path}: {str(folder_error)}")
                        # Continue with other folders even if one fails
                        continue
                
                self.sync_stats['folders_removed'] += 1
                print(f"🗑️  Removed orphaned folder: {folder_record.path}")
            
            if not dry_run:
                db.session.commit()
                print("✅ Database changes committed successfully")
                
            return True
            
        except Exception as e:
            if not dry_run:
                db.session.rollback()
                print("❌ Database changes rolled back due to error")
            error_msg = f"Error removing orphaned entries: {str(e)}"
            self.sync_stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
            return False
    
    def add_missing_entries(self, missing_entries: Dict, default_owner_id: int = 1, dry_run: bool = False) -> bool:
        """
        Add missing database entries for NAS items
        """
        try:
            # Add missing folders first (parents before children)
            missing_folders = sorted(
                missing_entries['missing_folders'], 
                key=lambda f: f['path'].count('/')
            )
            
            folder_id_map = {}  # path -> id mapping for new folders
            
            for folder_info in missing_folders:
                if not dry_run:
                    # Find parent folder ID
                    parent_id = None
                    if folder_info['parent_path'] and folder_info['parent_path'] != '/':
                        parent_folder = Folder.query.filter_by(path=folder_info['parent_path']).first()
                        if parent_folder:
                            parent_id = parent_folder.id
                        elif folder_info['parent_path'] in folder_id_map:
                            parent_id = folder_id_map[folder_info['parent_path']]
                    
                    # Create new folder
                    new_folder = Folder(
                        name=folder_info['name'],
                        path=folder_info['path'],
                        parent_path=folder_info['parent_path'],
                        owner_id=default_owner_id,
                        parent_id=parent_id,
                        created_at=folder_info.get('created') or datetime.now(timezone.utc),
                        updated_at=folder_info.get('modified') or datetime.now(timezone.utc)
                    )
                    
                    db.session.add(new_folder)
                    db.session.flush()  # Get the ID
                    folder_id_map[folder_info['path']] = new_folder.id
                
                self.sync_stats['folders_added'] += 1
                print(f"➕ Added missing folder: {folder_info['path']}")
            
            # Add missing files
            for file_info in missing_entries['missing_files']:
                if not dry_run:
                    # Find parent folder ID
                    folder_id = None
                    if file_info['parent_path']:
                        parent_folder = Folder.query.filter_by(path=file_info['parent_path']).first()
                        if parent_folder:
                            folder_id = parent_folder.id
                        elif file_info['parent_path'] in folder_id_map:
                            folder_id = folder_id_map[file_info['parent_path']]
                    
                    # Create new file
                    new_file = File(
                        name=file_info['name'],
                        path=file_info['path'],  # Use path field if it exists
                        size_kb=int(file_info.get('size', 0) / 1024) if file_info.get('size', 0) > 0 else 0,
                        mime_type=file_info.get('mime_type', 'application/octet-stream'),
                        owner_id=default_owner_id,
                        folder_id=folder_id,
                        created_at=file_info.get('created') or datetime.now(timezone.utc),
                        updated_at=file_info.get('modified') or datetime.now(timezone.utc)
                    )
                    
                    # Set file_path if the model has this field instead of path
                    if hasattr(new_file, 'file_path') and not hasattr(new_file, 'path'):
                        new_file.file_path = file_info['path']
                    
                    db.session.add(new_file)
                
                self.sync_stats['files_added'] += 1
                print(f"➕ Added missing file: {file_info['path']}")
            
            if not dry_run:
                db.session.commit()
                
            return True
            
        except Exception as e:
            if not dry_run:
                db.session.rollback()
            error_msg = f"Error adding missing entries: {str(e)}"
            self.sync_stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
            return False
    
    def full_sync(self, max_depth: int = 10, default_owner_id: int = 1, dry_run: bool = False) -> Dict:
        """
        Perform full synchronization between NAS and database
        """
        print("🔄 Starting NAS-Database synchronization...")
        
        # Reset stats
        self.sync_stats = {
            'folders_scanned': 0,
            'files_scanned': 0,
            'folders_added': 0,
            'files_added': 0,
            'folders_removed': 0,
            'files_removed': 0,
            'folders_updated': 0,
            'files_updated': 0,
            'errors': []
        }
        
        # Test NAS connection
        if not self.test_nas_connection():
            return {
                'success': False,
                'message': 'NAS connection failed - make sure you are connected to the work network',
                'stats': self.sync_stats,
                'nas_accessible': False
            }
        
        print("✅ connexion NAS réussie")
        
        # Scan NAS structure
        print("📂 Scanning NAS structure...")
        nas_structure = self.scan_nas_recursive("/", max_depth)
        
        # Get database structure
        print("🗄️  Reading database structure...")
        db_structure = self.get_database_structure()
        
        print(f"📊 NAS: {len(nas_structure['folders'])} folders, {len(nas_structure['files'])} files")
        print(f"📊 DB:  {len(db_structure['folders'])} folders, {len(db_structure['files'])} files")
        
        # Find discrepancies
        orphaned_entries = self.find_orphaned_entries(nas_structure, db_structure)
        missing_entries = self.find_missing_entries(nas_structure, db_structure)
        
        print(f"🗑️  Found {len(orphaned_entries['orphaned_folders'])} orphaned folders, {len(orphaned_entries['orphaned_files'])} orphaned files")
        print(f"➕ Found {len(missing_entries['missing_folders'])} missing folders, {len(missing_entries['missing_files'])} missing files")
        
        if dry_run:
            print("🔍 DRY RUN - No changes will be made")
        
        # Remove orphaned entries
        if orphaned_entries['orphaned_folders'] or orphaned_entries['orphaned_files']:
            print("🗑️  Removing orphaned database entries...")
            if not self.remove_orphaned_entries(orphaned_entries, dry_run):
                return {
                    'success': False,
                    'message': 'Failed to remove orphaned entries',
                    'stats': self.sync_stats
                }
        
        # Add missing entries
        if missing_entries['missing_folders'] or missing_entries['missing_files']:
            print("➕ Adding missing database entries...")
            if not self.add_missing_entries(missing_entries, default_owner_id, dry_run):
                return {
                    'success': False,
                    'message': 'Failed to add missing entries',
                    'stats': self.sync_stats
                }
        
        success_message = "✅ Synchronization completed successfully"
        if dry_run:
            success_message += " (DRY RUN)"
        
        print(success_message)
        print(f"📊 Final stats: +{self.sync_stats['folders_added']} folders, +{self.sync_stats['files_added']} files, -{self.sync_stats['folders_removed']} folders, -{self.sync_stats['files_removed']} files")
        
        return {
            'success': True,
            'message': success_message,
            'stats': self.sync_stats,
            'nas_structure': {
                'folders_count': len(nas_structure['folders']),
                'files_count': len(nas_structure['files'])
            },
            'db_structure': {
                'folders_count': len(db_structure['folders']),
                'files_count': len(db_structure['files'])
            }
        }
    
    def get_real_statistics(self) -> Dict:
        """
        Get real statistics from NAS (after sync)
        """
        try:
            # Get current database counts (should be synced with NAS)
            total_folders = Folder.query.count()
            total_files = File.query.count()
            
            # Get user counts
            total_users = User.query.count()
            admin_users = User.query.filter_by(role='ADMIN').count()
            simple_users = User.query.filter_by(role='SIMPLE_USER').count()
            
            # Calculate total size from files
            total_size_kb = db.session.query(db.func.sum(File.size_kb)).scalar() or 0
            total_size_bytes = total_size_kb * 1024
            
            return {
                'total_users': total_users,
                'total_groups': db.session.query(db.func.count(db.distinct(User.id))).scalar() or 0,  # Simplified
                'total_folders': total_folders,
                'total_files': total_files,
                'admin_users': admin_users,
                'simple_users': simple_users,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'nas_connected': self.test_nas_connection(),
                'last_sync': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            print(f"❌ Error getting real statistics: {str(e)}")
            return {
                'total_users': 0,
                'total_groups': 0,
                'total_folders': 0,
                'total_files': 0,
                'admin_users': 0,
                'simple_users': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'nas_connected': False,
                'last_sync': None,
                'error': str(e)
            }

# Global instance
nas_sync_service = NasSyncService()