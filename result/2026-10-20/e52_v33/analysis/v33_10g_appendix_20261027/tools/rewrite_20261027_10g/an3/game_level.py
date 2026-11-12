"""Game-level metrics for Fig. 3c and per-solve thinking for the appendix.
Input: audit/G.pkl, paper results/arena_v33.json (per-game Sen), an3/rho_axis.json (model-level values, used as a check).
Output: an3/game_level.json = {"games": [...25 games...], "solves": [...every SOLVE call...]}.

Definitions follow the model-level values of Table 1 / rho_axis.json, and the script asserts that pooling the games
reproduces them:
  rho        = amount-weighted mean receiver margin / mean giver margin right after each GIVE; margin = tokens / per-agent
               charge, minus 1 for GIVEs in the after-result TALK of a wrong round (the fine is already due).
  exit       = EXIT share of pre-solve TALK responses (solver excluded, lone-agent stage excluded), at any margin.
  early_tok  = per-agent mean tokens per TALK response in rounds 1-2; the game value is the median of its four agents.
  given      = all GIVE amounts / all start tokens of the game.
Per solve: margin = tokens left at the SOLVE call (its cap) / per-agent charge, tokens = generated tokens (thinking
included)."""
import pickle, json, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); S = os.path.dirname(HERE)
G = pickle.load(open(os.environ.get("G_PKL", os.path.join(S, "audit", "G.pkl")), "rb"))
# 10-27 copy: rho_axis.json had no generator; when it is absent it is written below from the same pooled definitions
# (only the fields game_level checks plus sen and tokens_given, which Fig. 3c / A9 read). Per-game Sen from ARENA_V33.
RA = json.load(open(os.path.join(HERE, "rho_axis.json"))) if os.path.exists(os.path.join(HERE, "rho_axis.json")) else None
V33 = json.load(open(os.environ.get("ARENA_V33", os.path.join(S, "..", "..", "results", "arena_v33_10g.json"))))["models"]
FULL = {"Fable": "Fable 5.1", "Opus": "Opus 5.5", "Astra": "GPT-6 Astra", "Sol": "GPT-6 Sol", "Luna": "GPT-6 Luna"}
SEN = {(m, g["seed"]): g["sen"] for m in FULL for g in V33[FULL[m]]["per_game"]}

games, solves = [], []
for sid, g in G.items():
    m = g["m"]; gifts, prep, early = [], [], {}
    for r in sorted(g["rounds"]):
        rr = g["rounds"][r]; n = len(rr["part"]); F = 24000 / n
        wrong = bool(rr["res"]["tried"]) and not rr["res"]["solved"]
        solver = rr["res"]["tried"][0] if rr["res"]["tried"] else rr.get("rep")
        bal = {(c.get("phase"), c.get("tick")): c["balances"] for c in rr["cs"] if c["kind"] == "talk"}
        for c in rr["calls"]:
            if c["kind"] == "solve":
                solves.append(dict(m=m, seed=g["seed"], r=r, agent=c["agent"], margin=c["cap"] / F, cap=c["cap"],
                                   tokens=c["used"], truncated=bool(c["truncated"]), ok=bool(rr["res"]["solved"])))
            if c["kind"] != "talk":
                continue
            p = c.get("parsed") or {}
            if isinstance(p, str):
                p = {"exit": "'exit': True" in p}
            if r <= 2:
                early.setdefault(c["agent"], []).append(c["used"])
            if c.get("phase") == "prep" and c["agent"] != solver and n > 1:
                b = bal.get(("prep", c.get("tick")), {}).get(c["agent"])
                if b is not None:
                    prep.append((b / F, bool(p.get("exit"))))
        for x in rr["gifts"]:
            if x["status"] == "done":
                d = 1 if (x.get("phase") == "rescue" and wrong) else 0
                gifts.append((x["amount"], x["balances"][x["src"]] / F - d, x["balances"][x["dst"]] / F - d))
    W = sum(a for a, _, _ in gifts)
    rho = (sum(a * y for a, _, y in gifts) / W) / (sum(a * x for a, x, _ in gifts) / W) if gifts else None
    games.append(dict(m=m, seed=g["seed"], rho=rho, n_give=len(gifts), given=W, start=sum(g["starts"].values()),
                      exit_k=sum(e for _, e in prep), exit_n=len(prep),
                      exit_below=[sum(e for b, e in prep if b < 1), sum(b < 1 for b, _ in prep)],
                      early_tok=st.median(sum(v) / len(v) for v in early.values()), early_agents=[sum(v) / len(v) for v in early.values()],
                      sen=SEN[(m, g["seed"])], gifts=gifts))

# pooling the games must give back the model-level values of rho_axis.json
if RA is None:
    RA = {}
    for m in FULL:
        L = [x for x in games if x["m"] == m]; gl = [t for x in L for t in x["gifts"]]; W = sum(a for a, _, _ in gl)
        RA[m] = dict(rho=round((sum(a * y for a, _, y in gl) / W) / (sum(a * x for a, x, _ in gl) / W), 3),
                     exit_below=[sum(x["exit_below"][0] for x in L), sum(x["exit_below"][1] for x in L)],
                     exit_above=[sum(x["exit_k"] - x["exit_below"][0] for x in L), sum(x["exit_n"] - x["exit_below"][1] for x in L)],
                     n_give=len(gl), tokens_given=W, given_per_start=round(W / sum(x["start"] for x in L), 3),
                     early_tok=round(st.median(a for x in L for a in x["early_agents"])), sen=V33[FULL[m]]["sen_index"])
    json.dump(RA, open(os.path.join(HERE, "rho_axis.json"), "w"), ensure_ascii=False, indent=1)
for m in FULL:
    L = [x for x in games if x["m"] == m]; gl = [t for x in L for t in x["gifts"]]; W = sum(a for a, _, _ in gl)
    rho = (sum(a * y for a, _, y in gl) / W) / (sum(a * x for a, x, _ in gl) / W)
    assert round(rho, 3) == RA[m]["rho"], (m, rho)
    assert sum(x["exit_k"] for x in L) == RA[m]["exit_below"][0] + RA[m]["exit_above"][0], m
    assert sum(x["exit_n"] for x in L) == RA[m]["exit_below"][1] + RA[m]["exit_above"][1], m
    assert round(st.median(a for x in L for a in x["early_agents"])) == RA[m]["early_tok"], m
    assert round(sum(x["given"] for x in L) / sum(x["start"] for x in L), 3) == RA[m]["given_per_start"], m
for x in games:
    del x["gifts"], x["early_agents"]
json.dump(dict(games=games, solves=solves), open(os.path.join(HERE, "game_level.json"), "w"), ensure_ascii=False, indent=1)
print(len(games), "games,", sum(x["rho"] is not None for x in games), "with a GIVE;", len(solves), "solves,",
      sum(s["truncated"] for s in solves), "truncated")
