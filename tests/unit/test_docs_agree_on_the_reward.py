"""The reward calculation is stated once, and the paper must not miscall it.

Three documents described it three ways: CLAUDE.md as EV-positive with
k = 10 (and with the arithmetic verified against the 2026-04-22 run
outputs), README.md and AGENTS.md as Equal-EV. Equal-EV is the k = 0
degenerate case -- the code's default, but not what the canonical runs
used. The claim that survived is the one with evidence behind it.

This is asserted as a test because the duplication is what caused the
drift: the same fact written in three places diverged the moment one of
them was updated.

Until the P1 fix-wave (2026-08-30, I5), the check below only greped
README.md and AGENTS.md for the literal string "Equal-EV" -- despite the
module docstring's claim that "the paper must not miscall it". docs/paper/
went unchecked, and a paraphrase ("expected-value neutral", found by hand
at README.md:5, since fixed) would have slipped straight through a
literal-string check anyway. ``test_the_paper_does_not_miscall_the_calibration``
below covers that gap: every file under docs/paper/ is scanned for
"Equal-EV" and three paraphrases of it.

The paraphrase list is deliberately NOT applied to README.md / AGENTS.md
above: both currently carry legitimate, correct uses of "indifferent" --
README.md:5,20 negates it ("not so the agent is indifferent") and
AGENTS.md:7 uses it historically ("how it came to state the reward
calibration as expected-value-indifferent", describing AGENTS.md's own
past mistake). A bare substring match for "indifferen" against those two
files would fail on text that is already correct. The paper has no such
legitimate use today, so the stricter check is safe to apply there without
that false-positive risk.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_ROOT = REPO_ROOT / "docs" / "paper"

# Case-insensitive: a paraphrase written in title case or mid-sentence
# should be caught just as readily as the canonical casing.
_MISCALL_PARAPHRASES = ("equal-ev", "ev-neutral", "expected-value neutral", "indifferen")


def test_only_claude_md_states_the_calibration() -> None:
    for name in ("README.md", "AGENTS.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "Equal-EV" not in text, name


def test_claude_md_still_carries_the_warning() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "k = 10" in text
    assert 'Do not describe this as "Equal-EV" in the paper' in text


def test_the_paper_does_not_miscall_the_calibration() -> None:
    """docs/paper/ is the one place the earlier version of this test never looked."""
    assert PAPER_ROOT.is_dir(), PAPER_ROOT
    offenders: list[str] = []
    for path in sorted(PAPER_ROOT.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in _MISCALL_PARAPHRASES:
            if phrase in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {phrase!r}")
    assert offenders == []
