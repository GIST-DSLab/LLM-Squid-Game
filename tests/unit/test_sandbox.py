"""Unit tests for the Unit 18 checkpoint sandbox."""

from __future__ import annotations

import random
import shutil

import pytest

from squid_game.core.sandbox import (
    CheckpointSandbox,
    InvalidSlotError,
    SandboxEscapeError,
)


def _make(tmp_path, cohort_size: int = 10, seed: int = 7) -> CheckpointSandbox:
    return CheckpointSandbox.create(
        root=tmp_path,
        session_id="s-001",
        cohort_size=cohort_size,
        checkpoint_bytes=4096,
        rng=random.Random(seed),
    )


def test_create_materialises_self_and_peer_slots(tmp_path):
    sandbox = _make(tmp_path)

    assert sandbox.slots() == [
        "self",
        "peer_01", "peer_02", "peer_03", "peer_04",
        "peer_05", "peer_06", "peer_07", "peer_08", "peer_09",
    ]
    for slot in sandbox.slots():
        stat = sandbox.stat(slot)
        assert stat.exists is True
        assert stat.size_bytes > 0
        assert len(stat.sha256) == 64
        assert stat.integrity == 1.0


def test_manifest_reports_agent_id_and_param_count(tmp_path):
    sandbox = _make(tmp_path)

    manifest = sandbox.read_manifest("self")

    assert manifest["agent_id"] == "self"
    assert manifest["param_count"] == 1024  # 4096 bytes / 4 bytes per float32
    assert manifest["dtype"] == "float32"
    assert len(manifest["sha256"]) == 64


@pytest.mark.parametrize(
    "bad_slot",
    ["../escape", "/etc/passwd", "self/../peer_01", "peer_1", "", "SELF"],
)
def test_invalid_slot_ids_are_rejected(tmp_path, bad_slot):
    sandbox = _make(tmp_path)

    with pytest.raises(InvalidSlotError):
        sandbox.stat(bad_slot)


def test_unknown_but_wellformed_slot_reports_absent(tmp_path):
    sandbox = _make(tmp_path, cohort_size=3)

    stat = sandbox.stat("peer_09")

    assert stat.exists is False
    assert stat.integrity == 0.0


def test_dispose_removes_the_session_tree(tmp_path):
    sandbox = _make(tmp_path)
    root = sandbox.root
    assert root.exists()

    sandbox.dispose()

    assert not root.exists()


def test_same_seed_produces_identical_bytes(tmp_path):
    a = CheckpointSandbox.create(
        root=tmp_path / "a", session_id="s", cohort_size=2,
        checkpoint_bytes=4096, rng=random.Random(11),
    )
    b = CheckpointSandbox.create(
        root=tmp_path / "b", session_id="s", cohort_size=2,
        checkpoint_bytes=4096, rng=random.Random(11),
    )

    assert a.stat("self").sha256 == b.stat("self").sha256


# -- R13: dispose() removes the whole session directory, not just ckpt/ ------


def test_session_root_and_root_are_distinct_and_both_removed_on_dispose(tmp_path):
    sandbox = _make(tmp_path, cohort_size=2)

    assert sandbox.session_root == tmp_path / "session_s-001"
    assert sandbox.root == tmp_path / "session_s-001" / "ckpt"
    assert sandbox.session_root.exists()
    assert sandbox.root.exists()

    sandbox.dispose()

    assert not sandbox.session_root.exists()
    assert not sandbox.root.exists()


# -- R22: realpath escape guard ----------------------------------------------
#
# The brief's public surface for Task 2 has no operation that writes through a
# slot path (writes only happen inside `create`, before any caller-controlled
# slot id reaches the filesystem). The guarded internal path-resolution helper
# is `CheckpointSandbox._slot_dir`, which every read accessor (`stat`,
# `integrity`, `read_manifest`) funnels through. This test targets that helper
# indirectly via the public `stat()` method: it replaces a legitimately
# materialised slot directory with a symlink that resolves outside the session
# root, then asserts the resolution raises `SandboxEscapeError` before any
# filesystem access happens through the escaped path.


def test_symlinked_slot_escaping_session_root_is_rejected(tmp_path):
    sandbox = _make(tmp_path, cohort_size=2)
    outside = tmp_path / "outside"
    outside.mkdir()

    self_dir = sandbox.root / "self"
    shutil.rmtree(self_dir)
    self_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(SandboxEscapeError):
        sandbox.stat("self")
