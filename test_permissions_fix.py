#!/usr/bin/env python3
"""
Script de test pour vérifier les corrections de permissions
"""

import requests
import json

# Configuration
BASE_URL = "http://127.0.0.1:5001"
ADMIN_TOKEN = None  # À remplir avec un token admin valide
USER_TOKEN = None   # À remplir avec un token utilisateur valide

def test_root_access():
    """Test l'accès à la racine"""
    print("🧪 Test d'accès à la racine...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    try:
        response = requests.get(f"{BASE_URL}/nas/browse?path=%2F", headers=headers)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Accès réussi - {len(data.get('items', []))} éléments trouvés")
        elif response.status_code == 403:
            data = response.json()
            print(f"❌ Accès refusé: {data.get('error', 'Erreur inconnue')}")
            if 'suggestion' in data:
                print(f"💡 Suggestion: {data['suggestion']}")
        else:
            print(f"❓ Réponse inattendue: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def test_debug_access():
    """Test la route de debug d'accès"""
    print("\n🔍 Test de diagnostic d'accès...")
    
    headers = {"Authorization": f"Bearer {USER_TOKEN}"} if USER_TOKEN else {}
    
    try:
        response = requests.get(f"{BASE_URL}/nas/debug/access-issue", headers=headers)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("📊 Diagnostic:")
            print(f"  - Utilisateur: {data['user']['username']}")
            print(f"  - Rôle: {data['user']['role']}")
            print(f"  - Groupes: {', '.join(data['user']['groups']) if data['user']['groups'] else 'Aucun'}")
            print(f"  - Accès racine: {'✅' if data['access_status']['root_access'] else '❌'}")
            print(f"  - Permissions dossiers: {data['access_status']['direct_folder_permissions']}")
            print(f"  - Permissions fichiers: {data['access_status']['direct_file_permissions']}")
            
            print("\n💡 Recommandations:")
            for rec in data['recommendations']:
                if rec:
                    print(f"  - {rec}")
        else:
            print(f"❌ Erreur: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def main():
    print("🚀 Test des corrections de permissions\n")
    
    if not USER_TOKEN:
        print("⚠️  USER_TOKEN non défini - certains tests ne fonctionneront pas")
        print("   Définissez USER_TOKEN avec un token utilisateur valide")
    
    test_root_access()
    test_debug_access()
    
    print("\n📝 Instructions:")
    print("1. Si l'accès à la racine est refusé, vérifiez les permissions en base")
    print("2. Utilisez la route /nas/debug/access-issue pour diagnostiquer")
    print("3. Un admin doit accorder des permissions sur le dossier racine")

if __name__ == "__main__":
    main()