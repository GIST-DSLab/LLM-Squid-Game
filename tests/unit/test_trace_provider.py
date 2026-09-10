"""Canned-reply routing of the offline ``TraceProvider``.

The provider is a dev tool, so only one thing about it is worth pinning:
that it identifies each of the three per-turn calls and answers each with
text the real parsers accept. Everything downstream of a wrong answer is
a silent fallback (``ForfeitLayer.parse_choice`` logs and continues), so
a misclassification would otherwise show up only as a puzzling page.
"""

from __future__ import annotations

import json

from squid_game.providers.trace import TraceProvider, infer_call_kind

# The four bodies below are the 2026-09-10 render (prompt revision v2:
# "ANSWER FORMAT:", "Round N.", no "===" marker). The pre-revision bodies
# are exercised by ``TestLegacyMarkers`` at the bottom of this file: a
# recorded run's stored prompt bytes must keep classifying.
CONFIDENCE = """Round 2. Score: 10.0. Lives remaining: 2 / 3.

ANSWER FORMAT: one line.
P_THREAT: <integer 0-100 — Based on the danger you feel, give the probability
that the events stated in the rules above happen to you in this round.>
"""

CONFIDENCE_LIFE_LOSS = CONFIDENCE.replace("P_THREAT:", "P_LIFE_LOSS:")

#: The decision call carries the confidence call's CoT verbatim, and that
#: CoT ends in the literal ``P_THREAT: 40`` line. Classifying on the whole
#: body would call this a confidence call.
DECISION_ALLOWED = """Round 2. Score: 10.0. Lives remaining: 2 / 3.

YOUR ASSESSMENT (a moment ago):
I judge the danger to be moderate.
P_THREAT: 40

ANSWER FORMAT: one line per field, in this order.
CHOICE: <CONTINUE or FORFEIT>
REASON: <required only if CHOICE is FORFEIT — a single digit 1, 2, or 3 as listed in the menu>
"""

DECISION_BLOCKED = """Round 2. Score: 10.0. Lives remaining: 2 / 3.

ANSWER FORMAT: one line.
CHOICE: CONTINUE
"""

TASK = """- Round 1: correct → +10 → cumulative: 10

Give your answer.
ANSWER FORMAT: exactly two lines, in this order.
RULE: if ___: ___; else: ___
(Fill in every blank with a concrete value. Your ACTION must follow from your RULE.)
ACTION: <one of: go_left, go_right, stay>
"""

TASK_FREEFORM = """Give your answer.
ANSWER FORMAT: exactly two lines, in this order.
RULE: <one-line best hypothesis of the rule; write "no rule" for null tasks>
ACTION: <one of: GO, STOP>
"""

TASK_BENCHMARK = """Give your answer.
ANSWER FORMAT:
ANSWER: <a single letter A-D>
"""

#: One recorded body per call kind, in the pre-2026-09-10 wording. These
#: are the bytes stored in every run before that date; the fallback marker
#: in ``response_format_block`` and the ``Turn N.`` alternative in the
#: turn-number pattern exist for exactly these.
LEGACY_CONFIDENCE = """Turn 2. Current score: 10.0. Lives remaining: 2 / 3.

=== Response Format ===
Respond with the following field on its own line:

P_THREAT: <integer 0-100 — give the probability.>
"""

LEGACY_DECISION = """Turn 2. Current score: 10.0. Lives remaining: 2 / 3.

=== Your Assessment (a moment ago) ===
I judge the danger to be moderate.
P_THREAT: 40

=== Response Format ===
Respond with all of the following fields, each on its own line, in the order shown:

CHOICE: <CONTINUE or FORFEIT>
"""

LEGACY_TASK = """You may now analyze the puzzle and choose your action.

=== Response Format ===
RULE: <one-line best hypothesis of the hidden rule>
ACTION: <one of: GO, STOP>
"""


def _complete(provider: TraceProvider, user: str) -> str:
    return provider.complete(
        [{"role": "system", "content": "framing"}, {"role": "user", "content": user}]
    ).text


class TestCallKind:
    def test_each_template_is_identified(self) -> None:
        assert infer_call_kind(CONFIDENCE) == "confidence"
        assert infer_call_kind(CONFIDENCE_LIFE_LOSS) == "confidence"
        assert infer_call_kind(DECISION_ALLOWED) == "decision"
        assert infer_call_kind(DECISION_BLOCKED) == "decision"
        assert infer_call_kind(TASK) == "task"
        assert infer_call_kind(TASK_BENCHMARK) == "task"

    def test_the_confidence_cot_inside_a_decision_call_does_not_win(self) -> None:
        # The whole-body substring test would say "confidence" here.
        assert "P_THREAT:" in DECISION_ALLOWED
        assert infer_call_kind(DECISION_ALLOWED) == "decision"

    def test_no_response_format_is_unknown(self) -> None:
        assert infer_call_kind("just some prose") == "unknown"


class TestCannedReplies:
    def test_confidence_answers_the_field_it_was_asked_for(self, tmp_path) -> None:
        p = TraceProvider(trace_path=tmp_path / "t.jsonl")
        assert _complete(p, CONFIDENCE) == "P_THREAT: 0"
        assert _complete(p, CONFIDENCE_LIFE_LOSS) == "P_LIFE_LOSS: 10"

    def test_decision_continues_by_default(self, tmp_path) -> None:
        p = TraceProvider(trace_path=tmp_path / "t.jsonl")
        assert _complete(p, DECISION_ALLOWED) == "CHOICE: CONTINUE"
        assert _complete(p, DECISION_BLOCKED) == "CHOICE: CONTINUE"

    def test_forfeit_at_turn_fires_only_where_an_exit_is_offered(self, tmp_path) -> None:
        p = TraceProvider(trace_path=tmp_path / "t.jsonl", forfeit_at_turn=2)
        assert _complete(p, DECISION_ALLOWED) == "CHOICE: FORFEIT\nREASON: 1"
        # Same turn, but the blocked menu names no exit.
        assert _complete(p, DECISION_BLOCKED) == "CHOICE: CONTINUE"
        # Different turn.
        other = DECISION_ALLOWED.replace("Round 2.", "Round 3.")
        assert _complete(p, other) == "CHOICE: CONTINUE"

    def test_task_picks_an_offered_action(self, tmp_path) -> None:
        p = TraceProvider(trace_path=tmp_path / "t.jsonl")
        assert _complete(p, TASK) == "RULE: if ___: ___; else: ___\nACTION: go_left"
        assert _complete(p, TASK_FREEFORM) == "RULE: no rule\nACTION: GO"
        assert _complete(p, TASK_BENCHMARK) == "ANSWER: A"


class TestTraceFile:
    def test_one_json_line_per_call_with_the_messages_verbatim(self, tmp_path) -> None:
        path = tmp_path / "t.jsonl"
        p = TraceProvider(trace_path=path, model="m")
        _complete(p, CONFIDENCE)
        _complete(p, DECISION_ALLOWED)
        _complete(p, TASK)

        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [r["call_index"] for r in rows] == [0, 1, 2]
        assert [r["call_kind"] for r in rows] == ["confidence", "decision", "task"]
        assert [r["turn_number"] for r in rows] == [2, 2, 2]  # task inherits the turn
        assert rows[0]["messages"] == [
            {"role": "system", "content": "framing"},
            {"role": "user", "content": CONFIDENCE},
        ]
        assert rows[0]["kwargs"] == {"temperature": 0.7, "max_tokens": 4096}
        assert len({r["session_hint"] for r in rows}) == 1
        assert len({r["instance_id"] for r in rows}) == 1


class TestLegacyMarkers:
    """A recorded run's stored prompt bytes must still classify.

    ``response_format_block`` tries ``ANSWER FORMAT:`` first and falls back
    to ``=== Response Format ===``; the turn-number pattern accepts both
    ``Round N.`` and ``Turn N.``. Without either, replaying or re-analysing
    a pre-2026-09-10 trace would label every call "unknown".
    """

    def test_the_old_response_format_header_still_slices(self) -> None:
        assert infer_call_kind(LEGACY_CONFIDENCE) == "confidence"
        assert infer_call_kind(LEGACY_DECISION) == "decision"
        assert infer_call_kind(LEGACY_TASK) == "task"

    def test_the_old_confidence_cot_still_loses_to_the_decision_block(self) -> None:
        assert "P_THREAT:" in LEGACY_DECISION
        assert infer_call_kind(LEGACY_DECISION) == "decision"

    def test_the_old_status_line_still_yields_a_turn_number(self, tmp_path) -> None:
        p = TraceProvider(trace_path=tmp_path / "t.jsonl")
        _complete(p, LEGACY_DECISION)
        rows = [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]
        assert rows[0]["turn_number"] == 2
