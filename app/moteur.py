from datetime import datetime
from math import radians, cos, sin, asin, sqrt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io

# ════════════════════════════════════════════════
# CALCUL DISTANCE GPS (formule Haversine)
# ════════════════════════════════════════════════
def distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))


# ════════════════════════════════════════════════
# VALIDATION AUTOMATIQUE D'UNE COLLECTE
# ════════════════════════════════════════════════
def valider_collecte_auto(collecte, mission, tolerance_km=5.0):
    raisons_rejet = []

    # Vérif GPS
    if collecte.latitude and collecte.longitude:
        if mission.marche_latitude and mission.marche_longitude:
            dist = distance_km(
                collecte.latitude, collecte.longitude,
                mission.marche_latitude, mission.marche_longitude
            )
            collecte.distance_marche = round(dist, 2)
            if dist > tolerance_km:
                raisons_rejet.append(
                    f"GPS trop loin du marché ({dist:.1f}km > {tolerance_km}km autorisés)")
    else:
        raisons_rejet.append("Pas de GPS fourni")

    # Vérif photo
    if not collecte.photo_url:
        raisons_rejet.append("Pas de photo fournie")

    # Vérif prix
    if collecte.prix_observe and collecte.prix_observe < 0:
        raisons_rejet.append("Prix négatif invalide")

    if raisons_rejet:
        collecte.statut          = "rejetee"
        collecte.commentaire_admin = " | ".join(raisons_rejet)
        return False, raisons_rejet

    collecte.statut = "validee"
    return True, []


# ════════════════════════════════════════════════
# CALCUL DES PRIX ET MARGES
# ════════════════════════════════════════════════
def calculer_prix_mission(nb_collectes, delai_heures, marge=0.40):
    """
    Tarification :
      - Base : 500 FCFA par collecte
      - Urgent (24h) : +30%
      - Standard (48h) : +0%
      - Étendu (72h) : -10%
    """
    prix_base = nb_collectes * 500

    if delai_heures <= 24:
        prix_base = int(prix_base * 1.30)
    elif delai_heures >= 72:
        prix_base = int(prix_base * 0.90)

    marge_fcfa         = int(prix_base * marge)
    budget_agents_fcfa = prix_base - marge_fcfa
    remuneration_agent = budget_agents_fcfa // nb_collectes if nb_collectes > 0 else 0

    return {
        "prix_client_fcfa":   prix_base,
        "marge_fcfa":         marge_fcfa,
        "budget_agents_fcfa": budget_agents_fcfa,
        "remuneration_agent": remuneration_agent
    }


# ════════════════════════════════════════════════
# ENVOI EMAIL AVEC PDF EN PIÈCE JOINTE
# ════════════════════════════════════════════════
def envoyer_rapport_email(mission, pdf_buffer, config):
    try:
        msg = MIMEMultipart()
        msg["From"]    = f"{config['nom']} <{config['expediteur']}>"
        msg["To"]      = mission.client_email
        msg["Subject"] = f"[DataBroker 229] Votre rapport — {mission.titre}"

        corps = f"""
Bonjour {mission.client_nom},

Votre rapport de collecte de données est prêt !

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 MISSION : {mission.titre}
📍 MARCHÉ  : {mission.marche_cible}
🛒 PRODUIT : {mission.produit_cible}
📅 DÉLAI   : {mission.delai_heures}h
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Le rapport PDF complet est joint à cet email.
Il contient : prix min/max/moyen, taux de disponibilité,
photos de terrain géolocalisées, données brutes.

Pour toute question :
📱 WhatsApp : {config['whatsapp']}
📞 Téléphone : {config['telephone']}

Merci de votre confiance,
L'équipe DataBroker 229
"""
        msg.attach(MIMEText(corps, "plain"))

        # Attacher le PDF
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_buffer.read())
        encoders.encode_base64(part)
        nom_fichier = f"rapport_{mission.marche_cible}_{datetime.now().strftime('%Y%m%d')}.pdf"
        part.add_header("Content-Disposition", f"attachment; filename={nom_fichier}")
        msg.attach(part)

        # Envoi via Gmail
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
            serveur.login(config["expediteur"], config["mot_de_passe"])
            serveur.send_message(msg)

        return True, "Email envoyé avec succès"

    except Exception as e:
        return False, f"Erreur email : {str(e)}"


# ════════════════════════════════════════════════
# FINALISATION D'UNE MISSION
# ════════════════════════════════════════════════
def finaliser_mission(mission_id, app):
    with app.app_context():
        from .models import db, Mission, Collecte, User, Transaction
        from .export import generer_pdf
        from .paiement import payer_agent

        mission = Mission.query.get(mission_id)
        if not mission or mission.statut == "finalisee":
            return

        print(f"[MOTEUR] Finalisation mission #{mission_id} — {mission.titre}")

        # Récupérer les collectes validées
        collectes_valides = Collecte.query.filter_by(
            mission_id=mission_id, statut="validee").all()

        if not collectes_valides:
            mission.statut = "echouee"
            db.session.commit()
            print(f"[MOTEUR] Mission #{mission_id} échouée — aucune collecte valide")
            return

        # 1. Générer le rapport PDF
        pdf_buffer = generer_pdf(mission, collectes_valides)

        # 2. Envoyer par email si email client disponible
        if mission.client_email:
            from flask import current_app
            config_email = {
                "expediteur":   current_app.config["EMAIL_EXPEDITEUR"],
                "mot_de_passe": current_app.config["EMAIL_MOT_DE_PASSE"],
                "nom":          current_app.config["EMAIL_NOM"],
                "whatsapp":     current_app.config["WHATSAPP"],
                "telephone":    current_app.config["TELEPHONE"]
            }
            pdf_buffer.seek(0)
            succes, msg = envoyer_rapport_email(mission, pdf_buffer, config_email)
            print(f"[MOTEUR] Email : {msg}")

        # 3. Payer les agents pour leurs collectes validées
        for collecte in collectes_valides:
            if not collecte.agent_paye:
                agent = User.query.get(collecte.agent_id)
                if agent:
                    montant = mission.remuneration_agent
                    # Enregistrer la transaction
                    transaction = Transaction(
                        agent_id=agent.id,
                        mission_id=mission.id,
                        montant_fcfa=montant,
                        operateur="auto",
                        reference=f"AUTO-{mission.id}-{agent.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        type_trans="paiement_mission",
                        statut="reussie"
                    )
                    db.session.add(transaction)
                    collecte.agent_paye = True
                    print(f"[MOTEUR] Agent {agent.nom} payé : {montant} FCFA")

        # 4. Passer la mission en finalisée
        mission.statut = "finalisee"
        db.session.commit()
        print(f"[MOTEUR] Mission #{mission_id} finalisée avec succès ✅")


# ════════════════════════════════════════════════
# VÉRIFICATION PÉRIODIQUE DES ÉCHÉANCES
# ════════════════════════════════════════════════
def verifier_echeances(app):
    with app.app_context():
        from .models import Mission
        now = datetime.utcnow()
        missions = Mission.query.filter(
            Mission.statut == "ouverte",
            Mission.date_echeance <= now
        ).all()

        for mission in missions:
            print(f"[SCHEDULER] Délai expiré pour mission #{mission.id}")
            finaliser_mission(mission.id, app)
