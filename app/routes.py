from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Mission, User, Submission, Transaction, Notification, Retrait, CollecteData
from datetime import datetime, timedelta
import csv, io, math, os, json as json_module, urllib.request as urllib_req, base64, time

main = Blueprint('main', __name__)
ADMIN_SECRET_CODE = 'DB229ADMIN'

def notif(user_id, message, type='info'):
    n = Notification(user_id=user_id, message=message, type=type)
    db.session.add(n)


# ─── SEO : SITEMAP + ROBOTS.TXT ──────────────────────────────
@main.route('/sitemap.xml')
def sitemap():
    from flask import Response
    import datetime
    base = "https://databroker229-1edb.onrender.com"
    today = datetime.date.today().isoformat()
    pages = [
        ("", "1.0", "weekly"),
        ("/login", "0.8", "monthly"),
        ("/register", "0.8", "monthly"),
        ("/about", "0.7", "monthly"),
        ("/pricing", "0.7", "monthly"),
        ("/contact", "0.6", "monthly"),
    ]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for path, priority, freq in pages:
        xml.append(f"  <url><loc>{base}{path}</loc><lastmod>{today}</lastmod><changefreq>{freq}</changefreq><priority>{priority}</priority></url>")
    xml.append('</urlset>')
    return Response("\n".join(xml), mimetype="application/xml")

@main.route('/robots.txt')
def robots():
    from flask import Response
    txt = "User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /setup-admin-db229secret\nSitemap: https://databroker229-1edb.onrender.com/sitemap.xml"
    return Response(txt, mimetype="text/plain")

# ─── PAGE D'ACCUEIL ───────────────────────────────────────────
@main.route('/')
def index():
    return render_template('index.html')


# ─── VÉRIFICATION GOOGLE SEARCH CONSOLE ──────────────────────
@main.route('/googleb745c890fd4fea44.html')
def google_verify():
    return 'google-site-verification: b745c890fd4fea44'

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


def analyser_collecte_ia(submission, mission):
    """Analyse une collecte avec Claude AI et retourne un score de confiance 0-100."""
    try:
        prompt = f"""Tu es un système de validation de collecte de données terrain au Bénin.

Analyse cette soumission et donne un score de confiance de 0 à 100.

MISSION : {mission.title}
DESCRIPTION : {mission.description}
ZONE : {mission.zone}

DONNÉES SOUMISES :
- Nom commerce : {submission.shop_name or 'Non renseigné'}
- Adresse : {submission.shop_address or 'Non renseignée'}
- Téléphone : {submission.shop_phone or 'Non renseigné'}
- Observations : {submission.observations or 'Aucune'}
- GPS : lat={submission.latitude}, lng={submission.longitude}
- Photo : {'Oui' if submission.photo_path else 'Non'}

Critères d'évaluation :
1. Le nom du commerce est-il plausible ? (pas "aaa", "test", "xxx")
2. Les observations sont-elles pertinentes par rapport à la mission ?
3. Les coordonnées GPS sont-elles au Bénin ? (latitude 6-13, longitude 1-4)
4. Les données sont-elles cohérentes entre elles ?

Réponds UNIQUEMENT en JSON sans aucun texte avant ou après :
{{"score": 85, "decision": "Approuver", "raison": "Données cohérentes et complètes"}}

decision doit être exactement : "Approuver", "Vérifier" ou "Rejeter"
score entre 0 et 100"""

        payload = json_module.dumps({
            "model": "mistralai/mistral-7b-instruct:free",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode('utf-8')

        req = urllib_req.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}")
        req.add_header("HTTP-Referer", "https://databroker229-1edb.onrender.com")
        req.add_header("X-Title", "LaCentraleDesDonnees229")

        with urllib_req.urlopen(req, timeout=15) as r:
            resp = json_module.loads(r.read().decode('utf-8'))
            text = resp['choices'][0]['message']['content'].strip()
            # Nettoyer et parser le JSON
            text = text.replace('```json', '').replace('```', '').strip()
            result = json_module.loads(text)
            return {
                'score': int(result.get('score', 50)),
                'decision': result.get('decision', 'Vérifier'),
                'raison': result.get('raison', 'Analyse IA indisponible')
            }
    except Exception as e:
        # En cas d'erreur IA, retourner score neutre
        return {'score': 50, 'decision': 'Vérifier', 'raison': f'Analyse manuelle requise'}


def anti_fraude_vitesse(agent_id, lat, lng):
    """Vérifie qu'un agent ne s'est pas téléporté entre deux collectes."""
    derniere = Submission.query.filter_by(user_id=agent_id).filter(
        Submission.latitude.isnot(None)
    ).order_by(Submission.submitted_at.desc()).first()

    if not derniere or not derniere.latitude:
        return True, None

    distance = haversine(lat, lng, derniere.latitude, derniere.longitude)
    delta_temps = (datetime.utcnow() - derniere.submitted_at).total_seconds()

    # Vitesse max humaine réaliste = 120 km/h (moto/voiture)
    if delta_temps > 0:
        vitesse_kmh = (distance / 1000) / (delta_temps / 3600)
        if vitesse_kmh > 120 and distance > 500:
            return False, f"Déplacement suspect : {int(distance)}m en {int(delta_temps)}s ({int(vitesse_kmh)} km/h)"

    return True, None


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

        # Anti-fraude 1 : Vitesse impossible entre collectes
        vitesse_ok, motif_vitesse = anti_fraude_vitesse(session['user_id'], lat, lng)
        if not vitesse_ok:
            notif(session['user_id'], f"⚠️ Collecte bloquée — {motif_vitesse}", 'warning')
            db.session.rollback()
            flash(f"⚠️ Collecte bloquée : {motif_vitesse}", "error")
            return redirect(url_for('main.agent_dashboard'))

        # Anti-fraude 2 : Doublon même agent (50m)
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
                motif_auto  = f"Doublon GPS — vous avez déjà collecté ce point à {int(dist)}m."
                break

        # Anti-fraude 3 : Doublon inter-agents (même boutique, même mission, rayon 30m)
        if statut_auto == 'Pending':
            autres_subs = Submission.query.filter(
                Submission.mission_id == mission_id,
                Submission.user_id != session['user_id'],
                Submission.status != 'Rejected',
                Submission.latitude.isnot(None)
            ).all()
            for s in autres_subs:
                dist = haversine(lat, lng, s.latitude, s.longitude)
                if dist < 30:
                    statut_auto = 'Rejected'
                    motif_auto  = f"Ce point a déjà été collecté par un autre agent à {int(dist)}m. Cherchez un autre commerce."
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
        db.session.flush()  # Pour avoir sub.id

        # Analyse IA en arrière-plan si pas déjà rejeté
        if statut_auto == 'Pending':
            ia_result = analyser_collecte_ia(sub, mission)
            ia_score    = ia_result['score']
            ia_decision = ia_result['decision']
            ia_raison   = ia_result['raison']
            # Stocker le résultat IA dans data_submitted
            sub.data_submitted = json_module.dumps({
                'observations': request.form.get('observations', ''),
                'ia_score': ia_score,
                'ia_decision': ia_decision,
                'ia_raison': ia_raison
            })
            # Auto-validation IA : score >= 80 → approuver automatiquement
            if ia_score >= 80:
                sub.status = 'Approved'
                gain_agent = mission.prix_agent if mission.prix_agent else mission.difficulte
                agent_obj  = User.query.get(session['user_id'])
                if agent_obj:
                    agent_obj.wallet_balance += gain_agent
                    tx = Transaction(user_id=agent_obj.id, mission_id=mission.id,
                                     amount=gain_agent, transaction_type='gain', status='Completed')
                    db.session.add(tx)
                notif(session['user_id'],
                      f"✅ Collecte auto-validée par IA pour \"{mission.title}\" — +{gain_agent} FCFA crédités ! (Score IA: {ia_score}/100)", 'success')
                # Notifier le client
                if mission.client_id:
                    notif(mission.client_id,
                          f"📊 Nouvelle collecte validée pour \"{mission.title}\" ({ia_score}/100 IA)", 'success')
                statut_auto = 'Approved'
            # Auto-rejet IA : score < 20 → rejeter automatiquement
            elif ia_score < 20:
                sub.status      = 'Rejected'
                sub.motif_rejet = f"IA : {ia_raison} (score: {ia_score}/100)"
                statut_auto     = 'Rejected'
                motif_auto      = sub.motif_rejet

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
    r = Retrait(agent_id=agent.id, montant=montant, mode_paiement=mode, numero_mobile=numero, montant_bloque=True)
    # L'argent reste dans le portefeuille — bloqué jusqu'à confirmation admin
    db.session.add(r)
    notif(agent.id, f"Demande de retrait de {montant} FCFA via {mode} soumise. Traitement sous 24h.", 'info')
    db.session.commit()
    flash(f"Demande de retrait de {montant} FCFA envoyée. L'argent sera déduit après confirmation.", "success")
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
        zone_raw   = request.form.get('zone', '1.2')
        zone_libre = request.form.get('zone_libre', '').strip()
        # Si le client a choisi "Autre ville", on prend sa saisie
        if zone_raw == 'autre':
            zone_val  = '1.3'  # coefficient moyen pour zone inconnue
            zone_nom  = zone_libre if zone_libre else 'Autre zone'
        else:
            zone_val  = zone_raw
            zone_noms = {'1.2':'Cotonou','1.1':'Porto-Novo','1.5':'Parakou','1.0':'Abomey-Calavi','1.3':'Bohicon','1.6':'Natitingou'}
            zone_nom  = zone_noms.get(zone_val, zone_val)
        prix       = round(quantite * difficulte * float(zone_val) * 1.4)
        # Construire les champs requis selon les choix du client
        champs = request.form.getlist('champs_requis')
        if not champs:
            champs = ['nom_boutique', 'observations']
        if request.form.get('photos', 'non') == 'oui' and 'photo' not in champs:
            champs.append('photo')

        prix_agent = difficulte  # gain net par collecte pour l'agent
        mission = Mission(
            title            = request.form.get('title', '').strip(),
            description      = request.form.get('description', '').strip(),
            instructions     = '',
            price            = prix,
            prix_agent       = prix_agent,
            difficulty       = 'Standard',
            organisation     = request.form.get('organisation', '').strip(),
            contact          = request.form.get('contact', '').strip(),
            type_donnees     = request.form.get('type_donnees', ''),
            zone             = zone_val,
            quantite         = quantite,
            difficulte       = difficulte,
            format_livraison = request.form.get('format_livraison', 'pdf'),
            photos_requises  = request.form.get('photos', 'non'),
            champs_requis    = ','.join(champs),
            status           = 'En attente',
            payment_status   = 'Pending_Payment',
            client_id        = session['user_id']
        )
        db.session.add(mission)
        db.session.commit()
        notif(session['user_id'], f"Mission \"{mission.title}\" créée. En attente de validation.", 'info')
        flash("Mission créée ! En attente de validation par l'équipe LaCentraleDesDonnees229.", "success")
        return redirect(url_for('main.client_dashboard'))

    client   = User.query.get_or_404(session['user_id'])
    missions = Mission.query.filter_by(client_id=session['user_id']).order_by(Mission.created_at.desc()).all()
    notifs   = Notification.query.filter_by(user_id=session['user_id'], is_read=False).order_by(Notification.created_at.desc()).all()

    # Calculer toutes les stats en Python pour éviter les lazy loads dans le template
    missions_data = []
    total_points  = 0
    budget_mois   = 0
    missions_actives = 0
    missions_attente = 0

    for m in missions:
        approved = sum(1 for s in m.submissions if s.status == 'Approved')
        pending  = sum(1 for s in m.submissions if s.status == 'Pending')
        rejected = sum(1 for s in m.submissions if s.status == 'Rejected')
        quantite = m.quantite or 1
        progression = min(100, round((approved / quantite) * 100))
        total_points += approved

        if m.payment_status == 'Paid':
            budget_mois += m.price
        if m.status == 'Actif':
            missions_actives += 1
        if m.status == 'En attente':
            missions_attente += 1

        missions_data.append({
            'id':             m.id,
            'title':          m.title,
            'organisation':   m.organisation or '',
            'type_donnees':   m.type_donnees or '',
            'status':         m.status,
            'payment_status': m.payment_status,
            'price':          m.price,
            'quantite':       quantite,
            'points_collectes': approved,
            'progression':    progression,
            'champs_requis':  m.champs_requis or 'nom_boutique,observations',
            'is_suspended':   m.is_suspended,
        })

    return render_template('client_dashboard.html',
        missions=missions_data,
        data_count=total_points,
        client=client,
        notifs=notifs,
        budget_mois=budget_mois,
        missions_actives=missions_actives,
        missions_attente=missions_attente)



# ─── PAIEMENT CLIENT ──────────────────────────────────────────
@main.route('/client/payer/<int:mission_id>', methods=['POST'])
def client_payer_mission(mission_id):
    if session.get('user_role') != 'client':
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    if mission.client_id != session['user_id']:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('main.client_dashboard'))
    if mission.payment_status == 'Paid':
        flash("Cette mission est déjà payée.", "info")
        return redirect(url_for('main.client_dashboard'))

    mode    = request.form.get('mode_paiement', '')
    numero  = request.form.get('numero_mobile', '').strip()

    # Simulation paiement — mission activée instantanément
    mission.payment_status = 'Paid'
    mission.status         = 'Actif'
    db.session.commit()

    notif(session['user_id'],
          f"💳 Paiement de {mission.price} FCFA via {mode} confirmé. Mission \"{mission.title}\" maintenant active !",
          'success')
    db.session.commit()
    flash(f"✅ Paiement confirmé via {mode} ! Votre mission est maintenant active.", "success")
    return redirect(url_for('main.client_recu_pdf', mission_id=mission.id))

@main.route('/client/recu/<int:mission_id>')
def client_recu_pdf(mission_id):
    if session.get('user_role') not in ['client', 'admin']:
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    client  = User.query.get_or_404(mission.client_id)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        import io as io_module

        buffer = io_module.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story  = []

        # En-tête
        title_style = ParagraphStyle('t', parent=styles['Title'], fontSize=20,
                                      textColor=colors.HexColor('#0a1628'), spaceAfter=4)
        sub_style   = ParagraphStyle('s', parent=styles['Normal'], fontSize=11,
                                      textColor=colors.HexColor('#f59e0b'), spaceAfter=16)
        story.append(Paragraph("LaCentraleDesDonnées229", title_style))
        story.append(Paragraph("REÇU DE PAIEMENT OFFICIEL", sub_style))
        story.append(Spacer(1, 0.5*cm))

        # Infos reçu
        ref = f"REC-{mission.id:05d}-{datetime.utcnow().strftime('%Y%m%d')}"
        data = [
            ['Référence', ref],
            ['Date paiement', datetime.utcnow().strftime('%d/%m/%Y à %H:%M') + ' UTC'],
            ['Client', client.fullname],
            ['Organisation', mission.organisation or '—'],
            ['Mission', mission.title],
            ['Zone', mission.zone or '—'],
            ['Points de collecte', str(mission.quantite)],
            ['Mode de paiement', mode],
            ['Statut', '✅ PAYÉ'],
            ['MONTANT TOTAL', f"{mission.price:,} FCFA".replace(',', ' ')],
        ]
        t = Table(data, colWidths=[6*cm, 10*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#0a1628')),
            ('TEXTCOLOR', (0,0), (0,-1), colors.white),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#f59e0b')),
            ('TEXTCOLOR', (0,-1), (-1,-1), colors.black),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 11),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(
            "Ce reçu confirme que votre paiement a été reçu et que votre mission est maintenant active. "
            "Vous serez notifié à chaque collecte validée.",
            ParagraphStyle('note', fontSize=10, textColor=colors.grey, leading=16)))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"LaCentraleDesDonnées229 — contact@lacentraledesdonnees229.com — Cotonou, Bénin",
            ParagraphStyle('footer', fontSize=8, textColor=colors.grey)))

        doc.build(story)
        buffer.seek(0)
        return Response(buffer.getvalue(), mimetype='application/pdf',
                       headers={"Content-Disposition": f"attachment;filename=recu_paiement_{ref}.pdf"})
    except Exception as e:
        flash("Reçu PDF indisponible temporairement.", "info")
        return redirect(url_for('main.client_dashboard'))

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

    missions_paid = Mission.query.filter_by(payment_status='Paid').all()
    revenus_total = sum(m.price for m in missions_paid)
    dues_agents   = sum(a.wallet_balance for a in User.query.filter_by(role='agent').all())

    return render_template('admin_dashboard.html',
        total_agents=total_agents, total_clients=total_clients,
        total_missions=total_missions, all_agents=all_agents,
        pending_submissions=pending_submissions, pending_payments=pending_payments,
        pending_retraits=pending_retraits, total_pending_pay=total_pending_pay,
        collectes_today=collectes_today, activite=activite,
        missions_paid=missions_paid, revenus_total=revenus_total, dues_agents=dues_agents)

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
            gain_agent = mission.prix_agent if mission.prix_agent else mission.difficulte
            agent.wallet_balance += gain_agent
            tx = Transaction(user_id=agent.id, mission_id=mission.id,
                             amount=gain_agent, transaction_type='gain', status='Completed')
            db.session.add(tx)
            notif(agent.id, f"✅ Collecte validée pour \"{mission.title}\" — +{gain_agent} FCFA crédités !", 'success')
            if mission.client_id:
                notif(mission.client_id, f"Nouvelle collecte validée pour votre mission \"{mission.title}\".", 'success')
            flash(f"Collecte approuvée ! {gain_agent} FCFA versés à {agent.fullname}.", "success")
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
    agent = User.query.get_or_404(r.agent_id)
    # Déduire l'argent du portefeuille seulement maintenant
    if r.montant_bloque and agent.wallet_balance >= r.montant:
        agent.wallet_balance -= r.montant
        r.montant_bloque = False
    r.status  = 'Payé'
    r.paid_at = datetime.utcnow()
    notif(r.agent_id, f"💰 Retrait de {r.montant} FCFA via {r.mode_paiement} effectué ! Votre argent a été envoyé.", 'success')
    db.session.commit()
    flash(f"Retrait de {r.montant} FCFA confirmé et déduit du portefeuille de {agent.fullname}.", "success")
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

# ── MESSAGE GROUPÉ ADMIN ──────────────────────────────────────
@main.route('/admin/message-groupe', methods=['POST'])
def admin_message_groupe():
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    message  = request.form.get('message', '').strip()
    cible    = request.form.get('cible', 'tous')
    type_msg = request.form.get('type_msg', 'info')
    if not message:
        flash("Message vide.", "error")
        return redirect(url_for('main.admin_dashboard'))
    if cible == 'agents':
        users = User.query.filter_by(role='agent', is_suspended=False).all()
    elif cible == 'clients':
        users = User.query.filter_by(role='client').all()
    else:
        users = User.query.filter(User.role.in_(['agent', 'client'])).all()
    count = 0
    for u in users:
        notif(u.id, f"📢 {message}", type_msg)
        count += 1
    db.session.commit()
    flash(f"Message envoyé à {count} utilisateur(s).", "success")
    return redirect(url_for('main.admin_dashboard'))

# ── BLOQUER PDF SI NON PAYÉ ────────────────────────────────────
# (déjà géré dans client_rapport_pdf via mission.payment_status)

# ── SAUVEGARDE FORMULAIRE AGENT (API) ─────────────────────────
@main.route('/api/save-draft', methods=['POST'])
def api_save_draft():
    """Sauvegarde temporaire des données formulaire agent côté serveur."""
    if not session.get('user_id'):
        return jsonify({'ok': False}), 401
    data = request.get_json()
    # Stocker dans la session temporairement
    session[f"draft_{data.get('mission_id')}"] = data
    return jsonify({'ok': True})

# ── KEEP-ALIVE (empêche Render de s'endormir) ─────────────────
@main.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat()})

# ── PAGE LÉGALE ────────────────────────────────────────────────
@main.route('/legal')
def legal():
    return render_template('legal.html')

# ── PDF RAPPORT MISSION ─────────────────────────────────────────
@main.route('/client/rapport/<int:mission_id>')
def client_rapport_pdf(mission_id):
    if session.get('user_role') not in ['client', 'admin']:
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    # Bloquer si non payé
    if mission.payment_status != 'Paid' and session.get('user_role') != 'admin':
        flash("⚠️ Le rapport PDF n'est disponible qu'après confirmation du paiement.", "error")
        return redirect(url_for('main.client_dashboard'))
    submissions = Submission.query.filter_by(mission_id=mission_id, status='Approved').all()

    # Générer PDF avec reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        import io as io_module

        buffer = io_module.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        # Titre
        title_style = ParagraphStyle('title', parent=styles['Title'],
                                      fontSize=18, textColor=colors.HexColor('#0a1628'),
                                      spaceAfter=6)
        story.append(Paragraph("LaCentraleDesDonnées229", title_style))
        story.append(Paragraph(f"Rapport de Mission — {mission.title}", styles['Heading2']))
        story.append(Spacer(1, 0.5*cm))

        # Infos mission
        info_data = [
            ['Organisation', mission.organisation or '—'],
            ['Zone', mission.zone or '—'],
            ['Type de données', mission.type_donnees or '—'],
            ['Points demandés', str(mission.quantite)],
            ['Points collectés', str(len(submissions))],
            ['Progression', f"{min(100, round(len(submissions)/max(mission.quantite,1)*100))}%"],
            ['Date de création', mission.created_at.strftime('%d/%m/%Y') if mission.created_at else '—'],
        ]
        info_table = Table(info_data, colWidths=[5*cm, 11*cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f59e0b')),
            ('TEXTCOLOR', (0,0), (0,-1), colors.white),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.8*cm))

        # Tableau des collectes
        story.append(Paragraph("Données collectées", styles['Heading3']))
        story.append(Spacer(1, 0.3*cm))

        if submissions:
            headers = ['#', 'Commerce', 'Adresse', 'Observations', 'GPS', 'Date']
            data = [headers]
            for i, s in enumerate(submissions, 1):
                gps = f"{s.latitude:.4f},{s.longitude:.4f}" if s.latitude else '—'
                date = s.submitted_at.strftime('%d/%m/%Y') if s.submitted_at else '—'
                obs = (s.observations or '—')[:50]
                data.append([str(i), s.shop_name or '—', s.shop_address or '—', obs, gps, date])

            col_widths = [1*cm, 4*cm, 4*cm, 4*cm, 3*cm, 2.5*cm]
            table = Table(data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0a1628')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.3, colors.grey),
                ('PADDING', (0,0), (-1,-1), 4),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f8f8')]),
            ]))
            story.append(table)
        else:
            story.append(Paragraph("Aucune collecte validée pour le moment.", styles['Normal']))

        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(f"Rapport généré le {datetime.utcnow().strftime('%d/%m/%Y à %H:%M')} UTC — LaCentraleDesDonnées229",
                               ParagraphStyle('footer', fontSize=8, textColor=colors.grey)))

        doc.build(story)
        buffer.seek(0)
        return Response(buffer.getvalue(), mimetype='application/pdf',
                       headers={"Content-Disposition": f"attachment;filename=rapport_mission_{mission_id}.pdf"})

    except ImportError:
        return "ReportLab non installé. Ajoutez reportlab dans requirements.txt.", 500

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
@main.route('/setup-admin-db229secret-jja2026')
def setup_admin():
    try:
        # Créer uniquement les tables manquantes — JAMAIS drop_all
        db.create_all()

        # Créer admin seulement s'il n'existe pas
        existing = User.query.filter(User.email == "admin@databroker229.com").first()
        if existing:
            return """
            <div style='font-family:monospace;padding:40px;background:#0a0a0a;color:#fff;min-height:100vh;'>
                <h2 style='color:#10b981;'>✅ Base de données OK — Admin déjà existant</h2>
                <p style='color:#888;margin-top:12px;'>Tous les comptes utilisateurs sont préservés.</p>
                <a href='/login' style='display:inline-block;margin-top:24px;background:#f59e0b;color:#000;padding:12px 24px;border-radius:100px;text-decoration:none;font-weight:800;'>→ Se connecter</a>
            </div>
            """

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
            <h2 style='color:#10b981;'>✅ Admin créé avec succès !</h2>
            <p style='color:#888;margin-top:12px;'>Les comptes existants sont préservés.</p>
            <p style='margin-top:12px;'>Email : <strong style='color:#f59e0b;'>admin@databroker229.com</strong></p>
            <p>Mot de passe : <strong style='color:#f59e0b;'>admin229</strong></p>
            <a href='/login' style='display:inline-block;margin-top:24px;background:#f59e0b;color:#000;padding:12px 24px;border-radius:100px;text-decoration:none;font-weight:800;'>→ Se connecter</a>
        </div>
        """
    except Exception as e:
        db.session.rollback()
        return f"<div style='font-family:monospace;padding:40px;background:#0a0a0a;color:red;'>❌ Erreur : {str(e)}</div>"




