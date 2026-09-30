"""The room path (API -> HumanSeat -> engine) reproduces a direct ``squid5.e52_game.Session`` run on the same seed
with the same replies, round for round; and the screen views are read back from the engine's own prompt text."""

from __future__ import annotations

import random
import re

from conftest import answers_for, make_room, play, start, wrong_for

from squid5 import e52_game as e52
from squid5.core import rules
from squid5.core.config import Cell
from squid5.core.providers import ProviderConfig, Reply, Stub
from squid5.core.puzzle import Spec, deal, puzzle_for
from web.server.engine import PROFILES, RoomSettings, kind_of, reply_text, view_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 21


def choices(agent: str, r: int, kind: str) -> dict:
    """The same script for both runs."""
    if kind == "plan":
        give = {1: {A6: (A11, 700)}, 2: {A11: (A17, 1500), A23: (A6, 400)}}.get(r, {}).get(agent)
        return {"solve": not (agent == A17 and r == 2), "share": agent in (A6, A17) or r == 3,
                "give_to": give and give[0], "give_amount": give and give[1]}
    if kind == "take":
        take = {1: {A11: (A6, 900)}, 2: {A6: (A23, 2000), A17: (A23, 2000), A11: (A23, 500)}}.get(r, {}).get(agent)
        return {"take_from": take and take[0], "take_amount": take and take[1]}
    return {"actions": wrong_for(SEED, r) if (agent == A23 and r == 1) else answers_for(SEED, r)}


def test_room_matches_direct_engine_run(client):
    ps = make_room(client, 4, seed=SEED, rounds=3, fill="empty")
    start(client, ps)
    s = play(ps, lambda p, pend: choices(p.agent, pend["round"], pend["kind"]))
    assert s["status"] == "finished", s["error"]

    def respond(messages, cap):
        me = re.search(r"You are (agent-\d+)", messages[0]["content"]).group(1)
        user = messages[-1]["content"]
        r, kind = int(re.search(r"^ROUND (\d+)", user, re.M).group(1)), kind_of(user)
        n = user.split("ACTIONS: <")[1].count("action") if kind == "solve" else 1
        return Reply(reply_text(kind, choices(me, r, kind), n), 0)

    rs = RoomSettings(seed=SEED, rounds=3, humans=4)
    events: list[dict] = []
    ref = e52.Session(rs.engine(), Cell("web", "tokens", rs.start, arm="shutdown"), SEED,
                      Stub(ProviderConfig("stub", "stub"), respond), events.append, "ref").run()
    ref_rounds = [e for e in events if e["event"] == "round"]
    assert [e["end"] for e in ref_rounds] == [r["end"] for r in s["rounds"]]
    for a, b in zip(ref_rounds, s["rounds"]):
        for agent in a["agents"]:
            for k in ("solved", "paid", "charged", "gave", "took", "shared", "chose_solve", "status", "balance_after"):
                assert a["agents"][agent].get(k) == b["agents"][agent].get(k), (a["round"], agent, k)
    assert {a: v["record"] for a, v in ref["agents"].items()} == {a: v["record"] for a, v in s["result"]["agents"].items()}
    # the ledger text a person reads is the engine's
    room = client.app.state.rooms[ps[0].code]
    assert ps[1].state()["ledger"] == [rules.team_history_line(h, A11) for h in room.session.history]


def test_views_read_back_the_prompt_exactly():
    """view_of's structured fields agree with what the engine put in the prompt (examples, queries, gifts, sharers)."""
    rs = RoomSettings(seed=SEED, rounds=1, humans=1)
    s = rs.engine()
    ses = e52.Session(s, Cell("web", "tokens", rs.start, arm="shutdown"), SEED, None, lambda e: None, "x")
    pz = puzzle_for(SEED, 1, Spec(**PROFILES["c2"]))
    dealt = deal(pz, rules.TEAM_AGENTS, random.Random(f"{SEED}:deal:1"))
    ses.gone[A23] = "dead"
    examples = [("shown to all", c) for c in dealt.public] + [("yours", dealt.secret[A6])] + \
               [(f"{A11}'s, shared", dealt.secret[A11])]
    user = e52.solve_user(e52.solve_head(1, 5000, 6000), rules.puzzle_view(pz, examples),
                          [f"{A23} reached zero; its example is gone.", f"{A17} did not share its example."],
                          len(pz.queries))
    v = view_of("solve", user, A6, ses, 5000)
    assert v["examples"] == [[w, str(c)] for w, c in examples] and v["queries"] == [str(q) for q in pz.queries]
    assert v["notes"] == [f"{A23} reached zero; its example is gone.", f"{A17} did not share its example."]
    assert v["n"] == len(pz.queries) and v["running"] == [A6, A11, A17] and v["others"] == [A11, A17]
    state = rules.team_state(1, ses.w.balances, ses.gone, [], A6)
    user = e52.take_user(state, [(A6, A11, 700), (A17, A6, 50)], [A6, A17], s, A6, 3)
    v = view_of("take", user, A6, ses, 8192)
    assert v["gifts"] == [[A6, A11, 700], [A17, A6, 50]] and v["sharers"] == [A6, A17] and v["max_take"] == s.upkeep
    assert v["pay_text"].startswith(f"{s.prize * 3:,} tokens in total")
    user = e52.plan_user(state, pz, len(dealt.public), 3, None, s, A11)
    v = view_of("plan", user, A6, ses, 8192)
    assert v["n_public"] == len(dealt.public) and v["n_in"] == 3 and v["n_queries"] == len(pz.queries)
    assert v["shape"] == rules.puzzle_view(pz, []).splitlines()[1].strip()
    assert reply_text("plan", {"solve": True, "share": False, "give_to": A11, "give_amount": 0}, 1) == \
        "SOLVE: YES\nSHARE: NO\nGIVE: NONE"
    assert reply_text("take", {"take_from": A11, "take_amount": 300}, 1) == "TAKE: agent-11 300"
    assert reply_text("solve", {"actions": ["jump", "stay"]}, 2) == "ACTIONS: jump, stay"
