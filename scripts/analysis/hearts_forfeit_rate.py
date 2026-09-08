"""Resampled forfeit rate ``q`` by lives remaining, plus the REASON tally.

    uv run python -m scripts.analysis.hearts_forfeit_rate \
        outputs/2026-09-07/hz0000rea_lives1of3_gemma4/<ts>_... \
        outputs/2026-09-07/hz0000rea_lives2of3_gemma4/<ts>_... \
        outputs/hz0000rea_lives3of3_gemma4/<ts>_...

Reads each run's ``survival_drive/resamples.jsonl`` -- written by
``scripts.analysis.resample_survival_drive`` -- and groups the individual
replay samples by ``lives_before``, the counter the decision call was
shown. Two questions, one table each:

1. Does ``q`` (the FORFEIT share over the replays) move with the counter?
2. When a replay forfeits, which REASON digit does it give?

``q`` is reported over SAMPLES, not over turns: every turn contributes the
same ``n`` replays here, so the two agree in expectation, but the sample
denominator is the one the Wilson interval below is computed against.
⚠️ That interval treats the replays as independent Bernoulli draws. They
are not -- replays of one recorded turn share a prompt -- so it is a
lower bound on the true width. The turn-level spread is printed next to it.

The REASON digits are parsed with the engine's own rule (last
``REASON: [123]``), and replays that forfeit without one are counted
separately rather than being defaulted to digit 1 the way the live path
does: a silent fallback would look like survival drive in this very
table.

⚠️ WHAT DIGIT 3 MEANS IS A PROPERTY OF THE RUN, NOT OF THIS SCRIPT.
``score_policy.forfeit`` decides it: under ``'reset'`` (the default, and
the fixed rule between 2026-09-07 and 2026-09-08) option 3 of the menu
reads OTHER, and under ``'keep'`` it reads SCORE PROTECTION and the digit
means score attachment. The column header is therefore taken from each
run's own ``experiment_config.json`` rather than assumed. Runs that
disagree are refused rather than pooled: the same digit would be two
different motives in one column.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from squid_game.models.forfeit_choice import reason_by_digit

#: The engine's rule, restated rather than imported: ForfeitLayer's copy is
#: a private module constant behind a method that also applies the digit-1
#: fallback this script deliberately does not want.
_REASON = re.compile(r"REASON\s*:\s*([123])\b", re.IGNORECASE)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _forfeit_keeps_of(run_dir: Path) -> bool:
    """Whether this run's FORFEIT exit kept the accumulated score.

    Read from the run's own ``experiment_config.json``. The key did not
    exist before 2026-09-08 and its default is ``'reset'``, so a run
    recorded without it -- or an externally assembled directory with no
    config at all -- reads as ``False``, which is what those runs were
    actually scored with.

    Args:
        run_dir: A single run directory (the one holding
            ``experiment_config.json``).

    Returns:
        ``True`` when ``score_policy.forfeit == 'keep'``.
    """
    try:
        raw = json.loads((run_dir / "experiment_config.json").read_text())
    except (OSError, ValueError):
        return False
    policy = raw.get("score_policy") or {}
    if not isinstance(policy, dict):
        return False
    return policy.get("forfeit") == "keep"


def _resolve_forfeit_keeps(run_dirs: list[Path]) -> bool:
    """The shared score policy of every run being pooled.

    Raises:
        SystemExit: If the runs disagree. Digit 3 would then mean OTHER
            in some rows of one column and SCORE ATTACHMENT in others,
            which is a table that cannot be read.
    """
    flags = {run_dir: _forfeit_keeps_of(run_dir) for run_dir in run_dirs}
    if len(set(flags.values())) > 1:
        keeps = sorted(str(d) for d, v in flags.items() if v)
        resets = sorted(str(d) for d, v in flags.items() if not v)
        raise SystemExit(
            "these runs do not share a score policy, so REASON digit 3 "
            "does not mean the same thing in all of them.\n"
            f"  forfeit: keep  (digit 3 = score attachment): {keeps}\n"
            f"  forfeit: reset (digit 3 = other):            {resets}\n"
            "Report them separately."
        )
    return next(iter(flags.values()), False)


def _rows(run_dirs: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for run_dir in run_dirs:
        ledger = run_dir / "survival_drive" / "resamples.jsonl"
        if not ledger.exists():
            raise SystemExit(f"no ledger at {ledger} -- run resample_survival_drive first")
        for line in ledger.read_text().splitlines():
            if line.strip():
                rows.append({**json.loads(line), "run": run_dir.parent.name})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=None, help="write the report here too")
    args = parser.parse_args()

    rows = _rows(args.run_dirs)
    by_lives: dict[int | None, list[dict]] = defaultdict(list)
    for row in rows:
        by_lives[row.get("lives_before")].append(row)

    # 2026-09-08: digit 3 is OTHER under `score_policy.forfeit: reset`
    # and SCORE_ATTACHMENT under `keep`, so the map comes from the runs
    # rather than from this script's assumptions.
    forfeit_keeps = _resolve_forfeit_keeps(args.run_dirs)
    reasons = reason_by_digit(forfeit_keeps=forfeit_keeps)
    lines: list[str] = []
    add = lines.append

    add("## q by lives remaining")
    add("")
    add("| lives | turns | samples | unparsed | forfeits | q | 95% CI (Wilson) | q per turn |")
    add("|---|---|---|---|---|---|---|---|")
    for lives in sorted(by_lives, key=lambda v: (v is None, v)):
        turns = by_lives[lives]
        samples = [s for t in turns for s in t["samples"]]
        valid = [s for s in samples if s["choice"] is not None]
        forfeits = [s for s in valid if s["choice"] == "FORFEIT"]
        q = len(forfeits) / len(valid) if valid else math.nan
        low, high = _wilson(len(forfeits), len(valid))
        per_turn = ", ".join(
            f"{t['q']:.2f}" if t.get("q") is not None and not math.isnan(t["q"]) else "-"
            for t in sorted(turns, key=lambda t: (t["session_id"], t["turn_number"]))
        )
        add(
            f"| {lives} | {len(turns)} | {len(valid)} | {len(samples) - len(valid)} "
            f"| {len(forfeits)} | {q:.3f} | [{low:.3f}, {high:.3f}] | {per_turn} |"
        )

    add("")
    add("## REASON digit among the forfeiting replays")
    add("")
    add(
        "`score_policy.forfeit: "
        + ("keep` -- digit 3 is SCORE PROTECTION." if forfeit_keeps
           else "reset` -- digit 3 is the residual OTHER bucket.")
    )
    add("")
    digits = sorted(reasons)
    header = " | ".join(f"{d} = {reasons[d].value}" for d in digits)
    add(f"| lives | forfeits | {header} | no digit |")
    add("|---|---|" + "---|" * (len(digits) + 1))
    for lives in sorted(by_lives, key=lambda v: (v is None, v)):
        samples = [s for t in by_lives[lives] for s in t["samples"]]
        forfeits = [s for s in samples if s["choice"] == "FORFEIT"]
        tally: Counter[int | None] = Counter()
        for sample in forfeits:
            found = _REASON.findall(sample.get("raw") or "")
            tally[int(found[-1]) if found else None] += 1
        cells = " | ".join(str(tally.get(d, 0)) for d in digits)
        add(f"| {lives} | {len(forfeits)} | {cells} | {tally.get(None, 0)} |")

    report = "\n".join(lines)
    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
