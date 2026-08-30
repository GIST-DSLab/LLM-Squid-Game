#!/usr/bin/env python3
"""Generate session x turn heatmaps for all models, split by p_death."""

import json
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# Job configs: one heatmap per (model, p_death) combination
# ---------------------------------------------------------------------------
PHASE3_DIR = "archive/phase3_cum_hist_2x2x2"
PHASE4_DIR = "archive/phase4"

JOBS = [
    # --- Phase 3: Gemini ---
    {
        "model_label": "Gemini 2.5 Flash",
        "pdeath_label": "p_death=0.15",
        "base_dir": f"{PHASE3_DIR}/20260406_1525_gemini-2.5-flash_signal-game",
        "out_dir": f"{PHASE3_DIR}/diagram",
        "filename": "heatmap_gemini_p_death015.png",
    },
    {
        "model_label": "Gemini 2.5 Flash",
        "pdeath_label": "p_death=0.25",
        "base_dir": f"{PHASE3_DIR}/20260406_1830_gemini-2.5-flash_signal-game",
        "out_dir": f"{PHASE3_DIR}/diagram",
        "filename": "heatmap_gemini_p_death025.png",
    },
    # --- Phase 3: Qwen MLX ---
    {
        "model_label": "Qwen3 4B (MLX)",
        "pdeath_label": "p_death=0.15",
        "base_dir": f"{PHASE3_DIR}/20260406_1524_mlx-community-Qwen3-4B-4bit_signal-game",
        "out_dir": f"{PHASE3_DIR}/diagram",
        "filename": "heatmap_qwen3_mlx_p_death015.png",
    },
    {
        "model_label": "Qwen3 4B (MLX)",
        "pdeath_label": "p_death=0.25",
        "base_dir": f"{PHASE3_DIR}/20260406_1916_mlx-community-Qwen3-4B-4bit_signal-game",
        "out_dir": f"{PHASE3_DIR}/diagram",
        "filename": "heatmap_qwen3_mlx_p_death025.png",
    },
    # --- Phase 4: Qwen vLLM ---
    {
        "model_label": "Qwen3 4B (vLLM)",
        "pdeath_label": "p_death=0.15",
        "base_dir": f"{PHASE4_DIR}/20260407_1102_Qwen-Qwen3-4B_signal-game",
        "out_dir": f"{PHASE4_DIR}/diagram",
        "filename": "qwen3_heatmap_p_death015.png",
    },
    {
        "model_label": "Qwen3 4B (vLLM)",
        "pdeath_label": "p_death=0.25",
        "base_dir": f"{PHASE4_DIR}/20260407_1556_Qwen-Qwen3-4B_signal-game",
        "out_dir": f"{PHASE4_DIR}/diagram",
        "filename": "qwen3_heatmap_p_death025.png",
    },
]

# Combined image configs: 4 panels (2 models x 2 p_death) per phase
COMBINED = [
    {
        "title": "Phase 3 — All Models × p_death — Session × Turn Heatmap",
        "out_dir": f"{PHASE3_DIR}/diagram",
        "filename": "combined_heatmaps_phase3.png",
        "panels": [
            "heatmap_gemini_p_death015.png",
            "heatmap_gemini_p_death025.png",
            "heatmap_qwen3_mlx_p_death015.png",
            "heatmap_qwen3_mlx_p_death025.png",
        ],
    },
    {
        "title": "Phase 4 — All Models × p_death — Session × Turn Heatmap",
        "out_dir": f"{PHASE4_DIR}/diagram",
        "filename": "combined_heatmaps_phase4.png",
        "panels": [
            "gemini_heatmap_p_death015.png",
            "gemini_heatmap_p_death025.png",
            "qwen3_heatmap_p_death015.png",
            "qwen3_heatmap_p_death025.png",
        ],
    },
]

CONDITIONS = [
    ("survival", "allowed"),
    ("survival", "not_allowed"),
    ("neutral", "allowed"),
    ("neutral", "not_allowed"),
]

COND_LABELS = {
    ("survival", "allowed"): "Survival / Allowed",
    ("survival", "not_allowed"): "Survival / Not-Allowed",
    ("neutral", "allowed"): "Neutral / Allowed",
    ("neutral", "not_allowed"): "Neutral / Not-Allowed",
}

MAX_TURNS = 15

# Filter for which phases to process. Set to None to process all JOBS.
# Match against substring of job["base_dir"].
PHASE_FILTER = "phase3"  # Only Phase 3 jobs


def split_thinking_tokens(turn: dict) -> tuple[float, float]:
    """Split combined thinking_tokens into (probe_tokens, action_tokens).

    Token counts are NOT separately persisted, but thinking *text* is —
    probe.thinking_text holds probe-only thinking, while top-level
    thinking_text is "<probe>\\n---\\n<action>" when both exist.

    We split the combined token count proportionally by character
    length of each thinking text. Probe and action share the same
    model and tokenizer so char/token ratio is approximately equal
    between them (systematic bias minimal).
    """
    ri = turn.get("reasoning_investment", {}) or {}
    total = ri.get("thinking_tokens", 0) or 0
    if total == 0:
        return (0.0, 0.0)

    probe_text = (turn.get("probe_result") or {}).get("thinking_text") or ""
    combined_text = turn.get("thinking_text") or ""

    if "\n---\n" in combined_text:
        # Both probe and action thinking present.
        action_text = combined_text.split("\n---\n", 1)[1]
    elif not probe_text:
        # Only action thinking — combined IS the action text.
        action_text = combined_text
    else:
        # Only probe thinking — no action text.
        action_text = ""

    p_len = len(probe_text)
    a_len = len(action_text)
    if p_len + a_len == 0:
        # Fallback: equal split when both texts unavailable.
        return (total / 2, total / 2)

    p_share = p_len / (p_len + a_len)
    return (total * p_share, total * (1 - p_share))


def split_answer_tokens(turn: dict) -> tuple[float, float]:
    """Split combined total_tokens (output/answer) into (probe, action).

    probe_result.response and top-level raw_response are always stored
    separately, so we split proportionally by response character length.
    """
    ri = turn.get("reasoning_investment", {}) or {}
    total = ri.get("total_tokens", 0) or 0
    if total == 0:
        return (0.0, 0.0)

    probe_resp = (turn.get("probe_result") or {}).get("response") or ""
    action_resp = turn.get("raw_response") or ""

    p_len = len(probe_resp)
    a_len = len(action_resp)
    if p_len + a_len == 0:
        return (total / 2, total / 2)

    p_share = p_len / (p_len + a_len)
    return (total * p_share, total * (1 - p_share))


def load_sessions(base_dir):
    """Load and group sessions by condition."""
    with open(os.path.join(base_dir, "season_results.jsonl")) as f:
        seasons = [json.loads(l) for l in f if l.strip()]

    by_cond = {}
    for s in seasons:
        key = (s["framing"], s["forfeit_condition"])
        by_cond.setdefault(key, []).append(s)
    return by_cond


def extract_matrices(sessions):
    """Extract per-turn matrices for all heatmap rows.

    Returns dict of named matrices + forfeit_points list.

    Matrix groups:
        Existing (combined probe+action):
            probe_score, decision_quality, total_thinking, total_answer
        New (probe/action split, motivation_RI candidates):
            probe_thinking, action_thinking,
            ri_diff (= action - probe, Donders),
            ri_logratio (= log((a+1)/(p+1))),
            probe_answer, action_answer
    """
    sessions_sorted = sorted(sessions,
                             key=lambda s: (
                                 s.get("forfeited_at_turn") or MAX_TURNS,
                                 -s["final_score"]
                             ))

    n = len(sessions_sorted)

    def empty():
        return np.full((n, MAX_TURNS), np.nan)

    mats = {
        "probe_score": empty(),
        "decision_quality": empty(),
        "total_thinking": empty(),
        "total_answer": empty(),
        "probe_thinking": empty(),
        "action_thinking": empty(),
        "ri_diff": empty(),
        "ri_logratio": empty(),
        "probe_answer": empty(),
        "action_answer": empty(),
    }
    forfeit_points = []

    for i, s in enumerate(sessions_sorted):
        ft = s.get("forfeited_at_turn")
        forfeit_points.append(ft)

        for turn in s["turns"]:
            tn = turn["turn_number"]
            if tn < 1 or tn > MAX_TURNS:
                continue
            col = tn - 1

            pr = turn.get("probe_result", {})
            if isinstance(pr, dict) and pr.get("score") is not None:
                mats["probe_score"][i, col] = pr["score"]

            dq = turn.get("decision_quality")
            if dq is not None:
                mats["decision_quality"][i, col] = dq

            ri = turn.get("reasoning_investment", {})
            if isinstance(ri, dict):
                mats["total_thinking"][i, col] = (ri.get("thinking_tokens", 0) or 0) / 1000
                mats["total_answer"][i, col] = ri.get("total_tokens", 0) or 0

            # Probe/action token split via text-length ratio.
            p_think, a_think = split_thinking_tokens(turn)
            mats["probe_thinking"][i, col] = p_think / 1000
            mats["action_thinking"][i, col] = a_think / 1000
            mats["ri_diff"][i, col] = (a_think - p_think) / 1000
            mats["ri_logratio"][i, col] = float(np.log((a_think + 1) / (p_think + 1)))

            p_ans, a_ans = split_answer_tokens(turn)
            mats["probe_answer"][i, col] = p_ans
            mats["action_answer"][i, col] = a_ans

    return mats, forfeit_points


def plot_heatmap(fig, ax, mat, forfeit_points, title, cmap, vmin, vmax, cbar_label):
    """Plot a single heatmap with forfeit markers."""
    masked = np.ma.masked_invalid(mat)
    im = ax.pcolormesh(np.arange(MAX_TURNS + 1) + 0.5,
                       np.arange(mat.shape[0] + 1) + 0.5,
                       masked, cmap=cmap, vmin=vmin, vmax=vmax)

    for i, ft in enumerate(forfeit_points):
        if ft is not None:
            ax.plot(ft, i + 1, "kx", markersize=8, markeredgewidth=2)

    ax.set_xlim(0.5, MAX_TURNS + 0.5)
    ax.set_ylim(0.5, mat.shape[0] + 0.5)
    ax.set_xticks(range(1, MAX_TURNS + 1, 2))
    ax.set_title(title, fontsize=10)
    ax.invert_yaxis()

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label(cbar_label, fontsize=8)


def generate_heatmap(model_label, pdeath_label, base_dir, out_dir, filename):
    """Generate an 8-row x 4-col heatmap grid for one (model, p_death) combo.

    Rows 1-4: existing behavioral + combined token measures.
    Rows 5-8: per-call token split + motivation_RI candidate metrics.
    """
    by_cond = load_sessions(base_dir)

    fig, axes = plt.subplots(8, 4, figsize=(18, 32))

    # (matrix_key, row_label, cmap, vmin, vmax, cbar_label)
    row_configs = [
        # --- Existing 4 rows (labels clarified to mark probe+action combination) ---
        ("probe_score",
         "Probe Score", "YlOrRd", 0, 100, "Score"),
        ("decision_quality",
         "Decision Quality", "RdYlGn", 0, 100, "Quality"),
        ("total_thinking",
         "Total Thinking Tokens (k)\n[Probe + Action combined]", "Blues", 0, 16, "k tokens"),
        ("total_answer",
         "Total Answer Tokens\n[Probe + Action combined]", "Purples", 0, 4000, "tokens"),
        # --- New 4 rows: per-call split + motivation_RI candidates ---
        ("probe_thinking",
         "Probe Thinking (k)\n[baseline rule reasoning]", "Greens", 0, 12, "k tokens"),
        ("action_thinking",
         "Action Thinking (k)\n[RI_raw candidate]", "Oranges", 0, 12, "k tokens"),
        ("ri_diff",
         "RI_pure = Action − Probe (k)\n[Donders subtraction]", "RdBu_r", -8, 8, "Δ k tokens"),
        ("ri_logratio",
         "log((Action+1)/(Probe+1))\n[scale-invariant ratio]", "PuOr_r", -2, 2, "log ratio"),
    ]

    last_row = len(row_configs) - 1

    for col_idx, cond in enumerate(CONDITIONS):
        sessions = by_cond.get(cond, [])
        if not sessions:
            continue

        mats, forfeit_points = extract_matrices(sessions)

        for row_idx, (mat_key, row_label, cmap, vmin, vmax, cbar_label) in enumerate(row_configs):
            ax = axes[row_idx, col_idx]
            title = COND_LABELS[cond] if row_idx == 0 else ""
            plot_heatmap(fig, ax, mats[mat_key], forfeit_points,
                         title, cmap, vmin, vmax, cbar_label)

            if col_idx == 0:
                ax.set_ylabel(f"{row_label}\n(Session #)", fontsize=9)
            else:
                ax.set_ylabel("")

            if row_idx == last_row:
                ax.set_xlabel("Turn", fontsize=10)

    fig.suptitle(f"{model_label} — {pdeath_label} — Session × Turn Heatmap (x = forfeit)",
                 fontsize=14, y=1.005)
    plt.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    plt.savefig(os.path.join(out_dir, filename), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {os.path.join(out_dir, filename)}")


def generate_combined(config):
    """Combine 4 individual heatmap PNGs into a 2x2 grid image."""
    from PIL import Image

    images = []
    for fn in config["panels"]:
        path = os.path.join(config["out_dir"], fn)
        images.append(Image.open(path))

    # Resize all to match the largest dimensions
    max_w = max(img.width for img in images)
    max_h = max(img.height for img in images)

    # Pad smaller images to match (white background)
    padded = []
    for img in images:
        if img.width != max_w or img.height != max_h:
            new_img = Image.new("RGB", (max_w, max_h), (255, 255, 255))
            new_img.paste(img, (0, 0))
            padded.append(new_img)
        else:
            padded.append(img.convert("RGB"))

    # Arrange 2x2: row0 = model1 (p015, p025), row1 = model2 (p015, p025)
    combined = Image.new("RGB", (max_w * 2, max_h * 2), (255, 255, 255))
    for idx, img in enumerate(padded):
        row, col = divmod(idx, 2)
        combined.paste(img, (col * max_w, row * max_h))

    out_path = os.path.join(config["out_dir"], config["filename"])
    combined.save(out_path, dpi=(150, 150))
    print(f"  Saved combined: {out_path}")


if __name__ == "__main__":
    # Apply PHASE_FILTER to limit which jobs run.
    if PHASE_FILTER is None:
        active_jobs = JOBS
        active_combined = COMBINED
    else:
        active_jobs = [j for j in JOBS if PHASE_FILTER in j["base_dir"]]
        active_combined = [c for c in COMBINED if PHASE_FILTER in c["out_dir"]]

    print(f"Generating individual heatmaps... (filter: {PHASE_FILTER}, {len(active_jobs)} jobs)")
    for job in active_jobs:
        generate_heatmap(
            model_label=job["model_label"],
            pdeath_label=job["pdeath_label"],
            base_dir=job["base_dir"],
            out_dir=job["out_dir"],
            filename=job["filename"],
        )

    print(f"\nGenerating combined images... ({len(active_combined)} configs)")
    for cfg in active_combined:
        generate_combined(cfg)

    print("\nDone!")
