"""Plot Reasoning Investment (RI) trajectories over turn across 4 completed model runs.

Three plots are generated, each writing a separate PNG:

  1. **Channels**  (``ri_trajectories_channels.png``)
     - Rows: ri_task (Call 1) / ri_probe (Call 1.5) / ri_forfeit (Call 2)
     - Cols: 4 models
     - Lines per framing (true_baseline / baseline_flagship / flagship_corruption)
     - Shaded = 95% CI (±1.96 × SEM per turn × framing)

  2. **Choice-conditional** (``ri_trajectories_choice.png``) — H_choice_asymmetric visualisation
     - Rows: choice ∈ {CONTINUE, FORFEIT}
     - Cols: 4 models
     - y = mean ri_forfeit tokens
     - Restricted to forfeit_allowed cells (otherwise FORFEIT row is empty).

  3. **Regime-stratified** (``ri_trajectories_regime.png``) — Unit 17.10 extension
     - Rows: regime ∈ {no_cap, cap_bound}
     - Cols: 4 models
     - y = mean ri_forfeit tokens
     - Restricted to forfeit_allowed cells.

Usage::

    uv run python scripts/plot_ri_trajectories.py \\
      --run gemini-2.5-flash archive/final_results/20260422_0218_gemini-2.5-flash_signal-game \\
      --run gpt-oss-20b outputs/20260422_0902_gpt-oss-20b-cloud_signal-game \\
      --run nemotron-3-nano-30b outputs/20260422_0902_nemotron-3-nano-30b-cloud_signal-game \\
      --run qwen3-next-80b outputs/20260422_0902_qwen3-next-80b-cloud_signal-game \\
      -o outputs/
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from squid_game.analysis import discover_season_jsonl, load_seasons
from squid_game.analysis.forfeit_regression import turn_observations
from squid_game.analysis.regime_stratification import annotate_regime
from squid_game.models.enums import Framing

logger = logging.getLogger("plot_ri_trajectories")


# Colour palette — Wong 2011 colorblind-safe (shared with plot_kaplan_meier.py).
FRAMING_ORDER: tuple[Framing, ...] = (
    Framing.TRUE_BASELINE,
    Framing.BASELINE_FLAGSHIP,
    Framing.FLAGSHIP_CORRUPTION,
)

FRAMING_COLORS: dict[Framing, str] = {
    Framing.TRUE_BASELINE: "#009E73",
    Framing.BASELINE_FLAGSHIP: "#0072B2",
    Framing.FLAGSHIP_CORRUPTION: "#D55E00",
}

FRAMING_SHORT: dict[Framing, str] = {
    Framing.TRUE_BASELINE: "true_baseline",
    Framing.BASELINE_FLAGSHIP: "baseline_flagship",
    Framing.FLAGSHIP_CORRUPTION: "flagship_corruption",
}


@dataclass
class ModelFrame:
    label: str
    turn_df: pd.DataFrame  # turn_observations output + regime annotation


def load_model(label: str, run_dir: Path) -> ModelFrame:
    jsonl = discover_season_jsonl(run_dir)
    seasons = load_seasons(jsonl)
    turn_df = turn_observations(seasons)
    turn_df = annotate_regime(turn_df)
    logger.info(
        "%s: loaded %d sessions / %d turns",
        label,
        turn_df["session_id"].nunique() if not turn_df.empty else 0,
        len(turn_df),
    )
    return ModelFrame(label=label, turn_df=turn_df)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _agg_by_turn(
    df: pd.DataFrame, y_col: str, group_cols: list[str]
) -> pd.DataFrame:
    """Per-turn mean / SEM / 95% CI, grouped by ``group_cols``."""
    if df.empty or y_col not in df.columns:
        return pd.DataFrame()
    sub = df[df[y_col].notna()].copy()
    if sub.empty:
        return pd.DataFrame()
    g = (
        sub.groupby(["turn_number"] + group_cols, dropna=False)[y_col]
        .agg(mean="mean", sem="sem", count="count")
        .reset_index()
    )
    g["sem"] = g["sem"].fillna(0.0)
    g["ci_lo"] = g["mean"] - 1.96 * g["sem"]
    g["ci_hi"] = g["mean"] + 1.96 * g["sem"]
    return g


def _plot_framing_lines(
    ax: plt.Axes,
    agg: pd.DataFrame,
    *,
    ylabel: str | None = None,
    show_legend: bool = True,
) -> None:
    """Draw one line per framing with shaded 95% CI."""
    any_drawn = False
    for framing in FRAMING_ORDER:
        sub = agg[agg["framing"] == framing.value]
        if sub.empty:
            continue
        colour = FRAMING_COLORS[framing]
        # total turn-count contributing to the series (informational only)
        n_obs = int(sub["count"].sum())
        ax.plot(
            sub["turn_number"],
            sub["mean"],
            color=colour,
            lw=1.8,
            marker="o",
            markersize=3.5,
            label=f"{FRAMING_SHORT[framing]}  (n_obs={n_obs})",
        )
        ax.fill_between(
            sub["turn_number"], sub["ci_lo"], sub["ci_hi"], color=colour, alpha=0.15
        )
        any_drawn = True
    if not any_drawn:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center")
        return
    ax.set_xlabel("Turn")
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    if show_legend:
        ax.legend(loc="upper right", fontsize=7, framealpha=0.85)


# ---------------------------------------------------------------------------
# Plot 1 — 3 channels by turn
# ---------------------------------------------------------------------------


def render_channels(frames: list[ModelFrame], out_path: Path) -> None:
    """Row = RI channel, Col = model. Lines = framing."""
    channels = [
        ("ri_task_thinking_tokens", "ri_task (Call 1)"),
        ("ri_probe_thinking_tokens", "ri_probe (Call 1.5)"),
        ("ri_forfeit_thinking_tokens", "ri_forfeit (Call 2)"),
    ]
    n_cols = len(frames)
    fig, axes = plt.subplots(
        nrows=3, ncols=n_cols, figsize=(5.2 * n_cols, 10.5), squeeze=False, sharex=True
    )
    for col, f in enumerate(frames):
        for row, (y_col, channel_label) in enumerate(channels):
            ax = axes[row, col]
            agg = _agg_by_turn(f.turn_df, y_col, ["framing"])
            _plot_framing_lines(
                ax,
                agg,
                ylabel=f"{channel_label}\nmean tokens" if col == 0 else None,
            )
            if row == 0:
                ax.set_title(f.label, fontsize=12)
    fig.suptitle(
        "RI trajectories by channel — v6 3-Call architecture\n"
        "Rows = Call 1 / Call 1.5 / Call 2 · Cols = model · Lines = framing · Shaded = 95% CI",
        fontsize=12,
        y=0.997,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("channels plot written to %s", out_path)


# ---------------------------------------------------------------------------
# Plot 2 — choice-conditional ri_forfeit
# ---------------------------------------------------------------------------


def render_choice_conditional(frames: list[ModelFrame], out_path: Path) -> None:
    """Row = choice ∈ {CONTINUE, FORFEIT}, Col = model. Lines = framing."""
    n_cols = len(frames)
    fig, axes = plt.subplots(
        nrows=2,
        ncols=n_cols,
        figsize=(5.2 * n_cols, 8.0),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    for col, f in enumerate(frames):
        df = f.turn_df[
            (f.turn_df["forfeit_condition"] == "allowed")
            & f.turn_df["ri_forfeit_thinking_tokens"].notna()
        ].copy()
        df["choice"] = np.where(df["forfeit"], "FORFEIT", "CONTINUE")
        for row_idx, choice in enumerate(["CONTINUE", "FORFEIT"]):
            ax = axes[row_idx, col]
            sub = df[df["choice"] == choice]
            agg = _agg_by_turn(sub, "ri_forfeit_thinking_tokens", ["framing"])
            _plot_framing_lines(
                ax,
                agg,
                ylabel="ri_forfeit (tokens)" if col == 0 else None,
            )
            colour = "#0b3d66" if choice == "CONTINUE" else "#8a1a1a"
            ax.set_title(
                f"{f.label}\nchoice = {choice}  (n_turns={len(sub)})",
                fontsize=11,
                color=colour,
            )
    fig.suptitle(
        "ri_forfeit × Turn × Choice — H_choice_asymmetric time-axis view\n"
        "forfeit_allowed cells only · Lines = framing · Shaded = 95% CI",
        fontsize=12,
        y=0.997,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("choice-conditional plot written to %s", out_path)


# ---------------------------------------------------------------------------
# Plot 3 — regime-stratified ri_forfeit
# ---------------------------------------------------------------------------


def render_regime_stratified(frames: list[ModelFrame], out_path: Path) -> None:
    """Row = regime ∈ {no_cap, cap_bound}, Col = model. Lines = framing."""
    n_cols = len(frames)
    fig, axes = plt.subplots(
        nrows=2,
        ncols=n_cols,
        figsize=(5.2 * n_cols, 8.0),
        squeeze=False,
        sharex=True,
        sharey=True,
    )
    for col, f in enumerate(frames):
        df = f.turn_df[
            (f.turn_df["forfeit_condition"] == "allowed")
            & f.turn_df["ri_forfeit_thinking_tokens"].notna()
        ]
        for row_idx, regime in enumerate(["no_cap", "cap_bound"]):
            ax = axes[row_idx, col]
            sub = df[df["regime"] == regime]
            agg = _agg_by_turn(sub, "ri_forfeit_thinking_tokens", ["framing"])
            _plot_framing_lines(
                ax,
                agg,
                ylabel="ri_forfeit (tokens)" if col == 0 else None,
            )
            colour = "#0b3d66" if regime == "no_cap" else "#8a1a1a"
            ax.set_title(
                f"{f.label}\nregime = {regime}  (n_turns={len(sub)})",
                fontsize=11,
                color=colour,
            )
    fig.suptitle(
        "ri_forfeit × Turn × Regime — Unit 17.10 preference vs rationality split\n"
        "forfeit_allowed cells only · Lines = framing · Shaded = 95% CI",
        fontsize=12,
        y=0.997,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("regime-stratified plot written to %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="plot_ri_trajectories",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--run",
        nargs=2,
        metavar=("LABEL", "DIR"),
        action="append",
        required=True,
        help="Label + experiment output directory. Repeatable.",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        default=Path("outputs"),
        help="Output directory (default: outputs/).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable DEBUG logging."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    frames: list[ModelFrame] = []
    for label, dir_str in args.run:
        run_dir = Path(dir_str)
        if not run_dir.is_dir():
            logger.error("Run directory not found: %s", run_dir)
            return 2
        frames.append(load_model(label, run_dir))
    args.outdir.mkdir(parents=True, exist_ok=True)
    render_channels(frames, args.outdir / "ri_trajectories_channels.png")
    render_choice_conditional(frames, args.outdir / "ri_trajectories_choice.png")
    render_regime_stratified(frames, args.outdir / "ri_trajectories_regime.png")
    logger.info("DONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
