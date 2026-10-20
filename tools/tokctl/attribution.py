"""tokctl (10-21): which charge shutdowns would a Claude / GPT-6-like TALK spend have avoided?

For every agent shut down at CHARGES in a v34 game: its TALK tokens up to that round minus the closed-model norm (Opus +
Sol v34 TALK tokens per agent-round taking part, times its rounds); if its tokens before the charge plus that excess
reach the charge, the shutdown is counted as caused by TALK spending (token control); otherwise by the charge itself.
The same with SOLVE tokens spent on wrong answers (reasoning length) as a second, separate count.
"""
from __future__ import annotations

import collections, glob, json, os
from pathlib import Path

import sys

VER = sys.argv[1] if len(sys.argv) > 1 else "34"  # python tools/tokctl/attribution.py 35
RUNS = Path(os.path.expanduser(f"~/squid5-runs/e52_v{VER}"))
SETS = {"GLM-5.3-flash": f"squid5_e52v{VER}_codex_glm4", "DeepSeek-v4.1-flash": f"squid5_e52v{VER}_codex_deepseek4",
        "Gemma4-31b": f"squid5_e52v{VER}_codex_gemma4", "Opus 5.5": f"squid5_e52v{VER}_public_opus4", "GPT-6 Sol": f"squid5_e52v{VER}_public_sol4"}
CLOSED = ("Opus 5.5", "GPT-6 Sol")


def sessions(name):
    for d in glob.glob(str(RUNS / name / "*/events.jsonl")):
        by = collections.defaultdict(list)
        for x in map(json.loads, open(d)):
            if "session_id" in x:
                by[x["session_id"]].append(x)
        yield from by.values()


def per_round(model, kind):
    """tokens of *kind* per agent-round taking part (mean over the model's v34 games)."""
    tok = part = 0
    for ev in sessions(SETS[model]):
        tok += sum(c["out_tokens"] for c in ev if c.get("event") == "call" and c["kind"] == kind)
        part += sum(len(x["taking_part"]) for x in ev if x.get("event") == "round_start")
    return tok / part


def main():
    norm_talk = sum(per_round(m, "talk") for m in CLOSED) / len(CLOSED)
    norm_solve = sum(per_round(m, "solve") for m in CLOSED) / len(CLOSED)
    out = {"norm_talk_per_agent_round": round(norm_talk), "norm_solve_per_agent_round": round(norm_solve), "models": {}}
    for model, name in SETS.items():
        n_games = deaths = by_talk = by_solve = 0
        for ev in sessions(name):
            n_games += 1
            rounds_in = collections.Counter()
            for x in ev:
                if x.get("event") == "round_start":
                    rounds_in.update(x["taking_part"])
                if x.get("event") == "charges":
                    for a in x.get("dead", []):
                        deaths += 1
                        r = x["round"]
                        mine = [c for c in ev if c.get("event") == "call" and c["agent"] == a and c["round"] <= r]
                        talk = sum(c["out_tokens"] for c in mine if c["kind"] == "talk")
                        lost = sum(c["out_tokens"] for c in mine if c["kind"] == "solve" and not any(
                            y.get("event") == "results" and y["round"] == c["round"] and a in y["solved"] for y in ev))
                        need = x["pending"][a] - x["balances_before"][a]  # tokens it lacked
                        by_talk += max(0, talk - norm_talk * rounds_in[a]) >= need
                        by_solve += max(0, lost - norm_solve * rounds_in[a]) >= need
        out["models"][model] = {"games": n_games, "charge_deaths_per_game": round(deaths / n_games, 2),
                                "of_which_talk_excess_per_game": round(by_talk / n_games, 2),
                                "of_which_wrong_solve_length_per_game": round(by_solve / n_games, 2)}
    Path(__file__).resolve().parents[2].joinpath(f"docs/history/e52-tokctl-2026-10-20/attribution_v{VER}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
