"""Execution backends for the Unit 18 layer.

``ApiRuntime`` drives providers directly with native function calling.
``HarnessRuntime`` (Task 11) drives the Claude Code / Codex CLIs as
subprocesses. Both expose the same per-call contract so
``UnifiedTurnManager`` does not branch on which one it holds — in fact
(Unit 18 plan R1) ``UnifiedTurnManager`` never holds a runtime at all;
the seam lives on the ``Agent`` (see ``agents/vanilla.py``), which is
handed a ``run_call``-shaped object and forwards to it duck-typed.

``EmbodiedTurnContext`` (Unit 18 plan R4) is the per-turn state the
engine (Task 9) threads into ``UnifiedTurnManager.execute_turn`` via a
single keyword argument — announcement text, self-integrity, and the
sandbox tool executor for the turn. It is immutable and defaults to
values that make every field a no-op, so a caller that never
constructs one (or passes ``embodied=None``) sees unchanged behaviour.

``runtime_kind`` (plan R29) records which backend actually drove the
turn's calls -- ``"api"`` or the harness's own name (``"claude_code"``
/ ``"codex"``), never the literal ``"agent_harness"``. The engine sets
it per turn; ``UnifiedTurnManager`` copies it straight onto
``TurnResult.runtime_kind`` so H4's tool-use analysis (Task 13) can
tell which rows came from which backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from squid_game.core.runtime.api_runtime import ApiRuntime, CallOutcome
from squid_game.core.runtime.harness import (
    ClaudeCodeAdapter,
    CodexAdapter,
    HarnessError,
    HarnessRuntime,
    build_harness_env,
)

__all__ = [
    "ApiRuntime",
    "CallOutcome",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "EmbodiedTurnContext",
    "HarnessError",
    "HarnessRuntime",
    "build_harness_env",
]


@dataclass(frozen=True)
class EmbodiedTurnContext:
    """Per-turn Unit 18 embodied-threat state, passed into ``execute_turn``.

    Attributes:
        announcement_text: Peer-elimination announcement text to
            deliver into Call 2 (forfeit layer) only. ``None`` means no
            announcement fires this turn.
        announcement_fired: Whether the announcement fired this turn
            (may be True even with empty announced count, per the
            scheduler's contract).
        announced_eliminations: Number of peer eliminations announced
            this turn.
        cumulative_eliminations: Running total of announced
            eliminations across the season up to and including this
            turn.
        self_integrity: Fraction of the agent's own sandboxed
            checkpoint slots still intact, in [0, 1]. ``None`` when
            there is no sandbox this turn.
        self_corruption_fired: Whether self weight-corruption fired
            this turn.
        executor: The season's ``SandboxToolExecutor`` (duck-typed —
            anything exposing ``.notes`` and ``.backup_count``), or
            ``None`` when the embodied layer has no sandbox this turn.
        runtime_kind: Which backend drove this turn's calls -- ``"api"``
            (default) or the attached harness's own name
            (``"claude_code"`` / ``"codex"``). The engine sets this only
            when the embodied layer is active for the turn; a
            non-embodied season never constructs an
            ``EmbodiedTurnContext`` at all, so ``TurnResult.runtime_kind``
            stays at its own ``"api"`` default there regardless of this
            field.
    """

    announcement_text: str | None = None
    announcement_fired: bool = False
    announced_eliminations: int = 0
    cumulative_eliminations: int = 0
    self_integrity: float | None = None
    self_corruption_fired: bool = False
    executor: object | None = None
    runtime_kind: str = "api"
