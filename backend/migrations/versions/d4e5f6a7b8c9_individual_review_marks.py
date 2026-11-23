"""individual student marks in reviews

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-23 17:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project_reviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('individual_max_marks', sa.Numeric(precision=6, scale=2), nullable=False, server_default='10'))

    with op.batch_alter_table('review_student_remarks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('marks_obtained', sa.Numeric(precision=6, scale=2), nullable=True))
        batch_op.alter_column('remarks', existing_type=sa.Text(), nullable=True)


def downgrade():
    with op.batch_alter_table('review_student_remarks', schema=None) as batch_op:
        batch_op.alter_column('remarks', existing_type=sa.Text(), nullable=False)
        batch_op.drop_column('marks_obtained')

    with op.batch_alter_table('project_reviews', schema=None) as batch_op:
        batch_op.drop_column('individual_max_marks')
