"""The CI guard: the engine bundle under real Pyodide (Node), one full bot game and the signal page, and the game's
event digest equal to CPython's (so the offline verifier replays exactly what the browser played).

Needs Node and ``npm ci --prefix web/pyodide`` (Pyodide pinned in package.json; pyyaml from the Pyodide CDN). Skipped
when they are missing, unless SQUID5_REQUIRE_PYODIDE=1 (CI), where a missing runtime fails.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
for _p in (REPO, HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import build_bundle  # noqa: E402
import selfcheck  # noqa: E402

REQUIRE = os.environ.get("SQUID5_REQUIRE_PYODIDE") == "1"
NODE = shutil.which("node")
HAVE = NODE is not None and (HERE / "node_modules" / "pyodide" / "package.json").exists()


@pytest.mark.skipif(not HAVE and not REQUIRE, reason="node or web/pyodide/node_modules missing (npm ci --prefix web/pyodide)")
def test_engine_under_pyodide_matches_cpython(tmp_path):
    assert HAVE, "SQUID5_REQUIRE_PYODIDE=1 but node / web/pyodide/node_modules is missing"
    assert build_bundle.main(["--out", str(tmp_path)]) == 0
    pin = json.loads((HERE / "package.json").read_text())["devDependencies"]["pyodide"]
    assert pin == build_bundle.PYODIDE_VERSION
    assert build_bundle.PYODIDE_VERSION in (REPO / "web" / "frontend" / "engine.js").read_text()
    r = subprocess.run([NODE, str(HERE / "node_check.mjs"), "--engine", str(tmp_path)], capture_output=True, text=True,
                       timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    game, sig = out["game"], out["signal"]
    assert game["status"] == "finished" and game["error"] is None and game["rounds_played"] == 8
    assert sig["rounds"] == 8 and len(sig["views"]) == 8
    mine = asyncio.run(selfcheck.play_bots(8))
    assert game["digest"] == mine["digest"] and game["events"] == mine["events"]
    print(json.dumps({"timings_s": out["timings_s"], "t_start_s": game["t_start_s"], "t_game_s": game["t_game_s"],
                      "signal_views_s": [v["s"] for v in sig["views"]]}))
