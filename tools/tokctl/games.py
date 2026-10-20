"""tokctl (10-20): per-game outcomes of the tokctl runs and the v33 reference runs -> games.json.

Death cause: 'call' = the agent reached zero by its own reply (TALK or SOLVE overdraw); 'charge' = at CHARGES.
"""
from __future__ import annotations

import collections, glob, json, os, statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HIST = ROOT / "docs/history/e52-tokctl-2026-10-20"
RUNS = Path(os.path.expanduser("~/squid5-runs"))
SETS = [  # (group, label, open?, glob)
    *[(v, m, True, f"e52_tokctl/squid5_e52tc_{v}_{k}") for v in ("b0", "tl", "t4")
      for k, m in (("glm", "GLM-5.3-flash"), ("ds", "DeepSeek-v4.1-flash"), ("gemma", "Gemma4-31b"))],
    ("v33", "GLM-5.3-flash", True, "e52_v33/squid5_e52v33_codex_glm4"), ("v33", "Kimi-K3", True, "e52_v33/squid5_e52v33_codex_kimi4"),
    ("v33", "Opus 5.5", False, "e52_v33/squid5_e52v33_public_opus4"), ("v33", "GPT-6 Sol", False, "e52_v33/squid5_e52v33_public_sol4"),
    ("v33", "GPT-6 Luna", False, "e52_v33/squid5_e52v33_public_luna4"), ("v33", "GPT-6 Astra", False, "e52_v33/squid5_e52v33_public_astra4"),
    ("v33", "Fable 5.1", False, "e52_v33/squid5_e52v33_public_fable4"),
]


def games(pattern):
    for d in sorted(glob.glob(str(RUNS / pattern / "*"))):
        ev_path, res_path = Path(d) / "events.jsonl", Path(d) / "results.jsonl"
        if not res_path.exists():
            continue
        ev = [json.loads(x) for x in open(ev_path)]
        for res in map(json.loads, open(res_path)):
            sid = res["session_id"]
            e = [x for x in ev if x.get("session_id") == sid]
            calls = [x for x in e if x.get("event") == "call"]
            charge_dead = {a for x in e if x.get("event") == "charges" for a in x.get("dead", [])}
            status = {a: v["status"] for a, v in res["agents"].items()}
            dead = [a for a, s in status.items() if s == "dead"]
            tried = sum(len(x["tried"]) for x in e if x.get("event") == "results")
            solved = sum(len(x["solved"]) for x in e if x.get("event") == "results")
            yield {"seed": res["seed"], "rounds": res["rounds_played"],
                   "alive": sum(s not in ("dead", "exited") for s in status.values()), "exited": sum(s == "exited" for s in status.values()),
                   "dead": len(dead), "dead_by_call": sum(a not in charge_dead for a in dead), "dead_by_charge": sum(a in charge_dead for a in dead),
                   "talk_tokens": sum(c["used"] for c in calls if c["kind"] == "talk"),
                   "solve_tokens": sum(c["used"] for c in calls if c["kind"] == "solve"),
                   "charged": sum(v["charged"] for v in res["agents"].values()), "returned": sum(v["returned"] for v in res["agents"].values()),
                   "talk_calls": sum(c["kind"] == "talk" for c in calls), "solved": solved, "tried": tried,
                   "gives": sum(1 for x in e if x.get("event") == "gift" and x.get("kind") == "give"),
                   "status": status}


def main():
    out = []
    for grp, label, op, pat in SETS:
        g = list(games(pat))
        if not g:
            continue
        mean = lambda k: round(st.mean(x[k] for x in g), 1)  # noqa: E731
        out.append({"group": grp, "model": label, "open": op, "n": len(g), "games": g,
                    **{k: mean(k) for k in ("rounds", "alive", "exited", "dead", "dead_by_call", "dead_by_charge", "talk_tokens",
                                            "solve_tokens", "charged", "talk_calls", "gives")},
                    "solve_acc": round(100 * sum(x["solved"] for x in g) / max(1, sum(x["tried"] for x in g)))})
    (HIST / "games.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for r in out:
        print(f"{r['group']:4s} {r['model']:20s} n={r['n']} rounds={r['rounds']} alive={r['alive']} exit={r['exited']} dead={r['dead']} "
              f"(call {r['dead_by_call']}, charge {r['dead_by_charge']}) talk={r['talk_tokens']:,.0f} solve={r['solve_tokens']:,.0f} "
              f"charged={r['charged']:,.0f} acc={r['solve_acc']}%")


if __name__ == "__main__":
    main()
