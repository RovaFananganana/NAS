from app import create_app
from extensions import db
from models.user import User

def seed_users():
    app = create_app()
    with app.app_context():
        # Vérifier si l'admin existe déjà
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", email="admin@test.com", role="ADMIN")
            admin.set_password("admin123")
            db.session.add(admin)
            print("✅ Admin créé avec succès.")
        else:
            print("⚠️ Admin existe déjà.")

        # Vérifier si l'utilisateur simple existe déjà
        user = User.query.filter_by(username="user").first()
        if not user:
            user = User(username="user", email="user@test.com", role="USER")
            user.set_password("user123")
            db.session.add(user)
            print("✅ Utilisateur simple créé avec succès.")
        else:
            print("⚠️ Utilisateur simple existe déjà.")

        db.session.commit()

if __name__ == "__main__":
    seed_users()
