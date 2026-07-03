"""Add api_keys table

Revision ID: 002_api_keys
Revises: 001_initial
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = '002_api_keys'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('api_keys',
        sa.Column('id',         sa.Integer(),    nullable=False),
        sa.Column('client_id',  sa.Integer(),    nullable=False),
        sa.Column('key',        sa.String(64),   nullable=False, unique=True),
        sa.Column('label',      sa.String(100),  nullable=True),
        sa.Column('is_active',  sa.Boolean(),    server_default='true'),
        sa.Column('requests',   sa.Integer(),    server_default='0'),
        sa.Column('last_used',  sa.DateTime(),   nullable=True),
        sa.Column('created_at', sa.DateTime(),   server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['client_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('api_keys')
