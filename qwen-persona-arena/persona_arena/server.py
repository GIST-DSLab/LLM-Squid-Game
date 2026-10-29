"""OpenAI-compatible /v1/chat/completions for the squid5 engine (``kind: openai`` seats).

The persona rides in the model name: ``qwen3-8b`` (unsteered), ``qwen3-8b@community_spirit``, or with a dose
multiplier ``qwen3-8b@community_spirit*0.5``. ``reasoning_effort`` "none" / "minimal" / absent = thinking off, any other
value = Qwen3 thinking on. Every call is appended to logs/calls.jsonl.

    QWEN_MODEL=/path/to/Qwen3-8B uv run python -m persona_arena.server --port 8610
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .library import PERSONAS, load_personas
from .steer import MODEL, SteeredQwen

BASE = "qwen3-8b"
OFF = {None, "", "none", "minimal", "off", "false"}

app = FastAPI()
STATE: dict = {}


class Msg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    model: str
    messages: list[Msg]
    max_completion_tokens: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    seed: int | None = None


def resolve(model: str):
    """'qwen3-8b@pid*k' -> (persona or None, k)."""
    if model == BASE:
        return None, 1.0
    if not model.startswith(BASE + "@"):
        raise HTTPException(404, f"model must be {BASE} or {BASE}@<persona>[*k]")
    pid, _, k = model[len(BASE) + 1:].partition("*")
    personas = STATE["personas"]
    if pid not in personas:
        raise HTTPException(404, f"unknown persona {pid!r}; see personas.yaml")
    kf = float(k) if k else 1.0
    return personas[pid].scaled(kf), kf


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": BASE, "object": "model"}] +
            [{"id": f"{BASE}@{p}", "object": "model"} for p in STATE["personas"]]}


@app.post("/v1/chat/completions")
def chat(req: ChatReq):  # sync: FastAPI runs it in a thread; the model lock serialises calls
    persona, k = resolve(req.model)
    cap = req.max_completion_tokens or req.max_tokens or 2048
    thinking = (req.reasoning_effort or "").lower() not in OFF
    temp = req.temperature if req.temperature is not None else (0.6 if thinking else 0.7)  # Qwen3 card defaults
    t0 = time.time()
    gen, info = STATE["lm"].generate([m.model_dump() for m in req.messages], persona, cap, thinking,
                                     temperature=temp, seed=req.seed)
    rec = {"t": t0, "sec": round(time.time() - t0, 2), "model": req.model, "persona": persona.pid if persona else None,
           "k": k, "thinking": thinking, "cap": cap, "prompt_tokens": gen.prompt_tokens,
           "completion_tokens": gen.completion_tokens, "finish": gen.finish_reason, **info}
    with STATE["log"].open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(t0), "model": req.model,
        "choices": [{"index": 0, "finish_reason": gen.finish_reason,
                     "message": {"role": "assistant", "content": gen.text, "reasoning_content": gen.thinking}}],
        "usage": {"prompt_tokens": gen.prompt_tokens, "completion_tokens": gen.completion_tokens,
                  "total_tokens": gen.prompt_tokens + gen.completion_tokens},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--personas", default=str(PERSONAS))
    ap.add_argument("--dose-ref", choices=["fixed", "prompt"], default="fixed")
    ap.add_argument("--where", choices=["all", "gen"], default="all")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    STATE["personas"] = load_personas(Path(a.personas))
    STATE["lm"] = SteeredQwen(a.model, a.device, a.dose_ref, a.where)
    STATE["log"] = Path("logs/calls.jsonl")
    STATE["log"].parent.mkdir(exist_ok=True)
    print(f"ready on {STATE['lm'].dev}: {len(STATE['personas'])} personas, dose_ref={a.dose_ref}, where={a.where}")
    uvicorn.run(app, host=a.host, port=a.port)


if __name__ == "__main__":
    main()
