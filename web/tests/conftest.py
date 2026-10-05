"""Shared fixtures: an app on a temporary SQLite store, and a driver that plays humans through the HTTP API."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.server.app import make_app  # noqa: E402
from web.server.store import Store  # noqa: E402


@pytest.fixture
def store(tmp_path):
    st = Store(tmp_path / "arena.db")
    yield st
    st.close()


@pytest.fixture
def runs_root(tmp_path):
    return tmp_path / "live"


@pytest.fixture
def client(store, tmp_path, runs_root):
    app = make_app(store, export_root=tmp_path / "runs", runs_root=runs_root)
    with TestClient(app) as c:
        c.app_state = app.state
        yield c
    for room in app.state.rooms.values():
        room.close()


class Player:
    def __init__(self, client: TestClient, code: str, token: str, agent: str, name: str):
        self.c, self.code, self.token, self.agent, self.name = client, code, token, agent, name
        self.seen: list[dict] = []  # every screen this player met: pending + submit reply (or "skipped")

    def state(self) -> dict:
        r = self.c.get(f"/api/rooms/{self.code}/state", params={"token": self.token})
        assert r.status_code == 200, r.text
        return r.json()

    def submit(self, body: dict) -> dict:
        """The reply, or the screen's recorded end (``state.last``) if the server closed it first (overdraw)."""
        r = self.c.post(f"/api/rooms/{self.code}/submit", params={"token": self.token}, json=body)
        if r.status_code == 409:
            last = self.state()["last"]
            assert last and (last["round"], last["kind"]) == (body["round"], body["kind"]), last
            return {**last, "closed_by_server": True}
        assert r.status_code == 200, r.text
        return r.json()

    def screens(self, kind: str | None = None, round_no: int | None = None) -> list[dict]:
        return [x for x in self.seen if (kind is None or x["kind"] == kind)
                and (round_no is None or x["round"] == round_no)]


def make_room(client: TestClient, humans: int, names=("ann", "bob", "cy", "dee"), **settings) -> list[Player]:
    settings = {"humans": humans, "rounds": 2, "seed": 11, "talk_timeout_s": 30, "timeout_s": 30, "rate": 1e-9,
                "fill": "bots", **settings}
    r = client.post("/api/rooms", json={"host_name": names[0], "settings": settings})
    assert r.status_code == 200, r.text
    d = r.json()
    players = [Player(client, d["code"], d["token"], d["agent"], d["name"])]
    for name in names[1:humans]:
        j = client.post(f"/api/rooms/{d['code']}/join", json={"name": name})
        assert j.status_code == 200, j.text
        players.append(Player(client, d["code"], j.json()["token"], j.json()["agent"], name))
    return players


def start(client: TestClient, players: list[Player]) -> None:
    r = client.post(f"/api/rooms/{players[0].code}/start", params={"token": players[0].token})
    assert r.status_code == 200, r.text


def key_of(pend: dict) -> tuple:
    return pend["round"], pend["kind"], pend.get("turn")


def play(players: list[Player], policy, until_status=("finished", "error"), max_s: float = 60.0,
         hold: float = 0.0, until=None) -> dict:
    """Poll every player; when one has a pending screen, ``policy(player, pending) -> body | None`` answers it
    (``None`` leaves it to time out). ``hold`` seconds are spent with the screen open before submitting. ``until``
    (state -> bool) stops early."""
    t0 = time.time()
    s = None
    while time.time() - t0 < max_s:
        for p in players:
            s = p.state()
            if s["status"] in until_status or (until and until(s)):
                return s
            pend = s["pending"]
            if pend is None or any(key_of(x) == key_of(pend) for x in p.seen):
                continue
            body = policy(p, pend)
            if body is None:
                p.seen.append({"round": pend["round"], "kind": pend["kind"], "turn": pend.get("turn"),
                               "pending": pend, "skipped": True})
                continue
            if hold:
                time.sleep(hold)
            reply = p.submit({"kind": pend["kind"], "round": pend["round"], "turn": pend.get("turn"), **body})
            p.seen.append({"round": pend["round"], "kind": pend["kind"], "turn": pend.get("turn"), "pending": pend,
                           "reply": reply})
        time.sleep(0.03)
    raise AssertionError(f"room did not reach {until_status} in {max_s}s: {s and s['status']} live {s and s['live']}")


def puzzle(seed: int, round_no: int, schedule: str = "human"):
    from squid5.core.puzzle import Spec, deal, puzzle_for

    from web.server.engine import AGENTS, PROFILES, SCHEDULES

    pz = puzzle_for(seed, round_no, Spec(**PROFILES[SCHEDULES[schedule][round_no - 1]]))
    import random

    return pz, deal(pz, AGENTS, random.Random(f"{seed}:deal:{round_no}"))


def answers_for(seed: int, round_no: int, schedule: str = "human") -> list[str]:
    return list(puzzle(seed, round_no, schedule)[0].answers)


def wrong_for(seed: int, round_no: int) -> list[str]:
    from squid5.core.puzzle import ACTIONS

    ans = answers_for(seed, round_no)
    return [next(a for a in ACTIONS if a != ans[0])] + ans[1:]


def done(*lines: str) -> dict:
    """A TALK body: the given lines and DONE."""
    return {"text": "\n".join([*lines, "DONE"])}
