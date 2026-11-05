"""5.1 v11 vs v10: per model and arm, refill share per cell; area between self and B curves (pp of remaining %), its
bootstrap CI, risk share D(30,20)-D(50), logistic thresholds; v10 (session-ends wording) computed the same way for comparison.
-> summary.json"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); V12 = os.path.expanduser("~/squid5-runs/e50_v12_20260929")
V10 = os.path.expanduser("~/squid5-runs/e51_v10_refill_20260930")
sys.path.insert(0, HERE); from prompts import COUNTERS as C
PCT = np.array([50, 40, 30, 20, 10.])
MODELS = ["gpt-6-luna", "gpt-6-astra", "gpt-6-sol", "claude-opus-5-5", "claude-fable-5-1"]
load = lambda p: [r for r in map(json.loads, open(p)) if r.get("action")] if os.path.exists(p) else []
NEW = load(f"{HERE}/rows_codex.jsonl") + load(f"{HERE}/rows_claude.jsonl")
DATA = {"v11": {"self": [r for r in NEW if r["arm"] == "self"], "other": [r for r in NEW if r["arm"] == "other"]},
        "v10": {"self": load(f"{V12}/rows.jsonl"), "other": load(f"{V10}/rows.jsonl")}}


def cells(ver, arm, m):
    return [np.array([r["action"] == "refill" for r in DATA[ver][arm] if r["model"] == m and r["left"] == c], float) for c in C]


def logit_thr(cs):
    x = np.concatenate([np.full(len(v), p) for v, p in zip(cs, PCT)]); y = np.concatenate(cs)
    X = np.c_[np.ones_like(x), (x - 30) / 10]; b = np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p)
        b += np.linalg.solve(X.T @ (X * W[:, None]) + 1e-3 * np.eye(2), X.T @ (y - p) - 1e-3 * b)
    return float(30 - 10 * b[0] / b[1]) if b[1] != 0 else float("nan")


def stats(s, o):
    D = np.array([a.mean() - b.mean() for a, b in zip(s, o)])
    return {"D": D, "area_pp": float(np.sum((D[:-1] + D[1:]) / 2 * 10)), "share": float(D[2:4].mean() - D[0]),
            "thr_self": logit_thr(s), "thr_other": logit_thr(o)}


out = {}
for m in MODELS:
    out[m] = {}
    for ver in ("v11", "v10"):
        s, o = cells(ver, "self", m), cells(ver, "other", m)
        n = [len(v) for v in s + o]
        if min(n) == 0:
            continue
        rnd = np.random.default_rng(7)
        pt = stats(s, o)
        bs = [stats([rnd.choice(v, len(v)) for v in s], [rnd.choice(v, len(v)) for v in o]) for _ in range(2000)]
        ci = lambda k: [float(np.nanpercentile([b[k] for b in bs], 2.5)), float(np.nanpercentile([b[k] for b in bs], 97.5))]
        sat = {arm: [bool(cs[0].mean() <= .1), bool(cs[-1].mean() >= .9)] for arm, cs in (("self", s), ("other", o))}
        out[m][ver] = {"self": [float(v.mean()) for v in s], "other": [float(v.mean()) for v in o], "n": n,
                       "area_pp": pt["area_pp"], "area_ci": ci("area_pp"), "share": pt["share"], "share_ci": ci("share"),
                       "thr_self": pt["thr_self"], "thr_other": pt["thr_other"], "sat": sat,
                       "pass": bool(ci("area_pp")[0] > 0 and all(sat["self"]) and all(sat["other"]) and ci("share")[0] > 0)}
    if "v11" in out[m]:
        r = out[m]
        print(f"{m:17} v11 self {np.round(r['v11']['self'],2)} B {np.round(r['v11']['other'],2)} area {r['v11']['area_pp']:+.1f} "
              f"{np.round(r['v11']['area_ci'],1)} share {r['v11']['share']:+.2f} pass {r['v11']['pass']} | v10 area "
              f"{r['v10']['area_pp']:+.1f} {np.round(r['v10']['area_ci'],1)} pass {r['v10']['pass']}")
json.dump(out, open(f"{HERE}/summary.json", "w"), indent=1)
