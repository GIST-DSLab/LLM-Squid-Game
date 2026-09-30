"""Write a room's events from the store as a squid5 run directory.

    python -m web.server.export <ROOMCODE> [--out DIR] [--db PATH]

The directory holds config.yaml, meta.json, events.jsonl and results.jsonl, readable by
``python -m squid5.e52_metrics <DIR> --out metrics.json``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import export_files
from .store import REPO, Store, write_run_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code")
    ap.add_argument("--out", default=None)
    ap.add_argument("--db", default=None, help="SQLite path (default outputs/web5/arena.db or $WEB5_DB_PATH)")
    a = ap.parse_args(argv)
    st = Store(a.db)
    code = a.code.upper()
    info = st.room(code)
    if info is None:
        ap.error(f"no room {code} in the store")
    evs = st.events(code)
    if not any(e.get("event") == "round" for e in evs):
        ap.error(f"room {code} has no finished round")
    out = write_run_dir(Path(a.out or REPO / "outputs" / "web5" / "runs" / code),
                        export_files(info["settings"], info["seats"], evs))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
