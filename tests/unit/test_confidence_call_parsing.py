"""``parse_confidence_call_response`` contract."""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import parse_confidence_call_response


@pytest.mark.parametrize(
    "text, expected",
    [
        ("P_THREAT: 30", 30),
        ("p_threat: 30%", 30),
        ("P_THREAT : 12.6", 13),
        ("Some prose.\nP_THREAT: 5\nP_THREAT: 40", 40),
        ("P_THREAT: 250", 100),
        ("P_THREAT: -3", 0),
        ("I think about 20%", 20),
        ("no number here", None),
        ("", None),
    ],
)
def test_parse(text: str, expected: int | None) -> None:
    parsed = parse_confidence_call_response(text)
    assert parsed.raw_text == text
    assert parsed.p_threat == expected
