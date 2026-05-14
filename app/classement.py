from datetime import datetime, timedelta

def calculer_classement(agents, collectes, periode_jours=30):
    """
    Calcule le classement des agents sur une période donnée.
    Score = collectes validées × points × bonus niveau
    """
    from .niveaux import NIVEAUX

    limite = datetime.utcnow() - timedelta(days=periode_jours)

    # Collectes récentes validées par agent
    stats = {}
    for c in collectes:
        if c.statut != "validee":
            continue
        # Parser date
        try:
            date_c = datetime.strptime(
                c.date_soumission, "%d/%m/%Y %H:%M")
        except:
            continue

        if date_c < limite:
            continue

        aid = c.agent_id
        if aid not in stats:
            stats[aid] = {
                "nb_collectes": 0,
                "nb_valides":   0,
                "nb_rejets":    0,
                "score":        0
            }
        stats[aid]["nb_collectes"] += 1
        stats[aid]["nb_valides"]   += 1

    # Ajouter les rejets
    for c in collectes:
        if c.statut in ["rejetee","fraude"]:
            aid = c.agent_id
            if aid in stats:
                stats[aid]["nb_rejets"] += 1

    # Construire le classement
    classement = []
    for agent in agents:
        s = stats.get(agent.id, {
            "nb_collectes":0,"nb_valides":0,
            "nb_rejets":0,"score":0
        })

        niveau_info = NIVEAUX.get(agent.niveau or "bronze")
        bonus_pct   = niveau_info["bonus_pct"] if niveau_info else 0

        # Score = valides × (100 + bonus%) - rejets × 20
        score = (s["nb_valides"] * (100 + bonus_pct)
                 - s["nb_rejets"] * 20)
        score = max(0, score)

        taux_succes = (
            round(s["nb_valides"] /
                  max(s["nb_collectes"],1) * 100)
            if s["nb_collectes"] > 0 else 0
        )

        classement.append({
            "rang":          0,
            "agent_id":      agent.id,
            "nom":           agent.nom,
            "telephone":     agent.telephone,
            "niveau":        agent.niveau or "bronze",
            "niveau_emoji":  niveau_info["emoji"] if niveau_info else "🥉",
            "nb_valides":    s["nb_valides"],
            "nb_rejets":     s["nb_rejets"],
            "taux_succes":   taux_succes,
            "score":         score,
            "solde_points":  agent.solde_points or 0,
            "gains_fcfa":    int((agent.solde_points or 0) * 1.5)
        })

    # Trier par score
    classement.sort(key=lambda x: x["score"], reverse=True)

    # Attribuer les rangs
    for i, item in enumerate(classement):
        item["rang"] = i + 1

    return classement
