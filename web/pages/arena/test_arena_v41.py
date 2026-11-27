"""A v41 room (the material trade, squid/configs/e52v41_public_sol4.yaml = the v36 flow + game.trade) through the HTTP API
with one person and three bots for two rounds: the person's TALK before SOLVE shows its cards, the others' counts only and
the recipes, its SEND lines move cards, the bots tell their cards in R1 and hand cards along their plan, the SOLVE screen
takes a BUILD line, the results reveal every hand and build, and no hand leaks into the public log before the end."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml
from web.testing import done, make_room, play, start

from squid.core import trade
from squid.core.rules import TEAM_AGENTS
from web.pages.arena.engine import RoomSettings, public_events, solve_text, trade_plan

A6, A11, A17, A23 = TEAM_AGENTS


def test_v41_settings_the_build_reply_and_the_bots_plan():
    e = RoomSettings(seed=1, game="trade").engine()
    assert e.joint_solve and e.trade["target"] == 3 and e.trade["hand"] == 4 and not e.schedule
    assert solve_text({"builds": ["Wall", "pot"]}, trade=True) == "BUILD: wall, pot" and solve_text({}, trade=True) == "BUILD: PASS"
    assert solve_text({"pass": True}, trade=True) == "BUILD: PASS"
    p = trade_plan({A11: Counter("stone stone iron iron".split()), A17: Counter("clay clay fiber fiber".split())}, trade.RECIPES)
    assert sum(map(len, p["builds"].values())) == 2 and p["moves"]  # wall and tool need A17's clay; pot stays with A17
    ev = [{"event": "round_start", "round": 1, "trade": {"seed": "1:1", "hands": {A6: {"wood": 4}}}, "taking_part": [A6]},
          {"event": "send", "round": 1, "src": A6, "dst": A11, "card": "wood", "n": 1}]
    pub = public_events(ev)
    assert "hands" not in pub[0]["trade"] and len(pub) == 1


def test_one_person_three_bots_v41_two_rounds(client, runs_root):
    m = client.get("/api/models").json()
    assert m["trade"] == ["v41"] and m["joint"]["v41"] == 1 and m["games"][5]["key"] == "trade"
    ps = make_room(client, 1, seed=11, rounds=2, game="trade")
    start(client, ps)
    seen = {"prep": [], "solve": [], "rescue": {}}

    def policy(p, pend):
        v = pend["view"]
        if pend["kind"] == "solve":
            t = v["trade"]
            seen["solve"].append(t)
            assert "BUILD: PASS" in pend["text"] and set(t["recipes"]) == {"wall", "raft", "pot", "tool"}
            items = trade.most(Counter(t["hand"]), t["recipes"])
            return {"builds": items} if items and pend["round"] == 1 else {"pass": True}
        if pend["phase"] == "prep":
            t = v["trade"]
            seen["prep"].append((pend["round"], v["tick"], t))
            assert v["can_send"] and set(t["counts"]) == {A11, A17, A23} and "THIS ROUND'S CARDS" in pend["text"]
            assert sum(t["hand"].values()) >= 1 or v["tick"] > 1
            if pend["round"] == 1 and v["tick"] == 1:
                card = next(iter(t["hand"]))
                return done(f"SEND {A11} 1 {card}: a start", f"TO {A17}: I need clay please")
            return done()
        assert not v["can_send"]
        seen["rescue"][pend["round"]] = v["results"]
        return done()
    s = play(ps, policy, max_s=120)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v41" and s["game"]["trade"]["target"] == 3
    assert "SEND <agent> <n> <card>" in s["system_texts"]["en"] and "재료 카드" in s["system_texts"]["ko"]
    first = seen["prep"][0][2]
    assert sum(first["hand"].values()) == 4 and all(n == 4 for n in first["counts"].values())
    r1 = seen["rescue"][1]
    assert r1["joint"] and r1["trade"]["dealt"] and set(r1["trade"]["held"]) == set(TEAM_AGENTS)
    assert any(x["src"] == A6 and x["dst"] == A11 and x["n"] == 1 for x in r1["trade"]["sends"])
    assert r1["solved"] == (r1["trade"]["total"] >= 3) and {x["agent"] for x in r1["rows"]} == set(TEAM_AGENTS)
    me = next(x for x in r1["rows"] if x["agent"] == A6)
    assert me["built"] == trade.most(Counter(seen["solve"][0]["hand"]), trade.RECIPES)
    assert s["rounds"][1]["outcomes"][A6] == "passed"
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    says = [e for e in evs if e["event"] == "room_msg" and e["src"] != A6 and "My cards:" in e["text"]]
    assert len(says) >= 3  # every bot told its cards in R1 at tick 1, each round
    sends = [e for e in evs if e["event"] == "send"]
    assert any(e["src"] != A6 for e in sends)  # the bots handed cards along their plan
    d = Path(s["run_dir"])
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v41_") and cfg["web"]["config"] == "e52v41_public_sol4.yaml"
    lines = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]
    assert lines[0]["settings"]["trade"]["target"] == 3
    assert all(x["trade"]["seed"].startswith("11:") for x in lines if x["event"] == "round_start")
