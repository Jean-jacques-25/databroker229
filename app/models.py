from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    telephone        = db.Column(db.String(20), unique=True, nullable=False)
    nom              = db.Column(db.String(100), nullable=False)
    email            = db.Column(db.String(150), nullable=True)
    role             = db.Column(db.String(20), default="agent")
    solde_points     = db.Column(db.Integer, default=0)
    date_inscription = db.Column(db.DateTime, default=datetime.utcnow)
    actif            = db.Column(db.Boolean, default=True)
    niveau           = db.Column(db.String(20), default="bronze")
# bronze | argent | or | platine
nb_collectes_total = db.Column(db.Integer, default=0)
nb_collectes_valides = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            "id":           self.id,
            "telephone":    self.telephone,
            "nom":          self.nom,
            "email":        self.email,
            "role":         self.role,
            "solde_points": self.solde_points
            "niveau":               self.niveau,
            "nb_collectes_total":   self.nb_collectes_total,
            "nb_collectes_valides": self.nb_collectes_valides,
        }

class Mission(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    titre               = db.Column(db.String(200), nullable=False)
    description         = db.Column(db.Text, nullable=False)
    marche_cible        = db.Column(db.String(100))
    marche_latitude     = db.Column(db.Float, nullable=True)
    marche_longitude    = db.Column(db.Float, nullable=True)
    produit_cible       = db.Column(db.String(100))
    nb_collectes_requis = db.Column(db.Integer, default=5)
    points_recompense   = db.Column(db.Integer, default=200)

    # Prix et marge
    prix_client_fcfa    = db.Column(db.Integer, default=0)
    marge_fcfa          = db.Column(db.Integer, default=0)
    budget_agents_fcfa  = db.Column(db.Integer, default=0)
    remuneration_agent  = db.Column(db.Integer, default=0)

    # Délai
    delai_heures        = db.Column(db.Integer, default=24)
    date_creation       = db.Column(db.DateTime, default=datetime.utcnow)
    date_echeance       = db.Column(db.DateTime, nullable=True)

    # Client
    client_nom          = db.Column(db.String(100))
    client_email        = db.Column(db.String(150))
    client_telephone    = db.Column(db.String(20))

    # Statut
    statut              = db.Column(db.String(30), default="en_attente_paiement")
    # en_attente_paiement | ouverte | prete | finalisee | echouee

    # Paiement Kkiapay
    paiement_reference  = db.Column(db.String(200), nullable=True)
    paiement_statut     = db.Column(db.String(30), default="non_paye")

    collectes = db.relationship("Collecte", backref="mission", lazy=True)

    def to_dict(self):
        return {
            "id":                  self.id,
            "titre":               self.titre,
            "description":         self.description,
            "marche_cible":        self.marche_cible,
            "produit_cible":       self.produit_cible,
            "nb_collectes_requis": self.nb_collectes_requis,
            "points_recompense":   self.points_recompense,
            "prix_client_fcfa":    self.prix_client_fcfa,
            "marge_fcfa":          self.marge_fcfa,
            "budget_agents_fcfa":  self.budget_agents_fcfa,
            "remuneration_agent":  self.remuneration_agent,
            "delai_heures":        self.delai_heures,
            "date_creation":       self.date_creation.strftime("%d/%m/%Y %H:%M"),
            "date_echeance":       self.date_echeance.strftime("%d/%m/%Y %H:%M") if self.date_echeance else None,
            "client_nom":          self.client_nom,
            "client_email":        self.client_email,
            "client_telephone":    self.client_telephone,
            "statut":              self.statut,
            "paiement_statut":     self.paiement_statut
        }

class Collecte(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    mission_id        = db.Column(db.Integer, db.ForeignKey("mission.id"), nullable=False)
    agent_id          = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    prix_observe      = db.Column(db.Float, nullable=True)
    disponibilite     = db.Column(db.Boolean, default=True)
    commentaire       = db.Column(db.Text)
    commentaire_admin = db.Column(db.Text, nullable=True)
    photo_url         = db.Column(db.String(300))
    latitude          = db.Column(db.Float)
    longitude         = db.Column(db.Float)
    distance_marche   = db.Column(db.Float, nullable=True)  # en km
    statut            = db.Column(db.String(20), default="en_attente")
    # en_attente | validee | rejetee | fraude
    agent_paye        = db.Column(db.Boolean, default=False)
    date_soumission   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":               self.id,
            "mission_id":       self.mission_id,
            "agent_id":         self.agent_id,
            "prix_observe":     self.prix_observe,
            "disponibilite":    self.disponibilite,
            "commentaire":      self.commentaire,
            "commentaire_admin":self.commentaire_admin,
            "photo_url":        self.photo_url,
            "latitude":         self.latitude,
            "longitude":        self.longitude,
            "distance_marche":  self.distance_marche,
            "statut":           self.statut,
            "agent_paye":       self.agent_paye,
            "date_soumission":  self.date_soumission.strftime("%d/%m/%Y %H:%M")
        }

class Transaction(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    agent_id       = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    mission_id     = db.Column(db.Integer, nullable=True)
    points_retires = db.Column(db.Integer, default=0)
    montant_fcfa   = db.Column(db.Integer, nullable=False)
    operateur      = db.Column(db.String(20))
    reference      = db.Column(db.String(100))
    type_trans     = db.Column(db.String(20), default="paiement_agent")
    statut         = db.Column(db.String(20), default="en_attente")
    date           = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":             self.id,
            "agent_id":       self.agent_id,
            "mission_id":     self.mission_id,
            "montant_fcfa":   self.montant_fcfa,
            "operateur":      self.operateur,
            "reference":      self.reference,
            "type_trans":     self.type_trans,
            "statut":         self.statut,
            "date":           self.date.strftime("%d/%m/%Y %H:%M")
        }

class Contact(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    nom         = db.Column(db.String(100), nullable=False)
    telephone   = db.Column(db.String(20), nullable=False)
    email       = db.Column(db.String(150), nullable=True)
    type_besoin = db.Column(db.String(100))
    marche      = db.Column(db.String(200))
    message     = db.Column(db.Text)
    traite      = db.Column(db.Boolean, default=False)
    date        = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":          self.id,
            "nom":         self.nom,
            "telephone":   self.telephone,
            "email":       self.email,
            "type_besoin": self.type_besoin,
            "marche":      self.marche,
            "message":     self.message,
            "traite":      self.traite,
            "date":        self.date.strftime("%d/%m/%Y %H:%M")
        }
