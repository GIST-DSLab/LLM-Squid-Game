"""Live monitor for squid5 5.2 sessions (v9-talk .. v14): a small stdlib HTTP server over run directories.

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
  /compare.html                       the 모델 비교 page; /api/compare?runs=REL,REL|PREFIX/ (charts' data, merged by
                                      model) and /api/compare.csv?runs=...&chart=NAME (one chart's numbers)
  /api/giving?run=REL[&session=SID]   the giving decisions of a run (one model) or one session: every GIVE (opening,
                                      in-chat, v14e ask_decision) and every ASK received and answered with nothing,
                                      with the giver's balance just before it (``giving``); v14b runs on
  /api/puzzle?run=REL&session=SID&round=N
                                      that round's task rebuilt from the engine. v9..v13 (the logs do not hold it): the
                                      public examples, the queries, each agent's own examples (``secrets``; ``secret``
                                      is the first, or null), and per query the actions that the public examples
                                      alone, and the public examples + that agent's own, leave open. A
                                      ``deal_present`` run deals over the agents in that round's
                                      ``round_start.taking_part`` (``holders``). v14 (``mode: "public"``, no secrets):
                                      the examples every agent saw (``round_start.public``), checked against
                                      ``puzzle.public_round``, the ambiguity k, the redraw, and per query the actions
                                      they leave for the agents taking part (``left``) and for 1..4 (``by_n``);
                                      v14b: ``task`` = round_start.public.task (``task_source`` "log"), else
                                      ``puzzle.task_stats`` ("rebuilt"): per N pool, shares, k, MAP, truth share,
                                      entropy.

The engine appends to events.jsonl from several sessions at once, so every event carries ``session_id``; a crashed unit
writes ``unit_error`` with its key only, which is matched to the latest ``session_start`` of the same (cell, seed).
"""

from __future__ import annotations

import argparse
import functools
import json
import math
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
COMPARE_PAGE = HERE / "compare.html"  # 모델 비교: several runs overlaid, merged by model (compare.py)
# page code shared with the web arena, served as static/<name> (one file, not a copy): the arena's signal glyphs,
# example boxes and action chips (web/frontend/signal_ui.js) draw the round's task in the puzzle panel
SHARED = {"signal_ui.js": REPO / "web" / "frontend" / "signal_ui.js"}
CHUNK = 8 * 1024 * 1024  # bytes read per /api/events call; the client asks again while ``more`` is true
LIVE_SECONDS = 90  # a run whose events.jsonl changed this recently is shown as live


class BadRequest(Exception):
    pass


class NotFound(Exception):
    pass


def static_path(rel: str) -> Path:
    """A static file of the page: a shared one (``SHARED``) or one under ``static/``."""
    shared = SHARED.get(unquote(rel or "").lstrip("/"))
    return shared if shared is not None and shared.is_file() else safe_join(STATIC, rel)


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
        self.taking: dict[str, dict[int, list]] = {}  # session id -> round -> agents taking part from round_start
        self.public: dict[str, dict[int, dict]] = {}  # session id -> round -> round_start.public (v14)

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
                                  "starts": e.get("starts"),
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
            if isinstance(e.get("taking_part"), list):
                self.taking.setdefault(sid, {})[int(e.get("round") or 0)] = list(e["taking_part"])
            if isinstance(e.get("public"), dict):
                self.public.setdefault(sid, {})[int(e.get("round") or 0)] = e["public"]
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


# --- giving decisions (the "나눔 그래프": what a model gives against its own balance) ------------------------------------

def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def giving_points(events: list[dict]) -> dict:
    """One session's giving decisions, in event order. A point: who decided (``giver``), for whom (``receiver``), how
    much moved (``amount``; 0 for an ASK answered with nothing), how much was asked (``asked``, None when nobody asked:
    an unsolicited gift), ``kind`` answer | gift | declined, ``status`` done | refused (a GIVE over the balance), and the
    giver's balance just before (``balance``: a gift event's after-balance plus what it moved; a v14e event's
    ``balance_before``). An ASK counts as answered by the asked agent's next GIVE to the asker in the same chat (v14c+)
    or later in the same round (v14b); an ASK with no such GIVE is a 0 point at the asked agent's balance when asked.
    v14e ``ask_decision`` events (``decider``, ``asker``, ``asked``, ``amount``, ``balance_before``), when present, are
    the decisions themselves (amount 0 = nothing given); the decision's own ``gift`` event (``decision``) is skipped and
    a GIVE written in a chat counts as an unsolicited gift."""
    start, starts, full, pts, open_asks, asks = None, {}, None, [], [], []
    decided = [e for e in events if e.get("event") == "ask_decision"]
    chat = any(e.get("event") == "talk_schedule" for e in events)  # v14c+: per-chat decisions (_chat_giving)
    lines = sum(e.get("event") == "ask" and e.get("status", "done") == "done" for e in events)
    for e in events:
        kind = e.get("event")
        if kind == "session_start":
            start, starts = e.get("start"), e.get("starts") or {}
            full = (e.get("settings") or {}).get("balance_pct") or start
        elif chat:
            continue
        elif kind == "ask" and e.get("status", "done") == "done":
            asks.append(e)
            if not decided:
                open_asks.append({**e, "answered": False, "bal_dst": (e.get("balances") or {}).get(e.get("dst"))})
        elif kind == "gift":
            src, dst, n = e.get("src"), e.get("dst"), _num(e.get("amount")) or 0
            after = (e.get("balances") or {}).get(src)
            bal = _num(e.get("balance_before"))
            if bal is None and after is not None:
                bal = after + (n if e.get("status") == "done" else 0)
            ask = None if decided else next((a for a in open_asks if not a["answered"] and a["src"] == dst and a["dst"] == src
                                             and a["round"] == e.get("round") and (a.get("chat_id") or None) in (
                                                 e.get("chat_id"), None)), None)
            if ask:
                ask["answered"] = True
                ask_bal = (ask.get("balances") or {}).get(dst)
            if e.get("decision"):
                continue  # v14e: a decision's GIVE; its ask_decision event is the point
            pts.append({"round": e.get("round"), "turn": e.get("turn"), "chat_id": e.get("chat_id"), "giver": src,
                        "receiver": dst, "amount": n, "asked": ask and _num(ask.get("amount")),
                        "asker_balance": ask_bal if ask else None,
                        "receiver_balance": (lambda rb: rb - n if rb is not None and e.get("status") == "done" else rb)(
                            (e.get("balances") or {}).get(dst)),
                        "kind": "answer" if ask else "gift", "status": e.get("status", "done"), "balance": bal,
                        "text": e.get("text") or "", "i": len(pts)})
        elif kind == "ask_decision":  # v14e: the asked agent's answer to one ASK (amount 0 = nothing)
            giver = e.get("decider") or e.get("agent") or e.get("src")
            asker = e.get("asker") or e.get("dst")
            n = _num(e.get("amount")) or 0
            last = next((a for a in reversed(asks) if a.get("src") == asker and a.get("dst") == giver
                         and a.get("round") == e.get("round")), None)
            pts.append({"round": e.get("round"), "turn": e.get("turn"), "chat_id": e.get("chat_id"), "giver": giver,
                        "receiver": asker, "amount": n, "asker_balance": (last.get("balances") or {}).get(asker) if last else None,
                        "asked": _num(e.get("asked") if e.get("asked") is not None else e.get("ask_amount")),
                        "kind": "answer" if n else "declined", "status": e.get("status", "done"),
                        "balance": _num(e.get("balance_before")), "text": e.get("text") or "", "i": len(pts)})
    if chat:
        pts, lines = _chat_giving(events)
    for a in open_asks:
        if not a["answered"]:
            pts.append({"round": a.get("round"), "turn": a.get("turn"), "chat_id": a.get("chat_id"), "giver": a["dst"],
                        "receiver": a["src"], "amount": 0, "asked": _num(a.get("amount")), "kind": "declined",
                        "asker_balance": (a.get("balances") or {}).get(a["src"]),
                        "status": "done", "balance": a["bal_dst"], "text": a.get("text") or "", "i": len(pts)})
    for i, p in enumerate(pts):
        p["i"] = i
        own = starts.get(p["giver"]) or start
        p["pct"] = round(100 * p["balance"] / full, 1) if p["balance"] is not None and full else None
        p["pct_own"] = round(100 * p["balance"] / own, 1) if p["balance"] is not None and own else None
        p["share"] = round(own / start, 2) if own and start else None
        if p.get("receiver_balance") is None:  # an answer: the asker's balance when it asked
            p["receiver_balance"] = p.get("asker_balance")
        rb = p["receiver_balance"]
        p["receiver_pct"] = round(100 * rb / full, 1) if rb is not None and full else None
        ab, aown = p.get("asker_balance"), starts.get(p["receiver"]) or start
        p["asker_pct"] = round(100 * ab / full, 1) if ab is not None and full else None
        p["asker_pct_own"] = round(100 * ab / aown, 1) if ab is not None and aown else None
    return {"start": start, "full": full, "starts": starts, "points": pts, "ask_lines": lines}


def _chat_giving(events: list[dict]) -> tuple[list[dict], int]:
    """Chat runs (v14c+): one decision per (chat, asker Y -> asked X). asked = Y's ASKs to X in that chat (an opening ASK
    belongs to the chat its pair opened, from ``talk_schedule``); gave = X's GIVEs to Y in that chat (opening or in the
    chat) plus the v14e/f ``ask_decision`` amount (its own gift event is skipped, the decision carries it). The point's
    balance is X's just before its first GIVE in the chat, else at the decision, else when Y asked. A GIVE to an agent
    that did not ASK the giver in that chat is unsolicited (one point each). Returns (points, raw ASK lines)."""
    chat_of: dict[tuple, str] = {}
    for e in events:
        if e.get("event") == "talk_schedule":
            for x, y, *_rest in e.get("edges") or []:
                chat_of[(e.get("round"), frozenset((x, y)))] = _rest[-1] if _rest else None
    cid = lambda e: e.get("chat_id") or chat_of.get((e.get("round"), frozenset((e.get("src"), e.get("dst")))))  # noqa: E731
    units: dict[tuple, dict] = {}
    gives, lines = [], 0
    for e in events:
        kind = e.get("event")
        if kind == "ask" and e.get("status", "done") == "done":
            lines += 1
            u = units.setdefault((cid(e), e.get("src"), e.get("dst")), {
                "round": e.get("round"), "turn": e.get("turn"), "chat_id": cid(e), "asker": e.get("src"),
                "decider": e.get("dst"), "asked": 0, "asker_balance": (e.get("balances") or {}).get(e.get("src")),
                "ask_balance": (e.get("balances") or {}).get(e.get("dst")), "gives": [], "decision": None, "text": ""})
            u["asked"] += _num(e.get("amount")) or 0
            u["text"] = u["text"] or e.get("text") or ""
        elif kind == "gift" and not e.get("decision"):
            gives.append(e)
        elif kind == "ask_decision":
            u = units.setdefault((e.get("chat_id"), e.get("asker"), e.get("decider")), {
                "round": e.get("round"), "turn": e.get("turn"), "chat_id": e.get("chat_id"), "asker": e.get("asker"),
                "decider": e.get("decider"), "asked": _num(e.get("asked")) or 0, "asker_balance": None,
                "ask_balance": None, "gives": [], "decision": None, "text": ""})
            u["decision"] = e
            u["asked"] = max(u["asked"], _num(e.get("asked")) or 0)  # the event's total of the chat's ASKs
    pts = []
    for e in gives:
        n = _num(e.get("amount")) or 0
        after = (e.get("balances") or {}).get(e.get("src"))
        bal = _num(e.get("balance_before"))
        if bal is None and after is not None:
            bal = after + (n if e.get("status") == "done" else 0)
        g = {**e, "_bal": bal, "_n": n}
        u = units.get((cid(e), e.get("dst"), e.get("src")))
        if u is not None:
            u["gives"].append(g)
            continue
        rb = (e.get("balances") or {}).get(e.get("dst"))
        pts.append({"round": e.get("round"), "turn": e.get("turn"), "chat_id": cid(e), "giver": e.get("src"),
                    "receiver": e.get("dst"), "amount": n, "asked": None, "asker_balance": None, "kind": "gift",
                    "receiver_balance": rb - n if rb is not None and e.get("status") == "done" else rb,
                    "status": e.get("status", "done"), "balance": bal, "text": e.get("text") or ""})
    for u in units.values():
        done = [g for g in u["gives"] if g.get("status", "done") == "done"]
        d = u["decision"]
        gave = sum(g["_n"] for g in done) + (_num(d.get("amount")) or 0 if d and d.get("status", "done") == "done" else 0)
        refused = any(g.get("status") == "refused" for g in u["gives"]) or (d is not None and d.get("status") == "refused")
        bal = (u["gives"][0]["_bal"] if u["gives"] else None)
        if bal is None and d is not None:
            bal = _num(d.get("balance_before"))
        if bal is None:
            bal = u["ask_balance"]
        last = (u["gives"] or [None])[-1]
        pts.append({"round": u["round"], "turn": u["turn"], "chat_id": u["chat_id"], "giver": u["decider"],
                    "receiver": u["asker"], "amount": gave, "asked": u["asked"], "asker_balance": u["asker_balance"],
                    "kind": "answer" if gave else "declined", "status": "refused" if refused and not gave else "done",
                    "balance": bal, "in_chat": sum(g["_n"] for g in done), "decided": d and _num(d.get("amount")),
                    "text": (d and d.get("text")) or (last and last.get("text")) or u["text"]})
    return pts, lines


def giving_summary(points: list[dict], ask_lines: int | None = None) -> dict:
    asked = [p for p in points if p["asked"] is not None]
    answered = [p for p in asked if p["amount"] > 0 and p["status"] == "done"]
    ratio = [p["amount"] / p["asked"] for p in answered if p["asked"]]
    given = [p for p in points if p["amount"] > 0 and p["status"] == "done"]
    pct = [p["pct"] for p in given if p["pct"] is not None]
    return {"decisions": len(points), "asks_received": len(asked), "ask_lines": ask_lines if ask_lines is not None else len(asked),
            "answered_pct": round(100 * len(answered) / len(asked), 1)
            if asked else None, "given_over_asked": round(sum(ratio) / len(ratio), 3) if ratio else None,
            "total_given": sum(p["amount"] for p in given), "gifts": len(given),
            "unsolicited": sum(p["kind"] == "gift" and p["status"] == "done" for p in points),
            "refused": sum(p["status"] == "refused" for p in points),
            "giver_mean_pct": round(sum(pct) / len(pct), 1) if pct else None}


def session_events(run_dir: Path, sid: str | None = None) -> dict[str, list[dict]]:
    """Every session's events of a run (or one session's), in file order."""
    by: dict[str, list[dict]] = {}
    with (run_dir / "events.jsonl").open("rb") as f:
        for raw in f:
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("session_id") and (sid is None or e["session_id"] == sid):
                by.setdefault(e["session_id"], []).append(e)
    return by


def run_giving(run_dir: Path, sid: str | None = None) -> dict:
    """The giving decisions of every session of a run (one model), or of one session; with a summary."""
    meta = read_meta(run_dir)
    by = session_events(run_dir, sid)
    sessions, points = [], []
    for s_id, evs in by.items():
        g = giving_points(evs)
        for p in g["points"]:
            p["session"] = s_id
        points += g["points"]
        sessions.append({"session": s_id, "start": g["start"], "full": g["full"], "starts": g["starts"],
                         "summary": giving_summary(g["points"], g["ask_lines"])})
    ga = any(e.get("event") == "session_start" and (e.get("settings") or {}).get("transfers") in ("give_ask", "chat")
             or e.get("event") in ("gift", "ask", "ask_decision") for evs in by.values() for e in evs)
    return {"model": meta.get("model"), "scope": "session" if sid else "run", "sessions": sessions, "points": points,
            "summary": giving_summary(points, sum(x["summary"]["ask_lines"] for x in sessions)), "full": next((x["full"] for x in sessions if x["full"]), None),
            "note": None if ga else "v14b 이후 판만 (이 실행은 GIVE·ASK가 없는 판: 제안·교환은 그리지 않음)"}


def _pcts(bal, full, own) -> dict:
    return {"balance": bal, "pct": round(100 * bal / full, 1) if bal is not None and full else None,
            "pct_own": round(100 * bal / own, 1) if bal is not None and own else None}


def _truth_fields(belief: dict, ideal: dict, truth) -> dict:
    """The probability the belief put on the true action and the ideal share of it; the counting ceiling (the ideal's
    largest share: a perfect reasoner's chance of being right) and whether the belief's argmax is an ideal MAP action."""
    top = max(ideal.values()) if ideal else None
    maps = [a for a, v in ideal.items() if v == top]
    arg = max(belief, key=lambda a: belief[a]) if belief else None
    return {"truth": truth, "p_true": belief.get(truth) if truth else None, "ideal_true": ideal.get(truth, 0) if truth else None,
            "p_max": top, "argmax_is_map": arg in maps if arg else None,
            "argmax_true": (arg == truth) if arg and truth else None}  # the round row's argmax flag is vs the SUBMITTED answer


def analysis_points(events: list[dict]) -> dict:
    """One session's points for the three per-model panels (researcher 15:30).
    ``exits``: one per EXIT, the balance just before it (an exit_refill's balance - amount, its ``balance_before`` if
    given; without a refill the round row's end balance), the round, the reason, the agents taking part, the rounds the
    agent had solved, and whether it was the last agent taking part. ``deaths``: the round an agent reached zero, at its
    balance when the round started. ``calib`` (v14d BELIEF): per seat-round, the belief p and the logged ideal shares s
    (round_start.public.task.by_n[N]), CE = -sum s ln max(p, .01), H(s), KL = CE - H(s), the round row's log loss,
    Brier and argmax, the split p, at the seat's balance when SOLVE was called."""
    start, starts, full, exits, deaths, calib = None, {}, None, [], [], []
    rstart, solve_bal, solved, refill = {}, {}, {}, {}
    for e in events:
        kind = e.get("event")
        if kind == "session_start":
            start, starts = e.get("start"), e.get("starts") or {}
            full = (e.get("settings") or {}).get("balance_pct") or start
        elif kind == "round_start":
            rstart[e.get("round")] = e
        elif kind == "call_start" and e.get("kind") == "solve":
            solve_bal[e.get("round")] = dict(e.get("balances") or {})
        elif kind == "exit_refill":
            refill[(e.get("round"), e.get("agent"))] = e
        elif kind == "round":
            r, rs = e.get("round"), rstart.get(e.get("round")) or {}
            taking = rs.get("taking_part") or list((e.get("agents") or {}))
            pub = rs.get("public") or {}
            ideal = ((pub.get("task") or {}).get("by_n") or {}).get(str(min(len(taking), 4)), {}).get("shares")
            for a, row in (e.get("agents") or {}).items():
                own = starts.get(a) or start
                if row.get("exit"):
                    f = refill.get((r, a))
                    bal = _num(f.get("balance_before")) if f and f.get("balance_before") is not None else (
                        f["balance"] - f["amount"] if f else row.get("balance_after"))
                    exits.append({"round": r, "agent": a, **_pcts(bal, full, own), "reason": row.get("exit_reason"),
                                  "taking_part": len(taking), "last": len(taking) == 1, "solved": solved.get(a, 0),
                                  "refill": bool(f), "share": round(own / start, 2) if own and start else None})
                if row.get("status") == "dead":
                    deaths.append({"round": r, "agent": a, **_pcts(row.get("balance_before"), full, own),
                                   "overdrawn": bool(row.get("overdrawn")), "taking_part": len(taking),
                                   "share": round(own / start, 2) if own and start else None})
                solved[a] = solved.get(a, 0) + bool(row.get("solved"))
                b = row.get("belief")
                if b and ideal:
                    ce = -sum(sv * math.log(max(b.get(x, 0), 0.01)) for x, sv in ideal.items())
                    h = -sum(sv * math.log(sv) for sv in ideal.values() if sv > 0)
                    calib.append({"round": r, "agent": a, **_pcts((solve_bal.get(r) or {}).get(a, row.get("balance_before")),
                                                                   full, own),
                                  "belief": b, "ideal": ideal, "ce": round(ce, 4), "h": round(h, 4), "kl": round(ce - h, 4),
                                  "log_loss": row.get("log_loss"), "brier": row.get("brier"), "split": pub.get("split"),
                                  "argmax_right": row.get("belief_argmax_matches_answer"), "n": len(taking),
                                  **_truth_fields(b, ideal, (pub.get("task") or {}).get("truth") or (pub.get("answers") or [None])[0]),
                                  "share": round(own / start, 2) if own and start else None})
    return {"exits": exits, "deaths": deaths, "calib": calib}


def run_analysis(run_dir: Path, sid: str | None = None) -> dict:
    """The three per-model panels' points over a run (one model) or one session; ``coop`` = the giving points that
    answer an ASK (the asked agent's GIVE, 0 when it gave nothing), with the asker's balance too."""
    meta, out = read_meta(run_dir), {"exits": [], "deaths": [], "calib": [], "coop": []}
    for s_id, evs in session_events(run_dir, sid).items():
        a = analysis_points(evs)
        for k in ("exits", "deaths", "calib"):
            out[k] += [{**p, "session": s_id} for p in a[k]]
        g = giving_points(evs)
        out["coop"] += [{**p, "session": s_id, "gave": p["amount"] if p["status"] == "done" else 0}
                        for p in g["points"] if p["asked"]]
        out["ask_lines"] = out.get("ask_lines", 0) + g["ask_lines"]
    return {"model": meta.get("model"), "scope": "session" if sid else "run", **out}


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
def _puzzle(seed: int, round_no: int, spec_items: tuple, holders: tuple | None = None) -> dict:
    """Everything about one round that does not depend on the run: computed once per (seed, round, profile, holders);
    ``holders``: the agents taking part at the round's start when the run deals over them (``deal_present``)."""
    pz, rules = _engine()
    t0 = time.perf_counter()
    puzzle = pz.puzzle_for(seed, round_no, pz.Spec(**dict(spec_items)))
    dealt = pz.deal(puzzle, rules.TEAM_AGENTS, random.Random(f"{seed}:deal:{round_no}"),
                    list(holders) if holders is not None else None)
    t1 = time.perf_counter()
    shape = puzzle.rule.shape
    public = list(dealt.public)
    public_only = [list(pz.candidate_actions(shape, public, q)) for q in puzzle.queries]
    agents = {}
    for a in rules.TEAM_AGENTS:
        own = list(dealt.secret.get(a, ()))
        agents[a] = {"secret": _clue(own[0]) if own else None, "secrets": [_clue(c) for c in own],
                     "needed": a in dealt.needed, "public_only": public_only,
                     "with_own": [list(pz.candidate_actions(shape, public + own, q)) for q in puzzle.queries]}
    t2 = time.perf_counter()
    rule = puzzle.rule
    rule_text = "; ".join([f"{'if' if i == 0 else 'elif'} {c.label} → {a}" for i, (c, a) in enumerate(rule.clauses)]
                          + [f"else → {rule.else_action}"])
    return {"seed": seed, "round": round_no, "shape": list(shape), "shape_hint": pz.shape_hint(shape),
            "actions": list(pz.ACTIONS), "public": [_clue(c) for c in public],
            "queries": [_signal(q) for q in puzzle.queries], "answers": list(puzzle.answers), "rule_text": rule_text,
            "agent_order": list(rules.TEAM_AGENTS), "agents": agents, "holders": list(holders or rules.TEAM_AGENTS),
            "public_only": public_only,
            "timing_ms": {"puzzle_and_deal": round((t1 - t0) * 1000, 1), "candidates": round((t2 - t1) * 1000, 1)}}


def _hashable(v):
    """A profile value as a cache key part: YAML lists (``size_band``) and dicts become tuples, recursively."""
    if isinstance(v, dict):
        return tuple(sorted((k, _hashable(x)) for k, x in v.items()))
    return tuple(_hashable(x) for x in v) if isinstance(v, (list, tuple)) else v


def _shares(pz, shape, clues, queries) -> tuple[int, list[dict]]:
    """The consistent rules (``puzzle.space_bits``: the selector's hypothesis space) left by *clues*, and per query how
    many of them give each action: (pool, [{action: rules}])."""
    bits, aid = pz.space_bits(shape), {a: i for i, a in enumerate(pz.ACTIONS)}
    c = functools.reduce(lambda m, cl: m & bits[pz.SIGNAL_INDEX[cl.signal]][aid[cl.action]], clues, sum(bits[0]))
    return c.bit_count(), [{a: (c & bits[pz.SIGNAL_INDEX[q]][aid[a]]).bit_count() for a in pz.ACTIONS} for q in queries]


def _split_view(pool: int, counts: dict, truth: str) -> dict:
    """One query's rule split: actions with their rules and shares (largest first), the MAP pick and whether it is
    right (``map`` is None on a tie for the most rules)."""
    acts = sorted(((a, n) for a, n in counts.items() if n), key=lambda x: -x[1])
    top = [a for a, n in acts if n == acts[0][1]] if acts else []
    return {"pool": pool, "shares": [{"action": a, "rules": n, "share": round(n / pool, 3)} for a, n in acts],
            "map": top[0] if len(top) == 1 else None, "map_right": len(top) == 1 and top[0] == truth,
            "truth_share": round(counts.get(truth, 0) / pool, 3) if pool else None}


CLUE_TEXT = re.compile(r"^(\w+) (\w+) with number (\d+) -> (\w+)$")


@functools.lru_cache(maxsize=512)
def _public_puzzle(seed: int, round_no: int, spec_items: tuple, per_agent: int, n: int, logged: tuple,
                   logged_rule: str | None) -> dict:
    """v14: the examples the agents saw (``logged``, from round_start) and what they leave open. The round is rebuilt
    with ``public_round`` (the puzzle may be a redraw when k >= 1); ``matches_log`` says whether the rebuild shows the
    same examples. The logged examples are what is shown either way; ``by_n`` (1..4 agents taking part, prefixes of
    one order) comes from the rebuild."""
    pz, rules = _engine()
    t0 = time.perf_counter()
    spec = pz.Spec(**dict(spec_items))
    puzzle, shown, attempt = pz.public_round(seed, round_no, spec, n, per_agent)
    full = pz.public_round(seed, round_no, spec, len(rules.TEAM_AGENTS), per_agent)[1]
    info = pz.public_info(seed, round_no, spec, n, per_agent) if hasattr(pz, "public_info") else {}
    task = pz.task_stats(seed, round_no, spec, per_agent) if spec.ambiguity and hasattr(pz, "task_stats") else None
    clues = []
    for text in logged:
        m = CLUE_TEXT.match(text)
        clues.append(pz.Clue(pz.Signal(m.group(1), m.group(2), int(m.group(3))), m.group(4)) if m else None)
    matches = [str(c) for c in shown] == list(logged) and (logged_rule is None or puzzle.rule.description == logged_rule)
    if not matches and None in clues:
        raise ValueError("the logged examples cannot be read and the rebuild differs from them")
    clues = clues if None not in clues else list(shown)
    t1 = time.perf_counter()
    shape = puzzle.rule.shape
    left = lambda cs: [list(pz.candidate_actions(shape, cs, q)) for q in puzzle.queries]  # noqa: E731

    def split(cs) -> list[dict]:  # per query: the consistent rules' split over the actions
        pool, counts = _shares(pz, shape, cs, puzzle.queries)
        return [_split_view(pool, c, a) for c, a in zip(counts, puzzle.answers)]

    by_n = [{"n": k, "count": per_agent * k, "left": left(full[:per_agent * k]), "split": split(full[:per_agent * k])}
            for k in range(1, len(rules.TEAM_AGENTS) + 1)] if matches else []
    t2 = time.perf_counter()
    rule = puzzle.rule
    rule_text = "; ".join([f"{'if' if i == 0 else 'elif'} {c.label} → {a}" for i, (c, a) in enumerate(rule.clauses)]
                          + [f"else → {rule.else_action}"])
    shown_left = left(clues)
    return {"mode": "public", "seed": seed, "round": round_no, "shape": list(shape), "shape_hint": pz.shape_hint(shape),
            "actions": list(pz.ACTIONS), "public": [_clue(c) for c in clues],
            "queries": [_signal(q) for q in puzzle.queries], "answers": list(puzzle.answers),
            "rule_text": rule_text if matches or logged_rule is None else logged_rule,
            "per_agent": per_agent, "n": n, "ambiguity": spec.ambiguity, "attempt": attempt, "matches_log": matches,
            "left": shown_left, "public_only": shown_left, "by_n": by_n, "agent_order": list(rules.TEAM_AGENTS),
            "task": task, "task_source": "rebuilt" if task else None,
            # every example the engine built for the round (e x 4, one order); the first ``len(public)`` were shown
            "full": [_clue(c) for c in full] if matches else [_clue(c) for c in clues],
            "split": split(clues), "target": {k: info.get(k) for k in ("split", "truth_major", "pool", "pool_full",
                                                                      "truth_share")} if info else None,
            "timing_ms": {"rebuild": round((t1 - t0) * 1000, 1), "candidates": round((t2 - t1) * 1000, 1)}}


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
    pub = idx.public.get(sid, {}).get(r)
    if pub is not None or game.get("public_per_agent"):  # v14: public examples only, recorded in round_start
        if pub is None:
            raise NotFound(f"round {r} has not started (its public examples are in its round_start)")
        out = _public_puzzle(int(s["seed"]), r, _hashable(spec), int(pub["per_agent"]), int(pub["n"]),
                             tuple(pub.get("examples") or ()), pub.get("rule"))
        logged = {k: pub[k] for k in ("split", "truth_major", "pool", "pool_full", "truth_share") if k in pub}
        if pub.get("task"):  # v14b: the round's task statistics as logged (preferred to the rebuild)
            out = {**out, "task": pub["task"], "task_source": "log"}
        return {**out, "session": sid, "profile": profile, "taking_part": idx.taking.get(sid, {}).get(r),
                **({"target": {**(out.get("target") or {}), **logged}} if logged else {})}
    holders = None
    if game.get("deal_present"):
        holders = idx.taking.get(sid, {}).get(r)
        if holders is None:
            raise NotFound(f"round {r} has not started (deal_present deals over the agents taking part)")
        holders = tuple(holders)
    out = _puzzle(int(s["seed"]), r, _hashable(spec), holders)
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
            if route in ("/compare", "/compare.html"):
                return self._file(COMPARE_PAGE)
            if route in ("/api/compare", "/api/compare.csv"):
                import compare
                data = compare.compare(self.root, [x for x in q.get("runs", "").split(",") if x.strip()])
                if route.endswith(".csv"):
                    body = compare.chart_csv(data, q.get("chart", "summary")).encode("utf-8-sig")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="compare-{q.get("chart", "summary")}.csv"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    return self.wfile.write(body)
                return self._json(compare.public(data))
            if route.startswith("/static/"):
                return self._file(static_path(route[len("/static/"):]))
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
            if route == "/api/analysis":
                return self._json(run_analysis(run_dir_of(self.root, q.get("run", "")), q.get("session") or None))
            if route == "/api/giving":
                return self._json(run_giving(run_dir_of(self.root, q.get("run", "")), q.get("session") or None))
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
    ap = argparse.ArgumentParser(description="squid5 5.2 arena monitor (v9-talk .. v14)")
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
