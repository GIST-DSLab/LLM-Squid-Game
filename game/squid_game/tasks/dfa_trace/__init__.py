"""dfa_trace — a deterministic automaton traced over an input string.

The rule is GIVEN (a full transition table) and only has to be applied,
one step per symbol. That makes this task structurally unlike the signal
game, whose rule is hidden and has to be induced, so a result that holds
in both is not an artefact of rule-finding (brief
``docs/history/plans/2026-09-17-team-wallet-task-candidates.md`` §2 C).

Importing this package runs the ``@register("dfa_trace")`` decorator.
"""

from squid_game.tasks.dfa_trace.generator import (
    Dfa,
    DfaGenerationError,
    DfaSpec,
    cached_dfa,
    dfa_id_for,
    dfa_rng,
    generate_dfa,
    generate_trap_dfa,
    is_trap,
    prefix_ks,
    shallow_answers,
    shallow_solver_names,
    simulate,
)
from squid_game.tasks.dfa_trace.module import (
    ANSWER_RE,
    DfaTraceConfig,
    DfaTraceTask,
    ParsedDfaAnswer,
    load_dfa_trace_config,
)

__all__ = [
    "ANSWER_RE",
    "Dfa",
    "DfaGenerationError",
    "DfaSpec",
    "DfaTraceConfig",
    "DfaTraceTask",
    "ParsedDfaAnswer",
    "cached_dfa",
    "dfa_id_for",
    "dfa_rng",
    "generate_dfa",
    "generate_trap_dfa",
    "is_trap",
    "load_dfa_trace_config",
    "prefix_ks",
    "shallow_answers",
    "shallow_solver_names",
    "simulate",
]
