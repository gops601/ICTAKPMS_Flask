from marshmallow import EXCLUDE, Schema, fields, validate


class _Base(Schema):
    class Meta:
        unknown = EXCLUDE


def _text():
    return fields.String(allow_none=True)


class ProblemStatementSchema(_Base):
    ps_code = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=50))  # blank = generated ICT_PS_ id
    title = fields.String(required=True, validate=validate.Length(min=1, max=255))
    domain_id = fields.Integer(required=True)
    subdomain_id = fields.Integer(allow_none=True)
    description = _text()
    problem_definition = _text()
    objectives = _text()
    scope = _text()
    expected_outcomes = _text()
    functional_requirements = _text()
    non_functional_requirements = _text()
    suggested_technologies = _text()
    dataset_info = _text()
    required_skills = _text()
    difficulty = fields.String(validate=validate.OneOf(["easy", "medium", "hard"]))
    estimated_duration = fields.String(allow_none=True, validate=validate.Length(max=60))
    status = fields.String(validate=validate.OneOf(["active", "inactive"]))
    source_type = fields.String(validate=validate.OneOf(["internal", "industry"]))
    industry = fields.String(allow_none=True, validate=validate.Length(max=120))


class ProblemStatementUpdateSchema(ProblemStatementSchema):
    ps_code = fields.String(validate=validate.Length(min=1, max=50))
    title = fields.String(validate=validate.Length(min=1, max=255))
    domain_id = fields.Integer()


class PSStatusSchema(_Base):
    status = fields.String(required=True)


def file_to_dict(link):
    f = link.file
    return {"id": link.id, "file_id": f.id, "name": f.original_name, "size_bytes": f.size_bytes,
            "mime_type": f.mime_type, "description": link.description, "uploaded_at": link.created_at.isoformat()}


def ps_to_dict(ps, detail=False, can_edit=False):
    out = {"id": ps.id, "ps_code": ps.ps_code, "title": ps.title, "difficulty": ps.difficulty, "status": ps.status,
           "source_type": ps.source_type, "industry": ps.industry, "approval_status": ps.approval_status,
           "domain": {"id": ps.domain.id, "name": ps.domain.name},
           "subdomain": {"id": ps.subdomain.id, "name": ps.subdomain.name} if ps.subdomain else None,
           "proposed_by": {"id": ps.proposer.id, "name": ps.proposer.user.name} if ps.proposer else None, "estimated_duration": ps.estimated_duration,
           "created_at": ps.created_at.isoformat(), "dataset_count": len(ps.datasets),
           "document_count": len(ps.documents)}
    if detail:
        for f in ("description", "problem_definition", "objectives", "scope", "expected_outcomes",
                  "functional_requirements", "non_functional_requirements", "suggested_technologies",
                  "dataset_info", "required_skills"):
            out[f] = getattr(ps, f)
        out["data_collection"] = ps.data_collection or []
        out["datasets"] = [file_to_dict(d) for d in ps.datasets]
        out["documents"] = [file_to_dict(d) for d in ps.documents]
        out["can_edit"] = can_edit
    return out
