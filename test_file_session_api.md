# Test des API de Session de Fichiers

## Endpoints disponibles

### 1. Ouvrir un fichier (créer une session)
```bash
POST /api/files/open
Authorization: Bearer <token>
Content-Type: application/json

{
  "file_path": "/test/document.txt",
  "mode": "edit"  # ou "view"
}
```

**Réponse:**
```json
{
  "success": true,
  "session_id": "uuid-here",
  "file_name": "document.txt",
  "file_size": 1024,
  "created_at": "2024-01-01T00:00:00Z",
  "mode": "edit",
  "lock_acquired": true,
  "lock_info": {...}
}
```

### 2. Lire le contenu du fichier
```bash
GET /api/files/session/<session_id>/content
Authorization: Bearer <token>
```

**Réponse:** Contenu binaire du fichier

### 3. Mettre à jour le contenu du fichier
```bash
PUT /api/files/session/<session_id>/content
Authorization: Bearer <token>
Content-Type: application/octet-stream

[Binary file content]
```

**Réponse:**
```json
{
  "success": true,
  "message": "Content updated",
  "last_modified": "2024-01-01T00:00:00Z",
  "sync_pending": true
}
```

### 4. Synchroniser vers le NAS
```bash
POST /api/files/session/<session_id>/sync
Authorization: Bearer <token>
```

**Réponse:**
```json
{
  "success": true,
  "message": "File synced to NAS",
  "synced_at": "2024-01-01T00:00:00Z"
}
```

### 5. Fermer la session
```bash
POST /api/files/session/<session_id>/close
Authorization: Bearer <token>
Content-Type: application/json

{
  "sync_before_close": true
}
```

**Réponse:**
```json
{
  "success": true,
  "message": "Session closed",
  "sync_result": {...}
}
```

### 6. Obtenir les informations de session
```bash
GET /api/files/session/<session_id>/info
Authorization: Bearer <token>
```

**Réponse:**
```json
{
  "session_id": "uuid",
  "file_name": "document.txt",
  "file_path": "/test/document.txt",
  "file_size": 1024,
  "is_modified": true,
  "sync_pending": true,
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z",
  "last_accessed": "2024-01-01T00:00:00Z",
  "last_modified": "2024-01-01T00:00:00Z",
  "last_synced": "2024-01-01T00:00:00Z"
}
```

### 7. Obtenir toutes les sessions de l'utilisateur
```bash
GET /api/files/sessions?active_only=true
Authorization: Bearer <token>
```

**Réponse:**
```json
{
  "sessions": [...]
}
```

## Flux de travail typique

1. **Ouvrir un fichier pour édition:**
   - POST `/api/files/open` avec `mode: "edit"`
   - Le système crée une session et acquiert un verrou
   - Retourne un `session_id`

2. **Lire le contenu:**
   - GET `/api/files/session/<session_id>/content`
   - Retourne le contenu du fichier depuis le cache

3. **Modifier le contenu:**
   - PUT `/api/files/session/<session_id>/content`
   - Met à jour le fichier dans le cache
   - Marque la session comme modifiée

4. **Synchroniser (optionnel):**
   - POST `/api/files/session/<session_id>/sync`
   - Copie les modifications vers le NAS

5. **Fermer la session:**
   - POST `/api/files/session/<session_id>/close`
   - Synchronise automatiquement si nécessaire
   - Libère le verrou
   - Marque la session comme inactive

## Sécurité

- Toutes les routes nécessitent une authentification JWT
- Les sessions sont liées à l'utilisateur qui les a créées
- Les verrous empêchent l'édition concurrente
- Les fichiers en cache sont stockés dans un répertoire sécurisé

## Nettoyage automatique

- Les sessions inactives sont nettoyées automatiquement
- POST `/api/files/cleanup` pour nettoyer manuellement (admin)
