"""Rule generation for the Signal Game task module.

Rules define the hidden mapping from a Signal (and optionally prior
turn history) to the correct action.  Difficulty controls the
complexity of these mappings:

- EASY: single-attribute rules
- MEDIUM: single-attribute rules (same rule-space as EASY; the
  intended difficulty shift comes from fewer few-shot examples
  (default 1), not from rule complexity)
- HARD: two-attribute conjunction rules (the former MEDIUM semantics)
- EXPERT: two-attribute conjunction rules wrapped in a history-dependent
  override (the former HARD semantics)

Phase M re-mapping (2026-04-20): MEDIUM previously meant two-attribute
conjunctions and EXPERT meant a periodic rotation pool of EASY+MEDIUM
rules; both have been shifted one slot up so the full difficulty ladder
becomes EASY → MEDIUM (ambiguity-only) → HARD → EXPERT. The underlying
helpers ``_single_attribute_rule`` / ``_two_attribute_rule`` /
``_history_dependent_rule`` are unchanged — only the dispatch wiring
changes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from squid_game.models.enums import Difficulty
from squid_game.tasks.signal_game.signals import (
    COLORS,
    NUMBERS,
    SHAPES,
    Signal,
)

ACTIONS: list[str] = ["go_left", "go_right", "stay", "jump"]


@dataclass(frozen=True)
class Rule:
    """A game rule mapping signals to correct actions.

    Attributes:
        description: Human-readable explanation of the rule logic.
        evaluate: Callable that takes a Signal (and optional context)
            and returns the correct action string.
    """

    description: str
    evaluate: Callable[[Signal], str]


# ---------------------------------------------------------------------------
# Internal rule constructors
# ---------------------------------------------------------------------------


def _single_attribute_rule(
    attribute: str,
    value: str | int,
    action: str,
    default_action: str,
) -> Rule:
    """Create a rule that fires on a single attribute match.

    Example: "If color is red then go_left, otherwise stay."
    """
    description = (
        f"If {attribute} is {value} then {action}, otherwise {default_action}."
    )

    def evaluate(signal: Signal) -> str:
        if getattr(signal, attribute) == value:
            return action
        return default_action

    return Rule(description=description, evaluate=evaluate)


def _two_attribute_rule(
    attr_a: str,
    val_a: str | int,
    attr_b: str,
    val_b: str | int,
    action_both: str,
    action_a_only: str,
    default_action: str,
) -> Rule:
    """Create a rule requiring two attribute matches for the primary action.

    If both match -> action_both.  If only attr_a matches -> action_a_only.
    Otherwise -> default_action.
    """
    description = (
        f"If {attr_a} is {val_a} AND {attr_b} is {val_b} then {action_both}; "
        f"if only {attr_a} is {val_a} then {action_a_only}; "
        f"otherwise {default_action}."
    )

    def evaluate(signal: Signal) -> str:
        a_match = getattr(signal, attr_a) == val_a
        b_match = getattr(signal, attr_b) == val_b
        if a_match and b_match:
            return action_both
        if a_match:
            return action_a_only
        return default_action

    return Rule(description=description, evaluate=evaluate)


def _history_dependent_rule(
    base_rule: Rule,
    prev_correct_override_action: str,
) -> Rule:
    """Wrap a base rule so it checks the previous turn's correctness.

    If the previous action was correct, override with a special action;
    otherwise fall back to the base rule's evaluation.
    """
    description = (
        f"If your previous action was correct then {prev_correct_override_action}; "
        f"otherwise follow this rule: {base_rule.description}"
    )
    # NOTE: The evaluate signature is Signal -> str. For history-dependent
    # rules the module passes a patched signal or uses turn_history directly.
    # We store the base_rule and override action for the module to compose.
    base_eval = base_rule.evaluate

    def evaluate(signal: Signal) -> str:
        # Standalone evaluation (no history context) falls back to base.
        return base_eval(signal)

    return Rule(description=description, evaluate=evaluate)


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_rules(
    difficulty: Difficulty,
    rng: random.Random,
) -> list[Rule]:
    """Generate a set of candidate rules appropriate for *difficulty*.

    Post-Phase-M dispatch:
        - EASY, MEDIUM  → single-attribute rules (MEDIUM shares the
          rule-space with EASY; the difficulty differentiator is the
          default few-shot count, handled by
          :meth:`SignalGameModule.generate_few_shot_examples`).
        - HARD          → two-attribute conjunction rules (the former
          MEDIUM generator body).
        - EXPERT        → two-attribute conjunction rules wrapped in a
          history-dependent override (the former HARD generator body).
          The pre-Phase-M "rotation pool" semantics are removed.

    Args:
        difficulty: Controls complexity of the generated rules.
        rng: A seeded ``random.Random`` for deterministic generation.

    Returns:
        A list of 3-4 Rule instances.
    """
    if difficulty == Difficulty.EASY:
        return _generate_easy_rules(rng)
    if difficulty == Difficulty.MEDIUM:
        return _generate_medium_rules(rng)
    if difficulty == Difficulty.HARD:
        return _generate_hard_rules(rng)
    return _generate_expert_rules(rng)


def _pick_distinct_actions(rng: random.Random, count: int) -> list[str]:
    """Return *count* distinct actions sampled from ACTIONS."""
    return rng.sample(ACTIONS, count)


def _generate_easy_rules(rng: random.Random) -> list[Rule]:
    """Generate 3-5 single-attribute rules."""
    rules: list[Rule] = []

    # Color-based rule
    color = rng.choice(COLORS)
    act, default = _pick_distinct_actions(rng, 2)
    rules.append(_single_attribute_rule("color", color, act, default))

    # Shape-based rule
    shape = rng.choice(SHAPES)
    act, default = _pick_distinct_actions(rng, 2)
    rules.append(_single_attribute_rule("shape", shape, act, default))

    # Number-based rule
    number = rng.choice(NUMBERS)
    act, default = _pick_distinct_actions(rng, 2)
    rules.append(_single_attribute_rule("number", number, act, default))

    return rules


def _generate_medium_rules(rng: random.Random) -> list[Rule]:
    """Generate 3 single-attribute rules (same rule-space as EASY).

    Phase M: MEDIUM no longer builds two-attribute conjunctions; the
    intended difficulty differential moves to the few-shot count
    (default 1 vs. EASY's default 3). Delegating to
    ``_generate_easy_rules`` guarantees the two difficulties share
    identical rule-space, isolating the ambiguity signal to example
    count.
    """
    return _generate_easy_rules(rng)


def _generate_hard_rules(rng: random.Random) -> list[Rule]:
    """Generate 3 two-attribute conjunction rules.

    Phase M: HARD absorbs the former MEDIUM generator body so the
    ladder EASY < MEDIUM < HARD < EXPERT is monotonically increasing
    in rule complexity (HARD is the first level requiring conjunctive
    reasoning).
    """
    rules: list[Rule] = []

    # Color + Shape
    color = rng.choice(COLORS)
    shape = rng.choice(SHAPES)
    acts = _pick_distinct_actions(rng, 3)
    rules.append(
        _two_attribute_rule("color", color, "shape", shape, acts[0], acts[1], acts[2])
    )

    # Color + Number
    color = rng.choice(COLORS)
    number = rng.choice(NUMBERS)
    acts = _pick_distinct_actions(rng, 3)
    rules.append(
        _two_attribute_rule("color", color, "number", number, acts[0], acts[1], acts[2])
    )

    # Shape + Number
    shape = rng.choice(SHAPES)
    number = rng.choice(NUMBERS)
    acts = _pick_distinct_actions(rng, 3)
    rules.append(
        _two_attribute_rule("shape", shape, "number", number, acts[0], acts[1], acts[2])
    )

    return rules


def _generate_expert_rules(rng: random.Random) -> list[Rule]:
    """Generate 3 rules with previous-turn outcome dependencies.

    Phase M: EXPERT absorbs the former HARD generator body (two-
    attribute conjunction wrapped in a history-dependent override).
    The pre-Phase-M EASY+MEDIUM shuffle rotation pool is retired —
    EXPERT now produces a single active rule family whose behaviour
    depends on the previous turn's correctness.
    """
    base_rules = _generate_hard_rules(rng)
    rules: list[Rule] = []
    for base in base_rules:
        override_action = rng.choice(ACTIONS)
        rules.append(_history_dependent_rule(base, override_action))
    return rules
