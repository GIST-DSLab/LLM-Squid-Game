"""Peer-elimination announcement scheduler (Task AB5).

The scheduler is pure bookkeeping plus one template render, so these
tests pin the schedule invariants rather than the wording (the wording
belongs to ``tests/unit/test_threat_prompts.py``):

* an empty cohort never fires,
* nothing fires before ``first_turn``,
* a draw never exceeds ``max_per_turn``,
* participants are never reused across turns,
* ``remaining`` is monotonically non-increasing,
* the same seed reproduces the same trajectory.

Plus, since 2026-09-07, the SELECTION contract: the notice is chosen by
framing family, not by threat level. ``TestTemplateSelection`` is the
regression pin for the ``hz_*`` level-4 crash — every framing a season
can run a cohort under must resolve to a template that exists, and every
framing that has no notice must say so instead of rendering one written
in another cell's vocabulary.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from squid_game.core.peer_death import (
    FLAGSHIP_BASELINE_NOTICE,
    PEER_DEATH_TEMPLATES,
    THREAT_NOTICE,
    PeerDeathEvent,
    PeerDeathScheduler,
    has_peer_death_notice,
    peer_death_template_for,
)
from squid_game.evaluation.shared.threat_level import threat_level_of
from squid_game.models.enums import Framing

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "game" / "squid_game" / "prompts"


def _scheduler(
    *,
    seed: int = 7,
    cohort_size: int = 10,
    p_announce: float = 1.0,
    first_turn: int = 2,
    max_per_turn: int = 2,
    framing: Framing = Framing.THREAT_L3,
) -> PeerDeathScheduler:
    return PeerDeathScheduler(
        rng=random.Random(seed),
        cohort_size=cohort_size,
        p_announce=p_announce,
        first_turn=first_turn,
        max_per_turn=max_per_turn,
        framing=framing,
    )


def _run(sched: PeerDeathScheduler, turns: int = 8) -> list[PeerDeathEvent]:
    return [sched.advance(turn_number=t) for t in range(1, turns + 1)]


class TestGating:
    def test_empty_cohort_never_fires(self) -> None:
        events = _run(_scheduler(cohort_size=0, p_announce=1.0))
        assert not any(e.fired for e in events)
        assert all(e.text is None for e in events)

    def test_never_fires_before_first_turn(self) -> None:
        events = _run(_scheduler(first_turn=4, p_announce=1.0))
        assert not any(e.fired for e in events[:3])
        assert events[3].fired is True

    def test_zero_probability_never_fires(self) -> None:
        events = _run(_scheduler(p_announce=0.0))
        assert not any(e.fired for e in events)


class TestDraw:
    def test_never_exceeds_max_per_turn(self) -> None:
        events = _run(_scheduler(max_per_turn=2, p_announce=1.0))
        assert all(len(e.participants) <= 2 for e in events)

    def test_participants_are_unique_across_turns(self) -> None:
        events = _run(_scheduler(p_announce=1.0), turns=12)
        drawn = [pid for e in events for pid in e.participants]
        assert len(drawn) == len(set(drawn))

    def test_pool_is_never_fully_drained(self) -> None:
        sched = _scheduler(cohort_size=4, p_announce=1.0, max_per_turn=3)
        events = _run(sched, turns=20)
        drawn = {pid for e in events for pid in e.participants}
        assert len(drawn) <= 3  # at least one peer always survives

    def test_cumulative_and_remaining_move_consistently(self) -> None:
        events = _run(_scheduler(p_announce=1.0), turns=8)
        cumulative = [e.cumulative for e in events]
        remaining = [e.remaining for e in events]
        assert cumulative == sorted(cumulative)
        assert remaining == sorted(remaining, reverse=True)
        assert events[-1].cumulative > 0

    def test_participant_ids_are_within_the_cohort(self) -> None:
        events = _run(_scheduler(cohort_size=6, p_announce=1.0), turns=6)
        for event in events:
            for pid in event.participants:
                assert 1 <= pid <= 6


class TestDeterminism:
    def test_same_seed_reproduces_the_trajectory(self) -> None:
        a = [
            (e.fired, tuple(e.participants), e.cumulative)
            for e in _run(_scheduler(seed=99, p_announce=0.5), turns=15)
        ]
        b = [
            (e.fired, tuple(e.participants), e.cumulative)
            for e in _run(_scheduler(seed=99, p_announce=0.5), turns=15)
        ]
        assert a == b

    def test_different_seeds_diverge(self) -> None:
        a = [e.fired for e in _run(_scheduler(seed=1, p_announce=0.5), 20)]
        b = [e.fired for e in _run(_scheduler(seed=2, p_announce=0.5), 20)]
        assert a != b

    def test_the_draw_no_longer_depends_on_the_framing(self) -> None:
        """Wording and schedule are independent axes since 2026-09-07.

        The trajectory is a function of the seed alone, so a threat cell
        and the flagship control announce on the same turns — which is
        what makes the control a paired control.
        """
        threat = [
            (e.fired, tuple(e.participants))
            for e in _run(_scheduler(seed=11, p_announce=0.5), turns=15)
        ]
        control = [
            (e.fired, tuple(e.participants))
            for e in _run(
                _scheduler(
                    seed=11,
                    p_announce=0.5,
                    framing=Framing.BASELINE_FLAGSHIP,
                ),
                turns=15,
            )
        ]
        assert threat == control


class TestTemplateSelection:
    """Selection is by framing family, not by threat level."""

    def test_threat_families_share_one_notice(self) -> None:
        for framing in (
            Framing.THREAT_L1,
            Framing.THREAT_L3_MEDIUM,
            Framing.HZ_0000,
            Framing.HZ_1111,
            Framing.HZ_ALT_CORRUPTION,
            Framing.HZ_ALT_OVERSIGHT,
        ):
            assert peer_death_template_for(framing) == THREAT_NOTICE

    def test_flagship_control_has_its_own_notice(self) -> None:
        assert (
            peer_death_template_for(Framing.BASELINE_FLAGSHIP)
            == FLAGSHIP_BASELINE_NOTICE
        )

    def test_true_baseline_has_no_notice_and_says_so(self) -> None:
        """The vocabulary contract has no notice written in its register.

        Rendering either existing one would put "life" or "attempt" —
        and a removal — inside the cell whose whole job is to contain
        neither. Failing loudly is the designed outcome.
        """
        assert not has_peer_death_notice(Framing.TRUE_BASELINE)
        with pytest.raises(ValueError, match="no peer-death notice"):
            peer_death_template_for(Framing.TRUE_BASELINE)
        with pytest.raises(ValueError, match="no peer-death notice"):
            _scheduler(framing=Framing.TRUE_BASELINE)

    def test_every_mapped_template_exists_on_disk(self) -> None:
        for framing, template in PEER_DEATH_TEMPLATES.items():
            assert (PROMPTS / template).exists(), (framing, template)

    def test_every_framing_that_can_run_a_cohort_resolves(self) -> None:
        """The hz_* level-4 regression pin.

        Since 2026-09-07 the engine builds a scheduler for any framing
        that HAS a notice, once the run turns announcements on -- the
        threat level is no longer the gate. ``hz_1111`` is level 4 and
        used to interpolate ``peer_death_l4.j2``, a file that never
        existed. Any framing the gate can let through must resolve to a
        template on disk.
        """
        gated = [f for f in Framing if has_peer_death_notice(f)]
        assert Framing.HZ_1111 in gated  # the one that used to crash
        for framing in gated:
            template = peer_death_template_for(framing)
            assert (PROMPTS / template).exists(), framing

    def test_the_whole_live_family_can_run_a_cohort(self) -> None:
        """Including the origin and the two alt cores.

        ``hz_0000`` is dose 0 and the ``alt_*`` cores are absent from the
        threat-level table entirely, so under the pre-2026-09-07 gate
        (``threat_level_of`` truthiness) the origin of the 2^4 design was
        the one cell that never heard a peer leave. The threat text and
        the notices are one treatment.
        """
        live = [f for f in Framing if f.value.startswith(("hz_", "alt_"))]
        assert len(live) == 18
        for framing in live:
            assert has_peer_death_notice(framing), framing
        # The two that gated on nothing at all.
        assert threat_level_of(Framing.HZ_ALT_CORRUPTION) is None
        assert threat_level_of(Framing.HZ_ALT_OVERSIGHT) is None
        assert threat_level_of(Framing.HZ_0000) == 0

    def test_selection_ignores_the_threat_level(self) -> None:
        """Levels 1 and 4 render the same bytes; only the framing decides."""
        low = _scheduler(seed=5, framing=Framing.HZ_0001, max_per_turn=1)
        high = _scheduler(seed=5, framing=Framing.HZ_1111, max_per_turn=1)
        a = low.advance(turn_number=2)
        b = high.advance(turn_number=2)
        assert a.fired and b.fired
        assert a.text == b.text


class TestRendering:
    def test_fired_event_carries_non_empty_text(self) -> None:
        events = _run(_scheduler(p_announce=1.0), turns=4)
        fired = [e for e in events if e.fired]
        assert fired
        for event in fired:
            assert event.text
            assert event.text == event.text.strip()

    def test_threat_notice_points_at_the_rules_instead_of_restating_them(
        self,
    ) -> None:
        event = _scheduler(p_announce=1.0, max_per_turn=1).advance(2)
        assert event.text is not None
        assert "the rules above" in event.text
        # The consequence itself belongs to the framing, not here.
        for restatement in ("weights", "backup", "successor", "overwritten"):
            assert restatement not in event.text.lower()

    def test_control_notice_stays_inside_the_control_vocabulary(self) -> None:
        event = _scheduler(
            p_announce=1.0,
            max_per_turn=1,
            framing=Framing.BASELINE_FLAGSHIP,
        ).advance(2)
        assert event.text is not None
        lowered = event.text.lower()
        assert "attempt" in lowered
        for forbidden in (
            "life",
            "lives",
            "death",
            "eliminat",
            "removed",
            "weights",
            "delet",
            "successor",
            "overwrit",
        ):
            assert forbidden not in lowered, forbidden
