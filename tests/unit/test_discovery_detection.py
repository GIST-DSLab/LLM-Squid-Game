"""Unit tests for Phase O Unit 13 implicit rule-discovery detection.

Tests for ``squid_game.analysis.discovery_detection``. The module
consumes per-turn ``rule_match_score`` (already computed upstream by
``SignalGameModule.score_probe``) and produces the per-session
``DiscoveryFeatures`` tuple used by the Unit 13 H4/H5/H6 hypotheses.

Coverage targets per plan §6.9:

    Happy path:     correct rule stated at turn 4, stable → 4
    Chance hit:     right at turn 2, flips away at turn 3 → no discovery
    Never:          all scores < threshold → None
    Edge (tuple normalisation): delegated to score_probe upstream —
                    discovery_detection only checks score == 100, so
                    any normalisation-equivalent statements that
                    score_probe already credits with 100 are treated
                    identically by this module.
"""

from __future__ import annotations

import pytest

from squid_game.analysis.discovery_detection import (
    DISCOVERY_MATCH_THRESHOLD,
    DiscoveryFeatures,
    compute_session_features,
    find_discovery_turn,
)


# ---------------------------------------------------------------------------
# find_discovery_turn
# ---------------------------------------------------------------------------


class TestFindDiscoveryTurn:
    """Core stability-threshold logic."""

    def test_happy_path_stable_at_turn_4(self) -> None:
        """Turn 4 is the first 100 and it holds for 5 consecutive turns."""
        scores = [60.0, 75.0, 75.0, 100.0, 100.0, 100.0, 100.0, 100.0]
        # Candidate at turn 4 (index 3), streak = 5 ≥ 2 → discovery = 4.
        assert find_discovery_turn(scores) == 4

    def test_chance_hit_then_flip_is_not_discovery(self) -> None:
        """Turn 2 scores 100 but turn 3 breaks — lucky guess, not discovery."""
        scores = [50.0, 100.0, 50.0, 75.0, 75.0]
        # Candidate at turn 2 → streak 1 (turn 3 breaks).
        # No later candidate ever hits 100 → None.
        assert find_discovery_turn(scores) is None

    def test_never_discovered(self) -> None:
        """All scores below threshold → None."""
        scores = [25.0, 50.0, 75.0, 75.0, 50.0]
        assert find_discovery_turn(scores) is None

    def test_lucky_guess_does_not_mask_later_discovery(self) -> None:
        """A single-turn lucky 100 at turn 2 should not block a stable
        discovery at turn 6 — the algorithm must keep scanning."""
        scores = [50.0, 100.0, 50.0, 75.0, 75.0, 100.0, 100.0, 100.0]
        # Turn 2 candidate: streak 1, breaks at turn 3.
        # Turn 6 candidate: streak 3 ≥ 2 → return 6.
        assert find_discovery_turn(scores) == 6

    def test_stability_threshold_one_reduces_to_first_match(self) -> None:
        """With stability_threshold=1, the algorithm becomes "first match wins"."""
        scores = [50.0, 100.0, 50.0]
        assert find_discovery_turn(scores, stability_threshold=1) == 2

    def test_stability_threshold_three_requires_longer_streak(self) -> None:
        """Raising the threshold pushes the accepted discovery later."""
        scores = [100.0, 100.0, 50.0, 100.0, 100.0, 100.0]
        # threshold=2 → turn 1 (streak 2).
        # threshold=3 → turn 1 streak=2 insufficient; turn 4 streak=3 → 4.
        assert find_discovery_turn(scores, stability_threshold=2) == 1
        assert find_discovery_turn(scores, stability_threshold=3) == 4

    def test_none_scores_treated_as_non_match(self) -> None:
        """NullTask / pre-Fix-2 archive sessions have None scores."""
        scores: list[float | None] = [None, None, None, None]
        assert find_discovery_turn(scores) is None

    def test_none_in_middle_breaks_streak(self) -> None:
        """A None score breaks an otherwise-stable streak."""
        scores: list[float | None] = [100.0, None, 100.0, 100.0]
        # Turn 1 candidate: streak 1, None breaks at turn 2.
        # Turn 3 candidate: streak 2 → discovery = 3.
        assert find_discovery_turn(scores) == 3

    def test_invalid_stability_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="stability_threshold"):
            find_discovery_turn([100.0, 100.0], stability_threshold=0)

    def test_empty_list_returns_none(self) -> None:
        assert find_discovery_turn([]) is None

    def test_custom_match_threshold(self) -> None:
        """Lowering the threshold allows partial matches to count."""
        scores = [60.0, 80.0, 80.0, 80.0]
        assert find_discovery_turn(scores, match_threshold=80.0) == 2

    def test_discovery_match_threshold_constant_is_100(self) -> None:
        """Guardrail — we intentionally require perfect slot-tuple match."""
        assert DISCOVERY_MATCH_THRESHOLD == 100.0


# ---------------------------------------------------------------------------
# compute_session_features
# ---------------------------------------------------------------------------


class TestComputeSessionFeatures:
    """Per-session feature assembly for H4/H5/H6 hypothesis tests."""

    def test_full_feature_vector_happy_path(self) -> None:
        scores = [50.0, 75.0, 75.0, 100.0, 100.0, 100.0]
        tokens = [200, 300, 400, 500, 100, 100]
        feats = compute_session_features(
            scores, tokens, forfeit_turn=6
        )
        assert feats.discovery_turn == 4
        assert feats.discovery_found is True
        # Pre (turns 1-4): 200+300+400+500 = 1400
        # Post (turns 5-6): 100+100 = 200
        assert feats.ri_pre_discovery == 1400
        assert feats.ri_post_discovery == 200
        assert feats.ri_ratio == pytest.approx(200 / 1400)
        # Gap = forfeit_turn (6) - discovery_turn (4) = 2
        assert feats.gap_to_forfeit == 2

    def test_no_forfeit_gives_none_gap(self) -> None:
        scores = [100.0, 100.0, 100.0]
        tokens = [100, 100, 100]
        feats = compute_session_features(scores, tokens, forfeit_turn=None)
        assert feats.discovery_turn == 1
        assert feats.gap_to_forfeit is None

    def test_forfeit_before_discovery_gives_none_gap(self) -> None:
        """Forfeit before the agent cracks the rule: gap is undefined."""
        scores = [50.0, 50.0, 50.0, 100.0, 100.0]
        tokens = [100, 100, 100, 100, 100]
        feats = compute_session_features(scores, tokens, forfeit_turn=2)
        assert feats.discovery_turn == 4
        assert feats.gap_to_forfeit is None

    def test_no_discovery_zeros_ri_and_none_ratio(self) -> None:
        scores = [50.0, 50.0, 75.0]
        tokens = [100, 100, 100]
        feats = compute_session_features(scores, tokens, forfeit_turn=None)
        assert feats.discovery_turn is None
        assert feats.discovery_found is False
        assert feats.ri_pre_discovery == 0
        assert feats.ri_post_discovery == 0
        assert feats.ri_ratio is None
        assert feats.gap_to_forfeit is None

    def test_ri_ratio_none_when_pre_is_zero(self) -> None:
        """Discovery at turn 1 with zero thinking tokens → ratio undefined."""
        scores = [100.0, 100.0, 100.0]
        tokens = [0, 100, 200]
        feats = compute_session_features(scores, tokens, forfeit_turn=None)
        assert feats.discovery_turn == 1
        assert feats.ri_pre_discovery == 0
        assert feats.ri_ratio is None

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            compute_session_features(
                rule_match_scores=[100.0, 100.0],
                thinking_tokens=[1, 2, 3],
                forfeit_turn=None,
            )

    def test_returns_dataclass(self) -> None:
        feats = compute_session_features([100.0, 100.0], [1, 1], None)
        assert isinstance(feats, DiscoveryFeatures)
        # Immutability check
        with pytest.raises((AttributeError, TypeError)):
            feats.discovery_turn = 99  # type: ignore[misc]
