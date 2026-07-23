#!/bin/bash
# ================================================================
# patch_and_push.sh — DataBroker229
# Corrige tous les fichiers et pousse sur GitHub
# Usage : bash patch_and_push.sh
# ================================================================

set -e  # Arrêter si une commande échoue
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   DataBroker229 — Patch & Push GitHub    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ──────────────────────────────────────────
# 1. requirements.txt
# ──────────────────────────────────────────
echo "📦 [1/6] Correction requirements.txt..."
python3 << 'PYEOF'
with open('requirements.txt', 'w') as f:
    f.write("""flask
flask-sqlalchemy
flask-migrate
flask-wtf
werkzeug
gunicorn
""")
print("    ✅ requirements.txt OK")
PYEOF

# ──────────────────────────────────────────
# 2. app/models.py
# ──────────────────────────────────────────
echo "🗄️  [2/6] Correction app/models.py..."
python3 << 'PYEOF'
content = '''from app import db
from datetime import datetime

class User(db.Model):
    __tablename__ = \'users\'

    id             = db.Column(db.Integer, primary_key=True)
    fullname       = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    phone          = db.Column(db.String(20),  unique=True, nullable=False)
    password       = db.Column(db.String(200), nullable=False)
    role           = db.Column(db.String(20),  nullable=False, default=\'agent\')
    location       = db.Column(db.String(100), nullable=True)
    wallet_balance = db.Column(db.Integer, default=0, nullable=False)

    submissions = db.relationship(\'Submission\', backref=\'agent\', lazy=True)

    @property
    def reliability_score(self):
        return 100


class Mission(db.Model):
    __tablename__ = \'missions\'

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(150), nullable=False)
    description  = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    price        = db.Column(db.Integer, nullable=False)
    difficulty   = db.Column(db.String(20), default=\'Standard\')
    deadline     = db.Column(db.DateTime, nullable=True)
    client_id    = db.Column(db.Integer, db.ForeignKey(\'users.id\'), nullable=True)

    organisation     = db.Column(db.String(100))
    contact          = db.Column(db.String(100))
    type_donnees     = db.Column(db.String(50))
    zone             = db.Column(db.String(50))
    quantite         = db.Column(db.Integer)
    difficulte       = db.Column(db.Integer)
    format_livraison = db.Column(db.String(20))
    photos_requises  = db.Column(db.String(5), default=\'non\')

    status         = db.Column(db.String(20),  default=\'En attente\')
    payment_status = db.Column(db.String(30),  default=\'Pending_Payment\')

    submissions = db.relationship(\'Submission\', backref=\'mission\', lazy=True)


class Submission(db.Model):
    __tablename__ = \'submissions\'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey(\'users.id\'),    nullable=False)
    mission_id  = db.Column(db.Integer, db.ForeignKey(\'missions.id\'), nullable=False)

    data_submitted = db.Column(db.Text,        nullable=True)
    shop_name      = db.Column(db.String(150), nullable=True)
    shop_phone     = db.Column(db.String(30),  nullable=True)
    shop_address   = db.Column(db.String(200), nullable=True)
    observations   = db.Column(db.Text,        nullable=True)
    photo_path     = db.Column(db.String(300), nullable=True)
    latitude       = db.Column(db.Float,       nullable=True)
    longitude      = db.Column(db.Float,       nullable=True)

    status       = db.Column(db.String(20), default=\'Pending\')
    submitted_at = db.Column(db.DateTime,   default=datetime.utcnow)


class Transaction(db.Model):
    __tablename__ = \'transactions\'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey(\'users.id\'),    nullable=False)
    mission_id       = db.Column(db.Integer, db.ForeignKey(\'missions.id\'), nullable=True)
    amount           = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    status           = db.Column(db.String(20), default=\'Completed\')
    created_at       = db.Column(db.DateTime,   default=datetime.utcnow)

    user    = db.relationship(\'User\',    backref=db.backref(\'transactions\', lazy=True))
    mission = db.relationship(\'Mission\', backref=db.backref(\'transactions\', lazy=True))


class CollecteData(db.Model):
    __tablename__ = \'collecte_data\'

    id            = db.Column(db.Integer, primary_key=True)
    description   = db.Column(db.String(200), nullable=False)
    latitude      = db.Column(db.Float, nullable=False)
    longitude     = db.Column(db.Float, nullable=False)
    agent_id      = db.Column(db.Integer, db.ForeignKey(\'users.id\'), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
'''
with open('app/models.py', 'w') as f:
    f.write(content)
print("    ✅ models.py OK")
PYEOF

# ──────────────────────────────────────────
# 3. app/routes.py
# ──────────────────────────────────────────
echo "🛣️  [3/6] Correction app/routes.py..."
python3 << 'PYEOF'
content = '''from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Mission, User, Submission, Transaction, CollecteData
import csv
import io

main = Blueprint(\'main\', __name__)

ADMIN_SECRET_CODE = \'DB229ADMIN\'

# ─────────────────────────────────────────────
# PAGE D\'ACCUEIL
# ─────────────────────────────────────────────
@main.route(\'/\')
def index():
    return render_template(\'index.html\')


# ─────────────────────────────────────────────
# INSCRIPTION
# ─────────────────────────────────────────────
@main.route(\'/register\', methods=[\'GET\', \'POST\'])
def register():
    if request.method == \'POST\':
        fullname = request.form.get(\'fullname\', \'\').strip()
        phone    = request.form.get(\'phone\', \'\').strip()
        email    = request.form.get(\'email\', \'\').strip().lower()
        password = request.form.get(\'password\', \'\')
        location = request.form.get(\'location\', \'\').strip()
        role     = request.form.get(\'role\', \'agent\')
        secret   = request.form.get(\'secret_code\', \'\')

        if role == \'admin\' and secret != ADMIN_SECRET_CODE:
            flash("Code administrateur incorrect.", "error")
            return render_template(\'register.html\')

        if User.query.filter_by(email=email).first():
            flash("Un compte avec cet email existe déjà.", "error")
            return render_template(\'register.html\')
        if User.query.filter_by(phone=phone).first():
            flash("Un compte avec ce numéro existe déjà.", "error")
            return render_template(\'register.html\')

        user = User(
            fullname=fullname, phone=phone, email=email,
            password=generate_password_hash(password),
            location=location, role=role, wallet_balance=0
        )
        db.session.add(user)
        db.session.commit()

        session[\'user_id\']   = user.id
        session[\'user_role\'] = user.role
        session[\'user_name\'] = user.fullname

        if role == \'agent\':
            return redirect(url_for(\'main.agent_dashboard\'))
        elif role == \'client\':
            return redirect(url_for(\'main.client_dashboard\'))
        else:
            return redirect(url_for(\'main.admin_dashboard\'))

    return render_template(\'register.html\')


# ─────────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────────
@main.route(\'/login\', methods=[\'GET\', \'POST\'])
def login():
    if request.method == \'POST\':
        identifier = request.form.get(\'identifier\', \'\').strip()
        password   = request.form.get(\'password\', \'\')

        user = User.query.filter(
            (User.email == identifier.lower()) | (User.phone == identifier)
        ).first()

        if not user or not check_password_hash(user.password, password):
            flash("Identifiants incorrects. Vérifiez votre email/téléphone et mot de passe.", "error")
            return render_template(\'login.html\')

        session[\'user_id\']   = user.id
        session[\'user_role\'] = user.role
        session[\'user_name\'] = user.fullname

        if user.role == \'agent\':
            return redirect(url_for(\'main.agent_dashboard\'))
        elif user.role == \'client\':
            return redirect(url_for(\'main.client_dashboard\'))
        else:
            return redirect(url_for(\'main.admin_dashboard\'))

    return render_template(\'login.html\')


# ─────────────────────────────────────────────
# DÉCONNEXION
# ─────────────────────────────────────────────
@main.route(\'/logout\')
def logout():
    session.clear()
    return redirect(url_for(\'main.index\'))


# ─────────────────────────────────────────────
# TABLEAU DE BORD AGENT
# ─────────────────────────────────────────────
@main.route(\'/agent/dashboard\')
def agent_dashboard():
    if session.get(\'user_role\') != \'agent\':
        flash("Accès réservé aux agents.", "error")
        return redirect(url_for(\'main.login\'))

    agent    = User.query.get_or_404(session[\'user_id\'])
    missions = Mission.query.filter_by(status=\'Actif\').all()
    history  = Transaction.query.filter_by(user_id=agent.id, transaction_type=\'gain\').order_by(Transaction.created_at.desc()).all()

    return render_template(\'agent_dashboard.html\', agent=agent, missions=missions, history=history)


# ─────────────────────────────────────────────
# SOUMISSION AGENT
# ─────────────────────────────────────────────
@main.route(\'/agent/submit/<int:mission_id>\', methods=[\'GET\', \'POST\'])
def agent_submit(mission_id):
    if session.get(\'user_role\') != \'agent\':
        return redirect(url_for(\'main.login\'))

    mission = Mission.query.get_or_404(mission_id)

    if request.method == \'POST\':
        sub = Submission(
            user_id        = session[\'user_id\'],
            mission_id     = mission_id,
            shop_name      = request.form.get(\'shop_name\', \'\').strip(),
            shop_phone     = request.form.get(\'shop_phone\', \'\').strip(),
            shop_address   = request.form.get(\'shop_address\', \'\').strip(),
            observations   = request.form.get(\'observations\', \'\').strip(),
            data_submitted = request.form.get(\'observations\', \'\'),
            latitude       = request.form.get(\'latitude\', type=float),
            longitude      = request.form.get(\'longitude\', type=float),
            status         = \'Pending\'
        )
        db.session.add(sub)
        db.session.commit()
        flash("Collecte soumise avec succès ! En attente de validation.", "success")
        return redirect(url_for(\'main.agent_dashboard\'))

    return render_template(\'agent_submit.html\', mission=mission)


# ─────────────────────────────────────────────
# TABLEAU DE BORD CLIENT
# ─────────────────────────────────────────────
@main.route(\'/client/dashboard\', methods=[\'GET\', \'POST\'])
def client_dashboard():
    if session.get(\'user_role\') != \'client\':
        flash("Accès réservé aux clients.", "error")
        return redirect(url_for(\'main.login\'))

    if request.method == \'POST\':
        quantite   = int(request.form.get(\'quantite\', 1))
        difficulte = int(request.form.get(\'difficulte\', 500))
        zone_val   = float(request.form.get(\'zone\', 1.2))
        prix       = round(quantite * difficulte * zone_val * 1.4)

        mission = Mission(
            title            = request.form.get(\'title\', \'\').strip(),
            description      = request.form.get(\'description\', \'\').strip(),
            instructions     = \'\',
            price            = prix,
            difficulty       = \'Standard\',
            organisation     = request.form.get(\'organisation\', \'\').strip(),
            contact          = request.form.get(\'contact\', \'\').strip(),
            type_donnees     = request.form.get(\'type_donnees\', \'\'),
            zone             = request.form.get(\'zone\', \'\'),
            quantite         = quantite,
            difficulte       = difficulte,
            format_livraison = request.form.get(\'format_livraison\', \'pdf\'),
            photos_requises  = request.form.get(\'photos\', \'non\'),
            status           = \'En attente\',
            payment_status   = \'Pending_Payment\',
            client_id        = session[\'user_id\']
        )
        db.session.add(mission)
        db.session.commit()
        flash("Mission créée ! En attente de validation par l\'équipe DataBroker229.", "success")
        return redirect(url_for(\'main.client_dashboard\'))

    missions   = Mission.query.filter_by(client_id=session[\'user_id\']).all()
    data_count = sum(len(m.submissions) for m in missions)
    return render_template(\'client_dashboard.html\', missions=missions, data_count=data_count)


# ─────────────────────────────────────────────
# EXPORT CSV CLIENT
# ─────────────────────────────────────────────
@main.route(\'/client/export/<int:mission_id>\')
def client_export_csv(mission_id):
    if session.get(\'user_role\') != \'client\':
        return redirect(url_for(\'main.login\'))

    mission = Mission.query.get_or_404(mission_id)
    if mission.client_id != session[\'user_id\']:
        flash("Accès non autorisé.", "error")
        return redirect(url_for(\'main.client_dashboard\'))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([\'ID\', \'Commerce\', \'Adresse\', \'Téléphone\', \'Observations\', \'Latitude\', \'Longitude\', \'Date\', \'Statut\'])
    for s in mission.submissions:
        writer.writerow([s.id, s.shop_name, s.shop_address, s.shop_phone, s.observations, s.latitude, s.longitude, s.submitted_at, s.status])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype=\'text/csv\',
        headers={"Content-Disposition": f"attachment;filename=mission_{mission_id}_data.csv"}
    )


# ─────────────────────────────────────────────
# TABLEAU DE BORD ADMIN
# ─────────────────────────────────────────────
@main.route(\'/admin/dashboard\')
def admin_dashboard():
    if session.get(\'user_role\') != \'admin\':
        flash("Accès réservé à l\'administration.", "error")
        return redirect(url_for(\'main.login\'))

    total_agents        = User.query.filter_by(role=\'agent\').count()
    total_missions      = Mission.query.count()
    all_agents          = User.query.filter_by(role=\'agent\').all()
    pending_submissions = Submission.query.filter_by(status=\'Pending\').all()
    pending_payments    = Mission.query.filter_by(payment_status=\'Pending_Payment\').all()

    return render_template(\'admin_dashboard.html\',
        total_agents        = total_agents,
        total_missions      = total_missions,
        all_agents          = all_agents,
        pending_submissions = pending_submissions,
        pending_payments    = pending_payments
    )


# ─────────────────────────────────────────────
# ADMIN — RÉVISION SOUMISSION
# ─────────────────────────────────────────────
@main.route(\'/admin/review/<int:submission_id>\', methods=[\'GET\', \'POST\'])
def admin_review(submission_id):
    if session.get(\'user_role\') != \'admin\':
        return redirect(url_for(\'main.login\'))

    sub     = Submission.query.get_or_404(submission_id)
    agent   = User.query.get_or_404(sub.user_id)
    mission = Mission.query.get_or_404(sub.mission_id)

    if request.method == \'POST\':
        action = request.form.get(\'action\')
        if action == \'approve\':
            sub.status = \'Approved\'
            agent.wallet_balance += mission.price
            tx = Transaction(
                user_id=agent.id, mission_id=mission.id,
                amount=mission.price, transaction_type=\'gain\', status=\'Completed\'
            )
            db.session.add(tx)
            flash(f"Collecte approuvée ! {mission.price} FCFA versés à {agent.fullname}.", "success")
        elif action == \'reject\':
            sub.status = \'Rejected\'
            flash("Collecte rejetée.", "info")

        db.session.commit()
        return redirect(url_for(\'main.admin_dashboard\'))

    return render_template(\'admin_review.html\', sub=sub, agent=agent, mission=mission)


# ─────────────────────────────────────────────
# ADMIN — CONFIRMATION PAIEMENT CLIENT
# ─────────────────────────────────────────────
@main.route(\'/admin/confirm-payment/<int:mission_id>\', methods=[\'POST\'])
def admin_confirm_payment(mission_id):
    if session.get(\'user_role\') != \'admin\':
        return redirect(url_for(\'main.login\'))

    mission = Mission.query.get_or_404(mission_id)
    mission.payment_status = \'Paid\'
    mission.status         = \'Actif\'
    db.session.commit()
    flash(f"Paiement confirmé. La mission \\"{mission.title}\\" est maintenant active.", "success")
    return redirect(url_for(\'main.admin_dashboard\'))


# ─────────────────────────────────────────────
# API — POINTS DE COLLECTE (carte Leaflet)
# ─────────────────────────────────────────────
@main.route(\'/api/points-collecte\')
def api_points_collecte():
    points = CollecteData.query.all()
    data   = [{\'id\': p.id, \'lat\': p.latitude, \'lng\': p.longitude, \'description\': p.description} for p in points]
    return jsonify(data)
'''
with open('app/routes.py', 'w') as f:
    f.write(content)
print("    ✅ routes.py OK")
PYEOF

# ──────────────────────────────────────────
# 4. app/admin_routes.py
# ──────────────────────────────────────────
echo "🔧 [4/6] Correction app/admin_routes.py..."
python3 << 'PYEOF'
content = '''# admin_routes.py — Blueprint conservé pour compatibilité
# Toutes les routes admin sont dans routes.py (blueprint main)
from flask import Blueprint
admin = Blueprint(\'admin\', __name__)
'''
with open('app/admin_routes.py', 'w') as f:
    f.write(content)
print("    ✅ admin_routes.py OK")
PYEOF

# ──────────────────────────────────────────
# 5. app/templates/admin_dashboard.html
# ──────────────────────────────────────────
echo "🖥️  [5/6] Correction templates/admin_dashboard.html..."
python3 << 'PYEOF'
content = '''{% extends "base.html" %}
{% block content %}

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<div class="bg-gray-900 min-h-screen text-gray-100 py-8">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">

        <div class="flex justify-between items-center border-b border-gray-800 pb-6 mb-8">
            <div>
                <h1 class="text-2xl font-black tracking-tight text-white">Console de Supervision Générale</h1>
                <p class="text-xs text-gray-400 mt-1">Gestion des flux de données terrain de DataBroker229</p>
            </div>
            <span class="px-3 py-1 bg-amber-500/10 text-amber-400 text-xs font-bold rounded-full border border-amber-500/20">
                Mode Admin Actif
            </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
            <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6">
                <div class="text-gray-400 text-xs font-bold uppercase tracking-wider">Agents Enregistrés</div>
                <div class="text-3xl font-black text-white mt-2 flex items-baseline gap-2">
                    {{ total_agents }}
                    <span class="text-xs font-normal text-emerald-400">Actifs au Bénin</span>
                </div>
            </div>
            <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6">
                <div class="text-gray-400 text-xs font-bold uppercase tracking-wider">Total Campagnes</div>
                <div class="text-3xl font-black text-white mt-2">{{ total_missions }}</div>
            </div>
            <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6 {% if pending_submissions|length > 0 %}border-amber-500/40 bg-amber-500/5{% endif %}">
                <div class="text-gray-400 text-xs font-bold uppercase tracking-wider">Dossiers à contrôler</div>
                <div class="text-3xl font-black mt-2 {% if pending_submissions|length > 0 %}text-amber-400{% else %}text-white{% endif %}">
                    {{ pending_submissions|length }}
                </div>
            </div>
        </div>

        <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6 mb-8">
            <h2 class="text-lg font-bold text-white mb-4">📍 Suivi Cartographique des Collectes</h2>
            <div id="map" class="w-full rounded-xl border border-gray-700 overflow-hidden" style="height: 420px; z-index: 1;"></div>
        </div>

        <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6 mb-8">
            <h2 class="text-lg font-bold text-amber-400 mb-4">💰 Dépôts Clients en attente de validation</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="bg-gray-700/50 text-gray-400 text-xs uppercase font-bold">
                        <tr>
                            <th class="p-4">ID</th>
                            <th class="p-4">Mission</th>
                            <th class="p-4">Budget</th>
                            <th class="p-4">Action</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-700">
                        {% for mission in pending_payments %}
                        <tr class="hover:bg-gray-700/30">
                            <td class="p-4 text-gray-500">#{{ mission.id }}</td>
                            <td class="p-4 font-semibold text-white">{{ mission.title }}</td>
                            <td class="p-4 font-bold text-emerald-400">{{ mission.price }} FCFA</td>
                            <td class="p-4">
                                <form action="/admin/confirm-payment/{{ mission.id }}" method="POST" class="inline">
                                    <button type="submit" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-gray-900 text-xs font-bold rounded-lg transition-colors">
                                        ✅ Confirmer réception des fonds
                                    </button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="4" class="p-4 text-center text-gray-500">Aucun paiement client en attente.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6 mb-8">
            <h2 class="text-lg font-bold text-white mb-4">⏳ Collectes en attente de vérification</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="bg-gray-700/50 text-gray-400 text-xs uppercase font-bold">
                        <tr>
                            <th class="p-4">Agent</th>
                            <th class="p-4">Commerce</th>
                            <th class="p-4">Adresse</th>
                            <th class="p-4">Action</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-700">
                        {% for sub in pending_submissions %}
                        <tr class="hover:bg-gray-700/30">
                            <td class="p-4 font-semibold text-white">{{ sub.agent.fullname }}</td>
                            <td class="p-4">{{ sub.shop_name or "—" }}</td>
                            <td class="p-4 text-gray-400">{{ sub.shop_address or "—" }}</td>
                            <td class="p-4">
                                <a href="/admin/review/{{ sub.id }}" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg transition-colors">
                                    🔍 Inspecter & Payer
                                </a>
                            </td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="4" class="p-4 text-center text-gray-500">Aucun dossier en attente.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="bg-gray-800 border border-gray-700 rounded-2xl p-6">
            <h2 class="text-lg font-bold text-white mb-4">👥 Performance des Agents</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-gray-300">
                    <thead class="bg-gray-700/50 text-gray-400 text-xs uppercase font-bold">
                        <tr>
                            <th class="p-4">Nom complet</th>
                            <th class="p-4">Téléphone</th>
                            <th class="p-4">Fiabilité</th>
                            <th class="p-4">Solde</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-700">
                        {% for agent in all_agents %}
                        <tr class="hover:bg-gray-700/30">
                            <td class="p-4 font-semibold text-white">{{ agent.fullname }}</td>
                            <td class="p-4 font-mono">{{ agent.phone }}</td>
                            <td class="p-4"><span class="text-emerald-400 font-bold">100%</span></td>
                            <td class="p-4 font-bold text-emerald-400">{{ agent.wallet_balance }} FCFA</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="4" class="p-4 text-center text-gray-500">Aucun agent enregistré.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

    </div>
</div>

<script>
    var map = L.map(\'map\').setView([6.3703, 2.4406], 12);
    L.tileLayer(\'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png\', {
        attribution: \'© OpenStreetMap contributors\'
    }).addTo(map);

    {% for sub in pending_submissions %}
        {% if sub.latitude and sub.longitude %}
        L.marker([{{ sub.latitude }}, {{ sub.longitude }}]).addTo(map)
            .bindPopup(\'<b>{{ sub.shop_name or "Commerce" }}</b><br>Agent : {{ sub.agent.fullname }}<br>#SUB-{{ sub.id }}\');
        {% endif %}
    {% endfor %}

    fetch(\'/api/points-collecte\')
        .then(r => r.json())
        .then(data => {
            data.forEach(p => {
                L.marker([p.lat, p.lng]).addTo(map)
                    .bindPopup(\'<b>📍 Validée #\' + p.id + \'</b><br>\' + p.description);
            });
        })
        .catch(err => console.error("Erreur carte:", err));
</script>
{% endblock %}
'''
with open('app/templates/admin_dashboard.html', 'w') as f:
    f.write(content)
print("    ✅ admin_dashboard.html OK")
PYEOF

# ──────────────────────────────────────────
# 6. app/templates/admin_review.html + register.html
# ──────────────────────────────────────────
echo "📄 [6/6] Correction templates admin_review.html & register.html..."
python3 << 'PYEOF'
review = '''{% extends "base.html" %}
{% block content %}
<div class="max-w-4xl mx-auto my-10 px-4">
    <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="bg-gray-900 text-white p-6">
            <h1 class="text-xl font-black">Contrôle Qualité : Mission #{{ mission.id }}</h1>
            <p class="text-xs text-gray-400 mt-1">Soumis par l\'agent : {{ agent.fullname }}</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-gray-100">
            <div class="p-6 flex flex-col justify-center bg-gray-50">
                <p class="text-xs font-bold text-gray-400 uppercase mb-2">Cliché de preuve terrain</p>
                {% if sub.photo_path %}
                    <img src="{{ url_for(\'static\', filename=sub.photo_path) }}" class="w-full h-auto rounded-xl shadow-sm border border-gray-200">
                {% else %}
                    <div class="w-full h-48 flex items-center justify-center bg-gray-100 rounded-xl border border-gray-200 text-gray-400 text-sm">
                        📷 Aucune photo soumise
                    </div>
                {% endif %}
            </div>
            <div class="p-6 space-y-4">
                <div>
                    <h3 class="text-xs font-bold text-gray-400 uppercase">Infos Commerce</h3>
                    <p class="text-sm font-bold text-gray-800 mt-1">{{ sub.shop_name or "—" }}</p>
                    <p class="text-xs text-gray-500">Tel gérant : {{ sub.shop_phone or "—" }}</p>
                    <p class="text-xs text-gray-500">Adresse : {{ sub.shop_address or "—" }}</p>
                </div>
                <div>
                    <h3 class="text-xs font-bold text-gray-400 uppercase">Géolocalisation</h3>
                    {% if sub.latitude and sub.longitude %}
                        <p class="text-xs text-blue-600 font-mono bg-blue-50 p-2 rounded-lg mt-1">
                            Lat: {{ sub.latitude }} / Lng: {{ sub.longitude }}
                        </p>
                    {% else %}
                        <p class="text-xs text-gray-400 italic mt-1">Coordonnées non disponibles</p>
                    {% endif %}
                </div>
                <div>
                    <h3 class="text-xs font-bold text-gray-400 uppercase">Observations Agent</h3>
                    <p class="text-sm text-gray-600 italic">"{{ sub.observations or \'Aucune note.\' }}"</p>
                </div>
                <div>
                    <h3 class="text-xs font-bold text-gray-400 uppercase">Rémunération prévue</h3>
                    <p class="text-lg font-black text-emerald-600 mt-1">{{ mission.price }} FCFA</p>
                </div>
                <form action="{{ url_for(\'main.admin_review\', submission_id=sub.id) }}" method="POST" class="pt-4 border-t border-gray-100 flex gap-4">
                    <button type="submit" name="action" value="approve"
                        class="flex-1 bg-emerald-600 text-white font-bold py-3 rounded-xl hover:bg-emerald-700 transition text-sm">
                        ✅ Approuver & Payer
                    </button>
                    <button type="submit" name="action" value="reject"
                        class="flex-1 bg-red-600 text-white font-bold py-3 rounded-xl hover:bg-red-700 transition text-sm">
                        ❌ Rejeter
                    </button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
'''

register = '''{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto my-16 bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
    <h2 class="text-2xl font-bold text-gray-900 text-center mb-2">Créer un compte</h2>
    <p class="text-sm text-gray-500 text-center mb-8">Rejoignez Databroker229 dès aujourd\'hui</p>

    {% with messages = get_flashed_messages() %}
        {% if messages %}
            <div class="bg-red-50 text-red-600 p-3 rounded-lg text-sm mb-4 font-medium">
                {{ messages[0] }}
            </div>
        {% endif %}
    {% endwith %}

    <form method="POST" action="/register" class="space-y-4">
        <div>
            <label class="block text-xs font-bold text-gray-500 uppercase mb-1">Votre Profil *</label>
            <select name="role" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600 bg-white" required>
                <option value="agent">Agent de collecte (Terrain)</option>
                <option value="client">Entreprise / Client (Commande de données)</option>
            </select>
        </div>
        <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1">Nom complet</label>
            <input type="text" name="fullname" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600" placeholder="Ex: Jean-Jacques Agan" required>
        </div>
        <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1">Numéro de téléphone</label>
            <input type="text" name="phone" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600" placeholder="Ex: +229 01000000" required>
        </div>
        <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1">Adresse Email</label>
            <input type="email" name="email" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600" placeholder="exemple@mail.com" required>
        </div>
        <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1">Mot de passe</label>
            <input type="password" name="password" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600" placeholder="••••••••" required>
        </div>
        <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1">Zone de localisation principale</label>
            <input type="text" name="location" class="w-full border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-600" placeholder="Ex: Cotonou, Calavi, Parakou..." required>
        </div>
        <button type="submit" class="w-full bg-blue-600 text-white font-semibold py-3 rounded-lg hover:bg-blue-700 transition mt-6">
            S\'inscrire
        </button>
    </form>

    <p class="text-xs text-center text-gray-500 mt-6">
        Vous avez déjà un compte ? <a href="/login" class="text-blue-600 font-semibold hover:underline">Connectez-vous ici</a>
    </p>
</div>
{% endblock %}
'''

with open('app/templates/admin_review.html', 'w') as f:
    f.write(review)
with open('app/templates/register.html', 'w') as f:
    f.write(register)
print("    ✅ admin_review.html OK")
print("    ✅ register.html OK")
PYEOF

# ──────────────────────────────────────────
# VÉRIFICATION RAPIDE
# ──────────────────────────────────────────
echo ""
echo "🔍 Vérification Flask..."
python3 -c "
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    routes = [str(r) for r in app.url_map.iter_rules()]
    expected = [
        '/static/<path:filename>',
        '/', '/login', '/logout', '/register',
        '/agent/dashboard', '/agent/submit/<int:mission_id>',
        '/client/dashboard', '/client/export/<int:mission_id>',
        '/admin/dashboard', '/admin/review/<int:submission_id>',
        '/admin/confirm-payment/<int:mission_id>',
        '/api/points-collecte'
    ]
    all_ok = True
    for e in expected:
        found = e in routes
        print(f'  {\"✅\" if found else \"❌\"} {e}')
        if not found:
            all_ok = False
    if all_ok:
        print()
        print('  ✅ Toutes les routes sont présentes.')
    else:
        print()
        print('  ❌ Certaines routes manquent — vérifiez les erreurs ci-dessus.')
"

# ──────────────────────────────────────────
# GIT PUSH
# ──────────────────────────────────────────
echo ""
echo "🚀 Envoi sur GitHub..."
git add app/models.py app/routes.py app/admin_routes.py \
        app/templates/admin_dashboard.html \
        app/templates/admin_review.html \
        app/templates/register.html \
        requirements.txt

git commit -m "fix: correction bugs critiques — routes manquantes, models dupliqués, templates Jinja cassés"
git push

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅  Patch terminé — projet sur GitHub  ║"
echo "╚══════════════════════════════════════════╝"
