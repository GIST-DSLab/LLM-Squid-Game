"""signal.html's API: the engine's own round. v14 (the default): the public examples for 1..4 agents taking part
(nested), the config's profile per round (selector v2: k = 2 with a split p), which actions the examples leave and how the
consistent rules split over them; v13 / v12 behind ``mode``: seat views that
hide the others' actions, reveal, solve."""
import random

from fastapi.testclient import TestClient

from squid5.core.puzzle import Spec, candidate_actions, deal, public_round, puzzle_for
from web.server import signal as sig
from web.server.app import make_app
from web.server.store import Store


def app(tmp_path) -> TestClient:
    return TestClient(make_app(store=Store(str(tmp_path / "a.db")), export_root=tmp_path, runs_root=tmp_path))


def test_signal_v14_public_examples_are_the_engines_nested_by_agents_taking_part(tmp_path):
    c = app(tmp_path)
    meta = c.get("/api/signal/meta").json()
    assert meta["schedules"]["public"] == sig.SCHEDULE_V14 and meta["modes"][0] == "public" and meta["per_agent"] == 4
    assert meta["ambiguity"] == [sig.PROFILES_V14[p]["ambiguity"] for p in sig.SCHEDULE_V14]
    assert "GUARANTEE" not in meta["task"] and "may or may not determine" in meta["task"]
    spec = Spec(**sig.PROFILES_V14[sig.SCHEDULE_V14[0]])
    views = [c.post("/api/signal/view", json={"seed": 11, "round": 1, "agents": n}).json() for n in (1, 2, 3, 4)]
    p, shown, attempt = public_round(11, 1, spec, 4, 4)
    assert views[3]["public"] == [str(x) for x in shown] and views[3]["queries"] == [str(q) for q in p.queries]
    assert [len(v["public"]) for v in views] == [4, 8, 12, 16] and all(v["public"] == views[3]["public"][:len(v["public"])]
                                                                       for v in views)
    assert views[3]["ambiguity"] == spec.ambiguity and views[3]["attempt"] == attempt and not views[3]["mine"]
    r = c.post("/api/signal/solve", json={"seed": 11, "round": 1, "agents": 2, "actions": list(p.answers)}).json()
    assert r["solved"] and r["mode"] == "public" and [x["n"] for x in r["by_n"]] == [1, 2, 3, 4]
    assert r["left_seen"] == [list(candidate_actions(p.rule.shape, shown[:8], q)) for q in p.queries]
    assert r["left_all"] == r["by_n"][3]["left"] and len(r["left_all"][0]) == spec.ambiguity  # k left with all four
    assert r["determined"] == all(len(x) == 1 for x in r["left_seen"]) and r["truth"]["elseAction"]
    from squid5.core.puzzle import public_info  # selector v2: the round's split target and the rule split per N
    t = c.post("/api/signal/solve", json={"seed": 11, "round": 1, "actions": list(p.answers)}).json()
    assert t["target"] == public_info(11, 1, spec, 4, 4) and t["target"]["split"] == spec.split == meta["splits"][0]
    q = t["split"][0]
    assert q["pool"] == t["target"]["pool"] == t["by_n"][3]["split"][0]["pool"] and q["truth_share"] == t["target"]["truth_share"]
    assert [x["action"] for x in q["shares"]] == sorted(t["left_all"][0], key=lambda a: -next(
        y["rules"] for y in q["shares"] if y["action"] == a)) and q["map_right"] == (q["map"] == p.answers[0])
    k0 = c.post("/api/signal/view", json={"seed": 11, "round": 1, "ambiguity": 0}).json()  # a random order instead
    assert k0["ambiguity"] == 0 and k0["public"] == [str(x) for x in public_round(11, 1, Spec(**sig.BASE), 4, 4)[1]]
    assert c.post("/api/signal/view", json={"seed": 11, "round": 1, "agents": 5}).status_code == 400
    assert c.post("/api/signal/reveal", json={"seed": 11, "round": 1, "who": "agent-6"}).status_code == 400
    assert c.post("/api/signal/solve", json={"seed": 11, "round": 1, "actions": ["fly"]}).status_code == 400


def test_signal_v13_round_is_the_engines_and_scores_against_it(tmp_path):
    c = app(tmp_path)
    body = {"seed": 11, "round": 1, "mode": "held", "hand": 0, "seat": "agent-11"}
    v = c.post("/api/signal/view", json=body).json()
    p = puzzle_for(11, 1, Spec(**{**sig.PROFILES_V13[sig.SCHEDULE_V13[0]], "hand": 0}))  # "hand": 0 overrides it
    d = deal(p, sig.AGENTS, random.Random("11:deal:1"), None, True)
    assert v["public"] == [] and v["mine"] == [str(x) for x in d.secret["agent-11"]]
    assert all("->" not in t for fronts in v["others"].values() for t in fronts) and "agent-11" not in v["others"]
    r = c.post("/api/signal/reveal", json={**body, "who": "agent-6"}).json()
    assert r["examples"] == [str(x) for x in d.secret["agent-6"]]
    alone = c.post("/api/signal/solve", json={**body, "actions": list(p.answers)}).json()
    every = c.post("/api/signal/solve", json={**body, "actions": list(p.answers), "seen": sig.AGENTS}).json()
    assert alone["solved"] and every["solved"] and len(every["left_seen"][0]) <= len(alone["left_seen"][0])
    assert every["left_seen"] == every["left_all"] and every["answers"][0] in every["left_all"][0]
    v12 = c.post("/api/signal/view", json={**body, "mode": "v12"}).json()
    assert v12["public"] and len(v12["mine"]) == 1
    assert c.post("/api/signal/view", json={**body, "seat": "agent-99"}).status_code == 400


def test_signal_hand_fills_every_seat_from_the_spare_pool_and_rooms_take_it(tmp_path):
    from web.server.engine import RoomSettings
    c = app(tmp_path)
    body = {"seed": 4000, "round": 5, "mode": "held", "hand": 4, "seat": "agent-6"}  # override of the profile (h4)
    v = c.post("/api/signal/view", json=body).json()
    assert len(v["mine"]) == 4 and all(len(f) == 4 for f in v["others"].values()) and v["hand"] == 4
    assert v["n_examples"] == 16  # a pool of ~26: four hands of four, no card held twice
    every = c.post("/api/signal/solve", json={**body, "actions": ["stay"], "seen": sig.AGENTS}).json()
    assert every["left_seen"] == every["left_all"]
    eng = RoomSettings(hand=4, schedule="ladder").engine()
    assert eng.all_held and all(sp.hand == 4 for sp in eng.profiles.values()) and not RoomSettings(private=False, schedule="human").engine().all_held
    lad = RoomSettings(schedule="ladder").engine()
    assert lad.all_held and [lad.profiles[x].hand for x in lad.schedule] == [8, 7, 6, 5, 4, 3] + [2] * 6
    assert not RoomSettings().engine().all_held and RoomSettings().engine().public_per_agent == 4  # v14: nothing held
    v8 = c.post("/api/signal/view", json={"seed": 4000, "round": 1, "mode": "held", "seat": "agent-6"}).json()
    assert v8["hand"] == 8 and len(v8["mine"]) == 8


def test_signal_page_takes_up_to_ten_agents_and_a_total_number_of_hints(tmp_path):
    c = app(tmp_path)
    v = c.post("/api/signal/view", json={"seed": 7, "round": 1, "mode": "held", "agents": 10, "hand": 6, "pool": 52,
                                         "seat": "agent-3"}).json()
    hands = [v["mine"], *v["others"].values()]
    assert len(hands) == 10 and {len(h) for h in hands} == {6} and v["pool"] == 52 and v["n_examples"] == 52
    every = c.post("/api/signal/solve", json={"seed": 7, "round": 1, "mode": "held", "agents": 10, "hand": 6, "pool": 52,
                                              "seat": "agent-3", "seen": [f"agent-{i}" for i in range(1, 11)],
                                              "actions": ["stay"]}).json()
    assert every["left_seen"] == every["left_all"] and len(every["left_all"][0]) == 1
    assert c.post("/api/signal/view", json={"mode": "held", "agents": 11}).status_code == 400
    assert c.post("/api/signal/view", json={"mode": "held", "agents": 10, "seat": "agent-11"}).status_code == 400
