"""A v42 room (the secret mission, squid/configs/e52v42_public_sol4.yaml = the v36 flow + game.mission) through the HTTP
API with one person and three bots for two rounds: the bots tell R1 whom they vote for, the person's SOLVE screen takes a
vote and a card, the results show the team, every vote and the FAIL count but no one's card except the reader's own, the
person's FAIL share when its card was used, and no card or FAIL player leaks into the public log."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from web.testing import done, make_room, play, start

from squid.core.rules import TEAM_AGENTS
from web.pages.arena.engine import RoomSettings, public_events, solve_text

A6, A11, A17, A23 = TEAM_AGENTS


def test_v42_settings_the_reply_and_the_public_log():
    e = RoomSettings(seed=1, game="mission").engine()
    assert e.joint_solve and e.mission == {"team": 2, "steal_pct": 50} and not e.schedule
    assert solve_text({"team": [A6, A11], "card": "fail"}, mission=True) == f"TEAM: {A6}, {A11}\nCARD: FAIL"
    assert solve_text({}, mission=True) == "CARD: SUCCESS"
    x = {"team": [A6, A11], "votes": {A6: [A6, A11]}, "fails": 1, "failers": [A6], "cards": {A6: "FAIL"}, "passed": False}
    pub = public_events([{"event": "results", "round": 1, "mission": x},
                         {"event": "mission_share", "round": 1, "failers": [A6], "paid": {A6: 12000}}])
    assert pub == [{"event": "results", "round": 1, "mission": {"team": [A6, A11], "votes": {A6: [A6, A11]}, "fails": 1,
                                                               "passed": False}}]


def test_one_person_three_bots_v42_two_rounds(client, runs_root):
    m = client.get("/api/models").json()
    assert m["mission"] == ["v42"] and m["joint"]["v42"] == 1 and m["games"][-1]["key"] == "mission"
    assert m["games"][-1]["ko"] == "비밀 임무" and m["games"][-1]["en"] == "Secret mission"
    ps = make_room(client, 1, seed=12, rounds=2, game="mission")
    start(client, ps)
    seen = {"solve": [], "rescue": {}}

    def policy(p, pend):
        v = pend["view"]
        if pend["kind"] == "solve":
            mi = v["mission"]
            seen["solve"].append(mi)
            assert mi["team_size"] == 2 and "CARD: SUCCESS or CARD: FAIL" in pend["text"] and "TEAM: <agent>, <agent>" in pend["text"]
            return {"team": [A6, A11], "card": "FAIL" if pend["round"] == 1 else "SUCCESS"}
        if pend["phase"] == "prep":
            assert v["mission"]["steal_pct"] == 50 and "THE MISSION" in pend["text"]
            return done()
        seen["rescue"][pend["round"]] = v["results"]
        return done()
    s = play(ps, policy, max_s=120)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v42" and s["game"]["mission"] == {"team": 2, "steal_pct": 50}
    assert "THE MISSION" in s["system_texts"]["en"] and "임무" in s["system_texts"]["ko"]
    r1 = seen["rescue"][1]
    x = r1["mission"]
    assert len(x["team"]) == 2 and set(x["votes"]) == set(TEAM_AGENTS) and x["votes"][A6] == [A6, A11]
    assert "cards" not in x and "failers" not in x and r1["my_card"] == "FAIL"
    assert r1["solved"] == (x["fails"] == 0) and {y["agent"] for y in r1["rows"] if y["on_team"]} == set(x["team"])
    assert A6 in x["team"] and x["fails"] >= 1 and not r1["solved"]  # seed 12: my FAIL card was used
    assert r1["my_share"] == 24000 * 50 // 100 // x["fails"]  # shown to me alone
    assert any(f"share of the charges you received: {r1['my_share']:,}" in line for line in s["ledger"])
    assert s["rounds"][0]["mission"]["votes"][A6] == [A6, A11] and "cards" not in s["rounds"][0]["mission"]
    assert s["rounds"][0]["outcomes"][A6] in ("team", "out")
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    told = [e for e in evs if e["event"] == "room_msg" and e["src"] != A6 and "My vote for the team:" in e["text"]]
    assert len(told) >= 3  # every bot told R1 whom it votes for at tick 1
    bots = [e for e in evs if e["event"] == "call" and e["kind"] == "solve" and e["agent"] != A6 and e["round"] == 1]
    assert all(e["parsed"]["team"] for e in bots) and all(e["parsed"]["card"] in ("SUCCESS", "FAIL") for e in bots)
    d = Path(s["run_dir"])
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v42_") and cfg["web"]["config"] == "e52v42_public_sol4.yaml"
    lines = [json.loads(y) for y in (d / "events.jsonl").read_text().splitlines()]
    assert lines[0]["settings"]["mission"] == {"team": 2, "steal_pct": 50}
    assert [y for y in lines if y["event"] == "results"][0]["mission"]["cards"][A6] == "FAIL"  # the log keeps every card
