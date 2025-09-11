import os
from pathlib import Path

# Prend la variable d'environnement ou valeur par défaut
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", r"C:\Users\Elite650\Desktop\Document"))

def create_folder(relative_path):
    folder_path = STORAGE_ROOT / relative_path
    folder_path.mkdir(parents=True, exist_ok=True)
    print("Dossier créé :", folder_path)
    return str(folder_path)

def create_file(relative_path, content=b""):
    file_path = STORAGE_ROOT / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)
    print("Fichier créé :", file_path)
    return str(file_path)

def delete_path(relative_path):
    path = STORAGE_ROOT / relative_path
    if path.is_dir():
        for child in path.iterdir():
            if child.is_file():
                child.unlink()
            else:
                delete_path(child.relative_to(STORAGE_ROOT))
        path.rmdir()
    elif path.is_file():
        path.unlink()
    print("Chemin supprimé :", path)