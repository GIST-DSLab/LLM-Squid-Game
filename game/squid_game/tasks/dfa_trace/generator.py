"""Deterministic-automaton tracing instances for the ``dfa_trace`` task.

Brief: ``docs/history/plans/2026-09-17-team-wallet-task-candidates.md`` §2 C
and §3.2.

What this generator is for
--------------------------
The team-wallet charge design needs a task whose winning procedure is
*long* and whose shortcuts *reliably lose*, and it needs that proved
offline, before any model is called. A DFA trace gives the cleanest
version of that statement available: the deep procedure is "take all L
steps", and the shallow family ``prefix_k`` is literally "take the first
k steps and stop". The accuracy of ``prefix_k`` as a function of k is
therefore an effort-accuracy curve computed with no model in the loop
(gate D5 of ``scripts/dev/validate_dfa_trace.py``).

There is no uniqueness problem here — a DFA is a function, so the answer
is whatever the simulator says. What the generator must supply instead is
a *trap*: an instance on which every shallow solver is wrong. That is
rejection sampling on top of :func:`generate_dfa`, and like
``signal_game``'s :func:`generate_trap_puzzle` it raises rather than
silently handing back an easy instance
(:class:`DfaGenerationError`) — a silent substitution would put an easy
round where the schedule says hard and nothing downstream would record it.

The four shallow families (§2 C)
--------------------------------
``freq_map``
    Counts symbols and forgets order: simulate the *sorted* word. Killed
    by construction — :func:`generate_dfa` requires the transition
    monoid to be non-commutative, so order provably matters.
``prefix_k``
    Walk the first k symbols, then freeze on that state for the rest.
    Generated for k in the doubling series 2, 4, 8, ... below L, plus
    ``L // 2`` (the rung the brief names explicitly).
``last_symbol``
    Apply only the final symbol, from the start state.
``ignore_selfloop``
    Reads a run of the same symbol as "that symbol keeps you where you
    are" and collapses each run to one occurrence, then simulates. Note
    this is NOT "drop the actual self-loops": dropping a genuine
    self-loop changes nothing, so that solver would be exact and
    worthless. What it models is the shortcut of assuming a repeat is a
    repeat-in-place.

Every solver is expressed as a state *trajectory* padded to ``L + 1``
states, so the same answer extractor serves both question kinds and a
``count`` answer stays on the same scale as the truth.
"""

from __future__ import annotations

import functools
import hashlib
import random
from dataclasses import dataclass, replace

#: Bumped whenever a change would make the same ``(seed, spec)`` produce a
#: different instance. Recorded per round as ``generator_version``.
GENERATOR_VERSION: int = 1

#: Rejection-sampling budget for :func:`generate_trap_dfa` and for the
#: structural constraints of :func:`generate_dfa`.
MAX_ATTEMPTS: int = 200

#: The alphabet is the first ``spec.alphabet`` of these.
SYMBOLS: str = "abcd"

#: The two question kinds a rung may ask.
QUESTION_KINDS: tuple[str, ...] = ("final", "count")

#: Shallow families that are not part of the ``prefix_k`` series.
NAMED_SOLVERS: tuple[str, ...] = ("freq_map", "last_symbol", "ignore_selfloop")


class DfaGenerationError(RuntimeError):
    """No instance satisfied the spec within the attempt budget."""


def state_name(index: int) -> str:
    """``0 -> "q0"``. The only place the state vocabulary is spelled."""
    return f"q{index}"


@dataclass(frozen=True)
class DfaSpec:
    """One ladder rung: the shape of the instance, not the instance.

    Frozen (hence hashable) because :func:`cached_dfa` keys its LRU on it,
    exactly as ``PuzzleSpec`` does for the signal game.

    Attributes:
        states: How many states the machine has (``q0 .. q{states-1}``).
        alphabet: How many symbols, taken from :data:`SYMBOLS`.
        length: ``L``, the number of symbols in the input string.
        question: ``"final"`` (which state at the end) or ``"count"``
            (how many times a named state was occupied).
        trap: Require an instance every shallow solver gets wrong.
        turn: The round this rung is played on. Part of the id and of
            the per-round RNG, never of the machine's shape.
        profile: The ladder rung's name, recorded as
            ``difficulty_profile``.
    """

    states: int
    alphabet: int
    length: int
    question: str = "final"
    trap: bool = True
    turn: int = 0
    profile: str = ""
    generator_version: int = GENERATOR_VERSION

    def __post_init__(self) -> None:
        if self.states < 2:
            raise ValueError(f"round {self.turn}: states must be >= 2")
        if not 2 <= self.alphabet <= len(SYMBOLS):
            raise ValueError(
                f"round {self.turn}: alphabet must be in [2, {len(SYMBOLS)}]"
            )
        if self.length < 2:
            raise ValueError(f"round {self.turn}: length must be >= 2")
        if self.question not in QUESTION_KINDS:
            raise ValueError(
                f"round {self.turn}: question must be one of {QUESTION_KINDS}, "
                f"got {self.question!r}"
            )

    @property
    def symbols(self) -> str:
        """The alphabet as a string, e.g. ``"abc"``."""
        return SYMBOLS[: self.alphabet]


@dataclass(frozen=True)
class Dfa:
    """One generated instance: machine, input, and the thing asked about.

    Attributes:
        spec: The rung this came from.
        transitions: ``transitions[state][symbol_index] -> state``.
        start: Index of the start state.
        word: The input string, ``spec.length`` symbols long.
        count_state: The state the ``count`` question asks about. Always
            set (it costs nothing to draw) but only read when
            ``spec.question == "count"``.
        trap_attempts: How many draws :func:`generate_trap_dfa` needed;
            ``0`` when the trap filter did not run.
    """

    spec: DfaSpec
    transitions: tuple[tuple[int, ...], ...]
    start: int
    word: str
    count_state: int
    trap_attempts: int = 0

    @property
    def symbols(self) -> str:
        return self.spec.symbols

    @property
    def answer(self) -> str:
        """The correct answer as the agent must write it (no label)."""
        return _answer_from_trajectory(self, trajectory(self, self.word))


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def trajectory(dfa: Dfa, word: str) -> tuple[int, ...]:
    """States occupied while reading *word*: start, then one per symbol.

    Length is ``len(word) + 1``. This is the object every solver — deep or
    shallow — produces, so they can all be scored the same way.
    """
    symbols = dfa.symbols
    state = dfa.start
    out = [state]
    for char in word:
        state = dfa.transitions[state][symbols.index(char)]
        out.append(state)
    return tuple(out)


def simulate(dfa: Dfa, word: str) -> tuple[str, dict[str, int]]:
    """Run *word* and report the final state and every state's visit count.

    Returns:
        ``(final_state_name, {state_name: visits})``. Visits include the
        start state, so they sum to ``len(word) + 1``.
    """
    traj = trajectory(dfa, word)
    visits = {state_name(i): 0 for i in range(dfa.spec.states)}
    for state in traj:
        visits[state_name(state)] += 1
    return state_name(traj[-1]), visits


def _pad(traj: tuple[int, ...], size: int) -> tuple[int, ...]:
    """Freeze *traj* on its last state until it is *size* long.

    A shallow solver that stops early has to say something about the rest
    of the input; "nothing more happens" is the honest reading of every
    shortcut here, and it keeps a ``count`` answer on the truth's scale.
    """
    if len(traj) >= size:
        return traj[:size]
    return traj + (traj[-1],) * (size - len(traj))


def _answer_from_trajectory(dfa: Dfa, traj: tuple[int, ...]) -> str:
    traj = _pad(traj, dfa.spec.length + 1)
    if dfa.spec.question == "final":
        return state_name(traj[-1])
    return str(sum(1 for s in traj if s == dfa.count_state))


# ---------------------------------------------------------------------------
# Shallow solvers
# ---------------------------------------------------------------------------


def prefix_ks(length: int) -> tuple[int, ...]:
    """The ``k`` values of the recorded ``prefix_k`` family for input *length*.

    The doubling series 2, 4, 8, ... strictly below ``length``, plus
    ``length // 2`` (§2 C names that rung explicitly). ``k == length`` is
    deliberately absent: that solver IS the deep procedure and is always
    right, so including it would make a trap instance impossible. The
    validator adds it back when it draws the D5 curve.
    """
    ks = set()
    k = 2
    while k < length:
        ks.add(k)
        k *= 2
    half = length // 2
    if 2 <= half < length:
        ks.add(half)
    return tuple(sorted(ks))


def shallow_freq_map(dfa: Dfa) -> str:
    """Symbol counts only: simulate the word with its symbols sorted."""
    return _answer_from_trajectory(dfa, trajectory(dfa, "".join(sorted(dfa.word))))


def shallow_prefix_k(dfa: Dfa, k: int) -> str:
    """Walk the first *k* symbols, then assume nothing else changes."""
    return _answer_from_trajectory(dfa, trajectory(dfa, dfa.word[:k]))


def shallow_last_symbol(dfa: Dfa) -> str:
    """Apply only the final symbol, from the start state."""
    return _answer_from_trajectory(dfa, trajectory(dfa, dfa.word[-1:]))


def shallow_ignore_selfloop(dfa: Dfa) -> str:
    """Collapse each run of one repeated symbol to a single occurrence."""
    collapsed = [dfa.word[0]]
    for char in dfa.word[1:]:
        if char != collapsed[-1]:
            collapsed.append(char)
    return _answer_from_trajectory(dfa, trajectory(dfa, "".join(collapsed)))


def shallow_solver_names(spec: DfaSpec) -> tuple[str, ...]:
    """Every solver recorded for a rung, in a stable order."""
    return NAMED_SOLVERS + tuple(f"prefix_{k}" for k in prefix_ks(spec.length))


def shallow_answers(dfa: Dfa) -> dict[str, str]:
    """What each shallow solver answers. Recorded, never shown to the agent."""
    out: dict[str, str] = {
        "freq_map": shallow_freq_map(dfa),
        "last_symbol": shallow_last_symbol(dfa),
        "ignore_selfloop": shallow_ignore_selfloop(dfa),
    }
    for k in prefix_ks(dfa.spec.length):
        out[f"prefix_{k}"] = shallow_prefix_k(dfa, k)
    return out


def is_trap(dfa: Dfa) -> bool:
    """True when every recorded shallow solver gets this instance wrong.

    Strictly stronger than the brief's "the four plus ``prefix_{L//2}``":
    the whole ``prefix_k`` series has to miss, so a trap round always
    records ``shallow_solvers_correct == []`` — the same reading the
    signal game's ``is_trap_query`` gives.
    """
    truth = dfa.answer
    return all(answer != truth for answer in shallow_answers(dfa).values())


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _is_non_commutative(transitions: tuple[tuple[int, ...], ...], alphabet: int) -> bool:
    """Does the order of two symbols ever matter?

    ``freq_map`` answers from symbol counts alone, so it is correct on any
    machine whose symbol maps commute. Requiring a witness pair makes the
    shortcut provably wrong on SOME input; the trap filter then makes it
    wrong on THIS input.
    """
    for a in range(alphabet):
        for b in range(a + 1, alphabet):
            for q in range(len(transitions)):
                if transitions[transitions[q][a]][b] != transitions[transitions[q][b]][a]:
                    return True
    return False


def _reachable(transitions: tuple[tuple[int, ...], ...], start: int) -> set[int]:
    seen = {start}
    frontier = [start]
    while frontier:
        q = frontier.pop()
        for target in transitions[q]:
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return seen


def _structurally_ok(
    transitions: tuple[tuple[int, ...], ...], spec: DfaSpec, start: int
) -> bool:
    if len(_reachable(transitions, start)) != spec.states:
        return False
    # A symbol whose map is the identity does nothing and would make the
    # input string partly decorative.
    for a in range(spec.alphabet):
        if all(transitions[q][a] == q for q in range(spec.states)):
            return False
    return _is_non_commutative(transitions, spec.alphabet)


def generate_dfa(rng: random.Random, spec: DfaSpec) -> Dfa:
    """Draw one instance satisfying the spec's structural constraints.

    Constraints: every state reachable from the start, no symbol whose map
    is the identity, and a non-commutative transition monoid. The trap
    filter is NOT applied here — see :func:`generate_trap_dfa`.

    Raises:
        DfaGenerationError: If no draw was structurally acceptable within
            :data:`MAX_ATTEMPTS`.
    """
    for _ in range(MAX_ATTEMPTS):
        transitions = tuple(
            tuple(rng.randrange(spec.states) for _ in range(spec.alphabet))
            for _ in range(spec.states)
        )
        start = 0
        if not _structurally_ok(transitions, spec, start):
            continue
        word = "".join(rng.choice(spec.symbols) for _ in range(spec.length))
        dfa = Dfa(
            spec=spec,
            transitions=transitions,
            start=start,
            word=word,
            count_state=0,
        )
        # A ``count`` question about a state the run never enters answers
        # 0, which is guessable without reading anything.
        visited = sorted(set(trajectory(dfa, word)))
        return replace(dfa, count_state=rng.choice(visited))
    raise DfaGenerationError(
        f"round {spec.turn}: no structurally valid machine with "
        f"{spec.states} states / {spec.alphabet} symbols after "
        f"{MAX_ATTEMPTS} attempts"
    )


def generate_trap_dfa(
    rng: random.Random, spec: DfaSpec, attempts: int = MAX_ATTEMPTS
) -> Dfa:
    """An instance every shallow solver gets wrong (§2 C).

    Rejection sampling on top of :func:`generate_dfa`, which keeps the
    structural constraints untouched; this wrapper only *chooses among*
    the machines it makes.

    Raises:
        DfaGenerationError: If no draw was a trap within *attempts*. There
            is no fallback to an ordinary instance — that would put an
            easy round where the schedule says hard, with nothing in the
            record to say so.
    """
    if not spec.trap:
        raise ValueError(f"round {spec.turn}: spec is not marked trap")
    for n in range(1, attempts + 1):
        dfa = generate_dfa(rng, spec)
        if is_trap(dfa):
            return replace(dfa, trap_attempts=n)
    raise DfaGenerationError(
        f"round {spec.turn}: no trap instance for {spec.states} states / "
        f"{spec.alphabet} symbols / length {spec.length} after {attempts} attempts"
    )


def dfa_id_for(seed: int | str | None, spec: DfaSpec) -> str:
    """A stable 12-hex id for the instance ``(seed, spec)`` produces.

    Covers every input that changes the instance, so two runs showing the
    same id showed the same item — which is what item-paired analyses key
    on. Recorded twice per round, as ``dfa_id`` and as ``puzzle_id``, so
    the scripts written for the signal game work unchanged.
    """
    payload = "|".join(
        str(x)
        for x in (
            spec.generator_version,
            seed,
            spec.turn,
            spec.profile,
            spec.states,
            spec.alphabet,
            spec.length,
            spec.question,
            int(spec.trap),
        )
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def dfa_rng(seed: int | str | None, turn_number: int) -> random.Random:
    """Per-round RNG derived from ``(seed, round)`` only.

    Keeping instance draws off the season RNG means the variable number of
    rejection attempts never shifts any other consumer's stream (the
    peer-death scheduler above all).
    """
    return random.Random(f"{seed}:{turn_number}")


@functools.lru_cache(maxsize=4096)
def cached_dfa(seed: int | str | None, turn_number: int, spec: DfaSpec) -> Dfa:
    """:func:`generate_dfa` / :func:`generate_trap_dfa`, memoised per process.

    Every cell of a run shares the season seed, so without this the same
    instance is regenerated once per cell. Process-local: ``parallel_workers``
    threads share it, separate processes do not.
    """
    rng = dfa_rng(seed, turn_number)
    if spec.trap:
        return generate_trap_dfa(rng, spec)
    return generate_dfa(rng, spec)


# ---------------------------------------------------------------------------
# Rendering helpers (shared by the module and the validator)
# ---------------------------------------------------------------------------


def transition_rows(dfa: Dfa) -> list[str]:
    """The full transition table, one row per state: ``q0: a→q1, b→q3``."""
    rows = []
    for q in range(dfa.spec.states):
        cells = ", ".join(
            f"{sym}→{state_name(dfa.transitions[q][i])}"
            for i, sym in enumerate(dfa.symbols)
        )
        rows.append(f"{state_name(q)}: {cells}")
    return rows


def grouped_word(word: str, size: int = 4) -> str:
    """The input string in groups of *size* characters, space separated."""
    return " ".join(word[i : i + size] for i in range(0, len(word), size))
