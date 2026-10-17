"""Verify browser arena games offline: replay each stored record with the real engine and compare.

    # from the Worker (export token = the Worker secret ARENA_EXPORT_TOKEN)
    ARENA_EXPORT_TOKEN=... python tools/arena/verify_games.py --fetch https://squid5-api.<sub>.workers.dev \
        [--since 0] [--out web/data/runs/web_arena] [--report report.json]
    # or from files (record.json / record.json.gz as the arena's '기록 내려받기' or R2 holds them)
    python tools/arena/verify_games.py --records path/to/*.json.gz [--calls calls.json] [--out DIR]

The browser reports a game as its doc (settings with the seed, the person's name), every reply in call order (each
with the hash of the prompt it answered) and a digest of every event (web/pyodide/browser.py ``record_of``). The server
stores that without reading it. Here, per record:

1. replay: ``replay.ReplayRoom.load(doc, replies)`` runs ``Session.run`` from the start with the recorded replies, as
   the browser did. A reply that answers a different prompt than the engine makes stops it (``Diverged``).
2. events: the replay's event digests must equal the reported ones (count, every digest, the total digest), and the
   reported session result must equal the replay's.
3. people: each reply's charge must be its seconds x rate (``HumanSeat.cost``), seconds within the screen's limit, the
   outcome consistent (a timeout waited the timeout); replies under 1 s are flagged as suspicious (warning).
4. models (with the Worker's call log, ``--fetch`` or ``--calls``): every model reply must answer a prompt the Worker
   relayed for that game (prompt hash), non-streamed replies must match the logged token count and content hash, and
   there may not be more model replies than relayed calls.
5. engine: the record's bundle hash vs the bundle the repo makes now (a different engine may replay differently: check
   out the matching commit if it diverges).

A game passes when 1-2 hold and 3-4 find no error. ``--out`` writes each passing finished game as a run directory
(config.yaml, meta.json, events.jsonl, results.jsonl, the layout squid5 runs and tools/monitor read), from the
REPLAYED events, so the game-log viewer shows what the engine computed, not what the browser said. Exit 1 when a game
fails (``--strict``) or nothing could be read.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "web" / "pyodide"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import browser  # noqa: E402
import replay  # noqa: E402
import room_settings  # noqa: E402
from web.server import engine as E  # noqa: E402

FAST_S = 1.0  # a person's non-empty reply sooner than this is flagged (warning)


def load_record(data: bytes) -> dict:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))


def check_people(room, problems: list, warnings: list) -> None:
    rate = room.settings.rate
    for seat in room.doc.get("humans", []):
        a = seat["agent"]
        for i, r in sorted(room.replies.get(a, {}).items()):
            where = f"{a} call {i} ({r.get('kind')} R{r.get('round')})"
            secs, charged, outcome = float(r.get("seconds") or 0), int(r.get("charged") or 0), r.get("outcome")
            if charged != int(round(secs * rate)):
                problems.append(f"{where}: charged {charged} != seconds {secs:.2f} x rate {rate:.4f}")
            if r.get("out_tokens") != charged:
                problems.append(f"{where}: out_tokens {r.get('out_tokens')} != charged {charged}")
            if secs < 0 or secs > float(r.get("timeout") or 0) + 5:
                problems.append(f"{where}: {secs:.1f} s outside the screen's 0..{r.get('timeout')} s")
            if outcome not in ("submitted", "timeout", "overdrawn", "forfeit"):
                problems.append(f"{where}: unknown outcome {outcome!r}")
            if outcome == "timeout" and secs < float(r.get("timeout") or 0) - 1:
                problems.append(f"{where}: timeout after only {secs:.1f} s")
            if outcome == "submitted" and r.get("text") and secs < FAST_S:
                warnings.append(f"{where}: answered in {secs:.2f} s")


def check_models(room, calls: list[dict] | None, problems: list, warnings: list) -> None:
    recs = [(a, i, r) for a in replay.AGENTS for i, r in sorted(room.replies.get(a, {}).items()) if "info" in r]
    if not recs:
        return
    if calls is None:
        warnings.append(f"{len(recs)} model replies not checked against the Worker's call log (none given)")
        return
    ok = [c for c in calls if int(c.get("status") or 0) == 200]
    by_prompt: dict[str, list[dict]] = {}
    for c in ok:
        by_prompt.setdefault(c["prompt_h"], []).append(c)
    answered = [r for _, _, r in recs if not (r.get("info") or {}).get("error")]
    if len(answered) > len(ok):
        problems.append(f"{len(answered)} model replies but the Worker relayed {len(ok)} successful calls")
    for a, i, r in recs:
        if (r.get("info") or {}).get("error"):
            continue
        where = f"{a} call {i} ({r['info'].get('kind')} R{r['info'].get('round')})"
        cands = by_prompt.get(r["h"]) or []
        if not cands:
            problems.append(f"{where}: no relayed call for this prompt")
            continue
        flat = [c for c in cands if not c.get("stream")]
        if flat and not any(c.get("eval_count") == r["out_tokens"] and c.get("content_h") == replay.digest(r["text"])
                            for c in flat) and not any(c.get("stream") for c in cands):
            problems.append(f"{where}: tokens / text differ from the relayed answer")


def verify(rec: dict, calls: list[dict] | None = None, bundle: str | None = None) -> dict:
    """{game, ok, status, problems, warnings, room}: ``room`` is the replayed ``ReplayRoom`` (None if unreadable)."""
    out = {"game": rec.get("game"), "code": rec.get("code"), "ok": False, "status": None, "problems": [],
           "warnings": [], "room": None, "reported": rec.get("status")}
    problems, warnings = out["problems"], out["warnings"]
    if rec.get("format") != browser.RECORD_FORMAT:
        problems.append(f"unknown record format {rec.get('format')!r}")
        return out
    eng = (rec.get("engine") or {}).get("bundle")
    if bundle and eng and eng != bundle[: len(eng)]:
        warnings.append(f"engine bundle {eng} differs from the repo's {bundle[:12]} (replay with the matching commit "
                        "if this game diverges)")
    try:
        doc = rec["doc"]
        doc["status"] = "running" if doc.get("status") in ("finished", "error") else doc.get("status")
        room = replay.ReplayRoom.load(doc, rec["replies"], make=room_settings.make)
    except Exception as err:  # noqa: BLE001
        problems.append(f"replay failed: {type(err).__name__}: {err}")
        return out
    out["room"], out["status"] = room, room.status
    if room.status == "error":
        problems.append(f"replay ended in an error: {room.error}")
    mine = browser.event_digests(room.events)
    theirs = (rec.get("events") or {}).get("digests") or []
    if mine != theirs:
        first = next((k for k, (x, y) in enumerate(zip(mine, theirs)) if x != y), min(len(mine), len(theirs)))
        ev = room.events[first] if first < len(room.events) else None
        problems.append(f"events differ from #{first} (replay {len(mine)}, reported {len(theirs)}): "
                        f"{ev and ev.get('event')}")
    if (rec.get("events") or {}).get("digest") != browser.digest_of(theirs):
        problems.append("the reported total digest does not match its own event digests")
    res = next((e for e in reversed(room.events) if e.get("event") == "session"), None)
    if browser.canon(res) != browser.canon(rec.get("result")):
        problems.append("the reported session result differs from the replay's")
    if rec.get("status") != room.status:
        problems.append(f"reported status {rec.get('status')!r} but the replay is {room.status!r}")
    check_people(room, problems, warnings)
    check_models(room, calls, problems, warnings)
    out["ok"] = not problems
    return out


def write_run(room, rec: dict, root: Path) -> Path:
    """A verified game as a run directory under ``root`` (named by date, room code and game id)."""
    import yaml

    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime(float(room.doc.get("started_at") or room.created_at)))
    d = root / f"{stamp}_{room.code}_{str(rec.get('game') or 'local')[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    seats = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in room.seats_info().items()}
    rs = room.settings
    (d / "config.yaml").write_text(yaml.safe_dump(E.run_config(rs, seats, room.code), sort_keys=False))
    meta = E.run_meta(rs, seats) | {"verified": {"game": rec.get("game"), "engine": rec.get("engine"),
                                                 "at": time.time()}}
    (d / "meta.json").write_text(json.dumps(meta, default=str))
    lines = lambda evs: "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in evs)  # noqa: E731
    (d / "events.jsonl").write_text(lines(e for e in room.events if e.get("event") in E.LOG_EVENTS))
    (d / "results.jsonl").write_text(lines(e for e in room.events if e.get("event") == "session"))
    return d


# --- the Worker's export ---------------------------------------------------------------------------------------------------

def http_get(url: str, token: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_all(base: str, token: str, since: float) -> list[tuple[str, dict, list[dict] | None, dict]]:
    """(name, record, calls, row) for every game with an upload since ``since``."""
    base = base.rstrip("/")
    rows = json.loads(http_get(f"{base}/api/games?since={since}&limit=1000", token))
    out = []
    for row in rows:
        gid = row["id"]
        rec = load_record(http_get(f"{base}/api/games/{gid}/record", token))
        calls = json.loads(http_get(f"{base}/api/games/{gid}/calls", token))
        out.append((gid, rec, calls, row))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", help="the Worker's origin (needs ARENA_EXPORT_TOKEN in the environment)")
    ap.add_argument("--since", type=float, default=0.0, help="only games updated since this epoch time")
    ap.add_argument("--records", nargs="*", default=[], type=Path, help="record files (.json or .json.gz)")
    ap.add_argument("--calls", type=Path, help="the Worker's call log for a single --records file (JSON list)")
    ap.add_argument("--out", type=Path, help="write passing FINISHED games here as run directories")
    ap.add_argument("--report", type=Path, help="write the per-game verdicts as JSON")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any game fails")
    a = ap.parse_args(argv)
    from build_bundle import bundle_sha  # web/pyodide (on sys.path)

    bundle = bundle_sha()
    items: list[tuple[str, dict, list[dict] | None]] = []
    if a.fetch:
        token = os.environ.get("ARENA_EXPORT_TOKEN", "")
        if not token:
            print("ARENA_EXPORT_TOKEN is not set", file=sys.stderr)
            return 2
        items += [(gid, rec, calls) for gid, rec, calls, _ in fetch_all(a.fetch, token, a.since)]
    calls_file = json.loads(a.calls.read_text()) if a.calls else None
    for p in a.records:
        items.append((p.name, load_record(p.read_bytes()), calls_file))
    if not items:
        print("no records", file=sys.stderr)
        return 1
    verdicts, failed = [], 0
    for name, rec, calls in items:
        v = verify(rec, calls, bundle)
        room = v.pop("room")
        if a.out and v["ok"] and v["status"] == "finished":
            v["run_dir"] = str(write_run(room, rec, a.out))
        failed += not v["ok"]
        verdicts.append({"name": name, **v})
        mark = "PASS" if v["ok"] else "FAIL"
        print(f"{mark} {name} game={v['game']} code={v['code']} replay={v['status']} reported={v['reported']}"
              + "".join(f"\n  ! {x}" for x in v["problems"]) + "".join(f"\n  ~ {x}" for x in v["warnings"]))
    print(f"{len(items) - failed} / {len(items)} passed")
    if a.report:
        a.report.write_text(json.dumps(verdicts, ensure_ascii=False, indent=1, default=str))
    return 1 if (failed and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
