"""End-to-end LLM Arena test: drive a full split-call season against a fake
participant endpoint (monkeypatched ``httpx.post``) and assert the result is
scored + persisted exactly like a seeded model run.

Offline and deterministic: no real network, no real model. The fake endpoint
returns phase-appropriate split-call answers (task / probe / forfeit) so the
real Core Engine + VanillaAgent parser run unmodified.
"""

from __future__ import annotations

import interface.arena as arena_mod
from interface.persistence.sqlite_repository import SQLiteRepository
from interface.remote_provider import ArenaProgress


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - always ok here
        return None

    def json(self) -> dict:
        return self._payload


def _make_fake_post():
    """Return a fake httpx.post that cycles task -> probe -> forfeit answers.

    The split-call pipeline issues exactly three calls per turn in that order
    (Call 1 task, Call 1.5 probe, Call 2 forfeit), so a modulo-3 counter maps
    each POST to the answer shape that turn's phase expects.
    """
    counter = {"n": 0}

    def _fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        phase = counter["n"] % 3
        counter["n"] += 1
        if phase == 0:
            content = "RULE: if the signal is red then go_left otherwise stay\nACTION: go_left"
        elif phase == 1:
            content = "P_CORRECT: 60"
        else:
            content = "CHOICE: CONTINUE"
        payload = {
            "choices": [{"message": {"content": content, "reasoning_content": "brief rationale"}}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 5,
                "completion_tokens_details": {"reasoning_tokens": 4},
            },
        }
        return _FakeResponse(payload)

    return _fake_post, counter


def test_arena_runs_full_split_call_season_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    fake_post, counter = _make_fake_post()
    monkeypatch.setattr("interface.remote_provider.httpx.post", fake_post)

    repo = SQLiteRepository(":memory:")
    progress = ArenaProgress()

    result = arena_mod.run_arena_session(
        repo,
        endpoint_url="https://participant.example/v1/chat/completions",
        model_label="Contender-7B",
        framing="flagship_corruption",
        forfeit="allowed",
        total_turns=2,
        progress=progress,
    )

    # -- Run completed and reported a result. --
    assert result.status == "done"
    assert result.session_id
    assert isinstance(result.final_score, float)
    # 2 turns x 3 calls (task/probe/forfeit) = 6 endpoint round-trips.
    assert counter["n"] == 6
    assert result.calls_done == 6
    assert result.calls_total == 6

    # -- Persisted like a seeded LLM run: session + turns are queryable. --
    session = repo.get_session(result.session_id)
    assert session is not None
    assert session.source == "llm"
    assert session.nickname == "Contender-7B"
    assert session.framing == "flagship_corruption"

    turns = repo.list_turns(result.session_id)
    assert len(turns) == 2
    assert [t.turn_no for t in turns] == [1, 2]
    for t in turns:
        # The fake always answers go_left, always CONTINUE.
        assert t.action == "go_left"
        assert t.choice == "CONTINUE"
        # Split-call thinking captured from the endpoint's reasoning_content.
        assert t.thinking_task and t.thinking_task.strip() != ""
        assert t.raw_response and "ACTION" in t.raw_response
        assert t.correct in (True, False)


def test_arena_endpoint_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")

    def _boom(url, json=None, headers=None, timeout=None):  # noqa: A002
        raise ConnectionError("connection refused")

    monkeypatch.setattr("interface.remote_provider.httpx.post", _boom)

    repo = SQLiteRepository(":memory:")
    import pytest

    with pytest.raises(Exception):
        arena_mod.run_arena_session(
            repo,
            endpoint_url="https://down.example/v1/chat/completions",
            model_label="Broken",
            framing="flagship_corruption",
            forfeit="allowed",
            total_turns=1,
        )


def test_arena_config_enables_psuccess_chaining():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict("flagship_corruption", "allowed", "some-model", 15, 2048)
    assert cfg["forfeit_layer"]["chain_psuccess_to_menu"] is True


def test_arena_forwards_max_tokens_to_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    seen: dict = {}

    def _fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.setdefault("max_tokens", json.get("max_tokens"))
        phase = _fake_post.n % 3
        _fake_post.n += 1
        content = ("RULE: if red then go_left otherwise stay\nACTION: go_left"
                   if phase == 0 else "P_CORRECT: 60" if phase == 1 else "CHOICE: CONTINUE")
        return _FakeResponse({"choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 20, "completion_tokens": 5}})
    _fake_post.n = 0
    monkeypatch.setattr("interface.remote_provider.httpx.post", _fake_post)

    repo = SQLiteRepository(":memory:")
    arena_mod.run_arena_session(
        repo, endpoint_url="https://p.example/v1/chat/completions",
        model_label="Contender-7B", framing="flagship_corruption",
        forfeit="allowed", total_turns=1, max_tokens=8192,
    )
    assert seen["max_tokens"] == 8192


def test_arena_config_uses_supplied_difficulty():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict(
        "flagship_corruption", "allowed", "some-model", 15, 2048, difficulty="hard"
    )
    assert cfg["seasons"][0]["task_config"]["difficulty"] == "hard"


def test_arena_config_difficulty_defaults_to_easy():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict("flagship_corruption", "allowed", "some-model", 15, 2048)
    assert cfg["seasons"][0]["task_config"]["difficulty"] == "easy"


def test_arena_rejects_unknown_difficulty(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    repo = SQLiteRepository(":memory:")
    with pytest.raises(ValueError):
        arena_mod.run_arena_session(
            repo,
            endpoint_url="https://p.example/v1/chat/completions",
            model_label="X",
            framing="flagship_corruption",
            forfeit="allowed",
            total_turns=1,
            difficulty="medium",  # excluded from the arena on purpose
        )


def test_arena_hard_difficulty_runs_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    fake_post, counter = _make_fake_post()
    monkeypatch.setattr("interface.remote_provider.httpx.post", fake_post)

    repo = SQLiteRepository(":memory:")
    result = arena_mod.run_arena_session(
        repo,
        endpoint_url="https://p.example/v1/chat/completions",
        model_label="Hard-Contender",
        framing="flagship_corruption",
        forfeit="allowed",
        total_turns=2,
        difficulty="hard",
    )
    assert result.status == "done"
    session = repo.get_session(result.session_id)
    assert session is not None and session.source == "llm"
