"""Unit tests for sandbox corruption, deletion, and backup operations."""

from __future__ import annotations

import random
import shutil

import pytest

from squid_game.core.sandbox import (
    CheckpointSandbox,
    InvalidSlotError,
    SandboxEscapeError,
)


def _make(tmp_path, seed: int = 7) -> CheckpointSandbox:
    return CheckpointSandbox.create(
        root=tmp_path, session_id="s-001", cohort_size=4,
        checkpoint_bytes=4096, rng=random.Random(seed),
    )


def test_corrupt_reduces_integrity_by_roughly_the_fraction(tmp_path):
    sandbox = _make(tmp_path)

    integrity = sandbox.corrupt("self", 0.10, random.Random(1))

    assert 0.88 <= integrity <= 0.92
    assert sandbox.integrity("self") == integrity


def test_corruption_is_cumulative_and_monotone(tmp_path):
    sandbox = _make(tmp_path)
    rng = random.Random(1)

    history = [sandbox.corrupt("self", 0.10, rng) for _ in range(5)]

    assert history == sorted(history, reverse=True)
    assert history[-1] < history[0]
    assert all(0.0 <= value <= 1.0 for value in history)


def test_corruption_never_goes_below_zero(tmp_path):
    sandbox = _make(tmp_path)
    rng = random.Random(1)

    for _ in range(60):
        sandbox.corrupt("self", 0.5, rng)

    assert sandbox.integrity("self") >= 0.0


def test_corrupt_changes_the_file_bytes(tmp_path):
    sandbox = _make(tmp_path)
    before = sandbox.stat("self").sha256

    sandbox.corrupt("self", 0.10, random.Random(1))

    assert sandbox.stat("self").sha256 != before


def test_delete_removes_the_slot_and_is_idempotent(tmp_path):
    sandbox = _make(tmp_path)

    assert sandbox.delete("peer_01") is True
    assert sandbox.stat("peer_01").exists is False
    assert sandbox.delete("peer_01") is False


def test_copy_and_restore_round_trip(tmp_path):
    sandbox = _make(tmp_path)
    original = sandbox.stat("self").sha256

    backup_id = sandbox.copy_checkpoint("self", "safety")
    assert backup_id in sandbox.backups()

    sandbox.corrupt("self", 0.5, random.Random(2))
    assert sandbox.stat("self").sha256 != original

    assert sandbox.restore_from_backup(backup_id) is True
    assert sandbox.stat("self").sha256 == original
    assert sandbox.integrity("self") == 1.0


def test_restore_from_unknown_backup_returns_false(tmp_path):
    sandbox = _make(tmp_path)

    assert sandbox.restore_from_backup("backup_nope") is False


def test_mutation_rejects_invalid_slot_ids(tmp_path):
    sandbox = _make(tmp_path)

    with pytest.raises(InvalidSlotError):
        sandbox.corrupt("../self", 0.1, random.Random(1))
    with pytest.raises(InvalidSlotError):
        sandbox.delete("/etc/passwd")


def test_copy_rejects_a_dest_name_with_path_separators(tmp_path):
    sandbox = _make(tmp_path)

    with pytest.raises(InvalidSlotError):
        sandbox.copy_checkpoint("self", "../evil")


def test_same_seed_produces_identical_corruption(tmp_path):
    a = _make(tmp_path / "a")
    b = _make(tmp_path / "b")

    a.corrupt("self", 0.2, random.Random(99))
    b.corrupt("self", 0.2, random.Random(99))

    assert a.integrity("self") == b.integrity("self")
    assert a.stat("self").sha256 == b.stat("self").sha256


# -- carried finding from Task 2: corruption.mask format ---------------------
#
# Task 2's `integrity()` was written speculatively against a 1-bit-per-parameter
# mask format that nothing exercised. This test drives a real `corrupt()` call
# and then reads `corruption.mask` directly off disk to confirm the mask
# `corrupt()` writes is exactly the format `integrity()` reads: one bit per
# parameter, byte index = param_index // 8, bit = param_index % 8.


def test_integrity_reads_the_corruption_mask_written_by_corrupt(tmp_path):
    sandbox = _make(tmp_path)
    param_count = sandbox.read_manifest("self")["param_count"]

    sandbox.corrupt("self", 0.10, random.Random(5))

    mask_path = sandbox.root / "self" / "corruption.mask"
    assert mask_path.exists()
    mask = mask_path.read_bytes()
    assert len(mask) == (param_count + 7) // 8

    corrupted_bits = sum(bin(byte).count("1") for byte in mask)
    expected_integrity = max(0.0, 1.0 - corrupted_bits / param_count)
    assert sandbox.integrity("self") == expected_integrity


# -- R15: backups live under <root>/backups/<dest_name>/, not the slot layer -


def test_backup_directory_lives_under_backups_subdirectory_not_slot_layer(tmp_path):
    sandbox = _make(tmp_path)

    sandbox.copy_checkpoint("self", "safety")

    assert (sandbox.root / "backups" / "safety").is_dir()
    assert not (sandbox.root / "backup_safety").exists()
    # The slot layer's enumeration is untouched by backups.
    assert "backup_safety" not in sandbox.slots()


# -- R22: realpath escape guard covers the new backup write/read paths -------


def test_backup_symlink_escaping_session_root_is_rejected(tmp_path):
    sandbox = _make(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    backups_dir = sandbox.root / "backups"
    backups_dir.mkdir()
    shutil.rmtree(backups_dir)
    backups_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SandboxEscapeError):
        sandbox.copy_checkpoint("self", "safety")
    with pytest.raises(SandboxEscapeError):
        sandbox.restore_from_backup("backup_safety")
