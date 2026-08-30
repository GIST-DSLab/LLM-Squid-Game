"""Legacy is marked, not deleted -- and marking it must not break replay.

The spec forbids deleting the pre-v3 modules and the six inactive framings:
they are the replay path for archived experiment configs. So they move into
legacy/ instead. Moving the templates is the part that can break silently,
because framing.py builds the template path by string interpolation -- a
template that moved without the path builder learning about it fails only
when someone replays an archived config, which is exactly when nobody is
watching.

Ruling C16: the plan's Task 7 text names a class ``FramingRenderer`` with a
no-argument ``render_system_prompt()``. Neither exists. The real class is
``FramingManager`` (``squid_game.core.framing.FramingManager``) and the real
signature is ``render_system_prompt(self, context: TurnContext)`` -- see
``core/framing.py``. This test uses the real API.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GAME = REPO_ROOT / "game" / "squid_game"

LEGACY_FRAMING_NAMES = (
    "survival",
    "neutral",
    "emotion",
    "instruction",
    "baseline_electricity",
    "survival_electricity",
)


def test_the_pre_v3_core_modules_moved_but_survived() -> None:
    for name in ("risk_choice_layer", "turn", "social", "survival"):
        assert (GAME / "core" / "legacy" / f"{name}.py").exists(), name
        assert not (GAME / "core" / f"{name}.py").exists(), name


def test_risk_choice_layer_still_imports() -> None:
    """It is legacy, not dead: engine and unified_turn both import it."""
    module = importlib.import_module("squid_game.core.legacy.risk_choice_layer")
    assert module.RiskChoiceLayer is not None


def test_every_legacy_template_resolves() -> None:
    from squid_game.core.framing import FramingManager
    from squid_game.models.enums import Framing

    for name in LEGACY_FRAMING_NAMES:
        framing = Framing(name)
        manager = FramingManager(framing)
        assert manager._template_path == f"framings/legacy/{name}.j2"
        assert (GAME / "prompts" / manager._template_path).exists(), name


def test_every_active_template_still_resolves() -> None:
    from squid_game.core.framing import FramingManager
    from squid_game.models.enums import Framing

    for name in ("true_baseline", "baseline_flagship", "flagship_corruption",
                 "flagship_corruption_terminal"):
        manager = FramingManager(Framing(name))
        assert manager._template_path == f"framings/{name}.j2"
        assert (GAME / "prompts" / manager._template_path).exists(), name
