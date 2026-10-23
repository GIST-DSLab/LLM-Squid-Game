"""The game-log snapshot the deployed server reads (``web/data/runs``, WEB5_MONITOR_ROOT in the API image).

    python3 web/tools/runs_snapshot.py add e52_v34 e52_v35 [--from ~/squid5-runs] [--to web/data/runs]
    python3 web/tools/runs_snapshot.py unpack web/data/runs        # the Dockerfile runs this at build time

``add`` copies every finished-or-not run dir (one that holds events.jsonl) under each named folder of the run root,
skipping any path part that starts with ``_`` (``_failed``, ``_stopped``, ``_backups``: attempts moved out of the
run roots, as in the earlier snapshots). Only config.yaml, meta.json and results.jsonl are copied as they are;
events.jsonl is stored as events.jsonl.xz because the model prompts it logs (``call.user``) repeat from call to call
(a 141 MB file packs to under 1 MB, and GitHub refuses files over 100 MB). Runs already in the snapshot, packed or
not, are left alone. ``unpack`` turns every ``*.xz`` back into the file the game-log viewer reads (it seeks by byte
offset, so it needs the plain file) and removes the ``.xz``.
"""

from __future__ import annotations

import argparse
import lzma
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO / "web" / "data" / "runs"
RUN_ROOT = Path.home() / "squid5-runs"
PLAIN = ("config.yaml", "meta.json", "results.jsonl")
EVENTS = "events.jsonl"
PRESET = 9  # lzma preset: a 64 MiB dictionary spans many repeated prompts


def run_dirs(top: Path) -> list[Path]:
    """Run dirs (holding events.jsonl) under ``top``, without any ``_*`` path part below it."""
    return sorted(p.parent for p in top.rglob(EVENTS)
                  if not any(part.startswith("_") for part in p.parent.relative_to(top).parts))


def in_snapshot(dest: Path) -> bool:
    return (dest / EVENTS).is_file() or (dest / f"{EVENTS}.xz").is_file()


def pack(src: Path, dest: Path) -> int:
    """Copy one run dir into the snapshot; returns the bytes written."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in PLAIN:
        if (src / name).is_file():
            shutil.copy2(src / name, dest / name)
    tmp = dest / f"{EVENTS}.xz.part"
    with (src / EVENTS).open("rb") as f, lzma.open(tmp, "wb", preset=PRESET) as out:
        shutil.copyfileobj(f, out, 1 << 20)
    tmp.replace(dest / f"{EVENTS}.xz")
    return sum(p.stat().st_size for p in dest.iterdir())


def add(names: list[str], root: Path, snap: Path, workers: int) -> list[str]:
    jobs = []
    for name in names:
        top = root / name
        if not top.is_dir():
            raise SystemExit(f"no such run folder: {top}")
        for d in run_dirs(top):
            rel = d.relative_to(root)
            if not in_snapshot(snap / rel):
                jobs.append((d, snap / rel))
    if workers <= 1 or len(jobs) <= 1:
        sizes = [pack(d, dest) for d, dest in jobs]
    else:
        with ProcessPoolExecutor(workers) as ex:
            sizes = list(ex.map(pack, *zip(*jobs)))
    for (d, dest), size in zip(jobs, sizes):
        print(f"{dest.relative_to(snap)}  {size / 1e6:.2f} MB")
    return [str(dest.relative_to(snap)) for _, dest in jobs]


def unpack(snap: Path) -> int:
    n = 0
    for xz in sorted(snap.rglob("*.xz")):
        plain = xz.with_suffix("")
        with lzma.open(xz, "rb") as f, plain.open("wb") as out:
            shutil.copyfileobj(f, out, 1 << 20)
        st = xz.stat()
        os.utime(plain, (st.st_atime, st.st_mtime))  # a fresh mtime would show the run as live in the viewer
        xz.unlink()
        n += 1
    return n


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="copy run folders from the run root into the snapshot")
    a.add_argument("names", nargs="+", help="top-level folders of the run root, e.g. e52_v35")
    a.add_argument("--from", dest="root", type=Path, default=RUN_ROOT)
    a.add_argument("--to", dest="snap", type=Path, default=SNAPSHOT)
    a.add_argument("--workers", type=int, default=4)
    u = sub.add_parser("unpack", help="turn every *.xz under the snapshot back into the plain file")
    u.add_argument("snap", type=Path, nargs="?", default=SNAPSHOT)
    args = ap.parse_args(argv)
    if args.cmd == "add":
        added = add(args.names, args.root.expanduser(), args.snap, args.workers)
        print(f"{len(added)} run(s) added", file=sys.stderr)
    else:
        print(f"{unpack(args.snap)} file(s) unpacked", file=sys.stderr)


if __name__ == "__main__":
    main()
