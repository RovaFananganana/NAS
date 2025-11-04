# File Session Cache Service

## Overview

The `FileCacheService` class provides session-based file caching for the file viewer/editor system. It manages temporary copies of files from the NAS on the server side, enabling safe editing without downloading files to client machines.

## Key Features

- **Session Management**: Creates unique sessions for each file editing operation
- **File Caching**: Copies files from NAS to temporary server cache
- **Metadata Storage**: Stores session information in JSON files
- **File Locking**: Prevents concurrent editing conflicts
- **Auto-Cleanup**: Removes inactive sessions automatically
- **Sync to NAS**: Synchronizes changes back to the original NAS location

## Usage

```python
from services.file_session_cache_service import file_session_cache_service

# Create a cache session
session_id = file_session_cache_service.create_cache_session(
    user_id=1,
    file_path='documents/report.docx',
    nas_file_path='/mnt/nas/documents/report.docx'
)

# Get cached file path
cached_file = file_session_cache_service.get_cached_file(session_id)

# Update cached file
file_session_cache_service.update_cached_file(session_id, new_content)

# Sync changes back to NAS
file_session_cache_service.sync_to_nas(session_id)

# Cleanup when done
file_session_cache_service.cleanup_session(session_id, sync_before_cleanup=True)
```

## Cache Directory Structure

```
/tmp/nas_file_cache/
├── sessions/
│   ├── {session_id_1}/
│   │   ├── original_file
│   │   ├── metadata.json
│   │   └── lock_info.json (if locked)
│   └── {session_id_2}/
│       └── ...
└── cleanup.log
```

## API Methods

### Session Management
- `create_cache_session(user_id, file_path, nas_file_path)` - Create new session
- `get_cached_file(session_id)` - Get path to cached file
- `update_cached_file(session_id, content)` - Update cached file content
- `sync_to_nas(session_id)` - Sync changes back to NAS
- `cleanup_session(session_id, sync_before_cleanup)` - Remove session

### File Locking
- `acquire_lock(session_id, user_id, file_path)` - Lock file for editing
- `release_lock(session_id)` - Release file lock
- `is_file_locked(file_path)` - Check if file is locked

### Monitoring
- `get_session_info(session_id)` - Get session metadata
- `get_all_active_sessions()` - List all active sessions
- `get_cache_statistics()` - Get cache usage statistics
- `cleanup_inactive_sessions(max_age_minutes)` - Clean up old sessions

## Configuration

The service can be configured during initialization:

```python
cache_service = FileCacheService(
    cache_base_dir='/custom/cache/path',  # Default: /tmp/nas_file_cache
    max_inactivity_minutes=60             # Default: 60 minutes
)
```

## Testing

Run the test suite:

```bash
cd backend
python test_file_cache_service.py
```

## Next Steps

This service is ready for integration with:
- Task 8.2: File locking mechanism (database model)
- Task 8.3: Auto-sync service (periodic worker)
- Task 8.4: Cache cleanup service (scheduled cleanup)
- Task 9.2: Cache-aware file content API routes

## Requirements Coverage

This implementation satisfies:
- Requirement 9.1: File copying from NAS to cache
- Requirement 9.2: Unique session ID generation
- Requirement 9.3: Secure cache directory storage
- Requirement 9.4: User association with cached files
