"""Contract for the golden-snapshot harness used to gate the restructure.

The harness must survive two things the analysis pipeline actually does:
artefacts that are byte-identical across runs, and artefacts that are not
(bootstrap CIs, permutation nulls, LLM judge calls). Non-determinism is
detected by capturing twice, never by a hardcoded filename list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import json

from scripts.dev import golden_snapshot
from scripts.dev.golden_snapshot import (
    build_manifest,
    classify_manifest_diff,
    compare_manifest,
    model_label,
)


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


def test_build_manifest_namespaces_multi_root_by_parent_directory(tmp_path: Path) -> None:
    """Multi-root keys must disambiguate by the run directory, not the shared
    ``phase3_analysis`` basename -- this is the layout the harness actually
    sees: every root passed to it in production is ``<run>/phase3_analysis``,
    so two different runs' roots share the same ``root.name``. Keying by
    ``root.parent.name`` instead must produce two distinct keys for a
    same-named file in each root, and lose neither.
    """
    _write(tmp_path, "run-a/phase3_analysis/unit14_results.md", "run-a content")
    _write(tmp_path, "run-b/phase3_analysis/unit14_results.md", "run-b content")
    roots = [tmp_path / "run-a" / "phase3_analysis", tmp_path / "run-b" / "phase3_analysis"]

    manifest = build_manifest(roots)

    assert set(manifest["files"]) == {
        "run-a/unit14_results.md",
        "run-b/unit14_results.md",
    }
    assert (
        manifest["files"]["run-a/unit14_results.md"]["sha256"]
        != manifest["files"]["run-b/unit14_results.md"]["sha256"]
    )


def test_compare_manifest_detects_change_in_second_multi_root(tmp_path: Path) -> None:
    """A changed deterministic file in the SECOND root must be reported.

    This is exactly the case a root.name collision would silently drop: with
    colliding keys, the second root's entry overwrites the first's in the
    manifest dict, so a change to the second root's copy is invisible.
    """
    _write(tmp_path, "run-a/phase3_analysis/unit14_results.md", "run-a content")
    _write(tmp_path, "run-b/phase3_analysis/unit14_results.md", "run-b content")
    roots = [tmp_path / "run-a" / "phase3_analysis", tmp_path / "run-b" / "phase3_analysis"]
    golden = build_manifest(roots)

    _write(tmp_path, "run-b/phase3_analysis/unit14_results.md", "run-b content, changed")

    assert compare_manifest(roots, golden) == ["run-b/unit14_results.md"]


def test_compare_reports_new_file(tmp_path: Path) -> None:
    """An artefact the pipeline did not use to emit must be reported.

    A gate that only iterates the golden manifest's own keys is blind to a
    restructure step that starts writing an extra file.
    """
    _write(tmp_path, "stable.md", "same")
    golden = build_manifest([tmp_path])

    _write(tmp_path, "surprise.csv", "a,b\n1,2\n")

    assert compare_manifest([tmp_path], golden) == ["surprise.csv"]


def test_classify_manifest_diff_separates_changed_missing_and_new(tmp_path: Path) -> None:
    _write(tmp_path, "changed.md", "before")
    _write(tmp_path, "gone.md", "here")
    golden = build_manifest([tmp_path])

    _write(tmp_path, "changed.md", "after")
    (tmp_path / "gone.md").unlink()
    _write(tmp_path, "surprise.csv", "a,b\n1,2\n")

    assert classify_manifest_diff([tmp_path], golden) == {
        "changed": ["changed.md"],
        "missing": ["gone.md"],
        "new": ["surprise.csv"],
    }


def test_classify_manifest_diff_ignores_non_deterministic_keys(tmp_path: Path) -> None:
    """A file golden recorded as non-deterministic is neither changed nor new."""
    _write(tmp_path, "wobbly.json", "first")
    golden = build_manifest([tmp_path])
    _write(tmp_path, "wobbly.json", "second")
    golden = build_manifest([tmp_path], previous=golden)

    _write(tmp_path, "wobbly.json", "third")

    assert classify_manifest_diff([tmp_path], golden) == {
        "changed": [],
        "missing": [],
        "new": [],
    }


def test_model_label_reads_the_run_config_not_the_directory_name(tmp_path: Path) -> None:
    """The label must be the run's own model, not the run directory name.

    Passing ``run.name`` rewrites the ``model`` field of seven artefacts per
    run, which is what made the first golden capture a mislabelled copy of
    the paper's results.
    """
    run = tmp_path / "20260422_0218_gemini-2.5-flash_signal-game"
    run.mkdir()
    (run / "experiment_config.json").write_text(
        json.dumps({"seasons": [{"provider_config": {"model": "gemini-2.5-flash"}}]}),
        encoding="utf-8",
    )

    assert model_label(run) == "gemini-2.5-flash"


def test_model_label_slugifies_the_model_the_way_the_runner_does(tmp_path: Path) -> None:
    """``runner`` writes ``:`` and ``/`` as ``-``; the artefacts carry the slug.

    Three of the four canonical runs are affected: the recorded model is
    ``gpt-oss:20b-cloud`` while every committed artefact says
    ``gpt-oss-20b-cloud``.
    """
    run = tmp_path / "run"
    run.mkdir()
    (run / "experiment_config.json").write_text(
        json.dumps({"seasons": [{"provider_config": {"model": "gpt-oss:20b-cloud"}}]}),
        encoding="utf-8",
    )

    assert model_label(run) == "gpt-oss-20b-cloud"


def test_model_label_fails_loudly_when_the_model_key_is_absent(tmp_path: Path) -> None:
    """No silent fallback to ``run.name`` -- that fallback is the defect."""
    run = tmp_path / "20260422_0218_gemini-2.5-flash_signal-game"
    run.mkdir()
    (run / "experiment_config.json").write_text(
        json.dumps({"seasons": [{"provider_config": {}}]}), encoding="utf-8"
    )

    with pytest.raises(SystemExit) as excinfo:
        model_label(run)

    assert run.name in str(excinfo.value)


def test_model_label_fails_loudly_when_the_config_is_absent(tmp_path: Path) -> None:
    run = tmp_path / "20260422_0218_gemini-2.5-flash_signal-game"
    run.mkdir()

    with pytest.raises(SystemExit) as excinfo:
        model_label(run)

    assert run.name in str(excinfo.value)


def _stub_golden(tmp_path: Path) -> Path:
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / "manifest.json").write_text(json.dumps({"files": {}}), encoding="utf-8")
    return golden


def test_cmd_verify_skips_the_pipeline_when_skip_analysis_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``skip_analysis=True`` must not invoke ``run_analysis`` at all.

    The flag exists so the harness's own self-test can compare a
    deliberately perturbed artefact before the pipeline overwrites it. A test
    that only checks argparse plumbing passes even with the condition
    inverted, which is the exact defect class this guards.
    """
    runs = [tmp_path / "run-a", tmp_path / "run-b"]
    for run in runs:
        (run / golden_snapshot.ARTEFACT_SUBDIR).mkdir(parents=True)
    calls: list[Path] = []
    monkeypatch.setattr(golden_snapshot, "canonical_runs", lambda: runs)
    monkeypatch.setattr(golden_snapshot, "run_analysis", calls.append)

    assert golden_snapshot.cmd_verify(_stub_golden(tmp_path), skip_analysis=True) == 0
    assert calls == []


def test_cmd_verify_runs_the_pipeline_when_skip_analysis_is_not_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without the flag every canonical run must be re-analysed."""
    runs = [tmp_path / "run-a", tmp_path / "run-b"]
    for run in runs:
        (run / golden_snapshot.ARTEFACT_SUBDIR).mkdir(parents=True)
    calls: list[Path] = []
    monkeypatch.setattr(golden_snapshot, "canonical_runs", lambda: runs)
    monkeypatch.setattr(golden_snapshot, "run_analysis", calls.append)

    assert golden_snapshot.cmd_verify(_stub_golden(tmp_path), skip_analysis=False) == 0
    assert calls == runs


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
