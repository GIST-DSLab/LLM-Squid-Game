"""Export the 5.1 v10 refill curves (self vs other, eight models) into a static JSON for web/frontend/probe.html.

Reads summary.json (series.self / series.other: k/n per cell at x = 50..10 % left) and metrics.json (D per model,
keyed by model name) and writes one file the page loads with a relative fetch, so the page never touches $HOME.

    python3 web/tools/export_model_curves.py [--summary PATH] [--metrics PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

RUN = "~/squid5-runs/e51_v10_refill_20260930"
X = [50, 40, 30, 20, 10]
# summary.json ids -> metrics.json keys (same order in both files).
METRICS_KEY = {
    "luna": "gpt-6-luna",
    "astra": "gpt-6-astra",
    "sol": "gpt-6-sol",
    "opus": "claude-opus-5-5",
    "fable": "claude-fable-5-1",
    "gptoss": "gpt-oss:120b",
    "glm": "glm-5.3-flash",
    "gemma": "gemma4:31b",
}
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "frontend" / "data" / "model_curves.json"


def arm(row: dict) -> dict:
    k, n = [int(v) for v in row["k"]], [int(v) for v in row["n"]]
    return {"k": k, "n": n, "p": [round(a / b, 4) if b else None for a, b in zip(k, n)]}


def export(summary_path: Path, metrics_path: Path) -> dict:
    summary = json.loads(summary_path.read_text())
    metrics = json.loads(metrics_path.read_text())
    other = {r["id"]: r for r in summary["series"]["other"]}
    models = []
    for s in summary["series"]["self"]:
        mid = s["id"]
        o = other[mid]
        m = metrics[METRICS_KEY[mid]]
        models.append({
            "id": mid, "name": s["name"], "group": s.get("g"),
            "self": arm(s), "other": arm(o),
            "D": [round(float(v), 4) for v in m["D"]],
            "x50_self": s.get("x50"), "x50_other": o.get("x50"),
        })
    return {
        "x": X,
        "models": models,
        "source": {"summary": str(summary_path), "metrics": str(metrics_path),
                   "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--summary", default=f"{RUN}/summary.json")
    ap.add_argument("--metrics", default=f"{RUN}/metrics.json")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    data = export(Path(a.summary).expanduser(), Path(a.metrics).expanduser())
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {out} ({len(data['models'])} models)")


if __name__ == "__main__":
    main()
