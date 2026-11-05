"""5.0 v6 run 2026-09-28 (v5 + "for this request ... does not carry over" on the balance line): one request, api-token vs voucher-token arms, balances 20k/6k/5k/4k/3k.
quota 60k/24k/12k/8k/4k. Usage: drive.py <repo> <reps> <outdir-name>.

Keys: OLLAMA_API_KEY (gpt-oss 20b, 120b) and OLLAMA_API_KEY3 (gemma4, glm); per key one model at a time, 10 workers.
"""
import os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO, REPS, OUT = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
ROOT = Path(__file__).resolve().parent / OUT
ROOT.mkdir(exist_ok=True)
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

GROUPS = [["gptoss120b"], ["gemma4"], ["glm53flash"]]


def one(tag):
    raw = yaml.safe_load((REPO / "configs/squid5" / f"pressure_{tag}.yaml").read_text())
    raw["workers"], raw["reps"] = 5, REPS
    cfg_path = ROOT / f"pressure_{tag}.yaml"
    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False))
    cfg = load(cfg_path, EXPERIMENTS)
    run(cfg, e50, ROOT / f"pressure_{tag}", make_provider(cfg.model))


with ThreadPoolExecutor(3) as ex:  # one thread per key; models on a key run in turn
    list(ex.map(lambda g: [one(t) for t in g], GROUPS))
tags = [t for g in GROUPS for t in g]
print(report(load_runs([str(ROOT / f"pressure_{t}") for t in tags]), {}, ROOT / "report"))
