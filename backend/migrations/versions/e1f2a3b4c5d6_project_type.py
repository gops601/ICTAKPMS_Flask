"""project type for Academic OU projects (add-on course / summer internship / other)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-24 16:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    # nullable: only projects in Academic OU batches carry a type
    op.add_column('projects', sa.Column('project_type', sa.String(length=30), nullable=True))
    op.create_index('ix_projects_project_type', 'projects', ['project_type'])


def downgrade():
    op.drop_index('ix_projects_project_type', table_name='projects')
    op.drop_column('projects', 'project_type')
