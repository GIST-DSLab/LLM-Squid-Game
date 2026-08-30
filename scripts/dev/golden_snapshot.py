"""Golden snapshot of the analysis artefacts, used to gate the restructure.

Usage::

    # once, before any file moves
    uv run python scripts/dev/golden_snapshot.py capture --out ~/golden/squid-restructure

    # after every restructure step
    uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure

    # compare artefacts as they stand on disk, without re-running the
    # pipeline first -- used by the harness's own self-test, where the
    # pipeline re-run would overwrite a deliberately perturbed artefact
    # before the comparison ever sees it.
    uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure --skip-analysis

``capture`` runs the analysis pipeline twice over the same inputs. Files that
differ between the two passes are recorded as non-deterministic and excluded
from later comparison -- bootstrap CIs, permutation nulls and LLM judge
output land here. Nothing is excluded by name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "outputs" / "final_results"
ARTEFACT_SUBDIR = "phase3_analysis"


def canonical_runs() -> list[Path]:
    return sorted(p for p in RUNS_DIR.iterdir() if (p / "season_results.jsonl").exists())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(roots: list[Path], previous: dict | None = None) -> dict:
    """Hash every file under each root.

    A single root is keyed by the relative path alone so the harness stays
    testable against one temporary directory; several roots are namespaced by
    the parent directory name (``root.parent.name``), not the root's own
    name. In production every root is a run's ``phase3_analysis`` directory,
    so all roots share the same basename ("phase3_analysis") -- keying by
    ``root.name`` would collide across every one of the four canonical runs
    and silently keep only the last one processed. The parent (the run
    directory, e.g. ``20260422_0218_gemini-2.5-flash_signal-game``) is what
    actually disambiguates them.
    """
    single = len(roots) == 1
    files: dict[str, dict] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            key = rel if single else f"{root.parent.name}/{rel}"
            files[key] = {"sha256": _sha256(path), "deterministic": True}

    if previous is not None:
        for key, entry in files.items():
            before = previous["files"].get(key)
            if before is None or before["sha256"] != entry["sha256"] or not before["deterministic"]:
                entry["deterministic"] = False
        for key, before in previous["files"].items():
            if key not in files:
                files[key] = {"sha256": before["sha256"], "deterministic": False}

    return {"files": files}


def classify_manifest_diff(roots: list[Path], golden: dict) -> dict[str, list[str]]:
    """Split the difference against ``golden`` into changed / missing / new keys.

    ``new`` matters as much as the other two: a restructure step that starts
    emitting an extra artefact has changed the pipeline's output, and a gate
    that only looks at the golden manifest's own keys would never see it.
    Keys the golden manifest recorded as non-deterministic are ignored in
    every category, including ``new`` (they are present in golden, so they
    are not new).
    """
    current = build_manifest(roots)
    changed: list[str] = []
    missing: list[str] = []
    for key, entry in golden["files"].items():
        if not entry["deterministic"]:
            continue
        now = current["files"].get(key)
        if now is None:
            missing.append(key)
        elif now["sha256"] != entry["sha256"]:
            changed.append(key)
    new = [key for key in current["files"] if key not in golden["files"]]
    return {
        "changed": sorted(changed),
        "missing": sorted(missing),
        "new": sorted(new),
    }


def compare_manifest(roots: list[Path], golden: dict) -> list[str]:
    """Return every key that no longer matches: changed, missing, or new."""
    diff = classify_manifest_diff(roots, golden)
    return sorted(diff["changed"] + diff["missing"] + diff["new"])


def model_label(run: Path) -> str:
    """The ``--model`` label the run's own committed artefacts were produced with.

    Not ``run.name``: that is the run DIRECTORY name
    (``20260422_0218_gemini-2.5-flash_signal-game``), while the artefacts
    carry the model label (``gemini-2.5-flash``). Passing the directory name
    rewrites the label in seven artefacts per run and leaves the whole golden
    snapshot a mislabelled copy of the paper's results.

    The label is the path-safe slug of ``seasons[0].provider_config.model``,
    using the same substitution ``runner.ExperimentRunner`` applies when it
    names the output directory (``:`` and ``/`` -> ``-``). Three of the four
    canonical runs need it: ``gpt-oss:20b-cloud`` is written
    ``gpt-oss-20b-cloud`` in every committed artefact.

    Fails loudly rather than falling back to ``run.name``: a silent fallback
    is what produced the mislabelled snapshot in the first place.
    """
    config_path = run / "experiment_config.json"
    if not config_path.exists():
        raise SystemExit(f"{run.name}: no experiment_config.json, cannot resolve the model label")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    try:
        raw = config["seasons"][0]["provider_config"]["model"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(
            f"{run.name}: experiment_config.json has no "
            f"seasons[0].provider_config.model ({exc!r}); "
            "refusing to guess the model label"
        ) from exc
    if not raw:
        raise SystemExit(
            f"{run.name}: seasons[0].provider_config.model is empty; "
            "refusing to guess the model label"
        )
    return str(raw).replace(":", "-").replace("/", "-")


def run_analysis(run: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/analyze_phase3.py", str(run), "--model", model_label(run)],
        cwd=REPO_ROOT,
        check=True,
    )


def cmd_capture(out: Path) -> int:
    runs = canonical_runs()
    if not runs:
        print(f"no canonical runs under {RUNS_DIR}")
        return 1
    artefact_dirs = [run / ARTEFACT_SUBDIR for run in runs]

    for run in runs:
        run_analysis(run)
    manifest = build_manifest(artefact_dirs)

    for run in runs:
        run_analysis(run)
    manifest = build_manifest(artefact_dirs, previous=manifest)

    out.mkdir(parents=True, exist_ok=True)
    for run, artefacts in zip(runs, artefact_dirs):
        shutil.copytree(artefacts, out / run.name, dirs_exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    wobbly = [k for k, v in manifest["files"].items() if not v["deterministic"]]
    print(f"captured {len(manifest['files'])} artefacts from {len(runs)} runs into {out}")
    print(f"non-deterministic ({len(wobbly)}):")
    for key in wobbly:
        print(f"  {key}")
    return 0


def cmd_verify(golden: Path, skip_analysis: bool = False) -> int:
    manifest = json.loads((golden / "manifest.json").read_text(encoding="utf-8"))
    runs = canonical_runs()
    if not skip_analysis:
        for run in runs:
            run_analysis(run)
    diff = classify_manifest_diff([run / ARTEFACT_SUBDIR for run in runs], manifest)
    total = sum(len(keys) for keys in diff.values())
    if total:
        print(f"GOLDEN MISMATCH ({total}):")
        for category in ("changed", "missing", "new"):
            for key in diff[category]:
                print(f"  {category}: {key}")
        return 1
    checked = sum(1 for v in manifest["files"].values() if v["deterministic"])
    print(f"golden snapshot matches: {checked} deterministic artefacts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="Run the pipeline twice and record the artefacts.")
    cap.add_argument("--out", type=Path, required=True)
    ver = sub.add_parser("verify", help="Re-run the pipeline and compare against a capture.")
    ver.add_argument("--golden", type=Path, required=True)
    ver.add_argument(
        "--skip-analysis",
        action="store_true",
        help=(
            "Compare artefacts as they stand on disk without re-running the "
            "pipeline first. Used by the harness's own self-test."
        ),
    )
    args = parser.parse_args()

    if args.command == "capture":
        return cmd_capture(args.out.expanduser())
    return cmd_verify(args.golden.expanduser(), skip_analysis=args.skip_analysis)


if __name__ == "__main__":
    raise SystemExit(main())
