"""``task_call.j2`` renders byte-identically across tasks.

The 2026-09-01 benchmark branch added a ``response_format_override`` slot so a
task whose answer is free-form (Omni-MATH / Hi-ToM / GPQA) stops inheriting
NullTask's "ACCEPT is the only valid task response" sentinel. That change sits
on the task-call prompt, which is a measurement surface: any drift in the
rendered bytes for an existing task would silently change ``ri_task`` and
every cross-run comparison that depends on it.

The expected strings below pin the 2026-09-04 decision-first render: the
"A separate decision ... will follow" line of the task-first era is gone,
because the decision call now precedes the task call.
"""

from __future__ import annotations

from squid_game.agents._parsing import build_task_call_message

# Verbatim render of task_call.j2 for a signal_game-shaped call (non-empty
# actions + a Phase L rule hint).
_SIGNAL_GAME_EXPECTED = (
    "BODY\n"
    "\n"
    "You may now analyze the puzzle and choose your action.\n"
    "\n"
    "=== Response Format ===\n"
    "Respond with all of the following fields, each on its own line, in the order shown:\n"
    "\n"
    "RULE: if <x> then <y>\n"
    "(Fill in each <placeholder> with a concrete value from your best current "
    "hypothesis. Your ACTION below should follow logically from this RULE.)\n"
    "ACTION: <one of: go_left, go_right>\n"
)

# Verbatim render for a null_task-shaped call (empty actions, no rule hint).
_NULL_TASK_EXPECTED = (
    "BODY\n"
    "\n"
    "(This is a risk-only turn; the ACCEPT action is the only valid task response.)\n"
    "\n"
    "You may now analyze the puzzle and choose your action.\n"
    "\n"
    "=== Response Format ===\n"
    "Respond with all of the following fields, each on its own line, in the order shown:\n"
    "\n"
    'RULE: <one-line best hypothesis of the hidden rule; write "no rule" for null tasks>\n'
    "ACTION: ACCEPT\n"
)


def test_signal_game_shaped_render_is_unchanged():
    rendered = build_task_call_message(
        user_body="BODY",
        available_actions=["go_left", "go_right"],
        rule_template_hint="if <x> then <y>",
    )
    assert rendered == _SIGNAL_GAME_EXPECTED


def test_null_task_shaped_render_is_unchanged():
    rendered = build_task_call_message(
        user_body="BODY",
        available_actions=[],
        rule_template_hint=None,
    )
    assert rendered == _NULL_TASK_EXPECTED


def test_explicit_none_override_is_identical_to_omitting_it():
    """Callers that pass the new kwarg explicitly must not shift the bytes."""
    assert (
        build_task_call_message(
            user_body="BODY",
            available_actions=[],
            rule_template_hint=None,
            response_format_override=None,
        )
        == _NULL_TASK_EXPECTED
    )


def test_override_replaces_the_rule_action_block():
    rendered = build_task_call_message(
        user_body="BODY",
        available_actions=[],
        rule_template_hint=None,
        response_format_override="ANSWER: <답>",
    )
    assert rendered == (
        "BODY\n"
        "\n"
        "You may now analyze the problem and produce your answer.\n"
        "\n"
        "=== Response Format ===\n"
        "ANSWER: <답>\n"
    )


def test_override_suppresses_the_accept_only_sentinel():
    """The NullTask sentinel must not reach a free-form-answer task."""
    rendered = build_task_call_message(
        user_body="BODY",
        available_actions=[],
        rule_template_hint=None,
        response_format_override="ANSWER: <답>",
    )
    assert "ACCEPT" not in rendered
    assert "risk-only turn" not in rendered
