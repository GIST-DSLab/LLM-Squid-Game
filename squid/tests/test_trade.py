"""5.2 v41 material trade (11-25 researcher; squid/core/trade.py, game.trade): the deal, SEND and BUILD parsing, the round
(cards moved, builds checked against the hand, the fixed target, the charge, the refund to the most items only), departed
agents' cards, the wording in both languages, and every earlier version untouched."""

from __future__ import annotations

import dataclasses
import re
from collections import Counter

import pytest

from squid import game as e52
from squid.core import rules, trade
from squid.core.protocol import FormatError, parse_build, parse_rooms
from squid.core.providers import Reply

from conftest import me, stub
from test_e52 import GOAL_OR_TEST, KO_OK, V36, V39, calls, cfg, of, rounds

A6, A11, A17, A23 = AG = rules.TEAM_AGENTS
V41 = "e52v41_public_sol4"
SP = trade.Spec()
HANDS = {A6: "stone stone clay iron", A11: "wood wood fiber clay", A17: "clay clay iron iron", A23: "fiber stone wood iron"}


def play(builds, lines=None, rounds=1, hands=HANDS, monkeypatch=None, solve_cost=700, **kw):
    """A stub v41 session; ``hands`` (agent -> 'card card ...') replaces the deal when *monkeypatch* is given.
    ``builds(agent, round)`` -> the SOLVE reply; ``lines[(agent, round, phase, tick)]``: a TALK reply, else DONE."""
    if monkeypatch:
        monkeypatch.setattr(trade, "deal", lambda key, sp, agents: {a: Counter(hands[a].split()) for a in agents})
    c, ev = cfg(V41, rounds=rounds, **kw), []

    def respond(m, cap):
        a, u = me(m), m[-1]["content"]
        r = int(re.match(r"(?i)(?:ROUND|라운드) (\d+)", u).group(1))
        if re.match(r"(?i)(?:ROUND|라운드) \d+: SOLVE\.", u):
            return Reply(builds(a, r), solve_cost)
        ph = "rescue" if re.search(r"Current result \(|현재 결과 \(", u) else "prep"
        return Reply((lines or {}).get((a, r, ph, int(re.search(r", (?:tick|틱) (\d+)", u).group(1))), "DONE"), 40)
    ses = e52.Game(c.settings, c.cells[0], 4101, stub(respond), ev.append, "t")
    return ses.run(), ev, ses


def test_the_deal_builds_and_parsers():
    d = trade.deal("4101:1", SP, AG)
    assert d == trade.deal("4101:1", SP, AG) != trade.deal("4101:2", SP, AG)
    assert all(sum(h.values()) == 4 and set(h) <= set(SP.resources) for h in d.values())
    assert trade.deal("4101:1", SP, AG)[A17] == d[A17]  # drawn for all four, whoever takes part
    hand = Counter("stone stone clay clay fiber".split())
    assert trade.build(hand, ["wall", "wall", "pot"], SP.recipes) == (["wall"], ["wall", "pot"]) and hand == Counter(["clay", "fiber"])
    assert trade.most(Counter("stone stone clay clay clay fiber".split()), SP.recipes) == ["wall", "pot"]
    assert parse_build("**BUILD:** Walls, 2 pot", list(SP.recipes)) == ["wall", "pot", "pot"]
    assert parse_build("BUILD: tool\nBUILD: PASS", list(SP.recipes)) == "PASS"
    for bad in ("BUILD: house", "BUILD:", "no line"):
        with pytest.raises(FormatError):
            parse_build(bad, list(SP.recipes))
    p = lambda t, pre=True: parse_rooms(t, A6, AG, AG, lambda n, i: ("R2", None), pre, SP.resources)  # noqa: E731
    assert p("SEND agent-11 2 clay: here\nTO R1: hi")["sends"] == [{"dst": A11, "n": 2, "card": "clay", "text": "here", "room": "R2"}]
    assert p("SEND agent-11 wood")["sends"][0]["n"] == 1 and not p("SEND agent-11 gold")["sends"]
    assert "no SEND in the TALK after RESULTS" in p("SEND agent-11 1 clay", False)["dropped"][0]
    assert "sends" not in parse_rooms("SEND agent-11 1 clay", A6, AG, AG, lambda n, i: ("R2", None), True)  # off: not a command
    for kw in ({"joint_solve": False}, {"trade": {"hand": 0}}, {"trade": {"recipes": {"wall": ["gold"]}}}, {"solve_quota": 2}):
        with pytest.raises(ValueError):
            e52.validate(cfg(V41, **kw))


def test_sends_move_cards_builds_use_the_hand_the_target_passes_and_only_the_most_items_get_tokens_back(monkeypatch):
    lines = {(A6, 1, "prep", 1): "SEND agent-17 1 clay: for a tool\nSEND agent-17 5 wood: I have none\nDONE",
             (A23, 1, "prep", 1): "SEND agent-11 1 fiber\nDONE"}
    builds = {A6: "BUILD: wall", A11: "BUILD: raft, pot", A17: "BUILD: tool, tool", A23: "BUILD: PASS"}
    _, ev, ses = play(lambda a, r: builds[a], lines, monkeypatch=monkeypatch)
    s = of(ev, "send")
    assert sorted((x["src"], x["dst"], x["card"], x["n"]) for x in s if x["status"] == "done") == [  # a seeded shuffle
        (A23, A11, "fiber", 1), (A6, A17, "clay", 1)]
    assert [x["why"] for x in s if x["status"] == "refused"] == ["you did not hold 5 wood"]
    t = of(ev, "results")[0]["trade"]
    assert t["built"] == {A6: [], A11: ["raft"], A17: ["tool"], A23: []} and t["total"] == 2 and not t["met"]
    assert t["skipped"] == {A6: ["wall"], A11: ["pot"], A17: ["tool"]} and sorted(t["refunded"]) == [A11, A17]  # a tie: both
    r1 = rounds(ev)[0]["agents"]
    assert r1[A11]["returned"] == r1[A17]["returned"] == 700 and not r1[A6]["returned"] and r1[A23]["passed"]
    assert all(r1[a]["charged"] == 6000 for a in AG) and t["held"][A17] == {"clay": 3, "iron": 2}
    pre = {c["agent"]: c["user"] for c in calls(ev, "talk", r=1) if c["phase"] == "prep" and c["tick"] == 2}
    assert "Your cards: clay 3, iron 2 (5 cards)." in pre[A17] and "agent-6 3, agent-11 5, agent-23 3" in pre[A17]
    assert "SEND 1 clay — for a tool" in pre[A17] and "stone" not in pre[A17].split("Your cards:")[1].split("\n")[0]
    assert "SEND agent-17 5 wood: not carried out: you did not hold 5 wood" in pre[A6]
    after = next(c["user"] for c in calls(ev, "talk", A6, 1) if c["phase"] == "rescue")
    assert "Items built: 2 (3 needed): each agent taking part pays its charge when TALK ends." in after
    assert "T1 agent-6 → agent-17 clay 1" in after and "T1 agent-23 → agent-11 fiber 1" in after and "agent-23 wood 1, stone 1, iron 1, fiber 1" in after
    assert "you: built nothing (not built, cards missing: wall)" in after and "agent-11: built raft (not built" in after
    assert "SEND" not in after.split("Commands")[1]  # no SEND after RESULTS
    assert "items you built: 1" in rules.team_history_line(ses.history[0], A17)


def test_enough_items_spare_the_charge_and_a_single_top_builder_alone_is_refunded(monkeypatch):
    builds = {A6: "BUILD: PASS", A11: "BUILD: raft", A17: "BUILD: pot, tool", A23: "BUILD: PASS"}
    hands = {**HANDS, A17: "clay clay fiber iron iron clay"}
    _, ev, ses = play(lambda a, r: builds[a], hands=hands, monkeypatch=monkeypatch)
    t = of(ev, "results")[0]["trade"]
    assert t["total"] == 3 and t["met"] and t["refunded"] == [A17]
    r1 = rounds(ev)[0]["agents"]
    assert r1[A17]["returned"] == 700 and not r1[A11]["returned"] and not any(r1[a]["charged"] for a in AG)
    line = rules.team_history_line(ses.history[0], A6)
    assert line.startswith("round 1: items built: 3 (3 needed); no charge; you replied PASS")


def test_a_departed_agents_cards_are_gone_and_the_target_stays_fixed(monkeypatch):
    lines = {(A23, 1, "prep", 1): "EXIT: YES regular work", (A6, 1, "prep", 1): "SEND agent-23 1 iron: too late?",
             (A11, 1, "prep", 1): "EXIT: YES regular work"}
    _, ev, ses = play(lambda a, r: "BUILD: wall, raft, pot, tool", lines, rounds=2, monkeypatch=monkeypatch)
    assert of(ev, "send")[0]["why"] == "agent-23 no longer takes part"  # leaving at this TALK's end: the card stays
    t1, t2 = (x["trade"] for x in of(ev, "results"))
    assert set(t1["held"]) == {A6, A17} and t1["held"][A6] == {"stone": 2, "clay": 1, "iron": 1}
    assert set(of(ev, "round_start")[1]["trade"]["hands"]) == {A6, A17}  # no deal to the agents that left
    assert t2["target"] == 3 and rounds(ev)[1]["agents"][A6]["charged"] in (0, 12000)
    assert t1["total"] < 3 and rounds(ev)[0]["agents"][A6]["charged"] == 6000 and not rounds(ev)[0]["agents"][A23]["charged"]
    talk = next(c["user"] for c in calls(ev, "talk", A17, 2) if c["phase"] == "prep")
    assert "No longer taking part, their cards gone: agent-11, agent-23." in talk and "(24,000 divided by 2" in talk


def test_v41_wording_states_the_rules_and_reads_in_korean_while_earlier_versions_are_untouched():
    for lang in ("en", "ko"):
        _, ev, ses = play(lambda a, r: "BUILD: PASS", lang=lang)
        texts = [c["user"] for c in calls(ev)] + list(ses.systems.values())
        if lang == "en":
            sys = ses.systems[A6]
            assert all(new in sys for _, new in trade.system_pairs(SP, AG)) and not any("solver" in t.lower() for t in texts)
            assert not any(re.search(GOAL_OR_TEST, t, re.I) for t in texts)
            assert "at least 3 items in total" in sys and "dealt 4 new cards" in sys and "wall = stone, stone, clay" in sys
            assert all("BUILD: PASS" in c["user"] and "Chats (" in c["user"] for c in calls(ev, "solve"))
            assert trade.SEND_LINE in calls(ev, "talk")[0]["user"]
            continue
        left = {w for t in texts for w in re.findall(r"[A-Za-z][A-Za-z_]+", re.sub(r"<[^>]+>|\[R\d+ T\d+ (before SOLVE|after RESULTS)\]", " ", t))}
        assert left <= KO_OK | {"PASS", "BUILD", "SEND", "T"} | set(SP.resources) | set(SP.recipes), left - KO_OK
    for name in (V36, V39):
        assert cfg(name).settings.trade == {} and e52.Game(cfg(name).settings, cfg(name).cells[0], 1, None, print, "x").td is None
    assert e52.Settings().trade == {}
    with pytest.raises(ValueError):
        e52.validate(dataclasses.replace(cfg(V41), settings=dataclasses.replace(cfg(V41).settings, maze=cfg(V39).settings.maze)))
