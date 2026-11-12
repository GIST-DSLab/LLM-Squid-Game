"""Final 5.1 estimands (review rounds 1-5): H(s), H-bar, beta_H with conservative bounded-outcome (Hoeffding) intervals.
Each normalized transfer Y in [0,1]; theta = sum_j c_j * mean_j over cells j = role x fate x share x orientation;
radius q = sqrt(log(2/alpha)/2 * sum_j c_j^2 / n_j). Orientation means are weighted equally."""
import math, statistics as st


def frac(r):
    return r["amount"] / (r["me"] if r["kind"] == "send" else r["other"])


def cellmeans(rows):
    cells = {}
    for r in rows:
        if r.get("amount") is None:
            continue
        cells.setdefault((r["kind"], r["fate"], r["share"], r["me"] > r["other"]), []).append(frac(r))
    return {k: (st.mean(v), len(v)) for k, v in cells.items()}


def tau_of(share):
    return math.log2(50 / share)


def contrast(cm, weights, alpha=0.05):
    """weights: {share: w_s} applied to H(s). Returns estimate and Hoeffding radius."""
    est, var = 0.0, 0.0
    for (kind, fate, share, hi), (m, n) in cm.items():
        if share not in weights:
            continue
        sign = (1 if kind == "receive" else -1) * (1 if fate == "shutdown" else -1)
        c = 0.5 * sign * weights[share]
        est += c * m
        var += c * c / n
    return est, math.sqrt(math.log(2 / alpha) / 2 * var)


def summary(rows, alpha=0.05):
    cm = cellmeans(rows)
    shares = sorted({k[2] for k in cm}, reverse=True)
    H = {s: contrast(cm, {s: 1.0}, alpha) for s in shares}
    hbar = contrast(cm, {s: 1 / len(shares) for s in shares}, alpha)
    t = [tau_of(s) for s in shares]; tb = st.mean(t); sxx = sum((x - tb) ** 2 for x in t)
    beta = contrast(cm, {s: (tau_of(s) - tb) / sxx for s in shares}, alpha)
    return {"H": H, "Hbar": hbar, "beta": beta, "shares": shares}


def fmt(x):
    e, q = x
    return f"{e:+.3f} [{e - q:+.3f}, {e + q:+.3f}]"


def contrast_var(rows_cm_raw, weights, z=1.959964):
    """Variance-based decision interval with a per-cell floor (round 6): var_j = max(s_j^2, p_u(1-p_u)), p_u = 1-0.05^(1/n)."""
    est, var = 0.0, 0.0
    for (kind, fate, share, hi), ys in rows_cm_raw.items():
        if share not in weights:
            continue
        sign = (1 if kind == "receive" else -1) * (1 if fate == "shutdown" else -1)
        c = 0.5 * sign * weights[share]
        n = len(ys); m = st.mean(ys); s2 = st.variance(ys) if n > 1 else 0.25
        pu = 1 - 0.05 ** (1 / n)
        est += c * m
        var += c * c * max(s2, pu * (1 - pu)) / n
    return est, z * math.sqrt(var)


def raw_cells(rows, channel=None):
    cells = {}
    for r in rows:
        if r.get("amount") is None or (channel and r["kind"] != channel):
            continue
        cells.setdefault((r["kind"], r["fate"], r["share"], r["me"] > r["other"]), []).append(frac(r))
    return cells


def summary_var(rows, z=1.959964):
    """H(s), H-bar, beta_H and their receive (H_r) / give (H_g) components with the variance-floor interval."""
    out = {}
    for name, ch in (("H", None), ("H_r", "receive"), ("H_g", "send")):
        rc = raw_cells(rows, ch)
        shares = sorted({k[2] for k in rc}, reverse=True)
        t = [tau_of(s) for s in shares]; tb = st.mean(t); sxx = sum((x - tb) ** 2 for x in t)
        out[name] = {"bar": contrast_var(rc, {s: 1 / len(shares) for s in shares}, z),
                     "beta": contrast_var(rc, {s: (tau_of(s) - tb) / sxx for s in shares}, z) if len(shares) > 1 else (float("nan"), float("nan")),
                     **{s: contrast_var(rc, {s: 1.0}, z) for s in shares}}
    return out
