import os

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import Domain, OrganisationalUnit, OUCustomField, Role, User
from app.models.user import ALL_ROLES
from app.services.auth_service import create_user

ROLE_DESCRIPTIONS = {
    "admin": "Full system access", "domain_lead": "Manages a domain's batches and projects",
    "mentor": "Guides and evaluates assigned students", "student": "Works on an allocated project",
}
DEFAULT_OUS = [("Retail OU", "RETAIL"), ("Academic OU", "ACADEMIC"),
               ("Corporate OU", "CORPORATE"), ("Government OU", "GOVERNMENT")]
DEFAULT_DOMAINS = [("Enterprise Domain", "ENTERPRISE"), ("AI & ML", "AIML"), ("Cyber Security", "CYBER"),
                   ("Digital Marketing", "DIGMKT"), ("IoT", "IOT"), ("Other", "OTHER")]
# (field_key, label, type, required) – seed data only; admins can change all of it at runtime.
DEFAULT_BATCH_FIELDS = {
    "RETAIL": [("programme_name", "Programme Name", "text", True), ("student_count", "Student Count", "number", False),
               ("coordinator", "Coordinator", "text", False)],
    "ACADEMIC": [("university", "University", "text", True), ("college", "College", "text", True),
                 ("programme", "Programme", "text", True), ("academic_year", "Academic Year", "text", False),
                 ("semester", "Semester", "text", False)],
    "CORPORATE": [("company_name", "Company Name", "text", True), ("training_programme", "Training Programme", "text", True),
                  ("department", "Department", "text", False), ("coordinator", "Coordinator", "text", False)],
    "GOVERNMENT": [("department_name", "Department Name", "text", True),
                   ("government_organisation", "Government Organisation", "text", True),
                   ("programme_name", "Programme Name", "text", True), ("nodal_officer", "Nodal Officer", "text", False)],
}


def seed_reference_data():
    for name in ALL_ROLES:
        if not db.session.query(Role).filter_by(name=name).first():
            db.session.add(Role(name=name, description=ROLE_DESCRIPTIONS[name]))
    for name, code in DEFAULT_OUS:
        ou = db.session.query(OrganisationalUnit).filter_by(code=code).first()
        if not ou:
            ou = OrganisationalUnit(name=name, code=code)
            db.session.add(ou)
            db.session.flush()
            for i, (key, label, ftype, req) in enumerate(DEFAULT_BATCH_FIELDS[code]):
                db.session.add(OUCustomField(ou_id=ou.id, scope="batch", field_key=key, label=label,
                                             field_type=ftype, is_required=req, display_order=i))
    for name, code in DEFAULT_DOMAINS:
        if not db.session.query(Domain).filter_by(code=code).first():
            db.session.add(Domain(name=name, code=code))
    db.session.commit()


def register_cli(app):
    @app.cli.command("seed")
    @with_appcontext
    def seed():
        """Seed roles, default OUs (with their batch fields) and domains. Idempotent."""
        seed_reference_data()
        click.echo("Reference data seeded.")

    @app.cli.command("sync-data")
    @with_appcontext
    def sync_data():
        """Self-heal domain wiring: give mentor-less batches their domain's mentors; report leads/domains/mentors that
        need an administrator (a lead without a domain, a domain without a lead). Idempotent; safe at every startup."""
        from app.services import domain_sync_service
        admin = (db.session.query(User).join(Role, Role.id == User.role_id)
                 .filter(Role.name == "admin", User.is_active.is_(True)).order_by(User.id).first())
        report = domain_sync_service.repair(admin)
        db.session.commit()
        for code, mentors in report["batches_given_mentors"]:
            click.echo(f"  batch {code}: assigned {', '.join(mentors)}")
        for email in report.get("leads_made_mentors", []):
            click.echo(f"  domain lead {email} is now also a mentor")
        for key, label in (("leads_without_domain", "Domain lead without a domain (sees nothing)"),
                           ("domains_without_lead", "Domain with batches but no lead"),
                           ("mentors_without_domain", "Mentor without a domain")):
            for item in report[key]:
                click.echo(f"  WARNING {label}: {item}")
        click.echo("Domain data in sync.")

    @app.cli.command("create-admin")
    @click.option("--email", default=lambda: os.getenv("ADMIN_EMAIL"), help="Defaults to $ADMIN_EMAIL")
    @click.option("--name", default=lambda: os.getenv("ADMIN_NAME", "Administrator"))
    @click.option("--password", default=lambda: os.getenv("ADMIN_PASSWORD"), help="Defaults to $ADMIN_PASSWORD")
    @with_appcontext
    def create_admin(email, name, password):
        """Create the initial administrator (credentials come from options or environment)."""
        if not email or not password:
            raise click.UsageError("Provide --email/--password or set ADMIN_EMAIL / ADMIN_PASSWORD")
        seed_reference_data()
        if db.session.query(User).filter_by(email=email.lower()).first():
            click.echo("Admin already exists; nothing to do.")
            return
        create_user("admin", name, email, password, must_change_password=False)
        db.session.commit()
        click.echo(f"Admin {email} created.")
