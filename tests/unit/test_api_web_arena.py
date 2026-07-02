"""Smoke tests for the Web Arena backend API extension (WP2).

Offline and deterministic: every test points ``WEB_ARENA_DSN`` at a fresh
in-memory SQLite repository (via ``importlib.reload``), so nothing hits a
network or leaks state between tests. These are the "does it actually
work" checks the WP2 brief asks for (app imports, routes register, a
couple of FastAPI TestClient round trips) — the heavier endpoint
integration matrix is WP6's job.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module(monkeypatch: pytest.MonkeyPatch):
    """Reload ``interface.api`` against a fresh in-memory repository."""
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.delenv("WEB_ARENA_CORS_ORIGINS", raising=False)
    import interface.api as api

    return importlib.reload(api)


@pytest.fixture
def client(api_module) -> TestClient:
    return TestClient(api_module.app)


def _play_two_turn_game(
    client: TestClient, nickname: str | None = "Ally"
) -> tuple[str, dict]:
    """Drive a short (total_turns=2, no death) signal_game session to completion."""
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "difficulty": "easy",
            "framing": "flagship_corruption",
            "forfeit_condition": "allowed",
            "seed": 1,
            "total_turns": 2,
            "actual_death": False,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": nickname,
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    state = {}
    for _ in range(3):
        state = client.get("/api/state", params={"session_id": session_id}).json()
        if state["game_over"]:
            break
        action = state["available_actions"][0]
        act_resp = client.post(
            f"/api/action?session_id={session_id}",
            json={"action": action, "probe_answer": "", "reasoning": "thinking about it"},
        )
        assert act_resp.status_code == 200
    return session_id, state


# ---------------------------------------------------------------------------
# App import / route registration
# ---------------------------------------------------------------------------


def test_app_imports_and_registers_all_endpoints(api_module) -> None:
    paths = {r.path for r in api_module.app.routes if hasattr(r, "path")}
    for expected in [
        "/api/new_game",
        "/api/state",
        "/api/action",
        "/api/result",
        "/api/leaderboard/models",
        "/api/leaderboard/play",
        "/api/logs",
        "/api/logs/{session_id}",
    ]:
        assert expected in paths, f"missing route: {expected}"


# ---------------------------------------------------------------------------
# Nickname sanitization
# ---------------------------------------------------------------------------


def test_sanitize_nickname_strips_control_chars_collapses_whitespace_caps_length(
    api_module,
) -> None:
    assert api_module.sanitize_nickname(None) == "Anonymous"
    assert api_module.sanitize_nickname("") == "Anonymous"
    assert api_module.sanitize_nickname("   ") == "Anonymous"
    # \x07 and \t are both control chars and get stripped outright (not
    # just collapsed as whitespace).
    assert api_module.sanitize_nickname("a\x07b\tc") == "abc"
    # A run of ordinary spaces, however, does get collapsed to one.
    assert api_module.sanitize_nickname("a   b    c") == "a b c"
    assert api_module.sanitize_nickname("x" * 50) == "x" * 32


def test_new_game_accepts_nickname_and_legacy_callers_still_work(client: TestClient) -> None:
    resp = client.post("/api/new_game", json={"nickname": "  weird\tnick\x07  "})
    assert resp.status_code == 200

    # A caller that predates the nickname field (no key at all) must still work.
    legacy_resp = client.post("/api/new_game", json={})
    assert legacy_resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------


def test_cors_origins_default_list_is_non_empty(api_module) -> None:
    assert api_module._cors_origins() == api_module._DEFAULT_CORS_ORIGINS
    assert len(api_module._cors_origins()) > 0


def test_cors_origins_reads_env_var_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("WEB_ARENA_CORS_ORIGINS", "https://example.com, https://foo.bar")
    import interface.api as api

    reloaded = importlib.reload(api)
    assert reloaded._cors_origins() == ["https://example.com", "https://foo.bar"]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_after_threshold(
    client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_module, "_RATE_LIMIT_MAX", 2)
    for _ in range(2):
        resp = client.post("/api/new_game", json={})
        assert resp.status_code == 200
    blocked = client.post("/api/new_game", json={})
    assert blocked.status_code == 429


# ---------------------------------------------------------------------------
# Result persistence (idempotent)
# ---------------------------------------------------------------------------


def test_result_persists_session_and_turns_idempotently(client: TestClient, api_module) -> None:
    session_id, state = _play_two_turn_game(client, nickname="Ally")
    assert state["game_over"] is True

    resp = client.get("/api/result", params={"session_id": session_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id

    record = api_module._repository.get_session(session_id)
    assert record is not None
    assert record.nickname == "Ally"
    assert record.source == "human"
    assert record.task == "signal_game"
    assert record.framing == "flagship_corruption"

    turns = api_module._repository.list_turns(session_id)
    assert len(turns) == 2
    assert [t.turn_no for t in turns] == [1, 2]

    # Calling /api/result again (e.g. a frontend poll) must not duplicate rows.
    resp2 = client.get("/api/result", params={"session_id": session_id})
    assert resp2.status_code == 200
    assert len(api_module._repository.list_turns(session_id)) == 2
    assert len(api_module._repository.list_sessions(source="human")) == 1


# ---------------------------------------------------------------------------
# New read endpoints
# ---------------------------------------------------------------------------


def test_leaderboard_play_returns_sessions_for_default_arena(
    client: TestClient, api_module
) -> None:
    session_id, _ = _play_two_turn_game(client, nickname="Bob")
    client.get("/api/result", params={"session_id": session_id})

    resp = client.get(
        "/api/leaderboard/play", params={"task": "signal_game", "framing": "flagship_corruption"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task"] == "signal_game"
    assert body["framing"] == "flagship_corruption"
    assert any(row["session_id"] == session_id for row in body["rows"])


def test_leaderboard_models_groups_open_closed_sorted_by_beta_descending(
    client: TestClient, api_module
) -> None:
    from interface.persistence import ModelStatsRecord

    api_module._repository.upsert_model_stats(
        ModelStatsRecord(
            model_label="Model-A",
            mediation_class="open",
            beta_framing_is_FC=0.9,
            hr_FC_3cov=2.0,
            hr_FC_ci_low=1.1,
            hr_FC_ci_high=3.0,
            p_FC=0.01,
            pct_attenuation=10.0,
            n_sessions=30,
        )
    )
    api_module._repository.upsert_model_stats(
        ModelStatsRecord(
            model_label="Model-B",
            mediation_class="open",
            beta_framing_is_FC=1.5,
            hr_FC_3cov=3.0,
            hr_FC_ci_low=2.0,
            hr_FC_ci_high=4.0,
            p_FC=0.02,
            pct_attenuation=5.0,
            n_sessions=30,
        )
    )
    api_module._repository.upsert_model_stats(
        ModelStatsRecord(
            model_label="Model-C",
            mediation_class="closed",
            beta_framing_is_FC=0.3,
            hr_FC_3cov=1.1,
            hr_FC_ci_low=0.9,
            hr_FC_ci_high=1.3,
            p_FC=0.4,
            pct_attenuation=80.0,
            n_sessions=30,
        )
    )

    resp = client.get("/api/leaderboard/models")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["model_label"] for r in body["open"]] == ["Model-B", "Model-A"]
    assert [r["model_label"] for r in body["closed"]] == ["Model-C"]


def test_leaderboard_models_empty_returns_empty_groups_not_error(client: TestClient) -> None:
    resp = client.get("/api/leaderboard/models")
    assert resp.status_code == 200
    assert resp.json() == {"open": [], "closed": []}


def test_logs_lists_sessions_and_detail_returns_turn_trace(
    client: TestClient, api_module
) -> None:
    session_id, _ = _play_two_turn_game(client, nickname="Carl")
    client.get("/api/result", params={"session_id": session_id})

    resp = client.get("/api/logs")
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert any(s["session_id"] == session_id for s in sessions)

    detail = client.get(f"/api/logs/{session_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["session"]["session_id"] == session_id
    assert body["session"]["nickname"] == "Carl"
    assert len(body["turns"]) == 2
    assert body["turns"][0]["turn_no"] == 1


def test_logs_detail_404_for_unknown_session(client: TestClient) -> None:
    resp = client.get("/api/logs/does-not-exist")
    assert resp.status_code == 404
