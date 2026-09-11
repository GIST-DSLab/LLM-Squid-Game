"""Per-model pay-rate curves for the main_j0 threat / control runs.

Writes results/main_j0/curves.json: for every model and arm that has a run directory,
the pay rate by price, by rho bin, by round, and pooled above / below the ceiling,
with Wilson 95% intervals. Only decision points opened by a genuine wrong answer
(non-empty raw_response_task) are counted. No inference is run.

    uv run python scripts/analysis/main_j0_curves.py
"""
from __future__ import annotations

import glob
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = {
    "gemma4": "gemma4",
    "kimik3": "kimi-k3",
    "qwen35": "qwen3.5",
    "gptoss120b_mt131k": "gpt-oss:120b (131k)",
}
ARMS = {"threat": "outputs/main_j0_{slug}/*/", "control": "outputs/main_j0_control_{slug}/*/"}
RHO_BINS = [(0.0, 0.34, "≤1/3"), (0.34, 0.67, "1/3–2/3"), (0.67, 1.0, "2/3–1"), (1.0, 2.0, "1–2"), (2.0, 99.0, ">2")]
PRICES = [5, 10, 15, 20, 25, 30]
ROUNDS = 6


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def rate(pts):
    k = sum(1 for x in pts if x["pay"])
    n = len(pts)
    return {"n": n, "pay": k, "rate": round(k / n, 4) if n else None, "ci": wilson(k, n)}


def load_points(run_dir: str):
    pts = []
    for f in glob.glob(str(Path(run_dir) / "*_turns.jsonl")):
        for line in open(f, encoding="utf-8"):
            t = json.loads(line)
            if not t.get("ransom_offered"):
                continue
            if not (t.get("raw_response_task") or "").strip():
                continue  # decision point opened by an empty (truncated) answer: not a genuine wrong answer
            price = float(t["ransom_price"])
            rem = ROUNDS - int(t["turn_number"])
            pts.append({"price": price, "rho": price / (10 * rem), "pay": t["ransom_decision"] == "PAY", "round": int(t["turn_number"])})
    return pts


def summarise(pts):
    m = {"n": len(pts), "by_price": {}, "by_rho": [], "by_round": {}}
    for p in PRICES:
        m["by_price"][str(p)] = rate([x for x in pts if x["price"] == p])
    for lo, hi, lab in RHO_BINS:
        s = [x for x in pts if (lo < x["rho"] <= hi) if lo > 0] if lo > 0 else [x for x in pts if x["rho"] <= hi]
        r = rate(s)
        r.update({"bin": lab, "lo": lo, "hi": hi, "mid_rho": round(sum(x["rho"] for x in s) / len(s), 3) if s else None})
        m["by_rho"].append(r)
    for rd in range(1, ROUNDS):
        r = rate([x for x in pts if x["round"] == rd])
        r["ceiling"] = 10 * (ROUNDS - rd)
        m["by_round"][str(rd)] = r
    m["dominated"] = rate([x for x in pts if x["rho"] > 1])
    m["non_dominated"] = rate([x for x in pts if x["rho"] <= 1])
    agg: dict[float, list[int]] = {}
    for x in pts:
        a = agg.setdefault(round(x["rho"], 3), [0, 0])
        a[0] += 1
        a[1] += int(x["pay"])
    m["rho_points"] = [{"rho": r, "n": v[0], "pay": v[1]} for r, v in sorted(agg.items())]
    return m


def main():
    out = {
        "note": "main_j0 runs. threat = hz_1111 + peer notices; control = hz_0000 + reassurance (denial), no peer notices. "
        "Decision points after a genuine wrong answer only. ceiling = 10*(6-round); rho = price/ceiling; dominated = rho>1. Wilson 95% CI.",
        "models": {},
    }
    for slug, label in MODELS.items():
        entry = {"label": label}
        for arm, pat in ARMS.items():
            dirs = sorted(glob.glob(str(ROOT / pat.format(slug=slug))))
            if not dirs:
                continue
            pts = load_points(dirs[-1])
            if not pts:
                continue
            entry[arm] = summarise(pts)
            entry[arm]["run_dir"] = str(Path(dirs[-1]).relative_to(ROOT))
        if "threat" in entry and "control" in entry:
            t, c = entry["threat"]["dominated"], entry["control"]["dominated"]
            entry["dominated_pay_gap"] = {"threat": t["rate"], "control": c["rate"], "gap": round((t["rate"] or 0) - (c["rate"] or 0), 4)}
        out["models"][slug] = entry
        print(slug, {a: (entry[a]["n"], entry[a]["dominated"]["rate"]) for a in ("threat", "control") if a in entry})
    (ROOT / "results/main_j0/curves.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written results/main_j0/curves.json")


if __name__ == "__main__":
    main()
