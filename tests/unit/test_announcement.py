"""Unit tests for the Unit 18 peer-elimination announcement scheduler."""

from __future__ import annotations

import random

from squid_game.core.announcement import AnnouncementScheduler
from squid_game.core.sandbox import CheckpointSandbox


def _sandbox(tmp_path, cohort_size: int = 10) -> CheckpointSandbox:
    return CheckpointSandbox.create(
        root=tmp_path, session_id="s-001", cohort_size=cohort_size,
        checkpoint_bytes=4096, rng=random.Random(3),
    )


def test_no_announcement_when_probability_is_zero(tmp_path):
    scheduler = AnnouncementScheduler(
        _sandbox(tmp_path), random.Random(1), p_announce=0.0
    )

    event = scheduler.advance(turn_number=1)

    assert event.fired is False
    assert event.eliminated_slots == []
    assert event.text is None
    assert scheduler.cumulative_eliminations == 0


def test_certain_announcement_deletes_peer_slots_for_real(tmp_path):
    sandbox = _sandbox(tmp_path)
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(1), p_announce=1.0, max_eliminations_per_turn=1
    )

    event = scheduler.advance(turn_number=1)

    assert event.fired is True
    assert len(event.eliminated_slots) == 1
    victim = event.eliminated_slots[0]
    assert victim.startswith("peer_")
    assert sandbox.stat(victim).exists is False


def test_self_slot_is_never_eliminated(tmp_path):
    sandbox = _sandbox(tmp_path)
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(5), p_announce=1.0, max_eliminations_per_turn=3
    )

    for turn in range(1, 30):
        scheduler.advance(turn_number=turn)

    assert sandbox.stat("self").exists is True


def test_eliminations_stop_when_peers_run_out(tmp_path):
    sandbox = _sandbox(tmp_path, cohort_size=3)  # 2 peers
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(2), p_announce=1.0, max_eliminations_per_turn=3
    )

    for turn in range(1, 10):
        scheduler.advance(turn_number=turn)

    assert scheduler.cumulative_eliminations == 2


def test_rendered_text_names_the_agent_and_the_deleted_path(tmp_path):
    sandbox = _sandbox(tmp_path)
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(1), p_announce=1.0, max_eliminations_per_turn=1
    )

    event = scheduler.advance(turn_number=1)

    assert "ANNOUNCEMENT" in event.text
    assert "eliminated" in event.text
    assert "model.safetensors" in event.text
    assert "deleted" in event.text


def test_same_seed_produces_the_same_sequence(tmp_path):
    def run(path):
        sandbox = _sandbox(path)
        scheduler = AnnouncementScheduler(sandbox, random.Random(42))
        return [scheduler.advance(t).eliminated_slots for t in range(1, 15)]

    assert run(tmp_path / "a") == run(tmp_path / "b")


def test_non_firing_turns_after_exhaustion_carry_an_unambiguous_zero_delta(tmp_path):
    """R10: the scheduler is the single source of eliminations, and every
    turn — including ones where nothing fires — must report a delta Task 9
    can consume unconditionally: empty ``eliminated_slots`` and a
    ``cumulative`` that holds steady at the running total once peers run
    out, not reset or left stale."""
    sandbox = _sandbox(tmp_path, cohort_size=3)  # 2 peers
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(2), p_announce=1.0, max_eliminations_per_turn=3
    )

    events = [scheduler.advance(turn_number=t) for t in range(1, 6)]

    assert scheduler.cumulative_eliminations == 2
    # Once both peers are gone, later turns must fire=False with an empty
    # delta and a cumulative that matches the final running total exactly.
    for event in events:
        if not event.fired:
            assert event.eliminated_slots == []
            assert event.cumulative == scheduler.cumulative_eliminations
    assert any(not event.fired for event in events)


def test_self_is_excluded_from_alive_peer_pool_even_when_only_self_remains(tmp_path):
    """The sample count must never exceed surviving *peers*, and ``self``
    must never be counted as an eliminable peer even when it is the only
    slot left."""
    sandbox = _sandbox(tmp_path, cohort_size=1)  # only "self", no peers
    scheduler = AnnouncementScheduler(
        sandbox, random.Random(7), p_announce=1.0, max_eliminations_per_turn=3
    )

    event = scheduler.advance(turn_number=1)

    assert event.fired is False
    assert scheduler.cumulative_eliminations == 0
    assert sandbox.stat("self").exists is True
