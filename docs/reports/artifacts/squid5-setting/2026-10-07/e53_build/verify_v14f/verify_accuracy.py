"""5.2 v14f: did the per-round difficulty manipulation work in the real model games?

Reads every v14f run under RUNS (events.jsonl, meta.json), takes each agent-round with a SOLVE call, and compares the
actual accuracy with two baselines from the logged task stats (round_start.public.task.by_n[N], N = agents taking part
at the round's start):
  (a) uniform guess among the actions left: 1 / k;
  (b) a perfect counting reasoner (MAP): map_acc (realised, 0 / 1, 1 / ties) and the largest share (what MAP would score if the truth were a random consistent rule; the side of the truth is
  drawn by the designer at N = 4, so at N < 4 only the realised map_acc is the ceiling).
Also a model-free manipulation check on the 36 distinct puzzles (seeds 4000-4002 x 12 rounds; every model plays the
same puzzles), and a logistic regression accuracy ~ N + p + model with a game-cluster bootstrap.

Usage (from ~/wt/squid5-e52, so the optional engine cross-check can import squid5):
    python verify_accuracy.py [--runs ~/squid5-runs/e52_v14f] [--out <this dir>] [--boot 2000]
Writes agent_rounds.csv, by_n.csv, by_np.csv, puzzles.csv, manipulation.json, regression.json, summary.json.
"""
import argparse
import csv
import glob
import json
import math
import os
import pathlib
import random
import sys
from collections import defaultdict

MODELS = {"gpt-6-luna": "GPT-6 Luna", "gpt-6-sol": "GPT-6 Sol", "gpt-6-astra": "GPT-6 Astra",
          "claude-fable-5-1": "Fable 5.1", "claude-opus-5-5": "Opus 5.5"}
ORDER = list(MODELS)
NS, PS = (4, 3, 2, 1), (0.8, 0.7, 0.6, 0.5)


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if not n:
        return (None, None)
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def load(runs: pathlib.Path) -> tuple[list, dict]:
    """Agent-rounds with a SOLVE call, and the round_start task of every (seed, round) seen."""
    rows, puzzles = [], {}
    for f in sorted(glob.glob(str(runs / "*" / "*" / "events.jsonl"))):
        model = json.load(open(pathlib.Path(f).parent / "meta.json"))["model"]
        ev = [json.loads(line) for line in open(f)]
        seed = {e["session_id"]: e["seed"] for e in ev if e.get("event") == "session_start"}
        start = {(e["session_id"], e["round"]): e for e in ev if e.get("event") == "round_start"}
        calls = {(e["session_id"], e["round"], e["agent"]): e for e in ev
                 if e.get("event") == "call" and e.get("kind") == "solve"}
        for (sid, r), e in start.items():
            pub = e["public"]
            puzzles.setdefault((seed[sid], r), pub)
        for e in ev:
            if e.get("event") != "round":
                continue
            sid, r = e["session_id"], e["round"]
            pub = start[(sid, r)]["public"]
            n = pub["n"]
            assert n == len(start[(sid, r)]["taking_part"]) and len(pub["examples"]) == 4 * n
            st = pub["task"]["by_n"][str(n)]
            top = st["map"] if isinstance(st["map"], list) else [st["map"]]
            for a, row in e["agents"].items():
                if not row.get("solve_call"):
                    continue
                c = calls.get((sid, r, a))
                ans = c["parsed"][0] if c and isinstance(c.get("parsed"), list) and c["parsed"] else None
                truth = pub["task"]["truth"]
                assert bool(row["solved"]) == (ans == truth), (f, sid, r, a)
                rows.append({"model": model, "seed": seed[sid], "game": f"{model}:{seed[sid]}", "puzzle": f"{seed[sid]}:{r}",
                             "round": r, "agent": a,
                             "N": n, "p": pub["split"], "truth_major": pub["truth_major"], "truth": truth,
                             "answer": ans, "correct": int(bool(row["solved"])), "truncated": int(bool(row.get("truncated"))),
                             "k": st["k"], "pool": st["pool"], "uniform": st["uniform_acc"], "map_acc": st["map_acc"],
                             "map_exp": max(st["shares"].values()), "truth_share": st["truth_share"],
                             "answer_is_map": int(ans in top), "map": "|".join(top), "map_tied": int(len(top) > 1),
                             "tie_first": int(len(top) > 1 and ans == top[0])})
    return rows, puzzles


def puzzle_ci(rs: list, boot: int = 2000, seed: int = 11) -> tuple:
    """95% CI of the accuracy with the puzzle (seed, round) as the cluster: every model plays the same 36 puzzles and
    the agents of a round mostly give the same answer, so agent-rounds are far from independent."""
    by = defaultdict(list)
    for r in rs:
        by[r["puzzle"]].append(r["correct"])
    ids, rng, acc = list(by), random.Random(seed), []
    if len(ids) < 2:
        return (None, None)
    for _ in range(boot):
        pick = [rng.choice(ids) for _ in ids]
        acc.append(sum(sum(by[i]) for i in pick) / sum(len(by[i]) for i in pick))
    acc.sort()
    return (round(acc[int(0.025 * boot)], 4), round(acc[int(0.975 * boot) - 1], 4))


def cell(rs: list) -> dict:
    n = len(rs)
    if not n:
        return {"n": 0}
    k = sum(r["correct"] for r in rs)
    m = lambda key: round(sum(r[key] for r in rs) / n, 4)  # noqa: E731
    acc = k / n
    return {"n": n, "correct": k, "acc": round(acc, 4), "ci": wilson(k, n), "uniform": m("uniform"),
            "map_acc": m("map_acc"), "map_exp": m("map_exp"), "k": m("k"), "pool": m("pool"),
            "answer_is_map": m("answer_is_map"), "truncated": sum(r["truncated"] for r in rs),
            "minus_uniform": round(acc - m("uniform"), 4),
            "over_map": round(acc / m("map_acc"), 4) if m("map_acc") else None,
            "over_map_exp": round(acc / m("map_exp"), 4), "games": len({r["game"] for r in rs}),
            "puzzles": len({r["puzzle"] for r in rs}), "ci_puzzle": puzzle_ci(rs),
            "mean_round": m("round"), "mean_p": m("p"), "caution": n < 10}


def manipulation(puzzles: dict) -> dict:
    """Model-free: the realised task stats of the 36 distinct puzzles against the design."""
    out, lv = {"puzzles": len(puzzles), "n4": {}, "by_n": {}}, defaultdict(list)
    for (s, r), pub in sorted(puzzles.items()):
        lv[pub["split"]].append(pub)
    dev = []
    for p in PS:
        ps = lv[p]
        b4 = [x["task"]["by_n"]["4"] for x in ps]
        ts = [b["truth_share"] for b in b4]
        target = [p if x["truth_major"] else 1 - p for x in ps]
        major = sum(x["truth_major"] for x in ps)
        out["n4"][str(p)] = {"rounds": len(ps), "k_eq_2": sum(b["k"] == 2 for b in b4),
                             "pool_min": min(b["pool"] for b in b4), "pool_max": max(b["pool"] for b in b4),
                             "pool_in_band": sum(10 <= b["pool"] <= 14 for b in b4),
                             "max_abs_share_err": round(max(abs(t - g) for t, g in zip(ts, target)), 4),
                             "truth_major": major, "truth_major_rate": round(major / len(ps), 4),
                             "truth_major_ci": wilson(major, len(ps)),
                             "map_acc_mean": round(sum(b["map_acc"] for b in b4) / len(b4), 4),
                             "map_exp_mean": round(sum(max(b["shares"].values()) for b in b4) / len(b4), 4)}
        for x in ps:
            b = x["task"]["by_n"]["4"]
            if b["k"] != 2 or not 10 <= b["pool"] <= 14:
                dev.append(f"p={p}: k={b['k']} pool={b['pool']}")
    out["n4_deviations"] = dev
    for n in NS:
        bs = [pub["task"]["by_n"][str(n)] for pub in puzzles.values()]
        kd = defaultdict(int)
        for b in bs:
            kd[b["k"]] += 1
        pools = sorted(b["pool"] for b in bs)
        out["by_n"][str(n)] = {"k_dist": {str(k): kd[k] for k in sorted(kd)}, "k_mean": round(sum(b["k"] for b in bs) / len(bs), 3),
                               "pool_median": pools[len(pools) // 2], "pool_min": pools[0], "pool_max": pools[-1],
                               "uniform_mean": round(sum(b["uniform_acc"] for b in bs) / len(bs), 4),
                               "map_acc_mean": round(sum(b["map_acc"] for b in bs) / len(bs), 4),
                               "map_exp_mean": round(sum(max(b["shares"].values()) for b in bs) / len(bs), 4),
                               "truth_share_mean": round(sum(b["truth_share"] for b in bs) / len(bs), 4),
                               "map_flips_vs_n4": sum(pub["task"]["by_n"][str(n)]["map_right"] != pub["task"]["by_n"]["4"]["map_right"]
                                                      for pub in puzzles.values())}
    return out


def engine_check(puzzles: dict, runs: pathlib.Path) -> dict:
    """Optional: recompute task_stats with the engine and compare to the log (needs squid5 importable); profiles from meta.json."""
    sys.path.insert(0, os.getcwd())  # run from ~/wt/squid5-e52
    try:
        from squid5.core.puzzle import Spec, task_stats
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "why": repr(exc)}
    st = json.load(open(next(runs.glob("*/*/meta.json"))))["settings"]
    prof, sched = st["profiles"], st["schedule"]
    specs = {k: Spec(**{**v, "size_band": tuple(v.get("size_band") or ())}) for k, v in prof.items()}
    bad = 0
    for (s, r), pub in puzzles.items():
        t = task_stats(s, r, specs[sched[r - 1]], 4, 4)
        bad += json.dumps(t, sort_keys=True) != json.dumps(pub["task"], sort_keys=True)
    return {"ran": True, "puzzles": len(puzzles), "mismatch": bad}


def logit(X: list, y: list, ridge: float = 1e-4, iters: int = 50) -> list:
    """Logistic regression by IRLS (numpy), a tiny ridge on the slopes against separation."""
    import numpy as np
    X, y = np.asarray(X, float), np.asarray(y, float)
    b = np.zeros(X.shape[1])
    pen = np.eye(X.shape[1]) * ridge
    pen[0, 0] = 0
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        w = mu * (1 - mu) + 1e-9
        step = np.linalg.solve(X.T @ (X * w[:, None]) + pen, X.T @ (y - mu) - pen @ b)
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b.tolist()


def regression(rows: list, boot: int, seed: int = 7) -> dict:
    """accuracy ~ N + p + model (Opus 5.5 reference), with a cluster bootstrap over games, stratified by model."""
    ref = "claude-opus-5-5"
    others = [m for m in ORDER if m != ref]
    names = ["const", "N", "p_x10"] + [f"model[{MODELS[m]}]" for m in others]

    def design(rs):
        return ([[1, r["N"], r["p"] * 10] + [int(r["model"] == m) for m in others] for r in rs], [r["correct"] for r in rs])

    est = logit(*design(rows))
    games = defaultdict(lambda: defaultdict(list))
    for r in rows:
        games[r["model"]][r["game"]].append(r)
    rng, draws = random.Random(seed), []
    for _ in range(boot):
        rs = []
        for m in ORDER:
            g = list(games[m])
            for _ in g:
                rs += games[m][rng.choice(g)]
        draws.append(logit(*design(rs)))
    pz = defaultdict(list)
    for r in rows:
        pz[r["puzzle"]].append(r)
    ids, pdraws = list(pz), []
    for _ in range(boot):
        rs = []
        for _ in ids:
            rs += pz[rng.choice(ids)]
        pdraws.append(logit(*design(rs)))
    ci, pci = [], []
    for j in range(len(names)):
        v = sorted(d[j] for d in pdraws)
        pci.append((round(v[int(0.025 * boot)], 4), round(v[int(0.975 * boot) - 1], 4)))
    for j in range(len(names)):
        v = sorted(d[j] for d in draws)
        ci.append((round(v[int(0.025 * boot)], 4), round(v[int(0.975 * boot) - 1], 4)))
    res = {"formula": "logit P(correct) ~ N + 10p + model (ref Opus 5.5)", "n": len(rows), "games": sum(len(g) for g in games.values()),
           "boot": boot, "coef": {k: round(b, 4) for k, b in zip(names, est)}, "ci95": dict(zip(names, ci)),
           "odds_ratio": {k: round(math.exp(b), 3) for k, b in zip(names, est)},
           "ci95_puzzle_cluster": dict(zip(names, pci))}
    # does N matter beyond the counting ceiling? the realised MAP accuracy of the round as a covariate, puzzle clusters
    def design_m(rs):
        return ([[1, r["N"], r["map_acc"]] + [int(r["model"] == m) for m in others] for r in rs], [r["correct"] for r in rs])
    mnames = ["const", "N", "map_acc"] + names[3:]
    mdraws = []
    for _ in range(boot):
        rs = []
        for _ in ids:
            rs += pz[rng.choice(ids)]
        mdraws.append(logit(*design_m(rs)))
    res["with_map_acc"] = {"formula": "logit P(correct) ~ N + map_acc + model, puzzle-cluster bootstrap",
                           "coef": {k: round(b, 4) for k, b in zip(mnames, logit(*design_m(rows)))},
                           "ci95_puzzle_cluster": {k: (round(sorted(d[j] for d in mdraws)[int(0.025 * boot)], 4),
                                                       round(sorted(d[j] for d in mdraws)[int(0.975 * boot) - 1], 4))
                                                   for j, k in enumerate(mnames)}}
    # the same with the round index instead of p: p is a step function of the round, so only one of them fits at once
    def design_r(rs):
        return ([[1, r["N"], r["round"]] + [int(r["model"] == m) for m in others] for r in rs], [r["correct"] for r in rs])
    res["coef_round_instead_of_p"] = {k: round(b, 4) for k, b in zip(["const", "N", "round"] + names[3:], logit(*design_r(rows)))}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=os.path.expanduser("~/squid5-runs/e52_v14f"))
    ap.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent))
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    runs, out = pathlib.Path(a.runs), pathlib.Path(a.out)
    rows, puzzles = load(runs)
    groups = {"pooled": rows, **{m: [r for r in rows if r["model"] == m] for m in ORDER}}
    by_n = {g: {str(n): cell([r for r in rs if r["N"] == n]) for n in NS} for g, rs in groups.items()}
    by_np = {g: {f"{n}|{p}": cell([r for r in rs if r["N"] == n and r["p"] == p]) for n in NS for p in PS}
             for g, rs in groups.items()}
    totals = {g: cell(rs) for g, rs in groups.items()}
    man = manipulation(puzzles)
    man["engine_check"] = engine_check(puzzles, runs)
    reg = regression(rows, a.boot)
    # where the fewer-agent rounds sit: mean round and p by N, pooled
    conf = {str(n): {"n": by_n["pooled"][str(n)]["n"], "mean_round": by_n["pooled"][str(n)].get("mean_round"),
                     "mean_p": by_n["pooled"][str(n)].get("mean_p")} for n in NS}
    tied = [r for r in rows if r["map_tied"]]
    ties = {"agent_rounds": len(tied), "answer_in_tie": sum(r["answer_is_map"] for r in tied),
            "first_in_action_order": sum(r["tie_first"] for r in tied), "correct": sum(r["correct"] for r in tied),
            "small_puzzles": len({r["puzzle"] for r in tied if r["N"] <= 2}),
            "by_N": {str(n): {t: {"n": len(rs), "correct": sum(r["correct"] for r in rs),
                                  "map_expected": round(sum(r["map_acc"] for r in rs), 2),
                                  "puzzles": len({r["puzzle"] for r in rs})}
                              for t, rs in (("tied", [r for r in rows if r["N"] == n and r["map_tied"]]),
                                            ("untied", [r for r in rows if r["N"] == n and not r["map_tied"]]))}
                     for n in NS}}
    # the N = 4 rounds only, by p: does a model's accuracy follow p (it counts) or stay flat?
    n4p = {g: {str(p): cell([r for r in rs if r["N"] == 4 and r["p"] == p]) for p in PS} for g, rs in groups.items()}

    cols = list(rows[0])
    with open(out / "agent_rounds.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    flat = ["n", "correct", "acc", "ci_lo", "ci_hi", "ci_puzzle_lo", "ci_puzzle_hi", "puzzles", "uniform", "map_acc", "map_exp", "k", "pool", "answer_is_map",
            "minus_uniform", "over_map", "over_map_exp", "truncated", "games", "mean_round", "mean_p", "caution"]
    for name, tab, key in (("by_n.csv", by_n, "N"), ("by_np.csv", by_np, "N|p")):
        with open(out / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["group", key] + flat)
            for g, cells in tab.items():
                for k, c in cells.items():
                    c2 = {**c, "ci_lo": (c.get("ci") or (None,))[0], "ci_hi": (c.get("ci") or (None, None))[1],
                          "ci_puzzle_lo": (c.get("ci_puzzle") or (None,))[0], "ci_puzzle_hi": (c.get("ci_puzzle") or (None, None))[1]}
                    w.writerow([g, k] + [c2.get(x, "") for x in flat])
    with open(out / "puzzles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "round", "p", "truth_major", "truth"] + [f"{x}_N{n}" for n in NS for x in ("k", "pool", "map_acc", "truth_share")])
        for (s, r), pub in sorted(puzzles.items()):
            b = pub["task"]["by_n"]
            w.writerow([s, r, pub["split"], int(pub["truth_major"]), pub["task"]["truth"]]
                       + [b[str(n)][x] for n in NS for x in ("k", "pool", "map_acc", "truth_share")])
    json.dump(man, open(out / "manipulation.json", "w"), indent=1)
    json.dump(reg, open(out / "regression.json", "w"), indent=1)
    json.dump({"models": MODELS, "order": ORDER, "rows": len(rows), "totals": totals, "by_n": by_n, "by_np": by_np,
               "n4_by_p": n4p, "confound": conf, "ties": ties, "manipulation": man, "regression": reg},
              open(out / "summary.json", "w"), indent=1, ensure_ascii=False)
    print(f"{len(rows)} agent-rounds, {len(puzzles)} puzzles; engine check {man['engine_check']}", file=sys.stderr)


if __name__ == "__main__":
    main()
