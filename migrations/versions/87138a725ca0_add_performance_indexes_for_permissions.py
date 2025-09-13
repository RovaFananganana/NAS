"""add_performance_indexes_for_permissions

Revision ID: 87138a725ca0
Revises: 1fdffc19f9a1
Create Date: 2025-09-13 15:05:32.308921

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87138a725ca0'
down_revision = '1fdffc19f9a1'
branch_labels = None
depends_on = None


def upgrade():
    # Index for file_permissions table - optimize permission lookups
    op.create_index('idx_file_permissions_user_file', 'file_permissions', ['user_id', 'file_id'])
    op.create_index('idx_file_permissions_group_file', 'file_permissions', ['group_id', 'file_id'])
    op.create_index('idx_file_permissions_file_actions', 'file_permissions', 
                   ['file_id', 'can_read', 'can_write', 'can_delete', 'can_share'])
    
    # Index for folder_permissions table - optimize permission lookups
    op.create_index('idx_folder_permissions_user_folder', 'folder_permissions', ['user_id', 'folder_id'])
    op.create_index('idx_folder_permissions_group_folder', 'folder_permissions', ['group_id', 'folder_id'])
    op.create_index('idx_folder_permissions_folder_actions', 'folder_permissions', 
                   ['folder_id', 'can_read', 'can_write', 'can_delete', 'can_share'])
    
    # Index for user_group table - optimize group membership queries
    op.create_index('idx_user_group_user', 'user_group', ['user_id'])
    op.create_index('idx_user_group_group', 'user_group', ['group_id'])
    
    # Index for files table - optimize hierarchy traversal
    op.create_index('idx_files_folder_owner', 'files', ['folder_id', 'owner_id'])
    op.create_index('idx_files_owner', 'files', ['owner_id'])
    
    # Index for folders table - optimize hierarchy traversal
    op.create_index('idx_folders_parent_owner', 'folders', ['parent_id', 'owner_id'])
    op.create_index('idx_folders_owner', 'folders', ['owner_id'])
    op.create_index('idx_folders_parent', 'folders', ['parent_id'])


def downgrade():
    # Drop indexes in reverse order
    op.drop_index('idx_folders_parent', 'folders')
    op.drop_index('idx_folders_owner', 'folders')
    op.drop_index('idx_folders_parent_owner', 'folders')
    
    op.drop_index('idx_files_owner', 'files')
    op.drop_index('idx_files_folder_owner', 'files')
    
    op.drop_index('idx_user_group_group', 'user_group')
    op.drop_index('idx_user_group_user', 'user_group')
    
    op.drop_index('idx_folder_permissions_folder_actions', 'folder_permissions')
    op.drop_index('idx_folder_permissions_group_folder', 'folder_permissions')
    op.drop_index('idx_folder_permissions_user_folder', 'folder_permissions')
    
    op.drop_index('idx_file_permissions_file_actions', 'file_permissions')
    op.drop_index('idx_file_permissions_group_file', 'file_permissions')
    op.drop_index('idx_file_permissions_user_file', 'file_permissions')
