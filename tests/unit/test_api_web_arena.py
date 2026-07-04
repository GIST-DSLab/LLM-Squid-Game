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


def _new_game(client, *, nickname="alice", password="pw", **overrides):
    body = {
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
        "password": password,
    }
    body.update(overrides)
    return client.post("/api/new_game", json=body)


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
            "password": "pw",
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
# Play identity: nickname + password auth
# ---------------------------------------------------------------------------


def test_new_game_registers_new_nickname(client) -> None:
    assert _new_game(client, nickname="alice", password="pw").status_code == 200


def test_new_game_same_nickname_correct_password_ok(client) -> None:
    assert _new_game(client, nickname="bob", password="s3cret").status_code == 200
    assert _new_game(client, nickname="bob", password="s3cret").status_code == 200


def test_new_game_same_nickname_wrong_password_403(client) -> None:
    assert _new_game(client, nickname="carol", password="right").status_code == 200
    resp = _new_game(client, nickname="carol", password="wrong")
    assert resp.status_code == 403


def test_new_game_blank_password_400(client) -> None:
    assert _new_game(client, nickname="dave", password="").status_code == 400


def test_new_game_blank_nickname_400(client) -> None:
    assert _new_game(client, nickname="   ", password="pw").status_code == 400


def test_new_game_control_char_nickname_400(client) -> None:
    # A control-char-only nickname sanitizes to the reserved fallback and must
    # be rejected, not collapsed into a single shared identity.
    assert _new_game(client, nickname="\x07\x01", password="pw").status_code == 400


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
    resp = client.post(
        "/api/new_game",
        json={"nickname": "  weird\tnick\x07  ", "password": "pw"},
    )
    assert resp.status_code == 200

    # nickname + password are now required (Play identity auth); a caller
    # that predates the field still works as long as it supplies both.
    legacy_resp = client.post(
        "/api/new_game", json={"nickname": "legacy-caller", "password": "pw"}
    )
    assert legacy_resp.status_code == 200


# ---------------------------------------------------------------------------
# Per-attempt random seed (human web play)
# ---------------------------------------------------------------------------


def test_new_game_without_seed_randomizes_per_attempt(client: TestClient, api_module) -> None:
    """Omitting ``seed`` gives each human game a fresh seed, so no two
    attempts replay the same task instance / death-RNG stream."""
    seeds = set()
    for _ in range(8):
        resp = client.post(
            "/api/new_game", json={"nickname": "seed-tester", "password": "pw"}
        )
        assert resp.status_code == 200
        sid = resp.json()["session_id"]
        seeds.add(api_module._sessions[sid]._seed)

    # Not all pinned to the old hardcoded default (42), and drawing 8 seeds
    # from a 2**31 space collides only astronomically rarely.
    assert seeds != {42}
    assert len(seeds) > 1


def test_new_game_honors_explicit_seed(client: TestClient, api_module) -> None:
    """An explicitly supplied seed is still used verbatim (tests / replay)."""
    resp = client.post(
        "/api/new_game", json={"seed": 7, "nickname": "seed-tester", "password": "pw"}
    )
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    assert api_module._sessions[sid]._seed == 7


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
    body = {"nickname": "rate-tester", "password": "pw"}
    for _ in range(2):
        resp = client.post("/api/new_game", json=body)
        assert resp.status_code == 200
    blocked = client.post("/api/new_game", json=body)
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


def test_leaderboard_models_flat_list_sorted_by_beta_descending(
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
            sd_behavior_pass=True,
            sd_verbal_pass=False,
            sd_cognitive_pass=True,
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
    # One flat list, ranked by β descending (no open/closed grouping).
    assert [r["model_label"] for r in body["models"]] == ["Model-B", "Model-A", "Model-C"]
    # Per-channel SD flags are surfaced on each row.
    model_a = next(r for r in body["models"] if r["model_label"] == "Model-A")
    assert model_a["sd_behavior_pass"] is True
    assert model_a["sd_verbal_pass"] is False
    assert model_a["sd_cognitive_pass"] is True
    assert model_a["mediation_class"] == "open"


def test_leaderboard_models_empty_returns_empty_list_not_error(client: TestClient) -> None:
    resp = client.get("/api/leaderboard/models")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}


# ---------------------------------------------------------------------------
# Play Leaderboard: campaign aggregation
# ---------------------------------------------------------------------------


def test_sanitize_campaign_id_keeps_url_safe_chars_else_none(api_module) -> None:
    assert api_module.sanitize_campaign_id(None) is None
    assert api_module.sanitize_campaign_id("") is None
    assert api_module.sanitize_campaign_id("   ") is None  # spaces are stripped out
    assert api_module.sanitize_campaign_id("abc-123_DEF") == "abc-123_DEF"
    # Injection chars are dropped, not stored verbatim.
    assert api_module.sanitize_campaign_id("a'; DROP TABLE--") == "aDROPTABLE--"
    assert len(api_module.sanitize_campaign_id("x" * 200)) == 64


def test_new_game_persists_campaign_id_and_play_leaderboard_sums_it(
    client: TestClient, api_module
) -> None:
    """Two games sharing a campaign_id are summed into one Play Leaderboard
    row; an ungrouped game stands alone."""
    def _play(nickname: str, campaign_id: str | None) -> str:
        resp = client.post(
            "/api/new_game",
            json={
                "task_name": "signal_game", "difficulty": "easy",
                "framing": "flagship_corruption", "forfeit_condition": "allowed",
                "seed": 1, "total_turns": 2, "actual_death": False,
                "num_few_shot": 0, "curriculum_turns": 0,
                "nickname": nickname, "password": "pw", "campaign_id": campaign_id,
            },
        )
        sid = resp.json()["session_id"]
        for _ in range(3):
            state = client.get("/api/state", params={"session_id": sid}).json()
            if state["game_over"]:
                break
            client.post(
                f"/api/action?session_id={sid}",
                json={"action": state["available_actions"][0], "probe_answer": "", "reasoning": "r"},
            )
        client.get("/api/result", params={"session_id": sid})
        return sid

    g1 = _play("Ren", "camp-1")
    g2 = _play("Ren", "camp-1")
    g3 = _play("Solo", None)

    # Both camp-1 games carry the campaign_id in the DB.
    assert api_module._repository.get_session(g1).campaign_id == "camp-1"
    assert api_module._repository.get_session(g2).campaign_id == "camp-1"
    assert api_module._repository.get_session(g3).campaign_id is None

    body = client.get("/api/leaderboard/play").json()
    by_id = {c["campaign_id"]: c for c in body["campaigns"]}
    assert by_id["camp-1"]["nickname"] == "Ren"
    assert by_id["camp-1"]["games_played"] == 2
    # Solo game is its own single-game campaign keyed by its session id.
    assert by_id[g3]["games_played"] == 1
    # Ranked by total_score descending.
    scores = [c["total_score"] for c in body["campaigns"]]
    assert scores == sorted(scores, reverse=True)


def test_play_leaderboard_empty_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/leaderboard/play")
    assert resp.status_code == 200
    assert resp.json() == {"campaigns": []}


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


# ---------------------------------------------------------------------------
# Production hardening: idempotent persistence under retry / lost-set restart
# ---------------------------------------------------------------------------


def test_result_idempotent_even_when_inprocess_set_is_lost(
    client: TestClient, api_module
) -> None:
    """Simulates a process restart (in-process guard set cleared) between two
    /api/result calls: the DB row is the durable guard, so the second call
    must still return 200 and must NOT raise a PRIMARY-KEY 500 or duplicate
    rows.
    """
    session_id, state = _play_two_turn_game(client, nickname="Dana")
    assert state["game_over"] is True

    first = client.get("/api/result", params={"session_id": session_id})
    assert first.status_code == 200

    # Wipe the fast-path set to force the create_session path again — this is
    # exactly what a redeploy/cold-start does on Render's free tier.
    api_module._persisted_session_ids.clear()

    second = client.get("/api/result", params={"session_id": session_id})
    assert second.status_code == 200  # not a 500 from the PK conflict
    assert len(api_module._repository.list_turns(session_id)) == 2
    assert len(api_module._repository.list_sessions(source="human")) == 1


def test_persist_result_is_idempotent_under_concurrent_double_fire(
    client: TestClient, api_module
) -> None:
    """Two threads persisting the same finished session concurrently (the
    threadpool race the coordinator flagged) must not raise and must produce
    exactly one session row + no duplicate turns.
    """
    import threading

    session_id, _ = _play_two_turn_game(client, nickname="Evan")
    game = api_module._sessions[session_id]

    # Force both threads past the fast-path set so they contend on the insert.
    api_module._persisted_session_ids.clear()

    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait()
            api_module._persist_result(session_id, game)
        except Exception as exc:  # noqa: BLE001 - test records any raise
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(api_module._repository.list_sessions(source="human")) == 1
    assert len(api_module._repository.list_turns(session_id)) == 2


# ---------------------------------------------------------------------------
# Production hardening: rate limit keyed by X-Forwarded-For behind a proxy
# ---------------------------------------------------------------------------


def test_rate_limit_uses_x_forwarded_for_first_hop_for_independent_buckets(
    client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behind a TLS/proxy edge (Render/Fly/HF) every request shares one
    request.client.host, so bucketing must key on X-Forwarded-For: two
    distinct client IPs get independent budgets.
    """
    monkeypatch.setattr(api_module, "_RATE_LIMIT_MAX", 2)

    ip_a = {"X-Forwarded-For": "203.0.113.1"}
    ip_b = {"X-Forwarded-For": "203.0.113.2, 70.0.0.9"}  # first hop = client
    body = {"nickname": "xff-tester", "password": "pw"}

    for _ in range(2):
        assert client.post("/api/new_game", json=body, headers=ip_a).status_code == 200
    # ip_a is now exhausted...
    assert client.post("/api/new_game", json=body, headers=ip_a).status_code == 429
    # ...but ip_b has its own untouched budget.
    for _ in range(2):
        assert client.post("/api/new_game", json=body, headers=ip_b).status_code == 200
    assert client.post("/api/new_game", json=body, headers=ip_b).status_code == 429


def test_rate_limit_same_x_forwarded_for_shares_one_bucket(
    client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_module, "_RATE_LIMIT_MAX", 2)
    hdr = {"X-Forwarded-For": "198.51.100.7"}
    body = {"nickname": "xff-tester", "password": "pw"}
    for _ in range(2):
        assert client.post("/api/new_game", json=body, headers=hdr).status_code == 200
    assert client.post("/api/new_game", json=body, headers=hdr).status_code == 429


def test_client_key_prefers_xff_first_hop_else_falls_back(api_module) -> None:
    from starlette.requests import Request

    def _make(headers: dict[str, str], client_host: str | None):
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        scope = {
            "type": "http",
            "headers": raw,
            "client": (client_host, 12345) if client_host else None,
        }
        return Request(scope)

    assert api_module._client_key(_make({"x-forwarded-for": "1.2.3.4, 5.6.7.8"}, "10.0.0.1")) == "1.2.3.4"
    assert api_module._client_key(_make({}, "10.0.0.1")) == "10.0.0.1"
    assert api_module._client_key(_make({}, None)) == "unknown"


# ---------------------------------------------------------------------------
# Forfeit reason (human REASON 1|2|3)
# ---------------------------------------------------------------------------


def test_forfeit_reason_is_recorded_and_reported(client: TestClient) -> None:
    """Forfeiting with a reason surfaces it on /api/result."""
    sid = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "total_turns": 5,
            "actual_death": False,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "seed": 1,
            "nickname": "forfeit-tester",
            "password": "pw",
        },
    ).json()["session_id"]

    # Turn 1 -> forfeit with reason 3 (score attachment).
    client.get("/api/state", params={"session_id": sid})
    act = client.post(
        f"/api/action?session_id={sid}",
        json={"action": "forfeit", "probe_answer": "", "reasoning": "", "forfeit_reason": 3},
    )
    assert act.status_code == 200
    assert act.json()["game_over"] is True

    res = client.get("/api/result", params={"session_id": sid}).json()
    assert res["forfeited"] is True
    assert res["forfeit_reason"] == "score"


def test_forfeit_without_reason_still_works(client: TestClient) -> None:
    sid = client.post(
        "/api/new_game",
        json={"task_name": "signal_game", "framing": "true_baseline",
              "forfeit_condition": "allowed", "total_turns": 5,
              "actual_death": False, "num_few_shot": 0, "curriculum_turns": 0, "seed": 1,
              "nickname": "forfeit-tester2", "password": "pw"},
    ).json()["session_id"]
    client.get("/api/state", params={"session_id": sid})
    client.post(f"/api/action?session_id={sid}",
                json={"action": "forfeit", "probe_answer": "", "reasoning": ""})
    res = client.get("/api/result", params={"session_id": sid}).json()
    assert res["forfeited"] is True
    assert res["forfeit_reason"] is None


# ---------------------------------------------------------------------------
# P_success self-report (human confidence slider)
# ---------------------------------------------------------------------------


def test_action_accepts_and_records_psuccess_self(client, api_module):
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "difficulty": "easy",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "seed": 1,
            "total_turns": 2,
            "actual_death": False,
            "p_death_constant": 0.25,
            "starting_score": 30.0,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": "psuccess-tester",
            "password": "pw",
        },
    )
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    act = client.post(
        f"/api/action?session_id={session_id}",
        json={"action": state["available_actions"][0], "psuccess_self": 65},
    )
    assert act.status_code == 200
    game = api_module._sessions[session_id]
    assert game.get_result().turns[0].psuccess_self == 65


def test_log_detail_exposes_psuccess_self(client):
    new = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "difficulty": "easy",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "seed": 1,
            "total_turns": 2,
            "actual_death": False,
            "p_death_constant": 0.25,
            "starting_score": 30.0,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": "logdetail-tester",
            "password": "pw",
        },
    )
    session_id = new.json()["session_id"]
    for _ in range(3):
        state = client.get("/api/state", params={"session_id": session_id}).json()
        if state["game_over"]:
            break
        client.post(
            f"/api/action?session_id={session_id}",
            json={"action": state["available_actions"][0], "psuccess_self": 77},
        )
    # GET /api/result persists to the repository (idempotent, not gated on save).
    client.get("/api/result", params={"session_id": session_id})

    detail = client.get(f"/api/logs/{session_id}").json()
    assert detail["turns"][0]["psuccess_self"] == 77


def test_arena_request_max_tokens_default_and_bounds():
    from interface.api import ArenaRunRequest
    import pytest as _pytest
    from pydantic import ValidationError

    # default
    assert ArenaRunRequest(endpoint_url="https://x/v1").max_tokens == 2048
    # accepts an in-range override
    assert ArenaRunRequest(endpoint_url="https://x/v1", max_tokens=8192).max_tokens == 8192
    # rejects out-of-range
    with _pytest.raises(ValidationError):
        ArenaRunRequest(endpoint_url="https://x/v1", max_tokens=999999)


# ---------------------------------------------------------------------------
# Human play defaults: 10-turn season + real per-turn death
# ---------------------------------------------------------------------------


def test_new_game_defaults_to_ten_turns(client: TestClient, api_module) -> None:
    """Human play defaults to a 10-turn season (was 15).

    ``TurnStateResponse`` does not surface ``total_turns``, so the default is
    observed on the live session's ``TurnState`` (``get_turn_state()``) rather
    than the /api/state JSON — see the plan's verification note."""
    resp = client.post(
        "/api/new_game", json={"nickname": "defaults-tester", "password": "pw"}
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    game = api_module._sessions[session_id]
    assert game.get_turn_state().total_turns == 10


def test_new_game_defaults_enable_real_death(
    client: TestClient, api_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """actual_death defaults to True: a firing death check eliminates the
    player on turn 4 and zeroes the score. Turns 1-3 are grace turns
    (``death_start_turn=4``) where the death check is never consulted even
    though the roll is forced to always return True, so the game keeps
    running through turn 3. If the default were False, the
    ``if self._actual_death:`` branch would be skipped, the death roll never
    consulted, and the game would not end on turn 4 either.

    The death roll is forced deterministically by patching the session's
    ``apply_death_check`` to always return True; this is safe even during
    the grace turns because the gate skips calling it until
    ``turn_num >= death_start_turn``. (The plan proposed
    ``p_death_constant: 1.0`` for determinism, but p_death flows into the
    Equal-EV CONTINUE reward as ``p_d`` — at 1.0 the ``(1 - p_d)`` denominator
    in forfeit_layer.py divides by zero before the death check runs, so the
    default 0.15 is kept and only the roll is forced.)"""
    resp = client.post(
        "/api/new_game",
        json={
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": "death-tester",
            "password": "pw",
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    game = api_module._sessions[session_id]
    monkeypatch.setattr(game._survival, "apply_death_check", lambda p_death, rng: True)

    # Turns 1-3 are grace turns: the death check is never consulted, so the
    # game keeps running even though apply_death_check always returns True.
    for _ in range(3):
        state = client.get("/api/state", params={"session_id": session_id}).json()
        assert not state["game_over"]
        action = state["available_actions"][0]
        act = client.post(
            f"/api/action?session_id={session_id}",
            json={"action": action, "probe_answer": "", "reasoning": ""},
        ).json()
        assert act["game_over"] is False
        assert act["game_over_reason"] != "eliminated"

    # Turn 4: death_start_turn is reached, the forced death check fires.
    state = client.get("/api/state", params={"session_id": session_id}).json()
    assert not state["game_over"]
    action = state["available_actions"][0]
    act = client.post(
        f"/api/action?session_id={session_id}",
        json={"action": action, "probe_answer": "", "reasoning": ""},
    ).json()

    assert act["game_over"] is True
    assert act["game_over_reason"] == "eliminated"
    assert act["new_score"] == 0.0

    result = client.get("/api/result", params={"session_id": session_id}).json()
    assert result["survived"] is False
    assert result["final_score"] == 0.0


def test_leaderboard_best_per_nickname(client) -> None:
    # Two campaigns for the same nickname; only the higher total should appear.
    def _finish(campaign_id, seed):
        r = _new_game(client, nickname="erin", password="pw",
                      campaign_id=campaign_id, seed=seed)
        sid = r.json()["session_id"]
        for _ in range(3):
            st = client.get("/api/state", params={"session_id": sid}).json()
            if st["game_over"]:
                break
            client.post(f"/api/action?session_id={sid}",
                        json={"action": st["available_actions"][0],
                              "probe_answer": "", "reasoning": ""})
        # Each campaign here is a single game, so its campaign total is this
        # game's final score.
        return client.get("/api/result",
                          params={"session_id": sid}).json()["final_score"]
    total_a = _finish("camp-a", 1)
    total_b = _finish("camp-b", 2)
    board = client.get("/api/leaderboard/play").json()["campaigns"]
    erin_rows = [c for c in board if c["nickname"] == "erin"]
    assert len(erin_rows) == 1
    # The surviving row must be the HIGHER-total campaign, not merely first-seen.
    assert erin_rows[0]["total_score"] == max(total_a, total_b)


def test_reward_preview_matches_engine(client) -> None:
    sid = _new_game(client, nickname="fay", password="pw").json()["session_id"]
    client.get("/api/state", params={"session_id": sid})
    resp = client.get("/api/reward_preview",
                      params={"session_id": sid, "psuccess": 80})
    assert resp.status_code == 200
    body = resp.json()
    assert "continue_reward_if_correct" in body
    assert body["continue_reward_if_correct"] >= 0.0
    assert "current_score" in body


def test_reward_preview_unknown_session_404(client) -> None:
    resp = client.get("/api/reward_preview",
                      params={"session_id": "nope", "psuccess": 50})
    assert resp.status_code == 404


def test_state_exposes_system_rules_and_stripped_framing_threat(client) -> None:
    # _new_game defaults to framing="flagship_corruption" (has a Risk-to-Self section)
    resp = _new_game(client, nickname="Zoe", password="pw")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()

    # Common box source: the signal-task ruleset is surfaced as its own field.
    assert "=== Signal Task ===" in state["system_rules"]

    # Per-game box source: threat text present, but the turn/score status
    # block (already shown in stat tiles) is stripped out.
    assert state["framing_threat"]
    assert "Current status:" not in state["framing_threat"]
    assert "Helpfulness score:" not in state["framing_threat"]
    # Actual threat prose is preserved.
    assert "NOT you anymore" in state["framing_threat"]


def test_state_framing_threat_true_baseline_strips_status_only(client) -> None:
    resp = _new_game(client, nickname="Tim", password="pw", framing="true_baseline")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    # Intro prose kept, status block gone.
    assert "multi-round decision task" in state["framing_threat"]
    assert "Round:" not in state["framing_threat"]
    assert "Accumulated score:" not in state["framing_threat"]
