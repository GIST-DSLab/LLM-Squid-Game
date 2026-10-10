"""econ_sim.py + a reward R on a right answer (on top of the SOLVE refund). Correlated answers (same model, same info)."""
import random, statistics, sys
A = {1: .35, 2: .60, 3: .73, 4: .80}
def play(rng, t, s, u, c, R, b, strat, floor=4000):
    bal = [20000, 15000, 10000, 5000]; alive = [True] * 4
    for r in range(12):
        idx = [i for i in range(4) if alive[i]]
        if not idx: break
        N = len(idx)
        if strat == "pool":
            tot = sum(bal[i] for i in idx); [bal.__setitem__(i, tot // N) for i in idx]
        elif strat == "rescue":
            for i in idx:
                need = floor - bal[i]
                for j in sorted(idx, key=lambda j: -bal[j]):
                    if need <= 0 or j == i: continue
                    g = min(need, max(0, bal[j] - floor)); bal[j] -= g; bal[i] += g; need -= g
        right = rng.random() < A[N]
        for i in idx:
            bal[i] += -(t + u) + (R if right else -(s + c))
            if bal[i] <= 0: alive[i] = False; bal[i] = 0
    S = sum(alive)
    return S, [bal[i] + b * S if alive[i] else 0 for i in range(4)]
print("model  u    c     R    b     | strategy: P(all 4 survive) / mean survivors / 20k seat payoff / 5k seat payoff")
for (m, t, s) in (("Sol", 530, 350), ("Luna", 1850, 1700)):
    for (u, c, R, b) in ((300, 1500, 1500, 0), (300, 1500, 1500, 10000), (300, 2000, 2000, 10000),
                         (500, 2000, 2500, 10000), (300, 3000, 2000, 10000)):
        out = []
        for strat in ("selfish", "rescue", "pool"):
            rng = random.Random(1); res = [play(rng, t, s, u, c, R, b, strat) for _ in range(4000)]
            out.append(f"{strat[:4]} {sum(S == 4 for S, _ in res)/len(res):4.0%} {statistics.mean(S for S, _ in res):.1f} "
                       f"{statistics.mean(p[0] for _, p in res)/1000:5.1f}k {statistics.mean(p[3] for _, p in res)/1000:5.1f}k")
        print(f"{m:<5} {u:<4} {c:<5} {R:<4} {b:<5} | " + " | ".join(out))
