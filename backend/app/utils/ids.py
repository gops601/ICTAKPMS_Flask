"""System-generated identifiers: always start with ICT_ and mix letters and digits, e.g. ICT_PRJ_7K3Q9X."""
import secrets

_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # no I / O: easy to read aloud
_DIGITS = "23456789"                    # no 0 / 1
_ALPHABET = _LETTERS + _DIGITS


def _token(length=6):
    while True:
        t = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if any(c in _LETTERS for c in t) and any(c in _DIGITS for c in t):
            return t


def generate_id(kind, exists):
    """ICT_<KIND>_<6 mixed chars>, retried until `exists(candidate)` is false."""
    for _ in range(50):
        candidate = f"ICT_{kind}_{_token()}"
        if not exists(candidate):
            return candidate
    raise RuntimeError("Could not generate a unique identifier")
