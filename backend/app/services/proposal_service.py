"""Student-proposed problem statements: submission rules and mentor review."""
from app.extensions import db
from app.models import BatchMentor, Mentor, ProjectStudent, StudentProposal
from app.models.base import utcnow
from app.services import file_service
from app.services.notification_service import notify
from app.utils.errors import AppError

DECISIONS = {"approve": "approved", "reject": "rejected"}


def has_project(student):
    return db.session.query(ProjectStudent.id).filter_by(student_id=student.id).first() is not None


def upload_block_reason(student):
    """Why the student cannot upload right now (None = allowed). Drives the disabled state in the UI."""
    if has_project(student):
        return "A project has already been allocated to you, so you can no longer upload your own problem statement."
    open_ = (db.session.query(StudentProposal).filter(StudentProposal.student_id == student.id,
                                                      StudentProposal.status.in_(("pending", "approved"))).first())
    if open_:
        return ("Your problem statement is awaiting mentor approval." if open_.status == "pending"
                else "Your problem statement has already been approved.")
    return None


def submit(student, title, summary, file_storage, user):
    title = (title or "").strip()
    if not title:
        raise AppError("Title is required", 422, {"title": "Title is required"})
    if len(title) > 255:
        raise AppError("Title must be at most 255 characters", 422, {"title": "Too long"})
    reason = upload_block_reason(student)
    if reason:
        raise AppError(reason, 409)
    attachment = file_service.save_upload(file_storage, "problem_statement", user.id)
    proposal = StudentProposal(student_id=student.id, title=title, summary=(summary or "").strip()[:5000] or None,
                               file_id=attachment.id)
    db.session.add(proposal)
    db.session.flush()
    mentors = (db.session.query(Mentor.user_id).join(BatchMentor, BatchMentor.mentor_id == Mentor.id)
               .filter(BatchMentor.batch_id == student.batch_id, BatchMentor.is_active.is_(True)).all())
    notify({m[0] for m in mentors}, "proposal_submitted", "Problem statement awaiting approval",
           f"{student.user.name} submitted “{title}”.", "/mentor/proposals")
    return proposal


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
    notify({proposal.student.user_id}, "proposal_reviewed", f"Problem statement {proposal.status}",
           f"“{proposal.title}” was {proposal.status}." + (f" Remarks: {remarks}" if remarks else ""),
           "/student/proposal")
    return proposal


def withdraw_pending(student_ids):
    """A student who gets a project no longer needs an open proposal."""
    db.session.query(StudentProposal).filter(StudentProposal.student_id.in_(student_ids or [-1]),
                                             StudentProposal.status == "pending").update(
        {"status": "withdrawn", "remarks": "Withdrawn automatically: a project was allocated."})
