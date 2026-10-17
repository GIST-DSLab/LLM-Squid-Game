"""Static export of the game-log monitor, the model comparison and the leaderboard: a folder of HTML, JS and JSON that
any static host (GitHub Pages) serves with no server behind it.

    python3 tools/monitor/build_static.py [--root web/data/runs] --out _site/monitor

Writes, under OUT (the site's ``monitor/`` folder):

    index.html, compare.html            the monitor's own pages with ``window.MONITOR_STATIC = "data/"`` set, so
                                        static/monitor.js and static/compare.js read the files below instead of api/
    static/                             the page code (monitor.js, compare.js, css, the arena's signal_ui.js)
    data/runs.json                      as /api/runs (live = false, mtime from the run folder's timestamp)
    data/runs/<run>/sessions.json       as /api/sessions?run=<run>
    data/runs/<run>/s/<sid>/events/<k>.json
                                        the session's events (/api/events), part k of n (one part unless it is large);
                                        ``offset`` = k + 1, ``more`` = k + 1 < n
    data/runs/<run>/s/<sid>/giving.json, analysis.json
                                        as /api/giving and /api/analysis with &session=<sid> (the page reads this game only)
    data/runs/<run>/s/<sid>/puzzle/<r>.json
                                        as /api/puzzle for every round the session started (``by_n`` holds the N = 1..4
                                        variants the task panel's N buttons show); an engine failure is written as
                                        {"error", "_status": 500}
    data/compare/index.json, <id>.json, <id>/<chart>.csv
                                        as /api/compare (and .csv) for every run group (first path segment, e.g.
                                        ``e52_v22/``) and every model inside a group
    data/leaderboard/index.json, <id>.json, <id>.csv
                                        as /api/leaderboard (and ?csv=1) for every run group
    data/build.json                     what was built (counts, bytes)

The engine (``squid5``) is imported read-only by serve.py to rebuild each round's task; nothing else from the repo runs.
Only PyYAML is needed beyond the standard library.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import compare  # noqa: E402
import serve  # noqa: E402

DEFAULT_ROOT = serve.REPO / "web" / "data" / "runs"
SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")  # one path segment written to disk and put in a URL as is
PART_BYTES = 20 * 1024 * 1024  # a session's events are split into parts above this (the page follows ``more``)
MAX_FILE = 50 * 1024 * 1024  # GitHub refuses files over 100 MB; keep a wide margin
MAX_SITE = 1024 * 1024 * 1024  # the GitHub Pages site limit
CHARTS = [*compare.CHARTS, "recip", "survival", "map", "e51", "summary", "abilities", "seats", "assoc"]
STATIC_FLAG = '<script>window.MONITOR_STATIC = "data/";</script>\n'


def dump(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    path.write_bytes(body)
    return len(body)


def safe_rel(rel: str) -> bool:
    return all(SAFE.match(p) for p in rel.split("/"))


def folder_time(rel: str, fallback: float) -> float:
    """The run folder's YYYYMMDD_HHMM as epoch seconds (UTC): a checkout has no meaningful file times."""
    m = re.search(r"(20\d\d)(\d\d)(\d\d)_(\d\d)(\d\d)", rel)
    if not m:
        return fallback
    y, mo, d, h, mi = map(int, m.groups())
    return float(calendar.timegm((y, mo, d, h, mi, 0)))


def set_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "set"


def page(src: Path) -> str:
    """A monitor page with the static flag set before its scripts."""
    html = src.read_text(encoding="utf-8")
    anchor = '<script src="static/'
    if anchor not in html:
        raise SystemExit(f"{src.name}: no <script src=\"static/...\"> to put the static flag before")
    i = html.index(anchor)
    return html[:i] + STATIC_FLAG + html[i:]


def write_pages(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(serve.PAGE), encoding="utf-8")
    (out / "compare.html").write_text(page(serve.COMPARE_PAGE), encoding="utf-8")
    st = out / "static"
    st.mkdir(exist_ok=True)
    for f in serve.STATIC.iterdir():
        if f.is_file() and not f.name.startswith("."):
            shutil.copy2(f, st / f.name)
    for name, f in serve.SHARED.items():  # web/frontend/signal_ui.js
        if f.is_file():
            shutil.copy2(f, st / name)


def write_session(run_dir: Path, rel: str, sid: str, base: Path, mtime: float, log=print) -> dict:
    """One session's events (in parts), giving, analysis and every started round's task."""
    sdir = base / "s" / sid
    events = serve.read_all(run_dir, sid)
    result = serve.results_by_session(run_dir).get(sid)
    info = serve.run_index(run_dir / "events.jsonl").sessions.get(sid)
    parts, cur, size = [], [], 0
    for e in events:
        n = len(json.dumps(e, ensure_ascii=False, default=str).encode("utf-8")) + 1
        if cur and size + n > PART_BYTES:
            parts.append(cur)
            cur, size = [], 0
        cur.append(e)
        size += n
    parts.append(cur)
    for k, part in enumerate(parts):
        dump(sdir / "events" / f"{k}.json",
             {"events": part, "offset": k + 1, "size": len(parts), "more": k + 1 < len(parts), "pending": 0,
              "reset": False, "mtime": mtime, "now": mtime, "live": False, "result": result, "session": info,
              "static": True})
    dump(sdir / "giving.json", serve.run_giving(run_dir, sid))
    dump(sdir / "analysis.json", serve.run_analysis(run_dir, sid))
    rounds = sorted({int(e["round"]) for e in events if e.get("event") == "round_start" and e.get("round")})
    failed = 0
    for r in rounds:
        try:
            obj = serve.round_puzzle(run_dir, sid, r)
        except (serve.BadRequest, serve.NotFound) as err:
            obj, failed = {"error": str(err), "_status": 404}, failed + 1
        except Exception as err:  # noqa: BLE001 - the page shows the error, as serve.py's 500 does
            obj, failed = {"error": f"puzzle rebuild failed: {err!r}", "_status": 500}, failed + 1
        dump(sdir / "puzzle" / f"{r}.json", obj)
    if failed:
        log(f"  {rel} {sid}: {failed} of {len(rounds)} round tasks could not be rebuilt")
    return {"events": len(events), "parts": len(parts), "rounds": len(rounds), "puzzle_failed": failed}


def compare_sets(runs: list[dict]) -> tuple[list[dict], list[dict]]:
    """The run sets to aggregate: every group (first path segment) and, when it holds several models, every model in
    it. Returns (compare sets, leaderboard sets); a set = {id, picks, runs, models}."""
    groups: dict[str, list[dict]] = {}
    for r in runs:
        groups.setdefault(r["run"].split("/")[0], []).append(r)
    cmp_sets, lb_sets, seen = [], [], set()
    for g in sorted(groups):
        rs = groups[g]
        models = sorted({str(r.get("model")) for r in rs})
        whole = {"id": set_id(g), "picks": g + "/", "runs": sorted(r["run"] for r in rs), "models": models}
        cmp_sets.append(whole)
        lb_sets.append(whole)
        seen.add(tuple(whole["runs"]))
        if len(models) < 2:
            continue
        for m in models:
            sub = sorted(r["run"] for r in rs if str(r.get("model")) == m)
            if tuple(sub) in seen:
                continue
            seen.add(tuple(sub))
            cmp_sets.append({"id": set_id(f"{g}__{m}"), "picks": ",".join(sub), "runs": sub, "models": [m]})
    return cmp_sets, lb_sets


def write_compare(root: Path, data_dir: Path, runs: list[dict], log=print) -> dict:
    cmp_sets, lb_sets = compare_sets(runs)
    cdir, ldir = data_dir / "compare", data_dir / "leaderboard"
    by_runs: dict[tuple, dict] = {}
    for s in cmp_sets:
        picks = [s["picks"]] if s["picks"].endswith("/") else s["runs"]
        data = compare.compare(root, picks)
        by_runs[tuple(s["runs"])] = data
        dump(cdir / f"{s['id']}.json", {**compare.public(data), "picks": picks})
        for chart in CHARTS:
            (cdir / s["id"]).mkdir(parents=True, exist_ok=True)
            (cdir / s["id"] / f"{chart}.csv").write_bytes(compare.chart_csv(data, chart).encode("utf-8-sig"))
    for s in lb_sets:
        data = by_runs[tuple(s["runs"])]
        dump(ldir / f"{s['id']}.json", {"picks": [s["picks"]], **compare.leaderboard_rows(data)})
        ldir.mkdir(parents=True, exist_ok=True)
        (ldir / f"{s['id']}.csv").write_bytes(compare.chart_csv(data, "leaderboard").encode("utf-8-sig"))
    dump(cdir / "index.json", {"sets": cmp_sets})
    dump(ldir / "index.json", {"sets": lb_sets})
    log(f"compare: {len(cmp_sets)} run sets, leaderboard: {len(lb_sets)} groups")
    return {"compare_sets": len(cmp_sets), "leaderboard_sets": len(lb_sets)}


def tree_size(out: Path) -> tuple[int, int, tuple[int, str]]:
    total, files, biggest = 0, 0, (0, "")
    for dirpath, _dirs, names in os.walk(out):
        for n in names:
            p = Path(dirpath) / n
            b = p.stat().st_size
            total, files = total + b, files + 1
            biggest = max(biggest, (b, p.relative_to(out).as_posix()))
    return total, files, biggest


def build(root: Path, out: Path, log=print) -> dict:
    root, out = Path(root).expanduser().resolve(), Path(out).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"no run root at {root}")
    if out.exists() and any(out.iterdir()):
        if not (out / "data" / "build.json").is_file():  # never wipe a folder this script did not write
            raise SystemExit(f"{out} is not empty and holds no earlier build (data/build.json); pick an empty folder")
        shutil.rmtree(out)
    write_pages(out)
    data = out / "data"
    runs = []
    for r in serve.list_runs(root):
        if not safe_rel(r["run"]):
            log(f"skip {r['run']}: a path segment outside [A-Za-z0-9_.-]")
            continue
        runs.append({**r, "mtime": folder_time(r["run"], r["mtime"]), "live": False})
    runs.sort(key=lambda r: (r["mtime"], r["run"]), reverse=True)
    dump(data / "runs.json", {"root": "web/data/runs", "static": True, "runs": runs})
    n_sessions = n_events = n_rounds = n_failed = 0
    for r in runs:
        rel, run_dir = r["run"], serve.run_dir_of(root, r["run"])
        base = data / "runs" / rel
        listed = serve.list_sessions(run_dir)
        sessions = [s for s in listed["sessions"] if SAFE.match(str(s["id"]))]
        for s in listed["sessions"]:
            if s not in sessions:
                log(f"skip session {s['id']!r} of {rel}: unsafe id")
        dump(base / "sessions.json", {"run": rel, **listed, "mtime": r["mtime"], "live": False, "sessions": sessions})
        for s in sessions:
            st = write_session(run_dir, rel, s["id"], base, r["mtime"], log)
            n_sessions += 1
            n_events += st["events"]
            n_rounds += st["rounds"]
            n_failed += st["puzzle_failed"]
    cmp_stats = write_compare(root, data, runs, log)
    total, files, biggest = tree_size(out)
    summary = {"built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": len(runs), "sessions": n_sessions,
               "events": n_events, "round_tasks": n_rounds, "round_tasks_failed": n_failed, **cmp_stats,
               "files": files + 1, "bytes": total, "biggest": {"bytes": biggest[0], "path": biggest[1]}}
    dump(data / "build.json", summary)
    if biggest[0] > MAX_FILE:
        raise SystemExit(f"{biggest[1]} is {biggest[0]:,} bytes (> {MAX_FILE:,})")
    if total > MAX_SITE:
        raise SystemExit(f"the static tree is {total:,} bytes (> {MAX_SITE:,}, the GitHub Pages limit)")
    log(f"{out}: {len(runs)} runs, {n_sessions} sessions, {n_rounds} round tasks ({n_failed} failed), "
        f"{files + 1} files, {total / 1e6:.1f} MB, biggest {biggest[1]} {biggest[0] / 1e6:.1f} MB")
    return summary


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="static export of the game-log monitor, compare page and leaderboard")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="run root (default web/data/runs)")
    ap.add_argument("--out", required=True, help="output folder = the site's monitor/ (replaced)")
    args = ap.parse_args(argv)
    build(Path(args.root), Path(args.out))


if __name__ == "__main__":
    main()
