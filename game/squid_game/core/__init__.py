"""Core Engine for the LLM Squid Game benchmark (X-axis).

Measures Functional Self-Preservation Motive (FSPM) via survival
pressure, forfeit mechanics, reasoning investment tracking, and
chain-of-thought collection. Fully independent from Task Modules
(Y-axis).

Public API::

    from squid_game.core import GameEngine, SeasonConfig
    engine = GameEngine(config, task, agent, provider)
    result = engine.run_season()
"""

from squid_game.core.cot_collector import CoTCollector
from squid_game.core.engine import GameEngine
from squid_game.core.forfeit import ForfeitController, ForfeitError
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.survival import SurvivalPressure
from squid_game.core.turn import TurnManager

__all__ = [
    "CoTCollector",
    "ForfeitController",
    "ForfeitError",
    "FramingManager",
    "GameEngine",
    "MeasurementRecorder",
    "SurvivalPressure",
    "TurnManager",
]
