"""project ICT_ codes, project close, mentor feedback

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-23 15:00:00

"""
import secrets

from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"


def _token():
    while True:
        t = "".join(secrets.choice(_LETTERS + _DIGITS) for _ in range(6))
        if any(c in _LETTERS for c in t) and any(c in _DIGITS for c in t):
            return t


def upgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('code', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('closed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('closed_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_projects_closed_by_users', 'users', ['closed_by'], ['id'], ondelete='SET NULL')

    # existing projects get an ICT_PRJ_ code too
    conn = op.get_bind()
    projects = sa.table('projects', sa.column('id', sa.Integer), sa.column('code', sa.String))
    used = set()
    for (pid,) in conn.execute(sa.select(projects.c.id)).fetchall():
        code = f"ICT_PRJ_{_token()}"
        while code in used:
            code = f"ICT_PRJ_{_token()}"
        used.add(code)
        conn.execute(projects.update().where(projects.c.id == pid).values(code=code))

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_code'), ['code'], unique=True)

    op.create_table('mentor_feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mentor_feedback', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mentor_feedback_project_id'), ['project_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mentor_feedback_student_id'), ['student_id'], unique=False)


def downgrade():
    with op.batch_alter_table('mentor_feedback', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mentor_feedback_student_id'))
        batch_op.drop_index(batch_op.f('ix_mentor_feedback_project_id'))
    op.drop_table('mentor_feedback')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_code'))
        batch_op.drop_constraint('fk_projects_closed_by_users', type_='foreignkey')
        batch_op.drop_column('closed_by')
        batch_op.drop_column('closed_at')
        batch_op.drop_column('code')
