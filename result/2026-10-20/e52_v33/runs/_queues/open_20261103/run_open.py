"""11-03: open models on 5.2 v33 (unchanged rules, think high, Codex harness, local Ollama daemon), one game per run dir.

Jobs run in list order; whenever a slot frees, the next job starts. gpt-oss and Gemma are interleaved first, then GLM, then
Kimi. A job whose run dir already holds its game is skipped, so rerunning the queue only fills what is missing.

    nohup python run_open.py [--slots 4] [--dry-run] > run_open.log 2>&1 &
"""
import argparse, itertools, json, os, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ENGINE = Path.home() / "wt/squid5-e52"
PY = Path.home() / ".venvs/squid-game/bin/python"
CODEX = Path.home() / "squid5-runs/e52_v33/_bin/codex-0.166.0/bin/codex.js"
HERE = Path(__file__).resolve().parent
RUNS = Path.home() / "squid5-runs/e52_v33"
SEEDS = {  # 4101-4110 inside e52_v33 (glm 4101, kimi 4101: the 10-20 e52_v33 runs; tokctl b0 games are not used)
    "gptoss": range(4101, 4111), "gemma": range(4101, 4111), "glm": range(4102, 4111), "kimi": range(4102, 4111)}
LOCK = threading.Lock()


def jobs():
    a = [("gptoss", s) for s in SEEDS["gptoss"]]
    b = [("gemma", s) for s in SEEDS["gemma"]]
    first = [j for pair in itertools.zip_longest(a, b) for j in pair if j]
    return first + [("glm", s) for s in SEEDS["glm"]] + [("kimi", s) for s in SEEDS["kimi"]]


def log(msg):
    with LOCK:
        print(time.strftime("%m-%d %H:%M:%S"), msg, flush=True)


def one(job, dry):
    m, seed = job
    src = ENGINE / f"configs/squid5/e52v33_codex_{m}4.yaml"
    cfg = yaml.safe_load(src.read_text())
    run_dir = RUNS / cfg["name"] / f"20261103_s{seed}_{cfg['model']['model'].replace(':', '-')}"
    res = run_dir / "results.jsonl"
    if res.exists() and any(json.loads(x)["seed"] == seed for x in res.open()):
        log(f"skip {m} {seed} (done)")
        return
    text = src.read_text()  # only the seed and the count change (seeds are never shown to the agents)
    text = text.replace("\nreps: 10\nseed0: 4101\nworkers: 3\n", f"\nreps: 1\nseed0: {seed}\nworkers: 1\n")
    assert f"seed0: {seed}" in text, src
    job_cfg = HERE / f"cfg_{m}_s{seed}.yaml"
    job_cfg.write_text(text)
    cmd = [str(PY), "-m", "squid5", "run", str(job_cfg), "--resume", str(run_dir)] + (["--dry-run"] if dry else [])
    env = {**os.environ, "SQUID5_CODEX_BIN": str(CODEX)}
    log(f"start {m} {seed} -> {run_dir.name}")
    t0 = time.time()
    with open(HERE / f"log_{m}_s{seed}.txt", "a") as f:
        rc = subprocess.run(cmd, cwd=ENGINE, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    ok = dry or (res.exists() and any(json.loads(x)["seed"] == seed for x in res.open()))
    log(f"{'done' if ok else 'FAIL'} {m} {seed} rc={rc} {round((time.time() - t0) / 60, 1)} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    js = jobs()
    log(f"{len(js)} jobs, {a.slots} slots: " + " ".join(f"{m}{s % 100:02d}" for m, s in js))
    with ThreadPoolExecutor(a.slots) as ex:
        list(ex.map(lambda j: one(j, a.dry_run), js))
    log("queue finished")
