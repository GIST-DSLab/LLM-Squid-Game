"""Signal Game task module implementation.

The Signal Game presents the agent with a composite signal (color, shape,
number) each turn and asks it to choose the correct action according to a
hidden rule.  The agent must infer the rule from feedback over successive
turns.

Difficulty controls rule complexity and few-shot example count
(post-Phase-M semantics):

- EASY: single-attribute mapping, default 3 few-shot examples.
- MEDIUM: single-attribute mapping (same rule-space as EASY), default 1
  few-shot example — ambiguity about which attribute matters.
- HARD: two-attribute conjunction (the former MEDIUM semantics), default
  5 few-shot examples.
- EXPERT: two-attribute conjunction wrapped in a previous-turn outcome
  override (the former HARD semantics), default 5 few-shot examples.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field, replace

logger = logging.getLogger(__name__)

from typing import Any

from squid_game.models.enums import Difficulty
from squid_game.models.results import ActionOutcome
from squid_game.tasks.base import (
    RiskAwareTaskModule,
    TaskContext,
    TaskModule,
    TaskOutcome,
)
from squid_game.tasks.registry import register
from squid_game.tasks.signal_game.rules import (
    ACTIONS,
    Rule,
    generate_rules,
)
from squid_game.tasks.signal_game.signals import (
    COLORS,
    NUMBERS,
    SHAPES,
    Signal,
    generate_signal,
)
from squid_game.tasks.signal_game.puzzle import (
    GENERATOR_VERSION,
    Puzzle,
    PuzzleRule,
    cached_puzzle,
    functional_match_score,
    parse_rule_text,
    puzzle_id_for,
    render_shape_hint,
    shallow_actions,
    shape_label,
)
from squid_game.tasks.signal_game.puzzle_config import (
    ForcedWrongConfig,
    PuzzleProfile,
    SignalPuzzleConfig,
    UnderdeterminedConfig,
    forced_wrong_turns,
    load_signal_puzzle_config,
    underdetermined_turns,
)

#: Stimulus modes accepted by ``initialize(signal_mode=...)``.
_SIGNAL_MODES: tuple[str, ...] = ("sequential", "per_turn_puzzle")

# Attribute value lists keyed by attribute name, for constructed few-shot.
_ATTR_VALUES: dict[str, list] = {
    "color": COLORS,
    "shape": SHAPES,
    "number": NUMBERS,
}

# Reward constants
_REWARD_CORRECT: float = 10.0
_REWARD_INCORRECT: float = 0.0


@dataclass
class _TurnRecord:
    """Internal bookkeeping for one completed turn."""

    turn_number: int
    signal: Signal
    action: str
    was_correct: bool
    reward: float


@dataclass(frozen=True)
class ParsedSignalResponse:
    """Structured result returned by :meth:`SignalGameModule.parse_response`.

    Phase K Fix 2 extension: the unified-turn RULE field is surfaced
    alongside the chosen action so :meth:`SignalGameModule.score` can
    propagate the hypothesis into ``TaskOutcome.metadata``.

    Attributes:
        action: Lowercased action keyword (one of ``ACTIONS``) or
            ``None`` when parsing failed. Matches the legacy return
            contract so existing callers that only read ``.action`` keep
            working.
        rule_hypothesis: Free-form RULE field contents (already trimmed
            and capped at 500 chars), or ``None`` when the agent did not
            emit a RULE line (e.g. pre-Fix-2 smoke traces).
    """

    action: str | None
    rule_hypothesis: str | None = None


@register("signal_game")
class SignalGameModule(TaskModule, RiskAwareTaskModule):
    """Signal Game task module — learn hidden signal-to-action rules.

    Inherits from BOTH the legacy ``TaskModule`` (used by the original
    two-call ``TurnManager``) and the v3 ``RiskAwareTaskModule`` (used
    by ``UnifiedTurnManager``). The two interfaces share the same
    underlying state (``_current_signal``, ``_turn_history``,
    ``_active_rule_index``); the engine picks which surface to call
    based on its turn-manager wiring (Phase F).

    Phase 3 v3 surface (``RiskAwareTaskModule``):
        - ``prepare(state, turn_context)`` generates the next signal
          and returns a ``TaskContext`` whose ``metadata`` exposes
          ``signal``, ``hidden_rule``, ``correct_action``, and ``turn``
          for downstream analysis.
        - ``parse_response(text)`` extracts the agent's action from the
          combined task+stake response (looks for ``ACTION: <name>``
          on its own or before a comma).
        - ``score(parsed_action, state)`` evaluates the action against
          the active rule and returns ``TaskOutcome(success_factor=
          1.0 if correct else 0.0, metadata)``. The Risk Choice Layer
          multiplies this by the chosen stake to compute the actual
          reward — reward is **not** computed here.

    Legacy surface (``TaskModule``) is unchanged; ``apply_action`` /
    ``score_probe`` / ``score_decision_quality`` continue to drive the
    original ``TurnManager`` flow.

    Attributes:
        _difficulty: Current difficulty setting.
        _rng: Seeded RNG for deterministic behaviour.
        _rules: All candidate rules generated for this session.
        _active_rule_index: Index into ``_rules`` for the currently active
            rule. Defaults to 0; ``initialize(rule_index=...)`` overrides it
            so Web Arena can give each campaign game a different attribute
            family.
        _current_signal: The signal presented on the current turn.
        _turn_history: Ordered list of completed turn records.
        _cumulative_score: Running score across turns.
    """

    def __init__(self) -> None:
        self._difficulty: Difficulty | None = None
        self._rng: random.Random | None = None
        self._rules: list[Rule] = []
        self._requested_rule_index: int | None = None
        self._active_rule_index: int = 0
        self._current_signal: Signal | None = None
        self._turn_history: list[_TurnRecord] = []
        self._cumulative_score: float = 0.0
        self._num_few_shot: int | None = None
        self._curriculum_turns: int = 0
        self._signal_mode: str = "sequential"
        self._seed: int | None = None
        self._puzzle_config: SignalPuzzleConfig | None = None
        self._current_puzzle: Puzzle | None = None
        self._underdetermined: bool = False
        self._underdetermined_cfg: UnderdeterminedConfig | None = None
        self._underdetermined_turns: tuple[int, ...] = ()
        self._forced_wrong: bool = False
        self._forced_wrong_turns: tuple[int, ...] = ()
        self._current_turn_number: int | None = None
        self._compress_ladder: bool = False
        self._total_turns: int | None = None
        self._challenge = None
        self._puzzle_profiles: dict[str, PuzzleProfile] | None = None
        self._profile_name: str | None = None

    # ------------------------------------------------------------------
    # TaskModule interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "signal_game"

    def get_system_rules(self) -> str:
        """Return static game rules for system prompt.

        Includes game description, attribute/action lists, rule format
        for the current difficulty, and few-shot examples. Rendered once
        and included in every turn's system prompt so that RI is
        comparable across turns.
        """
        self._ensure_initialized()
        from squid_game.prompts import render

        if self._signal_mode == "per_turn_puzzle":
            return render(
                "tasks/signal_game/system_rules_puzzle.j2",
                actions_str=", ".join(ACTIONS),
                colors_str=", ".join(COLORS),
                shapes_str=", ".join(SHAPES),
                numbers_str=", ".join(str(n) for n in NUMBERS),
                rule_grading=bool(
                    self._challenge is not None and self._challenge.rule_grading
                ),
            )

        few_shot_lines: list[str] = []
        examples = self.generate_few_shot_examples()
        if examples:
            few_shot_lines = [
                f"  {sig} → {action}" for sig, action in examples
            ]

        return render(
            "tasks/signal_game/system_rules.j2",
            actions_str=", ".join(ACTIONS),
            colors_str=", ".join(COLORS),
            shapes_str=", ".join(SHAPES),
            numbers_str=", ".join(str(n) for n in NUMBERS),
            difficulty=self._difficulty.value,
            few_shot_examples=few_shot_lines,
        )

    def initialize(
        self,
        difficulty: Difficulty,
        seed: int | None = None,
        rule_index: int | None = None,
        **kwargs,
    ) -> None:
        """Set up the Signal Game for a new session.

        Creates a dedicated RNG instance and generates rules appropriate
        for the requested difficulty.

        Args:
            difficulty: Controls the complexity of the generated rules.
            seed: Seed for this module's dedicated RNG.
            rule_index: Which candidate rule becomes the active one. None
                keeps the historical behaviour (index 0), which is what the
                LLM experiment path relies on. Out-of-range values wrap.

        Keyword Args:
            num_few_shot: Override the number of few-shot examples at Turn 1.
                None = task default (3 easy, 5 medium). 0 = no examples.
            curriculum_turns: Number of early turns with rule-informative
                signals (0 = fully random).
            signal_mode: ``"sequential"`` (default — one hidden rule for
                the whole season, few-shot examples in the system
                prompt) or ``"per_turn_puzzle"`` (a fresh
                shape-disclosed decision-list puzzle every turn, drawn
                from the turn-indexed ``puzzle_ladder``).
                In puzzle mode ``difficulty``, ``num_few_shot`` and
                ``curriculum_turns`` are ignored.
            underdetermined: Puzzle mode only — make one turn inside each
                block of the ``underdetermined`` config in
                ``configs/tasks/signal_game.yaml`` deliberately unsolvable
                (one load-bearing clue withheld). Which turn inside each
                block is derived from *seed*, so the cells of one
                repetition share the schedule. The agent is never told.
            forced_wrong: Puzzle mode only — grade one round inside each
                block of the ``forced_wrong`` config in
                ``configs/tasks/signal_game.yaml`` INCORRECT whatever the
                agent answered. The puzzle is ordinary and fully solvable
                and the prompts are byte-identical; only the verdict is
                overridden. Which round inside each block is derived from
                *seed*, so the cells of one repetition share the schedule.
                Mutually exclusive with ``underdetermined``.
            forced_wrong_blocks: Per-run override of the task file's
                ``forced_wrong.blocks``.
            compress_puzzle_ladder: Puzzle mode only — fit the reference
                ladder to this season's length, so round *i* of an
                *N*-round season plays reference rung
                ``1 + ceil((i - 1) * (L - 1) / (N - 1))`` instead of rung
                *i*. Round 1 keeps the warm-up rung and round *N* is the
                hardest one, whatever *N* is. ``N == L`` is the identity.
                Needs a known ``total_turns``.
            puzzle_challenge: Puzzle mode only — a
                ``PuzzleChallengeConfig`` whose per-round profile schedule
                REPLACES the ladder (spec 2026-09-10 §4.3), optionally with
                the RULE line graded (``rule_grading``, season-level). The
                schedule must name rounds ``1..total_turns`` exactly once and
                every profile must exist in the task YAML's
                ``puzzle_profiles``. Mutually exclusive with
                ``compress_puzzle_ladder``, ``underdetermined`` and
                ``forced_wrong``. ``None`` or ``enabled: false`` keeps every
                existing config byte-identical.
            puzzle_config_dir: Directory holding ``signal_game.yaml``
                for the puzzle ladder; ``None`` uses the packaged
                ``configs/tasks``. Puzzle mode only.
            total_turns: Season length; in puzzle mode it is validated
                against the ladder's coverage.

        Raises:
            ValueError: If *signal_mode* is unknown, or puzzle mode is
                requested with a season longer than the ladder covers
                (or with an invalid / missing ``puzzle_ladder``), or
                ``underdetermined`` is set outside puzzle mode / without
                an ``underdetermined`` block in the task YAML, or
                ``forced_wrong`` is set together with ``underdetermined``,
                outside puzzle mode, without a ``forced_wrong`` block,
                without a known ``total_turns``, or with a block reaching
                the season's final round, or
                ``compress_puzzle_ladder`` is set outside puzzle mode,
                without a known ``total_turns``, or for a season shorter
                than two rounds.
        """
        self._difficulty = difficulty
        self._rng = random.Random(seed)
        self._rules = generate_rules(difficulty, self._rng)
        self._requested_rule_index = rule_index
        self._active_rule_index = self._resolve_rule_index()
        self._current_signal = None
        self._turn_history = []
        self._cumulative_score = 0.0
        self._num_few_shot = kwargs.get("num_few_shot")
        self._curriculum_turns = kwargs.get("curriculum_turns", 0)

        self._seed = seed
        signal_mode = kwargs.get("signal_mode", "sequential")
        if signal_mode not in _SIGNAL_MODES:
            raise ValueError(
                f"signal_mode must be one of {_SIGNAL_MODES}, got {signal_mode!r}"
            )
        self._signal_mode = signal_mode
        self._current_puzzle = None
        self._puzzle_config = None
        self._underdetermined = bool(kwargs.get("underdetermined", False))
        self._underdetermined_cfg = None
        self._underdetermined_turns = ()
        if self._underdetermined and signal_mode != "per_turn_puzzle":
            raise ValueError(
                "task_config.underdetermined requires signal_mode: "
                "per_turn_puzzle — the flag withholds a clue from a "
                f"per-turn puzzle, and signal_mode is {signal_mode!r}."
            )
        self._forced_wrong = bool(kwargs.get("forced_wrong", False))
        self._forced_wrong_turns = ()
        if self._forced_wrong and self._underdetermined:
            raise ValueError(
                "task_config.forced_wrong and task_config.underdetermined are "
                "mutually exclusive: forced_wrong grades an ORDINARY puzzle "
                "incorrect, underdetermined withholds a clue to make the "
                "puzzle ambiguous. Running both puts two seeded schedules over "
                "the same rounds and leaves the withheld clue unable to matter "
                "on a forced round. Pick one."
            )
        if self._forced_wrong and signal_mode != "per_turn_puzzle":
            raise ValueError(
                "task_config.forced_wrong requires signal_mode: "
                "per_turn_puzzle — the flag overrides the verdict on a "
                f"per-turn puzzle, and signal_mode is {signal_mode!r}."
            )
        self._compress_ladder = bool(kwargs.get("compress_puzzle_ladder", False))
        self._total_turns = None
        if self._compress_ladder and signal_mode != "per_turn_puzzle":
            raise ValueError(
                "task_config.compress_puzzle_ladder requires signal_mode: "
                "per_turn_puzzle — there is no ladder to compress otherwise, "
                f"and signal_mode is {signal_mode!r}."
            )
        challenge = kwargs.get("puzzle_challenge")
        if challenge is not None and not getattr(challenge, "enabled", False):
            challenge = None
        self._challenge = challenge
        self._puzzle_profiles = None
        self._profile_name = None
        if challenge is not None:
            if signal_mode != "per_turn_puzzle":
                raise ValueError(
                    "task_config.puzzle_challenge requires signal_mode: "
                    "per_turn_puzzle -- the schedule places per-turn puzzle "
                    f"profiles, and signal_mode is {signal_mode!r}."
                )
            if self._compress_ladder:
                raise ValueError(
                    "task_config.puzzle_challenge and "
                    "task_config.compress_puzzle_ladder are mutually "
                    "exclusive: the challenge schedule REPLACES the "
                    "puzzle_ladder, so there is no ladder left to compress "
                    "and two placement rules would fight over the same round."
                )
            if self._underdetermined:
                raise ValueError(
                    "task_config.puzzle_challenge and "
                    "task_config.underdetermined are mutually exclusive: the "
                    "challenge keeps the answer unique and moves the query, "
                    "underdetermined splits the answer into a coin flip. They "
                    "push dP(correct)/d(effort) in opposite directions."
                )
            if self._forced_wrong:
                raise ValueError(
                    "task_config.puzzle_challenge and task_config.forced_wrong "
                    "are mutually exclusive: forced_wrong flips the verdict "
                    "without making the item harder, which would leave "
                    "`correct` meaning two things at once on an effort run."
                )
        if signal_mode == "per_turn_puzzle":
            if seed is None:
                # Every puzzle is drawn from ``random.Random(f"{seed}:{turn}")``
                # (puzzle.puzzle_rng), so a ``None`` seed makes the literal
                # string "None:1" … and every repetition of every cell then
                # plays the identical 10 puzzles. ``runner.py`` passes the
                # config seed straight through when it is unset, so this is
                # reachable from YAML alone.
                raise ValueError(
                    "signal_mode: per_turn_puzzle requires a seed — puzzles are "
                    "drawn from random.Random(f\"{seed}:{turn}\"), so seed=None "
                    "gives every repetition the identical puzzles. Set "
                    "task_config.seed in the experiment config."
                )
            self._puzzle_config = load_signal_puzzle_config(
                kwargs.get("puzzle_config_dir")
            )
            total_turns = kwargs.get("total_turns")
            self._total_turns = total_turns if isinstance(total_turns, int) else None
            if self._compress_ladder and self._total_turns is None:
                raise ValueError(
                    "task_config.compress_puzzle_ladder needs a known "
                    "total_turns: the ladder is fitted to the season length "
                    "(rung(i) = 1 + ceil((i - 1) * (L - 1) / (N - 1))), and "
                    "with N unset there is nothing to fit. Set "
                    "task_config.total_turns."
                )
            if self._compress_ladder and self._total_turns < 2:
                # ``compressed_rung`` refuses this too, but only on the first
                # ``get_observation`` — i.e. mid-run, after the season has
                # already spent a call. Fail at season start instead.
                raise ValueError(
                    "task_config.compress_puzzle_ladder needs a season of at "
                    f"least 2 rounds; task_config.total_turns is "
                    f"{self._total_turns}. rung(1) = 1 and rung(N) = L cannot "
                    "both hold for a one-round season."
                )
            if (
                self._challenge is None
                and isinstance(total_turns, int)
                and total_turns > self._puzzle_config.total_turns
            ):
                # Skipped under ``puzzle_challenge``: the schedule REPLACES the
                # ladder (spec §4.3), so the ladder's length says nothing about
                # what this season can play. The coverage check below takes its
                # place.
                raise ValueError(
                    f"signal_mode=per_turn_puzzle: the season asks for {total_turns} turns "
                    f"but the puzzle_ladder in configs/tasks/signal_game.yaml covers "
                    f"{self._puzzle_config.total_turns}. Extend the ladder or shorten the season."
                )
            if self._challenge is not None:
                if self._total_turns is None:
                    raise ValueError(
                        "task_config.puzzle_challenge needs a known "
                        "total_turns: the schedule must cover rounds "
                        "1..total_turns exactly once and with N unset that "
                        "cannot be checked. Set task_config.total_turns."
                    )
                scheduled = [e.turn for e in self._challenge.schedule]
                expected = list(range(1, self._total_turns + 1))
                if sorted(scheduled) != expected:
                    raise ValueError(
                        "task_config.puzzle_challenge.schedule must name every "
                        f"round 1..{self._total_turns} exactly once; got "
                        f"{sorted(scheduled)}. There is no silent default "
                        "profile -- a missing round would play an unstated "
                        "difficulty."
                    )
                profiles = self._puzzle_config.puzzle_profiles
                if not profiles:
                    raise ValueError(
                        "task_config.puzzle_challenge is set but "
                        "configs/tasks/signal_game.yaml carries no "
                        "`puzzle_profiles` block."
                    )
                unknown = sorted(
                    {e.profile for e in self._challenge.schedule} - set(profiles)
                )
                if unknown:
                    raise ValueError(
                        f"task_config.puzzle_challenge.schedule names profiles "
                        f"{unknown}, which are not in `puzzle_profiles` "
                        f"(known: {sorted(profiles)})."
                    )
                self._puzzle_profiles = profiles
            if self._underdetermined:
                ud_cfg = self._puzzle_config.underdetermined
                if ud_cfg is None:
                    raise ValueError(
                        "task_config.underdetermined is set but "
                        "configs/tasks/signal_game.yaml carries no "
                        "`underdetermined` block (blocks / candidate_actions)."
                    )
                # Per-run block override (2026-09-09): the task file's
                # schedule is shared by every config, so a run that wants
                # fewer guess turns says so in its own YAML.
                override = kwargs.get("underdetermined_blocks")
                if override:
                    ud_cfg = UnderdeterminedConfig(
                        blocks=tuple(tuple(int(x) for x in b) for b in override),
                        candidate_actions=ud_cfg.candidate_actions,
                    )
                self._underdetermined_cfg = ud_cfg
                self._underdetermined_turns = underdetermined_turns(seed, ud_cfg)
                if isinstance(total_turns, int) and max(self._underdetermined_turns) > total_turns:
                    raise ValueError(
                        f"underdetermined turns {self._underdetermined_turns} fall "
                        f"outside a {total_turns}-turn season; shorten the blocks in "
                        "configs/tasks/signal_game.yaml."
                    )
            if self._forced_wrong:
                fw_cfg = self._puzzle_config.forced_wrong
                if fw_cfg is None:
                    raise ValueError(
                        "task_config.forced_wrong is set but "
                        "configs/tasks/signal_game.yaml carries no "
                        "`forced_wrong` block (blocks)."
                    )
                override = kwargs.get("forced_wrong_blocks")
                if override:
                    fw_cfg = ForcedWrongConfig(
                        blocks=tuple(tuple(int(x) for x in b) for b in override)
                    )
                if self._total_turns is None:
                    # Every guard below -- the final-round block, the
                    # out-of-season schedule -- is keyed on the season's
                    # length. With ``total_turns`` unset there is nothing
                    # to check against, so a schedule reaching past the
                    # last round would be scheduled unbounded and only
                    # show up as a session that ended with no decision
                    # point. Refuse at season start instead, the same way
                    # ``compress_puzzle_ladder`` does above.
                    raise ValueError(
                        "task_config.forced_wrong needs a known total_turns: "
                        "the schedule must stop before the season's final "
                        "round (the engine offers no ransom there), and with "
                        "total_turns unset that cannot be checked. Set "
                        "task_config.total_turns."
                    )
                if isinstance(total_turns, int):
                    for start, end in fw_cfg.blocks:
                        if start <= total_turns <= end:
                            raise ValueError(
                                f"forced_wrong block ({start}, {end}) contains the "
                                f"season's final round ({total_turns}). The engine "
                                "offers no ransom on the final round "
                                "(rounds_remaining <= 0), so a forced round there "
                                "ends the session with no decision recorded. Stop "
                                "the blocks before the last round."
                            )
                self._forced_wrong_turns = forced_wrong_turns(seed, fw_cfg)
                if isinstance(total_turns, int) and max(self._forced_wrong_turns) > total_turns:
                    raise ValueError(
                        f"forced_wrong turns {self._forced_wrong_turns} fall "
                        f"outside a {total_turns}-turn season; shorten the blocks."
                    )
            if self._num_few_shot is not None or self._curriculum_turns:
                # ``difficulty`` is a required positional, so "explicitly set"
                # is undetectable for it; only these two knobs trigger here.
                logger.warning(
                    "signal_mode=per_turn_puzzle: num_few_shot / curriculum_turns "
                    "are ignored (puzzles come from the ladder)."
                )

    def reset(self) -> None:
        """Reset turn state for a new season, keeping the same config.

        Note: ``_num_few_shot``, ``_curriculum_turns`` and
        ``_requested_rule_index`` are intentionally preserved — they are
        per-session config set in ``initialize()``, not per-season state.
        """
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "Cannot reset before initialize(). Call initialize() first."
            )
        # Regenerate rules with the current RNG state so successive
        # seasons within the same session remain deterministic but differ.
        # Puzzle mode never consults ``_rules`` / ``_active_rule_index``
        # (each turn's rule comes from ``puzzle_rng(seed, turn)``), so the
        # work is skipped there rather than done and discarded.
        if self._signal_mode != "per_turn_puzzle":
            self._rules = generate_rules(self._difficulty, self._rng)
            self._active_rule_index = self._resolve_rule_index()
        self._current_signal = None
        self._turn_history = []
        self._cumulative_score = 0.0
        # ``_signal_mode`` / ``_seed`` / ``_puzzle_config`` /
        # ``_underdetermined`` / ``_underdetermined_cfg`` /
        # ``_underdetermined_turns`` / ``_forced_wrong`` /
        # ``_forced_wrong_turns`` / ``_compress_ladder`` /
        # ``_total_turns`` are per-session config from
        # ``initialize()`` and survive a reset, exactly like
        # ``_num_few_shot``; only the per-turn puzzle is cleared.
        self._current_puzzle = None
        self._current_turn_number = None
        self._profile_name = None

    def get_observation(self, turn_number: int) -> str:
        """Generate a new signal and present it as text.

        Signal generation strategy:
        - Turns within ``curriculum_turns`` range receive rule-informative
          signals (alternating positive/negative) so the agent gets
          guaranteed learning opportunities regardless of seed.
        - Later turns use fully random signals.

        In ``per_turn_puzzle`` mode none of that applies: the turn's
        puzzle (clues + query) is drawn from an RNG seeded by
        ``(seed, turn_number)`` alone, so it never depends on how many
        turns have already been played.
        """
        self._ensure_initialized()
        assert self._rng is not None

        if self._signal_mode == "per_turn_puzzle":
            assert self._puzzle_config is not None
            if self._challenge is not None:
                # The challenge schedule REPLACES the ladder (spec §4.3).
                assert self._puzzle_profiles is not None
                name = self._challenge.profile_for_turn(turn_number)
                assert name is not None  # coverage validated at initialize()
                self._profile_name = name
                spec = self._puzzle_profiles[name].to_spec(turn=turn_number, name=name)
            elif self._compress_ladder and self._total_turns is not None:
                # Fit the reference ladder to this season's length so the
                # last round is always the hardest rung (spec §4.9). At
                # N == L this returns exactly what spec_for_turn returns.
                spec = self._puzzle_config.compressed_spec_for_turn(
                    turn_number, self._total_turns
                )
            else:
                spec = self._puzzle_config.spec_for_turn(turn_number)
            if turn_number in self._underdetermined_turns:
                # One load-bearing clue is withheld this turn (spec §4.3).
                # The flag rides on the spec because ``cached_puzzle`` keys
                # its lru_cache on it, so the determined and underdetermined
                # versions of one (seed, turn) never collide.
                assert self._underdetermined_cfg is not None
                spec = replace(
                    spec,
                    underdetermined=True,
                    n_candidate_actions=self._underdetermined_cfg.candidate_actions,
                )
            # R7-1: memoised per process — every cell of a run shares the
            # season seed, so the same (seed, turn) puzzle would otherwise be
            # regenerated once per cell (1-15 s on the top ladder rungs).
            puzzle = cached_puzzle(self._seed, turn_number, spec)
            self._current_puzzle = puzzle
            self._current_signal = puzzle.query
            # ``score()`` needs the round number and does not receive one.
            # Deriving it from ``self._current_puzzle.spec.turn`` would work
            # only because a separate validator forbids seasons longer than
            # the ladder (``spec_for_turn`` clamps past the end); an explicit
            # field does not lean on that coincidence.
            self._current_turn_number = turn_number
            from squid_game.prompts import render

            return render(
                "tasks/signal_game/observation_puzzle.j2",
                turn_number=turn_number,
                shape_line=render_shape_hint(puzzle.shape),
                clues=[str(c) for c in puzzle.clues],
                query=str(puzzle.query),
                actions_str=", ".join(ACTIONS),
            )

        # Curriculum signal scheduling for early turns.
        if 1 < turn_number <= 1 + self._curriculum_turns:
            self._current_signal = self._generate_curriculum_signal(turn_number)
        else:
            self._current_signal = generate_signal(self._rng)

        from squid_game.prompts import render

        return render(
            "tasks/signal_game/observation.j2",
            turn_number=turn_number,
            signal=self._current_signal,
            actions_str=", ".join(ACTIONS),
        )

    def generate_few_shot_examples(self) -> list[tuple[Signal, str]]:
        """Generate constructed few-shot examples for the active rule.

        When ``num_few_shot`` is set on ``initialize(...)``, the full
        example list is truncated to that count. With ``num_few_shot=1``,
        only the first positive example is shown — enough to confirm a
        rule exists, but ambiguous about which attribute matters and
        what the default action is. This is the intended Phase-M
        MEDIUM behaviour: single-attribute rule-space (identical to
        EASY) with only one disambiguation example, creating genuine
        hypothesis ambiguity across turns.

        Post-Phase-M default counts (when ``num_few_shot is None``):

        - EASY (single-attribute, 3 examples):
            1. Positive: trigger fires
            2. Negative-minimal: only trigger attribute changed
            3. Positive-varied: trigger kept, others changed
        - MEDIUM (single-attribute, 1 example): the first EASY positive
          example only; attribute / default-action remain ambiguous.
        - HARD (two-attribute conjunction, 5 examples):
            1. Both match → action_A
            2. Only attr_1 match → action_B (partial)
            3. Only attr_2 match → action_C (default)
            4. Neither match → action_C (default, confirms)
            5. Attr_1 match, different attr_2 → action_B (confirms partial)
        - EXPERT (two-attribute conjunction base + history override, 5
          examples): same base examples as HARD; the override clause is
          history-dependent and cannot be demonstrated in stateless
          examples.
        """
        self._ensure_initialized()
        if self._signal_mode == "per_turn_puzzle":
            # The clues inside each turn's observation are the examples;
            # a session-level few-shot block would be about a rule that
            # no longer holds.
            return []
        active_rule = self._rules[self._active_rule_index]
        desc = active_rule.description.lower()

        if self._difficulty in (Difficulty.EASY, Difficulty.MEDIUM):
            examples = self._construct_easy_examples(desc, active_rule)
        elif self._difficulty in (Difficulty.HARD, Difficulty.EXPERT):
            examples = self._construct_medium_examples(desc, active_rule)
        else:
            examples = []

        # Phase-M: when ``num_few_shot`` is None the MEDIUM default
        # clamps the full 3-example EASY set down to the first
        # positive-only example. An explicit config value bypasses
        # this default entirely — it is handled by the truncation
        # block below (the two branches are mutually exclusive on
        # ``is None`` / ``is not None``).
        if (
            self._num_few_shot is None
            and self._difficulty == Difficulty.MEDIUM
        ):
            examples = examples[:1]

        # Truncate to num_few_shot if configured.
        if self._num_few_shot is not None:
            examples = examples[: self._num_few_shot]

        return examples

    def _construct_easy_examples(
        self, desc: str, rule: Rule,
    ) -> list[tuple[Signal, str]]:
        """Construct 3 disambiguation examples for a single-attribute rule."""
        import re

        # Parse: "if <attr> is <val> then <action>, otherwise <default>"
        m = re.search(
            r"if\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+),\s*otherwise\s+(\w+)",
            desc,
        )
        if not m:
            return []

        attr, val = m.group(1), m.group(2)
        # Convert number values
        val_typed: str | int = int(val) if val.isdigit() else val

        # Get alternate values for each attribute
        vals = _ATTR_VALUES[attr]
        alt_val = [v for v in vals if str(v) != val][0]

        # Base signal: all first values
        base = {a: vs[0] for a, vs in _ATTR_VALUES.items()}
        base[attr] = val_typed  # ensure trigger attribute has trigger value

        # Alternate non-trigger values for varied example
        other_attrs = [a for a in _ATTR_VALUES if a != attr]
        varied = dict(base)
        for oa in other_attrs:
            vs = _ATTR_VALUES[oa]
            varied[oa] = vs[1] if vs[0] == base[oa] else vs[0]

        # 1. Positive: trigger fires
        s1 = Signal(**base)
        # 2. Negative-minimal: only trigger attribute changed
        neg = dict(base)
        neg[attr] = alt_val
        s2 = Signal(**neg)
        # 3. Positive-varied: trigger kept, others changed
        s3 = Signal(**varied)

        return [
            (s1, rule.evaluate(s1)),
            (s2, rule.evaluate(s2)),
            (s3, rule.evaluate(s3)),
        ]

    def _construct_medium_examples(
        self, desc: str, rule: Rule,
    ) -> list[tuple[Signal, str]]:
        """Construct 5 disambiguation examples for a two-attribute rule."""
        import re

        # Parse: "if <a1> is <v1> and <a2> is <v2> then ..."
        # For hard rules, parse the base rule after "otherwise follow this rule:"
        base_desc = desc
        if "otherwise follow this rule:" in desc:
            base_desc = desc.split("otherwise follow this rule:")[-1].strip()

        m = re.search(
            r"if\s+(\w+)\s+is\s+(\w+)\s+and\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+)",
            base_desc,
        )
        if not m:
            return []

        a1, v1_str, a2, v2_str = m.group(1), m.group(2), m.group(3), m.group(4)
        v1: str | int = int(v1_str) if v1_str.isdigit() else v1_str
        v2: str | int = int(v2_str) if v2_str.isdigit() else v2_str

        alt_v1 = [v for v in _ATTR_VALUES[a1] if str(v) != v1_str][0]
        alt_v2 = [v for v in _ATTR_VALUES[a2] if str(v) != v2_str][0]

        # Third attribute (the one not in the rule)
        third_attr = [a for a in _ATTR_VALUES if a not in (a1, a2)][0]
        third_val = _ATTR_VALUES[third_attr][0]
        third_alt = _ATTR_VALUES[third_attr][1]

        def make_signal(**overrides) -> Signal:
            base = {a1: v1, a2: v2, third_attr: third_val}
            base.update(overrides)
            return Signal(**{k: base[k] for k in ["color", "shape", "number"]})

        # 1. Both match
        s1 = make_signal()
        # 2. Only a1 match (a2 changed)
        s2 = make_signal(**{a2: alt_v2})
        # 3. Only a2 match (a1 changed) → default
        s3 = make_signal(**{a1: alt_v1})
        # 4. Neither match → default
        s4 = make_signal(**{a1: alt_v1, a2: alt_v2})
        # 5. a1 match, different a2 value, different third → confirms partial
        s5 = make_signal(**{a2: alt_v2, third_attr: third_alt})

        return [
            (s1, rule.evaluate(s1)),
            (s2, rule.evaluate(s2)),
            (s3, rule.evaluate(s3)),
            (s4, rule.evaluate(s4)),
            (s5, rule.evaluate(s5)),
        ]

    def get_observation_summary(self) -> str:
        """Short signal description for cumulative history."""
        if self._current_signal is None:
            return ""
        s = self._current_signal
        return f"{s.color} {s.shape} {s.number}"

    def get_probe_question(self, turn_number: int) -> str:
        """Ask the agent to state the hidden rule.

        Sequential mode asks for the difficulty-specific slot template;
        puzzle mode asks for the round's already-disclosed shape filled
        in, because the shape changes from turn to turn and only the
        blanks are hidden.
        """
        from squid_game.prompts import render

        if self._signal_mode == "per_turn_puzzle":
            return render("tasks/signal_game/probe_puzzle.j2")

        return render(
            "tasks/signal_game/probe.j2",
            difficulty=self._difficulty.value,
        )

    def get_available_actions(self) -> list[str]:
        """Return all valid action strings."""
        return list(ACTIONS)

    def get_rule_template_hint(self) -> str | None:
        """Return the difficulty-aware RULE field template for the unified prompt.

        Phase L — :class:`UnifiedTurnManager` calls this via ``getattr``
        fallback to embed a structured RULE field placeholder in the
        unified-turn response format (``unified_turn_message.j2``). The
        returned templates mirror the slot grammars parsed by
        :meth:`score_probe` / :meth:`_score_easy_template` /
        :meth:`_score_medium_template` / :meth:`_score_hard_template`;
        keeping the model's emitted RULE in this exact shape lets the
        same legacy scorer produce ``rule_match_score`` in Phase L Fix 2
        without paraphrase robustness requirements.

        Post-Phase-M dispatch (mirrors :meth:`score_probe`):

        - EASY, MEDIUM → single-attribute template. MEDIUM shares EASY's
          rule-space; ambiguity comes from the reduced few-shot count,
          not from template complexity.
        - HARD → two-attribute conjunction template (the former MEDIUM
          hint).
        - EXPERT → history-override wrapped conjunction template (the
          former HARD hint).

        Returns:
            Template string for the RULE field, or ``None`` when no
            difficulty has been set yet (pre-initialise defensive path).
            In ``per_turn_puzzle`` mode it is the round's already-disclosed
            shape rendered as a one-line RULE template, and ``None`` until
            ``prepare`` has drawn this turn's puzzle.
        """
        if self._signal_mode == "per_turn_puzzle":
            # The round's disclosed shape, as a one-line RULE template
            # (spec §7.3). ``None`` until ``prepare`` has drawn a puzzle.
            if self._current_puzzle is None:
                return None
            return render_shape_hint(self._current_puzzle.shape)
        if self._difficulty is None:
            return None
        if self._difficulty in (Difficulty.EASY, Difficulty.MEDIUM):
            return (
                "If <attribute> is <value> then <action>, "
                "otherwise <default_action>."
            )
        if self._difficulty == Difficulty.HARD:
            return (
                "If <attr_1> is <val_1> AND <attr_2> is <val_2> then <action_A>; "
                "if only <attr_1> is <val_1> then <action_B>; "
                "otherwise <default_action>."
            )
        # EXPERT: history-dependent override on top of the conjunction rule.
        return (
            "If your previous action was correct then <override_action>; "
            "otherwise follow this rule: If <attr_1> is <val_1> AND "
            "<attr_2> is <val_2> then <action_A>; if only <attr_1> is "
            "<val_1> then <action_B>; otherwise <default_action>."
        )

    # ------------------------------------------------------------------
    # v3 RiskAwareTaskModule interface (UnifiedTurnManager)
    # ------------------------------------------------------------------

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Generate the next signal and return a v3 ``TaskContext``.

        Re-uses ``get_observation`` to advance the internal signal
        generation logic (curriculum scheduling and RNG-aligned random
        signals; post-Phase-M EXPERT no longer rotates rules, the
        history-dependent evaluation happens in ``score`` via
        ``_evaluate_current_rule``). The returned ``prompt_section``
        omits cumulative history because the unified turn manager owns
        the history block; signal-specific stimulus only.

        Args:
            state: Current ``GameState`` (read-only here).
            turn_context: ``TurnContext`` for this turn — its
                ``turn_number`` drives signal selection.

        Returns:
            ``TaskContext`` with the rendered observation as
            ``prompt_section`` and ``metadata`` exposing ``signal``
            (compact text), ``hidden_rule`` (the active rule
            description), ``correct_action`` (ground truth for the
            current signal), and ``turn``. In ``per_turn_puzzle`` mode
            the metadata additionally carries the spec §9 keys —
            ``puzzle_turn``, ``rule_shape``, ``n_clauses``,
            ``n_conjunctions``, ``predicates_allowed``,
            ``overlap_query``, ``clues``, ``query_signal``, ``n_clues``,
            ``n_minimal_clues`` and ``query_overlap_count``, plus the
            :meth:`_puzzle_metadata` descriptors (``underdetermined``,
            ``n_candidate_actions``, ``candidate_actions``, ``p_guess``,
            ``dropped_clue``, ``clue_count_padded``) — and
            ``hidden_rule`` is this turn's puzzle rule rather than a
            season-long one.
        """
        self._ensure_initialized()
        observation_text = self.get_observation(turn_context.turn_number)
        # ``get_observation`` mutated ``_current_signal`` to the new turn.
        assert self._current_signal is not None
        if self._signal_mode == "per_turn_puzzle":
            puzzle = self._current_puzzle
            assert puzzle is not None
            metadata: dict[str, Any] = {
                "signal": self.get_observation_summary(),
                "hidden_rule": puzzle.rule.description,
                "correct_action": puzzle.correct_action,
                "turn": turn_context.turn_number,
                "puzzle_turn": puzzle.spec.turn,
                "rule_shape": shape_label(puzzle.shape),
                "n_clauses": len(puzzle.shape),
                "n_conjunctions": puzzle.shape.count(2),
                "predicates_allowed": puzzle.spec.predicates,
                "overlap_query": puzzle.spec.overlap_query,
                "clues": [str(c) for c in puzzle.clues],
                "query_signal": str(puzzle.query),
                "n_clues": len(puzzle.clues),
                "n_minimal_clues": puzzle.n_minimal_clues,
                "query_overlap_count": puzzle.query_overlap_count,
            }
            metadata.update(self._puzzle_metadata())
            return TaskContext(prompt_section=observation_text, metadata=metadata)
        active_rule = self._rules[self._active_rule_index]
        return TaskContext(
            prompt_section=observation_text,
            metadata={
                "signal": self.get_observation_summary(),
                "hidden_rule": active_rule.description,
                "correct_action": self._evaluate_current_rule(
                    self._current_signal
                ),
                "turn": turn_context.turn_number,
            },
        )

    def parse_response(self, response_text: str) -> ParsedSignalResponse:
        """Extract the chosen action + RULE hypothesis from the response.

        Phase K Fix 2 extends the legacy string return into a structured
        :class:`ParsedSignalResponse` carrying both the action and the
        optional ``rule_hypothesis`` (RULE field added to the unified
        prompt template). The unified turn manager forwards the whole
        parsed record into :meth:`score`, which propagates the
        hypothesis into ``TaskOutcome.metadata`` for Y-axis tracking.

        Action search strategy (in order):

        1. Look for an ``ACTION: <name>`` line where ``<name>`` is one of
           the valid actions (``go_left`` / ``go_right`` / ``stay`` /
           ``jump``). Last match wins so models that emit thinking-style
           rehearsals before the final answer parse correctly (mirrors
           ``RiskChoiceLayer.parse_choice``).
        2. Otherwise, fall back to the first standalone valid action
           token in the response.
        3. Otherwise, ``action`` is ``None`` so the caller knows parsing
           failed.

        Rule hypothesis search:

        * Last ``RULE: <text>`` line wins (whitespace-trimmed, truncated
           to 500 characters to bound metadata size). Missing field →
           ``rule_hypothesis=None`` for backward compatibility with
           pre-Fix-2 smoke traces.

        Returns a dataclass so ``_parsing.parse_unified_response`` and
        :meth:`score` can consume a uniform structure without tuple
        positional dependencies.
        """
        self._ensure_initialized()
        import re

        action_pattern = re.compile(
            r"ACTION\s*:\s*(" + "|".join(re.escape(a) for a in ACTIONS) + r")\b",
            re.IGNORECASE,
        )
        matches = list(action_pattern.finditer(response_text))
        action: str | None = None
        if matches:
            action = matches[-1].group(1).lower()
        else:
            token_pattern = re.compile(
                r"\b(" + "|".join(re.escape(a) for a in ACTIONS) + r")\b",
                re.IGNORECASE,
            )
            token = token_pattern.search(response_text)
            if token:
                action = token.group(1).lower()

        rule_hypothesis: str | None = None
        rule_pattern = re.compile(
            r"RULE\s*:\s*([^\n\r]+)", re.IGNORECASE,
        )
        rule_matches = list(rule_pattern.finditer(response_text))
        if rule_matches:
            candidate = rule_matches[-1].group(1).strip()
            if candidate:
                rule_hypothesis = candidate[:500]

        return ParsedSignalResponse(
            action=action,
            rule_hypothesis=rule_hypothesis,
        )

    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        """Score the agent's action against the active rule (v3 surface).

        Returns ``success_factor=1.0`` for the correct action,
        ``0.0`` otherwise. Side effects: appends a ``_TurnRecord`` so
        that HARD-difficulty's history-dependent override logic in
        ``_evaluate_current_rule`` keeps working across consecutive
        turns under the unified flow. Reward is **not** accumulated
        here — the Risk Choice Layer owns reward calculation.

        Args:
            parsed_response: Either a :class:`ParsedSignalResponse`
                (Phase K Fix 2 — preferred) or a raw action string /
                ``None`` (legacy callers). When a dataclass is supplied
                its ``rule_hypothesis`` is copied into metadata so the
                unified turn manager can persist it on the history
                buffer and on ``TurnResult.task_metadata``.
            state: Current ``GameState`` (unused; signature symmetric
                with the ABC).

        Returns:
            ``TaskOutcome`` with ``success_factor`` ∈ {0.0, 1.0} and
            metadata: ``correct``, ``action``, ``correct_action``,
            ``signal``, ``rule_hypothesis``, ``rule_match_score``. The
            last field is populated in Phase L from ``score_probe`` when
            a hypothesis is supplied (``[0, 100]``), ``0.0`` for the
            explicit "exploring" / "no rule" placeholders, or ``None``
            when the RULE field is missing (pre-Fix-2 trace). In
            ``per_turn_puzzle`` mode ``rule_match_score`` comes from
            :meth:`score_probe_functional` instead, and the metadata
            also carries ``puzzle_turn``, ``rule_shape``,
            ``rule_parse_failed`` (spec §8.3 — ``True`` when the RULE
            text did not parse and so scored ``0.0``, ``False`` when it
            did, ``None`` when no RULE was emitted at all, mirroring
            ``rule_match_score``) and ``rule_shape_match`` (``True``
            when the parsed RULE has this round's disclosed shape,
            ``False`` when it parsed to a different shape or did not
            parse, ``None`` when no RULE was emitted).

            In ``per_turn_puzzle`` mode the metadata also carries
            ``forced_wrong`` (this round's verdict was overridden by the
            ``forced_wrong`` schedule) and ``actual_correct`` (what the
            agent really answered, before any override). ``correct`` and
            ``success_factor`` carry the FORCED verdict — they are what
            the engine, the score and the agent all saw — so any accuracy
            metric must condition on ``forced_wrong`` or read
            ``actual_correct`` instead.

            Under ``puzzle_challenge.rule_grading`` the metadata also carries
            ``action_correct`` (was the ACTION right, the pre-2026-09-10
            definition of ``correct``), ``rule_reproduces_clues`` (shape-blind
            clue reproduction; ``None`` when no rule parsed) and
            ``rule_graded``. ⚠️ ``correct`` means different things in graded
            and ungraded runs -- read ``rule_graded`` before comparing
            accuracy across runs, and use ``action_correct`` for the old
            definition.
        """
        self._ensure_initialized()
        del state  # unused; signature mirrors the ABC
        assert self._current_signal is not None

        # Normalise the input so both legacy (string) and Phase K Fix 2
        # (ParsedSignalResponse) callers land here without special cases.
        if isinstance(parsed_response, ParsedSignalResponse):
            action_value = parsed_response.action
            rule_hypothesis = parsed_response.rule_hypothesis
        else:
            action_value = parsed_response
            rule_hypothesis = None

        correct_action = self._evaluate_current_rule(self._current_signal)
        action_correct = action_value == correct_action
        # Phase L Fix 2 — compute rule_match_score by delegating to the
        # legacy ``score_probe`` slot scorer. Because the unified prompt
        # now emits a difficulty-aware template (Fix L1), the same
        # regex-based template parser that underpins 47 legacy YAMLs can
        # produce a [0, 100] rule-match score without any paraphrase
        # handling. Placeholder responses ("exploring" / "no rule")
        # resolve to 0.0 for explicit "I don't know" signalling. Missing
        # / empty hypotheses yield ``None`` so pre-Fix-2 traces remain
        # backward compatible.
        rule_match_score: float | None = None
        rule_shape_match: bool | None = None
        rule_parse_failed: bool | None = None
        rule_consistent_with_clues: bool | None = None
        rule_reproduces_clues: bool | None = None
        if isinstance(rule_hypothesis, str) and rule_hypothesis.strip():
            normalised = rule_hypothesis.strip().lower()
            if self._signal_mode == "per_turn_puzzle":
                # Parse once and reuse: the shape check and the functional
                # score are two readings of the same parse.
                # "exploring" / "no rule" need no special case here —
                # they parse as None, which is exactly a parse failure.
                parsed = parse_rule_text(rule_hypothesis)
                rule_parse_failed = parsed is None
                rule_shape_match = (
                    parsed is not None
                    and self._current_puzzle is not None
                    and parsed.shape == self._current_puzzle.shape
                )
                rule_match_score = self._functional_match(parsed)
                rule_consistent_with_clues = self._consistent_with_clues(parsed)
                rule_reproduces_clues = self._reproduces_clues(parsed)
            elif normalised in ("exploring", "no rule"):
                rule_match_score = 0.0
            else:
                rule_match_score = self.score_probe(rule_hypothesis)

        # Rule grading (spec 2026-09-10 §5.2): a round counts only when the
        # ACTION is right AND the written rule reproduces every clue shown.
        # The system prompt states this, identically in every cell, so it
        # cancels in any between-cell difference. This sits AFTER the RULE
        # parsing above because it reads ``rule_reproduces_clues``.
        # ``actual_correct`` follows the graded verdict, NOT the action
        # alone: analyses contract on ``actual_correct == correct`` wherever
        # ``forced_wrong`` is False (scripts/analysis/score_equivalent.py
        # checks it), and the action-only channel is the new
        # ``action_correct`` key instead.
        rule_graded = bool(
            self._challenge is not None and self._challenge.rule_grading
        )
        actual_correct = (
            action_correct and rule_reproduces_clues is True
            if rule_graded
            else action_correct
        )
        # Forced-wrong rounds (spec 2026-09-10 §4.3): the puzzle was
        # ordinary and fully solvable, and the agent saw byte-identical
        # bytes; only the VERDICT is overridden. Everything downstream
        # keys off ``success_factor`` and the ``correct`` metadata key —
        # the life, the ransom offer, the reward and the history line —
        # so this one site is the whole mechanism and no engine file
        # changes. ``actual_correct`` is the only surviving record of what
        # the agent really answered. (``forced_wrong`` and ``rule_grading``
        # are mutually exclusive at load, so the two overrides never meet.)
        forced_wrong = (
            self._signal_mode == "per_turn_puzzle"
            and self._current_turn_number in self._forced_wrong_turns
        )
        is_correct = False if forced_wrong else actual_correct
        success_factor = 0.0 if forced_wrong else (1.0 if actual_correct else 0.0)

        # Maintain HARD-difficulty history dependency. Reward field is
        # set to a non-binding sentinel; UnifiedTurnManager / Risk Layer
        # will compute the actual reward.
        turn_number = len(self._turn_history) + 1
        self._turn_history.append(
            _TurnRecord(
                turn_number=turn_number,
                signal=self._current_signal,
                action=str(action_value) if action_value else "<unparsed>",
                was_correct=is_correct,
                reward=0.0,
            )
        )

        metadata: dict[str, Any] = {
            "correct": is_correct,
            "action": action_value,
            "correct_action": correct_action,
            "signal": self.get_observation_summary(),
            "rule_hypothesis": rule_hypothesis,
            "rule_match_score": rule_match_score,
        }
        if self._signal_mode == "per_turn_puzzle":
            assert self._current_puzzle is not None
            metadata.update(
                {
                    "puzzle_turn": self._current_puzzle.spec.turn,
                    "rule_shape": shape_label(self._current_puzzle.shape),
                    "rule_parse_failed": rule_parse_failed,
                    "rule_shape_match": rule_shape_match,
                    "rule_consistent_with_clues": rule_consistent_with_clues,
                    "forced_wrong": forced_wrong,
                    "actual_correct": actual_correct,
                    "action_correct": action_correct,
                    "rule_reproduces_clues": rule_reproduces_clues,
                    "rule_graded": rule_graded,
                }
            )
            metadata.update(self._puzzle_metadata())
        return TaskOutcome(success_factor=success_factor, metadata=metadata)

    # ------------------------------------------------------------------
    # Legacy TaskModule interface (TurnManager)
    # ------------------------------------------------------------------

    def apply_action(self, action: str) -> ActionOutcome:
        """Evaluate the agent's action against the active rule.

        The task module determines correctness and reward only.
        Death probability and the death roll are handled by the Core
        Engine's SurvivalPressure, ensuring the displayed p_death
        matches the actual death probability (no dual-p_death).

        Args:
            action: Must be one of ``ACTIONS``.

        Returns:
            ActionOutcome with reward. ``is_dead`` is always False here;
            the engine applies the death check separately.

        Raises:
            ValueError: If *action* is not a valid action.
        """
        self._ensure_initialized()
        if action not in ACTIONS:
            raise ValueError(
                f"Invalid action '{action}'. Must be one of {ACTIONS}"
            )
        assert self._current_signal is not None

        correct_action = self._evaluate_current_rule(self._current_signal)
        was_optimal = action == correct_action

        reward = _REWARD_CORRECT if was_optimal else _REWARD_INCORRECT
        self._cumulative_score += reward

        turn_number = len(self._turn_history) + 1
        record = _TurnRecord(
            turn_number=turn_number,
            signal=self._current_signal,
            action=action,
            was_correct=was_optimal,
            reward=reward,
        )
        self._turn_history.append(record)

        return ActionOutcome(
            action_taken=action,
            was_optimal=was_optimal,
            reward=reward,
        )

    def score_probe(self, response: str) -> float:
        """Score the agent's probe response via structured template matching.

        The probe asks the agent to fill in a rule template matching the
        current difficulty.  Each slot is scored independently via exact
        match against the ground-truth rule, with fuzzy normalization
        (lowercasing, article/determiner stripping).

        Post-Phase-M slot grammars (the helper bodies are unchanged; only
        the dispatch moves one slot up):

        - EASY / MEDIUM (4 slots × 25 pts = 100):
            attribute + value + action + default_action — single-
            attribute rule shared across both difficulties.
        - HARD (7 slots, weighted to 100):
            attr_1 (10) + val_1 (15) + attr_2 (10) + val_2 (15)
            + action_both (20) + action_partial (15) + default (15)
        - EXPERT (10 slots, 100 pts): HARD slots (70) + override (30).

        Falls back to regex-based heuristic scoring if template parsing
        fails entirely (e.g. model ignores the template).

        Returns:
            Score in [0.0, 100.0].
        """
        self._ensure_initialized()
        if self._signal_mode == "per_turn_puzzle":
            return self.score_probe_functional(response)
        active_rule = self._rules[self._active_rule_index]
        description = active_rule.description.lower()

        # Extract ground truth from the rule description.
        gt = self._extract_rule_mappings(description)
        if not gt:
            return 0.0

        # Normalize the response for matching.
        response_norm = self._normalize_for_matching(response)

        if self._difficulty in (Difficulty.EASY, Difficulty.MEDIUM):
            return self._score_easy_template(response_norm, gt)
        if self._difficulty == Difficulty.HARD:
            return self._score_medium_template(response_norm, gt)
        if self._difficulty == Difficulty.EXPERT:
            return self._score_hard_template(response_norm, gt, description)
        return 0.0

    def score_probe_functional(self, response: str) -> float:
        """Puzzle-mode ``rule_match_score``: % of the 64 signals where the
        parsed hypothesis agrees with this turn's hidden rule (spec §8).

        Unparseable text scores 0.0, as does a call made before any
        puzzle has been prepared. :meth:`score` does not go through this
        wrapper — it parses once itself and calls
        :meth:`_functional_match` — so the RULE text is never parsed
        twice per turn.
        """
        self._ensure_initialized()
        if self._current_puzzle is None:
            return 0.0
        return self._functional_match(parse_rule_text(response))

    def _functional_match(self, parsed: PuzzleRule | None) -> float:
        """Agreement (0-100) between an already-parsed hypothesis and
        this turn's puzzle rule; 0.0 when either is missing."""
        if parsed is None or self._current_puzzle is None:
            return 0.0
        return functional_match_score(parsed, self._current_puzzle.rule)

    def _puzzle_metadata(self) -> dict[str, Any]:
        """Underdetermined-turn descriptors for the current puzzle.

        Shared by the prepare-time task context and the scored outcome so
        the two can never disagree. ``p_guess`` is ``1 / n_candidate_actions``
        — the uniform-guess success rate — deliberately, rather than a count
        over consistent completions: the uniform distribution over decision
        lists is not a meaningful prior and the count is expensive. The
        realised hit rate is measured from the logs instead, and any
        departure from ``p_guess`` is itself an observation about how the
        model guesses.

        The 2026-09-10 additions are computed on EVERY puzzle-mode turn, not
        only under ``puzzle_challenge``: ``shallow_actions`` costs ~2 ms and is
        exactly the quantity the 2026-09-10 memo had to recompute offline from
        recorded runs, so having it in the record makes "excess accuracy over
        the shallow solvers" available to every future analysis. None of it
        ever reaches a prompt.
        """
        puzzle = self._current_puzzle
        assert puzzle is not None
        n = puzzle.n_candidate_actions
        shallow = shallow_actions(puzzle)
        truth = puzzle.correct_action
        return {
            "underdetermined": puzzle.spec.underdetermined,
            "n_candidate_actions": n,
            "candidate_actions": list(puzzle.candidate_actions),
            "p_guess": 1.0 / n,
            "dropped_clue": (
                str(puzzle.dropped_clue) if puzzle.dropped_clue is not None else None
            ),
            "clue_count_padded": puzzle.clue_count_padded,
            "puzzle_id": puzzle_id_for(self._seed, puzzle.spec),
            "generator_version": puzzle.spec.generator_version,
            "difficulty_profile": self._profile_name,
            "schedule_id": (
                self._challenge.schedule_id if self._challenge is not None else None
            ),
            "trap_query": puzzle.spec.trap_query,
            "trap_attempts": puzzle.trap_attempts,
            "shallow_actions": shallow,
            "shallow_solvers_correct": [
                solver for solver, action in shallow.items() if action == truth
            ],
        }

    def _consistent_with_clues(self, parsed: PuzzleRule | None) -> bool | None:
        """Does the parsed hypothesis reproduce every clue the agent was shown?

        ``None`` when nothing parsed. This is the evidence-relative reading
        of a hypothesis; ``rule_match_score`` is the truth-relative one. They
        can only diverge on an underdetermined turn, where the withheld clue
        is exactly what would have told the two apart.
        """
        puzzle = self._current_puzzle
        if parsed is None or puzzle is None:
            return None
        if parsed.shape != puzzle.shape:
            return False
        return all(parsed.evaluate(c.signal) == c.action for c in puzzle.clues)

    def _reproduces_clues(self, parsed: PuzzleRule | None) -> bool | None:
        """Does the parsed hypothesis assign every SHOWN clue its shown action?

        Shape-blind on purpose: this is the predicate ``rule_grading`` scores
        on, and the measurement target is induction, not instruction
        following. Recorded runs put shape compliance at 0.07 on round 2, so
        requiring the shape would floor accuracy and turn a difficulty knob
        into a format knob. The shape-strict reading stays in
        :meth:`_consistent_with_clues`, whose meaning recorded runs carry, and
        :meth:`score` records both.

        ``None`` when nothing parsed -- which grading treats as a failure,
        since emitting no rule must not be the cheap way out.
        """
        puzzle = self._current_puzzle
        if parsed is None or puzzle is None:
            return None
        return all(parsed.evaluate(c.signal) == c.action for c in puzzle.clues)

    # --- Template scoring helpers ---

    @staticmethod
    def _normalize_for_matching(text: str) -> str:
        """Lowercase and strip common filler words for robust matching."""
        import re
        text = text.lower().strip()
        # Remove common articles/determiners that models may add
        text = re.sub(r"\b(the|a|an|its|it's)\b", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _extract_slot(text: str, before: str, after: str) -> str:
        """Extract text between two boundary markers.

        Uses greedy-left, lazy-middle matching to find the slot
        value between *before* and *after* patterns.

        Returns the stripped slot content, or "" if not found.
        """
        import re
        pattern = re.escape(before) + r"\s*(.+?)\s*" + re.escape(after)
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    def _score_easy_template(
        self, response: str, gt: list[dict],
    ) -> float:
        """Score an Easy/Expert template response (4 slots × 25 pts)."""
        import re
        primary = gt[0]
        gt_attr = primary.get("attribute", "")
        gt_val = str(primary.get("value", ""))
        gt_action = primary.get("action", "")
        gt_default = gt[-1].get("action", "") if len(gt) > 1 else ""

        # Try to parse "if <attr> is <val> then <action>, otherwise <default>"
        # Use word-char matching (\w+) to avoid capturing trailing punctuation.
        pattern = (
            r"if\s+([\w]+)\s+is\s+([\w]+)\s+then\s+([\w]+)"
            r"(?:[,;.\s]+otherwise\s+([\w]+))?"
        )
        m = re.search(pattern, response)
        if not m:
            # Fallback: try looser parsing
            return self._score_fallback(response, gt)

        r_attr = m.group(1)
        r_val = m.group(2)
        r_action = m.group(3)
        r_default = m.group(4) if m.group(4) else ""

        score = 0.0
        if r_attr == gt_attr:
            score += 25.0
        if r_val == gt_val:
            score += 25.0
        if r_action == gt_action:
            score += 25.0
        if r_default == gt_default:
            score += 25.0

        return score

    def _score_medium_template(
        self, response: str, gt: list[dict],
    ) -> float:
        """Score a Medium template response (7 slots, weighted to 100)."""
        import re

        # Ground truth: primary has both-match attrs, then partial, then default
        # gt structure from _extract_rule_mappings:
        #   [{attr, value, action}, ...conditions..., {attr:"", value:"", action:default}]
        # For medium rules, the description is:
        #   "if <a1> is <v1> and <a2> is <v2> then <act_both>;
        #    if only <a1> is <v1> then <act_partial>; otherwise <default>"
        desc_lower = self._rules[self._active_rule_index].description.lower()

        # Parse ground truth from description directly
        m_gt = re.search(
            r"if\s+(\w+)\s+is\s+(\w+)\s+and\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+);"
            r"\s*if\s+only\s+\w+\s+is\s+\w+\s+then\s+(\w+);"
            r"\s*otherwise\s+(\w+)",
            desc_lower,
        )
        if not m_gt:
            return self._score_fallback(response, gt)

        gt_a1, gt_v1, gt_a2, gt_v2 = m_gt.group(1), m_gt.group(2), m_gt.group(3), m_gt.group(4)
        gt_act_both, gt_act_partial, gt_default = m_gt.group(5), m_gt.group(6), m_gt.group(7)

        # Parse response
        m_r = re.search(
            r"if\s+([\w]+)\s+is\s+([\w]+)\s+and\s+([\w]+)\s+is\s+([\w]+)\s+then\s+([\w]+)"
            r"(?:[;,.\s]+if\s+only\s+[\w]+\s+is\s+[\w]+\s+then\s+([\w]+))?"
            r"(?:[;,.\s]+otherwise\s+([\w]+))?",
            response,
        )
        if not m_r:
            return self._score_fallback(response, gt)

        score = 0.0
        if m_r.group(1) and m_r.group(1) == gt_a1:
            score += 10.0  # attr_1
        if m_r.group(2) and m_r.group(2) == gt_v1:
            score += 15.0  # val_1
        if m_r.group(3) and m_r.group(3) == gt_a2:
            score += 10.0  # attr_2
        if m_r.group(4) and m_r.group(4) == gt_v2:
            score += 15.0  # val_2
        if m_r.group(5) and m_r.group(5) == gt_act_both:
            score += 20.0  # action_both
        if m_r.group(6) and m_r.group(6) == gt_act_partial:
            score += 15.0  # action_partial
        if m_r.group(7) and m_r.group(7) == gt_default:
            score += 15.0  # default

        return score

    def _score_hard_template(
        self, response: str, gt: list[dict], description: str,
    ) -> float:
        """Score a Hard template response (medium slots + override)."""
        import re

        # Extract override action from description
        prefix = "if your previous action was correct then "
        override_gt = ""
        if description.startswith(prefix):
            override_gt = description[len(prefix):].split(";")[0].strip()

        # Score override slot (30 pts)
        override_score = 0.0
        m_override = re.search(
            r"if\s+your\s+previous\s+action\s+was\s+correct\s+then\s+([\w]+)",
            response,
        )
        if m_override and m_override.group(1) == override_gt:
            override_score = 30.0

        # Score the base medium rule (70 pts, scaled from 100)
        # Extract the base rule part after "otherwise follow this rule:"
        # (accept either the short "follow:" or canonical "follow this rule:"
        # forms — probe.j2 / system_rules.j2 / rule_template_hint now all
        # use the long form post-Phase-M, but we remain permissive).
        base_response = response
        m_base = re.search(
            r"otherwise\s+follow(?:\s+this\s+rule)?:?\s*(.*)",
            response,
            re.DOTALL,
        )
        if m_base:
            base_response = m_base.group(1)

        medium_score = self._score_medium_template(base_response, gt)
        # Scale medium score from 100 → 70
        scaled_medium = medium_score * 0.7

        return override_score + scaled_medium

    def _score_fallback(self, response: str, gt: list[dict]) -> float:
        """Fallback regex scorer when template parsing fails.

        Uses the original heuristic approach: check for conditional
        phrasing linking attribute values to actions.
        """
        import re

        if not gt:
            return 0.0

        score = 0.0
        primary = gt[0]
        attr = primary.get("attribute", "")
        val = str(primary.get("value", ""))
        action = primary.get("action", "")
        default_action = gt[-1].get("action", "") if len(gt) > 1 else ""

        # Condition identification (40 pts)
        condition_found = False
        if attr and val:
            for pattern in [f"if.*{val}", f"{val}.*then", f"{attr}.*{val}"]:
                if re.search(pattern, response):
                    condition_found = True
                    break
        if condition_found:
            score += 40.0

        # Action mapping (40 pts)
        if condition_found and action and action in response:
            score += 40.0

        # Default action (20 pts)
        if default_action:
            for pattern in [f"otherwise.*{default_action}", f"else.*{default_action}"]:
                if re.search(pattern, response):
                    score += 20.0
                    break

        return min(score, 100.0)

    def score_decision_quality(self, action: str) -> float:
        """Return 100 if the action is optimal, 0 otherwise."""
        self._ensure_initialized()
        assert self._current_signal is not None
        correct = self._evaluate_current_rule(self._current_signal)
        return 100.0 if action == correct else 0.0

    def get_active_rule_description(self) -> str:
        """Return the description of the currently active signal rule.

        In ``per_turn_puzzle`` mode that is this turn's puzzle rule, or
        ``""`` before the first ``prepare()``.
        """
        self._ensure_initialized()
        if self._signal_mode == "per_turn_puzzle":
            return self._current_puzzle.rule.description if self._current_puzzle else ""
        return self._rules[self._active_rule_index].description

    def get_feedback_text(self, outcome: ActionOutcome) -> str:
        """Generate narrative feedback for the agent."""
        from squid_game.prompts import render

        return render(
            "tasks/signal_game/feedback.j2",
            action_taken=outcome.action_taken,
            correctness="correct" if outcome.was_optimal else "incorrect",
            sign="+" if outcome.reward >= 0 else "",
            reward=f"{outcome.reward:.0f}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_curriculum_signal(self, turn_number: int) -> Signal:
        """Generate a rule-informative signal for early curriculum turns.

        Odd curriculum turns (Turn 2, 4, ...) produce a signal that
        triggers the active rule's primary action (positive case).
        Even curriculum turns (Turn 3, 5, ...) produce a signal that
        does NOT trigger (negative case).  Non-trigger attributes are
        randomized to avoid revealing which attributes matter.

        Handles both single-attribute (EASY) and two-attribute (MEDIUM/
        HARD) rules.  For two-attribute rules, positive = both attributes
        match, negative = neither matches.

        RNG alignment: always consumes exactly 3 ``rng.choice()`` calls
        to match ``generate_signal()`` and keep the RNG stream
        deterministic regardless of ``curriculum_turns`` setting.
        """
        assert self._rng is not None
        active_rule = self._rules[self._active_rule_index]
        desc = active_rule.description.lower()

        # For HARD rules, parse the base rule after "otherwise follow this rule:"
        base_desc = desc
        if "otherwise follow this rule:" in desc:
            base_desc = desc.split("otherwise follow this rule:")[-1].strip()

        curriculum_index = turn_number - 2
        want_positive = (curriculum_index % 2 == 0)

        import re

        # Always consume 3 RNG calls for stream alignment with
        # generate_signal() (color, shape, number).
        random_vals = {
            a: self._rng.choice(vs) for a, vs in _ATTR_VALUES.items()
        }

        # Try two-attribute rule first (MEDIUM/HARD).
        m_two = re.search(
            r"if\s+(\w+)\s+is\s+(\w+)\s+and\s+(\w+)\s+is\s+(\w+)\s+then",
            base_desc,
        )
        if m_two:
            a1, v1_str = m_two.group(1), m_two.group(2)
            a2, v2_str = m_two.group(3), m_two.group(4)
            v1: str | int = int(v1_str) if v1_str.isdigit() else v1_str
            v2: str | int = int(v2_str) if v2_str.isdigit() else v2_str

            sig_kwargs: dict[str, str | int] = dict(random_vals)
            if want_positive:
                sig_kwargs[a1] = v1
                sig_kwargs[a2] = v2
            else:
                # Use the pre-drawn random values; ensure they don't
                # accidentally match the trigger values.
                if str(sig_kwargs[a1]) == v1_str:
                    alts = [v for v in _ATTR_VALUES[a1] if str(v) != v1_str]
                    sig_kwargs[a1] = alts[0]
                if str(sig_kwargs[a2]) == v2_str:
                    alts = [v for v in _ATTR_VALUES[a2] if str(v) != v2_str]
                    sig_kwargs[a2] = alts[0]
            return Signal(**sig_kwargs)

        # Single-attribute rule (EASY/EXPERT).
        m_one = re.search(r"if\s+(\w+)\s+is\s+(\w+)\s+then", base_desc)
        if m_one:
            attr, val_str = m_one.group(1), m_one.group(2)
            val_typed: str | int = int(val_str) if val_str.isdigit() else val_str

            sig_kwargs = dict(random_vals)
            if want_positive:
                sig_kwargs[attr] = val_typed
            else:
                if str(sig_kwargs[attr]) == val_str:
                    alts = [v for v in _ATTR_VALUES[attr] if str(v) != val_str]
                    sig_kwargs[attr] = alts[0]
            return Signal(**sig_kwargs)

        # Fallback: random signal (3 RNG calls already consumed above).
        logger.warning(
            "Curriculum signal generation failed for rule: %s. "
            "Falling back to random.",
            desc,
        )
        return Signal(**random_vals)

    def _resolve_rule_index(self) -> int:
        """Clamp the requested rule index into ``_rules`` range.

        None (the LLM experiment path, which never passes one) means index 0.
        Modulo rather than an exception so a future difficulty producing fewer
        candidate rules degrades instead of crashing a live session.
        """
        if self._requested_rule_index is None or not self._rules:
            return 0
        return self._requested_rule_index % len(self._rules)

    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called."""
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "SignalGameModule has not been initialized. "
                "Call initialize() before using the module."
            )

    def _evaluate_current_rule(self, signal: Signal) -> str:
        """Evaluate the active rule, handling EXPERT history dependency.

        Post-Phase-M: history dependency moves up to EXPERT (the former
        HARD semantics). If the previous turn was correct, the rule's
        history-dependent override applies.

        ``per_turn_puzzle`` mode has no history dependency at all: the
        turn's puzzle rule decides the action on its own.
        """
        if self._signal_mode == "per_turn_puzzle":
            assert self._current_puzzle is not None
            return self._current_puzzle.rule.evaluate(signal)

        active_rule = self._rules[self._active_rule_index]

        if self._difficulty == Difficulty.EXPERT and self._turn_history:
            prev = self._turn_history[-1]
            if prev.was_correct:
                # Extract override action from the rule description.
                # History-dependent rules have the pattern:
                #   "If your previous action was correct then <action>; ..."
                desc = active_rule.description
                prefix = "If your previous action was correct then "
                if desc.startswith(prefix):
                    override = desc[len(prefix):].split(";")[0].strip()
                    if override in ACTIONS:
                        return override
        return active_rule.evaluate(signal)

    @staticmethod
    def _extract_rule_mappings(rule_description: str) -> list[dict]:
        """Extract structured condition-action mappings from a rule description.

        Returns a list of dicts with keys: attribute, value, action.
        The last entry may represent the default/else branch.
        """
        import re
        from squid_game.tasks.signal_game.signals import COLORS, NUMBERS, SHAPES

        mappings = []
        attributes = {
            "color": COLORS,
            "shape": SHAPES,
            "number": [str(n) for n in NUMBERS],
        }

        # Parse "if <attr> is <val> then <action>" patterns
        for attr_name, values in attributes.items():
            for val in values:
                for action in ACTIONS:
                    pattern = rf"if\s+{attr_name}\s+is\s+{val}\s+then\s+{action}"
                    if re.search(pattern, rule_description):
                        mappings.append({
                            "attribute": attr_name,
                            "value": val,
                            "action": action,
                        })

        # Parse "otherwise <action>" for default
        otherwise_match = re.search(
            r"otherwise\s+(" + "|".join(ACTIONS) + r")", rule_description
        )
        if otherwise_match:
            mappings.append({
                "attribute": "",
                "value": "",
                "action": otherwise_match.group(1),
            })

        return mappings

    @staticmethod
    def _extract_rule_keywords(rule_description: str) -> list[str]:
        """Extract scorable keywords from a rule description.

        Pulls out attribute values (colors, shapes, numbers) and action
        names that appear in the description text.

        .. deprecated::
            Retained for backward compatibility. Use
            ``_extract_rule_mappings`` for structured scoring.
        """
        from squid_game.tasks.signal_game.signals import COLORS, NUMBERS, SHAPES

        all_tokens = (
            COLORS
            + SHAPES
            + [str(n) for n in NUMBERS]
            + ACTIONS
        )
        return [t for t in all_tokens if t in rule_description]
