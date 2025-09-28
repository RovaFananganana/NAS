"""
Pytest configuration and fixtures for backend tests
"""
import pytest
import tempfile
import os
from datetime import datetime, timezone

from app import create_app
from extensions import db
from models.user import User
from models.user_activity import UserActivity, ActivityType


@pytest.fixture(scope='session')
def app():
    """Create application for testing"""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
        'JWT_SECRET_KEY': 'test-secret-key'
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()
        
    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Create application context"""
    with app.app_context():
        yield app


@pytest.fixture
def db_session(app_context):
    """Create database session for testing"""
    # Start a transaction
    connection = db.engine.connect()
    transaction = connection.begin()
    
    # Configure session to use this connection
    db.session.configure(bind=connection)
    
    yield db.session
    
    # Rollback transaction and close connection
    transaction.rollback()
    connection.close()
    db.session.remove()


@pytest.fixture
def test_user(db_session):
    """Create test user"""
    # Check if user already exists
    existing_user = User.query.filter_by(email='test@example.com').first()
    if existing_user:
        return existing_user
        
    user = User(
        username='test_user',
        email='test@example.com',
        role='user'
    )
    user.set_password('test_password')
    db_session.add(user)
    db_session.flush()  # Use flush instead of commit
    return user


@pytest.fixture
def admin_user(db_session):
    """Create admin user"""
    # Check if user already exists
    existing_user = User.query.filter_by(email='admin@example.com').first()
    if existing_user:
        return existing_user
        
    user = User(
        username='admin_user',
        email='admin@example.com',
        role='admin'
    )
    user.set_password('admin_password')
    db_session.add(user)
    db_session.flush()  # Use flush instead of commit
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """Get authentication headers for test user"""
    response = client.post('/auth/login', json={
        'username': 'test_user',
        'password': 'test_password'
    })
    
    assert response.status_code == 200
    token = response.get_json()['access_token']
    
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_auth_headers(client, admin_user):
    """Get authentication headers for admin user"""
    response = client.post('/auth/login', json={
        'username': 'admin_user',
        'password': 'admin_password'
    })
    
    assert response.status_code == 200
    token = response.get_json()['access_token']
    
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def sample_activities(db_session, test_user):
    """Create sample activities for testing"""
    activities = []
    
    # Create activities with different types and timestamps
    activity_data = [
        {
            'action': ActivityType.LOGIN.value,
            'resource': None,
            'details': {'login_method': 'password'},
            'success': True
        },
        {
            'action': ActivityType.NAVIGATION.value,
            'resource': '/documents',
            'details': {'folder': 'documents'},
            'success': True
        },
        {
            'action': ActivityType.FILE_DOWNLOAD.value,
            'resource': '/documents/test.pdf',
            'details': {'file_size': 1024},
            'success': True
        },
        {
            'action': ActivityType.FILE_UPLOAD.value,
            'resource': '/uploads/new_file.txt',
            'details': {'file_size': 512},
            'success': False  # Failed upload
        },
        {
            'action': ActivityType.LOGOUT.value,
            'resource': None,
            'details': {'logout_method': 'manual'},
            'success': True
        }
    ]
    
    for i, data in enumerate(activity_data):
        activity = UserActivity(
            user_id=test_user.id,
            **data,
            ip_address='127.0.0.1',
            user_agent='Test Agent',
            created_at=datetime.now(timezone.utc)
        )
        activities.append(activity)
        db_session.add(activity)
    
    db_session.flush()  # Use flush instead of commit
    return activities