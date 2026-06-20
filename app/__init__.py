import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialisation des extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    
    # 🔐 Configuration de la clé secrète
    app.config['SECRET_KEY'] = 'databroker229_secret_key_pro'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 🗄️ Gestion dynamique de la base de données (Render PostgreSQL vs Local SQLite)
    # On regarde si une variable d'environnement DATABASE_URL existe (Configurée sur Render)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Render fournit parfois une URL commençant par 'postgres://'
        # SQLAlchemy exige impérativement 'postgresql://' pour fonctionner
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Si aucune variable n'est détectée, on utilise l'URL PostgreSQL directe que tu as fournie
        # (Idéal pour l'environnement de production ou les scripts d'initialisation)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://databroker229_db_y3vx_user:FsJO1tC9Cu8WMd228lpd4xCuxCdKfwYc@dpg-d8heota8qa3s73bkaml0-a/databroker229_db_y3vx'

    # 🔌 Liaison des extensions à l'application Flask
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 🗺️ Enregistrement du Blueprint des routes
    from .routes import main
    app.register_blueprint(main)
app.register_blueprint(admin)
    
    # 🛠️ Création automatique des tables au démarrage si elles n'existent pas
    with app.app_context():
        from . import models
        db.create_all()
    
    return app