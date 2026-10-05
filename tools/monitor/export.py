"""Write one session of a run as a single self-contained HTML file (no server needed).

    python3 tools/monitor/export.py RUN_DIR [--session SID] --out FILE.html

The page code is the monitor's own (monitor.html + static/monitor.{css,js}, inlined); the session's events go into a
<script type="application/json" id="monitor-data"> block that the page detects, with every played round's task rebuilt
from the engine (``puzzles``, as /api/puzzle returns it) so the round panel works offline. Sprites from
tools/monitor/assets/ are embedded as data URIs when present; otherwise the page draws its generated pixel avatars.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import serve  # noqa: E402


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def embedded_assets(assets: Path = serve.ASSETS) -> dict | None:
    man = assets / "manifest.json"
    if not man.exists():
        return None
    m = json.loads(man.read_text())
    chars = []
    for c in m.get("characters", []):
        sheet = assets / c["sheet"]
        if not sheet.exists():
            continue
        prof = assets / c["profile"] if c.get("profile") else None
        chars.append({"name": c["name"], "sheet": data_uri(sheet),
                      "profile": data_uri(prof) if prof and prof.exists() else None})
    bubble = assets / m["bubble"] if m.get("bubble") else None
    return {**m, "characters": chars, "bubble": data_uri(bubble) if bubble and bubble.exists() else None}


def script_json(obj) -> str:
    """JSON safe inside a <script> element: no "</" (could close it) and no "<!--"; both escapes stay valid JSON."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "\\u003c!--")


def build_page(payload: dict) -> str:
    html = serve.PAGE.read_text(encoding="utf-8")
    css = (serve.STATIC / "monitor.css").read_text(encoding="utf-8")
    js = (serve.STATIC / "monitor.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    html = html.replace('<link rel="stylesheet" href="static/monitor.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<script src="static/monitor.js"></script>', f"<script>\n{js}\n</script>")
    data = f'<script type="application/json" id="monitor-data">{script_json(payload)}</script>'
    return html.replace("<!--EMBED-->", data)


def session_puzzles(run_dir: Path, sid: str, events: list[dict]) -> tuple[dict, str | None]:
    """{round: puzzle} for every round the session started; an error string instead when the task cannot be rebuilt."""
    rounds = sorted({int(e["round"]) for e in events if e.get("event") == "round_start" and e.get("round")})
    out = {}
    try:
        for r in rounds:
            out[str(r)] = serve.round_puzzle(run_dir, sid, r)
    except Exception as err:  # noqa: BLE001 - the page still works without the panel's data
        return out, f"puzzle rebuild failed: {err}"
    return out, None


def export(run_dir: Path, session: str | None, out: Path, with_assets: bool = True) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    if not (run_dir / "events.jsonl").is_file():
        raise SystemExit(f"no events.jsonl in {run_dir}")
    sessions = serve.list_sessions(run_dir)["sessions"]
    if not sessions:
        raise SystemExit(f"no session_start in {run_dir}/events.jsonl")
    sid = session or sessions[0]["id"]
    if sid not in {s["id"] for s in sessions}:
        raise SystemExit(f"session {sid} not in this run; sessions: {', '.join(s['id'] for s in sessions)}")
    events = serve.read_all(run_dir, sid)
    puzzles, puzzle_error = session_puzzles(run_dir, sid, events)
    payload = {"run": f"{run_dir.parent.name}/{run_dir.name}",
               "session": sid, "model": serve.read_meta(run_dir).get("model"),
               "events": events, "result": serve.results_by_session(run_dir).get(sid),
               "puzzles": puzzles, "puzzle_error": puzzle_error,
               "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "assets": embedded_assets() if with_assets else None}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_page(payload), encoding="utf-8")
    return payload


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="export one session as a self-contained monitor page")
    ap.add_argument("run_dir")
    ap.add_argument("--session", help="session id (default: the first session in the run)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-assets", action="store_true", help="leave the sprites out (generated avatars)")
    args = ap.parse_args(argv)
    p = export(Path(args.run_dir), args.session, Path(args.out), not args.no_assets)
    print(f"{args.out}: session {p['session']}, {len(p['events'])} events, {len(p['puzzles'])} round tasks, "
          f"{'sprites embedded' if p['assets'] else 'generated avatars'}"
          + (f" ({p['puzzle_error']})" if p["puzzle_error"] else ""))


if __name__ == "__main__":
    main()
