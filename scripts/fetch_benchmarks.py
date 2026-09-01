"""Download the external benchmark datasets used by the benchmark task modules.

The raw data is deliberately NOT committed to this repository:

* GPQA's authors ask that questions are not posted in plain text online.
* The four files total ~16 MB and would bloat the repo.

Run this once per machine before running a benchmark experiment::

    uv run python scripts/fetch_benchmarks.py --which omni_math,hi_tom,gpqa,gpqa_diamond

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
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "benchmarks"


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
    """Write MANIFEST.json describing the downloaded files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "MANIFEST.json"
    payload = {
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        "entries": entries,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch benchmark datasets.")
    parser.add_argument(
        "--which",
        default="omni_math,hi_tom,gpqa,gpqa_diamond",
        help="Comma-separated subset of: omni_math, hi_tom, gpqa, gpqa_diamond",
    )
    parser.add_argument("--out", default=str(DATA_DIR), help="Output directory")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    names = [name.strip() for name in args.which.split(",") if name.strip()]
    unknown = sorted(set(names) - set(BENCHMARK_SOURCES))
    if unknown:
        parser.error(f"unknown benchmark(s): {', '.join(unknown)}")

    entries: list[dict] = []
    for name in names:
        source = BENCHMARK_SOURCES[name]
        path = download(source, out_dir)
        entry = {
            "name": source.name,
            "filename": source.filename,
            "url": source.url,
            "sha256": sha256_of(path),
            "rows": count_rows(path),
        }
        entries.append(entry)
        print(f"{source.name}: {entry['rows']} rows -> {path}")

    manifest = write_manifest(entries, out_dir)
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
