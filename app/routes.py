from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, mail, csrf
from app.models import Mission, User, Submission, Transaction, Notification, Retrait, CollecteData, AuditLog
from flask_mail import Message as MailMessage
from datetime import datetime, timedelta
import csv, io, math, os, json as json_module, urllib.request as urllib_req, base64, time

main = Blueprint('main', __name__)
ADMIN_SECRET_CODE = 'DB229ADMIN'

def notif(user_id, message, type='info'):
    n = Notification(user_id=user_id, message=message, type=type)
    db.session.add(n)


def log_action(action, target_type=None, target_id=None, details=None):
    """Enregistre une action dans le journal d'audit. A appeler avant tout db.session.commit()."""
    entry = AuditLog(
        actor_id   = session.get('user_id'),
        actor_name = session.get('user_name', 'Systeme'),
        actor_role = session.get('user_role', 'systeme'),
        action     = action,
        target_type= target_type,
        target_id  = target_id,
        details    = details
    )
    db.session.add(entry)


def check_agent_performance(agent):
    """Applique les seuils automatiques de performance apres chaque soumission traitee."""
    recent = Submission.query.filter_by(user_id=agent.id).order_by(Submission.submitted_at.desc()).limit(3).all()
    if len(recent) == 3 and all(s.status == 'Rejected' for s in recent) and not agent.is_paused_auto and not agent.is_suspended:
        agent.is_paused_auto = True
        notif(agent.id, "Votre compte a été mis en pause automatiquement suite à 3 collectes rejetées consécutivement. Un administrateur va examiner votre dossier avant réactivation.", 'warning')
        for adm in User.query.filter_by(role='admin').all():
            notif(adm.id, f"⚠️ Agent {agent.fullname} mis en pause automatiquement (3 rejets consécutifs).", 'warning')
        log_action('agent_auto_paused', target_type='User', target_id=agent.id,
                    details=f"3 rejets consecutifs (soumissions {[s.id for s in recent]})")

    if agent.total_missions >= 5:
        score = agent.reliability_score
        if score < 50 and not agent.low_score_notified:
            agent.low_score_notified = True
            notif(agent.id, f"Votre taux de fiabilité est descendu à {score}%. Soyez plus rigoureux sur les consignes de collecte pour éviter une suspension.", 'warning')
        elif score >= 50 and agent.low_score_notified:
            agent.low_score_notified = False


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
    missions_accueil = Mission.query.filter(
        Mission.status == 'Actif', Mission.is_suspended == False
    ).order_by(Mission.created_at.desc()).limit(3).all()
    nb_missions_actives = Mission.query.filter(
        Mission.status == 'Actif', Mission.is_suspended == False
    ).count()
    return render_template('index.html', missions_accueil=missions_accueil,
                           nb_missions_actives=nb_missions_actives)


# ─── MISSIONS DISPONIBLES (page publique) ─────────────────────
@main.route('/missions-disponibles')
def missions_disponibles():
    missions_toutes = Mission.query.filter(
        Mission.status == 'Actif', Mission.is_suspended == False
    ).order_by(Mission.created_at.desc()).all()
    return render_template('missions_disponibles.html', missions=missions_toutes)


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
        ip_fix = request.remote_addr or 'unknown'
        attempts_key = f'login_attempts_{ip_fix}'
        time_key = f'login_time_{ip_fix}'
        max_attempts = 5
        lockout_seconds = 15 * 60

        attempts = session.get(attempts_key, 0)
        last_attempt_time = session.get(time_key)
        if attempts >= max_attempts and last_attempt_time:
            elapsed = time.time() - last_attempt_time
            if elapsed < lockout_seconds:
                minutes_left = max(1, int((lockout_seconds - elapsed) // 60) + 1)
                flash(f"Trop de tentatives échouées. Réessayez dans {minutes_left} minute(s).", "error")
                return render_template('login.html')
            else:
                session.pop(attempts_key, None)
                session.pop(time_key, None)

        identifier = request.form.get('identifier', '').strip()
        password   = request.form.get('password', '')
        user = User.query.filter(
            (User.email == identifier.lower()) | (User.phone == identifier)
        ).first()
        if not user or not check_password_hash(user.password, password):
            session[attempts_key] = session.get(attempts_key, 0) + 1
            session[time_key] = time.time()
            flash("Identifiants incorrects.", "error")
            return render_template('login.html')
        if user.is_suspended:
            flash("Votre compte est suspendu. Contactez le support.", "error")
            return render_template('login.html')
        session.pop(attempts_key, None)
        session.pop(time_key, None)
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
    # Stats pour graphiques
    subs_all      = agent.submissions if hasattr(agent, 'submissions') else []
    subs_approved = sum(1 for s in subs_all if s.status == 'Approved')
    subs_pending  = sum(1 for s in subs_all if s.status == 'Pending')
    subs_rejected = sum(1 for s in subs_all if s.status == 'Rejected')
    missions_actives = len(missions)

    # Activite 6 derniers mois
    mois_labels    = []
    mois_collectes = []
    mois_gains     = []
    now = datetime.utcnow()
    for i in range(5, -1, -1):
        # Calculer debut/fin du mois
        mois_cible = now.month - i
        annee_cible = now.year
        while mois_cible <= 0:
            mois_cible += 12
            annee_cible -= 1
        debut = datetime(annee_cible, mois_cible, 1)
        if mois_cible == 12:
            fin = datetime(annee_cible + 1, 1, 1)
        else:
            fin = datetime(annee_cible, mois_cible + 1, 1)
        label = debut.strftime('%b')
        count = sum(1 for s in subs_all
                    if s.status == 'Approved' and s.submitted_at and debut <= s.submitted_at < fin)
        # Estimer le gain moyen par collecte
        gain_unitaire = 500
        try:
            tx = [t for t in history if t.created_at and debut <= t.created_at < fin]
            if tx:
                gain_unitaire = sum(t.amount for t in tx) // max(len(tx), 1)
        except Exception:
            pass
        mois_labels.append(label)
        mois_collectes.append(count)
        mois_gains.append(count * gain_unitaire)

    return render_template('agent_dashboard.html', agent=agent, missions=missions,
                           history=history, notifs=notifs, retraits=retraits,
                           subs_approved=subs_approved, subs_pending=subs_pending,
                           subs_rejected=subs_rejected, missions_actives=missions_actives,
                           mois_labels=mois_labels, mois_collectes=mois_collectes,
                           mois_gains=mois_gains)

def send_email(to, subject, body_html):
    """Envoyer un email HTML via Gmail."""
    try:
        msg = MailMessage(
            subject=subject,
            recipients=[to],
            html=body_html
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erreur email: {e}")
        return False


def email_bienvenue(user):
    """Email de bienvenue après inscription."""
    role_fr = "agent terrain" if user.role == 'agent' else "client entreprise"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:32px;border-radius:16px;">
        <h1 style="color:#f59e0b;font-size:24px;">🎉 Bienvenue sur LaCentraleDesDonnées229 !</h1>
        <p style="color:#aaa;font-size:15px;">Bonjour <strong style="color:#fff;">{user.fullname}</strong>,</p>
        <p style="color:#aaa;font-size:15px;">Votre compte <strong style="color:#f59e0b;">{role_fr}</strong> a été créé avec succès.</p>
        <div style="background:#111;border:1px solid #222;border-radius:12px;padding:20px;margin:20px 0;">
            <p style="color:#888;font-size:13px;margin:0;">📧 Email : <strong style="color:#fff;">{user.email}</strong></p>
            <p style="color:#888;font-size:13px;margin:8px 0 0;">📱 Téléphone : <strong style="color:#fff;">{user.phone}</strong></p>
        </div>
        <a href="https://databroker229-1edb.onrender.com/login"
           style="display:inline-block;background:#f59e0b;color:#000;font-weight:800;padding:14px 28px;border-radius:100px;text-decoration:none;font-size:15px;">
            Se connecter →
        </a>
        <p style="color:#888;font-size:12px;margin-top:24px;">LaCentraleDesDonnées229 — Votre terrain. Notre technologie.<br>contact@lacentraledesdonnees229.com</p>
    </div>
    """
    send_email(user.email, "Bienvenue sur LaCentraleDesDonnées229 !", body)


def email_mission_active(mission, client):
    """Email au client quand sa mission est activée."""
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:32px;border-radius:16px;">
        <h1 style="color:#10b981;font-size:22px;">✅ Votre mission est maintenant active !</h1>
        <p style="color:#aaa;">Bonjour <strong style="color:#fff;">{client.fullname}</strong>,</p>
        <div style="background:#111;border:1px solid #222;border-radius:12px;padding:20px;margin:20px 0;">
            <p style="color:#888;font-size:13px;margin:0;">📋 Mission : <strong style="color:#fff;">{mission.title}</strong></p>
            <p style="color:#888;font-size:13px;margin:8px 0 0;">📍 Zone : <strong style="color:#fff;">{mission.zone or '—'}</strong></p>
            <p style="color:#888;font-size:13px;margin:8px 0 0;">🎯 Points de collecte : <strong style="color:#fff;">{mission.quantite}</strong></p>
            <p style="color:#888;font-size:13px;margin:8px 0 0;">💰 Montant payé : <strong style="color:#f59e0b;">{mission.price:,} FCFA</strong></p>
        </div>
        <p style="color:#aaa;font-size:14px;">Nos agents terrain sont maintenant mobilisés. Vous serez notifié à chaque collecte validée.</p>
        <a href="https://databroker229-1edb.onrender.com/client/dashboard"
           style="display:inline-block;background:#10b981;color:#fff;font-weight:800;padding:14px 28px;border-radius:100px;text-decoration:none;font-size:15px;">
            Suivre ma mission →
        </a>
        <p style="color:#888;font-size:12px;margin-top:24px;">LaCentraleDesDonnées229 — contact@lacentraledesdonnees229.com</p>
    </div>
    """
    send_email(client.email, f"Mission activée : {mission.title}", body)


def email_reset_password(user, token_reset):
    """Email de réinitialisation mot de passe."""
    lien = f"https://databroker229-1edb.onrender.com/reset-password/{token_reset}"
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:32px;border-radius:16px;">
        <h1 style="color:#f59e0b;font-size:22px;">🔑 Réinitialisation de mot de passe</h1>
        <p style="color:#aaa;">Bonjour <strong style="color:#fff;">{user.fullname}</strong>,</p>
        <p style="color:#aaa;font-size:14px;">Vous avez demandé à réinitialiser votre mot de passe. Cliquez sur le bouton ci-dessous :</p>
        <a href="{lien}"
           style="display:inline-block;background:#f59e0b;color:#000;font-weight:800;padding:14px 28px;border-radius:100px;text-decoration:none;font-size:15px;margin:20px 0;">
            Réinitialiser mon mot de passe →
        </a>
        <p style="color:#888;font-size:12px;">Ce lien expire dans <strong>30 minutes</strong>. Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>
        <p style="color:#888;font-size:12px;margin-top:24px;">LaCentraleDesDonnées229 — contact@lacentraledesdonnees229.com</p>
    </div>
    """
    send_email(user.email, "Réinitialisation de votre mot de passe", body)


def crediter_commission_parrain(agent, gain_agent, mission_id):
    """Credite la commission parrain : 10% niveau 1, 3% niveau 2, 1% niveau 3."""
    if not agent.parrain_id:
        return
    niveaux = [
        (agent.parrain_id, 0.10),   # Parrain direct : 10%
    ]
    # Niveau 2 : parrain du parrain
    parrain1 = User.query.get(agent.parrain_id)
    if parrain1 and parrain1.parrain_id:
        niveaux.append((parrain1.parrain_id, 0.03))
        # Niveau 3
        parrain2 = User.query.get(parrain1.parrain_id)
        if parrain2 and parrain2.parrain_id:
            niveaux.append((parrain2.parrain_id, 0.01))

    for parrain_id, taux in niveaux:
        parrain = User.query.get(parrain_id)
        if not parrain:
            continue
        commission = max(1, round(gain_agent * taux))
        parrain.wallet_balance   += commission
        parrain.bonus_parrainage += commission
        tx = Transaction(
            user_id          = parrain.id,
            mission_id       = mission_id,
            amount           = commission,
            transaction_type = 'commission_parrain',
            status           = 'Completed'
        )
        db.session.add(tx)
        niveau_label = {0.10: "niveau 1", 0.03: "niveau 2", 0.01: "niveau 3"}.get(taux, "")
        notif(parrain.id,
              f"💸 Commission parrainage {niveau_label} : +{commission} FCFA (10% sur collecte de votre filleul)",
              'success')


def haversine(lat1, lon1, lat2, lon2):
    """Distance en mètres entre deux points GPS."""
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2-lat1)*p/2)**2 +
         math.cos(lat1*p) * math.cos(lat2*p) *
         math.sin((lon2-lon1)*p/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def analyser_photo_ia(photo_path):
    """Verifie si une photo contient un vrai commerce (pas selfie, paysage, photo floue)."""
    if not photo_path:
        return True, 100  # Pas de photo = pas de verification
    try:
        full_path = os.path.join('app', 'static', 'uploads', photo_path)
        if not os.path.exists(full_path):
            return True, 80
        with open(full_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        prompt_photo = """Analyse cette photo soumise par un agent terrain au Benin.
Est-ce que cette photo montre un vrai commerce, boutique, marche ou point de vente ?
Reponds UNIQUEMENT en JSON : {"ok": true, "score": 85, "raison": "Photo claire d'une boutique"}
score = 0-100 (confiance que c'est un vrai commerce)
ok = false si : selfie, photo floue, image aleatoire, screenshot, nature sans commerce"""

        payload = json_module.dumps({
            "model": "mistralai/mistral-7b-instruct:free",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt_photo},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]}]
        }).encode('utf-8')
        req_ia = urllib_req.Request("https://openrouter.ai/api/v1/chat/completions", data=payload, method="POST")
        req_ia.add_header("Authorization", f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}")
        req_ia.add_header("Content-Type", "application/json")
        with urllib_req.urlopen(req_ia, timeout=10) as r_ia:
            resp = json_module.loads(r_ia.read().decode('utf-8'))
            text = resp['choices'][0]['message']['content'].strip()
            text = text.replace('```json','').replace('```','').strip()
            result = json_module.loads(text)
            return result.get('ok', True), result.get('score', 70)
    except Exception:
        return True, 70  # En cas d erreur, ne pas bloquer


def valider_champs_personnalises(custom_defs, custom_data):
    """Validation deterministe des champs personnalises numeriques : plages plausibles
    et coherence entre champs. Ne depend d'aucun modele IA -> rapide, fiable, auditable."""
    anomalies = []
    valeurs_numeriques = {}

    for cdef in custom_defs:
        if cdef.get('type') != 'nombre':
            continue
        k = cdef.get('key', '')
        raw = custom_data.get(k, '')
        if raw == '':
            continue
        try:
            val = float(raw)
        except (ValueError, TypeError):
            anomalies.append(f"« {cdef.get('label', k)} » : valeur non numerique ({raw})")
            continue
        valeurs_numeriques[k] = val

        if 'min' in cdef and cdef['min'] is not None and val < cdef['min']:
            anomalies.append(f"« {cdef.get('label', k)} » = {val} : en dessous du minimum plausible ({cdef['min']})")
        if 'max' in cdef and cdef['max'] is not None and val > cdef['max']:
            anomalies.append(f"« {cdef.get('label', k)} » = {val} : au dessus du maximum plausible ({cdef['max']})")

    for cdef in custom_defs:
        if cdef.get('type') != 'nombre' or not cdef.get('coherence_with'):
            continue
        k = cdef.get('key', '')
        autre_k = cdef['coherence_with']
        if k not in valeurs_numeriques or autre_k not in valeurs_numeriques:
            continue
        v1, v2 = valeurs_numeriques[k], valeurs_numeriques[autre_k]
        op = cdef.get('coherence_op', 'lte')
        autre_label = next((c.get('label', autre_k) for c in custom_defs if c.get('key') == autre_k), autre_k)
        if op == 'lte' and v1 > v2:
            anomalies.append(f"« {cdef.get('label', k)} » ({v1}) devrait être ≤ « {autre_label} » ({v2})")
        elif op == 'gte' and v1 < v2:
            anomalies.append(f"« {cdef.get('label', k)} » ({v1}) devrait être ≥ « {autre_label} » ({v2})")

    return anomalies


def analyser_collecte_ia(submission, mission):
    """Analyse une collecte avec Claude AI et retourne un score de confiance 0-100."""
    try:
        prompt = f"""Tu es un systeme de validation de collecte de donnees terrain au Benin.

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
    agent = User.query.get(session['user_id'])

    if request.method == 'POST':
        if agent.is_paused_auto:
            flash("Votre compte est en pause en attente de revue par un administrateur, suite à plusieurs collectes rejetées. Contactez le support.", "error")
            return redirect(url_for('main.agent_dashboard'))
        lat  = request.form.get('latitude',  type=float)
        lng  = request.form.get('longitude', type=float)

        # GPS obligatoire
        if not lat or not lng:
            flash("La géolocalisation GPS est obligatoire.", "error")
            return render_template('agent_submit.html', mission=mission, draft={})

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
            return render_template('agent_submit.html', mission=mission, draft={})

        # Verifier mission d essai
        if not agent.essai_complete:
            essai_existant = Submission.query.filter_by(user_id=session['user_id'], status='Pending').first()
            if essai_existant:
                flash("Votre mission d'essai est en cours de validation. Patientez !", "info")
                return redirect(url_for('main.agent_dashboard'))

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

        # Champs personnalises definis par le client pour cette mission
        custom_defs = json_module.loads(mission.custom_fields) if mission.custom_fields else []
        custom_data = {}
        for cdef in custom_defs:
            k = cdef.get('key', '')
            if k:
                custom_data[k] = request.form.get(k, '').strip()

        anomalies_regles = valider_champs_personnalises(custom_defs, custom_data)

        # Signal anti-fraude : temps reellement passe entre l'ouverture du formulaire et l'envoi
        page_loaded_at = request.form.get('page_loaded_at', type=float)
        if page_loaded_at:
            temps_ecoule = (time.time() * 1000 - page_loaded_at) / 1000  # secondes
            seuil_min = 20 if mission.photos_requises == 'oui' else 10
            if temps_ecoule < seuil_min:
                anomalies_regles.append(f"Formulaire soumis en seulement {round(temps_ecoule)}s (minimum attendu : {seuil_min}s) — collecte possiblement precipitee")

        sub = Submission(
            user_id        = session['user_id'],
            mission_id     = mission_id,
            shop_name      = request.form.get('shop_name', '').strip(),
            shop_phone     = request.form.get('shop_phone', '').strip(),
            shop_address   = request.form.get('shop_address', '').strip(),
            observations   = request.form.get('observations', '').strip(),
            data_submitted = json_module.dumps({'observations': request.form.get('observations', ''), 'custom': custom_data, 'anomalies_regles': anomalies_regles}),
            latitude       = lat,
            longitude      = lng,
            photo_path     = photo_path,
            status         = statut_auto,
            motif_rejet    = motif_auto
        )
        db.session.add(sub)
        db.session.flush()  # Pour avoir sub.id

        # Analyse IA en arriere-plan si pas deja rejete
        if statut_auto == 'Pending':
            # Verifier la photo en premier
            if photo_path:
                photo_ok, photo_score = analyser_photo_ia(photo_path)
                if not photo_ok or photo_score < 30:
                    sub.status      = 'Rejected'
                    sub.motif_rejet = f"Photo invalide detectee par IA (score: {photo_score}/100). Soumettez une vraie photo de commerce."
                    log_action('submission_auto_rejected', target_type='Submission', target_id=sub.id,
                               details=f"Photo invalide (score IA {photo_score}/100)")
                    check_agent_performance(agent)
                    db.session.commit()
                    notif(session['user_id'], "Photo rejetee par IA. Assurez-vous de prendre une vraie photo du commerce.", 'error')
                    flash("Votre photo a ete rejetee. Soumettez une photo claire d'un commerce.", "error")
                    return redirect(url_for('main.agent_dashboard'))
            ia_result = analyser_collecte_ia(sub, mission)
            ia_score    = ia_result['score']
            ia_decision = ia_result['decision']
            ia_raison   = ia_result['raison']
            # Une anomalie de regle (plage ou coherence) plafonne le score et bloque toute auto-approbation,
            # peu importe ce que dit le modele IA generique — controle deterministe prioritaire.
            if anomalies_regles:
                ia_score = min(ia_score, 60)
                ia_raison = "Anomalie(s) detectee(s) sur les champs personnalises : " + " ; ".join(anomalies_regles)
            # Stocker le résultat IA dans data_submitted
            sub.data_submitted = json_module.dumps({
                'observations': request.form.get('observations', ''),
                'custom': custom_data,
                'anomalies_regles': anomalies_regles,
                'ia_score': ia_score,
                'ia_decision': ia_decision,
                'ia_raison': ia_raison
            })
            # Auto-validation IA : score >= 80 → approuver automatiquement (sauf anomalie de regle detectee)
            if ia_score >= 80 and not anomalies_regles:
                sub.status = 'Approved'
                gain_agent = mission.prix_agent if mission.prix_agent else mission.difficulte
                agent_obj  = User.query.get(session['user_id'])
                if agent_obj:
                    agent_obj.wallet_balance += gain_agent
                    tx = Transaction(user_id=agent_obj.id, mission_id=mission.id,
                                     amount=gain_agent, transaction_type='gain', status='Completed')
                    db.session.add(tx)
                    # Commission parrainage automatique
                    crediter_commission_parrain(agent_obj, gain_agent, mission.id)
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

        agent.total_missions += 1

        if statut_auto == 'Rejected':
            notif(session['user_id'],
                  f"⚠️ Collecte refusée automatiquement pour \"{mission.title}\" — {motif_auto}", 'warning')
            log_action('submission_auto_rejected', target_type='Submission', target_id=sub.id, details=motif_auto)
            check_agent_performance(agent)
            db.session.commit()
            flash("⚠️ Doublon GPS détecté — cette position a déjà été collectée pour cette mission.", "error")
            return redirect(url_for('main.agent_dashboard'))

        notif(session['user_id'], f"Collecte soumise pour \"{mission.title}\" — en attente de validation.", 'info')
        admins = User.query.filter_by(role='admin').all()
        for adm in admins:
            notif(adm.id, f"Nouvelle collecte soumise par {agent.fullname} pour \"{mission.title}\".", 'info')

        if statut_auto == 'Approved':
            log_action('submission_auto_approved', target_type='Submission', target_id=sub.id,
                       details=f"Score IA {ia_score}/100")
        check_agent_performance(agent)
        db.session.commit()
        flash("Collecte soumise avec succès ! En attente de validation.", "success")
        return redirect(url_for('main.agent_dashboard'))

    return render_template('agent_submit.html', mission=mission, draft=session.get(f'draft_{mission_id}', {}))

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
        # Type de données : si "autre", on prend la précision du client
        type_donnees_raw = request.form.get('type_donnees', '')
        if type_donnees_raw == 'autre':
            type_donnees_libre = request.form.get('type_donnees_libre', '').strip()
            type_donnees = type_donnees_libre if type_donnees_libre else 'Autre'
        else:
            type_donnees = type_donnees_raw

        # Date limite (optionnelle)
        deadline_raw = request.form.get('deadline', '').strip()
        deadline_val = None
        if deadline_raw:
            try:
                deadline_val = datetime.strptime(deadline_raw, '%Y-%m-%d')
            except ValueError:
                deadline_val = None

        # Zones supplementaires (optionnelles)
        zones_additionnelles = ','.join(request.form.getlist('zones_additionnelles'))

        # Photos : nombre et instructions
        photos_nombre = request.form.get('photos_nombre', 1, type=int) or 1
        photos_instructions = request.form.get('photos_instructions', '').strip()

        # Champs personnalises illimites definis par le client
        custom_fields_json = request.form.get('custom_fields_json', '[]')
        try:
            custom_fields_list = json_module.loads(custom_fields_json)
            if not isinstance(custom_fields_list, list):
                custom_fields_list = []
        except (ValueError, TypeError):
            custom_fields_list = []

        # Construire les champs requis selon les choix du client
        champs = request.form.getlist('champs_requis')
        if not champs:
            champs = ['nom_boutique', 'observations']
        if request.form.get('photos', 'non') == 'oui' and 'photo' not in champs:
            champs.append('photo')
        for cf in custom_fields_list:
            if cf.get('key'):
                champs.append(cf['key'])

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
            type_donnees     = type_donnees,
            zone             = zone_val,
            quantite         = quantite,
            difficulte       = difficulte,
            deadline         = deadline_val,
            zones_additionnelles = zones_additionnelles,
            format_livraison = request.form.get('format_livraison', 'pdf'),
            photos_requises  = request.form.get('photos', 'non'),
            photos_nombre    = photos_nombre,
            photos_instructions = photos_instructions,
            champs_requis    = ','.join(champs),
            custom_fields    = json_module.dumps(custom_fields_list) if custom_fields_list else None,
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

    from datetime import timedelta
    missions_terminees = sum(1 for m in missions if m.status == 'Termine')

    # Activite 6 derniers mois
    client_mois_labels    = []
    client_mois_missions  = []
    client_mois_collectes = []
    now = datetime.utcnow()
    for i in range(5, -1, -1):
        mois_cible = now.month - i
        annee_cible = now.year
        while mois_cible <= 0:
            mois_cible += 12
            annee_cible -= 1
        debut = datetime(annee_cible, mois_cible, 1)
        if mois_cible == 12:
            fin = datetime(annee_cible + 1, 1, 1)
        else:
            fin = datetime(annee_cible, mois_cible + 1, 1)
        nb_missions = sum(1 for m in missions if m.created_at and debut <= m.created_at < fin)
        nb_collectes = sum(
            sum(1 for s in m.submissions if s.status == 'Approved' and s.submitted_at and debut <= s.submitted_at < fin)
            for m in missions
        )
        client_mois_labels.append(debut.strftime('%b'))
        client_mois_missions.append(nb_missions)
        client_mois_collectes.append(nb_collectes)

    return render_template('client_dashboard.html',
        missions=missions_data,
        data_count=total_points,
        client=client,
        notifs=notifs,
        budget_mois=budget_mois,
        missions_actives=missions_actives,
        missions_attente=missions_attente,
        missions_terminees=missions_terminees,
        client_mois_labels=client_mois_labels,
        client_mois_missions=client_mois_missions,
        client_mois_collectes=client_mois_collectes)



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

    mode   = request.form.get('mode_paiement', '')
    numero = request.form.get('numero_mobile', '').strip()

    # ── FEDAPAY PAIEMENT REEL ──────────────────────────────────────
    fedapay_key = os.environ.get('FEDAPAY_API_KEY', '')
    if fedapay_key and mode in ['mtn', 'moov', 'celtiis']:
        try:
            # Creer la transaction FedaPay
            client_user = User.query.get(session['user_id'])
            payload_fp  = json_module.dumps({
                "description": f"Mission LaCentraleDesDonnees229 : {mission.title}",
                "amount": mission.price,
                "currency": {"iso": "XOF"},
                "callback_url": f"https://databroker229-1edb.onrender.com/client/fedapay/callback/{mission.id}",
                "customer": {
                    "firstname": (client_user.fullname or "Client").split()[0],
                    "lastname":  (client_user.fullname or "Client").split()[-1],
                    "email":     client_user.email,
                    "phone_number": {"number": numero, "country": "bj"}
                }
            }).encode('utf-8')

            req_fp = urllib_req.Request(
                "https://api.fedapay.com/v1/transactions",
                data=payload_fp, method="POST"
            )
            req_fp.add_header("Authorization", f"Bearer {fedapay_key}")
            req_fp.add_header("Content-Type", "application/json")

            with urllib_req.urlopen(req_fp, timeout=15) as r_fp:
                resp_fp = json_module.loads(r_fp.read().decode('utf-8'))
                transaction_id = resp_fp.get('v1/transaction', {}).get('id')
                token_fp       = resp_fp.get('v1/transaction', {}).get('token')

            if token_fp:
                # Stocker transaction en attente
                mission.payment_status = 'Pending_Fedapay'
                mission.status         = 'En attente'
                db.session.commit()
                # Rediriger vers page de paiement FedaPay
                return redirect(f"https://api.fedapay.com/v1/purchases/{token_fp}")

        except Exception as e:
            print(f"FedaPay erreur: {e}")
            # Fallback sur validation manuelle si FedaPay echoue
            pass

    # ── FALLBACK : Validation manuelle (virement ou erreur FedaPay) ─
    mission.payment_status = 'Paid'
    mission.status         = 'Actif'
    db.session.commit()

    notif(session['user_id'],
          f"Paiement de {mission.price} FCFA via {mode} confirme. Mission {mission.title} maintenant active !",
          'success')
    # Notifier tous les agents disponibles
    agents_actifs = User.query.filter_by(role='agent', is_suspended=False).all()
    for ag in agents_actifs:
        notif(ag.id,
              f"Nouvelle mission disponible : {mission.title} — {mission.prix_agent or mission.difficulte} FCFA/collecte a {mission.zone or 'voir details'}",
              'info')
    db.session.commit()
    try:
        client_user = User.query.get(session['user_id'])
        if client_user:
            email_mission_active(mission, client_user)
    except Exception:
        pass
    flash(f"Paiement confirme via {mode} ! Votre mission est maintenant active.", "success")
    return redirect(url_for('main.client_recu_pdf', mission_id=mission.id))


@main.route('/client/fedapay/callback/<int:mission_id>')
def fedapay_callback(mission_id):
    """Callback FedaPay apres paiement reussi."""
    mission = Mission.query.get_or_404(mission_id)
    status  = request.args.get('status', '')
    if status == 'approved':
        mission.payment_status = 'Paid'
        mission.status         = 'Actif'
        db.session.commit()
        client_user = User.query.get(mission.client_id)
        if client_user:
            notif(client_user.id, f"Paiement FedaPay confirme ! Mission {mission.title} active.", 'success')
            try:
                email_mission_active(mission, client_user)
            except Exception:
                pass
        flash("Paiement FedaPay confirme ! Votre mission est active.", "success")
        return redirect(url_for('main.client_recu_pdf', mission_id=mission.id))
    else:
        flash("Paiement non abouti. Reessayez.", "error")
        return redirect(url_for('main.client_dashboard'))

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
    custom_defs = json_module.loads(mission.custom_fields) if mission.custom_fields else []
    custom_labels = [cdef.get('label', cdef.get('key', '')) for cdef in custom_defs]
    custom_keys = [cdef.get('key', '') for cdef in custom_defs]
    writer.writerow(['ID', 'Commerce', 'Adresse', 'Téléphone', 'Observations', 'Latitude', 'Longitude', 'Date', 'Statut'] + custom_labels)
    for s in mission.submissions:
        custom_values = []
        try:
            parsed = json_module.loads(s.data_submitted) if s.data_submitted else {}
            custom_data = parsed.get('custom', {}) if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            custom_data = {}
        for k in custom_keys:
            custom_values.append(custom_data.get(k, ''))
        writer.writerow([s.id, s.shop_name, s.shop_address, s.shop_phone,
                         s.observations, s.latitude, s.longitude, s.submitted_at, s.status] + custom_values)
    output.seek(0)
    log_action('mission_data_exported_csv', target_type='Mission', target_id=mission.id, details=f'{len(mission.submissions)} soumissions exportees')
    db.session.commit()
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
            log_action('submission_approved', target_type='Submission', target_id=sub.id,
                       details=f"Par admin, agent {agent.fullname}, +{gain_agent} FCFA")
        elif action == 'reject':
            motif = request.form.get('motif_rejet', '').strip()
            sub.status      = 'Rejected'
            sub.motif_rejet = motif
            notif(agent.id, f"❌ Collecte rejetée pour \"{mission.title}\". Motif : {motif or 'Non précisé'}", 'warning')
            flash("Collecte rejetée.", "info")
            log_action('submission_rejected', target_type='Submission', target_id=sub.id,
                       details=f"Par admin, motif: {motif or 'non precise'}")
        check_agent_performance(agent)
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
    log_action('payment_confirmed', target_type='Mission', target_id=mission.id, details=f"{mission.price} FCFA")
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
    log_action('payout_completed', target_type='Retrait', target_id=r.id, details=f"{r.montant} FCFA a {agent.fullname}")
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
    log_action('mission_suspended' if mission.is_suspended else 'mission_reactivated',
               target_type='Mission', target_id=mission.id)
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
    if not agent.is_suspended:
        agent.is_paused_auto = False  # une reactivation manuelle leve aussi le gel automatique
    log_action('agent_suspended' if agent.is_suspended else 'agent_reactivated',
               target_type='User', target_id=agent.id)
    db.session.commit()
    flash(f"Agent {'suspendu' if agent.is_suspended else 'réactivé'}.", "success")
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/agent/<int:agent_id>/lever-pause', methods=['POST'])
def admin_lever_pause_agent(agent_id):
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    agent = User.query.get_or_404(agent_id)
    agent.is_paused_auto = False
    agent.low_score_notified = False
    notif(agent.id, "Votre compte a été réexaminé et débloqué par un administrateur. Vous pouvez de nouveau soumettre des collectes.", 'success')
    log_action('agent_auto_pause_lifted', target_type='User', target_id=agent.id)
    db.session.commit()
    flash(f"Pause automatique levée pour {agent.fullname}.", "success")
    return redirect(url_for('main.admin_dashboard'))

@main.route('/admin/journal')
def admin_journal():
    if session.get('user_role') != 'admin':
        return redirect(url_for('main.login'))
    page   = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '').strip()
    actor_filter  = request.args.get('actor', '').strip()

    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if action_filter:
        query = query.filter(AuditLog.action == action_filter)
    if actor_filter:
        query = query.filter(AuditLog.actor_name.ilike(f"%{actor_filter}%"))

    per_page = 40
    total    = query.count()
    logs     = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, (total + per_page - 1) // per_page)

    all_actions = [a[0] for a in db.session.query(AuditLog.action).distinct().all()]

    return render_template('admin_journal.html', logs=logs, page=page, total_pages=total_pages,
                            total=total, all_actions=all_actions,
                            action_filter=action_filter, actor_filter=actor_filter)

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
    log_action('agents_data_exported_csv', target_type='User', details='Export liste complete des agents')
    db.session.commit()
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
@csrf.exempt
def api_save_draft():
    """Sauvegarde temporaire des données formulaire agent côté serveur."""
    if not session.get('user_id'):
        return jsonify({'ok': False}), 401
    data = request.get_json()
    # Stocker dans la session temporairement
    session[f"draft_{data.get('mission_id')}"] = data
    return jsonify({'ok': True})

# ── MOT DE PASSE OUBLIÉ ───────────────────────────────────────
@main.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            import secrets
            token_reset = secrets.token_urlsafe(32)
            # Stocker le token dans la session (simple, sans table dédiée)
            from flask import current_app
            current_app.config[f'reset_{token_reset}'] = {'user_id': user.id, 'exp': datetime.utcnow().timestamp() + 1800}
            email_reset_password(user, token_reset)
        # Toujours afficher ce message (sécurité)
        flash("Si cet email existe, un lien de réinitialisation a été envoyé.", "success")
        return redirect(url_for('main.login'))
    return render_template('forgot_password.html')

@main.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from flask import current_app
    data = current_app.config.get(f'reset_{token}')
    if not data or datetime.utcnow().timestamp() > data['exp']:
        flash("Lien expiré ou invalide.", "error")
        return redirect(url_for('main.forgot_password'))
    user = User.query.get(data['user_id'])
    if not user:
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for('main.forgot_password'))
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        if len(new_password) < 6:
            flash("Le mot de passe doit faire au moins 6 caractères.", "error")
            return render_template('reset_password.html', token=token)
        user.password = generate_password_hash(new_password)
        db.session.commit()
        del current_app.config[f'reset_{token}']
        flash("Mot de passe modifié avec succès !", "success")
        return redirect(url_for('main.login'))
    return render_template('reset_password.html', token=token)

# ── ANALYTIQUES CLIENT ────────────────────────────────────────
@main.route('/client/analytiques/<int:mission_id>')
def client_analytiques(mission_id):
    if session.get('user_role') not in ['client', 'admin']:
        return redirect(url_for('main.login'))
    mission = Mission.query.get_or_404(mission_id)
    subs_all      = Submission.query.filter_by(mission_id=mission_id).all()
    approved      = [s for s in subs_all if s.status == 'Approved']
    pending       = [s for s in subs_all if s.status == 'Pending']
    rejected      = [s for s in subs_all if s.status == 'Rejected']
    progression   = min(100, round(len(approved) / max(mission.quantite, 1) * 100))
    # Collectes par jour (7 derniers jours)
    jours_labels = []
    jours_data   = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        label = day.strftime('%d/%m')
        count = sum(1 for s in approved if s.submitted_at and s.submitted_at.date() == day.date())
        jours_labels.append(label)
        jours_data.append(count)
    # Points GPS
    points_gps = [{'lat': s.latitude, 'lng': s.longitude, 'name': s.shop_name}
                  for s in approved if s.latitude and s.longitude]
    return render_template('client_analytics.html',
        mission=mission,
        approved_count=len(approved),
        pending_count=len(pending),
        rejected_count=len(rejected),
        progression=progression,
        jours_labels=jours_labels,
        jours_data=jours_data,
        points_gps=points_gps)


# ══════════════════════════════════════════════════════════════════
# API PUBLIQUE v1 — LaCentraleDesDonnees229
# ══════════════════════════════════════════════════════════════════

def require_api_key(f):
    """Decorateur pour verifier la cle API."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        from app.models import ApiKey
        key = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
        if not key:
            key = request.args.get('api_key', '')
        if not key:
            return jsonify({'error': 'Cle API manquante', 'doc': '/api/v1/docs'}), 401
        api_key = ApiKey.query.filter_by(key=key, is_active=True).first()
        if not api_key:
            return jsonify({'error': 'Cle API invalide ou desactivee'}), 403
        # Rate limiting : max 1000 requetes/jour
        api_key.requests += 1
        api_key.last_used = datetime.utcnow()
        db.session.commit()
        return f(api_key, *args, **kwargs)
    return decorated


@main.route('/offline')
def offline():
    return render_template('offline.html')


@main.route('/api/v1/docs')
def api_docs():
    """Documentation de l API publique."""
    return render_template('api_docs.html')


@main.route('/api/v1/missions')
@require_api_key
def api_missions(api_key):
    """Liste toutes les missions du client."""
    missions = Mission.query.filter_by(client_id=api_key.client_id).all()
    return jsonify({
        'total': len(missions),
        'missions': [{
            'id': m.id,
            'titre': m.title,
            'zone': m.zone,
            'type': m.type_donnees,
            'quantite': m.quantite,
            'statut': m.status,
            'paiement': m.payment_status,
            'progression': min(100, round(
                Submission.query.filter_by(mission_id=m.id, status='Approved').count()
                / max(m.quantite, 1) * 100
            )),
            'created_at': m.created_at.isoformat() if m.created_at else None
        } for m in missions]
    })


@main.route('/api/v1/missions/<int:mission_id>')
@require_api_key
def api_mission_detail(api_key, mission_id):
    """Detail d une mission specifique."""
    mission = Mission.query.filter_by(id=mission_id, client_id=api_key.client_id).first()
    if not mission:
        return jsonify({'error': 'Mission introuvable ou acces non autorise'}), 404
    approved = Submission.query.filter_by(mission_id=mission_id, status='Approved').count()
    return jsonify({
        'id': mission.id,
        'titre': mission.title,
        'description': mission.description,
        'zone': mission.zone,
        'type': mission.type_donnees,
        'quantite': mission.quantite,
        'collectes_validees': approved,
        'progression': min(100, round(approved / max(mission.quantite, 1) * 100)),
        'statut': mission.status,
        'paiement': mission.payment_status,
        'format_livraison': mission.format_livraison,
        'created_at': mission.created_at.isoformat() if mission.created_at else None
    })


@main.route('/api/v1/missions/<int:mission_id>/collectes')
@require_api_key
def api_mission_collectes(api_key, mission_id):
    """Toutes les collectes validees d une mission."""
    mission = Mission.query.filter_by(id=mission_id, client_id=api_key.client_id).first()
    if not mission:
        return jsonify({'error': 'Mission introuvable ou acces non autorise'}), 404
    page     = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    subs = Submission.query.filter_by(
        mission_id=mission_id, status='Approved'
    ).order_by(Submission.submitted_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'mission_id': mission_id,
        'total': subs.total,
        'page': page,
        'per_page': per_page,
        'pages': subs.pages,
        'collectes': [{
            'id': s.id,
            'commerce': s.shop_name,
            'adresse': s.shop_address,
            'telephone': s.shop_phone,
            'observations': s.observations,
            'latitude': s.latitude,
            'longitude': s.longitude,
            'photo': f"https://databroker229-1edb.onrender.com/static/uploads/{s.photo_path}" if s.photo_path else None,
            'date': s.submitted_at.isoformat() if s.submitted_at else None
        } for s in subs.items]
    })


@main.route('/api/v1/missions/<int:mission_id>/stats')
@require_api_key
def api_mission_stats(api_key, mission_id):
    """Statistiques completes d une mission."""
    mission = Mission.query.filter_by(id=mission_id, client_id=api_key.client_id).first()
    if not mission:
        return jsonify({'error': 'Mission introuvable'}), 404
    from datetime import timedelta
    approved  = Submission.query.filter_by(mission_id=mission_id, status='Approved').all()
    pending   = Submission.query.filter_by(mission_id=mission_id, status='Pending').count()
    rejected  = Submission.query.filter_by(mission_id=mission_id, status='Rejected').count()
    # Collectes par jour (7 derniers jours)
    par_jour = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        count = sum(1 for s in approved if s.submitted_at and s.submitted_at.date() == day.date())
        par_jour.append({'date': day.strftime('%Y-%m-%d'), 'count': count})
    return jsonify({
        'mission_id': mission_id,
        'titre': mission.title,
        'progression': min(100, round(len(approved) / max(mission.quantite, 1) * 100)),
        'collectes_validees': len(approved),
        'collectes_en_attente': pending,
        'collectes_rejetees': rejected,
        'points_gps': [{'lat': s.latitude, 'lng': s.longitude} for s in approved if s.latitude],
        'activite_7_jours': par_jour
    })


@main.route('/api/v1/profil')
@require_api_key
def api_profil(api_key):
    """Profil du client authentifie."""
    client = User.query.get(api_key.client_id)
    if not client:
        return jsonify({'error': 'Client introuvable'}), 404
    return jsonify({
        'id': client.id,
        'nom': client.fullname,
        'email': client.email,
        'organisation': client.organisation,
        'missions_total': Mission.query.filter_by(client_id=client.id).count(),
        'cle_api_label': api_key.label,
        'requetes_effectuees': api_key.requests,
        'derniere_requete': api_key.last_used.isoformat() if api_key.last_used else None
    })


# ── GESTION CLES API (depuis dashboard client) ─────────────────
@main.route('/client/api-keys', methods=['GET', 'POST'])
def client_api_keys():
    if session.get('user_role') not in ['client', 'admin']:
        return redirect(url_for('main.login'))
    from app.models import ApiKey
    import secrets
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            label  = request.form.get('label', 'Cle API').strip()
            new_key = ApiKey(
                client_id=session['user_id'],
                key=secrets.token_hex(32),
                label=label
            )
            db.session.add(new_key)
            db.session.commit()
            flash(f"Cle API creee : {new_key.key}", "success")
        elif action == 'delete':
            key_id = request.form.get('key_id')
            k = ApiKey.query.filter_by(id=key_id, client_id=session['user_id']).first()
            if k:
                db.session.delete(k)
                db.session.commit()
                flash("Cle API supprimee.", "success")
    keys = ApiKey.query.filter_by(client_id=session['user_id']).all()
    return render_template('client_api_keys.html', keys=keys)

# ── ERREURS ───────────────────────────────────────────────────────
from flask import render_template as rt
@main.app_errorhandler(404)
def page_not_found(e):
    return rt('404.html'), 404

# ── KEEP-ALIVE (empêche Render de s'endormir) ─────────────────
@main.route('/agent/parrainage')
def agent_parrainage():
    if session.get('user_role') != 'agent':
        return redirect(url_for('main.login'))
    agent = User.query.get_or_404(session['user_id'])
    filleuls = User.query.filter_by(parrain_id=agent.id).all()
    return render_template('agent_parrainage.html', agent=agent, filleuls=filleuls)


@main.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat()})


@main.route('/admin/backup-db', methods=['GET'])
def backup_db():
    """Backup automatique de toutes les donnees vers GitHub."""
    # Securiser : seulement admin ou appel interne
    auth = request.headers.get('X-Backup-Token', '')
    if auth != os.environ.get('BACKUP_TOKEN', 'backup-jja2026') and session.get('user_role') != 'admin':
        return jsonify({'error': 'Non autorise'}), 403

    try:
        from datetime import datetime as dt

        # Collecter toutes les donnees
        users = User.query.all()
        missions = Mission.query.all()
        submissions = Submission.query.all()
        transactions = Transaction.query.all()
        retraits = Retrait.query.all()

        backup_data = {
            'backup_date': dt.utcnow().isoformat(),
            'stats': {
                'users': len(users),
                'missions': len(missions),
                'submissions': len(submissions),
                'transactions': len(transactions),
                'retraits': len(retraits)
            },
            'users': [{
                'id': u.id, 'fullname': u.fullname, 'email': u.email,
                'phone': u.phone, 'role': u.role, 'location': u.location,
                'wallet_balance': u.wallet_balance, 'niveau': u.niveau,
                'total_missions': u.total_missions, 'is_suspended': u.is_suspended,
                'created_at': u.created_at.isoformat() if u.created_at else None
            } for u in users],
            'missions': [{
                'id': m.id, 'title': m.title, 'description': m.description,
                'price': m.price, 'difficulty': m.difficulty,
                'status': m.status, 'payment_status': m.payment_status,
                'client_id': m.client_id, 'zone': m.zone,
                'quantite': m.quantite, 'difficulte': m.difficulte,
                'prix_agent': m.prix_agent, 'type_donnees': m.type_donnees,
                'created_at': m.created_at.isoformat() if m.created_at else None
            } for m in missions],
            'submissions': [{
                'id': s.id, 'user_id': s.user_id, 'mission_id': s.mission_id,
                'shop_name': s.shop_name, 'shop_address': s.shop_address,
                'observations': s.observations, 'status': s.status,
                'latitude': s.latitude, 'longitude': s.longitude,
                'submitted_at': s.submitted_at.isoformat() if s.submitted_at else None
            } for s in submissions],
            'transactions': [{
                'id': t.id, 'user_id': t.user_id, 'mission_id': t.mission_id,
                'amount': t.amount, 'transaction_type': t.transaction_type,
                'status': t.status,
                'created_at': t.created_at.isoformat() if t.created_at else None
            } for t in transactions],
            'retraits': [{
                'id': r.id, 'agent_id': r.agent_id, 'montant': r.montant,
                'mode_paiement': r.mode_paiement, 'numero_mobile': r.numero_mobile,
                'status': r.status,
                'created_at': r.created_at.isoformat() if r.created_at else None
            } for r in retraits]
        }

        backup_json = json_module.dumps(backup_data, ensure_ascii=False, indent=2)

        # Sauvegarder sur GitHub dans le dossier backups/
        gh_token = os.environ.get('GITHUB_TOKEN', '')
        if gh_token:
            filename = f"backups/backup_{dt.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            b64_content = base64.b64encode(backup_json.encode('utf-8')).decode('utf-8')

            # Verifier si fichier existe
            check_url = f"https://api.github.com/repos/Jean-jacques-25/databroker229/contents/{filename}"
            req_check = urllib_req.Request(check_url)
            req_check.add_header("Authorization", f"token {gh_token}")
            try:
                with urllib_req.urlopen(req_check) as r_check:
                    old_sha = json_module.load(r_check).get('sha', '')
            except:
                old_sha = ''

            payload_gh = {"message": f"Backup auto {dt.utcnow().strftime('%Y-%m-%d %H:%M')}", "content": b64_content}
            if old_sha:
                payload_gh["sha"] = old_sha

            req_gh = urllib_req.Request(check_url, data=json_module.dumps(payload_gh).encode(), method="PUT")
            req_gh.add_header("Authorization", f"token {gh_token}")
            req_gh.add_header("Content-Type", "application/json")
            with urllib_req.urlopen(req_gh) as r_gh:
                resp_gh = json_module.load(r_gh)
                github_ok = "content" in resp_gh
        else:
            github_ok = False

        return jsonify({
            'status': 'ok',
            'date': dt.utcnow().isoformat(),
            'stats': backup_data['stats'],
            'github_saved': github_ok
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ── PAGE LÉGALE ────────────────────────────────────────────────
@main.route('/legal')
@main.route('/cgu')
@main.route('/mentions-legales')
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










