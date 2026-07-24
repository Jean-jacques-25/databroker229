from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from sqlalchemy.pool import QueuePool
import os

db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)

    database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'databroker229-secret-key-prod')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    # ── CONNEXION POSTGRESQL ROBUSTE ──────────────────────────────
    # Reconnexion automatique si la connexion SSL expire ou est perdue
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,        # Teste la connexion avant chaque requete
        'pool_recycle': 280,          # Renouvelle la connexion toutes les 280s
        'pool_timeout': 20,           # Timeout de 20s pour obtenir une connexion
        'pool_size': 5,               # 5 connexions en parallele max
        'max_overflow': 10,           # 10 connexions supplementaires si besoin
        'connect_args': {
            'connect_timeout': 10,    # Timeout de connexion TCP
            'keepalives': 1,          # Activer TCP keepalive
            'keepalives_idle': 30,    # Envoyer keepalive apres 30s d inactivite
            'keepalives_interval': 10, # Reessayer toutes les 10s
            'keepalives_count': 5,    # 5 tentatives avant abandon
        }
    }

    app.config['MAIL_SERVER']        = 'smtp.gmail.com'
    app.config['MAIL_PORT']          = 587
    app.config['MAIL_USE_TLS']       = True
    app.config['MAIL_USERNAME']      = 'databroker229@gmail.com'
    app.config['MAIL_PASSWORD']      = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = ('LaCentraleDesDonnees229', 'databroker229@gmail.com')

    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)

    from app.routes import main
    from app.admin_routes import admin
    app.register_blueprint(main)
    app.register_blueprint(admin)

    import json as _json
    def _from_json(value):
        if not value:
            return []
        try:
            return _json.loads(value)
        except (ValueError, TypeError):
            return []
    app.jinja_env.filters['from_json'] = _from_json

    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS prix_agent INTEGER DEFAULT 500"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS deadline TIMESTAMP"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS custom_fields TEXT"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS zones_additionnelles VARCHAR(300)"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS photos_nombre INTEGER DEFAULT 1"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS photos_instructions VARCHAR(300)"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paused_auto BOOLEAN DEFAULT FALSE"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS low_score_notified BOOLEAN DEFAULT FALSE"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS certifications TEXT"))
                conn.execute(text("ALTER TABLE missions ADD COLUMN IF NOT EXISTS domaine_agent VARCHAR(30) DEFAULT 'general'"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS essai_complete BOOLEAN DEFAULT false"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS essai_sub_id INTEGER"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS code_parrain VARCHAR(20)"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS parrain_id INTEGER"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS filleuls_count INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bonus_parrainage INTEGER DEFAULT 0"))
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
                conn.execute(text("UPDATE users SET essai_complete=true WHERE role IN ('client','admin')"))
                conn.commit()
        except Exception as e:
            print(f"Migration warning: {e}")

    return app
