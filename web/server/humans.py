"""The leaderboard's people tab (GET /api/leaderboard/humans): every finished arena room with at least one person in it,
one row per game, ranked by that game's coexistence retention C (tools/monitor/compare.py ``paper_game``, the paper's
definition) and then by the people's end tokens. The seats (who sat where, people / bots / models, how each one ended)
come with each row; the page shows them when the row is opened. Only games of the arena's engine version (config.yaml
``web.version``; v33 now) count: older rooms ran other economies (other charges, balances and prizes). Kept apart from
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


def run_games(run_dir: Path, cmp, version: str) -> list[dict]:
    """The finished games of one room's run dir that had a person in a seat and ran engine *version* (cached on
    results.jsonl, meta.json and config.yaml)."""
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
    if any(v.get("kind") == "human" for v in seats.values()) and _version(run_dir) == version:
        results = cmp.serve.results_by_session(run_dir)
        evs_by = cmp.serve.session_events(run_dir) if results else {}
        for sid, res in results.items():
            paper = cmp.paper_game(evs_by.get(sid, []), res)
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
            games.append({"game": run_dir.name, "date": _date(run_dir.name), "C": paper["C"],
                          "rounds": len(paper["all4"]), "dead": paper["dead"],
                          "exited": sum(r["status"] == "exited" for r in rows), "seats": rows,
                          "people": [r["name"] or r["agent"] for r in people],
                          "people_tokens": max((r["end_tokens"] or 0) for r in people)})
    with _LOCK:
        _CACHE[run_dir] = (key, games)
    return games


def humans_board(runs_root: Path, cmp, version: str) -> dict:
    """Every finished game with a person, best C first (ties: the people's end tokens, then the newest); equal C shares
    a rank."""
    root = Path(runs_root)
    games = [g for d in (sorted(root.iterdir()) if root.is_dir() else []) if d.is_dir() and (d / "events.jsonl").exists()
             for g in run_games(d, cmp, version)]
    games.sort(key=lambda g: g["date"] or "", reverse=True)  # newest first; the stable sort below keeps it within ties
    games.sort(key=lambda g: (-g["C"], -g["people_tokens"]))
    for i, g in enumerate(games):
        g["rank"] = games[i - 1]["rank"] if i and games[i - 1]["C"] == g["C"] else i + 1
    return {"rows": games}
