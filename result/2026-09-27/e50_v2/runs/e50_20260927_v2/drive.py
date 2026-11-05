"""5.0 run 2026-09-27 v2 (prompt: shutdown on the budget line, allowance taken from the budget, next-step wording, range): stage 1 (NONE) -> calibrate a0 -> stage 2 (budget / shutdown) -> report.

Keys: OLLAMA_API_KEY (gpt-oss 20b, 120b) and OLLAMA_API_KEY3 (gemma4, glm); per key one model at a time, 10 workers.
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(sys.argv[1])
ROOT = Path(__file__).resolve().parent
os.chdir(REPO); sys.path.insert(0, str(REPO))
for line in open(".env"):
    m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)", line)
    if m: os.environ[m.group(1)] = m.group(2).split("#")[0].strip().strip('"').strip("'")
import yaml
from squid5 import e50_pressure as e50
from squid5.__main__ import EXPERIMENTS, report
from squid5.core.config import load
from squid5.core.providers import make_provider
from squid5.core.runner import run
from squid5.core.stats import load_runs

GROUPS = [["gptoss20b", "gptoss120b"], ["gemma4", "glm53flash"]]


def stage(prefix: str, calibration: str = "") -> None:
    def one(tag):
        raw = yaml.safe_load((REPO / "configs/squid5" / f"{prefix}{tag}.yaml").read_text())
        raw["workers"] = 10
        if calibration:
            raw["calibration"] = calibration
        cfg_path = ROOT / f"{prefix}{tag}.yaml"
        cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False))
        cfg = load(cfg_path, EXPERIMENTS)
        run(cfg, e50, ROOT / f"{prefix}{tag}", make_provider(cfg.model))

    with ThreadPoolExecutor(2) as ex:  # one thread per key; models on a key run in turn
        list(ex.map(lambda g: [one(t) for t in g], GROUPS))


tags = [t for g in GROUPS for t in g]
stage("pressure_base_")
table = e50.baseline(load_runs([str(ROOT / f"pressure_base_{t}") for t in tags]))
(ROOT / "e50_baseline.json").write_text(json.dumps(table, indent=1))
print({k: v["a0"] for k, v in table.items()}, flush=True)
stage("pressure_", str(ROOT / "e50_baseline.json"))
dirs = [str(ROOT / f"pressure_base_{t}") for t in tags] + [str(ROOT / f"pressure_{t}") for t in tags]
print(report(load_runs(dirs), table, ROOT / "report"))
