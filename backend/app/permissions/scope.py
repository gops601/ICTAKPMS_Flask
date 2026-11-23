"""Data-scope guards.

Every route that touches a batch / domain / project must go through these helpers so that a
user cannot reach another domain's, batch's or student's data by editing an ID in the URL.
Query helpers return filtered selects; `can_*` helpers return booleans; `ensure_*` raise 404
(not 403) so resource existence is not leaked.
"""
from app.extensions import db
from app.models import (Batch, BatchMentor, DomainLead, Mentor, Project, ProjectStudent, Student)
from app.models.user import ROLE_ADMIN, ROLE_DOMAIN_LEAD, ROLE_MENTOR, ROLE_STUDENT
from app.utils.errors import NotFound


def lead_domain_ids(user):
    rows = db.session.query(DomainLead.domain_id).filter_by(user_id=user.id).all()
    return {r[0] for r in rows}


def mentor_profile(user):
    return db.session.query(Mentor).filter_by(user_id=user.id).first()


def student_profile(user):
    return db.session.query(Student).filter_by(user_id=user.id).first()


def mentor_batch_ids(user):
    m = mentor_profile(user)
    if not m:
        return set()
    rows = db.session.query(BatchMentor.batch_id).filter_by(mentor_id=m.id, is_active=True).all()
    return {r[0] for r in rows}


def can_access_domain(user, domain_id):
    if user.role_name == ROLE_ADMIN:
        return True
    if user.role_name == ROLE_DOMAIN_LEAD:
        return domain_id in lead_domain_ids(user)
    return False


def can_access_batch(user, batch):
    role = user.role_name
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_DOMAIN_LEAD:
        return batch.domain_id in lead_domain_ids(user)
    if role == ROLE_MENTOR:
        return batch.id in mentor_batch_ids(user)
    if role == ROLE_STUDENT:
        s = student_profile(user)
        return bool(s and s.batch_id == batch.id)
    return False


def can_access_project(user, project):
    role = user.role_name
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_DOMAIN_LEAD:
        return project.batch.domain_id in lead_domain_ids(user)
    if role == ROLE_MENTOR:
        m = mentor_profile(user)
        return bool(m and (project.mentor_id == m.id or project.batch_id in mentor_batch_ids(user)))
    if role == ROLE_STUDENT:
        s = student_profile(user)
        return bool(s and db.session.query(ProjectStudent).filter_by(
            project_id=project.id, student_id=s.id).first())
    return False


def scoped_batches(user):
    q = db.select(Batch)
    role = user.role_name
    if role == ROLE_ADMIN:
        return q
    if role == ROLE_DOMAIN_LEAD:
        return q.where(Batch.domain_id.in_(lead_domain_ids(user) or {-1}))
    if role == ROLE_MENTOR:
        return q.where(Batch.id.in_(mentor_batch_ids(user) or {-1}))
    s = student_profile(user)
    return q.where(Batch.id == (s.batch_id if s else -1))


def scoped_projects(user):
    q = db.select(Project)
    role = user.role_name
    if role == ROLE_ADMIN:
        return q
    if role == ROLE_DOMAIN_LEAD:
        return q.join(Batch, Batch.id == Project.batch_id).where(
            Batch.domain_id.in_(lead_domain_ids(user) or {-1}))
    if role == ROLE_MENTOR:
        m = mentor_profile(user)
        return q.where(db.or_(Project.mentor_id == (m.id if m else -1),
                              Project.batch_id.in_(mentor_batch_ids(user) or {-1})))
    s = student_profile(user)
    return q.join(ProjectStudent, ProjectStudent.project_id == Project.id).where(
        ProjectStudent.student_id == (s.id if s else -1))


def ensure_batch_access(user, batch_id):
    batch = db.session.get(Batch, batch_id)
    if not batch or not can_access_batch(user, batch):
        raise NotFound("Batch not found")
    return batch


def ensure_project_access(user, project_id):
    project = db.session.get(Project, project_id)
    if not project or not can_access_project(user, project):
        raise NotFound("Project not found")
    return project


def can_view_problem_statement(user, ps):
    """Admin / lead of the statement's domain, or anyone with a project that uses it."""
    if can_access_domain(user, ps.domain_id):
        return True
    q = scoped_projects(user).where(Project.problem_statement_id == ps.id).limit(1)
    return db.session.scalar(q) is not None
