"""The ladder bands come from the generator, not from a guess (spec §6)."""

from __future__ import annotations

from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from scripts.dev.calibrate_signal_puzzle_ladder import main, run_calibration


def test_run_calibration_reports_quantiles_per_tier() -> None:
    cfg = load_signal_puzzle_config()
    stats = run_calibration(cfg, seeds=6, turns_per_tier=2)
    assert sorted(stats) == [1, 2, 3, 4, 5]
    for tier_stats in stats.values():
        assert tier_stats["n"] == 12
        assert 1 <= tier_stats["p10"] <= tier_stats["p50"] <= tier_stats["p90"] <= tier_stats["max"]


def test_repo_ladder_medians_are_monotone_non_decreasing() -> None:
    """Spec §6: adjacent tiers must not get easier by the |H| index."""
    cfg = load_signal_puzzle_config()
    stats = run_calibration(cfg, seeds=25, turns_per_tier=4)
    medians = [stats[t]["p50"] for t in sorted(stats)]
    assert medians == sorted(medians), medians


def test_repo_bands_contain_the_generator_median() -> None:
    """The committed h_lo/h_hi must contain the empirical median.

    A 100-sample subset's 10/90 quantiles can sit just outside the
    200-sample band the script wrote, so the median is the stable check.
    """
    cfg = load_signal_puzzle_config()
    stats = run_calibration(cfg, seeds=25, turns_per_tier=4)
    for step in cfg.puzzle_ladder:
        s = stats[step.tier]
        assert step.h_lo <= s["p50"] <= step.h_hi, (step.tier, step.h_lo, step.h_hi, s)


def test_main_prints_yaml_snippet(capsys) -> None:
    assert main(["--seeds", "3", "--turns-per-tier", "1"]) == 0
    out = capsys.readouterr().out
    assert "puzzle_ladder:" in out
    assert "tier: 5" in out
