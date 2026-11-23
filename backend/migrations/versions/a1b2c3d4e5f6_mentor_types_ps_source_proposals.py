"""mentor types, problem statement source/industry, student proposals

Revision ID: a1b2c3d4e5f6
Revises: c12a80f8359a
Create Date: 2026-11-23 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'c12a80f8359a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('mentors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mentor_type', sa.String(length=20), nullable=False, server_default='internal'))
        batch_op.add_column(sa.Column('company', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('industry_sector', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('experience_years', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('linkedin_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('bio', sa.Text(), nullable=True))

    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_type', sa.String(length=20), nullable=False, server_default='internal'))
        batch_op.add_column(sa.Column('industry', sa.String(length=120), nullable=True))
        batch_op.create_index(batch_op.f('ix_problem_statements_source_type'), ['source_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_problem_statements_industry'), ['industry'], unique=False)

    op.create_table('student_proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reviewed_by', sa.Integer(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['file_attachments.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('student_proposals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_student_proposals_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_student_proposals_status'), ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('student_proposals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_student_proposals_status'))
        batch_op.drop_index(batch_op.f('ix_student_proposals_student_id'))
    op.drop_table('student_proposals')

    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_problem_statements_industry'))
        batch_op.drop_index(batch_op.f('ix_problem_statements_source_type'))
        batch_op.drop_column('industry')
        batch_op.drop_column('source_type')

    with op.batch_alter_table('mentors', schema=None) as batch_op:
        for c in ('bio', 'linkedin_url', 'experience_years', 'industry_sector', 'company', 'mentor_type'):
            batch_op.drop_column(c)
