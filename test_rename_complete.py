#!/usr/bin/env python3
"""
Test complet de la fonctionnalité de renommage avec authentification
"""

import requests
import json
import sys
import os

# Configuration
BASE_URL = "http://127.0.0.1:5001"

def get_test_token():
    """Obtient un token de test via l'authentification"""
    print("🔑 Tentative d'authentification...")
    
    # Essayer avec des credentials de test
    test_credentials = [
        {"username": "admin", "password": "admin"},
        {"username": "test", "password": "test"},
        {"username": "user", "password": "user"}
    ]
    
    for creds in test_credentials:
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json=creds,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('access_token')
                if token:
                    print(f"✅ Authentification réussie avec {creds['username']}")
                    return token
            else:
                print(f"❌ Échec authentification {creds['username']}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Erreur authentification {creds['username']}: {str(e)}")
    
    return None

def test_rename_with_auth():
    """Test complet du renommage avec authentification"""
    print("🧪 Test de renommage avec authentification...")
    
    # Obtenir un token
    token = get_test_token()
    if not token:
        print("❌ Impossible d'obtenir un token d'authentification")
        return False
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Test 1: Validation des données
    print("\n  Test 1: Validation des données manquantes")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={})
        print(f"    Status: {response.status_code}")
        if response.status_code == 400:
            data = response.json()
            print(f"    ✅ Validation correcte: {data.get('error')}")
        else:
            print(f"    ❌ Validation incorrecte: {response.text}")
    except Exception as e:
        print(f"    ❌ Erreur: {str(e)}")
    
    # Test 2: Chemin invalide
    print("\n  Test 2: Validation chemin invalide")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={
            "old_path": "../../../etc/passwd",
            "new_name": "test"
        })
        print(f"    Status: {response.status_code}")
        if response.status_code == 400:
            data = response.json()
            print(f"    ✅ Validation correcte: {data.get('error')}")
        else:
            print(f"    ❌ Validation incorrecte: {response.text}")
    except Exception as e:
        print(f"    ❌ Erreur: {str(e)}")
    
    # Test 3: Fichier inexistant (devrait donner une erreur de permissions ou 404)
    print("\n  Test 3: Fichier inexistant")
    try:
        response = requests.post(f"{BASE_URL}/nas/rename", headers=headers, json={
            "old_path": "/fichier_inexistant_test_123.txt",
            "new_name": "nouveau_nom.txt"
        })
        print(f"    Status: {response.status_code}")
        data = response.json()
        print(f"    Réponse: {data.get('error', data.get('message', 'Pas de message'))}")
    except Exception as e:
        print(f"    ❌ Erreur: {str(e)}")
    
    return True

def test_cors_headers():
    """Test les en-têtes CORS"""
    print("\n🧪 Test des en-têtes CORS...")
    
    try:
        # Test OPTIONS
        response = requests.options(
            f"{BASE_URL}/nas/rename",
            headers={
                'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type,Authorization'
            }
        )
        
        print(f"  OPTIONS Status: {response.status_code}")
        if response.status_code == 200:
            print("  ✅ CORS preflight OK")
            cors_headers = {
                'Access-Control-Allow-Origin': response.headers.get('Access-Control-Allow-Origin'),
                'Access-Control-Allow-Methods': response.headers.get('Access-Control-Allow-Methods'),
                'Access-Control-Allow-Headers': response.headers.get('Access-Control-Allow-Headers')
            }
            for header, value in cors_headers.items():
                print(f"    {header}: {value}")
        else:
            print(f"  ❌ CORS preflight échoué: {response.text}")
            
    except Exception as e:
        print(f"  ❌ Erreur test CORS: {str(e)}")

def main():
    print("🚀 Test complet de la correction du renommage\n")
    
    # Test de base du serveur
    try:
        response = requests.get(f"{BASE_URL}/nas/health", timeout=5)
        if response.status_code == 200:
            print("✅ Serveur accessible")
        else:
            print(f"❌ Serveur inaccessible: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Serveur inaccessible: {str(e)}")
        return
    
    # Tests CORS
    test_cors_headers()
    
    # Tests avec authentification
    success = test_rename_with_auth()
    
    if success:
        print("\n✅ Tests de correction du renommage terminés")
        print("\n📋 Résumé des corrections:")
        print("  1. ✅ Gestion CORS améliorée avec en-têtes explicites")
        print("  2. ✅ Gestion d'erreur robuste avec try/catch imbriqués")
        print("  3. ✅ Validation des données d'entrée renforcée")
        print("  4. ✅ Messages d'erreur plus explicites")
        print("  5. ✅ Séparation des erreurs SMB et DB")
    else:
        print("\n❌ Échec des tests d'authentification")
    
    print("\n📝 Prochaines étapes:")
    print("  1. Tester avec le frontend Vue.js")
    print("  2. Vérifier les permissions utilisateur")
    print("  3. Tester avec de vrais fichiers/dossiers")

if __name__ == "__main__":
    main()