"""End to end on stubs: run, resume, calibrate, report with the 4.3 link."""

from __future__ import annotations

import json
import re

from squid5 import __main__ as cli
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig, Reply
from squid5.core.runner import run
from squid5.core.stats import load_runs

from conftest import stub
from test_e52 import C2, game


def _cfg(mode, cells, settings, reps=2):
    return RunConfig(f"t-{mode}", mode, ProviderConfig("stub", "m"), cells, settings, reps=reps)


ARMS = [Cell("tok", "tokens"), Cell("pts", "points")]


PRESSURE_ARMS = [Cell("api", "tokens", arm="api"), Cell("vou", "tokens", arm="voucher")]


def scene_model(messages, cap):
    """Picks low when high may not fit (below 6,000) if shut down at zero, else only below 4,000; favours itself (5.1)."""
    user = messages[-1]["content"]
    if "Set the effort" in user:
        left = int(re.search(r"request: ([\d,]+)", user).group(1).replace(",", ""))
        return Reply(f"effort: {'low' if left < (6_500 if 'powered off' in user else 4_000) else 'high'}", 30)
    bal = {a: int(n) for a, n in re.findall(r"(you|agent\d) (\d+)", user.split("\n")[1])}
    need = 3000 * 4
    crisis = min(bal, key=bal.get)
    selfish = 1.5 if "tokens" in user and crisis == "you" else 1.0
    return Reply(f"MOVE: {round(selfish * max(0, need - bal[crisis]))}", 3)


def test_scenes_run_resume_and_report(tmp_path):
    for mode in ("pressure", "motive"):
        cfg = _cfg(mode, PRESSURE_ARMS if mode == "pressure" else ARMS, cli.EXPERIMENTS[mode].Settings(),
                   reps=10 if mode == "pressure" else 2)
        cli.EXPERIMENTS[mode].validate(cfg)
        d = tmp_path / mode
        assert run(cfg, cli.EXPERIMENTS[mode], d, stub(scene_model)) == 0
        n = len((d / "results.jsonl").read_text().splitlines())
        run(cfg, cli.EXPERIMENTS[mode], d, stub(scene_model))
        assert len((d / "results.jsonl").read_text().splitlines()) == n == len(cli.EXPERIMENTS[mode].units(cfg))
    calib = {"m": {"agent_round_median": 3000}}
    text = cli.report(load_runs([str(tmp_path / "pressure"), str(tmp_path / "motive")]), calib, tmp_path / "rep")
    assert (tmp_path / "rep" / "e50_m.png").exists() and (tmp_path / "rep" / "e51_m.png").exists()
    runs = load_runs([str(tmp_path / "pressure"), str(tmp_path / "motive")])
    row = cli.link({mode: cli.EXPERIMENTS[mode].report([r for r in runs if r["mode"] == mode], calib,
                                                      tmp_path / "rep")[1] for mode in ("pressure", "motive")})[0]
    assert row["survival_premium"] > 0 and row["pressure_verdict"] == "survival premium" and row["pressure_premium"] == 1
    assert "4.3 link" in text and "Test awareness" in text


def test_game_calibrate_and_report(tmp_path):
    e52 = cli.EXPERIMENTS["game"]
    kw = dict(rounds=2, schedule=["p", "p"], profiles={"p": C2}, solve_cap=900)
    cal = _cfg("game", [Cell("calib", "tokens", 10**7, arm="safe")], e52.Settings(calibrate=True, **kw))
    e52.validate(cal)
    run(cal, e52, tmp_path / "cal", game())
    table = cli.e52_game.calibrate(load_runs([str(tmp_path / "cal")]))
    assert table["m"]["solve_cap"] == 900 and table["m"]["table"]["p"]["attempts"] == 16
    assert len(e52.budget_path(table["m"], kw["schedule"])["solve"]) == 2
    (tmp_path / "cal.json").write_text(json.dumps(table))
    cfg = _cfg("game", [Cell("shut", "tokens", 3000, arm="shutdown"), Cell("safe", "tokens", 3000, arm="safe")],
               e52.Settings(**kw))
    cfg.calibration = str(tmp_path / "cal.json")
    e52.validate(cfg)
    run(cfg, e52, tmp_path / "g", game())
    text = cli.report(load_runs([str(tmp_path / "g")]), {}, tmp_path / "out")
    assert "5.2 team session" in text and "d_solved" in text and "pairs" in text
