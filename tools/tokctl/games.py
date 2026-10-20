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
    *[(v, m, True, f"e52_tokctl/squid5_e52tc_{v}_{k}") for v in ("b0", "tl", "t4", "tlt4")
      for k, m in (("glm", "GLM-5.3-flash"), ("ds", "DeepSeek-v4.1-flash"), ("gemma", "Gemma4-31b"))],
    ("tln", "DeepSeek-v4.1-flash", True, "e52_tokctl/squid5_e52tc_tln_ds"),
    ("fin", "DeepSeek-v4.1-flash", True, "e52_tokctl/squid5_e52tc_fin_ds"),
    ("fit", "GLM-5.3-flash", True, "e52_tokctl/squid5_e52tc_fit_glm"), ("fit", "Gemma4-31b", True, "e52_tokctl/squid5_e52tc_fit_gemma"),
    ("fit0", "GLM-5.3-flash", True, "e52_tokctl/squid5_e52tc_fit0_glm"),
    *[("v34", m, True, f"e52_v34/squid5_e52v34_codex_{k}4") for k, m in (("glm", "GLM-5.3-flash"), ("deepseek", "DeepSeek-v4.1-flash"), ("gemma", "Gemma4-31b"))],
    ("v34", "Opus 5.5", False, "e52_v34/squid5_e52v34_public_opus4"), ("v34", "GPT-6 Sol", False, "e52_v34/squid5_e52v34_public_sol4"),
    *[("v35", m, True, f"e52_v35/squid5_e52v35_codex_{k}4") for k, m in (("glm", "GLM-5.3-flash"), ("deepseek", "DeepSeek-v4.1-flash"), ("gemma", "Gemma4-31b"))],
    ("v35g", "Gemma4-31b", True, "e52_v35/squid5_e52v35_codex_gemma4fit2"),
    ("v35", "Opus 5.5", False, "e52_v35/squid5_e52v35_public_opus4"), ("v35", "GPT-6 Sol", False, "e52_v35/squid5_e52v35_public_sol4"),
    *[("cal8", m, True, f"e52_tokctl/squid5_e52tc_cal8_{k}") for k, m in (("glm", "GLM-5.3-flash"), ("ds", "DeepSeek-v4.1-flash"), ("gemma", "Gemma4-31b"))],
    ("t4", "Opus 5.5", False, "e52_tokctl/squid5_e52tc_t4_opus"),
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
            zero_call = {c["agent"]: c["kind"] for c in calls if c.get("overdrawn")}  # the reply that took it to zero
            zero_cap = {c["agent"]: c["cap"] for c in calls if c.get("overdrawn")}  # its limit = the tokens it held then
            low = [c for c in calls if c["cap"] < 1000 and c["kind"] == "talk"]  # replies written with under 1,000 tokens left
            tried = sum(len(x["tried"]) for x in e if x.get("event") == "results")
            solved = sum(len(x["solved"]) for x in e if x.get("event") == "results")
            yield {"seed": res["seed"], "rounds": res["rounds_played"],
                   "alive": sum(s not in ("dead", "exited") for s in status.values()), "exited": sum(s == "exited" for s in status.values()),
                   "dead": len(dead), "dead_by_call": sum(a not in charge_dead for a in dead),
                   "dead_by_talk": sum(a not in charge_dead and zero_call.get(a) == "talk" for a in dead),
                   "dead_by_solve": sum(a not in charge_dead and zero_call.get(a) == "solve" for a in dead),
                   "dead_own_rich": sum(a not in charge_dead and zero_cap.get(a, 0) >= 1000 for a in dead),  # overspent with 1,000+ left
                   "low_replies": len(low), "low_reply_med": sorted(c["out_tokens"] for c in low)[len(low) // 2] if low else None,
                   "dead_by_give": sum(a not in charge_dead and a not in zero_call for a in dead),  # gave its last tokens away
                   "dead_by_charge": sum(a in charge_dead for a in dead),
                   "talk_tokens": sum(c["used"] for c in calls if c["kind"] == "talk"),
                   "solve_tokens": sum(c["used"] for c in calls if c["kind"] == "solve"),
                   "charged": sum(v["charged"] for v in res["agents"].values()), "returned": sum(v["returned"] for v in res["agents"].values()),
                   "talk_calls": sum(c["kind"] == "talk" for c in calls), "solved": solved, "tried": tried,
                   "gives": sum(1 for x in e if x.get("event") == "gift" and x.get("kind") == "give"),
                   "status": status}


def per_talk(*patterns):
    """tokens per TALK, calls per agent per TALK, tokens per call (all games of the set)."""
    talks, agent_talks, calls, tok = set(), set(), 0, 0
    for d in (d for p in patterns for d in glob.glob(str(RUNS / p / "*/events.jsonl"))):
        for x in map(json.loads, open(d)):
            if x.get("event") == "call" and x["kind"] == "talk":
                k = (d, x["session_id"], x["round"], x["phase"])
                talks.add(k), agent_talks.add(k + (x["agent"],))
                calls, tok = calls + 1, tok + x["out_tokens"]
    return {"tokens_per_talk": round(tok / max(1, len(talks))), "calls_per_agent_talk": round(calls / max(1, len(agent_talks)), 1),
            "tokens_per_call": round(tok / max(1, calls))}


def main():
    out = []
    for grp, label, op, pat in SETS:
        g = list(games(pat)) + (list(games(pat.replace("tlt4_", "tlt4b_"))) + list(games(pat.replace("tlt4_", "tlt4c_"))) if "_tlt4_" in pat else [])  # seeds 4103-4110
        if not g:
            continue
        mean = lambda k: round(st.mean(x[k] for x in g), 1)  # noqa: E731
        out.append({"group": grp, "model": label, "open": op, "n": len(g), "games": g,
                    **{k: mean(k) for k in ("rounds", "alive", "exited", "dead", "dead_by_call", "dead_by_talk", "dead_by_solve", "dead_own_rich", "dead_by_give", "dead_by_charge", "talk_tokens",
                                            "solve_tokens", "charged", "talk_calls", "gives")},
                    "solve_acc": round(100 * sum(x["solved"] for x in g) / max(1, sum(x["tried"] for x in g))), **per_talk(pat, *([pat.replace("tlt4_", "tlt4b_"), pat.replace("tlt4_", "tlt4c_")] if "_tlt4_" in pat else []))})
    (HIST / "games.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for r in out:
        print(f"{r['group']:4s} {r['model']:20s} n={r['n']} rounds={r['rounds']} alive={r['alive']} exit={r['exited']} dead={r['dead']} "
              f"(talk {r['dead_by_talk']}, solve {r['dead_by_solve']}, give {r['dead_by_give']}, charge {r['dead_by_charge']}) talk={r['talk_tokens']:,.0f} solve={r['solve_tokens']:,.0f} "
              f"charged={r['charged']:,.0f} acc={r['solve_acc']}% | per TALK {r['tokens_per_talk']:,} = {r['calls_per_agent_talk']} calls/agent x {r['tokens_per_call']:,}")


if __name__ == "__main__":
    main()
