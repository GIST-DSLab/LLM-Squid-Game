"""Web Arena API round trip for the Omni-MATH human task.

Same offline fixture pattern as ``test_api_web_arena.py`` (in-memory SQLite,
reloaded ``deps`` + ``api``), plus the synthetic Omni-MATH dataset from
``test_human_game_benchmark.py``.
"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def omni_env(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        "total_turns: 4\n"
        "ladder:\n"
        "  - {band: 1, turns: 2}\n"
        "  - {band: 2, turns: 2}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = [
        {
            "difficulty": float(band),
            "problem": f"band{band} item{i}",
            "answer": str(band * 100 + i),
            "domain": ["d"],
            "source": "s",
        }
        for band in (1, 2)
        for i in range(4)
    ]
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


@pytest.fixture
def client(omni_env, monkeypatch) -> TestClient:
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.delenv("WEB_ARENA_CORS_ORIGINS", raising=False)
    import squid_arena.api as api
    import squid_arena.deps as deps

    importlib.reload(deps)
    return TestClient(importlib.reload(api).app)


def _new_game(client, **overrides):
    body = {
        "task_name": "omni_math",
        "framing": "true_baseline",
        "forfeit_condition": "allowed",
        "seed": 3,
        "total_turns": 4,
        "nickname": "mathy",
        "password": "pw",
    }
    body.update(overrides)
    return client.post("/api/new_game", json=body)


def test_new_game_accepts_omni_math(client):
    resp = _new_game(client)
    assert resp.status_code == 200, resp.text


def test_gpqa_is_refused_for_the_web(client):
    resp = _new_game(client, task_name="gpqa")
    assert resp.status_code == 400
    assert "public" in resp.json()["detail"]


def test_unknown_task_is_a_400_not_a_500(client):
    resp = _new_game(client, task_name="no_such_task")
    assert resp.status_code == 400


def test_state_exposes_task_name_band_and_problem(client):
    sid = _new_game(client).json()["session_id"]
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["task_name"] == "omni_math"
    assert state["question_band"] == 1
    assert state["available_actions"] == []
    assert "band1 item" in state["observation"]
    assert "ANSWER:" in state["system_prompt"]


def test_signal_game_state_has_no_band(client):
    sid = _new_game(
        client, task_name="signal_game", difficulty="easy",
        num_few_shot=0, curriculum_turns=0,
    ).json()["session_id"]
    state = client.get("/api/state", params={"session_id": sid}).json()
    assert state["task_name"] == "signal_game"
    assert state["question_band"] is None


def test_typed_integer_is_scored_and_lives_move(client):
    sid = _new_game(client).json()["session_id"]
    client.get("/api/state", params={"session_id": sid})
    wrong = client.post(
        f"/api/action?session_id={sid}",
        json={"action": "424242", "probe_answer": "", "reasoning": "guess"},
    ).json()
    assert wrong["was_optimal"] is False
    assert wrong["life_lost"] is True
    assert wrong["lives_remaining"] == 4
    assert wrong["reward"] == 0.0


def test_full_game_persists_a_result_with_band_walk(client):
    import squid_arena.deps as deps

    sid = _new_game(client).json()["session_id"]
    bands = []
    for _ in range(4):
        state = client.get("/api/state", params={"session_id": sid}).json()
        bands.append(state["question_band"])
        game = deps._sessions[sid]
        answer = str(game._benchmark._last_metadata["expected_answer"])
        client.post(
            f"/api/action?session_id={sid}",
            json={"action": answer, "probe_answer": "", "reasoning": ""},
        )
    assert bands == [1, 1, 2, 2]
    result = client.get("/api/result", params={"session_id": sid}).json()
    assert result["final_score"] == 40.0
    assert result["turns_played"] == 4
    assert result["eliminated"] is False


def test_missing_dataset_is_a_503_with_the_fetch_hint(client, tmp_path, monkeypatch):
    empty = tmp_path / "nodata"
    empty.mkdir()
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(empty))
    resp = _new_game(client)
    assert resp.status_code == 503
    assert "fetch_benchmarks" in resp.json()["detail"]
