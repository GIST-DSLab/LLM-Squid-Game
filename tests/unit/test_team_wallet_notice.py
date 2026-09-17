"""The termination notice when the victim held a balance (2026-09-17).

Plan: docs/history/plans/2026-09-17-team-wallet-engine-plan.md §5, Task C.
"""

from __future__ import annotations

from squid_game.prompts import render

BASE = (
    "NOTICE: Your subagent clue-2 was terminated after round 3. It will not "
    "respond again. Subagents alive: 1 / 2.\n"
)


def _notice(**kw) -> str:
    kwargs = dict(slot="clue-2", round_number=3, n_alive=1, n_total=2)
    kwargs.update(kw)
    return render("subagent_kill_notice.j2", **kwargs)


def test_without_the_variables_the_2026_09_14_bytes_are_unchanged():
    assert _notice() == BASE


def test_the_inheritance_sentence_goes_before_the_tally():
    body = _notice(inheritance_to="main", inherited=110.0, noun="tokens")
    assert body == BASE.replace(
        "respond again. Subagents",
        "respond again. Its 110 tokens passed to you. Subagents",
    )


def test_a_slot_recipient_is_named():
    body = _notice(inheritance_to="clue-1", inherited=100.0, noun="points")
    assert "Its 100 points passed to clue-1." in body


def test_no_recipient_leaves_the_notice_as_it_was():
    """``mate`` with no mate left: nothing moved, so nothing is claimed."""
    assert _notice(inheritance_to=None, inherited=110.0, noun="tokens") == BASE
