"""Inside-out vs outside-in multi-prefix selectors: success and time on the same 24 rounds and roles."""
import sys, time, random
from lib import *
from msel import select_multi, select_outside_in, draw_role
T = eval(sys.argv[1]) if len(sys.argv) > 1 else {4: (.8, .2), 3: (.6, .4), 2: (.45, .35, .2)}
which = sys.argv[2] if len(sys.argv) > 2 else "oi"
spec = spec_for(.8)
fn = select_outside_in if which == "oi" else select_multi
ok = 0; tt = []
for seed in range(1, 3):
    for r in range(1, 13):
        rr = random.Random(f"{seed}:roles:{r}")
        roles = {N: draw_role(t, rr.random()) for N, t in T.items()}
        t0 = time.time(); got = None
        for att in range(10):
            pz = P.puzzle_for(seed, r, spec, att)
            got = fn(pz.rule, pz.queries, T, roles, random.Random(f"{seed}:{r}:{att}"), tries=2) if which == "oi" else fn(pz.rule, pz.queries, T, roles, random.Random(f"{seed}:{r}:{att}"), tries=3, block_tries=2)
            if got: break
        tt.append(time.time() - t0); ok += bool(got)
        print(seed, r, roles, att if got else "FAIL", f"{tt[-1]:.1f}s", flush=True)
tt.sort(); print(which, T, "ok", ok, "/24 med %.1f p90 %.1f max %.1f" % (tt[12], tt[21], tt[-1]))
