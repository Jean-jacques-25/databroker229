from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from math import radians, cos, sin, asin, sqrt
import re, os, csv, uuid
from datetime import datetime, timedelta
from io import StringIO
from PIL import Image
from functools import wraps
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message

from . import db
from .models import User, Mission, Submission, Transaction, CollecteData

main = Blueprint("main", __name__)



# 🔐 DECORATEUR : Vérifie si l'utilisateur est connecté et est un ADMIN
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'admin':
            flash("🚫 Accès refusé. Cette zone est réservée à l'administration de Databroker229.")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# 🔐 DECORATEUR : Vérifie si l'utilisateur est connecté et est un CLIENT
def client_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'client':
            flash("🔒 Veuillez vous connecter à votre compte Client pour publier une mission.")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# 🔐 DECORATEUR : Vérifie si l'utilisateur est connecté et est un AGENT
def agent_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'agent':
            flash("🏃‍♂️ Zone réservée aux agents de collecte sur le terrain.")
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

# CONFIGURATION DU DOSSIER D'UPLOAD DES PHOTOS
UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------------------------------------------
# 1. ACCUEIL ET AUTHENTIFICATION
# ----------------------------------------------------

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        location = request.form.get('location')
        
        # 🔑 On récupère le choix du rôle et le code secret du formulaire
        chosen_role = request.form.get('role')
        secret_code = request.form.get('secret_code')

        # 🔐 SÉCURITÉ : Validation du rôle Admin
        if chosen_role == 'admin':
            if secret_code == "Admin229":
                role = 'admin'
            else:
                flash("🚫 Code secret Admin incorrect. Impossible de créer ce type de compte.")
                return redirect(url_for('main.register'))
        else:
            role = chosen_role if chosen_role else 'agent'

        # 🔍 Vérification si l'utilisateur existe déjà
        user_exists = User.query.filter((User.email == email) | (User.phone == phone)).first()
        if user_exists:
            flash("Cet e-mail ou ce numéro de téléphone est déjà utilisé.")
            return redirect(url_for('main.register'))

        # 🔒 Hachage du mot de passe et création
        hashed_password = generate_password_hash(password, method='scrypt')
        new_user = User(
            fullname=fullname, 
            email=email, 
            phone=phone, 
            password=hashed_password, 
            role=role, 
            location=location
        )

        db.session.add(new_user)
        db.session.commit()
        
        flash("Inscription réussie ! Connectez-vous.")
        return redirect(url_for('main.login'))

    return render_template('register.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')
        
        user = User.query.filter((User.email == identifier) | (User.phone == identifier)).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_role'] = user.role
            session['user_name'] = user.fullname
            
            if user.role == 'agent':
                return redirect(url_for('main.agent_dashboard'))
            elif user.role == 'client':
                return redirect(url_for('main.client_dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('main.admin_dashboard'))
        else:
            flash("Identifiants incorrects. Veuillez réessayer.")
            
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))

# ----------------------------------------------------
# 2. ESPACE CLIENT
# ----------------------------------------------------

@main_bp.route('/client/dashboard')
def client_dashboard():
    if session.get("user_role") != "client":
        flash("Accès réservé aux clients.", "danger")
        return redirect(url_for("main.login"))
    client_id = session.get("user_id")
    missions = Mission.query.filter_by(client_id=client_id).all()
    return render_template("client_dashboard.html", missions=missions)
    return render_template("client_dashboard.html", missions=missions)
    mission_ids = [m.id for m in missions]
    
    # 2. Récupérer uniquement les collectes approuvées pour ces missions
    approved_submissions = Submission.query.filter(
        Submission.mission_id.in_(mission_ids),
        Submission.status == 'Approved'
    ).all()
    
    # 3. Calculer les statistiques rapides
    stats = {
        'total_missions': len(missions),
        'active_missions': len([m for m in missions if m.payment_status == 'Paid']),
        'total_data_collected': len(approved_submissions)
    }
    
    return render_template('client_dashboard.html', missions=missions, submissions=approved_submissions, stats=stats)
# ----------------------------------------------------
# 3. ESPACE AGENT
# ----------------------------------------------------

@main_bp.route('/agent/dashboard')
@agent_required
def agent_dashboard():
    agent = User.query.get(session['user_id'])
    history = Transaction.query.filter_by(user_id=agent.id).order_by(Transaction.created_at.desc()).all()
    missions = Mission.query.filter_by(payment_status='Paid').all()
    
    return render_template('agent_dashboard.html', agent=agent, missions=missions, history=history)

@main_bp.route('/agent/submit/<int:mission_id>', methods=['POST'])
def agent_submit(mission_id):

    # --- SÉCURITÉ ANTI-TRICHE ET VALIDATION BÉNIN ---
    shop_phone = request.form.get('shop_phone', '').strip()
    latitude_str = request.form.get('latitude')
    longitude_str = request.form.get('longitude')
    
    if not shop_phone or not latitude_str or not longitude_str:
        flash("Données incomplètes (téléphone ou GPS manquant).", "danger")
        return redirect(request.referrer or url_for('main.agent_dashboard'))
        
    try:
        latitude = float(latitude_str)
        longitude = float(longitude_str)
    except ValueError:
        flash("Coordonnées GPS invalides.", "danger")
        return redirect(request.referrer or url_for('main.agent_dashboard'))

    # Validation stricte des 10 chiffres (sans raccourci d pour éviter les bugs Python)
    if not re.match(r"^01[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]$", shop_phone):
        flash("Erreur : Le numéro doit comporter 10 chiffres et commencer par 01 (Norme Bénin).", "danger")
        return redirect(request.referrer or url_for('main.agent_dashboard'))

    existing_phone = Submission.query.filter_by(mission_id=mission_id, shop_phone=shop_phone).first()
    if existing_phone:
        flash("Fraude : Ce numéro de boutique a déjà été enregistré pour cette mission !", "danger")
        return redirect(request.referrer or url_for('main.agent_dashboard'))

    past_submissions = Submission.query.filter_by(mission_id=mission_id).all()
    for sub in past_submissions:
        if sub.longitude and sub.latitude:
            distance = haversine(longitude, latitude, sub.longitude, sub.latitude)
            if distance < 15:
                flash("Erreur de position : Une collecte existe déjà à moins de 15 mètres.", "danger")
                return redirect(request.referrer or url_for('main.agent_dashboard'))
    # --- FIN SÉCURITÉ ---
    # ... (vérification de session et récupération du formulaire) ...
    
    photo_file = request.files.get('photo')
    if photo_file:
        # Traitement et compression automatique de la preuve terrain
        photo_relative_path = save_and_compress_image(photo_file)
    else:
        flash("La photo de preuve est obligatoire.", "danger")
        return redirect(request.referrer)
        
    # Création de l'enregistrement en BDD
    new_sub = Submission(
        mission_id=mission_id,
        agent_id=session['user_id'],
        shop_name=request.form.get('shop_name'),
        shop_phone=request.form.get('shop_phone'),
        shop_address=request.form.get('shop_address'),
        latitude=float(request.form.get('latitude')),
        longitude=float(request.form.get('longitude')),
        photo_path=photo_relative_path, # Sauvegarde du chemin .webp compressé
        observations=request.form.get('observations')
    )
    
    db.session.add(new_sub)
    db.session.commit()
    flash("Collecte soumise avec succès au contrôle qualité !", "success")
    return redirect(url_for('main.agent_dashboard'))
# ----------------------------------------------------
# 4. CONSOLE ADMIN
# ----------------------------------------------------

@main_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Recueil des statistiques de la plateforme
    total_agents = User.query.filter_by(role='agent').count()
    all_missions = Mission.query.all()
    total_missions = len(all_missions)
    pending_payments = Mission.query.filter_by(payment_status='Pending_Payment').all()
    pending_submissions = Submission.query.filter_by(status='Pending').all()
    all_agents = User.query.filter_by(role='agent').all()
    
    # Recueil des données de collectes de terrain pour l'affichage
    collectes = CollecteData.query.all()
    
    return render_template('admin_dashboard.html', 
                           total_agents=total_agents, 
                           total_missions=total_missions, 
                           all_agents=all_agents, 
                           pending_submissions=pending_submissions,
                           pending_payments=pending_payments, 
                           all_missions=all_missions,
                           collectes=collectes)

@main_bp.route('/admin/confirm-payment/<int:mission_id>', methods=['POST'])
@admin_required
def confirm_payment(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    mission.payment_status = 'Paid'
    db.session.commit()
    flash(f"Paiement reçu pour la mission #{mission.id}. Elle est maintenant disponible sur le terrain !")
    return redirect(url_for('main.admin_dashboard'))

@main_bp.route('/admin/review/<int:submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_review(submission_id):
    sub = Submission.query.get_or_404(submission_id)
    agent = User.query.get(sub.agent_id)
    mission = Mission.query.get(sub.mission_id)
    
    if request.method == 'POST':
        action = request.form.get('action') # 'approve' ou 'reject'
        
        if action == 'approve':
            sub.status = 'Approved'
            
            # 1. Rémunération de l'agent
            if agent.wallet_balance is None:
                agent.wallet_balance = 0
            agent.wallet_balance += mission.price
            
            # 2. Historique de la transaction de gain
            new_transaction = Transaction(
                user_id=agent.id,
                mission_id=mission.id,
                amount=mission.price,
                transaction_type='gain',
                status='Completed'
            )
            db.session.add(new_transaction)
            
            # 3. 📍 ARCHIVAGE : Enregistrement définitif du point dans le patrimoine data
            nouvelle_collecte = CollecteData(
                description=f"Commerce: {sub.shop_name} ({mission.title})",
                latitude=sub.latitude,
                longitude=sub.longitude,
                agent_id=agent.id
            )
            db.session.add(nouvelle_collecte)
            
            flash(f"💚 Dossier validé ! {mission.price} FCFA versés à {agent.fullname} et point ajouté au catalogue.")
            
        elif action == 'reject':
            sub.status = 'Rejected'
            flash("🔴 Dossier rejeté.")
            
        db.session.commit()
        return redirect(url_for('main.admin_dashboard'))
        
    return render_template('admin_review.html', sub=sub, agent=agent, mission=mission)

# API REST pour distribuer les coordonnées à la carte interactive Leaflet
@main_bp.route('/api/points-collecte')
def api_points_collecte():
    points = CollecteData.query.all()
    features = []
    
    # Ajout des collectes validées et archivées
    for p in points:
        features.append({
            "id": p.id,
            "description": p.description,
            "lat": p.latitude,
            "lng": p.longitude
        })
    return jsonify(features)

# 📊 EXPORTATION CSV POUR LE CLIENT
@main_bp.route('/client/export/<int:mission_id>')
def client_export_csv(mission_id):
    if 'user_id' not in session or session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    
    mission = Mission.query.get_or_404(mission_id)
    sub_validees = Submission.query.filter_by(mission_id=mission.id, status='Approved').all()
    
    si = StringIO()
    cw = csv.writer(si, delimiter=';') 
    
    cw.writerow(['ID_Soumission', 'Nom_Commerce', 'Telephone', 'Adresse_Quartier', 'Latitude', 'Longitude', 'Observations', 'Agent_ID'])
    
    for sub in sub_validees:
        cw.writerow([
            f"SUB-{sub.id}",
            sub.shop_name,
            sub.shop_phone if sub.shop_phone else "N/A",
            sub.shop_address,
            sub.latitude,
            sub.longitude,
            sub.observations if sub.observations else "",
            sub.agent_id
        ])
    
    output = si.getvalue()
    nom_fichier = f"databroker229_mission_{mission_id}.csv"
    
    return Response(
        output,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={nom_fichier}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )

def save_and_compress_image(form_photo):
    """Prend le fichier image du formulaire, le compresse et l'enregistre en WebP"""
    # 1. Générer un nom unique avec extension .webp
    unique_filename = f"{uuid.uuid4().hex}.webp"
    upload_folder = os.path.join('app', 'static', 'uploads')
    
    # S'assurer que le dossier existe
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        
    target_path = os.path.join(upload_folder, unique_filename)
    
    # 2. Ouvrir et compresser l'image avec Pillow
    image = Image.open(form_photo)
    
    # Convertir en RGB si l'image est en RGBA (PNG) car le JPEG/WebP gère mieux le RGB
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
        
    # Enregistrement au format WebP avec une qualité optimisée à 70%
    image.save(target_path, "WEBP", quality=70)
    
    # Retourner le chemin relatif pour la base de données
    return f"uploads/{unique_filename}"
# --- SYSTÈME DE RÉCUPÉRATION DE MOT DE PASSE ---
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash

# Initialisation du sérialiseur pour les tokens sécurisés (expire après 30 minutes)
def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expiration=1800):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
    except:
        return None
    return email

@main_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('main.reset_password', token=token, _external=True)
            
            # Configuration temporaire du message (sera envoyé via Flask-Mail)
            # Pour l'instant, on l'affiche aussi dans les logs pour tes tests faciles
            print(f"\n[MAIL SIMULATION] Lien de réinitialisation pour {email} : {reset_url}\n")
            
            try:
                mail = Mail(current_app)
                msg = Message("Réinitialisation de votre mot de passe - DataBroker229",
                              sender=current_app.config.get('MAIL_USERNAME'),
                              recipients=[email])
                msg.body = f"Bonjour,\n\nPour réinitialiser votre mot de passe, cliquez sur le lien suivant :\n{reset_url}\n\nCe lien expira dans 30 minutes.\nSi vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail."
                mail.send(msg)
            except Exception as e:
                print(f"Erreur d'envoi d'e-mail : {e}")
                
            flash("Si ce compte existe, un e-mail contenant les instructions vous a été envoyé.", "info")
        else:
            # Sécurité : on affiche le même message pour ne pas divulguer si un mail existe ou pas
            flash("Si ce compte existe, un e-mail contenant les instructions vous a été envoyé.", "info")
            
        return redirect(url_for('main.login'))
        
    return render_template('forgot_password.html')

@main_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = verify_reset_token(token)
    if not email:
        flash("Le lien de réinitialisation est invalide ou a expiré.", "danger")
        return redirect(url_for('main.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(request.referrer)
            
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash("Votre mot de passe a été mis à jour avec succès ! Vous pouvez vous connecter.", "success")
            return redirect(url_for('main.login'))
            
    return render_template('reset_password.html', token=token)
# --- FIN SYSTÈME DE RÉCUPÉRATION ---

# Nouvelle logique de création de campagne avec répartition Budget / Commission


@main_bp.route('/campaign/create', methods=['GET', 'POST'])
def create_campaign():
    if 'user_id' not in session:
        flash('Veuillez vous connecter pour accéder à cette page.', 'danger')
        return redirect(url_for('main.login'))
        
    if request.method == 'POST':
        # 1. Récupération des données du vrai formulaire
        title = request.form.get('title')
        description = request.form.get('description')
        protocol = request.form.get('protocol')
        zone = request.form.get('zone')
        difficulty = request.form.get('difficulty', 'Standard')
        quantity = int(request.form.get('quantity', 1))
        budget_total = float(request.form.get('budget_total', 0))
        
        # 2. Logique de répartition (80% Agent / 20% Toi)
        budget_par_point = budget_total / quantity
        remuneration_agent = budget_par_point * 0.80
        commission_plateforme = budget_par_point * 0.20
        
        # 3. Sauvegarde dans ton modèle 'Mission'
        new_mission = Mission(
            title=title,
            description=description,
            protocol=protocol,
            zone=zone,
            difficulty=difficulty,
            quantity=quantity,
            budget_total=budget_total,
            remuneration_agent=remuneration_agent,
            commission_plateforme=commission_plateforme,
            client_id=session['user_id'],
            status='En attente de paiement',
            created_at=datetime.utcnow()
        )
        db.session.add(new_mission)
        db.session.commit()
        
        flash('Mission créée avec succès ! En attente de financement.', 'success')
        return redirect(url_for('main.client_dashboard'))
        
    return render_template('create_campaign.html')
