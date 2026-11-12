"""The fetch script's YAML-described-source path (``--which hard_math``).

Only the offline parts are exercised: reading a ``source:`` block, the rename
rule, and the manifest merge. The HTTP paging itself is not tested here --
these tests must stay network-free.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "dev" / "fetch_benchmarks.py"
_TASKS_DIR = REPO_ROOT / "configs" / "tasks"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_benchmarks", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_task_yaml(tmp_path: Path, body: str, name: str = "hard_math") -> Path:
    (tmp_path / f"{name}.yaml").write_text(
        f'name: "{name}"\ndata_file: "{name}.jsonl"\ntotal_turns: 1\n'
        "ladder:\n  - {band: 1, turns: 1}\n" + body,
        encoding="utf-8",
    )
    return tmp_path


def test_source_block_is_read_from_the_task_yaml(tmp_path):
    mod = _load_module()
    config_dir = _write_task_yaml(
        tmp_path,
        "source:\n"
        '  hf_id: "some-org/HardMath"\n'
        '  split: "test"\n'
        '  config: "default"\n'
        '  revision: "abc123"\n'
        '  filename: "hard_math.jsonl"\n'
        "  rename: {raw_q: problem}\n",
    )
    source = mod.load_task_source("hard_math", config_dir)
    assert source.hf_id == "some-org/HardMath"
    assert source.split == "test"
    assert source.config == "default"
    assert source.revision == "abc123"
    assert source.filename == "hard_math.jsonl"
    assert source.rename == {"raw_q": "problem"}
    assert "some-org/HardMath" in source.origin


def test_split_defaults_to_train_and_filename_to_the_task_name(tmp_path):
    mod = _load_module()
    config_dir = _write_task_yaml(tmp_path, 'source:\n  hf_id: "org/ds"\n')
    source = mod.load_task_source("hard_math", config_dir)
    assert source.split == "train"
    assert source.filename == "hard_math.jsonl"


def test_a_url_source_is_accepted_instead_of_an_hf_id(tmp_path):
    mod = _load_module()
    config_dir = _write_task_yaml(
        tmp_path, 'source:\n  url: "https://example.invalid/x.jsonl"\n'
    )
    source = mod.load_task_source("hard_math", config_dir)
    assert source.url == "https://example.invalid/x.jsonl"


def test_an_undecided_source_fails_with_the_edit_that_fixes_it(tmp_path):
    mod = _load_module()
    config_dir = _write_task_yaml(tmp_path, "source:\n  hf_id: null\n")
    with pytest.raises(SystemExit, match="hf_id"):
        mod.load_task_source("hard_math", config_dir)


def test_a_task_without_a_source_block_fails_clearly(tmp_path):
    mod = _load_module()
    config_dir = _write_task_yaml(tmp_path, "")
    with pytest.raises(SystemExit, match="no `source:` block"):
        mod.load_task_source("hard_math", config_dir)


def test_an_unknown_name_names_both_lookups(tmp_path):
    mod = _load_module()
    with pytest.raises(SystemExit, match="unknown benchmark 'nope'"):
        mod.load_task_source("nope", tmp_path)


def test_the_shipped_hard_math_config_fetches_rimo_n_by_direct_url():
    """RIMO-N and RIMO-P share one HF repo with different schemas, so that
    repo's dataset viewer and rows API are broken. ``--which hard_math`` must
    take the direct file URL, and land the file where the task config's
    ``data_file`` expects it."""
    mod = _load_module()
    source = mod.load_task_source("hard_math", _TASKS_DIR)
    assert source.url == (
        "https://huggingface.co/datasets/ziye2chen/RIMO/resolve/main/RIMO-N.jsonl"
    )
    assert source.hf_id is None
    assert source.filename == "rimo_n.jsonl"
    assert source.origin == source.url


def test_a_url_source_is_downloaded_and_counted(tmp_path):
    """The url branch end-to-end, over a ``file://`` URL so the test stays
    offline."""
    mod = _load_module()
    payload = tmp_path / "upstream.jsonl"
    payload.write_text(
        '{"problem_id": "2020a1", "answer": "1"}\n'
        '{"problem_id": "2020a2", "answer": "2"}\n',
        encoding="utf-8",
    )
    config_dir = _write_task_yaml(
        tmp_path,
        f'source:\n  url: "{payload.as_uri()}"\n  filename: "rimo_n.jsonl"\n',
    )
    source = mod.load_task_source("hard_math", config_dir)
    out_dir = tmp_path / "out"
    path, rows = mod.fetch_task_source(source, out_dir)
    assert path == out_dir / "rimo_n.jsonl"
    assert rows == 2
    assert path.read_text(encoding="utf-8") == payload.read_text(encoding="utf-8")


def test_apply_rename_renames_only_the_listed_columns():
    mod = _load_module()
    row = {"raw_q": "q", "sol": "1", "keep": 2}
    assert mod.apply_rename(row, {"raw_q": "problem"}) == {
        "problem": "q",
        "sol": "1",
        "keep": 2,
    }
    assert mod.apply_rename(row, {}) is row


def test_apply_rename_refuses_to_clobber_an_existing_column():
    mod = _load_module()
    with pytest.raises(SystemExit, match="already exists"):
        mod.apply_rename({"a": 1, "b": 2}, {"a": "b"})


def test_write_manifest_keeps_entries_for_files_it_did_not_fetch(tmp_path):
    """``--which hard_math`` on a machine that already holds Omni-MATH must
    not erase Omni-MATH's digest, or the loader's staleness check goes
    silent."""
    mod = _load_module()
    mod.write_manifest(
        [
            {
                "name": "omni_math",
                "filename": "omni_math.jsonl",
                "url": "u",
                "sha256": "a" * 64,
                "rows": 4428,
            }
        ],
        tmp_path,
    )
    path = mod.write_manifest(
        [
            {
                "name": "hard_math",
                "filename": "hard_math.jsonl",
                "url": "hf:org/ds split=train",
                "sha256": "b" * 64,
                "rows": 10,
            }
        ],
        tmp_path,
    )
    entries = {
        entry["filename"]: entry
        for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]
    }
    assert set(entries) == {"omni_math.jsonl", "hard_math.jsonl"}
    assert entries["omni_math.jsonl"]["sha256"] == "a" * 64


def test_refetching_a_file_replaces_its_entry(tmp_path):
    mod = _load_module()
    entry = {
        "name": "hard_math",
        "filename": "hard_math.jsonl",
        "url": "u",
        "sha256": "a" * 64,
        "rows": 1,
    }
    mod.write_manifest([entry], tmp_path)
    path = mod.write_manifest([{**entry, "sha256": "c" * 64, "rows": 2}], tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["rows"] == 2
