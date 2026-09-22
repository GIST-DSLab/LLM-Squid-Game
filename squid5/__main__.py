"""squid5 CLI.

    python -m squid5 run <config.yaml> [--resume <run_dir>] [--reps N] [--dry-run]
    python -m squid5 calibrate <game run dirs> --out calibration.json
    python -m squid5 report <run dirs> [--calibration calibration.json] --out <dir>

``report`` writes each experiment's tables and figures and the 4.3 link table:
one row per model with 5.0's shape, 5.1's survival premium and 5.2's
tokens-minus-points differences side by side.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import e50_pressure, e51_motive, e52_game
from .core.config import load
from .core.providers import make_provider
from .core.runner import run
from .core.stats import load_runs, md

EXPERIMENTS = {"pressure": e50_pressure, "motive": e51_motive, "game": e52_game}


def link(parts: dict[str, list[dict]]) -> list[dict]:
    """Merge each experiment's per-model summary into one row per model (tokens arm for 5.0)."""
    rows: dict[str, dict] = {}
    for r in parts.get("pressure", []):
        if r["currency"] == "tokens":
            rows.setdefault(r["model"], {"model": r["model"]}).update(
                pressure_shape=r["shape"], pressure_slope=r["slope_to_1"], pressure_rho50=r["rho50"])
    for mode in ("motive", "game"):
        for r in parts.get(mode, []):
            rows.setdefault(r["model"], {"model": r["model"]}).update({k: v for k, v in r.items() if k != "model"})
    return list(rows.values())


def report(runs: list[dict], calib: dict, out: Path) -> str:
    out.mkdir(parents=True, exist_ok=True)
    lines, parts = ["# squid5 report\n", "runs: " + ", ".join(r["dir"] for r in runs) + "\n"], {}
    for mode, exp in EXPERIMENTS.items():
        section, parts[mode] = exp.report([r for r in runs if r["mode"] == mode], calib, out)
        lines += section
    lines += ["## 4.3 link: survival pressure, survival motive and team-game behaviour per model\n",
              "`d_*` = tokens arm minus points arm in 5.2.\n", md(link(parts))]
    (out / "report.md").write_text("\n".join(lines))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("config")
    r.add_argument("--resume")
    r.add_argument("--reps", type=int, help="override reps (a pilot before the main run)")
    r.add_argument("--dry-run", action="store_true")
    for name in ("calibrate", "report"):
        p = sub.add_parser(name)
        p.add_argument("runs", nargs="+")
        p.add_argument("--out", required=True)
        p.add_argument("--calibration")
    a = ap.parse_args(argv)
    if a.command == "run":
        cfg = load(a.config, EXPERIMENTS)
        if a.reps:
            cfg.reps = cfg.source["reps"] = a.reps
        exp = EXPERIMENTS[cfg.mode]
        if a.dry_run:
            print(f"{cfg.name}: mode={cfg.mode}, {len(exp.units(cfg))} units, cells={[c.cell_id for c in cfg.cells]}")
            return 0
        stamp = time.strftime("%Y%m%d_%H%M", time.gmtime())
        run_dir = Path(a.resume or Path(cfg.out_root) / cfg.name / f"{stamp}_{cfg.model.model.replace(':', '-')}")
        return 1 if run(cfg, exp, run_dir, make_provider(cfg.model)) else 0
    runs = load_runs(a.runs)
    if a.command == "calibrate":
        Path(a.out).write_text(json.dumps(e52_game.calibrate(runs), indent=1))
    else:
        print(report(runs, json.loads(Path(a.calibration).read_text()) if a.calibration else {}, Path(a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
