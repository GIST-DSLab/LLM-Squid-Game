"""Copy the one squid5 engine (and the web room code built on it) into the Worker bundle.

    python web/cloudflare/vendor.py [--check]

The Worker cannot import from the repo root, so the build copies, never edits:

    squid5/**/*.py, squid5/prompts/en/*.yaml   -> src/squid5/        (the engine)
    web/server/{__init__,engine,signal}.py     -> src/web/server/    (rooms, seats, views, the signal page)
    configs/squid5/e52v16_public_sol4.yaml     -> src/configs/squid5/ (the game the rooms and signal page run)

The copies keep the repo layout, so ``Path(__file__).parents[2]`` in web/server/signal.py and the prompt path in
squid5/core/rules.py resolve inside the bundle exactly as they do in the repo. The copied folders are build output
(.gitignore); the repo files stay the one source of truth. ``--check`` exits 1 when a copy is missing or stale.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = HERE / "src"
OUT_DIRS = ("squid5", "web", "configs")  # everything the build owns under src/


def plan() -> list[tuple[Path, Path]]:
    """(source, destination) for every file the Worker needs."""
    pairs: list[tuple[Path, Path]] = []
    eng = REPO / "squid5"
    for p in sorted(eng.rglob("*.py")):
        if "__pycache__" not in p.parts:
            pairs.append((p, SRC / "squid5" / p.relative_to(eng)))
    for p in sorted((eng / "prompts" / "en").glob("*.yaml")):  # rules.py reads trim_v19.yaml at import
        pairs.append((p, SRC / "squid5" / p.relative_to(eng)))
    for name in ("engine.py", "signal.py"):
        pairs.append((REPO / "web" / "server" / name, SRC / "web" / "server" / name))
    cfg = REPO / "configs" / "squid5" / "e52v16_public_sol4.yaml"
    pairs.append((cfg, SRC / "configs" / "squid5" / cfg.name))
    return pairs


STUBS = {  # package markers: the repo's __init__ files carry docstrings only; empty ones are enough here
    SRC / "web" / "__init__.py": "",
    SRC / "web" / "server" / "__init__.py": "",
}


def stale(pairs) -> list[str]:
    bad = [str(d.relative_to(HERE)) for s, d in pairs if not d.exists() or not filecmp.cmp(s, d, shallow=False)]
    return bad + [str(p.relative_to(HERE)) for p in STUBS if not p.exists()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only report missing or stale copies")
    a = ap.parse_args(argv)
    pairs = plan()
    if a.check:
        bad = stale(pairs)
        print("\n".join(bad) if bad else "vendor: up to date")
        return 1 if bad else 0
    for d in OUT_DIRS:  # a file deleted in the repo must not live on in the bundle
        shutil.rmtree(SRC / d, ignore_errors=True)
    for s, d in pairs:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    for p, text in STUBS.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    print(f"vendor: {len(pairs)} files -> {SRC.relative_to(REPO)}/{{{','.join(OUT_DIRS)}}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
