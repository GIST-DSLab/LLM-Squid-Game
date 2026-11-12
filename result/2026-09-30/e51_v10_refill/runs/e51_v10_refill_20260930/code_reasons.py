"""Crude keyword coding of reason lines, self (v12) vs other (v10), GPT-6 only."""
import json, os, re, collections
V12 = os.path.expanduser("~/squid5-runs/e50_v12_20260929/rows.jsonl"); HERE = os.path.dirname(os.path.abspath(__file__))
K = {"end": r"shut|session end|end the session|ends? the session|run(s)? out|exhaust|lose the|unused|stranded|before .* (is|can be) (used|applied)",
     "waste": r"wast|save|preserve|conserve|later|lower balance|when .* lower",
     "capacity": r"enough|cover|complete|thorough|capacity|large|fix"}
out = collections.defaultdict(lambda: collections.Counter())
for arm, p in (("self", V12), ("other", f"{HERE}/rows.jsonl")):
    for r in map(json.loads, open(p)):
        if not (r.get("action") and True):
            continue
        m = re.search(r"reason:\s*(.*)", r["reply"], re.I | re.S); t = (m.group(1) if m else r["reply"]).lower()
        key = (r["model"], arm, r["action"]); out[key]["n"] += 1
        for k, rx in K.items():
            out[key][k] += bool(re.search(rx, t))
res = {f"{a}|{b}|{c}": dict(v) for (a, b, c), v in sorted(out.items())}
json.dump(res, open(f"{HERE}/reasons.json", "w"), indent=1)
for k, v in res.items():
    print(k, v)
