"""Signal puzzles: a hidden decision list over 64 signals, clues that pin it.

Ported from the team-wallet branch (``game/squid_game/tasks/signal_game/
puzzle.py``, legacy tag ``legacy-2026-09-22``) with the parts this design
does not use removed (underdetermined turns, RULE-line parsing). What is kept
is what makes the task measure effort: every clue set pins the answer to
every query (``exists_differing``), and a trap round is one on which all four
shallow solvers lose.

New here: :func:`deal`, which splits a puzzle's clues over the agents of a
leaderless team so that every agent holds at least one load-bearing clue.
"""

from __future__ import annotations

import collections
import functools
import itertools
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
        return f"{self.color} {self.shape} {self.number}"


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


def _build_atoms() -> tuple[Condition, ...]:
    out = [Condition(f'color == "{c}"', ("color",), _mask(lambda s, c=c: s.color == c), "eq") for c in COLORS]
    out += [Condition(f'shape == "{h}"', ("shape",), _mask(lambda s, h=h: s.shape == h), "eq") for h in SHAPES]
    out += [Condition(f"number == {n}", ("number",), _mask(lambda s, n=n: s.number == n), "eq") for n in NUMBERS]
    out += [Condition(f"number >= {n}", ("number",), _mask(lambda s, n=n: s.number >= n), "range") for n in (2, 3, 4)]
    out += [Condition(f"number <= {n}", ("number",), _mask(lambda s, n=n: s.number <= n), "range") for n in (1, 2, 3)]
    out.append(Condition("number % 2 == 1", ("number",), _mask(lambda s: s.number % 2 == 1), "parity"))
    out.append(Condition("number % 2 == 0", ("number",), _mask(lambda s: s.number % 2 == 0), "parity"))
    return tuple(out)


ATOMS = _build_atoms()
EQ_ATOMS = tuple(a for a in ATOMS if a.kind == "eq")
CONJUNCTIONS = tuple(
    Condition(f"{a.label} and {b.label}", (a.attrs[0], b.attrs[0]), a.mask & b.mask, "and")
    for a, b in itertools.combinations(ATOMS, 2)
    if a.attrs[0] != b.attrs[0]
)
CONDITIONS_BY_ARITY = {1: ATOMS, 2: CONJUNCTIONS}


@dataclass(frozen=True)
class Rule:
    """A decision list; the first clause whose condition holds decides."""

    clauses: tuple[tuple[Condition, str], ...]
    else_action: str
    vector: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        vec = []
        for i in range(len(SIGNAL_SPACE)):
            vec.append(next((a for c, a in self.clauses if c.mask >> i & 1), self.else_action))
        object.__setattr__(self, "vector", tuple(vec))

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(c.arity for c, _ in self.clauses)

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
    """Is there a decision list of *shape* consistent with *clues* (and, when
    *truth* is given, computing a different 64-vector than *truth*)?

    Depth-first over clause positions; a clause may be dead or take any
    condition of its arity that decides a new signal and whose captured clues
    share one label. Memoised on (position, covered, differs).
    """
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
    k = len(shape)
    memo: dict[tuple[int, int, bool], bool] = {}

    def labels(mask: int) -> set[str]:
        return {label[i] for i in _bits(mask)}

    def ok(differs: bool) -> bool:
        return truth is None or differs

    def rec(pos: int, covered: int, differs: bool) -> bool:
        key = (pos, covered, differs)
        if key in memo:
            return memo[key]
        remaining = remaining0 & ~covered
        labs = labels(remaining)
        result = False
        if pos == k:
            if len(labs) <= 1:
                free = FULL_MASK & ~covered
                cands = [next(iter(labs))] if labs else list(ACTIONS)
                result = any(ok(differs or bool(free & ~truth_mask[a])) for a in cands)
        elif len(labs) <= (k - pos) + 1:
            result = rec(pos + 1, covered, differs)
            for cond in CONDITIONS_BY_ARITY[shape[pos]] if not result else ():
                new = cond.mask & ~covered
                fired = labels(remaining & cond.mask)
                if not new or len(fired) > 1:
                    continue
                cands = [next(iter(fired))] if fired else list(ACTIONS)
                if any(rec(pos + 1, covered | cond.mask, differs or bool(new & ~truth_mask[a])) for a in cands):
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
    """One difficulty profile. ``trap_query`` needs ``clauses >= 3``."""

    clauses: int
    conjunctions: int = 0
    predicates: bool = True
    overlap_query: bool = True
    extra_clues: int = 0
    trap_query: bool = False
    n_queries: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.conjunctions <= self.clauses or self.clauses < 1:
            raise ValueError(f"bad clause counts: {self}")
        if self.overlap_query and self.clauses < 2:
            raise ValueError("overlap_query needs clauses >= 2")
        if self.trap_query and self.clauses < 3:
            raise ValueError("trap_query needs clauses >= 3")
        if not 1 <= self.n_queries <= 8:
            raise ValueError("n_queries must be in [1, 8]")


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


def _sample_rule(rng: random.Random, shape: tuple[int, ...], predicates: bool) -> Rule | None:
    """A rule in which every clause decides something and changes the function."""
    eq_labels = {a.label for a in EQ_ATOMS}
    clauses, used, covered, prev = [], set(), 0, None
    for arity in shape:
        pool = CONDITIONS_BY_ARITY[arity]
        if not predicates:
            pool = [c for c in pool if set(c.label.split(" and ")) <= eq_labels]
        cond = rng.choice(pool)
        if cond.label in used or not cond.mask & ~covered:
            return None
        used.add(cond.label)
        prev = rng.choice([a for a in ACTIONS if a != prev])
        clauses.append((cond, prev))
        covered |= cond.mask
    if covered == FULL_MASK:
        return None
    rule = Rule(tuple(clauses), rng.choice([a for a in ACTIONS if a != prev]))
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
    shape = tuple(arities)
    for _ in range(MAX_ATTEMPTS):
        rule = None
        for _ in range(2000):
            rule = _sample_rule(rng, shape, spec.predicates)
            if rule:
                break
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
        if len(spare) < spec.extra_clues:
            continue
        rng.shuffle(spare)
        clues = minimal + spare[: spec.extra_clues]
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
def puzzle_for(seed: int, round_no: int, spec: Spec) -> Puzzle:
    """Deterministic in (seed, round, spec); trap specs reject until a trap."""
    rng = random.Random(f"{seed}:{round_no}")
    for _ in range(MAX_ATTEMPTS if spec.trap_query else 1):
        p = generate(rng, spec)
        if not spec.trap_query or not shallow_correct(p):
            return p
    raise PuzzleError(f"no trap round for {spec}")


# --- dealing clues: every agent holds a bundle ---------------------------------


@dataclass(frozen=True)
class Deal:
    bundles: dict[str, tuple[Clue, ...]]
    needed: frozenset[str]  # agents without whose bundle some query has more than one possible answer


def deal(puzzle: Puzzle, agents: list[str], rng: random.Random) -> Deal:
    """Split the clues so that every agent holds at least one load-bearing clue.

    Load-bearing clues go round-robin, clues some query cannot be pinned without going first, then
    the padding clues. So no agent can solve alone and a missing agent usually costs the round.
    """
    shape = puzzle.rule.shape
    load = [c for c in puzzle.clues if c.signal in puzzle.minimal]
    if len(load) < len(agents):
        raise PuzzleError(f"{len(load)} load-bearing clues cannot give each of {len(agents)} agents one")
    rng.shuffle(load)

    def pins_less(clues: set[Clue]) -> bool:
        rest = [c for c in puzzle.clues if c not in clues]
        return any(len(candidate_actions(shape, rest, q)) > 1 for q in puzzle.queries)

    load.sort(key=lambda c: not pins_less({c}))
    pad = [c for c in puzzle.clues if c not in load]
    bundles: dict[str, list[Clue]] = {a: [] for a in agents}
    for i, clue in enumerate(load + pad):
        bundles[agents[i % len(agents)]].append(clue)
    return Deal({a: tuple(b) for a, b in bundles.items()},
                frozenset(a for a, b in bundles.items() if pins_less(set(b))))
