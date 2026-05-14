import africastalking
from datetime import datetime

# ════════════════════════════════════════════════
# CONFIGURATION AFRICA'S TALKING (SANDBOX)
# En production : remplacer par tes vraies clés
# Inscription gratuite : https://africastalking.com
# ════════════════════════════════════════════════
AT_USERNAME = "sandbox"           # Ton username AT
AT_API_KEY  = "atsk_4fcee65b77b92ebd1900ca144bcb5768b87eef6fbbce796273918acf8226cd587c94287a"  # Ta clé API AT

def init_sms():
    africastalking.initialize(AT_USERNAME, AT_API_KEY)
    return africastalking.SMS

def formater_numero(telephone):
    """
    Convertit un numéro béninois en format international
    MTN    : 96/97/66/67
    Moov   : 94/95/64/65
    Celtiis: 98/99/68/69/01 (nouveaux numéros à 10 chiffres)
    """
    tel = telephone.strip().replace(" ","").replace("-","")

    if tel.startswith("+229"):
        return tel
    if tel.startswith("229"):
        return "+" + tel
    # Nouveaux numéros Celtiis commençant par 01
    if tel.startswith("01") and len(tel) == 10:
        return "+229" + tel
    # Numéros à 8 chiffres (anciens formats)
    if len(tel) == 8:
        return "+229" + tel

    return "+229" + tel

def detecter_operateur_sms(telephone):
    """Détecte l'opérateur pour personnaliser les messages"""
    tel = telephone.replace("+229","").replace(" ","").strip()

    if tel.startswith("01"):
        return "Celtiis Cash"

    prefixe = tel[:2] if len(tel) >= 2 else ""

    if prefixe in ["96","97","66","67"]:
        return "MTN MoMo"
    elif prefixe in ["94","95","64","65"]:
        return "Flooz"
    elif prefixe in ["98","99","68","69"]:
        return "Celtiis Cash"
    return "Mobile Money"
# ════════════════════════════════════════════════
# MESSAGES SMS PAR ÉVÉNEMENT
# ════════════════════════════════════════════════

def sms_nouvelle_mission(agent_telephone, agent_nom, mission_titre,
                          marche, points, date_echeance):
    """Notifier un agent qu'une nouvelle mission est disponible"""
    msg = (
        f"DataBroker229 :\n"
        f"Salut {agent_nom} !\n"
        f"Nouvelle mission disponible :\n"
        f"'{mission_titre}'\n"
        f"Marché : {marche}\n"
        f"Récompense : {points} pts\n"
        f"Délai : {date_echeance}\n"
        f"Connecte-toi vite !"
    )
    return envoyer_sms(agent_telephone, msg)

def sms_collecte_validee(agent_telephone, agent_nom,
                          mission_titre, points_gagnes, nouveau_solde):
    """Notifier un agent que sa collecte a été validée"""
    msg = (
        f"DataBroker229 :\n"
        f"Bravo {agent_nom} !\n"
        f"Ta collecte pour '{mission_titre}' "
        f"a été validée.\n"
        f"+{points_gagnes} pts crédités.\n"
        f"Solde : {nouveau_solde} pts "
        f"(={int(nouveau_solde*1.5)} FCFA)"
    )
    return envoyer_sms(agent_telephone, msg)

def sms_collecte_rejetee(agent_telephone, agent_nom,
                          mission_titre, raison):
    """Notifier un agent que sa collecte a été rejetée"""
    msg = (
        f"DataBroker229 :\n"
        f"Bonjour {agent_nom},\n"
        f"Ta collecte pour '{mission_titre}' "
        f"a été rejetée.\n"
        f"Raison : {raison}\n"
        f"Réessaie en respectant les consignes."
    )
    return envoyer_sms(agent_telephone, msg)

def sms_paiement_agent(agent_telephone, agent_nom,
                        montant_fcfa, operateur, reference):
    """Notifier un agent d'un paiement reçu"""
    # Détection automatique si opérateur non précisé
    if not operateur or operateur == "auto":
        operateur = detecter_operateur_sms(agent_telephone)

    msg = (
        f"DataBroker229 :\n"
        f"Paiement reçu {agent_nom} !\n"
        f"{montant_fcfa} FCFA envoyés "
        f"sur ton {operateur}.\n"
        f"Réf: {reference}\n"
        f"Merci pour ton travail !"
    )
    return envoyer_sms(agent_telephone, msg)

def sms_mission_publiee_client(client_telephone, client_nom,
                                mission_titre, nb_collectes,
                                delai_heures, echeance):
    """Confirmer au client que sa mission est publiée"""
    msg = (
        f"DataBroker229 :\n"
        f"Mission publiée {client_nom} !\n"
        f"'{mission_titre}'\n"
        f"{nb_collectes} collectes demandées.\n"
        f"Délai : {delai_heures}h\n"
        f"Rapport attendu le : {echeance}\n"
        f"Suivi : databroker229.com/client"
    )
    return envoyer_sms(client_telephone, msg)

def sms_rapport_pret(client_telephone, client_nom,
                      mission_titre, email_client):
    """Notifier le client que son rapport est prêt"""
    msg = (
        f"DataBroker229 :\n"
        f"Rapport prêt {client_nom} !\n"
        f"'{mission_titre}'\n"
        f"Rapport PDF envoyé sur :\n"
        f"{email_client}\n"
        f"Questions ? WhatsApp :\n"
        f"+229 61 97 67 12"
    )
    return envoyer_sms(client_telephone, msg)

def sms_bienvenue_agent(telephone, nom):
    """SMS de bienvenue pour un nouvel agent"""
    msg = (
        f"Bienvenue sur DataBroker229 !\n"
        f"Salut {nom},\n"
        f"Ton compte agent est créé.\n"
        f"Connecte-toi et accepte ta "
        f"première mission pour commencer "
        f"à gagner !\n"
        f"databroker229.com/agent"
    )
    return envoyer_sms(telephone, msg)

def sms_bienvenue_client(telephone, nom):
    """SMS de bienvenue pour un nouveau client"""
    msg = (
        f"Bienvenue sur DataBroker229 !\n"
        f"Bonjour {nom},\n"
        f"Votre compte client est créé.\n"
        f"Commandez votre première "
        f"mission dès maintenant :\n"
        f"databroker229.com/client\n"
        f"Support : +229 61 97 67 12"
    )
    return envoyer_sms(telephone, msg)

# ════════════════════════════════════════════════
# FONCTION D'ENVOI PRINCIPALE
# ════════════════════════════════════════════════
def envoyer_sms(telephone, message):
    """
    Envoie un SMS via Africa's Talking.
    En mode sandbox, les SMS sont simulés.
    """
    try:
        numero = formater_numero(telephone)
        sms    = init_sms()

        # Mode sandbox : affiche dans les logs
        print(f"[SMS] → {numero}")
        print(f"[SMS] Message : {message}")
        print(f"[SMS] {'—'*40}")

        response = sms.send(
            message    = message,
            recipients = [numero],
            sender_id  = "DataBroker"  # Nom affiché sur le téléphone
        )
        print(f"[SMS] Réponse AT : {response}")
        return {"succes": True, "response": response}

    except Exception as e:
        print(f"[SMS] Erreur : {str(e)}")
        # Ne pas bloquer l'app si SMS échoue
        return {"succes": False, "erreur": str(e)}

# ════════════════════════════════════════════════
# ENVOI EN MASSE (notifier tous les agents)
# ════════════════════════════════════════════════
def notifier_tous_agents(agents, mission_titre, marche,
                          points, date_echeance):
    """Envoyer une notification à tous les agents actifs"""
    resultats = []
    for agent in agents:
        if agent.telephone:
            r = sms_nouvelle_mission(
                agent.telephone, agent.nom,
                mission_titre, marche,
                points, date_echeance
            )
            resultats.append({
                "agent": agent.nom,
                "tel":   agent.telephone,
                "ok":    r["succes"]
            })
    return resultats
