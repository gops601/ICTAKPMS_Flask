"""batch subdomain

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-24 12:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('batches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subdomain_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_batches_subdomain_id'), ['subdomain_id'], unique=False)
        batch_op.create_foreign_key('fk_batches_subdomain', 'subdomains', ['subdomain_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('batches', schema=None) as batch_op:
        batch_op.drop_constraint('fk_batches_subdomain', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_batches_subdomain_id'))
        batch_op.drop_column('subdomain_id')
