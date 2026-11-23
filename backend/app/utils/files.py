from flask import Response

from app.services.storage import get_storage
from app.utils.errors import NotFound


def _stream(handle, chunk=64 * 1024):
    """Stream a stored file and always release the handle (Windows cannot delete open files)."""
    try:
        while data := handle.read(chunk):
            yield data
    finally:
        handle.close()


def file_download_response(attachment):
    """Attachment download for a stored file. Callers must have authorised access already."""
    try:
        handle = get_storage().open(attachment.storage_key)
    except FileNotFoundError:
        raise NotFound("The stored file is missing")
    resp = Response(_stream(handle), mimetype=attachment.mime_type or "application/octet-stream")
    # original_name went through secure_filename at upload, so it is header-safe ASCII.
    resp.headers["Content-Disposition"] = f'attachment; filename="{attachment.original_name}"'
    resp.headers["Content-Length"] = str(attachment.size_bytes)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
