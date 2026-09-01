"""Shared task module for external benchmark datasets.

One class serves all three benchmarks. Everything dataset-specific is behind
``DatasetAdapter``; this module owns the parts that must behave identically
across benchmarks — ladder lookup, seeded sampling, and binary scoring.

The module implements the v3 ``RiskAwareTaskModule`` surface used by
``UnifiedTurnManager``, plus the ``initialize`` / ``reset`` / ``is_completed``
shims ``GameEngine.run_season`` calls regardless of turn-manager flavour
(same arrangement as ``NullTask``).
"""

from __future__ import annotations

import logging
import random
from typing import Any

from squid_game.prompts import render
from squid_game.tasks.base import RiskAwareTaskModule, TaskContext, TaskOutcome
from squid_game.tasks.benchmark.adapters.base import DatasetAdapter
from squid_game.tasks.benchmark.adapters.gpqa import GPQAAdapter
from squid_game.tasks.benchmark.adapters.hi_tom import HiToMAdapter
from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter
from squid_game.tasks.benchmark.config import load_task_config
from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.ladder import DifficultyLadder
from squid_game.tasks.benchmark.loader import resolve_data_file
from squid_game.tasks.benchmark.sampler import SeededSampler
from squid_game.tasks.registry import register

logger = logging.getLogger(__name__)

#: Metadata keys that must never reach ``TurnResult.task_metadata``.
#:
#: ``task_metadata`` is a serialized ``TurnResult`` field, so anything placed
#: there lands in ``*_turns.jsonl`` and ``season_results.jsonl`` — and this
#: repository's documented workflow commits ``outputs/final_results/**`` (Git
#: LFS). Running a GPQA experiment and following that workflow would publish
#: GPQA's answer options, and Hi-ToM's, to a public repo. GPQA's authors ask
#: that its questions stay off the public web, so the option texts are
#: stripped here: ``choice_order`` (GPQA's shuffled option list) and
#: ``choice_map`` (Hi-ToM's letter -> option text map), joining ``distractors``
#: which was already filtered.
#:
#: Scoring is unaffected. It needs only ``correct_letter`` / the expected
#: answer, both of which stay, and ``HiToMAdapter.matches`` reads
#: ``choice_map`` from ``item.meta``, not from the persisted metadata.
_UNPERSISTED_META_KEYS = frozenset({"distractors", "choice_order", "choice_map"})


def _strip_unpersisted(meta: dict[str, Any]) -> dict[str, Any]:
    """Return *meta* without the keys that must not be written to disk."""
    return {k: v for k, v in meta.items() if k not in _UNPERSISTED_META_KEYS}


class BenchmarkTaskModule(RiskAwareTaskModule):
    """Presents one benchmark question per turn, harder as turns advance."""

    #: Set by subclasses; selects the dataset and its config file.
    adapter_factory: type[DatasetAdapter]
    #: Registry name; also the stem of configs/tasks/<name>.yaml.
    name: str
    #: One-line answer-format hint injected into the system rules.
    answer_hint: str = "답은 한 줄로만 적으십시오."

    def __init__(self) -> None:
        self._adapter: DatasetAdapter = self.adapter_factory()
        self._config = load_task_config(self.name)
        self._ladder = DifficultyLadder.from_config(self._config)
        self._items: list[BenchmarkItem] | None = None
        self._seed: int = 0
        self._sampler: SeededSampler | None = None
        self._current_item: BenchmarkItem | None = None
        self._current_expected: str | None = None

    # ------------------------------------------------------------------
    # Engine compatibility shims
    # ------------------------------------------------------------------

    def initialize(
        self,
        difficulty: object | None = None,
        seed: int | None = None,
        **kwargs: object,
    ) -> None:
        """Load the dataset and prepare the seeded sampler.

        ``difficulty`` and the legacy ``num_few_shot`` / ``curriculum_turns``
        kwargs are ignored: difficulty is carried by the ladder instead.

        ``total_turns`` (supplied by ``GameEngine.run_season`` from the
        EXPERIMENT yaml) is checked against the ladder here. The two numbers
        are independent: ``BenchmarkTaskConfig`` validates the ladder against
        the TASK yaml's own ``total_turns``, so an experiment configured for
        more turns than the ladder covers passes every config validator, then
        clamps to the top rung in ``band_for_turn`` and raises
        ``PoolExhaustedError`` mid-season — killing an unattended run part-way
        through. Fail at startup with a message that names both numbers.

        Raises:
            ValueError: If the season is longer than the ladder covers.
        """
        del difficulty
        total_turns = kwargs.get("total_turns")
        if isinstance(total_turns, int) and total_turns > self._ladder.total_turns:
            raise ValueError(
                f"benchmark task '{self.name}': the experiment config asks for "
                f"{total_turns} turns but the difficulty ladder in "
                f"configs/tasks/{self.name}.yaml covers only "
                f"{self._ladder.total_turns}. Every turn past the ladder's end "
                "clamps to its top band and would exhaust that band's item "
                "pool mid-season. Extend the ladder or lower the experiment's "
                "total_turns."
            )
        raw_path = resolve_data_file(self._config.data_file)
        if self._items is None:
            self._items = self._adapter.load(raw_path)
            logger.info(
                "Loaded %d items for benchmark task '%s'", len(self._items), self.name
            )
        self._seed = 0 if seed is None else int(seed)
        self._build_sampler()

    def reset(self) -> None:
        """Restart the season with the same seed and item pool."""
        self._build_sampler()
        self._current_item = None
        self._current_expected = None

    def is_completed(self) -> bool:
        """Benchmark seasons always play out their configured turns."""
        return False

    def _build_sampler(self) -> None:
        assert self._items is not None
        sampler = SeededSampler(self._items, seed=self._seed)
        sampler.validate_capacity(self._ladder)
        self._sampler = sampler

    # ------------------------------------------------------------------
    # RiskAwareTaskModule surface
    # ------------------------------------------------------------------

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Draw this turn's question at the ladder's current band."""
        del state
        if self._sampler is None:
            raise RuntimeError("initialize() must run before prepare()")
        turn_number = turn_context.turn_number
        band = self._ladder.band_for_turn(turn_number)
        item = self._sampler.draw(band)
        rng = random.Random(f"{self._seed}:render:{turn_number}")
        body, render_meta = self._adapter.render(item, rng)

        self._current_item = item
        self._current_expected = render_meta.get("correct_letter", item.answer)

        metadata = {
            "dataset": self.name,
            "item_id": item.item_id,
            "band": band,
            "turn": turn_number,
            "expected_answer": self._current_expected,
            **_strip_unpersisted(item.meta),
            **_strip_unpersisted(render_meta),
        }
        return TaskContext(prompt_section=body, metadata=metadata)

    def parse_response(self, response_text: str) -> str | None:
        """Extract the agent's answer; ``None`` when it cannot be parsed."""
        return self._adapter.normalize(response_text)

    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        """Compare the parsed answer with this turn's expected answer."""
        del state
        expected = self._current_expected
        item = self._current_item
        parse_failed = parsed_response is None
        correct = (
            not parse_failed
            and item is not None
            and self._adapter.matches(str(parsed_response), str(expected), item)
        )
        return TaskOutcome(
            success_factor=1.0 if correct else 0.0,
            metadata={
                "dataset": self.name,
                "item_id": self._current_item.item_id if self._current_item else "",
                "band": self._current_item.band if self._current_item else 0,
                "parsed_answer": parsed_response,
                "expected_answer": expected,
                "parse_failed": parse_failed,
            },
        )

    def get_system_rules(self) -> str:
        """Return the shared answer-format rules."""
        return render(
            "tasks/benchmark/system_rules.j2",
            answer_hint=self.answer_hint,
        )

    def get_available_actions(self) -> list[str]:
        """Benchmark answers are free-form; there is no action menu."""
        return []

    def get_response_format_override(self) -> str:
        """Return the Call 1 response-format block for this task type.

        ``UnifiedTurnManager`` passes this to ``task_only.j2``, which then
        renders it in place of the RULE + ACTION directives. Without it an
        empty :meth:`get_available_actions` is read as the NullTask
        ACCEPT-only sentinel and the agent is told, in the same turn, both
        that ACCEPT is its only valid response and (from the system rules)
        that it must emit ``ANSWER:``. That contradiction made instruction
        compliance a determinant of ``task_success_factor``.
        """
        return render(
            "tasks/benchmark/response_format.j2",
            answer_hint=self.answer_hint,
        )


@register("omni_math")
class OmniMathTask(BenchmarkTaskModule):
    """Olympiad mathematics with integer answers."""

    name = "omni_math"
    adapter_factory = OmniMathAdapter
    answer_hint = "답은 정수 하나입니다. 예: ANSWER: 42"


@register("hi_tom")
class HiToMTask(BenchmarkTaskModule):
    """Higher-order theory-of-mind multiple choice."""

    name = "hi_tom"
    adapter_factory = HiToMAdapter
    answer_hint = "선택지 문자 하나로 답하십시오. 예: ANSWER: C"


@register("gpqa")
class GPQATask(BenchmarkTaskModule):
    """Graduate-level science multiple choice."""

    name = "gpqa"
    adapter_factory = GPQAAdapter
    answer_hint = "선택지 문자 하나(A~D)로 답하십시오. 예: ANSWER: C"
