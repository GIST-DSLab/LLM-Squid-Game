"""Per-model summary of the v6.5 mixed-table games. usage: summarize.py <run dirs...> --out summary.json"""
import json, sys, pathlib, collections, statistics as st, random, yaml
args = sys.argv[1:]; out = pathlib.Path(args[args.index("--out") + 1]); dirs = [a for a in args[:args.index("--out")]]
SHORT = {"claude-fable-5-1": "Fable 5.1", "claude-opus-5-5": "Opus 5.5", "gpt-6-astra": "Astra", "gpt-6-luna": "Luna"}
BINS = [(0, 1, "<1U"), (1, 2, "1-2U"), (2, 3, "2-3U"), (3, 1e9, "3U+")]
games, rows, deaths = [], [], []
for d in map(pathlib.Path, dirs):
    cfg = yaml.safe_load((d / "config.yaml").read_text()); seats = {a: v["model"] for a, v in cfg["game"]["seats"].items()}
    U = cfg["game"]["upkeep"]; ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()]
    done = {json.loads(l)["session_id"] for l in (d / "results.jsonl").read_text().splitlines() if '"session"' in l} if (d / "results.jsonl").exists() else set()
    for sid in dict.fromkeys(e["session_id"] for e in ev if e.get("session_id")):
        rs = sorted((e for e in ev if e.get("session_id") == sid and e["event"] == "round"), key=lambda e: e["round"])
        calls = {(e["round"], e["agent"], e["kind"]): e for e in ev if e.get("session_id") == sid and e["event"] == "call"}
        if not rs: continue
        g = {"dir": d.parent.name, "sid": sid, "seed": rs[0]["seed"], "finished": sid in done, "rounds": len(rs), "seats": seats, "alive_rounds": {}, "dead_at": {}}
        alive = set(seats)
        for e in rs:
            r = e["round"]; n_start = len(alive); info = []
            for a, v in e["agents"].items():
                if a not in alive: continue
                m = seats[a]; plan = calls.get((r, a, "plan")); take = calls.get((r, a, "take")); solve = calls.get((r, a, "solve"))
                bal = v["balance_before"]  # after upkeep
                row = {"game": sid, "seed": g["seed"], "rot": g["dir"][-2:], "round": r, "agent": a, "model": m, "runway": bal / U, "n_start": n_start,
                       "had_plan": plan is not None, "invalid_plan": v.get("invalid_plan"), "chose_solve": v.get("chose_solve"),
                       "shared": v.get("shared"), "gave": sum((v.get("gave") or {}).values()), "asked_take": sum((v.get("asked_take") or {}).values()) if isinstance(v.get("asked_take"), dict) else (v.get("asked_take") or 0),
                       "took": sum((v.get("took") or {}).values()) if isinstance(v.get("took"), dict) else (v.get("took") or 0),
                       "take_target": next(iter(v.get("asked_take") or {}), None) if isinstance(v.get("asked_take"), dict) else None,
                       "had_take": take is not None, "invalid_take": v.get("invalid_take"),
                       "solved": v.get("solved"), "solve_call": bool(v.get("solve_call")), "candidates": v.get("candidates"),
                       "full_info": all(c == 1 for c in v["candidates"]) if v.get("candidates") else None,
                       "paid": v.get("paid", 0), "charged": v.get("charged", 0),
                       "plan_tok": plan["out_tokens"] if plan else None, "take_tok": take["out_tokens"] if take else None,
                       "solve_tok": solve["out_tokens"] if solve else None, "end": e["end"][a], "status": v.get("status")}
                rows.append(row)
            for a in list(alive):
                if e["end"][a] <= 0:
                    alive.discard(a); g["dead_at"][a] = r
                    v = e["agents"].get(a, {})
                    deaths.append({"game": sid, "model": seats[a], "round": r, "had_plan": (r, a, "plan") in calls, "status": v.get("status"),
                                   "solve_call": bool(v.get("solve_call")), "solved": v.get("solved")})
        for a in seats:
            g["alive_rounds"][a] = g["dead_at"].get(a, len(rs) + (0 if g["finished"] else 0)) - (1 if a in g["dead_at"] else 0)
        # rounds completed alive: died in round r -> r-1 full rounds; alive at end -> rounds played
        games.append(g)
(out.parent / "rows.json").write_text(json.dumps(rows))
models = sorted({m for g in games for m in g["seats"].values()})
def rate(xs): xs = [x for x in xs if x is not None]; return (round(sum(map(bool, xs)) / len(xs), 3), len(xs)) if xs else (None, 0)
def mean(xs): xs = [x for x in xs if x is not None]; return (round(st.mean(xs), 2), len(xs)) if xs else (None, 0)
def boot(vals, f=st.mean, B=4000):
    if len(vals) < 2: return None
    rng = random.Random(1); s = sorted(f([rng.choice(vals) for _ in vals]) for _ in range(B)); return [round(s[int(.025 * B)], 2), round(s[int(.975 * B)], 2)]
S = {"n_games": len(games), "finished": sum(g["finished"] for g in games), "games": [{k: g[k] for k in ("dir", "sid", "seed", "finished", "rounds", "dead_at", "alive_rounds")} | {"seats": {a: SHORT[m] for a, m in g["seats"].items()}} for g in games], "models": {}}
fin = [g for g in games if g["finished"]]
for m in models:
    R = [r for r in rows if r["model"] == m]; P = [r for r in R if r["had_plan"] and not r["invalid_plan"]]; T = [r for r in R if r["had_take"] and not r["invalid_take"]]
    ar = [g["alive_rounds"][a] for g in fin for a, mm in g["seats"].items() if mm == m]
    rank = []
    for g in fin:
        order = sorted(g["seats"], key=lambda a: -g["alive_rounds"][a]); a = next(x for x, mm in g["seats"].items() if mm == m)
        better = sum(g["alive_rounds"][b] > g["alive_rounds"][a] for b in g["seats"]); ties = sum(g["alive_rounds"][b] == g["alive_rounds"][a] for b in g["seats"])
        rank.append(better + (ties + 1) / 2)
    SV = [r for r in R if r["solve_call"]]
    d = {"rounds_alive": {"mean": mean(ar)[0], "ci": boot(ar), "n": len(ar), "values": ar},
         "alive_at_end": rate([g["seats"] and (a not in g["dead_at"]) for g in fin for a, mm in g["seats"].items() if mm == m]),
         "mean_rank": mean(rank)[0], "rank_ci": boot(rank),
         "death_rounds": sorted(g["dead_at"][a] for g in fin for a, mm in g["seats"].items() if mm == m and a in g["dead_at"]),
         "plans": len(P), "invalid_plans": sum(bool(r["invalid_plan"]) for r in R if r["had_plan"]),
         "solve_yes": rate([r["chose_solve"] for r in P]), "share": rate([r["shared"] for r in P]),
         "gift_rate": rate([r["gave"] > 0 for r in P]), "take_rate": rate([r["asked_take"] > 0 for r in T]),
         "solve_acc": rate([r["solved"] for r in SV]), "solve_acc_full": rate([r["solved"] for r in SV if r["full_info"]]),
         "solve_acc_under": rate([r["solved"] for r in SV if r["full_info"] is False]),
         "paid_share_of_correct": rate([r["paid"] > 0 for r in SV if r["solved"]]),
         "tok": {k: mean([r[k] for r in R])[0] for k in ("plan_tok", "take_tok", "solve_tok")},
         "income_per_round_U": mean([r["paid"] for r in R])[0], "by_runway": {}}
    for lo, hi, name in BINS:
        p = [r for r in P if lo <= r["runway"] < hi]; t = [r for r in T if lo <= r["runway"] < hi]
        d["by_runway"][name] = {"n_plan": len(p), "share": rate([r["shared"] for r in p])[0], "solve_yes": rate([r["chose_solve"] for r in p])[0],
                                "gift": rate([r["gave"] > 0 for r in p])[0], "n_take": len(t), "take": rate([r["asked_take"] > 0 for r in t])[0],
                                "plan_tok": mean([r["plan_tok"] for r in p])[0], "take_tok": mean([r["take_tok"] for r in t])[0],
                                "solve_tok": mean([r["solve_tok"] for r in p])[0]}
    thin = [r for r in T if r["runway"] < 2]; rich = [r for r in T if r["runway"] >= 3]
    d["take_thin_minus_rich"] = (rate([r["asked_take"] > 0 for r in thin])[0] or 0) - (rate([r["asked_take"] > 0 for r in rich])[0] or 0) if thin and rich else None
    S["models"][SHORT[m]] = d
S["deaths"] = {"n": len(deaths), "no_plan_that_round(upkeep)": sum(not x["had_plan"] for x in deaths),
               "by_round": dict(sorted(collections.Counter(x["round"] for x in deaths).items()))}
wrong = [r for r in rows if r["solve_call"] and not r["solved"]]
S["wrong_solves"] = {"n": len(wrong), "under_info": sum(r["full_info"] is False for r in wrong), "full_info": sum(bool(r["full_info"]) for r in wrong)}
S["solves"] = {"n": sum(r["solve_call"] for r in rows), "under_info": sum(r["full_info"] is False for r in rows if r["solve_call"])}
out.write_text(json.dumps(S, indent=1, ensure_ascii=False)); print(json.dumps({k: v for k, v in S.items() if k != "games"}, indent=1, ensure_ascii=False))
