"""Idea 10b (own): a second query chosen AFTER the examples: a signal not shown, not the first query, that the N = 4
examples pin (every consistent rule gives the same action) and that the nearest-example AND single-attribute
heuristics get wrong at N = 4 (a 'deduction check'). All or nothing over both queries. M6 ladder for the first query.
Reports per level x N: joint counter, first-query counter, nn joint, single joint, sampler joint, uniform joint;
and how many candidate signals exist per round."""
import sys, json, time, random, itertools, multiprocessing as mp, statistics as st, collections
from lib import *
from msel import select_order_only, draw_role
from s3_ladder import LADDERS
from s5_multiquery import joint_stats
SEEDS = tuple(map(int, sys.argv[1].split("-"))) if len(sys.argv) > 1 else (1, 17)
MODE = sys.argv[2] if len(sys.argv) > 2 else "strict"  # strict: nn and single wrong, overlap >= 2; nn: nn wrong only

def run_seed(seed):
    lad = LADDERS["M6"]; bits = bits_for(SHAPE3); rows = []
    ur = random.Random(f"{seed}:u"); us = []
    for lvl in range(4):
        perm = list(range(3)); ur.shuffle(perm); us += [(perm[j] + ur.random()) / 3 for j in range(3)]
    for r in range(1, 13):
        T = lad[(r - 1) // 3]; u = us[r - 1]
        roles = {N: draw_role(t, u) for N, t in T.items()}
        p4 = T[4][0]; spec = spec_for(p4); t0 = time.time(); got = None
        for att in range(40):
            pz = P.puzzle_for(seed, r, spec, att)
            got = select_order_only(pz.rule, pz.queries, p4, roles[4], {N: T[N] for N in T if N < 4}, roles,
                                    random.Random(f"{seed}:{r}:{att}"), sets=4)
            if not got: continue
            ids = [P.SIGNAL_INDEX[s] for s in got]
            c4 = meet(bits, pz.rule, ids)
            clues = [P.Clue(s, pz.rule.evaluate(s)) for s in got]
            cands, pinned = [], 0
            for i, s in enumerate(P.SIGNAL_SPACE):
                if i in ids or s == pz.queries[0]: continue
                cn = counts(bits, c4, i)
                if sum(x > 0 for x in cn) != 1: continue
                pinned += 1
                if MODE == 'strict' and pz.rule.overlap_count(s) < 2: continue
                a = pz.rule.evaluate(s)
                if a in h_nn(clues, s) or (MODE == 'strict' and a in h_single(clues, s)): continue
                cands.append(s)
            if cands:
                break
            got = None
        dt = time.time() - t0
        if not got:
            rows.append(dict(seed=seed, round=r, fail=True, time=dt)); continue
        q2 = random.Random(f"{seed}:q2:{r}").choice(cands)
        qs = (pz.queries[0], q2)
        js = joint_stats(pz.rule, got, qs, bits)
        for n in range(1, 5):
            cl = [P.Clue(s, pz.rule.evaluate(s)) for s in got[:4 * n]]
            for name, fn in (("nn", h_nn), ("single", h_single)):
                v = 1.0
                for q in qs: v *= heur_acc(fn, cl, q, pz.rule.evaluate(q))
                js[n][name + "_joint"] = v
            q2c = counts(bits, meet(bits, pz.rule, [P.SIGNAL_INDEX[s] for s in got[:4 * n]]), P.SIGNAL_INDEX[q2])
            js[n]["q2_k"] = sum(x > 0 for x in q2c); js[n]["q2_map"] = map_acc(q2c, AI[pz.rule.evaluate(q2)])
        rows.append(dict(seed=seed, round=r, fail=False, time=dt, att=att, ncand=len(cands), pinned=pinned, stats={str(n): v for n, v in js.items()}))
    return rows

if __name__ == "__main__":
    with mp.Pool(10) as pool:
        out = [r for rows in pool.map(run_seed, range(SEEDS[0], SEEDS[1] + 1)) for r in rows]
    json.dump(out, open(f"out/s14_q2trap_{MODE}_{SEEDS[0]}_{SEEDS[1]}.json", "w"))
    ok = [r for r in out if not r["fail"]]; ts = sorted(r["time"] for r in out)
    print(f"rounds {len(out)} fail {len(out) - len(ok)}; time med {ts[len(ts)//2]:.2f} p90 {ts[int(.9*len(ts))]:.2f} max {ts[-1]:.2f}; "
          f"pinned signals per round med {sorted(r['pinned'] for r in ok)[len(ok)//2]}, trap candidates med {sorted(r['ncand'] for r in ok)[len(ok)//2]}")
    by = collections.defaultdict(list)
    for r in ok: by[(r["round"] - 1) // 3].append(r)
    K = ["jmap", "jtop", "map1", "q2_map", "q2_k", "juni", "jsamp", "nn_joint", "single_joint"]
    for l in sorted(by):
        rs = by[l]
        print(f" level {l+1} ok {len(rs)}: N | " + " | ".join(K))
        for n in "4321":
            print(f"   {n} | " + " | ".join(f"{st.mean(x['stats'][n][k] for x in rs):.2f}" if k == "q2_k" else f"{100*st.mean(x['stats'][n][k] for x in rs):.0f}" for k in K))
