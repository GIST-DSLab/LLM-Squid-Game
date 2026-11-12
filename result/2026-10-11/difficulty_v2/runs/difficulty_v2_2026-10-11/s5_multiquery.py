"""Idea 4: two or three queries, all or nothing. (a) v14 selector with n_queries = 2 / 3: the first query k = 2 at
split p, the others pinned at N = 4 (the engine's 'miss' term); per N: joint MAP (most common answer tuple among
consistent functions), marginal-MAP tuple, uniform over the joint candidates, joint top share.
(b) query depth: overlap 2 vs 3 for the first query (v14g, single query)."""
import sys, time, random, json, itertools, multiprocessing as mp, statistics as st
from lib import *

def joint_stats(rule, order, queries, bits):
    qs = [P.SIGNAL_INDEX[q] for q in queries]
    truth = tuple(AI[rule.vector[q]] for q in qs)
    c = sum(bits[0]); out = {}
    for n in range(1, 5):
        for s in order[4 * (n - 1):4 * n]:
            i = P.SIGNAL_INDEX[s]; c &= bits[i][AI[rule.vector[i]]]
        tot = c.bit_count()
        jt = {}
        for combo in itertools.product(range(4), repeat=len(qs)):
            m = c
            for q, a in zip(qs, combo):
                m &= bits[q][a]
                if not m: break
            if m:
                jt[combo] = m.bit_count()
        top = max(jt.values()); tops = [k for k, v in jt.items() if v == top]
        jmap = (truth in tops) / len(tops)
        marg = []
        for j, q in enumerate(qs):
            cn = counts(bits, c, q); mx = max(cn); marg.append([a for a in range(4) if cn[a] == mx])
        mm = 1.0
        for j in range(len(qs)):
            mm *= (truth[j] in marg[j]) / len(marg[j])
        q1 = counts(bits, c, qs[0])
        out[n] = dict(jmap=jmap, jtop=top / tot, marg=mm, juni=1 / len(jt), jk=len(jt), pool=tot,
                      map1=map_acc(q1, truth[0]), jsamp=jt.get(truth, 0) / tot,
                      diff=float(set(tops) != {tuple(m[0] for m in marg)} if all(len(m) == 1 for m in marg) else 0))
    return out

def one(args):
    p, nq, seed, r = args
    spec = spec_for(p, n_queries=nq)
    t0 = time.time()
    try:
        pz, order, att, major = P._public_order(seed, r, spec, 4, 4)
    except P.PuzzleError:
        return None, time.time() - t0
    return joint_stats(pz.rule, order, pz.queries, bits_for(SHAPE3)), time.time() - t0

if __name__ == "__main__":
    res_all = {}
    with mp.Pool(5) as pool:
        for nq in (2, 3):
            for p in (.8, .7, .6, .5):
                res = pool.map(one, [(p, nq, s, r) for s in range(1, 6) for r in range(1, 13)])
                rows = [x for x, _ in res if x]; ts = sorted(t for _, t in res)
                print(f"n_queries={nq} p={p} ok {len(rows)}/{len(res)} time med {ts[len(ts)//2]:.2f} p90 {ts[int(.9*len(ts))]:.2f} max {ts[-1]:.2f}")
                print("  N | jointMAP | joint top share | marginal-MAP tuple | q1 MAP | joint uniform | joint k | sampler | jointMAP!=marg | pool med")
                for n in (4, 3, 2, 1):
                    m = lambda k: st.mean(x[n][k] for x in rows)
                    pools = sorted(x[n]["pool"] for x in rows)
                    print(f"  {n} | {100*m('jmap'):.0f} | {100*m('jtop'):.0f} | {100*m('marg'):.0f} | {100*m('map1'):.0f} | {100*m('juni'):.0f} | {m('jk'):.2f} | {100*m('jsamp'):.0f} | {100*m('diff'):.0f} | {pools[len(pools)//2]}", flush=True)
                res_all[f"{nq}_{p}"] = rows
    json.dump({k: [{str(n): v for n, v in x.items()} for x in rows] for k, rows in res_all.items()}, open("out/s5_multiquery.json", "w"))
