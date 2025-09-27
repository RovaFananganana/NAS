#!/usr/bin/env python3
"""
Script de test pour vérifier la route de renommage
"""

import requests
import json
import sys
import os

# Configuration
BASE_URL = "http://127.0.0.1:5001"
USER_TOKEN = None   # À remplir avec un token utilisateur valide

def get_auth_token():
    """Tente d'obtenir un token d'authentification"""
    global USER_TOKEN
    
    if USER_TOKEN:
        return USER_TOKEN
    
    # Essayer de lire depuis les variables d'environnement
    USER_TOKEN = os.getenv('AUTH_TOKEN')
    if USER_TOKEN:
        print(f"✅ Token trouvé dans les variables d'environnement")
        return USER_TOKEN
    
    # Demander à l'utilisateur
    print("🔑 Token d'authentification requis")
    print("   Vous pouvez:")
    print("   1. Définir la variable d'environnement AUTH_TOKEN")
    print("   2. Entrer le token maintenant")
    
    token = input("Entrez votre token d'authentification (ou appuyez sur Entrée pour continuer sans): ").strip()
    if token:
        USER_TOKEN = token
        return USER_TOKEN
    
    return None

def test_cors_preflight():
    """Test la requête OPTIONS pour CORS"""
    print("🧪 Test CORS preflight (OPTIONS)...")
    
    try:
        response = requests.options(
            f"{BASE_URL}/nas/rename",
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type,Authorization'
            }
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ CORS preflight réussi")
            print(f"  - Access-Control-Allow-Origin: {response.headers.get('Access-Control-Allow-Origin', 'Non défini')}")
            print(f"  - Access-Control-Allow-Methods: {response.headers.get('Access-Control-Allow-Methods', 'Non défini')}")
            print(f"  - Access-Control-Allow-Headers: {response.headers.get('Access-Control-Allow-Headers', 'Non défini')}")
        else:
            print(f"❌ Erreur CORS: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur de test CORS: {str(e)}")

def test_rename_debug():
    """Test la route de debug du renommage"""
    print("\n🧪 Test de debug du renommage...")
    
    token = get_auth_token()
    if not token:
        print("⚠️  Pas de token - test ignoré")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
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
            try:
                error_data = response.json()
                print(f"   Détails: {error_data}")
            except:
                pass
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def test_rename_validation():
    """Test la validation des données d'entrée"""
    print("\n🧪 Test de validation des données...")
    
    token = get_auth_token()
    if not token:
        print("⚠️  Pas de token - test ignoré")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Test 1: Données manquantes
    print("  Test 1: Données manquantes")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={})
        print(f"    Status: {response.status_code} - {response.json().get('error', 'Pas d\'erreur')}")
    except Exception as e:
        print(f"    Erreur: {str(e)}")
    
    # Test 2: Chemin invalide
    print("  Test 2: Chemin invalide")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={
            "old_path": "../../../etc/passwd",
            "new_name": "test"
        })
        print(f"    Status: {response.status_code} - {response.json().get('error', 'Pas d\'erreur')}")
    except Exception as e:
        print(f"    Erreur: {str(e)}")
    
    # Test 3: Nom invalide
    print("  Test 3: Nom invalide")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={
            "old_path": "/test",
            "new_name": "test<>|"
        })
        print(f"    Status: {response.status_code} - {response.json().get('error', 'Pas d\'erreur')}")
    except Exception as e:
        print(f"    Erreur: {str(e)}")

def test_rename_actual():
    """Test la route de renommage réelle"""
    print("\n🧪 Test de renommage réel...")
    
    token = get_auth_token()
    if not token:
        print("⚠️  Pas de token - test ignoré")
        return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    test_data = {
        "old_path": "/test_file.txt",  # Utilisez un fichier de test
        "new_name": "test_file_renamed.txt"
    }
    
    try:
        response = requests.post(
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
            try:
                error_data = response.json()
                print(f"   Détails: {error_data}")
            except:
                pass
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")

def test_server_health():
    """Test si le serveur répond"""
    print("🧪 Test de santé du serveur...")
    
    try:
        response = requests.get(f"{BASE_URL}/nas/health", timeout=5)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Serveur accessible")
            data = response.json()
            print(f"  - Message: {data.get('message')}")
        else:
            print(f"❌ Serveur inaccessible: {response.text}")
            
    except Exception as e:
        print(f"❌ Erreur connexion serveur: {str(e)}")
        return False
    
    return True

def main():
    print("🚀 Test complet de la fonctionnalité de renommage\n")
    
    # Test de base du serveur
    if not test_server_health():
        print("\n❌ Serveur inaccessible - arrêt des tests")
        return
    
    # Tests CORS
    test_cors_preflight()
    
    # Tests avec authentification
    token = get_auth_token()
    if token:
        test_rename_validation()
        test_rename_debug()
        test_rename_actual()
    else:
        print("\n⚠️  Tests d'authentification ignorés (pas de token)")
    
    print("\n📝 Instructions:")
    print("1. Vérifiez que le serveur Flask fonctionne sur le port 5001")
    print("2. Assurez-vous d'avoir un token d'authentification valide")
    print("3. Vérifiez les permissions dans le debug")
    print("4. Assurez-vous que le fichier/dossier existe")
    print("5. Vérifiez que l'utilisateur a les permissions d'écriture")

if __name__ == "__main__":
    main()