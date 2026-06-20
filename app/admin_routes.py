from flask import Blueprint, render_template, redirect, url_for, flash, session, abort
from app import db
from app.models import Mission
from functools import wraps

# Définition du Blueprint admin
admin = Blueprint('admin', __name__)

# Décorateur de sécurité
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@admin.route('/admin/missions')
@admin_required
def admin_missions():
    missions = Mission.query.filter_by(status='En attente').all()
    return render_template('admin_missions.html', missions=missions)

@admin.route('/admin/valider/<int:mission_id>')
@admin_required
def valider_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    mission.status = 'Actif'
    db.session.commit()
    flash(f'Mission {mission.title} activée.', 'success')
    return redirect(url_for('admin.admin_missions'))
