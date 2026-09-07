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
from squid_game.models.enums import Framing


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
        framing=Framing.THREAT_L3,
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
        framing=Framing.THREAT_L3,
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


def test_campaign_cells_are_three_framings_by_two_forfeits(api_module) -> None:
    """The 6-game campaign: each framing with forfeit blocked, then allowed.

    Order is load-bearing — the frontend's CAMPAIGN_CONDITIONS plays the
    cells in this sequence and the Logs report sorts games by it.
    """
    from squid_arena.rule_schedule import CAMPAIGN_GAME_COUNT

    assert [
        (c["framing"], c["forfeit"]) for c in api_module.CAMPAIGN_CELLS
    ] == [
        ("true_baseline", "not_allowed"),
        ("true_baseline", "allowed"),
        ("baseline_flagship", "not_allowed"),
        ("baseline_flagship", "allowed"),
        ("threat_l3", "not_allowed"),
        ("threat_l3", "allowed"),
    ]
    assert len(api_module.CAMPAIGN_CELLS) == CAMPAIGN_GAME_COUNT
    # The rungs the campaign no longer plays stay renderable for rows
    # recorded under the five-cell ladder / the threat_l2 interim design.
    legacy = {(c["framing"], c["forfeit"]) for c in api_module.LEGACY_REPORT_CELLS}
    assert ("threat_l1", "allowed") in legacy
    assert ("threat_l2", "allowed") in legacy
    assert ("threat_l2", "not_allowed") in legacy


# ---------------------------------------------------------------------------
# Peer-elimination notice on the wire (Task 1) and the campaign's
# off-ladder reward-only cell (Task 3)
# ---------------------------------------------------------------------------


def _first_announce_turn(api_module, seed: int, framing: Framing, turns: int = 20):
    """(turn, event) of the first notice a human game with *seed* schedules.

    Mirrors HumanGameSession's own scheduler construction so the test knows
    which turn to look at without probing private state.
    """
    import random

    from squid_game.models.config import PeerDeathConfig

    cfg = PeerDeathConfig()
    sched = PeerDeathScheduler(
        rng=random.Random(seed ^ api_module.PEER_DEATH_SEED_XOR),
        cohort_size=api_module.PEER_DEATH_COHORT_SIZE,
        p_announce=cfg.p_announce,
        first_turn=cfg.first_turn,
        max_per_turn=cfg.max_per_turn,
        framing=framing,
    )
    for t in range(1, turns + 1):
        ev = sched.advance(t)
        if ev.fired:
            return t, ev
    raise AssertionError(f"seed {seed} never announces within {turns} turns")


def test_state_carries_the_peer_death_notice_on_its_turn(client, api_module) -> None:
    """A threat_l2 game emits peer_death_text + the structured fields on the
    scheduled turn, and nothing before it. This is the contract the frontend
    banner (`.peer-notice`) and cinematic (`_openPeerDeath`) render from."""
    seed = 3
    fire_turn, ev = _first_announce_turn(
        api_module, seed, framing=Framing.THREAT_L2
    )
    sid = _new_game(client, seed=seed, framing="threat_l2", total_turns=20)
    for turn in range(1, fire_turn):
        state = client.get("/api/state", params={"session_id": sid}).json()
        assert state["turn_number"] == turn
        assert state["peer_death_text"] is None
        assert state["peer_death_participants"] == []
        assert state["cohort_size"] == api_module.PEER_DEATH_COHORT_SIZE
        _answer(client, api_module, sid, correct=True)

    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["turn_number"] == fire_turn
    assert state["threat_level"] == 2
    assert state["lives_enabled"] is True
    assert state["peer_death_text"] == ev.text
    assert "NOTICE" in state["peer_death_text"]
    assert state["peer_death_participants"] == list(ev.participants)
    assert state["peer_death_cumulative"] == ev.cumulative
    assert state["peer_death_remaining"] == ev.remaining
    # A second poll of the same turn must not re-roll the schedule.
    again = client.get("/api/state", params={"session_id": sid}).json()
    assert again["peer_death_text"] == state["peer_death_text"]
    assert again["peer_death_participants"] == state["peer_death_participants"]


@pytest.mark.parametrize("framing", ["true_baseline", "baseline_flagship"])
def test_no_threat_cells_never_announce(client, api_module, framing) -> None:
    """Level 0 and the off-ladder reward-only cell run no scheduler: no text,
    no participants and — the frontend's guard — no cohort at all."""
    sid = _new_game(client, seed=3, framing=framing, total_turns=12)
    for _ in range(12):
        state = client.get("/api/state", params={"session_id": sid}).json()
        if state["game_over"]:
            break
        assert state["peer_death_text"] is None
        assert state["peer_death_participants"] == []
        assert state["cohort_size"] is None
        _answer(client, api_module, sid, correct=True)


def test_reward_only_cell_runs_the_lives_mechanic_and_tells_the_player(
    client, api_module
) -> None:
    """baseline_flagship is off the threat ladder (threat_level None) but the
    campaign plays it under the lives mechanic, so the HUD fields must be
    populated and the framing text must state the attempts rule."""
    sid = _new_game(client, seed=3, framing="baseline_flagship", forfeit_condition="not_allowed")
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["threat_level"] is None
    assert state["lives_enabled"] is True
    assert state["lives_remaining"] == 5
    assert state["lives_total"] == 5
    assert state["forfeit_allowed"] is False
    assert "5 attempts" in state["framing_threat"]
    for word in ("life", "lives", "death", "eliminat"):
        assert word not in state["framing_threat"].lower()

    act = _answer(client, api_module, sid, correct=False)
    assert act["life_lost"] is True
    assert act["lives_remaining"] == 4
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["lives_remaining"] == 4
    assert "4 attempts" not in state["framing_threat"]  # the sentence states the total
    assert "5 attempts" in state["framing_threat"]


def test_every_campaign_cell_starts_a_game(client, api_module) -> None:
    for i, cell in enumerate(api_module.CAMPAIGN_CELLS):
        sid = _new_game(
            client,
            nickname="cells",
            framing=cell["framing"],
            forfeit_condition=cell["forfeit"],
            campaign_id="cells-campaign",
            campaign_index=i,
        )
        state = client.get("/api/state", params={"session_id": sid}).json()
        assert state["turn_number"] == 1
        assert state["lives_remaining"] == 5
        assert state["forfeit_allowed"] is (cell["forfeit"] == "allowed")


# ---------------------------------------------------------------------------
# Campaign game boundary (Task 2): game 2 starts after game 1 is persisted
# ---------------------------------------------------------------------------


def test_second_campaign_game_starts_after_first_is_finished_and_persisted(
    client, api_module
) -> None:
    """The exact sequence the frontend runs at the game-1 → game-2 boundary:
    new_game(index 0) → play out → GET /api/result (persists the row and
    the player) → new_game(index 1, same campaign / nickname / password) →
    GET /api/state. Every hop must answer 200."""
    cid = "boundary-campaign"
    sid1 = _new_game(
        client, nickname="boundary", framing="true_baseline",
        forfeit_condition="not_allowed", campaign_id=cid, campaign_index=0,
        total_turns=10,
    )
    for _ in range(5):  # five misses: eliminated, exactly as a lost game 1 ends
        _answer(client, api_module, sid1, correct=False)
    res = client.get("/api/result", params={"session_id": sid1})
    assert res.status_code == 200, res.text
    assert res.json()["eliminated"] is True

    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game", "difficulty": "easy",
            "framing": "true_baseline", "forfeit_condition": "allowed",
            "nickname": "boundary", "password": "pw",
            "campaign_id": cid, "campaign_index": 1, "num_few_shot": 2,
        },
    )
    assert resp.status_code == 200, resp.text
    sid2 = resp.json()["session_id"]
    assert sid2 != sid1
    state = client.get("/api/state", params={"session_id": sid2})
    assert state.status_code == 200, state.text
    assert state.json()["turn_number"] == 1
    assert state.json()["lives_remaining"] == 5
    assert api_module._campaigns[sid2] == cid
    # A wrong password on game 2 is a real 403 with a message, not a crash.
    bad = client.post(
        "/api/new_game",
        json={
            "framing": "true_baseline", "forfeit_condition": "allowed",
            "nickname": "boundary", "password": "wrong",
            "campaign_id": cid, "campaign_index": 1,
        },
    )
    assert bad.status_code == 403
    assert bad.json()["detail"]


# ---------------------------------------------------------------------------
# Difficulty (Task 4): the four engine levels are all playable by a human
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "expert"])
def test_new_game_accepts_every_engine_difficulty(client, api_module, difficulty) -> None:
    sid = _new_game(client, nickname="diff", difficulty=difficulty, num_few_shot=None)
    state = client.get("/api/state", params={"session_id": sid})
    assert state.status_code == 200, state.text
    assert api_module._sessions[sid]._difficulty.value == difficulty
    assert api_module._sessions[sid].settings_snapshot()["difficulty"] == difficulty
    # Any answer resolves: the level's rule-space is wired end to end.
    _answer(client, api_module, sid, correct=True)


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
