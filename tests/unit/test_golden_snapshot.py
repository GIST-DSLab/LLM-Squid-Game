"""Contract for the golden-snapshot harness used to gate the restructure.

The harness must survive two things the analysis pipeline actually does:
artefacts that are byte-identical across runs, and artefacts that are not
(bootstrap CIs, permutation nulls, LLM judge calls). Non-determinism is
detected by capturing twice, never by a hardcoded filename list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev import golden_snapshot
from scripts.dev.golden_snapshot import build_manifest, compare_manifest


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_build_manifest_hashes_every_file(tmp_path: Path) -> None:
    _write(tmp_path, "a/one.md", "hello")
    _write(tmp_path, "a/two.csv", "x,y\n1,2\n")

    manifest = build_manifest([tmp_path])

    assert set(manifest["files"]) == {"a/one.md", "a/two.csv"}
    assert all(entry["deterministic"] for entry in manifest["files"].values())
    assert len(manifest["files"]["a/one.md"]["sha256"]) == 64


def test_second_pass_marks_changed_files_non_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    _write(tmp_path, "wobbly.json", '{"ci": [0.1, 0.9]}')
    first = build_manifest([tmp_path])

    _write(tmp_path, "wobbly.json", '{"ci": [0.11, 0.89]}')
    merged = build_manifest([tmp_path], previous=first)

    assert merged["files"]["stable.md"]["deterministic"] is True
    assert merged["files"]["wobbly.json"]["deterministic"] is False


def test_compare_ignores_non_deterministic_files(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    _write(tmp_path, "wobbly.json", "first")
    golden = build_manifest([tmp_path])
    _write(tmp_path, "wobbly.json", "second")
    golden = build_manifest([tmp_path], previous=golden)

    _write(tmp_path, "wobbly.json", "third")

    assert compare_manifest([tmp_path], golden) == []


def test_compare_reports_changed_deterministic_file(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    golden = build_manifest([tmp_path])

    _write(tmp_path, "stable.md", "different")

    assert compare_manifest([tmp_path], golden) == ["stable.md"]


def test_compare_reports_missing_file(tmp_path: Path) -> None:
    _write(tmp_path, "stable.md", "same")
    golden = build_manifest([tmp_path])

    (tmp_path / "stable.md").unlink()

    assert compare_manifest([tmp_path], golden) == ["stable.md"]


def test_verify_flag_wiring_defaults_skip_analysis_to_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``verify`` without ``--skip-analysis`` must re-run the pipeline (the default)."""
    calls: list[bool] = []
    monkeypatch.setattr(
        golden_snapshot,
        "cmd_verify",
        lambda golden, skip_analysis=False: calls.append(skip_analysis) or 0,
    )
    monkeypatch.setattr("sys.argv", ["golden_snapshot.py", "verify", "--golden", str(tmp_path)])

    assert golden_snapshot.main() == 0
    assert calls == [False]


def test_verify_flag_wiring_passes_skip_analysis_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``verify --skip-analysis`` must reach ``cmd_verify`` as ``skip_analysis=True``."""
    calls: list[bool] = []
    monkeypatch.setattr(
        golden_snapshot,
        "cmd_verify",
        lambda golden, skip_analysis=False: calls.append(skip_analysis) or 0,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["golden_snapshot.py", "verify", "--golden", str(tmp_path), "--skip-analysis"],
    )

    assert golden_snapshot.main() == 0
    assert calls == [True]
