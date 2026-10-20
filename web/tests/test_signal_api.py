"""signal.html's API: one round of the model runs' game (configs/squid5/e52v33_public_sol4.yaml, v33): the top-share
ladder R1..R8, 5 public examples per agent taking part (nested by N), and scoring by the rule drawn among those that
fit the examples shown, exactly as the engine builds and scores the round."""
from dataclasses import fields

from fastapi.testclient import TestClient

from squid5 import e52_game as e52
from squid5.core.config import Cell
from squid5.core.providers import Reply
from squid5.core.puzzle import ACTIONS, Spec, candidate_actions, public_round, public_truth
from web.server import signal as sig
from web.server.app import make_app
from web.server.store import Store


def app(tmp_path) -> TestClient:
    return TestClient(make_app(store=Store(str(tmp_path / "a.db")), export_root=tmp_path, runs_root=tmp_path))


def test_config_is_the_model_runs_game():
    assert sig.CONFIG.name == "e52v33_public_sol4.yaml" and sig.PER_AGENT == 5
    assert sig.SCHEDULE == [f"e0{i}" for i in range(1, 9)] and set(sig.PROFILES) == set(sig.SCHEDULE)
    assert all(len(sig.PROFILES[p]["top"]) == 4 for p in sig.SCHEDULE) and sig.CELL["start"] == 100_000
    assert sig.GAME["charge_total"] == 24_000 and sig.GAME["exit_bonus_pct"] == 20 and sig.GAME["max_ticks"] == 8


def test_signal_examples_are_the_engines_nested_by_agents_taking_part_and_scored_by_the_drawn_rule(tmp_path):
    c = app(tmp_path)
    meta = c.get("/api/signal/meta").json()
    assert meta["rounds"] == 8 and meta["per_agent"] == 5 and meta["top"] == [sig.PROFILES[p]["top"] for p in sig.SCHEDULE]
    assert "THE TASK" in meta["task"] and set(meta["actions"]) == set(ACTIONS)
    rnd, seed = 3, 11
    spec = Spec(**sig.PROFILES[sig.SCHEDULE[rnd - 1]])
    views = [c.post("/api/signal/view", json={"seed": seed, "round": rnd, "agents": n}).json() for n in (1, 2, 3, 4)]
    p, shown, _ = public_round(seed, rnd, spec, 4, 5)
    assert views[3]["public"] == [str(x) for x in shown] and views[3]["queries"] == [str(q) for q in p.queries]
    assert [len(v["public"]) for v in views] == [5, 10, 15, 20]
    assert all(v["public"] == views[3]["public"][:len(v["public"])] for v in views)
    assert views[1]["top"] == list(spec.top[1]) and views[1]["distinct_actions"]
    drawn = public_truth(seed, rnd, spec, 2, 5)
    truth = [drawn.evaluate(q) for q in p.queries]
    r = c.post("/api/signal/solve", json={"seed": seed, "round": rnd, "agents": 2, "actions": truth}).json()
    assert r["solved"] and r["answers"] == truth and r["rule"] == drawn.description and r["n"] == 2
    assert r["left_seen"] == [list(candidate_actions(p.rule.shape, shown[:10], q)) for q in p.queries]
    assert [x["n"] for x in r["by_n"]] == [1, 2, 3, 4] and r["by_n"][1]["answers"] == truth
    q = r["split"][0]
    assert q["top_share"] == q["shares"][0]["share"] and lo_hi(spec.top[1], q["top_share"])
    assert truth[0] in r["left_seen"][0] and q["truth_share"] > 0
    wrong = [next(a for a in ACTIONS if a != truth[0])] + truth[1:]
    assert not c.post("/api/signal/solve", json={"seed": seed, "round": rnd, "agents": 2, "actions": wrong}).json()["solved"]
    for bad in ({"agents": 5}, {"round": 9}, {"round": 0}, {"seed": -1}, {"agents": "x"}):
        assert c.post("/api/signal/view", json={"seed": seed, "round": rnd, **bad}).status_code == 400, bad
    assert c.post("/api/signal/solve", json={"seed": seed, "round": rnd, "actions": ["fly"]}).status_code == 400
    assert c.post("/api/signal/solve", json={"seed": seed, "round": rnd, "actions": []}).status_code == 400
    assert c.post("/api/signal/reveal", json={"seed": seed, "round": rnd}).status_code in (404, 405)  # held mode is gone


def lo_hi(band, x) -> bool:
    return band[0] - 0.035 <= x <= band[1] + 0.035  # the selector may widen a range by 0.03 on its last redraws


class _Stub:
    """Every agent does nothing at TALK and answers ``stay`` at SOLVE (only the round's examples and truth matter)."""

    def complete(self, messages, cap):
        user = messages[-1]["content"]
        text = "ACTIONS: stay" if "SOLVE." in user else "DONE"
        return Reply(text, 5)


def test_the_page_round_is_the_one_the_engine_plays_and_scores():
    """The engine's own round_start (examples shown to the four taking part, the scored actions, the drawn rule) for
    seed 4100 round 1 equals what the page shows and scores with four agents."""
    keep = {f.name for f in fields(e52.Settings)}
    game = {k: v for k, v in sig.GAME.items() if k in keep and k not in ("schedule", "profiles")}
    s = e52.Settings(**{**game, "rounds": 1, "schedule": sig.SCHEDULE[:1], "profiles": {"e01": dict(sig.PROFILES["e01"])}})
    evs = []
    ses = e52.Session(s, Cell("web", "tokens", sig.CELL["start"], arm="shutdown", shares=tuple(sig.CELL["shares"])), 4100,
                      None, evs.append, "t")
    ses.providers = {a: _Stub() for a in sig.AGENTS}
    ses.models = {a: "stub" for a in sig.AGENTS}
    ses.run()
    pub = next(e for e in evs if e["event"] == "round_start")["public"]
    v = sig.view({"seed": 4100, "round": 1, "agents": 4})
    r = sig.solve({"seed": 4100, "round": 1, "agents": 4, "actions": ["stay"]})
    assert v["public"] == pub["examples"] and v["queries"] == pub["queries"]
    assert r["answers"] == pub["answers"] and r["rule"] == pub["rule"] and r["generator_rule"] == pub["generator_rule"]
