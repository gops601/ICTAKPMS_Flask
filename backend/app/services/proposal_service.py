"""Student-proposed projects.

Flow: the student's problem details go onto the Project Shelf immediately (marked *pending*). A mentor of the batch
approves or rejects. Approval makes the shelf entry allocatable and starts the student's project with that mentor, which
is what unlocks SRS submission. Rejection marks the entry rejected and inactive.
"""
from html import escape

from app.extensions import db
from app.models import (BatchMentor, Mentor, ProblemStatement, ProblemStatementDataset, ProblemStatementDocument,
                        ProjectStudent, ProposalDataset, StudentProposal, Subdomain)
from app.models.base import utcnow
from app.services import data_collection, file_service, problem_service
from app.services.notification_service import domain_lead_user_ids, notify
from app.utils.errors import AppError

DECISIONS = {"approve": "approved", "reject": "rejected"}
MAX_DATASETS = 10


def has_project(student):
    return db.session.query(ProjectStudent.id).filter_by(student_id=student.id).first() is not None


def upload_block_reason(student):
    """Why the student cannot upload right now (None = allowed). Drives the disabled state in the UI."""
    if has_project(student):
        return "A project has already been allocated to you, so you can no longer upload your own project."
    open_ = (db.session.query(StudentProposal).filter(StudentProposal.student_id == student.id,
                                                      StudentProposal.status.in_(("pending", "approved"))).first())
    if open_:
        return ("Your project is on the Project Shelf and awaiting mentor approval. The SRS opens once it is approved."
                if open_.status == "pending" else "Your project has already been approved.")
    return None


def _clean_subdomain(student, subdomain_id):
    """The project lands in the student's batch domain; pick one of its subdomains when it has any."""
    domain = student.batch.domain
    if not domain:
        raise AppError("Your batch has no domain yet, so a project cannot be uploaded.", 409)
    sub = db.session.get(Subdomain, subdomain_id) if subdomain_id else None
    if subdomain_id and (not sub or sub.domain_id != domain.id or not sub.is_active):
        raise AppError("Choose a subdomain of your batch's domain", 422, {"subdomain_id": "Invalid subdomain"})
    if not sub and any(s.is_active for s in domain.subdomains):
        raise AppError(f"Choose a subdomain of {domain.name}", 422, {"subdomain_id": "Subdomain is required"})
    return sub


def submit(student, title, summary, file_storage, user, dataset_files=None, subdomain_id=None, data_sheet=None):
    title = (title or "").strip()
    if not title:
        raise AppError("Title is required", 422, {"title": "Title is required"})
    if len(title) > 255:
        raise AppError("Title must be at most 255 characters", 422, {"title": "Too long"})
    reason = upload_block_reason(student)
    if reason:
        raise AppError(reason, 409)
    sub = _clean_subdomain(student, subdomain_id)
    dataset_files = [f for f in (dataset_files or []) if f and f.filename]
    if len(dataset_files) > MAX_DATASETS:
        raise AppError(f"At most {MAX_DATASETS} datasets per project", 422, {"datasets": "Too many files"})
    has_sheet = bool(data_sheet and data_sheet.filename)
    if dataset_files and not has_sheet:
        raise AppError("Describe your datasets in the data collection sheet (download the Excel template) and upload it with them.", 422,
                       {"data_sheet": "Required when you upload datasets"})
    rows = data_collection.parse(data_sheet) if has_sheet else None
    attachment = file_service.save_upload(file_storage, "problem_statement", user.id)
    proposal = StudentProposal(data_collection=rows, student_id=student.id, title=title, summary=(summary or "").strip()[:5000] or None,
                               file_id=attachment.id, subdomain_id=sub.id if sub else None)
    db.session.add(proposal)
    db.session.flush()
    datasets = []
    for f in dataset_files:
        ds = file_service.save_upload(f, "dataset", user.id)
        db.session.add(ProposalDataset(proposal_id=proposal.id, file_id=ds.id))
        datasets.append(ds)
    if has_sheet:                                   # keep the filled sheet itself next to the datasets
        sheet = file_service.save_upload(data_sheet, "dataset", user.id)
        db.session.add(ProposalDataset(proposal_id=proposal.id, file_id=sheet.id, description="Data collection sheet"))
        datasets.append(sheet)
    db.session.flush()
    ps = add_to_shelf(proposal, student, attachment, datasets, user)
    mentors = (db.session.query(Mentor.user_id).join(BatchMentor, BatchMentor.mentor_id == Mentor.id)
               .filter(BatchMentor.batch_id == student.batch_id, BatchMentor.is_active.is_(True)).all())
    notify({m[0] for m in mentors}, "proposal_submitted", "Student project awaiting approval",
           f"{student.user.name} submitted “{title}” ({ps.ps_code}). Approve it so they can start the SRS.",
           "/mentor/proposals")
    notify(domain_lead_user_ids(ps.domain_id), "shelf_student_project", "Student project added to the Project Shelf",
           f"“{ps.title}” ({ps.ps_code}) by {student.user.name} is on your shelf, awaiting mentor approval.",
           f"/lead/project-shelf/{ps.id}")
    return proposal


def add_to_shelf(proposal, student, document, datasets, user):
    """The student's problem details go onto the Project Shelf straight away, marked pending until a mentor approves."""
    body = proposal.summary or proposal.title
    ps = ProblemStatement(
        ps_code=problem_service.new_ps_code(), title=proposal.title, domain_id=student.batch.domain_id,
        subdomain_id=proposal.subdomain_id, description=problem_service.sanitize_html(f"<p>{escape(body)}</p>"),
        difficulty="medium", status="active", approval_status="pending", source_type="internal", created_by=user.id,
        proposed_by_student_id=student.id, data_collection=proposal.data_collection)
    db.session.add(ps)
    db.session.flush()
    db.session.add(ProblemStatementDocument(problem_statement_id=ps.id, file_id=document.id,
                                            description=f"Detailed project document by {student.user.name}"))
    for ds in datasets:
        db.session.add(ProblemStatementDataset(problem_statement_id=ps.id, file_id=ds.id))
    proposal.problem_statement_id = ps.id
    db.session.flush()
    return ps


def review(proposal, decision, remarks, user):
    if decision not in DECISIONS:
        raise AppError("decision must be approve or reject", 422)
    if proposal.status != "pending":
        raise AppError(f"This proposal was already {proposal.status}", 409)
    remarks = (remarks or "").strip() or None
    if decision == "reject" and not remarks:
        raise AppError("Remarks are required when rejecting", 422, {"remarks": "Tell the student why"})
    proposal.status, proposal.remarks = DECISIONS[decision], remarks
    proposal.reviewed_by, proposal.reviewed_at = user.id, utcnow()
    ps = proposal.problem_statement
    extra = ""
    if proposal.status == "approved":
        ps.approval_status = "approved"
        project = _start_project(proposal, ps, user)
        extra = f" It is on the Project Shelf as {ps.ps_code} and your project has started – you can now begin the SRS."
        notify(domain_lead_user_ids(ps.domain_id), "shelf_student_project", "Student project approved",
               f"“{ps.title}” ({ps.ps_code}) was approved and allocated to {proposal.student.user.name}.",
               f"/projects/{project.id}")
    else:
        ps.approval_status, ps.status = "rejected", "inactive"
    notify({proposal.student.user_id}, "proposal_reviewed", f"Project {proposal.status}",
           f"“{proposal.title}” was {proposal.status}." + extra + (f" Remarks: {remarks}" if remarks else ""),
           "/student/project" if proposal.status == "approved" else "/student/proposal")
    return proposal


def _start_project(proposal, ps, mentor_user):
    """Mentor approval = allocation: the student's own problem becomes their project, with the approving mentor."""
    from app.services import project_service  # local import: project_service imports this module
    student = proposal.student
    mentor = db.session.query(Mentor).filter_by(user_id=mentor_user.id).first()
    projects = project_service.allocate(
        student.batch, [{"problem_statement_id": ps.id, "student_ids": [student.id], "team": False}], mentor_user,
        mentor_id=mentor.id if mentor else None)
    return projects[0]


def withdraw_pending(student_ids):
    """A student who gets a project some other way no longer needs an open proposal (and its pending shelf entry)."""
    pending = db.session.query(StudentProposal).filter(StudentProposal.student_id.in_(student_ids or [-1]),
                                                       StudentProposal.status == "pending").all()
    for p in pending:
        p.status, p.remarks = "withdrawn", "Withdrawn automatically: a project was allocated."
        if p.problem_statement and p.problem_statement.approval_status == "pending":
            p.problem_statement.approval_status, p.problem_statement.status = "withdrawn", "inactive"
