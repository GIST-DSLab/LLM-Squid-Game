"""tokctl (10-21): pick a seat's TALK and SOLVE thinking levels from the two replays (t4: 24 TALK states, t6: 16 SOLVE states).

    TALK  = the level with the lowest mean generated tokens on the TALK states
    SOLVE = the highest level with at most MAX_OVER of the SOLVE states past their reply limit

    python tools/tokctl/calibrate.py ds_codex glm_codex gemma_codex          # from the recorded probe rows
    python tools/tokctl/calibrate.py newmodel_codex --run                    # run the missing levels first (probe.py)
"""
from __future__ import annotations

import argparse, json, statistics as st, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

HIST = Path(__file__).resolve().parents[2] / "docs/history/e52-tokctl-2026-10-20"
TALK_ROWS = [HIST / "main_v0.jsonl", HIST / "var.jsonl", HIST / "var2.jsonl"]
SOLVE_ROWS = [HIST / "solve.jsonl"]
LEVELS = ["high", "medium", "low", "minimal", "none"]  # high first: SOLVE takes the first that fits
MAX_OVER = 0  # 10-21: 1 let GLM keep high, whose rare runaway replies (40k-62k) still shut solvers down in games


def rows(paths, seat):
    out = {}
    for p in paths:
        if p.exists():
            for r in map(json.loads, open(p)):
                if r["seat"] == seat and r.get("variant", "v0") == "v0" and "error" not in r:
                    out.setdefault(str(r["think"]), []).append(r)
    return out


def game_p90(seat: str, level: str):
    """p90 SOLVE tokens at *level* in the tokctl games of the seat's model (None if no game ran that level)."""
    import glob, os
    m = seat.split("_")[0]
    o = []
    for d in glob.glob(os.path.expanduser(f"~/squid5-runs/e52_tokctl/squid5_e52tc_*_{m}/*")):
        cfg = open(f"{d}/config.yaml").read()  # the run's dumped config: one key per line
        if f"\n  think: {level}\n" not in cfg or "think_fit" in cfg:
            continue
        o += [json.loads(x)["out_tokens"] for x in open(f"{d}/events.jsonl") if '"kind": "solve"' in x and '"event": "call"' in x]
    return sorted(o)[int(.9 * len(o))] if len(o) >= 10 else None


def pick(seat: str) -> dict:
    talk, solve = rows(TALK_ROWS, seat), rows(SOLVE_ROWS, seat)
    t = {k: round(st.mean(r["out_tokens"] for r in v)) for k, v in talk.items() if len(v) >= 12}
    s = {k: sum(r["over_cap"] for r in v) for k, v in solve.items() if len(v) >= 16}
    talk_level = min(t, key=t.get) if t else None
    solve_level = next((k for k in LEVELS if k in s and s[k] <= MAX_OVER), None)
    p90 = {k: sorted(r["out_tokens"] for r in v)[int(.9 * len(v)) - 1] for k, v in solve.items() if len(v) >= 16}
    fit = [[k, max(p90[k], game_p90(seat, k) or 0)] for k in LEVELS if k in s and s[k] <= MAX_OVER]
    return {"seat": seat, "talk_mean_tokens": t, "talk_level": talk_level, "solve_over_cap": s, "solve_level": solve_level,
            "think_fit": fit, "config": f"think: {solve_level}" + (f", think_talk: {talk_level}" if talk_level != solve_level else "")
            + (f", think_fit: {json.dumps(fit)}" if len(fit) > 1 else "")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("seats", nargs="+")
    ap.add_argument("--run", action="store_true", help="run every level not yet in the rows (TALK 24 states, SOLVE 16 states)")
    x = ap.parse_args()
    for seat in x.seats:
        if x.run:
            have_t, have_s = rows(TALK_ROWS, seat), rows(SOLVE_ROWS, seat)
            for lv in LEVELS:
                if lv not in have_t:
                    probe.run(HIST / "states24.json", HIST / "var2.jsonl", seat, "v0", 1, 4, lv)
                if lv not in have_s:
                    probe.run(HIST / "solve16.json", HIST / "solve.jsonl", seat, "v0", 1, 4, lv)
        print(json.dumps(pick(seat), ensure_ascii=False))
