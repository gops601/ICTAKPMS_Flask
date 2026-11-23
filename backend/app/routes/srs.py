from flask import request
from flask_smorest import Blueprint

from app.extensions import db
from app.models import Batch, Project, ProjectGithubRepository, SrsSubmission
from app.permissions import current_user, login_required, roles_required
from app.permissions.scope import ensure_project_access, scoped_projects
from app.schemas.project import project_to_dict
from app.schemas.srs import GithubSchema, ReviewSchema, srs_summary, submission_to_dict
from app.services import srs_service
from app.utils.audit import audit
from app.utils.errors import NotFound
from app.utils.files import file_download_response
from app.utils.responses import ok

bp = Blueprint("srs", __name__, url_prefix="/api", description="SRS submission/review and GitHub repository")
SEC = [{"bearerAuth": []}]
REVIEWERS = ("mentor", "admin")


def _submissions(project_id):
    return (db.session.query(SrsSubmission).filter_by(project_id=project_id)
            .order_by(SrsSubmission.version.desc()).all())


def _submission_for(user, submission_id):
    """Fetch a submission the user may access (via project scope), hiding existence otherwise."""
    sub = db.session.get(SrsSubmission, submission_id)
    if not sub:
        raise NotFound("SRS submission not found")
    ensure_project_access(user, sub.project_id)
    return sub


# ------------------------------------------------------------------------ SRS
@bp.post("/srs/projects/<int:project_id>")
@bp.doc(security=SEC, description="multipart/form-data: file (PDF/DOCX), description (optional)")
@roles_required("student")
def submit_srs(project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    sub = srs_service.submit(project, request.files.get("file"), request.form.get("description"), user)
    audit(user.id, "srs.submit", "project", project.id, {"version": sub.version})
    db.session.commit()
    return ok(srs_summary(project, _submissions(project.id)), f"SRS v{sub.version} submitted", 201)


@bp.get("/srs/projects/<int:project_id>")
@bp.doc(security=SEC)
@login_required
def get_srs(project_id):
    project = ensure_project_access(current_user(), project_id)
    return ok(srs_summary(project, _submissions(project.id)))


@bp.get("/srs/submissions/<int:submission_id>/download")
@bp.doc(security=SEC)
@login_required
def download_srs(submission_id):
    return file_download_response(_submission_for(current_user(), submission_id).file)


@bp.post("/srs/submissions/<int:submission_id>/review")
@bp.doc(security=SEC, description="decision: start_review | approve | request_changes | reject")
@bp.arguments(ReviewSchema)
@roles_required(*REVIEWERS)
def review_srs(data, submission_id):
    user = current_user()
    sub = _submission_for(user, submission_id)       # mentors only reach projects assigned to them
    srs_service.review(sub, data["decision"], data.get("remarks"), user)
    audit(user.id, f"srs.{data['decision']}", "srs_submission", sub.id, {"project_id": sub.project_id})
    db.session.commit()
    project = db.session.get(Project, sub.project_id)
    return ok(srs_summary(project, _submissions(project.id)), "Review saved")


@bp.get("/srs/queue")
@bp.doc(security=SEC, description="Projects whose latest SRS is awaiting a decision (scoped by role).")
@roles_required("mentor", "domain_lead", "admin")
def queue():
    a = request.args
    q = scoped_projects(current_user()).where(Project.stage.in_(["srs_submitted", "srs_under_review"]))
    if a.get("batch_id", type=int):
        q = q.where(Project.batch_id == a.get("batch_id", type=int))
    q = q.order_by(Project.updated_at.asc())      # oldest waiting first
    page = db.paginate(q, page=a.get("page", 1, type=int),
                       per_page=min(a.get("per_page", 20, type=int), 100), error_out=False)
    items = []
    for p in page.items:
        latest = srs_service.latest_submission(p.id)
        items.append({**project_to_dict(p), "srs_version": latest.version if latest else None,
                      "srs_submitted_at": latest.submitted_at.isoformat() if latest and latest.submitted_at else None})
    return ok(items, meta={"page": page.page, "per_page": page.per_page, "total": page.total, "pages": page.pages})


# --------------------------------------------------------------------- GitHub
def _repo_dict(project_id):
    repo = db.session.query(ProjectGithubRepository).filter_by(project_id=project_id).first()
    return {"url": repo.url, "description": repo.description, "updated_at": repo.updated_at.isoformat()} if repo else None


@bp.get("/github/projects/<int:project_id>")
@bp.doc(security=SEC)
@login_required
def get_github(project_id):
    project = ensure_project_access(current_user(), project_id)
    return ok({"repository": _repo_dict(project.id), "can_edit": current_user().role_name == "student",
               "implementation_unlocked": srs_service.implementation_unlocked(project)})


@bp.put("/github/projects/<int:project_id>")
@bp.doc(security=SEC)
@bp.arguments(GithubSchema)
@roles_required("student")
def set_github(data, project_id):
    user = current_user()
    project = ensure_project_access(user, project_id)
    srs_service.set_github(project, data["url"], data.get("description"), user)
    audit(user.id, "github.set", "project", project.id)
    db.session.commit()
    return ok({"repository": _repo_dict(project.id), "can_edit": True, "implementation_unlocked": True}, "Repository saved")
