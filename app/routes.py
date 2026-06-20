from flask import render_template, request, redirect, url_for, session, flash
from app import db
from app.models import Mission

@main.route('/client/dashboard', methods=['GET', 'POST'])
def client_dashboard():
    if request.method == 'POST':
        nouvelle_mission = Mission(
            client_id=session.get('user_id'),
            organisation=request.form.get('organisation'),
            contact=request.form.get('contact'),
            title=request.form.get('title'),
            type_donnees=request.form.get('type_donnees'),
            description=request.form.get('description'),
            zone=request.form.get('zone'),
            quantite=request.form.get('quantite'),
            difficulte=request.form.get('difficulte'),
            status='En attente',
            payment_status='Pending'
        )
        db.session.add(nouvelle_mission)
        db.session.commit()
        flash('Mission enregistrée. En attente de paiement.', 'success')
        return redirect(url_for('main.client_dashboard'))

    missions = Mission.query.filter_by(client_id=session.get('user_id')).all()
    return render_template('client_dashboard.html', missions=missions)
