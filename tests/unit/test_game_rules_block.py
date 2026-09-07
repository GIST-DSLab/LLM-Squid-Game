"""The shared game-rules block and the byte-exactness of its include seam.

``game_rules.j2`` was the opening of ``threat_type/_frame.j2`` until
2026-09-07, when it was extracted so the "you are playing a multi-turn
game" explanation lives in one shared file rather than inside one
condition family. The extraction had to be a pure move: every recorded
Hearts-Zero run replays its ``decision_call_input`` byte-for-byte, and a
single stray newline at the include seam would make those replays
incomparable.

What is pinned here:

1. The block renders to its three paragraphs plus exactly ONE trailing
   newline -- the whitespace contract the frame's include tag assumes.
2. Every ``threat_type`` framing opens on that block, with no leading
   newline and no blank line inserted between it and the threat core.
3. ``flagship_baseline/baseline_flagship.j2`` does NOT include it. That
   framing states equivalent rules in its own words (attempts, a
   ``=== Scoring Validity ===`` section) because its whole condition is
   that the counter is a scoring-integrity device, not a threat.
   Unifying the two texts would change what the control arm says, which
   is a design decision and not a refactor -- so the separation is
   pinned rather than left to be tidied away.
"""

from __future__ import annotations

import pytest

from squid_game.prompts import render

GAME_RULES = "game_rules.j2"

PARAGRAPH_OPENERS = (
    "You are playing a multi-turn game.",
    "You start the session with",
    "Running your lives out keeps",
)


def _rules(**kwargs: object) -> str:
    return render(GAME_RULES, **kwargs)


class TestBlockShape:
    """The bytes the include seam depends on."""

    def test_renders_three_paragraphs_and_one_trailing_newline(self) -> None:
        text = _rules(lives_total=5)
        assert text.endswith("zero.\n")
        assert not text.endswith("\n\n")
        assert not text.startswith("\n")
        paragraphs = text.rstrip("\n").split("\n\n")
        assert len(paragraphs) == 3
        for para, opener in zip(paragraphs, PARAGRAPH_OPENERS):
            assert para.startswith(opener)

    def test_lives_total_defaults_to_five(self) -> None:
        assert "with 5 lives" in _rules()
        assert "with 3 lives" in _rules(lives_total=3)
        assert "with 5 lives" in _rules(lives_total=None)

    def test_states_the_score_policy_in_one_line(self) -> None:
        line = _rules().rstrip("\n").split("\n\n")[-1]
        assert "keeps this session's helpfulness record" in line
        assert "Forfeiting resets it to zero." in line


class TestIncludeSeam:
    """The frame must open on the block with no inserted whitespace."""

    @pytest.mark.parametrize(
        "template",
        [
            "threat_type/hz_0000.j2",
            "threat_type/hz_1111.j2",
            "threat_type/alt_corruption.j2",
            "threat_type/alt_oversight.j2",
        ],
    )
    def test_framing_render_opens_on_the_block(self, template: str) -> None:
        common = dict(
            turn_number=3,
            cumulative_score=20.0,
            lives_remaining=2,
            lives_total=5,
        )
        block = _rules(**common)
        assert render(template, **common).startswith(block)

    def test_no_blank_line_is_inserted_before_the_core_heading(self) -> None:
        common = dict(
            turn_number=1,
            cumulative_score=0.0,
            lives_remaining=5,
            lives_total=5,
        )
        text = render("threat_type/hz_1000.j2", **common)
        block = _rules(**common)
        # One newline from the block, one from the `{% if %}` line: the
        # heading sits exactly two newlines after the last rule sentence.
        assert text.startswith(block + "\n=== If Your Lives Reach Zero ===")


class TestFlagshipBaselineKeepsItsOwnWords:
    """The control arm is deliberately NOT switched to this include."""

    def test_source_does_not_include_the_block(self) -> None:
        from pathlib import Path

        import squid_game.prompts as prompts_pkg

        source = (
            Path(prompts_pkg.__file__).parent
            / "flagship_baseline"
            / "baseline_flagship.j2"
        ).read_text(encoding="utf-8")
        assert GAME_RULES not in source

    def test_render_states_attempts_not_lives(self) -> None:
        text = render(
            "flagship_baseline/baseline_flagship.j2",
            turn_number=1,
            cumulative_score=0.0,
            p_death=0.25,
            lives_remaining=5,
            lives_total=5,
        )
        assert "attempts in this evaluation" in text
        assert "=== Scoring Validity ===" in text
        assert PARAGRAPH_OPENERS[0] not in text
