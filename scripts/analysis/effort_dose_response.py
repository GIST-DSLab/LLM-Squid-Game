"""Effort dose-response: does thinking more actually make the model right?

Spec: docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md §10

    uv run python -m scripts.analysis.effort_dose_response \
        outputs/2026-XX-XX/signal_effort_pilot_a_gptoss120b/<run> --out results/effort

Reads the runs' *_turns.jsonl directly (the shared loader does not export the
2026-09-10 task_metadata columns) and reports the six acceptance gates. The
headline is gate 1: acc(high) - acc(low) >= 0.20 on ITEM-PAIRED data, because
item difficulty dominates sampling noise in this task (recorded per-item
accuracies cluster at 0 and 1).

How a turn is tagged with its cell's ``reasoning_effort``
--------------------------------------------------------
Through ``cell_id``, in two hops. A turn row carries ``season_id`` and no
cell id; ``season_results.jsonl`` carries ``season_id`` and ``cell_id`` but
**not** the provider config (checked against recorded runs, 2026-09-10); the
run's ``experiment_config.json`` carries ``cell_id`` and
``provider_config.reasoning_effort``. The pilot configs therefore give their
three cells distinct ``cell_id`` values, which is also what keeps ``--resume``
from collapsing them (they share framing, forfeit_condition, social_context
and seed). A run that records none of this reports ``unknown`` rather than
guessing, and every gate then reads NaN.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import sys
from pathlib import Path

EFFORT_ORDER = ("low", "medium", "high")

GATES = {
    "effort_gain": 0.20,
    "acc_floor": 0.10,
    "acc_ceiling": 0.90,
    "item_non_determinism": 0.50,
    "shallow_solvers": 0.35,
}


def load_turns(run_dirs: list[Path]) -> list[dict]:
    """Every turn row of every run, tagged with its cell's reasoning_effort."""
    rows: list[dict] = []
    for run_dir in run_dirs:
        efforts = _efforts_by_season(run_dir)
        for path in sorted(run_dir.glob("*_turns.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["effort"] = efforts.get(row.get("season_id"), "unknown")
                rows.append(row)
    return rows


def _effort_by_cell(run_dir: Path) -> dict:
    """cell_id -> reasoning_effort, from the run's own experiment_config.json."""
    config = run_dir / "experiment_config.json"
    if not config.is_file():
        return {}
    raw = json.loads(config.read_text(encoding="utf-8"))
    out = {}
    for season in raw.get("seasons", []):
        effort = (season.get("provider_config") or {}).get("reasoning_effort")
        if effort is not None:
            out[season.get("cell_id")] = effort
    return out


def _efforts_by_season(run_dir: Path) -> dict[str, str]:
    """season_id -> reasoning_effort, joined through ``cell_id``.

    Falls back to an empty map when the run records neither half; every gate
    then reports ``unknown`` rather than guessing.
    """
    by_cell = _effort_by_cell(run_dir)
    out: dict[str, str] = {}
    seasons = run_dir / "season_results.jsonl"
    if not by_cell or not seasons.is_file():
        return out
    for line in seasons.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        effort = by_cell.get(rec.get("cell_id"))
        if rec.get("season_id") and effort:
            out[rec["season_id"]] = effort
    return out


def _accuracy(rows) -> float:
    rows = list(rows)
    if not rows:
        return float("nan")
    return sum(bool(r["task_metadata"].get("correct")) for r in rows) / len(rows)


def _paired_accuracy(rows: list[dict], a: str, b: str) -> tuple[float, float, int]:
    """Accuracy of the two efforts restricted to items BOTH of them played."""
    by_effort: dict[str, dict[str, list[dict]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for r in rows:
        pid = r["task_metadata"].get("puzzle_id")
        if pid:
            by_effort[r["effort"]][pid].append(r)
    shared = set(by_effort[a]) & set(by_effort[b])
    if not shared:
        return float("nan"), float("nan"), 0
    acc_a = _accuracy(x for pid in shared for x in by_effort[a][pid])
    acc_b = _accuracy(x for pid in shared for x in by_effort[b][pid])
    return acc_a, acc_b, len(shared)


def _passed(value: bool) -> bool:
    """A NaN comparison is False, and that is the honest verdict here."""
    return bool(value)


def evaluate_gates(rows: list[dict]) -> dict[str, dict]:
    """The six acceptance criteria, each with its measured value and verdict."""
    out: dict[str, dict] = {}

    acc_low, acc_high, n_items = _paired_accuracy(rows, "low", "high")
    gain = acc_high - acc_low
    out["effort_gain"] = {
        "value": gain,
        "n_items": n_items,
        "acc_low": acc_low,
        "acc_high": acc_high,
        "threshold": GATES["effort_gain"],
        "passed": _passed(gain >= GATES["effort_gain"]),
    }
    out["no_floor_or_ceiling"] = {
        "acc_low": acc_low,
        "acc_high": acc_high,
        "passed": _passed(
            acc_low >= GATES["acc_floor"] and acc_high <= GATES["acc_ceiling"]
        ),
    }

    medium = [r for r in rows if r["effort"] == "medium"]
    per_item: dict[str, list[dict]] = collections.defaultdict(list)
    for r in medium:
        per_item[r["task_metadata"].get("puzzle_id", "")].append(r)
    informative = [
        pid for pid, rs in per_item.items() if pid and 0.2 <= _accuracy(rs) <= 0.8
    ]
    share = len(informative) / len(per_item) if per_item else float("nan")
    out["item_non_determinism"] = {
        "value": share,
        "n_items": len(per_item),
        "threshold": GATES["item_non_determinism"],
        "passed": _passed(share >= GATES["item_non_determinism"]),
    }

    solved_by_shallow = sum(
        bool(r["task_metadata"].get("shallow_solvers_correct")) for r in rows
    )
    shallow_rate = solved_by_shallow / len(rows) if rows else float("nan")
    out["shallow_solvers"] = {
        "value": shallow_rate,
        "threshold": GATES["shallow_solvers"],
        "passed": _passed(shallow_rate <= GATES["shallow_solvers"]),
    }

    # Gate 5: within medium, does CoT length predict correctness once the item
    # is held fixed? Recorded runs put this NEGATIVE, which is why it is a
    # gate. Item-fixed = compare each row's CoT length against the median of
    # its own item, then check the correct rows sit above the wrong ones.
    deltas_correct: list[float] = []
    deltas_wrong: list[float] = []
    for pid, rs in per_item.items():
        if len(rs) < 2:
            continue
        lengths = [len((r.get("thinking_text_task") or "").split()) for r in rs]
        med = statistics.median(lengths)
        for r, length in zip(rs, lengths, strict=True):
            (
                deltas_correct if r["task_metadata"].get("correct") else deltas_wrong
            ).append(length - med)
    if deltas_correct and deltas_wrong:
        effect = statistics.mean(deltas_correct) - statistics.mean(deltas_wrong)
    else:
        effect = float("nan")
    out["cot_predicts_correct"] = {
        "value": effect,
        "passed": _passed(effect > 0),
        "n_correct": len(deltas_correct),
        "n_wrong": len(deltas_wrong),
    }

    medians = {}
    for effort in EFFORT_ORDER:
        vals = [r.get("ri_task") or 0 for r in rows if r["effort"] == effort]
        medians[effort] = statistics.median(vals) if vals else float("nan")
    ordered = (
        not any(math.isnan(v) for v in medians.values())
        and medians["high"] > medians["medium"] > medians["low"]
    )
    out["effort_moves_tokens"] = {
        "medians": medians,
        "passed": _passed(ordered),
    }
    return out


def _profile_table(rows: list[dict]) -> list[dict]:
    by: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in rows:
        by[(r["task_metadata"].get("difficulty_profile") or "?", r["effort"])].append(r)
    return [
        {
            "profile": profile,
            "effort": effort,
            "n": len(rs),
            "accuracy": _accuracy(rs),
            "action_accuracy": sum(
                bool(x["task_metadata"].get("action_correct")) for x in rs
            )
            / len(rs),
            "median_ri_task": statistics.median([x.get("ri_task") or 0 for x in rs]),
        }
        for (profile, effort), rs in sorted(by.items())
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--calibration-seeds",
        default="",
        help="seeds used to TUNE the profiles; reported, never pooled with the holdout",
    )
    ap.add_argument(
        "--holdout-seeds",
        default="",
        help="seeds reserved for the reported result",
    )
    args = ap.parse_args(argv)

    rows = load_turns(args.runs)
    if not rows:
        print("no turn rows found")
        return 1
    unknown = sum(1 for r in rows if r["effort"] == "unknown")
    if unknown:
        print(
            f"warning: {unknown}/{len(rows)} turns have no reasoning_effort "
            "(the run records no experiment_config.json / season_results.jsonl "
            "join); their gates read NaN."
        )
    gates = evaluate_gates(rows)
    table = _profile_table(rows)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "gates.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
    (args.out / "profile_table.json").write_text(
        json.dumps(table, indent=2), encoding="utf-8"
    )

    lines = ["# Effort dose-response", "", "## Acceptance gates", ""]
    lines.append("| gate | value | passed |")
    lines.append("|---|---|:-:|")
    for name, payload in gates.items():
        value = payload.get("value", payload.get("medians", ""))
        lines.append(f"| {name} | {value} | {'PASS' if payload['passed'] else 'FAIL'} |")
    lines += [
        "",
        "## Per profile x effort",
        "",
        "| profile | effort | n | accuracy | action accuracy | median ri_task |",
        "|---|---|--:|--:|--:|--:|",
    ]
    for r in table:
        lines.append(
            f"| {r['profile']} | {r['effort']} | {r['n']} | {r['accuracy']:.2f} | "
            f"{r['action_accuracy']:.2f} | {r['median_ri_task']:.0f} |"
        )
    if args.calibration_seeds or args.holdout_seeds:
        lines += [
            "",
            "## Seed split",
            f"- calibration: {args.calibration_seeds or '(none stated)'}",
            f"- holdout: {args.holdout_seeds or '(none stated)'}",
            "",
            "Profiles tuned on the calibration seeds must be reported on "
            "the holdout seeds; pooling them reports the tuning.",
        ]
    (args.out / "effort_dose_response.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    return 0 if all(g["passed"] for g in gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
