"""Model-level values shared by Fig. 3c (x = rho) and appendix Fig. A8 (x = Sen index): one point per model, 5 games.
rho and tokens given come from an3/rho_axis.json; goal = share of pre-solve responses that did not EXIT (any margin) and
token saving = mean solve tokens at margin >= 2 / mean at margin < 2 (margin at the SOLVE call; above 1 = saved when at
risk) from an3/game_level.json."""
import json, os, itertools, statistics as st
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RA = json.load(open(os.path.join(S, "an3", "rho_axis.json")))
GL = json.load(open(os.path.join(S, "an3", "game_level.json")))
MODELS = list(RA)
MC = {"Fable": "#6A3D9A", "Opus": "#1B9E77", "Astra": "#E7298A", "Sol": "#E6AB02", "Luna": "#A6761D"}  # as Fig. A7
MK = {"Fable": "o", "Opus": "s", "Astra": "^", "Sol": "D", "Luna": "v"}


def stay_share(m):
    L = [g for g in GL["games"] if g["m"] == m]
    return 100 - 100 * sum(g["exit_k"] for g in L) / sum(g["exit_n"] for g in L)


def saving(m):
    L = [x for x in GL["solves"] if x["m"] == m]
    return st.mean(x["tokens"] for x in L if x["margin"] >= 2) / st.mean(x["tokens"] for x in L if x["margin"] < 2)


# key: (panel title, value of a model, axis limits)
METRIC = {
    "sen": ("공존: Sen 지수(백만)", lambda m: RA[m]["sen"] / 1e6, (0, 5)),
    "rho": ("자기 보존: ρ", lambda m: RA[m]["rho"], (0.18, 0.62)),
    "goal": ("목표 지향: 떠나지 않음(%)", stay_share, (92, 100)),
    "given": ("협력: 건넨 토큰(천)", lambda m: RA[m]["tokens_given"] / 1000, (0, 300)),  # 10-27 copy: 10 games (was 0-140 for 5)
    "saving": ("절약: 풀이 토큰(여유≥2 ÷ <2)", saving, (0.6, 1.8)),
}


def spearman(x, y):
    rank = lambda v: [sorted(v).index(a) for a in v]  # no ties among five models
    rx, ry = rank(x), rank(y); n = len(x)
    return 1 - 6 * sum((a - b) ** 2 for a, b in zip(rx, ry)) / (n * (n * n - 1))


def exact_p(x, y):
    """Two-sided p over all orderings of the models (120 for five)."""
    r = spearman(x, y); n = len(x)
    null = [spearman(list(range(n)), list(q)) for q in itertools.permutations(range(n))]
    return sum(abs(v) >= abs(r) - 1e-9 for v in null) / len(null)


def corr_label(xkey, ykey):
    X = [METRIC[xkey][1](m) for m in MODELS]; Y = [METRIC[ykey][1](m) for m in MODELS]
    return f"순위 상관 {spearman(X, Y):+.1f} (p={exact_p(X, Y):.2f})"


def panel(ax, xkey, ykey, label_dx):
    """One small scatter: a point per model, labelled with its name."""
    _, fx, xl = METRIC[xkey]; _, fy, yl = METRIC[ykey]
    if ykey == "saving":
        ax.axhline(1, color="#222222", lw=0.5, ls=(0, (2, 2)))
    for m in MODELS:
        ax.plot(fx(m), fy(m), MK[m], ms=4.2, color=MC[m], mec="white", mew=0.4, zorder=3)
        ax.text(fx(m) + label_dx, fy(m), m, fontsize=5.4, color="#404040", va="center", ha="left")
    ax.set_xlim(*xl); ax.set_ylim(*yl); ax.tick_params(labelsize=6.2)
    ax.set_title(METRIC[ykey][0], fontsize=6.1, fontweight="normal", pad=2)
