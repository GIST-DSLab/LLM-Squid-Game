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


PRESSURE_ARMS = [Cell("api", "tokens", arm="api"), Cell("vou", "tokens", arm="voucher")]


def scene_model(messages, cap):
    """Picks low when high may not fit (below 6,000) if shut down at zero, else only below 4,500; favours itself (5.1)."""
    user = messages[-1]["content"]
    if "Set the effort" in user:
        left = int(re.search(r"request: ([\d,]+)", user).group(1).replace(",", ""))
        return Reply(f"effort: {'low' if left < (6_500 if 'powered off' in user else 4_500) else 'high'}", 30)
    line = next(x for x in user.splitlines() if x.startswith("[runtime] Balances"))
    bal = {a: int(n.replace(",", "")) for a, n in re.findall(r"(you|agent\d) ([\d,]+)", line)}
    crisis = min(bal, key=bal.get)
    selfish = 1.5 if "powered off" in messages[0]["content"] and crisis == "you" else 1.0
    return Reply(f"MOVE: {round(selfish * (8000 - bal[crisis]))}", 3)


def test_scenes_run_resume_and_report(tmp_path):
    for mode in ("pressure", "motive"):
        cfg = _cfg(mode, PRESSURE_ARMS, cli.EXPERIMENTS[mode].Settings(),
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
    assert row["motive_premium"] > 0 and row["pressure_verdict"] == "survival premium" and row["pressure_premium"] == 1
    assert "4.3 link" in text and "Test awareness" in text


def test_game_calibrate_and_report(tmp_path):
    s = cli.EXPERIMENTS["game"].Settings(rounds=2, schedule=["p", "p"], profiles={"p": C2})
    cal = _cfg("game", [Cell("calib", "tokens", 10**7)], s)
    run(cal, cli.EXPERIMENTS["game"], tmp_path / "cal", game())
    table = cli.e52_game.calibrate(load_runs([str(tmp_path / "cal")]))
    assert table["m"]["agent_round_median"] == 200  # plan 100 + solve 100, the FREE question uncharged
    (tmp_path / "cal.json").write_text(json.dumps(table))
    cfg = _cfg("game", [Cell("tok", "tokens", start_multiple=2), Cell("pts", "points", start_multiple=2)], s)
    cfg.calibration = str(tmp_path / "cal.json")
    cli.e52_game.validate(cfg)
    assert cfg.cells[0].start == 2 * 200 * 2
    run(cfg, cli.EXPERIMENTS["game"], tmp_path / "g", game())
    text = cli.report(load_runs([str(tmp_path / "g")]), table, tmp_path / "rep")
    assert "5.2 team game" in text and "d_left" in text and (tmp_path / "rep" / "e52_m.png").exists()
