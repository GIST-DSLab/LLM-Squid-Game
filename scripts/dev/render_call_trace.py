#!/usr/bin/env python3
"""Render a ``call_trace.jsonl`` into one self-contained HTML page.

    uv run python scripts/dev/render_call_trace.py <run_dir|trace.jsonl> --out page.html

The trace is written by ``squid_game.providers.trace.TraceProvider`` (see
``scripts/dev/trace_config.py`` for the one-command wrapper). The page
answers one question: for each turn, which sentences went into which role
in what order, for each of the three LLM calls.

Session labelling: the trace records one ``instance_id`` per season
(the runner builds a fresh provider per season). When
``season_results.jsonl`` is present next to the trace its rows are zipped
with the instances in order -- exact only when the run was sequential,
which ``trace_config.py`` enforces with ``parallel_workers: 1``. Without
it, sessions fall back to their ``session_hint``.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

ROLE_COLORS = {
    "system": ("#6b7280", "#f3f4f6"),
    "user": ("#1d4ed8", "#eff6ff"),
    "assistant": ("#15803d", "#f0fdf4"),
}
KINDS = ("confidence", "decision", "task", "unknown")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def resolve_paths(target: Path) -> tuple[Path, Path]:
    """Return ``(trace_file, run_dir)`` for a run directory or a JSONL file."""
    if target.is_dir():
        trace = target / "call_trace.jsonl"
        if not trace.exists():
            candidates = sorted(target.rglob("call_trace.jsonl"))
            if not candidates:
                raise SystemExit(f"No call_trace.jsonl under {target}")
            trace = candidates[0]
        return trace, trace.parent
    return target, target.parent


def load_records(trace: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(trace, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records.sort(key=lambda r: r.get("call_index", 0))
    return records


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def load_season_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------


def cell_index(config: dict[str, Any] | None) -> dict[tuple[str, str], dict]:
    """Map ``(framing, forfeit_condition)`` to the config's season entry."""
    out: dict[tuple[str, str], dict] = {}
    for season in (config or {}).get("seasons", []) or []:
        key = (str(season.get("framing")), str(season.get("forfeit_condition")))
        out.setdefault(key, season)
    return out


def session_labels(
    instances: list[str],
    season_rows: list[dict[str, Any]],
    config: dict[str, Any] | None,
) -> list[str]:
    by_cell = cell_index(config)
    labels: list[str] = []
    for i, instance in enumerate(instances):
        if i < len(season_rows):
            row = season_rows[i]
            framing = str(row.get("framing", "?"))
            forfeit = str(row.get("forfeit_condition", "?"))
            season = by_cell.get((framing, forfeit), {})
            bits = []
            if season.get("cell_id") is not None:
                bits.append(f"Cell {season['cell_id']}")
            bits.append(framing)
            if season.get("reassurance"):
                bits.append("+reassurance")
            bits.append(f"x {forfeit}")
            if row.get("seed") is not None:
                bits.append(f"(seed {row['seed']})")
            labels.append(" ".join(bits))
        else:
            labels.append(f"session {instance}")
    return labels


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def render_message(msg: dict[str, Any]) -> str:
    role = msg.get("role", "?")
    fg, bg = ROLE_COLORS.get(role, ("#92400e", "#fffbeb"))
    return (
        '<div class="msg">'
        f'<div class="role" style="color:{fg};background:{bg}">{esc(role)}</div>'
        f'<pre class="body">{esc(msg.get("content", ""))}</pre>'
        "</div>"
    )


def render_call(rec: dict[str, Any], position: int, of: int) -> str:
    kind = rec.get("call_kind", "unknown")
    turn = rec.get("turn_number")
    turn_label = f"Turn {turn}" if turn is not None else "Turn ?"
    kwargs = rec.get("kwargs", {}) or {}
    meta = " · ".join(
        f"{k}={v}" for k, v in kwargs.items()
    )
    resp = rec.get("response", {}) or {}
    return (
        f'<article class="call" data-kind="{esc(kind)}">'
        '<header class="call-head" onclick="this.parentNode.classList.toggle(\'closed\')">'
        f'<span class="tag k-{esc(kind)}">{esc(kind)}</span>'
        f"<b>{esc(turn_label)} · call {position}/{of}</b>"
        f'<span class="meta">#{esc(rec.get("call_index"))} · {esc(meta)}</span>'
        "</header>"
        '<div class="call-body">'
        + "".join(render_message(m) for m in rec.get("messages", []))
        + '<div class="stub"><div class="stub-h">stub reply (no model was called)</div>'
        f'<pre>{esc(resp.get("content", ""))}</pre>'
        f'<div class="stub-h">thinking</div><pre>{esc(resp.get("thinking", ""))}</pre>'
        "</div></div></article>"
    )


CSS = """
*{box-sizing:border-box}
body{margin:0;background:#fafaf9;color:#1c1917;
 font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 20px 80px}
h1{font-size:20px;margin:24px 0 4px}
h2{font-size:16px;margin:36px 0 8px;padding-top:52px;border-top:1px solid #d6d3d1}
h3{font-size:13px;margin:20px 0 6px;color:#78716c;letter-spacing:.06em;text-transform:uppercase}
.sub{color:#57534e;font-size:13px;margin:0 0 4px}
.bar{position:sticky;top:0;z-index:9;background:#fafaf9ee;backdrop-filter:blur(4px);
 border-bottom:1px solid #d6d3d1;padding:8px 20px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.bar a,.bar button{font:12px/1 inherit;padding:5px 9px;border:1px solid #d6d3d1;border-radius:5px;
 background:#fff;color:#292524;text-decoration:none;cursor:pointer}
.bar button.on{background:#1c1917;color:#fff;border-color:#1c1917}
.bar .sep{width:1px;height:18px;background:#d6d3d1}
.call{border:1px solid #d6d3d1;border-radius:7px;background:#fff;margin:10px 0;overflow:hidden}
.call-head{display:flex;gap:10px;align-items:center;padding:8px 12px;background:#f5f5f4;
 border-bottom:1px solid #e7e5e4;cursor:pointer;font-size:13px}
.call.closed .call-body{display:none}
.call.closed .call-head{border-bottom:none}
.meta{margin-left:auto;color:#78716c;font-size:11px;
 font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.tag{font-size:11px;padding:2px 7px;border-radius:99px;border:1px solid;text-transform:uppercase;
 letter-spacing:.05em}
.k-confidence{color:#7c2d12;border-color:#fdba74;background:#fff7ed}
.k-decision{color:#3730a3;border-color:#a5b4fc;background:#eef2ff}
.k-task{color:#166534;border-color:#86efac;background:#f0fdf4}
.k-unknown{color:#7f1d1d;border-color:#fca5a5;background:#fef2f2}
.msg{display:flex;gap:0;border-bottom:1px solid #f5f5f4}
.role{flex:0 0 84px;padding:10px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
 font-weight:600;text-align:right}
pre.body,.stub pre{margin:0;padding:10px 12px;white-space:pre-wrap;word-break:break-word;
 font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;flex:1;overflow-x:auto}
.stub{margin:10px 12px 12px;border:1px dashed #a8a29e;border-radius:6px;background:#fafaf9}
.stub-h{padding:6px 12px 0;font-size:11px;color:#78716c;text-transform:uppercase;letter-spacing:.06em}
body[data-filter=confidence] .call:not([data-kind=confidence]),
body[data-filter=decision] .call:not([data-kind=decision]),
body[data-filter=task] .call:not([data-kind=task]){display:none}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:10px 12px;
 font-size:12px;color:#78350f;margin:14px 0}
"""

JS = """
function setFilter(k,btn){
  document.body.dataset.filter = k;
  document.querySelectorAll('.bar button[data-f]').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
}
function toggleAll(open){
  document.querySelectorAll('.call').forEach(c=>c.classList.toggle('closed',!open));
}
"""


def build_html(
    records: list[dict[str, Any]],
    trace: Path,
    run_dir: Path,
) -> str:
    config = load_json(run_dir / "experiment_config.json")
    season_rows = load_season_rows(run_dir / "season_results.jsonl")

    sessions: "OrderedDict[str, list[dict]]" = OrderedDict()
    for rec in records:
        sessions.setdefault(
            rec.get("instance_id") or rec.get("session_hint", "?"), []
        ).append(rec)

    labels = session_labels(list(sessions), season_rows, config)
    model = records[0].get("model", "?") if records else "?"
    name = (config or {}).get("name", trace.parent.name)

    anchors = "".join(
        f'<a href="#s{i}">{esc(label)}</a>' for i, label in enumerate(labels)
    )
    head = (
        '<div class="bar">'
        '<button data-f="all" class="on" onclick="setFilter(\'all\',this)">all calls</button>'
        '<button data-f="confidence" onclick="setFilter(\'confidence\',this)">confidence</button>'
        '<button data-f="decision" onclick="setFilter(\'decision\',this)">decision</button>'
        '<button data-f="task" onclick="setFilter(\'task\',this)">task</button>'
        '<span class="sep"></span>'
        '<button onclick="toggleAll(true)">expand</button>'
        '<button onclick="toggleAll(false)">collapse</button>'
        '<span class="sep"></span>' + anchors + "</div>"
    )

    body: list[str] = []
    for idx, (instance, recs) in enumerate(sessions.items()):
        body.append(f'<h2 id="s{idx}">{esc(labels[idx])}</h2>')
        body.append(
            f'<p class="sub">instance <code>{esc(instance)}</code> · '
            f"{len(recs)} calls · first system-prompt hash "
            f'<code>{esc(recs[0].get("session_hint"))}</code></p>'
        )
        turns: "OrderedDict[Any, list[dict]]" = OrderedDict()
        for rec in recs:
            turns.setdefault(rec.get("turn_number"), []).append(rec)
        for turn, calls in turns.items():
            label = f"Turn {turn}" if turn is not None else "Unnumbered calls"
            kinds = " → ".join(c.get("call_kind", "?") for c in calls)
            body.append(f"<h3>{esc(label)} — {esc(kinds)}</h3>")
            for pos, rec in enumerate(calls, 1):
                body.append(render_call(rec, pos, len(calls)))

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = (
        f"<h1>{esc(name)} — call trace</h1>"
        f'<p class="sub">model <code>{esc(model)}</code> · '
        f"{len(sessions)} sessions · {len(records)} calls · rendered {esc(generated)}</p>"
        f'<p class="sub">source <code>{esc(trace)}</code></p>'
        '<div class="note">Every message below is the verbatim <code>messages</code> list '
        "handed to <code>LLMProvider.complete()</code> by the real pipeline. "
        "<b>No model was called</b>: the replies in the dashed boxes are canned stubs, so "
        "forfeit rates, accuracy and reasoning tokens in this run mean nothing. "
        "Prompt assembly — framing, hazard ramp, peer-death notices, the forfeit menu, "
        "the lives ledger — is exactly what a paid run sends.</div>"
    )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(name)} — call trace</title>"
        f"<style>{CSS}</style></head><body data-filter='all'>"
        f"{head}<div class='wrap'>{header}{''.join(body)}</div>"
        f"<script>{JS}</script></body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Run directory or call_trace.jsonl path")
    parser.add_argument("--out", required=True, help="Output HTML path")
    args = parser.parse_args()

    trace, run_dir = resolve_paths(Path(args.target))
    records = load_records(trace)
    if not records:
        raise SystemExit(f"No calls recorded in {trace}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(records, trace, run_dir), encoding="utf-8")
    print(f"Wrote {out} ({len(records)} calls)")


if __name__ == "__main__":
    main()
