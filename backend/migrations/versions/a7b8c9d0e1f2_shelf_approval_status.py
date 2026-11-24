"""project shelf approval status

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-23 23:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # existing entries are staff-created, i.e. already approved
    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approval_status', sa.String(length=20), nullable=False, server_default='approved'))
        batch_op.create_index(batch_op.f('ix_problem_statements_approval_status'), ['approval_status'], unique=False)


def downgrade():
    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_problem_statements_approval_status'))
        batch_op.drop_column('approval_status')
