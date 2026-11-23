"""Secure upload handling: allow-listed types, size limits, content sniffing, random storage names."""
import mimetypes
import os
import uuid

from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import FileAttachment
from app.services.storage import get_storage
from app.utils.errors import AppError

_DOC_EXT = {"pdf", "doc", "docx", "txt", "md", "ppt", "pptx", "xls", "xlsx", "png", "jpg", "jpeg"}
_DATA_EXT = {"csv", "tsv", "xlsx", "xls", "json", "xml", "txt", "zip", "gz", "parquet"}

# category -> (storage directory, allowed extensions, max size in MB)
CATEGORIES = {
    "dataset": ("datasets", _DATA_EXT, 50),
    "reference_document": ("reference_documents", _DOC_EXT, 25),
    "problem_statement": ("problem_statements", _DOC_EXT, 25),
    "srs": ("srs", {"pdf", "docx"}, 15),
    "project_document": ("project_documents", _DOC_EXT | {"zip"}, 25),
}

_MAGIC = {
    "pdf": (b"%PDF",), "docx": (b"PK",), "xlsx": (b"PK",), "pptx": (b"PK",), "zip": (b"PK",),
    "png": (b"\x89PNG",), "jpg": (b"\xff\xd8",), "jpeg": (b"\xff\xd8",), "gz": (b"\x1f\x8b",),
    "doc": (b"\xd0\xcf\x11\xe0",), "xls": (b"\xd0\xcf\x11\xe0",), "ppt": (b"\xd0\xcf\x11\xe0",),
    "parquet": (b"PAR1",),
}
_TEXT_EXT = {"csv", "tsv", "json", "xml", "txt", "md"}


def _extension(name):
    return os.path.splitext(name)[1].lower().lstrip(".")


def _validate_content(ext, head):
    if ext in _MAGIC:
        if not any(head.startswith(m) for m in _MAGIC[ext]):
            raise AppError(f"The file content does not match its .{ext} extension", 422)
    elif ext in _TEXT_EXT and b"\x00" in head:
        raise AppError(f"The file does not look like a valid .{ext} text file", 422)


def save_upload(file_storage, category, user_id):
    """Validate and persist an uploaded file; returns the (flushed) FileAttachment."""
    if category not in CATEGORIES:
        raise AppError("Unknown file category", 500)
    directory, allowed, max_mb = CATEGORIES[category]
    if file_storage is None or not file_storage.filename:
        raise AppError("A file is required", 422)

    display_name = secure_filename(file_storage.filename) or "file"
    ext = _extension(display_name)
    if ext not in allowed:
        raise AppError(f"File type .{ext or '?'} is not allowed. Allowed: {', '.join(sorted(allowed))}", 422)

    stream = file_storage.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise AppError("The uploaded file is empty", 422)
    if size > max_mb * 1024 * 1024:
        raise AppError(f"File is too large (max {max_mb} MB for this type)", 413)
    _validate_content(ext, stream.read(8192))
    stream.seek(0)

    stored_name = f"{uuid.uuid4().hex}.{ext}"  # never derived from user input
    key = f"{directory}/{stored_name}"
    get_storage().save(key, stream)
    attachment = FileAttachment(
        category=category, original_name=display_name[:255], stored_name=stored_name, storage_key=key,
        mime_type=mimetypes.guess_type(display_name)[0] or "application/octet-stream",
        size_bytes=size, uploaded_by=user_id)
    db.session.add(attachment)
    db.session.flush()
    return attachment


def delete_file(attachment):
    """Remove the stored object and its metadata row (call after detaching it from owners)."""
    get_storage().delete(attachment.storage_key)
    db.session.delete(attachment)
