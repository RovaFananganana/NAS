# routes/folder_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import Folder, User, FolderPermission, File
from extensions import db
from services.file_service import create_folder
from services.permission_optimizer import PermissionOptimizer

folder_bp = Blueprint('folder_bp', __name__, url_prefix='/folders')

# Initialize permission optimizer
permission_optimizer = PermissionOptimizer()

@folder_bp.route('/', methods=['GET'])
@jwt_required()
def list_folders():
    """
    List folders with optimized bulk permission loading and pagination.
    Supports filtering by parent folder and efficient permission checking.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    # Get query parameters
    parent_id = request.args.get('parent_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)  # Max 100 items per page
    include_files = request.args.get('include_files', 'false').lower() == 'true'
    
    # Admin users see everything
    if user.role == 'admin':
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
            # Get files in the folders for admin
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
                        "folder_id": f.folder_id,
                        "owner_id": f.owner_id,
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
    # Step 1: Get candidate folders (owned + potentially accessible)
    base_query = db.session.query(Folder.id).distinct()
    
    # Filter by parent if specified
    if parent_id is not None:
        base_query = base_query.filter_by(parent_id=parent_id)
    
    # Get folders that user might have access to:
    # 1. Owned folders
    # 2. Folders with direct permissions
    # 3. Folders with group permissions
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
    
    # Apply pagination to candidate folders
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
    
    # Step 2: Bulk load permissions for candidate folders
    folder_permissions = permission_optimizer.get_bulk_folder_permissions(
        user_id, candidate_folder_ids
    )
    
    # Step 3: Filter folders by read permission and build response
    accessible_folders = []
    accessible_folder_ids = []
    
    # Get full folder objects for accessible folders
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
    
    # Step 4: Include files if requested
    if include_files and accessible_folder_ids:
        # Get files in accessible folders
        files_in_folders = File.query.filter(File.folder_id.in_(accessible_folder_ids)).all()
        file_ids = [f.id for f in files_in_folders]
        
        if file_ids:
            # Bulk load file permissions
            file_permissions = permission_optimizer.get_bulk_file_permissions(user_id, file_ids)
            
            # Filter files by read permission
            accessible_files = []
            for file in files_in_folders:
                file_perm = file_permissions.get(file.id)
                if file_perm and file_perm.can_read:
                    accessible_files.append({
                        "id": file.id,
                        "name": file.name,
                        "folder_id": file.folder_id,
                        "owner_id": file.owner_id,
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
    Get folder contents (subfolders and files) with preloaded permissions.
    Optimized for displaying folder tree views.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    # Check if folder exists and user has read access
    folder = Folder.query.get_or_404(folder_id)
    
    # For admin users, return everything
    if user.role == 'admin':
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
                    'folder_id': f.folder_id,
                    'owner_id': f.owner_id,
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
    
    # Check folder access permission first
    folder_permissions = permission_optimizer.get_bulk_folder_permissions(user_id, [folder_id])
    folder_perm = folder_permissions.get(folder_id)
    
    if not folder_perm or not folder_perm.can_read:
        return jsonify({"msg": "Accès refusé au dossier"}), 403
    
    # Get subfolders and files
    subfolders = Folder.query.filter_by(parent_id=folder_id).all()
    files = File.query.filter_by(folder_id=folder_id).all()
    
    # Bulk load permissions for all subfolders and files
    subfolder_ids = [sf.id for sf in subfolders]
    file_ids = [f.id for f in files]
    
    subfolder_permissions = {}
    file_permissions = {}
    
    if subfolder_ids:
        subfolder_permissions = permission_optimizer.get_bulk_folder_permissions(user_id, subfolder_ids)
    
    if file_ids:
        file_permissions = permission_optimizer.get_bulk_file_permissions(user_id, file_ids)
    
    # Filter and build response for accessible items only
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
                'folder_id': file.folder_id,
                'owner_id': file.owner_id,
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

@folder_bp.route('/tree/<int:folder_id>', methods=['GET'])
@jwt_required()
def get_folder_tree(folder_id):
    """
    Get folder tree with preloaded permissions for efficient tree navigation.
    Supports depth limiting to prevent loading too much data.
    """
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    
    # Get query parameters
    max_depth = min(request.args.get('depth', 3, type=int), 5)  # Max depth of 5
    
    # Check if root folder exists and user has access
    root_folder = Folder.query.get_or_404(folder_id)
    
    # For admin users, get full tree
    if user.role == 'admin':
        tree_permissions = {}  # Admin has all permissions
        tree_data = permission_optimizer.get_folder_tree_permissions(user_id, folder_id, max_depth)
        
        # Build tree structure (simplified for admin)
        return jsonify({
            'tree': _build_folder_tree_admin(folder_id, max_depth, user_id),
            'permissions_loaded': len(tree_data)
        })
    
    # Use optimized tree loading for regular users
    tree_permissions = permission_optimizer.get_folder_tree_permissions(user_id, folder_id, max_depth)
    
    # Check root folder access
    root_perm = tree_permissions.get(folder_id)
    if not root_perm or not root_perm.can_read:
        return jsonify({"msg": "Accès refusé au dossier racine"}), 403
    
    # Build tree structure with permissions
    tree_data = _build_folder_tree_with_permissions(folder_id, tree_permissions, max_depth)
    
    return jsonify({
        'tree': tree_data,
        'permissions_loaded': len(tree_permissions)
    })

def _build_folder_tree_admin(folder_id, max_depth, user_id, current_depth=0):
    """Build folder tree for admin users (simplified)."""
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
    """Build folder tree with permission filtering."""
    if current_depth >= max_depth:
        return None
    
    # Check if user has permission to see this folder
    perm = permissions_dict.get(folder_id)
    if not perm or not perm.can_read:
        return None
    
    folder = Folder.query.get(folder_id)
    if not folder:
        return None
    
    # Get subfolders
    subfolders = Folder.query.filter_by(parent_id=folder_id).all()
    
    tree_node = {
        'id': folder.id,
        'name': folder.name,
        'path': folder.path,
        'owner_id': folder.owner_id,
        'permissions': perm.to_dict(),
        'children': []
    }
    
    # Recursively build children
    for subfolder in subfolders:
        child_tree = _build_folder_tree_with_permissions(
            subfolder.id, permissions_dict, max_depth, current_depth + 1
        )
        if child_tree:
            tree_node['children'].append(child_tree)
    
    return tree_node

@folder_bp.route('/create', methods=['POST'])
@jwt_required()
def create_folder_route():
    data = request.json
    user_id =int(get_jwt_identity())
    user = User.query.get(user_id)

    if not data.get('name'):
        return jsonify({"msg": "Le nom du dossier est requis"}), 400

    parent_id = data.get('parent_id')
    relative_path = data['name']

    if parent_id:
        parent_folder = Folder.query.get(parent_id)
        if not parent_folder:
            return jsonify({"msg": "Dossier parent introuvable"}), 404
        perm = parent_folder.get_effective_permissions(user)
        if not perm or not perm.can_write:
            return jsonify({"msg": "Permission refusée"}), 403
        relative_path = f"{parent_folder.path}/{data['name']}"

    physical_path = create_folder(relative_path)

    folder = Folder(
        name=data['name'],
        owner_id=user.id,
        parent_id=parent_id,
        path=relative_path
    )
    db.session.add(folder)
    db.session.commit()

    return jsonify({
        "msg": "Dossier créé",
        "id": folder.id,
        "path": folder.path,
        "physical_path": physical_path
    })
