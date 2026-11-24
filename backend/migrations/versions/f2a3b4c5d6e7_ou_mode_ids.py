"""re-issue system IDs as <OU>_<MODE>_NNNN (batches, students, projects)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-24 17:00:00

Only IDs the system itself issued (the old ICT_... ones) are renamed; codes and registration numbers somebody typed in
are left alone. The numbers continue after the highest one already used for that OU + mode.
"""
import re

from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def _prefix(ou_code, mode):
    return f"{re.sub(r'[^A-Za-z0-9]', '', ou_code or '').upper() or 'OU'}_{(mode or 'online').upper()}_"


def _rename(conn, table, column, rows, old_prefix):
    """rows: [(id, current_value, ou_code, mode)] ordered by id. Renames those whose value starts with old_prefix."""
    taken = {}                                    # prefix -> highest number in use
    for _id, value, ou_code, mode in rows:
        p = _prefix(ou_code, mode)
        tail = (value or "")[len(p):] if (value or "").startswith(p) else ""
        if tail.isdigit():
            taken[p] = max(taken.get(p, 0), int(tail))
    for _id, value, ou_code, mode in rows:
        if not (value or "").startswith(old_prefix):
            continue
        p = _prefix(ou_code, mode)
        taken[p] = taken.get(p, 0) + 1
        conn.execute(table.update().where(table.c.id == _id).values({column: f"{p}{taken[p]:04d}"}))


def upgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:   # <OU>_<MODE>_NNNN can be longer than 30 characters
        batch_op.alter_column('code', existing_type=sa.String(length=30), type_=sa.String(length=60), existing_nullable=True)

    conn = op.get_bind()
    ous = sa.table('organisational_units', sa.column('id', sa.Integer), sa.column('code', sa.String))
    batches = sa.table('batches', sa.column('id', sa.Integer), sa.column('code', sa.String), sa.column('ou_id', sa.Integer),
                       sa.column('mode', sa.String))
    students = sa.table('students', sa.column('id', sa.Integer), sa.column('batch_id', sa.Integer), sa.column('registration_no', sa.String))
    projects = sa.table('projects', sa.column('id', sa.Integer), sa.column('batch_id', sa.Integer), sa.column('code', sa.String))

    ou_of = {r.id: r.code for r in conn.execute(sa.select(ous.c.id, ous.c.code))}
    batch_rows = list(conn.execute(sa.select(batches.c.id, batches.c.code, batches.c.ou_id, batches.c.mode).order_by(batches.c.id)))
    where = {b.id: (ou_of.get(b.ou_id), b.mode) for b in batch_rows}

    _rename(conn, batches, 'code', [(b.id, b.code, *where[b.id]) for b in batch_rows], 'ICT_')
    _rename(conn, students, 'registration_no',
            [(s.id, s.registration_no, *where.get(s.batch_id, (None, None)))
             for s in conn.execute(sa.select(students.c.id, students.c.batch_id, students.c.registration_no).order_by(students.c.id))], 'ICT_STU_')
    _rename(conn, projects, 'code',
            [(p.id, p.code, *where.get(p.batch_id, (None, None)))
             for p in conn.execute(sa.select(projects.c.id, projects.c.batch_id, projects.c.code).order_by(projects.c.id))], 'ICT_PRJ_')


def downgrade():
    # The old random IDs cannot be recovered; the renamed IDs stay and the wider column is harmless.
    pass
