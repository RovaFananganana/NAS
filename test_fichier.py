import os

# Chemin de base pour les tests
BASE_PATH = r"C:\Users\Elite650\Desktop\Document"

def create_test_folder(folder_name):
    """
    Crée un dossier dans BASE_PATH avec le nom donné.
    """
    if not folder_name:
        print("Erreur : nom du dossier vide")
        return None

    # chemin complet
    full_path = os.path.join(BASE_PATH, folder_name)

    try:
        os.makedirs(full_path, exist_ok=True)  # exist_ok=True évite l'erreur si le dossier existe
        print(f"Dossier créé avec succès : {full_path}")
        return full_path
    except Exception as e:
        print(f"Erreur lors de la création du dossier : {e}")
        return None

if __name__ == "__main__":
    # Test : créer un dossier "TestFolder1"
    create_test_folder("TestFolder1")

    # Test : créer un sous-dossier "TestFolder2/SubFolder"
    create_test_folder(r"TestFolder2\SubFolder")
