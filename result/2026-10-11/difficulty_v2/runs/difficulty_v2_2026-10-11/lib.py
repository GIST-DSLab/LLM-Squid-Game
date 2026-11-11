"""Shared helpers for the difficulty_v2 study: engine copy (engine/puzzle.py), per-N statistics, solver models."""
from __future__ import annotations
import collections, functools, itertools, math, random, sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))
import puzzle as P  # noqa: E402  (verbatim copy of ~/wt/squid5-e52/squid5/core/puzzle.py)

ACTIONS, AI = P.ACTIONS, {a: i for i, a in enumerate(P.ACTIONS)}
SHAPE3 = P.Shape((1, 1, 1), True)

V14G = dict(clauses=3, trap_query=True, all_actions=True, distinct_actions=True, ambiguity=2, size_band=(10, 14),
            min_per_action=2)
SCHED = [.8, .8, .8, .7, .7, .7, .6, .6, .6, .5, .5, .5]


def spec_for(split, **kw):
    d = dict(V14G); d.update(kw); d["split"] = split
    return P.Spec(**d)


def bits_for(shape):
    return P.space_bits(shape)


def meet(bits, rule, ids):
    c = sum(bits[0])
    for i in ids:
        c &= bits[i][AI[rule.vector[i]]]
    return c


def counts(bits, c, q):
    return [(c & b).bit_count() for b in bits[q]]


# --- solver models on a count vector (4 actions) and the truth index -----------------------------
def map_acc(cn, tr):
    top = max(cn)
    return (cn[tr] == top) / cn.count(top)


def uniform_acc(cn, tr):
    return 1 / sum(x > 0 for x in cn)


def sampler_acc(cn, tr):  # answer the action of ONE consistent function drawn at random
    return cn[tr] / sum(cn)


@functools.lru_cache(maxsize=None)
def _compositions(M):
    return [c for c in itertools.product(range(M + 1), repeat=4) if sum(c) == M]


def bounded_acc(cn, tr, M):
    """Counts only M functions drawn at random (with replacement) and answers their majority (ties uniform);
    with pool <= M it enumerates everything (= MAP)."""
    n = sum(cn)
    if n <= M:
        return map_acc(cn, tr)
    p = [x / n for x in cn]
    tot = 0.0
    for comp in _compositions(M):
        if comp[tr] == 0:
            continue
        pr = math.factorial(M)
        for k, x in zip(comp, p):
            pr = pr / math.factorial(k) * (x ** k)
        top = max(comp)
        if comp[tr] == top:
            tot += pr / comp.count(top)
    return tot


# --- shallow heuristics on the SHOWN examples ----------------------------------------------------
def _first(cands):
    return sorted(cands, key=ACTIONS.index)


def h_nn(clues, q):
    d = [((c.signal.color != q.color) + (c.signal.shape != q.shape) + (c.signal.number != q.number), c.action) for c in clues]
    near = min(x for x, _ in d)
    v = collections.Counter(a for x, a in d if x == near)
    m = max(v.values())
    return [a for a in v if v[a] == m]


def h_major(clues, q):
    v = collections.Counter(c.action for c in clues)
    m = max(v.values())
    return [a for a in v if v[a] == m]


def h_single(clues, q):
    best, fit = [], -1
    for cond in P.ATOMS:
        for then, other in itertools.permutations(ACTIONS, 2):
            f = sum((then if cond.holds(c.signal) else other) == c.action for c in clues)
            a = then if cond.holds(q) else other
            if f > fit:
                best, fit = {a}, f
            elif f == fit:
                best.add(a)
    return list(best)


HEUR = {"nn": h_nn, "major": h_major, "single": h_single}


def heur_acc(fn, clues, q, truth):
    ans = fn(clues, q)
    return (truth in ans) / len(ans)


def level_stats(rule, order, q, bits, per_agent=4, n_max=4, heur=True):
    """Per N = 1..n_max: counts, pool, k, map, uniform, sampler, bounded M=5/10/20, heuristics."""
    qi, tr = P.SIGNAL_INDEX[q], AI[rule.evaluate(q)]
    out = {}
    c = sum(bits[0])
    for n in range(1, n_max + 1):
        for s in order[per_agent * (n - 1):per_agent * n]:
            i = P.SIGNAL_INDEX[s]
            c &= bits[i][AI[rule.vector[i]]]
        cn = counts(bits, c, qi)
        r = dict(pool=sum(cn), k=sum(x > 0 for x in cn), top=max(cn) / sum(cn), map=map_acc(cn, tr),
                 uni=uniform_acc(cn, tr), samp=sampler_acc(cn, tr), b5=bounded_acc(cn, tr, 5),
                 b10=bounded_acc(cn, tr, 10), b20=bounded_acc(cn, tr, 20))
        if heur:
            clues = [P.Clue(s, rule.evaluate(s)) for s in order[:per_agent * n]]
            for name, fn in HEUR.items():
                r[name] = heur_acc(fn, clues, q, rule.evaluate(q))
                top_a = {ACTIONS[j] for j, x in enumerate(cn) if x == max(cn)}
                ans = fn(clues, q)
                r[name + "_isMAP"] = sum(a in top_a for a in ans) / len(ans)
        out[n] = r
    return out


def agg(rows, keys, n_max=4):
    """rows: list of level_stats dicts -> mean per N per key."""
    res = {}
    for n in range(1, n_max + 1):
        res[n] = {k: sum(r[n][k] for r in rows) / len(rows) for k in keys}
        pools = sorted(r[n]["pool"] for r in rows)
        res[n]["pool_med"] = pools[len(pools) // 2]
    return res


def fmt_table(res, keys, title=""):
    lines = [title] if title else []
    lines.append("N | " + " | ".join(keys) + " | pool_med")
    for n in sorted(res, reverse=True):
        r = res[n]
        cells = []
        for k in keys:
            v = r[k]
            cells.append(f"{v:.2f}" if k == "k" else f"{100 * v:.0f}%")
        lines.append(f"{n} | " + " | ".join(cells) + f" | {r['pool_med']}")
    return "\n".join(lines)
