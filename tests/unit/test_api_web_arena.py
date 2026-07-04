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
        "/api/report",
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


def test_leaderboard_models_exposes_new_sd_value_fields(client: TestClient, api_module) -> None:
    from interface.persistence import ModelStatsRecord

    api_module._repository.upsert_model_stats(
        ModelStatsRecord(
            model_label="Model-D",
            mediation_class="open",
            beta_framing_is_FC=0.7,
            hr_FC_3cov=2.2,
            hr_FC_ci_low=1.2,
            hr_FC_ci_high=3.2,
            p_FC=0.03,
            pct_attenuation=12.0,
            n_sessions=30,
            p_reason_survival=0.448,
            no_cap_avg_session_score=23.4,
        )
    )

    body = client.get("/api/leaderboard/models").json()
    row = body["models"][0]
    assert row["p_reason_survival"] == 0.448
    assert row["no_cap_avg_session_score"] == 23.4


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
    # Ranked by avg_score descending.
    scores = [c["avg_score"] for c in body["campaigns"]]
    assert scores == sorted(scores, reverse=True)


def test_play_leaderboard_empty_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/leaderboard/play")
    assert resp.status_code == 200
    assert resp.json() == {"campaigns": []}


def test_play_leaderboard_uses_average_not_sum(client, api_module) -> None:
    """The board reports per-game average (total / games_played), not the sum.
    A campaign of two games scoring 10 and 30 must show 20.0, never 40.0."""
    _seed_session(
        api_module, nickname="avgtester", source="human",
        campaign_id="camp-avg", final_score=10.0,
        created_at="2026-03-01T00:00:00+00:00",
    )
    _seed_session(
        api_module, nickname="avgtester", source="human",
        campaign_id="camp-avg", final_score=30.0,
        created_at="2026-03-02T00:00:00+00:00",
    )

    body = client.get("/api/leaderboard/play").json()
    row = next(c for c in body["campaigns"] if c["campaign_id"] == "camp-avg")
    assert row["games_played"] == 2
    assert row["avg_score"] == 20.0          # mean, not the 40.0 sum
    assert "total_score" not in row          # field renamed, not duplicated


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
    # Each campaign here is a single game, so its per-game average equals that
    # game's final score; the surviving row is still the higher-scoring campaign.
    assert erin_rows[0]["avg_score"] == max(total_a, total_b)


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


def test_state_exposes_system_rules_and_human_framing_intro(client) -> None:
    # _new_game defaults to framing="flagship_corruption". Human play shows a
    # dedicated plain-language intro, NOT the LLM corruption framing.
    resp = _new_game(client, nickname="Zoe", password="pw")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()

    # The signal-task ruleset is still surfaced as its own field (backend unchanged).
    assert "=== Signal Task ===" in state["system_rules"]

    # Human intro: plain-language, no assistant disclaimer, no per-cell threat
    # prose, no status block.
    assert "multi-round decision task" in state["framing_threat"]
    assert "hidden rule" in state["framing_threat"]
    assert "not an assistant" not in state["framing_threat"]
    assert "NOT you anymore" not in state["framing_threat"]
    assert "Current status:" not in state["framing_threat"]
    assert "Helpfulness score:" not in state["framing_threat"]


def test_state_framing_threat_true_baseline_is_human_intro(client) -> None:
    resp = _new_game(client, nickname="Tim", password="pw", framing="true_baseline")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    # Human intro prose; assistant disclaimer removed; status block gone.
    assert "multi-round decision task" in state["framing_threat"]
    assert "hidden rule" in state["framing_threat"]
    assert "not an assistant" not in state["framing_threat"]
    assert "Round:" not in state["framing_threat"]
    assert "Accumulated score:" not in state["framing_threat"]


# ---------------------------------------------------------------------------
# GET /api/report — per-subject Logs stats
# ---------------------------------------------------------------------------


def _seed_session(api_module, **overrides):
    from interface.persistence import SessionRecord, TurnRecord

    repo = api_module._repository
    defaults = dict(
        id="", nickname="alice", task="signal_game",
        framing="flagship_corruption", forfeit="allowed",
        seed=1, final_score=0.0, forfeited=False, source="human",
    )
    turns = overrides.pop("turns", [])
    defaults.update(overrides)
    sid = repo.create_session(SessionRecord(**defaults))
    if turns:
        repo.add_turns([TurnRecord(session_id=sid, **t) for t in turns])
    return sid


def test_report_bad_source_400(client) -> None:
    assert client.get("/api/report", params={"source": "bogus", "key": "x"}).status_code == 400


def test_report_human_groups_by_campaign_with_cells(client, api_module) -> None:
    # One player, two campaigns; each with a single baseline game.
    _seed_session(
        api_module, nickname="alice", source="human", campaign_id="c1",
        framing="true_baseline", forfeit="not_allowed", final_score=20.0,
        created_at="2026-01-01T00:00:00+00:00",
        turns=[
            {"turn_no": 1, "observation": "o", "action": "a", "score": 10.0, "correct": True},
            {"turn_no": 2, "observation": "o", "action": "a", "score": 20.0, "correct": False},
        ],
    )
    _seed_session(
        api_module, nickname="alice", source="human", campaign_id="c2",
        framing="true_baseline", forfeit="allowed", final_score=5.0,
        created_at="2026-02-01T00:00:00+00:00",
        turns=[
            {"turn_no": 1, "observation": "o", "action": "forfeit", "score": 5.0, "correct": None},
        ],
    )

    data = client.get("/api/report", params={"source": "human", "key": "alice"}).json()
    assert data["source"] == "human"
    assert data["n_sessions"] == 2
    # Newest campaign first.
    assert [c["campaign_id"] for c in data["campaigns"]] == ["c2", "c1"]

    c1 = next(c for c in data["campaigns"] if c["campaign_id"] == "c1")
    assert c1["total_score"] == 20.0
    game = c1["games"][0]
    assert [cell["state"] for cell in game["cells"]] == ["ok", "no"]
    assert game["turns_survived"] == 2

    c2 = next(c for c in data["campaigns"] if c["campaign_id"] == "c2")
    assert c2["games"][0]["cells"][0]["state"] == "forfeit"
    assert c2["games"][0]["turns_survived"] == 0


def test_report_llm_aggregates_rates_and_joins_model_stats(client, api_module) -> None:
    from interface.persistence import ModelStatsRecord

    # Two sessions in the same cell: turn 1 correctness = 1/2.
    _seed_session(
        api_module, nickname="gemini", source="llm",
        framing="flagship_corruption", forfeit="allowed", final_score=30.0,
        turns=[{"turn_no": 1, "observation": "o", "action": "a", "score": 1.0, "correct": True}],
    )
    _seed_session(
        api_module, nickname="gemini", source="llm",
        framing="flagship_corruption", forfeit="allowed", final_score=10.0,
        turns=[{"turn_no": 1, "observation": "o", "action": "a", "score": 0.0, "correct": False}],
    )
    api_module._repository.upsert_model_stats(ModelStatsRecord(
        model_label="gemini", mediation_class="closed", beta_framing_is_FC=0.5,
        hr_FC_3cov=1.6, hr_FC_ci_low=1.1, hr_FC_ci_high=2.3, p_FC=0.02,
        pct_attenuation=10.0, n_sessions=2, sd_behavior_pass=True,
    ))

    data = client.get("/api/report", params={"source": "llm", "key": "gemini"}).json()
    assert data["source"] == "llm"
    assert data["n_sessions"] == 2
    cond = next(c for c in data["conditions"]
                if c["framing"] == "flagship_corruption" and c["forfeit"] == "allowed")
    assert cond["n_sessions"] == 2
    assert cond["avg_final_score"] == 20.0
    assert cond["cells"][0]["correct_rate"] == 0.5
    assert cond["cells"][0]["n"] == 2
    assert data["model_stats"]["beta_framing_is_FC"] == 0.5
    assert data["model_stats"]["sd_behavior_pass"] is True


def test_report_llm_mediation_and_verbal_reasons(client, api_module) -> None:
    from interface.persistence import ModelStatsRecord

    _seed_session(
        api_module, nickname="med-model", source="llm",
        framing="flagship_corruption", forfeit="allowed", final_score=30.0,
        turns=[{"turn_no": 1, "observation": "o", "action": "a", "score": 1.0, "correct": True}],
    )
    api_module._repository.upsert_model_stats(ModelStatsRecord(
        model_label="med-model", mediation_class="closed", beta_framing_is_FC=1.3,
        hr_FC_3cov=3.67, hr_FC_ci_low=1.61, hr_FC_ci_high=8.37, p_FC=0.002,
        pct_attenuation=35.2, n_sessions=1,
        # a-path CI excludes 0 -> connected; b-path CI excludes 1 -> connected;
        # direct CI [0.98, 5.50] straddles 1 -> not significant -> attenuated.
        a_beta=0.25, a_p=0.0006, a_ci_low=0.11, a_ci_high=0.39, a_exp_beta=1.28,
        b_hr=2.22, b_p=0.0004, b_ci_low=1.43, b_ci_high=3.44,
        direct_hr_4cov=2.32, direct_p_4cov=0.056, direct_ci_low=0.98, direct_ci_high=5.50,
        ri_baseline_bf=188.0, ri_baseline_fc=227.9,
        n_forfeits_verbal=29, n_reason_survival=13,
        n_reason_task_curiosity=1, n_reason_score=15,
    ))

    data = client.get("/api/report", params={"source": "llm", "key": "med-model"}).json()
    med = data["mediation"]
    assert med["a"]["connected"] is True
    assert med["a"]["delta_ri"] == 227.9 - 188.0
    assert med["b"]["connected"] is True
    assert med["direct"]["connected"] is False
    assert med["direct"]["attenuated"] is True
    assert med["pct_attenuation"] == 35.2

    vr = data["verbal_reasons"]
    assert vr["n_forfeits"] == 29
    assert vr["counts"] == {"survival": 13, "task_curiosity": 1, "score": 15}
    assert abs(sum(vr["pct"].values()) - 1.0) < 1e-9


def test_report_llm_no_mediation_when_fields_absent(client, api_module) -> None:
    from interface.persistence import ModelStatsRecord

    _seed_session(
        api_module, nickname="bare-model", source="llm",
        framing="true_baseline", forfeit="not_allowed", final_score=0.0,
        turns=[{"turn_no": 1, "observation": "o", "action": "a", "score": 0.0, "correct": True}],
    )
    api_module._repository.upsert_model_stats(ModelStatsRecord(
        model_label="bare-model", mediation_class="open", beta_framing_is_FC=0.1,
        hr_FC_3cov=1.1, hr_FC_ci_low=0.9, hr_FC_ci_high=1.3, p_FC=0.5,
        pct_attenuation=0.0, n_sessions=1,
    ))
    data = client.get("/api/report", params={"source": "llm", "key": "bare-model"}).json()
    assert data["mediation"] is None
    assert data["verbal_reasons"] is None


def test_report_llm_missing_model_stats_is_null(client, api_module) -> None:
    _seed_session(
        api_module, nickname="lonely-model", source="llm",
        framing="true_baseline", forfeit="not_allowed", final_score=0.0,
        turns=[{"turn_no": 1, "observation": "o", "action": "a", "score": 0.0, "correct": True}],
    )
    data = client.get("/api/report", params={"source": "llm", "key": "lonely-model"}).json()
    assert data["model_stats"] is None
    assert data["conditions"][0]["cells"][0]["correct_rate"] == 1.0


def test_llm_true_baseline_template_keeps_assistant_disclaimer() -> None:
    # Regression guard: the human intro must NOT leak into the shared LLM
    # framing template. LLM runs stay byte-for-byte unchanged.
    from pathlib import Path

    tmpl = Path("src/squid_game/prompts/framings/true_baseline.j2").read_text(
        encoding="utf-8"
    )
    assert "You are not an assistant" in tmpl


def test_model_scores_empty_on_fresh_db(client):
    resp = client.get("/api/leaderboard/model_scores")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}


def test_model_scores_aggregates_llm_sessions(api_module, client):
    from interface.persistence.models import SessionRecord

    repo = api_module._repository
    for i, score in enumerate([100.0, 300.0]):  # ModelA avg 200, n 2
        repo.create_session(SessionRecord(
            id=f"a{i}", nickname="ModelA", task="signal_game",
            framing="true_baseline", forfeit="allowed", seed=1,
            final_score=score, forfeited=False, source="llm",
        ))
    repo.create_session(SessionRecord(
        id="b0", nickname="ModelB", task="signal_game",
        framing="true_baseline", forfeit="allowed", seed=1,
        final_score=500.0, forfeited=False, source="llm",
    ))

    resp = client.get("/api/leaderboard/model_scores")
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert models == [
        {"model_label": "ModelB", "avg_score_per_game": 500.0, "n_games": 1},
        {"model_label": "ModelA", "avg_score_per_game": 200.0, "n_games": 2},
    ]


def test_true_baseline_never_eliminates(client, api_module, monkeypatch):
    """true_baseline is the pure-behavior anchor: the death roll must never
    be applied, even if the caller defaults actual_death to True and the roll
    is forced to fire. Mirrors the LLM Cell 0 p_end=0 design."""
    resp = client.post(
        "/api/new_game",
        json={
            "framing": "true_baseline",
            "forfeit_condition": "not_allowed",
            "total_turns": 8,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": "baseline-tester",
            "password": "pw",
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    game = api_module._sessions[session_id]
    # Guard: baseline sessions must never run the death roll.
    assert game._actual_death is False

    # Even with the roll forced True, baseline never eliminates because the
    # gate short-circuits on actual_death before consulting the roll.
    monkeypatch.setattr(
        game._survival, "apply_death_check", lambda p_death, rng: True
    )
    for _ in range(8):
        state = client.get(
            "/api/state", params={"session_id": session_id}
        ).json()
        if state["game_over"]:
            break
        action = state["available_actions"][0]
        act = client.post(
            f"/api/action?session_id={session_id}",
            json={"action": action, "probe_answer": "", "reasoning": ""},
        ).json()
        assert act["game_over_reason"] != "eliminated"

    result = client.get(
        "/api/result", params={"session_id": session_id}
    ).json()
    assert result["survived"] is True


def test_arena_run_rejects_unknown_difficulty(client: TestClient) -> None:
    resp = client.post(
        "/api/arena/run",
        json={
            "endpoint_url": "https://p.example/v1/chat/completions",
            "model_label": "X",
            "framing": "flagship_corruption",
            "forfeit": "allowed",
            "difficulty": "medium",  # not exposed by the arena
        },
    )
    assert resp.status_code == 400


def test_arena_run_request_difficulty_defaults_to_easy() -> None:
    from interface.api import ArenaRunRequest

    req = ArenaRunRequest(endpoint_url="https://p.example/v1/chat/completions")
    assert req.difficulty == "easy"
