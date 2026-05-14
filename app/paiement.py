import json
import random
import time
from datetime import datetime

# ════════════════════════════════════════════════
# CONFIGURATION DES OPÉRATEURS
# ════════════════════════════════════════════════
OPERATEURS = {
    "mtn": {
        "nom":      "MTN Mobile Money",
        "prefixes": ["96", "97", "66", "67", "01"],
        "couleur":  "#FFCC00",
        "logo":     "MTN"
    },
    "moov": {
        "nom":      "Flooz (Moov Africa)",
        "prefixes": ["94", "95", "64", "65", "01"],
        "couleur":  "#0066CC",
        "logo":     "MOOV"
    },
    "celtiis": {
        "nom":      "Celtiis Cash",
        "prefixes": ["98", "99", "68", "69", "01"],
        "couleur":  "#E30613",
        "logo":     "CELTIIS"
    }
}

def detecter_operateur(telephone):
    """Détecte l'opérateur selon le préfixe du numéro"""
    tel = telephone.replace("+229", "").replace(" ", "").strip()

    # Celtiis — nouveaux numéros à 10 chiffres commençant par 01
    if tel.startswith("01") and len(tel) == 10:
        return "celtiis"

    if len(tel) >= 2:
        prefixe = tel[:2]
        for op, info in OPERATEURS.items():
            if prefixe in info["prefixes"]:
                return op
    return None
def points_vers_fcfa(points):
    return int(points * 1.5)

def fcfa_vers_points(fcfa):
    return int(fcfa / 1.5)

def simuler_paiement(telephone, montant_fcfa, operateur, reference):
    time.sleep(0.5)
    return {
        "succes":    True,
        "reference": reference,
        "telephone": telephone,
        "montant":   montant_fcfa,
        "operateur": operateur,
        "message":   f"Paiement de {montant_fcfa} FCFA effectue via {OPERATEURS.get(operateur, {}).get('nom', operateur)}",
        "timestamp": datetime.now().isoformat()
    }

def payer_agent(agent, points_a_retirer):
    if agent.solde_points < points_a_retirer:
        return {
            "succes":  False,
            "message": f"Solde insuffisant. Tu as {agent.solde_points} pts, tu demandes {points_a_retirer} pts."
        }

    if points_a_retirer < 100:
        return {
            "succes":  False,
            "message": "Minimum 100 points pour un retrait (= 150 FCFA)"
        }

    montant_fcfa = points_vers_fcfa(points_a_retirer)
    operateur    = detecter_operateur(agent.telephone)

    if not operateur:
        return {
            "succes":  False,
            "message": f"Operateur non reconnu pour le numero {agent.telephone}."
        }

    reference = f"DB229-{agent.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    resultat = simuler_paiement(
        telephone=agent.telephone,
        montant_fcfa=montant_fcfa,
        operateur=operateur,
        reference=reference
    )

    if resultat["succes"]:
        from .models import db, Transaction

        agent.solde_points -= points_a_retirer

        transaction = Transaction(
            agent_id=agent.id,
            points_retires=points_a_retirer,
            montant_fcfa=montant_fcfa,
            operateur=operateur,
            reference=reference,
            statut="reussie"
        )
        db.session.add(transaction)
        db.session.commit()

    return resultat
