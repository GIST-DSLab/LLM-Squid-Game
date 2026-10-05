"""Live monitor for squid5 5.2 v9-talk sessions: a small stdlib HTTP server over run directories.

    python3 tools/monitor/serve.py [--root ~/squid5-runs] [--port 8765] [--host 127.0.0.1]

Routes
  /                                   the page (monitor.html)
  /static/<file>                      page code (monitor.js, monitor.css)
  /assets/<file>                      optional sprites copied by fetch_assets.py
  /api/runs                           run dirs under the root that hold events.jsonl, newest first
  /api/sessions?run=REL               the sessions of one run
  /api/events?run=REL&session=SID&offset=N
                                      that session's events from byte offset N on; returns the new offset. A trailing
                                      line without its newline (still being written) is left for the next call.
  /api/puzzle?run=REL&session=SID&round=N
                                      that round's task rebuilt from the engine (the logs do not hold it): the public
                                      examples, the queries, each agent's own example, and per query the actions that
                                      the public examples alone, and the public examples + that agent's own, leave open.

The engine appends to events.jsonl from several sessions at once, so every event carries ``session_id``; a crashed unit
writes ``unit_error`` with its key only, which is matched to the latest ``session_start`` of the same (cell, seed).
"""

from __future__ import annotations

import argparse
import functools
import json
import mimetypes
import os
import random
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]  # the repo root: squid5 is imported from there for /api/puzzle
STATIC = HERE / "static"
ASSETS = HERE / "assets"
PAGE = HERE / "monitor.html"
CHUNK = 8 * 1024 * 1024  # bytes read per /api/events call; the client asks again while ``more`` is true
LIVE_SECONDS = 90  # a run whose events.jsonl changed this recently is shown as live


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


def safe_join(base: Path, rel: str) -> Path:
    """``base / rel`` resolved, or BadRequest if it leaves ``base``."""
    base = base.resolve()
    rel = unquote(rel or "").lstrip("/")
    if "\x00" in rel:
        raise BadRequest("bad path")
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise BadRequest("path outside the root")
    return p


# --- reading a run --------------------------------------------------------------------------------------------------

class RunIndex:
    """Incremental scan of one events.jsonl: the sessions in it and which session each unit_error belongs to."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.scanned = 0
        self.sessions: dict[str, dict] = {}
        self.latest_by_key: dict[tuple, str] = {}
        self.errors: dict[int, str] = {}  # byte offset of a unit_error line -> session id
        self.profiles: dict[str, dict[int, str]] = {}  # session id -> round -> task profile from round_start

    def update(self) -> int:
        """Scan the complete lines added since the last call; returns the file size."""
        with self.lock:
            size = self.path.stat().st_size
            if size < self.scanned:  # the file was replaced
                self._reset()
            if size == self.scanned:
                return size
            with self.path.open("rb") as f:
                f.seek(self.scanned)
                data = f.read(size - self.scanned)
            end = data.rfind(b"\n")
            if end < 0:
                return size
            pos = self.scanned
            for raw in data[:end + 1].splitlines(keepends=True):
                self._see(raw, pos)
                pos += len(raw)
            self.scanned = pos
            return size

    def _see(self, raw: bytes, offset: int) -> None:
        try:
            e = json.loads(raw)
        except ValueError:
            return
        if not isinstance(e, dict):
            return
        kind, sid = e.get("event"), e.get("session_id")
        if kind == "session_start" and sid:
            key = (str(e.get("cell_id")), e.get("seed"))
            self.sessions[sid] = {"id": sid, "cell": e.get("cell_id"), "seed": e.get("seed"), "start": e.get("start"),
                                  "agents": e.get("agents") or [], "seats": e.get("seats") or {},
                                  "rounds": (e.get("settings") or {}).get("rounds"), "offset": offset,
                                  "order": len(self.sessions), "round": 0, "rounds_done": 0, "events": 0,
                                  "calls": 0, "error": None}
            self.latest_by_key[key] = sid
        if kind == "unit_error":
            key = e.get("key") or [None, None]
            owner = self.latest_by_key.get((str(key[0]), key[1] if len(key) > 1 else None))
            if owner:
                self.errors[offset] = owner
                self.sessions[owner]["error"] = e.get("error")
                self.sessions[owner]["events"] += 1
            return
        s = self.sessions.get(sid)
        if s is None:
            return
        s["events"] += 1
        if kind == "round_start":
            s["round"] = max(s["round"], int(e.get("round") or 0))
            if e.get("profile"):
                self.profiles.setdefault(sid, {})[int(e.get("round") or 0)] = str(e["profile"])
        elif kind == "round":
            s["rounds_done"] = max(s["rounds_done"], int(e.get("round") or 0))
        elif kind == "call":
            s["calls"] += 1


_INDEXES: dict[Path, RunIndex] = {}
_INDEX_LOCK = threading.Lock()


def run_index(events: Path) -> RunIndex:
    with _INDEX_LOCK:
        idx = _INDEXES.get(events)
        if idx is None:
            idx = _INDEXES[events] = RunIndex(events)
    idx.update()
    return idx


def read_results(run_dir: Path) -> list[dict]:
    p = run_dir / "results.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a line still being written
        if isinstance(row, dict):
            out.append(row)
    return out


def results_by_session(run_dir: Path) -> dict[str, dict]:
    return {r["session_id"]: r for r in read_results(run_dir) if r.get("session_id")}


def expected_units(run_dir: Path) -> int | None:
    """reps x cells from config.yaml (a plain-text read; the engine writes it with yaml.safe_dump)."""
    p = run_dir / "config.yaml"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    reps = re.search(r"^reps:\s*(\d+)", text, re.M)
    cells = len(re.findall(r"^\s*-\s+cell_id:", text, re.M))
    return int(reps.group(1)) * cells if reps and cells else None


def read_meta(run_dir: Path) -> dict:
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_runs(root: Path) -> list[dict]:
    root = root.resolve()
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if "events.jsonl" not in filenames:
            continue
        d = Path(dirpath)
        ev = d / "events.jsonl"
        st = ev.stat()
        res = d / "results.jsonl"
        mtime = max(st.st_mtime, res.stat().st_mtime if res.exists() else 0)
        results = read_results(d)
        expected = expected_units(d)
        finished = sum(1 for r in results if r.get("session_id"))
        meta = read_meta(d)
        out.append({"run": d.relative_to(root).as_posix(), "mtime": mtime, "size": st.st_size,
                    "model": meta.get("model"), "mode": meta.get("mode"), "finished": finished,
                    "expected": expected, "done": expected is not None and finished >= expected,
                    "live": time.time() - st.st_mtime < LIVE_SECONDS})
    out.sort(key=lambda r: r["mtime"], reverse=True)
    return out


def run_dir_of(root: Path, rel: str) -> Path:
    d = safe_join(root, rel)
    if not (d / "events.jsonl").is_file():
        raise BadRequest("no events.jsonl in that run")
    return d


def list_sessions(run_dir: Path) -> dict:
    ev = run_dir / "events.jsonl"
    idx = run_index(ev)
    res = results_by_session(run_dir)
    meta = read_meta(run_dir)
    sessions = []
    for s in sorted(idx.sessions.values(), key=lambda s: s["order"]):
        r = res.get(s["id"])
        sessions.append({**s, "finished": r is not None, "crashed": s["error"] is not None,
                         "winner": (r.get("final") or {}).get("winner") if r else None})
    return {"model": meta.get("model"), "mtime": ev.stat().st_mtime,
            "live": time.time() - ev.stat().st_mtime < LIVE_SECONDS, "sessions": sessions}


def read_events(run_dir: Path, sid: str, offset: int = 0, chunk: int = CHUNK) -> dict:
    """The session's events in the complete lines from ``offset``; ``offset`` in the reply is where to go on from."""
    ev = run_dir / "events.jsonl"
    idx = run_index(ev)
    size = ev.stat().st_size
    reset = False
    if offset < 0 or offset > size:
        offset, reset = 0, True
    events: list[dict] = []
    pos = offset
    with ev.open("rb") as f:
        f.seek(offset)
        data = f.read(min(chunk, size - offset))
        while data and b"\n" not in data and offset + len(data) < size:  # one line longer than the chunk
            more = f.read(chunk)
            if not more:
                break
            data += more
    end = data.rfind(b"\n")
    if end >= 0:
        idx.update()  # errors seen in these lines are indexed before they are matched
        for raw in data[:end + 1].splitlines(keepends=True):
            line_at = pos
            pos += len(raw)
            try:
                e = json.loads(raw)
            except ValueError:  # a malformed line of this session is shown, not skipped silently
                if sid.encode() in raw:
                    events.append({"event": "_bad_line", "session_id": sid, "offset": line_at,
                                   "text": raw[:300].decode("utf-8", "replace")})
                continue
            if not isinstance(e, dict):
                continue
            if e.get("session_id") == sid or (e.get("event") == "unit_error" and idx.errors.get(line_at) == sid):
                events.append(e)
    res = results_by_session(run_dir).get(sid)
    return {"events": events, "offset": pos, "size": size, "more": offset + len(data) < size and end >= 0,
            "pending": size - pos, "reset": reset, "mtime": ev.stat().st_mtime, "now": time.time(),
            "live": time.time() - ev.stat().st_mtime < LIVE_SECONDS, "result": res,
            "session": idx.sessions.get(sid)}


def read_all(run_dir: Path, sid: str) -> list[dict]:
    out, offset = [], 0
    while True:
        r = read_events(run_dir, sid, offset)
        out += r["events"]
        if r["offset"] == offset:
            return out
        offset = r["offset"]


# --- the round's task (rebuilt; the engine is deterministic in seed, round and profile) --------------------------------

def _engine():
    """squid5's puzzle code, imported on first use so the rest of the monitor runs without the repo on the path."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from squid5.core import puzzle, rules
    return puzzle, rules


def read_game(run_dir: Path) -> dict:
    """The ``game:`` block of config.yaml (schedule and profiles)."""
    p = run_dir / "config.yaml"
    if not p.is_file():
        raise NotFound("no config.yaml in that run")
    import yaml  # the engine's own dependency; only this route needs it
    game = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("game") or {}
    if not game.get("profiles"):
        raise NotFound("config.yaml has no game profiles")
    return game


def _signal(sig) -> dict:
    return {"color": sig.color, "shape": sig.shape, "number": sig.number, "text": str(sig)}


def _clue(c) -> dict:
    return {"signal": _signal(c.signal), "text": str(c), "action": c.action}


@functools.lru_cache(maxsize=512)
def _puzzle(seed: int, round_no: int, spec_items: tuple) -> dict:
    """Everything about one round that does not depend on the run: computed once per (seed, round, profile)."""
    pz, rules = _engine()
    t0 = time.perf_counter()
    puzzle = pz.puzzle_for(seed, round_no, pz.Spec(**dict(spec_items)))
    dealt = pz.deal(puzzle, rules.TEAM_AGENTS, random.Random(f"{seed}:deal:{round_no}"))
    t1 = time.perf_counter()
    shape = puzzle.rule.shape
    public = list(dealt.public)
    public_only = [list(pz.candidate_actions(shape, public, q)) for q in puzzle.queries]
    agents = {}
    for a in rules.TEAM_AGENTS:
        own = dealt.secret[a]
        agents[a] = {"secret": _clue(own), "needed": a in dealt.needed, "public_only": public_only,
                     "with_own": [list(pz.candidate_actions(shape, public + [own], q)) for q in puzzle.queries]}
    t2 = time.perf_counter()
    rule = puzzle.rule
    rule_text = "; ".join([f"{'if' if i == 0 else 'elif'} {c.label} → {a}" for i, (c, a) in enumerate(rule.clauses)]
                          + [f"else → {rule.else_action}"])
    return {"seed": seed, "round": round_no, "shape": list(shape), "shape_hint": pz.shape_hint(shape),
            "actions": list(pz.ACTIONS), "public": [_clue(c) for c in public],
            "queries": [_signal(q) for q in puzzle.queries], "answers": list(puzzle.answers), "rule_text": rule_text,
            "agent_order": list(rules.TEAM_AGENTS), "agents": agents,
            "public_only": public_only,
            "timing_ms": {"puzzle_and_deal": round((t1 - t0) * 1000, 1), "candidates": round((t2 - t1) * 1000, 1)}}


def round_puzzle(run_dir: Path, sid: str, round_no) -> dict:
    """The task of one round of one session, as /api/puzzle returns it."""
    try:
        r = int(round_no)
    except (TypeError, ValueError):
        raise BadRequest("round must be an integer") from None
    idx = run_index(run_dir / "events.jsonl")
    s = idx.sessions.get(sid)
    if s is None:
        raise NotFound("no such session in that run")
    game = read_game(run_dir)
    schedule = game.get("schedule") or []
    rounds = s.get("rounds") or game.get("rounds") or len(schedule)
    if not 1 <= r <= int(rounds or 0):
        raise BadRequest(f"round must be in 1..{rounds}")
    profile = idx.profiles.get(sid, {}).get(r) or (schedule[r - 1] if r <= len(schedule) else None)
    spec = (game.get("profiles") or {}).get(profile)
    if spec is None:
        raise NotFound(f"no profile for round {r}")
    if s.get("seed") is None:
        raise NotFound("the session has no seed")
    out = _puzzle(int(s["seed"]), r, tuple(sorted(spec.items())))
    return {**out, "session": sid, "profile": profile}


# --- HTTP -----------------------------------------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    root: Path = Path.home() / "squid5-runs"
    server_version = "squid5-monitor/1"

    def log_message(self, fmt, *args):  # quiet: the page polls every 1.5 s
        if os.environ.get("MONITOR_LOG"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _file(self, path: Path) -> None:
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        route = url.path
        try:
            if route in ("/", "/index.html", "/monitor.html"):
                return self._file(PAGE)
            if route.startswith("/static/"):
                return self._file(safe_join(STATIC, route[len("/static/"):]))
            if route.startswith("/assets/"):
                return self._file(safe_join(ASSETS, route[len("/assets/"):]))
            if route == "/api/runs":
                return self._json({"root": str(self.root), "runs": list_runs(self.root)})
            if route == "/api/sessions":
                return self._json({"run": q.get("run", ""), **list_sessions(run_dir_of(self.root, q.get("run", "")))})
            if route == "/api/events":
                sid = q.get("session")
                if not sid:
                    raise BadRequest("session is required")
                try:
                    offset = int(q.get("offset", "0"))
                except ValueError:
                    raise BadRequest("offset must be an integer") from None
                return self._json(read_events(run_dir_of(self.root, q.get("run", "")), sid, offset))
            if route == "/api/puzzle":
                sid = q.get("session")
                if not sid:
                    raise BadRequest("session is required")
                if "round" not in q:
                    raise BadRequest("round is required")
                run_dir = run_dir_of(self.root, q.get("run", ""))
                try:
                    return self._json(round_puzzle(run_dir, sid, q["round"]))
                except (BadRequest, NotFound, BrokenPipeError, ConnectionResetError):
                    raise
                except Exception as err:  # noqa: BLE001 - the engine or config failed; tell the page why
                    return self._json({"error": f"puzzle rebuild failed: {err!r}"}, 500)
            return self._json({"error": "not found"}, 404)
        except BadRequest as err:
            return self._json({"error": str(err)}, HTTPStatus.BAD_REQUEST)
        except NotFound as err:
            return self._json({"error": str(err)}, HTTPStatus.NOT_FOUND)
        except (BrokenPipeError, ConnectionResetError):
            return None


def make_server(root: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"root": Path(root).expanduser().resolve()})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="squid5 5.2 v9-talk arena monitor")
    ap.add_argument("--root", default="~/squid5-runs", help="directory searched for run dirs (default ~/squid5-runs)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args(argv)
    for port in range(args.port, args.port + 20):  # the next free port if this one is taken
        try:
            srv = make_server(Path(args.root), args.host, port)
            break
        except OSError as err:
            if err.errno not in (48, 98):  # EADDRINUSE on macOS / Linux
                raise
            print(f"port {port} is in use; trying {port + 1}", flush=True)
    else:
        raise SystemExit(f"no free port in {args.port}..{args.port + 19}")
    print(f"monitor: http://{args.host}:{srv.server_address[1]}/  (root {Path(args.root).expanduser()})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
