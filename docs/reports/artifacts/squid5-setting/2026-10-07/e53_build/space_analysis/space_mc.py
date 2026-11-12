"""Generator sampling share, shrinkage curve (Monte Carlo), by-hand cross-check, v13 seed-4000 rounds.
Run from ~/wt/squid5-e52 after space_enum.py: python3 <this>."""
import pathlib, random, sys, collections, statistics, time, itertools, json
import numpy as np, yaml
sys.path.insert(0, ".")
from squid5.core.puzzle import (Spec, Shape, puzzle_for, deal, _by_hand, _sample_rule, candidate_actions, ACTIONS,
                                SIGNAL_SPACE, SIGNAL_INDEX, Clue)
from squid5.e52_game import AGENTS
here = pathlib.Path(__file__).parent
z = np.load(here / "space_funcs.npz"); F23, SOL = z["f23"], z["sol"]
AI = {a: i for i, a in enumerate(ACTIONS)}
cfg = yaml.safe_load(open("configs/squid5/e52v13_hand_ladder_mix4.yaml"))["game"]
prof = {k: Spec(**v) for k, v in cfg["profiles"].items()}
pat = lambda rule: {1: "same3", 2: "two+one", 3: "all_diff"}[len({c.attrs[0] for c, _ in rule.clauses})]

# d. raw _sample_rule vs generated puzzles
rng = random.Random(1); raw = collections.Counter(); n = 0
shape = Shape((1, 1, 1), True)
while n < 20000:
    r = _sample_rule(rng, shape)
    if r: raw[pat(r)] += 1; n += 1
print("raw _sample_rule (n=20000):", {k: f"{v/n:.1%}" for k, v in raw.items()})
t = time.time(); P = []
for seed in range(1, 43):
    for rd in range(1, 13):
        P.append(puzzle_for(seed, rd, prof["hand8"]))
gen = collections.Counter(pat(p.rule) for p in P)
print(f"generated v13 puzzles n={len(P)} ({time.time()-t:.0f}s):", {k: f"{v} ({v/len(P):.1%})" for k, v in gen.items()})
mins = [len(p.minimal) for p in P]
print("minimal examples: mean", round(statistics.mean(mins), 2), "min", min(mins), "max", max(mins),
      "dist", dict(sorted(collections.Counter(mins).items())), "| clues per round", collections.Counter(len(p.clues) for p in P))

def cons(F, sigs, labs):
    return np.all(F[:, sigs] == labs, axis=1) if len(sigs) else np.ones(len(F), bool)
def look(F, rule_vec, sigs, q):
    m = cons(F, sigs, rule_vec[sigs]); return int(m.sum()), len(np.unique(F[m, q]))

# b. shrinkage curve: random examples of generated (rule, query) pairs
vecs = [np.array([AI[a] for a in p.rule.vector], np.uint8) for p in P]
qi = [SIGNAL_INDEX[p.queries[0]] for p in P]
rng = random.Random(7); D = 2000; rows = []
check = mism = 0
for k in (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 26):
    c23, cs, d23, ds, u23, us, n23, ns = [], [], 0, 0, 0, 0, 0, 0
    for i in range(D):
        j = i % len(P); pool = [x for x in range(64) if x != qi[j]]
        sigs = np.array(sorted(rng.sample(pool, k)), int)
        a, b = look(F23, vecs[j], sigs, qi[j]); c, d = look(SOL, vecs[j], sigs, qi[j])
        c23.append(a); cs.append(c); d23 += b == 1; ds += d == 1; u23 += a == 1; us += c == 1; n23 += b; ns += d
        if i < 25 and k in (2, 4, 6, 8):  # engine cross-check of the answer set
            check += 1
            eng = candidate_actions(P[j].rule.shape, [Clue(SIGNAL_SPACE[s], ACTIONS[vecs[j][s]]) for s in sigs], P[j].queries[0])
            m = cons(SOL, sigs, vecs[j][sigs]); mine = {ACTIONS[x] for x in np.unique(SOL[m, qi[j]])}
            mism += set(eng) != mine
    rows.append((k, statistics.median(c23), round(statistics.mean(c23), 1), round(100 * d23 / D, 1),
                 statistics.median(cs), round(100 * ds / D, 1), round(100 * u23 / D, 1), round(100 * us / D, 1),
                 round(n23 / D, 2), round(ns / D, 2)))
print(f"engine candidate_actions vs SOL-vector answer sets: {mism} mismatches in {check}")
print("k | median left (23,112) | mean left | P(query fixed) % (23,112) | median left (solver 25,996) | P fixed % (solver) | P function fixed % (23,112) | (solver) | mean query answers (23,112) | (solver)")
for r in rows: print(" | ".join(map(str, r)))

# cross-check: the page's by-hand numbers with the same 504 puzzles, 4 agents, pool 26
print("by-hand deal (4 agents), share of seats/pairs whose cards fix the query, solver space:")
for h in (8, 6, 4, 2):
    al = pr = al_n = pr_n = 0; left = []; mincards = []
    for j, p in enumerate(P):
        d = _by_hand(p, list(AGENTS), random.Random(f"x:{j}:{h}"), h)
        hands = {a: np.array(sorted({SIGNAL_INDEX[c.signal] for c in d.secret[a]}), int) for a in AGENTS}
        for a in AGENTS:
            c, u = look(SOL, vecs[j], hands[a], qi[j]); al += u == 1; al_n += 1; left.append(c)
            mincards.append(sum(c.signal in p.minimal for c in d.secret[a]))
        for a, b in itertools.combinations(AGENTS, 2):
            s = np.union1d(hands[a], hands[b]); pr += look(SOL, vecs[j], s, qi[j])[1] == 1; pr_n += 1
    print(f"  hand {h}: alone {100*al/al_n:.0f}% pair {100*pr/pr_n:.0f}%  median functions left alone {statistics.median(left)}  minimal cards per hand {statistics.mean(mincards):.2f}")

# c. v13 seed 4000 as the game deals it
out = []
for rd in range(1, 13):
    sp = prof[cfg["schedule"][rd - 1]]; p = puzzle_for(4000, rd, sp)
    d = deal(p, list(AGENTS), random.Random(f"4000:deal:{rd}"), None, True)
    v = np.array([AI[a] for a in p.rule.vector], np.uint8); q = SIGNAL_INDEX[p.queries[0]]
    own = {}
    for a in AGENTS:
        s = np.array(sorted({SIGNAL_INDEX[c.signal] for c in d.secret[a]}), int)
        own[a] = look(F23, v, s, q) + look(SOL, v, s, q)
    allc = np.array(sorted({SIGNAL_INDEX[c.signal] for c in p.clues}), int)
    mn = np.array(sorted(SIGNAL_INDEX[s] for s in p.minimal), int)
    out.append({"round": rd, "hand": sp.hand, "rule": p.rule.description, "pattern": pat(p.rule),
                "own_23_left/q": {a: own[a][:2] for a in AGENTS}, "own_sol_left/q": {a: own[a][2:] for a in AGENTS},
                "pool26": look(F23, v, allc, q) + look(SOL, v, allc, q), "minimal": (len(mn),) + look(F23, v, mn, q) + look(SOL, v, mn, q)})
for o in out: print(json.dumps(o))

diff = [(o["round"], a, o["own_23_left/q"][a][1], o["own_sol_left/q"][a][1]) for o in out for a in AGENTS
        if o["own_23_left/q"][a][1] != o["own_sol_left/q"][a][1]]
print("seats where the query answer count differs (23,112 vs solver):", diff)
