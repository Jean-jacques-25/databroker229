"""Migration initiale - toutes les tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-06-29

"""
from alembic import op
import sqlalchemy as sa

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Table users
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fullname', sa.String(100), nullable=False),
        sa.Column('email', sa.String(120), nullable=False, unique=True),
        sa.Column('phone', sa.String(20), nullable=False, unique=True),
        sa.Column('password', sa.String(200), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='agent'),
        sa.Column('location', sa.String(100), nullable=True),
        sa.Column('wallet_balance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('organisation', sa.String(150), nullable=True),
        sa.Column('secteur', sa.String(100), nullable=True),
        sa.Column('nif_rccm', sa.String(80), nullable=True),
        sa.Column('logo_path', sa.String(300), nullable=True),
        sa.Column('niveau', sa.String(20), server_default='Débutant'),
        sa.Column('total_missions', sa.Integer(), server_default='0'),
        sa.Column('is_suspended', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Table missions
    op.create_table('missions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('difficulty', sa.String(20), server_default='Standard'),
        sa.Column('deadline', sa.DateTime(), nullable=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('organisation', sa.String(100), nullable=True),
        sa.Column('contact', sa.String(100), nullable=True),
        sa.Column('type_donnees', sa.String(50), nullable=True),
        sa.Column('zone', sa.String(50), nullable=True),
        sa.Column('quantite', sa.Integer(), server_default='1'),
        sa.Column('difficulte', sa.Integer(), server_default='500'),
        sa.Column('prix_agent', sa.Integer(), server_default='500'),
        sa.Column('format_livraison', sa.String(20), nullable=True),
        sa.Column('photos_requises', sa.String(5), server_default='non'),
        sa.Column('champs_requis', sa.String(300), server_default='nom_boutique,observations'),
        sa.Column('status', sa.String(20), server_default='En attente'),
        sa.Column('payment_status', sa.String(30), server_default='Pending_Payment'),
        sa.Column('is_suspended', sa.Boolean(), server_default='false'),
        sa.PrimaryKeyConstraint('id')
    )

    # Table submissions
    op.create_table('submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('data_submitted', sa.Text(), nullable=True),
        sa.Column('shop_name', sa.String(150), nullable=True),
        sa.Column('shop_phone', sa.String(30), nullable=True),
        sa.Column('shop_address', sa.String(200), nullable=True),
        sa.Column('observations', sa.Text(), nullable=True),
        sa.Column('photo_path', sa.String(300), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('motif_rejet', sa.String(300), nullable=True),
        sa.Column('status', sa.String(20), server_default='Pending'),
        sa.Column('submitted_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Table transactions
    op.create_table('transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), server_default='Completed'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Table retraits
    op.create_table('retraits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('montant', sa.Integer(), nullable=False),
        sa.Column('mode_paiement', sa.String(30), nullable=False),
        sa.Column('numero_mobile', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), server_default='En attente'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('montant_bloque', sa.Boolean(), server_default='true'),
        sa.PrimaryKeyConstraint('id')
    )

    # Table notifications
    op.create_table('notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message', sa.String(300), nullable=False),
        sa.Column('type', sa.String(30), server_default='info'),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Table collecte_data
    op.create_table('collecte_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(200), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date_creation', sa.DateTime(), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('collecte_data')
    op.drop_table('notifications')
    op.drop_table('retraits')
    op.drop_table('transactions')
    op.drop_table('submissions')
    op.drop_table('missions')
    op.drop_table('users')
