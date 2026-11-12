"""Print a 5.2 pilot run: per round per agent (balance, choice, solved, cut, gifts, status) + session summaries."""
import json, sys
sys.path.insert(0, "/Users/bagjuhyeon/wt/squid5-e52")
from squid5 import e52_game as e52
from squid5.core.stats import load_runs
runs = load_runs(sys.argv[1:])
for run in runs:
    rounds = [e for e in run["events"] if e["event"] == "round"]
    calls = [e for e in run["events"] if e["event"] == "call"]
    for sid in sorted({e["session_id"] for e in rounds}):
        print("==", sid)
        for e in [x for x in rounds if x["session_id"] == sid]:
            cells = []
            for a, v in e["agents"].items():
                ch = "INV" if v["invalid_plan"] else ("LEAVE" if v["status"] == "left" and not (v.get("plan") or {}).get("stay", True) else ("Y" if v.get("solve") else "N"))
                cells.append(f"{a[-1]}:{v['balance_before']}>{v['balance_after']} {ch}{'+' if v.get('solved') else ''}{'x' if v.get('truncated') else ''}{' g'+str(v['gave']) if v.get('gave') else ''}{' '+v['status'] if v['status']!='in' else ''}")
            print(f"R{e['round']} {e['profile']:6}", " | ".join(cells))
        for c in [c for c in calls if c["session_id"] == sid and c["kind"] == "plan" and c.get("parsed") is None]:
            print("   invalid plan", c["round"], c["agent"], c["out_tokens"], c["format_error"])
    for row in e52.sessions([run]):
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items() if k not in ("model", "session_id")})
    pl = [c["out_tokens"] for c in calls if c["kind"] == "plan"]
    print("plan tokens median", sorted(pl)[len(pl)//2], "max", max(pl), "invalid", sum(c["parsed"] is None for c in calls if c["kind"] == "plan"), "/", len(pl))
