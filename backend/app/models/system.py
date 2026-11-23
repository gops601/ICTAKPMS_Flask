from app.extensions import db
from .base import TimestampMixin, utcnow


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (db.Index("ix_notif_user_read", "user_id", "is_read"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    link = db.Column(db.String(255))
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class FileAttachment(TimestampMixin, db.Model):
    __tablename__ = "file_attachments"
    id = db.Column(db.Integer, primary_key=True)
    # srs | dataset | reference_document | problem_statement | project_document
    category = db.Column(db.String(40), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(120), unique=True, nullable=False)
    storage_key = db.Column(db.String(255), nullable=False)  # relative key; backend-agnostic (local / S3)
    mime_type = db.Column(db.String(120))
    size_bytes = db.Column(db.BigInteger, nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))


class ImportJob(TimestampMixin, db.Model):
    __tablename__ = "import_jobs"
    id = db.Column(db.Integer, primary_key=True)
    import_type = db.Column(db.String(30), nullable=False)  # batches | students | problem_statements
    ou_id = db.Column(db.Integer, db.ForeignKey("organisational_units.id", ondelete="SET NULL"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    filename = db.Column(db.String(255))
    status = db.Column(db.String(20), default="previewed", nullable=False)  # previewed | confirmed | failed
    total_rows = db.Column(db.Integer, default=0)
    valid_rows = db.Column(db.Integer, default=0)
    error_rows = db.Column(db.Integer, default=0)
    imported_rows = db.Column(db.Integer, default=0)
    payload = db.Column(db.JSON)  # validated rows staged for confirmation

    errors = db.relationship("ImportError", back_populates="job", cascade="all, delete-orphan")


class ImportError(db.Model):
    __tablename__ = "import_errors"
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = db.Column(db.Integer, nullable=False)
    field = db.Column(db.String(80))
    message = db.Column(db.String(500), nullable=False)
    row_data = db.Column(db.JSON)

    job = db.relationship("ImportJob", back_populates="errors")


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(60))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class SystemSetting(TimestampMixin, db.Model):
    __tablename__ = "system_settings"
    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.JSON)
    description = db.Column(db.String(255))
