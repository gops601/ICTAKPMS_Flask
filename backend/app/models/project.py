from app.extensions import db
from .base import TimestampMixin


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True)  # system-generated, ICT_PRJ_XXXXXX
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    problem_statement_id = db.Column(db.Integer, db.ForeignKey("problem_statements.id", ondelete="RESTRICT"),
                                     nullable=False, index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id", ondelete="SET NULL"), index=True)  # optional override
    title = db.Column(db.String(255))
    stage = db.Column(db.String(30), default="allocated", nullable=False, index=True)
    start_date = db.Column(db.Date)
    target_end_date = db.Column(db.Date)
    implementation_started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    mentor_can_edit_board = db.Column(db.Boolean, default=False, nullable=False)
    final_remarks = db.Column(db.Text)
    final_signed_off_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    closed_at = db.Column(db.DateTime)  # a completed project is closed by its domain lead; reopening clears this
    closed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    batch = db.relationship("Batch")
    problem_statement = db.relationship("ProblemStatement")
    mentor = db.relationship("Mentor")
    members = db.relationship("ProjectStudent", back_populates="project", cascade="all, delete-orphan")


class ProjectStudent(TimestampMixin, db.Model):
    __tablename__ = "project_students"
    __table_args__ = (db.UniqueConstraint("project_id", "student_id", name="uq_project_student"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    is_lead = db.Column(db.Boolean, default=False, nullable=False)

    project = db.relationship("Project", back_populates="members")
    student = db.relationship("Student")


class ProjectMentor(TimestampMixin, db.Model):
    """A mentor explicitly assigned to a project. Several may be assigned; Project.mentor_id mirrors the first."""
    __tablename__ = "project_mentors"
    __table_args__ = (db.UniqueConstraint("project_id", "mentor_id", name="uq_project_mentor"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id", ondelete="CASCADE"), nullable=False, index=True)


class ProjectAssignment(TimestampMixin, db.Model):
    """History of allocations / mentor reassignments for a project."""
    __tablename__ = "project_assignments"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_type = db.Column(db.String(30), nullable=False)  # allocation | mentor_assignment | reassignment
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id", ondelete="SET NULL"))
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    notes = db.Column(db.String(500))


class SrsSubmission(TimestampMixin, db.Model):
    __tablename__ = "srs_submissions"
    __table_args__ = (db.UniqueConstraint("project_id", "version", name="uq_srs_version"),)
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey("file_attachments.id", ondelete="RESTRICT"), nullable=False)
    description = db.Column(db.Text)
    # submitted | under_review | changes_requested | approved | rejected
    status = db.Column(db.String(30), default="submitted", nullable=False)
    submitted_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at = db.Column(db.DateTime)

    file = db.relationship("FileAttachment")
    history = db.relationship("SrsReviewHistory", back_populates="submission", cascade="all, delete-orphan")


class SrsReviewHistory(TimestampMixin, db.Model):
    __tablename__ = "srs_review_history"
    id = db.Column(db.Integer, primary_key=True)
    srs_submission_id = db.Column(db.Integer, db.ForeignKey("srs_submissions.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    decision = db.Column(db.String(30), nullable=False)
    remarks = db.Column(db.Text)

    submission = db.relationship("SrsSubmission", back_populates="history")
    reviewer = db.relationship("User")


class ProjectGithubRepository(TimestampMixin, db.Model):
    __tablename__ = "project_github_repositories"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)
    url = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))


class ProjectLifecycleTransition(db.Model):
    __tablename__ = "project_lifecycle_transitions"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage = db.Column(db.String(30))
    to_stage = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reason = db.Column(db.String(500))
    is_reopen = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)


class ProjectActivityLog(db.Model):
    __tablename__ = "project_activity_logs"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, index=True)


class MentorFeedback(TimestampMixin, db.Model):
    """Feedback from a mentor to one student of a project, or to the whole team (student_id NULL)."""
    __tablename__ = "mentor_feedback"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    message = db.Column(db.Text, nullable=False)

    author = db.relationship("User")
    student = db.relationship("Student")
