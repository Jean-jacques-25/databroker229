from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Mission, User, Submission, Transaction, Notification, Retrait, CollecteData
from datetime import datetime
import csv, io, math, os

main = Blueprint('main', __name__)
ADMIN_SECRET_CODE = 'DB229ADMIN'

def notif(user_id, message, type='info'):
    n = Notification(user_id=user_id, message=message, type=type)
    db.session.add(n)

# ─── PAGE D'ACCUEIL ───────────────────────────────────────────
@main.route('/')
def index():
    return render_template('index.html')

# ─── INSCRIPTION ──────────────────────────────────────────────
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

        if role == 'admin' and secret != ADMIN_SECRET_CODE:
            flash("Code administrateur incorrect.", "error")
            return render_template('register.html')
        if User.query.filter_by(email=email).first():
            flash("Un compte avec cet email existe déjà.", "error")
            return render_template('register.html')
        if User.query.filter_by(phone=phone).first():
            flash("Un compte avec ce numéro existe déjà.", "error")
            return render_template('register.html')

        user = User(fullname=fullname, phone=phone, email=email,
                    password=generate_password_hash(password),
                    location=location, role=role, wallet_balance=0)
        db.session.add(user)
        db.session.commit()
        flash("Compte créé avec succès ! Connectez-vous maintenant.", "success")
        return redirect(url_for('main.login'))
    return render_template('register.html')

# ─── CONNEXION ────────────────────────────────────────────────
@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password   = request.form.get('password', '')
        user = User.query.filter(
            (User.email == identifier.lower()) | (User.phone == identifier)
        ).first()
        if not user or not check_password_hash(user.password, password):
            flash("Identifiants incorrects.", "error")
            return render_template('login.html')
        if user.is_suspended:
            flash("Votre compte est suspendu. Contactez le support.", "error")
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

# ─── DÉCONNEXION ──────────────────────────────────────────────
@main.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))

# ══════════════════════════════════════════════════════════════
# ESPACE AGENT
# ══════════════════════════════════════════════════════════════

@main.route('/agent/dashboard')
def agent_dashboard():
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))
    agent    = User.query.get_or_404(session['user_id'])
    missions = Mission.query.filter(Mission.status=='Actif', Mission.is_suspended==False).all()
    history  = Transaction.query.filter_by(user_id=agent.id, transaction_type='gain').order_by(Transaction.created_at.desc()).limit(10).all()
    notifs   = Notification.query.filter_by(user_id=agent.id, is_read=False).order_by(Notification.created_at.desc()).all()
    retraits = Retrait.query.filter_by(agent_id=agent.id).order_by(Retrait.created_at.desc()).limit(5).all()
    return render_template('agent_dashboard.html', agent=agent, missions=missions,
                           history=history, notifs=notifs, retraits=retraits)

def haversine(lat1, lon1, lat2, lon2):
    """Distance en mètres entre deux points GPS."""
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p) * math.cos(lat2*p) *
         math.sin((lon2-lon1)*p/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


@main.route('/agent/submit/<int:mission_id>', methods=['GET', 'POST'])
def agent_submit(mission_id):
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)

    if request.method == 'POST':
        lat  = request.form.get('latitude',  type=float)
        lng  = request.form.get('longitude', type=float)

        # GPS obligatoire
        if not lat or not lng:
            flash("La géolocalisation GPS est obligatoire.", "error")
            return render_template('agent_submit.html', mission=mission)

        # Sauvegarde photo
        photo_path = None
        photo_file = request.files.get('photo')
        if photo_file and photo_file.filename:
            upload_dir = os.path.join('app', 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            filename = f"sub_{session['user_id']}_{mission_id}_{int(__import__('time').time())}.jpg"
            photo_file.save(os.path.join(upload_dir, filename))
            photo_path = f"uploads/{filename}"
        elif mission.photos_requises == 'oui':
            flash("Une photo est obligatoire pour cette mission.", "error")
            return render_template('agent_submit.html', mission=mission)

        # Anti-fraude GPS — vérifier doublons (distance < 50m pour même mission)
        subs_existantes = Submission.query.filter_by(
            user_id=session['user_id'],
            mission_id=mission_id
        ).filter(Submission.latitude.isnot(None)).all()

        statut_auto = 'Pending'
        motif_auto  = None
        for s in subs_existantes:
            dist = haversine(lat, lng, s.latitude, s.longitude)
            if dist < 50:
                statut_auto = 'Rejected'
                motif_auto  = f"Doublon GPS détecté — point déjà collecté à {int(dist)}m de cette position."
                break

        sub = Submission(
            user_id        = session['user_id'],
            mission_id     = mission_id,
            shop_name      = request.form.get('shop_name', '').strip(),
            shop_phone     = request.form.get('shop_phone', '').strip(),
            shop_address   = request.form.get('shop_address', '').strip(),
            observations   = request.form.get('observations', '').strip(),
            data_submitted = request.form.get('observations', ''),
            latitude       = lat,
            longitude      = lng,
            photo_path     = photo_path,
            status         = statut_auto,
            motif_rejet    = motif_auto
        )
        db.session.add(sub)

        agent = User.query.get(session['user_id'])
        agent.total_missions += 1

        if statut_auto == 'Rejected':
            notif(session['user_id'],
                  f"⚠️ Collecte refusée automatiquement pour \"{mission.title}\" — {motif_auto}", 'warning')
            db.session.commit()
            flash("⚠️ Doublon GPS détecté — cette position a déjà été collectée pour cette mission.", "error")
            return redirect(url_for('main.agent_dashboard'))

        notif(session['user_id'], f"Collecte soumise pour \"{mission.title}\" — en attente de validation.", 'info')
        admins = User.query.filter_by(role='admin').all()
        for adm in admins:
            notif(adm.id, f"Nouvelle collecte soumise par {agent.fullname} pour \"{mission.title}\".", 'info')

        db.session.commit()
        flash("Collecte soumise avec succès ! En attente de validation.", "success")
        return redirect(url_for('main.agent_dashboard'))

    return render_template('agent_submit.html', mission=mission)

@main.route('/agent/retrait', methods=['POST'])
def agent_retrait():
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))
    agent  = User.query.get_or_404(session['user_id'])
    montant = int(request.form.get('montant', 0))
    mode   = request.form.get('mode_paiement', '')
    numero = request.form.get('numero_mobile', '').strip()
    if montant <= 0 or montant > agent.wallet_balance:
        flash("Montant invalide ou insuffisant.", "error")
        return redirect(url_for('main.agent_dashboard'))
    r = Retrait(agent_id=agent.id, montant=montant, mode_paiement=mode, numero_mobile=numero)
    agent.wallet_balance -= montant
    db.session.add(r)
    notif(agent.id, f"Demande de retrait de {montant} FCFA via {mode} soumise.", 'info')
    db.session.commit()
    flash(f"Demande de retrait de {montant} FCFA envoyée. Traitement sous 24h.", "success")
    return redirect(url_for('main.agent_dashboard'))

@main.route('/agent/notif-read/<int:notif_id>', methods=['POST'])
def agent_notif_read(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if n.user_id == session.get('user_id'):
        n.is_read = True
        db.session.commit()
    return jsonify({'ok': True})

@main.route('/agent/profile', methods=['GET', 'POST'])
def agent_profile():
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))
    agent = User.query.get_or_404(session['user_id'])
    if request.method == 'POST':
        agent.fullname = request.form.get('fullname', agent.fullname).strip()
        agent.phone    = request.form.get('phone', agent.phone).strip()
        agent.location = request.form.get('location', agent.location).strip()
        db.session.commit()
        flash("Profil mis à jour.", "success")
        return redirect(url_for('main.agent_profile'))
    return render_template('agent_profile.html', agent=agent)

# ══════════════════════════════════════════════════════════════
# ESPACE CLIENT
# ══════════════════════════════════════════════════════════════

@main.route('/client/dashboard', methods=['GET', 'POST'])
def client_dashboard():
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        quantite   = int(request.form.get('quantite', 1))
        difficulte = int(request.form.get('difficulte', 500))
        zone_val   = request.form.get('zone', '1.2')
        prix       = round(quantite * difficulte * float(zone_val) * 1.4)
        mission = Mission(
            title            = request.form.get('title', '').strip(),
            description      = request.form.get('description', '').strip(),
            instructions     = '',
            price            = prix,
            difficulty       = 'Standard',
            organisation     = request.form.get('organisation', '').strip(),
            contact          = request.form.get('contact', '').strip(),
            type_donnees     = request.form.get('type_donnees', ''),
            zone             = zone_val,
            quantite         = quantite,
            difficulte       = difficulte,
            format_livraison = request.form.get('format_livraison', 'pdf'),
            photos_requises  = request.form.get('photos', 'non'),
            status           = 'En attente',
            payment_status   = 'Pending_Payment',
            client_id        = session['user_id']
        )
        db.session.add(mission)
        db.session.commit()
        notif(session['user_id'], f"Mission \"{mission.title}\" créée. En attente de validation.", 'info')
        flash("Mission créée ! En attente de validation par l'équipe DataBroker229.", "success")
        return redirect(url_for('main.client_dashboard'))

    client     = User.query.get_or_404(session['user_id'])
    missions   = Mission.query.filter_by(client_id=session['user_id']).order_by(Mission.created_at.desc()).all()
    data_count = sum(m.points_collectes for m in missions)
    notifs     = Notification.query.filter_by(user_id=session['user_id'], is_read=False).order_by(Notification.created_at.desc()).all()
    budget_mois = sum(m.price for m in missions if m.payment_status == 'Paid')
    return render_template('client_dashboard.html', missions=missions, data_count=data_count,
                           client=client, notifs=notifs, budget_mois=budget_mois)

@main.route('/client/mission/<int:mission_id>')
def client_mission_detail(mission_id):
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    if mission.client_id != session['user_id']:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('main.client_dashboard'))
    submissions = Submission.query.filter_by(mission_id=mission_id).all()
    return render_template('client_mission_detail.html', mission=mission, submissions=submissions)

@main.route('/client/export/<int:mission_id>')
def client_export_csv(mission_id):
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    if mission.client_id != session['user_id']:
        return redirect(url_for('main.client_dashboard'))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Commerce', 'Adresse', 'Téléphone', 'Observations', 'Latitude', 'Longitude', 'Date', 'Statut'])
    for s in mission.submissions:
        writer.writerow([s.id, s.shop_name, s.shop_address, s.shop_phone,
                         s.observations, s.latitude, s.longitude, s.submitted_at, s.status])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment;filename=mission_{mission_id}_data.csv"})

@main.route('/client/profile', methods=['GET', 'POST'])
def client_profile():
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    client = User.query.get_or_404(session['user_id'])
    if request.method == 'POST':
        client.fullname     = request.form.get('fullname', client.fullname).strip()
        client.organisation = request.form.get('organisation', '').strip()
        client.secteur      = request.form.get('secteur', '').strip()
        client.nif_rccm     = request.form.get('nif_rccm', '').strip()
        client.phone        = request.form.get('phone', client.phone).strip()
        db.session.commit()
        flash("Profil entreprise mis à jour.", "success")
        return redirect(url_for('main.client_profile'))
    return render_template('client_profile.html', client=client)

@main.route('/client/notif-read/<int:notif_id>', methods=['POST'])
def client_notif_read(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if n.user_id == session.get('user_id'):
        n.is_read = True
        db.session.commit()
    return jsonify({'ok': True})

# ══════════════════════════════════════════════════════════════
# ESPACE ADMIN
# ══════════════════════════════════════════════════════════════

@main.route('/admin/dashboard')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    total_agents        = User.query.filter_by(role='agent').count()
    total_clients       = User.query.filter_by(role='client').count()
    total_missions      = Mission.query.count()
    all_agents          = User.query.filter_by(role='agent').order_by(User.wallet_balance.desc()).all()
    pending_submissions = Submission.query.filter_by(status='Pending').order_by(Submission.submitted_at.desc()).all()
    pending_payments    = Mission.query.filter_by(payment_status='Pending_Payment').all()
    pending_retraits    = Retrait.query.filter_by(status='En attente').order_by(Retrait.created_at.desc()).all()
    total_pending_pay   = sum(r.montant for r in pending_retraits)
    today               = datetime.utcnow().date()
    collectes_today     = Submission.query.filter(db.func.date(Submission.submitted_at) == today).count()

    # Activité 7 derniers jours
    from datetime import timedelta
    activite = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = Submission.query.filter(db.func.date(Submission.submitted_at) == d).count()
        activite.append({'date': d.strftime('%d/%m'), 'count': count})

    return render_template('admin_dashboard.html',
        total_agents=total_agents, total_clients=total_clients,
        total_missions=total_missions, all_agents=all_agents,
        pending_submissions=pending_submissions, pending_payments=pending_payments,
        pending_retraits=pending_retraits, total_pending_pay=total_pending_pay,
        collectes_today=collectes_today, activite=activite)

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
            tx = Transaction(user_id=agent.id, mission_id=mission.id,
                             amount=mission.price, transaction_type='gain', status='Completed')
            db.session.add(tx)
            notif(agent.id, f"✅ Collecte validée pour \"{mission.title}\" — +{mission.price} FCFA crédités !", 'success')
            if mission.client_id:
                notif(mission.client_id, f"Nouvelle collecte validée pour votre mission \"{mission.title}\".", 'success')
            flash(f"Collecte approuvée ! {mission.price} FCFA versés à {agent.fullname}.", "success")
        elif action == 'reject':
            motif = request.form.get('motif_rejet', '').strip()
            sub.status      = 'Rejected'
            sub.motif_rejet = motif
            notif(agent.id, f"❌ Collecte rejetée pour \"{mission.title}\". Motif : {motif or 'Non précisé'}", 'warning')
            flash("Collecte rejetée.", "info")
        db.session.commit()
        return redirect(url_for('main.admin_dashboard'))
    return render_template('admin_review.html', sub=sub, agent=agent, mission=mission)

@main.route('/admin/confirm-payment/<int:mission_id>', methods=['POST'])
def admin_confirm_payment(mission_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    mission.payment_status = 'Paid'
    mission.status         = 'Actif'
    if mission.client_id:
        notif(mission.client_id, f"💳 Paiement confirmé pour \"{mission.title}\". La mission est maintenant active !", 'success')
    db.session.commit()
    flash(f"Paiement confirmé. Mission \"{mission.title}\" activée.", "success")
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/retrait/<int:retrait_id>/payer', methods=['POST'])
def admin_payer_retrait(retrait_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    r = Retrait.query.get_or_404(retrait_id)
    r.status  = 'Payé'
    r.paid_at = datetime.utcnow()
    notif(r.agent_id, f"💰 Retrait de {r.montant} FCFA via {r.mode_paiement} effectué avec succès !", 'success')
    db.session.commit()
    flash(f"Retrait de {r.montant} FCFA marqué comme payé.", "success")
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/mission/<int:mission_id>/suspendre', methods=['POST'])
def admin_suspendre_mission(mission_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    mission.is_suspended = not mission.is_suspended
    mission.status = 'Suspendue' if mission.is_suspended else 'Actif'
    db.session.commit()
    flash(f"Mission {'suspendue' if mission.is_suspended else 'réactivée'}.", "success")
    return redirect(url_for('main.admin_missions'))

@main.route('/admin/missions')
def admin_missions():
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    missions = Mission.query.order_by(Mission.created_at.desc()).all()
    return render_template('admin_missions.html', missions=missions)

@main.route('/admin/agent/<int:agent_id>/suspendre', methods=['POST'])
def admin_suspendre_agent(agent_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    agent = User.query.get_or_404(agent_id)
    agent.is_suspended = not agent.is_suspended
    db.session.commit()
    flash(f"Agent {'suspendu' if agent.is_suspended else 'réactivé'}.", "success")
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/export/agents')
def admin_export_agents():
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Nom', 'Email', 'Téléphone', 'Zone', 'Niveau', 'Missions', 'Solde', 'Fiabilité'])
    for a in User.query.filter_by(role='agent').all():
        writer.writerow([a.id, a.fullname, a.email, a.phone, a.location,
                         a.niveau, a.total_missions, a.wallet_balance, f"{a.reliability_score}%"])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=agents_databroker229.csv"})

# ── API ────────────────────────────────────────────────────────
@main.route('/api/points-collecte')
def api_points_collecte():
    points = CollecteData.query.all()
    return jsonify([{'id': p.id, 'lat': p.latitude, 'lng': p.longitude, 'description': p.description} for p in points])

@main.route('/api/mission-points/<int:mission_id>')
def api_mission_points(mission_id):
    subs = Submission.query.filter_by(mission_id=mission_id, status='Approved').all()
    return jsonify([{'id': s.id, 'lat': s.latitude, 'lng': s.longitude,
                     'nom': s.shop_name, 'adresse': s.shop_address} for s in subs if s.latitude])

# ── ROUTE SECRÈTE ADMIN ────────────────────────────────────────
@main.route('/setup-admin-db229secret')
def setup_admin():
    try:
        # Recréer toutes les tables avec le nouveau schéma
        db.drop_all()
        db.create_all()

        # Créer le compte admin
        admin = User(
            fullname="Admin DataBroker",
            email="admin@databroker229.com",
            phone="00000000",
            password=generate_password_hash("admin229"),
            role="admin",
            location="Cotonou",
            wallet_balance=0
        )
        db.session.add(admin)
        db.session.commit()
        return """
        <div style='font-family:monospace;padding:40px;background:#0a0a0a;color:#fff;min-height:100vh;'>
            <h2 style='color:#10b981;'>✅ Base de données réinitialisée avec succès !</h2>
            <p style='color:#888;margin-top:16px;'>Toutes les tables ont été recréées avec le nouveau schéma.</p>
            <p style='margin-top:12px;'>Email : <strong style='color:#f59e0b;'>admin@databroker229.com</strong></p>
            <p>Mot de passe : <strong style='color:#f59e0b;'>admin229</strong></p>
            <a href='/login' style='display:inline-block;margin-top:24px;background:#f59e0b;color:#000;padding:12px 24px;border-radius:100px;text-decoration:none;font-weight:800;'>→ Se connecter</a>
        </div>
        """
    except Exception as e:
        db.session.rollback()
        return f"<div style='font-family:monospace;padding:40px;color:red;'>❌ Erreur : {str(e)}</div>"
