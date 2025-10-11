#!/usr/bin/env python3
"""
Script de test pour l'endpoint de recherche
"""

import requests
import json
import sys
import os

# Configuration
BASE_URL = "http://127.0.0.1:5001"
LOGIN_URL = f"{BASE_URL}/auth/login"
SEARCH_URL = f"{BASE_URL}/nas/search"

def test_search_endpoint():
    """Test l'endpoint de recherche"""
    
    print("🧪 Test de l'endpoint de recherche /nas/search")
    print("=" * 50)
    
    # 1. Se connecter pour obtenir un token
    print("1. Connexion...")
    login_data = {
        "username": "admin",  # Ajustez selon votre configuration
        "password": "admin123"  # Ajustez selon votre configuration
    }
    
    try:
        response = requests.post(LOGIN_URL, json=login_data)
        if response.status_code != 200:
            print(f"❌ Échec de connexion: {response.status_code}")
            print(f"Réponse: {response.text}")
            return False
            
        token = response.json().get('access_token')
        if not token:
            print("❌ Token non reçu")
            return False
            
        print("✅ Connexion réussie")
        
    except Exception as e:
        print(f"❌ Erreur de connexion: {str(e)}")
        return False
    
    # 2. Tester la recherche
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Tests de recherche
    test_cases = [
        {
            "name": "Recherche simple",
            "params": {"query": "doc", "recursive": "true", "max_results": "10"}
        },
        {
            "name": "Recherche non récursive",
            "params": {"query": "test", "recursive": "false", "path": "/"}
        },
        {
            "name": "Recherche avec chemin spécifique",
            "params": {"query": "pdf", "path": "/Documents", "recursive": "true"}
        }
    ]
    
    for i, test_case in enumerate(test_cases, 2):
        print(f"\n{i}. {test_case['name']}...")
        
        try:
            response = requests.get(SEARCH_URL, headers=headers, params=test_case['params'])
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    results = data.get('results', [])
                    print(f"   ✅ {len(results)} résultats trouvés")
                    print(f"   Temps: {data.get('search_time_ms', 0)}ms")
                    
                    # Afficher quelques résultats
                    for j, result in enumerate(results[:3]):
                        print(f"      - {result.get('name')} ({'dossier' if result.get('is_directory') else 'fichier'})")
                        
                    if len(results) > 3:
                        print(f"      ... et {len(results) - 3} autres")
                        
                else:
                    print(f"   ❌ Erreur: {data.get('error', 'Erreur inconnue')}")
                    
            else:
                print(f"   ❌ Erreur HTTP: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
    
    print("\n" + "=" * 50)
    print("🏁 Test terminé")
    return True

if __name__ == "__main__":
    test_search_endpoint()