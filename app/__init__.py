from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from sqlalchemy import text
import os

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()

def create_app():
    app = Flask(__name__)

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'databroker229-secret-key-prod')
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    app.config['MAIL_SERVER']        = 'smtp.gmail.com'
    app.config['MAIL_PORT']          = 587
    app.config['MAIL_USE_TLS']       = True
    app.config['MAIL_USERNAME']      = 'databroker229@gmail.com'
    app.config['MAIL_PASSWORD']      = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = ('LaCentraleDesDonnees229', 'databroker229@gmail.com')

    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    from app.routes import main
    from app.admin_routes import admin
    app.register_blueprint(main)
    app.register_blueprint(admin)

    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                # Colonnes missions
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS prix_agent INTEGER DEFAULT 500"))
                # Colonnes parrainage et mission essai
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS essai_complete BOOLEAN DEFAULT false"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS essai_sub_id INTEGER"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS code_parrain VARCHAR(20)"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS parrain_id INTEGER"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS filleuls_count INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_parrainage INTEGER DEFAULT 0"))
                # Table api_keys
                conn.execute(text("""CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES users(id),
                    key VARCHAR(64) UNIQUE NOT NULL,
                    label VARCHAR(100),
                    is_active BOOLEAN DEFAULT true,
                    requests INTEGER DEFAULT 0,
                    last_used TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )"""))
                # Activer clients et admins existants
                conn.execute(text("UPDATE users SET essai_complete=true WHERE role IN ('client','admin')"))
                conn.commit()
        except Exception as e:
            print(f"Migration warning: {e}")

    return app
