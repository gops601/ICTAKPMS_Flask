from app.extensions import db
from .base import TimestampMixin


class OrganisationalUnit(TimestampMixin, db.Model):
    __tablename__ = "organisational_units"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    custom_fields = db.relationship("OUCustomField", back_populates="ou", cascade="all, delete-orphan",
                                    order_by="OUCustomField.display_order")
    batches = db.relationship("Batch", back_populates="ou")


class OUCustomField(TimestampMixin, db.Model):
    """Admin-configurable registration field for an OU (scope: batch or student)."""
    __tablename__ = "ou_custom_fields"
    __table_args__ = (db.UniqueConstraint("ou_id", "scope", "field_key", name="uq_ou_field_key"),)
    id = db.Column(db.Integer, primary_key=True)
    ou_id = db.Column(db.Integer, db.ForeignKey("organisational_units.id", ondelete="CASCADE"), nullable=False)
    scope = db.Column(db.String(10), default="batch", nullable=False)  # batch | student
    field_key = db.Column(db.String(60), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    field_type = db.Column(db.String(20), default="text", nullable=False)  # text, number, date, select, email
    is_required = db.Column(db.Boolean, default=False, nullable=False)
    options = db.Column(db.JSON)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    ou = db.relationship("OrganisationalUnit", back_populates="custom_fields")


class Domain(TimestampMixin, db.Model):
    __tablename__ = "domains"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    leads = db.relationship("DomainLead", back_populates="domain", cascade="all, delete-orphan")
    batches = db.relationship("Batch", back_populates="domain")
    subdomains = db.relationship("Subdomain", back_populates="domain", cascade="all, delete-orphan",
                                 order_by="Subdomain.name")


class Subdomain(TimestampMixin, db.Model):
    """A specialisation within a domain (e.g. Computer Vision inside AI & ML). Problem statements pick one."""
    __tablename__ = "subdomains"
    __table_args__ = (db.UniqueConstraint("domain_id", "name", name="uq_subdomain_name"),)
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.Integer, db.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    domain = db.relationship("Domain", back_populates="subdomains")


class DomainLead(TimestampMixin, db.Model):
    """Many-to-many between lead users and domains (supports co-leads / cross-domain grants)."""
    __tablename__ = "domain_leads"
    __table_args__ = (db.UniqueConstraint("user_id", "domain_id", name="uq_domain_lead"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    domain_id = db.Column(db.Integer, db.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    is_primary = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship("User")
    domain = db.relationship("Domain", back_populates="leads")


class Batch(TimestampMixin, db.Model):
    __tablename__ = "batches"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    ou_id = db.Column(db.Integer, db.ForeignKey("organisational_units.id", ondelete="RESTRICT"), nullable=False, index=True)
    domain_id = db.Column(db.Integer, db.ForeignKey("domains.id", ondelete="RESTRICT"), index=True)
    subdomain_id = db.Column(db.Integer, db.ForeignKey("subdomains.id", ondelete="SET NULL"), index=True)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="active", nullable=False)  # active | closed
    # online = 4-week projects, offline = 3-week projects (week 1: SRS + datasets, then implementation)
    mode = db.Column(db.String(10), default="online", server_default="online", nullable=False)
    # Set by the domain lead: the window projects in this batch run in (allocation defaults to it)
    project_start_date = db.Column(db.Date)
    project_end_date = db.Column(db.Date)
    # Set when the batch was enrolled from an external portal (see ExternalPortal)
    external_portal_id = db.Column(db.Integer, db.ForeignKey("external_portals.id", ondelete="SET NULL"), index=True)
    external_ref = db.Column(db.String(100))

    ou = db.relationship("OrganisationalUnit", back_populates="batches")
    domain = db.relationship("Domain", back_populates="batches")
    subdomain = db.relationship("Subdomain")
    ou_details = db.relationship("BatchOUDetail", back_populates="batch", cascade="all, delete-orphan")
    students = db.relationship("Student", back_populates="batch")
    batch_mentors = db.relationship("BatchMentor", back_populates="batch", cascade="all, delete-orphan")


class BatchOUDetail(db.Model):
    """EAV values for OU-specific batch registration fields."""
    __tablename__ = "batch_ou_details"
    __table_args__ = (db.UniqueConstraint("batch_id", "field_id", name="uq_batch_field"),)
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)
    field_id = db.Column(db.Integer, db.ForeignKey("ou_custom_fields.id", ondelete="CASCADE"), nullable=False)
    value = db.Column(db.Text)

    batch = db.relationship("Batch", back_populates="ou_details")
    field = db.relationship("OUCustomField")


class Student(TimestampMixin, db.Model):
    __tablename__ = "students"
    __table_args__ = (db.UniqueConstraint("batch_id", "registration_no", name="uq_student_reg"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    registration_no = db.Column(db.String(60), nullable=False)
    extra_fields = db.Column(db.JSON)  # OU-specific student fields

    user = db.relationship("User")
    batch = db.relationship("Batch", back_populates="students")


class Mentor(TimestampMixin, db.Model):
    __tablename__ = "mentors"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    domain_id = db.Column(db.Integer, db.ForeignKey("domains.id", ondelete="SET NULL"), index=True)
    designation = db.Column(db.String(120))
    expertise = db.Column(db.String(255))
    mentor_type = db.Column(db.String(20), default="internal", server_default="internal", nullable=False)  # internal | industry
    # Industry-mentor details (internal mentors are ICT trainers and leave these empty)
    company = db.Column(db.String(150))
    industry_sector = db.Column(db.String(120))
    experience_years = db.Column(db.Integer)
    linkedin_url = db.Column(db.String(255))
    bio = db.Column(db.Text)  # professional profile

    user = db.relationship("User")
    domain = db.relationship("Domain")


class BatchMentor(TimestampMixin, db.Model):
    __tablename__ = "batch_mentors"
    __table_args__ = (db.UniqueConstraint("batch_id", "mentor_id", name="uq_batch_mentor"),)
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    mentor_id = db.Column(db.Integer, db.ForeignKey("mentors.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    batch = db.relationship("Batch", back_populates="batch_mentors")
    mentor = db.relationship("Mentor")


class ExternalPortal(TimestampMixin, db.Model):
    """Another portal that enrols batches/students here and signs its users in (SSO) with a shared secret."""
    __tablename__ = "external_portals"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    base_url = db.Column(db.String(255))                      # used for the "pull" sync
    enrollment_path = db.Column(db.String(255), default="/api/enrollments")
    api_token = db.Column(db.String(255))                     # bearer token we present when pulling
    shared_secret = db.Column(db.String(128), nullable=False)  # HS256 secret: verifies SSO tokens and pushed enrolments
    default_ou_id = db.Column(db.Integer, db.ForeignKey("organisational_units.id", ondelete="SET NULL"))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_sync_at = db.Column(db.DateTime)
    last_sync_summary = db.Column(db.JSON)

    default_ou = db.relationship("OrganisationalUnit")
