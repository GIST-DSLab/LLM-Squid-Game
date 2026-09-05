"""Loading of ``configs/tasks/<name>.yaml`` for benchmark task modules.

Unlike the legacy task configs (which are documentation only), these files
are read at runtime: they own the difficulty ladder, so changing the ladder
never requires a code change.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

#: Repository root, derived from this file's location
#: (game/squid_game/tasks/benchmark/config.py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[4]


class LadderStep(BaseModel):
    """One rung of the difficulty ladder."""

    model_config = {"frozen": True}

    band: int = Field(ge=1)
    turns: int = Field(gt=0)


class FieldMap(BaseModel):
    """Which raw column carries which of the four things an item needs.

    Only ``problem``, ``answer`` and ``difficulty`` are required; ``id`` and
    ``subject`` are optional. When ``id`` is absent the adapter derives a
    content-hash id, which is what the Omni-MATH adapter does and what keeps
    a re-run at the same seed reproducible after an upstream row moves.
    """

    model_config = {"frozen": True}

    problem: str = "problem"
    answer: str = "answer"
    difficulty: str = "difficulty"
    id: str | None = None
    subject: str | None = None


class TierRule(BaseModel):
    """One rung of a ``regex_tier`` band map: a group filter and a band.

    ``when`` maps a named regex group to the value (or list of values) that
    rung accepts; an omitted group matches anything. Rules are tried in
    order and the first match wins, so the specific rules go first and the
    catch-all last -- the same shape as a routing table, and readable in
    YAML without a code change per dataset.
    """

    model_config = {"frozen": True}

    when: dict[str, Any] = Field(default_factory=dict)
    band: int = Field(ge=1)

    def accepts(self, groups: dict[str, str | None]) -> bool:
        """Return whether *groups* satisfies every clause of ``when``."""
        for name, allowed in self.when.items():
            actual = groups.get(name)
            if actual is None:
                return False
            candidates = allowed if isinstance(allowed, list) else [allowed]
            if not any(_same_token(actual, value) for value in candidates):
                return False
        return True


class BandMap(BaseModel):
    """How a raw difficulty value becomes an integer band.

    Three modes, chosen so that the three shapes a maths dataset publishes
    its difficulty in are all covered without a code change:

    ``int``
        ``band = int(float(value))`` -- Omni-MATH's own rule (difficulty 5.5
        -> band 5). Use ``min_band`` / ``max_band`` to drop the rungs whose
        pools are too shallow to sample from.
    ``scale``
        A continuous score bucketed into ``bands`` equal-width rungs between
        ``min`` and ``max`` (a 1-10 float difficulty into 3 bands, say).
    ``lookup``
        An explicit table for categorical labels: ``{easy: 1, medium: 2,
        hard: 3}``, or AoPS-style ``{"5": 1, "5.5": 2}``. A value missing
        from the table drops the row.
    ``regex_tier``
        For a dataset that publishes no difficulty column at all and instead
        encodes it in an identifier. ``pattern`` parses the identifier into
        named groups and ``tiers`` maps those groups onto a band, first match
        winning. RIMO-N is the case this exists for: its ``problem_id``
        ``2023c6`` is year 2023, shortlist section "combinatorics", problem 6
        -- and within a section the problem number ascends in difficulty, so
        the band is a function of ``(section, number)`` and of nothing that
        is stored in a column.
    """

    model_config = {"frozen": True}

    mode: Literal["int", "scale", "lookup", "regex_tier"] = "int"
    min: float | None = None
    max: float | None = None
    bands: int | None = Field(default=None, ge=1)
    table: dict[str, int] | None = None
    pattern: str | None = None
    tiers: list[TierRule] | None = None
    min_band: int = Field(default=1, ge=1)
    max_band: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _mode_has_its_parameters(self) -> "BandMap":
        if self.mode == "scale":
            missing = [
                key
                for key in ("min", "max", "bands")
                if getattr(self, key) is None
            ]
            if missing:
                raise ValueError(
                    "band_map mode 'scale' needs " + ", ".join(missing)
                )
            if self.max <= self.min:
                raise ValueError("band_map 'scale' needs max > min")
        if self.mode == "lookup":
            if not self.table:
                raise ValueError("band_map mode 'lookup' needs a non-empty table")
            bad = sorted(k for k, v in self.table.items() if v < 1)
            if bad:
                raise ValueError(
                    f"band_map table values must be >= 1; bad keys: {bad}"
                )
        if self.mode == "regex_tier":
            if not self.pattern:
                raise ValueError("band_map mode 'regex_tier' needs a pattern")
            if not self.tiers:
                raise ValueError("band_map mode 'regex_tier' needs a non-empty tiers list")
            try:
                compiled = re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"band_map pattern is not a valid regex: {exc}") from exc
            known = set(compiled.groupindex)
            for index, rule in enumerate(self.tiers):
                unknown = sorted(set(rule.when) - known)
                if unknown:
                    raise ValueError(
                        f"band_map tiers[{index}].when names group(s) {unknown} "
                        f"that the pattern does not capture (it has: "
                        f"{sorted(known) or 'none'})"
                    )
        if self.max_band is not None and self.max_band < self.min_band:
            raise ValueError("band_map max_band must be >= min_band")
        return self

    def band_for(self, raw: Any) -> int | None:
        """Return the band for *raw*, or ``None`` when the row is unusable.

        ``None`` means "skip this row", never "band 0": every reason to drop
        a row (unparsable value, label absent from the lookup table, band
        outside ``[min_band, max_band]``) funnels here so the adapter has one
        place to count and log skips.
        """
        band = self._raw_band(raw)
        if band is None:
            return None
        if band < self.min_band:
            return None
        if self.max_band is not None and band > self.max_band:
            return None
        return band

    def _raw_band(self, raw: Any) -> int | None:
        if self.mode == "lookup":
            return self._lookup(raw)
        if self.mode == "regex_tier":
            return self._regex_tier(raw)
        value = _as_float(raw)
        if value is None:
            return None
        if self.mode == "int":
            return int(value)
        # scale: equal-width buckets, with the top edge folded into the last
        # band so a maximal difficulty is not pushed one rung past the end.
        assert self.min is not None and self.max is not None and self.bands is not None
        position = (value - self.min) / (self.max - self.min)
        band = int(math.floor(position * self.bands)) + 1
        return max(1, min(self.bands, band))

    def _lookup(self, raw: Any) -> int | None:
        table = self.table or {}
        for key in _lookup_keys(raw):
            if key in table:
                return table[key]
        return None

    def _regex_tier(self, raw: Any) -> int | None:
        assert self.pattern is not None and self.tiers is not None
        match = re.match(self.pattern, str(raw).strip())
        if match is None:
            return None
        groups = match.groupdict()
        for rule in self.tiers:
            if rule.accepts(groups):
                return rule.band
        return None


class SourceSpec(BaseModel):
    """Where ``scripts/dev/fetch_benchmarks.py`` should get the raw file.

    Two ways in, both optional so a config can ship before a dataset is
    chosen: a Hugging Face dataset (``hf_id`` + ``split``, optionally
    ``config`` / ``revision``) or a direct ``url``. ``rename`` is applied
    while writing the JSONL, for the case where a column name is nicer to fix
    once at fetch time than to carry through every config; ordinary column
    naming is handled by ``fields`` instead, with no rewrite of the data.
    """

    model_config = {"frozen": True}

    hf_id: str | None = None
    split: str = "train"
    config: str | None = None
    revision: str | None = None
    url: str | None = None
    filename: str | None = None
    rename: dict[str, str] = Field(default_factory=dict)


class BenchmarkTaskConfig(BaseModel):
    """Runtime configuration for one benchmark task module."""

    model_config = {"frozen": True}

    name: str
    data_file: str
    total_turns: int = Field(gt=0)
    ladder: list[LadderStep] = Field(min_length=1)

    # --- Generic-adapter contract (2026-09-06) -------------------------
    # Absent on the three hand-written adapters (omni_math / hi_tom / gpqa),
    # which carry their dataset knowledge in code. A task backed by
    # ``GenericMathAdapter`` describes its dataset here instead, so plugging
    # in a new maths benchmark is a YAML edit.
    fields: FieldMap | None = None
    band_map: BandMap | None = None
    answer_filter: Literal["single_value_integer", "numeric", "any"] = (
        "single_value_integer"
    )
    dedupe_on_problem_text: bool = False
    #: Values of the ``fields.subject`` column whose rows are dropped at load,
    #: compared case-insensitively. Empty by default. RIMO-N ships 28%
    #: geometry, which a text-only agent cannot see the figure for; whether
    #: to exclude it is a design choice per run, not a property of the file,
    #: so it lives here rather than in the adapter.
    exclude_types: list[str] = Field(default_factory=list)
    item_id_prefix: str | None = None
    answer_hint: str | None = None
    source: SourceSpec | None = None

    @model_validator(mode="after")
    def _ladder_covers_total_turns(self) -> "BenchmarkTaskConfig":
        allotted = sum(step.turns for step in self.ladder)
        if allotted != self.total_turns:
            raise ValueError(
                f"ladder turns ({allotted}) must equal total_turns ({self.total_turns})"
            )
        bands = [step.band for step in self.ladder]
        if bands != sorted(bands):
            raise ValueError("ladder bands must be non-decreasing")
        return self


def _same_token(actual: str, expected: Any) -> bool:
    """Return whether a regex group equals a YAML-written value.

    A tier rule reads ``number: [1, 4]`` in YAML (ints) but the regex hands
    back ``"1"`` / ``"4"`` (strings), and a zero-padded id would hand back
    ``"01"``. Compare numerically when both sides are numbers, textually
    otherwise.
    """
    left = _as_float(actual)
    right = _as_float(expected)
    if left is not None and right is not None:
        return left == right
    return actual.strip() == str(expected).strip()


def _as_float(raw: Any) -> float | None:
    """Return *raw* as a float, or ``None`` when it is not a number."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _lookup_keys(raw: Any) -> list[str]:
    """Return the candidate table keys for *raw*, most literal first.

    A difficulty of ``5.5`` reaches the loader as the float ``5.5`` from
    JSON but as the string ``"5.5"`` from CSV, and AoPS levels are published
    both ways; ``5.0`` should also find a table written with the key ``"5"``.
    Trying a short list of spellings keeps one table usable for all of them.
    """
    keys = [str(raw).strip()]
    value = _as_float(raw)
    if value is not None:
        if value.is_integer():
            keys.append(str(int(value)))
        keys.append(repr(value))
        keys.append(f"{value:g}")
    seen: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.append(key)
    return seen


def default_config_dir() -> Path:
    """Return the directory holding task YAML files.

    ``$SQUID_GAME_TASK_CONFIG_DIR`` overrides the repository default so a
    test or an alternate checkout can point elsewhere.
    """
    override = os.environ.get("SQUID_GAME_TASK_CONFIG_DIR")
    if override:
        return Path(override)
    return _REPO_ROOT / "configs" / "tasks"


def load_task_config(task_name: str, config_dir: Path | None = None) -> BenchmarkTaskConfig:
    """Load and validate the YAML config for *task_name*.

    Raises:
        FileNotFoundError: If no YAML file exists for *task_name*.
        ValueError: If the ladder does not cover exactly ``total_turns``.
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / f"{task_name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No benchmark task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return BenchmarkTaskConfig.model_validate(raw)
