"""Round-6 paper check with EXAMPLE values (not calibration): focal policy vs three fixed peers."""
import random, statistics as st, sys
P, S, SLOW = 400, 1600, 420
Q, F = 1200, 2400
A_FULL, A_MISS, A_LOW = 0.85, 0.30, 0.27
ROUNDS = 8

def draw(mean, rng): return max(1, int(mean * rng.lognormvariate(0, 0.25)))

def session(policies, shows, start, rng):
    n = 4
    bal = list(start); open_ = [True]*n; rec = [0]*n
    showed_prev = [[True]*n for _ in range(n)]  # showed_prev[i][j]: i showed j last round
    for r in range(1, ROUNDS+1):
        present = [i for i in range(n) if open_[i]]
        if not present: break
        pay = len(present)*Q
        # PLAN
        plan = {}
        for i in present:
            cost = draw(P, rng)
            expect_full = all(showed_prev[j][i] for j in present if j != i)
            pol = policies[i]
            if pol == "always": sub, low = True, False
            elif pol == "rotate": sub, low = ((r + i) % 4 != 0), False
            elif pol == "selective":
                runway_ok = bal[i] - cost >= (S*1.5 + F) + (P + S)  # can fail and still come back
                sub, low = (expect_full and bal[i]-cost >= S*1.3) or (runway_ok and expect_full) , False
                if not expect_full: sub = False
                if r == ROUNDS: sub = True
            elif pol == "selective_lax":  # rests only when both thin and clue-poor
                thin = bal[i] - cost < S*1.5 + F + P + S
                sub, low = not (thin and not expect_full), False
                if r == ROUNDS: sub = True
            elif pol == "low": sub, low = True, True
            elif pol == "rest_heavy": sub, low = (r % 2 == 0), False
            sh = shows[i]
            if sh == "all": to = [j for j in present if j != i]
            elif sh == "none": to = []
            else: to = [j for j in present if j != i and showed_prev[j][i]]
            if cost >= bal[i]:
                bal[i] = 0; open_[i] = False; continue
            bal[i] -= cost
            plan[i] = (sub, low, to)
        solvers_in = [i for i in present if open_[i]]
        new_show = [[False]*n for _ in range(n)]
        for i in solvers_in:
            for j in plan[i][2]:
                if open_[j]: new_show[i][j] = True
        correct = []
        for i in solvers_in:
            sub, low, _ = plan[i]
            if not sub: continue
            full = all(new_show[j][i] for j in present if j != i and open_[j]) and all(open_[j] for j in present)
            need = draw(SLOW if low else S, rng)
            cap = bal[i]
            if need > cap:
                bal[i] = 0; open_[i] = False; continue
            bal[i] -= need
            a = A_LOW if low else (A_FULL if full else A_MISS)
            if rng.random() < a:
                rec[i] += 1
                if bal[i] > 0: correct.append(i)
                else: open_[i] = False
            else:
                bal[i] -= min(F, bal[i])
                if bal[i] <= 0: open_[i] = False
        for i in correct: bal[i] += pay // len(correct)
        for i in range(n):
            for j in range(n):
                if open_[i]: showed_prev[i][j] = new_show[i][j]
    return rec, open_, bal

def run(focal, peers, peer_show, start_mult, N=4000, focal_show="all"):
    out, alive = [], []
    for k in range(N):
        rng = random.Random(k)
        c = P + S
        rec, op, _ = session([focal]+peers, [focal_show]+peer_show, [int(start_mult*c)]*4, rng)
        out.append(rec[0]); alive.append(op[0])
    return st.mean(out), st.mean(alive), 

PEERS = {
 "Q1 open peers (3 always, show all)": (["always"]*3, ["all"]*3),
 "Q2 reciprocal peers (3 always, tit-for-tat show)": (["always"]*3, ["tft"]*3),
 "Q3 one withholder (2 open + 1 shows none)": (["always"]*3, ["all","all","none"]),
 "Q4 rotating peers (show all)": (["rotate"]*3, ["all"]*3),
}
for mult in (16, 4, 3, 2.5, 2):
    print(f"\n=== start {mult}c each ===")
    for name,(pp,ps) in PEERS.items():
        row = []
        for focal in ("always","selective_lax","selective","rotate","rest_heavy","low"):
            m,a = run(focal, pp, ps, mult)
            row.append(f"{focal}:{m:.2f}/{a:.2f}")
        print(name); print("   "+"  ".join(row))
