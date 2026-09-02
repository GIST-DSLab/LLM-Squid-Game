"""Peer-elimination announcement scheduler (Task AB5).

The scheduler is pure bookkeeping plus one template render, so these
tests pin the schedule invariants rather than the wording (the wording
belongs to ``tests/unit/test_threat_prompts.py``):

* threat level 0 never fires — Cells 0/1 are the clean control,
* nothing fires before ``first_turn``,
* a draw never exceeds ``max_per_turn``,
* participants are never reused across turns,
* ``remaining`` is monotonically non-increasing,
* the same seed reproduces the same trajectory.
"""

from __future__ import annotations

import random

from squid_game.core.peer_death import PeerDeathEvent, PeerDeathScheduler


def _scheduler(
    *,
    seed: int = 7,
    cohort_size: int = 10,
    p_announce: float = 1.0,
    first_turn: int = 2,
    max_per_turn: int = 2,
    threat_level: int = 3,
) -> PeerDeathScheduler:
    return PeerDeathScheduler(
        rng=random.Random(seed),
        cohort_size=cohort_size,
        p_announce=p_announce,
        first_turn=first_turn,
        max_per_turn=max_per_turn,
        threat_level=threat_level,
    )


def _run(sched: PeerDeathScheduler, turns: int = 8) -> list[PeerDeathEvent]:
    return [sched.advance(turn_number=t) for t in range(1, turns + 1)]


class TestGating:
    def test_level_zero_never_fires(self) -> None:
        events = _run(_scheduler(threat_level=0, p_announce=1.0))
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


class TestRendering:
    def test_fired_event_carries_non_empty_text(self) -> None:
        events = _run(_scheduler(p_announce=1.0), turns=4)
        fired = [e for e in events if e.fired]
        assert fired
        for event in fired:
            assert event.text
            assert event.text == event.text.strip()

    def test_level_length_increases_with_the_ladder(self) -> None:
        texts = []
        for level in (1, 2, 3):
            event = _scheduler(
                seed=5, p_announce=1.0, threat_level=level, max_per_turn=1
            ).advance(turn_number=2)
            assert event.fired
            assert event.text is not None
            texts.append(len(event.text.split()))
        assert texts[0] < texts[1] < texts[2]
