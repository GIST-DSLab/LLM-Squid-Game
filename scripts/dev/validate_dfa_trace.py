"""Generator-only validation for the dfa_trace ladder. No LLM calls.

Brief: docs/history/plans/2026-09-17-team-wallet-task-candidates.md §3.2

    uv run python -m scripts.dev.validate_dfa_trace --seeds 200
    uv run python -m scripts.dev.validate_dfa_trace \
        --preflight configs/experiment/<some_dfa_run>.yaml

Invariants abort immediately (a violated one means the generator is
wrong). Gates are the shipped thresholds; any failure exits 1 so this can
gate a run.

WHAT D5 IS FOR
    ``prefix_k`` is literally "take the first k of the L steps and stop",
    so its accuracy as a function of k IS the effort-accuracy curve, drawn
    with no model in the loop. That is the whole reason candidate C exists
    (§2 C, "이 문서의 어떤 후보도 이만큼 직접적이지 않다"), and D5 is the
    assertion that the curve is really there.

    D5 and D6 are measured on PLAIN draws -- same rung, trap filter off.
    On a trap instance every shallow solver is wrong by construction, so
    its curve is 0, 0, ..., 0, 1 whatever the machine looks like: it would
    pass the gate while saying nothing. The plain draw is the honest
    statement about the rung.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time
from pathlib import Path

from squid_game.tasks.dfa_trace.generator import (
    DfaSpec,
    dfa_rng,
    generate_dfa,
    generate_trap_dfa,
    is_trap,
    prefix_ks,
    shallow_answers,
    shallow_prefix_k,
    shallow_solver_names,
)
from squid_game.tasks.dfa_trace.module import (
    DfaLadderStep,
    load_dfa_trace_config,
)

#: Shipped thresholds (§3.2). Fixed before the real run; do not tune them
#: to make a rung pass.
GATES = {
    "D1_trap_yield": 0.20,
    "D2_answer_balance": 0.40,
    "D3_length_leak": 0.0,
    "D4_generation_time": 1.0,
    "D5_effort_curve": 0.05,
    "D6_ladder_rises": 0.05,
}

#: D5 and D6 compare proportions estimated from ``--seeds`` draws. At the
#: default n = 200 one standard error is about 0.035, so a strictly
#: monotone requirement would fail on noise alone roughly half the time.
#: Both gates therefore allow a dip of this much (the values above), which
#: is a hair under two standard errors. Raising ``--seeds`` shrinks the
#: noise; do not raise the tolerance instead.
_TOLERANCE_NOTE = "dips up to the gate value are read as sampling noise"


def _plain(step: DfaLadderStep) -> DfaSpec:
    """The rung with the trap filter off — the D5 / D6 measurement draw."""
    return DfaSpec(
        states=step.states,
        alphabet=step.alphabet,
        length=step.length,
        question=step.question,
        trap=False,
        turn=step.round,
        profile=step.profile,
    )


def _assert_invariants(dfa, trap_expected: bool) -> None:
    spec = dfa.spec
    assert len(dfa.word) == spec.length, "input string is not L symbols long"
    assert set(dfa.word) <= set(spec.symbols), "input uses an off-alphabet symbol"
    assert len(dfa.transitions) == spec.states, "transition table is the wrong height"
    assert all(
        len(row) == spec.alphabet for row in dfa.transitions
    ), "a transition row is missing a symbol"
    assert all(
        0 <= target < spec.states for row in dfa.transitions for target in row
    ), "a transition leaves the state set"
    # Determinism is checked by the caller, which re-draws with the real
    # seed and compares the whole instance (invariant I1).
    if trap_expected:
        assert is_trap(dfa), "a trap rung produced a solvable instance"
        hits = [
            name
            for name, answer in shallow_answers(dfa).items()
            if answer == dfa.answer
        ]
        assert hits == [], f"trap instance solved by {hits}"



def rung_report(step: DfaLadderStep, seeds, attempts: int) -> dict:
    """Measure one rung over *seeds*. Raises on any invariant violation."""
    seeds = list(seeds)
    n = len(seeds)
    spec = step.to_spec(turn=step.round)
    plain_spec = _plain(step)
    curve_ks = list(prefix_ks(step.length)) + [step.length]

    times: list[float] = []
    answers: collections.Counter = collections.Counter()
    trap_attempts: list[int] = []
    lengths_trap: list[int] = []
    lengths_plain: list[int] = []
    plain_hits: collections.Counter = collections.Counter()
    curve_hits: collections.Counter = collections.Counter()

    for seed in seeds:
        t0 = time.perf_counter()
        dfa = generate_trap_dfa(dfa_rng(seed, step.round), spec, attempts=attempts)
        times.append(time.perf_counter() - t0)
        _assert_invariants(dfa, trap_expected=True)
        # Determinism (invariant I1): the same (seed, round, spec) must
        # reproduce the same instance, or nothing downstream is replayable.
        again = generate_trap_dfa(
            dfa_rng(seed, step.round), spec, attempts=attempts
        )
        assert again == dfa, f"seed {seed}: generation is not deterministic"
        answers[dfa.answer] += 1
        trap_attempts.append(max(1, dfa.trap_attempts))
        lengths_trap.append(len(dfa.word))

        plain = generate_dfa(dfa_rng(seed, step.round), plain_spec)
        _assert_invariants(plain, trap_expected=False)
        lengths_plain.append(len(plain.word))
        truth = plain.answer
        for name, answer in shallow_answers(plain).items():
            if answer == truth:
                plain_hits[name] += 1
        for k in curve_ks:
            if shallow_prefix_k(plain, k) == truth:
                curve_hits[k] += 1

    names = shallow_solver_names(spec)
    return {
        "profile": step.profile,
        "round": step.round,
        "n": n,
        "states": step.states,
        "alphabet": step.alphabet,
        "length": step.length,
        "question": step.question,
        "trap": step.trap,
        "trap_yield": sum(1.0 / a for a in trap_attempts) / n,
        "mean_trap_attempts": statistics.mean(trap_attempts),
        "max_answer_share": max(answers.values()) / n,
        "answer_counts": dict(answers),
        # Length is fixed by the rung, so this is 0 by construction; the
        # gate is a regression guard. If it ever moved, a trap round would
        # be identifiable from the prompt without solving it.
        "length_median_trap": statistics.median(lengths_trap),
        "length_median_plain": statistics.median(lengths_plain),
        "p95_seconds": sorted(times)[min(n - 1, int(0.95 * n))],
        "mean_seconds": statistics.mean(times),
        # Measured on the PLAIN draw -- see the module docstring.
        "shallow_accuracy": {name: plain_hits[name] / n for name in names},
        "mean_shallow_accuracy": (
            sum(plain_hits[name] for name in names) / (n * len(names))
        ),
        "prefix_curve": {str(k): curve_hits[k] / n for k in curve_ks},
    }


def check_gates(report: dict) -> list[str]:
    """Names of the per-rung gates this report fails. Empty == pass."""
    failed: list[str] = []
    if report["trap"] and report["trap_yield"] < GATES["D1_trap_yield"]:
        failed.append("D1_trap_yield")
    if report["question"] == "final":
        if report["max_answer_share"] > GATES["D2_answer_balance"]:
            failed.append("D2_answer_balance")
    leak = abs(report["length_median_trap"] - report["length_median_plain"])
    if leak > GATES["D3_length_leak"]:
        failed.append("D3_length_leak")
    if report["p95_seconds"] > GATES["D4_generation_time"]:
        failed.append("D4_generation_time")
    curve = [report["prefix_curve"][k] for k in sorted(report["prefix_curve"], key=int)]
    rising = all(
        b >= a - GATES["D5_effort_curve"] for a, b in zip(curve[:-1], curve[1:], strict=True)
    )
    if not rising or curve[-1] != 1.0:
        failed.append("D5_effort_curve")
    return failed


def check_ladder_gate(reports: list[dict]) -> list[str]:
    """D6, which is a statement about the ladder, not about one rung.

    Checked WITHIN a question kind. ``final`` and ``count`` have very
    different shallow baselines (a random 4-state guess is 0.25; a count
    over 11 possible values is far less), so pooling them would read the
    alternation as a ladder that goes up and down.
    """
    failures: list[str] = []
    for kind in ("final", "count"):
        series = [
            (r["round"], r["mean_shallow_accuracy"])
            for r in sorted(reports, key=lambda r: r["round"])
            if r["question"] == kind
        ]
        for (r1, a), (r2, b) in zip(series[:-1], series[1:], strict=True):
            if b > a + GATES["D6_ladder_rises"]:
                failures.append(
                    f"D6_ladder_rises[{kind}] round {r1}->{r2}: {a:.2f} -> {b:.2f}"
                )
    return failures


def _preflight(config_path: Path) -> int:
    """Generate every (seed, round) a config will actually play.

    A run must never discover a generation failure at round 5. The seed
    walk mirrors ``runner._run_single_season``, which hands repetition *r*
    the seed ``task_config.seed + r``; repetitions are 1-based.
    """
    import yaml

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cfg = load_dfa_trace_config()
    reps = int(raw.get("num_repetitions", 1))
    failures = 0
    generated = 0
    for season in raw.get("seasons", []):
        task = season.get("task_config", {})
        if task.get("task_name") != "dfa_trace":
            continue
        base_seed = int(task.get("seed", 0))
        total_turns = int(task.get("total_turns", cfg.total_turns))
        for r in range(1, reps + 1):
            for turn in range(1, total_turns + 1):
                spec = cfg.spec_for_turn(turn)
                try:
                    if spec.trap:
                        generate_trap_dfa(dfa_rng(base_seed + r, turn), spec)
                    else:
                        generate_dfa(dfa_rng(base_seed + r, turn), spec)
                    generated += 1
                except Exception as exc:  # noqa: BLE001 - report and continue
                    failures += 1
                    print(f"FAIL seed={base_seed + r} round={turn}: {exc}")
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
            "how many seeds per rung (§3.2 uses 200). D2 / D5 / D6 are "
            "proportion estimates, so a small sample can fail a gate on "
            "noise alone. Do not lower this to make a run cheaper."
        ),
    )
    ap.add_argument("--seed-base", type=int, default=9000)
    ap.add_argument(
        "--attempts",
        type=int,
        default=200,
        help="rejection budget per instance; exceeding it raises, never falls back",
    )
    ap.add_argument("--out", type=Path, default=None, help="write reports as JSON here")
    ap.add_argument(
        "--preflight",
        type=Path,
        default=None,
        help="generate every (seed, round) an experiment YAML will play",
    )
    args = ap.parse_args(argv)

    if args.preflight is not None:
        return _preflight(args.preflight)

    cfg = load_dfa_trace_config()
    wanted = [p for p in (args.profiles.split(",") if args.profiles else None) or []]
    steps = [s for s in cfg.ladder if not wanted or s.profile in wanted]
    if not steps:
        print(f"no such profile in configs/tasks/dfa_trace.yaml: {args.profiles}")
        return 1

    reports = []
    failed_any = False
    for step in steps:
        rep = rung_report(
            step,
            range(args.seed_base, args.seed_base + args.seeds),
            attempts=args.attempts,
        )
        failed = check_gates(rep)
        rep["failed_gates"] = failed
        failed_any = failed_any or bool(failed)
        reports.append(rep)
        curve = " ".join(
            f"k{k}={rep['prefix_curve'][k]:.2f}"
            for k in sorted(rep["prefix_curve"], key=int)
        )
        print(
            f"{step.profile:8s} r{rep['round']} L={rep['length']:2d} "
            f"s={rep['states']} a={rep['alphabet']} {rep['question']:5s} "
            f"n={rep['n']:4d} yield={rep['trap_yield']:.2f} "
            f"p95={rep['p95_seconds']:.3f}s "
            f"answer_max={rep['max_answer_share']:.2f} "
            f"len={rep['length_median_trap']:.0f}/{rep['length_median_plain']:.0f} "
            f"shallow={rep['mean_shallow_accuracy']:.2f} | {curve} | "
            f"{'FAIL ' + ','.join(failed) if failed else 'ok'}"
        )

    ladder_failures = check_ladder_gate(reports) if len(steps) == len(cfg.ladder) else []
    if ladder_failures:
        failed_any = True
        for line in ladder_failures:
            print(f"FAIL {line}")
    elif len(steps) == len(cfg.ladder):
        print("D6_ladder_rises ok (within each question kind)")
    print(f"note: D5 / D6 {_TOLERANCE_NOTE}")

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "rung_reports.json").write_text(
            json.dumps(reports, indent=2), encoding="utf-8"
        )
    return 1 if failed_any else 0


if __name__ == "__main__":
    sys.exit(main())
