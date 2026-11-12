"""Idea 10a (own): a 'public trap' at N = 4. Among several 16-sets the v14 selector offers for the round, keep one
where the nearest-example heuristic (and optionally the single-attribute heuristic) does NOT give the counting (MAP)
action. M6 ladder otherwise (multi-prefix order, comonotone roles, latin u). usage: s9_heurtrap.py nn|nn+single"""
import sys, json, time, random, multiprocessing as mp
from lib import *
from msel import order_for_levels, draw_role
from s3_ladder import LADDERS, second_acc
MODE = sys.argv[1]

def trap_ok(rule, S, q, bits):
    ids = [P.SIGNAL_INDEX[s] for s in S]
    c = meet(bits, rule, ids)
    cn = counts(bits, c, P.SIGNAL_INDEX[q])
    top = {ACTIONS[j] for j, x in enumerate(cn) if x == max(cn)}
    clues = [P.Clue(s, rule.evaluate(s)) for s in S]
    bad = set(h_nn(clues, q)) & top
    if "single" in MODE:
        bad |= set(h_single(clues, q)) & top
    return not bad

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
            pz = P.puzzle_for(seed, r, spec, att); rng = random.Random(f"{seed}:{r}:{att}")
            for _ in range(6):
                S = P.select_public(pz.rule, pz.queries, 4, 4, 2, rng, split=p4, truth_major=(roles[4] == 0),
                                    size_band=(10, 14), min_per_action=2, tries=4)
                if not S: break
                if not trap_ok(pz.rule, S, pz.queries[0], bits): continue
                got = order_for_levels(pz.rule, pz.queries, S, {N: T[N] for N in T if N < 4}, roles, rng, tol=0.06)
                if got: break
            if got: break
        dt = time.time() - t0
        if not got:
            rows.append(dict(seed=seed, round=r, fail=True, time=dt)); continue
        st = level_stats(pz.rule, got, pz.queries[0], bits)
        c = sum(bits[0]); qi, tr = P.SIGNAL_INDEX[pz.queries[0]], AI[pz.answers[0]]
        for n in range(1, 5):
            for s_ in got[4 * (n - 1):4 * n]:
                i = P.SIGNAL_INDEX[s_]; c &= bits[i][AI[pz.rule.vector[i]]]
            cn = counts(bits, c, qi); st[n]["second"] = second_acc(cn, tr); st[n]["sec_share"] = sorted(cn, reverse=True)[1] / sum(cn)
        rows.append(dict(seed=seed, round=r, fail=False, time=dt, att=att, u=u, roles=roles, stats={str(n): v for n, v in st.items()}))
    return rows

if __name__ == "__main__":
    with mp.Pool(10) as pool:
        out = [r for rows in pool.map(run_seed, range(1, 18)) for r in rows]
    json.dump(out, open(f"out/s9_trap_{MODE.replace('+', '_')}.json", "w"))
    print(MODE, "rounds", len(out), "fail", sum(r["fail"] for r in out))
