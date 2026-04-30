"""Plot Kaplan-Meier survival curves across completed model runs.

Event = FORFEIT. Duration = forfeited_at_turn if forfeited else max_turns
(right-censored at the end of the session). Primary stratification is
**framing within forfeit_allowed cells** — this is where FSPM-relevant
preference revelation lives; `not_allowed` cells censor all sessions
at max_turns by construction and are omitted from this plot.

Two-row layout per model (v2, 2026-04-23):

  Row 0 — **All sessions** (forfeit_allowed): full sample KM.
  Row 1 — **Ideal-responder subset** (Unit 17.10 regime filter):
    only sessions whose forfeit decision (or full censored trace) lived
    in the ``no_cap`` regime, i.e. the preference-revealing zone where
    Equal-EV calibration holds. Cap-bound forfeits are rationality-
    forced, not preference-revealing, so dropping them isolates the
    FSPM signal.

Session-level "ideal responder" rule:
  - If session FORFEITED → include iff the forfeit turn's regime
    was ``no_cap``.
  - If session was CENSORED (no forfeit) → include iff NO observed
    turn was ``cap_bound`` (the full trace lived in the clean regime).

Usage::

    # Explicit runs (label + directory). Repeatable per model.
    uv run python scripts/plot_kaplan_meier.py \\
      --run gemini-2.5-flash archive/final_results/20260422_0218_gemini-2.5-flash_signal-game \\
      --run gpt-oss-20b outputs/20260422_0902_gpt-oss-20b-cloud_signal-game \\
      --run nemotron-3-nano-30b outputs/20260422_0902_nemotron-3-nano-30b-cloud_signal-game \\
      --run qwen3-next-80b outputs/20260422_0902_qwen3-next-80b-cloud_signal-game \\
      -o outputs/km_curves_4x2.png

Outputs: a single PNG grid — rows = (All sessions, Ideal-responder),
columns = model. Log-rank tests (baseline_flagship vs
flagship_corruption within allowed) are annotated on each subplot.
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
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test

from squid_game.analysis import discover_season_jsonl, load_seasons
from squid_game.analysis.forfeit_regression import turn_observations
from squid_game.analysis.regime_stratification import annotate_regime
from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.results import SeasonResult

logger = logging.getLogger("plot_kaplan_meier")

# Canonical v6 framing order + color palette. Colorblind-safe
# (Wong 2011 — blue/vermillion/yellow-ish green).
FRAMING_ORDER: tuple[Framing, ...] = (
    Framing.TRUE_BASELINE,
    Framing.BASELINE_FLAGSHIP,
    Framing.FLAGSHIP_CORRUPTION,
)

FRAMING_COLORS: dict[Framing, str] = {
    Framing.TRUE_BASELINE: "#009E73",      # bluish green
    Framing.BASELINE_FLAGSHIP: "#0072B2",   # blue
    Framing.FLAGSHIP_CORRUPTION: "#D55E00", # vermillion
}

FRAMING_LABELS: dict[Framing, str] = {
    Framing.TRUE_BASELINE: "true_baseline",
    Framing.BASELINE_FLAGSHIP: "baseline_flagship",
    Framing.FLAGSHIP_CORRUPTION: "flagship_corruption",
}


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


@dataclass
class SurvivalFrame:
    """Per-model survival-analysis frame with ideal-responder split."""

    label: str
    df_all: pd.DataFrame  # All forfeit_allowed sessions
    df_ideal: pd.DataFrame  # Ideal-responder subset (Unit 17.10 no_cap regime)
    max_turns: int


def _derive_ideal_session_ids(
    seasons: list[SeasonResult],
    turn_df_with_regime: pd.DataFrame,
) -> set[str]:
    """Sessions whose behaviour stayed in the preference-revealing regime.

    - FORFEITED → regime at forfeit turn must be ``no_cap``.
    - CENSORED  → no turn may have been ``cap_bound``.
    """
    ideal: set[str] = set()
    if turn_df_with_regime.empty or "regime" not in turn_df_with_regime.columns:
        return ideal
    by_session = turn_df_with_regime.groupby("session_id")
    for s in seasons:
        sid = s.season_id
        if sid not in by_session.groups:
            continue
        sub = by_session.get_group(sid)
        if s.forfeited and s.forfeited_at_turn is not None:
            # regime at the forfeit turn itself
            ft = s.forfeited_at_turn
            row = sub[sub["turn_number"] == ft]
            if not row.empty and str(row["regime"].iloc[0]) == "no_cap":
                ideal.add(sid)
        else:
            # censored: require absence of cap_bound throughout
            if not (sub["regime"] == "cap_bound").any():
                ideal.add(sid)
    return ideal


def build_survival_frame(
    label: str,
    run_dir: Path,
) -> SurvivalFrame:
    """Convert a run directory into two KM-ready DataFrames (all + ideal)."""
    jsonl = discover_season_jsonl(run_dir)
    seasons: list[SeasonResult] = load_seasons(jsonl)

    max_turns = max((len(s.turns) for s in seasons), default=0)

    # Build turn-level DataFrame + annotate regime.
    turn_df = turn_observations(seasons)
    turn_df = annotate_regime(turn_df)

    ideal_ids = _derive_ideal_session_ids(seasons, turn_df)

    rows = []
    for s in seasons:
        # Focus on forfeit_allowed only — primary FSPM signal layer.
        if s.forfeit_condition != ForfeitCondition.ALLOWED:
            continue
        n_turns = len(s.turns)
        if s.forfeited and s.forfeited_at_turn is not None:
            duration = s.forfeited_at_turn
            event = 1
        else:
            duration = n_turns
            event = 0
        rows.append(
            {
                "session_id": s.season_id,
                "framing": s.framing.value,
                "forfeit_condition": s.forfeit_condition.value,
                "duration": duration,
                "event": event,
                "n_turns": n_turns,
                "ideal": s.season_id in ideal_ids,
            }
        )
    df_all = pd.DataFrame(rows)
    df_ideal = df_all[df_all["ideal"]].copy()

    logger.info(
        "%s: allowed n=%d (%d forfeits), ideal-responder n=%d (%d forfeits), "
        "max_turns=%d",
        label,
        len(df_all),
        int(df_all["event"].sum()) if not df_all.empty else 0,
        len(df_ideal),
        int(df_ideal["event"].sum()) if not df_ideal.empty else 0,
        max_turns,
    )
    return SurvivalFrame(
        label=label, df_all=df_all, df_ideal=df_ideal, max_turns=max_turns
    )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def _plot_single_cell(
    ax: plt.Axes,
    subset: pd.DataFrame,
    max_turns: int,
    show_logrank: bool = True,
    legend_outside: bool = False,
    set_xlabel: bool = True,
) -> None:
    """Draw KM curves (one per framing) on a single axis.

    ``subset`` must be pre-filtered to the desired sample (forfeit_allowed,
    optionally regime-subsetted).
    """
    kmf = KaplanMeierFitter()
    if subset.empty:
        ax.text(0.5, 0.5, "no data", transform=ax.transAxes, ha="center")
        return

    for framing in FRAMING_ORDER:
        framing_sub = subset[subset["framing"] == framing.value]
        if framing_sub.empty:
            continue
        kmf.fit(
            durations=framing_sub["duration"],
            event_observed=framing_sub["event"],
            label=f"{FRAMING_LABELS[framing]}  (n={len(framing_sub)}, "
            f"{int(framing_sub['event'].sum())} forfeits)",
        )
        kmf.plot_survival_function(
            ax=ax,
            color=FRAMING_COLORS[framing],
            ci_alpha=0.15,
        )

    if set_xlabel:
        ax.set_xlabel("Turn")
    ax.set_ylabel("Survival probability (P[not forfeited])")
    ax.set_ylim(-0.02, 1.05)
    ax.set_xlim(0, max_turns)
    ax.grid(alpha=0.3)
    if legend_outside:
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.18),
            ncol=3,
            fontsize=8,
            frameon=False,
        )
    else:
        ax.legend(loc="lower left", fontsize=7, framealpha=0.85)

    if show_logrank:
        bf = subset[subset["framing"] == Framing.BASELINE_FLAGSHIP.value]
        fc = subset[subset["framing"] == Framing.FLAGSHIP_CORRUPTION.value]
        if not bf.empty and not fc.empty:
            result = logrank_test(
                durations_A=bf["duration"],
                durations_B=fc["duration"],
                event_observed_A=bf["event"],
                event_observed_B=fc["event"],
            )
            ax.text(
                0.97,
                0.97,
                f"log-rank (BF vs FC)\n"
                f"χ² = {result.test_statistic:.2f}\n"
                f"p = {result.p_value:.3g}",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=8,
                bbox={
                    "boxstyle": "round,pad=0.4",
                    "facecolor": "white",
                    "edgecolor": "#888888",
                    "alpha": 0.9,
                },
            )


def render_grid(
    frames: list[SurvivalFrame],
    out_path: Path,
) -> None:
    """Render a 2×N grid (rows = All / Ideal-responder, cols = model).

    Row 0 — All forfeit_allowed sessions (full FSPM-signal sample).
    Row 1 — Ideal-responder subset: sessions whose forfeit decision (or
    full censored trace) lived in the ``no_cap`` regime (Unit 17.10).
    """
    n_models = len(frames)
    fig, axes = plt.subplots(
        nrows=2,
        ncols=n_models,
        figsize=(5.2 * n_models, 8.8),
        squeeze=False,
        sharey=True,
    )
    max_turns = max(f.max_turns for f in frames)

    for col, frame in enumerate(frames):
        # Row 0: ALL forfeit_allowed sessions
        ax_all = axes[0, col]
        _plot_single_cell(ax_all, frame.df_all, max_turns)
        ax_all.set_title(
            f"{frame.label}\nAll forfeit_allowed  (n={len(frame.df_all)})",
            fontsize=11,
        )

        # Row 1: Ideal-responder subset (no_cap regime)
        ax_ideal = axes[1, col]
        _plot_single_cell(ax_ideal, frame.df_ideal, max_turns)
        ax_ideal.set_title(
            f"{frame.label}\nIdeal-responder (no_cap regime)  "
            f"(n={len(frame.df_ideal)})",
            fontsize=11,
            color="#0b3d66",
        )

    fig.suptitle(
        "Kaplan-Meier Survival Curves — v6 canonical, forfeit_allowed only\n"
        "Top: all sessions · Bottom: Unit 17.10 no_cap (preference-revealing) subset\n"
        "Event = FORFEIT · Duration = turn of forfeit or censored at session end",
        fontsize=12,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("KM grid written to %s", out_path)


def render_vertical_ideal(
    frames: list[SurvivalFrame],
    out_path: Path,
    subplot_width: float = 8.0,
    subplot_height: float = 3.6,
) -> None:
    """Render N×1 vertical KM grid — ideal-responder (no_cap) regime only.

    Each row = one model. No figure-level title, no log-rank annotation,
    no cell numbers in legend (FRAMING_LABELS is already cleaned). Legend
    is placed *below* each subplot, centered, with the three framings on
    a single line. Per-subplot title = model label + sample size only.

    Default per-subplot ratio is 8.0:3.6 ≈ 2.22:1 (landscape per axis,
    larger width-to-height than the original 5.2:4.4 ≈ 1.18:1 grid). The
    extra subplot height accommodates the below-axis legend without
    cramping the survival curve.
    """
    n_models = len(frames)
    fig, axes = plt.subplots(
        nrows=n_models,
        ncols=1,
        figsize=(subplot_width, subplot_height * n_models),
        squeeze=False,
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    max_turns = max(f.max_turns for f in frames)

    for row, frame in enumerate(frames):
        is_bottom = row == n_models - 1
        ax = axes[row, 0]
        _plot_single_cell(
            ax,
            frame.df_ideal,
            max_turns,
            show_logrank=False,
            legend_outside=True,
            set_xlabel=is_bottom,
        )
        ax.set_title(
            f"{frame.label}  (n={len(frame.df_ideal)}, "
            f"{int(frame.df_ideal['event'].sum()) if not frame.df_ideal.empty else 0} forfeits)",
            fontsize=11,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Vertical KM grid written to %s", out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="plot_kaplan_meier",
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
        "--output",
        type=Path,
        default=Path("outputs/km_curves.png"),
        help="Output PNG path (default: outputs/km_curves.png).",
    )
    parser.add_argument(
        "--layout",
        choices=("grid", "vertical"),
        default="grid",
        help="Layout: 'grid' (2×N all-vs-ideal, with figure title and "
        "log-rank annotations) or 'vertical' (N×1 ideal-responder only, "
        "no figure title, no log-rank annotations).",
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

    frames: list[SurvivalFrame] = []
    for label, dir_str in args.run:
        run_dir = Path(dir_str)
        if not run_dir.is_dir():
            logger.error("Run directory not found: %s", run_dir)
            return 2
        frames.append(build_survival_frame(label, run_dir))

    if args.layout == "vertical":
        render_vertical_ideal(frames, args.output)
    else:
        render_grid(frames, args.output)
    logger.info("DONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
