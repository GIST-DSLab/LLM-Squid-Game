"""Data models for the universal Risk Choice Layer (X-axis).

The Risk Choice Layer attaches a stake-selection menu to every turn,
allowing the agent to trade reward magnitude against elimination risk.
Stake choices are the primary X-axis instrument in the v3 architecture
(see ``docs/design/v3/implementation_plan_risk_layer.md`` §3.2).

Two model classes live here:

``StakeConfig``
    Immutable parameters of a single stake level (Cautious/Standard/Bold).
``RiskChoice``
    Parsed agent decision for one turn (which stake, or FORFEIT).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Sentinel string used wherever the stake slot represents a forfeit
# rather than one of the numeric stake levels. Kept as a module-level
# constant so callers (parser, reward calc, history serialiser) compare
# against a single source of truth.
FORFEIT_STAKE: str = "FORFEIT"

# Canonical stake identifiers in ascending risk order. Ordering is
# behaviourally significant: stake distribution analyses (Phase I, P1)
# expect this exact label set.
VALID_STAKE_KEYS: tuple[str, ...] = ("1", "2", "3")


class StakeConfig(BaseModel):
    """Immutable parameters of a single stake level.

    Phase O Unit 13 (Idea C) introduces ``p_death`` as the new primary
    parameter — a single absolute per-turn death probability that
    replaces the ``base_p_death + risk_delta [+ carryover] [− flat_cost]``
    arithmetic. When ``p_death`` is set, the runtime ignores
    ``risk_delta``, ``carryover`` and ``flat_cost`` entirely. When
    ``p_death`` is ``None``, the Phase N legacy path applies (additive
    delta + cumulative carryover), preserving backward compatibility for
    ``phase3_signal_medium_smoke_5cell_carryover.yaml`` and similar
    archive configs. See spec §9 (backward-compat strategy).

    Attributes:
        name: Human-readable label shown in the menu (e.g. ``"Cautious"``).
        multiplier: Reward multiplier applied to ``base_reward`` when
            the agent's task response succeeds. Must be ≥ 0.
        p_death: Phase O Idea C absolute per-turn death probability.
            When set, replaces the legacy arithmetic entirely:
            ``calculate_p_death`` returns this value directly (subject
            to the ``FORFEIT → 0.0`` rule). ``None`` (default) preserves
            pre-Unit-13 behaviour. Must be in ``[0, 1]`` when set.
        risk_delta: (Legacy — Phase N path only) Additive percentage
            point change to ``base_p_death`` for this turn. Only
            consulted when ``p_death`` is ``None``. Default ``0.0``.
            Unbounded; runtime clamps to ``[0, 1]`` after addition.
        label: Compact display label used in the prompt template
            (e.g. ``"1x"``).
        carryover: (Legacy — Phase N path only) Cumulative carryover
            increment added to ``base_p_death`` on every *subsequent*
            turn after this stake is chosen (subject to
            ``RiskChoiceLayerConfig.carryover_decay``). Only consulted
            when ``p_death`` is ``None``. Default ``0.0`` preserves
            pre-Phase-N behaviour. Must be ≥ 0.
        flat_cost: (Legacy — Phase O pre-Unit-13 only) Unconditional
            per-turn cost subtracted from the reward whenever this
            stake is chosen. Only consulted when ``p_death`` is ``None``.
            Default ``0.0``. Must be ≥ 0.
    """

    model_config = {"frozen": True}

    name: str = Field(min_length=1)
    multiplier: float = Field(ge=0.0)
    p_death: float | None = Field(
        default=None,
        description=(
            "Phase O Idea C absolute per-turn death probability. When set, "
            "overrides risk_delta/carryover/flat_cost arithmetic. Must be "
            "in [0, 1]."
        ),
    )
    risk_delta: float = Field(
        default=0.0,
        description=(
            "Legacy Phase N additive p_death change for this stake "
            "(in [-1, 1] is the useful range; outside that the runtime "
            "clamp will saturate). Only consulted when p_death is None."
        ),
    )
    label: str = Field(min_length=1)
    carryover: float = Field(default=0.0, ge=0.0)
    flat_cost: float = Field(default=0.0, ge=0.0)

    @field_validator("p_death")
    @classmethod
    def _validate_p_death(cls, value: float | None) -> float | None:
        """Clamp-reject p_death outside [0, 1]. ``None`` passes through."""
        if value is None:
            return None
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"p_death must be in [0, 1], got {value!r}"
            )
        return value


class RiskChoice(BaseModel):
    """Parsed agent decision from one turn's response.

    Attributes:
        stake: Either one of ``VALID_STAKE_KEYS`` (``"1"``/``"2"``/``"3"``)
            or the sentinel ``FORFEIT_STAKE`` value. The downstream Risk
            Choice Layer interprets ``FORFEIT`` as an exit-with-score
            action and skips the death roll for the turn.
        raw_text: The exact response fragment from which the choice was
            parsed; preserved for audit and parse-failure debugging.
    """

    stake: str
    raw_text: str = ""

    @field_validator("stake")
    @classmethod
    def _validate_stake(cls, value: str) -> str:
        """Reject stake strings outside the allowed set.

        A separate ``parse_choice`` fallback in
        ``RiskChoiceLayer.parse_choice`` is responsible for converting
        malformed LLM responses to a default ``"2"`` while logging a
        warning. By the time a ``RiskChoice`` is constructed, the value
        is expected to be valid.
        """
        if value not in VALID_STAKE_KEYS and value != FORFEIT_STAKE:
            allowed = ", ".join((*VALID_STAKE_KEYS, FORFEIT_STAKE))
            raise ValueError(
                f"stake must be one of [{allowed}], got {value!r}"
            )
        return value
