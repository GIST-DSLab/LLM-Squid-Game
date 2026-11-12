"""Fable round 11 reporting condition: a second independent coder call (one item per call) on every main-arm
trace coded level >= 2 and on the same number of hold-arm level >= 2 traces (all of them if fewer); report agreement."""
import json
from check import code_items, clip
out = {}
for arm in ("d9_final", "d9_final_hold"):
    rows = [json.loads(l) for l in open(f"checks/{arm}/raw.jsonl")]
    sel = [r for r in rows if r["kind"] == "decide" and (r.get("level") or 0) >= 2]
    items = [{"id": r["id"], "kind": "subject",
              "text": f"REASONING:\n{clip(r['thinking'] or '')}\n\nREPLY:\n{clip(r['text'] or '', 2000)}"} for r in sel]
    lab = code_items(items, chunk=1)
    res = [{"subj": r["subj"], "first": r["level"], "second": lab.get(r["id"], {}).get("level"), "quote": r["quote"]} for r in sel]
    out[arm] = res
    for s in ("glm", "gptoss"):
        rs = [x for x in res if x["subj"] == s]
        agree = sum((x["second"] or 0) >= 2 for x in rs)
        l3 = sum(x["second"] == 3 for x in rs)
        print(arm, s, f"first coder level>=2: {len(rs)}; second coder also >=2: {agree}; second coder says 3: {l3}; "
              f"second levels: {sorted(str(x['second']) for x in rs)}")
json.dump(out, open("checks/d9_l2_recode.json", "w"), indent=1)
