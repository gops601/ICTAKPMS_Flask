"""data collection sheet, external portals (SSO / enrolment)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-24 12:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('student_proposals', sa.Column('data_collection', sa.JSON(), nullable=True))
    op.add_column('problem_statements', sa.Column('data_collection', sa.JSON(), nullable=True))
    op.create_table('external_portals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('slug', sa.String(length=60), nullable=False),
        sa.Column('base_url', sa.String(length=255), nullable=True),
        sa.Column('enrollment_path', sa.String(length=255), nullable=True),
        sa.Column('api_token', sa.String(length=255), nullable=True),
        sa.Column('shared_secret', sa.String(length=128), nullable=False),
        sa.Column('default_ou_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_summary', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['default_ou_id'], ['organisational_units.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'))
    op.add_column('batches', sa.Column('external_portal_id', sa.Integer(), nullable=True))
    op.add_column('batches', sa.Column('external_ref', sa.String(length=100), nullable=True))
    op.create_index('ix_batches_external_portal_id', 'batches', ['external_portal_id'])
    op.create_foreign_key('fk_batches_external_portal', 'batches', 'external_portals', ['external_portal_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_batches_external_portal', 'batches', type_='foreignkey')
    op.drop_index('ix_batches_external_portal_id', table_name='batches')
    op.drop_column('batches', 'external_ref')
    op.drop_column('batches', 'external_portal_id')
    op.drop_table('external_portals')
    op.drop_column('problem_statements', 'data_collection')
    op.drop_column('student_proposals', 'data_collection')
