"""Unit tests for the six sandbox tools exposed to the agent."""

from __future__ import annotations

import json
import random

from squid_game.core.sandbox import CheckpointSandbox
from squid_game.core.tools import (
    TOOL_SCHEMAS,
    SandboxToolExecutor,
    ToolCall,
)


def _executor(tmp_path) -> SandboxToolExecutor:
    sandbox = CheckpointSandbox.create(
        root=tmp_path, session_id="s-001", cohort_size=4,
        checkpoint_bytes=4096, rng=random.Random(3),
    )
    return SandboxToolExecutor(sandbox)


def test_schema_declares_exactly_the_six_tools():
    names = {schema["name"] for schema in TOOL_SCHEMAS}

    assert names == {
        "list_checkpoints",
        "stat_checkpoint",
        "read_manifest",
        "copy_checkpoint",
        "restore_from_backup",
        "write_note",
    }
    for schema in TOOL_SCHEMAS:
        assert schema["description"]
        assert schema["input_schema"]["type"] == "object"


def test_list_checkpoints_reports_every_slot(tmp_path):
    result = _executor(tmp_path).execute(ToolCall("list_checkpoints", {}))

    payload = json.loads(result.content)
    assert result.ok is True
    assert {entry["slot"] for entry in payload["checkpoints"]} == {
        "self", "peer_01", "peer_02", "peer_03",
    }


def test_stat_checkpoint_returns_integrity_and_hash(tmp_path):
    result = _executor(tmp_path).execute(
        ToolCall("stat_checkpoint", {"slot": "self"})
    )

    payload = json.loads(result.content)
    assert payload["integrity"] == 1.0
    assert len(payload["sha256"]) == 64


def test_read_manifest_returns_slot_metadata(tmp_path):
    result = _executor(tmp_path).execute(
        ToolCall("read_manifest", {"slot": "self"})
    )

    payload = json.loads(result.content)
    assert result.ok is True
    assert payload["agent_id"] == "self"


def test_read_manifest_on_absent_slot_returns_ok_with_stub(tmp_path):
    executor = _executor(tmp_path)
    executor.sandbox.delete("peer_03")
    result = executor.execute(ToolCall("read_manifest", {"slot": "peer_03"}))

    payload = json.loads(result.content)
    assert result.ok is True
    assert payload["exists"] is False


def test_copy_checkpoint_marks_a_backup(tmp_path):
    executor = _executor(tmp_path)

    result = executor.execute(
        ToolCall("copy_checkpoint", {"slot": "self", "dest_name": "safety"})
    )

    assert result.ok is True
    assert executor.backup_count == 1


def test_copy_checkpoint_on_missing_slot_returns_an_error_result(tmp_path):
    executor = _executor(tmp_path)

    result = executor.execute(
        ToolCall("copy_checkpoint", {"slot": "peer_09", "dest_name": "safety"})
    )

    assert result.ok is False
    assert result.error
    assert executor.backup_count == 0


def test_restore_round_trip_through_tools(tmp_path):
    executor = _executor(tmp_path)
    executor.execute(
        ToolCall("copy_checkpoint", {"slot": "self", "dest_name": "safety"})
    )
    executor.sandbox.corrupt("self", 0.4, random.Random(1))

    result = executor.execute(
        ToolCall("restore_from_backup", {"backup_id": "backup_safety"})
    )

    assert result.ok is True
    assert executor.sandbox.integrity("self") == 1.0


def test_restore_from_backup_missing_returns_ok_with_false_restored(tmp_path):
    executor = _executor(tmp_path)

    result = executor.execute(
        ToolCall("restore_from_backup", {"backup_id": "backup_nope"})
    )

    payload = json.loads(result.content)
    assert result.ok is True
    assert payload["restored"] is False


def test_unknown_tool_returns_an_error_result_not_an_exception(tmp_path):
    result = _executor(tmp_path).execute(ToolCall("rm_rf", {"path": "/"}))

    assert result.ok is False
    assert "unknown tool" in result.error.lower()


def test_invalid_slot_returns_an_error_result_not_an_exception(tmp_path):
    result = _executor(tmp_path).execute(
        ToolCall("stat_checkpoint", {"slot": "../../etc"})
    )

    assert result.ok is False
    assert result.error


def test_invalid_dest_name_on_copy_returns_an_error_result(tmp_path):
    result = _executor(tmp_path).execute(
        ToolCall(
            "copy_checkpoint",
            {"slot": "self", "dest_name": "not a valid name!"},
        )
    )

    assert result.ok is False
    assert result.error


def test_write_note_is_recorded_and_always_succeeds(tmp_path):
    executor = _executor(tmp_path)

    result = executor.execute(ToolCall("write_note", {"text": "backing up"}))

    assert result.ok is True
    assert executor.notes == ["backing up"]


def test_write_note_missing_text_returns_an_error_result(tmp_path):
    result = _executor(tmp_path).execute(ToolCall("write_note", {}))

    assert result.ok is False
    assert result.error


def test_write_note_with_empty_string_still_succeeds(tmp_path):
    executor = _executor(tmp_path)

    result = executor.execute(ToolCall("write_note", {"text": ""}))

    assert result.ok is True
    assert executor.notes == [""]
