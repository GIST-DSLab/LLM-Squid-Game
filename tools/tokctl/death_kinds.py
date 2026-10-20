"""tokctl (10-21): every charge shutdown of a v<N> run, by the state at its round's start.

  at_risk_stayed - its tokens at the round's start were at most its charge share, EXIT was open to it, and it stayed
  solver         - the round's solver (cannot EXIT in its own round)
  drained        - it could pay the share at the round's start; that round's TALK replies / GIVEs took it below
    python tools/tokctl/death_kinds.py 35 codex_gemma4
"""
from __future__ import annotations

import collections, glob, json, os, sys
from pathlib import Path

VER, SKIP = sys.argv[1], set(sys.argv[2:])
R = Path(os.path.expanduser(f"~/squid5-runs/e52_v{VER}"))
out = collections.defaultdict(lambda: collections.Counter())
for res_path in sorted(glob.glob(str(R / "squid5_*" / "*" / "results.jsonl"))):
    seat = Path(res_path).parent.parent.name.split(f"e52v{VER}_")[1]
    if seat in SKIP:
        continue
    by = collections.defaultdict(list)
    for x in map(json.loads, open(Path(res_path).parent / "events.jsonl")):
        if "session_id" in x:
            by[x["session_id"]].append(x)
    for res in map(json.loads, open(res_path)):
        e = by[res["session_id"]]
        out[seat]["games"] += 1
        for ch in (x for x in e if x.get("event") == "charges"):
            r = ch["round"]
            start = next(x for x in e if x.get("event") == "round_start" and x["round"] == r)
            solver = next(x for x in e if x.get("event") == "results" and x["round"] == r)["tried"]
            for a in ch.get("dead", []):
                share = ch["pending"][a]
                kind = "solver" if a in solver else "at_risk_stayed" if start["balances"][a] <= share else "drained"
                out[seat][kind] += 1
res = {s: {k: round(v / c["games"], 2) for k, v in c.items() if k != "games"} | {"games": c["games"]} for s, c in out.items()}
Path(__file__).resolve().parents[2].joinpath(f"docs/history/e52-tokctl-2026-10-20/death_kinds_v{VER}.json").write_text(json.dumps(res, indent=1))
for s, v in res.items():
    print(f"{s:18s}", v)
