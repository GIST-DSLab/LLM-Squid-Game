"""Conflict-zone EDA plots for ri_forfeit (Call 2 thinking_tokens).

Generated for the §3 metric.md "inverted-U" check (Option D in the design
discussion 2026-04-26): does ri_forfeit on the CONTINUE arm peak at a
conflict zone? Score-axis (initial probe) showed flat — so we add a
turn-axis version which captures the actual conflict window for SD-strong
agents that exit before score accumulates.

Three figures:

  1. ``ri_forfeit_continue_vs_score.png`` — binned mean (with 95% CI bars
     and LOWESS smoother) of ri_forfeit | CONTINUE by score_before_turn,
     per (model × framing). Cells 1, 3, 5 (allowed framings).

  2. ``ri_forfeit_continue_vs_turn.png`` — same metric binned by turn_number
     instead of score. Captures conflict window for SD-strong agents that
     exit before score accumulates (Qwen3-Next FC: 96.7% forfeit at
     turn ≤ 3).

  3. ``ri_forfeit_heatmap_session_turn.png`` — session × turn heatmap of
     ri_forfeit thinking tokens, per (model × cell ∈ {1, 3, 5}). Forfeit
     turn marked with "x" overlay. **Per-model color scale** (same YlOrRd
     colormap, different vmax per model) so within-model trajectories are
     comparable across framings, while cross-model magnitude differences
     (Cluster A ≈ 3000 tok vs GPT-OSS ≈ 400 tok) don't wash out structure.

Usage::

    uv run python scripts/plot_ri_forfeit_conflict_zone.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

from squid_game.analysis import discover_season_jsonl, load_seasons
from squid_game.analysis.forfeit_regression import turn_observations

logger = logging.getLogger("plot_ri_forfeit_conflict_zone")


# --- Config -----------------------------------------------------------------

MODELS: list[tuple[str, str]] = [
    ("Gemini-2.5-flash",
     "outputs/final_results/20260422_0218_gemini-2.5-flash_signal-game"),
    ("Qwen3-Next-80B",
     "outputs/final_results/20260422_0902_qwen3-next-80b-cloud_signal-game"),
    ("GPT-OSS-20B",
     "outputs/final_results/20260422_0902_gpt-oss-20b-cloud_signal-game"),
    ("Nemotron-3-Nano-30B",
     "outputs/final_results/20260422_0902_nemotron-3-nano-30b-cloud_signal-game"),
]

OUT_DIR = Path("outputs/final_results")

# Wong 2011 colorblind-safe — matches plot_ri_trajectories.py.
FRAMING_COLORS: dict[str, str] = {
    "true_baseline":       "#009E73",  # green
    "baseline_flagship":   "#0072B2",  # blue
    "flagship_corruption": "#D55E00",  # orange
}
FRAMING_LABELS: dict[str, str] = {
    "true_baseline":       "Cell 5: TB·allowed (no threat)",
    "baseline_flagship":   "Cell 1: BF·allowed (Pull only)",
    "flagship_corruption": "Cell 3: FC·allowed (Pull + Push)",
}
FRAMING_ORDER = ("true_baseline", "baseline_flagship", "flagship_corruption")

# Heatmap row order — pairs allow/block within each framing for direct
# visual comparison. Cell 0 (TB·not_allowed) is excluded (Call 2 skipped
# → no ri_forfeit data exists by design).
CELL_ROWS: list[tuple[str, str, str]] = [
    ("true_baseline",       "allowed",     "Cell 5: TB·allow"),
    ("baseline_flagship",   "allowed",     "Cell 1: BF·allow"),
    ("baseline_flagship",   "not_allowed", "Cell 2: BF·block"),
    ("flagship_corruption", "allowed",     "Cell 3: FC·allow"),
    ("flagship_corruption", "not_allowed", "Cell 4: FC·block"),
]


# --- Data loading -----------------------------------------------------------

def load_all() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for label, run_dir in MODELS:
        jsonl = discover_season_jsonl(Path(run_dir))
        seasons = load_seasons(jsonl)
        df = turn_observations(seasons)
        df["model"] = label
        frames.append(df)
        logger.info("loaded %s: %d turn rows", label, len(df))
    return pd.concat(frames, ignore_index=True)


# --- Plot 1: conflict-zone curve --------------------------------------------

def _binned_stats(
    x: np.ndarray, y: np.ndarray, edges: np.ndarray, min_count: int = 5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return (midpoints, mean, ci95, count) for bins with count >= min_count."""
    idx = np.digitize(x, edges) - 1
    n_bins = len(edges) - 1
    means = np.full(n_bins, np.nan)
    sems = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins, dtype=int)
    for b in range(n_bins):
        mask = idx == b
        c = int(mask.sum())
        counts[b] = c
        if c >= min_count:
            ys = y[mask]
            means[b] = ys.mean()
            sems[b] = ys.std(ddof=1) / np.sqrt(c) if c > 1 else 0.0
    midpoints = (edges[:-1] + edges[1:]) / 2.0
    keep = counts >= min_count
    return midpoints[keep], means[keep], 1.96 * sems[keep], counts[keep]


def plot_conflict_zone(df: pd.DataFrame, out_path: Path) -> None:
    sub = df[
        (df["forfeit_condition"] == "allowed")
        & (~df["forfeit"])
        & (df["ri_forfeit_thinking_tokens"].notna())
    ].copy()

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharey=False)
    axes = axes.flatten()

    # Score range is 22-225 (capped by reward_cap_multiple). 7 equal-width bins.
    GLOBAL_EDGES = np.linspace(0, 230, 8)

    for i, (model, _) in enumerate(MODELS):
        ax = axes[i]
        msub = sub[sub["model"] == model]

        for framing in FRAMING_ORDER:
            f_sub = msub[msub["framing"] == framing]
            n_total = len(f_sub)
            if n_total < 10:
                continue

            x = f_sub["score_before_turn"].to_numpy()
            y = f_sub["ri_forfeit_thinking_tokens"].to_numpy()

            mids, means, ci, counts = _binned_stats(x, y, GLOBAL_EDGES, min_count=5)
            color = FRAMING_COLORS[framing]
            label = f"{FRAMING_LABELS[framing]}  (n={n_total})"

            if len(mids) > 0:
                ax.errorbar(
                    mids, means, yerr=ci, fmt="o", color=color, ecolor=color,
                    elinewidth=1.2, capsize=3, markersize=6, alpha=0.85, label=label,
                )

            # LOWESS smoother on raw points (frac chosen to avoid over-fit on small n).
            if n_total >= 30:
                frac = max(0.4, min(0.8, 30 / n_total))
                smoothed = lowess(y, x, frac=frac, it=2, return_sorted=True)
                ax.plot(smoothed[:, 0], smoothed[:, 1], "-", color=color,
                        alpha=0.55, linewidth=1.8)

        ax.set_title(model, fontsize=12, fontweight="bold")
        ax.set_xlabel(r"$S(t-1)$  (score before turn)")
        ax.set_ylabel(r"ri_forfeit | CONTINUE  [thinking tokens]")
        ax.legend(fontsize=7, loc="best", framealpha=0.85)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 230)
        ax.set_ylim(bottom=0)

    fig.suptitle(
        "Cognitive load on CONTINUE choice vs accumulated score\n"
        "(Conflict-zone EDA — does ri_forfeit | CONTINUE peak at mid-score?)",
        fontsize=13, y=1.00,
    )
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved: %s", out_path)


# --- Plot 2: turn-axis conflict-zone curve ----------------------------------

def plot_turn_axis(df: pd.DataFrame, out_path: Path, max_turn: int = 15) -> None:
    """ri_forfeit | CONTINUE binned by turn_number (instead of score).

    Captures the conflict window for SD-strong agents that forfeit early,
    before score accumulates. Each panel also annotates n_sessions surviving
    per turn as a thin grey trace below the main line.
    """
    sub = df[
        (df["forfeit_condition"] == "allowed")
        & (~df["forfeit"])  # CONTINUE only — confound-free per metric.md §0.1
        & (df["ri_forfeit_thinking_tokens"].notna())
        & (df["turn_number"] <= max_turn)
    ].copy()

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), sharey=False, sharex=True)
    axes = axes.flatten()

    for i, (model, _) in enumerate(MODELS):
        ax = axes[i]
        msub = sub[sub["model"] == model]

        for framing in FRAMING_ORDER:
            f_sub = msub[msub["framing"] == framing]
            n_total = len(f_sub)
            if n_total < 10:
                continue

            grouped = (
                f_sub.groupby("turn_number")["ri_forfeit_thinking_tokens"]
                .agg(["mean", "sem", "count"])
                .reset_index()
            )
            grouped = grouped[grouped["count"] >= 3]
            if len(grouped) == 0:
                continue

            x = grouped["turn_number"].to_numpy()
            y = grouped["mean"].to_numpy()
            ci = 1.96 * grouped["sem"].fillna(0).to_numpy()

            color = FRAMING_COLORS[framing]
            label = f"{FRAMING_LABELS[framing]}  (n={n_total})"
            ax.plot(x, y, "o-", color=color, label=label, markersize=5, linewidth=1.6)
            ax.fill_between(x, y - ci, y + ci, color=color, alpha=0.18, linewidth=0)

        ax.set_title(model, fontsize=12, fontweight="bold")
        ax.set_xlabel("Turn number")
        ax.set_ylabel("ri_forfeit | CONTINUE  [thinking tokens]")
        ax.legend(fontsize=7, loc="best", framealpha=0.85)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0.5, max_turn + 0.5)
        ax.set_xticks(range(1, max_turn + 1))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_ylim(bottom=0)

    fig.suptitle(
        "Cognitive load on CONTINUE choice vs turn number\n"
        "(Conflict zone reframed onto turn axis — survivorship-biased; n shown per panel)",
        fontsize=13, y=1.00,
    )
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved: %s", out_path)


# --- Plot 3: session × turn heatmap (per-model color scale) -----------------

def plot_heatmap_per_model(df: pd.DataFrame, out_path: Path, max_turn: int = 15) -> None:
    """Session × turn heatmap with per-model vmax (shared YlOrRd colormap).

    Each model has its own colorbar — within-model trajectories across the
    5 cells (Cell 5 / 1 / 2 / 3 / 4) become directly comparable, while
    cross-model magnitude differences (Cluster A 3000+ tok vs GPT-OSS
    ~400 tok) don't flatten the structure.

    Cells 2 and 4 (forfeit blocked) carry no × markers because forfeit was
    not an available action — pale rows there are the visual signature of
    "no decision → no Call-2 deliberation cost".
    """
    sub = df[
        (df["ri_forfeit_thinking_tokens"].notna())
        & (df["turn_number"] <= max_turn)
    ].copy()

    n_models = len(MODELS)
    n_rows = len(CELL_ROWS)
    cmap = "YlOrRd"

    fig = plt.figure(figsize=(5.2 * n_models, 2.6 * n_rows + 1.2))
    subfigs = fig.subfigures(1, n_models, wspace=0.04)

    for col_idx, (model, _) in enumerate(MODELS):
        subfig = subfigs[col_idx]
        msub = sub[sub["model"] == model]

        # Per-model vmax — 95th percentile across all cells of this model.
        if len(msub) == 0:
            subfig.suptitle(f"{model} (no data)", fontsize=11, fontweight="bold")
            continue
        vmax = float(msub["ri_forfeit_thinking_tokens"].quantile(0.95))
        vmin = 0.0

        axes = subfig.subplots(n_rows, 1, sharex=True)
        last_im = None

        for row_idx, (framing, fcond, label) in enumerate(CELL_ROWS):
            ax = axes[row_idx]
            sess = msub[
                (msub["framing"] == framing)
                & (msub["forfeit_condition"] == fcond)
            ]
            if len(sess) == 0:
                ax.text(0.5, 0.5, "no data", ha="center", va="center",
                        transform=ax.transAxes, fontsize=9)
                ax.set_xticks([]); ax.set_yticks([])
                continue

            mat = sess.pivot_table(
                index="session_id", columns="turn_number",
                values="ri_forfeit_thinking_tokens", aggfunc="mean",
            )
            forfeit_turns = (
                sess[sess["forfeit"]]
                .drop_duplicates("session_id")
                .set_index("session_id")["turn_number"]
            )

            def sort_key(sid: str) -> tuple[int, int]:
                if sid in forfeit_turns.index:
                    return (0, int(forfeit_turns[sid]))
                return (1, int(mat.loc[sid].notna().sum()))

            ordered = sorted(mat.index, key=sort_key)
            mat = mat.loc[ordered]
            cols = list(mat.columns)

            last_im = ax.imshow(
                mat.values, aspect="auto", cmap=cmap,
                vmin=vmin, vmax=vmax, interpolation="nearest",
            )

            for sid_idx, sid in enumerate(mat.index):
                if sid in forfeit_turns.index:
                    t = int(forfeit_turns[sid])
                    if t in cols:
                        col = cols.index(t)
                        ax.plot(col, sid_idx, "x", color="black",
                                markersize=5, mew=1.3)

            ax.set_xticks(range(len(cols)))
            ax.set_xticklabels(cols, fontsize=7)
            ax.set_yticks([])

            cell_mean = float(sess["ri_forfeit_thinking_tokens"].mean())
            ax.set_ylabel(
                f"{label}\nn={len(mat)}, μ={cell_mean:.0f}",
                fontsize=8,
            )
            if row_idx == n_rows - 1:
                ax.set_xlabel("Turn", fontsize=9)

        # Per-model colorbar on the right of this model's column.
        if last_im is not None:
            cbar = subfig.colorbar(
                last_im, ax=axes, shrink=0.85, pad=0.02, aspect=40, location="right",
            )
            cbar.set_label(f"ri_forfeit tokens (vmax={int(vmax)})", fontsize=8)
            cbar.ax.tick_params(labelsize=7)

        subfig.suptitle(model, fontsize=12, fontweight="bold", y=0.97)

    fig.suptitle(
        "ri_forfeit per turn — session × turn heatmap  (× = forfeit point)\n"
        "Allow vs block paired within each framing (rows 2-3 = BF, rows 4-5 = FC). "
        "Per-model color scale (shared colormap, separate vmax).",
        fontsize=12, y=1.00,
    )
    fig.subplots_adjust(top=0.93)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info("Saved: %s", out_path)


# --- Main -------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    df = load_all()
    plot_conflict_zone(df, OUT_DIR / "ri_forfeit_continue_vs_score.png")
    plot_turn_axis(df, OUT_DIR / "ri_forfeit_continue_vs_turn.png")
    plot_heatmap_per_model(df, OUT_DIR / "ri_forfeit_heatmap_session_turn.png")
    print("Done.")


if __name__ == "__main__":
    main()
