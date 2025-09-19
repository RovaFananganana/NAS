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
            
            self.conn = SMBConnection(
                self.username,
                self.password,
                self.client_name,
                self.server_name,
                domain=self.domain_name,
                use_ntlm_v2=True
            )
            
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
        """Liste les fichiers et dossiers"""
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
            # Une seule tentative de reconnexion
            try:
                self._connect()
                files = self.conn.listPath(self.shared_folder, path)
                result = []
                for file_obj in files:
                    if file_obj.filename not in [".", ".."]:
                        file_info = format_smb_file_info(file_obj, path)
                        result.append(file_info)
                result.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
                return result
            except Exception as e2:
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

def check_folder_permission(user, path, required_action='read'):
    """
    Vérifie les permissions d'un utilisateur sur un chemin via la base de données
    Actions possibles: 'read', 'write', 'delete', 'share'
    """
    if user.role.upper() == 'ADMIN':
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
        
        # Par défaut, autoriser la lecture pour les utilisateurs authentifiés
        return required_action == 'read'
        
    except Exception as e:
        print(f"Erreur vérification permission {required_action} pour {user.username} sur {path}: {str(e)}")
        # En cas d'erreur, autoriser seulement la lecture
        return required_action == 'read'

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

@nas_bp.route('/test-connection', methods=['GET'])
@jwt_required()
def test_connection():
    """Test de la connexion SMB - Admin uniquement"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user or user.role.upper() != 'ADMIN':
        return jsonify({"error": "Accès réservé aux administrateurs"}), 403
    
    try:
        smb_client = get_smb_client()
        result = smb_client.test_connection()
        return jsonify(result)
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
        smb_client = get_smb_client()
        
        # Configuration pour Synology Drive Client
        config = {
            "server_address": smb_client.server_ip,
            "server_name": smb_client.server_name,
            "shared_folder": smb_client.shared_folder,
            "protocol": "SMB",
            "port": smb_client.port,
            "sync_enabled": True,
            "real_time_sync": True,
            "conflict_resolution": "server_wins",  # ou "client_wins", "manual"
            "sync_filters": {
                "exclude_patterns": [
                    "*.tmp",
                    "*.temp",
                    ".DS_Store",
                    "Thumbs.db",
                    "~$*"
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
            }
        }
        
        # Ajouter les informations utilisateur pour la connexion
        if user.role.upper() == 'ADMIN':
            config["connection"] = {
                "username": smb_client.username,
                "domain": smb_client.domain_name,
                "authentication": "NTLM_v2"
            }
        else:
            # Pour les utilisateurs normaux, ils utilisent leurs propres credentials
            config["connection"] = {
                "username": user.username,
                "domain": smb_client.domain_name,
                "authentication": "NTLM_v2"
            }
        
        return jsonify({
            "success": True,
            "config": config,
            "drive_client_url": f"synology-drive://connect?server={smb_client.server_ip}&share={smb_client.shared_folder}",
            "web_interface_url": f"http://{smb_client.server_ip}:5000"  # Port par défaut Synology DSM
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
        # Ici vous pourriez intégrer avec l'API Synology pour obtenir le statut réel
        # Pour l'instant, on retourne un statut simulé
        status = {
            "connected": True,
            "last_sync": datetime.utcnow().isoformat(),
            "sync_in_progress": False,
            "pending_uploads": 0,
            "pending_downloads": 0,
            "total_files": 0,
            "synced_files": 0,
            "errors": [],
            "bandwidth_usage": {
                "upload_kbps": 0,
                "download_kbps": 0
            }
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
        # Ici vous pourriez déclencher une synchronisation via l'API Synology
        # Pour l'instant, on simule le déclenchement
        
        return jsonify({
            "success": True,
            "message": f"Synchronisation déclenchée pour {sync_path}",
            "sync_id": f"sync_{user_id}_{int(datetime.utcnow().timestamp())}"
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
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "Utilisateur introuvable"}), 404

    path = request.args.get('path', '/')
    path = normalize_smb_path(path)
    
    if not validate_smb_path(path):
        return jsonify({"error": "Chemin invalide"}), 400
        
    # Vérifier les permissions de lecture via la base de données
    if not check_folder_permission(user, path, 'read'):
        return jsonify({"error": "Accès refusé à ce répertoire"}), 403

    try:
        smb_client = get_smb_client()
        items = smb_client.list_files(path)
        
        # Filtrer les éléments selon les permissions pour les non-admins
        if user.role.upper() != 'ADMIN':
            accessible_items = []
            for item in items:
                if check_folder_permission(user, item['path'], 'read'):
                    accessible_items.append(item)
            items = accessible_items
        
        return jsonify({
            "success": True,
            "path": path,
            "parent_path": get_parent_path(path) if path != '/' else None,
            "items": items,
            "total": len(items)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur navigation: {str(e)}"
        }), 500

@nas_bp.route('/create-folder', methods=['POST'])
@jwt_required()
def create_folder():
    """Création d'un nouveau dossier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json()
    parent_path = normalize_smb_path(data.get('parent_path', '/'))
    folder_name = sanitize_filename(data.get('name', '').strip())

    if not folder_name:
        return jsonify({"error": "Le nom du dossier est requis"}), 400
        
    if not validate_smb_path(parent_path):
        return jsonify({"error": "Chemin parent invalide"}), 400
    
    # Vérifier les permissions d'écriture via la base de données
    if not check_folder_permission(user, parent_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée sur ce dossier"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.create_folder(parent_path, folder_name)
        
        if result.get('success'):
            # Synchroniser avec la DB
            try:
                parent_folder = Folder.query.filter_by(path=parent_path).first()
                parent_id = parent_folder.id if parent_folder else None
                
                folder_data = {
                    'name': folder_name,
                    'path': result['path']
                }
                
                sync_folder_to_db(folder_data, parent_id, user.id)
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation DB: {str(sync_error)}")
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur création dossier: {str(e)}"
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

@nas_bp.route('/download/<path:file_path>', methods=['GET'])
@jwt_required()
def download_file(file_path):
    """Téléchargement de fichier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    file_path = urllib.parse.unquote(file_path)
    file_path = normalize_smb_path(file_path)
    
    if not validate_smb_path(file_path):
        return jsonify({"error": "Chemin de fichier invalide"}), 400

    # Vérifier les permissions de lecture via la base de données
    if not check_folder_permission(user, get_parent_path(file_path), 'read'):
        return jsonify({"error": "Permission de lecture refusée sur ce fichier"}), 403

    try:
        smb_client = get_smb_client()
        file_stream = smb_client.download_file(file_path)
        filename = get_filename_from_path(file_path)
        mime_type = get_file_mime_type(filename)

        def generate():
            chunk_size = 8192
            while True:
                chunk = file_stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            file_stream.close()

        return Response(
            generate(),
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': mime_type
            }
        )
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur téléchargement: {str(e)}"
        }), 500

@nas_bp.route('/delete', methods=['DELETE'])
@jwt_required()
def delete_item():
    """Suppression de fichier ou dossier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json()
    target_path = normalize_smb_path(data.get('path', '').strip())

    if not target_path:
        return jsonify({"error": "Chemin requis"}), 400
        
    if not validate_smb_path(target_path):
        return jsonify({"error": "Chemin invalide"}), 400
    
    # Vérifier les permissions de suppression via la base de données
    if not check_folder_permission(user, target_path, 'delete'):
        return jsonify({"error": "Permission de suppression refusée"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.delete_file(target_path)
        
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
        return jsonify({
            "success": False,
            "error": f"Erreur suppression: {str(e)}"
        }), 500

@nas_bp.route('/rename', methods=['PUT'])
@jwt_required()
def rename_item():
    """Renommage de fichier ou dossier avec vérification des permissions"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    data = request.get_json()
    old_path = normalize_smb_path(data.get('old_path', '').strip())
    new_name = sanitize_filename(data.get('new_name', '').strip())

    if not old_path or not new_name:
        return jsonify({"error": "Chemin source et nouveau nom requis"}), 400
        
    if not validate_smb_path(old_path):
        return jsonify({"error": "Chemin source invalide"}), 400

    # Vérifier les permissions d'écriture via la base de données
    if not check_folder_permission(user, old_path, 'write'):
        return jsonify({"error": "Permission d'écriture refusée pour le renommage"}), 403

    try:
        smb_client = get_smb_client()
        result = smb_client.rename_file(old_path, new_name)
        
        if result.get('success'):
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
                        files = File.query.filter_by(folder_id=folder.id).all()
                        for f in files:
                            if f.path.startswith(old_base):
                                f.path = f.path.replace(old_base, new_base, 1)
                        
                        subfolders = Folder.query.filter_by(parent_id=folder.id).all()
                        for sf in subfolders:
                            if sf.path.startswith(old_base):
                                sf.path = sf.path.replace(old_base, new_base, 1)
                                update_paths_recursive(sf, old_base, new_base)
                    
                    update_paths_recursive(folder_entry, old_path, result['new_path'])
                
                db.session.commit()
                
            except Exception as sync_error:
                print(f"Erreur synchronisation renommage DB: {str(sync_error)}")
                db.session.rollback()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Erreur renommage: {str(e)}"
        }), 500

@nas_bp.route('/move', methods=['POST'])
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