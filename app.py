from flask import Flask, request, make_response
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
    
    # ✅ Configuration pour gros fichiers
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB limit

    # Enable CORS for development - very permissive for debugging
    CORS(app, 
         origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:3000", "null"],
         allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         supports_credentials=True)

    @app.before_request
    def handle_preflight():
        # Autoriser toutes les requêtes OPTIONS (prévol CORS)
        if request.method == "OPTIONS":
            response = make_response()
            origin = request.headers.get('Origin')
            allowed_origins = ["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:3000", "null"]
            
            if origin in allowed_origins or origin is None:
                response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Requested-With"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin')
        allowed_origins = ["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://localhost:3000", "null"]
        
        if origin in allowed_origins or origin is None:
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Requested-With"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

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
