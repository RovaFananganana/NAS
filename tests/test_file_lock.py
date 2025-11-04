"""
Tests for file locking mechanism
"""
import pytest
from datetime import datetime, timezone, timedelta
from models.file_lock import FileLock
from models.user import User
from extensions import db


@pytest.fixture
def test_user_2(db_session):
    """Create second test user for lock conflict testing"""
    existing_user = User.query.filter_by(email='test2@example.com').first()
    if existing_user:
        return existing_user
        
    user = User(
        username='test_user_2',
        email='test2@example.com',
        role='user'
    )
    user.set_password('test_password')
    db_session.add(user)
    db_session.flush()
    return user


class TestFileLockModel:
    """Test FileLock model methods"""
    
    def test_acquire_lock_success(self, db_session, test_user):
        """Test successful lock acquisition"""
        file_path = "/test/file.txt"
        session_id = "session-123"
        
        success, message, lock = FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id=session_id,
            lock_duration_minutes=30
        )
        
        assert success is True
        assert "acquired" in message.lower()
        assert lock.file_path == file_path
        assert lock.user_id == test_user.id
        assert lock.session_id == session_id
        assert lock.is_active is True
    
    def test_acquire_lock_conflict(self, db_session, test_user, test_user_2):
        """Test lock acquisition conflict when file is already locked"""
        file_path = "/test/file.txt"
        
        # User 1 acquires lock
        success1, message1, lock1 = FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id="session-1",
            lock_duration_minutes=30
        )
        
        assert success1 is True
        
        # User 2 tries to acquire lock on same file
        success2, message2, lock2 = FileLock.acquire_lock(
            user_id=test_user_2.id,
            file_path=file_path,
            session_id="session-2",
            lock_duration_minutes=30
        )
        
        assert success2 is False
        assert "locked by" in message2.lower()
        assert lock2.user_id == test_user.id  # Returns existing lock
    
    def test_acquire_lock_renew_same_user(self, db_session, test_user):
        """Test lock renewal when same user acquires lock again"""
        file_path = "/test/file.txt"
        
        # First acquisition
        success1, message1, lock1 = FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id="session-1",
            lock_duration_minutes=30
        )
        
        assert success1 is True
        original_expires_at = lock1.expires_at
        
        # Second acquisition with new session ID
        success2, message2, lock2 = FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id="session-2",
            lock_duration_minutes=30
        )
        
        assert success2 is True
        assert "renewed" in message2.lower()
        assert lock2.session_id == "session-2"
        assert lock2.expires_at > original_expires_at
    
    def test_release_lock_by_session_id(self, db_session, test_user):
        """Test releasing lock by session ID"""
        file_path = "/test/file.txt"
        session_id = "session-123"
        
        # Acquire lock
        FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id=session_id,
            lock_duration_minutes=30
        )
        
        # Release lock
        success = FileLock.release_lock(session_id=session_id)
        
        assert success is True
        
        # Verify lock is inactive
        lock = FileLock.query.filter_by(session_id=session_id).first()
        assert lock.is_active is False
    
    def test_release_lock_by_file_path(self, db_session, test_user):
        """Test releasing lock by file path and user ID"""
        file_path = "/test/file.txt"
        
        # Acquire lock
        FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id="session-123",
            lock_duration_minutes=30
        )
        
        # Release lock
        success = FileLock.release_lock(file_path=file_path, user_id=test_user.id)
        
        assert success is True
        
        # Verify lock is inactive
        lock = FileLock.query.filter_by(file_path=file_path).first()
        assert lock.is_active is False
    
    def test_check_lock_status_locked(self, db_session, test_user):
        """Test checking lock status for locked file"""
        file_path = "/test/file.txt"
        session_id = "session-123"
        
        # Acquire lock
        FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id=session_id,
            lock_duration_minutes=30
        )
        
        # Check status
        status = FileLock.check_lock_status(file_path)
        
        assert status['is_locked'] is True
        assert status['locked_by_user_id'] == test_user.id
        assert status['locked_by_username'] == test_user.username
        assert status['session_id'] == session_id
    
    def test_check_lock_status_unlocked(self, db_session):
        """Test checking lock status for unlocked file"""
        file_path = "/test/unlocked_file.txt"
        
        status = FileLock.check_lock_status(file_path)
        
        assert status['is_locked'] is False
        assert status['locked_by_user_id'] is None
        assert status['locked_by_username'] is None
    
    def test_release_expired_locks(self, db_session, test_user):
        """Test automatic release of expired locks"""
        file_path = "/test/file.txt"
        
        # Create an expired lock manually
        expired_lock = FileLock(
            file_path=file_path,
            user_id=test_user.id,
            session_id="expired-session",
            locked_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            is_active=True
        )
        db_session.add(expired_lock)
        db_session.flush()
        
        # Release expired locks
        count = FileLock.release_expired_locks()
        
        assert count == 1
        
        # Verify lock is inactive
        lock = FileLock.query.filter_by(session_id="expired-session").first()
        assert lock.is_active is False
    
    def test_release_inactive_locks(self, db_session, test_user):
        """Test automatic release of inactive locks"""
        file_path = "/test/file.txt"
        
        # Create an inactive lock manually
        inactive_lock = FileLock(
            file_path=file_path,
            user_id=test_user.id,
            session_id="inactive-session",
            locked_at=datetime.now(timezone.utc) - timedelta(hours=1),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            last_activity_at=datetime.now(timezone.utc) - timedelta(minutes=20),
            is_active=True
        )
        db_session.add(inactive_lock)
        db_session.flush()
        
        # Release inactive locks (15 minutes threshold)
        count = FileLock.release_inactive_locks(inactivity_minutes=15)
        
        assert count == 1
        
        # Verify lock is inactive
        lock = FileLock.query.filter_by(session_id="inactive-session").first()
        assert lock.is_active is False
    
    def test_update_activity(self, db_session, test_user):
        """Test updating lock activity timestamp"""
        file_path = "/test/file.txt"
        session_id = "session-123"
        
        # Acquire lock
        FileLock.acquire_lock(
            user_id=test_user.id,
            file_path=file_path,
            session_id=session_id,
            lock_duration_minutes=30
        )
        
        # Get original activity time
        lock = FileLock.query.filter_by(session_id=session_id).first()
        original_activity = lock.last_activity_at
        
        # Wait a moment and update activity
        import time
        time.sleep(0.1)
        
        success = FileLock.update_activity(session_id)
        
        assert success is True
        
        # Verify activity was updated
        lock = FileLock.query.filter_by(session_id=session_id).first()
        assert lock.last_activity_at > original_activity
    
    def test_get_user_locks(self, db_session, test_user):
        """Test getting all locks for a user"""
        # Create multiple locks
        for i in range(3):
            FileLock.acquire_lock(
                user_id=test_user.id,
                file_path=f"/test/file{i}.txt",
                session_id=f"session-{i}",
                lock_duration_minutes=30
            )
        
        # Get user locks
        locks = FileLock.get_user_locks(test_user.id, active_only=True)
        
        assert len(locks) >= 3
        for lock in locks:
            assert lock.user_id == test_user.id
            assert lock.is_active is True
    
    def test_release_all_user_locks(self, db_session, test_user):
        """Test releasing all locks for a user"""
        # Create multiple locks
        for i in range(3):
            FileLock.acquire_lock(
                user_id=test_user.id,
                file_path=f"/test/file{i}.txt",
                session_id=f"session-{i}",
                lock_duration_minutes=30
            )
        
        # Release all locks
        count = FileLock.release_all_user_locks(test_user.id)
        
        assert count >= 3
        
        # Verify all locks are inactive
        locks = FileLock.get_user_locks(test_user.id, active_only=True)
        assert len(locks) == 0


class TestFileLockAPI:
    """Test file lock API endpoints"""
    
    def test_acquire_lock_endpoint(self, client, auth_headers, test_user):
        """Test lock acquisition endpoint"""
        response = client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': '/test/file.txt',
                'session_id': 'session-123',
                'lock_duration_minutes': 30
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['lock']['file_path'] == '/test/file.txt'
    
    def test_acquire_lock_conflict_endpoint(self, client, auth_headers, test_user, test_user_2):
        """Test lock conflict via endpoint"""
        # User 1 acquires lock
        client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': '/test/file.txt',
                'session_id': 'session-1',
                'lock_duration_minutes': 30
            },
            headers=auth_headers
        )
        
        # Create auth headers for user 2
        response = client.post('/auth/login', json={
            'username': 'test_user_2',
            'password': 'test_password'
        })
        token = response.get_json()['access_token']
        auth_headers_2 = {'Authorization': f'Bearer {token}'}
        
        # User 2 tries to acquire lock
        response = client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': '/test/file.txt',
                'session_id': 'session-2',
                'lock_duration_minutes': 30
            },
            headers=auth_headers_2
        )
        
        assert response.status_code == 409
        data = response.get_json()
        assert data['success'] is False
    
    def test_release_lock_endpoint(self, client, auth_headers):
        """Test lock release endpoint"""
        # Acquire lock first
        client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': '/test/file.txt',
                'session_id': 'session-123',
                'lock_duration_minutes': 30
            },
            headers=auth_headers
        )
        
        # Release lock
        response = client.post(
            '/api/file-locks/release',
            json={'session_id': 'session-123'},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_check_lock_status_endpoint(self, client, auth_headers):
        """Test lock status check endpoint"""
        file_path = '/test/file.txt'
        
        # Acquire lock
        client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': file_path,
                'session_id': 'session-123',
                'lock_duration_minutes': 30
            },
            headers=auth_headers
        )
        
        # Check status
        response = client.get(
            f'/api/file-locks/status/{file_path}',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['is_locked'] is True
    
    def test_update_activity_endpoint(self, client, auth_headers):
        """Test activity update endpoint"""
        # Acquire lock
        client.post(
            '/api/file-locks/acquire',
            json={
                'file_path': '/test/file.txt',
                'session_id': 'session-123',
                'lock_duration_minutes': 30
            },
            headers=auth_headers
        )
        
        # Update activity
        response = client.post(
            '/api/file-locks/update-activity',
            json={'session_id': 'session-123'},
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_get_user_locks_endpoint(self, client, auth_headers):
        """Test get user locks endpoint"""
        # Acquire multiple locks
        for i in range(2):
            client.post(
                '/api/file-locks/acquire',
                json={
                    'file_path': f'/test/file{i}.txt',
                    'session_id': f'session-{i}',
                    'lock_duration_minutes': 30
                },
                headers=auth_headers
            )
        
        # Get user locks
        response = client.get(
            '/api/file-locks/user-locks',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert len(data['locks']) >= 2
    
    def test_release_all_user_locks_endpoint(self, client, auth_headers):
        """Test release all user locks endpoint"""
        # Acquire multiple locks
        for i in range(2):
            client.post(
                '/api/file-locks/acquire',
                json={
                    'file_path': f'/test/file{i}.txt',
                    'session_id': f'session-{i}',
                    'lock_duration_minutes': 30
                },
                headers=auth_headers
            )
        
        # Release all locks
        response = client.post(
            '/api/file-locks/release-all',
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['count'] >= 2
