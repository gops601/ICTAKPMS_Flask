"""batch mode: online (4 weeks) / offline (3 weeks)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-24 15:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    # every existing batch keeps its 4-week plan
    op.add_column('batches', sa.Column('mode', sa.String(length=10), nullable=False, server_default='online'))


def downgrade():
    op.drop_column('batches', 'mode')
