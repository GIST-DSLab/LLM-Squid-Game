"""Per-turn puzzle mode for the Signal Game, v2 (spec 2026-09-06).

Every turn is an independent induction puzzle whose hidden rule is a
Python-style decision list::

    if <cond_1>: <act_1>
    elif <cond_2>: <act_2>
    ...
    else: <act_else>

The *shape* of the list (how many clauses, which of them are ``and``
conjunctions) is disclosed to the agent; the conditions and actions are
hidden. Clues are ``signal -> action`` pairs generated so that, within
the disclosed shape and the condition grammar below, every decision list
consistent with the clues computes the same function over all 64
signals. The query answer is therefore unique too.

Pure functions and frozen dataclasses only; ``SignalGameModule``
(module.py) is the only caller on the run path.

Grammar (spec §3):

    atomic     color == "red" | shape == "star" | number == 3        (12)
               number >= 2|3|4 | number <= 1|2|3                     (6)
               number % 2 == 1 | number % 2 == 0                     (2)
    conjunction <atomic> and <atomic> on two different attributes   (112)

Every condition is a 64-bit mask over ``SIGNAL_SPACE`` (colour-major);
a rule is its 64-entry action vector.
"""

from __future__ import annotations

import functools
import itertools
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import COLORS, NUMBERS, SHAPES, Signal

ATTRIBUTES: tuple[str, ...] = ("color", "shape", "number")
ATTR_VALUES: dict[str, list] = {"color": COLORS, "shape": SHAPES, "number": NUMBERS}

#: Colour-major enumeration of every signal; the index is the bit position
#: in every mask and the position in every ``PuzzleRule.vector``.
SIGNAL_SPACE: tuple[Signal, ...] = tuple(
    Signal(color=c, shape=s, number=n) for c in COLORS for s in SHAPES for n in NUMBERS
)
SIGNAL_INDEX: dict[Signal, int] = {sig: i for i, sig in enumerate(SIGNAL_SPACE)}
FULL_MASK: int = (1 << len(SIGNAL_SPACE)) - 1


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """One test on a signal, as Python text plus its 64-bit mask.

    ``kind`` is ``"eq"`` / ``"range"`` / ``"parity"`` for atoms and
    ``"and"`` for conjunctions; ``attrs`` lists the attributes the test
    reads (one for atoms, two distinct ones for conjunctions).
    """

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
    m = 0
    for i, sig in enumerate(SIGNAL_SPACE):
        if pred(sig):
            m |= 1 << i
    return m


def _build_atoms() -> tuple[Condition, ...]:
    out: list[Condition] = []
    for c in COLORS:
        out.append(Condition(f'color == "{c}"', ("color",), _mask(lambda s, c=c: s.color == c), "eq"))
    for sh in SHAPES:
        out.append(Condition(f'shape == "{sh}"', ("shape",), _mask(lambda s, sh=sh: s.shape == sh), "eq"))
    for n in NUMBERS:
        out.append(Condition(f"number == {n}", ("number",), _mask(lambda s, n=n: s.number == n), "eq"))
    for n in (2, 3, 4):
        out.append(Condition(f"number >= {n}", ("number",), _mask(lambda s, n=n: s.number >= n), "range"))
    for n in (1, 2, 3):
        out.append(Condition(f"number <= {n}", ("number",), _mask(lambda s, n=n: s.number <= n), "range"))
    out.append(Condition("number % 2 == 1", ("number",), _mask(lambda s: s.number % 2 == 1), "parity"))
    out.append(Condition("number % 2 == 0", ("number",), _mask(lambda s: s.number % 2 == 0), "parity"))
    return tuple(out)


ATOMS: tuple[Condition, ...] = _build_atoms()
EQ_ATOMS: tuple[Condition, ...] = tuple(a for a in ATOMS if a.kind == "eq")


def _build_conjunctions() -> tuple[Condition, ...]:
    out: list[Condition] = []
    for a, b in itertools.combinations(ATOMS, 2):
        if a.attrs[0] == b.attrs[0]:
            continue
        out.append(Condition(f"{a.label} and {b.label}", (a.attrs[0], b.attrs[0]), a.mask & b.mask, "and"))
    return tuple(out)


CONJUNCTIONS: tuple[Condition, ...] = _build_conjunctions()
CONDITIONS_BY_ARITY: dict[int, tuple[Condition, ...]] = {1: ATOMS, 2: CONJUNCTIONS}
CONDITION_BY_LABEL: dict[str, Condition] = {c.label: c for c in ATOMS + CONJUNCTIONS}
#: Conjunction lookup that ignores operand order: ``{a.label, b.label}`` -> condition.
CONJUNCTION_BY_ATOMS: dict[frozenset[str], Condition] = {
    frozenset(c.label.split(" and ")): c for c in CONJUNCTIONS
}


# ---------------------------------------------------------------------------
# Decision lists
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PuzzleRule:
    """A decision list: ordered ``(condition, action)`` clauses plus an else action.

    Semantics are Python's: the first clause whose condition holds decides.
    ``vector`` is the action for every signal in ``SIGNAL_SPACE`` order.
    """

    clauses: tuple[tuple[Condition, str], ...]
    else_action: str
    vector: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.clauses:
            raise ValueError("a decision list needs at least one clause")
        for _, a in self.clauses:
            if a not in ACTIONS:
                raise ValueError(f"unknown action {a!r}")
        if self.else_action not in ACTIONS:
            raise ValueError(f"unknown action {self.else_action!r}")
        vec = []
        for i in range(len(SIGNAL_SPACE)):
            act = self.else_action
            for cond, a in self.clauses:
                if cond.mask >> i & 1:
                    act = a
                    break
            vec.append(act)
        object.__setattr__(self, "vector", tuple(vec))

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(cond.arity for cond, _ in self.clauses)

    def evaluate(self, signal: Signal) -> str:
        return self.vector[SIGNAL_INDEX[signal]]

    def overlap_count(self, signal: Signal) -> int:
        """How many clause conditions hold on *signal* (priority matters when >= 2)."""
        return sum(cond.holds(signal) for cond, _ in self.clauses)

    def region_masks(self) -> list[int]:
        """Signals decided by each clause in turn, then by ``else``; a partition of the grid."""
        covered = 0
        regions: list[int] = []
        for cond, _ in self.clauses:
            regions.append(cond.mask & ~covered)
            covered |= cond.mask
        regions.append(FULL_MASK & ~covered)
        return regions

    @property
    def description(self) -> str:
        parts = []
        for i, (cond, a) in enumerate(self.clauses):
            parts.append(f"{'if' if i == 0 else 'elif'} {cond.label}: {a}")
        parts.append(f"else: {self.else_action}")
        return "; ".join(parts)


def shape_label(shape: tuple[int, ...]) -> str:
    return ",".join(str(a) for a in shape)


def render_shape_hint(shape: tuple[int, ...]) -> str:
    """The blanked one-line skeleton (spec §7.2/§7.3).

    One renderer, because the observation, the response format and the
    parser must agree on a single grammar. The observation used to show an
    indented ``if ___:\n    action = ___`` block while the response format
    and ``parse_rule_text`` accepted only this one-line form, and models
    answered in the shape they had been *shown* -- ``... : action = 'go_left';
    elif ...`` -- which the parser rejected, losing that turn's
    ``rule_match_score``. Filling every blank of this string is now exactly a
    well-formed answer.
    """
    parts = []
    for i, arity in enumerate(shape):
        cond = " and ".join(["___"] * arity)
        parts.append(f"{'if' if i == 0 else 'elif'} {cond}: ___")
    parts.append("else: ___")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Clues, specs, puzzles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Clue:
    """One revealed signal->action pair shown to the agent."""

    signal: Signal
    action: str

    def __str__(self) -> str:
        return f"{self.signal} → {self.action}"


def puzzle_rng(seed: int | None, turn_number: int) -> random.Random:
    """Per-turn RNG derived from ``(seed, turn_number)`` only.

    A ``str`` seed is hashed with SHA-512 by ``random.seed``, so the
    stream is stable across processes and independent of
    ``PYTHONHASHSEED``. Keeping puzzle draws off the season RNG means the
    variable number of generator attempts never shifts any other
    consumer's stream (peer-death scheduler, legacy signal draws).
    """
    return random.Random(f"{seed}:{turn_number}")


# --- Task 2 appends: exists_differing / is_unique -------------------------


# ---------------------------------------------------------------------------
# Functional uniqueness within a disclosed shape (spec §4)
# ---------------------------------------------------------------------------


def _lowest_bits(mask: int) -> Iterable[int]:
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def exists_differing(
    shape: tuple[int, ...],
    clues: Iterable[Clue],
    truth: tuple[str, ...],
) -> bool:
    """Does some decision list of *shape*, consistent with *clues*, compute a
    different 64-vector than *truth*?

    Depth-first search over clause positions (spec §4.2). State: position,
    the grid mask already decided by earlier clauses, the mask of clues no
    earlier clause captured, and whether the list already differs from
    *truth* somewhere. At each position a clause may be dead (decides no new
    signal; skipped) or use any condition of the position's arity that
    decides at least one new signal and whose captured clues all share one
    label; the action is that label (or any action if it captured none).
    Prune when the remaining clues carry more distinct labels than the
    remaining clauses + else can serve. Memoised on (position, covered,
    differs).

    ``clues`` is consumed exactly once, so pass a list or tuple rather
    than a generator.
    """
    clue_label: dict[int, str] = {}
    remaining0 = 0
    for c in clues:
        i = SIGNAL_INDEX[c.signal]
        clue_label[i] = c.action
        remaining0 |= 1 << i
    truth_mask: dict[str, int] = {a: 0 for a in ACTIONS}
    for i, a in enumerate(truth):
        truth_mask[a] |= 1 << i
    k = len(shape)
    memo: dict[tuple[int, int, bool], bool] = {}

    def labels_of(mask: int) -> set[str]:
        return {clue_label[i] for i in _lowest_bits(mask)}

    def rec(pos: int, covered: int, remaining: int, differs: bool) -> bool:
        key = (pos, covered, differs)
        if key in memo:
            return memo[key]
        labs = labels_of(remaining)
        result = False
        if pos == k:
            if len(labs) <= 1:
                candidates = [next(iter(labs))] if labs else list(ACTIONS)
                free = FULL_MASK & ~covered
                for a in candidates:
                    if differs or (free & ~truth_mask[a]):
                        result = True
                        break
        elif len(labs) <= (k - pos) + 1:
            if rec(pos + 1, covered, remaining, differs):
                result = True
            else:
                for cond in CONDITIONS_BY_ARITY[shape[pos]]:
                    new = cond.mask & ~covered
                    if not new:
                        continue
                    fired = labels_of(remaining & cond.mask)
                    if len(fired) > 1:
                        continue
                    candidates = [next(iter(fired))] if fired else list(ACTIONS)
                    for a in candidates:
                        d = differs or bool(new & ~truth_mask[a])
                        if rec(pos + 1, covered | cond.mask, remaining & ~cond.mask, d):
                            result = True
                            break
                    if result:
                        break
        memo[key] = result
        return result

    return rec(0, 0, remaining0, False)


def is_unique(shape: tuple[int, ...], clues: Iterable[Clue], rule: PuzzleRule) -> bool:
    """Spec §4.1: every list of *shape* consistent with *clues* equals *rule* as a function."""
    return not exists_differing(shape, list(clues), rule.vector)


def exists_consistent(shape: tuple[int, ...], clues: Iterable[Clue]) -> bool:
    """Does any decision list of *shape* agree with every clue in *clues*?

    The same depth-first walk as :func:`exists_differing` with the
    ``differs`` bookkeeping removed, so the memo key drops to
    ``(position, covered)`` — ``remaining`` is always
    ``remaining0 & ~covered``. At each position a clause may be dead
    (decides no new signal; skipped) or take any condition of that
    position's arity that decides at least one new signal and whose
    captured clues all carry one action label. Success means the clues
    left for ``else`` carry at most one label.

    ``clues`` is consumed exactly once, so pass a list or tuple rather
    than a generator. Two clues naming different actions for the same
    signal make the set unsatisfiable by definition.
    """
    clue_label: dict[int, str] = {}
    remaining0 = 0
    for c in clues:
        i = SIGNAL_INDEX[c.signal]
        if clue_label.setdefault(i, c.action) != c.action:
            return False
        remaining0 |= 1 << i
    k = len(shape)
    memo: dict[tuple[int, int], bool] = {}

    def labels_of(mask: int) -> set[str]:
        return {clue_label[i] for i in _lowest_bits(mask)}

    def rec(pos: int, covered: int) -> bool:
        key = (pos, covered)
        if key in memo:
            return memo[key]
        remaining = remaining0 & ~covered
        labs = labels_of(remaining)
        result = False
        if pos == k:
            result = len(labs) <= 1
        elif len(labs) <= (k - pos) + 1:
            if rec(pos + 1, covered):
                result = True
            else:
                for cond in CONDITIONS_BY_ARITY[shape[pos]]:
                    new = cond.mask & ~covered
                    if not new:
                        continue
                    if len(labels_of(remaining & cond.mask)) > 1:
                        continue
                    if rec(pos + 1, covered | cond.mask):
                        result = True
                        break
        memo[key] = result
        return result

    return rec(0, 0)


def candidate_actions(
    shape: tuple[int, ...], clues: Iterable[Clue], query: Signal
) -> tuple[str, ...]:
    """Actions the query can still take under some list consistent with *clues*.

    One reachability query per action: pin the query to that action as an
    extra clue and ask whether anything in the hypothesis space survives.
    Length 1 means the clue set determines the answer (the uniqueness the
    v2 generator guarantees); length >= 2 means the turn is
    underdetermined and the agent can only guess. Length 0 means the clue
    set is unsatisfiable under *shape* — no decision list of that shape
    reproduces the clues, so no answer is reachable either. The generator
    never builds such a set (its clues are read off a real rule), so an
    empty tuple in practice means a caller passed clues from a different
    shape. Returned in ``ACTIONS`` order.
    """
    base = list(clues)
    return tuple(
        a for a in ACTIONS if exists_consistent(shape, base + [Clue(query, a)])
    )


def enumerate_shape(shape: tuple[int, ...]) -> Iterable[PuzzleRule]:
    """Every decision list of *shape* (brute force; tests only).

    Conditions may repeat and actions are unconstrained, matching the
    hypothesis space of :func:`exists_differing`.
    """
    pools = [CONDITIONS_BY_ARITY[a] for a in shape]
    for conds in itertools.product(*pools):
        for acts in itertools.product(ACTIONS, repeat=len(shape) + 1):
            yield PuzzleRule(
                clauses=tuple(zip(conds, acts[:-1], strict=True)),
                else_action=acts[-1],
            )


# --- Task 3 appends: PuzzleSpec / Puzzle / sample_rule / minimal_clues / generate_puzzle


# ---------------------------------------------------------------------------
# Specs, puzzles, generator (spec §5)
# ---------------------------------------------------------------------------


class PuzzleGenerationError(RuntimeError):
    """No rule / clue set satisfied the spec within the attempt budget."""


@dataclass(frozen=True)
class PuzzleSpec:
    """One ladder rung (spec §6), plus the underdetermined-turn flag."""

    turn: int
    clauses: int
    conjunctions: int
    predicates: bool
    overlap_query: bool
    extra_clues: int
    #: When True the turn is deliberately unsolvable: one load-bearing clue
    #: is withheld so the query splits ``n_candidate_actions`` ways. The flag
    #: rides on the spec because ``cached_puzzle`` keys its lru_cache on it.
    underdetermined: bool = False
    #: How many actions the query may take. 1 = determined (the default).
    n_candidate_actions: int = 1

    def __post_init__(self) -> None:
        if self.clauses < 1:
            raise ValueError(f"turn {self.turn}: clauses must be >= 1")
        if not 0 <= self.conjunctions <= self.clauses:
            raise ValueError(f"turn {self.turn}: conjunctions must be in [0, clauses]")
        if self.extra_clues < 0:
            raise ValueError(f"turn {self.turn}: extra_clues must be >= 0")
        if self.overlap_query and self.clauses < 2:
            raise ValueError(f"turn {self.turn}: overlap_query needs clauses >= 2")
        if self.underdetermined:
            if not 2 <= self.n_candidate_actions <= len(ACTIONS):
                raise ValueError(
                    f"turn {self.turn}: an underdetermined turn needs "
                    f"n_candidate_actions in [2, {len(ACTIONS)}], got "
                    f"{self.n_candidate_actions}"
                )
        elif self.n_candidate_actions != 1:
            raise ValueError(
                f"turn {self.turn}: n_candidate_actions must be 1 unless "
                "underdetermined is set"
            )


@dataclass(frozen=True)
class Puzzle:
    """A generated puzzle. Its clues pin the rule and the query answer —
    unless ``spec.underdetermined``, where one load-bearing clue is
    withheld and ``candidate_actions`` holds every answer still open."""

    rule: PuzzleRule
    spec: PuzzleSpec
    clues: tuple[Clue, ...]
    query: Signal
    #: Size of the minimal (all load-bearing) clue set. On a determined
    #: puzzle this is exactly ``len(minimal_clue_signals)`` and describes
    #: the clues shown. On an underdetermined one it is the *base* puzzle's
    #: count minus the dropped clue, so it is one less than the count of
    #: load-bearing clues the minimal set would need and does NOT describe
    #: a minimal set for the clues actually shown — the shown set no longer
    #: pins the answer at all. Analyses must condition on
    #: ``spec.underdetermined`` before reading it.
    n_minimal_clues: int
    #: Signals of the load-bearing clues among ``clues`` (the rest are
    #: redundant padding). ``generate_underdetermined_puzzle`` drops one
    #: of these, never a pad.
    minimal_clue_signals: frozenset[Signal] = frozenset()
    #: Actions the query may still take given ``clues``; length 1 on a
    #: determined turn.
    candidate_actions: tuple[str, ...] = ()
    #: The load-bearing clue withheld to create the ambiguity, if any.
    dropped_clue: Clue | None = None
    #: Whether a redundant clue was added back so the visible clue count
    #: matches the determined twin of this rung.
    clue_count_padded: bool = False
    #: How many clues the determined puzzle this one was carved from showed
    #: (a determined puzzle reports its own count). Padding restores exactly
    #: this count, so ``clue_count_padded`` implies
    #: ``len(clues) == base_clue_count`` and its absence implies one fewer.
    base_clue_count: int = 0

    @property
    def n_candidate_actions(self) -> int:
        """How many actions the query may take; 1 on a determined turn."""
        return len(self.candidate_actions) or 1

    @property
    def shape(self) -> tuple[int, ...]:
        return self.rule.shape

    @property
    def correct_action(self) -> str:
        return self.rule.evaluate(self.query)

    @property
    def query_overlap_count(self) -> int:
        return self.rule.overlap_count(self.query)


MAX_ATTEMPTS: int = 200
_RULE_SAMPLE_ATTEMPTS: int = 2000


def draw_shape(rng: random.Random, spec: PuzzleSpec) -> tuple[int, ...]:
    """``spec.clauses`` positions, ``spec.conjunctions`` of them arity 2 at random positions."""
    arities = [1] * spec.clauses
    for i in rng.sample(range(spec.clauses), spec.conjunctions):
        arities[i] = 2
    return tuple(arities)


def _condition_pool(arity: int, predicates: bool) -> tuple[Condition, ...]:
    pool = CONDITIONS_BY_ARITY[arity]
    if predicates:
        return pool
    if arity == 1:
        return EQ_ATOMS
    eq_labels = {a.label for a in EQ_ATOMS}
    return tuple(c for c in pool if set(c.label.split(" and ")) <= eq_labels)


def sample_rule(rng: random.Random, shape: tuple[int, ...], predicates: bool) -> PuzzleRule:
    """A decision list of *shape* meeting the honesty constraints of spec §3.5."""
    for _ in range(_RULE_SAMPLE_ATTEMPTS):
        clauses: list[tuple[Condition, str]] = []
        used: set[str] = set()
        covered = 0
        ok = True
        prev_action: str | None = None
        for arity in shape:
            cond = rng.choice(_condition_pool(arity, predicates))
            if cond.label in used or not (cond.mask & ~covered):
                ok = False
                break
            used.add(cond.label)
            action = rng.choice([a for a in ACTIONS if a != prev_action])
            clauses.append((cond, action))
            covered |= cond.mask
            prev_action = action
        if not ok or covered == FULL_MASK:
            continue
        else_action = rng.choice([a for a in ACTIONS if a != prev_action])
        rule = PuzzleRule(clauses=tuple(clauses), else_action=else_action)
        # Every clause must change the function.
        if any(
            PuzzleRule(
                clauses=tuple(c for j, c in enumerate(rule.clauses) if j != i),
                else_action=rule.else_action,
            ).vector == rule.vector
            for i in range(len(rule.clauses))
            if len(rule.clauses) > 1
        ):
            continue
        return rule
    raise PuzzleGenerationError(f"no honest rule of shape {shape} (predicates={predicates})")


def minimal_clues(
    rng: random.Random, shape: tuple[int, ...], rule: PuzzleRule, query: Signal
) -> list[Clue]:
    """Spec §4.3 steps 1–3: start from every other signal, drop clues while uniqueness holds."""
    keep = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE if s != query]
    rng.shuffle(keep)
    for clue in list(keep):
        trial = [c for c in keep if c is not clue]
        if not exists_differing(shape, trial, rule.vector):
            keep = trial
    return keep


def generate_puzzle(rng: random.Random, spec: PuzzleSpec) -> Puzzle:
    """Sample a puzzle for one ladder rung (spec §5)."""
    shape = draw_shape(rng, spec)
    for _ in range(MAX_ATTEMPTS):
        rule = sample_rule(rng, shape, spec.predicates)
        if spec.overlap_query:
            candidates = [s for s in SIGNAL_SPACE if rule.overlap_count(s) >= 2]
        else:
            candidates = list(SIGNAL_SPACE)
        if not candidates:
            continue
        query = rng.choice(candidates)
        # Spec §4.3 step 2 takes the 63 non-query clues to pin the query answer
        # ("유일성 자명"). They do not always: a list of the same shape can agree
        # with every one of them and still differ at the query (e.g. truth
        # `elif color == "blue" and number % 2 == 1` vs `elif color == "blue" and
        # number == 3`, which only part ways on one odd blue card). Such a
        # (rule, query) pair has no minimal set at all, so resample.
        full_clues = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE if s != query]
        if not is_unique(shape, full_clues, rule):
            continue
        minimal = minimal_clues(rng, shape, rule, query)
        if len({c.action for c in minimal}) < 2:
            continue
        removed = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE
                   if s != query and all(c.signal != s for c in minimal)]
        # Too few droppable clues to pad with: legitimate, but it would break
        # len(clues) == n_minimal_clues + extra_clues, so take another attempt.
        if len(removed) < spec.extra_clues:
            continue
        rng.shuffle(removed)
        clues = minimal + removed[: spec.extra_clues]
        rng.shuffle(clues)
        return Puzzle(
            rule=rule,
            spec=spec,
            clues=tuple(clues),
            query=query,
            n_minimal_clues=len(minimal),
            minimal_clue_signals=frozenset(c.signal for c in minimal),
            candidate_actions=(rule.evaluate(query),),
            base_clue_count=len(clues),
        )
    raise PuzzleGenerationError(
        f"turn {spec.turn}: no puzzle for shape {shape} after {MAX_ATTEMPTS} attempts"
    )


def generate_underdetermined_puzzle(rng: random.Random, spec: PuzzleSpec) -> Puzzle:
    """A puzzle whose query answer is deliberately NOT pinned (spec §4.3).

    Takes a determined puzzle for the same rung, removes exactly one
    load-bearing clue so the query splits ``spec.n_candidate_actions``
    ways, then pads the clue count back with a redundant clue that does
    not re-pin the answer, so the round is indistinguishable from an
    ordinary one. The rule and every shown clue stay truthful — only a
    clue is missing — and the answer is still graded against the rule,
    so the agent can do no better than guess among the candidates.

    Raises:
        PuzzleGenerationError: If no (rule, query, dropped clue) combination
            reached the requested candidate count within the attempt budget.
    """
    if not spec.underdetermined:
        raise ValueError(f"turn {spec.turn}: spec is not marked underdetermined")
    want = spec.n_candidate_actions
    for _ in range(MAX_ATTEMPTS):
        base = generate_puzzle(rng, spec)
        shown = list(base.clues)
        # Only load-bearing clues can create ambiguity; dropping a pad
        # leaves the minimal set intact and the answer pinned.
        droppable = [c for c in shown if c.signal in base.minimal_clue_signals]
        rng.shuffle(droppable)
        for clue in droppable:
            kept = [c for c in shown if c.signal != clue.signal]
            cands = candidate_actions(base.shape, kept, base.query)
            if len(cands) != want:
                continue
            # Restore the clue count: a redundant clue from the unused pool
            # that leaves the ambiguity intact.
            shown_signals = {c.signal for c in kept}
            pool = [
                Clue(s, base.rule.evaluate(s))
                for s in SIGNAL_SPACE
                if s != base.query and s != clue.signal and s not in shown_signals
            ]
            rng.shuffle(pool)
            padded = False
            for extra in pool:
                if len(candidate_actions(base.shape, kept + [extra], base.query)) == want:
                    kept.append(extra)
                    padded = True
                    break
            rng.shuffle(kept)
            return Puzzle(
                rule=base.rule,
                spec=spec,
                clues=tuple(kept),
                query=base.query,
                n_minimal_clues=base.n_minimal_clues - 1,
                minimal_clue_signals=base.minimal_clue_signals - {clue.signal},
                # ``cands`` was computed before the pad clue was appended,
                # but it still describes the clues shown: adding a clue is
                # monotone (candidates can only shrink), and the pad was
                # accepted only when the count stayed at ``want``, so equal
                # size implies the same set. Any future pad rule that does
                # not re-check the count must recompute this instead.
                candidate_actions=cands,
                dropped_clue=clue,
                clue_count_padded=padded,
                base_clue_count=len(shown),
            )
    raise PuzzleGenerationError(
        f"turn {spec.turn}: no clue drop split the query {want} ways "
        f"after {MAX_ATTEMPTS} attempts"
    )


# --- Task 4 appends: parse_rule_text / functional_match_score --------------


# ---------------------------------------------------------------------------
# RULE-line parsing and functional scoring (spec §8)
# ---------------------------------------------------------------------------

_ACTION_RE = "|".join(re.escape(a) for a in ACTIONS)
_ATOM_EQ = re.compile(r"^(color|shape|number)\s*==\s*([a-z]+|[1-4])$")
_ATOM_RANGE = re.compile(r"^number\s*(>=|<=)\s*([1-4])$")
_ATOM_PARITY = re.compile(r"^number\s*%\s*2\s*==\s*([01])$")
_CLAUSE_SPLIT = re.compile(r"(?:^|;|\n)\s*(?=(?:if|elif|else)\b)")
_CLAUSE_RE = re.compile(rf"^(if|elif)\s+(.+?)\s*:\s*(?:action\s*=\s*)?({_ACTION_RE})\b")
_ELSE_RE = re.compile(rf"^else\s*:\s*(?:action\s*=\s*)?({_ACTION_RE})\b")
#: A *different* action token in the text left over after a clause match makes
#: the clause ambiguous (``go_left is wrong, go_right``), so the parse is
#: refused. A repeat of the action just matched (``stay (best guess, stay)``)
#: adds nothing and is tolerated.
_TRAILING_ACTION_RE = re.compile(rf"\b(?:{_ACTION_RE})\b")


def _ambiguous_remainder(rest: str, action: str) -> bool:
    """Does *rest* name an action other than the one already matched?"""
    return any(tok != action for tok in _TRAILING_ACTION_RE.findall(rest))


def _normalise_rule_text(text: str) -> str:
    s = text.strip()
    s = re.sub(r"^\s*rule\s*:\s*", "", s, flags=re.IGNORECASE)
    s = s.lower().replace("colour", "color")
    s = s.replace("'", "").replace('"', "")
    # Parentheses carry no meaning in this grammar, so a wrapped condition
    # (``if (color == red): stay``) and a parenthesised aside (``stay (my best
    # guess)``) both normalise to the bare form.
    s = s.replace("(", " ").replace(")", " ")
    # A single ``=`` on an attribute is an assignment in Python but an equality
    # test in every model that writes it; ``number >= 3`` / ``number <= 3`` are
    # untouched because the lookahead only fires on a bare ``=``.
    s = re.sub(r"\b(color|shape|number)\s*=\s*(?!=)", r"\1 == ", s)
    # v1 / prose spellings -> Python spellings.
    s = re.sub(r"\botherwise\b", "else:", s)
    s = re.sub(r"\belse if\b", "elif", s)
    s = re.sub(r"\bthen\b", ":", s)
    s = re.sub(r"\bnumber\s+is\s+odd\b", "number % 2 == 1", s)
    s = re.sub(r"\bnumber\s+is\s+even\b", "number % 2 == 0", s)
    # Comparators before the generic ``is`` rewrite, so that "number is at least 3"
    # becomes "number is >= 3" and not "number == at least 3".
    s = re.sub(r"\bat least\s+([1-4])", r">= \1", s)
    s = re.sub(r"\bat most\s+([1-4])", r"<= \1", s)
    # ``is`` in front of a comparator is filler ("number is >= 3"), not an equality.
    s = re.sub(r"\b(color|shape|number)\s+is\s+(?=[<>=%])", r"\1 ", s)
    s = re.sub(r"\b(color|shape|number)\s+is\s+", r"\1 == ", s)
    s = re.sub(r"\bnumber\s*(>=|<=)\s*([1-4])", r"number \1 \2", s)
    s = re.sub(r"\belse\s*:\s*:", "else:", s)
    return s


def _parse_atom(text: str) -> Condition | None:
    t = text.strip()
    m = _ATOM_EQ.match(t)
    if m:
        attr, raw = m.group(1), m.group(2)
        if attr == "number":
            label = f"number == {raw}" if raw.isdigit() else None
        else:
            label = f'{attr} == "{raw}"'
        return CONDITION_BY_LABEL.get(label) if label else None
    m = _ATOM_RANGE.match(t)
    if m:
        return CONDITION_BY_LABEL.get(f"number {m.group(1)} {m.group(2)}")
    m = _ATOM_PARITY.match(t)
    if m:
        return CONDITION_BY_LABEL.get(f"number % 2 == {m.group(1)}")
    return None


def _parse_condition(text: str) -> Condition | None:
    parts = [p.strip() for p in re.split(r"\band\b", text)]
    if len(parts) == 1:
        return _parse_atom(parts[0])
    if len(parts) != 2:
        return None
    atoms = [_parse_atom(p) for p in parts]
    if any(a is None for a in atoms):
        return None
    return CONJUNCTION_BY_ATOMS.get(frozenset(a.label for a in atoms))


def parse_rule_text(text: str) -> PuzzleRule | None:
    """Parse an agent's RULE text (one line or a Python block) into a decision list.

    Accepts ``if / elif / else`` with ``:`` separators, ``action = x``
    or bare ``x`` after the colon, ``;`` or newlines between clauses,
    quotes optional, case-insensitive, and the v1 prose spellings
    (``color is red then stay; otherwise jump``). Returns ``None`` when
    there is no ``if`` clause, no ``else``, a value or action off the
    grid, or a conjunction on one attribute. Harmless trailing prose
    after an action is tolerated (``stay  (my best guess)``), but a
    remainder naming a *different* action is ambiguous
    (``go_left is wrong, go_right``) and is refused too; a remainder that
    merely repeats the matched action (``stay (best guess, stay)``) is not. The shape is
    NOT checked against the round's shape; callers compare ``.shape``
    themselves.
    """
    s = _normalise_rule_text(text)
    if not s:
        return None
    chunks = [c.strip() for c in _CLAUSE_SPLIT.split(s) if c and c.strip()]
    clauses: list[tuple[Condition, str]] = []
    else_action: str | None = None
    for chunk in chunks:
        m = _ELSE_RE.match(chunk)
        if m:
            if _ambiguous_remainder(chunk[m.end():], m.group(1)):
                return None
            else_action = m.group(1)
            break
        m = _CLAUSE_RE.match(chunk)
        if not m:
            return None
        if _ambiguous_remainder(chunk[m.end():], m.group(3)):
            return None
        if (m.group(1) == "if") != (not clauses):
            return None
        cond = _parse_condition(m.group(2))
        if cond is None:
            return None
        clauses.append((cond, m.group(3)))
    if not clauses or else_action is None:
        return None
    return PuzzleRule(clauses=tuple(clauses), else_action=else_action)


def functional_match_score(hypothesis: PuzzleRule, truth: PuzzleRule) -> float:
    """Percentage of the 64 signals on which the two rules agree."""
    agree = sum(a == b for a, b in zip(hypothesis.vector, truth.vector, strict=True))
    return 100.0 * agree / len(SIGNAL_SPACE)


# --- Task 7 appends: cached_puzzle (controller ruling R7-1) ----------------


@functools.lru_cache(maxsize=4096)
def cached_puzzle(seed: int | str | None, turn_number: int, spec: PuzzleSpec) -> Puzzle:
    """``generate_puzzle`` / ``generate_underdetermined_puzzle`` memoised per process.

    Every cell of a run shares the season seed, so the same puzzle is otherwise
    regenerated once per cell; generation is 1-15 s on the top ladder rungs.
    ``PuzzleSpec`` is a frozen dataclass, hence hashable, and it carries
    ``underdetermined`` — so the determined and underdetermined versions of one
    ``(seed, turn)`` occupy separate cache entries. The cache is process-local:
    ``parallel_workers`` threads share it, separate processes do not.
    """
    rng = puzzle_rng(seed, turn_number)
    if spec.underdetermined:
        return generate_underdetermined_puzzle(rng, spec)
    return generate_puzzle(rng, spec)
