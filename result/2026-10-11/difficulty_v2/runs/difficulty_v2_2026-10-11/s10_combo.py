"""Combination: M6 multi-prefix ladder (comonotone roles, latin u) + extra queries pinned at N = 4 (the engine's
n_queries, all or nothing). Per level x N: joint MAP ceiling, joint top share, first-query MAP, joint uniform, joint
sampler, nearest-example heuristic (joint), pool. usage: s10_combo.py NQ [LADDER]"""
import sys, json, time, random, itertools, multiprocessing as mp, statistics as st, collections
from lib import *
from msel import select_order_only, draw_role
from s3_ladder import LADDERS
from s5_multiquery import joint_stats
NQ = int(sys.argv[1]); LAD = sys.argv[2] if len(sys.argv) > 2 else "M6"
SEEDS = tuple(map(int, sys.argv[3].split("-"))) if len(sys.argv) > 3 else (1, 17)

def run_seed(seed):
    lad = LADDERS[LAD]; bits = bits_for(SHAPE3); rows = []
    ur = random.Random(f"{seed}:u"); us = []
    for lvl in range(4):
        perm = list(range(3)); ur.shuffle(perm); us += [(perm[j] + ur.random()) / 3 for j in range(3)]
    for r in range(1, 13):
        T = lad[(r - 1) // 3]; u = us[r - 1]
        roles = {N: draw_role(t, u) for N, t in T.items()}
        p4 = T[4][0]; spec = spec_for(p4, n_queries=NQ); t0 = time.time(); got = None
        for att in range(40):
            pz = P.puzzle_for(seed, r, spec, att)
            got = select_order_only(pz.rule, pz.queries, p4, roles[4], {N: T[N] for N in T if N < 4}, roles,
                                    random.Random(f"{seed}:{r}:{att}"), sets=4)
            if got: break
        dt = time.time() - t0
        if not got:
            rows.append(dict(seed=seed, round=r, fail=True, time=dt)); continue
        js = joint_stats(pz.rule, got, pz.queries, bits)
        for n in range(1, 5):
            clues = [P.Clue(s, pz.rule.evaluate(s)) for s in got[:4 * n]]
            v = 1.0
            for q in pz.queries:
                v *= heur_acc(h_nn, clues, q, pz.rule.evaluate(q))
            js[n]["nn_joint"] = v
            js[n]["nn_q1"] = heur_acc(h_nn, clues, pz.queries[0], pz.answers[0])
            js[n]["nn_q2"] = heur_acc(h_nn, clues, pz.queries[1], pz.answers[1]) if len(pz.queries) > 1 else 1.0
        rows.append(dict(seed=seed, round=r, fail=False, time=dt, att=att, stats={str(n): v for n, v in js.items()}))
    return rows

if __name__ == "__main__":
    with mp.Pool(10) as pool:
        out = [r for rows in pool.map(run_seed, range(SEEDS[0], SEEDS[1] + 1)) for r in rows]
    json.dump(out, open(f"out/s10_{LAD}_nq{NQ}_{SEEDS[0]}_{SEEDS[1]}.json", "w"))
    ts = sorted(r["time"] for r in out)
    print(f"{LAD} n_queries={NQ}: rounds {len(out)} fail {sum(r['fail'] for r in out)}; time/round med {ts[len(ts)//2]:.2f} p90 {ts[int(.9*len(ts))]:.2f} max {ts[-1]:.2f}")
    by = collections.defaultdict(list)
    for r in out:
        if not r["fail"]: by[(r["round"] - 1) // 3].append(r)
    K = ["jmap", "jtop", "map1", "marg", "juni", "jk", "jsamp", "nn_joint", "nn_q1", "nn_q2"]
    for l in sorted(by):
        rs = by[l]
        print(f" level {l+1} (rounds {3*l+1}-{3*l+3}) ok {len(rs)}: N | " + " | ".join(K) + " | pool med")
        for n in "4321":
            vals = [f"{st.mean(x['stats'][n][k] for x in rs):.2f}" if k == "jk" else f"{100*st.mean(x['stats'][n][k] for x in rs):.0f}" for k in K]
            pools = sorted(x["stats"][n]["pool"] for x in rs)
            print(f"   {n} | " + " | ".join(vals) + f" | {pools[len(pools)//2]}")
