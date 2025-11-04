# services/file_session_cache_service.py

import os
import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

class FileCacheService:
    """
    Service for managing file editing sessions with server-side caching.
    Handles copying files from NAS to temporary cache, session management,
    and metadata storage for file editing workflows.
    """
    
    def __init__(self, cache_base_dir: str = None, max_inactivity_minutes: int = 60):
        """
        Initialize the FileCacheService
        
        Args:
            cache_base_dir: Base directory for cache storage (default: /tmp/nas_file_cache)
            max_inactivity_minutes: Maximum inactivity time before session cleanup
        """
        self.cache_base_dir = Path(cache_base_dir or '/tmp/nas_file_cache')
        self.sessions_dir = self.cache_base_dir / 'sessions'
        self.max_inactivity_minutes = max_inactivity_minutes
        
        # Create cache directory structure
        self._initialize_cache_directories()
        
        # Session tracking
        self.active_sessions = {}  # session_id -> session_info
        
        logger.info(f"FileCacheService initialized with cache dir: {self.cache_base_dir}")
    
    def _initialize_cache_directories(self):
        """Create necessary cache directory structure"""
        try:
            self.cache_base_dir.mkdir(parents=True, exist_ok=True)
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            
            # Create cleanup log file if it doesn't exist
            cleanup_log = self.cache_base_dir / 'cleanup.log'
            if not cleanup_log.exists():
                cleanup_log.touch()
            
            logger.info(f"Cache directories initialized at {self.cache_base_dir}")
        except Exception as e:
            logger.error(f"Error initializing cache directories: {e}")
            raise
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID"""
        return str(uuid.uuid4())
    
    def _get_session_dir(self, session_id: str) -> Path:
        """Get the directory path for a specific session"""
        return self.sessions_dir / session_id
    
    def _create_session_metadata(self, session_id: str, user_id: int, file_path: str, 
                                 original_nas_path: str) -> Dict:
        """
        Create metadata for a cache session
        
        Args:
            session_id: Unique session identifier
            user_id: ID of the user who opened the file
            file_path: Relative file path
            original_nas_path: Absolute path to the original file on NAS
            
        Returns:
            Dictionary containing session metadata
        """
        now = datetime.now(timezone.utc)
        
        metadata = {
            'session_id': session_id,
            'user_id': user_id,
            'file_path': file_path,
            'original_nas_path': original_nas_path,
            'cached_path': str(self._get_session_dir(session_id) / 'original_file'),
            'created_at': now.isoformat(),
            'last_accessed_at': now.isoformat(),
            'last_synced_at': now.isoformat(),
            'is_dirty': False,
            'is_locked': False,
            'locked_by': None
        }
        
        return metadata
    
    def _save_session_metadata(self, session_id: str, metadata: Dict):
        """Save session metadata to JSON file"""
        try:
            session_dir = self._get_session_dir(session_id)
            metadata_file = session_dir / 'metadata.json'
            
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            logger.debug(f"Session metadata saved for {session_id}")
        except Exception as e:
            logger.error(f"Error saving session metadata for {session_id}: {e}")
            raise
    
    def _load_session_metadata(self, session_id: str) -> Optional[Dict]:
        """Load session metadata from JSON file"""
        try:
            session_dir = self._get_session_dir(session_id)
            metadata_file = session_dir / 'metadata.json'
            
            if not metadata_file.exists():
                logger.warning(f"Metadata file not found for session {session_id}")
                return None
            
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            return metadata
        except Exception as e:
            logger.error(f"Error loading session metadata for {session_id}: {e}")
            return None
    
    def create_cache_session(self, user_id: int, file_path: str, nas_file_path: str) -> str:
        """
        Create a new cache session and copy file from NAS to cache
        
        Args:
            user_id: ID of the user opening the file
            file_path: Relative path of the file
            nas_file_path: Absolute path to the file on NAS
            
        Returns:
            session_id: Unique identifier for the cache session
            
        Raises:
            FileNotFoundError: If the source file doesn't exist
            IOError: If file copy fails
        """
        try:
            # Generate unique session ID
            session_id = self._generate_session_id()
            
            # Create session directory
            session_dir = self._get_session_dir(session_id)
            session_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy file from NAS to cache
            cached_file_path = session_dir / 'original_file'
            
            if not os.path.exists(nas_file_path):
                raise FileNotFoundError(f"Source file not found: {nas_file_path}")
            
            shutil.copy2(nas_file_path, cached_file_path)
            logger.info(f"File copied to cache: {nas_file_path} -> {cached_file_path}")
            
            # Create and save metadata
            metadata = self._create_session_metadata(
                session_id=session_id,
                user_id=user_id,
                file_path=file_path,
                original_nas_path=nas_file_path
            )
            self._save_session_metadata(session_id, metadata)
            
            # Track active session
            self.active_sessions[session_id] = metadata
            
            logger.info(f"Cache session created: {session_id} for user {user_id}")
            return session_id
            
        except Exception as e:
            logger.error(f"Error creating cache session: {e}")
            # Cleanup on failure
            if 'session_dir' in locals() and session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            raise
    
    def get_cached_file(self, session_id: str) -> str:
        """
        Get the path to the cached file for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Absolute path to the cached file
            
        Raises:
            ValueError: If session doesn't exist
        """
        metadata = self._load_session_metadata(session_id)
        
        if not metadata:
            raise ValueError(f"Session not found: {session_id}")
        
        cached_file_path = Path(metadata['cached_path'])
        
        if not cached_file_path.exists():
            raise FileNotFoundError(f"Cached file not found for session {session_id}")
        
        # Update last accessed time
        metadata['last_accessed_at'] = datetime.now(timezone.utc).isoformat()
        self._save_session_metadata(session_id, metadata)
        
        return str(cached_file_path)
    
    def update_cached_file(self, session_id: str, content: bytes) -> bool:
        """
        Update the cached file with new content
        
        Args:
            session_id: Session identifier
            content: New file content as bytes
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            metadata = self._load_session_metadata(session_id)
            
            if not metadata:
                logger.error(f"Session not found: {session_id}")
                return False
            
            cached_file_path = Path(metadata['cached_path'])
            
            # Write new content to cached file
            with open(cached_file_path, 'wb') as f:
                f.write(content)
            
            # Update metadata
            now = datetime.now(timezone.utc).isoformat()
            metadata['last_accessed_at'] = now
            metadata['is_dirty'] = True
            self._save_session_metadata(session_id, metadata)
            
            logger.info(f"Cached file updated for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating cached file for session {session_id}: {e}")
            return False
    
    def sync_to_nas(self, session_id: str) -> bool:
        """
        Synchronize cached file back to NAS
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if sync successful, False otherwise
        """
        try:
            metadata = self._load_session_metadata(session_id)
            
            if not metadata:
                logger.error(f"Session not found: {session_id}")
                return False
            
            cached_file_path = Path(metadata['cached_path'])
            original_nas_path = metadata['original_nas_path']
            
            if not cached_file_path.exists():
                logger.error(f"Cached file not found: {cached_file_path}")
                return False
            
            # Copy cached file back to NAS
            shutil.copy2(cached_file_path, original_nas_path)
            
            # Update metadata
            now = datetime.now(timezone.utc).isoformat()
            metadata['last_synced_at'] = now
            metadata['last_accessed_at'] = now
            metadata['is_dirty'] = False
            self._save_session_metadata(session_id, metadata)
            
            logger.info(f"File synced to NAS for session {session_id}: {original_nas_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing to NAS for session {session_id}: {e}")
            return False
    
    def cleanup_session(self, session_id: str, sync_before_cleanup: bool = True) -> bool:
        """
        Clean up a cache session and remove cached files
        
        Args:
            session_id: Session identifier
            sync_before_cleanup: If True, sync to NAS before cleanup
            
        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            metadata = self._load_session_metadata(session_id)
            
            if not metadata:
                logger.warning(f"Session not found for cleanup: {session_id}")
                return False
            
            # Sync to NAS if requested and file is dirty
            if sync_before_cleanup and metadata.get('is_dirty', False):
                logger.info(f"Syncing dirty file before cleanup: {session_id}")
                self.sync_to_nas(session_id)
            
            # Remove session directory
            session_dir = self._get_session_dir(session_id)
            if session_dir.exists():
                shutil.rmtree(session_dir)
                logger.info(f"Session directory removed: {session_dir}")
            
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            # Log cleanup
            self._log_cleanup(session_id, metadata)
            
            logger.info(f"Session cleaned up: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
            return False
    
    def cleanup_inactive_sessions(self, max_age_minutes: int = None) -> int:
        """
        Clean up sessions that have been inactive for too long
        
        Args:
            max_age_minutes: Maximum inactivity time in minutes (uses default if None)
            
        Returns:
            Number of sessions cleaned up
        """
        if max_age_minutes is None:
            max_age_minutes = self.max_inactivity_minutes
        
        cleaned_count = 0
        current_time = datetime.now(timezone.utc)
        max_age = timedelta(minutes=max_age_minutes)
        
        try:
            # Iterate through all session directories
            if not self.sessions_dir.exists():
                return 0
            
            for session_dir in self.sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                
                session_id = session_dir.name
                metadata = self._load_session_metadata(session_id)
                
                if not metadata:
                    # Orphaned session directory, remove it
                    shutil.rmtree(session_dir, ignore_errors=True)
                    cleaned_count += 1
                    continue
                
                # Check last accessed time
                last_accessed = datetime.fromisoformat(metadata['last_accessed_at'])
                
                if current_time - last_accessed > max_age:
                    logger.info(f"Cleaning up inactive session: {session_id}")
                    if self.cleanup_session(session_id, sync_before_cleanup=True):
                        cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} inactive sessions")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during inactive session cleanup: {e}")
            return cleaned_count
    
    def _log_cleanup(self, session_id: str, metadata: Dict):
        """Log cleanup operation to cleanup.log"""
        try:
            cleanup_log = self.cache_base_dir / 'cleanup.log'
            
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'session_id': session_id,
                'user_id': metadata.get('user_id'),
                'file_path': metadata.get('file_path'),
                'was_dirty': metadata.get('is_dirty', False),
                'last_synced': metadata.get('last_synced_at')
            }
            
            with open(cleanup_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            logger.error(f"Error logging cleanup: {e}")
    
    def is_file_locked(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a file is currently locked by an active session
        
        Args:
            file_path: Relative path of the file to check
            
        Returns:
            Tuple of (is_locked, locked_by_user_id)
        """
        try:
            # Check all active sessions
            for session_id, session_info in self.active_sessions.items():
                if session_info.get('file_path') == file_path and session_info.get('is_locked'):
                    return True, str(session_info.get('user_id'))
            
            # Also check session directories for persistence
            if self.sessions_dir.exists():
                for session_dir in self.sessions_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    metadata = self._load_session_metadata(session_dir.name)
                    if metadata and metadata.get('file_path') == file_path and metadata.get('is_locked'):
                        # Check if session is still active (not expired)
                        last_accessed = datetime.fromisoformat(metadata['last_accessed_at'])
                        if datetime.now(timezone.utc) - last_accessed < timedelta(minutes=self.max_inactivity_minutes):
                            return True, str(metadata.get('user_id'))
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking file lock for {file_path}: {e}")
            return False, None
    
    def acquire_lock(self, session_id: str, user_id: int, file_path: str) -> bool:
        """
        Acquire a lock on a file for editing
        
        Args:
            session_id: Session identifier
            user_id: ID of the user acquiring the lock
            file_path: Relative path of the file
            
        Returns:
            True if lock acquired, False if already locked
        """
        try:
            # Check if file is already locked
            is_locked, locked_by = self.is_file_locked(file_path)
            
            if is_locked and locked_by != str(user_id):
                logger.warning(f"File {file_path} is already locked by user {locked_by}")
                return False
            
            # Update session metadata with lock
            metadata = self._load_session_metadata(session_id)
            if not metadata:
                logger.error(f"Session not found: {session_id}")
                return False
            
            metadata['is_locked'] = True
            metadata['locked_by'] = user_id
            metadata['locked_at'] = datetime.now(timezone.utc).isoformat()
            self._save_session_metadata(session_id, metadata)
            
            # Update active sessions
            if session_id in self.active_sessions:
                self.active_sessions[session_id] = metadata
            
            # Save lock info to separate file for quick access
            lock_info_file = self._get_session_dir(session_id) / 'lock_info.json'
            lock_info = {
                'user_id': user_id,
                'file_path': file_path,
                'locked_at': metadata['locked_at']
            }
            with open(lock_info_file, 'w', encoding='utf-8') as f:
                json.dump(lock_info, f, indent=2)
            
            logger.info(f"Lock acquired for session {session_id} by user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error acquiring lock for session {session_id}: {e}")
            return False
    
    def release_lock(self, session_id: str) -> bool:
        """
        Release a lock on a file
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if lock released, False otherwise
        """
        try:
            metadata = self._load_session_metadata(session_id)
            
            if not metadata:
                logger.error(f"Session not found: {session_id}")
                return False
            
            # Update metadata
            metadata['is_locked'] = False
            metadata['locked_by'] = None
            metadata['unlocked_at'] = datetime.now(timezone.utc).isoformat()
            self._save_session_metadata(session_id, metadata)
            
            # Update active sessions
            if session_id in self.active_sessions:
                self.active_sessions[session_id] = metadata
            
            # Remove lock info file
            lock_info_file = self._get_session_dir(session_id) / 'lock_info.json'
            if lock_info_file.exists():
                lock_info_file.unlink()
            
            logger.info(f"Lock released for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error releasing lock for session {session_id}: {e}")
            return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        Get information about a cache session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with session information or None if not found
        """
        return self._load_session_metadata(session_id)
    
    def get_all_active_sessions(self) -> Dict[str, Dict]:
        """
        Get information about all active sessions
        
        Returns:
            Dictionary mapping session_id to session metadata
        """
        active_sessions = {}
        
        try:
            if not self.sessions_dir.exists():
                return active_sessions
            
            for session_dir in self.sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                
                session_id = session_dir.name
                metadata = self._load_session_metadata(session_id)
                
                if metadata:
                    # Check if session is still active
                    last_accessed = datetime.fromisoformat(metadata['last_accessed_at'])
                    if datetime.now(timezone.utc) - last_accessed < timedelta(minutes=self.max_inactivity_minutes):
                        active_sessions[session_id] = metadata
            
            return active_sessions
            
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return active_sessions
    
    def get_cache_statistics(self) -> Dict:
        """
        Get statistics about the cache
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            total_sessions = 0
            total_size_bytes = 0
            active_sessions_count = 0
            locked_files_count = 0
            
            if self.sessions_dir.exists():
                for session_dir in self.sessions_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    
                    total_sessions += 1
                    
                    # Calculate directory size
                    for file_path in session_dir.rglob('*'):
                        if file_path.is_file():
                            total_size_bytes += file_path.stat().st_size
                    
                    # Check if session is active
                    metadata = self._load_session_metadata(session_dir.name)
                    if metadata:
                        last_accessed = datetime.fromisoformat(metadata['last_accessed_at'])
                        if datetime.now(timezone.utc) - last_accessed < timedelta(minutes=self.max_inactivity_minutes):
                            active_sessions_count += 1
                            
                            if metadata.get('is_locked'):
                                locked_files_count += 1
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions_count,
                'locked_files': locked_files_count,
                'total_size_bytes': total_size_bytes,
                'total_size_mb': round(total_size_bytes / (1024 * 1024), 2),
                'cache_directory': str(self.cache_base_dir),
                'max_inactivity_minutes': self.max_inactivity_minutes
            }
            
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {
                'error': str(e)
            }


# Create singleton instance
file_session_cache_service = FileCacheService()
