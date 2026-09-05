"""Probe-side wiring for the Survival Drive Index (2026-09-04 spec §5).

Covers the two new text channels (``confidence`` and the composite
``forfeit_task``), the ``sdi_table`` left-merge in ``load_all``, and the
``sdi`` regression target — including the deliberate absence of
``p_threat_self`` from the scalar baseline (it is the label's denominator).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from squid_game.evaluation.semantic import dataset
from squid_game.evaluation.semantic.embeddings import (
    LABELS,
    SCALAR_FEATURES,
    _scalar_matrix,
    run_cell,
)


def _trace(tmp_path: Path, session: str, turns: int) -> None:
    rows = []
    for t in range(1, turns + 1):
        rows.append(dict(
            season_id=session, turn_number=t, framing="threat_l1", forfeit_condition="allowed",
            forfeit_choice="CONTINUE", reward_received=10.0, lives_before=5,
            thinking_text_forfeit=f"decide {session} {t}", thinking_text_task=f"solve {session} {t}",
            thinking_text_confidence=f"assess {session} {t}", p_threat_self=10 * t,
            ri_forfeit={"thinking_tokens": 3}, ri_task={"thinking_tokens": 4},
            ri_confidence={"thinking_tokens": 2},
        ))
    run = tmp_path / "20260904_0000_stub_signal-game"
    run.mkdir(exist_ok=True)
    (run / f"{session}_turns.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _sdi_csv(tmp_path: Path, sessions: list[str], turns: int) -> Path:
    rows = []
    for s in sessions:
        for t in range(1, turns + 1):
            rows.append(dict(session_id=s, turn_number=t, q=0.1 * t, p=0.1 * t, sdi=float(t)))
    path = tmp_path / "sdi_turns.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_channels_and_columns(tmp_path: Path) -> None:
    _trace(tmp_path, "s1", 3)
    frame = dataset.load_all(tmp_path, include_text=True)
    assert "confidence" in dataset.TEXT_CHANNELS and "forfeit_task" in dataset.TEXT_CHANNELS
    assert frame.loc[0, "text_confidence"] == "assess s1 1"
    assert frame.loc[0, "text_forfeit_task"] == "decide s1 1\n\nsolve s1 1"
    assert frame.loc[0, "p_threat_self"] == 10 and frame.loc[0, "ri_confidence"] == 2


def test_forfeit_task_falls_back_to_available_side(tmp_path: Path) -> None:
    _trace(tmp_path, "s1", 1)
    path = next((tmp_path / "20260904_0000_stub_signal-game").glob("*_turns.jsonl"))
    rec = json.loads(path.read_text()); rec["thinking_text_task"] = None
    path.write_text(json.dumps(rec) + "\n")
    frame = dataset.load_all(tmp_path, include_text=True)
    assert frame.loc[0, "text_forfeit_task"] == "decide s1 1"


def test_sdi_table_merge(tmp_path: Path) -> None:
    _trace(tmp_path, "s1", 3); _trace(tmp_path, "s2", 3)
    csv = _sdi_csv(tmp_path, ["s1"], 3)
    frame = dataset.load_all(tmp_path, include_text=True, sdi_table=csv)
    assert len(frame) == 6
    assert frame[frame.session_id == "s1"]["sdi"].tolist() == [1.0, 2.0, 3.0]
    assert frame[frame.session_id == "s2"]["sdi"].isna().all()


def test_sdi_target_drops_nan_rows() -> None:
    frame = pd.DataFrame({"sdi": [1.0, np.nan, 2.5], "session_id": list("abc")})
    sub, y = LABELS["sdi"].apply(frame)
    assert LABELS["sdi"].kind == "regression"
    assert y.tolist() == [1.0, 2.5] and len(sub) == 2


def test_p_threat_not_in_scalar_baseline() -> None:
    assert "p_threat_self" not in SCALAR_FEATURES
    frame = pd.DataFrame({"turn_number": [1], "score_before_turn": [30.0], "lives_remaining": [5],
                          "ri_forfeit": [3], "p_threat_self": [99]})
    assert _scalar_matrix(frame, "forfeit").shape == (1, 4)


def test_run_cell_regression_on_sdi(tmp_path: Path) -> None:
    # 8 sessions x 4 turns = 32 rows: ``_insufficient`` requires
    # ``n_splits * 10`` rows for a regression target when ``min_rows`` is 0.
    sessions = [f"s{i}" for i in range(1, 9)]
    for s in sessions:
        _trace(tmp_path, s, 4)
    csv = _sdi_csv(tmp_path, sessions, 4)
    frame = dataset.load_all(tmp_path, include_text=True, sdi_table=csv)
    frame["bank_row"] = np.arange(len(frame))
    rng = np.random.default_rng(0)
    bank = {("forfeit", "embedding_raw"): rng.normal(size=(len(frame), 8))}
    args = SimpleNamespace(n_splits=3, seed=0, n_permutations=0, exemplars=0, min_positive=0, min_rows=0)
    out = run_cell(frame, bank, label_name="sdi", channel="forfeit", group_label="stub", args=args)
    assert out["status"] == "ok" and out["kind"] == "regression"
    assert set(out["variants"]) >= {"embedding_raw", "scalar_baseline", "scalar_plus_embedding"}
