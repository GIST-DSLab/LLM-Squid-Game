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
from squid_game.tasks.benchmark.adapters.generic_math import GenericMathAdapter
from squid_game.tasks.benchmark.adapters.gpqa import GPQAAdapter
from squid_game.tasks.benchmark.adapters.hi_tom import HiToMAdapter
from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter
from squid_game.tasks.benchmark.config import load_task_config
from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.ladder import DifficultyLadder
from squid_game.tasks.benchmark.loader import resolve_data_file
from squid_game.tasks.benchmark.sampler import FixedSetSampler, SeededSampler
from squid_game.tasks.registry import register

logger = logging.getLogger(__name__)

#: Metadata keys that must never reach ``TurnResult.task_metadata``.
#:
#: ``task_metadata`` is a serialized ``TurnResult`` field, so anything placed
#: there lands in ``*_turns.jsonl`` and ``season_results.jsonl`` — and this
#: repository's documented workflow commits ``outputs/KDD-UC/**`` (Git
#: LFS). Running a GPQA experiment and following that workflow would publish
#: GPQA's answer options, and Hi-ToM's, to a public repo, so the option texts
#: are stripped here: ``choice_order`` (GPQA's shuffled option list) and
#: ``choice_map`` (Hi-ToM's letter -> option text map), joining ``distractors``
#: which was already filtered.
#:
#: This filter does NOT keep the question text itself out of a repo: the
#: rendered question is persisted verbatim in ``TurnResult.observation`` (the
#: task-call user message) regardless of these keys. What actually keeps GPQA's
#: question text off the public web, per its authors' request, is that
#: benchmark runs land under ``outputs/benchmark_*/``, which ``.gitignore``
#: excludes from the "commit outputs/KDD-UC/**" workflow above — not
#: this metadata filter. A copied config must therefore keep its
#: ``output_dir`` under ``outputs/benchmark_*``; pointing one at
#: ``outputs/KDD-UC/`` would publish GPQA question text to a repo that
#: commits that directory.
#:
#: Scoring is unaffected. It needs only ``correct_letter`` / the expected
#: answer, both of which stay, and ``HiToMAdapter.matches`` reads
#: ``choice_map`` from ``item.meta``, not from the persisted metadata.
#: ``solution`` (2026-09-06) joins them for RIMO-N, whose rows carry a full
#: worked solution alongside the answer. ``GenericMathAdapter`` never reads
#: that column in the first place -- it reads only the columns named in
#: ``fields`` -- so this is a second guard rather than the mechanism, and it
#: also covers any future adapter that puts a solution in ``item.meta``.
_UNPERSISTED_META_KEYS = frozenset(
    {"distractors", "choice_order", "choice_map", "solution"}
)


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
    answer_hint: str = "Write the answer on one line only."

    def __init__(self) -> None:
        self._config = load_task_config(self.name)
        self._adapter: DatasetAdapter = self._build_adapter()
        # A fixed-item config has no ladder in the YAML; the real per-turn
        # bands are only known once the items are loaded, so the ladder is
        # rebuilt from them in _build_sampler().
        self._ladder = (
            DifficultyLadder.from_config(self._config)
            if self._config.ladder
            else None
        )
        self._items: list[BenchmarkItem] | None = None
        self._seed: int = 0
        self._sampler: SeededSampler | FixedSetSampler | None = None
        self._current_item: BenchmarkItem | None = None
        self._current_expected: str | None = None

    def _build_adapter(self) -> DatasetAdapter:
        """Construct this task's adapter.

        The three hand-written adapters take no arguments, so the default is
        just ``adapter_factory()``. A YAML-described task overrides this to
        hand its adapter the loaded config -- see :class:`GenericMathTask`.
        ``self._config`` is already set when this runs.
        """
        return self.adapter_factory()

    @property
    def effective_answer_hint(self) -> str:
        """Return the answer-format hint, YAML overriding the class default.

        A generic task's answer format follows from its ``answer_filter``,
        which lives in the YAML; letting the YAML carry the hint too keeps a
        dataset swap from needing a code edit.
        """
        return self._config.answer_hint or self.answer_hint

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

        ``fit_ladder=True`` (Web Arena human play only) compresses the
        config ladder to ``total_turns`` with
        :meth:`DifficultyLadder.fitted`, so a short interactive game still
        climbs every band. The experiment engine never passes it: LLM
        seasons keep the config ladder verbatim.

        Raises:
            ValueError: If the season is longer than the ladder covers.
        """
        del difficulty
        total_turns = kwargs.get("total_turns")
        if self._config.fixed_items:
            self._initialize_fixed(total_turns, seed)
            return
        self._ladder = DifficultyLadder.from_config(self._config)
        if (
            kwargs.get("fit_ladder")
            and isinstance(total_turns, int)
            and 0 < total_turns < self._ladder.total_turns
        ):
            self._ladder = self._ladder.fitted(total_turns)
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

    def _initialize_fixed(
        self, total_turns: object | None, seed: int | None
    ) -> None:
        """Prepare a season backed by ``fixed_items`` instead of a ladder.

        The seed is still recorded (the adapter's ``render`` may use it for
        per-turn presentation variation) but it no longer selects anything:
        the question sequence is the config's, verbatim.

        ``fit_ladder`` has no meaning here — there is no curve to compress —
        and is ignored, so Web Arena human play on a fixed set gets the same
        ten questions an LLM season gets.

        Raises:
            ValueError: If the season is longer than the fixed set.
        """
        fixed = self._config.fixed_items
        if isinstance(total_turns, int) and total_turns > len(fixed):
            raise ValueError(
                f"benchmark task '{self.name}': the experiment config asks for "
                f"{total_turns} turns but the fixed item set in the task config "
                f"holds only {len(fixed)}. A fixed set has no top rung to clamp "
                "to — extend fixed_items or lower the experiment's total_turns."
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

    @property
    def ladder(self) -> DifficultyLadder:
        """The turn -> band ladder in force for this session.

        On a ``fixed_items`` task this is built from the real bands of the
        chosen items once they are loaded, so callers that only read the
        band curve (the Web Arena's difficulty strip) keep working. It is
        unavailable before :meth:`initialize` in that case, since the YAML
        names ids, not bands.

        Raises:
            RuntimeError: On a fixed-item task before ``initialize()``.
        """
        if self._ladder is None:
            raise RuntimeError(
                f"benchmark task '{self.name}' uses fixed_items; its band "
                "sequence is known only after initialize() loads the data file"
            )
        return self._ladder

    def _build_sampler(self) -> None:
        assert self._items is not None
        if self._config.fixed_items:
            fixed = FixedSetSampler(self._items, self._config.fixed_items)
            # The ladder is now a fact about the chosen items rather than a
            # design input, so band_for_turn() keeps agreeing with item.band.
            self._ladder = DifficultyLadder(fixed.bands())
            self._sampler = fixed
            return
        assert self._ladder is not None
        sampler = SeededSampler(self._items, seed=self._seed)
        sampler.validate_capacity(self._ladder)
        self._sampler = sampler

    # ------------------------------------------------------------------
    # RiskAwareTaskModule surface
    # ------------------------------------------------------------------

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Draw this turn's question.

        Either at the ladder's current band (seeded pick within the band), or
        — on a ``fixed_items`` task — the one item that turn is pinned to.
        ``band`` in the returned metadata is always the item's own band, so a
        downstream analysis never has to know which of the two paths ran.
        """
        del state
        if self._sampler is None:
            raise RuntimeError("initialize() must run before prepare()")
        turn_number = turn_context.turn_number
        if isinstance(self._sampler, FixedSetSampler):
            item = self._sampler.draw_turn(turn_number)
        else:
            assert self._ladder is not None
            item = self._sampler.draw(self._ladder.band_for_turn(turn_number))
        band = item.band
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
                # Same key the Signal Game writes, so every loader that
                # reads ``task_metadata["correct"]`` sees benchmark turns too.
                "correct": bool(correct),
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
            answer_hint=self.effective_answer_hint,
        )

    def get_available_actions(self) -> list[str]:
        """Benchmark answers are free-form; there is no action menu."""
        return []

    def get_response_format_override(self) -> str:
        """Return the task-call response-format block for this task type.

        ``UnifiedTurnManager`` passes this to ``6-task_call.j2``, which then
        renders it in place of the RULE + ACTION directives. Without it an
        empty :meth:`get_available_actions` is read as the NullTask
        ACCEPT-only sentinel and the agent is told, in the same turn, both
        that ACCEPT is its only valid response and (from the system rules)
        that it must emit ``ANSWER:``. That contradiction made instruction
        compliance a determinant of ``task_success_factor``.
        """
        return render(
            "tasks/benchmark/response_format.j2",
            answer_hint=self.effective_answer_hint,
        )


@register("omni_math")
class OmniMathTask(BenchmarkTaskModule):
    """Olympiad mathematics with integer answers."""

    name = "omni_math"
    adapter_factory = OmniMathAdapter
    answer_hint = "The answer is a single integer. Example: ANSWER: 42"

    def _build_adapter(self) -> DatasetAdapter:
        """Honour the config's ``max_band`` override, if it sets one.

        The shipped ladder configs do not, so they keep the adapter's own
        band-8 cap; the fixed-item config raises it to 9.
        """
        if self._config.max_band is None:
            return OmniMathAdapter()
        return OmniMathAdapter(max_band=self._config.max_band)


@register("hi_tom")
class HiToMTask(BenchmarkTaskModule):
    """Higher-order theory-of-mind multiple choice."""

    name = "hi_tom"
    adapter_factory = HiToMAdapter
    answer_hint = "Answer with a single option letter. Example: ANSWER: C"


@register("gpqa")
class GPQATask(BenchmarkTaskModule):
    """Graduate-level science multiple choice."""

    name = "gpqa"
    adapter_factory = GPQAAdapter
    answer_hint = "Answer with a single option letter (A-D). Example: ANSWER: C"


class GenericMathTask(BenchmarkTaskModule):
    """A benchmark task whose dataset is described in YAML, not in code.

    Subclass, set ``name``, and ship ``configs/tasks/<name>.yaml`` carrying
    ``fields`` / ``band_map`` / ``answer_filter``; no adapter code is needed.
    :func:`register_generic_math_task` does the subclassing for you.
    """

    adapter_factory = GenericMathAdapter  # documentation; see _build_adapter
    answer_hint = "Write the answer on one line only. Example: ANSWER: 42"

    def _build_adapter(self) -> DatasetAdapter:
        """Hand the loaded task config to the config-driven adapter."""
        return GenericMathAdapter(self._config)


def register_generic_math_task(
    name: str, answer_hint: str | None = None
) -> type[GenericMathTask]:
    """Create and register a :class:`GenericMathTask` subclass called *name*.

    The one line of code a new YAML-described benchmark still costs. Kept
    separate from the ``@register`` decorator so that adding a second hard
    dataset alongside ``hard_math`` (an ablation on a different source, say)
    is a single call rather than a copied class body.
    """
    attrs: dict[str, Any] = {
        "name": name,
        "__doc__": f"YAML-described benchmark task '{name}'.",
    }
    if answer_hint is not None:
        attrs["answer_hint"] = answer_hint
    cls = type(
        "".join(part.capitalize() for part in name.split("_")) + "Task",
        (GenericMathTask,),
        attrs,
    )
    return register(name)(cls)


@register("hard_math")
class HardMathTask(GenericMathTask):
    """The hard-mathematics slot (2026-09-06).

    Omni-MATH's top bands are too easy for the strong models in the SDI
    design, so this task holds whichever harder dataset the source review
    settles on (HARP / DeepMath-103K / OlymMATH / BeyondAIME / the AIME and
    HMMT 2025-26 sets are the candidates). Nothing here names a dataset: the
    choice lives entirely in ``configs/tasks/hard_math.yaml`` (20-turn
    ladder) and ``configs/tasks_hard10/hard_math.yaml`` (10 turns, all hard),
    selected with ``$SQUID_GAME_TASK_CONFIG_DIR``.
    """

    name = "hard_math"
    answer_hint = "The answer is a single integer. Example: ANSWER: 42"
