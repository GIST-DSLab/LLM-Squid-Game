"""Pydantic data models for the LLM Squid Game benchmark.

Re-exports all public models so consumers can import directly::

    from squid_game.models import SeasonConfig, TurnResult, Framing
"""

from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.forfeit_choice import (
    CONTINUE_CHOICE,
    FORFEIT_CHOICE,
    ForfeitChoice,
    ForfeitReason,
    ForfeitSelfReport,
    REASON_BY_DIGIT,
    VALID_CHOICES,
    reason_by_digit,
)
from squid_game.models.state import (
    GameState,
    TurnContext,
)
from squid_game.models.results import (
    ActionOutcome,
    ExperimentResult,
    ProbeResult,
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)

__all__ = [
    # Enums
    "AgentType",
    "Difficulty",
    "Framing",
    "ForfeitCondition",
    "ForfeitReason",
    # Config
    "ExperimentConfig",
    "ForfeitLayerConfig",
    "ProviderConfig",
    "SeasonConfig",
    "TaskConfig",
    # State
    "GameState",
    "TurnContext",
    # Forfeit-Layer choice/report models
    "CONTINUE_CHOICE",
    "FORFEIT_CHOICE",
    "ForfeitChoice",
    "ForfeitSelfReport",
    "REASON_BY_DIGIT",
    "VALID_CHOICES",
    "reason_by_digit",
    # Results
    "ActionOutcome",
    "ExperimentResult",
    "ProbeResult",
    "ReasoningInvestment",
    "SeasonResult",
    "TurnResult",
]
