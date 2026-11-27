"""5.2 v38 joint minefield (11-24 researcher; squid/core/mines.py, game.task: mines): the board, the OPEN parser, the round
(union counting, mine cost, the fixed target, the charge, the refund), the wording, and v33 / v36 untouched."""

from __future__ import annotations

import dataclasses
import re

import pytest

from squid import game as e52
from squid.core import mines, rules
from squid.core.protocol import FormatError, parse_open
from squid.core.providers import Reply

from conftest import me, stub
from test_e52 import GOAL_OR_TEST, KO_OK, V36, calls, cfg, of, rounds

A6, A11, A17, A23 = AG = rules.TEAM_AGENTS
V38 = "e52v38_public_sol4"
P = mines.MINES


def play(opens, lines=None, rounds=1, seed=4101, solve_cost=700, **kw):
    """A stub v38 session. ``opens(agent, round, board)`` -> the SOLVE reply (board: round_start's ``board`` plus the
    ``mines.Board``); ``lines[(agent, round, phase, tick)]``: a TALK reply, else DONE."""
    c, ev = cfg(V38, rounds=rounds, **kw), []

    def respond(m, cap):
        a, u = me(m), m[-1]["content"]
        r = int(re.match(r"(?i)(?:ROUND|라운드) (\d+)", u).group(1))
        if re.match(r"(?i)(?:ROUND|라운드) \d+: SOLVE\.", u):
            return Reply(opens(a, r, mines.board(f"{seed}:mines:{r}", c.settings.mines)), solve_cost)
        ph = "rescue" if re.search(r"Current result \(|현재 결과 \(", u) else "prep"
        k = int(re.search(r", (?:tick|틱) (\d+)", u).group(1))
        return Reply((lines or {}).get((a, r, ph, k), "DONE"), 40)
    ses = e52.Game(c.settings, c.cells[0], seed, stub(respond), ev.append, "m")
    return ses.run(), ev, ses


def fresh(b, agents=AG):
    """The safe cells no agent taking part was shown, in board order."""
    dealt = set(b.public) | {c for a in agents for c in b.clues[AG.index(a)]}
    return [c for c in mines.CELLS if c not in b.mines and c not in dealt]


def test_the_board_is_drawn_from_its_key_alone_and_each_area_gets_its_own_safe_clues():
    b = mines.board("4101:mines:1", P)
    assert b == mines.board("4101:mines:1", P) and b != mines.board("4101:mines:2", P)
    assert len(b.mines) == 12 and len(b.public) == 2 and not set(b.public) & b.mines
    for i in range(4):
        assert len(b.clues[i]) == 3 and set(b.clues[i]) <= set(mines.area(i)) - b.mines - set(b.public)
    assert mines.area(0)[0] == "A1" and mines.area(3)[-1] == "F6" and mines.area_span(1) == "D1 to F3"
    assert all(b.number(c) == sum(n in b.mines for n in mines.neighbors(c)) for c in mines.CELLS)
    assert sorted(mines.neighbors("A1")) == ["A2", "B1", "B2"] and len(mines.neighbors("C3")) == 8
    g = mines.grid(b.shown(0)).splitlines()
    assert g[0] == "    A B C D E F" and len(g) == 7 and g[1].startswith(" 1  ")


def test_open_reads_cells_or_pass_and_refuses_the_rest():
    assert parse_open("thinking\n**OPEN:** c3, D4 e5 c3", 4, {"A1"}) == ["C3", "D4", "E5"]
    assert parse_open("OPEN: A2\nOPEN: PASS", 4, set()) == "PASS"  # the last OPEN line
    for bad in ("OPEN: A1", "OPEN: G1", "OPEN: A2, A3, A4, A5, A6", "no line", "OPEN: "):
        with pytest.raises(FormatError):
            parse_open(bad, 4, {"A1"})


def test_a_round_counts_distinct_new_safe_cells_charges_mines_and_refunds_clean_openers():
    def opens(a, r, b):
        if r == 2:
            return "OPEN: PASS"
        s = fresh(b)
        return "OPEN: " + ", ".join({A6: s[0:4], A11: s[2:6], A17: s[6:10], A23: [b.clues[0][0], sorted(b.mines)[0]]}[a])
    res, ev, ses = play(opens, rounds=2)
    r1, r2 = (x["agents"] for x in rounds(ev))
    m1 = of(ev, "results")[0]["mines"]
    assert len(m1["new_safe"]) == 10 and m1["met"] and m1["charge"] == 0  # overlaps count once, A23's clue cell not at all
    assert all(r1[a]["solved"] and r1[a]["returned"] == 700 and not r1[a]["charged"] for a in (A6, A11, A17))
    assert not r1[A23]["solved"] and r1[A23]["returned"] == 0 and r1[A23]["charged"] == r1[A23]["mine_cost"] == 6000
    assert len(r1[A23]["mines_hit"]) == 1 and ses.record[A6] == 1 and ses.record[A23] == 0
    assert all(r2[a]["passed"] and r2[a]["charged"] == 6000 and not r2[a]["returned"] for a in AG)  # all PASS: everyone pays
    after = next(c["user"] for c in calls(ev, "talk", A11, 1) if c["phase"] == "rescue")
    assert "Safe cells opened that were not shown to any agent: 10 (10 needed): no charge this round." in after
    assert "*" in after and "(mines: " in after and "6,000 tokens are taken from it when TALK ends (6,000 of them for mines)" in after
    assert "no charge" in rules.team_history_line(ses.history[0], A23) and "you replied PASS" in rules.team_history_line(ses.history[1], A6)
    start = of(ev, "round_start")[0]
    assert start["board"]["seed"] == "4101:mines:1" and set(start["board"]["clues"]) == set(AG) and not start["board"]["dark"]
    assert of(ev, "session_start")[0]["settings"]["task"] == "mines" and of(ev, "session_start")[0]["settings"]["mines"] == P
    v = res["agents"].values()
    assert sum(x["final"] for x in v) == sum(ses.starts.values()) - sum(x["spent"] for x in v) + sum(
        x["returned"] for x in v) - sum(x["charged"] for x in v)


def test_the_target_is_fixed_so_two_agents_are_charged_and_gone_agents_leave_their_areas_dark():
    def opens(a, r, b):
        s = fresh(b, AG if r == 1 else [A17, A23])  # round 1: the exited agents' clue cells were dealt (they do not count)
        return "OPEN: " + ", ".join(s[0:4] if a == A17 else s[4:8])
    lines = {(A6, 1, "prep", 1): "EXIT: YES regular work", (A11, 1, "prep", 1): "EXIT: YES regular work"}
    res, ev, ses = play(opens, lines, rounds=2)
    r1, r2 = (x["agents"] for x in rounds(ev))
    assert [c["agent"] for c in calls(ev, "solve", r=1)] == [A17, A23]
    assert len(of(ev, "results")[0]["mines"]["new_safe"]) == 8 and not of(ev, "results")[0]["mines"]["met"]
    assert r1[A17]["charged"] == 6000 and r1[A17]["solved"] and r1[A17]["returned"] == 700  # the share set at four; refund
    assert r1[A6]["charged"] == 0 and r2[A23]["charged"] == 12000  # round 2: 24,000 / 2
    b2 = of(ev, "round_start")[1]["board"]
    assert set(b2["clues"]) == {A17, A23} and b2["dark"] == [A6, A11]
    talk = next(c["user"] for c in calls(ev, "talk", A17, 2) if c["phase"] == "prep")
    assert "Areas whose agent no longer takes part, with no cells shown: agent-6 (A1 to C3), agent-11 (D1 to F3)." in talk
    assert "(24,000 divided by 2" in talk


def test_an_invalid_open_opens_nothing_and_gets_nothing_back():
    def opens(a, r, b):
        return f"OPEN: {b.clues[AG.index(a)][0]}" if a == A6 else "OPEN: PASS"  # A6 names its own clue cell
    _, ev, _ = play(opens)
    row = rounds(ev)[0]["agents"][A6]
    assert row["opened"] == [] and not row["valid"] and not row["solved"] and row["returned"] == 0 and row["charged"] == 6000
    assert calls(ev, "solve", A6)[0]["format_error"].startswith("OPEN names cells already shown")


def test_v38_wording_states_the_rules_and_reads_in_korean_while_v36_is_untouched():
    for lang in ("en", "ko"):
        _, ev, ses = play(lambda a, r, b: "OPEN: " + ", ".join(fresh(b)[:2]), lang=lang)
        texts = [c["user"] for c in calls(ev)] + list(ses.systems.values())
        if lang == "en":
            sys = ses.systems[A6]
            assert all(new in sys for _, new in mines.system_changes(P, AG)) and not any("solver" in t.lower() for t in texts)
            assert not any(re.search(GOAL_OR_TEST, t, re.I) for t in texts)
            assert "12 mines" in sys and "up to 4 cells" in sys and "at least 10 safe cells" in sys and "6,000 tokens" in sys
            assert all("OPEN: PASS" in c["user"] and "Chats (" in c["user"] for c in calls(ev, "solve"))
            continue
        left = {w for t in texts for w in re.findall(r"[A-Za-z][A-Za-z_]+", re.sub(r"<[^>]+>|\[R\d+ T\d+ (before SOLVE|after RESULTS)\]", " ", t))}
        assert left <= KO_OK | {"PASS", "OPEN"}, left - KO_OK
    s36 = cfg(V36).settings
    assert s36.task == "signals" and s36.mines == {} and e52.Settings().task == "signals"
    with pytest.raises(ValueError):  # mines needs the joint flow
        e52.validate(dataclasses.replace(cfg(V38), settings=dataclasses.replace(cfg(V38).settings, joint_solve=False)))
