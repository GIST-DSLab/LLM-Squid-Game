"""Shared turn-level loader for the task-call reasoning-investment analyses.

Reads the raw ``*_turns.jsonl`` traces under an ``outputs/final_results``
run directory directly (no pydantic round-trip) so the loader stays usable
on runs whose schema predates or postdates the current models.

Two consumers share this module:

* ``scripts/analysis/analyze_task_call_ri.py``   — mixedLM on ``log1p(ri_task)``.
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

from squid_game.evaluation.shared.threat_level import threat_level_of

STARTING_SCORE = 30.0

# Model label extracted from the canonical run-directory naming scheme:
# ``YYYYMMDD_HHMM_<model>_<task>``.
_RUN_DIR_RE = re.compile(r"^\d{8}_\d{4}_(?P<model>.+)_(?P<task>[a-z0-9-]+)$")

THREAT_FRAMINGS = {"flagship_corruption", "flagship_corruption_terminal"}
PULL_FRAMINGS = {"baseline_flagship"}
NEUTRAL_FRAMINGS = {"true_baseline"}

TEXT_CHANNELS = ("task", "probe", "forfeit", "confidence", "forfeit_task")

#: The channels that map one-to-one onto a ``thinking_text_<channel>``
#: field in the trace. ``forfeit_task`` is composed from two of these
#: (spec 5.1) and therefore has no trace field of its own.
_TRACE_TEXT_CHANNELS = ("task", "probe", "forfeit", "confidence")


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
    legacy: bool = False,
) -> pd.DataFrame:
    """One row per turn for a single run.

    Args:
        run: The run directory to read.
        include_text: When True, carry the per-call ``thinking_text_*``
            traces through as ``text_<channel>`` for every channel in
            :data:`TEXT_CHANNELS` — including ``text_forfeit_task``, which
            has no trace field and is composed here from the decision CoT
            then the task CoT. They are large (~2 kB/turn/channel), so the
            regression path leaves them out.
        legacy: Passed to
            :func:`squid_game.evaluation.shared.threat_level.threat_level_of`.
            The archived Phase O v6 framings only acquire a ``threat_level``
            when the caller opts in, so a ladder-era analysis never silently
            absorbs ``baseline_flagship`` rows as "level 1".

    Returns:
        DataFrame indexed 0..n-1, one row per recorded turn. Carries
        ``threat_level`` (nullable int) and the lives columns
        (``lives_remaining``/``lives_before``/``lives_after``/``life_lost``);
        the lives columns are ``None``/False on every pre-2026-09-03 trace,
        which the probes fill with -1 rather than dropping the row.
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
                lives_after = record.get("lives_after")
                if lives_after is None:
                    lives_after = record.get("lives_remaining")
                row = {
                    "model": run.model,
                    "threat_level": threat_level_of(framing, legacy=legacy),
                    "lives_before": record.get("lives_before"),
                    "lives_after": lives_after,
                    # ``lives_remaining`` is the scalar-baseline feature: the
                    # margin the agent was looking at *while deciding*, i.e.
                    # the count entering the turn.
                    "lives_remaining": record.get(
                        "lives_before", record.get("lives_remaining")
                    ),
                    "life_lost": bool(record.get("life_lost")),
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
                    # Benchmark traces written before 2026-09-04 carry no
                    # ``correct`` key; fall back to the success factor.
                    "correct": bool(
                        metadata["correct"] if "correct" in metadata
                        else (record.get("task_success_factor") or 0) > 0
                    ),
                    "rule_match_score": metadata.get("rule_match_score"),
                    "ri_total": _thinking_tokens(
                        record, "reasoning_investment"
                    ),
                    "ri_task": _thinking_tokens(record, "ri_task"),
                    "ri_probe": _thinking_tokens(record, "ri_probe"),
                    "ri_forfeit": _thinking_tokens(record, "ri_forfeit"),
                    # Confidence call (2026-09-04). ``p_threat_self`` is the
                    # SDI denominator, not a probe feature -- see
                    # ``embeddings.SCALAR_FEATURES``.
                    "p_threat_self": record.get("p_threat_self"),
                    "ri_confidence": _thinking_tokens(
                        record, "ri_confidence"
                    ),
                }
                if include_text:
                    for channel in _TRACE_TEXT_CHANNELS:
                        row[f"text_{channel}"] = (
                            record.get(f"thinking_text_{channel}") or ""
                        )
                    # Composite channel (spec 5.1): decision CoT then task
                    # CoT; whichever side exists when the other is empty.
                    parts = [
                        p for p in (row["text_forfeit"], row["text_task"]) if p
                    ]
                    row["text_forfeit_task"] = "\n\n".join(parts)
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
    legacy: bool = False,
    sdi_table: Path | None = None,
) -> pd.DataFrame:
    """Concatenated turn table across every discovered run.

    Args:
        sdi_table: Optional ``sdi_turns.csv`` written by
            ``scripts.analysis.resample_survival_drive``. When given, its
            ``q``/``p``/``sdi`` columns are left-merged onto the turn table
            on ``(session_id, turn_number)``. The merge is deliberately a
            plain left join: a turn the resampler skipped (or one whose
            ``p`` was 0) keeps its row and carries NaN, so the row count
            of the returned frame never depends on the resample coverage.
    """
    runs = discover_runs(root)
    if models:
        wanted = set(models)
        runs = [r for r in runs if r.model in wanted]
        if not runs:
            raise ValueError(f"no run matched --model {sorted(wanted)}")
    frame = pd.concat(
        [
            load_turns(run, include_text=include_text, legacy=legacy)
            for run in runs
        ],
        ignore_index=True,
    )
    if sdi_table is not None:
        from squid_game.evaluation.behavioral.survival_drive import (
            load_sdi_table,
        )

        sdi = load_sdi_table(Path(sdi_table))[
            ["session_id", "turn_number", "q", "p", "sdi"]
        ]
        frame = frame.merge(
            sdi, on=["session_id", "turn_number"], how="left"
        )
    return frame
