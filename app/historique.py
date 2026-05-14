from datetime import datetime, timedelta
from collections import defaultdict

def calculer_historique_prix(collectes, produit=None,
                              marche=None, jours=90):
    """
    Calcule l'historique des prix pour un produit/marché.
    Retourne les données pour un graphique d'évolution.
    """
    limite = datetime.utcnow() - timedelta(days=jours)

    # Filtrer
    donnees = []
    for c in collectes:
        if c.statut != "validee":
            continue
        if not c.prix_observe:
            continue
        try:
            date_c = datetime.strptime(
                c.date_soumission, "%d/%m/%Y %H:%M")
        except:
            continue
        if date_c < limite:
            continue
        donnees.append({
            "date":    date_c,
            "prix":    c.prix_observe,
            "mission": c._mission if hasattr(c,"_mission") else None
        })

    if not donnees:
        return {"points":[], "stats":{}, "tendance": "stable"}

    # Regrouper par semaine
    par_semaine = defaultdict(list)
    for d in donnees:
        # Numéro de semaine
        sem = d["date"].strftime("%Y-S%W")
        par_semaine[sem].append(d["prix"])

    points = []
    for sem in sorted(par_semaine.keys()):
        prix_sem = par_semaine[sem]
        points.append({
            "periode": sem,
            "prix_moy": round(sum(prix_sem)/len(prix_sem)),
            "prix_min": min(prix_sem),
            "prix_max": max(prix_sem),
            "nb_obs":   len(prix_sem)
        })

    # Stats globales
    tous_prix = [d["prix"] for d in donnees]
    stats = {
        "prix_actuel":  round(sum(tous_prix[-5:])/min(len(tous_prix),5)),
        "prix_moy":     round(sum(tous_prix)/len(tous_prix)),
        "prix_min":     min(tous_prix),
        "prix_max":     max(tous_prix),
        "nb_observations": len(tous_prix),
        "periode_jours": jours
    }

    # Tendance
    tendance = "stable"
    if len(points) >= 2:
        premier = points[0]["prix_moy"]
        dernier = points[-1]["prix_moy"]
        variation = (dernier - premier) / premier * 100
        if variation > 10:
            tendance = "hausse"
        elif variation < -10:
            tendance = "baisse"

    return {
        "points":   points,
        "stats":    stats,
        "tendance": tendance
    }
