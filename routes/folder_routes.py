# routes/folder_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Folder, User, FolderPermission, File
from extensions import db
from services.permission_optimizer import PermissionOptimizer
from utils.nas_utils import normalize_smb_path, validate_smb_path, sanitize_filename
from utils.smb_client import SMBClientNAS

folder_bp = Blueprint('folder_bp', __name__, url_prefix='/folders')

# Initialize permission optimizer
permission_optimizer = PermissionOptimizer()

# Instance SMB pour synchronisation
def get_nas_client():
    return SMBClientNAS()

def sync_folder_with_nas(folder, nas_client=None):
    """Synchronise un dossier DB avec le NAS"""
    if nas_client is None:
        nas_client = get_nas_client()
    
    try:
        # Vérifier si le dossier existe sur le NAS
        if not nas_client.path_exists(folder.path):
            # Créer le dossier sur le NAS
            parent_path = "/".join(folder.path.split("/")[:-1]) or "/"
            nas_client.create_folder(parent_path, folder.name)
        return True
    except Exception as e:
        print(f"Erreur sync dossier {folder.path} avec NAS: {str(e)}")
        return False

@folder_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    """
    List folders with optimized bulk permission loading and pagination.
    Integrates with NAS synchronization.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    # Get query parameters
    parent_id = request.args.get('parent_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    include_files = request.args.get('include_files', 'false').lower() == 'true'
    sync_with_nas = request.args.get('sync_nas', 'false').lower() == 'true'
    
    # Admin users see everything
    if user.role.upper() == 'ADMIN':
        query = Folder.query
        if parent_id is not None:
            query = query.filter_by(parent_id=parent_id)
        
        folders_page = query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        result = {
            'folders': [
                {
                    "id": f.id, 
                    "name": f.name, 
                    "path": f.path,
                    "parent_id": f.parent_id,
                    "owner_id": f.owner_id,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                    "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                    "permissions": {
                        "can_read": True,
                        "can_write": True,
                        "can_delete": True,
                        "can_share": True,
                        "is_owner": f.owner_id == user_id,
                        "source": "admin"
                    }
                } 
                for f in folders_page.items
            ],
            'pagination': {
                'page': folders_page.page,
                'per_page': folders_page.per_page,
                'total': folders_page.total,
                'pages': folders_page.pages,
                'has_next': folders_page.has_next,
                'has_prev': folders_page.has_prev
            }
        }
        
        if include_files:
            folder_ids = [f.id for f in folders_page.items]
            if folder_ids:
                files_query = File.query.filter(File.folder_id.in_(folder_ids))
                if parent_id is not None:
                    files_query = files_query.filter_by(folder_id=parent_id)
                
                files = files_query.all()
                result['files'] = [
                    {
                        "id": f.id,
                        "name": f.name,
                        "path": f.path,
                        "folder_id": f.folder_id,
                        "owner_id": f.owner_id,
                        "size_kb": f.size_kb,
                        "mime_type": f.mime_type,
                        "created_at": f.created_at.isoformat() if f.created_at else None,
                        "permissions": {
                            "can_read": True,
                            "can_write": True,
                            "can_delete": True,
                            "can_share": True,
                            "is_owner": f.owner_id == user_id,
                            "source": "admin"
                        }
                    }
                    for f in files
                ]
        
        return jsonify(result)
    
    # For non-admin users, use optimized permission loading
    base_query = db.session.query(Folder.id).distinct()
    
    # Filter by parent if specified
    if parent_id is not None:
        base_query = base_query.filter_by(parent_id=parent_id)
    
    # Get folders that user might have access to
    candidate_query = base_query.filter(
        db.or_(
            Folder.owner_id == user_id,
            Folder.id.in_(
                db.session.query(FolderPermission.folder_id)
                .filter_by(user_id=user_id)
            ),
            Folder.id.in_(
                db.session.query(FolderPermission.folder_id)
                .join(User.groups)
                .filter(User.id == user_id)
            )
        )
    )
    
    candidate_folders_page = candidate_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    candidate_folder_ids = [row.id for row in candidate_folders_page.items]
    
    if not candidate_folder_ids:
        return jsonify({
            'folders': [],
            'files': [] if include_files else None,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': 0,
                'pages': 0,
                'has_next': False,
                'has_prev': False
            }
        })
    
    # Bulk load permissions
    folder_permissions = permission_optimizer.get_bulk_folder_permissions(
        user_id, candidate_folder_ids
    )
    
    # Filter and build response
    accessible_folders = []
    accessible_folder_ids = []
    
    folders_dict = {f.id: f for f in Folder.query.filter(Folder.id.in_(candidate_folder_ids)).all()}
    
    for folder_id in candidate_folder_ids:
        perm_set = folder_permissions.get(folder_id)
        if perm_set and perm_set.can_read:
            folder = folders_dict.get(folder_id)
            if folder:
                accessible_folders.append({
                    "id": folder.id,
                    "name": folder.name,
                    "path": folder.path,
                    "parent_id": folder.parent_id,
                    "owner_id": folder.owner_id,
                    "created_at": folder.created_at.isoformat() if folder.created_at else None,
                    "updated_at": folder.updated_at.isoformat() if folder.updated_at else None,
                    "permissions": perm_set.to_dict()
                })
                accessible_folder_ids.append(folder_id)
    
    result = {
        'folders': accessible_folders,
        'pagination': {
            'page': candidate_folders_page.page,
            'per_page': candidate_folders_page.per_page,
            'total': candidate_folders_page.total,
            'pages': candidate_folders_page.pages,
            'has_next': candidate_folders_page.has_next,
            'has_prev': candidate_folders_page.has_prev
        }
    }
    
    # Include files if requested
    if include_files and accessible_folder_ids:
        files_in_folders = File.query.filter(File.folder_id.in_(accessible_folder_ids)).all()
        file_ids = [f.id for f in files_in_folders]
        
        if file_ids:
            file_permissions = permission_optimizer.get_bulk_file_permissions(user_id, file_ids)
            
            accessible_files = []
            for file in files_in_folders:
                file_perm = file_permissions.get(file.id)
                if file_perm and file_perm.can_read:
                    accessible_files.append({
                        "id": file.id,
                        "name": file.name,
                        "path": file.path,
                        "folder_id": file.folder_id,
                        "owner_id": file.owner_id,
                        "size_kb": file.size_kb,
                        "mime_type": file.mime_type,
                        "created_at": file.created_at.isoformat() if file.created_at else None,
                        "permissions": file_perm.to_dict()
                    })
            
            result['files'] = accessible_files
        else:
            result['files'] = []
    elif include_files:
        result['files'] = []
    
    return jsonify(result)

@folder_bp.route('/<int:folder_id>/contents', methods=['GET'])
@jwt_required()
def get_folder_contents(folder_id):
    """
    Get folder contents with NAS integration
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    folder = Folder.query.get_or_404(folder_id)
    
    # Check permissions for admin users
    if user.role.upper() == 'ADMIN':
        subfolders = Folder.query.filter_by(parent_id=folder_id).all()
        files = File.query.filter_by(folder_id=folder_id).all()
        
        return jsonify({
            'folder': {
                'id': folder.id,
                'name': folder.name,
                'path': folder.path,
                'parent_id': folder.parent_id,
                'permissions': {
                    "can_read": True,
                    "can_write": True,
                    "can_delete": True,
                    "can_share": True,
                    "is_owner": folder.owner_id == user_id,
                    "source": "admin"
                }
            },
            'subfolders': [
                {
                    'id': sf.id,
                    'name': sf.name,
                    'path': sf.path,
                    'owner_id': sf.owner_id,
                    'permissions': {
                        "can_read": True,
                        "can_write": True,
                        "can_delete": True,
                        "can_share": True,
                        "is_owner": sf.owner_id == user_id,
                        "source": "admin"
                    }
                }
                for sf in subfolders
            ],
            'files': [
                {
                    'id': f.id,
                    'name': f.name,
                    'path': f.path,
                    'folder_id': f.folder_id,
                    'owner_id': f.owner_id,
                    'size_kb': f.size_kb,
                    'mime_type': f.mime_type,
                    'permissions': {
                        "can_read": True,
                        "can_write": True,
                        "can_delete": True,
                        "can_share": True,
                        "is_owner": f.owner_id == user_id,
                        "source": "admin"
                    }
                }
                for f in files
            ]
        })
    
    # Check folder access permission
    folder_permissions = permission_optimizer.get_bulk_folder_permissions(user_id, [folder_id])
    folder_perm = folder_permissions.get(folder_id)
    
    if not folder_perm or not folder_perm.can_read:
        return jsonify({"msg": "Accès refusé au dossier"}), 403
    
    # Get subfolders and files with permissions
    subfolders = Folder.query.filter_by(parent_id=folder_id).all()
    files = File.query.filter_by(folder_id=folder_id).all()
    
    subfolder_ids = [sf.id for sf in subfolders]
    file_ids = [f.id for f in files]
    
    subfolder_permissions = {}
    file_permissions = {}
    
    if subfolder_ids:
        subfolder_permissions = permission_optimizer.get_bulk_folder_permissions(user_id, subfolder_ids)
    
    if file_ids:
        file_permissions = permission_optimizer.get_bulk_file_permissions(user_id, file_ids)
    
    # Build response
    accessible_subfolders = []
    for subfolder in subfolders:
        perm = subfolder_permissions.get(subfolder.id)
        if perm and perm.can_read:
            accessible_subfolders.append({
                'id': subfolder.id,
                'name': subfolder.name,
                'path': subfolder.path,
                'owner_id': subfolder.owner_id,
                'permissions': perm.to_dict()
            })
    
    accessible_files = []
    for file in files:
        perm = file_permissions.get(file.id)
        if perm and perm.can_read:
            accessible_files.append({
                'id': file.id,
                'name': file.name,
                'path': file.path,
                'folder_id': file.folder_id,
                'owner_id': file.owner_id,
                'size_kb': file.size_kb,
                'mime_type': file.mime_type,
                'permissions': perm.to_dict()
            })
    
    return jsonify({
        'folder': {
            'id': folder.id,
            'name': folder.name,
            'path': folder.path,
            'parent_id': folder.parent_id,
            'permissions': folder_perm.to_dict()
        },
        'subfolders': accessible_subfolders,
        'files': accessible_files
    })

@folder_bp.route('/create', methods=['POST'])
@jwt_required()
def create_folder_route():
    """Create folder with NAS synchronization"""
    data = request.json
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if not data.get('name'):
        return jsonify({"msg": "Le nom du dossier est requis"}), 400

    folder_name = sanitize_filename(data['name'])
    parent_id = data.get('parent_id')
    create_on_nas = data.get('create_on_nas', True)

    # Determine path
    if parent_id:
        parent_folder = Folder.query.get(parent_id)
        if not parent_folder:
            return jsonify({"msg": "Dossier parent introuvable"}), 404
            
        # Check permissions
        perm = permission_optimizer.get_bulk_folder_permissions(user_id, [parent_id]).get(parent_id)
        if not perm or not perm.can_write:
            return jsonify({"msg": "Permission refusée"}), 403
            
        relative_path = normalize_smb_path(f"{parent_folder.path}/{folder_name}")
    else:
        relative_path = normalize_smb_path(f"/{folder_name}")

    if not validate_smb_path(relative_path):
        return jsonify({"msg": "Chemin invalide"}), 400

    try:
        # Create on NAS first if requested
        nas_success = True
        if create_on_nas:
            try:
                nas_client = get_nas_client()
                parent_path = "/".join(relative_path.split("/")[:-1]) or "/"
                nas_result = nas_client.create_folder(parent_path, folder_name)
                if not nas_result.get('success'):
                    nas_success = False
            except Exception as nas_error:
                print(f"Erreur création NAS: {str(nas_error)}")
                nas_success = False

        # Create in database
        folder = Folder(
            name=folder_name,
            owner_id=user.id,
            parent_id=parent_id,
            path=relative_path
        )
        db.session.add(folder)
        db.session.commit()

        response_data = {
            "msg": "Dossier créé",
            "id": folder.id,
            "path": folder.path,
            "nas_synchronized": nas_success
        }
        
        if not nas_success:
            response_data["warning"] = "Dossier créé en DB mais pas synchronisé avec le NAS"

        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur création dossier: {str(e)}"}), 500

@folder_bp.route('/<int:folder_id>', methods=['DELETE'])
@jwt_required()
def delete_folder(folder_id):
    """Delete folder with NAS synchronization"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    folder = Folder.query.get_or_404(folder_id)
    
    # Check permissions
    if user.role.upper() != 'ADMIN':
        perm = permission_optimizer.get_bulk_folder_permissions(user_id, [folder_id]).get(folder_id)
        if not perm or not perm.can_delete:
            return jsonify({"msg": "Permission refusée"}), 403
    
    try:
        # Delete from NAS first
        nas_success = True
        try:
            nas_client = get_nas_client()
            nas_result = nas_client.delete_file(folder.path)
            if not nas_result.get('success'):
                nas_success = False
        except Exception as nas_error:
            print(f"Erreur suppression NAS: {str(nas_error)}")
            nas_success = False
        
        # Delete from database (cascade will handle subfolders and files)
        db.session.delete(folder)
        db.session.commit()
        
        return jsonify({
            "msg": "Dossier supprimé",
            "nas_synchronized": nas_success,
            "warning": "Supprimé de la DB mais pas du NAS" if not nas_success else None
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erreur suppression: {str(e)}"}), 500

@folder_bp.route('/<int:folder_id>/sync-nas', methods=['POST'])
@jwt_required()
def sync_folder_nas(folder_id):
    """Synchronize specific folder with NAS"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    if user.role.upper() != 'ADMIN':
        return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
    
    folder = Folder.query.get_or_404(folder_id)
    
    try:
        nas_client = get_nas_client()
        success = sync_folder_with_nas(folder, nas_client)
        
        if success:
            return jsonify({
                "msg": f"Dossier {folder.name} synchronisé avec le NAS",
                "success": True
            })
        else:
            return jsonify({
                "msg": f"Échec synchronisation du dossier {folder.name}",
                "success": False
            }), 500
            
    except Exception as e:
        return jsonify({
            "msg": f"Erreur synchronisation: {str(e)}",
            "success": False
        }), 500

@folder_bp.route('/tree/<int:folder_id>', methods=['GET'])
@jwt_required()
def get_folder_tree(folder_id):
    """Get folder tree with permissions (unchanged from original)"""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    max_depth = min(request.args.get('depth', 3, type=int), 5)
    
    root_folder = Folder.query.get_or_404(folder_id)
    
    if user.role.upper() == 'ADMIN':
        return jsonify({
            'tree': _build_folder_tree_admin(folder_id, max_depth, user_id),
            'permissions_loaded': 1  # Admin has all permissions
        })
    
    tree_permissions = permission_optimizer.get_folder_tree_permissions(user_id, folder_id, max_depth)
    
    root_perm = tree_permissions.get(folder_id)
    if not root_perm or not root_perm.can_read:
        return jsonify({"msg": "Accès refusé au dossier racine"}), 403
    
    tree_data = _build_folder_tree_with_permissions(folder_id, tree_permissions, max_depth)
    
    return jsonify({
        'tree': tree_data,
        'permissions_loaded': len(tree_permissions)
    })

def _build_folder_tree_admin(folder_id, max_depth, user_id, current_depth=0):
    """Build folder tree for admin users"""
    if current_depth >= max_depth:
        return None
    
    folder = Folder.query.get(folder_id)
    if not folder:
        return None
    
    subfolders = Folder.query.filter_by(parent_id=folder_id).all()
    
    tree_node = {
        'id': folder.id,
        'name': folder.name,
        'path': folder.path,
        'owner_id': folder.owner_id,
        'permissions': {
            "can_read": True,
            "can_write": True,
            "can_delete": True,
            "can_share": True,
            "is_owner": folder.owner_id == user_id,
            "source": "admin"
        },
        'children': []
    }
    
    for subfolder in subfolders:
        child_tree = _build_folder_tree_admin(subfolder.id, max_depth, user_id, current_depth + 1)
        if child_tree:
            tree_node['children'].append(child_tree)
    
    return tree_node

def _build_folder_tree_with_permissions(folder_id, permissions_dict, max_depth, current_depth=0):
    """Build folder tree with permission filtering"""
    if current_depth >= max_depth:
        return None
    
    perm = permissions_dict.get(folder_id)
    if not perm or not perm.can_read:
        return None
    
    folder = Folder.query.get(folder_id)
    if not folder:
        return None
    
    subfolders = Folder.query.filter_by(parent_id=folder_id).all()
    
    tree_node = {
        'id': folder.id,
        'name': folder.name,
        'path': folder.path,
        'owner_id': folder.owner_id,
        'permissions': perm.to_dict(),
        'children': []
    }
    
    for subfolder in subfolders:
        child_tree = _build_folder_tree_with_permissions(
            subfolder.id, permissions_dict, max_depth, current_depth + 1
        )
        if child_tree:
            tree_node['children'].append(child_tree)
    
    return tree_node