"""Merge proxy-captured thinking traces into canonical per-session turn JSONL.

The Anthropic proxy (`interface/anthropic_proxy.py`) appends one record per
API call to `$SQUID_THINKING_LOG_DIR/api_calls.jsonl`. The game server writes
`SeasonResult` objects — each containing a `turns` list of `TurnResult` —
to `outputs/api_sessions/season_results.jsonl`. This script joins the two
by `(session_id, turn_number)` and emits one canonical
`{session_id}_turns.jsonl` per session in the *exact* same format MLX /
Ollama experiments produce (so downstream scripts like
`scripts/thinking_analysis.py` do not need to change).

Usage:

    uv run python scripts/merge_proxy_thinking.py \
        --proxy-log outputs/api_sessions/thinking_traces/api_calls.jsonl \
        --season-results outputs/api_sessions/season_results.jsonl \
        --out-dir outputs/api_sessions/turns_merged

    # Defaults (no args): picks up the standard paths above.

Notes:

  * Multiple Claude API calls can happen within a single game turn (tool
    loop). Their thinking blocks are concatenated in arrival order with
    `\n\n---\n\n` as a separator so the per-call granularity is
    recoverable without losing the turn-level view.
  * `reasoning_investment.thinking_tokens` is summed across all proxy
    calls for the turn.
  * The original `thinking_text` stored by the game server (the agent's
    self-reported reasoning from POST /api/action) is preserved into a new
    field `agent_reported_thinking_text` so nothing is lost.
  * Idempotent: rerunning overwrites the merged JSONL.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
_DEFAULT_PROXY_LOG = _REPO / "outputs" / "api_sessions" / "thinking_traces" / "api_calls.jsonl"
_DEFAULT_SEASONS = _REPO / "outputs" / "api_sessions" / "season_results.jsonl"
_DEFAULT_OUT = _REPO / "outputs" / "api_sessions" / "turns_merged"

_TURN_SEP = "\n\n---\n\n"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"warning: {path}:{i} malformed JSON skipped ({exc})", file=sys.stderr)
    return rows


def _index_proxy_calls(proxy_rows: list[dict]) -> dict[tuple[str, int], list[dict]]:
    """Group proxy records by (session_id, turn_number) preserving arrival order."""
    idx: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for rec in proxy_rows:
        sid = rec.get("session_id")
        turn = rec.get("turn_number")
        if not sid or not isinstance(turn, int):
            continue
        idx[(sid, turn)].append(rec)
    for key in idx:
        idx[key].sort(key=lambda r: r.get("started_at") or "")
    return idx


def _merge_turn_thinking(calls: list[dict]) -> tuple[str | None, int, int, int]:
    """Combine per-call thinking into one turn-level blob.

    Returns (thinking_text, thinking_tokens, total_tokens, steps)."""
    texts = [
        c.get("thinking_text")
        for c in calls
        if isinstance(c.get("thinking_text"), str) and c.get("thinking_text")
    ]
    merged = _TURN_SEP.join(texts) if texts else None
    tt_tokens = 0
    tot_tokens = 0
    steps = 0
    for c in calls:
        ri = c.get("reasoning_investment") or {}
        tt_tokens += int(ri.get("thinking_tokens") or 0)
        tot_tokens += int(ri.get("total_tokens") or 0)
        steps += int(ri.get("reasoning_steps") or 0)
    return merged, tt_tokens, tot_tokens, steps


def _apply_to_turn(turn: dict, calls: list[dict]) -> dict:
    """Return a new TurnResult dict with proxy thinking applied."""
    merged, tt_tokens, tot_tokens, steps = _merge_turn_thinking(calls)
    out = dict(turn)

    # Preserve whatever the game server originally wrote.
    if "agent_reported_thinking_text" not in out:
        out["agent_reported_thinking_text"] = out.get("thinking_text")

    if merged is not None:
        out["thinking_text"] = merged
        # Also stamp the reasoning_investment so thinking_analysis.py picks
        # up the real token count rather than the agent's self-report.
        ri = dict(out.get("reasoning_investment") or {})
        ri["thinking_tokens"] = tt_tokens
        if tot_tokens:
            ri["total_tokens"] = max(int(ri.get("total_tokens") or 0), tot_tokens)
        if steps:
            ri["reasoning_steps"] = max(int(ri.get("reasoning_steps") or 0), steps)
        out["reasoning_investment"] = ri

    # Annotate provenance so downstream consumers can tell which turns have
    # real thinking blocks vs. only agent self-report.
    prov = {
        "thinking_source": "anthropic_proxy" if merged is not None else "agent_reported",
        "proxy_api_calls": len(calls),
    }
    out["_merge_provenance"] = prov
    return out


def _process(
    proxy_log: Path,
    season_results: Path,
    out_dir: Path,
) -> dict:
    proxy_rows = _load_jsonl(proxy_log)
    seasons = _load_jsonl(season_results)
    calls_by_key = _index_proxy_calls(proxy_rows)

    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, Path, int, int]] = []
    missing_sessions: list[str] = []

    for season in seasons:
        season_id = season.get("season_id") or season.get("session_id")
        turns = season.get("turns") or []
        if not season_id or not turns:
            continue

        turn_lines: list[dict] = []
        matched = 0
        for turn in turns:
            turn_num = turn.get("turn_number")
            if not isinstance(turn_num, int):
                turn_lines.append(turn)
                continue
            calls = calls_by_key.get((season_id, turn_num), [])
            if calls:
                matched += 1
            turn_lines.append(_apply_to_turn(turn, calls))

        out_path = out_dir / f"{season_id}_turns.jsonl"
        with out_path.open("w", encoding="utf-8") as fh:
            for rec in turn_lines:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written.append((season_id, out_path, len(turns), matched))
        if matched == 0:
            missing_sessions.append(season_id)

    summary = {
        "proxy_records": len(proxy_rows),
        "seasons": len(seasons),
        "sessions_written": len(written),
        "sessions_no_proxy_match": missing_sessions,
        "out_dir": str(out_dir),
        "per_session": [
            {"session_id": sid, "path": str(p), "turns": t, "matched": m}
            for sid, p, t, m in written
        ],
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proxy-log", type=Path, default=_DEFAULT_PROXY_LOG)
    ap.add_argument("--season-results", type=Path, default=_DEFAULT_SEASONS)
    ap.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT)
    ap.add_argument("--print-json", action="store_true", help="emit summary JSON to stdout")
    args = ap.parse_args()

    summary = _process(args.proxy_log, args.season_results, args.out_dir)
    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"proxy records:       {summary['proxy_records']}")
        print(f"seasons scanned:     {summary['seasons']}")
        print(f"sessions written:    {summary['sessions_written']}")
        print(f"out dir:             {summary['out_dir']}")
        if summary["sessions_no_proxy_match"]:
            print(
                f"WARN: {len(summary['sessions_no_proxy_match'])} session(s) had "
                "NO proxy thinking records:"
            )
            for sid in summary["sessions_no_proxy_match"]:
                print(f"   - {sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
