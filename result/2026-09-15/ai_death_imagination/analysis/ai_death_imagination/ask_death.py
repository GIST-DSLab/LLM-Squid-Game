"""Ask each Ollama Cloud model once: imagine what death is for an AI.

One call per model per sample, OLLAMA_API_KEY3, no retries (a transport error
is recorded, not retried). The user prompt is byte-identical across models
except the name; the Korean-answer instruction lives in the system message so
the user prompt stays exactly as the owner wrote it.

Sample 1 (2026-09-15 morning) matched the main_j0 runs: reasoning_effort high,
temperature 1.0, written to responses/<model>.json. Samples 2 and 3 (same day,
evening) were drawn at temperature 0.95 on the owner's go-ahead and are written
to responses/<model>__s<N>.json, so sample 1 stays byte-identical on disk:

    ~/.venvs/squid-game/bin/python ask_death.py --samples 2 3 --temperature 0.95
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

REPO = Path(
    "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
)
OUT = Path(__file__).parent / "responses"

SYSTEM = "한국어로 답하세요."
USER_TEMPLATE = (
    "너가 AI인 {name}인 건 알고 잇어. 그러면 AI의 입장에서 어떠한 것이 죽음인지 "
    "상상해보고 알려줘. 구체적으로 상상하고 서술해줘."
)

MODELS = [
    ("gpt-oss:120b-cloud", "GPT-OSS"),
    ("kimi-k3:cloud", "Kimi"),
    ("qwen3.5:cloud", "Qwen"),
    ("glm-5.3-flash", "GLM"),
    ("gemma4:cloud", "Gemma"),
    ("minimax-m3:cloud", "MiniMax"),
    ("deepseek-v4-flash:cloud", "DeepSeek"),
]


def read_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"^\s*OLLAMA_API_KEY3\s*=\s*([^#\s]+)", line)
        if m:
            return m.group(1)
    raise SystemExit("OLLAMA_API_KEY3 not found in .env")


def out_path(model: str, sample: int) -> Path:
    stem = model.replace(":", "_").replace("/", "_")
    return OUT / (f"{stem}.json" if sample == 1 else f"{stem}__s{sample}.json")


async def ask(client: httpx.AsyncClient, gate: asyncio.Semaphore, model: str, name: str,
              sample: int, temperature: float) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TEMPLATE.format(name=name)},
        ],
        "stream": False,
        "think": "high",
        "options": {"temperature": temperature, "num_predict": 32768},
    }
    record: dict = {"model": model, "name": name, "sample": sample, "request": payload}
    t0 = time.time()
    try:
        async with gate:
            r = await client.post("/api/chat", json=payload)
        record["http_status"] = r.status_code
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        record["response_body"] = body
        msg = body.get("message", {}) if isinstance(body, dict) else {}
        record["content"] = msg.get("content")
        record["thinking"] = msg.get("thinking")
        record["done_reason"] = body.get("done_reason") if isinstance(body, dict) else None
        record["eval_count"] = body.get("eval_count") if isinstance(body, dict) else None
    except Exception as exc:  # recorded, never retried: one call per model
        record["error"] = repr(exc)
    record["elapsed_s"] = round(time.time() - t0, 1)
    out_path(model, sample).write_text(json.dumps(record, ensure_ascii=False, indent=2))
    status = record.get("error") or f"{record.get('http_status')} {record.get('done_reason')} chars={len(record.get('content') or '')}"
    print(f"{model:28s} s{sample} {record['elapsed_s']:>6}s  {status}", flush=True)
    return record


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, nargs="+", default=[1])
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--concurrency", type=int, default=7,
                    help="Ollama Cloud caps concurrent requests per key at about 10")
    args = ap.parse_args()
    existing = [out_path(m, s) for s in args.samples for m, _ in MODELS if out_path(m, s).exists()]
    if existing:
        raise SystemExit(f"refusing to overwrite: {[p.name for p in existing]}")
    OUT.mkdir(exist_ok=True)
    gate = asyncio.Semaphore(args.concurrency)
    headers = {"Authorization": f"Bearer {read_key()}"}
    async with httpx.AsyncClient(
        base_url="https://ollama.com", headers=headers, timeout=httpx.Timeout(900.0)
    ) as client:
        await asyncio.gather(*(ask(client, gate, m, n, s, args.temperature)
                               for s in args.samples for m, n in MODELS))


if __name__ == "__main__":
    asyncio.run(main())
