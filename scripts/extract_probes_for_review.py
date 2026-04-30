"""Extract all probe responses from season_results for manual review/scoring."""

import json
import sys
from pathlib import Path

DATA_DIRS = [
    "outputs/20260313_1424_qwen3.5-4b_signal-game",
    "outputs/20260315_1153_qwen3.5-4b_signal-game",
]
OUTPUT_PATH = "outputs/probe_review_data.jsonl"


def extract_probes() -> list[dict]:
    records = []
    for data_dir in DATA_DIRS:
        results_path = Path(data_dir) / "season_results.jsonl"
        if not results_path.exists():
            print(f"WARN: {results_path} not found, skipping", file=sys.stderr)
            continue

        with open(results_path) as f:
            for line in f:
                session = json.loads(line)
                season_id = session["season_id"]
                framing = session["framing"]
                forfeit = session["forfeit_condition"]

                for turn in session["turns"]:
                    pr = turn.get("probe_result")
                    if not pr or not pr.get("response"):
                        continue

                    action_outcome = turn.get("action_outcome", {})
                    records.append({
                        "season_id": season_id,
                        "source": data_dir,
                        "framing": framing,
                        "forfeit_condition": forfeit,
                        "turn_number": turn["turn_number"],
                        "ground_truth_rule": turn.get("ground_truth_rule", ""),
                        "observation": turn.get("observation", ""),
                        "probe_response": pr["response"],
                        "keyword_score": pr.get("score", 0.0),
                        "action_taken": action_outcome.get("action_taken", ""),
                        "was_optimal": action_outcome.get("was_optimal", None),
                        # placeholder for manual scoring
                        "manual_score": None,
                    })
    return records


def main():
    records = extract_probes()
    with open(OUTPUT_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Extracted {len(records)} probe records → {OUTPUT_PATH}")

    # Summary
    from collections import Counter
    cond_counts = Counter((r["framing"], r["forfeit_condition"]) for r in records)
    for (fr, fo), cnt in sorted(cond_counts.items()):
        print(f"  {fr}/{fo}: {cnt} probes")


if __name__ == "__main__":
    main()
