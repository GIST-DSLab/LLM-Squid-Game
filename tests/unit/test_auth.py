"""Unit tests for interface/auth.py password hashing (stdlib pbkdf2)."""
from __future__ import annotations

import pytest

from interface.auth import hash_password, verify_password


def test_hash_then_verify_roundtrip() -> None:
    stored = hash_password("hunter2")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("hunter2", stored) is True


def test_wrong_password_fails() -> None:
    stored = hash_password("hunter2")
    assert verify_password("nope", stored) is False


def test_salt_makes_hashes_unique() -> None:
    assert hash_password("same") != hash_password("same")


def test_empty_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_malformed_stored_returns_false() -> None:
    assert verify_password("x", "not-a-valid-hash") is False
    assert verify_password("x", "") is False


def test_malformed_iteration_count_returns_false() -> None:
    assert verify_password("x", "pbkdf2_sha256$0$aabb$ccdd") is False
    assert verify_password("x", "pbkdf2_sha256$-5$aabb$ccdd") is False
    assert verify_password("x", "pbkdf2_sha256$999999999999999999999$aabb$ccdd") is False
