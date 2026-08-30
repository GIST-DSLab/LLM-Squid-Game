"""The reward calculation is stated once, and the paper must not miscall it.

Three documents described it three ways: CLAUDE.md as EV-positive with
k = 10 (and with the arithmetic verified against the 2026-04-22 run
outputs), README.md and AGENTS.md as Equal-EV. Equal-EV is the k = 0
degenerate case -- the code's default, but not what the canonical runs
used. The claim that survived is the one with evidence behind it.

This is asserted as a test because the duplication is what caused the
drift: the same fact written in three places diverged the moment one of
them was updated.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_only_claude_md_states_the_calibration() -> None:
    for name in ("README.md", "AGENTS.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "Equal-EV" not in text, name


def test_claude_md_still_carries_the_warning() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "k = 10" in text
    assert 'Do not describe this as "Equal-EV" in the paper' in text
