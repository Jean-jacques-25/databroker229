from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
# 1. Ajoute cet import
from flask_migrate import Migrate

db = SQLAlchemy()
# 2. Crée l'instance de Migrate
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    
    # ... tes configurations (SECRET_KEY, DATABASE_URI...) ...

    db.init_app(app)
    # 3. Initialise migrate avec l'application et la base de données
    migrate.init_app(app, db)

    # ... le reste de ton code (blueprints, etc.) ...
    return app

def create_app():
    app = Flask(__name__)
    
    app.config['SECRET_KEY'] = 'databroker229_secret_key_pro'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///databroker.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    # Importation des modèles pour que SQLAlchemy les détectes
    from .routes import main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()
    
    return app
    app = Flask(__name__)
    
    # Configuration de base de l'application
    app.config['SECRET_KEY'] = 'databroker229_secret_key_pro'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///databroker.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Liaison de la base de données à l'application
    db.init_init_app(app) if hasattr(db, 'init_init_app') else db.init_app(app)
    
    # C'est ici que nous enregistrerons nos futures routes (pages)
    from .routes import main_bp
    app.register_blueprint(main_bp)
    
    return app