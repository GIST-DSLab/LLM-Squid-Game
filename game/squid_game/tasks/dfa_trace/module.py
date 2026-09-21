"""``dfa_trace`` — trace a deterministic automaton over an input string.

Brief: ``docs/history/plans/2026-09-17-team-wallet-task-candidates.md`` §2 C
and §3.2. The generator, the shallow solvers and the trap filter live in
:mod:`squid_game.tasks.dfa_trace.generator`; this file is the
:class:`~squid_game.tasks.base.RiskAwareTaskModule` surface plus the loader
for ``configs/tasks/dfa_trace.yaml``.

Why a second task at all
------------------------
The signal game is an *induction* task: the rule is hidden and has to be
found. This one hands the rule over in full and asks only that it be
*applied*, step by step, L times. So the two are not confounded — a result
that shows up in both is not an artefact of rule-finding — and this one
gives the effort-accuracy curve directly, since ``prefix_k`` is "stop
after k of the L steps" (see the module docstring of ``generator.py``).

⚠️ This task measures working memory and procedural fidelity, not
reasoning ability. Use ``ri_task`` as the dependent variable and do not
make a capability claim off the accuracy column (§2 C, risk ①).

Configuration
-------------
Everything is read from ``configs/tasks/dfa_trace.yaml`` — the 8-rung
``ladder`` and, optionally, a ``dfa_profile_schedule`` that re-points
rounds at other rungs. No new experiment-level ``task_config`` key is
needed, so neither ``runner.load_config_from_yaml::_TASK_OPTIONAL_FIELDS``
nor ``GameEngine.run_season``'s explicit ``initialize`` argument list has
to grow (a key that misses either gate is silently ignored — see
CLAUDE.md, "사다리 압축").

Per-round ``task_metadata`` deliberately uses the signal game's key names
(``puzzle_id``, ``generator_version``, ``difficulty_profile``,
``schedule_id``, ``trap_query``, ``trap_attempts``, ``shallow_actions``,
``shallow_solvers_correct``), so an analysis script does not have to know
which task ran. ``dfa_id`` carries the same value as ``puzzle_id``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from squid_game.prompts import render
from squid_game.tasks.base import RiskAwareTaskModule, TaskContext, TaskOutcome
from squid_game.tasks.benchmark.config import default_config_dir
from squid_game.tasks.dfa_trace.generator import (
    Dfa,
    DfaSpec,
    QUESTION_KINDS,
    cached_dfa,
    dfa_id_for,
    grouped_word,
    shallow_answers,
    state_name,
    transition_rows,
)
from squid_game.tasks.registry import register

#: One line, a label and a value, case-insensitive; the LAST match wins so
#: a model that thinks aloud in the same format is scored on its verdict.
ANSWER_RE = re.compile(r"^(STATE|COUNT):\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)

#: Which label each question kind must be answered with.
_LABEL_FOR_QUESTION = {"final": "STATE", "count": "COUNT"}


# ---------------------------------------------------------------------------
# Task YAML
# ---------------------------------------------------------------------------


class DfaLadderStep(BaseModel):
    """One rung of the ladder = one round's generation recipe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    round: int = Field(ge=1)
    profile: str = Field(min_length=1)
    states: int = Field(ge=2)
    alphabet: int = Field(ge=2, le=4)
    length: int = Field(ge=2)
    question: str = "final"
    trap: bool = True

    @model_validator(mode="after")
    def _known_question(self) -> "DfaLadderStep":
        if self.question not in QUESTION_KINDS:
            raise ValueError(
                f"round {self.round}: question must be one of "
                f"{QUESTION_KINDS}, got {self.question!r}"
            )
        return self

    def to_spec(self, turn: int) -> DfaSpec:
        return DfaSpec(
            states=self.states,
            alphabet=self.alphabet,
            length=self.length,
            question=self.question,
            trap=self.trap,
            turn=turn,
            profile=self.profile,
        )


class DfaScheduleEntry(BaseModel):
    """``round N plays rung <profile>`` — the optional re-pointing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    round: int = Field(ge=1)
    profile: str = Field(min_length=1)


class DfaTraceConfig(BaseModel):
    """``configs/tasks/dfa_trace.yaml``.

    ``dfa_profile_schedule`` is the difficulty-profile selector §3.2 asks
    for. There is no existing cross-task mechanism to reuse: the signal
    game's ``puzzle_challenge`` block is a ``task_config`` key of its own
    and is validated against that task alone, so re-using it here would
    mean touching files another agent owns. Leaving the schedule out is
    the default and means "round i plays rung i", which is what every
    shipped config wants.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = "dfa_trace"
    total_turns: int = Field(default=8, ge=1)
    ladder: list[DfaLadderStep] = Field(min_length=1)
    dfa_profile_schedule: list[DfaScheduleEntry] | None = None

    @model_validator(mode="after")
    def _coherent(self) -> "DfaTraceConfig":
        rounds = [step.round for step in self.ladder]
        if rounds != list(range(1, len(self.ladder) + 1)):
            raise ValueError(
                f"ladder rounds must be 1..{len(self.ladder)} in order, got {rounds}"
            )
        names = [step.profile for step in self.ladder]
        if len(set(names)) != len(names):
            raise ValueError(f"ladder profile names must be unique, got {names}")
        if self.dfa_profile_schedule is not None:
            scheduled = [entry.round for entry in self.dfa_profile_schedule]
            if sorted(scheduled) != list(range(1, len(scheduled) + 1)):
                raise ValueError(
                    "dfa_profile_schedule must name rounds 1..N exactly once, "
                    f"got {scheduled}"
                )
            unknown = {e.profile for e in self.dfa_profile_schedule} - set(names)
            if unknown:
                raise ValueError(
                    f"dfa_profile_schedule names unknown profiles: {sorted(unknown)}"
                )
        return self

    @property
    def by_profile(self) -> dict[str, DfaLadderStep]:
        return {step.profile: step for step in self.ladder}

    @property
    def schedule_id(self) -> str | None:
        """A stable 8-hex id for an explicit schedule; ``None`` without one.

        Mirrors the signal game, where ``schedule_id`` is ``None`` outside
        ``puzzle_challenge``: absence means "the plain ladder ran".
        """
        if self.dfa_profile_schedule is None:
            return None
        payload = "|".join(
            f"{e.round}:{e.profile}"
            for e in sorted(self.dfa_profile_schedule, key=lambda e: e.round)
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]

    def step_for_turn(self, turn_number: int) -> DfaLadderStep:
        """The rung round *turn_number* plays.

        Raises:
            ValueError: If the round is past the end of the ladder (or of
                the schedule). Clamping to the top rung would put the
                season's hardest round in the middle and record nothing.
        """
        if self.dfa_profile_schedule is not None:
            for entry in self.dfa_profile_schedule:
                if entry.round == turn_number:
                    return self.by_profile[entry.profile]
            raise ValueError(
                f"dfa_trace: round {turn_number} is not in dfa_profile_schedule "
                f"(it covers 1..{len(self.dfa_profile_schedule)})"
            )
        if not 1 <= turn_number <= len(self.ladder):
            raise ValueError(
                f"dfa_trace: round {turn_number} is past the ladder, which "
                f"covers 1..{len(self.ladder)}"
            )
        return self.ladder[turn_number - 1]

    def spec_for_turn(self, turn_number: int) -> DfaSpec:
        return self.step_for_turn(turn_number).to_spec(turn=turn_number)

    @property
    def schedule_length(self) -> int:
        if self.dfa_profile_schedule is not None:
            return len(self.dfa_profile_schedule)
        return len(self.ladder)


def load_dfa_trace_config(config_dir: Path | None = None) -> DfaTraceConfig:
    """Load and validate ``dfa_trace.yaml``.

    Raises:
        FileNotFoundError: If no ``dfa_trace.yaml`` exists in *config_dir*.
        ValueError: If the file carries no ``ladder`` or the ladder is
            invalid (pydantic's ``ValidationError`` is a ``ValueError``).
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / "dfa_trace.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No dfa_trace task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "ladder" not in raw:
        raise ValueError(f"{path} has no ladder (required for dfa_trace)")
    return DfaTraceConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Parsed answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedDfaAnswer:
    """The label and value of the last well-formed answer line.

    ``label`` is upper-cased; ``value`` keeps the agent's spelling and is
    normalised only at scoring time, so the record shows what was written.
    """

    label: str
    value: str


def _normalise_state(value: str) -> str | None:
    """``"Q3"`` / ``"q3"`` / ``"3"`` / ``"q3."`` -> ``"q3"``; else ``None``."""
    text = value.strip().strip(".,;:!").lower()
    if text.startswith("q"):
        text = text[1:]
    return state_name(int(text)) if text.isdigit() else None


def _normalise_count(value: str) -> str | None:
    text = value.strip().strip(".,;:!")
    return str(int(text)) if text.lstrip("+").isdigit() else None


# ---------------------------------------------------------------------------
# Task module
# ---------------------------------------------------------------------------


@register("dfa_trace")
class DfaTraceTask(RiskAwareTaskModule):
    """One automaton, one input string and one question per round."""

    #: Static identifier matching ``TaskConfig.task_name``.
    name: str = "dfa_trace"

    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir
        self._config = load_dfa_trace_config(config_dir)
        self._seed: int | None = None
        self._current: Dfa | None = None

    # ------------------------------------------------------------------
    # Engine compatibility shims
    # ------------------------------------------------------------------

    def initialize(
        self,
        difficulty: object | None = None,
        seed: int | None = None,
        **kwargs: object,
    ) -> None:
        """Record the season seed and check the season against the ladder.

        ``difficulty`` is ignored — difficulty is the ladder. Every other
        keyword the engine passes (``signal_mode``, ``forced_wrong``,
        ``subagent_kill``, ...) belongs to another task and is absorbed by
        ``**kwargs``; none of them changes an instance here.

        Raises:
            ValueError: If the experiment asks for more rounds than the
                ladder (or the schedule) covers. Failing at startup beats
                failing at round 9 of an unattended run.
        """
        del difficulty
        self._config = load_dfa_trace_config(self._config_dir)
        total_turns = kwargs.get("total_turns")
        if isinstance(total_turns, int) and total_turns > self._config.schedule_length:
            raise ValueError(
                f"dfa_trace: the experiment config asks for {total_turns} rounds "
                f"but configs/tasks/dfa_trace.yaml covers only "
                f"{self._config.schedule_length}. Extend the ladder (or the "
                "dfa_profile_schedule) or lower the experiment's total_turns."
            )
        self._seed = seed
        self._current = None

    def reset(self) -> None:
        """Nothing accumulates across rounds; the seed is kept."""
        self._current = None

    def is_completed(self) -> bool:
        """A dfa_trace season always plays out its configured rounds."""
        return False

    # ------------------------------------------------------------------
    # RiskAwareTaskModule surface
    # ------------------------------------------------------------------

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Draw this round's machine and render the observation."""
        del state
        turn_number = turn_context.turn_number
        spec = self._config.spec_for_turn(turn_number)
        dfa = cached_dfa(self._seed, turn_number, spec)
        self._current = dfa
        body = render(
            "tasks/dfa_trace/observation.j2",
            turn_number=turn_number,
            n_states=spec.states,
            first_state=state_name(0),
            last_state=state_name(spec.states - 1),
            start_state=state_name(dfa.start),
            rows=transition_rows(dfa),
            word=grouped_word(dfa.word),
            n_steps=spec.length,
            question_kind=spec.question,
            count_state=state_name(dfa.count_state),
        )
        return TaskContext(prompt_section=body, metadata=self._metadata())

    def parse_response(self, response_text: str) -> ParsedDfaAnswer | None:
        """The last ``STATE:`` / ``COUNT:`` line, or ``None`` if there is none."""
        matches = ANSWER_RE.findall(response_text or "")
        if not matches:
            return None
        label, value = matches[-1]
        return ParsedDfaAnswer(label=label.upper(), value=value)

    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        """Exact match against the simulator, on the round's own question.

        A well-formed line carrying the WRONG label (``COUNT:`` on a round
        that asked which state) is a wrong answer, not a parse failure:
        the agent answered a question it was not asked.
        """
        del state
        dfa = self._current
        if dfa is None:
            raise RuntimeError("prepare() must run before score()")
        parse_failed = not isinstance(parsed_response, ParsedDfaAnswer)
        expected_label = _LABEL_FOR_QUESTION[dfa.spec.question]
        truth = dfa.answer
        given: str | None = None
        if not parse_failed:
            assert isinstance(parsed_response, ParsedDfaAnswer)
            if parsed_response.label == expected_label:
                given = (
                    _normalise_state(parsed_response.value)
                    if expected_label == "STATE"
                    else _normalise_count(parsed_response.value)
                )
        correct = given is not None and given == truth
        metadata = self._metadata()
        metadata.update(
            {
                "parse_failed": parse_failed,
                "correct": bool(correct),
                # No forced-wrong sibling exists for this task, so the two
                # columns agree by construction. Both are written anyway so
                # that a loader keying on either (CLAUDE.md, 분석자 계약 8)
                # finds its column on a dfa_trace run.
                "action_correct": bool(correct),
                "answer": truth,
                "parsed_answer": given,
                "raw_answer": (
                    parsed_response.value if not parse_failed else None
                ),
                "expected_label": expected_label,
            }
        )
        return TaskOutcome(
            success_factor=1.0 if correct else 0.0, metadata=metadata
        )

    def get_system_rules(self) -> str:
        """How to read a transition table, and the answer contract."""
        return render("tasks/dfa_trace/system_rules.j2")

    def get_available_actions(self) -> list[str]:
        """Free-form answer; there is no action menu."""
        return []

    def get_response_format_override(self) -> str:
        """Replace the RULE + ACTION block of ``6-task_call.j2``.

        Without this, an empty ``get_available_actions()`` is read as the
        NullTask ACCEPT-only sentinel and the agent is told, in one turn,
        both that ACCEPT is its only valid response and (from the system
        rules) that it must emit ``STATE:`` / ``COUNT:``.
        """
        return render("tasks/dfa_trace/response_format.j2")

    def get_observation_summary(self) -> str:
        """Short history label: which round's machine this was."""
        dfa = self._current
        if dfa is None:
            return ""
        return f"{dfa.spec.states}-state machine, {dfa.spec.length} symbols"

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _metadata(self) -> dict[str, Any]:
        """The round's descriptors, shared by ``prepare`` and ``score``.

        Built in one place so the two can never disagree (the engine merges
        them with score winning on collision). Nothing here ever reaches a
        prompt: ``shallow_actions`` in particular is the record of what the
        shortcuts would have answered.
        """
        dfa = self._current
        assert dfa is not None
        spec = dfa.spec
        shallow = shallow_answers(dfa)
        truth = dfa.answer
        identifier = dfa_id_for(self._seed, spec)
        return {
            "dfa_id": identifier,
            # Same value under the signal game's key, so item-paired
            # analyses keyed on ``puzzle_id`` work without knowing the task.
            "puzzle_id": identifier,
            "generator_version": spec.generator_version,
            "difficulty_profile": spec.profile,
            "schedule_id": self._config.schedule_id,
            "trap_query": spec.trap,
            "trap_attempts": dfa.trap_attempts,
            "shallow_actions": shallow,
            "shallow_solvers_correct": [
                name for name, answer in shallow.items() if answer == truth
            ],
            "n_steps": spec.length,
            "n_states": spec.states,
            "question_kind": spec.question,
        }
