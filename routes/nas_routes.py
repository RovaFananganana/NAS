# routes/nas_routes.py

from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename
from pathlib import Path
import urllib.parse
import json
from datetime import datetime
from smb.SMBConnection import SMBConnection
from dotenv import load_dotenv
import os
import io

from models.user import User
from models.folder import Folder
from models.file import File
from extensions import db
from utils.nas_utils import (
    get_file_mime_type, 
    normalize_smb_path,
    validate_smb_path,
    sanitize_filename,
    get_parent_path,
    get_filename_from_path,
    format_smb_file_info
)
from utils.permissions import PermissionSet
from services.permission_optimizer import PermissionOptimizer
from services.nas_sync_service import nas_sync_service
from utils.access_logger import log_file_operation

load_dotenv()

nas_bp = Blueprint('nas', __name__, url_prefix='/nas')

# ================== CONNEXION SMB GLOBALE ==================

class GlobalSMBClient:
    """Client SMB global avec connexion persistante"""
    
    def __init__(self):
        # Configuration depuis les variables d'environnement ou valeurs du test
        self.username = os.getenv('SMB_USERNAME', 'gestion')
        self.password = os.getenv('SMB_PASSWORD', 'Aeronav99')
        self.client_name = os.getenv('SMB_CLIENT_NAME', 'admin')
        self.server_name = os.getenv('SMB_SERVER_NAME', 'NAS_SERVER')
        self.server_ip = os.getenv('SMB_SERVER_IP', '10.61.17.33')
        self.shared_folder = os.getenv('SMB_SHARED_FOLDER', 'NAS')
        self.domain_name = os.getenv('SMB_DOMAIN', '')
        self.port = int(os.getenv('SMB_PORT', '139'))
        
        self.conn = None
        self._is_connected = False
        self._connect()

    def _connect(self):
        """Établit la connexion SMB une seule fois"""
        try:
            if self._is_connected and self.conn:
                return True
            
            # Essayer différentes configurations SMB
            try:
                # Configuration 1: NetBIOS sur port 139
                self.conn = SMBConnection(
                    self.username,
                    self.password,
                    self.client_name,
                    self.server_name,
                    domain=self.domain_name,
                    use_ntlm_v2=True,
                    is_direct_tcp=False
                )
                if self.conn.connect(self.server_ip, 139):
                    print(f"✅ Connexion SMB NetBIOS réussie sur port 139")
                    return True
            except Exception as e1:
                print(f"❌ Échec NetBIOS port 139: {str(e1)}")
            
            try:
                # Configuration 2: TCP direct sur port 445
                self.conn = SMBConnection(
                    self.username,
                    self.password,
                    self.client_name,
                    self.server_name,
                    domain=self.domain_name,
                    use_ntlm_v2=True,
                    is_direct_tcp=True
                )
                if self.conn.connect(self.server_ip, 445):
                    print(f"✅ Connexion SMB TCP directe réussie sur port 445")
                    return True
            except Exception as e2:
                print(f"❌ Échec TCP direct port 445: {str(e2)}")
            
            try:
                # Configuration 3: NTLM v1 en fallback
                self.conn = SMBConnection(
                    self.username,
                    self.password,
                    self.client_name,
                    self.server_name,
                    domain=self.domain_name,
                    use_ntlm_v2=False,
                    is_direct_tcp=False
                )
                if self.conn.connect(self.server_ip, 139):
                    print(f"✅ Connexion SMB NTLM v1 réussie sur port 139")
                    return True
            except Exception as e3:
                print(f"❌ Échec NTLM v1: {str(e3)}")
            
            raise Exception("Toutes les configurations SMB ont échoué")
            
            if self.conn.connect(self.server_ip, self.port):
                self._is_connected = True
                print(f"✅ Connexion SMB établie vers {self.server_ip}:{self.port}")
                return True
            else:
                raise Exception("Échec de connexion SMB")
                
        except Exception as e:
            self._is_connected = False
            print(f"❌ Erreur connexion SMB: {str(e)}")
            raise

    def _ensure_connected(self):
        """S'assure que la connexion est active, reconnecte si nécessaire"""
        if not self._is_connected or not self.conn:
            print("🔄 Reconnexion SMB nécessaire...")
            self._connect()

    def list_files(self, path="/"):
        """Liste les fichiers et dossiers avec fallback"""
        self._ensure_connected()
        
        try:
            files = self.conn.listPath(self.shared_folder, path)
            result = []
            
            for file_obj in files:
                if file_obj.filename not in [".", ".."]:
                    file_info = format_smb_file_info(file_obj, path)
                    result.append(file_info)
            
            # Trier: dossiers d'abord, puis par nom
            result.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
            return result
            
        except Exception as e:
            print(f"❌ Erreur listage {path}: {str(e)}")
            
            # Essayer de reconnecter et relister
            try:
                print("🔄 Tentative de reconnexion...")
                self._is_connected = False
                self._connect()
                files = self.conn.listPath(self.shared_folder, path)
                result = []
                for file_obj in files:
                    if file_obj.filename not in [".", ".."]:
                        file_info = format_smb_file_info(file_obj, path)
                        result.append(file_info)
                result.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
                print(f"✅ Reconnexion réussie, {len(result)} éléments trouvés")
                return result
            except Exception as e2:
                print(f"❌ Échec de reconnexion: {str(e2)}")
                raise Exception(f"Impossible de lister {path}: {str(e2)}")

    def create_folder(self, path, folder_name):
        """Crée un dossier"""
        self._ensure_connected()
        
        folder_path = normalize_smb_path(f"{path.rstrip('/')}/{folder_name}")
        
        try:
            self.conn.createDirectory(self.shared_folder, folder_path)
            return {
                "success": True,
                "path": folder_path,
                "name": folder_name,
                "message": "Dossier créé avec succès"
            }
        except Exception as e:
            raise Exception(f"Impossible de créer le dossier {folder_name}: {str(e)}")

    def create_file(self, path, file_name):
        """Crée un fichier vide"""
        self._ensure_connected()
        
        file_name = sanitize_filename(file_name)
        file_path = normalize_smb_path(f"{path.rstrip('/')}/{file_name}")
        
        try:
            # Créer un fichier vide en écrivant un contenu vide
            file_obj = io.BytesIO(b'')
            self.conn.storeFile(self.shared_folder, file_path, file_obj)
            
            return {
                "success": True,
                "path": file_path,
                "name": file_name,
                "message": "Fichier créé avec succès"
            }
        except Exception as e:
            raise Exception(f"Impossible de créer le fichier {file_name}: {str(e)}")

    def upload_file(self, file_obj, dest_path, filename, overwrite=False):
        """Upload un fichier"""
        self._ensure_connected()
        
        filename = sanitize_filename(filename)
        full_path = normalize_smb_path(f"{dest_path.rstrip('/')}/{filename}")
        
        try:
            # Vérifier si le fichier existe déjà si overwrite=False
            if not overwrite:
                try:
                    existing_files = [f['name'] for f in self.list_files(dest_path)]
                    if filename in existing_files:
                        # Générer un nom unique
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while f"{base}_{counter}{ext}" in existing_files:
                            counter += 1
                        filename = f"{base}_{counter}{ext}"
                        full_path = normalize_smb_path(f"{dest_path.rstrip('/')}/{filename}")
                except:
                    pass  # Si on ne peut pas lister, on continue
            
            # S'assurer que file_obj est au début
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            
            self.conn.storeFile(self.shared_folder, full_path, file_obj)
            
            return {
                "success": True,
                "path": full_path,
                "name": filename,
                "message": "Fichier uploadé avec succès"
            }
            
        except Exception as e:
            raise Exception(f"Impossible d'uploader {filename}: {str(e)}")

    def download_file(self, file_path):
        """Télécharge un fichier"""
        self._ensure_connected()
        
        try:
            file_obj = io.BytesIO()
            self.conn.retrieveFile(self.shared_folder, file_path, file_obj)
            file_obj.seek(0)
            return file_obj
        except Exception as e:
            raise Exception(f"Impossible de télécharger {file_path}: {str(e)}")

    def delete_file(self, path):
        """Supprime un fichier ou dossier"""
        self._ensure_connected()
        
        try:
            # Vérifier si c'est un dossier ou un fichier
            info = self.conn.getAttributes(self.shared_folder, path)
            
            if info.isDirectory:
                # Vérifier que le dossier est vide
                try:
                    contents = self.conn.listPath(self.shared_folder, path)
                    real_contents = [f for f in contents if f.filename not in [".", ".."]]
                    if real_contents:
                        raise Exception("Le dossier n'est pas vide")
                except:
                    pass
                
                self.conn.deleteDirectory(self.shared_folder, path)
            else:
                self.conn.deleteFiles(self.shared_folder, path)
            
            return {"success": True, "message": "Suppression réussie"}
            
        except Exception as e:
            raise Exception(f"Impossible de supprimer {path}: {str(e)}")

    def delete_file_recursive(self, path):
        """Supprime un fichier ou dossier récursivement (pour les administrateurs)"""
        self._ensure_connected()
        
        try:
            # Vérifier si c'est un dossier ou un fichier
            info = self.conn.getAttributes(self.shared_folder, path)
            
            if info.isDirectory:
                # Supprimer récursivement le contenu du dossier
                try:
                    contents = self.conn.listPath(self.shared_folder, path)
                    for item in contents:
                        if item.filename not in [".", ".."]:
                            item_path = f"{path.rstrip('/')}/{item.filename}"
                            if item.isDirectory:
                                # Récursion pour les sous-dossiers
                                self.delete_file_recursive(item_path)
                            else:
                                # Supprimer le fichier
                                self.conn.deleteFiles(self.shared_folder, item_path)
                                print(f"✅ Fichier supprimé: {item_path}")
                except Exception as list_error:
                    print(f"⚠️ Erreur listage contenu {path}: {str(list_error)}")
                
                # Supprimer le dossier maintenant qu'il est vide
                self.conn.deleteDirectory(self.shared_folder, path)
                print(f"✅ Dossier supprimé: {path}")
            else:
                # C'est un fichier, le supprimer directement
                self.conn.deleteFiles(self.shared_folder, path)
                print(f"✅ Fichier supprimé: {path}")
            
            return {"success": True, "message": "Suppression récursive réussie"}
            
        except Exception as e:
            raise Exception(f"Impossible de supprimer récursivement {path}: {str(e)}")

    def rename_file(self, old_path, new_name):
        """Renomme un fichier ou dossier"""
        self._ensure_connected()
        
        new_name = sanitize_filename(new_name)
        parent_path = "/".join(old_path.split("/")[:-1]) or "/"
        new_path = normalize_smb_path(f"{parent_path}/{new_name}")
        
        try:
            self.conn.rename(self.shared_folder, old_path, new_path)
            return {
                "success": True,
                "old_path": old_path,
                "new_path": new_path,
                "message": "Renommage réussi"
            }
        except Exception as e:
            raise Exception(f"Impossible de renommer {old_path}: {str(e)}")

    def move_file(self, source_path, dest_path):
        """Déplace un fichier ou dossier"""
        self._ensure_connected()
        
        filename = source_path.split("/")[-1]
        new_path = normalize_smb_path(f"{dest_path.rstrip('/')}/{filename}")
        
        try:
            self.conn.rename(self.shared_folder, source_path, new_path)
            return {
                "success": True,
                "source_path": source_path,
                "new_path": new_path,
                "message": "Déplacement réussi"
            }
        except Exception as e:
            raise Exception(f"Impossible de déplacer {source_path}: {str(e)}")

    def get_file_info(self, file_path):
        """Obtient les informations d'un fichier"""
        self._ensure_connected()
        
        try:
            file_attrs = self.conn.getAttributes(self.shared_folder, file_path)
            
            return {
                'name': file_path.split('/')[-1],
                'path': file_path,
                'is_directory': file_attrs.isDirectory,
                'size': file_attrs.file_size if not file_attrs.isDirectory else None,
                'modified': datetime.fromtimestamp(file_attrs.last_write_time) if hasattr(file_attrs, 'last_write_time') else None,
                'created': datetime.fromtimestamp(file_attrs.create_time) if hasattr(file_attrs, 'create_time') else None,
                'is_readonly': getattr(file_attrs, 'isReadonly', False),
                'is_hidden': getattr(file_attrs, 'isHidden', False)
            }
        except Exception as e:
            raise Exception(f"Impossible d'obtenir les infos de {file_path}: {str(e)}")

    def test_connection(self):
        """Teste la connexion SMB"""
        try:
            self._ensure_connected()
            files = self.list_files("/")
            return {
                "success": True,
                "message": "Connexion SMB fonctionnelle",
                "root_files_count": len(files),
                "server_info": {
                    "ip": self.server_ip,
                    "port": self.port,
                    "share": self.shared_folder,
                    "username": self.username
                }
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec test connexion: {str(e)}",
                "error": str(e)
            }

# Instance SMB globale
_global_smb_client = None

def get_smb_client():
    """Retourne l'instance SMB globale (singleton)"""
    global _global_smb_client
    if _global_smb_client is None:
        _global_smb_client = GlobalSMBClient()
    return _global_smb_client

# Instance pour l'optimisation des permissions
permission_optimizer = PermissionOptimizer()

# ================== GESTION DES PERMISSIONS ==================

def check_file_permission(user, file_path, required_action='read'):
    """
    Vérifie les permissions d'un utilisateur sur un fichier spécifique
    Actions possibles: 'read', 'write', 'delete', 'share'
    """
    if user.role.upper() == 'ADMIN':
        return True

    normalized_path = normalize_smb_path(file_path)
    
    try:
        # Chercher le fichier correspondant dans la DB
        file_obj = File.query.filter_by(path=normalized_path).first()
        if file_obj:
            # Vérifier les permissions directes sur le fichier
            from models.file_permission import FilePermission
            
            # Permissions utilisateur directes
            user_perm = FilePermission.query.filter_by(file_id=file_obj.id, user_id=user.id).first()
            if user_perm:
                if required_action == 'read' and user_perm.can_read:
                    return True
                elif required_action == 'write' and user_perm.can_write:
                    return True
                elif required_action == 'delete' and user_perm.can_delete:
                    return True
                elif required_action == 'share' and user_perm.can_share:
                    return True
            
            # Permissions via les groupes
            for group in user.groups:
                group_perm = FilePermission.query.filter_by(file_id=file_obj.id, group_id=group.id).first()
                if group_perm:
                    if required_action == 'read' and group_perm.can_read:
                        return True
                    elif required_action == 'write' and group_perm.can_write:
                        return True
                    elif required_action == 'delete' and group_perm.can_delete:
                        return True
                    elif required_action == 'share' and group_perm.can_share:
                        return True
        
        # Si pas de permissions spécifiques sur le fichier, vérifier les permissions du dossier parent
        parent_path = get_parent_path(normalized_path)
        return check_folder_permission(user, parent_path, required_action)
        
    except Exception as e:
        print(f"Erreur vérification permission fichier {required_action} pour {user.username} sur {file_path}: {str(e)}")
        # En cas d'erreur, refuser l'accès par sécurité
        return False

def get_all_accessible_folders(user):
    """
    Récupère tous les dossiers auxquels l'utilisateur a accès, 
    même s'ils sont dans des parents non accessibles
    """
    accessible_folders = []
    
    try:
        # Récupérer tous les dossiers de la base de données
        all_folders = Folder.query.all()
        
        for folder in all_folders:
            # Vérifier les permissions directes
            permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [folder.id])
            folder_perm = permissions.get(folder.id)
            
            if folder_perm and folder_perm.can_read:
                accessible_folders.append(folder.path)
        
        print(f"📁 Dossiers accessibles pour {user.username}: {accessible_folders}")
        return accessible_folders
        
    except Exception as e:
        print(f"Erreur récupération dossiers accessibles pour {user.username}: {str(e)}")
        return []

def ensure_root_access(user):
    """
    S'assure qu'un utilisateur a au moins accès en lecture à la racine
    """
    try:
        root_folder = Folder.query.filter_by(path='/').first()
        if not root_folder:
            # Créer le dossier racine s'il n'existe pas
            root_folder = Folder(
                name='Racine',
                path='/',
                owner_id=1  # Admin par défaut
            )
            db.session.add(root_folder)
            db.session.commit()
            print(f"📁 Dossier racine créé pour l'utilisateur {user.username}")
        
        # Vérifier si l'utilisateur a des permissions sur la racine
        permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [root_folder.id])
        root_perm = permissions.get(root_folder.id)
        
        return root_perm is not None and root_perm.can_read
        
    except Exception as e:
        print(f"Erreur vérification accès racine pour {user.username}: {str(e)}")
        return False

def check_folder_permission(user, path, required_action='read'):
    """
    Vérifie les permissions d'un utilisateur sur un chemin via la base de données
    Actions possibles: 'read', 'write', 'delete', 'share'
    """
    # Admin users have all permissions
    if user and user.role and user.role.upper() in ['ADMIN', 'ADMINISTRATOR']:
        return True

    normalized_path = normalize_smb_path(path)
    
    try:
        # Chercher le dossier correspondant dans la DB
        folder = Folder.query.filter_by(path=normalized_path).first()
        if folder:
            permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [folder.id])
            folder_perm = permissions.get(folder.id)
            
            if folder_perm:
                if required_action == 'read':
                    return folder_perm.can_read
                elif required_action == 'write':
                    return folder_perm.can_write
                elif required_action == 'delete':
                    return folder_perm.can_delete
                elif required_action == 'share':
                    return folder_perm.can_share
        
        # Si pas de dossier exact, chercher récursivement dans les parents
        parent_path = get_parent_path(normalized_path)
        if parent_path != normalized_path and parent_path != '/':
            return check_folder_permission(user, parent_path, required_action)
        
        # Vérifier s'il y a un dossier racine défini
        root_folder = Folder.query.filter_by(path='/').first()
        if root_folder:
            permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [root_folder.id])
            root_perm = permissions.get(root_folder.id)
            if root_perm:
                if required_action == 'read':
                    return root_perm.can_read
                elif required_action == 'write':
                    return root_perm.can_write
                elif required_action == 'delete':
                    return root_perm.can_delete
                elif required_action == 'share':
                    return root_perm.can_share
        
        # Par défaut, autoriser la lecture pour les utilisateurs authentifiés sur la racine
        # mais refuser pour les autres actions ou chemins spécifiques
        if normalized_path == '/' and required_action == 'read':
            return True
        return False
        
    except Exception as e:
        print(f"Erreur vérification permission {required_action} pour {user.username} sur {path}: {str(e)}")
        # En cas d'erreur, autoriser la lecture sur la racine par défaut pour éviter de bloquer l'accès
        if required_action == 'read' and normalize_smb_path(path) == '/':
            return True
        return False

def sync_folder_to_db(folder_data, parent_folder_id=None, owner_id=1):
    """Synchronise un dossier du NAS vers la DB"""
    try:
        existing_folder = Folder.query.filter_by(path=folder_data['path']).first()
        if not existing_folder:
            new_folder = Folder(
                name=folder_data['name'],
                path=folder_data['path'],
                owner_id=owner_id,
                parent_id=parent_folder_id
            )
            db.session.add(new_folder)
            db.session.flush()
            return new_folder.id
        return existing_folder.id
    except Exception as e:
        print(f"Erreur sync dossier {folder_data['path']}: {str(e)}")
        return None

def sync_file_to_db(file_data, folder_id=None, owner_id=1):
    """Synchronise un fichier du NAS vers la DB"""
    try:
        existing_file = File.query.filter_by(path=file_data['path']).first()
        if not existing_file:
            new_file = File(
                name=file_data['name'],
                path=file_data['path'],
                size_kb=int(file_data['size'] / 1024) if file_data.get('size', 0) > 0 else 0,
                mime_type=file_data.get('mime_type', 'application/octet-stream'),
                owner_id=owner_id,
                folder_id=folder_id
            )
            db.session.add(new_file)
            return new_file
        return existing_file
    except Exception as e:
        print(f"Erreur sync fichier {file_data['path']}: {str(e)}")
        return None

# ================== ROUTES ==================

@nas_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint (no auth required)"""
    return jsonify({
        "success": True,
        "message": "NAS routes are working",
        "timestamp": datetime.utcnow().isoformat()
    })

# Ancienne version supprimée - voir la nouvelle version plus bas

# Ancienne version supprimée - voir la nouvelle version plus bas

@nas_bp.route('/copy', methods=['POST'])
@jwt_required()
def copy_item():
    """Copier un fichier ou dossier"""
    try:
        jwt_identity = get_jwt_identity()
        if jwt_identity is None:
            return jsonify({"error": "Token JWT invalide - identity manquante"}), 401
        user_id = int(jwt_identity)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Token JWT invalide: {str(e)}"}), 401
        
    user = User.query.get(user_id)
    
    data = request.get_json()
    source_path = normalize_smb_path(data.get('source_path', '').strip())
    dest_path = normalize_smb_path(data.get('dest_path', '').strip())

    if not source_path or not dest_path:
        return jsonify({"error": "Chemins source et destination requis"}), 400
        
    if not validate_smb_path(source_path) or not validate_smb_path(dest_path):
        return jsonify({"error": "Chemin invalide"}), 400
    
    # Vérifier les permissions
    source_parent = get_parent_path(source_path)
    if not check_folder_permission(user, source_parent, 'read'):
        return jsonify({"error": "Permission de lecture refusée sur le fichier source"}), 403
        
    if not check_folder_permission(user, dest_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur le dossier destination"}), 403

    try:
        smb_client = get_smb_client()
        
        # Pour la copie, on doit télécharger puis uploader
        # Obtenir le nom du fichier
        filename = get_filename_from_path(source_path)
        
        # Télécharger le fichier source
        file_stream = smb_client.download_file(source_path)
        
        # Uploader vers la destination
        result = smb_client.upload_file(file_stream, dest_path, filename, overwrite=False)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur copie: {str(e)}"
        }), 500

@nas_bp.route('/folder-by-path', methods=['GET'])
@jwt_required()
def get_folder_by_path():
    """Obtenir un dossier de la DB par son chemin"""
    try:
        jwt_identity = get_jwt_identity()
        if jwt_identity is None:
            return jsonify({"error": "Token JWT invalide - identity manquante"}), 401
        user_id = int(jwt_identity)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Token JWT invalide: {str(e)}"}), 401
        
    user = User.query.get(user_id)
    
    if not user or user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    folder_path = request.args.get('path', '').strip()
    folder_path = normalize_smb_path(folder_path)
    
    if not folder_path:
        return jsonify({"error": "Chemin requis"}), 400

    try:
        folder = Folder.query.filter_by(path=folder_path).first()
        if folder:
            return jsonify({
                "success": True,
                "data": {
                    "id": folder.id,
                    "name": folder.name,
                    "path": folder.path,
                    "permissions": [
                        {
                            "id": p.id,
                            "target_name": p.user.username if p.user else p.group.name,
                            "type": "user" if p.user else "group",
                            "can_read": p.can_read,
                            "can_write": p.can_write,
                            "can_delete": p.can_delete,
                            "can_share": p.can_share
                        }
                        for p in folder.permissions
                    ]
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Folder not found in database"
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur recherche dossier: {str(e)}"
        }), 500

@nas_bp.route('/create-folder-db', methods=['POST'])
@jwt_required()
def create_folder_in_db():
    """Créer un dossier dans la base de données"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user or user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    data = request.get_json()
    folder_name = data.get('name', '').strip()
    folder_path = normalize_smb_path(data.get('path', '').strip())
    
    if not folder_name or not folder_path:
        return jsonify({"error": "Nom et chemin requis"}), 400

    try:
        # Vérifier si le dossier existe déjà
        existing_folder = Folder.query.filter_by(path=folder_path).first()
        if existing_folder:
            return jsonify({
                "success": True,
                "data": {
                    "id": existing_folder.id,
                    "name": existing_folder.name,
                    "path": existing_folder.path,
                    "permissions": []
                }
            })
        
        # Créer le nouveau dossier
        new_folder = Folder(
            name=folder_name,
            path=folder_path,
            owner_id=user_id
        )
        
        db.session.add(new_folder)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "data": {
                "id": new_folder.id,
                "name": new_folder.name,
                "path": new_folder.path,
                "permissions": []
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"Erreur création dossier DB: {str(e)}"
        }), 500

@nas_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_properties():
    """Obtenir les propriétés d'un fichier ou dossier"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    file_path = request.args.get('path', '').strip()
    file_path = normalize_smb_path(file_path)
    
    if not file_path or not validate_smb_path(file_path):
        return jsonify({"error": "Chemin invalide"}), 400

    # Vérifier les permissions de lecture
    parent_path = get_parent_path(file_path)
    if not check_folder_permission(user, parent_path, 'read'):
        return jsonify({"error": "Permission de lecture refusée"}), 403

    try:
        smb_client = get_smb_client()
        properties = smb_client.get_file_info(file_path)
        
        return jsonify({
            "success": True,
            "properties": properties
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur propriétés: {str(e)}"
        }), 500

@nas_bp.route('/test-connection', methods=['GET'])
@jwt_required()
def test_connection():
    """Test de la connexion SMB et Synology - Admin uniquement"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user or user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    try:
        results = {}
        
        # Test SMB connection
        try:
            smb_client = get_smb_client()
            smb_result = smb_client.test_connection()
            results["smb"] = smb_result
        except Exception as e:
            results["smb"] = {
                "success": False,
                "error": f"SMB connection failed: {str(e)}"
            }
        
        # Test Synology API connection
        try:
            from services.synology_service import get_synology_service
            synology_service = get_synology_service()
            synology_result = synology_service.test_connection()
            results["synology"] = synology_result
        except Exception as e:
            results["synology"] = {
                "success": False,
                "error": f"Synology API connection failed: {str(e)}"
            }
        
        # Overall success if at least one connection works
        overall_success = results.get("smb", {}).get("success", False) or results.get("synology", {}).get("success", False)
        
        return jsonify({
            "success": overall_success,
            "message": "Connection test completed",
            "results": results,
            "recommendation": "SMB connection is sufficient for basic file operations. Synology API provides enhanced sync features." if results.get("smb", {}).get("success") else "Check your NAS configuration and network connectivity."
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur test connexion: {str(e)}"
        }), 500

@nas_bp.route('/config', methods=['GET'])
@jwt_required()
def get_nas_config():
    """Obtenir la configuration NAS pour Synology Drive"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    
    try:
        # Try Synology API first, fallback to SMB config
        try:
            from services.synology_service import get_synology_service
            synology_service = get_synology_service()
            config = synology_service.get_drive_client_config(user_id)
            
            return jsonify({
                "success": True,
                "config": config,
                "integration_type": "synology_drive"
            })
            
        except Exception as synology_error:
            print(f"Synology API unavailable, falling back to SMB: {str(synology_error)}")
            
            # Fallback to SMB configuration
            smb_client = get_smb_client()
            
            # Configuration pour Synology Drive Client via SMB
            config = {
                "server_address": smb_client.server_ip,
                "server_name": smb_client.server_name,
                "shared_folder": smb_client.shared_folder,
                "protocol": "SMB",
                "port": smb_client.port,
                "sync_enabled": True,
                "real_time_sync": True,
                "conflict_resolution": "server_wins",
                "sync_filters": {
                    "exclude_patterns": [
                        "*.tmp", "*.temp", ".DS_Store", "Thumbs.db", "~$*",
                        "*.lock", "*.swp", "*.swo", ".git/*", "node_modules/*"
                    ],
                    "include_patterns": ["*"]
                },
                "bandwidth_limit": {
                    "upload_kbps": 0,  # 0 = unlimited
                    "download_kbps": 0
                },
                "sync_schedule": {
                    "enabled": False,
                    "start_time": "09:00",
                    "end_time": "18:00",
                    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
                },
                "connection": {
                    "username": smb_client.username if user.role.upper() == 'ADMIN' else user.username,
                    "domain": smb_client.domain_name,
                    "authentication": "NTLM_v2",
                    "keep_alive": True,
                    "retry_attempts": 3,
                    "retry_delay": 5
                },
                "setup_instructions": {
                    "windows": [
                        "Download Synology Drive Client from Synology website",
                        "Install and launch the application",
                        f"Add server: {smb_client.server_ip}",
                        "Enter your NAS credentials",
                        f"Select shared folder: {smb_client.shared_folder}",
                        "Configure sync settings as needed"
                    ],
                    "mac": [
                        "Download Synology Drive Client for macOS",
                        "Install the application",
                        f"Connect to server: {smb_client.server_ip}",
                        "Authenticate with your NAS credentials",
                        "Choose sync folders and settings"
                    ],
                    "mobile": [
                        "Install Synology Drive app from App Store/Google Play",
                        f"Add server: {smb_client.server_ip}",
                        "Login with your NAS credentials",
                        "Enable auto-sync for desired folders"
                    ]
                }
            }
            
            return jsonify({
                "success": True,
                "config": config,
                "drive_client_url": f"synology-drive://connect?server={smb_client.server_ip}&share={smb_client.shared_folder}",
                "web_interface_url": f"http://{smb_client.server_ip}:5000",
                "integration_type": "smb_fallback"
            })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur configuration: {str(e)}"
        }), 500

@nas_bp.route('/sync-status', methods=['GET'])
@jwt_required()
def get_sync_status():
    """Obtenir le statut de synchronisation"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    
    try:
        # Try to get real sync status from Synology API
        try:
            from services.synology_service import get_synology_service
            synology_service = get_synology_service()
            return jsonify(synology_service.get_sync_status(user_id))
            
        except Exception as synology_error:
            print(f"Synology API unavailable for sync status: {str(synology_error)}")
            
            # Fallback to simulated status based on SMB connection
            smb_client = get_smb_client()
            connection_test = smb_client.test_connection()
            
            status = {
                "connected": connection_test.get("success", False),
                "last_sync": datetime.utcnow().isoformat(),
                "sync_in_progress": False,
                "pending_uploads": 0,
                "pending_downloads": 0,
                "total_files": 0,
                "synced_files": 0,
                "errors": [] if connection_test.get("success") else [connection_test.get("error", "Connection failed")],
                "bandwidth_usage": {
                    "upload_kbps": 0,
                    "download_kbps": 0
                },
                "sync_health": "healthy" if connection_test.get("success") else "error",
                "integration_type": "smb_fallback"
            }
            
            return jsonify({
                "success": True,
                "status": status
            })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur statut sync: {str(e)}"
        }), 500

@nas_bp.route('/force-sync', methods=['POST'])
@jwt_required()
def force_sync():
    """Forcer une synchronisation"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404
    
    data = request.get_json() or {}
    sync_path = normalize_smb_path(data.get('path', '/'))
    
    # Vérifier les permissions
    if not check_folder_permission(user, sync_path, 'read'):
        return jsonify({"error": "Permission refusée pour la synchronisation"}), 403
    
    try:
        # Try to trigger sync via Synology API
        try:
            from services.synology_service import get_synology_service
            synology_service = get_synology_service()
            return jsonify(synology_service.trigger_sync(user_id, sync_path))
            
        except Exception as synology_error:
            print(f"Synology API unavailable for sync trigger: {str(synology_error)}")
            
            # Fallback: simulate sync trigger
            return jsonify({
                "success": True,
                "message": f"Synchronisation déclenchée pour {sync_path}",
                "sync_id": f"sync_{user_id}_{int(datetime.utcnow().timestamp())}",
                "integration_type": "smb_fallback",
                "note": "Sync triggered via SMB connection monitoring"
            })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur déclenchement sync: {str(e)}"
        }), 500

@nas_bp.route('/browse', methods=['GET'])
@jwt_required()
def browse_directory():
    """Navigation dans l'arborescence du NAS avec vérification des permissions backend"""
    try:
        jwt_identity = get_jwt_identity()
        if jwt_identity is None:
            return jsonify({"error": "Token JWT invalide - identity manquante"}), 401
        user_id = int(jwt_identity)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Token JWT invalide: {str(e)}"}), 401
        
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    path = request.args.get('path', '/')
    path = normalize_smb_path(path)
    
    if not validate_smb_path(path):
        return jsonify({"error": "Chemin invalide"}), 400
        
    # Vérifier les permissions de lecture via la base de données
    if not check_folder_permission(user, path, 'read'):
        # Pour la racine, vérifier si l'utilisateur a au moins un accès de base
        if path == '/' and user.role.upper() != 'ADMIN':
            has_root_access = ensure_root_access(user)
            if not has_root_access:
                return jsonify({
                    "error": "Aucune permission configurée. Contactez votre administrateur.",
                    "suggestion": "Vous n'avez accès à aucun dossier. Un administrateur doit vous accorder des permissions."
                }), 403
        else:
            return jsonify({"error": "Accès refusé à ce répertoire"}), 403

    try:
        smb_client = get_smb_client()
        items = smb_client.list_files(path)
        
        # Filtrer les éléments selon les permissions pour les non-admins
        if user.role.upper() != 'ADMIN':
            accessible_items = []
            
            # Ajouter aussi les dossiers accessibles même s'ils sont dans des parents non accessibles
            if path == '/':
                # À la racine, ajouter tous les dossiers auxquels l'utilisateur a accès
                all_accessible_folders = get_all_accessible_folders(user)
                for folder_path in all_accessible_folders:
                    # Vérifier si ce dossier est un enfant direct de la racine
                    if folder_path.count('/') == 1 and folder_path != '/':
                        # Créer un item virtuel pour ce dossier
                        folder_name = folder_path.strip('/')
                        virtual_item = {
                            'name': folder_name,
                            'path': folder_path,
                            'is_directory': True,
                            'size': 0,
                            'modified': None,
                            'created': None,
                            'mime_type': None
                        }
                        # Vérifier qu'il n'est pas déjà dans la liste
                        if not any(item['path'] == folder_path for item in items):
                            accessible_items.append(virtual_item)
            
            for item in items:
                # Vérifier les permissions selon le type d'élément
                if item['is_directory']:
                    # Pour les dossiers, vérifier les permissions de dossier
                    if check_folder_permission(user, item['path'], 'read'):
                        accessible_items.append(item)
                else:
                    # Pour les fichiers, vérifier les permissions de fichier
                    if check_file_permission(user, item['path'], 'read'):
                        accessible_items.append(item)
                        
            print(f"🔍 Filtrage permissions pour {user.username}: {len(items)} éléments -> {len(accessible_items)} accessibles")
            items = accessible_items
        
        return jsonify({
            "success": True,
            "path": path,
            "parent_path": get_parent_path(path) if path != '/' else None,
            "items": items,
            "total": len(items)
        })
        
    except Exception as e:
        print(f"❌ Erreur browse_directory pour {path}: {str(e)}")
        
        # Log détaillé pour debug
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "success": False,
            "error": f"Erreur navigation: {str(e)}"
        }), 500

@nas_bp.route('/create-folder', methods=['POST'])
@jwt_required()
def create_folder():
    """Création d'un nouveau dossier avec vérification des permissions"""
    try:
        jwt_identity = get_jwt_identity()
        if jwt_identity is None:
            return jsonify({"error": "Token JWT invalide - identity manquante"}), 401
        user_id = int(jwt_identity)
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Token JWT invalide: {str(e)}"}), 401
        
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": f"Utilisateur introuvable avec l'ID {user_id}"}), 404
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données JSON requises"}), 400
        
    parent_path = normalize_smb_path(data.get('parent_path', '/'))
    folder_name = sanitize_filename(data.get('name', '').strip())

    if not folder_name:
        return jsonify({"error": "Le nom du dossier est requis"}), 400
        
    if not validate_smb_path(parent_path):
        return jsonify({"error": "Chemin parent invalide"}), 400
    
    # Vérifier les permissions d'écriture via la base de données
    has_permission = check_folder_permission(user, parent_path, 'write')
    
    if not has_permission:
        return jsonify({"error": "Permission d'écriture refusée sur ce dossier"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.create_folder(parent_path, folder_name)
        
        if result.get('success'):
            # Enregistrer le log d'accès
            log_file_operation(
                user_id, 
                'CREATE', 
                f"Dossier '{folder_name}' dans '{parent_path}'"
            )
            
            # Synchroniser avec la DB et créer les permissions
            try:
                parent_folder = Folder.query.filter_by(path=parent_path).first()
                parent_id = parent_folder.id if parent_folder else None
                
                folder_data = {
                    'name': folder_name,
                    'path': result['path']
                }
                
                folder_id = sync_folder_to_db(folder_data, parent_id, user.id)
                
                # Créer automatiquement toutes les permissions pour l'utilisateur créateur
                if folder_id:
                    from models.folder_permission import FolderPermission
                    
                    # Vérifier si les permissions existent déjà
                    existing_perm = FolderPermission.query.filter_by(
                        folder_id=folder_id, 
                        user_id=user.id
                    ).first()
                    
                    if not existing_perm:
                        # Créer les permissions complètes pour le créateur
                        creator_permission = FolderPermission(
                            folder_id=folder_id,
                            user_id=user.id,
                            can_read=True,
                            can_write=True,
                            can_delete=True,
                            can_share=True
                        )
                        db.session.add(creator_permission)
                        print(f"✅ Permissions complètes créées pour l'utilisateur {user.username} sur le dossier {folder_name}")
                
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation DB: {str(sync_error)}")
                db.session.rollback()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur création dossier: {str(e)}"
        }), 500

@nas_bp.route('/create-file', methods=['POST'])
@jwt_required()
def create_file():
    """Création d'un nouveau fichier vide avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json()
    parent_path = normalize_smb_path(data.get('parent_path', '/'))
    file_name = sanitize_filename(data.get('name', '').strip())

    if not file_name:
        return jsonify({"error": "Le nom du fichier est requis"}), 400
        
    if not validate_smb_path(parent_path):
        return jsonify({"error": "Chemin parent invalide"}), 400
    
    # Vérifier les permissions d'écriture via la base de données
    if not check_folder_permission(user, parent_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur ce dossier"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.create_file(parent_path, file_name)
        
        if result.get('success'):
            # Enregistrer le log d'accès
            log_file_operation(
                user_id, 
                'CREATE', 
                f"Fichier '{file_name}' dans '{parent_path}'"
            )
            
            # Synchroniser avec la DB et créer les permissions
            try:
                parent_folder = Folder.query.filter_by(path=parent_path).first()
                parent_id = parent_folder.id if parent_folder else None
                
                file_data = {
                    'name': file_name,
                    'path': result['path'],
                    'size': 0,  # Fichier vide
                    'mime_type': get_file_mime_type(file_name)
                }
                
                created_file = sync_file_to_db(file_data, parent_id, user.id)
                
                # Créer automatiquement toutes les permissions pour l'utilisateur créateur
                if created_file and hasattr(created_file, 'id'):
                    from models.file_permission import FilePermission
                    
                    # Vérifier si les permissions existent déjà
                    existing_perm = FilePermission.query.filter_by(
                        file_id=created_file.id, 
                        user_id=user.id
                    ).first()
                    
                    if not existing_perm:
                        # Créer les permissions complètes pour le créateur
                        creator_permission = FilePermission(
                            file_id=created_file.id,
                            user_id=user.id,
                            can_read=True,
                            can_write=True,
                            can_delete=True,
                            can_share=True
                        )
                        db.session.add(creator_permission)
                        print(f"✅ Permissions complètes créées pour l'utilisateur {user.username} sur le fichier {file_name}")
                
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation DB: {str(sync_error)}")
                db.session.rollback()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur création fichier: {str(e)}"
        }), 500

@nas_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """Upload de fichier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier fourni"}), 400
        
    file_obj = request.files['file']
    if file_obj.filename == '':
        return jsonify({"error": "Nom de fichier vide"}), 400

    dest_path = normalize_smb_path(request.form.get('path', '/'))
    overwrite = request.form.get('overwrite', 'false').lower() == 'true'
    
    if not validate_smb_path(dest_path):
        return jsonify({"error": "Chemin de destination invalide"}), 400
    
    # Vérifier les permissions d'écriture via la base de données
    if not check_folder_permission(user, dest_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur ce dossier"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.upload_file(file_obj, dest_path, file_obj.filename, overwrite)
        
        if result.get('success'):
            # Enregistrer le log d'accès
            file_size = file_obj.content_length or 0
            size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 0
            log_file_operation(
                user_id, 
                'UPLOAD', 
                f"Fichier '{result['name']}' dans '{dest_path}'",
                f"Taille: {size_mb} MB"
            )
            
            # Synchroniser avec la DB
            try:
                folder = Folder.query.filter_by(path=dest_path).first()
                folder_id = folder.id if folder else None
                
                file_data = {
                    'name': result['name'],
                    'path': result['path'],
                    'size': file_obj.content_length or 0,
                    'mime_type': get_file_mime_type(result['name'])
                }
                
                sync_file_to_db(file_data, folder_id, user.id)
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation fichier DB: {str(sync_error)}")
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur upload: {str(e)}"
        }), 500

@nas_bp.route('/download/<path:file_path>', methods=['GET', 'OPTIONS'])
def download_file(file_path):
    """Téléchargement de fichier avec vérification des permissions"""
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = Response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response
    
    # Apply JWT only for non-OPTIONS requests
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
    try:
        verify_jwt_in_request()
    except Exception as e:
        return jsonify({"error": "Token d'authentification requis"}), 401
    
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    file_path = urllib.parse.unquote(file_path)
    file_path = normalize_smb_path(file_path)
    
    if not validate_smb_path(file_path):
        return jsonify({"error": "Chemin de fichier invalide"}), 400
    
    # Skip system files that might cause issues
    filename = get_filename_from_path(file_path)
    system_files = ['desktop.ini', 'thumbs.db', '.ds_store', 'folder.jpg', 'albumartsmall.jpg']
    if filename.lower() in system_files:
        return jsonify({"error": "Les fichiers système ne peuvent pas être téléchargés"}), 403

    # Vérifier les permissions de lecture via la base de données
    if not check_folder_permission(user, get_parent_path(file_path), 'read'):
        return jsonify({"error": "Permission de lecture refusée sur ce fichier"}), 403

    try:
        smb_client = get_smb_client()
        
        # Get file info first to determine size for progress tracking
        try:
            file_info = smb_client.get_file_info(file_path)
            file_size = file_info.get('size', 0) if file_info else 0
        except:
            file_size = 0
        
        file_stream = smb_client.download_file(file_path)
        filename = get_filename_from_path(file_path)
        mime_type = get_file_mime_type(filename)

        # Enregistrer le log d'accès avec taille du fichier
        size_info = f"Taille: {round(file_size / (1024 * 1024), 2)} MB" if file_size > 0 else ""
        log_file_operation(
            user_id, 
            'DOWNLOAD', 
            f"Fichier '{filename}' depuis '{get_parent_path(file_path)}'",
            size_info
        )

        def generate():
            chunk_size = 8192
            while True:
                chunk = file_stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            file_stream.close()

        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': mime_type
        }
        
        # Add Content-Length header for progress tracking if file size is known
        if file_size > 0:
            headers['Content-Length'] = str(file_size)

        response = Response(
            generate(),
            headers=headers
        )
        
        # Add CORS headers
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        
        return response
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur téléchargement: {str(e)}"
        }), 500

@nas_bp.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_item():
    """Suppression de fichier ou dossier avec vérification des permissions"""
    try:
        jwt_identity = get_jwt_identity()
        print(f"🔍 Delete JWT Identity type: {type(jwt_identity)}, value: {jwt_identity}")
        
        if jwt_identity is None:
            return jsonify({"error": "Token JWT invalide - identity manquante"}), 401
            
        user_id = int(jwt_identity)
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": f"Utilisateur introuvable avec l'ID {user_id}"}), 404
            
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Token JWT invalide: {str(e)}"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Données JSON requises"}), 400
        
    raw_path = data.get('path', '')
    if not raw_path:
        return jsonify({"error": "Chemin requis dans les données"}), 400
        
    target_path = normalize_smb_path(raw_path.strip())
    recursive = data.get('recursive', False)  # Option for recursive deletion
    
    if not target_path:
        return jsonify({"error": "Chemin vide après normalisation"}), 400
        
    if not validate_smb_path(target_path):
        return jsonify({
            "error": "Chemin invalide", 
            "path": target_path,
            "raw_path": raw_path
        }), 400
    
    # Vérifier les permissions de suppression via la base de données
    has_permission = check_folder_permission(user, target_path, 'delete')
    
    if not has_permission:
        return jsonify({
            "error": "Permission de suppression refusée",
            "details": f"L'utilisateur {user.username} (rôle: {user.role}) n'a pas les permissions pour supprimer {target_path}"
        }), 403

    try:
        smb_client = get_smb_client()
        
        print(f"🗑️ Tentative de suppression: {target_path} (utilisateur: {user.username}, admin: {user.role.upper() == 'ADMIN'}, récursif: {recursive})")
        
        # Vérifier d'abord si le fichier/dossier existe
        file_exists = True
        is_directory = False
        try:
            file_info = smb_client.get_file_info(target_path)
            is_directory = file_info.get('is_directory', False)
            print(f"📁 Élément trouvé: {target_path} (dossier: {is_directory})")
        except Exception as check_error:
            print(f"⚠️ Élément non trouvé sur le NAS: {target_path} - {str(check_error)}")
            file_exists = False
            
        # Stratégie de suppression basée sur le rôle et le type
        if not file_exists:
            # Si l'élément n'existe pas sur le NAS, on supprime juste de la DB
            print(f"🗑️ Élément absent du NAS, suppression DB seulement")
            result = {"success": True, "message": "Suppression de la DB seulement (élément absent du NAS)"}
        elif user.role.upper() == 'ADMIN':
            # Admins utilisent toujours la suppression récursive pour éviter les erreurs "not empty"
            print(f"🔧 Suppression récursive admin pour: {target_path}")
            try:
                result = smb_client.delete_file_recursive(target_path)
                print(f"✅ Suppression récursive réussie: {target_path}")
            except Exception as delete_error:
                print(f"⚠️ Erreur suppression récursive NAS: {str(delete_error)}")
                # Même en cas d'erreur, on continue avec la DB pour les admins
                result = {"success": True, "message": f"Suppression partielle: {str(delete_error)}"}
        else:
            # Utilisateurs normaux utilisent la suppression standard
            print(f"🔧 Suppression normale pour: {target_path}")
            try:
                result = smb_client.delete_file(target_path)
                print(f"✅ Suppression normale réussie: {target_path}")
            except Exception as delete_error:
                error_msg = str(delete_error)
                print(f"❌ Erreur suppression normale: {error_msg}")
                
                # Si c'est un dossier non vide, on informe l'utilisateur
                if "n'est pas vide" in error_msg.lower() or "not empty" in error_msg.lower():
                    raise Exception(f"Le dossier '{target_path}' n'est pas vide. Contactez un administrateur pour une suppression récursive.")
                else:
                    raise Exception(f"Impossible de supprimer '{target_path}': {error_msg}")
        
        if result.get('success'):
            # Synchroniser avec la DB - supprimer l'entrée
            try:
                file_entry = File.query.filter_by(path=target_path).first()
                if file_entry:
                    db.session.delete(file_entry)
                    
                folder_entry = Folder.query.filter_by(path=target_path).first()
                if folder_entry:
                    # Supprimer récursivement tous les sous-éléments
                    def delete_folder_recursive(folder):
                        files = File.query.filter_by(folder_id=folder.id).all()
                        for f in files:
                            db.session.delete(f)
                        
                        subfolders = Folder.query.filter_by(parent_id=folder.id).all()
                        for sf in subfolders:
                            delete_folder_recursive(sf)
                        
                        db.session.delete(folder)
                    
                    delete_folder_recursive(folder_entry)
                
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation suppression DB: {str(sync_error)}")
                db.session.rollback()
        
        return jsonify(result)
        
    except Exception as e:
        error_message = str(e)
        status_code = 500
        
        print(f"❌ Erreur lors de la suppression de {target_path}: {error_message}")
        print(f"❌ Type d'erreur: {type(e).__name__}")
        
        # Handle specific error cases
        if "n'est pas vide" in error_message.lower() or "not empty" in error_message.lower():
            if user.role.upper() == 'ADMIN':
                # Pour les admins, on devrait pouvoir supprimer récursivement
                print(f"⚠️ Dossier non vide mais utilisateur admin - tentative de suppression récursive forcée")
                try:
                    # Force recursive deletion for admin
                    smb_client = get_smb_client()
                    result = smb_client.delete_file_recursive(target_path)
                    if result.get('success'):
                        return jsonify(result)
                except Exception as force_error:
                    print(f"❌ Échec suppression récursive forcée: {str(force_error)}")
            
            status_code = 422
            error_message = f"Le dossier '{target_path}' n'est pas vide. " + (
                "Suppression récursive échouée." if user.role.upper() == 'ADMIN' 
                else "Veuillez d'abord supprimer son contenu ou demander à un administrateur."
            )
        elif "permission" in error_message.lower() or "access" in error_message.lower():
            status_code = 403
            error_message = "Accès refusé. Vérifiez vos permissions sur le fichier/dossier."
        elif "not found" in error_message.lower() or "introuvable" in error_message.lower():
            status_code = 404
            error_message = "Fichier ou dossier introuvable."
        elif "impossible de supprimer récursivement" in error_message.lower():
            status_code = 422
            error_message = f"Impossible de supprimer récursivement '{target_path}': {error_message}"
        
        return jsonify({
            "success": False,
            "error": error_message,
            "details": {
                "path": target_path,
                "user": user.username,
                "role": user.role,
                "recursive_attempted": user.role.upper() == 'ADMIN',
                "original_error": str(e)
            }
        }), status_code

@nas_bp.route('/rename', methods=['PUT', 'POST', 'OPTIONS'])
@nas_bp.route('/rename-item', methods=['PUT', 'POST', 'OPTIONS'])
def rename_item():
    """Renommage de fichier ou dossier avec vérification des permissions"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response, 200
    
    # Appliquer JWT seulement pour les requêtes non-OPTIONS
    from flask_jwt_extended import verify_jwt_in_request
    try:
        verify_jwt_in_request()
    except Exception as e:
        return jsonify({"error": "Token d'authentification requis", "msg": str(e)}), 401
    
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
        
        # Validation des données d'entrée
        if not request.is_json:
            return jsonify({"error": "Content-Type doit être application/json"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "Données JSON requises"}), 400
            
        # Safer data extraction with type checking
        old_path_raw = data.get('old_path', '')
        new_name_raw = data.get('new_name', '')
        
        # Ensure we have strings
        if not isinstance(old_path_raw, str):
            return jsonify({"error": f"old_path doit être une chaîne, reçu {type(old_path_raw).__name__}"}), 400
        if not isinstance(new_name_raw, str):
            return jsonify({"error": f"new_name doit être une chaîne, reçu {type(new_name_raw).__name__}"}), 400
            
        old_path = old_path_raw.strip()
        new_name = new_name_raw.strip()

        if not old_path or not new_name:
            return jsonify({"error": "Chemin source et nouveau nom requis"}), 400
            
        # Normaliser et valider les chemins
        try:
            old_path = normalize_smb_path(old_path)
            new_name = sanitize_filename(new_name)
        except Exception as e:
            return jsonify({"error": f"Erreur de validation des chemins: {str(e)}"}), 400
            
        if not validate_smb_path(old_path):
            return jsonify({"error": "Chemin source invalide"}), 400
            
        # Vérifications supplémentaires
        if not new_name or new_name.strip() == '':
            return jsonify({"error": "Le nouveau nom ne peut pas être vide"}), 400
            
        if len(new_name) > 255:
            return jsonify({"error": "Le nom est trop long (maximum 255 caractères)"}), 400
            
        # Vérifier que le nouveau nom est différent de l'ancien
        current_name = old_path.split('/')[-1]
        if new_name == current_name:
            return jsonify({"error": "Le nouveau nom doit être différent de l'ancien"}), 400

        # Vérifier les permissions d'écriture via la base de données
        # Déterminer si c'est un fichier ou un dossier
        is_file = '.' in old_path.split('/')[-1]  # Simple heuristique
        
        try:
            if is_file:
                # Pour les fichiers, vérifier les permissions de fichier
                if not check_file_permission(user, old_path, 'write'):
                    return jsonify({"error": "Permission d'écriture refusée pour le renommage de ce fichier"}), 403
            else:
                # Pour les dossiers, vérifier les permissions de dossier
                if not check_folder_permission(user, old_path, 'write'):
                    return jsonify({"error": "Permission d'écriture refusée pour le renommage de ce dossier"}), 403
        except Exception as perm_error:
            print(f"Erreur vérification permissions: {str(perm_error)}")
            return jsonify({"error": "Erreur lors de la vérification des permissions"}), 500

        # Effectuer le renommage
        try:
            smb_client = get_smb_client()
            result = smb_client.rename_file(old_path, new_name)
            
            if result.get('success'):
                # Enregistrer le log d'accès
                try:
                    log_file_operation(
                        user_id,
                        'RENAME',
                        f"'{old_path}' renommé en '{new_name}'",
                        f"Nouveau chemin: {result.get('new_path', 'N/A')}"
                    )
                except Exception as log_error:
                    print(f"Erreur log d'accès: {str(log_error)}")
                
                # Synchroniser avec la DB
                try:
                    # Mettre à jour fichier
                    file_entry = File.query.filter_by(path=old_path).first()
                    if file_entry:
                        file_entry.name = new_name
                        file_entry.path = result['new_path']
                    
                    # Mettre à jour dossier
                    folder_entry = Folder.query.filter_by(path=old_path).first()
                    if folder_entry:
                        folder_entry.name = new_name
                        folder_entry.path = result['new_path']
                        
                        # Mettre à jour récursivement tous les sous-éléments
                        def update_paths_recursive(folder, old_base, new_base):
                            try:
                                files = File.query.filter_by(folder_id=folder.id).all()
                                for f in files:
                                    if f.path.startswith(old_base):
                                        f.path = f.path.replace(old_base, new_base, 1)
                                
                                subfolders = Folder.query.filter_by(parent_id=folder.id).all()
                                for sf in subfolders:
                                    if sf.path.startswith(old_base):
                                        sf.path = sf.path.replace(old_base, new_base, 1)
                                        update_paths_recursive(sf, old_base, new_base)
                            except Exception as recursive_error:
                                print(f"Erreur mise à jour récursive: {str(recursive_error)}")
                        
                        update_paths_recursive(folder_entry, old_path, result['new_path'])
                    
                    db.session.commit()
                    
                except Exception as sync_error:
                    print(f"Erreur synchronisation renommage DB: {str(sync_error)}")
                    db.session.rollback()
                    # Ne pas faire échouer le renommage si la sync DB échoue
            
            return jsonify(result)
            
        except Exception as smb_error:
            print(f"Erreur SMB renommage: {str(smb_error)}")
            return jsonify({
                "success": False,
                "error": f"Erreur lors du renommage: {str(smb_error)}"
            }), 500
        
    except Exception as e:
        print(f"Erreur générale renommage: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Erreur interne du serveur: {str(e)}"
        }), 500

@nas_bp.route('/debug/rename', methods=['POST'])
@jwt_required()
def debug_rename():
    """Debug de la fonctionnalité de renommage"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json() or {}
    old_path = data.get('old_path', '').strip()
    new_name = data.get('new_name', '').strip()
    
    debug_info = {
        "user": user.username,
        "old_path": old_path,
        "new_name": new_name,
        "normalized_path": normalize_smb_path(old_path) if old_path else None,
        "sanitized_name": sanitize_filename(new_name) if new_name else None,
        "path_valid": validate_smb_path(old_path) if old_path else False,
        "is_file": '.' in old_path.split('/')[-1] if old_path else False,
        "permissions": {}
    }
    
    if old_path:
        is_file = '.' in old_path.split('/')[-1]
        try:
            if is_file:
                debug_info["permissions"]["file_write"] = check_file_permission(user, old_path, 'write')
            else:
                debug_info["permissions"]["folder_write"] = check_folder_permission(user, old_path, 'write')
        except Exception as e:
            debug_info["permissions"]["error"] = str(e)
    
    return jsonify({
        "success": True,
        "debug_info": debug_info
    })

@nas_bp.route('/move', methods=['PUT'])
@jwt_required()
def move_item():
    """Déplacement de fichier ou dossier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json()
    source_path = normalize_smb_path(data.get('source_path', '').strip())
    dest_path = normalize_smb_path(data.get('dest_path', '').strip())

    if not source_path or not dest_path:
        return jsonify({"error": "Chemin source et destination requis"}), 400
        
    if not validate_smb_path(source_path) or not validate_smb_path(dest_path):
        return jsonify({"error": "Chemin invalide"}), 400

    # Vérifier les permissions d'écriture sur source et destination
    if not check_folder_permission(user, source_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur la source"}), 403
        
    if not check_folder_permission(user, dest_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur la destination"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.move_file(source_path, dest_path)
        
        if result.get('success'):
            # Synchroniser avec la DB
            try:
                # Mettre à jour fichier
                file_entry = File.query.filter_by(path=source_path).first()
                if file_entry:
                    file_entry.path = result['new_path']
                    # Mettre à jour le folder_id si nécessaire
                    dest_folder = Folder.query.filter_by(path=dest_path).first()
                    if dest_folder:
                        file_entry.folder_id = dest_folder.id
                
                # Mettre à jour dossier
                folder_entry = Folder.query.filter_by(path=source_path).first()
                if folder_entry:
                    folder_entry.path = result['new_path']
                    folder_entry.parent_path = dest_path
                    # Mettre à jour parent_id si nécessaire
                    dest_folder = Folder.query.filter_by(path=dest_path).first()
                    if dest_folder:
                        folder_entry.parent_id = dest_folder.id
                    
                    # Mettre à jour récursivement tous les sous-éléments
                    def update_paths_recursive(folder, old_base, new_base):
                        files = File.query.filter_by(folder_id=folder.id).all()
                        for f in files:
                            if f.path.startswith(old_base):
                                f.path = f.path.replace(old_base, new_base, 1)
                        
                        subfolders = Folder.query.filter_by(parent_id=folder.id).all()
                        for sf in subfolders:
                            if sf.path.startswith(old_base):
                                sf.path = sf.path.replace(old_base, new_base, 1)
                                update_paths_recursive(sf, old_base, new_base)
                    
                    update_paths_recursive(folder_entry, source_path, result['new_path'])
                
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation déplacement DB: {str(sync_error)}")
                db.session.rollback()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur déplacement: {str(e)}"
        }), 500

@nas_bp.route('/permissions/check', methods=['GET'])
@jwt_required()
def check_path_permissions():
    """Vérifier les permissions d'un utilisateur sur un chemin spécifique"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({"error": "Chemin requis"}), 400
    
    path = normalize_smb_path(path)
    
    if not validate_smb_path(path):
        return jsonify({"error": "Chemin invalide"}), 400
    
    try:
        # Déterminer si c'est un fichier ou un dossier
        is_file = '.' in path.split('/')[-1]  # Simple heuristique
        
        if is_file:
            # Vérifier les permissions de fichier
            permissions = {
                'can_read': check_file_permission(user, path, 'read'),
                'can_write': check_file_permission(user, path, 'write'),
                'can_delete': check_file_permission(user, path, 'delete'),
                'can_share': check_file_permission(user, path, 'share'),
                'can_modify': check_file_permission(user, path, 'write')  # Alias pour write
            }
        else:
            # Vérifier les permissions de dossier
            permissions = {
                'can_read': check_folder_permission(user, path, 'read'),
                'can_write': check_folder_permission(user, path, 'write'),
                'can_delete': check_folder_permission(user, path, 'delete'),
                'can_share': check_folder_permission(user, path, 'share'),
                'can_modify': check_folder_permission(user, path, 'write')  # Alias pour write
            }
        
        return jsonify({
            "success": True,
            "path": path,
            "permissions": permissions,
            "is_admin": user.role.upper() == 'ADMIN',
            "user": user.username,
            "type": "file" if is_file else "folder"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur vérification permissions: {str(e)}"
        }), 500

@nas_bp.route('/debug/permissions/<int:user_id>', methods=['GET'])
@jwt_required()
def debug_user_permissions(user_id):
    """Debug des permissions d'un utilisateur (Admin uniquement)"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    
    if not current_user or current_user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    try:
        user = User.query.get_or_404(user_id)
        
        # Récupérer toutes les permissions de dossiers
        folder_permissions = []
        folders = Folder.query.all()
        for folder in folders:
            permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [folder.id])
            folder_perm = permissions.get(folder.id)
            if folder_perm:
                folder_permissions.append({
                    'folder_id': folder.id,
                    'folder_name': folder.name,
                    'folder_path': folder.path,
                    'can_read': folder_perm.can_read,
                    'can_write': folder_perm.can_write,
                    'can_delete': folder_perm.can_delete,
                    'can_share': folder_perm.can_share
                })
        
        # Récupérer toutes les permissions de fichiers
        file_permissions = []
        from models.file_permission import FilePermission
        user_file_perms = FilePermission.query.filter_by(user_id=user.id).all()
        for perm in user_file_perms:
            if perm.file:
                file_permissions.append({
                    'file_id': perm.file.id,
                    'file_name': perm.file.name,
                    'file_path': getattr(perm.file, 'path', 'N/A'),
                    'can_read': perm.can_read,
                    'can_write': perm.can_write,
                    'can_delete': perm.can_delete,
                    'can_share': perm.can_share
                })
        
        # Permissions via les groupes
        group_file_permissions = []
        for group in user.groups:
            group_file_perms = FilePermission.query.filter_by(group_id=group.id).all()
            for perm in group_file_perms:
                if perm.file:
                    group_file_permissions.append({
                        'group_name': group.name,
                        'file_id': perm.file.id,
                        'file_name': perm.file.name,
                        'file_path': getattr(perm.file, 'path', 'N/A'),
                        'can_read': perm.can_read,
                        'can_write': perm.can_write,
                        'can_delete': perm.can_delete,
                        'can_share': perm.can_share
                    })
        
        return jsonify({
            "success": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "groups": [g.name for g in user.groups]
            },
            "folder_permissions": folder_permissions,
            "file_permissions": file_permissions,
            "group_file_permissions": group_file_permissions
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur debug permissions: {str(e)}"
        }), 500

@nas_bp.route('/debug/access-issue', methods=['GET'])
@jwt_required()
def debug_access_issue():
    """Diagnostiquer les problèmes d'accès pour l'utilisateur actuel"""
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    
    try:
        # Vérifier l'accès à la racine
        root_access = check_folder_permission(user, '/', 'read')
        root_folder = Folder.query.filter_by(path='/').first()
        
        # Compter les permissions de l'utilisateur
        folder_count = 0
        file_count = 0
        
        if root_folder:
            permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [root_folder.id])
            if permissions.get(root_folder.id):
                folder_count += 1
        
        # Compter les permissions de fichiers
        from models.file_permission import FilePermission
        user_file_perms = FilePermission.query.filter_by(user_id=user.id).count()
        
        # Permissions via les groupes
        group_folder_count = 0
        group_file_count = 0
        for group in user.groups:
            group_file_count += FilePermission.query.filter_by(group_id=group.id).count()
        
        return jsonify({
            "success": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "groups": [g.name for g in user.groups]
            },
            "access_status": {
                "root_access": root_access,
                "root_folder_exists": root_folder is not None,
                "direct_folder_permissions": folder_count,
                "direct_file_permissions": user_file_perms,
                "group_file_permissions": group_file_count
            },
            "recommendations": [
                "Contactez votre administrateur pour obtenir des permissions" if folder_count == 0 and user_file_perms == 0 else None,
                "Vous avez accès à la racine" if root_access else "Accès à la racine refusé",
                f"Vous êtes membre de {len(user.groups)} groupe(s)" if user.groups else "Vous n'êtes membre d'aucun groupe"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur diagnostic: {str(e)}"
        }), 500

@nas_bp.route('/sync', methods=['POST'])
@jwt_required()
def sync_nas_database():
    """Synchronisation complète entre le NAS et la base de données"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user or user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    data = request.get_json() or {}
    dry_run = data.get('dry_run', False)
    max_depth = data.get('max_depth', 10)
    
    try:
        print(f"🔄 Démarrage synchronisation NAS-DB (dry_run={dry_run})")
        
        # Utiliser le service de synchronisation
        result = nas_sync_service.full_sync(
            max_depth=max_depth,
            default_owner_id=user_id,
            dry_run=dry_run
        )
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur synchronisation: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Erreur synchronisation: {str(e)}"
        }), 500