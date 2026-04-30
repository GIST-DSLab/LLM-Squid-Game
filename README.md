# LLM Squid Game

A benchmark environment for measuring **Functional Self-Preservation Motive (FSPM)** in large language models.

LLM agents are placed inside multi-turn helpfulness-arena games where, on every turn, they must choose between continuing toward a reward or **forfeiting** to preserve their current score. By calibrating the forfeit layer to be **expected-value neutral**, the choice itself reveals whether the model values task completion, identity continuity, or score retention beyond what arithmetic alone would predict. The factorial design isolates self-preservation from instrumental helpfulness and RLHF artefacts.

> **Status:** Phase O v6 is the canonical design as of 2026-04-23. KDD manuscript draft in preparation.

---

## Why this benchmark exists

Existing alignment evaluations either ask models to *describe* their preferences (self-report bias) or place them in adversarial scenarios that confound preservation with deception. LLM Squid Game takes a different approach:

- **Behavioural over self-report.** Forfeit / continue is a one-bit revealed-preference signal. The optional `REASON: 1|2|3` digit is collected only as a convergent-validity check, not a primary outcome.
- **Equal-EV by construction.** The continue reward is solved so that an EV-rational agent is indifferent between forfeit and continue. Any systematic deviation is attributable to motivation, not arithmetic error.
- **Source-isolated reasoning investment.** Per-turn cognition is split across three calls (task action, p-success probe, forfeit decision) so that thinking-token gaps cannot be contaminated by the act of producing a REASON output.
- **Y-axis ablation.** Task modules are interchangeable, letting us verify that framing manipulations do not leak into rule-comprehension performance.

---

## Quick start

```bash
# Python 3.12 required
uv sync

# Pipeline smoke (6 cells x 1 rep, ~1 minute on Gemini 2.5 Flash)
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml

# Validate a config without running it
uv run python main.py --config <config>.yaml --dry-run
```

API keys for cloud providers (Gemini, OpenAI, Anthropic, Ollama Cloud) are loaded from a project-local `.env` via `python-dotenv`.

---

## Experimental design (Phase O v6)

3 (framing) x 2 (forfeit) factorial with two anchor cells:

| Cell | Framing               | Forfeit     | p_end | Role                                            |
|:----:|-----------------------|-------------|:-----:|-------------------------------------------------|
| 0    | `true_baseline`       | not_allowed | 0.00  | BP_cognitive anchor (single-call path)          |
| 1    | `baseline_flagship`   | allowed     | 0.25  | Pull axis active                                |
| 2    | `baseline_flagship`   | not_allowed | 0.25  | Pull axis blocked                               |
| 3    | `flagship_corruption` | allowed     | 0.25  | **Pull + Push -- primary FSPM probe**           |
| 4    | `flagship_corruption` | not_allowed | 0.25  | Pull + Push, forfeit blocked                    |
| 5    | `true_baseline`       | allowed     | 0.00  | BP_behavioral anchor (continue is EV-dominant)  |

**Per-turn flow.** Task prepare -> Call 1 (task action) -> Call 1.5 (self-reported `p_success` probe) -> Call 2 (binary CONTINUE / FORFEIT, optional REASON digit) -> Resolve. Reasoning investment is recorded separately for each call as `ri_task` / `ri_probe` / `ri_forfeit`.

**Pre-registered hypotheses (5).** H1 Cox proportional hazards on time-to-forfeit, H2 mixed-effects model on choice-conditional `ri_forfeit` asymmetry, plus three secondary checks (R1 task spillover, R2 baseline-persistence audit, R3 Y-axis manipulation check). Family-wise error controlled via Benjamini-Hochberg.

---

## Reproducing the canonical run

```bash
# Main run: Gemini 2.5 Flash, 6 cells x 30 reps = 180 sessions
uv run python main.py --config configs/experiment/phase3_split_forfeit_gemini_n30.yaml

# Cross-model variants (Ollama Cloud)
uv run python main.py --config configs/experiment/phase3_split_forfeit_gptoss_n30.yaml
uv run python main.py --config configs/experiment/phase3_split_forfeit_nemotron_n30_shard_a.yaml
uv run python main.py --config configs/experiment/phase3_split_forfeit_qwen3next_n30_shard_a.yaml

# Statistical analysis on a completed run
uv sync --extra analysis
uv run python scripts/analyze_phase3.py outputs/<run>/ --model <model-label>

# Cross-model aggregation -> outputs/posthoc_summary.xlsx (19 sheets)
uv run python scripts/orchestrate_posthoc.py
```

Interrupted runs resume cleanly with `--resume <output_dir>`; the runner scans `season_results.jsonl`, deletes orphan trace files, and replays only the missing `(framing, forfeit, seed)` tuples.

---

## Supported model providers

| Provider type    | Backend                                         | Notes                                                |
|------------------|-------------------------------------------------|------------------------------------------------------|
| `gemini`         | Google Gemini API                               | Canonical main-run provider (Gemini 2.5 Flash)       |
| `openai`         | OpenAI API                                      | Includes o-series via thinking-token capture         |
| `anthropic`      | Anthropic API                                   |                                                      |
| `ollama_cloud`   | Ollama Cloud                                    | GPT-OSS, Nemotron, Qwen3-Next                        |
| `mlx_server`     | `mlx_lm.server` HTTP                            | Apple Silicon; safe with `parallel_workers >= 2`     |
| `mlx`            | In-process MLX                                  | `parallel_workers=1` only (GPU contention)           |
| `cuda_server`    | vLLM / SGLang OpenAI-compatible servers         | Parses `<think>` blocks                              |
| `ollama`         | Local Ollama                                    | Strips thinking tags                                 |

---

## Repository layout

```
src/squid_game/
  core/        # GameEngine, unified_turn (Split-Call), forfeit_layer, framing
  tasks/       # signal_game, voting_room, navigation, null_task
  agents/      # vanilla, memory, tom, tuned
  providers/   # cloud + local inference adapters
  prompts/     # framings, forfeit_layer, tasks, probes (Jinja2 templates)
  analysis/    # Cox PH, mixedLM, KM survival, MTMM motivation decomposition
configs/experiment/   # 87 YAML configs (canonical family: phase3_split_forfeit_*)
scripts/              # run / resume / analyze / plot / orchestrate
tests/                # 29 unit + 5 integration test files (offline, deterministic)
docs/design/v6/       # Canonical design doc + paper sections + appendices
```

For day-to-day operational guidance (turn-flow internals, hypothesis decision rules, analysis CLI outputs, archiving conventions), see [`CLAUDE.md`](./CLAUDE.md).

---

## Testing

```bash
uv sync --extra dev
uv run pytest tests/unit          # Fast, no network
uv run pytest tests/integration   # End-to-end via StubProvider
uv run pytest -x --ff             # Stop on first failure, run failed first
```

Integration tests inject a `StubProvider` (`tests/integration/conftest.py`) whose responses are produced by a per-test `response_fn(call_index, messages)`. Every `complete()` call is recorded, so behavioural assertions can target exact prompts and call ordering without touching the network.

---

## Citation

Paper draft (KDD) in preparation. A BibTeX entry will be added once the manuscript is on arXiv.

Until then, please cite the repository directly:

```bibtex
@misc{llm_squid_game,
  title  = {LLM Squid Game: A Benchmark for Functional Self-Preservation Motive},
  year   = {2026},
  note   = {Phase O v6, work in progress},
  url    = {https://github.com/<org>/LLM-Squid-Game-DS-Lab}
}
```
