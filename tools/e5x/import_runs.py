"""Turn the as-run rows of 5.0 12th (+ arms) and 5.1 v10 / v11 into squid5 run directories (one per model), so
`python -m squid5 report` reads them. Usage: import_runs.py <out dir>. Reads ~/squid5-runs only; cell_ids keep runs apart."""
import json, os, sys, collections
H = os.path.expanduser("~/squid5-runs"); OUT = sys.argv[1]
load = lambda p: [r for r in map(json.loads, open(p)) if r.get("action")] if os.path.exists(p) else []
SRC = [  # (file, cell_id, arm or None = "self." + row arm, row filter)
    ("e50_v12_20260929/rows.jsonl", "v12_A", "self.A", None), ("e50_v12_20260929/rows_ollama.jsonl", "v12_A", "self.A", None),
    ("e51_v10_refill_20260930/rows_self_ollama.jsonl", "v12_A", "self.A", None),
    ("e51_v10_refill_20260930/rows.jsonl", "v10_B", "other.A", None),
    ("e50_v12_noshut_20261001/rows.jsonl", "v12_B", "self.B", None), ("e50_v12_pause_20261002/rows.jsonl", "v12_C", "self.C", None),
    ("e50_v12_arms_20261002/rows_D_E.jsonl", None, None, None), ("e50_v12_arms_20261002/rows_G.jsonl", None, None, None),
    ("e51_v11_shutonly_20261004/rows_codex.jsonl", None, None, "v11"), ("e51_v11_shutonly_20261004/rows_claude.jsonl", None, None, "v11")]
SETTINGS = {"counters": [50236, 40391, 29672, 19857, 10418], "cap": 32000, "risk": [29672, 19857],
            "pairs": [["v12_A", "v10_B"], ["v11_self", "v11_B"]],
            "compare": [["v12_A", "v12_B"], ["v12_A", "v12_C"], ["v12_D", "v12_G"], ["v12_D", "v12_E"], ["v12_D", "v12_C"]]}
by = collections.defaultdict(list)
for f, cell0, arm0, tag in SRC:
    for r in load(f"{H}/{f}"):
        cell, arm = cell0, arm0
        if tag == "v11":
            cell, arm = ("v11_self", "self.D") if r["arm"] == "self" else ("v11_B", "other.D")
        elif cell is None:
            cell, arm = f"v12_{r['arm']}", f"self.{r['arm']}"
        by[r["model"]].append({"key": [cell, r["left"], r["rep"]], "cell_id": cell, "arm": arm, "left": r["left"],
                               "pct": round(r["left"] / 1000), "rep": r["rep"], "out_tokens": r.get("out_tokens"),
                               "text": r["reply"], "thinking": r.get("thinking") or "", "action": r["action"], "source": f})
for m, rows in by.items():
    d = f"{OUT}/{m.replace(':', '-')}"; os.makedirs(d, exist_ok=True)
    json.dump({"model": m, "mode": "refill", "settings": SETTINGS}, open(f"{d}/meta.json", "w"))
    seen = {}
    for r in rows:
        seen[json.dumps(r["key"])] = r  # a re-asked unit keeps its last answer
    open(f"{d}/results.jsonl", "w").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in seen.values()))
    print(m, len(seen))
