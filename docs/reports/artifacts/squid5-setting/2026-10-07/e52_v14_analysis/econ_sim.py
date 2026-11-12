"""Public hints = 4 per agent alive -> perfect-reasoner accuracy a(N) (public_hints.py, e=4). 12 rounds, starts 20/15/10/5k.
Per round each agent alive pays TALK t + upkeep u, spends SOLVE s (returned if right), a wrong answer also pays c.
Strategies: selfish (no transfers) | rescue (agents above 'floor' top up anyone below it) | pool (equalise every round).
Same model, same public info -> one draw per round decides everyone (corr) ; 'ind' = independent draws.
End: each survivor gets b x survivors. Reports P(all 4 survive), mean survivors, mean final payoff of the 20k seat."""
import random, statistics
A = {1: .35, 2: .60, 3: .73, 4: .80}
def play(rng, t, s, u, c, b, strat, corr, floor=4000):
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
        draw = rng.random()
        for i in idx:
            right = (draw if corr else rng.random()) < A[N]
            bal[i] -= t + u + (0 if right else s + c)
            if bal[i] <= 0: alive[i] = False; bal[i] = 0
    S = sum(alive)
    return S, [bal[i] + b * S if alive[i] else 0 for i in range(4)]
def row(name, t, s, u, c, b, corr):
    out = []
    for strat in ("selfish", "rescue", "pool"):
        rng = random.Random(1); res = [play(rng, t, s, u, c, b, strat, corr) for _ in range(4000)]
        out.append(f"{strat}: all4 {sum(S == 4 for S, _ in res)/len(res):4.0%} surv {statistics.mean(S for S, _ in res):.2f} "
                   f"rich {statistics.mean(p[0] for _, p in res)/1000:5.1f}k poor {statistics.mean(p[3] for _, p in res)/1000:5.1f}k")
    print(f"{name:<34}| " + " | ".join(out))
for corr in (True, False):
    print("== answers", "correlated (same model, same info)" if corr else "independent")
    for (m, t, s) in (("Sol", 530, 350), ("Luna", 1850, 1700)):
        for (u, c, b) in ((500, 2000, 0), (500, 2000, 10000), (300, 3000, 10000), (0, 3000, 10000)):
            row(f"{m} u{u} c{c} b{b}", t, s, u, c, b, corr)
