"""v14 public examples with a set ambiguity (v2, 10-10 13:05): k answers left for the query at full length, the truth
holding a set share of the consistent functions. Written to replace space_bits/select_public in squid5/core/puzzle.py
(replace the import below by the module's own names)."""
import functools
import itertools

from puzzle_v2 import ACTIONS, CONDITIONS_BY_ARITY, SIGNAL_INDEX, SIGNAL_SPACE, Rule, Shape


@functools.lru_cache(maxsize=4)
def space_bits(shape: Shape) -> tuple[tuple[int, ...], ...]:
    """The solver's hypothesis space for *shape* (every clause may be dead; ``distinct`` as in :func:`_search`), one
    distinct function per bit: ``bits[i][a]`` has bit j set when function j sends signal i to ``ACTIONS[a]``."""
    funcs = set()
    for conds in itertools.product(*[(None,) + CONDITIONS_BY_ARITY[a] for a in shape]):
        live = [c for c in conds if c]
        hit = [next((j for j, c in enumerate(live) if c.mask >> i & 1), len(live)) for i in range(len(SIGNAL_SPACE))]
        acts = (itertools.permutations(range(len(ACTIONS)), len(live) + 1) if getattr(shape, "distinct", False)
                else itertools.product(range(len(ACTIONS)), repeat=len(live) + 1))
        funcs.update(bytes(a[h] for h in hit) for a in acts)
    cols = [[bytearray((len(funcs) + 7) // 8) for _ in ACTIONS] for _ in SIGNAL_SPACE]
    for j, f in enumerate(sorted(funcs)):
        for i, a in enumerate(f):
            cols[i][a][j >> 3] |= 1 << (j & 7)
    return tuple(tuple(int.from_bytes(b, "little") for b in col) for col in cols)


def ambiguity(rule, signals, queries) -> tuple[int, list[list[int]]]:
    """Functions consistent with *rule* on *signals*, and per query how many of them give each action."""
    bits, aid = space_bits(rule.shape), {a: i for i, a in enumerate(ACTIONS)}
    c = sum(bits[0])  # every function: signal 0 goes to exactly one action
    for s in signals:
        c &= bits[SIGNAL_INDEX[s]][aid[rule.evaluate(s)]]
    return c.bit_count(), [[(c & b).bit_count() for b in bits[SIGNAL_INDEX[q]]] for q in queries]


def select_public(rule: Rule, queries, e: int, n_max: int, k: int, rng, split: float = 0.0,
                  truth_major: bool | None = None, size_band: tuple[int, int] = (0, 0), min_per_action: int = 0,
                  tol: float = 0.05, tries: int = 20):
    """``e * n_max`` non-query signals, in order, whose consistent functions give the FIRST query exactly k actions and
    pin every other query. The truth's action holds a share within ``tol`` of t, each other one ``(1 - t) / (k - 1)``:
    t = 1/k, or with *split* t = split when ``truth_major`` (else 1 - split; drawn from rng with odds *split* when None,
    before the search). ``size_band`` (lo, hi): lo..hi consistent functions; ``min_per_action``: every action shown at
    least that often. Each try: add examples one by one, each a random pick among the 3 that best approach the share
    target (ties: the one keeping more functions), then take the best one-for-one swap until none helps. Ordered so
    that each shorter prefix (one agent fewer) keeps as many functions as it can: the most informative come last. None
    when *tries* tries fail."""
    bits, aid, m = space_bits(rule.shape), {a: i for i, a in enumerate(ACTIONS)}, e * n_max
    keep = [bits[i][aid[a]] for i, a in enumerate(rule.vector)]  # the functions an example leaves
    q, others, every = SIGNAL_INDEX[queries[0]], [SIGNAL_INDEX[x] for x in queries[1:]], sum(bits[0])
    pool = [i for i in range(len(SIGNAL_SPACE)) if SIGNAL_SPACE[i] not in queries]
    if split and truth_major is None:
        truth_major = rng.random() < split
    t = (split if truth_major else 1 - split) if split else 1 / k
    tq, lo, hi = aid[rule.vector[q]], size_band[0] or 1, size_band[1] or every.bit_count()

    def loss(c: int, s=None) -> tuple[float, bool]:
        n = c.bit_count()
        p = [(c & b).bit_count() / n for b in bits[q]]
        rest = sorted((x for a, x in enumerate(p) if a != tq), reverse=True)
        miss = sum(1 - (c & keep[o]).bit_count() / n for o in others)  # other queries must be pinned
        err = [abs(p[tq] - t)] + [abs(x - (1 - t) / (k - 1)) for x in rest[:k - 1]]
        short = s and sum(max(0, min_per_action - [rule.vector[i] for i in s].count(a)) for a in ACTIONS) / m
        far = s and (max(0, lo - n) / lo + max(0, n - hi) / hi) / 4
        return (round(sum(err) + sum(rest[k - 1:]) + miss + (short or 0) + (far or 0), 9),
                not (miss or short or far or any(rest[k - 1:])) and max(err) <= tol)

    def meet(ids) -> int:
        return functools.reduce(lambda c, i: c & keep[i], ids, every)

    for _ in range(tries):
        s, c = [], every
        for _ in range(m):
            s.append(x := rng.choice(sorted((i for i in pool if i not in s),
                                            key=lambda i: (loss(c & keep[i])[0], -(c & keep[i]).bit_count()))[:3]))
            c &= keep[x]
        best = loss(c, s)
        while not best[1]:
            pre, suf = [-1], [-1]
            for i, j in zip(s, reversed(s)):
                pre.append(pre[-1] & keep[i])
                suf.append(suf[-1] & keep[j])
            moves = [(loss(pre[r] & suf[m - 1 - r] & keep[x], s[:r] + [x] + s[r + 1:]), r, x)
                     for r in range(m) for x in pool if x not in s]
            top = min(mv[0][0] for mv in moves)
            if top >= best[0]:
                break
            best, r, x = rng.choice([mv for mv in moves if mv[0][0] == top])
            s[r] = x
        if best[1]:
            order = []  # from the back: the example whose removal frees the most functions goes last
            while s:
                s.remove(gone := max(rng.sample(s, len(s)), key=lambda i: meet(j for j in s if j != i).bit_count()))
                order.append(gone)
            return [SIGNAL_SPACE[i] for i in reversed(order)]
    return None
