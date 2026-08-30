"""Lightweight password hashing for the Web Arena Play identity system.

stdlib-only (pbkdf2_hmac). Not a full auth stack — nicknames are disposable
and there is no password recovery (a lost password locks that nickname). The
only durable store of a password is ``players.pw_hash``; plaintext must never
be logged or persisted elsewhere.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGO = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """Return ``pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`` for ``password``."""
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a ``hash_password`` string."""
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    except (ValueError, AttributeError, OverflowError):
        # Any malformed/degenerate stored value (bad format, non-numeric or
        # out-of-range iteration count, invalid hex) degrades to a rejection.
        return False
    return hmac.compare_digest(dk, expected)
