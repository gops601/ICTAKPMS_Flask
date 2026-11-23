"""subdomains

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-23 19:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('subdomains',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('domain_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('domain_id', 'name', name='uq_subdomain_name')
    )
    with op.batch_alter_table('subdomains', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subdomains_domain_id'), ['domain_id'], unique=False)

    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subdomain_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_problem_statements_subdomain_id'), ['subdomain_id'], unique=False)
        batch_op.create_foreign_key('fk_problem_statements_subdomain', 'subdomains', ['subdomain_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_problem_statements_subdomain', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_problem_statements_subdomain_id'))
        batch_op.drop_column('subdomain_id')

    with op.batch_alter_table('subdomains', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subdomains_domain_id'))
    op.drop_table('subdomains')
