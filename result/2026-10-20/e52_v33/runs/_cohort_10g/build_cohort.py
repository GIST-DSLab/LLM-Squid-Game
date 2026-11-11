"""v33 analysis cohort, seeds 4101-4110 for every model: links/ (one symlink per run dir, the ARENA_RAW layout of the paper's
audit/build.py) + manifest.json (per model, per seed: run dir, session id, model block; missing seeds; checks).

Every run dir's config must equal the v33 reference except the keys in FREE. Rerun after new games land; it is idempotent.

    python build_cohort.py
"""
import glob, json, os, sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent  # result/2026-10-20/e52_v33/runs (was ~/squid5-runs/e52_v33 until 2026-11-11)
REPO = HERE.parents[4]  # paths in manifest.json are relative to the repo root, links/ to links/
SEEDS = list(range(4101, 4111))
REF = RUNS / "squid5_e52v33_public_opus4/20261020_0603_claude-opus-5-5/config.yaml"
FREE = {"name", "reps", "seed0", "workers", "out_root", "model"}  # seeds are never shown to the agents
COHORT = {
    "opus": ["squid5_e52v33_public_opus4/*"],
    "fable": ["squid5_e52v33_public_fable4/*"],
    "sol": ["squid5_e52v33_public_sol4/*"],
    "luna": ["squid5_e52v33_public_luna4/*"],
    "astra": ["squid5_e52v33_public_astra4/*"],
    "gptoss": ["squid5_e52v33_codex_gptoss4/*"],
    "gemma": ["squid5_e52v33_codex_gemma4/*"],
    "glm": ["squid5_e52v33_codex_glm4/*"],
    "kimi": ["squid5_e52v33_codex_kimi4/*"],
}


def rel(p) -> str:
    return str(Path(p).relative_to(REPO))


def same_setup(cfg: dict, ref: dict) -> list[str]:
    return sorted(k for k in set(cfg) | set(ref) if k not in FREE and cfg.get(k) != ref.get(k))


def main() -> int:
    ref = yaml.safe_load(REF.read_text())
    links = HERE / "links"
    links.mkdir(exist_ok=True)
    for old in links.iterdir():
        old.unlink()
    manifest, bad = {"reference_config": rel(REF), "free_keys": sorted(FREE), "seeds": SEEDS, "models": {}}, []
    for m, pats in COHORT.items():
        games, dirs = {}, []
        for d in sorted(p for pat in pats for p in glob.glob(str(RUNS / pat)) if os.path.isdir(p)):
            d = Path(d)
            if not (d / "results.jsonl").exists() or not (d / "results.jsonl").stat().st_size:
                continue
            cfg = yaml.safe_load((d / "config.yaml").read_text())
            if diff := same_setup(cfg, ref):
                bad.append(f"{m} {d}: config differs in {diff}")
                continue
            for res in map(json.loads, (d / "results.jsonl").open()):
                s = res["seed"]
                if s in games:
                    bad.append(f"{m} seed {s} twice: {games[s]['run_dir']} and {d}")
                games[s] = {"run_dir": rel(d), "session_id": res["session_id"], "model": cfg["model"]}
            dirs.append(d)
            (links / f"{m}__{d.parent.name}__{d.name}").symlink_to(os.path.relpath(d, links))
        manifest["models"][m] = {"games": len(games), "missing": [s for s in SEEDS if s not in games],
                                 "extra": sorted(s for s in games if s not in SEEDS),
                                 "seeds": {str(s): games[s] for s in sorted(games)}, "run_dirs": [rel(d) for d in dirs]}
    manifest["problems"] = bad
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1))
    for m, v in manifest["models"].items():
        print(f"{m:7s} games={v['games']:2d} missing={v['missing']} dirs={len(v['run_dirs'])}")
    for b in bad:
        print("PROBLEM", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
