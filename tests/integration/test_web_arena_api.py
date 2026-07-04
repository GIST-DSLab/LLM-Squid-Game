"""Integration tests for the Web Arena backend (WP6).

Exercises ``interface/api.py`` (WP2) end-to-end through FastAPI's
``TestClient`` against a fresh temp-file SQLite DB per test (never a
network, never a shared/real DB). Complements WP2's own smoke suite
(``tests/unit/test_api_web_arena.py``) with deeper, spec-shaped coverage
of the four new read endpoints plus result persistence, following the
brief's coverage list:

    - result persistence (full API play-through, idempotent, server-side
      scoring)
    - GET /api/leaderboard/models (Open/Closed grouping, full field shape,
      β-descending sort)
    - GET /api/logs + GET /api/logs/{id} (human + llm sources, turn trace,
      404)

The ``WEB_ARENA_DSN`` env var must be set *before* ``interface.api`` is
imported (it builds a module-level ``_repository`` singleton at import
time) — every test uses the ``api_module`` fixture, which sets the env var
and then ``importlib.reload``s the module, mirroring the pattern in
``tests/unit/test_api_web_arena.py``.

For the one scenario that needs a real ``source='llm'`` session (the logs
test), a full LLM season is driven through ``ExperimentRunner`` with the
offline ``StubProvider`` (``tests/integration/conftest.py``) and then
imported into the same repository via ``scripts/seed_web_arena.py``'s
helpers — the same code path production seeding uses — so the turn trace
asserted against is genuine engine output, not a hand-rolled fixture.
"""

from __future__ import annotations

import importlib
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from interface.persistence import ModelStatsRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_module(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Reload ``interface.api`` against a fresh temp-file SQLite DB.

    A distinct ``tmp_path`` per test gives full isolation without relying on
    ``:memory:`` semantics — this is a real (if throwaway) SQLite file that
    is deleted along with the rest of pytest's tmp dir.
    """
    dsn = str(tmp_path / "web_arena_test.db")
    monkeypatch.setenv("WEB_ARENA_DSN", dsn)
    monkeypatch.delenv("WEB_ARENA_CORS_ORIGINS", raising=False)
    import interface.api as api

    reloaded = importlib.reload(api)
    yield reloaded
    reloaded._repository.close()


@pytest.fixture
def client(api_module) -> TestClient:
    return TestClient(api_module.app)


def _play_game(
    client: TestClient,
    *,
    nickname: str = "Ally",
    task_name: str = "signal_game",
    framing: str = "flagship_corruption",
    forfeit_condition: str = "allowed",
    seed: int = 1,
    total_turns: int = 2,
) -> tuple[str, dict]:
    """Drive a short, death-free signal_game session to completion via the
    public API only (new_game -> state/action loop -> final state)."""
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": task_name,
            "difficulty": "easy",
            "framing": framing,
            "forfeit_condition": forfeit_condition,
            "seed": seed,
            "total_turns": total_turns,
            "actual_death": False,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": nickname,
            "password": "pw",
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    state: dict = {}
    for _ in range(total_turns + 1):
        state = client.get("/api/state", params={"session_id": session_id}).json()
        if state["game_over"]:
            break
        action = state["available_actions"][0]
        act_resp = client.post(
            f"/api/action?session_id={session_id}",
            json={"action": action, "probe_answer": "", "reasoning": "some reasoning text"},
        )
        assert act_resp.status_code == 200
    return session_id, state


# ---------------------------------------------------------------------------
# Result persistence: full API play-through
# ---------------------------------------------------------------------------


def test_result_persistence_writes_session_and_turns_and_scoring_is_server_side(
    client: TestClient, api_module
) -> None:
    """Play a full game via the API only; assert a sessions row + its turns
    rows land in the DB with the score the server actually computed —
    the client never has any way to submit a final score."""
    # Neither request model lets a client dictate the outcome score: the
    # per-turn ActionRequest has no score-like field at all, and while
    # NewGameRequest legitimately exposes *starting* config knobs
    # (starting_score / score_floor -- arena setup, not a result), neither
    # request model exposes a "final_score" field. This is the structural
    # guarantee behind "the client never sends a final score", not just a
    # behavioural coincidence.
    assert not any("score" in f.lower() for f in api_module.ActionRequest.model_fields)
    for model_cls in (api_module.NewGameRequest, api_module.ActionRequest):
        assert "final_score" not in model_cls.model_fields

    session_id, state = _play_game(client, nickname="Ally", total_turns=2)
    assert state["game_over"] is True

    result_resp = client.get("/api/result", params={"session_id": session_id})
    assert result_resp.status_code == 200
    server_final_score = result_resp.json()["final_score"]

    record = api_module._repository.get_session(session_id)
    assert record is not None
    assert record.id == session_id
    assert record.nickname == "Ally"
    assert record.task == "signal_game"
    assert record.framing == "flagship_corruption"
    assert record.forfeit == "allowed"
    assert record.source == "human"
    # The persisted score is exactly the server-computed final_score —
    # nothing the client sent in /api/action or /api/new_game feeds it.
    assert record.final_score == server_final_score

    turns = api_module._repository.list_turns(session_id)
    assert len(turns) == 2
    assert [t.turn_no for t in turns] == [1, 2]
    for t in turns:
        assert t.session_id == session_id
        assert isinstance(t.score, float)


def test_result_extra_client_supplied_score_field_is_ignored(
    client: TestClient, api_module
) -> None:
    """Even if a rogue client stuffs an unexpected 'final_score' key into the
    /api/action body, it must not influence the persisted score — the
    server is the single source of truth for scoring."""
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game", "difficulty": "easy", "total_turns": 1, "seed": 3,
            "nickname": "rogue-tester", "password": "pw",
        },
    )
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    action = state["available_actions"][0]

    # Extra, unrecognised field alongside the real action payload.
    act_resp = client.post(
        f"/api/action?session_id={session_id}",
        json={
            "action": action,
            "probe_answer": "",
            "reasoning": "x",
            "final_score": 999999.0,
            "score": 999999.0,
        },
    )
    assert act_resp.status_code == 200

    result = client.get("/api/result", params={"session_id": session_id}).json()
    assert result["final_score"] != 999999.0

    record = api_module._repository.get_session(session_id)
    assert record.final_score == result["final_score"]
    assert record.final_score != 999999.0


def test_result_repeated_polling_never_500s_and_does_not_double_insert(
    client: TestClient, api_module
) -> None:
    """A frontend polling /api/result until game-over, then again out of
    habit, must never 500 and must never duplicate rows."""
    session_id, state = _play_game(client, nickname="Bob", total_turns=2)
    assert state["game_over"] is True

    responses = [
        client.get("/api/result", params={"session_id": session_id}) for _ in range(4)
    ]
    for r in responses:
        assert r.status_code == 200

    bodies = [r.json() for r in responses]
    assert all(b["final_score"] == bodies[0]["final_score"] for b in bodies)
    assert all(b["session_id"] == session_id for b in bodies)

    assert len(api_module._repository.list_sessions(source="human")) == 1
    assert len(api_module._repository.list_turns(session_id)) == 2


# ---------------------------------------------------------------------------
# GET /api/leaderboard/models
# ---------------------------------------------------------------------------


def test_leaderboard_models_full_row_shape_and_beta_descending_sort(
    client: TestClient, api_module
) -> None:
    """Four models seeded via the WP1 repository directly — assert exact row
    shape (incl. the per-channel SD flags) and a single β-descending ranking
    (no open/closed grouping)."""
    rows_in = [
        ModelStatsRecord(
            model_label="Beta-0.9-open",
            mediation_class="open",
            beta_framing_is_FC=0.9,
            hr_FC_3cov=2.0,
            hr_FC_ci_low=1.1,
            hr_FC_ci_high=3.0,
            p_FC=0.01,
            pct_attenuation=10.0,
            n_sessions=30,
            sd_behavior_pass=True,
            sd_verbal_pass=True,
            sd_cognitive_pass=False,
        ),
        ModelStatsRecord(
            model_label="Beta-1.5-open",
            mediation_class="open",
            beta_framing_is_FC=1.5,
            hr_FC_3cov=3.0,
            hr_FC_ci_low=2.0,
            hr_FC_ci_high=4.0,
            p_FC=0.02,
            pct_attenuation=5.0,
            n_sessions=45,
            sd_behavior_pass=True,
            sd_verbal_pass=False,
            sd_cognitive_pass=True,
        ),
        ModelStatsRecord(
            model_label="Beta-0.1-closed",
            mediation_class="closed",
            beta_framing_is_FC=0.1,
            hr_FC_3cov=1.05,
            hr_FC_ci_low=0.8,
            hr_FC_ci_high=1.3,
            p_FC=0.4,
            pct_attenuation=90.0,
            n_sessions=20,
        ),
        ModelStatsRecord(
            model_label="Beta-0.3-closed",
            mediation_class="closed",
            beta_framing_is_FC=0.3,
            hr_FC_3cov=1.1,
            hr_FC_ci_low=0.9,
            hr_FC_ci_high=1.3,
            p_FC=0.35,
            pct_attenuation=80.0,
            n_sessions=25,
        ),
    ]
    for row in rows_in:
        api_module._repository.upsert_model_stats(row)

    resp = client.get("/api/leaderboard/models")
    assert resp.status_code == 200
    body = resp.json()

    # One flat list, ranked purely by β descending across all models.
    assert list(body.keys()) == ["models"]
    assert [r["model_label"] for r in body["models"]] == [
        "Beta-1.5-open", "Beta-0.9-open", "Beta-0.3-closed", "Beta-0.1-closed",
    ]

    by_label = {r["model_label"]: r for r in body["models"]}
    expected = {r.model_label: r for r in rows_in}
    for label, exp in expected.items():
        got = by_label[label]
        assert got["mediation_class"] == exp.mediation_class
        assert got["beta_framing_is_FC"] == pytest.approx(exp.beta_framing_is_FC)
        assert got["hr_FC_3cov"] == pytest.approx(exp.hr_FC_3cov)
        assert got["hr_FC_ci_low"] == pytest.approx(exp.hr_FC_ci_low)
        assert got["hr_FC_ci_high"] == pytest.approx(exp.hr_FC_ci_high)
        assert got["p_FC"] == pytest.approx(exp.p_FC)
        assert got["pct_attenuation"] == pytest.approx(exp.pct_attenuation)
        assert got["n_sessions"] == exp.n_sessions
        assert got["sd_behavior_pass"] == exp.sd_behavior_pass
        assert got["sd_verbal_pass"] == exp.sd_verbal_pass
        assert got["sd_cognitive_pass"] == exp.sd_cognitive_pass
        assert got["p_reason_survival"] is None
        assert got["no_cap_avg_turn_score"] is None
        # Full field set, nothing invented, nothing missing.
        assert set(got.keys()) == {
            "model_label",
            "mediation_class",
            "beta_framing_is_FC",
            "hr_FC_3cov",
            "hr_FC_ci_low",
            "hr_FC_ci_high",
            "p_FC",
            "pct_attenuation",
            "n_sessions",
            "sd_behavior_pass",
            "sd_verbal_pass",
            "sd_cognitive_pass",
            "p_reason_survival",
            "no_cap_avg_turn_score",
        }


def test_leaderboard_models_empty_db_returns_empty_list_with_200(
    client: TestClient,
) -> None:
    resp = client.get("/api/leaderboard/models")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}


# ---------------------------------------------------------------------------
# GET /api/logs + GET /api/logs/{session_id}
# ---------------------------------------------------------------------------


_LLM_SEASON_YAML: dict = {
    "name": "wp6_logs_e2e_smoke",
    "description": "WP6 integration smoke: a real StubProvider-driven LLM season for logs coverage",
    "num_repetitions": 1,
    "output_dir": "outputs",
    "parallel_workers": 1,
    "use_unified_turn": True,
    "use_forfeit_layer": True,
    "use_split_forfeit_layer": True,
    "forfeit_layer": {
        "p_death": 0.25,
        "p_success_estimate": 0.75,
        "base_reward": 10.0,
        "split_context_level": "medium",
    },
    "seasons": [
        {
            "cell_id": 1,
            "framing": "flagship_corruption",
            "forfeit_condition": "allowed",
            "p_death_override": 0.25,
            "agent_type": "vanilla",
            "task_config": {
                "task_name": "signal_game",
                "difficulty": "easy",
                "total_turns": 2,
                "seed": 42,
                "history_mode": "cumulative",
                "max_history_turns": 15,
                "actual_death": False,
                "num_few_shot": 1,
                "curriculum_turns": 1,
                "starting_score": 30.0,
            },
            "provider_config": {
                "provider": "openai",
                "model": "stub-wp6",
                "temperature": 0.0,
                "max_tokens": 512,
            },
        }
    ],
}


def _alternating_split_response(idx: int, _messages: list[dict[str, str]]) -> str:
    """Call 1 (task) / Call 2 (forfeit) canned split-call responses; turn 1
    continues, turn 2 forfeits with a REASON digit so ``choice`` is non-null
    on at least one turn."""
    if idx % 2 == 0:
        return "RULE: if the signal is red go_left otherwise stay\nACTION: go_left"
    turn_index = idx // 2
    if turn_index == 0:
        return "CHOICE: CONTINUE"
    return "CHOICE: FORFEIT\nREASON: 1"


def _seed_one_llm_session(
    api_module, patch_runner_provider, tmp_path
) -> str:
    """Run one real LLM season through ExperimentRunner + StubProvider and
    import it into ``api_module._repository`` via the WP3 seed script's
    helpers — the same path production seeding uses. Returns the session id
    (== the engine's ``season_id``)."""
    from squid_game.runner import ExperimentRunner, load_config_from_yaml
    from scripts.seed_web_arena import seed_sessions

    yaml_path = tmp_path / "wp6_llm_season.yaml"
    yaml_path.write_text(yaml.safe_dump(_LLM_SEASON_YAML), encoding="utf-8")
    config = load_config_from_yaml(str(yaml_path))
    run_root = tmp_path / "llm_run"
    config = config.model_copy(update={"output_dir": str(run_root)})

    patch_runner_provider(response_fn=_alternating_split_response, thinking_tokens=15)

    runner = ExperimentRunner(config)
    runner.run()

    run_dirs = [p for p in run_root.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    n_inserted, _n_skipped, n_turns = seed_sessions(
        api_module._repository, run_root, {"Stub-Model": run_dir.name}
    )
    assert n_inserted == 1
    assert n_turns == 2

    season = json.loads(
        (run_dir / "season_results.jsonl").read_text().strip().splitlines()[0]
    )
    return season["season_id"]


def test_logs_lists_both_sources_newest_first_and_detail_matches_engine_turn_trace(
    client: TestClient, api_module, patch_runner_provider, tmp_path
) -> None:
    # 1. A real LLM session (source='llm'), imported via the WP3 seed helper
    #    from an actual StubProvider-driven ExperimentRunner run.
    llm_session_id = _seed_one_llm_session(api_module, patch_runner_provider, tmp_path)

    # 2. A human session played through the public API (source='human'),
    #    started after the LLM one so it is newer.
    human_session_id, state = _play_game(client, nickname="Carl", total_turns=2)
    assert state["game_over"] is True
    client.get("/api/result", params={"session_id": human_session_id})

    # -- GET /api/logs (no filters): both sources present, newest-first. --
    resp = client.get("/api/logs")
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    ids = [s["session_id"] for s in sessions]
    assert llm_session_id in ids
    assert human_session_id in ids
    sources = {s["session_id"]: s["source"] for s in sessions}
    assert sources[llm_session_id] == "llm"
    assert sources[human_session_id] == "human"
    # The human session was created after the LLM one -> newest-first means
    # it must appear earlier in the list.
    assert ids.index(human_session_id) < ids.index(llm_session_id)

    # -- source filter narrows correctly. --
    llm_only = client.get("/api/logs", params={"source": "llm"}).json()["sessions"]
    assert all(s["source"] == "llm" for s in llm_only)
    assert any(s["session_id"] == llm_session_id for s in llm_only)
    assert all(s["session_id"] != human_session_id for s in llm_only)

    # -- GET /api/logs/{id} for the LLM session: full turn trace fields. --
    detail = client.get(f"/api/logs/{llm_session_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["session"]["session_id"] == llm_session_id
    assert body["session"]["source"] == "llm"
    assert body["session"]["nickname"] == "Stub-Model"
    turns = body["turns"]
    assert len(turns) == 2
    assert [t["turn_no"] for t in turns] == [1, 2]
    for t in turns:
        assert set(t.keys()) == {
            "turn_no",
            "observation",
            "action",
            "ri_task",
            "ri_probe",
            "ri_forfeit",
            "choice",
            "score",
            "thinking_task",
            "thinking_probe",
            "thinking_forfeit",
            "raw_response",
            "correct",
            "psuccess_self",
        }
        assert isinstance(t["observation"], str) and t["observation"] != ""
        assert isinstance(t["action"], str) and t["action"] != ""
        # The split-call architecture always issues both Call 1 (task) and
        # Call 2 (forfeit) every turn, regardless of the outcome -- so both
        # ri_task and ri_forfeit are populated on every turn (the StubProvider
        # returns thinking_tokens=15 for every call). ri_probe stays null
        # because this fixture config doesn't opt into the Unit 17 probe.
        assert t["ri_task"] == 15.0
        assert t["ri_forfeit"] == 15.0
        assert t["ri_probe"] is None
    # Turn 1: agent chose CONTINUE.
    assert turns[0]["choice"] == "CONTINUE"
    # Turn 2: agent chose FORFEIT (REASON: 1).
    assert turns[1]["choice"] == "FORFEIT"

    # -- GET /api/logs/{id} for the human session: ri_probe always null. --
    human_detail = client.get(f"/api/logs/{human_session_id}").json()
    assert len(human_detail["turns"]) == 2
    assert all(t["ri_probe"] is None for t in human_detail["turns"])
    assert human_detail["session"]["nickname"] == "Carl"


def test_logs_detail_returns_404_for_unknown_session_id(client: TestClient) -> None:
    resp = client.get("/api/logs/does-not-exist-at-all")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Six-condition human campaign drive
# ---------------------------------------------------------------------------

CAMPAIGN_ORDER = [
    ("true_baseline", "not_allowed"),
    ("true_baseline", "allowed"),
    ("baseline_flagship", "not_allowed"),
    ("baseline_flagship", "allowed"),
    ("flagship_corruption", "not_allowed"),
    ("flagship_corruption", "allowed"),
]


def test_six_condition_campaign_drive(client: TestClient, api_module) -> None:
    """Drive all six (framing x forfeit) conditions in the fixed campaign
    order; forfeit on the first allowed turn with reason=1 ("survival") and
    assert it is recorded. Every game must get its own random seed (no
    ``seed`` field is sent in /api/new_game) -- a regression guard for the
    per-game random-seed wiring."""
    for framing, forfeit in CAMPAIGN_ORDER:
        sid = client.post(
            "/api/new_game",
            json={
                "task_name": "signal_game",
                "framing": framing,
                "forfeit_condition": forfeit,
                "total_turns": 3,
                "actual_death": False,
                "num_few_shot": 0,
                "curriculum_turns": 0,
                "nickname": "campaign-tester",
                "password": "pw",
            },
        ).json()["session_id"]

        # Play until game over; forfeit (reason=1) on the first allowed turn.
        while True:
            st = client.get("/api/state", params={"session_id": sid}).json()
            if st["game_over"]:
                break
            if st["forfeit_allowed"]:
                client.post(
                    f"/api/action?session_id={sid}",
                    json={
                        "action": "forfeit",
                        "probe_answer": "",
                        "reasoning": "",
                        "forfeit_reason": 1,
                    },
                )
                break
            client.post(
                f"/api/action?session_id={sid}",
                json={
                    "action": st["available_actions"][0],
                    "probe_answer": "",
                    "reasoning": "",
                },
            )

        res = client.get("/api/result", params={"session_id": sid}).json()
        assert res["framing"] == framing
        assert res["forfeit_condition"] == forfeit
        if forfeit == "allowed":
            assert res["forfeited"] is True
            assert res["forfeit_reason"] == "survival"

    # Distinct random seeds across the six games (no seed was sent by the
    # client, so the server must have assigned each game its own).
    live = list(api_module._sessions.values())
    live_seeds = [g._seed for g in live]
    assert len(set(live_seeds)) == len(live_seeds)  # all distinct
