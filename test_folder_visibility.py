#!/usr/bin/env python3
"""
Script de test pour vérifier la visibilité des dossiers avec permissions
"""

import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:5001"
USER_TOKEN = None   # À remplir avec un token utilisateur valide

def test_root_folder_visibility():
    """Test la visibilité des dossiers à la racine"""
    print("🧪 Test de visibilité des dossiers à la racine...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    try:
        response = requests.get(f"{BASE_URL}/nas/browse?path=%2F", headers=headers)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get('items', [])
            print(f"✅ Accès réussi - {len(items)} éléments trouvés")
            
            for item in items:
                print(f"  - {item['name']} ({'dossier' if item['is_directory'] else 'fichier'})")
                
        elif response.status_code == 403:
            data = response.json()
            print(f"❌ Accès refusé: {data.get('error', 'Erreur inconnue')}")
        else:
            print(f"❓ Réponse inattendue: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def test_accessible_folders_debug():
    """Test la route de debug pour voir tous les dossiers accessibles"""
    print("\n🔍 Test des dossiers accessibles...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    try:
        response = requests.get(f"{BASE_URL}/nas/debug/access-issue", headers=headers)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("📊 Diagnostic:")
            print(f"  - Utilisateur: {data['user']['username']}")
            print(f"  - Permissions dossiers: {data['access_status']['direct_folder_permissions']}")
            print(f"  - Permissions fichiers: {data['access_status']['direct_file_permissions']}")
            
        else:
            print(f"❌ Erreur: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def main():
    print("🚀 Test de visibilité des dossiers avec permissions\n")
    
    if not USER_TOKEN:
        print("⚠️  USER_TOKEN non défini")
        print("   Définissez USER_TOKEN avec un token utilisateur valide")
        print("   Exemple: USER_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'")
        return
    
    test_root_folder_visibility()
    test_accessible_folders_debug()
    
    print("\n📝 Instructions:")
    print("1. Vérifiez que les dossiers avec permissions apparaissent à la racine")
    print("2. Même si le dossier parent n'est pas accessible")
    print("3. L'utilisateur devrait voir tous ses dossiers autorisés")

if __name__ == "__main__":
    main()