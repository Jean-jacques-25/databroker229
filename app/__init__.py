from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
    app.config['SECRET_KEY'] = 'dev'

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.routes import main
    from app.admin_routes import admin
    
    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        
    return app
