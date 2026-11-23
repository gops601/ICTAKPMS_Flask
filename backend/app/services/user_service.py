"""Account provisioning for mentors, leads and students (profile rows included)."""
import secrets
import string

from app.extensions import db
from app.models import Batch, Mentor, Student, User
from app.services.auth_service import create_user, validate_password_strength
from app.utils.errors import AppError, NotFound


def generate_temp_password():
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(10))
        if any(c.isalpha() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def create_staff_user(role, name, email, password, phone=None, domain_id=None, designation=None, expertise=None):
    if role == "student":
        raise AppError("Students are created through the student endpoints (a batch is required)", 422)
    user = create_user(role, name, email, password, phone)
    if role == "mentor":
        db.session.add(Mentor(user_id=user.id, domain_id=domain_id, designation=designation, expertise=expertise))
    return user


def create_student(batch, name, email, phone, registration_no, extra_fields=None, password=None):
    """Create user + student profile. Returns (student, temp_password)."""
    registration_no = (registration_no or "").strip()
    if not registration_no:
        raise AppError("Registration number is required", 422)
    if db.session.query(Student).filter_by(batch_id=batch.id).filter(
            db.func.lower(Student.registration_no) == registration_no.lower()).first():
        raise AppError(f"Registration number '{registration_no}' already exists in this batch", 409)
    password = password or generate_temp_password()
    user = create_user("student", name, email, password, phone, must_change_password=True)
    student = Student(user_id=user.id, batch_id=batch.id, registration_no=registration_no,
                      extra_fields=extra_fields or None)
    db.session.add(student)
    db.session.flush()
    return student, password


def credential_row(student, temporary_password):
    """One shareable login record (never persisted; shown to the admin once)."""
    return {"name": student.user.name, "email": student.user.email, "phone": student.user.phone or "",
            "registration_no": student.registration_no, "batch_code": student.batch.code, "batch_name": student.batch.name,
            "temporary_password": temporary_password}


def issue_batch_credentials(batch, student_ids=None):
    """Fresh temporary passwords for students who have not logged in yet (must_change_password still set).

    Students who already chose their own password are skipped, so this can never lock out or override
    someone who is actively using their account. Returns (issued, skipped).
    """
    q = db.session.query(Student).filter_by(batch_id=batch.id)
    if student_ids:
        q = q.filter(Student.id.in_(student_ids))
    issued, skipped = [], []
    for s in q.order_by(Student.registration_no).all():
        user = s.user
        if not user.is_active:
            skipped.append({"name": user.name, "registration_no": s.registration_no, "reason": "Account is deactivated"})
        elif not user.must_change_password:
            skipped.append({"name": user.name, "registration_no": s.registration_no, "reason": "Already set their own password"})
        else:
            issued.append(credential_row(s, reset_user_password(user)))
    return issued, skipped


def reset_user_password(user, new_password=None):
    password = new_password or generate_temp_password()
    validate_password_strength(password)
    user.set_password(password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    return password


def get_user_or_404(user_id):
    u = db.session.get(User, user_id)
    if not u:
        raise NotFound("User not found")
    return u


def ensure_batch(batch_id):
    b = db.session.get(Batch, batch_id)
    if not b:
        raise AppError("Batch not found", 422, {"batch_id": "Batch not found"})
    return b
