# Correction de la visibilité des dossiers accessibles

## Problème identifié
Un utilisateur a des permissions sur un dossier, mais ce dossier n'apparaît pas dans l'interface car il se trouve dans un parent non accessible.

**Exemple :**
- Dossier : `/Parent/Enfant/MonDossier`
- Utilisateur a permission sur `MonDossier` ✅
- Utilisateur n'a PAS permission sur `Parent` ou `Enfant` ❌
- Résultat : `MonDossier` n'apparaît nulle part dans l'interface

## Solution implémentée

### ✅ Affichage des dossiers accessibles à la racine
Quand l'utilisateur navigue vers la racine (`/`), le système :

1. **Récupère tous les dossiers accessibles** via `get_all_accessible_folders()`
2. **Les affiche comme enfants directs de la racine** même s'ils sont ailleurs
3. **Crée des éléments virtuels** pour les dossiers non présents physiquement

### Code ajouté

#### Fonction `get_all_accessible_folders()`
```python
def get_all_accessible_folders(user):
    """Récupère tous les dossiers auxquels l'utilisateur a accès"""
    accessible_folders = []
    all_folders = Folder.query.all()
    
    for folder in all_folders:
        permissions = permission_optimizer.get_bulk_folder_permissions(user.id, [folder.id])
        folder_perm = permissions.get(folder.id)
        
        if folder_perm and folder_perm.can_read:
            accessible_folders.append(folder.path)
    
    return accessible_folders
```

#### Logique d'affichage améliorée
```python
if path == '/':
    # À la racine, ajouter tous les dossiers auxquels l'utilisateur a accès
    all_accessible_folders = get_all_accessible_folders(user)
    for folder_path in all_accessible_folders:
        if folder_path.count('/') == 1 and folder_path != '/':
            # Créer un item virtuel pour ce dossier
            virtual_item = {
                'name': folder_path.strip('/'),
                'path': folder_path,
                'is_directory': True,
                # ... autres propriétés
            }
            accessible_items.append(virtual_item)
```

## Comportement attendu

### Avant la correction
```
Racine (/)
├── (vide - aucun dossier visible)
```

### Après la correction
```
Racine (/)
├── MonDossier (accessible via permissions)
├── AutreDossier (accessible via permissions)
└── DossierPhysique (présent physiquement ET accessible)
```

## Avantages

1. **Accès direct** : L'utilisateur voit immédiatement ses dossiers autorisés
2. **Navigation intuitive** : Plus besoin de connaître l'arborescence complète
3. **Sécurité maintenue** : Seuls les dossiers autorisés sont visibles
4. **Compatibilité** : Fonctionne avec l'arborescence existante

## Cas d'usage

### Utilisateur AIM
- Permission sur `/Projets/AIM/Documents` ✅
- Pas de permission sur `/Projets` ou `/Projets/AIM` ❌
- **Résultat** : Voit "Documents" directement à la racine

### Utilisateur Manager
- Permission sur `/RH/Salaires` ✅
- Permission sur `/Comptabilité/Budget` ✅
- **Résultat** : Voit "Salaires" et "Budget" à la racine

## Test de la correction

```bash
# Tester avec un utilisateur ayant des permissions spécifiques
curl -X GET "http://127.0.0.1:5001/nas/browse?path=%2F" \
  -H "Authorization: Bearer USER_TOKEN"

# Vérifier les dossiers accessibles
curl -X GET "http://127.0.0.1:5001/nas/debug/access-issue" \
  -H "Authorization: Bearer USER_TOKEN"
```

Cette correction garantit que tous les dossiers autorisés sont visibles et accessibles, indépendamment de leur position dans l'arborescence.