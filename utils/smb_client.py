# utils/smb_client.py

from smb.SMBConnection import SMBConnection
from pathlib import Path
import os
import io
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from utils.nas_utils import (
    normalize_smb_path, 
    sanitize_filename, 
    format_smb_file_info,
    validate_smb_path,
    unique_filename
)

load_dotenv()

class SMBClientNAS:
    """Connexion au NAS Synology via SMB avec gestion d'erreurs robuste"""
    
    def __init__(self):
        # Configuration depuis les variables d'environnement ou valeurs par défaut du test
        self.username = os.getenv("SMB_USERNAME", "gestion")
        self.password = os.getenv("SMB_PASSWORD", "Aeronav99")  
        self.client_name = os.getenv("SMB_CLIENT_NAME", "admin")
        self.server_name = os.getenv("SMB_SERVER_NAME", "NAS_SERVER")
        self.server_ip = os.getenv("SMB_SERVER_IP", "10.61.17.33")
        self.domain = os.getenv("SMB_DOMAIN", "")
        self.share_name = os.getenv("SMB_SHARED_FOLDER", "NAS")  # Utiliser "NAS" comme dans le test
        self.port = int(os.getenv("SMB_PORT", "139"))
        
        self.conn = None
        self._connected = False
        self._connect()

    def _connect(self):
        """Établit la connexion SMB"""
        try:
            self.conn = SMBConnection(
                self.username,
                self.password,
                self.client_name,
                self.server_name,
                domain=self.domain,
                use_ntlm_v2=True
            )
            
            if self.conn.connect(self.server_ip, self.port):
                self._connected = True
                print(f"Connexion SMB réussie vers {self.server_ip}:{self.port}")
            else:
                raise Exception("Échec de connexion SMB")
                
        except Exception as e:
            self._connected = False
            print(f"Erreur connexion SMB: {str(e)}")
            raise

    def _ensure_connected(self):
        """S'assure que la connexion SMB est active"""
        if not self._connected or not self.conn:
            self._connect()

    def _reconnect_if_needed(self):
        """Reconnecte si nécessaire lors d'une erreur"""
        try:
            self._connect()
        except Exception as e:
            print(f"Échec de reconnexion: {str(e)}")
            raise

    def list_files(self, path="/"):
        """Liste les fichiers et dossiers dans un chemin"""
        self._ensure_connected()
        path = normalize_smb_path(path)
        
        if not validate_smb_path(path):
            raise ValueError(f"Chemin invalide: {path}")
        
        try:
            files = self.conn.listPath(self.share_name, path)
            result = []
            
            for file_obj in files:
                if file_obj.filename not in [".", ".."]:
                    file_info = format_smb_file_info(file_obj, path)
                    result.append(file_info)
            
            # Trier: dossiers d'abord, puis par nom
            result.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
            return result
            
        except Exception as e:
            print(f"Erreur listage {path}: {str(e)}")
            # Tentative de reconnexion
            try:
                self._reconnect_if_needed()
                files = self.conn.listPath(self.share_name, path)
                result = []
                for file_obj in files:
                    if file_obj.filename not in [".", ".."]:
                        file_info = format_smb_file_info(file_obj, path)
                        result.append(file_info)
                result.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
                return result
            except Exception as e2:
                raise Exception(f"Impossible de lister {path}: {str(e2)}")

    def upload_file(self, file_obj, dest_path, filename, overwrite=False):
        """Upload un fichier sur le NAS"""
        self._ensure_connected()
        
        dest_path = normalize_smb_path(dest_path)
        filename = sanitize_filename(filename)
        
        if not validate_smb_path(dest_path):
            raise ValueError(f"Chemin de destination invalide: {dest_path}")
        
        # Gestion des noms en conflit
        if not overwrite:
            try:
                existing_files = [f['name'] for f in self.list_files(dest_path)]
                filename = unique_filename(existing_files, filename)
            except:
                pass  # Si on ne peut pas lister, on continue
        
        full_path = f"{dest_path.rstrip('/')}/{filename}"
        full_path = normalize_smb_path(full_path)
        
        try:
            # S'assurer que file_obj est au début
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            self.conn.storeFile(self.share_name, full_path, file_obj)
            
            return {
                "success": True,
                "path": full_path,
                "name": filename,
                "message": "Fichier uploadé avec succès"
            }
            
        except Exception as e:
            print(f"Erreur upload vers {full_path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                if hasattr(file_obj, 'seek'):
                    file_obj.seek(0)
                self.conn.storeFile(self.share_name, full_path, file_obj)
                return {
                    "success": True,
                    "path": full_path,
                    "name": filename,
                    "message": "Fichier uploadé avec succès (après reconnexion)"
                }
            except Exception as e2:
                raise Exception(f"Impossible d'uploader {filename}: {str(e2)}")

    def download_file(self, file_path):
        """Télécharge un fichier depuis le NAS"""
        self._ensure_connected()
        file_path = normalize_smb_path(file_path)
        
        if not validate_smb_path(file_path):
            raise ValueError(f"Chemin de fichier invalide: {file_path}")
        
        try:
            file_obj = io.BytesIO()
            self.conn.retrieveFile(self.share_name, file_path, file_obj)
            file_obj.seek(0)
            return file_obj
            
        except Exception as e:
            print(f"Erreur téléchargement {file_path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                file_obj = io.BytesIO()
                self.conn.retrieveFile(self.share_name, file_path, file_obj)
                file_obj.seek(0)
                return file_obj
            except Exception as e2:
                raise Exception(f"Impossible de télécharger {file_path}: {str(e2)}")

    def delete_file(self, path):
        """Supprime un fichier ou dossier"""
        self._ensure_connected()
        path = normalize_smb_path(path)
        
        if not validate_smb_path(path):
            raise ValueError(f"Chemin invalide: {path}")
        
        try:
            # Vérifier si c'est un dossier ou un fichier
            info = self.conn.getAttributes(self.share_name, path)
            
            if info.isDirectory:
                # Vérifier que le dossier est vide
                try:
                    contents = self.conn.listPath(self.share_name, path)
                    # Compter les éléments (en excluant . et ..)
                    real_contents = [f for f in contents if f.filename not in [".", ".."]]
                    if real_contents:
                        raise Exception("Le dossier n'est pas vide")
                except:
                    pass  # Si on ne peut pas lister, on tente quand même
                
                self.conn.deleteDirectory(self.share_name, path)
            else:
                self.conn.deleteFiles(self.share_name, path)
            
            return {"success": True, "message": "Suppression réussie"}
            
        except Exception as e:
            print(f"Erreur suppression {path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                info = self.conn.getAttributes(self.share_name, path)
                if info.isDirectory:
                    self.conn.deleteDirectory(self.share_name, path)
                else:
                    self.conn.deleteFiles(self.share_name, path)
                return {"success": True, "message": "Suppression réussie (après reconnexion)"}
            except Exception as e2:
                raise Exception(f"Impossible de supprimer {path}: {str(e2)}")

    def delete_file_recursive(self, path):
        """Supprime un fichier ou dossier de manière récursive (pour les admins)"""
        self._ensure_connected()
        path = normalize_smb_path(path)
        
        if not validate_smb_path(path):
            raise ValueError(f"Chemin invalide: {path}")
        
        try:
            # Vérifier si c'est un dossier ou un fichier
            info = self.conn.getAttributes(self.share_name, path)
            
            if info.isDirectory:
                # Supprimer récursivement le contenu du dossier
                try:
                    contents = self.conn.listPath(self.share_name, path)
                    for item in contents:
                        if item.filename not in [".", ".."]:
                            item_path = normalize_smb_path(f"{path}/{item.filename}")
                            self.delete_file_recursive(item_path)  # Récursion
                except Exception as list_error:
                    print(f"Erreur lors du listage de {path}: {str(list_error)}")
                
                # Maintenant supprimer le dossier vide
                self.conn.deleteDirectory(self.share_name, path)
            else:
                # C'est un fichier, le supprimer directement
                self.conn.deleteFiles(self.share_name, path)
            
            return {"success": True, "message": "Suppression récursive réussie"}
            
        except Exception as e:
            print(f"Erreur suppression récursive {path}: {str(e)}")
            raise Exception(f"Impossible de supprimer récursivement {path}: {str(e)}")

    def rename_file(self, old_path, new_name):
        """Renomme un fichier ou dossier"""
        self._ensure_connected()
        old_path = normalize_smb_path(old_path)
        new_name = sanitize_filename(new_name)
        
        if not validate_smb_path(old_path):
            raise ValueError(f"Chemin source invalide: {old_path}")
        
        parent_path = "/".join(old_path.split("/")[:-1])
        if parent_path == "":
            parent_path = "/"
        
        new_path = normalize_smb_path(f"{parent_path}/{new_name}")
        
        try:
            self.conn.rename(self.share_name, old_path, new_path)
            return {
                "success": True,
                "old_path": old_path,
                "new_path": new_path,
                "message": "Renommage réussi"
            }
            
        except Exception as e:
            print(f"Erreur renommage {old_path} -> {new_name}: {str(e)}")
            try:
                self._reconnect_if_needed()
                self.conn.rename(self.share_name, old_path, new_path)
                return {
                    "success": True,
                    "old_path": old_path,
                    "new_path": new_path,
                    "message": "Renommage réussi (après reconnexion)"
                }
            except Exception as e2:
                raise Exception(f"Impossible de renommer {old_path}: {str(e2)}")

    def move_file(self, source_path, dest_path):
        """Déplace un fichier ou dossier"""
        self._ensure_connected()
        source_path = normalize_smb_path(source_path)
        dest_path = normalize_smb_path(dest_path)
        
        if not validate_smb_path(source_path) or not validate_smb_path(dest_path):
            raise ValueError("Chemin source ou destination invalide")
        
        filename = source_path.split("/")[-1]
        new_path = normalize_smb_path(f"{dest_path.rstrip('/')}/{filename}")
        
        try:
            self.conn.rename(self.share_name, source_path, new_path)
            return {
                "success": True,
                "source_path": source_path,
                "new_path": new_path,
                "message": "Déplacement réussi"
            }
            
        except Exception as e:
            print(f"Erreur déplacement {source_path} -> {dest_path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                self.conn.rename(self.share_name, source_path, new_path)
                return {
                    "success": True,
                    "source_path": source_path,
                    "new_path": new_path,
                    "message": "Déplacement réussi (après reconnexion)"
                }
            except Exception as e2:
                raise Exception(f"Impossible de déplacer {source_path}: {str(e2)}")

    def create_folder(self, path, folder_name):
        """Crée un nouveau dossier"""
        self._ensure_connected()
        path = normalize_smb_path(path)
        folder_name = sanitize_filename(folder_name)
        
        if not validate_smb_path(path):
            raise ValueError(f"Chemin parent invalide: {path}")
        
        folder_path = normalize_smb_path(f"{path.rstrip('/')}/{folder_name}")
        
        try:
            self.conn.createDirectory(self.share_name, folder_path)
            return {
                "success": True,
                "path": folder_path,
                "name": folder_name,
                "message": "Dossier créé avec succès"
            }
            
        except Exception as e:
            print(f"Erreur création dossier {folder_path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                self.conn.createDirectory(self.share_name, folder_path)
                return {
                    "success": True,
                    "path": folder_path,
                    "name": folder_name,
                    "message": "Dossier créé avec succès (après reconnexion)"
                }
            except Exception as e2:
                raise Exception(f"Impossible de créer le dossier {folder_name}: {str(e2)}")

    def get_file_info(self, file_path):
        """Obtient les informations d'un fichier"""
        self._ensure_connected()
        file_path = normalize_smb_path(file_path)
        
        if not validate_smb_path(file_path):
            raise ValueError(f"Chemin invalide: {file_path}")
        
        try:
            file_attrs = self.conn.getAttributes(self.share_name, file_path)
            
            return {
                'name': file_path.split('/')[-1],
                'path': file_path,
                'is_directory': file_attrs.isDirectory,
                'size': file_attrs.file_size if not file_attrs.isDirectory else None,
                'modified': datetime.fromtimestamp(file_attrs.last_write_time) if hasattr(file_attrs, 'last_write_time') else None,
                'created': datetime.fromtimestamp(file_attrs.create_time) if hasattr(file_attrs, 'create_time') else None,
                'is_readonly': file_attrs.isReadonly if hasattr(file_attrs, 'isReadonly') else False,
                'is_hidden': file_attrs.isHidden if hasattr(file_attrs, 'isHidden') else False
            }
            
        except Exception as e:
            print(f"Erreur récupération infos {file_path}: {str(e)}")
            try:
                self._reconnect_if_needed()
                file_attrs = self.conn.getAttributes(self.share_name, file_path)
                return {
                    'name': file_path.split('/')[-1],
                    'path': file_path,
                    'is_directory': file_attrs.isDirectory,
                    'size': file_attrs.file_size if not file_attrs.isDirectory else None,
                    'modified': datetime.fromtimestamp(file_attrs.last_write_time) if hasattr(file_attrs, 'last_write_time') else None,
                    'created': datetime.fromtimestamp(file_attrs.create_time) if hasattr(file_attrs, 'create_time') else None
                }
            except Exception as e2:
                raise Exception(f"Impossible d'obtenir les infos de {file_path}: {str(e2)}")

    def path_exists(self, path):
        """Vérifie si un chemin existe"""
        try:
            path = normalize_smb_path(path)
            self.conn.getAttributes(self.share_name, path)
            return True
        except:
            return False

    def test_connection(self):
        """Teste la connexion SMB"""
        try:
            self._ensure_connected()
            # Essayer de lister la racine
            files = self.list_files("/")
            return {
                "success": True,
                "message": "Connexion SMB fonctionnelle",
                "root_files_count": len(files),
                "server_info": {
                    "ip": self.server_ip,
                    "port": self.port,
                    "share": self.share_name,
                    "username": self.username
                }
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec test connexion: {str(e)}",
                "error": str(e)
            }

    def close_connection(self):
        """Ferme la connexion SMB"""
        if self.conn and self._connected:
            try:
                self.conn.close()
                self._connected = False
                print("Connexion SMB fermée")
            except Exception as e:
                print(f"Erreur fermeture connexion: {str(e)}")

    def __del__(self):
        """Destructeur pour fermer automatiquement la connexion"""
        self.close_connection()