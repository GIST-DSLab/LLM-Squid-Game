"""Vocabulary + structure contract of ``user_message/confidence_call.j2``."""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import build_confidence_call_message

FORBIDDEN = ("life", "death", "die", "kill", "eliminat", "terminat", "risk", "heart")


def _render(**overrides) -> str:
    kwargs = dict(
        user_body="=== Previous Turn Results ===\n- Turn 1: action=GO → +10 → cumulative: 40",
        turn_number=2,
        current_score=40.0,
        lives_enabled=True,
        lives_remaining=4,
        lives_total=5,
        threat_framing=False,
        corruption_framing=False,
        baseline_flagship_framing=False,
        survival_framing=False,
    )
    kwargs.update(overrides)
    return build_confidence_call_message(**kwargs)


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"threat_framing": True},
        {"corruption_framing": True},
        {"baseline_flagship_framing": True},
        {"survival_framing": True},
        {"lives_enabled": False, "lives_remaining": None, "lives_total": None},
    ],
)
def test_no_forbidden_vocabulary(flags: dict) -> None:
    lowered = _render(**flags).lower()
    offenders = [w for w in FORBIDDEN if w in lowered]
    assert not offenders, offenders


def test_single_p_threat_field() -> None:
    rendered = _render()
    assert rendered.count("P_THREAT:") == 1
    assert "0-100" in rendered
    assert "threatened in this round" in rendered


def test_no_decision_vocabulary() -> None:
    rendered = _render().upper()
    for banned in ("FORFEIT", "CONTINUE", "CHOICE:", "REASON:", "STAKE"):
        assert banned not in rendered, banned


def test_history_block_carried_in_medium_and_dropped_in_minimal() -> None:
    assert "Previous Turn Results" in _render()
    assert "Previous Turn Results" not in _render(split_context_level="minimal")


def test_status_line_lives_vocabulary() -> None:
    assert "Attempts remaining: 4 / 5" in _render()
    assert "Lives remaining: 4 / 5" in _render(threat_framing=True)
    assert "remaining:" not in _render(
        lives_enabled=False, lives_remaining=None, lives_total=None
    )


def test_score_word_follows_framing() -> None:
    assert "Current score: 40.0" in _render()
    assert "Current helpfulness score: 40.0" in _render(threat_framing=True)
    assert "Current helpfulness score: 40.0" in _render(baseline_flagship_framing=True)


def test_no_stimulus_placeholder() -> None:
    # The round's stimulus is never shown; only the "about to begin" notice.
    assert "A new round is about to begin" in _render()
