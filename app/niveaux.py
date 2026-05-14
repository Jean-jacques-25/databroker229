# ════════════════════════════════════════════════
# SYSTÈME DE NIVEAUX AGENTS
# ════════════════════════════════════════════════

NIVEAUX = {
    "bronze": {
        "nom":        "Bronze",
        "emoji":      "🥉",
        "couleur":    "#cd7f32",
        "min_valid":  0,
        "bonus_pct":  0,       # 0% de bonus
        "avantages":  "Accès aux missions standard"
    },
    "argent": {
        "nom":        "Argent",
        "emoji":      "🥈",
        "couleur":    "#a0aec0",
        "min_valid":  10,
        "bonus_pct":  10,      # +10% sur chaque collecte
        "avantages":  "Missions premium + bonus 10%"
    },
    "or": {
        "nom":        "Or",
        "emoji":      "🥇",
        "couleur":    "#ffd700",
        "min_valid":  30,
        "bonus_pct":  20,      # +20% sur chaque collecte
        "avantages":  "Toutes missions + bonus 20% + priorité"
    },
    "platine": {
        "nom":        "Platine",
        "emoji":      "💎",
        "couleur":    "#553c9a",
        "min_valid":  100,
        "bonus_pct":  35,      # +35% sur chaque collecte
        "avantages":  "Accès exclusif missions urgentes + bonus 35%"
    }
}

def calculer_niveau(nb_valides):
    """Retourne le niveau selon le nombre de collectes validées"""
    if nb_valides >= 100:
        return "platine"
    elif nb_valides >= 30:
        return "or"
    elif nb_valides >= 10:
        return "argent"
    return "bronze"

def calculer_bonus(remuneration_base, niveau):
    """Calcule la rémunération avec bonus selon le niveau"""
    bonus_pct = NIVEAUX.get(niveau, NIVEAUX["bronze"])["bonus_pct"]
    bonus     = int(remuneration_base * bonus_pct / 100)
    return remuneration_base + bonus, bonus

def progression_vers_suivant(nb_valides):
    """Retourne la progression vers le niveau suivant"""
    paliers = [0, 10, 30, 100]
    noms    = ["bronze","argent","or","platine"]

    for i, palier in enumerate(paliers):
        if nb_valides < palier:
            precedent = paliers[i-1]
            progression = nb_valides - precedent
            restant     = palier - nb_valides
            total       = palier - precedent
            pct         = int(progression / total * 100)
            return {
                "niveau_actuel":  noms[i-1],
                "niveau_suivant": noms[i],
                "emoji_suivant":  NIVEAUX[noms[i]]["emoji"],
                "progression":    progression,
                "restant":        restant,
                "total":          total,
                "pct":            pct
            }

    # Déjà platine
    return {
        "niveau_actuel":  "platine",
        "niveau_suivant": None,
        "pct":            100,
        "restant":        0
    }

def mettre_a_jour_niveau(agent):
    """Met à jour le niveau d'un agent après une collecte validée"""
    agent.nb_collectes_valides = (agent.nb_collectes_valides or 0) + 1
    agent.nb_collectes_total   = (agent.nb_collectes_total   or 0) + 1
    nouveau_niveau = calculer_niveau(agent.nb_collectes_valides)

    niveau_monte = nouveau_niveau != agent.niveau
    agent.niveau = nouveau_niveau

    return niveau_monte, nouveau_niveau
