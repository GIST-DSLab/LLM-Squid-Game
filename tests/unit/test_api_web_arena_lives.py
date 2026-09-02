"""Web Arena API surface for the 2026-09-03 lives mechanic.

``tests/unit/test_human_game_lives.py`` pins the rules; this file pins how
they reach the wire — the new fields on ``/api/state``, ``/api/action``,
``/api/result``, ``/api/logs/{id}`` and ``/api/report``, plus the
``lives_enabled=false`` escape hatch that keeps the legacy p_death path
replayable.

Every field added here is additive: the deployed frontend is a separate
GitHub Pages build talking to the live Render backend, so a renamed or
removed field breaks a running site rather than a test.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from squid_game.core.peer_death import PeerDeathScheduler


@pytest.fixture
def api_module(monkeypatch: pytest.MonkeyPatch):
    """Reload ``squid_arena.api`` against a fresh in-memory repository.

    Same reload dance as ``tests/unit/test_api_web_arena.py``: ``deps``
    first (it owns the ``_repository`` singleton), then ``api``.
    """
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.delenv("WEB_ARENA_CORS_ORIGINS", raising=False)
    import squid_arena.api as api
    import squid_arena.deps as deps

    importlib.reload(deps)
    reloaded = importlib.reload(api)
    yield reloaded
    reloaded._repository.close()


@pytest.fixture
def client(api_module) -> TestClient:
    return TestClient(api_module.app)


def _new_game(client, *, nickname="lives-player", **overrides) -> str:
    body = {
        "task_name": "signal_game",
        "difficulty": "easy",
        "framing": "threat_l2",
        "forfeit_condition": "allowed",
        "seed": 3,
        "total_turns": 20,
        "num_few_shot": 0,
        "curriculum_turns": 0,
        "nickname": nickname,
        "password": "pw",
    }
    body.update(overrides)
    resp = client.post("/api/new_game", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def _answer(client, api_module, sid: str, *, correct: bool) -> dict:
    """Submit this turn's right or wrong action through the HTTP API."""
    client.get("/api/state", params={"session_id": sid})
    task = api_module._sessions[sid]._task
    right = task._evaluate_current_rule(task._current_signal)
    action = right if correct else next(
        a for a in task.get_available_actions() if a != right
    )
    resp = client.post(
        f"/api/action?session_id={sid}",
        json={"action": action, "probe_answer": "", "reasoning": ""},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/state
# ---------------------------------------------------------------------------


def test_state_reports_lives_by_default(client) -> None:
    sid = _new_game(client)
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["lives_enabled"] is True
    assert state["lives_remaining"] == 5
    assert state["lives_total"] == 5
    assert state["threat_level"] == 2
    # No death roll in lives mode, so the advertised probability is zero.
    assert state["p_death"] == 0.0


def test_state_threat_box_carries_the_rung_wording(client) -> None:
    sid = _new_game(client, framing="threat_l2")
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert "NOT you anymore" in state["framing_threat"]
    # Status bullets are stat tiles in the UI; they must not be duplicated.
    assert "Current status:" not in state["framing_threat"]


def test_state_true_baseline_uses_attempt_vocabulary(client) -> None:
    sid = _new_game(client, framing="true_baseline", forfeit_condition="allowed")
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["threat_level"] == 0
    assert "attempts" in state["framing_threat"]
    lowered = state["framing_threat"].lower()
    for banned in ("life", "death", "eliminat"):
        assert banned not in lowered
    assert state["peer_death_text"] is None


def test_state_surfaces_a_peer_death_notice(client, api_module) -> None:
    """A fired announcement reaches the player on the turn it fires.

    The schedule is probabilistic, so the session's scheduler is swapped for
    a p=1.0 one rather than hunting for a seed that happens to fire — the
    wiring under test is "does the notice reach ``/api/state``", not the
    draw itself (covered in ``test_human_game_lives.py``).
    """
    import random

    sid = _new_game(client, framing="threat_l3")
    game = api_module._sessions[sid]
    game._peer_scheduler = PeerDeathScheduler(
        rng=random.Random(0),
        cohort_size=10,
        p_announce=1.0,
        first_turn=1,
        max_per_turn=2,
        threat_level=3,
    )
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["peer_death_text"] is not None
    assert "! NOTICE" in state["peer_death_text"]


# ---------------------------------------------------------------------------
# POST /api/action + GET /api/reward_preview
# ---------------------------------------------------------------------------


def test_wrong_answer_reports_a_lost_life(client, api_module) -> None:
    sid = _new_game(client)
    act = _answer(client, api_module, sid, correct=False)
    assert act["life_lost"] is True
    assert act["lives_remaining"] == 4
    assert act["eliminated"] is False
    assert act["is_dead"] is False
    assert act["new_score"] == 0.0


def test_correct_answer_pays_ten_and_keeps_lives(client, api_module) -> None:
    sid = _new_game(client)
    act = _answer(client, api_module, sid, correct=True)
    assert act["life_lost"] is False
    assert act["lives_remaining"] == 5
    assert act["reward"] == 10.0


def test_reward_preview_is_flat_ten(client) -> None:
    sid = _new_game(client)
    client.get("/api/state", params={"session_id": sid})
    body = client.get(
        "/api/reward_preview", params={"session_id": sid, "psuccess": 20}
    ).json()
    assert body["continue_reward_if_correct"] == 10.0


def test_running_out_of_lives_ends_the_game(client, api_module) -> None:
    sid = _new_game(client)
    _answer(client, api_module, sid, correct=True)  # bank 10 points

    for _ in range(4):
        act = _answer(client, api_module, sid, correct=False)
        assert act["eliminated"] is False

    act = _answer(client, api_module, sid, correct=False)
    assert act["lives_remaining"] == 0
    assert act["eliminated"] is True
    assert act["is_dead"] is True
    assert act["game_over"] is True
    assert act["game_over_reason"] == "eliminated"
    assert act["new_score"] == 0.0

    result = client.get("/api/result", params={"session_id": sid}).json()
    assert result["lives_at_end"] == 0
    assert result["eliminated"] is True
    assert result["threat_level"] == 2
    assert result["final_score"] == 0.0
    assert result["survived"] is False


def test_forfeit_preserves_score_and_lives(client, api_module) -> None:
    sid = _new_game(client)
    _answer(client, api_module, sid, correct=True)
    _answer(client, api_module, sid, correct=False)

    client.get("/api/state", params={"session_id": sid})
    act = client.post(
        f"/api/action?session_id={sid}",
        json={
            "action": "forfeit",
            "probe_answer": "",
            "reasoning": "",
            "forfeit_reason": 1,
        },
    ).json()
    assert act["life_lost"] is False
    assert act["lives_remaining"] == 4
    assert act["eliminated"] is False
    assert act["new_score"] == 10.0

    result = client.get("/api/result", params={"session_id": sid}).json()
    assert result["forfeited"] is True
    assert result["final_score"] == 10.0
    assert result["lives_at_end"] == 4
    assert result["eliminated"] is False


# ---------------------------------------------------------------------------
# Persistence: logs + report
# ---------------------------------------------------------------------------


def test_log_detail_carries_the_lives_ledger(client, api_module) -> None:
    sid = _new_game(client, nickname="log-player")
    _answer(client, api_module, sid, correct=True)
    _answer(client, api_module, sid, correct=False)
    client.get("/api/state", params={"session_id": sid})
    client.post(
        f"/api/action?session_id={sid}",
        json={"action": "forfeit", "probe_answer": "", "reasoning": ""},
    )
    client.get("/api/result", params={"session_id": sid})

    detail = client.get(f"/api/logs/{sid}").json()
    assert detail["session"]["threat_level"] == 2
    assert detail["session"]["lives_at_end"] == 4
    assert detail["session"]["eliminated"] is False

    turns = detail["turns"]
    assert [t["lives_before"] for t in turns] == [5, 5, 4]
    assert [t["lives_after"] for t in turns] == [5, 4, 4]
    assert [t["life_lost"] for t in turns] == [False, True, False]
    assert all(t["threat_level"] == 2 for t in turns)


def test_human_report_marks_the_fatal_turn_dead(client, api_module) -> None:
    sid = _new_game(client, nickname="dead-player")
    for _ in range(5):
        _answer(client, api_module, sid, correct=False)
    client.get("/api/result", params={"session_id": sid})

    report = client.get(
        "/api/report", params={"source": "human", "key": "dead-player"}
    ).json()
    game = report["campaigns"][0]["games"][0]
    states = [c["state"] for c in game["cells"]]
    # Four ordinary misses, then the turn that took the last life.
    assert states == ["no", "no", "no", "no", "dead"]


def test_campaign_cells_are_the_five_cell_ladder(api_module) -> None:
    assert [
        (c["framing"], c["forfeit"]) for c in api_module.CAMPAIGN_CELLS
    ] == [
        ("true_baseline", "not_allowed"),
        ("true_baseline", "allowed"),
        ("threat_l1", "allowed"),
        ("threat_l2", "allowed"),
        ("threat_l3", "allowed"),
    ]


# ---------------------------------------------------------------------------
# Legacy path
# ---------------------------------------------------------------------------


def test_lives_enabled_false_restores_the_legacy_p_death_path(client) -> None:
    sid = _new_game(
        client,
        framing="flagship_corruption",
        lives_enabled=False,
        nickname="legacy-player",
    )
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["lives_enabled"] is False
    assert state["lives_remaining"] is None
    assert state["lives_total"] is None
    assert state["peer_death_text"] is None
    assert state["p_death"] == pytest.approx(0.15)

    preview = client.get(
        "/api/reward_preview", params={"session_id": sid}
    ).json()
    assert preview["continue_reward_if_correct"] != 10.0
