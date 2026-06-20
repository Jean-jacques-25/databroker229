from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Mission

main = Blueprint('main', __name__)

@main.route('/client/dashboard', methods=['GET', 'POST'])
def client_dashboard():
    # Logique de création de mission ici
    missions = Mission.query.filter_by(client_id=session.get('user_id')).all()
    return render_template('client_dashboard.html', missions=missions)

@main.route('/')
def index():
    return redirect(url_for('main.client_dashboard'))
