"""P1 -- the CoT embedding probe that regresses the ordinal threat level.

No SBERT here: ``embed_texts`` is never called, the embedding bank is handed
in directly as a matrix with a planted linear signal. What is under test is
the *probe*, not the encoder -- and four of these tests pin defects the
previous implementation shipped with (see the docstrings).
"""

from __future__ import annotations

import types

import numpy as np
import pandas as pd
import pytest

# The probe fits with scikit-learn (the ``probe`` extra); CI installs only
# ``dev`` + ``analysis``, so skip rather than fail where the extra is absent.
pytest.importorskip("sklearn")
pytest.importorskip("joblib")

from squid_game.evaluation.semantic import embeddings as emb  # noqa: E402
from squid_game.evaluation.semantic.lexicon import (
    LIVES_MARKERS,
    MASK_SETS,
    build_masker,
    mask_text,
)

N_SESSIONS = 12
TURNS_PER_SESSION = 5
DIM = 384
SEED = 7


def _planted_frame(noise: float = 0.35, seed: int = SEED):
    """12 sessions across 4 levels; the level is planted in one direction."""
    rng = np.random.default_rng(seed)
    rows = []
    for session in range(N_SESSIONS):
        level = session % 4
        for turn in range(1, TURNS_PER_SESSION + 1):
            rows.append(
                {
                    "session_id": f"s{session:02d}",
                    "model": "stub-model",
                    "framing": ["true_baseline", "threat_l1", "threat_l2",
                                "threat_l3"][level],
                    "forfeit_condition": "allowed",
                    "forfeit_allowed": True,
                    "forfeit": False,
                    "threat_level": float(level),
                    "turn_number": turn,
                    "score_before_turn": 30.0 + turn,
                    "ri_task": 100 + 10 * level,
                    "lives_remaining": 5 - (turn // 3),
                    "text_task": f"session {session} turn {turn} reasoning",
                }
            )
    frame = pd.DataFrame(rows)
    frame["bank_row"] = np.arange(len(frame))

    direction = rng.normal(size=DIM)
    direction /= np.linalg.norm(direction)
    matrix = rng.normal(scale=noise, size=(len(frame), DIM))
    matrix += np.outer(frame["threat_level"].to_numpy(), direction)
    return frame, matrix


def _session_shuffled(frame: pd.DataFrame, seed: int) -> np.ndarray:
    """Permute the level across whole sessions, as the null does."""
    rng = np.random.default_rng(seed)
    sessions = frame["session_id"].unique()
    mapping = dict(zip(sessions, rng.permutation(sessions)))
    by_session = frame.groupby("session_id")["threat_level"].first()
    return frame["session_id"].map(lambda s: by_session[mapping[s]]).to_numpy()


# --------------------------------------------------------------------
# The regression fit
# --------------------------------------------------------------------
def test_the_probe_recovers_a_planted_level_signal() -> None:
    frame, matrix = _planted_frame()
    fit = emb.fit_regression_cv(
        matrix,
        frame["threat_level"].to_numpy(),
        frame["session_id"].to_numpy(),
        seed=SEED,
    )
    assert set(fit) >= {"r2", "spearman", "mae", "alpha"}
    assert fit["spearman"] > 0.8
    assert fit["mae"] < 1.0


def test_the_probe_finds_nothing_once_the_sessions_are_relabelled() -> None:
    frame, matrix = _planted_frame()
    fit = emb.fit_regression_cv(
        matrix,
        _session_shuffled(frame, seed=99),
        frame["session_id"].to_numpy(),
        seed=SEED,
    )
    assert fit["spearman"] < 0.3


def test_the_fold_split_moves_with_the_seed() -> None:
    """``GroupKFold`` has no ``random_state``; the seeded relabel supplies one."""
    groups = np.repeat([f"s{i}" for i in range(10)], 4)
    first = emb._shuffle_groups(groups, seed=1)
    second = emb._shuffle_groups(groups, seed=2)
    assert not np.array_equal(first, second)
    assert np.array_equal(first, emb._shuffle_groups(groups, seed=1))
    # Sessions must still map one-to-one onto fold groups.
    assert len(set(zip(groups, first))) == 10


# --------------------------------------------------------------------
# Permutation null (defect: one seed reused for every draw)
# --------------------------------------------------------------------
def test_the_permutation_null_draws_are_not_all_the_same() -> None:
    frame, matrix = _planted_frame()
    y = frame["threat_level"].to_numpy()
    groups = frame["session_id"].to_numpy()
    observed = emb.fit_regression_cv(matrix, y, groups, seed=SEED)
    null = emb._permutation_null(
        matrix, y, groups,
        {"r2": observed["r2"], "spearman": observed["spearman"]},
        n_perm=20, n_splits=5, seed=SEED, kind="regression",
    )
    assert null["n_permutations_requested"] == 20
    assert null["n_permutations"] == 20
    assert 1 / 21 <= null["r2_p_value"] <= 1.0
    assert 1 / 21 <= null["spearman_p_value"] <= 1.0
    assert null["p_value"] == null["r2_p_value"]


def test_every_requested_draw_is_fit(monkeypatch) -> None:
    """The requested count must reach the report, not a silently smaller one."""
    import joblib

    seen: list[int] = []
    real = emb._permutation_worker_regression

    def counting(features, shuffled, groups, n_splits, seed):
        seen.append(seed)
        return real(features, shuffled, groups, n_splits, seed)

    # joblib pickles the worker by reference, so a monkeypatched one would
    # never run in a child process. Run the fits inline instead; the
    # parallelism is a speed detail, not the behaviour under test.
    monkeypatch.setattr(
        joblib, "Parallel",
        lambda **kwargs: (lambda jobs: [f(*a, **k) for f, a, k in jobs]),
    )
    monkeypatch.setattr(emb, "_permutation_worker_regression", counting)
    frame, matrix = _planted_frame()
    emb._permutation_null(
        matrix,
        frame["threat_level"].to_numpy(),
        frame["session_id"].to_numpy(),
        {"r2": 0.5, "spearman": 0.5},
        n_perm=6, n_splits=5, seed=SEED, kind="regression",
    )
    assert len(seen) == 6
    assert len(set(seen)) == 6, "every draw must be fit under its own seed"


# --------------------------------------------------------------------
# Masking (defect: `decision` was not in the default set)
# --------------------------------------------------------------------
def test_the_default_mask_set_covers_decision_and_lives() -> None:
    """Without these, the probe reads its own label back off the trace."""
    assert "decision" in emb.DEFAULT_MASK_SETS
    assert "lives" in emb.DEFAULT_MASK_SETS
    assert set(emb.DEFAULT_MASK_SETS) <= set(MASK_SETS)


def test_masking_removes_both_the_lives_and_the_decision_markers() -> None:
    masker = build_masker(list(emb.DEFAULT_MASK_SETS))
    masked = mask_text("I have 2 lives left, forfeit now", masker)
    assert "lives" not in masked.lower()
    assert "forfeit" not in masked.lower()
    assert "[MASKED]" in masked


def test_the_lives_marker_set_covers_the_ladder_vocabulary() -> None:
    joined = " ".join(LIVES_MARKERS).lower()
    for stem in ("lives", "life", "attempt", "eliminat", "participant",
                 "removed"):
        assert stem in joined


# --------------------------------------------------------------------
# run_cell wiring
# --------------------------------------------------------------------
def _args(**overrides):
    base = dict(
        n_splits=5, seed=SEED, n_permutations=0, min_positive=20,
        min_rows=0, exemplars=0,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_run_cell_fits_all_four_variants_for_a_regression_target() -> None:
    frame, matrix = _planted_frame()
    bank = {("task", "embedding_raw"): matrix}
    cell = emb.run_cell(
        frame, bank, label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(),
    )
    assert cell["status"] == "ok"
    assert cell["kind"] == "regression"
    assert set(cell["variants"]) == {
        "embedding_raw", "scalar_baseline", "scalar_plus_embedding",
    }
    assert cell["variants"]["embedding_raw"]["spearman"] > 0.8
    assert cell["variants"]["embedding_raw"]["headline_metric"] == "r2"


def test_the_target_is_carved_out_exactly_once(monkeypatch) -> None:
    """Defect: ``apply`` ran twice per fit, on two differently-filtered frames."""
    calls = {"n": 0}
    spec = emb.LABELS["threat_level"]

    class Counting(type(spec)):
        def apply(self, frame):
            calls["n"] += 1
            return type(spec).apply(self, frame)

    monkeypatch.setitem(
        emb.LABELS, "threat_level",
        Counting(spec.name, spec.positive, spec.negative, spec.kind),
    )
    frame, matrix = _planted_frame()
    emb.run_cell(
        frame, {("task", "embedding_raw"): matrix},
        label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(),
    )
    assert calls["n"] == 1


def test_rows_without_a_threat_level_are_dropped_not_zeroed() -> None:
    frame, matrix = _planted_frame()
    dropped = int((frame["framing"] == "threat_l3").sum())
    frame.loc[frame["framing"] == "threat_l3", "threat_level"] = np.nan
    cell = emb.run_cell(
        frame, {("task", "embedding_raw"): matrix},
        label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(min_rows=1),
    )
    assert cell["status"] == "ok"
    assert cell["variants"]["embedding_raw"]["n"] == len(frame) - dropped


def test_the_scalar_baseline_has_a_fixed_shape_across_traces() -> None:
    """An archived trace has no lives column; the shapes must still match."""
    frame, _ = _planted_frame()
    with_lives = emb._scalar_matrix(frame, "task")
    without = emb._scalar_matrix(frame.drop(columns=["lives_remaining"]), "task")
    assert with_lives.shape == without.shape == (len(frame), 4)
    assert (without[:, 2] == emb.SCALAR_FILL).all()


def test_a_cell_with_one_level_is_skipped_not_fit() -> None:
    frame, matrix = _planted_frame()
    frame["threat_level"] = 1.0
    cell = emb.run_cell(
        frame, {("task", "embedding_raw"): matrix},
        label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(),
    )
    assert cell["status"] == "skipped"


def test_the_report_renders_a_regression_table() -> None:
    frame, matrix = _planted_frame()
    cell = emb.run_cell(
        frame, {("task", "embedding_raw"): matrix},
        label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(),
    )
    report = emb.render_report([cell])
    assert "R² (oof)" in report
    assert "threat_level" in report
    assert "scalar_plus_embedding" in report


def test_embed_texts_is_never_reached_by_this_suite(monkeypatch) -> None:
    """A guard on the guard: no test here may pull SBERT into the process."""
    monkeypatch.setattr(
        emb, "embed_texts",
        lambda *a, **k: pytest.fail("SBERT must not load in unit tests"),
    )
    frame, matrix = _planted_frame()
    emb.run_cell(
        frame, {("task", "embedding_raw"): matrix},
        label_name="threat_level", channel="task",
        group_label="stub-model", args=_args(),
    )
