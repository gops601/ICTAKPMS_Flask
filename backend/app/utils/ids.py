"""System-generated identifiers.

Batches, students and projects get ``<OU>_<MODE>_<4 digits>`` (e.g. ACADEMIC_ONLINE_0001): the OU code, the batch mode
(ONLINE / OFFLINE) and a running number that counts separately for every OU + mode combination.
Problem statements have no OU or mode, so they keep ``ICT_PS_<6 mixed chars>``.
"""
import re
import secrets

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # no I / O: easy to read aloud
_DIGITS = "23456789"                    # no 0 / 1
_ALPHABET = _LETTERS + _DIGITS


def _token(length=6):
    while True:
        t = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if any(c in _LETTERS for c in t) and any(c in _DIGITS for c in t):
            return t


def scoped_prefix(ou_code, mode):
    """``ACADEMIC_ONLINE_`` - the OU code reduced to letters/digits, then the mode."""
    ou = re.sub(r"[^A-Za-z0-9]", "", ou_code or "").upper() or "OU"
    return f"{ou}_{(mode or 'online').strip().upper()}_"


def next_scoped_id(ou_code, mode, column):
    """The next free ``<OU>_<MODE>_NNNN`` for `column` (a Batch.code / Student.registration_no / Project.code column).

    The number is one more than the highest already issued for this OU + mode, so numbers are never reused after a
    delete of anything but the newest record. Pending (flushed) rows count, so a bulk import gets 0001, 0002, ...
    """
    from app.extensions import db
    prefix = scoped_prefix(ou_code, mode)
    like = column.startswith(prefix, autoescape=True)
    top = db.session.query(column).filter(like).order_by(db.func.length(column).desc(), column.desc()).first()
    number = 0
    if top and top[0][len(prefix):].isdigit():
        number = int(top[0][len(prefix):])
    elif top:                                    # someone typed a free-text id with this prefix: scan for the real maximum
        number = max((int(v[len(prefix):]) for (v,) in db.session.query(column).filter(like) if v[len(prefix):].isdigit()), default=0)
    return f"{prefix}{number + 1:04d}"


def generate_id(kind, exists):
    """ICT_<KIND>_<6 mixed chars>, retried until `exists(candidate)` is false."""
    for _ in range(50):
        candidate = f"ICT_{kind}_{_token()}"
        if not exists(candidate):
            return candidate
    raise RuntimeError("Could not generate a unique identifier")
