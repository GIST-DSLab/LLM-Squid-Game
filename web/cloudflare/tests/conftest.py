"""CPython tests of the Worker's Python: the repo's own squid5 and web/server (no vendored copy), plus src/."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, HERE.parent / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
