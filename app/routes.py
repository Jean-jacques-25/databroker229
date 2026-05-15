from .niveaux import mettre_a_jour_niveau, calculer_bonus, NIVEAUX, progression_vers_suivant
from flask import Blueprint, request, jsonify, send_from_directory, render_template, send_file
from .models import db, User, Mission, Collecte, Transaction, Contact
from .export import generer_pdf, generer_excel
from .paiement import payer_agent, detecter_operateur, points_vers_fcfa, OPERATEURS
from .moteur import valider_collecte_auto, calculer_prix_mission, finaliser_mission
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from flask import current_app
import os, uuid
from .sms import (sms_bienvenue_agent, sms_bienvenue_client,
                  sms_collecte_validee, sms_collecte_rejetee,
                  sms_mission_publiee_client, notifier_tous_agents)
from .antifraude import analyser_collecte
from .classement import calculer_classement
from .historique import calculer_historique_prix
main = Blueprint("main", __name__)
UPLOAD_FOLDER    = "uploads"
EXTENSIONS_OK    = {"jpg", "jpeg", "png"}

def ext_ok(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EXTENSIONS_OK

# ════════════════════════════════════════
# PAGES
# ════════════════════════════════════════
@main.route("/")
def public():
    return render_template("public.html")

@main.route("/agent")
def agent():
    return render_template("index.html")

@main.route("/admin")
def admin():
    return render_template("admin.html")

@main.route("/analytique")
def analytique():
    return render_template("analytique.html")

@main.route("/client")
def client():
    return render_template("client.html")

# ════════════════════════════════════════
# AUTH AGENTS
# ════════════════════════════════════════
@main.route("/api/inscription", methods=["POST"])
def inscription():
    data      = request.get_json()
    telephone = data.get("telephone", "").strip()
    nom       = data.get("nom", "").strip()
    role      = data.get("role", "agent")
    email     = data.get("email", "").strip()

    if not telephone or not nom:
        return jsonify({"erreur": "Téléphone et nom obligatoires"}), 400
    if User.query.filter_by(telephone=telephone).first():
        return jsonify({"erreur": "Ce numéro est déjà enregistré"}), 409

    user = User(telephone=telephone, nom=nom, role=role, email=email)
    db.session.add(user)
    db.session.commit()
    # SMS de bienvenue
    if user.role == "agent":
        sms_bienvenue_agent(user.telephone, user.nom)
    elif user.role == "client":
        sms_bienvenue_client(user.telephone, user.nom)
    return jsonify({"message": "Inscription réussie", "user": user.to_dict()}), 201

@main.route("/api/connexion", methods=["POST"])
def connexion():
    data      = request.get_json()
    telephone = data.get("telephone", "").strip()
    user      = User.query.filter_by(telephone=telephone, actif=True).first()
    if not user:
        return jsonify({"erreur": "Numéro non trouvé"}), 404
    return jsonify({"message": "Connexion réussie", "user": user.to_dict()}), 200

# ════════════════════════════════════════
# MISSIONS (lecture publique pour agents)
# ════════════════════════════════════════
@main.route("/api/missions", methods=["GET"])
def liste_missions():
    missions = Mission.query.filter_by(statut="ouverte").all()
    return jsonify([m.to_dict() for m in missions]), 200

@main.route("/api/missions/toutes", methods=["GET"])
def toutes_missions():
    missions = Mission.query.order_by(Mission.date_creation.desc()).all()
    return jsonify([m.to_dict() for m in missions]), 200

# ════════════════════════════════════════
# CRÉATION MISSION (par client ou admin)
# ════════════════════════════════════════
@main.route("/api/missions/creer", methods=["POST"])
def creer_mission():
    data = request.get_json()

    nb       = int(data.get("nb_collectes_requis", 5))
    delai    = int(data.get("delai_heures", 24))
    marge    = current_app.config.get("MARGE", 0.40)
    calcul   = calculer_prix_mission(nb, delai, marge)

    mission = Mission(
        titre              = data.get("titre"),
        description        = data.get("description"),
        marche_cible       = data.get("marche_cible"),
        marche_latitude    = data.get("marche_latitude"),
        marche_longitude   = data.get("marche_longitude"),
        produit_cible      = data.get("produit_cible"),
        nb_collectes_requis= nb,
        delai_heures       = delai,
        client_nom         = data.get("client_nom"),
        client_email       = data.get("client_email"),
        client_telephone   = data.get("client_telephone"),
        prix_client_fcfa   = calcul["prix_client_fcfa"],
        marge_fcfa         = calcul["marge_fcfa"],
        budget_agents_fcfa = calcul["budget_agents_fcfa"],
        remuneration_agent = calcul["remuneration_agent"],
        statut             = "en_attente_paiement"
    )
    db.session.add(mission)
    db.session.commit()
    # SMS confirmation au client
    if mission.client_telephone:
        sms_mission_publiee_client(
            mission.client_telephone,
            mission.client_nom or "Client",
            mission.titre,
            mission.nb_collectes_requis,
            mission.delai_heures,
            mission.date_echeance.strftime("%d/%m/%Y %H:%M")
        )
    # SMS à tous les agents
    from .models import User
    agents = User.query.filter_by(role="agent", actif=True).all()
    notifier_tous_agents(
        agents, mission.titre,
        mission.marche_cible,
        mission.points_recompense,
        mission.date_echeance.strftime("%d/%m à %H:%M")
    )
    return jsonify({
        "message": "Mission créée",
        "mission": mission.to_dict(),
        "tarif":   calcul
    }), 201

# ════════════════════════════════════════
# SIMULER PAIEMENT KKIAPAY (sandbox)
# ════════════════════════════════════════
@main.route("/api/missions/<int:mission_id>/payer", methods=["POST"])
def simuler_paiement_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    data    = request.get_json() or {}

    # En sandbox on simule directement le succès
    mission.paiement_reference = f"KKIAPAY-SIM-{mission_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    mission.paiement_statut    = "paye"
    mission.statut             = "ouverte"
    mission.date_echeance      = datetime.utcnow() + timedelta(hours=mission.delai_heures)

    db.session.commit()
    return jsonify({
        "message":   "Paiement simulé avec succès — Mission publiée !",
        "mission":   mission.to_dict(),
        "echeance":  mission.date_echeance.strftime("%d/%m/%Y à %H:%M")
    }), 200

# ════════════════════════════════════════
# COLLECTES
# ════════════════════════════════════════
@main.route("/api/collectes", methods=["POST"])
def soumettre_collecte():
    mission_id  = request.form.get("mission_id")
    agent_id    = request.form.get("agent_id")
    prix        = request.form.get("prix_observe")
    dispo       = request.form.get("disponibilite","true").lower() == "true"
    commentaire = request.form.get("commentaire","")
    latitude    = request.form.get("latitude")
    longitude   = request.form.get("longitude")

    photo_url = None
    if "photo" in request.files:
        fichier = request.files["photo"]
        if fichier and ext_ok(fichier.filename):
            nom = f"{uuid.uuid4().hex}_{secure_filename(fichier.filename)}"
            fichier.save(os.path.join(UPLOAD_FOLDER, nom))
            photo_url = f"/uploads/{nom}"

    collecte = Collecte(
        mission_id   = int(mission_id),
        agent_id     = int(agent_id),
        prix_observe = float(prix) if prix else None,
        disponibilite= dispo,
        commentaire  = commentaire,
        photo_url    = photo_url,
        latitude     = float(latitude) if latitude else None,
        longitude    = float(longitude) if longitude else None
    )
    db.session.add(collecte)
    db.session.flush()

    # Analyse anti-fraude complète
    mission = Mission.query.get(int(mission_id))
    score, statut, raison, problemes, avertissements = \
        analyser_collecte(collecte, mission, db)

    collecte.statut            = statut
    collecte.commentaire_admin = raison
    db.session.commit()

    # Si fraude détectée — alerter
    if statut == "fraude":
        agent = User.query.get(int(agent_id))
        print(f"[FRAUDE] Agent {agent.nom if agent else agent_id} "
              f"— {raison}")

    # Vérifier si mission peut être finalisée
    nb_valides = Collecte.query.filter_by(
        mission_id=int(mission_id), statut="validee").count()
    if nb_valides >= mission.nb_collectes_requis:
        mission.statut = "prete"
        db.session.commit()
        finaliser_mission(
            mission.id, current_app._get_current_object())

    return jsonify({
        "message":          "Collecte soumise",
        "statut_auto":      statut,
        "score_confiance":  score,
        "raison":           raison,
        "problemes":        problemes,
        "avertissements":   avertissements,
        "collecte":         collecte.to_dict()
    }), 201
@main.route("/api/collectes/mission/<int:mission_id>", methods=["GET"])
def collectes_par_mission(mission_id):
    collectes = Collecte.query.filter_by(mission_id=mission_id).all()
    return jsonify([c.to_dict() for c in collectes]), 200

@main.route("/api/agent/<int:agent_id>/collectes", methods=["GET"])
def collectes_agent(agent_id):
    collectes = Collecte.query.filter_by(agent_id=agent_id).all()
    return jsonify([c.to_dict() for c in collectes]), 200

# ════════════════════════════════════════
# AGENTS
# ════════════════════════════════════════
@main.route("/api/agents", methods=["GET"])
def liste_agents():
    agents = User.query.filter_by(role="agent").all()
    return jsonify([a.to_dict() for a in agents]), 200

# ════════════════════════════════════════
# CONTACT
# ════════════════════════════════════════
@main.route("/api/contact", methods=["POST"])
def nouveau_contact():
    data = request.get_json()
    contact = Contact(
        nom        = data.get("nom"),
        telephone  = data.get("telephone"),
        email      = data.get("email", ""),
        type_besoin= data.get("type_besoin"),
        marche     = data.get("marche"),
        message    = data.get("message", "")
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({"message": "Demande enregistrée"}), 201

# ════════════════════════════════════════
# EXPORT
# ════════════════════════════════════════
@main.route("/api/export/pdf/<int:mission_id>")
def export_pdf(mission_id):
    mission   = Mission.query.get_or_404(mission_id)
    collectes = Collecte.query.filter_by(mission_id=mission_id).all()
    buffer    = generer_pdf(mission, collectes)
    nom       = f"rapport_{mission.marche_cible}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(buffer, mimetype="application/pdf",
                     as_attachment=True, download_name=nom)

@main.route("/api/export/excel/<int:mission_id>")
def export_excel(mission_id):
    mission   = Mission.query.get_or_404(mission_id)
    collectes = Collecte.query.filter_by(mission_id=mission_id).all()
    buffer    = generer_excel(mission, collectes)
    nom       = f"rapport_{mission.marche_cible}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=nom)

# ════════════════════════════════════════
# ADMIN API
# ════════════════════════════════════════
@main.route("/api/admin/missions", methods=["GET"])
def admin_missions():
    missions = Mission.query.order_by(Mission.date_creation.desc()).all()
    return jsonify([m.to_dict() for m in missions]), 200

@main.route("/api/admin/collectes/en_attente", methods=["GET"])
def collectes_en_attente():
    collectes = Collecte.query.filter_by(statut="en_attente").order_by(
        Collecte.date_soumission.desc()).all()
    resultat = []
    for c in collectes:
        agent   = User.query.get(c.agent_id)
        mission = Mission.query.get(c.mission_id)
        d = c.to_dict()
        d["agent_nom"]      = agent.nom if agent else "—"
        d["agent_tel"]      = agent.telephone if agent else "—"
        d["mission_titre"]  = mission.titre if mission else "—"
        d["mission_points"] = mission.points_recompense if mission else 0
        resultat.append(d)
    return jsonify(resultat), 200

@main.route("/api/admin/collecte/<int:collecte_id>/valider", methods=["POST"])
def valider_collecte(collecte_id):
    collecte = Collecte.query.get_or_404(collecte_id)
    if collecte.statut != "en_attente":
        return jsonify({"erreur": "Collecte déjà traitée"}), 400
    collecte.statut = "validee"
    mission = Mission.query.get(collecte.mission_id)
    agent   = User.query.get(collecte.agent_id)
    if mission and agent:
        # Calculer bonus selon niveau
        remun_base = mission.points_recompense
        remun_avec_bonus, bonus = calculer_bonus(remun_base, agent.niveau or "bronze")
        agent.solde_points += remun_avec_bonus

        # Mettre à jour le niveau
        niveau_monte, nouveau_niveau = mettre_a_jour_niveau(agent)

    db.session.commit()

    # SMS avec info niveau si montée
    if agent:
        msg_niveau = ""
        if niveau_monte:
            info = NIVEAUX[nouveau_niveau]
            msg_niveau = f" 🎉 Tu passes niveau {info['emoji']} {info['nom']} !"
        sms_collecte_validee(
            agent.telephone, agent.nom,
            mission.titre if mission else "Mission",
            remun_avec_bonus,
            agent.solde_points
        )

    return jsonify({
        "message":       f"Collecte validée — {remun_avec_bonus} pts à {agent.nom if agent else '?'}",
        "bonus":         bonus,
        "niveau_monte":  niveau_monte,
        "nouveau_niveau": nouveau_niveau if niveau_monte else None
    }), 200

@main.route("/api/agent/<int:agent_id>/niveau", methods=["GET"])
def niveau_agent(agent_id):
    agent = User.query.get_or_404(agent_id)
    prog  = progression_vers_suivant(agent.nb_collectes_valides or 0)
    info  = NIVEAUX.get(agent.niveau or "bronze")
    return jsonify({
        "agent":       agent.to_dict(),
        "niveau_info": info,
        "progression": prog
    }), 200

@main.route("/api/admin/collecte/<int:collecte_id>/rejeter", methods=["POST"])
def rejeter_collecte(collecte_id):
    data     = request.get_json() or {}
    collecte = Collecte.query.get_or_404(collecte_id)
    if collecte.statut != "en_attente":
        return jsonify({"erreur": "Collecte déjà traitée"}), 400
    collecte.statut            = "rejetee"
    collecte.commentaire_admin = data.get("raison", "Non conforme")
    db.session.commit()
    # SMS à l'agent
    agent = User.query.get(collecte.agent_id)
    if agent:
        sms_collecte_rejetee(
            agent.telephone, agent.nom,
            collecte.commentaire_admin or "Non conforme",
            data.get("raison","Non conforme")
        )
    return jsonify({"message": "Collecte rejetée"}), 200

@main.route("/api/admin/mission/<int:mission_id>/forcer_finalisation", methods=["POST"])
def forcer_finalisation(mission_id):
    finaliser_mission(mission_id, current_app._get_current_object())
    return jsonify({"message": f"Mission #{mission_id} finalisée manuellement"}), 200

@main.route("/api/admin/contacts", methods=["GET"])
def liste_contacts():
    contacts = Contact.query.order_by(Contact.date.desc()).all()
    return jsonify([c.to_dict() for c in contacts]), 200

@main.route("/api/admin/revenus", methods=["GET"])
def revenus_admin():
    missions_finalisees = Mission.query.filter_by(statut="finalisee").all()
    total_revenus  = sum(m.marge_fcfa for m in missions_finalisees)
    total_missions = len(missions_finalisees)
    total_agents   = sum(m.budget_agents_fcfa for m in missions_finalisees)
    return jsonify({
        "total_revenus_fcfa":  total_revenus,
        "total_missions":      total_missions,
        "total_paye_agents":   total_agents,
        "missions":            [m.to_dict() for m in missions_finalisees]
    }), 200

# Servir les photos
@main.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
@main.route("/api/admin/test-sms", methods=["POST"])
def test_sms():
    from .sms import envoyer_sms
    data = request.get_json()
    tel  = data.get("telephone")
    msg  = data.get("message", "Test DataBroker 229 — SMS fonctionnel !")
    r    = envoyer_sms(tel, msg)
    return jsonify(r), 200 if r["succes"] else 500
# ════════════════════════════════════════
# CLASSEMENT
# ════════════════════════════════════════
@main.route("/api/classement", methods=["GET"])
def classement_agents():
    periode = int(request.args.get("periode", 30))
    agents  = User.query.filter_by(role="agent").all()

    toutes_collectes = []
    for a in agents:
        cols = Collecte.query.filter_by(agent_id=a.id).all()
        toutes_collectes.extend(cols)

    classement = calculer_classement(agents, toutes_collectes, periode)
    return jsonify(classement), 200

@main.route("/classement")
def page_classement():
    return render_template("classement.html")

# ════════════════════════════════════════
# HISTORIQUE PRIX
# ════════════════════════════════════════
@main.route("/api/historique/prix", methods=["GET"])
def historique_prix():
    produit = request.args.get("produit")
    marche  = request.args.get("marche")
    jours   = int(request.args.get("jours", 90))

    # Récupérer toutes les collectes validées
    missions = Mission.query.all()
    toutes   = []
    for m in missions:
        if produit and produit.lower() not in (m.produit_cible or "").lower():
            continue
        if marche and marche != m.marche_cible:
            continue
        cols = Collecte.query.filter_by(
            mission_id=m.id, statut="validee").all()
        for c in cols:
            c._mission = m
        toutes.extend(cols)

    historique = calculer_historique_prix(toutes, produit, marche, jours)
    return jsonify(historique), 200

@main.route("/historique")
def page_historique():
    return render_template("historique.html")

# ════════════════════════════════════════
# ANTI-FRAUDE STATS (admin)
# ════════════════════════════════════════
@main.route("/api/admin/fraudes", methods=["GET"])
def stats_fraudes():
    fraudes = Collecte.query.filter_by(statut="fraude").all()
    resultat = []
    for c in fraudes:
        agent   = User.query.get(c.agent_id)
        mission = Mission.query.get(c.mission_id)
        d = c.to_dict()
        d["agent_nom"]     = agent.nom if agent else "—"
        d["mission_titre"] = mission.titre if mission else "—"
        resultat.append(d)
    return jsonify(resultat), 200
@main.route("/api/admin/mission/<int:mission_id>/supprimer", methods=["DELETE"])
def supprimer_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    # Supprimer les collectes liées
    Collecte.query.filter_by(mission_id=mission_id).delete()
    db.session.delete(mission)
    db.session.commit()
    return jsonify({"message": f"Mission #{mission_id} supprimée"}), 200
