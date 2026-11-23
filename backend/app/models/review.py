from app.extensions import db
from .base import TimestampMixin


class EvaluationTemplate(TimestampMixin, db.Model):
    """Reusable criteria set a mentor can clone into a review."""
    __tablename__ = "evaluation_templates"
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    week_no = db.Column(db.Integer)
    criteria = db.Column(db.JSON, nullable=False)  # [{"name": ..., "max_marks": ...}]


class ProjectReview(TimestampMixin, db.Model):
    __tablename__ = "project_reviews"
    __table_args__ = (db.UniqueConstraint("project_id", "week_no", name="uq_review_week"),
                      db.CheckConstraint("week_no BETWEEN 1 AND 4", name="ck_week_range"))
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    week_no = db.Column(db.Integer, nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id", ondelete="SET NULL"))
    due_date = db.Column(db.Date, index=True)
    review_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending|draft|submitted|reopened
    remarks = db.Column(db.Text)
    strengths = db.Column(db.Text)
    improvements = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime)
    version = db.Column(db.Integer, default=1, nullable=False)  # optimistic concurrency

    criteria = db.relationship("EvaluationCriterion", back_populates="review", cascade="all, delete-orphan",
                               order_by="EvaluationCriterion.display_order")
    revisions = db.relationship("EvaluationRevision", back_populates="review", cascade="all, delete-orphan")
    student_remarks = db.relationship("ReviewStudentRemark", back_populates="review", cascade="all, delete-orphan")
    date_requests = db.relationship("ReviewDateRequest", back_populates="review", cascade="all, delete-orphan")


class EvaluationCriterion(TimestampMixin, db.Model):
    __tablename__ = "evaluation_criteria"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("project_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    max_marks = db.Column(db.Numeric(6, 2), nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    review = db.relationship("ProjectReview", back_populates="criteria")
    score = db.relationship("EvaluationScore", back_populates="criterion", uselist=False,
                            cascade="all, delete-orphan")


class EvaluationScore(TimestampMixin, db.Model):
    __tablename__ = "evaluation_scores"
    id = db.Column(db.Integer, primary_key=True)
    criterion_id = db.Column(db.Integer, db.ForeignKey("evaluation_criteria.id", ondelete="CASCADE"),
                             unique=True, nullable=False)
    marks_obtained = db.Column(db.Numeric(6, 2), nullable=False)
    remarks = db.Column(db.Text)

    criterion = db.relationship("EvaluationCriterion", back_populates="score")


class EvaluationRevision(db.Model):
    """Snapshot of a submitted evaluation before a controlled, audited modification."""
    __tablename__ = "evaluation_revisions"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("project_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot = db.Column(db.JSON, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False)

    review = db.relationship("ProjectReview", back_populates="revisions")


class ReviewStudentRemark(TimestampMixin, db.Model):
    """Individual remark for one student within a review (matters for team projects; also used for solo ones)."""
    __tablename__ = "review_student_remarks"
    __table_args__ = (db.UniqueConstraint("review_id", "student_id", name="uq_review_student_remark"),)
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("project_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    remarks = db.Column(db.Text, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    review = db.relationship("ProjectReview", back_populates="student_remarks")
    student = db.relationship("Student")


class ReviewDateRequest(TimestampMixin, db.Model):
    """A mentor's request to move an already-scheduled review date; needs Domain Lead approval."""
    __tablename__ = "review_date_requests"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("project_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    old_date = db.Column(db.Date, nullable=False)
    new_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(12), default="pending", nullable=False, index=True)  # pending|approved|rejected|cancelled
    decided_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    decided_at = db.Column(db.DateTime)
    decision_note = db.Column(db.String(500))

    review = db.relationship("ProjectReview", back_populates="date_requests")
