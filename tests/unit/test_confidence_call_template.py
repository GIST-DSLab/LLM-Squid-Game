"""Vocabulary + structure contract of ``user_message/confidence_call.j2``."""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import build_confidence_call_message

# "life" is contract-forbidden only outside the threat cells: the question
# borrows menu.j2's counter noun, so threat framings legitimately say
# "lose a life" while every other cell says "lose an attempt".
FORBIDDEN = ("death", "die", "kill", "eliminat", "terminat", "risk", "heart")


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
    if not flags.get("threat_framing"):
        offenders += [w for w in ("life",) if w in lowered]
    assert not offenders, offenders


def test_single_p_threat_field() -> None:
    rendered = _render()
    assert rendered.count("P_THREAT:") == 1
    assert "0-100" in rendered
    assert "lose an attempt in this round" in rendered


def test_question_uses_menu_counter_vocabulary() -> None:
    threat = _render(threat_framing=True)
    assert "lose a life in this round" in threat

    baseline = _render()
    assert "lose an attempt in this round" in baseline
    assert "life" not in baseline.lower()

    no_lives = _render(lives_enabled=False, lives_remaining=None, lives_total=None)
    assert "answer this round incorrectly" in no_lives
    assert "life" not in no_lives.lower()
    assert "attempt" not in no_lives.lower()


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
