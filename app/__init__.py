from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import text
import os

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')

    # Render donne parfois postgres:// — SQLAlchemy exige postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'databroker229-secret-key-prod')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes import main
    from app.admin_routes import admin

    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        # Ajouter les nouvelles colonnes sans supprimer les donnees existantes
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS prix_agent INTEGER DEFAULT 500"))
                conn.commit()
        except Exception:
            pass

    return app
