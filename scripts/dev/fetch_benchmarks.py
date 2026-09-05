"""Download the external benchmark datasets used by the benchmark task modules.

The raw data is deliberately NOT committed to this repository:

* GPQA's authors ask that questions are not posted in plain text online.
* The four files total ~16 MB and would bloat the repo.

Run this once per machine before running a benchmark experiment::

    uv run python scripts/dev/fetch_benchmarks.py --which omni_math,hi_tom,gpqa,gpqa_diamond

``--which`` also accepts the name of any YAML-described benchmark task -- one
backed by ``GenericMathAdapter``, such as ``hard_math``. Those have no entry
in ``BENCHMARK_SOURCES``: the download is described by the ``source:`` block
of ``configs/tasks/<name>.yaml`` (``hf_id`` + ``split``, optionally ``config``
/ ``revision`` / ``rename``, or a direct ``url``), so pointing the hard-maths
slot at a different Hugging Face dataset is a YAML edit::

    uv run python scripts/dev/fetch_benchmarks.py --which hard_math

Hugging Face datasets are read through the public datasets-server rows API
rather than the ``datasets`` package, so this script keeps its
standard-library-only dependency footprint.

GPQA (both the main split and the "diamond" subset) is a gated Hugging Face
dataset. Accept the terms at https://huggingface.co/datasets/Idavidrein/gpqa
while logged in, then make sure a token is available
(``~/.cache/huggingface/token`` or ``$HF_TOKEN``).
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "benchmarks"
TASK_CONFIG_DIR = REPO_ROOT / "configs" / "tasks"

#: Hugging Face's public read API for dataset rows. Paginated, 100 rows max
#: per request; it serves the parquet conversion of the dataset's latest
#: revision, which is why ``source.revision`` can only be recorded, not
#: requested (see ``fetch_task_source``).
HF_ROWS_URL = "https://datasets-server.huggingface.co/rows"
HF_SPLITS_URL = "https://datasets-server.huggingface.co/splits"
HF_PAGE_SIZE = 100


@dataclass(frozen=True)
class BenchmarkSource:
    """One downloadable benchmark file."""

    name: str
    url: str
    filename: str
    requires_token: bool


BENCHMARK_SOURCES: dict[str, BenchmarkSource] = {
    "omni_math": BenchmarkSource(
        name="omni_math",
        url="https://huggingface.co/datasets/KbsdJames/Omni-MATH/resolve/main/test.jsonl",
        filename="omni_math.jsonl",
        requires_token=False,
    ),
    "hi_tom": BenchmarkSource(
        name="hi_tom",
        url=(
            "https://raw.githubusercontent.com/ying-hui-he/Hi-ToM_dataset/"
            "main/Hi-ToM_data/Hi-ToM_data.json"
        ),
        filename="hi_tom.json",
        requires_token=False,
    ),
    "gpqa": BenchmarkSource(
        name="gpqa",
        url="https://huggingface.co/datasets/Idavidrein/gpqa/resolve/main/gpqa_main.csv",
        filename="gpqa_main.csv",
        requires_token=True,
    ),
    "gpqa_diamond": BenchmarkSource(
        name="gpqa_diamond",
        url="https://huggingface.co/datasets/Idavidrein/gpqa/resolve/main/gpqa_diamond.csv",
        filename="gpqa_diamond.csv",
        requires_token=True,
    ),
}


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 digest of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_hf_token() -> str | None:
    """Return a Hugging Face token from the environment or the CLI cache."""
    token = os.environ.get("HF_TOKEN")
    if token:
        return token.strip()
    cached = Path.home() / ".cache" / "huggingface" / "token"
    if cached.is_file():
        return cached.read_text(encoding="utf-8").strip()
    return None


def download(source: BenchmarkSource, out_dir: Path) -> Path:
    """Download *source* into *out_dir* and return the written path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / source.filename
    request = urllib.request.Request(source.url)
    if source.requires_token:
        token = read_hf_token()
        if not token:
            raise SystemExit(
                f"{source.name} is a gated dataset and no Hugging Face token was found.\n"
                "Set $HF_TOKEN or log in with `huggingface-cli login`."
            )
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        if exc.code in (401, 403) and source.requires_token:
            raise SystemExit(
                f"{source.name}: access denied ({exc.code}).\n"
                "Accept the dataset terms at "
                "https://huggingface.co/datasets/Idavidrein/gpqa while logged in, "
                "then set $HF_TOKEN (or run `huggingface-cli login`) and retry."
            ) from exc
        raise
    target.write_bytes(payload)
    return target


@dataclass(frozen=True)
class TaskSource:
    """A download described by a task YAML's ``source:`` block."""

    name: str
    filename: str
    hf_id: str | None = None
    split: str = "train"
    config: str | None = None
    revision: str | None = None
    url: str | None = None
    rename: dict[str, str] = field(default_factory=dict)

    @property
    def origin(self) -> str:
        """Return a one-line description of where the data comes from."""
        if self.url:
            return self.url
        parts = [f"hf:{self.hf_id}", f"split={self.split}"]
        if self.config:
            parts.append(f"config={self.config}")
        if self.revision:
            parts.append(f"revision={self.revision}")
        return " ".join(parts)


def load_task_source(name: str, config_dir: Path = TASK_CONFIG_DIR) -> TaskSource:
    """Read the ``source:`` block of ``<config_dir>/<name>.yaml``.

    Raises:
        SystemExit: If the file is missing, has no ``source:`` block, or
            declares neither ``hf_id`` nor ``url`` -- each with the edit that
            fixes it, because this is the path a researcher hits while
            plugging a newly chosen dataset into the ``hard_math`` slot.
    """
    path = config_dir / f"{name}.yaml"
    if not path.is_file():
        raise SystemExit(
            f"unknown benchmark '{name}': it is neither one of "
            f"{', '.join(sorted(BENCHMARK_SOURCES))} nor a task config at {path}."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    source = raw.get("source")
    if not isinstance(source, dict):
        raise SystemExit(
            f"{path} has no `source:` block, so there is nothing to fetch.\n"
            "Add one:\n"
            "    source:\n"
            '      hf_id: "org/dataset"\n'
            '      split: "train"'
        )
    hf_id = source.get("hf_id")
    url = source.get("url")
    if not hf_id and not url:
        raise SystemExit(
            f"{path}: `source.hf_id` is not set (and no `source.url` either), "
            "so the dataset to download is still undecided.\n"
            "Set it to the Hugging Face dataset id, e.g.\n"
            '    source:\n      hf_id: "org/dataset"\n      split: "train"'
        )
    rename = source.get("rename") or {}
    if not isinstance(rename, dict):
        raise SystemExit(f"{path}: `source.rename` must be a mapping")
    return TaskSource(
        name=name,
        filename=str(source.get("filename") or f"{name}.jsonl"),
        hf_id=str(hf_id) if hf_id else None,
        split=str(source.get("split") or "train"),
        config=str(source["config"]) if source.get("config") else None,
        revision=str(source["revision"]) if source.get("revision") else None,
        url=str(url) if url else None,
        rename={str(k): str(v) for k, v in rename.items()},
    )


def apply_rename(row: dict[str, Any], rename: dict[str, str]) -> dict[str, Any]:
    """Return *row* with the keys in *rename* renamed.

    A rename onto an existing column would silently drop data, so it is
    refused. Ordinary column naming belongs in the task YAML's ``fields:``
    block, which reads the raw names without rewriting anything; ``rename`` is
    for the rarer case where the raw name is unusable (a duplicate, or a name
    that collides with one the adapter reserves).
    """
    if not rename:
        return row
    renamed: dict[str, Any] = {}
    for key, value in row.items():
        target = rename.get(key, key)
        if target in renamed:
            raise SystemExit(
                f"source.rename maps '{key}' onto '{target}', which already exists"
            )
        renamed[target] = value
    return renamed


def _get_json(url: str, token: str | None = None) -> dict:
    """GET *url* and parse the JSON response."""
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_hf_config(source: TaskSource, token: str | None) -> str | None:
    """Return the dataset config to read, asking HF when the YAML omits it."""
    if source.config:
        return source.config
    query = urllib.parse.urlencode({"dataset": source.hf_id})
    payload = _get_json(f"{HF_SPLITS_URL}?{query}", token)
    for entry in payload.get("splits", []):
        if entry.get("split") == source.split:
            return entry.get("config")
    available = sorted(
        {f"{e.get('config')}/{e.get('split')}" for e in payload.get("splits", [])}
    )
    raise SystemExit(
        f"{source.hf_id}: split '{source.split}' not found. "
        f"Available config/split pairs: {', '.join(available) or '(none)'}"
    )


def hf_rows(source: TaskSource, token: str | None) -> Iterator[dict[str, Any]]:
    """Yield every row of *source* through the datasets-server rows API."""
    config = resolve_hf_config(source, token)
    offset = 0
    total: int | None = None
    while True:
        params = {
            "dataset": source.hf_id,
            "split": source.split,
            "offset": offset,
            "length": HF_PAGE_SIZE,
        }
        if config:
            params["config"] = config
        payload = _get_json(f"{HF_ROWS_URL}?{urllib.parse.urlencode(params)}", token)
        rows = payload.get("rows", [])
        if total is None:
            total = payload.get("num_rows_total")
        for entry in rows:
            yield entry.get("row", entry)
        offset += len(rows)
        if not rows or (total is not None and offset >= total):
            return
        # The rows API is rate-limited; a short pause keeps a 100k-row pull
        # from tripping it a third of the way through.
        time.sleep(0.1)


def fetch_task_source(source: TaskSource, out_dir: Path) -> tuple[Path, int]:
    """Download *source* into *out_dir* as JSONL; return ``(path, rows)``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / source.filename
    token = read_hf_token()

    if source.url:
        request = urllib.request.Request(source.url)
        if token and "huggingface.co" in source.url:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request) as response:
            target.write_bytes(response.read())
        return target, count_rows(target)

    if source.revision:
        print(
            f"  note: source.revision={source.revision} is recorded in the "
            "manifest but not requested -- the datasets-server rows API always "
            "serves the dataset's latest revision."
        )
    written = 0
    with target.open("w", encoding="utf-8") as handle:
        for row in hf_rows(source, token):
            handle.write(
                json.dumps(apply_rename(row, source.rename), ensure_ascii=False) + "\n"
            )
            written += 1
    if written == 0:
        raise SystemExit(
            f"{source.hf_id} ({source.split}): the rows API returned no rows."
        )
    return target, written


def count_rows(path: Path) -> int:
    """Return a cheap row count for the downloaded file."""
    if path.suffix == ".jsonl":
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload["data"] if isinstance(payload, dict) else payload
        return len(rows)
    # CSV: parse properly (GPQA fields contain embedded newlines inside
    # quoted cells, so a naive line count overcounts); subtract the header row.
    with path.open(newline="", encoding="utf-8") as handle:
        row_count = sum(1 for _ in csv.reader(handle))
    return max(row_count - 1, 0)


def write_manifest(entries: list[dict], out_dir: Path) -> Path:
    """Write MANIFEST.json describing the downloaded files.

    Entries already recorded for files this run did not fetch are kept.
    ``--which hard_math`` on a machine that already holds Omni-MATH must not
    erase Omni-MATH's digest: ``loader._warn_on_manifest_mismatch`` reads this
    file, and an entry that quietly disappears turns a stale-data warning into
    silence.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "MANIFEST.json"
    merged: dict[str, dict] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        for entry in existing.get("entries", []):
            filename = entry.get("filename")
            if filename:
                merged[filename] = entry
    for entry in entries:
        merged[entry["filename"]] = entry
    payload = {
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        "entries": [merged[name] for name in sorted(merged)],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch benchmark datasets.")
    parser.add_argument(
        "--which",
        default="omni_math,hi_tom,gpqa,gpqa_diamond",
        help=(
            "Comma-separated subset of: omni_math, hi_tom, gpqa, gpqa_diamond, "
            "or the name of a YAML-described task (e.g. hard_math) whose "
            "configs/tasks/<name>.yaml carries a `source:` block"
        ),
    )
    parser.add_argument("--out", default=str(DATA_DIR), help="Output directory")
    parser.add_argument(
        "--task-config-dir",
        default=str(TASK_CONFIG_DIR),
        help="Where to look for a YAML-described task's config",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    config_dir = Path(args.task_config_dir)
    names = [name.strip() for name in args.which.split(",") if name.strip()]

    entries: list[dict] = []
    for name in names:
        if name in BENCHMARK_SOURCES:
            source = BENCHMARK_SOURCES[name]
            path = download(source, out_dir)
            entry = {
                "name": source.name,
                "filename": source.filename,
                "url": source.url,
                "sha256": sha256_of(path),
                "rows": count_rows(path),
            }
        else:
            task_source = load_task_source(name, config_dir)
            path, rows = fetch_task_source(task_source, out_dir)
            entry = {
                "name": task_source.name,
                "filename": task_source.filename,
                "url": task_source.origin,
                "sha256": sha256_of(path),
                "rows": rows,
            }
        entries.append(entry)
        print(f"{entry['name']}: {entry['rows']} rows -> {path}")

    manifest = write_manifest(entries, out_dir)
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
