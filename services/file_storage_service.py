# services/file_storage_service.py
import os
import shutil
import mimetypes
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

class FileStorageService:
    def __init__(self, base_path: str = None):
        """
        Service de gestion des fichiers sur disque local
        
        Args:
            base_path: Chemin racine pour stocker les fichiers
        """
        self.base_path = Path(base_path or current_app.config.get('UPLOAD_FOLDER', 'storage'))
        self.base_path.mkdir(parents=True, exist_ok=True)
        
    def get_user_root_path(self, user_id: int) -> Path:
        """Retourne le chemin racine d'un utilisateur"""
        user_path = self.base_path / f"user_{user_id}"
        user_path.mkdir(parents=True, exist_ok=True)
        return user_path
    
    def get_folder_physical_path(self, folder_id: int, user_id: int) -> Path:
        """
        Construit le chemin physique d'un dossier basé sur sa hiérarchie en DB
        """
        from models.folder import Folder
        
        folder = Folder.query.get(folder_id)
        if not folder:
            raise FileNotFoundError(f"Folder {folder_id} not found")
        
        # Construire le chemin à partir de la hiérarchie
        path_parts = []
        current_folder = folder
        
        while current_folder:
            path_parts.append(secure_filename(current_folder.name))
            if current_folder.parent_id:
                current_folder = Folder.query.get(current_folder.parent_id)
            else:
                break
        
        path_parts.reverse()
        
        # Construire le chemin complet
        user_root = self.get_user_root_path(user_id)
        folder_path = user_root
        
        for part in path_parts:
            folder_path = folder_path / part
            
        return folder_path
    
    def create_folder(self, folder_id: int, user_id: int) -> bool:
        """Crée physiquement un dossier sur le disque"""
        try:
            folder_path = self.get_folder_physical_path(folder_id, user_id)
            folder_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            current_app.logger.error(f"Error creating folder {folder_id}: {str(e)}")
            return False
    
    def delete_folder(self, folder_id: int, user_id: int) -> bool:
        """Supprime physiquement un dossier du disque"""
        try:
            folder_path = self.get_folder_physical_path(folder_id, user_id)
            if folder_path.exists():
                shutil.rmtree(folder_path)
            return True
        except Exception as e:
            current_app.logger.error(f"Error deleting folder {folder_id}: {str(e)}")
            return False
    
    def rename_folder(self, folder_id: int, user_id: int, old_name: str, new_name: str) -> bool:
        """Renomme physiquement un dossier"""
        try:
            # Reconstruire le chemin avec l'ancien nom
            from models.folder import Folder
            folder = Folder.query.get(folder_id)
            
            # Chemin parent
            if folder.parent_id:
                parent_path = self.get_folder_physical_path(folder.parent_id, user_id)
            else:
                parent_path = self.get_user_root_path(user_id)
            
            old_path = parent_path / secure_filename(old_name)
            new_path = parent_path / secure_filename(new_name)
            
            if old_path.exists():
                old_path.rename(new_path)
            
            return True
        except Exception as e:
            current_app.logger.error(f"Error renaming folder {folder_id}: {str(e)}")
            return False
    
    def save_file(self, file, folder_id: int, user_id: int, custom_filename: str = None) -> Tuple[str, str]:
        """
        Sauvegarde un fichier sur le disque
        
        Returns:
            Tuple[filename, filepath] - nom du fichier et chemin relatif
        """
        try:
            # Générer un nom unique si nécessaire
            original_filename = secure_filename(file.filename)
            if custom_filename:
                filename = secure_filename(custom_filename)
                # Garder l'extension originale si elle n'est pas dans le nom custom
                if '.' not in filename:
                    ext = Path(original_filename).suffix
                    filename = f"{filename}{ext}"
            else:
                # Ajouter un UUID pour éviter les conflits
                name_part = Path(original_filename).stem
                ext_part = Path(original_filename).suffix
                filename = f"{name_part}_{uuid.uuid4().hex[:8]}{ext_part}"
            
            # Déterminer le dossier de destination
            if folder_id:
                folder_path = self.get_folder_physical_path(folder_id, user_id)
            else:
                folder_path = self.get_user_root_path(user_id)
            
            folder_path.mkdir(parents=True, exist_ok=True)
            
            # Chemin complet du fichier
            file_path = folder_path / filename
            
            # Sauvegarder le fichier
            file.save(str(file_path))
            
            # Retourner le chemin relatif depuis la racine utilisateur
            user_root = self.get_user_root_path(user_id)
            relative_path = str(file_path.relative_to(user_root))
            
            return filename, relative_path
            
        except Exception as e:
            current_app.logger.error(f"Error saving file: {str(e)}")
            raise
    
    def delete_file(self, filepath: str, user_id: int) -> bool:
        """Supprime un fichier du disque"""
        try:
            user_root = self.get_user_root_path(user_id)
            full_path = user_root / filepath
            
            if full_path.exists() and full_path.is_file():
                full_path.unlink()
                return True
            return False
        except Exception as e:
            current_app.logger.error(f"Error deleting file {filepath}: {str(e)}")
            return False
    
    def move_file(self, old_filepath: str, new_folder_id: int, user_id: int) -> str:
        """Déplace un fichier vers un autre dossier"""
        try:
            user_root = self.get_user_root_path(user_id)
            old_path = user_root / old_filepath
            
            if not old_path.exists():
                raise FileNotFoundError(f"File not found: {old_filepath}")
            
            # Nouveau dossier de destination
            if new_folder_id:
                new_folder_path = self.get_folder_physical_path(new_folder_id, user_id)
            else:
                new_folder_path = user_root
            
            new_folder_path.mkdir(parents=True, exist_ok=True)
            
            # Nouveau chemin complet
            filename = old_path.name
            new_path = new_folder_path / filename
            
            # Déplacer le fichier
            shutil.move(str(old_path), str(new_path))
            
            # Retourner le nouveau chemin relatif
            return str(new_path.relative_to(user_root))
            
        except Exception as e:
            current_app.logger.error(f"Error moving file {old_filepath}: {str(e)}")
            raise
    
    def get_file_info(self, filepath: str, user_id: int) -> Optional[Dict]:
        """Retourne les informations d'un fichier"""
        try:
            user_root = self.get_user_root_path(user_id)
            full_path = user_root / filepath
            
            if not full_path.exists():
                return None
            
            stat = full_path.stat()
            
            return {
                'name': full_path.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'created': datetime.fromtimestamp(stat.st_ctime),
                'mime_type': mimetypes.guess_type(str(full_path))[0],
                'extension': full_path.suffix,
                'is_file': full_path.is_file(),
                'is_dir': full_path.is_dir()
            }
        except Exception as e:
            current_app.logger.error(f"Error getting file info {filepath}: {str(e)}")
            return None
    
    def get_file_stream(self, filepath: str, user_id: int):
        """Retourne un stream du fichier pour téléchargement"""
        user_root = self.get_user_root_path(user_id)
        full_path = user_root / filepath
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        return open(full_path, 'rb')
    
    def get_directory_size(self, folder_id: int, user_id: int) -> int:
        """Calcule la taille totale d'un dossier"""
        try:
            folder_path = self.get_folder_physical_path(folder_id, user_id)
            
            total_size = 0
            for path in folder_path.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
            
            return total_size
        except Exception as e:
            current_app.logger.error(f"Error calculating directory size {folder_id}: {str(e)}")
            return 0
    
    def cleanup_orphaned_files(self, user_id: int):
        """Nettoie les fichiers orphelins (présents sur disque mais pas en DB)"""
        try:
            from models.file import File
            
            user_root = self.get_user_root_path(user_id)
            db_files = set()
            
            # Récupérer tous les fichiers de l'utilisateur en DB
            user_files = File.query.filter_by(owner_id=user_id).all()
            for file in user_files:
                if file.filepath:
                    db_files.add(file.filepath)
            
            # Parcourir les fichiers sur disque
            orphaned_files = []
            for path in user_root.rglob('*'):
                if path.is_file():
                    relative_path = str(path.relative_to(user_root))
                    if relative_path not in db_files:
                        orphaned_files.append(path)
            
            # Supprimer les fichiers orphelins
            for orphaned_file in orphaned_files:
                try:
                    orphaned_file.unlink()
                    current_app.logger.info(f"Deleted orphaned file: {orphaned_file}")
                except Exception as e:
                    current_app.logger.error(f"Error deleting orphaned file {orphaned_file}: {e}")
            
            return len(orphaned_files)
            
        except Exception as e:
            current_app.logger.error(f"Error during cleanup for user {user_id}: {str(e)}")
            return 0