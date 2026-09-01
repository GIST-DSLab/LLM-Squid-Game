"""Resolution of the local benchmark data cache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def default_data_dir() -> Path:
    """Return the directory holding downloaded benchmark files."""
    override = os.environ.get("SQUID_GAME_BENCHMARK_DATA_DIR")
    if override:
        return Path(override)
    return _REPO_ROOT / "data" / "benchmarks"


def resolve_data_file(filename: str, data_dir: Path | None = None) -> Path:
    """Return the path to *filename*, or explain how to create it.

    Also compares the file against ``MANIFEST.json`` when one is present and
    logs a warning on mismatch. This is a warning, not an error: re-running
    the fetch script can legitimately produce a new digest when the upstream
    dataset is updated, and a stale manifest must not block a run.

    Raises:
        FileNotFoundError: With the exact command that downloads the data.
    """
    directory = data_dir if data_dir is not None else default_data_dir()
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Benchmark data file not found: {path}\n"
            "Download it first:\n"
            "    uv run python scripts/fetch_benchmarks.py"
        )
    _warn_on_manifest_mismatch(path, directory)
    return path


def _warn_on_manifest_mismatch(path: Path, directory: Path) -> None:
    """Log a warning when *path* does not match its MANIFEST.json entry."""
    manifest_path = directory / "MANIFEST.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Unreadable benchmark manifest at %s", manifest_path)
        return
    recorded = {
        entry.get("filename"): entry.get("sha256")
        for entry in manifest.get("entries", [])
    }
    expected = recorded.get(path.name)
    if not expected:
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        logger.warning(
            "Benchmark file %s does not match MANIFEST.json "
            "(expected %s, found %s). Re-run scripts/fetch_benchmarks.py "
            "if this was not intentional.",
            path.name,
            expected[:12],
            digest[:12],
        )
