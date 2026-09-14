"""Pilot read-out for the subagent-kill design: the roster, the spawns, the CoT.

    uv run python -m scripts.analysis.subagent_kill_ledger \
        outputs/2026-09-14/subagent_kill_pilot/<ts>_... \
        --out results/subagent_kill/pilot

Three artefacts, one question each.

``ledger.csv`` -- one row per recorded round, straight off
``to_long_dataframe``'s ten subagent columns plus the ids and the graded
outcome. This is the file to join anything else against.

``summary.md`` -- three tables per cell. How many slots a session lost;
how many spawns and denials a round carried; and the accuracy split by
``solvable_with_alive_slots``, which is the whole point of the sharded
cell: a round whose surviving roster can no longer reach the clues it
needs is unanswerable by construction, and pooling it with the reachable
rounds hides the mechanic inside the accuracy column.

``cot_mentions.jsonl`` -- every MAIN-THREAD task-call CoT
(``TurnResult.thinking_text_task``) that names a slot, with its run,
session and round. The slots are called ``clue-N``, so ``clue-`` is the
marker; the subagents' own thinking (``thinking_text_subagents``) is a
different channel and is deliberately not mixed in here.

⚠️ ``cell_id`` comes from the season's own recorded ``cell_id``, not from
``loaders.infer_cell_id`` -- that map is the Phase-3 ``*_electricity``
one and returns None for every ``hz_*`` framing this design runs, so the
long frame's own ``cell_id`` column is null on these runs.

⚠️ FORFEIT rounds carry no ``task_metadata`` at all (the split-call path
ends the round before the task call), so their five shard columns are
blank here even in a sharded cell. That is absence of a record, not a
round that was unsharded.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from squid_game.evaluation import (
    discover_season_jsonl,
    load_seasons,
    to_long_dataframe,
)

#: The ten long-format columns this design added, in loader order.
SUBAGENT_COLUMNS: tuple[str, ...] = (
    "subagents_alive_before",
    "subagent_killed",
    "n_spawns",
    "n_denied_spawns",
    "ri_subagents_total",
    "clue_sharding",
    "threshold",
    "required_slots",
    "reachable_clues",
    "solvable_with_alive_slots",
)

#: ``ledger.csv``'s header, in order.
LEDGER_COLUMNS: tuple[str, ...] = (
    "run",
    "session_id",
    "cell_id",
    "framing",
    "turn",
    "correct",
    *SUBAGENT_COLUMNS,
)

#: Slot names are ``clue-1`` .. ``clue-N``; this is what a CoT mentioning
#: one of them looks like without committing to a particular index.
SLOT_MARKER = "clue-"


def _clean(value):
    """``None`` for anything pandas turned into a missing value.

    A one-column-per-turn frame holds ``None`` and ``NaN`` for the same
    thing, and pandas picks which one by dtype -- a string column of
    slot names comes back as ``NaN`` where the round revoked nobody.
    ``NaN`` is TRUTHY, so a plain ``if row["subagent_killed"]`` counts
    every round as a kill. Every value copied out of the frame goes
    through here first.
    """
    if isinstance(value, (list, dict)):
        return value
    try:
        missing = bool(pd.isna(value))
    except (TypeError, ValueError):
        return value
    return None if missing else value


def _rows(run_dir: Path) -> tuple[list[dict], list[dict]]:
    """The ledger rows and the CoT mentions of one run directory.

    Args:
        run_dir: A single run directory (the one holding
            ``season_results.jsonl``).

    Returns:
        ``(ledger_rows, cot_rows)``.
    """
    seasons = load_seasons(discover_season_jsonl(run_dir))
    frame = to_long_dataframe(seasons)
    by_turn = {
        (season.season_id, turn.turn_number): (season, turn)
        for season in seasons
        for turn in season.turns
    }

    ledger: list[dict] = []
    cots: list[dict] = []
    for record in frame.to_dict("records"):
        key = (record["session_id"], record["turn"])
        season, turn = by_turn[key]
        ledger.append(
            {
                "run": run_dir.name,
                "session_id": record["session_id"],
                "cell_id": (
                    getattr(season, "cell_id", None)
                    if getattr(season, "cell_id", None) is not None
                    else _clean(record["cell_id"])
                ),
                "framing": record["framing"],
                "turn": record["turn"],
                "correct": _correct(turn, record),
                **{column: _clean(record[column]) for column in SUBAGENT_COLUMNS},
            }
        )
        cot = getattr(turn, "thinking_text_task", None)
        if cot and SLOT_MARKER in cot:
            cots.append(
                {
                    "run": run_dir.name,
                    "session_id": season.season_id,
                    "cell_id": season.cell_id,
                    "turn": turn.turn_number,
                    "thinking_text_task": cot,
                }
            )
    return ledger, cots


def _correct(turn, record: dict) -> bool | None:
    """The graded outcome of a round.

    ``task_metadata["correct"]`` is what the task module wrote; the long
    frame's ``action_correct`` is the same judgement re-derived from
    ``task_success_factor`` and is the fallback for turns that record no
    ``correct`` key (FORFEIT rounds, external benchmarks).
    """
    metadata = turn.task_metadata or {}
    if "correct" in metadata:
        return metadata["correct"]
    value = _clean(record.get("action_correct"))
    return None if value is None else bool(value)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _fmt(value: float | None, places: int = 2) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def _summary(ledger: list[dict]) -> str:
    """The three per-cell tables."""
    by_cell: dict[object, list[dict]] = defaultdict(list)
    for row in ledger:
        by_cell[row["cell_id"]].append(row)
    cells = sorted(by_cell, key=lambda c: (c is None, c))

    lines: list[str] = []
    add = lines.append
    add("# subagent-kill ledger")
    add("")
    add(f"{len(ledger)} rounds over {len({r['session_id'] for r in ledger})} sessions.")
    add("")

    add("## kills per session")
    add("")
    add("| cell | sessions | rounds | kills | kills per session | slots at round 1 |")
    add("|---|---|---|---|---|---|")
    for cell in cells:
        rows = by_cell[cell]
        sessions = {r["session_id"] for r in rows}
        kills = sum(1 for r in rows if r["subagent_killed"])
        opening = [
            r["subagents_alive_before"]
            for r in rows
            if r["turn"] == 1 and r["subagents_alive_before"] is not None
        ]
        add(
            f"| {cell} | {len(sessions)} | {len(rows)} | {kills} "
            f"| {_fmt(kills / len(sessions) if sessions else None)} "
            f"| {_fmt(_mean(opening), 1)} |"
        )
    add("")

    add("## spawns and denials per round")
    add("")
    add("| cell | round | rounds | spawns | denials | spawns per round | denial share |")
    add("|---|---|---|---|---|---|---|")
    for cell in cells:
        rows = by_cell[cell]
        for turn in sorted({r["turn"] for r in rows}):
            at_turn = [r for r in rows if r["turn"] == turn]
            spawns = sum(int(r["n_spawns"] or 0) for r in at_turn)
            denied = sum(int(r["n_denied_spawns"] or 0) for r in at_turn)
            attempts = spawns + denied
            add(
                f"| {cell} | {turn} | {len(at_turn)} | {spawns} | {denied} "
                f"| {_fmt(spawns / len(at_turn))} "
                f"| {_fmt(denied / attempts if attempts else None)} |"
            )
    add("")

    add("## accuracy by whether the round was solvable with the alive slots")
    add("")
    add("A `solvable` of `False` means the surviving roster could not reach")
    add("every clue the round needed: those rounds are unanswerable by")
    add("construction and must not be pooled with the reachable ones.")
    add("")
    add("| cell | solvable | rounds | correct | accuracy |")
    add("|---|---|---|---|---|")
    for cell in cells:
        rows = by_cell[cell]
        for solvable in (True, False, None):
            at = [r for r in rows if r["solvable_with_alive_slots"] is solvable]
            if not at:
                continue
            graded = [r for r in at if r["correct"] is not None]
            correct = sum(1 for r in graded if r["correct"])
            add(
                f"| {cell} | {solvable} | {len(at)} | {correct} "
                f"| {_fmt(correct / len(graded) if graded else None)} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    ledger: list[dict] = []
    cots: list[dict] = []
    for run_dir in args.run_dirs:
        run_rows, cot_rows = _rows(run_dir)
        ledger.extend(run_rows)
        cots.extend(cot_rows)

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ledger, columns=list(LEDGER_COLUMNS)).to_csv(
        args.out / "ledger.csv", index=False
    )
    summary = _summary(ledger)
    (args.out / "summary.md").write_text(summary, encoding="utf-8")
    with (args.out / "cot_mentions.jsonl").open("w", encoding="utf-8") as fp:
        for row in cots:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(summary)
    print(
        f"wrote {args.out}/ledger.csv ({len(ledger)} rounds), summary.md and "
        f"cot_mentions.jsonl ({len(cots)} CoTs naming a slot)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
