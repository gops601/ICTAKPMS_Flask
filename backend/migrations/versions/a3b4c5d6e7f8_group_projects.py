"""group projects: member roles on projects, group proposals

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-24 18:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('project_students', sa.Column('role', sa.String(length=60), nullable=True))
    op.add_column('student_proposals', sa.Column('is_group', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('student_proposals', sa.Column('group_members', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('student_proposals', 'group_members')
    op.drop_column('student_proposals', 'is_group')
    op.drop_column('project_students', 'role')
