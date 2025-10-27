# services/file_cache_service.py

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime, timezone, timedelta
import logging
from PIL import Image
import io
import base64

logger = logging.getLogger(__name__)

class FileCacheService:
    """Service for caching file conversions and thumbnails"""
    
    def __init__(self, cache_dir: str = None, max_cache_size_mb: int = 500):
        self.cache_dir = Path(cache_dir or os.path.join(os.getcwd(), 'cache'))
        self.max_cache_size_bytes = max_cache_size_mb * 1024 * 1024
        
        # Create cache directories
        self.conversion_cache_dir = self.cache_dir / 'conversions'
        self.thumbnail_cache_dir = self.cache_dir / 'thumbnails'
        self.metadata_cache_dir = self.cache_dir / 'metadata'
        
        for cache_dir in [self.conversion_cache_dir, self.thumbnail_cache_dir, self.metadata_cache_dir]:
            cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_size': 0
        }
        
        # Load existing cache index
        self.cache_index = self._load_cache_index()
    
    def _get_file_hash(self, file_path: str) -> str:
        """Generate a hash for the file based on path and modification time"""
        try:
            stat = os.stat(file_path)
            content = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
            return hashlib.md5(content.encode()).hexdigest()
        except OSError:
            # If file doesn't exist, use path only
            return hashlib.md5(file_path.encode()).hexdigest()
    
    def _load_cache_index(self) -> Dict[str, Dict]:
        """Load cache index from disk"""
        index_file = self.cache_dir / 'cache_index.json'
        try:
            if index_file.exists():
                with open(index_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading cache index: {e}")
        
        return {}
    
    def _save_cache_index(self):
        """Save cache index to disk"""
        index_file = self.cache_dir / 'cache_index.json'
        try:
            with open(index_file, 'w') as f:
                json.dump(self.cache_index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache index: {e}")
    
    def _get_cache_entry_path(self, cache_type: str, file_hash: str, extension: str = '') -> Path:
        """Get the path for a cache entry"""
        cache_dirs = {
            'conversion': self.conversion_cache_dir,
            'thumbnail': self.thumbnail_cache_dir,
            'metadata': self.metadata_cache_dir
        }
        
        cache_dir = cache_dirs.get(cache_type, self.cache_dir)
        filename = f"{file_hash}{extension}"
        return cache_dir / filename
    
    def _update_cache_stats(self, file_path: Path, operation: str):
        """Update cache statistics"""
        if operation == 'add' and file_path.exists():
            self.stats['total_size'] += file_path.stat().st_size
        elif operation == 'remove' and file_path.exists():
            self.stats['total_size'] -= file_path.stat().st_size
    
    def _cleanup_cache(self):
        """Clean up cache if it exceeds size limit"""
        if self.stats['total_size'] <= self.max_cache_size_bytes:
            return
        
        # Sort cache entries by last access time (oldest first)
        entries = []
        for file_hash, entry in self.cache_index.items():
            entries.append((entry.get('last_access', 0), file_hash, entry))
        
        entries.sort(key=lambda x: x[0])
        
        # Remove oldest entries until we're under the limit
        for _, file_hash, entry in entries:
            if self.stats['total_size'] <= self.max_cache_size_bytes * 0.8:  # 80% of limit
                break
            
            self._remove_cache_entry(file_hash)
            self.stats['evictions'] += 1
    
    def _remove_cache_entry(self, file_hash: str):
        """Remove a cache entry and its files"""
        if file_hash not in self.cache_index:
            return
        
        entry = self.cache_index[file_hash]
        
        # Remove all associated files
        for cache_type in ['conversion', 'thumbnail', 'metadata']:
            if cache_type in entry:
                file_path = Path(entry[cache_type]['path'])
                if file_path.exists():
                    try:
                        file_path.unlink()
                        self._update_cache_stats(file_path, 'remove')
                    except OSError as e:
                        logger.warning(f"Error removing cache file {file_path}: {e}")
        
        # Remove from index
        del self.cache_index[file_hash]
    
    def get_conversion_cache(self, file_path: str, conversion_type: str) -> Optional[Dict[str, Any]]:
        """Get cached conversion result"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_{conversion_type}"
        
        if cache_key in self.cache_index:
            entry = self.cache_index[cache_key]
            cache_file = Path(entry['conversion']['path'])
            
            if cache_file.exists():
                try:
                    # Update last access time
                    entry['last_access'] = time.time()
                    self.stats['hits'] += 1
                    
                    # Load cached content
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    return {
                        'content': content,
                        'metadata': entry.get('metadata', {}),
                        'cached_at': entry.get('cached_at'),
                        'conversion_type': conversion_type
                    }
                except Exception as e:
                    logger.warning(f"Error reading cache file {cache_file}: {e}")
                    self._remove_cache_entry(cache_key)
        
        self.stats['misses'] += 1
        return None
    
    def set_conversion_cache(self, file_path: str, conversion_type: str, content: str, metadata: Dict = None):
        """Cache conversion result"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_{conversion_type}"
        
        # Determine file extension based on conversion type
        extensions = {
            'html': '.html',
            'text': '.txt',
            'json': '.json',
            'xml': '.xml'
        }
        extension = extensions.get(conversion_type, '.cache')
        
        cache_file = self._get_cache_entry_path('conversion', cache_key, extension)
        
        try:
            # Write content to cache file
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Update cache index
            self.cache_index[cache_key] = {
                'file_path': file_path,
                'conversion_type': conversion_type,
                'cached_at': time.time(),
                'last_access': time.time(),
                'conversion': {
                    'path': str(cache_file),
                    'size': cache_file.stat().st_size
                },
                'metadata': metadata or {}
            }
            
            self._update_cache_stats(cache_file, 'add')
            self._cleanup_cache()
            self._save_cache_index()
            
        except Exception as e:
            logger.error(f"Error caching conversion for {file_path}: {e}")
    
    def get_thumbnail_cache(self, file_path: str, size: tuple = (200, 200)) -> Optional[str]:
        """Get cached thumbnail as base64 string"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_thumb_{size[0]}x{size[1]}"
        
        if cache_key in self.cache_index:
            entry = self.cache_index[cache_key]
            cache_file = Path(entry['thumbnail']['path'])
            
            if cache_file.exists():
                try:
                    # Update last access time
                    entry['last_access'] = time.time()
                    self.stats['hits'] += 1
                    
                    # Load and encode thumbnail
                    with open(cache_file, 'rb') as f:
                        thumbnail_data = f.read()
                    
                    return base64.b64encode(thumbnail_data).decode('utf-8')
                    
                except Exception as e:
                    logger.warning(f"Error reading thumbnail cache {cache_file}: {e}")
                    self._remove_cache_entry(cache_key)
        
        self.stats['misses'] += 1
        return None
    
    def set_thumbnail_cache(self, file_path: str, thumbnail_data: bytes, size: tuple = (200, 200)):
        """Cache thumbnail data"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_thumb_{size[0]}x{size[1]}"
        
        cache_file = self._get_cache_entry_path('thumbnail', cache_key, '.jpg')
        
        try:
            # Write thumbnail to cache file
            with open(cache_file, 'wb') as f:
                f.write(thumbnail_data)
            
            # Update cache index
            self.cache_index[cache_key] = {
                'file_path': file_path,
                'cached_at': time.time(),
                'last_access': time.time(),
                'thumbnail': {
                    'path': str(cache_file),
                    'size': cache_file.stat().st_size,
                    'dimensions': size
                }
            }
            
            self._update_cache_stats(cache_file, 'add')
            self._cleanup_cache()
            self._save_cache_index()
            
        except Exception as e:
            logger.error(f"Error caching thumbnail for {file_path}: {e}")
    
    def generate_thumbnail(self, file_path: str, size: tuple = (200, 200)) -> Optional[str]:
        """Generate thumbnail for image files"""
        # Check cache first
        cached_thumbnail = self.get_thumbnail_cache(file_path, size)
        if cached_thumbnail:
            return cached_thumbnail
        
        try:
            # Generate thumbnail
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Create thumbnail
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Save to bytes
                thumbnail_io = io.BytesIO()
                img.save(thumbnail_io, format='JPEG', quality=85, optimize=True)
                thumbnail_data = thumbnail_io.getvalue()
                
                # Cache the thumbnail
                self.set_thumbnail_cache(file_path, thumbnail_data, size)
                
                # Return base64 encoded thumbnail
                return base64.b64encode(thumbnail_data).decode('utf-8')
                
        except Exception as e:
            logger.error(f"Error generating thumbnail for {file_path}: {e}")
            return None
    
    def get_metadata_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get cached file metadata"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_metadata"
        
        if cache_key in self.cache_index:
            entry = self.cache_index[cache_key]
            cache_file = Path(entry['metadata']['path'])
            
            if cache_file.exists():
                try:
                    # Update last access time
                    entry['last_access'] = time.time()
                    self.stats['hits'] += 1
                    
                    # Load cached metadata
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    return metadata
                    
                except Exception as e:
                    logger.warning(f"Error reading metadata cache {cache_file}: {e}")
                    self._remove_cache_entry(cache_key)
        
        self.stats['misses'] += 1
        return None
    
    def set_metadata_cache(self, file_path: str, metadata: Dict[str, Any]):
        """Cache file metadata"""
        file_hash = self._get_file_hash(file_path)
        cache_key = f"{file_hash}_metadata"
        
        cache_file = self._get_cache_entry_path('metadata', cache_key, '.json')
        
        try:
            # Write metadata to cache file
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)
            
            # Update cache index
            self.cache_index[cache_key] = {
                'file_path': file_path,
                'cached_at': time.time(),
                'last_access': time.time(),
                'metadata': {
                    'path': str(cache_file),
                    'size': cache_file.stat().st_size
                }
            }
            
            self._update_cache_stats(cache_file, 'add')
            self._cleanup_cache()
            self._save_cache_index()
            
        except Exception as e:
            logger.error(f"Error caching metadata for {file_path}: {e}")
    
    def clear_cache(self, file_path: str = None):
        """Clear cache for a specific file or all cache"""
        if file_path:
            # Clear cache for specific file
            file_hash = self._get_file_hash(file_path)
            entries_to_remove = []
            
            for cache_key, entry in self.cache_index.items():
                if entry.get('file_path') == file_path or cache_key.startswith(file_hash):
                    entries_to_remove.append(cache_key)
            
            for cache_key in entries_to_remove:
                self._remove_cache_entry(cache_key)
        else:
            # Clear all cache
            for cache_key in list(self.cache_index.keys()):
                self._remove_cache_entry(cache_key)
            
            self.stats = {
                'hits': 0,
                'misses': 0,
                'evictions': 0,
                'total_size': 0
            }
        
        self._save_cache_index()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        hit_rate = 0
        total_requests = self.stats['hits'] + self.stats['misses']
        if total_requests > 0:
            hit_rate = (self.stats['hits'] / total_requests) * 100
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'hit_rate': round(hit_rate, 2),
            'evictions': self.stats['evictions'],
            'total_size_mb': round(self.stats['total_size'] / (1024 * 1024), 2),
            'max_size_mb': round(self.max_cache_size_bytes / (1024 * 1024), 2),
            'entries_count': len(self.cache_index),
            'cache_dirs': {
                'conversions': str(self.conversion_cache_dir),
                'thumbnails': str(self.thumbnail_cache_dir),
                'metadata': str(self.metadata_cache_dir)
            }
        }
    
    def cleanup_expired_entries(self, max_age_hours: int = 24):
        """Remove cache entries older than specified hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        expired_entries = []
        for cache_key, entry in self.cache_index.items():
            if current_time - entry.get('cached_at', 0) > max_age_seconds:
                expired_entries.append(cache_key)
        
        for cache_key in expired_entries:
            self._remove_cache_entry(cache_key)
        
        if expired_entries:
            self._save_cache_index()
            logger.info(f"Cleaned up {len(expired_entries)} expired cache entries")
        
        return len(expired_entries)

# Create singleton instance
file_cache_service = FileCacheService()