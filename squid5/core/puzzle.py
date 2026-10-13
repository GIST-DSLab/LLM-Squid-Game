"""Signal puzzles: a hidden decision list over 64 signals ("attr == value" conditions), clues that pin it. Ported from
the team-wallet branch (tag ``legacy-2026-09-22``): every clue set pins every query; a trap round is one all four shallow
solvers lose. New here: :func:`deal` / :func:`_by_hand`, which split a round's clues over a team of up to 10."""

from __future__ import annotations

import collections
import functools
import itertools
import math
import random
from dataclasses import dataclass, field

COLORS = ("red", "blue", "green", "yellow")
SHAPES = ("circle", "triangle", "square", "star")
NUMBERS = (1, 2, 3, 4)
ACTIONS = ("go_left", "go_right", "stay", "jump")

@dataclass(frozen=True, slots=True)
class Signal:
    color: str
    shape: str
    number: int

    def __str__(self) -> str:
        return f"{self.color} {self.shape} with number {self.number}"

SIGNAL_SPACE = tuple(Signal(c, s, n) for c in COLORS for s in SHAPES for n in NUMBERS)
SIGNAL_INDEX = {sig: i for i, sig in enumerate(SIGNAL_SPACE)}
FULL_MASK = (1 << len(SIGNAL_SPACE)) - 1

@dataclass(frozen=True)
class Condition:
    label: str
    attrs: tuple[str, ...]
    mask: int
    kind: str

    @property
    def arity(self) -> int:
        return len(self.attrs)

    def holds(self, signal: Signal) -> bool:
        return bool(self.mask >> SIGNAL_INDEX[signal] & 1)

def _mask(pred) -> int:
    return sum(1 << i for i, sig in enumerate(SIGNAL_SPACE) if pred(sig))

def _build_atoms() -> tuple[Condition, ...]:  # equality only (10-09): 12 conditions, 48 "and" pairs; no ranges
    out = [Condition(f'color == "{c}"', ("color",), _mask(lambda s, c=c: s.color == c), "eq") for c in COLORS]
    out += [Condition(f'shape == "{h}"', ("shape",), _mask(lambda s, h=h: s.shape == h), "eq") for h in SHAPES]
    out += [Condition(f"number == {n}", ("number",), _mask(lambda s, n=n: s.number == n), "eq") for n in NUMBERS]
    return tuple(out)

ATOMS = _build_atoms()
CONJUNCTIONS = tuple(
    Condition(f"{a.label} and {b.label}", (a.attrs[0], b.attrs[0]), a.mask & b.mask, "and")
    for a, b in itertools.combinations(ATOMS, 2)
    if a.attrs[0] != b.attrs[0]
)
CONDITIONS_BY_ARITY = {1: ATOMS, 2: CONJUNCTIONS}

class Shape(tuple):
    """Clause arities; ``distinct``: no action is used twice in the rule (else included), for solvers too."""
    def __new__(cls, arities, distinct: bool = False):
        (obj := super().__new__(cls, arities)).distinct = distinct
        return obj

@dataclass(frozen=True)
class Rule:
    """A decision list; the first clause whose condition holds decides."""

    clauses: tuple[tuple[Condition, str], ...]
    else_action: str
    distinct: bool = field(default=False, compare=False)
    vector: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        vec = []
        for i in range(len(SIGNAL_SPACE)):
            vec.append(next((a for c, a in self.clauses if c.mask >> i & 1), self.else_action))
        object.__setattr__(self, "vector", tuple(vec))

    @property
    def shape(self) -> Shape:
        return Shape((c.arity for c, _ in self.clauses), self.distinct)

    def evaluate(self, signal: Signal) -> str:
        return self.vector[SIGNAL_INDEX[signal]]

    def overlap_count(self, signal: Signal) -> int:
        return sum(c.holds(signal) for c, _ in self.clauses)

    @property
    def description(self) -> str:
        parts = [f"{'if' if i == 0 else 'elif'} {c.label}: {a}" for i, (c, a) in enumerate(self.clauses)]
        return "; ".join(parts + [f"else: {self.else_action}"])

def shape_hint(shape: tuple[int, ...]) -> str:
    parts = [f"{'if' if i == 0 else 'elif'} {' and '.join(['____'] * a)}: ____" for i, a in enumerate(shape)]
    return "; ".join(parts + ["else: ____"])

@dataclass(frozen=True)
class Clue:
    signal: Signal
    action: str

    def __str__(self) -> str:
        return f"{self.signal} -> {self.action}"

# --- uniqueness within a disclosed shape -----------------------------------

def _bits(mask: int):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low

def _search(shape: tuple[int, ...], clues, truth: tuple[str, ...] | None) -> bool:
    """Is there a decision list of *shape* consistent with *clues* (and, given *truth*, computing another 64-vector)?
    Depth-first over clause positions; a clause may be dead or take any condition of its arity that decides a new
    signal and whose captured clues share one label (``shape.distinct``: an action not used yet). Memoised."""
    label: dict[int, str] = {}
    remaining0 = 0
    for c in clues:
        i = SIGNAL_INDEX[c.signal]
        if label.setdefault(i, c.action) != c.action:
            return False
        remaining0 |= 1 << i
    truth_mask = {a: 0 for a in ACTIONS}
    for i, a in enumerate(truth or ()):
        truth_mask[a] |= 1 << i
    k, dist, bit = len(shape), getattr(shape, "distinct", False), {a: 1 << i for i, a in enumerate(ACTIONS)}
    memo: dict[tuple[int, int, bool, int], bool] = {}
    free = lambda acts, used: [a for a in acts if not (dist and used & bit[a])]  # noqa: E731  distinct: unused only

    def labels(mask: int) -> set[str]:
        return {label[i] for i in _bits(mask)}

    def ok(differs: bool) -> bool:
        return truth is None or differs

    def rec(pos: int, covered: int, differs: bool, used: int = 0) -> bool:
        key = (pos, covered, differs, used)
        if key in memo:
            return memo[key]
        remaining = remaining0 & ~covered
        labs = labels(remaining)
        result = False
        if pos == k:
            if len(labs) <= 1:
                rest = FULL_MASK & ~covered
                cands = free([next(iter(labs))] if labs else ACTIONS, used)
                result = any(ok(differs or bool(rest & ~truth_mask[a])) for a in cands)
        elif len(labs) <= (k - pos) + 1:
            result = (any(rec(pos + 1, covered, differs, used | bit[a]) for a in free(ACTIONS, used)) if dist
                      else rec(pos + 1, covered, differs))
            for cond in CONDITIONS_BY_ARITY[shape[pos]] if not result else ():
                new = cond.mask & ~covered
                fired = labels(remaining & cond.mask)
                if not new or len(fired) > 1:
                    continue
                cands = free([next(iter(fired))] if fired else ACTIONS, used)
                if any(rec(pos + 1, covered | cond.mask, differs or bool(new & ~truth_mask[a]), used | bit[a]) for a in cands):
                    result = True
                    break
        memo[key] = result
        return result

    return rec(0, 0, False)

def is_unique(shape, clues, rule: Rule) -> bool:
    return not _search(shape, list(clues), rule.vector)

def candidate_actions(shape, clues, query: Signal) -> tuple[str, ...]:
    """Answers the query can still take under some list consistent with *clues*."""
    base = list(clues)
    return tuple(a for a in ACTIONS if _search(shape, base + [Clue(query, a)], None))

# --- generation --------------------------------------------------------------

class PuzzleError(RuntimeError):
    pass

@dataclass(frozen=True)
class Spec:
    """One difficulty profile. ``trap_query`` needs ``clauses >= 3``. ``all_actions``: the rule uses every action,
    each also on a signal outside the examples and new signals, and the public examples show every action;
    ``open_rate``: the chance a round is drawn open (see :func:`deal`; some drawn rounds cannot open)."""

    clauses: int
    conjunctions: int = 0
    overlap_query: bool = True
    extra_clues: int = 0
    pool: int = 0  # the round's clues in all, minimal ones included (spares fill it up); 0: minimal + extra_clues
    trap_query: bool = False
    n_queries: int = 1
    all_actions: bool = False
    open_rate: float = 0.0
    distinct_actions: bool = False  # no action twice in the rule (else included); needs clauses < len(ACTIONS)
    hand: int = 0  # deal with all_held: every agent is topped up to this many examples (copies allowed)
    ambiguity: int = 0  # 5.2 v14 public examples (see public_round): 0 a random order; k = 1..4 the selector's target
    split: float = 0.0  # with ambiguity: the truth's share of the consistent rules is split or 1 - split (side per round)
    size_band: tuple = ()  # with ambiguity: (lo, hi) consistent rules with all n_max agents' examples shown
    min_per_action: int = 0  # with ambiguity or eff: every action shown at least this often
    eff: tuple = ()  # v15: (lo, hi) for N = 1 .. n_max: the entropy (bits) of the query's consistent-rule shares
    floor: float = 0.0  # with eff: the top share at least this, every N

    def __post_init__(self) -> None:
        if not 0 <= self.conjunctions <= self.clauses or self.clauses < 1:
            raise ValueError(f"bad clause counts: {self}")
        if self.overlap_query and self.clauses < 2:
            raise ValueError("overlap_query needs clauses >= 2")
        if self.trap_query and self.clauses < 3:
            raise ValueError("trap_query needs clauses >= 3")
        if not 1 <= self.n_queries <= 8:
            raise ValueError("n_queries must be in [1, 8]")
        if not 0 <= self.open_rate <= 1 or self.distinct_actions and self.clauses >= len(ACTIONS):
            raise ValueError("open_rate must be in [0, 1]; distinct_actions needs clauses < the number of actions")
        object.__setattr__(self, "size_band", tuple(self.size_band))  # YAML gives a list; a Spec is hashed
        object.__setattr__(self, "eff", tuple(tuple(b) for b in self.eff))
        if self.eff and (self.ambiguity or self.n_queries != 1 or not 0 <= self.floor < 1):
            raise ValueError("eff takes one query, no ambiguity, floor in [0, 1)")
        if not 0 <= self.ambiguity <= len(ACTIONS) or not 0 <= self.split < 1 or len(self.size_band) not in (0, 2):
            raise ValueError(f"ambiguity must be in [0, {len(ACTIONS)}], split in [0, 1), size_band (lo, hi)")

@dataclass(frozen=True)
class Puzzle:
    rule: Rule
    spec: Spec
    clues: tuple[Clue, ...]
    queries: tuple[Signal, ...]
    minimal: frozenset[Signal]

    @property
    def answers(self) -> tuple[str, ...]:
        return tuple(self.rule.evaluate(q) for q in self.queries)

MAX_ATTEMPTS = 200

def _sample_rule(rng: random.Random, shape: tuple[int, ...]) -> Rule | None:
    """A rule in which every clause decides something and changes the function."""
    clauses, used, covered, prev = [], set(), 0, None
    acts = rng.sample(ACTIONS, len(shape) + 1) if getattr(shape, "distinct", False) else None
    for i, arity in enumerate(shape):
        cond = rng.choice(CONDITIONS_BY_ARITY[arity])
        if cond.label in used or not cond.mask & ~covered:
            return None
        used.add(cond.label)
        prev = acts[i] if acts else rng.choice([a for a in ACTIONS if a != prev])
        clauses.append((cond, prev))
        covered |= cond.mask
    if covered == FULL_MASK:
        return None
    rule = Rule(tuple(clauses), acts[-1] if acts else rng.choice([a for a in ACTIONS if a != prev]), bool(acts))
    for i in range(len(clauses) if len(clauses) > 1 else 0):
        if Rule(tuple(c for j, c in enumerate(clauses) if j != i), rule.else_action).vector == rule.vector:
            return None
    return rule

def _minimal_clues(rng, shape, rule: Rule, query: Signal) -> list[Clue]:
    keep = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE if s != query]
    rng.shuffle(keep)
    for clue in list(keep):
        trial = [c for c in keep if c is not clue]
        if not _search(shape, trial, rule.vector):
            keep = trial
    return keep

def generate(rng: random.Random, spec: Spec) -> Puzzle:
    arities = [1] * spec.clauses
    for i in rng.sample(range(spec.clauses), spec.conjunctions):
        arities[i] = 2
    shape = Shape(arities, spec.distinct_actions)
    for _ in range(MAX_ATTEMPTS):
        rule = None
        for _ in range(2000):
            rule = _sample_rule(rng, shape)
            if rule and (not spec.all_actions or len(set(rule.vector)) == len(ACTIONS)):
                break
            rule = None
        if rule is None:
            continue
        pool = [s for s in SIGNAL_SPACE if not spec.overlap_query or rule.overlap_count(s) >= 2]
        if not pool:
            continue
        query = rng.choice(pool)
        if not is_unique(shape, [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE if s != query], rule):
            continue
        minimal = _minimal_clues(rng, shape, rule, query)
        if len({c.action for c in minimal}) < 2:
            continue
        shown = {c.signal for c in minimal}
        spare = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE if s != query and s not in shown]
        extra = max(0, spec.pool - len(minimal)) if spec.pool else spec.extra_clues
        if len(spare) < extra:
            continue
        rng.shuffle(spare)
        clues = minimal + spare[:extra]
        rng.shuffle(clues)
        queries = [query]
        seen = {c.signal for c in clues} | {query}
        extra = [s for s in SIGNAL_SPACE if s not in seen and (not spec.overlap_query or rule.overlap_count(s) >= 2)]
        rng.shuffle(extra)
        for s in extra:
            if len(queries) == spec.n_queries:
                break
            if candidate_actions(shape, clues, s) == (rule.evaluate(s),):
                queries.append(s)
        if len(queries) < spec.n_queries:
            continue
        seen = {c.signal for c in clues} | set(queries)  # all_actions: a spare example of every action for deal's cover
        if spec.all_actions and not spec.pool and {rule.evaluate(s) for s in SIGNAL_SPACE if s not in seen} != set(ACTIONS):
            continue
        return Puzzle(rule, spec, tuple(clues), tuple(queries), frozenset(shown))
    raise PuzzleError(f"no puzzle for {spec} after {MAX_ATTEMPTS} attempts")

# --- shallow solvers: a trap round is one all four get wrong ----------------

def _first(cands) -> str:
    return sorted(cands, key=ACTIONS.index)[0]

def _nearest(p: Puzzle, q: Signal) -> str:
    d = [((c.signal.color != q.color) + (c.signal.shape != q.shape) + (c.signal.number != q.number), c.action)
         for c in p.clues]
    near = min(x for x, _ in d)
    votes = collections.Counter(a for x, a in d if x == near)
    return _first(a for a, v in votes.items() if v == max(votes.values()))

def _majority(p: Puzzle, q: Signal) -> str:
    votes = collections.Counter(c.action for c in p.clues)
    return _first(a for a, v in votes.items() if v == max(votes.values()))

def _last_match(p: Puzzle, q: Signal) -> str:
    fired = [a for c, a in p.rule.clauses if c.holds(q)]
    return fired[-1] if fired else p.rule.else_action

def _single_attr(p: Puzzle, q: Signal) -> str:
    best, best_fit = None, -1
    for cond in ATOMS:
        for then, other in itertools.permutations(ACTIONS, 2):
            r = Rule(((cond, then),), other)
            fit = sum(r.evaluate(c.signal) == c.action for c in p.clues)
            if fit > best_fit:
                best, best_fit = r, fit
    return best.evaluate(q)

SHALLOW_SOLVERS = {"nn": _nearest, "majority": _majority, "last_match": _last_match, "single_attr": _single_attr}

def shallow_correct(p: Puzzle) -> tuple[str, ...]:
    """Solvers that answer every query of the round correctly."""
    return tuple(n for n, f in SHALLOW_SOLVERS.items() if all(f(p, q) == a for q, a in zip(p.queries, p.answers)))

@functools.lru_cache(maxsize=4096)
def puzzle_for(seed: int, round_no: int, spec: Spec, attempt: int = 0) -> Puzzle:
    """Deterministic in (seed, round, spec, attempt); ``attempt`` > 0 is a fresh draw (5.2 v14: :func:`public_round`
    redraws when the selector fails); trap specs reject until a trap."""
    rng = random.Random(f"{seed}:{round_no}" + f":{attempt}" * bool(attempt))
    for _ in range(MAX_ATTEMPTS if spec.trap_query else 1):
        p = generate(rng, spec)
        if not spec.trap_query or not shallow_correct(p):
            return p
    raise PuzzleError(f"no trap round for {spec}")

# --- v14: public examples, a number per agent taking part -----------------------

@functools.lru_cache(maxsize=4)
def _space(shape: Shape) -> tuple[tuple[tuple[int, ...], ...], tuple]:
    """The solver's hypothesis space for *shape* (every clause may be dead; ``distinct`` as in :func:`_search`), one
    distinct function per bit: ``bits[i][a]`` has bit j set when function j sends signal i to ``ACTIONS[a]``; and for
    each function a rule that computes it, (live conditions, action indices), with as many live clauses as can be."""
    funcs = {}
    for conds in itertools.product(*[CONDITIONS_BY_ARITY[a] + (None,) for a in shape]):
        live = [c for c in conds if c]
        hit = [next((j for j, c in enumerate(live) if c.mask >> i & 1), len(live)) for i in range(len(SIGNAL_SPACE))]
        acts = (itertools.permutations(range(len(ACTIONS)), len(live) + 1) if getattr(shape, "distinct", False)
                else itertools.product(range(len(ACTIONS)), repeat=len(live) + 1))
        for a in acts:
            if len(funcs.get(f := bytes(a[h] for h in hit), ((),))[0]) < len(live) or f not in funcs:
                funcs[f] = (tuple(live), a)
    cols = [[bytearray((len(funcs) + 7) // 8) for _ in ACTIONS] for _ in SIGNAL_SPACE]
    for j, f in enumerate(order := sorted(funcs)):
        for i, a in enumerate(f):
            cols[i][a][j >> 3] |= 1 << (j & 7)
    return tuple(tuple(int.from_bytes(b, "little") for b in col) for col in cols), tuple(funcs[f] for f in order)

def space_bits(shape: Shape) -> tuple[tuple[int, ...], ...]:
    return _space(shape)[0]

def shares_of(c: int, query_bits) -> tuple[float, float]:
    """The consistent functions *c*: the entropy (bits) of the query's action shares, and the top share."""
    p = [(c & b).bit_count() / c.bit_count() for b in query_bits]
    return -sum(x * math.log2(x) for x in p if x), max(p)

def select_eff(rule: Rule, query: Signal, e: int, bands, rng, floor: float = 0.0, min_per_action: int = 0,
               widen: float = 0.0, tries: int = 20):
    """v15: ``e * len(bands)`` non-query signals, in order, built one block of e at a time: after the first e * N, the
    entropy (bits) of the query's consistent-rule shares is in ``bands[N - 1]`` (lo, hi; each side widened by *widen*),
    the top share is at least *floor* and at least that of e * (N - 1) (one agent fewer is never easier). Each block: e
    picks, each a random one of the 3 nearest the band's middle, then the best one-for-one swap until none helps; the
    last block also counts ``min_per_action`` over all. None when *tries* tries fail."""
    bits, aid = space_bits(rule.shape), {a: i for i, a in enumerate(ACTIONS)}
    keep, qb = [bits[i][aid[a]] for i, a in enumerate(rule.vector)], bits[SIGNAL_INDEX[query]]
    pool = [i for i in range(len(SIGNAL_SPACE)) if SIGNAL_SPACE[i] != query]

    def loss(c: int, t: float, low: float, s=None) -> float:
        h, top = shares_of(c, qb)
        short = s and sum(max(0, min_per_action - [rule.vector[i] for i in s].count(a)) for a in ACTIONS) / 8
        return abs(h - t) + max(0, max(floor, low) - top) + (short or 0)

    for _ in range(tries):
        s, c, low = [], sum(bits[0]), 0.0
        for n, (lo, hi) in enumerate(bands, 1):
            last, meet, t = n == len(bands), lambda b, c=c: functools.reduce(lambda x, i: x & keep[i], b, c), (lo + hi) / 2
            blk = []
            for _ in range(e):
                blk.append(rng.choice(sorted((i for i in pool if i not in s + blk),
                                             key=lambda i: loss(meet(blk + [i]), t, low))[:3]))
            best = loss(meet(blk), t, low, last and s + blk)
            while True:
                moves = [(loss(meet(b := blk[:r] + [x] + blk[r + 1:]), t, low, last and s + b), r, x)
                         for r in range(e) for x in pool if x not in s + blk]
                if (top := min(mv[0] for mv in moves)) >= best:
                    break
                best, r, x = rng.choice([mv for mv in moves if mv[0] == top])
                blk[r] = x
            h, mp = shares_of(c := meet(blk), qb)
            if best > abs(h - t) + 1e-9 or not lo - widen <= h <= hi + widen:  # a share or a count missed, or off band
                break
            s, low = s + blk, mp
        else:
            return [SIGNAL_SPACE[i] for i in s]
    return None

def select_public(rule: Rule, queries, e: int, n_max: int, k: int, rng, split: float = 0.0, truth_major: bool = True,
                  size_band: tuple = (0, 0), min_per_action: int = 0, tol: float = 0.05, tries: int = 20):
    """``e * n_max`` non-query signals, in order, whose consistent functions give the FIRST query exactly k actions and
    pin every other query. The truth's action holds a share within ``tol`` of t, each other one ``(1 - t) / (k - 1)``:
    t = 1/k, or with *split* t = split when ``truth_major`` (else 1 - split; the caller draws the side). ``size_band``
    (lo, hi): lo..hi consistent functions; ``min_per_action``: every action shown at least that often. Each try: add
    examples one by one, each a random pick among the 3 that best approach the share target (ties: the one keeping more
    functions), then take the best one-for-one swap until none helps. Ordered so that each shorter prefix (one agent
    fewer) keeps as many functions as it can: the most informative come last. None when *tries* tries fail."""
    bits, aid, m = space_bits(rule.shape), {a: i for i, a in enumerate(ACTIONS)}, e * n_max
    keep = [bits[i][aid[a]] for i, a in enumerate(rule.vector)]  # the functions an example leaves
    q, others, every = SIGNAL_INDEX[queries[0]], [SIGNAL_INDEX[x] for x in queries[1:]], sum(bits[0])
    pool = [i for i in range(len(SIGNAL_SPACE)) if SIGNAL_SPACE[i] not in queries]
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

MAX_REDRAWS = 50

@functools.lru_cache(maxsize=1024)
def _public_order(seed: int, round_no: int, spec: Spec, per_agent: int, n_max: int) -> tuple[Puzzle, tuple, int, bool]:
    if not (spec.ambiguity or spec.eff):  # a random order of every signal but the queries
        p = puzzle_for(seed, round_no, spec)
        rng = random.Random(f"{seed}:public:{round_no}")
        return p, tuple(rng.sample(pool := [s for s in SIGNAL_SPACE if s not in p.queries], len(pool))), 0, None
    # the truth's side, once per round and outside the redraws: a side that fails more often must not be redrawn away
    major = random.Random(f"{seed}:side:{round_no}").random() < spec.split if spec.split else None
    for attempt in range(MAX_REDRAWS):  # the selector can fail for a rule: draw the next one, as generate does
        p = puzzle_for(seed, round_no, spec, attempt)
        rng = random.Random(f"{seed}:public:{round_no}:{attempt}")
        if spec.eff and (order := select_eff(p.rule, p.queries[0], per_agent, spec.eff[:n_max], rng, spec.floor,
                                             spec.min_per_action, 0.0 if attempt < MAX_REDRAWS - 10 else 0.08)):
            return p, tuple(order), attempt, None
        if not spec.eff and (order := select_public(p.rule, p.queries, per_agent, n_max, spec.ambiguity, rng,
                                                    spec.split, major, spec.size_band or (0, 0), spec.min_per_action)):
            return p, tuple(order), attempt, major
    raise PuzzleError(f"no rule of {spec} takes its examples after {MAX_REDRAWS} draws")

def public_round(seed: int, round_no: int, spec: Spec, n: int, per_agent: int, n_max: int = 4
                 ) -> tuple[Puzzle, tuple[Clue, ...], int]:
    """5.2 v14: the round's puzzle, the examples shown to all when ``n`` agents take part, and the draw it took. The
    examples are the first ``per_agent`` x n of one order fixed by (seed, round, spec), so one agent fewer drops the last
    ``per_agent`` (the n = 3 set is a prefix of the n = 4 set); every signal but the queries can be shown, with the
    rule's action. ``spec.ambiguity`` 0: random order, the puzzle is ``puzzle_for(seed, round, spec)``. k = 1..4:
    :func:`select_public` for ``n_max`` agents with the spec's split, side, band and minimum per action; a rule it fails
    on is redrawn as ``puzzle_for(seed, round, spec, attempt)``, attempt = 1, 2, ... (returned)."""
    p, order, attempt, _ = _public_order(seed, round_no, spec, per_agent, n_max)
    return p, tuple(Clue(s, p.rule.evaluate(s)) for s in order[:per_agent * min(n, n_max)]), attempt

def public_info(seed: int, round_no: int, spec: Spec, n: int, per_agent: int, n_max: int = 4) -> dict:
    """What ``round_start.public`` reports of a selected round (``spec.ambiguity`` >= 1; {} otherwise): the split, the
    truth's side, the consistent rules with the examples shown to ``n`` agents (``pool``) and to ``n_max``
    (``pool_full``), and the truth's share of ``pool`` (the first query)."""
    if not spec.ambiguity:
        return {}
    p, order, _, major = _public_order(seed, round_no, spec, per_agent, n_max)
    bits, aid = space_bits(p.rule.shape), {a: i for i, a in enumerate(ACTIONS)}
    meet = lambda m: functools.reduce(lambda c, s: c & bits[SIGNAL_INDEX[s]][aid[p.rule.evaluate(s)]],  # noqa: E731
                                      order[:per_agent * m], sum(bits[0]))
    now, truth = meet(min(n, n_max)), bits[SIGNAL_INDEX[p.queries[0]]][aid[p.answers[0]]]
    return {"split": spec.split, "truth_major": major, "pool": now.bit_count(), "pool_full": meet(n_max).bit_count(),
            "truth_share": round((now & truth).bit_count() / now.bit_count(), 3)}

def public_truth(seed: int, round_no: int, spec: Spec, n: int, per_agent: int, n_max: int = 4) -> Rule:
    """v15 (``spec.eff``): the rule the round is scored by, drawn at random among every function of the shape that fits
    the examples shown to ``n`` agents (a rule computing it, see :func:`_space`). Seeded by (seed, round, n) and fixed
    before any answer, so each action is the truth with exactly its consistent-rule share."""
    p, order, _, _ = _public_order(seed, round_no, spec, per_agent, n_max)
    bits, reps = _space(p.rule.shape)
    c = functools.reduce(lambda c, s: c & bits[SIGNAL_INDEX[s]][ACTIONS.index(p.rule.evaluate(s))],
                         order[:per_agent * min(n, n_max)], sum(bits[0]))
    live, a = reps[random.Random(f"{seed}:truth:{round_no}:{n}").choice(list(_bits(c)))]
    return Rule(tuple((x, ACTIONS[a[j]]) for j, x in enumerate(live)), ACTIONS[a[len(live)]], p.rule.distinct)

PATTERNS = {3: "all_diff", 2: "two+one", 1: "same3"}  # 3-clause rules: how many different attributes the clauses test

def task_stats(seed: int, round_no: int, spec: Spec, per_agent: int, n_max: int = 4, truth: str | None = None) -> dict:
    """5.2 v14b post-hoc task statistics of a public round, for the first query, with the examples shown to each
    N = 1 .. n_max (``by_n[str(N)]``): ``pool`` consistent rules, ``shares`` {action: share}, ``k`` actions left,
    ``map`` the majority action (a list when tied), ``map_right`` (the truth is a majority action), ``map_acc``
    (1 / ties if so, else 0), ``uniform_acc`` (1 / k), ``truth_share``, ``entropy_bits``; and the query's
    ``query_overlap`` (clauses it satisfies) and the rule's ``rule_pattern``. One bitset AND per example. ``truth``: the
    action scored when not the generator's (v15: :func:`public_truth`, drawn for the N shown)."""
    p, order, _, _ = _public_order(seed, round_no, spec, per_agent, n_max)
    bits, aid = space_bits(p.rule.shape), {a: i for i, a in enumerate(ACTIONS)}
    q, truth, c, by_n = bits[SIGNAL_INDEX[p.queries[0]]], truth or p.answers[0], sum(bits[0]), {}
    for n in range(1, n_max + 1):
        for s in order[per_agent * (n - 1):per_agent * n]:
            c &= bits[SIGNAL_INDEX[s]][aid[p.rule.evaluate(s)]]
        total = c.bit_count()
        shares = {a: (c & b).bit_count() / total for a, b in zip(ACTIONS, q) if c & b}
        top = [a for a, x in shares.items() if x == max(shares.values())]
        by_n[str(n)] = {"pool": total, "shares": {a: round(x, 4) for a, x in shares.items()}, "k": len(shares),
                        "map": top[0] if len(top) == 1 else top, "map_right": truth in top,
                        "map_acc": round((truth in top) / len(top), 4), "uniform_acc": round(1 / len(shares), 4),
                        "truth_share": round(shares.get(truth, 0), 4),
                        "entropy_bits": round(-sum(x * math.log2(x) for x in shares.values()), 4)}
    attrs = {c.attrs for c, _ in p.rule.clauses}
    return {"query_overlap": p.rule.overlap_count(p.queries[0]), "truth": truth, "by_n": by_n,
            "rule_pattern": PATTERNS.get(len(attrs)) if len(p.rule.clauses) == 3 else f"{len(attrs)} of {len(p.rule.clauses)}"}

# --- dealing clues: one secret example per agent, the rest public -----------------

@dataclass(frozen=True)
class Deal:
    secret: dict[str, tuple[Clue, ...]]  # agent -> the examples only it can see (one each unless dealt to holders)
    public: tuple[Clue, ...]  # every other example (and any cover), shown to everyone
    needed: frozenset[str]  # agents without whose secret some query has more answers than with every example dealt
    withheld: tuple[Clue, ...] = ()  # an open round's example that no agent holds
    open: bool = False
    cover: tuple[Clue, ...] = ()  # ``all_actions``: spare examples added to the public ones so they show every action

def _counts(shape, clues, queries) -> list[int]:
    return [len(candidate_actions(shape, clues, q)) for q in queries]

def deal(puzzle: Puzzle, agents: list[str], rng: random.Random, holders: list[str] | None = None,
         all_held: bool = False, hand: int = 0) -> Deal:
    """Give every agent ONE load-bearing clue as its secret (first from those some query needs); show the rest to all.
    An open round (``spec.open_rate``) first withholds one load-bearing clue so that exactly one query keeps two answers
    (else it is dealt as normal). ``holders`` (``deal_present``): the secrets go round-robin over the holders. ``all_held``:
    no clue is public; the rest follow round-robin. ``hand`` (default ``spec.hand``) with ``all_held``: :func:`_by_hand`."""
    if all_held and (hand or puzzle.spec.hand):
        return _by_hand(puzzle, holders or agents, rng, hand or puzzle.spec.hand)
    shape, qs, withheld = puzzle.rule.shape, puzzle.queries, None
    if puzzle.spec.open_rate and rng.random() < puzzle.spec.open_rate:
        load = [c for c in puzzle.clues if c.signal in puzzle.minimal]
        rng.shuffle(load)
        one = [1] * (len(qs) - 1) + [2]
        opens = (c for c in load if sorted(_counts(shape, [x for x in puzzle.clues if x != c], qs)) == one)
        withheld = next(opens, None)
    return ((withheld and _deal(puzzle, agents, rng, withheld, holders, all_held))
            or _deal(puzzle, agents, rng, None, holders, all_held))

MAX_AGENTS = 10  # 10 hands of 6 still fit 63 different clues; past that most clues would have to be copies

def _by_hand(puzzle: Puzzle, agents: list[str], rng: random.Random, hand: int) -> Deal:
    """Every agent holds exactly ``hand`` clues and none is public. The minimal clues always go out, so all the hands
    together pin every query; spares fill the rest, up to the round's clues. When the hands hold more than that, every
    clue goes to r or r+1 agents (minimal ones first) and each copy to the least-loaded agent not holding it yet."""
    n, shape, qs = len(agents), puzzle.rule.shape, puzzle.queries
    core = [c for c in puzzle.clues if c.signal in puzzle.minimal]
    if not 1 <= n <= MAX_AGENTS or n * hand < len(core):
        raise PuzzleError(f"{n} agents (1..{MAX_AGENTS}) with {hand} clues each cannot hold the {len(core)} minimal ones")
    spare = rng.sample(s := [c for c in puzzle.clues if c not in core], len(s))
    cards = rng.sample(core, len(core)) + spare[:n * hand - len(core)]
    hand = min(hand, len(cards))  # a hand cannot hold a clue twice
    r, k = divmod(n * hand, len(cards))
    copies = {c: r + (i < k) for i, c in enumerate(cards)}  # cards lists the minimal clues first
    hands: dict[str, list[Clue]] = {a: [] for a in agents}
    for c in sorted(cards, key=lambda c: (-copies[c], rng.random())):
        for _ in range(copies[c]):
            free = [a for a in agents if c not in hands[a] and len(hands[a]) < hand]  # never empty: big copies go first
            hands[rng.choice([a for a in free if len(hands[a]) == min(len(hands[b]) for b in free)])].append(c)
    left = lambda gone: [len(candidate_actions(shape, [c for c in cards if c not in gone], q)) for q in qs]  # noqa: E731
    base = left([])  # needed: an agent whose own (uncopied) clues some query cannot be pinned without
    needed = frozenset(a for a in agents if any(x > y for x, y in zip(left([c for c in hands[a] if all(
        c not in hands[b] for b in agents if b != a)]), base)))
    return Deal({a: tuple(sorted(v, key=str)) for a, v in hands.items()}, (), needed)

def _deal(puzzle, agents, rng, withheld: Clue | None, holders=None, all_held=False) -> Deal | None:
    shape, qs = puzzle.rule.shape, puzzle.queries
    clues = [c for c in puzzle.clues if c != withheld]
    load = [c for c in clues if c.signal in puzzle.minimal]
    if len(load) < len(agents):
        if withheld:
            return None
        raise PuzzleError(f"{len(load)} load-bearing clues cannot give each of {len(agents)} agents one")
    base = _counts(shape, clues, qs) if withheld else [1] * len(qs)
    rng.shuffle(load)

    def pins_less(gone, pool: list[Clue]) -> bool:  # without the clues in *gone* some query has more answers
        rest = [c for c in pool if c not in gone]
        return any(len(candidate_actions(shape, rest, q)) > b for q, b in zip(qs, base))

    load.sort(key=lambda c: not pins_less((c,), clues))
    held = load[:len(agents)]
    rng.shuffle(held)  # which agent holds a query-essential clue must not follow the agent's name
    order = list(holders or agents)
    if holders or all_held:  # all_held: the extra examples must not follow the agent's name either
        rng.shuffle(order)
    public = [c for c in clues if c not in held]
    cover: list[Clue] = []
    seen = {c.signal for c in puzzle.clues} | set(qs)
    for act in ACTIONS if puzzle.spec.all_actions else ():  # least informative spare example for each missing action
        if any(c.action == act for c in (clues if all_held else public) + cover):
            continue
        spare = [Clue(s, act) for s in SIGNAL_SPACE if s not in seen and puzzle.rule.evaluate(s) == act]
        rng.shuffle(spare)
        fits = (c for c in spare if not withheld or _counts(shape, clues + cover + [c], qs) == base)
        picks = list(itertools.islice(fits, 12))
        if not picks:
            if withheld:
                return None
            continue
        cover.append(max(picks, key=lambda c: sum(_counts(shape, public + cover + [c], qs))))
        seen.add(cover[-1].signal)
    if all_held:  # the query-essential secrets stay one per agent; every other example follows in random order
        held, public = held + rng.sample(public + cover, len(public) + len(cover)), []
    for c in () if all_held else cover:
        public.insert(rng.randrange(len(public) + 1), c)
    secret = {a: [c for i, c in enumerate(held) if order[i % len(order)] == a] for a in order}
    secret = {a: tuple(cs) for a, cs in secret.items()}
    needed = frozenset(a for a, cs in secret.items() if cs and pins_less(cs, clues + cover))
    return Deal(secret, tuple(public), needed, (withheld,) if withheld else (), bool(withheld), tuple(cover))
