from app import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='agent') # admin, client, agent
    location = db.Column(db.String(100), nullable=True)
    wallet_balance = db.Column(db.Integer, default=0, nullable=False) # Portefeuille en FCFA
    
    submissions = db.relationship('Submission', backref='agent', lazy=True)
    
    @property
    def reliability_score(self):
        return 100


class Mission(db.Model):
    __tablename__ = 'missions'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False) # Rémunération en FCFA
    difficulty = db.Column(db.String(20), default='Standard')
    deadline = db.Column(db.DateTime, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    payment_status = db.Column(db.String(30), default='Pending_Payment') # Pending_Payment ou Paid

    submissions = db.relationship('Submission', backref='mission', lazy=True)


class Submission(db.Model):
    __tablename__ = 'submissions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mission_id = db.Column(db.Integer, db.ForeignKey('missions.id'), nullable=False)
    data_submitted = db.Column(db.Text, nullable=False) 
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mission_id = db.Column(db.Integer, db.ForeignKey('missions.id'), nullable=True)
    amount = db.Column(db.Integer, nullable=False) # Montant en FCFA
    transaction_type = db.Column(db.String(20), nullable=False) # 'gain' ou 'retrait'
    status = db.Column(db.String(20), default='Completed') # Completed, Pending
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

class CollecteData(db.Model):
    __tablename__ = 'collecte_data'  # Nom de la table en base de données
    
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    
    # Clé étrangère reliée à la table 'users' définie juste au-dessus
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)