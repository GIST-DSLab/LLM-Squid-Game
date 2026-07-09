"""Threat-registration re-analysis (spec 2026-07-09). A1 + A2."""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from pathlib import Path

ANALYSIS_FRAMINGS = {
    "baseline_flagship": "pull_only",
    "flagship_corruption": "pull_push",
}


@dataclass(frozen=True)
class ThreatTurn:
    turn_id: str
    session_id: str
    model: str
    framing: str
    forfeit_condition: str
    cell_id: int
    framing_bucket: str          # "pull_only" | "pull_push"
    text: str
    text_source: str             # "thinking_forfeit" | "raw_forfeit" | "missing"


def _cell_id(framing: str, forfeit_condition: str) -> int:
    return {
        ("baseline_flagship", "allowed"): 1,
        ("baseline_flagship", "not_allowed"): 2,
        ("flagship_corruption", "allowed"): 3,
        ("flagship_corruption", "not_allowed"): 4,
    }.get((framing, forfeit_condition), -1)


def _resolve_text(rec: dict) -> tuple[str, str]:
    tf = (rec.get("thinking_text_forfeit") or "").strip()
    if tf:
        return tf, "thinking_forfeit"
    rf = (rec.get("raw_response_forfeit") or "").strip()
    if rf:
        return rf, "raw_forfeit"
    return "", "missing"


def load_forfeit_turns(run_dir: str | Path, model: str) -> list[ThreatTurn]:
    """Load Cells 1-4 Call 2 reasoning turns from a run directory."""
    out: list[ThreatTurn] = []
    for path in sorted(glob.glob(os.path.join(str(run_dir), "*_turns.jsonl"))):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                framing = rec.get("framing")
                if framing not in ANALYSIS_FRAMINGS:
                    continue
                forfeit = rec.get("forfeit_condition")
                cell = _cell_id(framing, forfeit)
                if cell < 0:
                    continue
                text, source = _resolve_text(rec)
                out.append(ThreatTurn(
                    turn_id=str(rec.get("turn_id")),
                    session_id=str(rec.get("season_id")),
                    model=model,
                    framing=framing,
                    forfeit_condition=forfeit,
                    cell_id=cell,
                    framing_bucket=ANALYSIS_FRAMINGS[framing],
                    text=text,
                    text_source=source,
                ))
    return out
