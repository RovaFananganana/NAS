# Utilise une image Python
FROM python:3.11-slim

# Crée un répertoire dans le conteneur
WORKDIR /app

# Copie les fichiers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie tout le projet
COPY . .

# Définit la variable d'environnement Flask
ENV FLASK_APP=app.py

# Expose le port
EXPOSE 5001

# Commande de lancement
CMD ["flask", "run", "--host=0.0.0.0", "--port=5001"]
