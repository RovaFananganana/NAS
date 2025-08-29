from flask import Flask
from extensions import db, migrate
from config import Config
from routes import register_blueprints

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    register_blueprints(app)

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True,port=5001)
