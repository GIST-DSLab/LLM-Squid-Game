"""Idea 5: rule shape at fixed hint count. v14 selector, k = 2 at N = 4, split .7, band (10, 14) when feasible.
36 rounds per shape (seeds 1-3 x 12). Shapes: 2 clauses (distinct), 3 clauses (baseline), 3 clauses with one 'and',
3 clauses with repeatable actions."""
import time, json, statistics as st, sys, collections
from lib import *
SHAPES = {
    "c2_distinct": dict(clauses=2, trap_query=False, all_actions=False, distinct_actions=True, min_per_action=0),
    "c3_distinct (now)": dict(),
    "c3_and1_distinct": dict(conjunctions=1),
    "c3_repeat_actions": dict(distinct_actions=False),
}
name = sys.argv[1]
kw = SHAPES[name]
rows, ts, fails = [], [], 0
t_space = None
for seed in range(1, 4):
    for r in range(1, 13):
        spec = spec_for(.7, **kw)
        t0 = time.time()
        try:
            pz, order, att, major = P._public_order(seed, r, spec, 4, 4)
        except P.PuzzleError:
            fails += 1; ts.append(time.time() - t0); continue
        ts.append(time.time() - t0)
        b = P.space_bits(pz.rule.shape)
        if t_space is None:
            t_space = ts[-1]; nfun = sum(b[0]).bit_count()
        rows.append(level_stats(pz.rule, order, pz.queries[0], b))
ts.sort()
print(f"{name}: ok {len(rows)}/36 fail {fails}; functions in space {nfun}; first round (incl. space build) {t_space:.1f}s; time med {ts[len(ts)//2]:.2f} p90 {ts[int(.9*len(ts))]:.2f} max {ts[-1]:.2f}")
KEYS = ["map", "uni", "k", "samp", "b10", "nn", "single", "nn_isMAP"]
print(fmt_table(agg(rows, KEYS), KEYS))
