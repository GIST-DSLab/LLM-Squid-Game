"""Quick feasibility probe of select_multi on 24 rounds for one ladder level."""
import sys, time, random
from lib import *
from msel import select_multi, draw_role
T = {4: (.8, .2), 3: (.6, .4), 2: (.45, .35, .2)}
spec = spec_for(.8)
bits = bits_for(SHAPE3)
ok = 0; tt = []
rows = []
for seed in range(1, 3):
    for r in range(1, 13):
        rr = random.Random(f"{seed}:roles:{r}")
        u = rr.random(); roles = {N: draw_role(t, u) for N, t in T.items()}
        t0 = time.time(); got = None
        for att in range(20):
            pz = P.puzzle_for(seed, r, spec, att)
            got = select_multi(pz.rule, pz.queries, T, roles, random.Random(f"{seed}:{r}:{att}"))
            if got: break
        tt.append(time.time() - t0)
        if got:
            ok += 1
            st = level_stats(pz.rule, got, pz.queries[0], bits, heur=False)
            print(seed, r, roles, att, f"{tt[-1]:.1f}s", {n: (st[n]['pool'], round(st[n]['top'], 2), st[n]['map'], st[n]['k']) for n in (4, 3, 2, 1)})
        else:
            print(seed, r, roles, "FAIL", f"{tt[-1]:.1f}s")
print(ok, sorted(tt))
