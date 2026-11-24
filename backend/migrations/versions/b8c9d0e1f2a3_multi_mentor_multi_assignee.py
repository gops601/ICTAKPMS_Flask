"""several mentors per project, several assignees per task

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-24 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('project_mentors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('mentor_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mentor_id'], ['mentors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'mentor_id', name='uq_project_mentor'))
    op.create_index('ix_project_mentors_project_id', 'project_mentors', ['project_id'])
    op.create_index('ix_project_mentors_mentor_id', 'project_mentors', ['mentor_id'])
    op.create_table('scrum_task_assignees',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['scrum_tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id', 'student_id', name='uq_task_assignee'))
    op.create_index('ix_scrum_task_assignees_task_id', 'scrum_task_assignees', ['task_id'])
    op.create_index('ix_scrum_task_assignees_student_id', 'scrum_task_assignees', ['student_id'])
    # carry over the single mentor / assignee that already exists
    op.execute("INSERT INTO project_mentors (project_id, mentor_id, created_at, updated_at) "
               "SELECT id, mentor_id, NOW(), NOW() FROM projects WHERE mentor_id IS NOT NULL")
    op.execute("INSERT INTO scrum_task_assignees (task_id, student_id, created_at, updated_at) "
               "SELECT id, assigned_student_id, NOW(), NOW() FROM scrum_tasks WHERE assigned_student_id IS NOT NULL")


def downgrade():
    op.drop_table('scrum_task_assignees')
    op.drop_table('project_mentors')
