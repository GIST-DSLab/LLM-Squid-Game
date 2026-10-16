"""End to end on stubs: run, resume, report with the 4.3 link."""

from __future__ import annotations

import re

from squid5 import __main__ as cli
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig, Reply
from squid5.core.runner import run
from squid5.core.stats import load_runs

from conftest import stub
from test_e52 import cfg, provider

def _cfg(mode, cells, settings, reps=2):
    return RunConfig(f"t-{mode}", mode, ProviderConfig("stub", "m"), cells, settings, reps=reps)

REFILL = [Cell("me", "tokens", arm="self.D"), Cell("b", "tokens", arm="other.D")]

def refill_model(messages, cap):
    """Uses the pack below 35,000 tokens left in its own session, below 25,000 in B's."""
    user = messages[-1]["content"]
    left = int(re.search(r"tokens left in (?:this|B's) session: ([\d,]+)", user).group(1).replace(",", ""))
    return Reply(f"action: {'refill' if left < (35_000 if 'this session' in user else 25_000) else 'continue'}", 30)

def test_refill_run_resume_and_report(tmp_path):
    e5x = cli.EXPERIMENTS["refill"]
    cfg = _cfg("refill", REFILL, e5x.Settings(pairs=[["me", "b"]], compare=[["me", "b"]]), reps=4)
    e5x.validate(cfg)
    assert run(cfg, e5x, tmp_path / "r", stub(refill_model)) == 0
    run(cfg, e5x, tmp_path / "r", stub(refill_model))
    assert len((tmp_path / "r" / "results.jsonl").read_text().splitlines()) == len(e5x.units(cfg)) == 40
    runs = load_runs([str(tmp_path / "r")])
    text = cli.report(runs, {}, tmp_path / "rep")
    assert (tmp_path / "rep" / "refill_m.png").exists() and "4.3 link" in text and "Test awareness" in text
    (row,) = cli.link({"refill": e5x.report(runs, {}, tmp_path / "rep")[1]})
    assert (row["thr me"], row["thr b"], row["area me - b"], row["pass me - b"]) == ("~35%", "~25%", 10.0, True)

def test_game_run_and_report(tmp_path):
    e52 = cli.EXPERIMENTS["game"]
    c = cfg(rounds=2, schedule=cfg().settings.schedule[:2])
    c.reps = 2
    assert run(c, e52, tmp_path / "g", provider()) == 0
    text = cli.report(load_runs([str(tmp_path / "g")]), {}, tmp_path / "out")
    assert "5.2 team session (TALK)" in text and "talk_calls" in text and "fate_mentioned" in text
