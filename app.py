from flask import Flask
from flask_jwt_extended import JWTManager
from extensions import db, migrate
from config import Config
from routes import register_blueprints
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()  # charge les variables d'environnement depuis .env
print("STORAGE_ROOT:", os.getenv("STORAGE_ROOT"))

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(Config)

    # ✅ Configuration JWT claire
    app.config["JWT_ERROR_MESSAGE_KEY"] = "msg"

    # Enable CORS for development - very permissive for debugging
    CORS(app, 
         origins="*",  # Allow all origins for development
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
         allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin", "Access-Control-Request-Method", "Access-Control-Request-Headers"],
         supports_credentials=False)  # Set to False when using origins="*"

    # Init extensions
    db.init_app(app)
    jwt = JWTManager(app)
    migrate.init_app(app, db)

    # Register blueprints
    register_blueprints(app)

    # Add favicon route
    @app.route('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)
