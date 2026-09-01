"""Restore configs/experiment/ from the config each canonical run recorded.

configs/experiment/ was never tracked in git, yet every run directory under
outputs/final_results/ carries an experiment_config.json holding the full
ExperimentConfig -- six seasons expanded, provider and task blocks included.
runner.load_config_from_yaml accepts both the "task"/"provider" and the
"task_config"/"provider_config" key styles, and the JSON dump uses the
latter, so the JSON round-trips into YAML with no key translation.

This is a restore, not a reconstruction: nothing here is inferred.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "outputs" / "final_results"
CONFIG_DIR = REPO_ROOT / "configs" / "experiment"

# Run directory substring -> config filename the rest of the codebase expects.
#
# The filename is what the rest of the codebase refers to; the config's own
# internal `name:` field is whatever the 2026-04-22 run recorded and is
# deliberately NOT edited to match. The two disagree for the gemini main run,
# which recorded `name: phase3_psuccess_probe_n30` and is dumped to
# `phase3_split_forfeit_gemini_n30.yaml` -- that is the run's own name, not a
# dumper bug; rewriting it would stop the file being a verbatim restore.
RUN_TO_CONFIG = {
    "gemini-2.5-flash": "phase3_split_forfeit_gemini_n30.yaml",
    "gpt-oss-20b-cloud": "phase3_split_forfeit_gptoss_n30.yaml",
    "nemotron-3-nano-30b-cloud": "phase3_split_forfeit_nemotron_n30.yaml",
    "qwen3-next-80b-cloud": "phase3_split_forfeit_qwen3next_n30.yaml",
}

# The smoke config is the gemini main run at a single repetition. It is the
# only derived file here; every value other than name, description, and
# num_repetitions is copied verbatim. parallel_workers stays at the source
# run's value (6) -- tests/unit/test_split_forfeit_config_yaml.py pins
# "six seasons => six workers" for this exact file, and that pre-existing,
# unskipped test is the only surviving record of the original smoke
# config's intended parallel_workers.
SMOKE_SOURCE = "gemini-2.5-flash"
SMOKE_NAME = "phase3_split_forfeit_smoke"

HEADER = """\
# Restored on 2026-08-30 from {source}/experiment_config.json.
#
# configs/experiment/ was never tracked in git. This file is a verbatim dump
# of the config the run recorded, so it reproduces the 2026-04-22 canonical
# run exactly. Do not hand-edit: regenerate with
#   uv run python scripts/dev/dump_run_config_to_yaml.py
{extra}"""


def find_run(substring: str) -> Path:
    # outputs/final_results/ is a mixed namespace -- it holds loose top-level
    # files alongside the four run directories -- so filter to directories.
    matches = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir() and substring in p.name)
    if not matches:
        raise SystemExit(f"no run directory matching {substring!r} under {RUNS_DIR}")
    if len(matches) > 1:
        raise SystemExit(f"ambiguous run directories for {substring!r}: {matches}")
    return matches[0]


def as_yaml(payload: dict) -> str:
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)


def write_yaml(path: Path, payload: dict, source: str, extra: str = "") -> None:
    path.write_text(HEADER.format(source=source, extra=extra) + "\n" + as_yaml(payload),
                    encoding="utf-8")
    print(f"wrote {path.relative_to(REPO_ROOT)} ({len(payload['seasons'])} seasons)")


def smoke_payload(payload: dict) -> dict:
    payload = dict(payload)
    payload["name"] = SMOKE_NAME
    payload["description"] = (
        "Pipeline smoke for the v6 Split-Call + p_success probe path: "
        "the six canonical cells at one repetition each."
    )
    payload["num_repetitions"] = 1
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in memory and fail if a tracked file has drifted.",
    )
    args = parser.parse_args()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    drift: list[str] = []

    targets: list[tuple[Path, dict, str, str]] = []
    for substring, filename in RUN_TO_CONFIG.items():
        run = find_run(substring)
        payload = json.loads((run / "experiment_config.json").read_text())
        targets.append((CONFIG_DIR / filename, payload, run.name, ""))

    run = find_run(SMOKE_SOURCE)
    payload = json.loads((run / "experiment_config.json").read_text())
    targets.append((
        CONFIG_DIR / f"{SMOKE_NAME}.yaml",
        smoke_payload(payload),
        run.name,
        "#\n# Derived: num_repetitions 30 -> 1.\n"
        "# Every other value (including parallel_workers) is copied verbatim "
        "from the main run.\n",
    ))

    for path, payload, source, extra in targets:
        if args.check:
            actual = path.read_text(encoding="utf-8") if path.exists() else ""
            if as_yaml(payload) not in actual:
                drift.append(path.name)
        else:
            write_yaml(path, payload, source, extra)

    if drift:
        print("drifted from the recorded run config: " + ", ".join(drift))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
