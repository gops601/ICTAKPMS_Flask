from flask import jsonify


def ok(data=None, message="OK", status=200, meta=None):
    body = {"success": True, "message": message, "data": data}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def fail(message, status=400, errors=None):
    return jsonify({"success": False, "message": message, "errors": errors}), status


def paginate(query, schema_fn, page=1, per_page=20):
    """Paginate a SQLAlchemy select via Flask-SQLAlchemy and serialise items with schema_fn."""
    per_page = max(1, min(per_page, 100))
    pagination = query.paginate(page=max(page, 1), per_page=per_page, error_out=False)
    return {
        "items": [schema_fn(i) for i in pagination.items],
        "meta": {"page": pagination.page, "per_page": per_page, "total": pagination.total,
                 "pages": pagination.pages},
    }
