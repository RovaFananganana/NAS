# Correction de la route /nas/rename

## Problème identifié
```
Access to fetch at 'http://127.0.0.1:5001/nas/rename' from origin 'http://localhost:5173' 
has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present
PUT http://127.0.0.1:5001/nas/rename net::ERR_FAILED 500 (INTERNAL SERVER ERROR)
```

## Causes possibles identifiées

1. **Problème CORS** : Requête preflight OPTIONS non gérée
2. **Permissions incorrectes** : Utilisation de `check_folder_permission` pour les fichiers
3. **Erreur 500** : Exception non gérée dans la route

## Solutions implémentées

### ✅ 1. Gestion des requêtes OPTIONS pour CORS
```python
@nas_bp.route('/rename', methods=['PUT', 'POST', 'OPTIONS'])
def rename_item():
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
```

### ✅ 2. Vérification des permissions selon le type
**Avant (incorrect) :**
```python
if not check_folder_permission(user, old_path, 'write'):
    return jsonify({"error": "Permission refusée"}), 403
```

**Après (correct) :**
```python
is_file = '.' in old_path.split('/')[-1]

if is_file:
    if not check_file_permission(user, old_path, 'write'):
        return jsonify({"error": "Permission refusée pour ce fichier"}), 403
else:
    if not check_folder_permission(user, old_path, 'write'):
        return jsonify({"error": "Permission refusée pour ce dossier"}), 403
```

### ✅ 3. Ajout des logs d'accès
```python
if result.get('success'):
    log_file_operation(
        user_id,
        'RENAME',
        f"'{old_path}' renommé en '{new_name}'",
        f"Nouveau chemin: {result.get('new_path', 'N/A')}"
    )
```

### ✅ 4. Route de debug
```python
@nas_bp.route('/debug/rename', methods=['POST'])
def debug_rename():
    """Debug de la fonctionnalité de renommage"""
    # Retourne des informations de debug sur les permissions et la validation
```

## Configuration CORS existante

La configuration CORS dans `app.py` est correcte :
```python
CORS(app, 
     origins=["http://localhost:5173", "http://localhost:5174", ...],
     allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
```

## Test de la correction

### Script de test
```bash
cd backend
python test_rename_route.py
```

### Test manuel
```bash
# Debug des permissions
curl -X POST "http://127.0.0.1:5001/nas/debug/rename" \
  -H "Authorization: Bearer USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"old_path": "/test.txt", "new_name": "test_renamed.txt"}'

# Test de renommage réel
curl -X PUT "http://127.0.0.1:5001/nas/rename" \
  -H "Authorization: Bearer USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"old_path": "/test.txt", "new_name": "test_renamed.txt"}'
```

## Résultats attendus

### Avant la correction
- ❌ Erreur CORS sur les requêtes preflight
- ❌ Erreur 500 pour les fichiers (mauvaise vérification de permissions)
- ❌ Pas de logs des opérations de renommage

### Après la correction
- ✅ Requêtes OPTIONS gérées correctement
- ✅ Permissions vérifiées selon le type (fichier/dossier)
- ✅ Logs d'accès enregistrés pour les renommages
- ✅ Route de debug disponible pour diagnostiquer les problèmes

## Actions de vérification

1. **Tester le renommage** dans l'interface utilisateur
2. **Vérifier les logs** dans la section "Journaux" de l'admin
3. **Utiliser la route de debug** si des problèmes persistent
4. **Vérifier les permissions** en base de données si nécessaire

Cette correction devrait résoudre les problèmes CORS et les erreurs 500 lors du renommage.