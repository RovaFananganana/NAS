import os
import sys

# Ensure backend root is on sys.path when running this script directly
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app import create_app
from models.role_permission import RolePermission
from models.permission import Permission
from models.user import User

app = create_app()
with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        print('admin:', admin.username, 'role:', admin.role)
    else:
        print('admin: not found')

    rps = RolePermission.query.filter_by(role='ADMIN').all()
    print('ADMIN RolePermission count:', len(rps))
    for rp in rps[:200]:
        try:
            print(rp.permission.resource, rp.permission.action)
        except Exception as e:
            print('roleperm error:', e)

    p_update = Permission.query.filter_by(resource='file', action='UPDATE').first()
    print('file UPDATE permission id:', p_update.id if p_update else None)
