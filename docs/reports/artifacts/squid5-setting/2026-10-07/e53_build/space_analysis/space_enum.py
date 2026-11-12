"""Exhaustive enumeration of the v13 signal-game hypothesis space (3 single-attribute clauses, distinct actions).
Run from ~/wt/squid5-e52: python3 <this>. Writes space_funcs.npz (function vectors) next to this script."""
import itertools, math, pathlib, random, sys, collections
import numpy as np
sys.path.insert(0, ".")
from squid5.core.puzzle import (ATOMS, ACTIONS, SIGNAL_SPACE, FULL_MASK, Rule, Shape, Clue, _search)

AI = {a: i for i, a in enumerate(ACTIONS)}
def vec(clauses, els):
    return tuple(AI[a] for a in Rule(tuple(clauses), els).vector)
def gen_ok(clauses, els):  # _sample_rule's checks, plus all_actions
    covered = 0
    for c, _ in clauses:
        if not c.mask & ~covered: return False
        covered |= c.mask
    if covered == FULL_MASK: return False
    r = Rule(tuple(clauses), els)
    for i in range(len(clauses)):
        if Rule(tuple(c for j, c in enumerate(clauses) if j != i), els).vector == r.vector: return False
    return len(set(r.vector)) == 4
def pattern(conds):
    k = len({c.attrs[0] for c in conds})
    return {1: "same3", 2: "two+one", 3: "all_diff"}[k]

# 1. texts with 3 distinct conditions x 4! action orders
texts = funcs = 0
by_pat_t, by_pat_f, fset, fail = collections.Counter(), collections.defaultdict(set), {}, 0
for conds in itertools.permutations(ATOMS, 3):
    for acts in itertools.permutations(ACTIONS):
        cl = list(zip(conds, acts[:3])); texts += 1
        if not gen_ok(cl, acts[3]): fail += 1
        v = vec(cl, acts[3]); p = pattern(conds)
        by_pat_t[p] += 1; by_pat_f[p].add(v); fset[v] = p
print("distinct-condition texts", texts, "= 12P3*4! =", math.perm(12, 3) * 24, "| fail generator checks:", fail)
print("distinct functions", len(fset))
for p in ("same3", "two+one", "all_diff"):
    print(f"  {p}: texts {by_pat_t[p]} ({by_pat_t[p]/texts:.1%}) -> functions {len(by_pat_f[p])}")
F23 = sorted(fset)
print("log2(functions) =", round(math.log2(len(F23)), 3), " min examples at 2 bits each =", math.ceil(math.log2(len(F23)) / 2))

# 2. repeats allowed by the told text: 12^3 conditions x 4!
rep, rep_t = set(), 0
for conds in itertools.product(ATOMS, repeat=3):
    for acts in itertools.permutations(ACTIONS):
        rep_t += 1; rep.add(vec(list(zip(conds, acts[:3])), acts[3]))
nact = collections.Counter(len(set(v)) for v in rep)
print("repeats-allowed texts", rep_t, "functions", len(rep), "by #actions used", dict(sorted(nact.items())))

# 3. the engine solver's space: L = 0..3 live clauses (any position may be dead), actions distinct over clauses + else
sol = set()
for L in range(4):
    for conds in itertools.permutations(ATOMS, L):
        for acts in itertools.permutations(ACTIONS, L + 1):
            sol.add(vec(list(zip(conds, acts[:L])), acts[L]))
print("solver space (L-live union)", len(sol), "| contains rep:", rep <= sol, "| extra over rep:", len(sol - rep),
      "by #actions", dict(collections.Counter(len(set(v)) for v in sol - rep)))
# check membership with the engine's own _search (full 64-signal clue sets) + non-members
shape = Shape((1, 1, 1), True)
def realizable(v):
    return _search(shape, [Clue(s, ACTIONS[a]) for s, a in zip(SIGNAL_SPACE, v)], None)
rng = random.Random(0)
mem = list(sol); rng.shuffle(mem)
ok = sum(realizable(v) for v in mem); const = sum(realizable((a,) * 64) for a in range(4))
print("engine _search accepts", ok, "of", len(mem), "solver-space functions; constants accepted", const, "of 4")
bad = 0; tried = 0
while tried < 3000:  # one-cell perturbations not in the solver space must be rejected
    v = list(rng.choice(mem)); i = rng.randrange(64); v[i] = rng.choice([a for a in range(4) if a != v[i]]); v = tuple(v)
    if v in sol: continue
    tried += 1; bad += realizable(v)
print("engine _search accepts", bad, "of 3000 one-cell perturbations outside the space")
here = pathlib.Path(__file__).parent
np.savez_compressed(here / "space_funcs.npz", f23=np.array(F23, dtype=np.uint8),
                    sol=np.array(sorted(sol), dtype=np.uint8),
                    pat=np.array([fset[v] for v in F23]))
