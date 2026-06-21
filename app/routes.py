from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Mission, User, Submission, Transaction, CollecteData
import csv
import io

main = Blueprint('main', __name__)

ADMIN_SECRET_CODE = 'DB229ADMIN'

# ─────────────────────────────────────────────
# PAGE D'ACCUEIL
# ─────────────────────────────────────────────
@main.route('/')
def index():
    return render_template('index.html')


# ─────────────────────────────────────────────
# INSCRIPTION
# ─────────────────────────────────────────────
@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        phone    = request.form.get('phone', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        location = request.form.get('location', '').strip()
        role     = request.form.get('role', 'agent')
        secret   = request.form.get('secret_code', '')

        # Vérification code admin
        if role == 'admin' and secret != ADMIN_SECRET_CODE:
            flash("Code administrateur incorrect.", "error")
            return render_template('register.html')

        # Vérifier doublon email / téléphone
        if User.query.filter_by(email=email).first():
            flash("Un compte avec cet email existe déjà.", "error")
            return render_template('register.html')
        if User.query.filter_by(phone=phone).first():
            flash("Un compte avec ce numéro existe déjà.", "error")
            return render_template('register.html')

        user = User(
            fullname=fullname,
            phone=phone,
            email=email,
            password=generate_password_hash(password),
            location=location,
            role=role,
            wallet_balance=0
        )
        db.session.add(user)
        db.session.commit()

        session['user_id']   = user.id
        session['user_role'] = user.role
        session['user_name'] = user.fullname

        if role == 'agent':
            return redirect(url_for('main.agent_dashboard'))
        elif role == 'client':
            return redirect(url_for('main.client_dashboard'))
        else:
            return redirect(url_for('main.admin_dashboard'))

    return render_template('register.html')


# ─────────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────────
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password   = request.form.get('password', '')

        user = User.query.filter(
            (User.email == identifier.lower()) | (User.phone == identifier)
        ).first()

        if not user or not check_password_hash(user.password, password):
            flash("Identifiants incorrects. Vérifiez votre email/téléphone et mot de passe.", "error")
            return render_template('login.html')

        session['user_id']   = user.id
        session['user_role'] = user.role
        session['user_name'] = user.fullname

        if user.role == 'agent':
            return redirect(url_for('main.agent_dashboard'))
        elif user.role == 'client':
            return redirect(url_for('main.client_dashboard'))
        else:
            return redirect(url_for('main.admin_dashboard'))

    return render_template('login.html')


# ─────────────────────────────────────────────
# DÉCONNEXION
# ─────────────────────────────────────────────
@main.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))


# ─────────────────────────────────────────────
# TABLEAU DE BORD AGENT
# ─────────────────────────────────────────────
@main.route('/agent/dashboard')
def agent_dashboard():
    if session.get('user_role') != 'agent':
        flash("Accès réservé aux agents.", "error")
        return redirect(url_for('main.login'))

    agent   = User.query.get_or_404(session['user_id'])
    missions = Mission.query.filter_by(status='Actif').all()
    history  = Transaction.query.filter_by(user_id=agent.id, transaction_type='gain').order_by(Transaction.created_at.desc()).all()

    return render_template('agent_dashboard.html', agent=agent, missions=missions, history=history)


# ─────────────────────────────────────────────
# SOUMISSION AGENT
# ─────────────────────────────────────────────
@main.route('/agent/submit/<int:mission_id>', methods=['GET', 'POST'])
def agent_submit(mission_id):
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))

    mission = Mission.query.get_or_404(mission_id)

    if request.method == 'POST':
        sub = Submission(
            user_id       = session['user_id'],
            mission_id    = mission_id,
            shop_name     = request.form.get('shop_name', '').strip(),
            shop_phone    = request.form.get('shop_phone', '').strip(),
            shop_address  = request.form.get('shop_address', '').strip(),
            observations  = request.form.get('observations', '').strip(),
            data_submitted= request.form.get('observations', ''),
            latitude      = request.form.get('latitude', type=float),
            longitude     = request.form.get('longitude', type=float),
            status        = 'Pending'
        )
        db.session.add(sub)
        db.session.commit()
        flash("Collecte soumise avec succès ! En attente de validation.", "success")
        return redirect(url_for('main.agent_dashboard'))

    return render_template('agent_submit.html', mission=mission)


# ─────────────────────────────────────────────
# TABLEAU DE BORD CLIENT
# ─────────────────────────────────────────────
@main.route('/client/dashboard', methods=['GET', 'POST'])
def client_dashboard():
    if session.get('user_role') != 'client':
        flash("Accès réservé aux clients.", "error")
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        quantite  = int(request.form.get('quantite', 1))
        difficulte= int(request.form.get('difficulte', 500))
        zone_val  = float(request.form.get('zone', 1.2))
        prix      = round(quantite * difficulte * zone_val * 1.4)

        mission = Mission(
            title           = request.form.get('title', '').strip(),
            description     = request.form.get('description', '').strip(),
            instructions    = '',
            price           = prix,
            difficulty      = 'Standard',
            organisation    = request.form.get('organisation', '').strip(),
            contact         = request.form.get('contact', '').strip(),
            type_donnees    = request.form.get('type_donnees', ''),
            zone            = request.form.get('zone', ''),
            quantite        = quantite,
            difficulte      = difficulte,
            format_livraison= request.form.get('format_livraison', 'pdf'),
            photos_requises = request.form.get('photos', 'non'),
            status          = 'En attente',
            payment_status  = 'Pending_Payment',
            client_id       = session['user_id']
        )
        db.session.add(mission)
        db.session.commit()
        flash("Mission créée avec succès ! En attente de validation par l'équipe DataBroker229.", "success")
        return redirect(url_for('main.client_dashboard'))

    missions   = Mission.query.filter_by(client_id=session['user_id']).all()
    data_count = sum(len(m.submissions) for m in missions)
    return render_template('client_dashboard.html', missions=missions, data_count=data_count)


# ─────────────────────────────────────────────
# EXPORT CSV CLIENT
# ─────────────────────────────────────────────
@main.route('/client/export/<int:mission_id>')
def client_export_csv(mission_id):
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))

    mission = Mission.query.get_or_404(mission_id)
    if mission.client_id != session['user_id']:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('main.client_dashboard'))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Commerce', 'Adresse', 'Téléphone', 'Observations', 'Latitude', 'Longitude', 'Date', 'Statut'])
    for s in mission.submissions:
        writer.writerow([s.id, s.shop_name, s.shop_address, s.shop_phone, s.observations, s.latitude, s.longitude, s.submitted_at, s.status])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment;filename=mission_{mission_id}_data.csv"}
    )


# ─────────────────────────────────────────────
# TABLEAU DE BORD ADMIN
# ─────────────────────────────────────────────
@main.route('/admin/dashboard')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        flash("Accès réservé à l'administration.", "error")
        return redirect(url_for('main.login'))

    total_agents       = User.query.filter_by(role='agent').count()
    total_missions     = Mission.query.count()
    all_agents         = User.query.filter_by(role='agent').all()
    pending_submissions= Submission.query.filter_by(status='Pending').all()
    pending_payments   = Mission.query.filter_by(payment_status='Pending_Payment').all()

    return render_template('admin_dashboard.html',
        total_agents       = total_agents,
        total_missions     = total_missions,
        all_agents         = all_agents,
        pending_submissions= pending_submissions,
        pending_payments   = pending_payments
    )


# ─────────────────────────────────────────────
# ADMIN — RÉVISION D'UNE SOUMISSION
# ─────────────────────────────────────────────
@main.route('/admin/review/<int:submission_id>', methods=['GET', 'POST'])
def admin_review(submission_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))

    sub     = Submission.query.get_or_404(submission_id)
    agent   = User.query.get_or_404(sub.user_id)
    mission = Mission.query.get_or_404(sub.mission_id)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'approve':
            sub.status = 'Approved'
            agent.wallet_balance += mission.price
            tx = Transaction(
                user_id          = agent.id,
                mission_id       = mission.id,
                amount           = mission.price,
                transaction_type = 'gain',
                status           = 'Completed'
            )
            db.session.add(tx)
            flash(f"Collecte approuvée ! {mission.price} FCFA versés à {agent.fullname}.", "success")
        elif action == 'reject':
            sub.status = 'Rejected'
            flash("Collecte rejetée.", "info")

        db.session.commit()
        return redirect(url_for('main.admin_dashboard'))

    return render_template('admin_review.html', sub=sub, agent=agent, mission=mission)


# ─────────────────────────────────────────────
# ADMIN — CONFIRMATION PAIEMENT CLIENT
# ─────────────────────────────────────────────
@main.route('/admin/confirm-payment/<int:mission_id>', methods=['POST'])
def admin_confirm_payment(mission_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))

    mission = Mission.query.get_or_404(mission_id)
    mission.payment_status = 'Paid'
    mission.status         = 'Actif'
    db.session.commit()
    flash(f"Paiement confirmé. La mission \"{mission.title}\" est maintenant active.", "success")
    return redirect(url_for('main.admin_dashboard'))


# ─────────────────────────────────────────────
# API — POINTS DE COLLECTE (carte Leaflet)
# ─────────────────────────────────────────────
@main.route('/api/points-collecte')
def api_points_collecte():
    points = CollecteData.query.all()
    data   = [{'id': p.id, 'lat': p.latitude, 'lng': p.longitude, 'description': p.description} for p in points]
    return jsonify(data)
