from marshmallow import EXCLUDE, Schema, fields, validate

from app.extensions import db
from app.models import SrsReviewHistory
from app.services import srs_service


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


class ReviewSchema(_Base):
    decision = fields.String(required=True, validate=validate.OneOf(list(srs_service.DECISIONS)))
    remarks = fields.String(allow_none=True, validate=validate.Length(max=4000))


class GithubSchema(_Base):
    url = fields.String(required=True, validate=validate.Length(min=1, max=255))
    description = fields.String(allow_none=True, validate=validate.Length(max=2000))


def submission_to_dict(sub):
    history = (db.session.query(SrsReviewHistory).filter_by(srs_submission_id=sub.id)
               .order_by(SrsReviewHistory.id).all())
    f = sub.file
    return {
        "id": sub.id, "version": sub.version, "status": sub.status, "description": sub.description,
        "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
        "submitted_by": sub.submitted_by,
        "file": {"name": f.original_name, "size_bytes": f.size_bytes, "mime_type": f.mime_type},
        "history": [{"id": h.id, "decision": h.decision, "remarks": h.remarks,
                     "reviewer": h.reviewer.name if h.reviewer else None, "at": h.created_at.isoformat()}
                    for h in history],
    }


def srs_summary(project, submissions):
    status = srs_service.srs_status(project)
    return {
        "project_id": project.id, "title": project.title, "stage": project.stage, "status": status,
        "status_label": srs_service.LABELS[status],
        "can_submit": project.stage in srs_service.SUBMITTABLE_STAGES,
        "implementation_unlocked": srs_service.implementation_unlocked(project),
        "submissions": [submission_to_dict(s) for s in submissions],
    }
