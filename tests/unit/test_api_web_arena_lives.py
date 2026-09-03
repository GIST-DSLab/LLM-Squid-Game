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


def test_state_surfaces_structured_peer_death_fields(client, api_module) -> None:
    """The rendered notice is accompanied by the event in structured form.

    The web cinematic draws a participant line, so it needs the numbers
    themselves rather than the prose: which participants fell THIS turn,
    how many are down in total, how many are left, and how many there
    were to begin with.
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

    fell = state["peer_death_participants"]
    assert fell, "a fired announcement must name its participants"
    assert all(1 <= p <= 10 for p in fell)
    assert len(set(fell)) == len(fell)
    assert state["cohort_size"] == 10
    assert state["peer_death_cumulative"] == len(fell)
    # remaining excludes the player, so it is cohort - cumulative - 1.
    assert state["peer_death_remaining"] == 10 - len(fell) - 1
    # Same event, two representations: every number named in the structured
    # field also appears in the prose the player reads.
    for p in fell:
        assert f"Participant {p}" in state["peer_death_text"]

    # A re-poll of the same turn must not re-roll or double-count.
    again = client.get("/api/state", params={"session_id": sid}).json()
    assert again["peer_death_participants"] == fell
    assert again["peer_death_cumulative"] == state["peer_death_cumulative"]


def test_state_level_zero_has_no_structured_peer_death(client) -> None:
    """The level-0 control runs no scheduler, so the cinematic can never
    be triggered there: no participants, no cohort to draw."""
    sid = _new_game(client, framing="true_baseline")
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["peer_death_text"] is None
    assert state["peer_death_participants"] == []
    assert state["peer_death_cumulative"] == 0
    assert state["peer_death_remaining"] is None
    assert state["cohort_size"] is None


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


# ---------------------------------------------------------------------------
# Run-settings snapshot (spec 2026-09-03 web-logs-settings, T3)
# ---------------------------------------------------------------------------


def _finish_by_forfeit(client, sid: str) -> None:
    client.get("/api/state", params={"session_id": sid})
    client.post(
        f"/api/action?session_id={sid}",
        json={"action": "forfeit", "probe_answer": "", "reasoning": ""},
    )
    client.get("/api/result", params={"session_id": sid})


def test_log_detail_carries_the_human_settings_snapshot(client) -> None:
    sid = _new_game(client, nickname="settings-player")
    _finish_by_forfeit(client, sid)

    settings = client.get(f"/api/logs/{sid}").json()["session"]["settings"]
    assert settings is not None
    assert settings["runtime"] == "human"
    assert settings["lives_enabled"] is True
    assert settings["lives_total"] == 5
    assert settings["reward_mode"] == "flat"
    assert settings["base_reward"] == 10.0
    assert settings["use_psuccess_probe"] is False
    assert settings["p_death"] == 0.0
    # The NewGameRequest values this game was started with.
    assert settings["task"] == "signal_game"
    assert settings["difficulty"] == "easy"
    assert settings["framing"] == "threat_l2"
    assert settings["forfeit_condition"] == "allowed"
    assert settings["threat_level"] == 2
    assert settings["seed"] == 3
    assert settings["total_turns"] == 20
    assert settings["history_mode"] == "cumulative"
    # A threat rung runs the announcement scheduler, so its knobs are quoted.
    assert settings["peer_death_p_announce"] > 0
    # No provider for a human game.
    assert "model" not in settings and "provider" not in settings


def test_logs_list_carries_the_settings_snapshot(client) -> None:
    """The session list renders a short meta line from the same dict."""
    sid = _new_game(client, nickname="list-player")
    _finish_by_forfeit(client, sid)

    rows = client.get("/api/logs", params={"source": "human"}).json()["sessions"]
    row = next(r for r in rows if r["session_id"] == sid)
    assert row["settings"]["runtime"] == "human"
    assert row["settings"]["difficulty"] == "easy"


def test_baseline_rung_snapshot_omits_the_announcement_knobs(client) -> None:
    """true_baseline runs no peer-elimination scheduler, so quoting its
    probability would describe a mechanic that cannot fire."""
    sid = _new_game(client, nickname="base-player", framing="true_baseline")
    _finish_by_forfeit(client, sid)

    settings = client.get(f"/api/logs/{sid}").json()["session"]["settings"]
    assert settings["threat_level"] == 0
    assert "peer_death_p_announce" not in settings
    assert settings["lives_enabled"] is True


def test_legacy_p_death_game_snapshot_reports_that_mode(client) -> None:
    sid = _new_game(
        client,
        nickname="legacy-player",
        framing="threat_l1",
        lives_enabled=False,
        p_death_constant=0.15,
    )
    _finish_by_forfeit(client, sid)

    settings = client.get(f"/api/logs/{sid}").json()["session"]["settings"]
    assert settings["lives_enabled"] is False
    assert "lives_total" not in settings
    assert settings["reward_mode"] == "calibrated"
    assert settings["p_death"] == 0.15
    assert "peer_death_p_announce" not in settings


def test_sessions_recorded_before_the_snapshot_read_back_as_none(
    client, api_module
) -> None:
    """A legacy row (no snapshot) must serialise as null, not {} — that is
    what makes the frontend show 'settings not recorded'."""
    from squid_store import SessionRecord

    api_module._repository.create_session(
        SessionRecord(
            id="legacy-row",
            nickname="old-player",
            task="signal_game",
            framing="flagship_corruption",
            forfeit="allowed",
            seed=1,
            final_score=30.0,
            forfeited=False,
            source="human",
        )
    )
    detail = client.get("/api/logs/legacy-row").json()
    assert detail["session"]["settings"] is None


def test_settings_snapshot_is_shaped_like_the_seeder_snapshot() -> None:
    """Human and LLM snapshots share one flat key vocabulary — the settings
    panel renders both through the same code path, keyed off `runtime`."""
    from squid_arena.human_game import HumanGameSession
    from squid_arena.seeding import build_settings_snapshot

    game = HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="threat_l3",
        forfeit_condition="allowed",
        seed=11,
        total_turns=12,
    )
    human = game.settings_snapshot()
    llm = build_settings_snapshot(
        {
            "framing": "threat_l3",
            "forfeit_condition": "allowed",
            "task_name": "signal_game",
            "difficulty": "easy",
            "seed": 11,
        },
        None,
    )
    assert human["runtime"] == "human"
    assert llm["runtime"] == "llm"
    shared = set(human) & set(llm)
    assert {"task", "difficulty", "seed", "framing", "forfeit_condition",
            "threat_level", "runtime"} <= shared
    for key in shared - {"runtime"}:
        assert human[key] == llm[key], key
