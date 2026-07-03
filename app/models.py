from app import db
from datetime import datetime


class User(db.Model):
    __tablename__ = 'users'

    id             = db.Column(db.Integer, primary_key=True)
    fullname       = db.Column(db.String(100), nullable=False)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    phone          = db.Column(db.String(20),  unique=True, nullable=False)
    password       = db.Column(db.String(200), nullable=False)
    role           = db.Column(db.String(20),  nullable=False, default='agent')
    location       = db.Column(db.String(100), nullable=True)
    wallet_balance = db.Column(db.Integer, default=0, nullable=False)

    # Profil entreprise (client)
    organisation   = db.Column(db.String(150), nullable=True)
    secteur        = db.Column(db.String(100), nullable=True)
    nif_rccm       = db.Column(db.String(80),  nullable=True)
    logo_path      = db.Column(db.String(300), nullable=True)

    # Profil agent
    niveau         = db.Column(db.String(20), default='Débutant')  # Débutant, Standard, Expert, Pro
    total_missions = db.Column(db.Integer, default=0)
    is_suspended   = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    submissions    = db.relationship('Submission', backref='agent', lazy=True)
    notifications  = db.relationship('Notification', backref='user', lazy=True)
    retraits       = db.relationship('Retrait', backref='agent', lazy=True)

    @property
    def reliability_score(self):
        total = len(self.submissions)
        if total == 0:
            return 100
        approved = sum(1 for s in self.submissions if s.status == 'Approved')
        return round((approved / total) * 100)

    @property
    def niveau_badge(self):
        score = self.reliability_score
        total = self.total_missions
        if total >= 50 and score >= 90:
            return ('Pro', '🏆', '#f59e0b')
        elif total >= 20 and score >= 80:
            return ('Expert', '⭐', '#10b981')
        elif total >= 5:
            return ('Standard', '🔵', '#3b82f6')
        else:
            return ('Débutant', '🌱', '#6b7280')


class Mission(db.Model):
    __tablename__ = 'missions'

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(150), nullable=False)
    description      = db.Column(db.Text, nullable=False)
    instructions     = db.Column(db.Text, nullable=True)
    price            = db.Column(db.Integer, nullable=False)
    difficulty       = db.Column(db.String(20), default='Standard')
    deadline         = db.Column(db.DateTime, nullable=True)
    client_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    organisation     = db.Column(db.String(100))
    contact          = db.Column(db.String(100))
    type_donnees     = db.Column(db.String(50))
    zone             = db.Column(db.String(50))
    quantite         = db.Column(db.Integer, default=1)
    difficulte       = db.Column(db.Integer, default=500)
    prix_agent       = db.Column(db.Integer, default=500)  # gain net par collecte pour l'agent
    format_livraison = db.Column(db.String(20))
    photos_requises  = db.Column(db.String(5), default='non')
    champs_requis    = db.Column(db.String(300), default='nom_boutique,observations')

    status           = db.Column(db.String(20), default='En attente')
    payment_status   = db.Column(db.String(30), default='Pending_Payment')
    is_suspended     = db.Column(db.Boolean, default=False)

    submissions      = db.relationship('Submission', backref='mission', lazy=True)
    client           = db.relationship('User', foreign_keys=[client_id], backref='missions')

    @property
    def progression(self):
        if not self.quantite or self.quantite == 0:
            return 0
        approved = sum(1 for s in self.submissions if s.status == 'Approved')
        return min(100, round((approved / self.quantite) * 100))

    @property
    def points_collectes(self):
        return sum(1 for s in self.submissions if s.status == 'Approved')


class Submission(db.Model):
    __tablename__ = 'submissions'

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mission_id     = db.Column(db.Integer, db.ForeignKey('missions.id'), nullable=False)

    data_submitted = db.Column(db.Text,        nullable=True)
    shop_name      = db.Column(db.String(150), nullable=True)
    shop_phone     = db.Column(db.String(30),  nullable=True)
    shop_address   = db.Column(db.String(200), nullable=True)
    observations   = db.Column(db.Text,        nullable=True)
    photo_path     = db.Column(db.String(300), nullable=True)
    latitude       = db.Column(db.Float,       nullable=True)
    longitude      = db.Column(db.Float,       nullable=True)
    motif_rejet    = db.Column(db.String(300), nullable=True)

    status         = db.Column(db.String(20), default='Pending')
    submitted_at   = db.Column(db.DateTime,   default=datetime.utcnow)


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mission_id       = db.Column(db.Integer, db.ForeignKey('missions.id'), nullable=True)
    amount           = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    status           = db.Column(db.String(20), default='Completed')
    created_at       = db.Column(db.DateTime,   default=datetime.utcnow)

    user    = db.relationship('User',    backref=db.backref('transactions', lazy=True))
    mission = db.relationship('Mission', backref=db.backref('transactions', lazy=True))


class Retrait(db.Model):
    __tablename__ = 'retraits'

    id            = db.Column(db.Integer, primary_key=True)
    agent_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    montant       = db.Column(db.Integer, nullable=False)
    mode_paiement = db.Column(db.String(30), nullable=False)
    numero_mobile = db.Column(db.String(20), nullable=False)
    status        = db.Column(db.String(20), default='En attente')  # En attente, Payé, Rejeté
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at       = db.Column(db.DateTime, nullable=True)
    # L'argent reste bloqué dans le portefeuille jusqu'à confirmation admin
    montant_bloque = db.Column(db.Boolean, default=True)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.String(300), nullable=False)
    type       = db.Column(db.String(30), default='info')  # info, success, warning
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CollecteData(db.Model):
    __tablename__ = 'collecte_data'

    id            = db.Column(db.Integer, primary_key=True)
    description   = db.Column(db.String(200), nullable=False)
    latitude      = db.Column(db.Float, nullable=False)
    longitude     = db.Column(db.Float, nullable=False)
    agent_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)



class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id         = db.Column(db.Integer, primary_key=True)
    client_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    key        = db.Column(db.String(64), unique=True, nullable=False)
    label      = db.Column(db.String(100), default='Cle API')
    is_active  = db.Column(db.Boolean, default=True)
    requests   = db.Column(db.Integer, default=0)
    last_used  = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('User', backref=db.backref('api_keys', lazy=True))
