# routes/admin_routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, verify_jwt_in_request
from werkzeug.exceptions import Unauthorized
from models.user import User
from models.group import Group
from models.folder import Folder
from models.file import File
from models.access_log import AccessLog
from extensions import db
from functools import wraps
from datetime import datetime, timezone
from services.file_storage_service import FileStorageService

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def check_jwt():
    try:
        verify_jwt_in_request()
    except Exception as e:
        print("JWT ERROR:", str(e))  # Debug dans la console
        raise Unauthorized("Token invalide ou manquant")

# ------------------------ UTILITAIRES ------------------------

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        claims = get_jwt()
        if claims.get('role', '').upper() != 'ADMIN':
            return jsonify({"msg": "Accès réservé aux administrateurs"}), 403
        return f(*args, **kwargs)
    return decorated_function

def log_admin_action(action, target):
    """Enregistre les actions admin dans les logs"""
    try:
        current_user_id = int(get_jwt_identity())
        log = AccessLog(
            user_id=current_user_id,
            action=action,
            target=target,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print("Erreur log_admin_action:", e)

# ------------------------ UTILISATEURS ------------------------

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    users = User.query.all()
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role.upper(),
            'quota_mb': user.quota_mb,
            'created_at': user.created_at.isoformat(),
            'groups': [group.name for group in user.groups] if hasattr(user, 'groups') else []
        })
    return jsonify(users_data), 200

@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Missing required fields"}), 400

    username = data['username']
    email = data.get('email')
    password = data['password']
    role = data.get('role', 'SIMPLE_USER').upper()

    # Vérification d'unicité : username obligatoire, email seulement si fourni
    existing_user = User.query.filter(User.username == username).first()
    if email:
        if User.query.filter(User.email == email).first():
            existing_user = True

    if existing_user:
        return jsonify({"error": "User already exists"}), 400

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    log_admin_action('CREATE_USER', f"user:{user.username}")
    return jsonify({"message": "Utilisateur créé avec succès"}), 201


@admin_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if data.get('username') and data['username'] != user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({"msg": "Ce nom d'utilisateur existe déjà"}), 409
        user.username = data['username']

    if data.get('email') and data['email'] != user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({"msg": "Cet email est déjà utilisé"}), 409
        user.email = data['email']

    if data.get('role'):
        user.role = data['role'].upper()

    if data.get('quota_mb'):
        user.quota_mb = data['quota_mb']

    if data.get('password'):
        user.set_password(data['password'])

    try:
        db.session.commit()
        log_admin_action('UPDATE_USER', f"user:{user.username}")
        return jsonify({"msg": "Utilisateur modifié avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la modification"}), 500

@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    current_user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if user.id == current_user_id:
        return jsonify({"msg": "Impossible de supprimer votre propre compte"}), 400

    try:
        db.session.delete(user)
        db.session.commit()
        log_admin_action('DELETE_USER', f"user:{user.username}")
        return jsonify({"msg": "Utilisateur supprimé avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur interne lors de la suppression"}), 500

# ------------------------ GROUPES ------------------------

@admin_bp.route('/groups', methods=['GET'])
@admin_required
def get_all_groups():
    groups = Group.query.all()
    groups_data = []
    for group in groups:
        groups_data.append({
            'id': group.id,
            'name': group.name,
            'users': [{'id': user.id, 'username': user.username} for user in group.users]
        })
    return jsonify(groups_data), 200

@admin_bp.route('/groups', methods=['POST'])
@admin_required
def create_group():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"msg": "Nom du groupe requis"}), 400

    if Group.query.filter_by(name=data['name']).first():
        return jsonify({"msg": "Ce groupe existe déjà"}), 409

    group = Group(name=data['name'])
    try:
        db.session.add(group)
        db.session.commit()
        log_admin_action('CREATE_GROUP', f"group:{group.name}")
        return jsonify({"msg": "Groupe créé avec succès", "group": {"id": group.id, "name": group.name}}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la création"}), 500

@admin_bp.route('/groups/<int:group_id>', methods=['PUT'])
@admin_required
def update_group(group_id):
    group = Group.query.get_or_404(group_id)
    data = request.get_json()

    if data.get('name') and data['name'] != group.name:
        if Group.query.filter_by(name=data['name']).first():
            return jsonify({"msg": "Ce nom de groupe existe déjà"}), 409
        group.name = data['name']

    try:
        db.session.commit()
        log_admin_action('UPDATE_GROUP', f"group:{group.name}")
        return jsonify({"msg": "Groupe modifié avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la modification"}), 500

@admin_bp.route('/groups/<int:group_id>', methods=['DELETE'])
@admin_required
def delete_group(group_id):
    group = Group.query.get_or_404(group_id)
    group_name = group.name
    try:
        db.session.delete(group)
        db.session.commit()
        log_admin_action('DELETE_GROUP', f"group:{group_name}")
        return jsonify({"msg": "Groupe supprimé avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@admin_bp.route('/groups/<int:group_id>/users', methods=['POST'])
@admin_required
def add_user_to_group(group_id):
    group = Group.query.get_or_404(group_id)
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"msg": "ID utilisateur requis"}), 400

    user = User.query.get_or_404(user_id)
    if user in group.users:
        return jsonify({"msg": "L'utilisateur est déjà dans ce groupe"}), 409

    try:
        group.users.append(user)
        db.session.commit()
        log_admin_action('ADD_USER_TO_GROUP', f"user:{user.username} -> group:{group.name}")
        return jsonify({"msg": "Utilisateur ajouté au groupe avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de l'ajout"}), 500

@admin_bp.route('/groups/<int:group_id>/users/<int:user_id>', methods=['DELETE'])
@admin_required
def remove_user_from_group(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    user = User.query.get_or_404(user_id)
    if user not in group.users:
        return jsonify({"msg": "L'utilisateur n'est pas dans ce groupe"}), 404

    try:
        group.users.remove(user)
        db.session.commit()
        log_admin_action('REMOVE_USER_FROM_GROUP', f"user:{user.username} <- group:{group.name}")
        return jsonify({"msg": "Utilisateur retiré du groupe avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

# ------------------------ DOSSIERS ET FICHIERS ------------------------

@admin_bp.route('/folders', methods=['GET'])
@admin_required
def get_all_folders():
    folders = Folder.query.all()
    folders_data = []
    for folder in folders:
        folders_data.append({
            'id': folder.id,
            'name': folder.name,
            'owner': folder.owner.username,
            'parent_id': folder.parent_id,
            'created_at': folder.created_at.isoformat()
        })
    return jsonify(folders_data), 200

@admin_bp.route('/folders', methods=['POST'])
@admin_required
def create_folder_route():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"msg": "Nom du dossier requis"}), 400

    parent_id = data.get('parent_id')
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    claims = get_jwt()
    if claims.get('role', '').upper() != 'ADMIN' and parent_id:
        parent_folder = Folder.query.get(parent_id)
        perm = parent_folder.get_effective_permissions(user)
        if not perm or not perm.can_write:
            return jsonify({"msg": "Permission refusée"}), 403

    relative_path = data['name']
    if parent_id:
        parent_folder = Folder.query.get(parent_id)
        relative_path = f"{parent_folder.path}/{data['name']}"

    physical_path = create_folder(relative_path)
    folder = Folder(name=data['name'], owner_id=user.id, parent_id=parent_id, path=relative_path)
    db.session.add(folder)
    db.session.commit()
    log_admin_action('CREATE_FOLDER', f"folder:{folder.name}")

    return jsonify({"msg": "Dossier créé", "id": folder.id, "path": folder.path, "physical_path": physical_path})

@admin_bp.route('/folders/<int:folder_id>', methods=['DELETE'])
@admin_required
def delete_folder(folder_id):
    folder = Folder.query.get_or_404(folder_id)
    folder_name = folder.name
    try:
        db.session.delete(folder)
        db.session.commit()
        log_admin_action('DELETE_FOLDER', f"folder:{folder_name}")
        return jsonify({"msg": "Dossier supprimé avec succès"}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Erreur lors de la suppression"}), 500

@admin_bp.route('/files', methods=['GET'])
@admin_required
def get_all_files():
    files = File.query.all()
    files_data = []
    for file in files:
        files_data.append({
            'id': file.id,
            'name': file.name,
            'path': file.path,
            'size_kb': file.size_kb,
            'owner': file.owner.username,
            'folder': file.folder.name if file.folder else None,
            'created_at': file.created_at.isoformat()
        })
    return jsonify(files_data), 200

# ------------------------ LOGS ET STATISTIQUES ------------------------

@admin_bp.route('/logs', methods=['GET'])
@admin_required
def get_access_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    logs_data = []
    for log in logs.items:
        logs_data.append({
            'id': log.id,
            'user': log.user.username,
            'action': log.action,
            'target': log.target,
            'timestamp': log.timestamp.isoformat()
        })
    return jsonify({'logs': logs_data, 'total': logs.total, 'pages': logs.pages, 'current_page': logs.page}), 200

@admin_bp.route('/stats', methods=['GET'])
@admin_required
def get_statistics():
    """Get statistics - optionally sync with NAS first"""
    sync_with_nas = request.args.get('sync', 'false').lower() == 'true'
    
    try:
        if sync_with_nas:
            # Import here to avoid circular imports
            from services.nas_sync_service import nas_sync_service
            
            # Perform sync and get real statistics
            sync_result = nas_sync_service.full_sync(dry_run=False)
            if sync_result['success']:
                stats = nas_sync_service.get_real_statistics()
                stats['sync_performed'] = True
                stats['sync_stats'] = sync_result['stats']
            else:
                # Fallback to database stats if sync fails
                stats = {
                    'total_users': User.query.count(),
                    'total_groups': Group.query.count(),
                    'total_folders': Folder.query.count(),
                    'total_files': File.query.count(),
                    'admin_users': User.query.filter_by(role='ADMIN').count(),
                    'simple_users': User.query.filter_by(role='SIMPLE_USER').count(),
                    'sync_performed': False,
                    'sync_error': sync_result.get('message', 'Sync failed')
                }
        else:
            # Regular database statistics
            stats = {
                'total_users': User.query.count(),
                'total_groups': Group.query.count(),
                'total_folders': Folder.query.count(),
                'total_files': File.query.count(),
                'admin_users': User.query.filter_by(role='ADMIN').count(),
                'simple_users': User.query.filter_by(role='SIMPLE_USER').count(),
                'sync_performed': False
            }
        
        return jsonify(stats), 200
        
    except Exception as e:
        # Fallback to basic stats if anything fails
        stats = {
            'total_users': User.query.count(),
            'total_groups': Group.query.count(),
            'total_folders': Folder.query.count(),
            'total_files': File.query.count(),
            'admin_users': User.query.filter_by(role='ADMIN').count(),
            'simple_users': User.query.filter_by(role='SIMPLE_USER').count(),
            'sync_performed': False,
            'error': str(e)
        }
        return jsonify(stats), 200

@admin_bp.route('/sync-nas', methods=['POST'])
@admin_required
def sync_with_nas():
    """Synchronize database with NAS content"""
    data = request.get_json() or {}
    dry_run = data.get('dry_run', False)
    max_depth = data.get('max_depth', 10)
    
    try:
        from services.nas_sync_service import nas_sync_service
        
        result = nas_sync_service.full_sync(
            max_depth=max_depth,
            default_owner_id=1,  # Default to admin user
            dry_run=dry_run
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': result['message'],
                'stats': result['stats'],
                'nas_structure': result.get('nas_structure', {}),
                'db_structure': result.get('db_structure', {})
            }), 200
        else:
            # Check if it's a connection issue
            status_code = 400 if result.get('nas_accessible') == False else 500
            return jsonify({
                'success': False,
                'message': result['message'],
                'stats': result['stats'],
                'nas_accessible': result.get('nas_accessible', True)
            }), status_code
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Sync failed: {str(e)}',
            'error': str(e)
        }), 500

@admin_bp.route('/nas-status', methods=['GET'])
@admin_required
def get_nas_status():
    """Get NAS connection status and basic info"""
    try:
        from services.nas_sync_service import nas_sync_service
        
        # Set a shorter timeout for connection test
        import socket
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5.0)  # 5 second timeout
        
        try:
            is_connected = nas_sync_service.test_nas_connection()
            
            if is_connected:
                # Get basic NAS info
                client = nas_sync_service._get_smb_client()
                test_result = client.test_connection()
                
                return jsonify({
                    'connected': True,
                    'server_info': test_result.get('server_info', {}),
                    'root_files_count': test_result.get('root_files_count', 0),
                    'message': 'NAS connection successful'
                }), 200
            else:
                return jsonify({
                    'connected': False,
                    'message': 'NAS not accessible - check network connection to work environment',
                    'errors': nas_sync_service.sync_stats.get('errors', [])
                }), 200
                
        finally:
            socket.setdefaulttimeout(original_timeout)
            
    except Exception as e:
        return jsonify({
            'connected': False,
            'message': f'NAS connection test failed: {str(e)}',
            'error': str(e),
            'suggestion': 'Make sure you are connected to the work network'
        }), 200  # Return 200 instead of 500 for connection issues
