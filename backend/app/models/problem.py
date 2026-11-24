from app.extensions import db
from .base import TimestampMixin


class ProblemStatement(TimestampMixin, db.Model):
    __tablename__ = "problem_statements"
    id = db.Column(db.Integer, primary_key=True)
    ps_code = db.Column(db.String(50), unique=True, nullable=False)  # Problem Statement ID
    title = db.Column(db.String(255), nullable=False)
    domain_id = db.Column(db.Integer, db.ForeignKey("domains.id", ondelete="RESTRICT"), nullable=False, index=True)
    subdomain_id = db.Column(db.Integer, db.ForeignKey("subdomains.id", ondelete="SET NULL"), index=True)
    description = db.Column(db.Text)
    problem_definition = db.Column(db.Text)
    objectives = db.Column(db.Text)
    scope = db.Column(db.Text)
    expected_outcomes = db.Column(db.Text)
    functional_requirements = db.Column(db.Text)
    non_functional_requirements = db.Column(db.Text)
    suggested_technologies = db.Column(db.Text)
    dataset_info = db.Column(db.Text)
    difficulty = db.Column(db.String(20), default="medium", nullable=False)
    estimated_duration = db.Column(db.String(60))
    required_skills = db.Column(db.Text)
    status = db.Column(db.String(20), default="active", nullable=False)  # active | inactive
    # Staff-created entries are approved. A student's project lands on the shelf immediately as "pending" and only a
    # mentor's approval makes it allocatable / lets the student start the SRS.
    approval_status = db.Column(db.String(20), default="approved", server_default="approved", nullable=False, index=True)  # approved | pending | rejected | withdrawn
    source_type = db.Column(db.String(20), default="internal", server_default="internal", nullable=False, index=True)  # internal | industry
    industry = db.Column(db.String(120), index=True)  # sector; required when source_type == industry
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    # Set when the entry came from an approved student proposal ("student projects" on the shelf)
    proposed_by_student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="SET NULL"), index=True)
    data_collection = db.Column(db.JSON)  # detailed dataset descriptions from the student's data-collection sheet

    domain = db.relationship("Domain")
    subdomain = db.relationship("Subdomain")
    proposer = db.relationship("Student")
    datasets = db.relationship("ProblemStatementDataset", back_populates="problem_statement",
                               cascade="all, delete-orphan")
    documents = db.relationship("ProblemStatementDocument", back_populates="problem_statement",
                                cascade="all, delete-orphan")


class ProblemStatementDataset(TimestampMixin, db.Model):
    __tablename__ = "problem_statement_datasets"
    id = db.Column(db.Integer, primary_key=True)
    problem_statement_id = db.Column(db.Integer, db.ForeignKey("problem_statements.id", ondelete="CASCADE"),
                                     nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("file_attachments.id", ondelete="RESTRICT"), nullable=False)
    description = db.Column(db.String(255))

    problem_statement = db.relationship("ProblemStatement", back_populates="datasets")
    file = db.relationship("FileAttachment")


class ProblemStatementDocument(TimestampMixin, db.Model):
    __tablename__ = "problem_statement_documents"
    id = db.Column(db.Integer, primary_key=True)
    problem_statement_id = db.Column(db.Integer, db.ForeignKey("problem_statements.id", ondelete="CASCADE"),
                                     nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("file_attachments.id", ondelete="RESTRICT"), nullable=False)
    description = db.Column(db.String(255))

    problem_statement = db.relationship("ProblemStatement", back_populates="documents")
    file = db.relationship("FileAttachment")


class StudentProposal(TimestampMixin, db.Model):
    """A detailed problem statement proposed by a student; a mentor must approve it."""
    __tablename__ = "student_proposals"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.Text)
    file_id = db.Column(db.Integer, db.ForeignKey("file_attachments.id", ondelete="RESTRICT"), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)  # pending | approved | rejected | withdrawn
    subdomain_id = db.Column(db.Integer, db.ForeignKey("subdomains.id", ondelete="SET NULL"))
    problem_statement_id = db.Column(db.Integer, db.ForeignKey("problem_statements.id", ondelete="SET NULL"))  # shelf entry created on approval
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    remarks = db.Column(db.Text)
    data_collection = db.Column(db.JSON)  # rows of the detailed data-collection sheet (one per dataset)

    student = db.relationship("Student")
    file = db.relationship("FileAttachment")
    subdomain = db.relationship("Subdomain")
    problem_statement = db.relationship("ProblemStatement")
    datasets = db.relationship("ProposalDataset", back_populates="proposal", cascade="all, delete-orphan")


class ProposalDataset(TimestampMixin, db.Model):
    """A dataset the student uploaded with their proposal; copied onto the shelf entry when it is approved."""
    __tablename__ = "proposal_datasets"
    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey("student_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("file_attachments.id", ondelete="RESTRICT"), nullable=False)
    description = db.Column(db.String(255))

    proposal = db.relationship("StudentProposal", back_populates="datasets")
    file = db.relationship("FileAttachment")
