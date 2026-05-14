from flask import Flask
from .models import db
from config import Config
from apscheduler.schedulers.background import BackgroundScheduler
import os

scheduler = BackgroundScheduler()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        print("✅ Base de données prête.")

    # Démarrer le scheduler
    if not scheduler.running:
        from .moteur import verifier_echeances
        scheduler.add_job(
            func=verifier_echeances,
            args=[app],
            trigger="interval",
            minutes=30,
            id="check_echeances"
        )
        scheduler.start()
        print("✅ Scheduler démarré — vérification toutes les 30 minutes.")

    return app
