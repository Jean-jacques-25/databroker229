from math import radians, cos, sin, asin, sqrt
from datetime import datetime, timedelta
from collections import defaultdict

# ════════════════════════════════════════════════
# CALCUL DISTANCE GPS
# ════════════════════════════════════════════════
def distance_km(lat1, lon1, lat2, lon2):
    R = 6371
    lat1,lon1,lat2,lon2 = map(radians,[lat1,lon1,lat2,lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return R * 2 * asin(sqrt(a))

# ════════════════════════════════════════════════
# COORDONNÉES OFFICIELLES DES MARCHÉS
# ════════════════════════════════════════════════
MARCHES_COORDS = {
    "Dantokpa":    (6.3698,  2.4382),
    "Ouando":      (6.4969,  2.6289),
    "Akpakpa":     (6.3654,  2.4419),
    "Missèbo":     (6.3744,  2.4197),
    "Sainte Rita": (6.3601,  2.3987),
    "Bohicon":     (7.1793,  2.0669),
    "Parakou":     (9.3370,  2.6280),
    "Natitingou":  (10.3079, 1.3762),
    "Rural":       None
}

# ════════════════════════════════════════════════
# VÉRIFICATIONS ANTI-FRAUDE
# ════════════════════════════════════════════════

def verifier_gps_marche(lat, lon, marche_nom, tolerance_km=5.0):
    """Vérifie que le GPS correspond bien au marché indiqué"""
    coords = MARCHES_COORDS.get(marche_nom)
    if not coords:
        return True, 0, "Marché rural — GPS non vérifié"

    dist = distance_km(lat, lon, coords[0], coords[1])
    if dist > tolerance_km:
        return False, round(dist,2), f"Trop loin du marché ({dist:.1f}km > {tolerance_km}km)"

    return True, round(dist,2), f"GPS valide ({dist:.1f}km du marché)"

def verifier_doublon(agent_id, mission_id, db):
    """Vérifie qu'un agent n'a pas déjà soumis pour cette mission"""
    from .models import Collecte
    existant = Collecte.query.filter_by(
        agent_id=agent_id,
        mission_id=mission_id
    ).filter(Collecte.statut != "rejetee").first()

    if existant:
        return False, "Tu as déjà soumis une collecte pour cette mission"
    return True, "OK"

def verifier_vitesse_deplacement(agent_id, lat, lon, db):
    """
    Vérifie qu'un agent ne soumet pas depuis deux endroits
    trop éloignés en peu de temps (impossible physiquement)
    Vitesse max : 100km/h
    """
    from .models import Collecte
    limite = datetime.utcnow() - timedelta(hours=1)
    recentes = Collecte.query.filter(
        Collecte.agent_id == agent_id,
        Collecte.date_soumission >= limite,
        Collecte.latitude != None
    ).order_by(Collecte.date_soumission.desc()).first()

    if not recentes or not recentes.latitude:
        return True, "OK"

    dist = distance_km(lat, lon,
                       recentes.latitude, recentes.longitude)
    minutes = (datetime.utcnow() - recentes.date_soumission
               ).total_seconds() / 60

    if minutes > 0:
        vitesse_kmh = (dist / minutes) * 60
        if vitesse_kmh > 100:
            return False, (f"Déplacement suspect : {dist:.1f}km "
                          f"en {minutes:.0f} min "
                          f"({vitesse_kmh:.0f}km/h)")
    return True, "OK"

def verifier_prix_aberrant(prix, mission_id, db):
    """
    Vérifie que le prix soumis n'est pas aberrant
    par rapport aux autres collectes de la même mission
    """
    if not prix or prix <= 0:
        return False, "Prix invalide ou nul"

    from .models import Collecte
    autres = Collecte.query.filter(
        Collecte.mission_id == mission_id,
        Collecte.prix_observe != None,
        Collecte.statut == "validee"
    ).all()

    if len(autres) < 3:
        return True, "Pas assez de données pour comparaison"

    prix_vals = [c.prix_observe for c in autres]
    moy  = sum(prix_vals) / len(prix_vals)
    ecart_max = moy * 3  # Prix max = 3x la moyenne
    ecart_min = moy * 0.2  # Prix min = 20% de la moyenne

    if prix > ecart_max:
        return False, f"Prix trop élevé ({prix} vs moyenne {moy:.0f} FCFA)"
    if prix < ecart_min:
        return False, f"Prix trop bas ({prix} vs moyenne {moy:.0f} FCFA)"

    return True, f"Prix cohérent (moyenne : {moy:.0f} FCFA)"

def verifier_soumissions_rapides(agent_id, db):
    """
    Détecte les agents qui soumettent trop rapidement
    (spam de collectes en quelques minutes)
    Max : 3 collectes par 10 minutes
    """
    from .models import Collecte
    limite = datetime.utcnow() - timedelta(minutes=10)
    nb_recent = Collecte.query.filter(
        Collecte.agent_id == agent_id,
        Collecte.date_soumission >= limite
    ).count()

    if nb_recent >= 3:
        return False, f"Trop de soumissions rapides ({nb_recent} en 10 min)"
    return True, "OK"

# ════════════════════════════════════════════════
# ANALYSE COMPLÈTE ANTI-FRAUDE
# ════════════════════════════════════════════════
def analyser_collecte(collecte, mission, db):
    """
    Analyse complète d'une collecte.
    Retourne : (score_confiance, statut, raisons)
    Score : 0-100 (100 = parfaitement fiable)
    """
    problemes  = []
    avertissements = []
    score = 100

    # 1. Vérif GPS position
    if collecte.latitude and collecte.longitude:
        gps_ok, dist, msg_gps = verifier_gps_marche(
            collecte.latitude, collecte.longitude,
            mission.marche_cible or ""
        )
        collecte.distance_marche = dist
        if not gps_ok:
            problemes.append(msg_gps)
            score -= 40
        elif dist > 2:
            avertissements.append(f"Agent à {dist:.1f}km du centre du marché")
            score -= 10
    else:
        avertissements.append("Pas de GPS fourni")
        score -= 20

    # 2. Vérif doublon
    doublon_ok, msg_doublon = verifier_doublon(
        collecte.agent_id, collecte.mission_id, db)
    if not doublon_ok:
        problemes.append(msg_doublon)
        score -= 50

    # 3. Vérif vitesse déplacement
    vitesse_ok, msg_vitesse = verifier_vitesse_deplacement(
        collecte.agent_id,
        collecte.latitude or 0,
        collecte.longitude or 0,
        db
    )
    if not vitesse_ok:
        problemes.append(msg_vitesse)
        score -= 30

    # 4. Vérif prix aberrant
    if collecte.prix_observe:
        prix_ok, msg_prix = verifier_prix_aberrant(
            collecte.prix_observe, collecte.mission_id, db)
        if not prix_ok:
            avertissements.append(msg_prix)
            score -= 15

    # 5. Vérif spam soumissions
    spam_ok, msg_spam = verifier_soumissions_rapides(
        collecte.agent_id, db)
    if not spam_ok:
        problemes.append(msg_spam)
        score -= 25

    # 6. Photo obligatoire
    if not collecte.photo_url:
        avertissements.append("Pas de photo fournie")
        score -= 15

    # Déterminer statut final
    score = max(0, score)

    if problemes:
        statut = "fraude"
        raison = " | ".join(problemes)
    elif score < 50:
        statut = "rejetee"
        raison = " | ".join(avertissements)
    elif avertissements:
        statut = "validee"
        raison = "Validée avec avertissements : " + " | ".join(avertissements)
    else:
        statut = "validee"
        raison = "Collecte conforme"

    return score, statut, raison, problemes, avertissements
