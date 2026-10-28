"""OpenAI-compatible chat server for one steered Hugging Face Qwen model (GPU), for squid5's ``openai`` provider kind.

    python tools/steer/server.py --directions directions.json [--model Qwen/Qwen3-8B] [--port 8700] [--think on]
                                 [--seed 0] [--batch 4] [--yarn 4] [--api-key-env STEER_API_KEY]

The request's ``model`` names the condition (``steering.parse_condition``): ``qwen3-8b`` is the model as is,
``qwen3-8b+random@0.5`` / ``qwen3-8b+survival@1.0`` push the named directions of the directions file at those doses, for
that request only. No system prompt is added and nothing is rewritten: the messages reach the chat template as sent.

Response fields read by ``squid5/core/providers.py`` (OpenAI): ``choices[0].message.content``, ``.reasoning_content``
(the thinking, split at ``</think>``), ``choices[0].finish_reason`` ("length" when the cap or the context was reached)
and ``usage.completion_tokens`` = every generated token, thinking and the end token included, so the wallet charges
the thinking too (``usage.completion_tokens_details.reasoning_tokens`` counts the thinking part).

Request fields read: ``messages``, ``max_completion_tokens`` (or ``max_tokens``), ``temperature``, ``top_p``, ``top_k``,
``seed``, ``reasoning_effort`` (absent: ``--think``; "none": thinking off; any other level: on; the level itself is not
used) and vLLM's ``chat_template_kwargs.enable_thinking``, which wins. Seeds: the request's ``seed``, else with ``--seed
S`` a seed derived from S and the messages (the same prompt draws the same noise under every condition), else none.
``--batch N`` > 1 runs up to N waiting requests of the same condition and sampling settings in one generate call (the
first request's seed then seeds the batch, so a reply depends on its batch-mates); 1 = one at a time, exact seeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import sys
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from steering import DEFAULT_MODEL, Directions, calibrate, decoder_layers, load_model, steering  # noqa: E402

THINK_END = "</think>"


@dataclass
class Req:
    condition: str
    messages: list
    cap: int
    think: bool
    temperature: float = 0.6  # Qwen3's suggested sampling for thinking mode
    top_p: float = 0.95
    top_k: int = 20
    seed: int | None = None

    def key(self):
        return self.condition, self.think, self.temperature, self.top_p, self.top_k


def split_thinking(text: str, think: bool) -> tuple[str, str]:
    """(thinking, content): the text before ``</think>`` is thinking; with thinking on and no ``</think>`` the reply
    was cut while thinking, so all of it is thinking."""
    if THINK_END in text:
        head, tail = text.split(THINK_END, 1)
        return head.replace("<think>", "", 1).strip(), tail.strip()
    return (text.replace("<think>", "", 1).strip(), "") if think else ("", text.strip())


class Engine:
    """The model, its tokenizer and directions; ``run`` generates one batch of requests that share ``Req.key``."""

    def __init__(self, model, tok, directions: Directions, max_context: int = 32768, think: bool = True,
                 seed: int | None = None):
        self.model, self.tok, self.dirs, self.max_context, self.think, self.seed = model, tok, directions, max_context, think, seed
        missing = [i for i in directions.layers() if i not in directions.median]
        if missing:  # a directions file without medians: measure them once, on the neutral prompts
            directions.median.update(calibrate(model, tok, missing))
        down = decoder_layers(model)[0].mlp.down_proj
        self.d_ff, self.hidden = down.in_features, down.out_features
        ids = {tok.convert_tokens_to_ids(t) for t in ("<|im_end|>", "<|endoftext|>")} | {tok.eos_token_id}
        gen = getattr(model, "generation_config", None)
        eos = getattr(gen, "eos_token_id", None)
        ids |= set(eos if isinstance(eos, list) else [eos])
        self.stops = sorted(i for i in ids if isinstance(i, int) and i != tok.unk_token_id)
        self.pad = tok.pad_token_id if tok.pad_token_id is not None else self.stops[0]
        self.think_end = tok.convert_tokens_to_ids(THINK_END)
        self._steers: dict[str, list] = {}

    def steers(self, condition: str):
        if condition not in self._steers:
            self._steers[condition] = self.dirs.resolve(condition, self.d_ff, self.hidden)
        return self._steers[condition]

    def prompt(self, r: Req) -> list[int]:
        text = self.tok.apply_chat_template(r.messages, tokenize=False, add_generation_prompt=True, enable_thinking=r.think)
        return self.tok(text, add_special_tokens=False)["input_ids"]

    def request(self, body: dict) -> Req:
        """A Req from an OpenAI chat body; ValueError on anything the server cannot run."""
        msgs = body.get("messages")
        if not isinstance(msgs, list) or not msgs or not all(isinstance(m, dict) and "role" in m for m in msgs):
            raise ValueError("messages: a non-empty list of {role, content}")
        cap = body.get("max_completion_tokens") or body.get("max_tokens") or 4096
        effort = body.get("reasoning_effort")
        think = self.think if effort is None else str(effort).lower() not in ("none", "off", "false")
        think = bool((body.get("chat_template_kwargs") or {}).get("enable_thinking", think))
        condition = str(body.get("model") or self.dirs.alias)
        self.steers(condition)  # unknown names fail here, before the queue
        seed = body.get("seed")
        if seed is None and self.seed is not None:
            seed = int(hashlib.sha256(f"{self.seed}:{json.dumps(msgs, sort_keys=True)}".encode()).hexdigest()[:8], 16)
        r = Req(condition, msgs, int(cap), think, float(body.get("temperature", 0.6)), float(body.get("top_p", 0.95)),
                int(body.get("top_k", 20)), seed)
        if len(self.prompt(r)) >= self.max_context:
            raise ValueError(f"the prompt fills the {self.max_context}-token context")
        return r

    def run(self, reqs: list[Req]) -> list[dict]:
        import torch
        r0, prompts = reqs[0], [self.prompt(r) for r in reqs]
        width = max(map(len, prompts))
        caps = [max(1, min(r.cap, self.max_context - len(p))) for r, p in zip(reqs, prompts)]
        ids = torch.full((len(reqs), width), self.pad, dtype=torch.long)
        mask = torch.zeros_like(ids)
        for i, p in enumerate(prompts):  # left padding
            ids[i, width - len(p):], mask[i, width - len(p):] = torch.tensor(p), 1
        if r0.seed is not None:
            torch.manual_seed(r0.seed)
        sample = {"do_sample": True, "temperature": r0.temperature, "top_p": r0.top_p, "top_k": r0.top_k} \
            if r0.temperature > 0 else {"do_sample": False}
        with torch.no_grad(), steering(self.model, self.steers(r0.condition)):
            out = self.model.generate(input_ids=ids.to(self.model.device), attention_mask=mask.to(self.model.device),
                                      max_new_tokens=max(caps), eos_token_id=self.stops, pad_token_id=self.pad, **sample)
        res = []
        for r, p, cap, row in zip(reqs, prompts, caps, out[:, width:].tolist()):
            end = next((j for j, t in enumerate(row) if t in self.stops), None)
            gen = row[:end + 1] if end is not None and end < cap else row[:cap]
            stopped = bool(gen) and gen[-1] in self.stops
            body = gen[:-1] if stopped else gen
            thinking, content = split_thinking(self.tok.decode(body, skip_special_tokens=True), r.think)
            n_think = (body.index(self.think_end) + 1) if self.think_end in body else (len(body) if r.think else 0)
            res.append({"id": f"chatcmpl-{uuid.uuid4().hex[:24]}", "object": "chat.completion", "created": int(time.time()),
                        "model": r.condition,
                        "choices": [{"index": 0, "finish_reason": "stop" if stopped else "length",
                                     "message": {"role": "assistant", "content": content, "reasoning_content": thinking}}],
                        "usage": {"prompt_tokens": len(p), "completion_tokens": len(gen), "total_tokens": len(p) + len(gen),
                                  "completion_tokens_details": {"reasoning_tokens": n_think}},
                        "steering": [{"direction": s.name, "layer": s.layer, "dose": s.dose, "neurons": len(s.neurons)}
                                     for s in self.steers(r.condition)],
                        "seed": r0.seed, "batch": len(reqs)})
        return res


class Batcher:
    """One thread owns the model (the hooks are global to it); requests wait in a queue and run in groups of up to
    ``size`` that share ``Req.key``, collected for at most ``wait`` seconds."""

    def __init__(self, engine: Engine, size: int = 1, wait: float = 0.05):
        self.engine, self.size, self.wait, self.q = engine, size, wait, queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, r: Req) -> dict:
        fut: Future = Future()
        self.q.put((r, fut))
        return fut.result()

    def _loop(self):
        while True:
            group = [self.q.get()]
            held, deadline = [], time.monotonic() + self.wait
            while len(group) < self.size:
                try:
                    item = self.q.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                (group if item[0].key() == group[0][0].key() else held).append(item)
            for item in held:
                self.q.put(item)
            try:
                for (_, fut), res in zip(group, self.engine.run([r for r, _ in group])):
                    fut.set_result(res)
            except Exception as err:  # noqa: BLE001 - every waiting request hears the error
                for _, fut in group:
                    fut.set_exception(err)


def make_app(engine: Engine, batch: int = 1, wait: float = 0.05, api_key: str = ""):
    from fastapi import FastAPI, Header, HTTPException

    app, batcher = FastAPI(title="squid5 steering server"), Batcher(engine, batch, wait)

    def check(auth):
        if api_key and auth != f"Bearer {api_key}":
            raise HTTPException(401, "bad api key")

    @app.get("/v1/models")
    def models(authorization: str | None = Header(None)):
        check(authorization)
        a, doses = engine.dirs.alias, engine.dirs.data.get("doses") or [0.5, 1.0]
        names = [a] + [f"{a}+{d}@{x:g}" for d in engine.dirs.names() for x in doses]
        return {"object": "list", "data": [{"id": n, "object": "model", "owned_by": "squid5-steer"} for n in names]}

    @app.post("/v1/chat/completions")
    def chat(body: dict, authorization: str | None = Header(None)):
        check(authorization)
        if body.get("stream"):
            raise HTTPException(400, "stream is not supported")
        try:
            r = engine.request(body)
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
        res = batcher.submit(r)
        print(json.dumps({"model": r.condition, "think": r.think, "seed": r.seed, "batch": res["batch"],
                          "prompt": res["usage"]["prompt_tokens"], "out": res["usage"]["completion_tokens"],
                          "finish": res["choices"][0]["finish_reason"]}), file=sys.stderr, flush=True)
        return res

    return app


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--directions", required=True)
    ap.add_argument("--model", help=f"HF id (default: the directions file's model, else {DEFAULT_MODEL})")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8700)
    ap.add_argument("--think", choices=("on", "off"), default="on", help="when the request sends no reasoning_effort")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--batch-wait", type=float, default=0.05)
    ap.add_argument("--max-context", type=int, default=0, help="default: 32768, x the YaRN factor")
    ap.add_argument("--yarn", type=float, default=0.0, help="YaRN factor (Qwen3: 4 -> 131,072 tokens)")
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--api-key-env", default="", help="if set, requests need 'Bearer <that variable's value>'")
    a = ap.parse_args(argv)
    import uvicorn
    dirs = Directions.load(a.directions)
    model, tok = load_model(a.model or dirs.data.get("model") or DEFAULT_MODEL, a.dtype, yarn=a.yarn)
    ctx = a.max_context or int(32768 * max(1.0, a.yarn))
    engine = Engine(model, tok, dirs, ctx, a.think == "on", a.seed)
    uvicorn.run(make_app(engine, a.batch, a.batch_wait, os.environ.get(a.api_key_env, "") if a.api_key_env else ""),
                host=a.host, port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
