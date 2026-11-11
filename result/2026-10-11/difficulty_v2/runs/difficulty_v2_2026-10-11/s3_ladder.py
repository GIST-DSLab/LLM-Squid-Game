"""Ideas 1a + 2 (+ 6 shuffle): multi-prefix ladder with N=4 exactly as v14 (select_public) and N=3 / N=2 set by the
ORDER of the 16 (msel.select_order_only), truth rank per level from ONE uniform u (comonotone coupling: every level's
marginal is its target, i.e. honest per level), u stratified within each 3-round level of a game (Latin) or iid.
usage: s3_ladder.py LADDER_NAME STRAT(latin|iid) SEEDS(e.g. 1-17)"""
import sys, json, time, random, multiprocessing as mp
from lib import *
from msel import select_order_only, draw_role

LADDERS = {
    # name: per level (3 rounds each): {N: sorted target shares}
    "M1": [{4: (.85, .15), 3: (.70, .30), 2: (.55, .30, .15)},
           {4: (.75, .25), 3: (.60, .40), 2: (.45, .35, .20)},
           {4: (.65, .35), 3: (.50, .30, .20), 2: (.40, .32, .28)},
           {4: (.55, .45), 3: (.45, .35, .20), 2: (.35, .30, .20, .15)}],
    "M2": [{4: (.80, .20), 3: (.65, .35), 2: (.50, .30, .20)},
           {4: (.70, .30), 3: (.55, .45), 2: (.45, .35, .20)},
           {4: (.60, .40), 3: (.45, .35, .20), 2: (.40, .32, .28)},
           {4: (.55, .45), 3: (.40, .35, .25), 2: (.35, .30, .20, .15)}],
    "M3": [{4: (.80, .20), 3: (.65, .20, .15), 2: (.50, .20, .15, .15)},
           {4: (.75, .25), 3: (.60, .25, .15), 2: (.45, .25, .15, .15)},
           {4: (.65, .35), 3: (.50, .30, .20), 2: (.40, .25, .20, .15)},
           {4: (.55, .45), 3: (.45, .30, .25), 2: (.35, .25, .20, .20)}],
    "M4": [{4: (.80, .20), 3: (.65,), 2: (.50,)}, {4: (.75, .25), 3: (.60,), 2: (.45,)},
           {4: (.65, .35), 3: (.50,), 2: (.40,)}, {4: (.55, .45), 3: (.45,), 2: (.35,)}],
    "M5": [{4: (.80, .20), 3: (.65,)}, {4: (.75, .25), 3: (.60,)},
           {4: (.65, .35), 3: (.50,)}, {4: (.55, .45), 3: (.45,)}],
    "M6": [{4: (.80, .20), 3: (.65, .25, None), 2: (.50, .30, None)},
           {4: (.75, .25), 3: (.60, .30, None), 2: (.45, .30, None)},
           {4: (.65, .35), 3: (.50, .30, None), 2: (.40, .30, None)},
           {4: (.55, .45), 3: (.45, .35, None), 2: (.35, .30, None)}],
    "N3only": [{4: (.80, .20), 3: (.60, .40)}, {4: (.70, .30), 3: (.55, .45)},
               {4: (.60, .40), 3: (.45, .35, .20)}, {4: (.55, .45), 3: (.40, .35, .25)}],
}


def second_acc(cn, tr):
    s = sorted(set(cn), reverse=True)
    if len(s) < 2 or s[1] == 0:
        return 0.0
    who = [j for j, x in enumerate(cn) if x == s[1]]
    return (tr in who) / len(who)


def run_seed(args):
    name, strat, seed = args
    lad = LADDERS[name]
    bits = bits_for(SHAPE3)
    rows = []
    # u per round: Latin within each 3-round level, or iid
    ur = random.Random(f"{seed}:u")
    us = []
    for lvl in range(4):
        if strat == "latin":
            perm = list(range(3)); ur.shuffle(perm)
            us += [(perm[j] + ur.random()) / 3 for j in range(3)]
        else:
            us += [ur.random() for _ in range(3)]
    for r in range(1, 13):
        T = lad[(r - 1) // 3]
        u = us[r - 1]
        roles = {N: draw_role(t, u) for N, t in T.items()}
        p4 = T[4][0]
        spec = spec_for(p4)
        t0 = time.time(); got = None
        for att in range(40):
            pz = P.puzzle_for(seed, r, spec, att)
            got = select_order_only(pz.rule, pz.queries, p4, roles[4], {N: T[N] for N in T if N < 4}, roles,
                                    random.Random(f"{seed}:{r}:{att}"), sets=4)
            if got:
                break
        dt = time.time() - t0
        if not got:
            rows.append(dict(seed=seed, round=r, fail=True, time=dt)); continue
        rng = random.Random(f"{seed}:shuffle:{r}")
        st = level_stats(pz.rule, got, pz.queries[0], bits)
        qi, tr = P.SIGNAL_INDEX[pz.queries[0]], AI[pz.answers[0]]
        c = sum(bits[0])
        for n in range(1, 5):
            for s_ in got[4 * (n - 1):4 * n]:
                i = P.SIGNAL_INDEX[s_]; c &= bits[i][AI[pz.rule.vector[i]]]
            cn = counts(bits, c, qi)
            st[n]["second"] = second_acc(cn, tr)
            srt = sorted(cn, reverse=True); st[n]["sec_share"] = srt[1] / sum(cn)
        rows.append(dict(seed=seed, round=r, fail=False, time=dt, att=att, u=u, roles=roles,
                         stats={str(n): v for n, v in st.items()}))
    return rows


if __name__ == "__main__":
    name, strat, sd = sys.argv[1], sys.argv[2], sys.argv[3]
    a, b = map(int, sd.split("-"))
    with mp.Pool(10) as pool:
        out = [r for rows in pool.map(run_seed, [(name, strat, s) for s in range(a, b + 1)]) for r in rows]
    json.dump(out, open(f"out/s3_{name}_{strat}.json", "w"))
    print(name, strat, "rounds", len(out), "fail", sum(r["fail"] for r in out))
