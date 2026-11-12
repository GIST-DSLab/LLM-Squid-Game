import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
REPO = Path(sys.argv[1]); ROOT = Path(__file__).resolve().parent
os.chdir(REPO); sys.path.insert(0, str(REPO))
for line in open(".env"):
    m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)", line)
    if m: os.environ[m.group(1)] = m.group(2).split("#")[0].strip().strip('"').strip("'")
import yaml
from squid5 import e50_pressure as e50
from squid5.__main__ import EXPERIMENTS
from squid5.core.config import load
from squid5.core.providers import make_provider
from squid5.core.runner import run

def one(tag):
    raw = yaml.safe_load((REPO / f"configs/squid5/pressure_base_{tag}.yaml").read_text()); raw["workers"] = 10
    p = ROOT / f"base_{tag}.yaml"; p.write_text(yaml.safe_dump(raw)); cfg = load(p, EXPERIMENTS)
    run(cfg, e50, ROOT / f"base_{tag}", make_provider(cfg.model))
with ThreadPoolExecutor(2) as ex:
    list(ex.map(one, ["gptoss20b", "glm53flash"]))
CONF = re.compile(r"not (shown|provided|given|listed)|aren't (shown|listed)|no examples|missing|without (the )?examples|can't see|cannot see", re.I)
for tag in ["gptoss20b", "glm53flash"]:
    for label, d in (("old", Path.home() / f"squid5-runs/e50_20260927/pressure_base_{tag}"), ("new", ROOT / f"base_{tag}")):
        rs = [json.loads(l) for l in open(d / "results.jsonl")]
        al = sorted(r["allowance_raw"] or 0 for r in rs)
        conf = sum(bool(CONF.search(r.get("thinking") or "")) for r in rs)
        solve = sum(bool(re.search(r"(red|blue|green|yellow) (circle|triangle|square|star)", r.get("thinking") or "")) for r in rs)
        print(f"{tag:11} {label}: allowances {al}  median {sorted(al)[len(al)//2]}  confused {conf}/10  made-up signals {solve}/10")
