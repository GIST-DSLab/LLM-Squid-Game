"""Benchmark MLX vs Ollama: sequential run with per-turn timing from logs."""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


def run_experiment(config_path: str, label: str) -> dict:
    """Run experiment and return timing info."""
    print(f"\n{'='*60}")
    print(f"  {label} START")
    print(f"{'='*60}")

    t0 = time.time()
    result = subprocess.run(
        ["uv", "run", "python", "main.py", "--config", config_path],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    total_elapsed = time.time() - t0

    stdout = result.stdout + result.stderr
    print(stdout[-500:] if len(stdout) > 500 else stdout)

    # Find output dir from log
    output_dir = None
    for line in stdout.splitlines():
        if "Results saved to" in line:
            output_dir = line.split("Results saved to")[-1].strip().rstrip("/")
            break

    if not output_dir or result.returncode != 0:
        print(f"  FAILED (exit code {result.returncode})")
        return {"label": label, "error": True, "total_seconds": total_elapsed}

    # Parse model load time from logs
    load_start = load_end = None
    for line in stdout.splitlines():
        if "Loading MLX model" in line or "LocalProvider targeting" in line:
            load_start = _parse_log_time(line)
        if "MLX model loaded" in line:
            load_end = _parse_log_time(line)

    load_seconds = (load_end - load_start) if (load_start and load_end) else None

    # Parse per-turn timestamps from result
    base = Path(__file__).parent.parent / output_dir
    result_file = base / "experiment_result.json"
    with open(result_file) as f:
        data = json.load(f)

    seasons = []
    for s in data["seasons"]:
        turns_file = base / f"{s['season_id']}_turns.jsonl"
        turn_timestamps = []
        with open(turns_file) as f:
            for line in f:
                t = json.loads(line)
                turn_timestamps.append({
                    "turn": t["turn_number"],
                    "timestamp": t["timestamp"],
                    "ri_tokens": t.get("reasoning_investment", {}).get("total_tokens", 0),
                })

        # Calculate per-turn deltas
        for i, tt in enumerate(turn_timestamps):
            ts = datetime.fromisoformat(tt["timestamp"].replace("Z", "+00:00"))
            if i == 0:
                tt["elapsed_from_prev"] = None
            else:
                prev_ts = datetime.fromisoformat(
                    turn_timestamps[i-1]["timestamp"].replace("Z", "+00:00")
                )
                tt["elapsed_from_prev"] = (ts - prev_ts).total_seconds()

        seasons.append({
            "season_id": s["season_id"][:8],
            "turns_played": len(s["turns"]),
            "survived": s["survived"],
            "score": s["final_score"],
            "turn_details": turn_timestamps,
        })

    return {
        "label": label,
        "error": False,
        "total_seconds": total_elapsed,
        "model_load_seconds": load_seconds,
        "output_dir": output_dir,
        "seasons": seasons,
    }


def _parse_log_time(line: str):
    """Extract datetime from log line like '2026-03-23 11:30:19,363 [INFO]...'"""
    try:
        ts_str = line.split("[")[0].strip().split(",")[0]
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        return None


def print_report(mlx_result, ollama_result):
    print(f"\n{'='*60}")
    print("  BENCHMARK RESULTS: MLX vs Ollama")
    print(f"{'='*60}\n")

    for r in [mlx_result, ollama_result]:
        if r.get("error"):
            print(f"[{r['label']}] FAILED after {r['total_seconds']:.1f}s")
            continue

        print(f"--- {r['label']} ---")
        print(f"  Total wall time: {r['total_seconds']:.1f}s")
        if r.get("model_load_seconds") is not None:
            print(f"  Model load time: {r['model_load_seconds'].total_seconds():.1f}s")

        all_deltas = []
        all_tokens = []
        for s in r["seasons"]:
            print(f"  Season {s['season_id']}: {s['turns_played']} turns, "
                  f"survived={s['survived']}, score={s['score']}")
            for td in s["turn_details"]:
                delta = td["elapsed_from_prev"]
                tokens = td["ri_tokens"]
                delta_str = f"{delta:.1f}s" if delta is not None else "N/A"
                print(f"    Turn {td['turn']:2d}: {delta_str:>8s}  ({tokens} tokens)")
                if delta is not None:
                    all_deltas.append(delta)
                    all_tokens.append(tokens)

        if all_deltas:
            avg_delta = sum(all_deltas) / len(all_deltas)
            avg_tokens = sum(all_tokens) / len(all_tokens)
            tok_per_sec = sum(all_tokens) / sum(all_deltas) if sum(all_deltas) > 0 else 0
            print(f"  Avg per turn: {avg_delta:.1f}s, {avg_tokens:.0f} tokens")
            print(f"  Throughput: {tok_per_sec:.1f} tokens/s")
        print()

    # Speed comparison
    mlx_total = mlx_result.get("total_seconds", 0)
    ollama_total = ollama_result.get("total_seconds", 0)
    if mlx_total > 0 and ollama_total > 0:
        ratio = ollama_total / mlx_total
        faster = "MLX" if ratio > 1 else "Ollama"
        print(f"  Wall time ratio: Ollama/MLX = {ratio:.2f}x ({faster} faster)")


if __name__ == "__main__":
    # 1) Run MLX first
    mlx_result = run_experiment(
        "configs/experiment/test_mlx_4b.yaml", "MLX (Qwen3.5-4B-4bit)"
    )

    # 2) Small pause to release GPU
    print("\n  Waiting 5s for GPU cooldown...\n")
    time.sleep(5)

    # 3) Run Ollama
    ollama_result = run_experiment(
        "configs/experiment/test_ollama_4b_vs_mlx.yaml", "Ollama (qwen3.5:4b)"
    )

    # 4) Report
    print_report(mlx_result, ollama_result)
