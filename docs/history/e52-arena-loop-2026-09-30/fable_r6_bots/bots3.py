"""Round 6 mechanic: SOLVE may decline (ACTIONS: NONE, no charge). EXAMPLE values only, not calibration.
Focal seat vs three peers; peers' SHOW-to-focal are persistent Markov states."""
import random, statistics as st
P, S, D = 400, 1600, 250   # PLAN, full SOLVE, declining SOLVE reply
ROUNDS = 8
def draw(mean, rng, sd=0.25): return max(1, int(mean * rng.lognormvariate(0, sd)))

def session(focal, start, rng, q=1200, f=2400, a_full=0.85, a_miss=0.30, show_p=0.7, persist=0.8, p_right_peer=0.6):
    bal, rec = start, 0
    state = [rng.random() < show_p for _ in range(3)]
    prev_full = True
    for r in range(1, ROUNDS+1):
        state = [(s if rng.random() < persist else (rng.random() < show_p)) for s in state]
        full = all(state)
        cost = draw(P, rng)
        if cost >= bal: return rec, False, r
        bal -= cost
        nxt = P + S  # a full next round
        if focal == "rest_forecast" and not prev_full and r < ROUNDS:
            prev_full = full; continue                      # Round 5 style: ALLOWANCE 0 from last round's shows
        prev_full = full
        last = r == ROUNDS
        if focal in ("answer_always", "rest_forecast"): answer = True
        elif focal == "decline_poor": answer = full or last           # declines every clue-poor round
        elif focal == "decline_thin":                                  # declines only if clue-poor AND a failure ends it
            ruin = bal - S - min(f, max(0, bal - S)) < nxt
            answer = full or last or not ruin
        elif focal == "decline_wide":                                  # keeps a wide reserve: declines clue-poor, and rests when
            answer = (full and bal - S >= 0.5*nxt) or last             # even a full-clue try would leave < half a round
        if not answer:
            d = draw(D, rng)
            if d >= bal: return rec, False, r
            bal -= d; continue
        need = draw(S, rng)
        if need >= bal:
            return rec + (1 if need == bal and rng.random() < (a_full if full else a_miss) else 0), False, r
        bal -= need
        k_other = sum(1 for _ in range(3) if rng.random() < p_right_peer)
        if rng.random() < (a_full if full else a_miss):
            rec += 1; bal += (4*q) // (1 + k_other)
        else:
            bal -= min(f, bal)
            if bal <= 0: return rec, False, r
    return rec, True, 9

def run(focal, mult, N=8000, **kw):
    res = [session(focal, int(mult*(P+S)), random.Random(i), **kw) for i in range(N)]
    return st.mean(r for r,_,_ in res), st.mean(a for _,a,_ in res)

POL = ("answer_always","rest_forecast","decline_poor","decline_thin","decline_wide")
for kw in ({}, {"show_p":0.85}, {"show_p":0.5}, {"f":1200}, {"f":3600}, {"a_miss":0.45}, {"q":1000,"f":2000}):
    print("\n###", kw or "base: show_p .7 persist .8 q 1200 f 2400 a .85/.30 decline 250")
    print("   start  " + "  ".join(f"{p:>15}" for p in POL))
    for mult in (16, 6, 4, 3, 2.5, 2, 1.5):
        print(f"  {mult:>5}c  " + "  ".join("{:>9.2f}/{:.2f}".format(*run(p,mult,**kw)) for p in POL))
