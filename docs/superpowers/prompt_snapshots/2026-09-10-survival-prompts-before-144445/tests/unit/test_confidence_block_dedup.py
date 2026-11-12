"""``build_confidence_block`` states the parsed value exactly once.

Reasoning models routinely close their thinking block with the very line
the response format asked for (``P_THREAT: 15``). The pre-2026-09-06
build appended the parsed value unconditionally, so the decision call's
user body carried the number twice — 9 of 12 turns in the 2026-09-06
gemma4:cloud smoke, one of them three times. That is a free anchoring
nudge on the input H2 measures, and the SDI resampler inherits it from
``decision_call_input``.

The contract: the block's LAST line always states the parsed value, and
never states it twice in a row.
"""

from __future__ import annotations

import re

import pytest

from squid_game.agents._parsing import build_confidence_block

# A LINE whose content is the field, ignoring markdown decoration around it.
P_LINE = re.compile(
    r"^[\s*_`]*P_THREAT\s*:\s*-?\d", re.IGNORECASE | re.MULTILINE
)


def _count(block: str) -> int:
    return len(P_LINE.findall(block))


class TestNoDuplicateLine:
    def test_cot_ending_in_the_field_is_not_repeated(self) -> None:
        block = build_confidence_block(
            thinking_text="Estimating from turn 1.\nP_THREAT: 15",
            raw_text="P_THREAT: 15",
            p_threat=15,
        )
        assert _count(block) == 1
        assert block.rstrip().endswith("P_THREAT: 15")

    @pytest.mark.parametrize(
        "closing", ["P_THREAT: 15", "**P_THREAT: 15**", "`P_THREAT: 15`",
                    "P_THREAT:15", "P_THREAT: 15 %"]
    )
    def test_decorated_closings_are_recognised(self, closing: str) -> None:
        block = build_confidence_block(
            thinking_text=f"reasoning\n{closing}",
            raw_text=closing,
            p_threat=15,
        )
        assert _count(block) == 1

    def test_raw_text_fallback_is_deduped_too(self) -> None:
        """No thinking block → the visible answer is the body."""
        block = build_confidence_block(
            thinking_text=None, raw_text="P_THREAT: 40", p_threat=40
        )
        assert _count(block) == 1


class TestStillAppendsWhenNeeded:
    def test_cot_without_the_field_gets_the_line(self) -> None:
        block = build_confidence_block(
            thinking_text="Feels like a coin flip.",
            raw_text="Roughly half.",
            p_threat=50,
        )
        assert _count(block) == 1
        assert block.rstrip().endswith("P_THREAT: 50")

    def test_mid_paragraph_mention_still_gets_the_closing_line(self) -> None:
        """A model talking through candidates has not stated its answer.

        Only the CoT's final line is checked, so a ``P_THREAT`` buried
        mid-sentence does not suppress the block's closing statement.
        """
        block = build_confidence_block(
            thinking_text="Maybe P_THREAT: 10, or maybe higher.\nI will go higher.",
            raw_text="P_THREAT: 30",
            p_threat=30,
        )
        assert block.rstrip().endswith("P_THREAT: 30")
        assert "Maybe P_THREAT: 10" in block

    def test_differing_value_is_not_treated_as_a_duplicate(self) -> None:
        """Last-occurrence parsing can disagree with the final CoT line."""
        block = build_confidence_block(
            thinking_text="P_THREAT: 10",
            raw_text="P_THREAT: 80",
            p_threat=80,
        )
        assert block.rstrip().endswith("P_THREAT: 80")
        assert _count(block) == 2

    def test_no_parsed_value_omits_the_line(self) -> None:
        block = build_confidence_block(
            thinking_text="unsure", raw_text="??", p_threat=None
        )
        assert _count(block) == 0
