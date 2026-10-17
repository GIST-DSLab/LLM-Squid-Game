"""Pack the one squid5 engine (and the room code built on it) for the browser: a zip Pyodide unpacks in a Web Worker.

    python web/pyodide/build_bundle.py [--out web/frontend/engine] [--check]

Writes ``<out>/squid5-engine-<sha12>.zip`` (the name carries the content hash, so a browser never mixes an old cached
bundle with a new page) and ``<out>/manifest.json`` ({file, sha256, version, files, bytes, pyodide}). The zip copies,
never edits, the repo's files and keeps the repo layout, so ``Path(__file__).parents[2]`` in web/server/signal.py and
the prompt path in squid5/core/rules.py resolve inside the bundle as they do in the repo:

    squid5/**/*.py, squid5/prompts/en/*.yaml   the engine
    web/server/{engine,signal}.py              rooms, seats, screen views, the signal page (empty package markers)
    configs/squid5/e52v16_public_sol4.yaml     the game the rooms and the signal page run
    <root>/*.py                                web/pyodide's glue: browser, replay, room_settings, modelcalls,
                                               ollama_fetch, compat, stub_transport

The zip is deterministic (sorted names, fixed times), so the same sources give the same hash; the game record names
it (``engine.bundle``) and tools/arena/verify_games.py compares it with the repo's. The output folder is build output
(not committed); the Pages workflow builds it into the site.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PYODIDE_VERSION = "314.0.7"  # the browser's Pyodide (Python 3.14); engine_worker.js and package.json pin the same
GLUE = ("browser.py", "replay.py", "room_settings.py", "modelcalls.py", "ollama_fetch.py", "compat.py",
        "stub_transport.py")
CONFIG = REPO / "configs" / "squid5" / "e52v16_public_sol4.yaml"
DEFAULT_OUT = REPO / "web" / "frontend" / "engine"


def members() -> list[tuple[str, bytes]]:
    """(name in the zip, bytes) for every file, sorted by name."""
    out: dict[str, bytes] = {}
    eng = REPO / "squid5"
    for p in sorted(eng.rglob("*.py")):
        if "__pycache__" not in p.parts:
            out["squid5/" + p.relative_to(eng).as_posix()] = p.read_bytes()
    for p in sorted((eng / "prompts" / "en").glob("*.yaml")):  # rules.py reads trim_v19.yaml at import
        out["squid5/" + p.relative_to(eng).as_posix()] = p.read_bytes()
    out["web/__init__.py"] = b""
    out["web/server/__init__.py"] = b""
    for name in ("engine.py", "signal.py"):
        out[f"web/server/{name}"] = (REPO / "web" / "server" / name).read_bytes()
    out["configs/squid5/" + CONFIG.name] = CONFIG.read_bytes()
    for name in GLUE:
        out[name] = (HERE / name).read_bytes()
    return sorted(out.items())


def build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in members():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return buf.getvalue()


def bundle_sha() -> str:
    """The sha256 of the bundle the repo's sources make now (what a game record's ``engine.bundle`` should be)."""
    return hashlib.sha256(build_zip()).hexdigest()


def manifest(data: bytes) -> dict:
    from web.server.engine import VERSION  # noqa: PLC0415 - the repo root is on sys.path (main)

    sha = hashlib.sha256(data).hexdigest()
    return {"file": f"squid5-engine-{sha[:12]}.zip", "sha256": sha, "bundle": sha[:12], "version": VERSION,
            "files": len(members()), "bytes": len(data), "pyodide": PYODIDE_VERSION, "packages": ["pyyaml"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="exit 1 unless <out>/manifest.json matches the sources")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(REPO))
    data = build_zip()
    man = manifest(data)
    mpath = a.out / "manifest.json"
    if a.check:
        old = json.loads(mpath.read_text()) if mpath.exists() else {}
        ok = old.get("sha256") == man["sha256"] and (a.out / man["file"]).exists()
        print("bundle: up to date" if ok else f"bundle: stale ({old.get('bundle')} -> {man['bundle']})")
        return 0 if ok else 1
    a.out.mkdir(parents=True, exist_ok=True)
    for old in a.out.glob("squid5-engine-*.zip"):
        if old.name != man["file"]:
            old.unlink()
    (a.out / man["file"]).write_bytes(data)
    mpath.write_text(json.dumps(man, indent=1) + "\n")
    print(f"bundle: {man['file']} ({man['files']} files, {man['bytes'] / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
