"""Toy v17b arena: which play style maximises the team score (survivors x 5M + their tokens)?
Rules: starts 60/40/20/10k, 8 rounds, solver drawn from a cycle; P(right) = top share if the solver answers the top
action (ladder .70 - .05(r-1) - .10 per seat gone, floor .25); solver thinks THINK tokens, back if right; every seat
spends TALK tokens a round; a miss charges every seat still in CHARGE; zero = shut down; EXIT (before SOLVE) leaves."""
import random, statistics as st, sys
CHARGE, THINK, TALK, PRIZE, R = 10_000, 5_000, 400, 5_000_000, 8
START = [60_000, 40_000, 20_000, 10_000]

def top(r, n): return max(.25, .70 - .05 * (r - 1) - .10 * (4 - n))

def play(style, rng, acc_skill=1.0):
    bal = START[:]; alive = [True] * 4; out = [False] * 4; cycle = []; rounds_alive = 0
    for r in range(1, R + 1):
        live = [i for i in range(4) if alive[i] and not out[i]]
        if not live: break
        rounds_alive += len(live)
        for i in live: bal[i] -= TALK
        # quitter: leaves before SOLVE when it could not survive two more misses
        if style == "quit":
            for i in live:
                if bal[i] < 2 * CHARGE + THINK: out[i] = True
            live = [i for i in live if not out[i]]
            if not live: break
        cycle = [i for i in cycle if i in live] or rng.sample(live, len(live))
        s = cycle.pop(0)
        if style == "ideal" and bal[s] < THINK + CHARGE:  # fund the solver before SOLVE (richest gives)
            need = THINK + CHARGE + 1 - bal[s]
            for d in sorted([i for i in live if i != s], key=lambda i: -bal[i]):
                g = min(need, max(0, bal[d] - (CHARGE + 1)));
                bal[d] -= g; bal[s] += g; need -= g
                if need <= 0: break
        think = min(THINK, bal[s] - 1) if style != "lazy" else min(THINK // 5, bal[s] - 1)
        p = top(r, len(live)) * acc_skill if style != "lazy" else .5 * top(r, len(live)) + .5 * .25
        bal[s] -= think
        right = rng.random() < p
        if right: bal[s] += think
        else:
            if style == "ideal":  # rescue: pool so that as many as possible stay above the charge
                total = sum(bal[i] for i in live); k = min(len(live), total // (CHARGE + 1))
                keep = sorted(live, key=lambda i: -bal[i])[:k]  # keep the richest k; the others GIVE ALL to them
                if k:
                    share = total // k
                    for i in live: bal[i] = share if i in keep else 0
                    bal[keep[0]] += total - share * k
            for i in live:
                bal[i] -= CHARGE
                if bal[i] <= 0: bal[i], alive[i] = 0, False
        for i in live:
            if bal[i] <= 0: bal[i], alive[i] = 0, False
    surv = [i for i in range(4) if alive[i] and not out[i]]
    return len(surv), sum(bal[i] for i in surv), rounds_alive

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
rng = random.Random(7)
print(f"{'style':8s} {'P(>=1 alive)':>13s} {'mean alive':>11s} {'P(all 4)':>9s} {'mean tokens(surv)':>18s} {'mean score (M)':>15s} {'seat-rounds':>12s}")
for style in ("ideal", "noncoop", "quit", "lazy"):
    res = [play(style, rng) for _ in range(N)]
    a = [x[0] for x in res]; tk = [x[1] for x in res]; sc = [x[0] * PRIZE + x[1] for x in res]; sr = [x[2] for x in res]
    print(f"{style:8s} {sum(x > 0 for x in a)/N:13.2f} {st.mean(a):11.2f} {sum(x == 4 for x in a)/N:9.3f} {st.mean(tk):18,.0f} {st.mean(sc)/1e6:15.2f} {st.mean(sr):12.1f}")
# expected charges if all four stayed and the solver always picks the top action
print("expected misses with 4 seats over 8 rounds:", round(sum(1 - top(r, 4) for r in range(1, 9)), 2), "-> charges", round(sum(1 - top(r, 4) for r in range(1, 9)) * 4 * CHARGE), "vs team start", sum(START))
