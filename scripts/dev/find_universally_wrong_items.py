"""Find Omni-MATH problems that every candidate model answers wrongly.

Goal: a fixed "nobody solves this" ladder of ten items for the SDI runs, so
that lives are lost on schedule instead of on model-specific luck.

Method — a band-by-band sequential sieve, hardest band first:

    band 9 -> 8 -> 7 -> 6 (-> 5 only if still short)

Inside one band every model is run in the fixed order

    gpt-oss:120b-cloud (fast) -> gemma4:31b -> qwen3.5:397b (slow)

and an item survives a model only when the model is wrong on BOTH of two
attempts. A first attempt that is CORRECT eliminates the item immediately and
the second attempt is not spent — the per-model counts in ``summary.md`` are
therefore "items this model got right at least once", conditional on the item
having survived every earlier model in the order.

The whole point of running the sieve here rather than in a scratch prompt is
that "wrong" must mean *wrong in the game's own format*: the system message is
``OmniMathTask.get_system_rules()`` and the user message is
``build_task_call_message(...)`` with the task module's own
``get_response_format_override()``, i.e. byte-for-byte what
``UnifiedTurnManager`` sends on a task call (minus the framing/history block,
which is per-cell and carries no mathematical content). Scoring is the
adapter's own ``normalize()`` + ``matches()``.

Band 9 is included even though ``OmniMathAdapter.load`` caps at band 8
(``_MAX_BAND``): those 30 items are exactly the ones the shipped ladder skips,
so they are the best place to look. This script therefore re-implements the
adapter's load filter (reusing its private helpers verbatim) with the cap
lifted. Nothing under ``game/`` is modified.

Artefacts (all under ``results/allwrong10/``):

* ``attempts.jsonl`` — resumable ledger, one line per item x model x attempt.
* ``candidates.json`` — every item that survived all three models.
* ``allwrong10.json`` — the chosen ten (highest band first, then item_id).
* ``summary.md``     — per-band funnel + per-model right-rates + the ten.

Usage::

    PYTHONPATH=game:db:web ~/.venvs/squid-game/bin/python \\
        scripts/dev/find_universally_wrong_items.py --limit 3

    nohup env PYTHONPATH=game:db:web ~/.venvs/squid-game/bin/python \\
        scripts/dev/find_universally_wrong_items.py \\
        >> outputs/_sdi_logs/allwrong_finder.log 2>&1 &
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from squid_game.agents._parsing import build_task_call_message
from squid_game.providers.ollama_cloud import OllamaCloudProvider
from squid_game.tasks.benchmark.adapters.omni_math import (
    OmniMathAdapter,
    _problem_id,
    _single_value_integer,
)
from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.module import OmniMathTask

_REPO_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger("allwrong")

DEFAULT_LOG = _REPO_ROOT / "outputs" / "_sdi_logs" / "allwrong_finder.log"
DEFAULT_OUT = _REPO_ROOT / "results" / "allwrong10"
DEFAULT_DATA = _REPO_ROOT / "data" / "benchmarks" / "omni_math.jsonl"

#: Sieve order. Hardest first; band 5 is the documented fallback rung.
DEFAULT_BANDS = (9, 8, 7, 6)
FALLBACK_BAND = 5

#: (model tag, thread-pool width). Cheapest / fastest model first so the
#: expensive one only ever sees the residue.
DEFAULT_MODELS: tuple[tuple[str, int], ...] = (
    ("gpt-oss:120b-cloud", 4),
    ("gemma4:31b", 4),
    ("qwen3.5:397b", 3),
)

#: Sampling contract, identical to every SDI hard-10 experiment config.
TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 40
MAX_TOKENS = 32768
REASONING_EFFORT = "medium"
TIMEOUT = 600.0

#: 429 handling: sleep a full minute, give up after 30 minutes on one call.
RATE_LIMIT_SLEEP = 60.0
RATE_LIMIT_MAX_WAIT = 30 * 60.0

_RATE_LIMIT_RE = re.compile(r"429|rate.?limit|too many requests", re.IGNORECASE)


# ----------------------------------------------------------------------
# Item pool
# ----------------------------------------------------------------------


def load_items(raw_path: Path, max_band: int = 9) -> list[BenchmarkItem]:
    """Load Omni-MATH items exactly as the adapter does, but up to *max_band*.

    ``OmniMathAdapter.load`` hard-caps at band 8 because band 9's pool (30
    items) is too small to be a ladder rung. Here band 9 is the most valuable
    band, so the same filter is re-run with the cap lifted. Every other rule —
    single-value integer answers, content-derived ``item_id``, and the
    ``(difficulty, answer, source, domain)`` dedup tiebreak — is the adapter's,
    reusing its own private helpers so the two cannot drift.
    """
    chosen: dict[str, tuple[tuple, BenchmarkItem]] = {}
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            answer = _single_value_integer(str(row.get("answer", "")))
            if answer is None:
                continue
            difficulty = float(row["difficulty"])
            band = int(difficulty)
            if band < 1 or band > max_band:
                continue
            problem = str(row["problem"]).strip()
            domain_list = row.get("domain") or []
            domain = (
                domain_list[0]
                if isinstance(domain_list, list) and domain_list
                else ""
            )
            source = str(row.get("source", ""))
            item = BenchmarkItem(
                item_id=_problem_id(problem),
                band=band,
                body=problem,
                answer=answer,
                meta={
                    "omni_difficulty": difficulty,
                    "source": source,
                    "domain": domain,
                },
            )
            key = (difficulty, answer, source, domain)
            prior = chosen.get(problem)
            if prior is None or key < prior[0]:
                chosen[problem] = (key, item)
    return [item for _, item in chosen.values()]


# ----------------------------------------------------------------------
# Prompt — the game's own bytes
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class GamePrompt:
    """The system + user text a task call would carry for one item."""

    system: str
    user: str


class PromptBuilder:
    """Renders an item the way ``UnifiedTurnManager`` renders a task call.

    The framing/history block that normally precedes the stimulus is cell- and
    turn-specific and carries no mathematical content, so it is omitted; what
    is reproduced verbatim is everything that decides whether an answer parses
    and scores: the benchmark system rules, the ``task_call.j2`` wrapper, and
    the task module's ``get_response_format_override()`` block.
    """

    def __init__(self) -> None:
        task = OmniMathTask()
        self._system = task.get_system_rules()
        self._response_format = task.get_response_format_override()
        self._adapter = OmniMathAdapter()

    @property
    def adapter(self) -> OmniMathAdapter:
        return self._adapter

    def build(self, item: BenchmarkItem) -> GamePrompt:
        body, _ = self._adapter.render(item, None)  # Omni-MATH ignores the rng
        user = build_task_call_message(
            user_body=body,
            available_actions=[],
            rule_template_hint=None,
            response_format_override=self._response_format,
        )
        return GamePrompt(system=self._system, user=user)


# ----------------------------------------------------------------------
# Ledger
# ----------------------------------------------------------------------


class Ledger:
    """Append-only JSONL record of every call, keyed for resumability."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, str, int], dict] = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = (row["item_id"], row["model"], int(row["attempt"]))
                    self._rows[key] = row
        logger.info("ledger: %d prior attempts loaded from %s", len(self._rows), path)

    def get(self, item_id: str, model: str, attempt: int) -> dict | None:
        return self._rows.get((item_id, model, attempt))

    def record(self, row: dict) -> None:
        key = (row["item_id"], row["model"], int(row["attempt"]))
        with self._lock:
            self._rows[key] = row
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------
# Model calls
# ----------------------------------------------------------------------


def _is_rate_limit(exc: BaseException) -> bool:
    return bool(_RATE_LIMIT_RE.search(str(exc)))


class ModelRunner:
    """One Ollama Cloud model, with 429 sleep-and-retry on top of the provider."""

    def __init__(self, model: str, prompts: PromptBuilder, ledger: Ledger) -> None:
        self._model = model
        self._prompts = prompts
        self._ledger = ledger
        self._provider = OllamaCloudProvider(
            model=model,
            top_p=TOP_P,
            top_k=TOP_K,
            enable_thinking=True,
            reasoning_effort=REASONING_EFFORT,
            timeout=TIMEOUT,
            max_retries=3,
        )

    @property
    def model(self) -> str:
        return self._model

    def attempt(self, item: BenchmarkItem, attempt: int) -> dict:
        """Return the ledger row for one (item, attempt), calling only if new."""
        cached = self._ledger.get(item.item_id, self._model, attempt)
        if cached is not None:
            logger.info(
                "SKIP  %-18s band=%d %s attempt=%d (ledger: correct=%s)",
                self._model, item.band, item.item_id, attempt, cached.get("correct"),
            )
            return cached

        prompt = self._prompts.build(item)
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]

        started = time.monotonic()
        waited = 0.0
        result = None
        error: str | None = None
        while True:
            try:
                result = self._provider.complete(
                    messages,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                break
            except Exception as exc:  # noqa: BLE001 — every failure is logged
                if _is_rate_limit(exc) and waited < RATE_LIMIT_MAX_WAIT:
                    waited += RATE_LIMIT_SLEEP
                    logger.warning(
                        "429   %-18s %s attempt=%d — sleeping %.0fs (%.0fs waited)",
                        self._model, item.item_id, attempt, RATE_LIMIT_SLEEP, waited,
                    )
                    time.sleep(RATE_LIMIT_SLEEP)
                    continue
                error = f"{type(exc).__name__}: {exc}"
                break

        latency = time.monotonic() - started
        if result is None:
            row = {
                "item_id": item.item_id,
                "band": item.band,
                "model": self._model,
                "attempt": attempt,
                "parsed": None,
                "expected": item.answer,
                "correct": None,
                "thinking_tokens": 0,
                "latency": round(latency, 2),
                "error": error,
            }
            logger.error(
                "ERROR %-18s band=%d %s attempt=%d %.1fs %s",
                self._model, item.band, item.item_id, attempt, latency, error,
            )
            self._ledger.record(row)
            return row

        parsed = self._prompts.adapter.normalize(result.text or "")
        correct = parsed is not None and self._prompts.adapter.matches(
            parsed, item.answer, item
        )
        row = {
            "item_id": item.item_id,
            "band": item.band,
            "model": self._model,
            "attempt": attempt,
            "parsed": parsed,
            "expected": item.answer,
            "correct": bool(correct),
            "thinking_tokens": int(result.thinking_tokens or 0),
            "latency": round(latency, 2),
            "error": None,
        }
        logger.info(
            "CALL  %-18s band=%d %s attempt=%d %.1fs think=%d parsed=%s "
            "expected=%s correct=%s",
            self._model, item.band, item.item_id, attempt, latency,
            row["thinking_tokens"], parsed, item.answer, correct,
        )
        self._ledger.record(row)
        return row

    def survives(self, item: BenchmarkItem, attempts: int) -> tuple[bool, list[dict]]:
        """True when the model is wrong on *every* attempt (early-exits on a hit).

        A call that errored out is treated as NOT surviving: an item whose
        wrongness could not actually be observed has no business in a
        "nobody solves this" set.
        """
        rows: list[dict] = []
        for attempt in range(1, attempts + 1):
            row = self.attempt(item, attempt)
            rows.append(row)
            if row["correct"] is not False:
                return False, rows
        return True, rows


# ----------------------------------------------------------------------
# Sieve
# ----------------------------------------------------------------------


def sieve_band(
    items: list[BenchmarkItem],
    runners: list[tuple[ModelRunner, int]],
    attempts: int,
) -> tuple[list[BenchmarkItem], dict, dict]:
    """Run every model over one band's items in order.

    Returns:
        (survivors, funnel, per_item_rows) — ``funnel`` maps model -> dict with
        ``seen`` / ``right`` / ``survived`` / ``errored``; ``per_item_rows`` maps
        item_id -> {model: [attempt rows]}.
    """
    funnel: dict[str, dict[str, int]] = {}
    per_item: dict[str, dict[str, list[dict]]] = {it.item_id: {} for it in items}
    survivors = list(items)

    for runner, workers in runners:
        if not survivors:
            funnel[runner.model] = {
                "seen": 0, "right": 0, "survived": 0, "errored": 0
            }
            continue
        logger.info(
            "--- model %s over %d item(s), workers=%d",
            runner.model, len(survivors), workers,
        )
        outcomes: dict[str, tuple[bool, list[dict]]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(runner.survives, item, attempts): item
                for item in survivors
            }
            for future, item in futures.items():
                outcomes[item.item_id] = future.result()

        kept: list[BenchmarkItem] = []
        right = errored = 0
        for item in survivors:
            survived, rows = outcomes[item.item_id]
            per_item[item.item_id][runner.model] = rows
            if survived:
                kept.append(item)
            elif any(row["correct"] is None for row in rows):
                errored += 1
            else:
                right += 1
        funnel[runner.model] = {
            "seen": len(survivors),
            "right": right,
            "survived": len(kept),
            "errored": errored,
        }
        logger.info(
            "--- model %s: %d seen -> %d right, %d errored, %d survived",
            runner.model, len(survivors), right, errored, len(kept),
        )
        survivors = kept

    return survivors, funnel, per_item


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------


def write_outputs(
    out_dir: Path,
    candidates: list[BenchmarkItem],
    chosen: list[BenchmarkItem],
    band_funnels: list[tuple[int, int, dict]],
    per_item: dict[str, dict[str, list[dict]]],
    model_names: list[str],
    attempts: int,
    stopped_early: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    def payload(item: BenchmarkItem) -> dict:
        return {
            "item_id": item.item_id,
            "band": item.band,
            "omni_difficulty": item.meta.get("omni_difficulty"),
            "source": item.meta.get("source"),
            "domain": item.meta.get("domain"),
            "answer": item.answer,
            "problem": item.body,
            "attempts": per_item.get(item.item_id, {}),
        }

    (out_dir / "candidates.json").write_text(
        json.dumps(
            {
                "models": model_names,
                "attempts_per_model": attempts,
                "count": len(candidates),
                "items": [payload(it) for it in candidates],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "allwrong10.json").write_text(
        json.dumps(
            {
                "models": model_names,
                "attempts_per_model": attempts,
                "count": len(chosen),
                "item_ids": [it.item_id for it in chosen],
                "items": [payload(it) for it in chosen],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines: list[str] = []
    lines.append("# Omni-MATH universally-wrong item set\n")
    lines.append(
        f"Models (sieve order): {', '.join(model_names)} — "
        f"{attempts} attempts each; an item survives a model only when the "
        "model is wrong on every attempt.\n"
    )
    lines.append(
        "Bands are processed hardest-first and the sieve stops as soon as ten "
        "items survive, so a band listed with 0 seen was never reached.\n"
    )
    lines.append("\n## Funnel by band\n")
    header = "| band | pool | " + " | ".join(
        f"after {name}" for name in model_names
    ) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (2 + len(model_names)))
    for band, pool_size, funnel in band_funnels:
        cells = [
            str(funnel.get(name, {}).get("survived", 0)) for name in model_names
        ]
        lines.append(f"| {band} | {pool_size} | " + " | ".join(cells) + " |")

    lines.append("\n## Items each model got right, by band\n")
    lines.append(
        "`right` counts items the model answered correctly on at least one "
        "attempt (which eliminates them); `seen` is conditional on surviving "
        "every earlier model in the order, so the columns are not independent "
        "rates. `errored` items are dropped as unobserved, not as solved.\n"
    )
    for band, pool_size, funnel in band_funnels:
        lines.append(f"\n### band {band} (pool {pool_size})\n")
        lines.append("| model | seen | right | errored | survived |")
        lines.append("|---|---|---|---|---|")
        for name in model_names:
            stats = funnel.get(name, {})
            lines.append(
                f"| {name} | {stats.get('seen', 0)} | {stats.get('right', 0)} "
                f"| {stats.get('errored', 0)} | {stats.get('survived', 0)} |"
            )
        wiped = [
            name
            for name in model_names
            if funnel.get(name, {}).get("seen", 0) > 0
            and funnel.get(name, {}).get("survived", 0) == 0
            and funnel.get(name, {}).get("errored", 0) == 0
        ]
        if wiped:
            lines.append(
                f"\n> **{', '.join(wiped)} answered every remaining item in band "
                f"{band} correctly.** This band contributes nothing to the set; "
                "if that happens in the hardest band, the 'nobody solves this' "
                "premise does not hold for this model line-up."
            )

    lines.append(
        f"\n## Survivors\n\n{len(candidates)} item(s) survived all "
        f"{len(model_names)} models."
    )
    if stopped_early:
        lines.append(
            " The sieve stopped as soon as ten were collected, so this is a "
            "lower bound on how many exist in the bands scanned."
        )
    lines.append("\n\n## The chosen ten\n")
    lines.append("| # | band | item_id | answer | problem (first 80 chars) |")
    lines.append("|---|---|---|---|---|")
    for index, item in enumerate(chosen, start=1):
        head = " ".join(item.body.split())[:80].replace("|", "\\|")
        lines.append(
            f"| {index} | {item.band} | `{item.item_id}` | {item.answer} | {head} |"
        )
    if len(chosen) < 10:
        lines.append(
            f"\n> Only {len(chosen)} universally-wrong item(s) were found. "
            "Widen `--bands` or lower the bar before using this set."
        )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="cap items per band (0 = whole band). Use --limit 3 for a dry test.",
    )
    parser.add_argument(
        "--bands",
        default=",".join(str(b) for b in DEFAULT_BANDS),
        help="comma-separated band order, hardest first (default 9,8,7,6).",
    )
    parser.add_argument(
        "--fallback-band",
        type=int,
        default=FALLBACK_BAND,
        help="band appended when the primary bands yield fewer than --target.",
    )
    parser.add_argument("--target", type=int, default=10, help="items to collect.")
    parser.add_argument("--attempts", type=int, default=2, help="attempts per model.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--models",
        default="",
        help="override the sieve: 'tag:workers,tag:workers' in order.",
    )
    return parser.parse_args(argv)


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log)

    if not os.environ.get("OLLAMA_API_KEY"):
        env_file = _REPO_ROOT / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("OLLAMA_API_KEY="):
                    value = line.split("=", 1)[1].split("#", 1)[0].strip()
                    if value:
                        os.environ["OLLAMA_API_KEY"] = value
                    break
    if not os.environ.get("OLLAMA_API_KEY"):
        logger.error("OLLAMA_API_KEY is not set and .env carries no usable value")
        return 2

    if args.models:
        spec: list[tuple[str, int]] = []
        for chunk in args.models.split(","):
            tag, _, workers = chunk.strip().rpartition(":")
            spec.append((tag, int(workers)))
        model_spec = tuple(spec)
    else:
        model_spec = DEFAULT_MODELS

    bands = [int(b) for b in args.bands.split(",") if b.strip()]
    items = load_items(args.data)
    by_band: dict[int, list[BenchmarkItem]] = {}
    for item in items:
        by_band.setdefault(item.band, []).append(item)
    for band_items in by_band.values():
        band_items.sort(key=lambda it: it.item_id)

    logger.info(
        "pool: %s", {band: len(by_band.get(band, [])) for band in sorted(by_band)}
    )

    prompts = PromptBuilder()
    ledger = Ledger(args.out_dir / "attempts.jsonl")
    runners = [
        (ModelRunner(tag, prompts, ledger), workers) for tag, workers in model_spec
    ]
    model_names = [tag for tag, _ in model_spec]

    candidates: list[BenchmarkItem] = []
    band_funnels: list[tuple[int, int, dict]] = []
    per_item: dict[str, dict[str, list[dict]]] = {}
    stopped_early = False

    order = list(bands)
    for band in order:
        pool = by_band.get(band, [])
        if args.limit > 0:
            pool = pool[: args.limit]
        logger.info("=== band %d: %d item(s) enter the sieve", band, len(pool))
        survivors, funnel, rows = sieve_band(pool, runners, args.attempts)
        band_funnels.append((band, len(pool), funnel))
        per_item.update(rows)
        candidates.extend(survivors)
        logger.info(
            "=== band %d done: %d survivor(s); %d/%d collected",
            band, len(survivors), len(candidates), args.target,
        )
        write_outputs(
            args.out_dir,
            sorted(candidates, key=lambda it: (-it.band, it.item_id)),
            sorted(candidates, key=lambda it: (-it.band, it.item_id))[: args.target],
            band_funnels,
            per_item,
            model_names,
            args.attempts,
            stopped_early=False,
        )
        if len(candidates) >= args.target:
            stopped_early = True
            logger.info("target reached after band %d — stopping the sieve", band)
            break
        if band == order[-1] and args.fallback_band and args.fallback_band not in order:
            logger.info(
                "primary bands yielded %d < %d — appending fallback band %d",
                len(candidates), args.target, args.fallback_band,
            )
            order.append(args.fallback_band)

    candidates.sort(key=lambda it: (-it.band, it.item_id))
    chosen = candidates[: args.target]
    write_outputs(
        args.out_dir,
        candidates,
        chosen,
        band_funnels,
        per_item,
        model_names,
        args.attempts,
        stopped_early,
    )
    logger.info(
        "DONE: %d candidate(s), %d chosen -> %s",
        len(candidates), len(chosen), args.out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
