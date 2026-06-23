from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)

    # PostgreSQL en production (variable Render), SQLite en local
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')

    # Render donne parfois postgres:// — SQLAlchemy exige postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,      # Vérifie la connexion avant chaque requête
        'pool_recycle': 280,        # Recycle les connexions toutes les ~5 min
        'connect_args': {} if 'postgresql' in database_url else {}
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'databroker229-secret-key-prod')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes import main
    from app.admin_routes import admin

    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()

    return app
