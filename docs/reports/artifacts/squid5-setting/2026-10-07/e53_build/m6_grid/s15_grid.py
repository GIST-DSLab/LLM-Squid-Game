"""Round x alive-agents grid for a pre-generated game: per cell the consistent-hypothesis count, the hypothesis-space
size, and the 4-action share among consistent hypotheses (what a perfect counter believes). v14g order vs M6 order.
usage: s15_grid.py v14g|M6 SEEDS(e.g. 18-67)"""
import sys, json, time, random, multiprocessing as mp
from lib import *
from msel import select_order_only, draw_role
from s3_ladder import LADDERS


def cells(rule, order, q, bits):
    qi, tr = P.SIGNAL_INDEX[q], AI[rule.evaluate(q)]
    c, out = sum(bits[0]), {}
    for n in range(1, 5):
        for s in order[4 * (n - 1):4 * n]:
            i = P.SIGNAL_INDEX[s]; c &= bits[i][AI[rule.vector[i]]]
        out[n] = dict(cn=counts(bits, c, qi), pool=c.bit_count())
    return out, tr


def run_seed(args):
    mode, seed = args
    bits = bits_for(SHAPE3)
    rows = []
    if mode == "M6":
        lad = LADDERS["M6"]; ur = random.Random(f"{seed}:u"); us = []
        for lvl in range(4):
            perm = list(range(3)); ur.shuffle(perm); us += [(perm[j] + ur.random()) / 3 for j in range(3)]
    for r in range(1, 13):
        t0 = time.time()
        if mode == "v14g":
            pz, order, att, major = P._public_order(seed, r, spec_for(SCHED[r - 1]), 4, 4)
            target = {4: SCHED[r - 1]}
        else:
            T = lad[(r - 1) // 3]; u = us[r - 1]
            roles = {N: draw_role(t, u) for N, t in T.items()}
            p4 = T[4][0]; order = None
            for att in range(40):
                pz = P.puzzle_for(seed, r, spec_for(p4), att)
                order = select_order_only(pz.rule, pz.queries, p4, roles[4], {N: T[N] for N in T if N < 4}, roles,
                                          random.Random(f"{seed}:{r}:{att}"), sets=4)
                if order:
                    break
            if not order:
                rows.append(dict(seed=seed, round=r, fail=True)); continue
            target = {N: T[N][0] for N in T}
        cl, tr = cells(pz.rule, order, pz.queries[0], bits)
        rows.append(dict(seed=seed, round=r, fail=False, time=time.time() - t0, truth=tr, target=target,
                         query=str(pz.queries[0]), cells={str(n): v for n, v in cl.items()}))
    return rows


if __name__ == "__main__":
    mode, sd = sys.argv[1], sys.argv[2]
    a, b = map(int, sd.split("-"))
    with mp.Pool(10) as pool:
        out = [r for rows in pool.map(run_seed, [(mode, s) for s in range(a, b + 1)]) for r in rows]
    space = sum(bits_for(SHAPE3)[0]).bit_count()
    json.dump(dict(space=space, rows=out), open(f"out/s15_{mode}_{a}_{b}.json", "w"))
    print(mode, "rounds", len(out), "fail", sum(r["fail"] for r in out), "space", space)
