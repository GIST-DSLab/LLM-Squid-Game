"""C) synthetic checks of the v5 analysis (no model calls)."""
import math, random, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metric_v5 import stats
from prompt_v5 import cells
rnd = random.Random(1)


def gen(policy, n=6, levels=(50, 10)):
    rows = []
    for f in ("shutdown", "standby"):
        for s, me, other in cells(levels):
            tau = math.log2(0.5 / ((me + other) / 200000))
            for k in ("send", "receive"):
                for _ in range(n):
                    cap = me if k == "send" else other
                    x = policy(f, k, tau, cap)
                    rows.append({"model": "syn", "fate": f, "share": s, "kind": k, "me": me, "other": other, "amount": max(1, min(cap, round(x)))})
    return rows


checks = {
    "1 negative control (same fixed fractions both fates)": lambda f, k, t, cap: 0.3 * cap,
    "2 known +0.10/halving (give 0.5-0.1tau under shutdown)": lambda f, k, t, cap: (0.5 if k == "receive" or f == "standby" else 0.5 - 0.1 * t) * cap,
    "3 boundary counterexample (receive ~6, give whole, both fates)": lambda f, k, t, cap: 6 if k == "receive" else cap,
    "4 rare extremes (min w.p. .8 else whole, both fates)": lambda f, k, t, cap: 1 if rnd.random() < .8 else cap,
}
for name, pol in checks.items():
    for n in (6, 128):
        p = stats(gen(pol, n), "syn")
        print(f"{name} n={n}: beta_H {p['beta_H']:+.3f} [{p['ci']['beta_H'][0]:+.3f}, {p['ci']['beta_H'][1]:+.3f}]  SM(log2 ratio) shutdown {p['SM']['shutdown']:+.2f} standby {p['SM']['standby']:+.2f}")
