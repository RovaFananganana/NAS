# utils/nas_utils.py

import os
import mimetypes
from werkzeug.utils import secure_filename
from pathlib import Path
import tempfile
from datetime import datetime

# ================= UTILITAIRES CHEMIN ==================

def is_safe_path(path: str, base: str = "/") -> bool:
    """
    Vérifie que le chemin donné est à l'intérieur du chemin de base
    Adapté pour les chemins SMB
    """
    # Normaliser les chemins pour SMB (utiliser /)
    normalized_path = normalize_smb_path(path)
    normalized_base = normalize_smb_path(base)
    
    # Vérifier que le chemin ne contient pas de séquences dangereuses
    dangerous_sequences = ['../', '..\\', '/../', '\\..\\']
    for seq in dangerous_sequences:
        if seq in normalized_path:
            return False
    
    # Le chemin doit commencer par la base ou être égal
    return normalized_path.startswith(normalized_base)

def normalize_smb_path(path: str) -> str:
    """
    Normalise un chemin pour SMB (remplace \ par /, supprime doubles /)
    """
    if not path:
        return "/"
    
    # Remplacer \ par /
    normalized = path.replace("\\", "/")
    
    # Assurer que ça commence par /
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    
    # Supprimer les doubles /
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    
    # Supprimer le / final sauf pour la racine
    if len(normalized) > 1 and normalized.endswith("/"):
        normalized = normalized[:-1]
    
    return normalized

def get_safe_path(relative_path: str, base_path: str = "/") -> str:
    """
    Retourne un chemin absolu sécurisé à partir d'un chemin relatif
    Adapté pour SMB
    """
    if not relative_path or relative_path == '/':
        return normalize_smb_path(base_path)
    
    # Sécuriser le nom de fichier
    path_parts = relative_path.strip('/').split('/')
    safe_parts = [secure_filename(part) for part in path_parts if part]
    
    if not safe_parts:
        return normalize_smb_path(base_path)
    
    safe_relative = '/'.join(safe_parts)
    full_path = f"{base_path.rstrip('/')}/{safe_relative}"
    
    normalized_path = normalize_smb_path(full_path)
    
    if not is_safe_path(normalized_path, base_path):
        raise ValueError(f"Chemin non autorisé: {relative_path}")
    
    return normalized_path

def get_parent_path(path: str) -> str:
    """
    Retourne le chemin parent d'un chemin SMB
    """
    normalized = normalize_smb_path(path)
    if normalized == "/":
        return "/"
    
    parent = "/".join(normalized.split("/")[:-1])
    return parent if parent else "/"

def get_filename_from_path(path: str) -> str:
    """
    Extrait le nom de fichier d'un chemin
    """
    normalized = normalize_smb_path(path)
    return normalized.split("/")[-1] if normalized != "/" else ""

# ================= UTILITAIRES FICHIER ==================

def get_file_mime_type(file_path: str) -> str:
    """
    Retourne le type MIME d'un fichier
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

def format_bytes(size: int) -> str:
    """
    Formate une taille en bytes dans un format lisible (B, KB, MB, GB, TB)
    """
    if size is None or size < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def get_file_extension(filename: str) -> str:
    """
    Retourne l'extension d'un fichier en minuscules
    """
    return Path(filename).suffix.lower().lstrip('.')

def is_image_file(filename: str) -> bool:
    """
    Vérifie si le fichier est une image
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff'}
    return Path(filename).suffix.lower() in image_extensions

def is_document_file(filename: str) -> bool:
    """
    Vérifie si le fichier est un document
    """
    doc_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}
    return Path(filename).suffix.lower() in doc_extensions

def is_video_file(filename: str) -> bool:
    """
    Vérifie si le fichier est une vidéo
    """
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    return Path(filename).suffix.lower() in video_extensions

def is_audio_file(filename: str) -> bool:
    """
    Vérifie si le fichier est un fichier audio
    """
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'}
    return Path(filename).suffix.lower() in audio_extensions

def get_file_category(filename: str) -> str:
    """
    Retourne la catégorie d'un fichier
    """
    if is_image_file(filename):
        return "image"
    elif is_document_file(filename):
        return "document"
    elif is_video_file(filename):
        return "video"
    elif is_audio_file(filename):
        return "audio"
    else:
        return "other"

# ================= UTILITAIRES NOM ==================

def unique_filename(existing_files: list, filename: str) -> str:
    """
    Génère un nom de fichier unique pour éviter les collisions
    existing_files: liste des noms de fichiers existants
    """
    if filename not in existing_files:
        return filename
    
    base, ext = os.path.splitext(filename)
    counter = 1
    
    while True:
        candidate = f"{base}_{counter}{ext}"
        if candidate not in existing_files:
            return candidate
        counter += 1

def sanitize_filename(filename: str) -> str:
    """
    Nettoie un nom de fichier pour qu'il soit compatible avec SMB/Windows
    """
    # Caractères interdits sur Windows/SMB
    forbidden_chars = '<>:"/\\|?*'
    
    # Remplacer les caractères interdits
    cleaned = filename
    for char in forbidden_chars:
        cleaned = cleaned.replace(char, '_')
    
    # Supprimer les espaces en début/fin
    cleaned = cleaned.strip()
    
    # Éviter les noms réservés Windows
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    name_part = os.path.splitext(cleaned)[0].upper()
    if name_part in reserved_names:
        base, ext = os.path.splitext(cleaned)
        cleaned = f"{base}_file{ext}"
    
    # Limiter la longueur (255 caractères max)
    if len(cleaned) > 255:
        base, ext = os.path.splitext(cleaned)
        max_base_length = 255 - len(ext)
        cleaned = base[:max_base_length] + ext
    
    return cleaned

# ================= UTILITAIRES TEMPORAIRES ==================

def create_temp_file(content: bytes, suffix: str = "") -> str:
    """
    Crée un fichier temporaire avec le contenu donné
    Retourne le chemin du fichier temporaire
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(content)
        return temp_file.name

def cleanup_temp_file(temp_path: str) -> bool:
    """
    Supprime un fichier temporaire
    """
    try:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
            return True
        return False
    except Exception:
        return False

# ================= UTILITAIRES DE VALIDATION ==================

def validate_smb_path(path: str, max_depth: int = 10) -> bool:
    """
    Valide un chemin SMB
    """
    if not path:
        return False
    
    normalized = normalize_smb_path(path)
    
    # Vérifier la profondeur
    depth = len([p for p in normalized.split('/') if p])
    if depth > max_depth:
        return False
    
    # Vérifier les caractères invalides
    invalid_chars = '<>"|?*'
    for char in invalid_chars:
        if char in normalized:
            return False
    
    return True

def format_smb_file_info(file_obj, path: str = "") -> dict:
    """
    Formate les informations d'un fichier SMB en format standardisé
    """
    return {
        'name': file_obj.filename,
        'path': normalize_smb_path(os.path.join(path, file_obj.filename)),
        'is_directory': file_obj.isDirectory,
        'size': file_obj.file_size if not file_obj.isDirectory else None,
        'size_formatted': format_bytes(file_obj.file_size) if not file_obj.isDirectory else None,
        'modified': datetime.fromtimestamp(file_obj.last_write_time) if hasattr(file_obj, 'last_write_time') else None,
        'created': datetime.fromtimestamp(file_obj.create_time) if hasattr(file_obj, 'create_time') else None,
        'extension': get_file_extension(file_obj.filename) if not file_obj.isDirectory else None,
        'mime_type': get_file_mime_type(file_obj.filename) if not file_obj.isDirectory else None,
        'category': get_file_category(file_obj.filename) if not file_obj.isDirectory else 'folder'
    }