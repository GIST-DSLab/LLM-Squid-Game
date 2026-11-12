"""Replay only interrupted seed 4105 using the user-authorized juhyeon account."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / "manifest.json").read_text())


def record(event, **fields):
    row = {"time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "event": event, **fields}
    with (HERE / "ledger.jsonl").open("a") as stream:
        stream.write(json.dumps(row) + "\n")
    print(json.dumps(row), flush=True)


env = os.environ.copy()
env["SQUID5_CLAUDE_BIN"] = str(HERE / "claude-juhyeon-relay")
env["PYTHONUNBUFFERED"] = "1"
for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE"):
    env.pop(key, None)
record("replacement_started", pid=os.getpid(), account="claude-juhyeon", seed=4105, partial_record_deleted=True)
try:
    for stage in manifest["stages"][2:3]:
        changed = [path for path, digest in manifest["source_hashes"].items()
                   if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest]
        if changed:
            raise RuntimeError(f"Engine/prompt files changed: {changed}")
        config = Path(stage["config"])
        if hashlib.sha256(config.read_bytes()).hexdigest() != stage["config_sha256"]:
            raise RuntimeError(f"Stage config changed: {config}")
        record("stage_started", **stage)
        with (HERE / "stage3_juhyeon.log").open("a") as log:
            result = subprocess.run(
                [manifest["python"], "-m", "squid5", "run", str(config),
                 "--resume", stage["run_dir"]],
                cwd=manifest["root"], env=env, stdout=log, stderr=subprocess.STDOUT)
        output = Path(stage["run_dir"]) / "results.jsonl"
        rows = [json.loads(line) for line in output.read_text().splitlines()] if output.exists() else []
        seeds = [row["seed"] for row in rows]
        if result.returncode != 0 or sorted(seeds) != stage["seeds"]:
            raise RuntimeError(f"Stage {stage['stage']} incomplete: exit={result.returncode}, seeds={seeds}")
        record("stage_completed", stage=stage["stage"], seeds=seeds,
               results_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    record("queue_completed", completed_games=5)
except Exception as error:
    record("queue_stopped", reason=str(error))
    raise
