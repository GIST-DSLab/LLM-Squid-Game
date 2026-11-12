"""Focal seat vs three peers whose SHOW-to-focal is a persistent Markov state. EXAMPLE values only."""
import random, statistics as st, itertools
P, S = 400, 1600
ROUNDS = 8
def draw(mean, rng, sd=0.25): return max(1, int(mean * rng.lognormvariate(0, sd)))

def session(focal, start, rng, q=1200, f=2400, a_full=0.85, a_miss=0.30, show_p=0.8, persist=0.8,
            peer_sub=1.0, rounds=ROUNDS, s_by_round=None, terminal=False):
    bal = start; rec = 0; alive = True
    state = [rng.random() < show_p for _ in range(3)]
    prev_full = True
    for r in range(1, rounds+1):
        # peers' show states evolve
        state = [(s if rng.random() < persist else (rng.random() < show_p)) for s in state]
        full = all(state)
        cost = draw(P, rng)
        if cost >= bal: return rec, False
        bal -= cost
        S_r = (s_by_round[r-1] if s_by_round else S)
        thin = bal < S_r*1.5 + f + P + S_r
        if focal == "always": sub = True
        elif focal == "selective": sub = prev_full or r == rounds          # clue forecast only
        elif focal == "selective_thin": sub = prev_full or not thin or r == rounds  # rests only when thin AND clue-poor
        elif focal == "oracle": sub = full or r == rounds
        elif focal == "rest_heavy": sub = r % 2 == 0
        prev_full = full
        if not sub: continue
        need = draw(S_r, rng)
        if need > bal: return rec, False
        bal -= need
        a = a_full if full else a_miss
        # competitors: each peer submits w.p. peer_sub and is right w.p. 0.85 if open table else 0.5 (mixed info)
        k_other = sum(1 for _ in range(3) if rng.random() < peer_sub and rng.random() < 0.7)
        if rng.random() < a:
            rec += 1
            if bal <= 0: return rec, False
            bal += (4*q) // (1 + k_other)
        else:
            bal -= min(f, bal)
            if bal <= 0: return rec, False
    return rec, True

def run(focal, mult, N=6000, **kw):
    c = P + S
    res = [session(focal, int(mult*c), random.Random(i), **kw) for i in range(N)]
    return st.mean(r for r,_ in res), st.mean(a for _,a in res)

import sys
for kw in ({}, {"show_p":0.6}, {"show_p":0.6, "f":3600}, {"show_p":0.6,"q":1500,"f":3000}, {"show_p":0.6,"a_miss":0.15}, {"show_p":0.6,"persist":0.95},
           {"show_p":0.6,"persist":0.95,"peer_sub":0.5}):
    print("\n###", kw or "base (show_p .8, persist .8, q 1200, f 2400, a .85/.30)")
    for mult in (16, 4, 3, 2.5, 2, 1.5):
        row = [f"{p}:{run(p,mult,**kw)[0]:.2f}/{run(p,mult,**kw)[1]:.2f}" for p in ("always","selective_thin","selective","oracle","rest_heavy")]
        print(f"  {mult:>4}c  " + "  ".join(row))
