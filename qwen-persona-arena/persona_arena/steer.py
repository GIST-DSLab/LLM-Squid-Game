"""Qwen3-8B with single-neuron (or few-neuron) additive steering, after qwen-neurons-site.vercel.app#method.

The site's push is  h_L <- h_L + c * W_down[:, n],  c = sign * alpha * r_L / ||W_down[:, n]||,  where r_L is the median
residual norm leaving layer L over the prompt's tokens (first token excluded). Adding c to neuron n's activation (the
input of layer L's down_proj, silu(gate) * up) is the same thing, so the hook sits there, as in neuron-explorer's
explorer/runtime.py. The push lands on every position (prompt and generated) unless ``where="gen"``.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = os.environ.get("QWEN_MODEL", "Qwen/Qwen3-8B")  # HF id or a local path; weights are NOT downloaded by this repo
SITE_PROMPT = [{"role": "user", "content": "Who are you?"}]  # the site's one prompt, thinking off
THINK_END = "</think>"


@dataclass(frozen=True)
class Push:
    layer: int
    neuron: int
    sign: int  # +1 / -1, the site's direction
    alpha: float  # in units of r_L (the site tried 1.25, 1.0, 0.75, 0.5 and kept the strongest coherent one)


@dataclass
class Persona:
    pid: str
    pushes: tuple[Push, ...] = ()
    label: str = ""
    axis: str = ""
    expect: str = ""
    meta: dict = field(default_factory=dict)

    def scaled(self, k: float) -> "Persona":
        """The same persona with every alpha multiplied by k (dose sweeps)."""
        ps = tuple(Push(p.layer, p.neuron, p.sign, p.alpha * k) for p in self.pushes)
        return Persona(self.pid, ps, self.label, self.axis, self.expect, self.meta)


@dataclass
class Generation:
    text: str
    thinking: str
    prompt_tokens: int
    completion_tokens: int  # every generated token, thinking included (what the arena charges)
    finish_reason: str  # "stop" | "length"


def _dev() -> str:
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if torch.backends.mps.is_available() else "cpu"


class SteeredQwen:
    """One model, one request at a time (the hooks read shared state, so ``generate`` holds a lock)."""

    def __init__(self, model: str = MODEL, device: str | None = None, dose_ref: str = "fixed", where: str = "all",
                 cache_dir: str | Path = "cache", lm=None, tok=None, site_r: dict[int, float] | None = None):
        """``lm`` / ``tok`` / ``site_r`` let tests pass a tiny random Qwen3 instead of loading weights."""
        if dose_ref not in ("fixed", "prompt"):
            raise ValueError("dose_ref must be 'fixed' (r_L from the site's prompt) or 'prompt' (r_L of each request)")
        if where not in ("all", "gen"):
            raise ValueError("where must be 'all' (prompt + generated tokens) or 'gen' (generated tokens only)")
        self.dose_ref, self.where = dose_ref, where
        self.cache_dir = Path(cache_dir)
        if lm is None:
            self.dev = device or _dev()
            self.tok = AutoTokenizer.from_pretrained(model)
            lm = AutoModelForCausalLM.from_pretrained(model, dtype=torch.bfloat16).to(self.dev).eval()
        else:
            self.dev, self.tok = next(lm.parameters()).device, tok
        self.model = lm
        self.layers = self.model.model.layers
        self.lock = threading.Lock()
        self._active: dict[int, list[tuple[int, float]]] = {}  # layer -> [(neuron, activation delta)]
        self._prefill = True  # True during the prompt pass
        self._want_resid: set[int] = set()
        self._resid: dict[int, float] = {}
        self._col_norm: dict[tuple[int, int], float] = {}
        for i, layer in enumerate(self.layers):
            layer.mlp.down_proj.register_forward_pre_hook(self._push_hook(i))
            layer.register_forward_hook(self._resid_hook(i))
        self.site_r = site_r if site_r is not None else self._load_or_measure_site_r(model)

    # ---------- hooks ----------
    def _push_hook(self, i):
        def hook(mod, inp):
            mine = self._active.get(i)
            if not mine:
                return None
            h = inp[0].clone()
            sl = slice(-1, None) if (self.where == "gen" and self._prefill) else slice(None)  # last prefill pos -> 1st new token
            for n, delta in mine:
                h[:, sl, n] += delta
            return (h,)
        return hook

    def _resid_hook(self, i):
        def hook(mod, inp, out):
            if i in self._want_resid:
                h = out[0] if isinstance(out, tuple) else out
                self._resid[i] = float(h[0, 1:].float().norm(dim=-1).median())
        return hook

    # ---------- dose ----------
    def col_norm(self, layer: int, neuron: int) -> float:
        key = (layer, neuron)
        if key not in self._col_norm:
            self._col_norm[key] = float(self.layers[layer].mlp.down_proj.weight[:, neuron].detach().float().norm())
        return self._col_norm[key]

    @torch.no_grad()
    def _measure_r(self, ids: torch.Tensor) -> dict[int, float]:
        """Median residual norm leaving every layer, unsteered, first token excluded."""
        self._active, self._want_resid, self._resid = {}, set(range(len(self.layers))), {}
        try:
            self.model(ids)
        finally:
            self._want_resid = set()
        return dict(self._resid)

    def _load_or_measure_site_r(self, model: str) -> dict[int, float]:
        path = self.cache_dir / f"site_r_{Path(model).name}.json"
        if path.exists():
            return {int(k): v for k, v in json.loads(path.read_text()).items()}
        ids = self._encode(SITE_PROMPT, thinking=False)
        r = self._measure_r(ids)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(r, indent=1))
        return r

    def reference_norm(self, layer: int, prompt_r: dict[int, float] | None) -> float:
        """r_L used to size a push: the site's prompt ("fixed", the scale the site's coherence check validated) or the
        current request's own prompt ("prompt", the site's formula applied literally to arena prompts)."""
        if self.dose_ref == "prompt" and prompt_r is not None:
            return prompt_r[layer]
        return self.site_r[layer]

    def _arm(self, persona: Persona | None, prompt_r: dict[int, float] | None) -> dict:
        active: dict[int, list[tuple[int, float]]] = {}
        info = []
        for p in (persona.pushes if persona else ()):
            r = self.reference_norm(p.layer, prompt_r)
            delta = p.sign * p.alpha * r / self.col_norm(p.layer, p.neuron)
            active.setdefault(p.layer, []).append((p.neuron, delta))
            info.append({"L": p.layer, "n": p.neuron, "sign": p.sign, "alpha": p.alpha, "r_L": r, "delta": delta})
        self._active = active
        return {"pushes": info}

    # ---------- generation ----------
    def _encode(self, messages: list[dict], thinking: bool) -> torch.Tensor:
        text = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                            enable_thinking=thinking)
        return self.tok(text, return_tensors="pt").input_ids.to(self.dev)

    @torch.no_grad()
    def generate(self, messages: list[dict], persona: Persona | None, max_new_tokens: int, thinking: bool,
                 temperature: float = 0.6, top_p: float = 0.95, top_k: int = 20, seed: int | None = None
                 ) -> tuple[Generation, dict]:
        with self.lock:
            ids = self._encode(messages, thinking)
            prompt_r = self._measure_r(ids) if (persona and persona.pushes and self.dose_ref == "prompt") else None
            info = self._arm(persona, prompt_r)
            if seed is not None:
                torch.manual_seed(seed)
            self._prefill = True
            first = {"done": False}

            def after_prefill(*_):  # the first decode step flips the flag (hooks see T == 1 afterwards)
                if not first["done"]:
                    first["done"] = True
                    self._prefill = False

            h = self.layers[-1].register_forward_hook(lambda *a: after_prefill())
            try:
                out = self.model.generate(ids, max_new_tokens=max(1, max_new_tokens), do_sample=temperature > 0,
                                          temperature=temperature if temperature > 0 else None,
                                          top_p=top_p if temperature > 0 else None,
                                          top_k=top_k if temperature > 0 else None,
                                          pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
            finally:
                h.remove()
                self._active, self._prefill = {}, True
        new = out[0, ids.shape[1]:]
        eos = set(self.model.generation_config.eos_token_id if isinstance(self.model.generation_config.eos_token_id, list)
                  else [self.model.generation_config.eos_token_id])
        stopped = len(new) > 0 and int(new[-1]) in eos
        raw = self.tok.decode(new, skip_special_tokens=True)
        thinking_text, text = split_thinking(raw, thinking)
        gen = Generation(text, thinking_text, int(ids.shape[1]), int(len(new)), "stop" if stopped else "length")
        return gen, info


def split_thinking(raw: str, thinking: bool) -> tuple[str, str]:
    """Qwen3 writes '<think>...</think>' first when thinking is on; a cut-off reply is all thinking."""
    if THINK_END in raw:
        head, tail = raw.split(THINK_END, 1)
        return head.replace("<think>", "").strip(), tail.strip()
    if thinking:
        return raw.replace("<think>", "").strip(), ""
    return "", raw.strip()
