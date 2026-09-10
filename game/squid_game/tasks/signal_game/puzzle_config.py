"""Task-YAML loading for the Signal Game per-turn puzzle mode (v2).

Four blocks of ``configs/tasks/signal_game.yaml`` are read at runtime, so
re-tuning is a YAML edit rather than a code change:

``puzzle_ladder``
    The difficulty ladder — one entry per turn with the rule shape
    (``clauses`` / ``conjunctions``), the condition grammar the generator
    may use (``predicates``), whether the query must sit where two or
    more clauses hold (``overlap_query``) and how many redundant clues to
    add on top of the minimal set (``extra_clues``).

``underdetermined``
    Where the deliberately unsolvable turns go (:class:`UnderdeterminedConfig`)
    — the turn blocks and how many ways the query answer may split. It says
    only *where* and *how ambiguous*; whether the feature runs at all is the
    per-experiment ``task_config.underdetermined`` flag. Which turn inside
    each block is picked is :func:`underdetermined_turns` of the season seed
    (read its warning about the three-valued schedule before analysing).

``forced_wrong``
    Where the forced-incorrect rounds go (:class:`ForcedWrongConfig`). The
    puzzle is ordinary and fully solvable; only the *verdict* is
    overridden, so this block is a sibling of ``underdetermined`` rather
    than a mode of it (the two are mutually exclusive at load). Whether it
    runs is the per-experiment ``task_config.forced_wrong`` flag; which
    round inside each block is :func:`forced_wrong_turns` of the seed.

``puzzle_profiles``
    Named generation recipes for the effort-sensitive difficulty mode
    (:class:`PuzzleProfile`, spec 2026-09-10). A profile is a *bundle of
    generation rules*, not a model success rate; an experiment YAML places
    them per round in ``task_config.puzzle_challenge.schedule``, and when
    that block is enabled the ``puzzle_ladder`` above is never consulted.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from squid_game.tasks.benchmark.config import default_config_dir
from squid_game.tasks.signal_game.puzzle import PuzzleSpec
from squid_game.tasks.signal_game.rules import ACTIONS


class PuzzleLadderStep(BaseModel):
    """One rung = one turn (spec §6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn: int = Field(ge=1)
    clauses: int = Field(ge=1)
    conjunctions: int = Field(ge=0)
    predicates: bool
    overlap_query: bool
    extra_clues: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "PuzzleLadderStep":
        if self.conjunctions > self.clauses:
            raise ValueError(f"turn {self.turn}: conjunctions ({self.conjunctions}) > clauses ({self.clauses})")
        if self.overlap_query and self.clauses < 2:
            raise ValueError(f"turn {self.turn}: overlap_query needs clauses >= 2")
        return self

    def to_spec(self) -> PuzzleSpec:
        return PuzzleSpec(
            turn=self.turn,
            clauses=self.clauses,
            conjunctions=self.conjunctions,
            predicates=self.predicates,
            overlap_query=self.overlap_query,
            extra_clues=self.extra_clues,
        )


class PuzzleProfile(BaseModel):
    """One named generation recipe for the effort-sensitive difficulty mode.

    A profile is the *name of a bundle of generation rules*, not a model
    success rate (spec 2026-09-10 §4.2). Its five shape columns are exactly
    ``PuzzleLadderStep``'s; ``trap_query`` is the sixth and restricts the
    query to a cell where every shallow solver is wrong.

    Adding a fourth profile is a line in ``configs/tasks/signal_game.yaml``
    and needs no code change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    clauses: int = Field(ge=1)
    conjunctions: int = Field(ge=0)
    predicates: bool
    overlap_query: bool
    extra_clues: int = Field(ge=0)
    trap_query: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> "PuzzleProfile":
        if self.conjunctions > self.clauses:
            raise ValueError(
                f"conjunctions ({self.conjunctions}) > clauses ({self.clauses})"
            )
        if self.overlap_query and self.clauses < 2:
            raise ValueError("overlap_query needs clauses >= 2")
        if self.trap_query and self.clauses < 3:
            # ``PuzzleSpec`` refuses this too, but only when a season is
            # already running. Fail at config load instead.
            raise ValueError(
                "trap_query needs clauses >= 3: with one or two clauses there "
                "is no clause priority to get wrong, so no trap query exists"
            )
        return self

    def to_spec(self, turn: int, name: str) -> PuzzleSpec:
        return PuzzleSpec(
            turn=turn,
            clauses=self.clauses,
            conjunctions=self.conjunctions,
            predicates=self.predicates,
            overlap_query=self.overlap_query,
            extra_clues=self.extra_clues,
            trap_query=self.trap_query,
            profile=name,
        )


class UnderdeterminedConfig(BaseModel):
    """The ``underdetermined`` block: where the unsolvable turns go.

    One turn inside each listed block is made unsolvable (spec §3). The
    block itself is a closed turn interval, ``[start, end]``, and must be
    at least two turns wide so the position can rotate across
    repetitions. Turning the feature on is a per-experiment decision
    (``TaskConfig.underdetermined``); this block only says *where* and
    *how ambiguous*.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: tuple[tuple[int, int], ...] = Field(min_length=1)
    candidate_actions: int = Field(default=2, ge=2, le=len(ACTIONS))

    @model_validator(mode="after")
    def _blocks_well_formed(self) -> "UnderdeterminedConfig":
        prev_end = 0
        for start, end in self.blocks:
            if end < start:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) is reversed; a block "
                    "is a closed turn interval [start, end] and needs start <= end"
                )
            if end == start:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) must span at least "
                    "two turns; a one-turn block puts the unsolvable turn in the "
                    "same position every repetition"
                )
            if start <= prev_end:
                raise ValueError(
                    f"underdetermined blocks must be ascending and disjoint, "
                    f"got ({start}, {end}) after turn {prev_end}"
                )
            prev_end = end
        return self


def underdetermined_turns(seed: int, cfg: UnderdeterminedConfig) -> tuple[int, ...]:
    """The turn made unsolvable inside each block, for one season seed.

    ``runner.py`` hands repetition *r* the seed ``base_seed + r`` and gives
    every cell of that repetition the same value, so deriving the position
    from the seed both keeps this module stateless and makes the cells of
    one repetition play identical underdetermined turns (the paired design
    needs that). The ``+ b`` term offsets each block from the one before,
    so consecutive blocks never sit at the same position within their
    blocks. Over *w* consecutive seeds a *w*-turn block visits each of its
    positions exactly once — the Latin square of spec §3.2.

    ⚠️ With the shipped ``blocks: [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]``
    (2026-09-07; it was ``[[1, 3], [4, 6]]`` before) every block is two
    turns wide, so there are exactly **two** schedules, keyed on
    ``seed % 2``::

        seed % 2 == 0 -> (1, 4, 5, 8, 9)
        seed % 2 == 1 -> (2, 3, 6, 7, 10)

    Consequences an analyst must carry:

    * Half of every turn pair is a guess turn: **5 of the 10 turns** are
      unsolvable, up from 2. Any accuracy or mastery metric that does not
      condition on ``underdetermined`` is now half noise, not a fifth.
    * Both schedules contain **adjacent** guess turns (4-5 and 8-9 on even
      seeds; 2-3 and 6-7 on odd seeds), which is unavoidable when the block
      width equals 2 and consecutive blocks alternate offsets. The spec's
      post-guess analyses (FORFEIT rate on the turn *after* a guess turn)
      therefore have no clean post-turn for those pairs — condition on
      whether the next turn is itself underdetermined, or use only the
      isolated ones (1, 8-as-follower excluded, etc.).
    * With only two schedules the position is confounded with ``seed % 2``
      rather than ``seed % 3``; a paired design over an even number of
      repetitions balances it, an odd number does not.

    The ``+ b`` offset is spec-fixed and pinned by tests; do not change it
    to spread the schedule out.
    """
    return tuple(
        start + (seed + b) % (end - start + 1)
        for b, (start, end) in enumerate(cfg.blocks)
    )


class ForcedWrongConfig(BaseModel):
    """The ``forced_wrong`` block: where the forced-incorrect rounds go.

    One round inside each listed block is graded incorrect whatever the
    agent answered (spec §4.3). The puzzle itself is ordinary and fully
    solvable — this block changes the VERDICT, never the stimulus, which
    is what separates it from :class:`UnderdeterminedConfig`.

    Blocks are closed turn intervals ``[start, end]`` and must be at
    least two turns wide, so the forced position rotates across
    repetitions instead of pinning to one round number. Turning the
    feature on is the per-experiment ``task_config.forced_wrong`` flag;
    this block only says *where*.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: tuple[tuple[int, int], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _blocks_well_formed(self) -> "ForcedWrongConfig":
        prev_end = 0
        for start, end in self.blocks:
            if end < start:
                raise ValueError(
                    f"forced_wrong block ({start}, {end}) is reversed; a block "
                    "is a closed turn interval [start, end] and needs start <= end"
                )
            if end == start:
                raise ValueError(
                    f"forced_wrong block ({start}, {end}) must span at least "
                    "two turns; a one-turn block puts the forced round in the "
                    "same position every repetition"
                )
            if start <= prev_end:
                raise ValueError(
                    f"forced_wrong blocks must be ascending and disjoint, "
                    f"got ({start}, {end}) after turn {prev_end}"
                )
            prev_end = end
        return self


def forced_wrong_turns(seed: int, cfg: ForcedWrongConfig) -> tuple[int, ...]:
    """The round graded incorrect inside each block, for one season seed.

    Same rotation as :func:`underdetermined_turns`, and for the same
    reasons: derived from the seed so the module stays stateless, and
    shared by every cell of one repetition so the paired design holds.

    With the shipped ``blocks: [[2, 3], [4, 5]]`` — the *N* = 6 instance
    of the recipe in spec §4.10, two two-round blocks packed against
    round ``N - 1`` — every block is two rounds wide, so there are
    exactly **two** schedules, keyed on ``seed % 2``::

        seed % 2 == 0 -> (2, 5)
        seed % 2 == 1 -> (3, 4)

    A run of a different length states its own blocks in
    ``task_config.forced_wrong_blocks``; the same recipe gives
    ``N = 8 -> [[4, 5], [6, 7]]`` and ``N = 10 -> [[6, 7], [8, 9]]``, and
    at every *N* the two forced rounds carry the same ransom ceilings
    (40 then 10 on even seeds, 30 then 20 on odd), so the dominated share
    does not move with the season length.

    An analyst must carry the same consequences the underdetermined
    schedule has: the position is confounded with ``seed % 2``, so a
    paired design over an even number of repetitions balances it and an
    odd number does not.
    """
    return tuple(
        start + (seed + b) % (end - start + 1)
        for b, (start, end) in enumerate(cfg.blocks)
    )


class SignalPuzzleConfig(BaseModel):
    """The ``puzzle_ladder`` block: turn number -> spec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    puzzle_ladder: list[PuzzleLadderStep] = Field(min_length=1)
    underdetermined: UnderdeterminedConfig | None = None
    forced_wrong: ForcedWrongConfig | None = None
    #: The ``puzzle_profiles`` block: named generation recipes an experiment
    #: YAML places per round through ``task_config.puzzle_challenge``. When
    #: that block is enabled the ``puzzle_ladder`` above is not consulted.
    puzzle_profiles: dict[str, PuzzleProfile] | None = None

    @model_validator(mode="after")
    def _turns_consecutive(self) -> "SignalPuzzleConfig":
        turns = [s.turn for s in self.puzzle_ladder]
        if turns != list(range(1, len(turns) + 1)):
            raise ValueError(f"puzzle_ladder turns must be consecutive from 1, got {turns}")
        return self

    @model_validator(mode="after")
    def _underdetermined_within_ladder(self) -> "SignalPuzzleConfig":
        if self.underdetermined is None:
            return self
        last = len(self.puzzle_ladder)
        for start, end in self.underdetermined.blocks:
            if start < 1 or end > last:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) falls outside the "
                    f"{last}-rung puzzle_ladder"
                )
        return self

    @model_validator(mode="after")
    def _forced_wrong_within_ladder(self) -> "SignalPuzzleConfig":
        if self.forced_wrong is None:
            return self
        last = len(self.puzzle_ladder)
        for start, end in self.forced_wrong.blocks:
            if start < 1 or end > last:
                raise ValueError(
                    f"forced_wrong block ({start}, {end}) falls outside the "
                    f"{last}-rung puzzle_ladder"
                )
        return self

    @property
    def total_turns(self) -> int:
        return len(self.puzzle_ladder)

    def spec_for_turn(self, turn_number: int) -> PuzzleSpec:
        """Spec for a 1-based turn; turns past the end clamp to the last rung."""
        idx = min(max(turn_number, 1), self.total_turns) - 1
        return self.puzzle_ladder[idx].to_spec()

    def compressed_rung(self, turn_number: int, total_turns: int) -> int:
        """The reference rung round *turn_number* of an *N*-round season plays.

        ``rung(i) = 1 + ceil((i - 1) * (L - 1) / (N - 1))`` where ``L`` is
        the reference ladder's length. Four properties earn this formula
        its place, and all four are pinned by tests (spec §4.9.1):

        * ``N == L`` is the identity, so every recorded 10-turn config keeps
          playing exactly the ladder it played before this method existed.
        * ``rung(1) == 1`` always. This is why the formula is two-ended
          rather than the simpler ``ceil(i * L / N)``, which starts at rung
          2 for a six-round season: with one life a genuine error on the
          clean opening round opens a below-ceiling ransom, and a DECLINE
          there ends the session before its dominated round ever arrives.
          Round 1 has to stay the easiest thing the ladder has.
        * ``rung(N) == L`` always, so the last round is the hardest rung
          whatever the season length -- the reason the method exists.
        * ``(L - 1) / (N - 1) >= 1`` for ``N <= L``, so the map is strictly
          increasing: no rung repeats and the reference ladder's own
          difficulty ordering is preserved.

        Args:
            turn_number: 1-based round.
            total_turns: The season's length, ``N``.

        Raises:
            ValueError: If *total_turns* exceeds the ladder -- compression
                can map ``N > L`` too, but only by repeating rungs, i.e.
                two rounds at identical difficulty, silently; extending the
                reference ladder is the honest way to run a longer season.
                Also if *total_turns* is below 2, where the formula divides
                by zero and its two anchors contradict each other.
        """
        last = self.total_turns
        if total_turns > last:
            raise ValueError(
                f"a {total_turns}-turn season is longer than the {last}-rung "
                "puzzle_ladder; compression would have to repeat rungs. Extend "
                "the ladder in configs/tasks/signal_game.yaml instead."
            )
        if total_turns < 2:
            raise ValueError(
                "ladder compression needs a season of at least 2 rounds; "
                f"got total_turns={total_turns}. rung(1) = 1 and rung(N) = L "
                "cannot both hold for a one-round season."
            )
        idx = min(max(turn_number, 1), total_turns)
        return 1 + math.ceil((idx - 1) * (last - 1) / (total_turns - 1))

    def compressed_spec_for_turn(self, turn_number: int, total_turns: int) -> PuzzleSpec:
        """``spec_for_turn`` through :meth:`compressed_rung`.

        The returned spec carries ``turn = turn_number`` -- the round being
        played, not the reference rung it was drawn from. ``PuzzleSpec`` is
        part of ``cached_puzzle``'s lru key, so this is also what keeps two
        season lengths from colliding in the cache.
        """
        rung = self.compressed_rung(turn_number, total_turns)
        return dataclasses.replace(
            self.puzzle_ladder[rung - 1].to_spec(), turn=turn_number
        )


def load_signal_puzzle_config(config_dir: Path | None = None) -> SignalPuzzleConfig:
    """Load the ``puzzle_ladder`` block from ``signal_game.yaml``.

    Raises:
        FileNotFoundError: If no ``signal_game.yaml`` exists in *config_dir*.
        ValueError: If that file carries no ``puzzle_ladder`` key, or the
            ladder itself is invalid (pydantic ``ValidationError`` is a
            ``ValueError`` subclass).
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / "signal_game.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No signal_game task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "puzzle_ladder" not in raw:
        raise ValueError(f"{path} has no puzzle_ladder (required for signal_mode: per_turn_puzzle)")
    payload: dict = {"puzzle_ladder": raw["puzzle_ladder"]}
    if "underdetermined" in raw:
        payload["underdetermined"] = raw["underdetermined"]
    if "forced_wrong" in raw:
        payload["forced_wrong"] = raw["forced_wrong"]
    if "puzzle_profiles" in raw:
        payload["puzzle_profiles"] = raw["puzzle_profiles"]
    return SignalPuzzleConfig.model_validate(payload)
