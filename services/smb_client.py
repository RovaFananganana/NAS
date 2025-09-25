# services/smb_client.py

import os
import io
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Import smbprotocol
from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.file import File, FileAttributes, CreateDisposition, CreateOptions, ShareAccess, FileAccessMask
from smbprotocol.open import Open
from smbprotocol.query_info import QueryInfoRequest, FileInformationClass
from smbprotocol.create import CreateRequest
from smbprotocol.close import CloseRequest
from smbprotocol.read import ReadRequest
from smbprotocol.write import WriteRequest
from smbprotocol.exceptions import SMBException

load_dotenv()

class ModernSMBClient:
    """Client SMB moderne utilisant smbprotocol pour une meilleure compatibilité Synology"""
    
    def __init__(self):
        # Configuration depuis les variables d'environnement
        self.server_ip = os.getenv('SMB_SERVER_IP', '10.61.17.33')
        self.username = os.getenv('SMB_USERNAME', 'gestion')
        self.password = os.getenv('SMB_PASSWORD', 'Aeronav99')
        self.shared_folder = os.getenv('SMB_SHARED_FOLDER', 'NAS')
        self.domain = os.getenv('SMB_DOMAIN', '')
        self.port = int(os.getenv('SMB_PORT', '445'))  # smbprotocol utilise 445 par défaut
        
        self.connection = None
        self.session = None
        self.tree = None
        self._is_connected = False
        
    def _connect(self):
        """Établit la connexion SMB moderne"""
        try:
            if self._is_connected and self.connection:
                return True
            
            # Créer la connexion
            self.connection = Connection(uuid.uuid4(), self.server_ip, self.port)
            self.connection.connect()
            
            # Créer la session
            self.session = Session(self.connection, self.username, self.password, domain=self.domain)
            self.session.connect()
            
            # Se connecter au partage
            self.tree = TreeConnect(self.session, f"\\\\{self.server_ip}\\{self.shared_folder}")
            self.tree.connect()
            
            self._is_connected = True
            print(f"✅ Connexion SMB moderne établie vers {self.server_ip}:{self.port}")
            return True
            
        except Exception as e:
            self._is_connected = False
            print(f"❌ Erreur connexion SMB moderne: {str(e)}")
            raise
    
    def _ensure_connected(self):
        """S'assure que la connexion est active"""
        if not self._is_connected:
            self._connect()
    
    def _normalize_path(self, path):
        """Normalise le chemin pour SMB"""
        if not path or path == '/':
            return ''
        return path.replace('/', '\\').lstrip('\\')
    
    def list_files(self, path="/"):
        """Liste les fichiers et dossiers"""
        self._ensure_connected()
        
        try:
            smb_path = self._normalize_path(path)
            if smb_path:
                smb_path += "\\*"
            else:
                smb_path = "*"
            
            # Ouvrir le répertoire pour lister
            file_obj = File(self.tree, smb_path)
            
            # Créer la requête d'ouverture
            open_req = CreateRequest()
            open_req['desired_access'] = FileAccessMask.GENERIC_READ
            open_req['file_attributes'] = FileAttributes.FILE_ATTRIBUTE_DIRECTORY
            open_req['share_access'] = ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE
            open_req['create_disposition'] = CreateDisposition.FILE_OPEN
            open_req['create_options'] = CreateOptions.FILE_DIRECTORY_FILE
            open_req['name'] = smb_path.encode('utf-16le')
            
            # Envoyer la requête
            response = self.session.send(open_req)
            
            # Traiter la réponse et lister les fichiers
            # Cette partie nécessite une implémentation plus complexe
            # Pour l'instant, retournons une liste vide
            return []
            
        except Exception as e:
            print(f"❌ Erreur listage moderne {path}: {str(e)}")
            raise Exception(f"Impossible de lister {path}: {str(e)}")
    
    def test_connection(self):
        """Teste la connexion SMB moderne"""
        try:
            self._ensure_connected()
            
            # Test simple : essayer de lister la racine
            files = self.list_files("/")
            
            return {
                "success": True,
                "message": "Connexion SMB moderne fonctionnelle",
                "root_files_count": len(files),
                "server_info": {
                    "ip": self.server_ip,
                    "port": self.port,
                    "share": self.shared_folder,
                    "username": self.username,
                    "protocol": "SMB3 (smbprotocol)"
                }
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Échec test connexion moderne: {str(e)}",
                "error": str(e)
            }
    
    def disconnect(self):
        """Ferme la connexion"""
        try:
            if self.tree:
                self.tree.disconnect()
            if self.session:
                self.session.disconnect()
            if self.connection:
                self.connection.disconnect()
            self._is_connected = False
            print("✅ Connexion SMB moderne fermée")
        except Exception as e:
            print(f"❌ Erreur fermeture connexion: {str(e)}")

# Import uuid pour la connexion
import uuid