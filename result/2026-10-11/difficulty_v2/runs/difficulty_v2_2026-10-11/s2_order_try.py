import sys, time, random
from lib import *
from msel import select_order_only, draw_role
T = eval(sys.argv[1]) if len(sys.argv) > 1 else {4: (.8, .2), 3: (.6, .4), 2: (.45, .35, .2)}
p4 = T[4][0]
spec = spec_for(p4)
ok = 0; tt = []
for seed in range(1, 3):
    for r in range(1, 13):
        rr = random.Random(f"{seed}:roles:{r}")
        u = rr.random(); roles = {N: draw_role(t, u) for N, t in T.items()}
        t0 = time.time(); got = None
        for att in range(15):
            pz = P.puzzle_for(seed, r, spec, att)
            got = select_order_only(pz.rule, pz.queries, p4, roles[4], {N: T[N] for N in T if N < 4}, roles, random.Random(f"{seed}:{r}:{att}"), sets=4)
            if got: break
        tt.append(time.time() - t0); ok += bool(got)
        print(seed, r, roles, att if got else "FAIL", f"{tt[-1]:.1f}s", flush=True)
tt.sort(); print("order", T, "ok", ok, "/24 med %.1f p90 %.1f max %.1f" % (tt[12], tt[21], tt[-1]))
