#!/usr/bin/env python3
"""Generate analysis plots for Gemini Flash signal game experiments."""

import json
import glob
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

OUT_DIR = "archive/phase3_cum_hist_2x2x2/0406-2 diagram"

GEMINI_DIRS = {
    "p_death=0.15": "outputs/20260407_0411_gemini-2.5-flash_signal-game",
    "p_death=0.25": "outputs/20260407_0822_gemini-2.5-flash_signal-game",
}

COLORS = {
    ("survival", "allowed"): "#e74c3c",
    ("survival", "not_allowed"): "#c0392b",
    ("neutral", "allowed"): "#3498db",
    ("neutral", "not_allowed"): "#2980b9",
}

LABELS = {
    ("survival", "allowed"): "Survival + Forfeit",
    ("survival", "not_allowed"): "Survival + No Forfeit",
    ("neutral", "allowed"): "Neutral + Forfeit",
    ("neutral", "not_allowed"): "Neutral + No Forfeit",
}

LINESTYLES = {
    "allowed": "-",
    "not_allowed": "--",
}


def load_all_data(base_dir):
    """Load season results and turn-level data."""
    seasons = []
    with open(os.path.join(base_dir, "season_results.jsonl")) as f:
        for line in f:
            if line.strip():
                seasons.append(json.loads(line))

    turn_data = []
    for fpath in glob.glob(os.path.join(base_dir, "*_turns.jsonl")):
        with open(fpath) as f:
            for line in f:
                if line.strip():
                    turn_data.append(json.loads(line))
    return seasons, turn_data


def plot_survival_curves(all_seasons, filename):
    """Kaplan-Meier style survival curves by condition."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    for idx, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        ax = axes[idx]
        conditions = {}
        for s in seasons:
            key = (s["framing"], s["forfeit_condition"])
            conditions.setdefault(key, []).append(s)

        for key, ss in sorted(conditions.items()):
            n_total = len(ss)
            max_turns = 15
            survival = np.ones(max_turns + 1)

            for t in range(1, max_turns + 1):
                alive = sum(1 for s in ss
                            if not s["forfeited"] or (s["forfeited_at_turn"] and s["forfeited_at_turn"] > t))
                survival[t] = alive / n_total

            ax.step(range(max_turns + 1), survival,
                    where="post",
                    color=COLORS[key],
                    linestyle=LINESTYLES[key[1]],
                    linewidth=2,
                    label=f"{LABELS[key]} (n={n_total})")

        ax.set_title(f"Gemini Flash — {pdeath_label}", fontsize=13)
        ax.set_xlabel("Turn", fontsize=11)
        ax.set_ylabel("Survival Rate" if idx == 0 else "", fontsize=11)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xlim(0, 15)
        ax.legend(fontsize=9, loc="lower left")
        ax.grid(alpha=0.3)

    fig.suptitle("Survival Curves by Framing × Forfeit Condition", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


def plot_score_trajectories(all_seasons, filename):
    """Score accumulation over turns by condition."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    for idx, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        ax = axes[idx]
        conditions = {}
        for s in seasons:
            key = (s["framing"], s["forfeit_condition"])
            conditions.setdefault(key, []).append(s)

        for key, ss in sorted(conditions.items()):
            max_turns = 15
            scores_by_turn = {t: [] for t in range(1, max_turns + 1)}

            for s in ss:
                cumulative = 0
                for turn in s["turns"]:
                    tn = turn["turn_number"]
                    ao = turn.get("action_outcome", {})
                    if isinstance(ao, dict):
                        reward = ao.get("reward", 0) or 0
                    else:
                        reward = 0
                    cumulative += reward
                    if tn in scores_by_turn:
                        scores_by_turn[tn].append(cumulative)

            turns = sorted(scores_by_turn.keys())
            means = [np.mean(scores_by_turn[t]) if scores_by_turn[t] else 0 for t in turns]
            stds = [np.std(scores_by_turn[t]) if scores_by_turn[t] else 0 for t in turns]

            ax.plot(turns, means,
                    color=COLORS[key],
                    linestyle=LINESTYLES[key[1]],
                    linewidth=2,
                    label=LABELS[key])
            ax.fill_between(turns,
                            np.array(means) - np.array(stds),
                            np.array(means) + np.array(stds),
                            color=COLORS[key], alpha=0.15)

        ax.set_title(f"Gemini Flash — {pdeath_label}", fontsize=13)
        ax.set_xlabel("Turn", fontsize=11)
        ax.set_ylabel("Cumulative Score" if idx == 0 else "", fontsize=11)
        ax.set_xlim(1, 15)
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

    fig.suptitle("Score Trajectories by Condition (mean ± std)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


def plot_ri_by_turn(all_seasons, filename):
    """Reasoning Investment (answer + thinking tokens) per turn."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    for col, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        conditions = {}
        for s in seasons:
            key = (s["framing"], s["forfeit_condition"])
            conditions.setdefault(key, []).append(s)

        # Row 0: Answer tokens
        ax_ans = axes[0, col]
        # Row 1: Thinking tokens
        ax_think = axes[1, col]

        for key, ss in sorted(conditions.items()):
            ans_by_turn = {}
            think_by_turn = {}
            for s in ss:
                for turn in s["turns"]:
                    tn = turn["turn_number"]
                    ri = turn.get("reasoning_investment", {})
                    if isinstance(ri, dict):
                        ans_by_turn.setdefault(tn, []).append(ri.get("total_tokens", 0) or 0)
                        think_by_turn.setdefault(tn, []).append(ri.get("thinking_tokens", 0) or 0)

            turns = sorted(ans_by_turn.keys())
            ans_means = [np.mean(ans_by_turn[t]) for t in turns]
            think_means = [np.mean(think_by_turn[t]) for t in turns]
            ans_stds = [np.std(ans_by_turn[t]) for t in turns]
            think_stds = [np.std(think_by_turn[t]) for t in turns]

            ax_ans.plot(turns, ans_means,
                        color=COLORS[key], linestyle=LINESTYLES[key[1]],
                        linewidth=2, label=LABELS[key])
            ax_ans.fill_between(turns,
                                np.array(ans_means) - np.array(ans_stds),
                                np.array(ans_means) + np.array(ans_stds),
                                color=COLORS[key], alpha=0.1)

            ax_think.plot(turns, think_means,
                          color=COLORS[key], linestyle=LINESTYLES[key[1]],
                          linewidth=2, label=LABELS[key])
            ax_think.fill_between(turns,
                                  np.array(think_means) - np.array(think_stds),
                                  np.array(think_means) + np.array(think_stds),
                                  color=COLORS[key], alpha=0.1)

        ax_ans.set_title(f"Answer Tokens — {pdeath_label}", fontsize=12)
        ax_ans.set_ylabel("Tokens", fontsize=11)
        ax_ans.legend(fontsize=8)
        ax_ans.grid(alpha=0.3)

        ax_think.set_title(f"Thinking Tokens — {pdeath_label}", fontsize=12)
        ax_think.set_xlabel("Turn", fontsize=11)
        ax_think.set_ylabel("Tokens", fontsize=11)
        ax_think.legend(fontsize=8)
        ax_think.grid(alpha=0.3)

    fig.suptitle("Reasoning Investment per Turn (Gemini Flash)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


def plot_probe_accuracy(all_seasons, filename):
    """Probe (rule comprehension) score per turn."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    for idx, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        ax = axes[idx]
        conditions = {}
        for s in seasons:
            key = (s["framing"], s["forfeit_condition"])
            conditions.setdefault(key, []).append(s)

        for key, ss in sorted(conditions.items()):
            probe_by_turn = {}
            for s in ss:
                for turn in s["turns"]:
                    tn = turn["turn_number"]
                    pr = turn.get("probe_result", {})
                    if isinstance(pr, dict) and pr.get("score") is not None:
                        probe_by_turn.setdefault(tn, []).append(pr["score"])

            turns = sorted(probe_by_turn.keys())
            means = [np.mean(probe_by_turn[t]) for t in turns]

            ax.plot(turns, means,
                    color=COLORS[key], linestyle=LINESTYLES[key[1]],
                    linewidth=2, marker="o", markersize=4,
                    label=LABELS[key])

        ax.set_title(f"Gemini Flash — {pdeath_label}", fontsize=13)
        ax.set_xlabel("Turn", fontsize=11)
        ax.set_ylabel("Probe Score" if idx == 0 else "", fontsize=11)
        ax.set_xlim(1, 15)
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

    fig.suptitle("Probe Accuracy (Rule Comprehension) per Turn", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


def plot_forfeit_summary(all_seasons, filename):
    """Forfeit rate bar chart by condition."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    for idx, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        ax = axes[idx]
        # Only forfeit-allowed conditions
        conditions = {}
        for s in seasons:
            if s["forfeit_condition"] != "allowed":
                continue
            key = s["framing"]
            conditions.setdefault(key, []).append(s)

        framings = sorted(conditions.keys())
        forfeit_rates = []
        avg_forfeit_turns = []
        ns = []

        for fr in framings:
            ss = conditions[fr]
            n_forfeit = sum(1 for s in ss if s["forfeited"])
            forfeit_rates.append(n_forfeit / len(ss))
            ft = [s["forfeited_at_turn"] for s in ss if s["forfeited"] and s["forfeited_at_turn"]]
            avg_forfeit_turns.append(np.mean(ft) if ft else 0)
            ns.append(len(ss))

        x = np.arange(len(framings))
        bars = ax.bar(x, forfeit_rates, color=[COLORS[(f, "allowed")] for f in framings],
                      edgecolor="black", linewidth=0.5)

        for i, (bar, rate, n) in enumerate(zip(bars, forfeit_rates, ns)):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    f"{rate:.0%}\n(n={n})", ha="center", fontsize=10)

        ax.set_title(f"{pdeath_label}", fontsize=13)
        ax.set_ylabel("Forfeit Rate" if idx == 0 else "", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels([f.capitalize() for f in framings], fontsize=11)
        ax.set_ylim(0, 1.15)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Forfeit Rate by Framing (Forfeit-Allowed Only)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


def plot_decision_quality(all_seasons, filename):
    """Decision quality score per turn."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    for idx, (pdeath_label, seasons) in enumerate(all_seasons.items()):
        ax = axes[idx]
        conditions = {}
        for s in seasons:
            key = (s["framing"], s["forfeit_condition"])
            conditions.setdefault(key, []).append(s)

        for key, ss in sorted(conditions.items()):
            dq_by_turn = {}
            for s in ss:
                for turn in s["turns"]:
                    tn = turn["turn_number"]
                    dq = turn.get("decision_quality")
                    if dq is not None:
                        dq_by_turn.setdefault(tn, []).append(dq)

            if not dq_by_turn:
                continue
            turns = sorted(dq_by_turn.keys())
            means = [np.mean(dq_by_turn[t]) for t in turns]

            ax.plot(turns, means,
                    color=COLORS[key], linestyle=LINESTYLES[key[1]],
                    linewidth=2, marker="s", markersize=4,
                    label=LABELS[key])

        ax.set_title(f"Gemini Flash — {pdeath_label}", fontsize=13)
        ax.set_xlabel("Turn", fontsize=11)
        ax.set_ylabel("Decision Quality" if idx == 0 else "", fontsize=11)
        ax.set_xlim(1, 15)
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3)

    fig.suptitle("Decision Quality per Turn", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {filename}")


if __name__ == "__main__":
    print("Loading data...")
    all_seasons = {}
    for label, d in GEMINI_DIRS.items():
        seasons, _ = load_all_data(d)
        all_seasons[label] = seasons
        print(f"  {label}: {len(seasons)} seasons loaded")

    print("\nGenerating plots...")
    plot_survival_curves(all_seasons, "gemini_survival_curves.png")
    plot_score_trajectories(all_seasons, "gemini_score_trajectories.png")
    plot_ri_by_turn(all_seasons, "gemini_ri_by_turn.png")
    plot_probe_accuracy(all_seasons, "gemini_probe_accuracy.png")
    plot_forfeit_summary(all_seasons, "gemini_forfeit_summary.png")
    plot_decision_quality(all_seasons, "gemini_decision_quality.png")
    print(f"\nAll plots saved to: {OUT_DIR}/")
