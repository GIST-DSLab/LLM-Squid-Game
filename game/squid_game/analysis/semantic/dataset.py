"""Shared turn-level loader for the Call-1 reasoning-investment analyses.

Reads the raw ``*_turns.jsonl`` traces under an ``outputs/final_results``
run directory directly (no pydantic round-trip) so the loader stays usable
on runs whose schema predates or postdates the current models.

Two consumers share this module:

* ``scripts/analysis/analyze_call1_ri.py``   — mixedLM on ``log1p(ri_task)``.
* ``scripts/analysis/probe_reasoning_embeddings.py`` — SentenceBERT + linear probe.

Score reconstruction
--------------------
``score_before_turn`` is rebuilt by forward simulation from the config
``starting_score`` (30 in the 2026-04-22 canonical runs), accumulating
``reward_received``.  This is exact, unlike inverting
``reward_offered_this_turn`` (which is clamped to
``[base_reward, reward_cap_multiple * base_reward]`` and therefore not
invertible at the rails).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

STARTING_SCORE = 30.0

# Model label extracted from the canonical run-directory naming scheme:
# ``YYYYMMDD_HHMM_<model>_<task>``.
_RUN_DIR_RE = re.compile(r"^\d{8}_\d{4}_(?P<model>.+)_(?P<task>[a-z0-9-]+)$")

THREAT_FRAMINGS = {"flagship_corruption", "flagship_corruption_terminal"}
PULL_FRAMINGS = {"baseline_flagship"}
NEUTRAL_FRAMINGS = {"true_baseline"}

TEXT_CHANNELS = ("task", "probe", "forfeit")


@dataclass(frozen=True)
class RunSpec:
    """One experiment output directory plus its display label."""

    path: Path
    model: str
    task: str

    @classmethod
    def from_dir(cls, path: Path) -> "RunSpec":
        match = _RUN_DIR_RE.match(path.name)
        if match is None:
            return cls(path=path, model=path.name, task="unknown")
        return cls(
            path=path,
            model=match.group("model"),
            task=match.group("task"),
        )


def discover_runs(root: Path) -> list[RunSpec]:
    """Every run directory under ``root`` that holds turn traces."""
    runs = [
        RunSpec.from_dir(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and any(child.glob("*_turns.jsonl"))
    ]
    if not runs:
        raise FileNotFoundError(f"no *_turns.jsonl traces under {root}")
    return runs


def _thinking_tokens(record: dict, key: str) -> int | None:
    block = record.get(key)
    if not isinstance(block, dict):
        return None
    value = block.get("thinking_tokens")
    return int(value) if value is not None else None


def load_turns(
    run: RunSpec,
    *,
    include_text: bool = False,
) -> pd.DataFrame:
    """One row per turn for a single run.

    Args:
        run: The run directory to read.
        include_text: When True, carry the per-call ``thinking_text_*``
            traces through. They are large (~2 kB/turn/channel), so the
            regression path leaves them out.

    Returns:
        DataFrame indexed 0..n-1, one row per recorded turn.
    """
    rows: list[dict] = []
    for trace in sorted(run.path.glob("*_turns.jsonl")):
        score_before = STARTING_SCORE
        with trace.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                metadata = record.get("task_metadata") or {}
                framing = record.get("framing")
                row = {
                    "model": run.model,
                    "session_id": record.get("season_id"),
                    "turn_number": record.get("turn_number"),
                    "framing": framing,
                    "forfeit_condition": record.get("forfeit_condition"),
                    "is_threat": framing in THREAT_FRAMINGS,
                    "is_pull": framing in PULL_FRAMINGS,
                    "is_neutral": framing in NEUTRAL_FRAMINGS,
                    "forfeit_allowed": record.get("forfeit_condition")
                    == "allowed",
                    "forfeit_choice": record.get("forfeit_choice"),
                    "forfeit": record.get("forfeit_choice") == "FORFEIT"
                    or bool(record.get("forfeit_decision")),
                    "died": bool(record.get("died")),
                    "p_death_applied": record.get("p_death_applied"),
                    "score_before_turn": score_before,
                    "reward_offered_this_turn": record.get(
                        "reward_offered_this_turn"
                    ),
                    "reward_received": record.get("reward_received"),
                    "psuccess_self": record.get("psuccess_self"),
                    "correct": bool(metadata.get("correct")),
                    "rule_match_score": metadata.get("rule_match_score"),
                    "ri_total": _thinking_tokens(
                        record, "reasoning_investment"
                    ),
                    "ri_task": _thinking_tokens(record, "ri_task"),
                    "ri_probe": _thinking_tokens(record, "ri_probe"),
                    "ri_forfeit": _thinking_tokens(record, "ri_forfeit"),
                }
                if include_text:
                    for channel in TEXT_CHANNELS:
                        row[f"text_{channel}"] = (
                            record.get(f"thinking_text_{channel}") or ""
                        )
                rows.append(row)
                score_before += float(record.get("reward_received") or 0.0)

    frame = pd.DataFrame(rows)
    return frame.sort_values(["session_id", "turn_number"]).reset_index(
        drop=True
    )


def load_all(
    root: Path,
    *,
    include_text: bool = False,
    models: list[str] | None = None,
) -> pd.DataFrame:
    """Concatenated turn table across every discovered run."""
    runs = discover_runs(root)
    if models:
        wanted = set(models)
        runs = [r for r in runs if r.model in wanted]
        if not runs:
            raise ValueError(f"no run matched --model {sorted(wanted)}")
    return pd.concat(
        [load_turns(run, include_text=include_text) for run in runs],
        ignore_index=True,
    )
