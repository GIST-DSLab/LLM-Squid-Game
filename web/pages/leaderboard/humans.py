"""The leaderboard's people tab (GET /api/leaderboard/humans): every finished arena room with at least one person in it,
one row per game, ranked by that game's presence (the seats still taking part at each round's start, summed over the
rounds, over 4 x the round count; 2026-11-23 researcher: one departure no longer ends the game's score, so a game the
person played to the end with three seats left outranks one where everyone left early) and then by the people's end
tokens. The paper's coexistence retention C (tools/monitor/compare.py ``paper_game``) stays in each row as ``C``. The seats (who sat where, people / bots / models, how each one ended)
come with each row; the page shows them when the row is opened. Each game carries the arena game it was (config.yaml
``web.version``: v33, v36 ... v42, the room's GAME_LIST entry; 11-26: every game of the arena is on the board and the
page filters by game; ranks are counted within one game, since the games differ). Rooms of older engine versions
(v17b, v35 ...) ran other economies and stay off. A joint-SOLVE game (session_start ``settings.joint_solve``) written
as v33 by an older room counts as v36. Kept apart from
the model board: a person's game has other kinds of seats beside it, so its C is not the same measure as four copies of
one model."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

_CACHE: dict[Path, tuple[tuple, list[dict]]] = {}
_LOCK = threading.Lock()


def _stamp(run_dir: Path) -> tuple:
    out = []
    for name in ("results.jsonl", "meta.json", "config.yaml"):
        p = run_dir / name
        st = p.stat() if p.exists() else None
        out.append((st.st_size, st.st_mtime) if st else None)
    return tuple(out)


def _date(name: str) -> str | None:
    m = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_", name)
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else None


def _version(run_dir: Path) -> str | None:
    """The engine version a room ran (config.yaml ``web.version``, written by engine.run_config)."""
    try:
        text = (run_dir / "config.yaml").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^web:\n(?:[ ].*\n)*?[ ]+version: *['\"]?([\w.]+)", text, re.M)
    return m[1] if m else None


def run_games(run_dir: Path, cmp, versions) -> list[dict]:
    """The finished games of one room's run dir that had a person in a seat and ran one of the arena's *versions*
    (cached on results.jsonl, meta.json and config.yaml)."""
    key = _stamp(run_dir)
    with _LOCK:
        hit = _CACHE.get(run_dir)
    if hit and hit[0] == key:
        return hit[1]
    games: list[dict] = []
    try:
        seats = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")).get("seats") or {}
    except (OSError, ValueError):
        seats = {}
    room = _version(run_dir)
    if any(v.get("kind") == "human" for v in seats.values()) and room in versions:
        results = cmp.serve.results_by_session(run_dir)
        evs_by = cmp.serve.session_events(run_dir) if results else {}
        for sid, res in results.items():
            evs = evs_by.get(sid, [])
            joint = any((e.get("settings") or {}).get("joint_solve") for e in evs if e.get("event") == "session_start")
            version = "v36" if room == "v33" and joint else room  # a joint game is never pooled with v33's
            paper = cmp.paper_game(evs, res)
            if paper is None:
                continue
            agents = res.get("agents") or {}
            ends = {e["agent"]: e for e in cmp.end_tokens(res)}
            rows = []
            for a in agents:
                s, e = seats.get(a) or {}, ends.get(a) or {}
                rows.append({"agent": a, "kind": s.get("kind"), "name": s.get("name"), "model": s.get("model"),
                             "status": agents[a].get("status"), "out_round": agents[a].get("out_round"),
                             "end_tokens": e.get("end_tokens")})
            people = [r for r in rows if r["kind"] == "human"]
            n = len(paper["all4"])  # the round count
            here = sum(v.get("status") == "in" or (v.get("out_round") or 0) >= r  # in at round r's start
                       for r in range(1, n + 1) for v in agents.values())
            games.append({"game": run_dir.name, "version": version, "date": _date(run_dir.name), "C": paper["C"],
                          "presence": here / (len(agents) * n),
                          "rounds": len(paper["all4"]), "dead": paper["dead"],
                          "exited": sum(r["status"] == "exited" for r in rows), "seats": rows,
                          "people": [r["name"] or r["agent"] for r in people],
                          "people_tokens": max((r["end_tokens"] or 0) for r in people)})
    with _LOCK:
        _CACHE[run_dir] = (key, games)
    return games


def humans_board(runs_root: Path, cmp, versions, names: dict | None = None) -> dict:
    """Every finished game with a person, best presence first (ties: the people's end tokens, then the newest); the rank
    counts within one game (``version``), equal presence sharing a rank. ``games``: the arena's games in order (*names*:
    version -> its name) with how many rows each has, for the page's filter."""
    root = Path(runs_root)
    games = [g for d in (sorted(root.iterdir()) if root.is_dir() else []) if d.is_dir() and (d / "events.jsonl").exists()
             for g in run_games(d, cmp, tuple(versions))]
    games.sort(key=lambda g: g["date"] or "", reverse=True)  # newest first; the stable sort below keeps it within ties
    games.sort(key=lambda g: (-g["presence"], -g["people_tokens"]))
    seen: dict[str, list[dict]] = {}  # version -> its rows so far, best first
    for g in games:
        mine = seen.setdefault(g["version"], [])
        g["rank"] = mine[-1]["rank"] if mine and mine[-1]["presence"] == g["presence"] else len(mine) + 1
        mine.append(g)
    return {"rows": games, "games": [{"version": v, "name": (names or {}).get(v, v),
                                      "n": sum(g["version"] == v for g in games)} for v in versions]}
