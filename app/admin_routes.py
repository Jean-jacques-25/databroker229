# admin_routes.py — conservé pour compatibilité Blueprint
# Toutes les routes admin sont maintenant dans routes.py (blueprint 'main')
# Ce fichier est vide mais le blueprint doit rester enregistré dans __init__.py

from flask import Blueprint

admin = Blueprint('admin', __name__)
