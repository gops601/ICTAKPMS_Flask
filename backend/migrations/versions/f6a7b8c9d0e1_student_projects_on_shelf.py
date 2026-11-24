"""student projects with datasets on the project shelf

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-23 21:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proposed_by_student_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_problem_statements_proposed_by_student_id'), ['proposed_by_student_id'], unique=False)
        batch_op.create_foreign_key('fk_problem_statements_proposer', 'students', ['proposed_by_student_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('student_proposals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subdomain_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('problem_statement_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_student_proposals_subdomain', 'subdomains', ['subdomain_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_student_proposals_shelf', 'problem_statements', ['problem_statement_id'], ['id'], ondelete='SET NULL')

    op.create_table('proposal_datasets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('proposal_id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['file_attachments.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['proposal_id'], ['student_proposals.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('proposal_datasets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_proposal_datasets_proposal_id'), ['proposal_id'], unique=False)


def downgrade():
    with op.batch_alter_table('proposal_datasets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_proposal_datasets_proposal_id'))
    op.drop_table('proposal_datasets')

    with op.batch_alter_table('student_proposals', schema=None) as batch_op:
        batch_op.drop_constraint('fk_student_proposals_shelf', type_='foreignkey')
        batch_op.drop_constraint('fk_student_proposals_subdomain', type_='foreignkey')
        batch_op.drop_column('problem_statement_id')
        batch_op.drop_column('subdomain_id')

    with op.batch_alter_table('problem_statements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_problem_statements_proposer', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_problem_statements_proposed_by_student_id'))
        batch_op.drop_column('proposed_by_student_id')
