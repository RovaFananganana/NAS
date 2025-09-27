#!/usr/bin/env python3
"""
Script de test pour vérifier la route de renommage
"""

import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:5001"
USER_TOKEN = None   # À remplir avec un token utilisateur valide

def test_rename_debug():
    """Test la route de debug du renommage"""
    print("🧪 Test de debug du renommage...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    test_data = {
        "old_path": "/Navigation Aérienne",
        "new_name": "Navigation Aérienne Renamed"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/nas/debug/rename", 
            headers=headers,
            json=test_data
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            debug_info = data.get('debug_info', {})
            
            print("📊 Debug Info:")
            print(f"  - Utilisateur: {debug_info.get('user')}")
            print(f"  - Chemin original: {debug_info.get('old_path')}")
            print(f"  - Nouveau nom: {debug_info.get('new_name')}")
            print(f"  - Chemin normalisé: {debug_info.get('normalized_path')}")
            print(f"  - Nom nettoyé: {debug_info.get('sanitized_name')}")
            print(f"  - Chemin valide: {debug_info.get('path_valid')}")
            print(f"  - Est un fichier: {debug_info.get('is_file')}")
            print(f"  - Permissions: {debug_info.get('permissions')}")
            
        else:
            print(f"❌ Erreur: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def test_rename_actual():
    """Test la route de renommage réelle"""
    print("\n🧪 Test de renommage réel...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    test_data = {
        "old_path": "/test_file.txt",  # Utilisez un fichier de test
        "new_name": "test_file_renamed.txt"
    }
    
    try:
        response = requests.put(
            f"{BASE_URL}/nas/rename", 
            headers=headers,
            json=test_data
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Renommage réussi:")
            print(f"  - Succès: {data.get('success')}")
            print(f"  - Nouveau chemin: {data.get('new_path')}")
            print(f"  - Message: {data.get('message')}")
        else:
            print(f"❌ Erreur: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def main():
    print("🚀 Test de la fonctionnalité de renommage\n")
    
    if not USER_TOKEN:
        print("⚠️  USER_TOKEN non défini")
        print("   Définissez USER_TOKEN avec un token utilisateur valide")
        return
    
    test_rename_debug()
    test_rename_actual()
    
    print("\n📝 Instructions:")
    print("1. Vérifiez les permissions dans le debug")
    print("2. Assurez-vous que le fichier/dossier existe")
    print("3. Vérifiez que l'utilisateur a les permissions d'écriture")

if __name__ == "__main__":
    main()