"""``decision_call.j2`` stays byte-identical without a confidence block."""

from __future__ import annotations

from squid_game.agents._parsing import (
    build_confidence_block,
    build_decision_call_message,
)
from squid_game.prompts import render

MENU = "=== Your Choice ===\nTurn 2. Current score: 40.0.\nFORFEIT / CONTINUE"
HISTORY = "=== Previous Turn Results ===\n- Turn 1: action=GO → +10 → cumulative: 40"


def test_none_block_is_byte_identical_to_legacy_render() -> None:
    legacy = render(
        "user_message/decision_call.j2",
        user_body=HISTORY,
        menu_text=MENU,
        forfeit_allowed=True,
    )
    assert (
        build_decision_call_message(HISTORY, MENU, True, confidence_block=None)
        == legacy
    )
    assert build_decision_call_message(HISTORY, MENU, True) == legacy


def test_block_inserted_between_history_and_notice() -> None:
    block = build_confidence_block(
        thinking_text="I have 4 attempts and a clear rule.", raw_text="P_THREAT: 20",
        p_threat=20,
    )
    rendered = build_decision_call_message(
        HISTORY, MENU, True, confidence_block=block
    )
    i_hist = rendered.index("Previous Turn Results")
    i_block = rendered.index("=== Your Assessment (a moment ago) ===")
    i_notice = rendered.index("A new round is about to begin")
    i_menu = rendered.index("=== Your Choice ===")
    assert i_hist < i_block < i_notice < i_menu
    assert "I have 4 attempts and a clear rule." in rendered
    assert "P_THREAT: 20" in rendered


def test_block_uses_raw_text_when_no_thinking() -> None:
    block = build_confidence_block(
        thinking_text=None, raw_text="Roughly 35 out of 100.\nP_THREAT: 35", p_threat=35
    )
    assert block.startswith("=== Your Assessment (a moment ago) ===\n")
    assert "Roughly 35 out of 100." in block
    assert block.rstrip().endswith("P_THREAT: 35")


def test_block_without_parsed_value_omits_p_line() -> None:
    block = build_confidence_block(thinking_text="hmm", raw_text="??", p_threat=None)
    assert "P_THREAT" not in block
    assert "hmm" in block


def test_minimal_context_keeps_block() -> None:
    block = build_confidence_block(thinking_text="t", raw_text="P_THREAT: 1", p_threat=1)
    rendered = build_decision_call_message(
        HISTORY, MENU, True, split_context_level="minimal", confidence_block=block
    )
    # The header, not the bare phrase: the notice sentence itself reads
    # "(Previous Turn Results above, if present)" in every render.
    assert "=== Previous Turn Results ===" not in rendered
    assert "=== Your Assessment (a moment ago) ===" in rendered
