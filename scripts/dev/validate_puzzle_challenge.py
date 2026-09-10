"""Generator-only validation for the puzzle_challenge profiles. No LLM calls.

Spec: docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md §9

    uv run python -m scripts.dev.validate_puzzle_challenge --seeds 200
    uv run python -m scripts.dev.validate_puzzle_challenge \
        --preflight configs/experiment/signal_effort_pilot_a_gptoss120b.yaml

Invariants abort immediately (a violated one means the generator is wrong).
Gates are the shipped thresholds; any failure exits 1 so this can gate a run.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import sys
import time
from pathlib import Path

from squid_game.tasks.signal_game.puzzle import (
    SHALLOW_SOLVER_NAMES,
    generate_puzzle,
    generate_trap_puzzle,
    is_trap_query,
    is_unique,
    puzzle_rng,
    shallow_actions,
    shape_label,
)
from squid_game.tasks.signal_game.puzzle_config import (
    PuzzleProfile,
    load_signal_puzzle_config,
)

#: Shipped thresholds (spec §9). Fixed before the real run; do not tune them
#: to make a profile pass.
GATES = {
    "G1_trap_yield": 0.05,
    "G2_answer_balance": 0.50,
    "G3_clue_count_leak": 2.0,
    "G4_generation_time": 10.0,
    "G5_easy_is_shallow": 0.80,
    "G6_shape_diversity": 0.60,
}


def _generate(profile: PuzzleProfile, name: str, seed: int, turn: int):
    spec = profile.to_spec(turn=turn, name=name)
    rng = puzzle_rng(seed, turn)
    if spec.trap_query:
        return generate_trap_puzzle(rng, spec)
    return generate_puzzle(rng, spec)


def _assert_invariants(puzzle, trap_expected: bool) -> None:
    assert all(
        puzzle.rule.evaluate(c.signal) == c.action for c in puzzle.clues
    ), "a shown clue contradicts the rule"
    assert is_unique(
        puzzle.shape, puzzle.clues, puzzle.rule
    ), "the clue set does not pin the rule"
    assert all(
        c.signal != puzzle.query for c in puzzle.clues
    ), "the query appears among the clues"
    if trap_expected:
        assert is_trap_query(puzzle), "a trap profile produced a non-trap query"
        hits = [
            n
            for n, a in shallow_actions(puzzle).items()
            if a == puzzle.correct_action
        ]
        assert hits == [], f"trap puzzle solved by {hits}"


def profile_report(name: str, profile: PuzzleProfile, seeds, turn: int) -> dict:
    """Measure one profile over *seeds*. Raises on any invariant violation."""
    seeds = list(seeds)
    times: list[float] = []
    answers: collections.Counter = collections.Counter()
    shapes: collections.Counter = collections.Counter()
    clue_counts: list[int] = []
    plain_clue_counts: list[int] = []
    attempts: list[int] = []
    solver_hits: collections.Counter = collections.Counter()

    for seed in seeds:
        t0 = time.perf_counter()
        puzzle = _generate(profile, name, seed, turn)
        times.append(time.perf_counter() - t0)
        _assert_invariants(puzzle, profile.trap_query)
        answers[puzzle.correct_action] += 1
        shapes[shape_label(puzzle.shape)] += 1
        clue_counts.append(len(puzzle.clues))
        attempts.append(max(1, puzzle.trap_attempts))
        for solver, action in shallow_actions(puzzle).items():
            if action == puzzle.correct_action:
                solver_hits[solver] += 1
        if profile.trap_query:
            # The non-trap twin: same shape, trap filter off. Its clue count
            # is the leak baseline (G3) -- a trap round must not be
            # identifiable by counting examples.
            plain = _generate(
                profile.model_copy(update={"trap_query": False}), name, seed, turn
            )
            plain_clue_counts.append(len(plain.clues))

    n = len(seeds)
    return {
        "name": name,
        "n": n,
        "turn": turn,
        "clauses": profile.clauses,
        "trap_query": profile.trap_query,
        "trap_yield": (
            (sum(1.0 / a for a in attempts) / n) if profile.trap_query else 1.0
        ),
        "mean_trap_attempts": statistics.mean(attempts),
        "shallow_accuracy": {s: solver_hits[s] / n for s in SHALLOW_SOLVER_NAMES},
        "max_answer_share": max(answers.values()) / n,
        "answer_counts": dict(answers),
        "max_shape_share": max(shapes.values()) / n,
        # How many shapes ``draw_shape`` can even produce for this profile:
        # ``conjunctions`` of the ``clauses`` positions are arity 2, chosen at
        # random, so it is C(clauses, conjunctions). G6 asks whether the trap
        # filter biased the shape, which is only a question where more than
        # one shape exists -- at 1 clause / 0 conjunctions (``easy``) or
        # 3 / 0 (``medium``) the single possible shape holds 100% share by
        # construction and no generator could do otherwise.
        "n_possible_shapes": math.comb(profile.clauses, profile.conjunctions),
        "clue_count_median": statistics.median(clue_counts),
        "clue_count_median_plain": (
            statistics.median(plain_clue_counts)
            if plain_clue_counts
            else statistics.median(clue_counts)
        ),
        "p95_seconds": sorted(times)[min(n - 1, int(0.95 * n))],
        "mean_seconds": statistics.mean(times),
    }


def check_gates(report: dict) -> list[str]:
    """Names of the gates this report fails (spec §9). Empty == pass."""
    failed: list[str] = []
    if report["trap_query"] and report["trap_yield"] < GATES["G1_trap_yield"]:
        failed.append("G1_trap_yield")
    if report["max_answer_share"] > GATES["G2_answer_balance"]:
        failed.append("G2_answer_balance")
    leak = abs(report["clue_count_median"] - report["clue_count_median_plain"])
    if leak > GATES["G3_clue_count_leak"]:
        failed.append("G3_clue_count_leak")
    if report["p95_seconds"] > GATES["G4_generation_time"]:
        failed.append("G4_generation_time")
    if (not report["trap_query"]) and report["clauses"] == 1:
        if report["shallow_accuracy"].get("nn", 0.0) < GATES["G5_easy_is_shallow"]:
            failed.append("G5_easy_is_shallow")
    # G6 only asks a question where the profile's shape can vary; see
    # ``n_possible_shapes`` above. Reports written before that key existed
    # fall back to applying the gate.
    if report.get("n_possible_shapes", 2) > 1:
        if report["max_shape_share"] > GATES["G6_shape_diversity"]:
            failed.append("G6_shape_diversity")
    return failed


def _preflight(config_path: Path) -> int:
    """Generate every (seed, turn) a config will actually play.

    A run must never discover a generation failure at round 5. Reads the
    experiment YAML, walks seasons x repetitions x schedule, and generates.

    The seed walk mirrors ``runner._run_single_season``, which hands
    repetition *r* the seed ``task_config.seed + r``.
    """
    import yaml

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profiles = load_signal_puzzle_config().puzzle_profiles or {}
    reps = int(raw.get("num_repetitions", 1))
    failures = 0
    generated = 0
    for season in raw.get("seasons", []):
        task = season.get("task_config", {})
        challenge = task.get("puzzle_challenge") or {}
        if not challenge.get("enabled"):
            continue
        base_seed = int(task["seed"])
        for r in range(reps):
            for entry in challenge["schedule"]:
                turn, name = int(entry["turn"]), entry["profile"]
                try:
                    _generate(profiles[name], name, base_seed + r, turn)
                    generated += 1
                except Exception as exc:  # noqa: BLE001 - report and continue
                    failures += 1
                    print(
                        f"FAIL seed={base_seed + r} turn={turn} "
                        f"profile={name}: {exc}"
                    )
    print(f"preflight: {generated} generated, {failures} failures")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profiles", default="", help="comma-separated; default all")
    ap.add_argument(
        "--seeds",
        type=int,
        default=200,
        help=(
            "how many seeds per profile (spec §9 uses 200). G2 / G5 / G6 are "
            "proportion estimates, so a small sample can fail a gate on noise "
            "alone: `easy` sits at nn = 0.83-0.86 against a 0.80 threshold, "
            "and an n = 100 draw of it measured 0.77. Do not lower this to "
            "make a run cheaper."
        ),
    )
    ap.add_argument("--seed-base", type=int, default=9000)
    ap.add_argument("--turn", type=int, default=3, help="turn index used for the RNG")
    ap.add_argument("--out", type=Path, default=None, help="write reports as JSON here")
    ap.add_argument(
        "--preflight",
        type=Path,
        default=None,
        help="generate every (seed, turn) an experiment YAML will play",
    )
    args = ap.parse_args(argv)

    if args.preflight is not None:
        return _preflight(args.preflight)

    profiles = load_signal_puzzle_config().puzzle_profiles
    if not profiles:
        print("configs/tasks/signal_game.yaml has no puzzle_profiles block")
        return 1
    wanted = [p for p in (args.profiles.split(",") if args.profiles else profiles) if p]

    reports = []
    failed_any = False
    for name in wanted:
        rep = profile_report(
            name,
            profiles[name],
            range(args.seed_base, args.seed_base + args.seeds),
            args.turn,
        )
        failed = check_gates(rep)
        rep["failed_gates"] = failed
        failed_any = failed_any or bool(failed)
        reports.append(rep)
        shallow = " ".join(
            f"{s}={rep['shallow_accuracy'][s]:.2f}" for s in SHALLOW_SOLVER_NAMES
        )
        print(
            f"{name:8s} n={rep['n']:4d} trap={rep['trap_query']!s:5s} "
            f"yield={rep['trap_yield']:.2f} p95={rep['p95_seconds']:.2f}s "
            f"answer_max={rep['max_answer_share']:.2f} "
            f"shape_max={rep['max_shape_share']:.2f} "
            f"clues={rep['clue_count_median']:.0f}/{rep['clue_count_median_plain']:.0f} "
            f"| {shallow} | {'FAIL ' + ','.join(failed) if failed else 'ok'}"
        )

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "profile_reports.json").write_text(
            json.dumps(reports, indent=2), encoding="utf-8"
        )
    return 1 if failed_any else 0


if __name__ == "__main__":
    sys.exit(main())
