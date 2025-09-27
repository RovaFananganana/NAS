# Correction du problème 403 FORBIDDEN

## Problème identifié
Après nos corrections de sécurité, les utilisateurs non-admin ne peuvent plus accéder à la racine (`/`) et reçoivent une erreur `403 FORBIDDEN` sur `/nas/browse?path=%2F`.

## Cause du problème
Notre changement de sécurité était trop restrictif :
```python
# AVANT (trop permissif)
return required_action == 'read'  # Autorisait tout en lecture

# APRÈS (trop restrictif) 
return False  # Refusait tout par défaut
```

## Solution implémentée

### 1. ✅ Accès à la racine autorisé par défaut
```python
# Par défaut, autoriser la lecture pour les utilisateurs authentifiés sur la racine
if normalized_path == '/' and required_action == 'read':
    return True
return False
```

### 2. ✅ Gestion d'erreur améliorée
```python
# En cas d'erreur, autoriser la lecture sur la racine par défaut pour éviter de bloquer l'accès
if required_action == 'read' and normalize_smb_path(path) == '/':
    return True
return False
```

### 3. ✅ Fonction de vérification d'accès racine
```python
def ensure_root_access(user):
    """S'assure qu'un utilisateur a au moins accès en lecture à la racine"""
    # Crée le dossier racine s'il n'existe pas
    # Vérifie les permissions sur la racine
```

### 4. ✅ Messages d'erreur informatifs
```python
return jsonify({
    "error": "Aucune permission configurée. Contactez votre administrateur.",
    "suggestion": "Vous n'avez accès à aucun dossier. Un administrateur doit vous accorder des permissions."
}), 403
```

### 5. ✅ Route de diagnostic
- `/nas/debug/access-issue` - Diagnostique les problèmes d'accès pour l'utilisateur actuel
- Affiche les permissions, groupes, et recommandations

## Logique de permissions corrigée

### Pour les dossiers (`check_folder_permission`)
1. **Admin** → Accès total ✅
2. **Permissions explicites** → Respectées ✅
3. **Dossier racine** → Lecture autorisée par défaut ✅
4. **Autres dossiers** → Refus par défaut (sécurisé) ✅

### Pour les fichiers (`check_file_permission`)
1. **Admin** → Accès total ✅
2. **Permissions explicites sur le fichier** → Respectées ✅
3. **Permissions via groupes** → Respectées ✅
4. **Fallback** → Permissions du dossier parent ✅

## Comment tester la correction

### 1. Test manuel
```bash
# Tester l'accès à la racine
curl -X GET "http://127.0.0.1:5001/nas/browse?path=%2F" \
  -H "Authorization: Bearer USER_TOKEN"

# Diagnostiquer les problèmes d'accès
curl -X GET "http://127.0.0.1:5001/nas/debug/access-issue" \
  -H "Authorization: Bearer USER_TOKEN"
```

### 2. Script de test
```bash
cd backend
python test_permissions_fix.py
```

### 3. Interface utilisateur
1. Connectez-vous avec un utilisateur non-admin
2. Accédez à la section "Mes fichiers"
3. Vérifiez que la racine est accessible
4. Vérifiez que les fichiers avec permissions sont visibles

## Résultats attendus

### ✅ Utilisateurs avec permissions
- Accès à la racine : **Autorisé**
- Fichiers avec permissions : **Visibles**
- Navigation : **Fonctionnelle**

### ✅ Utilisateurs sans permissions
- Accès à la racine : **Autorisé** (mais vide)
- Message informatif : **Affiché**
- Suggestion de contacter l'admin : **Présente**

### ✅ Sécurité maintenue
- Dossiers sans permissions : **Bloqués**
- Fichiers sans permissions : **Cachés**
- Actions non autorisées : **Refusées**

## Équilibre sécurité/utilisabilité

| Aspect | Avant | Problème | Maintenant |
|--------|-------|----------|------------|
| Racine | Auto-autorisé | Trop permissif | Lecture seule autorisée |
| Dossiers | Auto-autorisé | Trop permissif | Permissions explicites requises |
| Fichiers | Non vérifié | Pas de contrôle | Permissions granulaires |
| Erreurs | Permissif | Risque sécurité | Racine autorisée, reste sécurisé |

Cette correction maintient la sécurité tout en permettant aux utilisateurs d'accéder à l'interface de base.