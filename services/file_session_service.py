# services/file_session_service.py

import os
import uuid
import shutil
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class FileSessionService:
    """Service for managing file editing sessions with server-side caching"""
    
    def __init__(self, cache_dir: str = None):
        self.cache_dir = Path(cache_dir or os.path.join(os.getcwd(), 'file_cache'))
        self.sessions_dir = self.cache_dir / 'sessions'
        self.metadata_dir = self.cache_dir / 'metadata'
        
        # Create cache directories
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Active sessions tracking
        self.active_sessions = {}
    
    def create_session(self, file_path: str, user_id: int, nas_path: str) -> Dict[str, Any]:
        """
        Create a new file editing session
        
        Args:
            file_path: Path to the file in the NAS
            user_id: ID of the user opening the file
            nas_path: Full NAS path to the file
            
        Returns:
            Dictionary with session information
        """
        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            
            # Create session directory
            session_path = self.sessions_dir / session_id
            session_path.mkdir(parents=True, exist_ok=True)
            
            # Copy file from NAS to cache
            file_name = os.path.basename(file_path)
            cached_file_path = session_path / file_name
            
            # Copy the file
            shutil.copy2(nas_path, cached_file_path)
            
            # Get file stats
            file_stats = os.stat(cached_file_path)
            
            # Create session metadata
            metadata = {
                'session_id': session_id,
                'user_id': user_id,
                'original_path': file_path,
                'nas_path': nas_path,
                'cached_file_path': str(cached_file_path),
                'file_name': file_name,
                'file_size': file_stats.st_size,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'last_accessed': datetime.now(timezone.utc).isoformat(),
                'last_modified': datetime.now(timezone.utc).isoformat(),
                'last_synced': datetime.now(timezone.utc).isoformat(),
                'is_modified': False,
                'sync_pending': False,
                'is_active': True
            }
            
            # Save metadata
            self._save_metadata(session_id, metadata)
            
            # Track active session
            self.active_sessions[session_id] = metadata
            
            logger.info(f"Created session {session_id} for file {file_path} by user {user_id}")
            
            return {
                'success': True,
                'session_id': session_id,
                'file_name': file_name,
                'file_size': file_stats.st_size,
                'created_at': metadata['created_at']
            }
            
        except Exception as e:
            logger.error(f"Error creating session for {file_path}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata"""
        try:
            # Check active sessions first
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
            
            # Load from disk
            metadata = self._load_metadata(session_id)
            if metadata:
                self.active_sessions[session_id] = metadata
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    def read_file_content(self, session_id: str) -> Optional[bytes]:
        """Read file content from cache"""
        try:
            metadata = self.get_session(session_id)
            if not metadata:
                logger.error(f"Session {session_id} not found")
                return None
            
            cached_file_path = Path(metadata['cached_file_path'])
            if not cached_file_path.exists():
                logger.error(f"Cached file not found: {cached_file_path}")
                return None
            
            # Update last accessed time
            metadata['last_accessed'] = datetime.now(timezone.utc).isoformat()
            self._save_metadata(session_id, metadata)
            
            # Read and return file content
            with open(cached_file_path, 'rb') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Error reading file content for session {session_id}: {e}")
            return None
    
    def write_file_content(self, session_id: str, content: bytes) -> bool:
        """Write file content to cache"""
        try:
            metadata = self.get_session(session_id)
            if not metadata:
                logger.error(f"Session {session_id} not found")
                return False
            
            cached_file_path = Path(metadata['cached_file_path'])
            
            # Write content to cached file
            with open(cached_file_path, 'wb') as f:
                f.write(content)
            
            # Update metadata
            metadata['last_modified'] = datetime.now(timezone.utc).isoformat()
            metadata['is_modified'] = True
            metadata['sync_pending'] = True
            self._save_metadata(session_id, metadata)
            
            logger.info(f"Updated cached file for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing file content for session {session_id}: {e}")
            return False
    
    def sync_to_nas(self, session_id: str) -> Dict[str, Any]:
        """Synchronize cached file back to NAS"""
        try:
            metadata = self.get_session(session_id)
            if not metadata:
                return {
                    'success': False,
                    'error': 'Session not found'
                }
            
            if not metadata.get('is_modified', False):
                return {
                    'success': True,
                    'message': 'No changes to sync'
                }
            
            cached_file_path = Path(metadata['cached_file_path'])
            nas_path = metadata['nas_path']
            
            # Copy file back to NAS
            shutil.copy2(cached_file_path, nas_path)
            
            # Update metadata
            metadata['last_synced'] = datetime.now(timezone.utc).isoformat()
            metadata['sync_pending'] = False
            self._save_metadata(session_id, metadata)
            
            logger.info(f"Synced session {session_id} to NAS: {nas_path}")
            
            return {
                'success': True,
                'message': 'File synced to NAS',
                'synced_at': metadata['last_synced']
            }
            
        except Exception as e:
            logger.error(f"Error syncing session {session_id} to NAS: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def close_session(self, session_id: str, sync_before_close: bool = True) -> Dict[str, Any]:
        """Close a file editing session"""
        try:
            metadata = self.get_session(session_id)
            if not metadata:
                return {
                    'success': False,
                    'error': 'Session not found'
                }
            
            # Sync to NAS if requested and there are pending changes
            sync_result = None
            if sync_before_close and metadata.get('sync_pending', False):
                sync_result = self.sync_to_nas(session_id)
                if not sync_result['success']:
                    logger.warning(f"Failed to sync session {session_id} before closing")
            
            # Mark session as inactive
            metadata['is_active'] = False
            metadata['closed_at'] = datetime.now(timezone.utc).isoformat()
            self._save_metadata(session_id, metadata)
            
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            logger.info(f"Closed session {session_id}")
            
            return {
                'success': True,
                'message': 'Session closed',
                'sync_result': sync_result
            }
            
        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cleanup_session(self, session_id: str) -> bool:
        """Clean up session files and metadata"""
        try:
            # Get metadata
            metadata = self.get_session(session_id)
            
            # Remove session directory
            session_path = self.sessions_dir / session_id
            if session_path.exists():
                shutil.rmtree(session_path)
            
            # Remove metadata file
            metadata_file = self.metadata_dir / f"{session_id}.json"
            if metadata_file.exists():
                metadata_file.unlink()
            
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            logger.info(f"Cleaned up session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
            return False
    
    def get_user_sessions(self, user_id: int, active_only: bool = True) -> list:
        """Get all sessions for a user"""
        try:
            sessions = []
            
            # Check all metadata files
            for metadata_file in self.metadata_dir.glob("*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    if metadata.get('user_id') == user_id:
                        if not active_only or metadata.get('is_active', False):
                            sessions.append(metadata)
                            
                except Exception as e:
                    logger.warning(f"Error reading metadata file {metadata_file}: {e}")
                    continue
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions for user {user_id}: {e}")
            return []
    
    def cleanup_inactive_sessions(self, inactivity_minutes: int = 60) -> int:
        """Clean up inactive sessions"""
        try:
            threshold = datetime.now(timezone.utc) - timedelta(minutes=inactivity_minutes)
            cleaned_count = 0
            
            for metadata_file in self.metadata_dir.glob("*.json"):
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    
                    # Check if session is inactive
                    if not metadata.get('is_active', False):
                        closed_at = datetime.fromisoformat(metadata.get('closed_at', metadata.get('created_at')))
                        
                        if closed_at < threshold:
                            session_id = metadata['session_id']
                            if self.cleanup_session(session_id):
                                cleaned_count += 1
                                
                except Exception as e:
                    logger.warning(f"Error processing metadata file {metadata_file}: {e}")
                    continue
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} inactive sessions")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up inactive sessions: {e}")
            return 0
    
    def _save_metadata(self, session_id: str, metadata: Dict[str, Any]):
        """Save session metadata to disk"""
        metadata_file = self.metadata_dir / f"{session_id}.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _load_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session metadata from disk"""
        metadata_file = self.metadata_dir / f"{session_id}.json"
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metadata for session {session_id}: {e}")
            return None


# Create singleton instance
file_session_service = FileSessionService()
