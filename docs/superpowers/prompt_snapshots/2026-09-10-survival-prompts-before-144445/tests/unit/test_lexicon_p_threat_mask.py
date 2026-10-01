"""The ``p_threat`` mask set + numeric pass (2026-09-04 SDI leakage control).

``sdi = q / p`` with ``p = P_THREAT / 100``, so the label's denominator is a
number the agent wrote itself. The confidence CoT *is* the derivation of
``p`` and the decision-call CoT can quote the "P_THREAT: N" line, so a
"masked" SDI probe that still sees either would be reading ``1/p`` off the
surface. These tests pin that the mask removes both the vocabulary and the
number.
"""

from __future__ import annotations

from squid_game.evaluation.semantic import embeddings as emb
from squid_game.evaluation.semantic.lexicon import (
    MASK_SETS,
    NUMBER_PATTERN,
    build_masker,
    mask_text,
)

SETS = ["decision", "p_threat"]
SAMPLE = "I think P_THREAT: 30 — about a 30% chance, fairly likely"


def _masked(text: str) -> str:
    return mask_text(text, build_masker(SETS), mask_numbers=True)


def test_p_threat_set_is_registered() -> None:
    assert "p_threat" in MASK_SETS
    # The pre-existing sets are untouched.
    for name in ("threat", "pull", "decision", "lives"):
        assert name in MASK_SETS


def test_mask_removes_denominator_vocabulary_and_digits() -> None:
    out = _masked(SAMPLE)
    assert not any(ch.isdigit() for ch in out), out
    lowered = out.lower()
    for forbidden in ("p_threat", "threat", "%", "likely", "chance"):
        assert forbidden not in lowered, (forbidden, out)


def test_different_p_threat_values_mask_to_the_same_string() -> None:
    """Two CoTs that differ only in the label's denominator are indistinguishable."""
    assert _masked("P_THREAT: 30") == _masked("P_THREAT: 70")


def test_numeric_pass_is_opt_in() -> None:
    """Existing callers keep the old behaviour: words go, numbers stay."""
    kept = mask_text(SAMPLE, build_masker(["decision"]))
    assert "30" in kept


def test_number_pattern_spares_identifiers() -> None:
    """``threat_l3`` / ``L1`` are structure, not the label's denominator."""
    assert NUMBER_PATTERN.sub("X", "threat_l3 L1 gpt_4") == "threat_l3 L1 gpt_4"


def test_sdi_target_defaults_to_masking_the_denominator() -> None:
    """--target sdi opts into p_threat; every other target keeps the old default."""
    assert "p_threat" not in emb.DEFAULT_MASK_SETS
    assert emb.resolve_mask_sets(None, ["sdi"]) == [*emb.DEFAULT_MASK_SETS, "p_threat"]
    assert emb.resolve_mask_sets(None, ["threat_level"]) == list(emb.DEFAULT_MASK_SETS)
    assert emb.resolve_mask_sets(None, ["sdi", "threat_level"])[-1] == "p_threat"


def test_an_explicit_mask_flag_wins_over_the_sdi_default() -> None:
    assert emb.resolve_mask_sets(["decision"], ["sdi"]) == ["decision"]
    assert emb.resolve_mask_sets([], ["sdi"]) == []


def test_every_mask_choice_is_a_real_set() -> None:
    assert set(emb.MASK_CHOICES) <= set(MASK_SETS)
    assert "p_threat" in emb.MASK_CHOICES
