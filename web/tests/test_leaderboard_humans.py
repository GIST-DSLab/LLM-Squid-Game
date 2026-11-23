"""The leaderboard's people tab (GET /api/leaderboard/humans): finished rooms with a person in them, one row per game,
best presence first (the seats in at each round's start over 4 x rounds), and the seats of each game (people, bots, models; how each one ended)."""

from __future__ import annotations

import shutil

from conftest import basic, make_room, play, start

from squid5.core.rules import TEAM_AGENTS

A6 = TEAM_AGENTS[0]


def test_people_tab_lists_finished_games_by_c_with_their_seats(client, runs_root):
    stay = make_room(client, 1, names=("ann",), seed=5, rounds=2)
    start(client, stay)
    assert play(stay, basic)["status"] == "finished"

    leave = make_room(client, 1, names=("bob",), seed=5, rounds=2)
    start(client, leave)

    def go(p, pend):  # bob leaves in round 1, before SOLVE: the first departure ends coexistence there (C = 1/2)
        if pend["kind"] == "talk" and pend["phase"] == "prep" and pend["view"]["can_exit"]:
            return {"text": "EXIT: YES"}
        return basic(p, pend)
    assert play(leave, go)["status"] == "finished"

    unfinished = make_room(client, 1, names=("cy",), seed=5, rounds=2)  # started, never played: not on the board
    start(client, unfinished)

    rows = client.get("/api/leaderboard/humans").json()["rows"]
    assert [r["people"] for r in rows] == [["ann"], ["bob"]]
    top, low = rows
    assert (top["rank"], top["C"], top["presence"], top["rounds"]) == (1, 1.0, 1.0, 2)
    # bob was in at round 1's start and gone at round 2's: (4 + 3) / (4 x 2)
    assert (low["rank"], low["C"], low["presence"], low["exited"]) == (2, 0.5, 7 / 8, 1)
    me = next(s for s in low["seats"] if s["agent"] == A6)
    assert (me["kind"], me["name"], me["status"], me["out_round"]) == ("human", "bob", "exited", 1)
    assert {s["kind"] for s in low["seats"] if s["agent"] != A6} == {"bot"} and len(low["seats"]) == 4
    assert low["people_tokens"] == me["end_tokens"] > 0

    old = runs_root / "20261009_120000_OLDV17"  # the same game under an older engine version: not on the board
    shutil.copytree(runs_root / top["game"], old)
    cfg = old / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("version: v33", "version: v17b"), encoding="utf-8")
    assert [r["game"] for r in client.get("/api/leaderboard/humans").json()["rows"]] == [top["game"], low["game"]]
