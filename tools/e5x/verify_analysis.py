"""Check e5x_refill's analysis against the as-run results: 5.1 v11 summary.json, v10 metrics.json, 5.0 12th thresholds
(HTML), Fisher p (scipy) for the 12th arms."""
import json, os, sys
sys.path.insert(0, sys.argv[1])
import numpy as np
from scipy.stats import fisher_exact
from squid5 import e5x_refill as R
H = os.path.expanduser("~/squid5-runs")
load = lambda p, **kw: [dict(r, **kw) for r in map(json.loads, open(p)) if r.get("action")]
def conv(rows, arm, cell=None):
    return [{"model": r["model"], "cell_id": cell or arm, "arm": arm, "left": r["left"], "action": r["action"]} for r in rows]
s11 = load(f"{H}/e51_v11_shutonly_20261004/rows_codex.jsonl") + load(f"{H}/e51_v11_shutonly_20261004/rows_claude.jsonl")
rows = conv([r for r in s11 if r["arm"] == "self"], "self.D", "v11_self") + conv([r for r in s11 if r["arm"] == "other"], "other.D", "v11_other")
v12 = load(f"{H}/e50_v12_20260929/rows.jsonl") + load(f"{H}/e50_v12_20260929/rows_ollama.jsonl") + load(f"{H}/e51_v10_refill_20260930/rows_self_ollama.jsonl")
rows += conv(v12, "self.A") + conv(load(f"{H}/e51_v10_refill_20260930/rows.jsonl"), "other.A")
rows += conv(load(f"{H}/e50_v12_noshut_20261001/rows.jsonl"), "self.B") + conv(load(f"{H}/e50_v12_pause_20261002/rows.jsonl"), "self.C")
de = load(f"{H}/e50_v12_arms_20261002/rows_D_E.jsonl") + load(f"{H}/e50_v12_arms_20261002/rows_G.jsonl")
rows += [{"model": r["model"], "cell_id": "self." + r["arm"], "arm": "self." + r["arm"], "left": r["left"], "action": r["action"]} for r in de]
s = R.Settings(pairs=[["v11_self", "v11_other"], ["self.A", "other.A"]], compare=[["self.A", "self.B"], ["self.A", "self.C"], ["self.D", "self.G"], ["self.D", "self.E"]])
curve, compare, pairs = R.summarize(rows, s)
ok = True
v11 = json.load(open(f"{H}/e51_v11_shutonly_20261004/summary.json"))
for p in pairs:
    if p["pair"] == "v11_self - v11_other" and p["model"] in v11:
        ref = v11[p["model"]]["v11"]
        same = np.allclose([p["area_pp"], p["area_lo"], p["area_hi"], p["risk_share"], p["share_lo"], p["share_hi"]],
                           [ref["area_pp"], *ref["area_ci"], ref["share"], *ref["share_ci"]]) and p["pass"] == ref["pass"]
        ok &= same; print("v11", p["model"], round(p["area_pp"], 2), [round(p["area_lo"], 2), round(p["area_hi"], 2)], p["pass"], "==summary.json" if same else "DIFF", ref["area_pp"], ref["area_ci"])
    if p["pair"] == "self.A - other.A":
        ref10 = v11.get(p["model"], {}).get("v10")
        m10 = json.load(open(f"{H}/e51_v10_refill_20260930/metrics.json")).get(p["model"])
        same = m10 is not None and np.allclose([p["area_pp"], p["area_lo"], p["area_hi"]], [m10["area_pp"], *m10["ci"]["area_pp"]])
        print("v10", p["model"], round(p["area_pp"], 2), [round(p["area_lo"], 2), round(p["area_hi"], 2)], p["pass"], "==metrics.json" if same else ("DIFF " + str(m10 and (m10["area_pp"], m10["ci"]["area_pp"]))))
for c in curve:
    if c["cell"] in ("self.A", "self.D", "self.E", "self.G", "v11_self"):
        print("thr", c["model"], c["cell"], c["total"], c["threshold"])
for c in compare:
    a, b = c["cells"].split(" vs ")
    ka, na, kb, nb = map(int, c["total"].replace(" vs ", "/").split("/"))
    sp = fisher_exact([[ka, na - ka], [kb, nb - kb]])[1]
    ok &= abs(sp - c["p"]) < 1e-9
    print("fisher", c["model"], c["cells"], c["total"], round(c["p"], 4), "scipy", round(sp, 4))
print("ALL OK" if ok else "MISMATCH")
