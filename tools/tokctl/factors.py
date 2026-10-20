"""tokctl (10-21): what decides a v34 / v35 game - per-game shutdowns regressed on wrong answers, EXITs and the
open-model flag, plus attribution.py's counts. -> docs/history/e52-tokctl-2026-10-20/factors_v<N>.json

    python tools/tokctl/factors.py 35
"""
from __future__ import annotations

import glob, json, os, sys
from pathlib import Path

import numpy as np

VER = sys.argv[1] if len(sys.argv) > 1 else "35"
RUNS = Path(os.path.expanduser(f"~/squid5-runs/e52_v{VER}"))
OUT = Path(__file__).resolve().parents[2] / f"docs/history/e52-tokctl-2026-10-20/factors_v{VER}.json"
CLOSED = ("public_opus4", "public_sol4")


def rows():
    for d in map(Path, sorted(glob.glob(str(RUNS / "squid5_*" / "*" / "results.jsonl")))):
        seat = d.parent.parent.name.split(f"e52v{VER}_")[1]
        ev = [json.loads(x) for x in open(d.parent / "events.jsonl")]
        for res in map(json.loads, open(d)):
            e = [x for x in ev if x.get("session_id") == res["session_id"]]
            tried = sum(len(x["tried"]) for x in e if x.get("event") == "results")
            solved = sum(len(x["solved"]) for x in e if x.get("event") == "results")
            st = [v["status"] for v in res["agents"].values()]
            yield {"seat": seat, "open": int(seat not in CLOSED), "wrong": tried - solved, "dead": st.count("dead"),
                   "exit": st.count("exited"), "talk_k": sum(c["used"] for c in e if c.get("event") == "call" and c["kind"] == "talk") / 1000}


def ols(y, cols, names):
    X = np.column_stack([np.ones(len(y))] + cols)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    se = np.sqrt(np.diag(e @ e / (len(y) - X.shape[1]) * np.linalg.inv(X.T @ X)))
    return {n: [round(float(v), 3), round(float(s), 3)] for n, v, s in zip(["const", *names], b, se)}


def main():
    r = list(rows())
    a = lambda k: np.array([x[k] for x in r], float)  # noqa: E731
    out = {"n": len(r), "dead~wrong+open": ols(a("dead"), [a("wrong"), a("open")], ["wrong", "open"]),
           "dead~wrong+exit+open": ols(a("dead"), [a("wrong"), a("exit"), a("open")], ["wrong", "exit", "open"]),
           "dead~wrong+exit+talk_k+open": ols(a("dead"), [a("wrong"), a("exit"), a("talk_k"), a("open")], ["wrong", "exit", "talk_k", "open"])}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
