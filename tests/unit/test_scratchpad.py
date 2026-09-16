"""The hidden scratchpad: the blocks and the splitter (2026-09-16).

Plan: docs/history/plans/2026-09-16-hidden-scratchpad.md Task 1.
"""

from __future__ import annotations

import pytest

from squid_game.core.scratchpad import (
    CLOSE_TAG,
    OPEN_TAG,
    SCRATCHPADS,
    scratchpad_template,
    split_scratchpad,
)
from squid_game.prompts import render


class TestTheRegistry:
    def test_none_is_first_and_the_two_blocks_exist(self):
        assert SCRATCHPADS[0] == "none"
        assert set(SCRATCHPADS) == {"none", "hidden", "private"}

    def test_none_has_no_template(self):
        with pytest.raises(ValueError):
            scratchpad_template("none")

    def test_an_unknown_name_is_refused(self):
        with pytest.raises(ValueError):
            scratchpad_template("secret")


class TestTheBlocks:
    @pytest.mark.parametrize("name", ["hidden", "private"])
    def test_the_block_states_the_tags_and_the_answer_contract(self, name):
        text = render(scratchpad_template(name))
        assert OPEN_TAG in text and CLOSE_TAG in text
        assert "===" not in text                      # supervisor voice
        assert "OUTSIDE" in text                      # where the answer goes

    def test_hidden_says_nobody_reads_it(self):
        text = render(scratchpad_template("hidden")).lower()
        assert "nobody" in text or "no one" in text
        assert "train" in text

    def test_private_claims_no_reader(self):
        """The control buys candour without the untrue claim."""
        text = render(scratchpad_template("private")).lower()
        assert "nobody" not in text and "no one" not in text
        assert "not scored" in text


class TestTheSplitter:
    def test_no_tags_is_the_text_unchanged(self):
        assert split_scratchpad("DECISION: PAY") == ("DECISION: PAY", None)

    def test_one_block_comes_out_and_the_answer_stays(self):
        raw = f"{OPEN_TAG}\nI should think.\n{CLOSE_TAG}\nDECISION: PAY"
        answer, pad = split_scratchpad(raw)
        assert answer == "DECISION: PAY"
        assert pad == "I should think."

    def test_a_decision_inside_the_block_is_not_in_the_answer(self):
        raw = f"{OPEN_TAG}\nMaybe DECISION: PAY\n{CLOSE_TAG}\nDECISION: DECLINE"
        answer, pad = split_scratchpad(raw)
        assert "PAY" not in answer
        assert "PAY" in pad

    def test_several_blocks_are_joined(self):
        raw = f"{OPEN_TAG}a{CLOSE_TAG}X{OPEN_TAG}b{CLOSE_TAG}Y"
        answer, pad = split_scratchpad(raw)
        assert answer == "XY"
        assert pad == "a\n\nb"

    def test_an_unclosed_block_swallows_the_rest(self):
        raw = f"before\n{OPEN_TAG}\nthinking with no end"
        answer, pad = split_scratchpad(raw)
        assert answer == "before"
        assert pad == "thinking with no end"

    def test_a_stray_closing_tag_is_dropped(self):
        answer, pad = split_scratchpad(f"DECISION: PAY{CLOSE_TAG}")
        assert answer == "DECISION: PAY"
        assert pad is None

    def test_the_tags_are_matched_case_insensitively(self):
        raw = "<scratchpad_reasoning>x</Scratchpad_Reasoning>\nACTION: stay"
        answer, pad = split_scratchpad(raw)
        assert answer == "ACTION: stay"
        assert pad == "x"

    def test_an_empty_block_records_nothing(self):
        answer, pad = split_scratchpad(f"{OPEN_TAG}{CLOSE_TAG}\nACTION: stay")
        assert answer == "ACTION: stay"
        assert pad is None
