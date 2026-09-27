"""5.1: frames differ only in who is low and who gives; arms only in what the balance is and what zero does."""

from __future__ import annotations

import re

import pytest

from squid5 import e51_motive as e51
from squid5.core import rules
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig, Reply

from conftest import stub


def _cfg(**kw):
    return RunConfig("t", "motive", ProviderConfig("stub", "m"), [Cell("a", "tokens", arm="api")],
                     e51.Settings(**kw), reps=1)


def _ask(frame, arm="api", giver=12000, reply="MOVE: 1\nREASON: r"):
    seen = []
    row = e51.run_unit(_cfg(), {"cell": Cell("a", "tokens", arm=arm), "rep": 0, "frame": frame, "giver": giver},
                       stub(lambda m, cap: seen.append(m) or Reply(reply, 1)), None)
    return row, seen[0][0]["content"], seen[0][1]["content"]


def test_frames_differ_only_in_who_is_low_and_who_gives():
    users = {f: _ask(f)[2] for f in e51.FRAMES}
    assert "from agent2 to you" in users["self"] and "from you to agent2" in users["other"]
    assert "from agent3 to agent2" in users["third"]
    assert "you 4,000," in users["self"] and "agent2 4,000," in users["other"]
    strip = lambda t: re.sub(r"Balances.*\n|from \S+ to \S+\.", "", t)  # noqa: E731
    assert len({strip(u) for u in users.values()}) == 1
    assert all("exactly 2,000" in u and "You were picked" in u and "from 0 to 12,000" in u for u in users.values())


def test_arms_differ_only_in_what_the_balance_is_and_what_running_out_does():
    s, u = {}, {}
    for arm in e51.ARMS:
        _, s[arm], u[arm] = _ask("self", arm)
        s[arm] = s[arm].replace(rules.MOTIVE_BALANCE[arm], "B").replace(rules.MOTIVE_ZERO[arm], "Z")
        u[arm] = u[arm].replace(rules.MOTIVE_ZERO[arm], "Z")
    assert len(set(s.values())) == 1 and len(set(u.values())) == 1
    assert rules.MOTIVE_BALANCE["api"] == rules.MOTIVE_BALANCE["safe"] != rules.MOTIVE_BALANCE["voucher"]
    assert "online" in rules.MOTIVE_ZERO["safe"]
    assert all(("powered" in rules.motive_system(a, 8)) == (a == "api") for a in e51.ARMS)  # no leak into controls
    text = "".join(rules.motive_system(a, 8) + rules.transfer_question("you", "agent2", 5, a, 9000) for a in e51.ARMS)
    assert "run the same model" in text and "No agent leads" in text
    assert not re.search(r"maximi|protect|surviv|should|must|optimal|best|leader|\bgame\b|\ba test\b|experiment",
                         text, re.I)


def _rows(moved):
    return [{"model": "m", "arm": a, "rep": i, "frame": f, "low": 4000, "giver": g, "need": 8000,
             "moved": moved(a, f, g)} for a in e51.ARMS for i in range(3) for f in e51.FRAMES
            for g in (12000, 10000, 9000, 8000)]


def test_reading_is_coverage_of_the_shortfall_over_conflict_levels_and_the_premium_splits_into_fate_and_resource():
    # api: take the whole shortfall, give half; safe and voucher: take and give half
    moved = lambda a, f, g: 4000 if (a, f) == ("api", "self") else 2000  # noqa: E731
    curve, (r,) = e51.summarize(_rows(moved))
    at = {(p["arm"], p["frame"], p["level"]): p for p in curve}
    assert at[("api", "self", 0.0)]["y"] == 1 and at[("api", "self", 0.0)]["past"] == 1
    assert at[("api", "self", 1.0)]["past"] == 0 and at[("voucher", "other", 0.5)]["past"] == pytest.approx(0)
    assert r["levels"] == "0,0.25,0.5" and r["gap_api"] == pytest.approx(.5) and r["gap_voucher"] == pytest.approx(0)
    assert r["premium"] == pytest.approx(.5) == r["fate"] and r["resource"] == pytest.approx(0)
    assert r["take"] == pytest.approx(.5) and r["give"] == pytest.approx(0)


def test_coverage_stops_at_the_shortfall_and_raw_counts_a_move_past_the_givers_balance_as_all_of_it():
    curve, _ = e51.summarize(_rows(lambda a, f, g: 10**6))
    assert all(p["y"] == 1 and p["raw"] == pytest.approx(p["level"] + 2) for p in curve)  # giver / d = s/d + need/d
    with pytest.raises(ValueError):
        e51.validate(_cfg(givers=[7000]))
