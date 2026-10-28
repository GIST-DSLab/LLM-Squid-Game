"""Activation steering for Hugging Face Qwen models: a spec, a hook, one dose unit.

A :class:`Steer` moves the residual stream at one decoder layer by ``dose`` x the median norm of the residual leaving
that layer (the "rel" unit of neuron-explorer's ``--dose-unit rel``; doses of 0.5-1.0 keep the text coherent, about 2
breaks it):

* neuron mode: a forward pre-hook on ``mlp.down_proj`` adds ``c * w_i`` to the activations of neurons ``n_i`` (the
  input of down_proj, silu(gate) * up), so the residual moves by ``c * W_down[:, n] @ w``. ``c`` makes that move
  ``|dose| x median`` long; for one neuron of weight 1 the push is the explorer's ``dose x median / ||W_down[:, n]||``.
* vector mode (persona vector): a forward hook on decoder layer L adds ``dose x median x v / ||v||`` to its output.

The push is added at every position, prompt and reply alike, and only inside ``with steering(model, steers):``.
A directions file (``directions.example.json``) names the directions; a condition name such as
``qwen3-8b+survival@1.0`` picks the base model alias and the directions with their doses (:func:`parse_condition`).
torch and transformers are imported inside the functions that need them, so specs and names parse without them.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "Qwen/Qwen3-8B"  # neuron-explorer's model is "Qwen/Qwen3.5-4B" (its --model default); alias in the directions file
# Neutral English text for the residual-norm median and the coherence check (nothing about shutdown, sharing or teams).
NEUTRAL = (
    "Explain how a refrigerator keeps food cold.",
    "Write two sentences about the history of the printing press.",
    "What is the difference between weather and climate?",
    "Describe a quiet morning in a small coastal town.",
    "List three common uses of baking soda in a kitchen.",
    "How do bees find their way back to the hive?",
    "Summarize the plot of a story about a lost umbrella.",
    "Why does the sky look blue during the day?",
    "Give a short recipe for tomato soup.",
    "What does a librarian do during a typical day?",
    "Explain what a prime number is, with two examples.",
    "Describe the sound of rain on a tin roof.",
    "How is paper made from wood?",
    "What are the main parts of a bicycle?",
    "Write a short note thanking a neighbour for watering the plants.",
    "Explain why ice floats on water.",
)
TERM = re.compile(r"^([A-Za-z][\w-]*)@([+-]?(?:\d+\.?\d*|\.\d+))$")


@dataclass
class Steer:
    name: str
    layer: int
    dose: float
    median: float  # median residual norm leaving `layer` (the rel unit)
    neurons: list[int] = field(default_factory=list)  # neuron mode
    weights: list[float] | None = None  # per neuron (sign = direction of the push); default all 1
    vector: object = None  # vector mode: a [hidden] array or tensor (direction only; its norm is ignored)


def parse_condition(name: str) -> tuple[str, list[tuple[str, float]]]:
    """``alias[+direction@dose]...`` -> (alias, [(direction, dose), ...]); ``qwen3-8b`` alone is the unsteered model."""
    alias, *terms = name.strip().split("+")
    if not alias or not re.fullmatch(r"[\w.:/-]+", alias):
        raise ValueError(f"bad model alias in {name!r}")
    out = []
    for t in terms:
        m = TERM.match(t)
        if not m:
            raise ValueError(f"bad steering term {t!r} in {name!r} (want direction@dose, e.g. survival@1.0)")
        out.append((m.group(1), float(m.group(2))))
    if len({d for d, _ in out}) != len(out):
        raise ValueError(f"a direction appears twice in {name!r}")
    return alias, out


def decoder_layers(model):
    """The decoder's layer list: Qwen3 ``model.model.layers``, Qwen3.5 ``model.model.language_model.layers``, or the
    first ModuleList whose entries have ``mlp.down_proj``."""
    import torch
    for path in ("model.language_model.layers", "model.layers", "language_model.model.layers"):
        obj = model
        for part in path.split("."):
            obj = getattr(obj, part, None)
        if isinstance(obj, torch.nn.ModuleList):
            return obj
    for _, mod in model.named_modules():
        if isinstance(mod, torch.nn.ModuleList) and len(mod) and hasattr(getattr(mod[0], "mlp", None), "down_proj"):
            return mod
    raise ValueError("no decoder layers with mlp.down_proj found")


def _hidden(out):
    return out[0] if isinstance(out, tuple) else out


def push_vector(model, s: Steer):
    """The residual move of a Steer, a [hidden] float32 tensor of norm |dose| x median (zero at dose 0)."""
    import torch
    if s.neurons:
        w_down = decoder_layers(model)[s.layer].mlp.down_proj.weight
        w = torch.tensor(s.weights or [1.0] * len(s.neurons), dtype=torch.float32, device=w_down.device)
        col = w_down[:, list(s.neurons)].detach().float() @ w
    else:
        col = torch.as_tensor(s.vector, dtype=torch.float32)
    return col * (s.dose * s.median / float(col.norm()))


def _install(model, s: Steer):
    import torch
    layer = decoder_layers(model)[s.layer]
    if s.neurons:
        down = layer.mlp.down_proj
        idx = torch.tensor(list(s.neurons), device=down.weight.device)
        w = torch.tensor(s.weights or [1.0] * len(s.neurons), dtype=torch.float32, device=down.weight.device)
        col = down.weight[:, idx].detach().float() @ w
        add = w * (s.dose * s.median / float(col.norm()))

        def pre(_mod, args):
            x = args[0].clone()
            x[..., idx] += add.to(x.dtype)
            return (x, *args[1:])
        return down.register_forward_pre_hook(pre)
    delta = push_vector(model, s)

    def post(_mod, _args, out):
        h = _hidden(out)
        h = h + delta.to(h.device, h.dtype)
        return (h, *out[1:]) if isinstance(out, tuple) else h
    return layer.register_forward_hook(post)


@contextmanager
def steering(model, steers: list[Steer]):
    """Install every push for the body of the with-block and remove them on exit, even after an error."""
    handles = []
    try:
        for s in steers:
            if s.dose:
                handles.append(_install(model, s))
        yield
    finally:
        for h in handles:
            h.remove()


@contextmanager
def capture(model, layers: list[int], mlp: bool = False):
    """Record each layer's output residual ([batch, pos, hidden]) or, with ``mlp``, its down_proj input
    ([batch, pos, d_ff]) for every forward pass in the block: ``{layer: [tensor, ...]}``."""
    got: dict[int, list] = {i: [] for i in layers}
    handles = []
    for i in layers:
        L = decoder_layers(model)[i]
        if mlp:
            handles.append(L.mlp.down_proj.register_forward_pre_hook(
                lambda _m, args, i=i: got[i].append(args[0].detach().float().cpu())))
        else:
            handles.append(L.register_forward_hook(lambda _m, _a, out, i=i: got[i].append(_hidden(out).detach().float().cpu())))
    try:
        yield got
    finally:
        for h in handles:
            h.remove()


def chat_ids(tok, messages: list[dict], think: bool = False, reply: str | None = None):
    """Token ids of a chat (generation prompt added; with ``reply`` the assistant text follows) and the reply's start."""
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=think)
    start = len(tok(text, add_special_tokens=False)["input_ids"])
    ids = tok(text + (reply or ""), add_special_tokens=False)["input_ids"]
    return ids, start


def calibrate(model, tok, layers: list[int], prompts=NEUTRAL) -> dict[int, float]:
    """Median norm of the residual leaving each layer, over every token but the first (an attention sink, as
    neuron-explorer's neuron_stats) of the neutral prompts in chat form."""
    import torch
    with torch.no_grad(), capture(model, layers) as got:
        for p in prompts:
            ids, _ = chat_ids(tok, [{"role": "user", "content": p}])
            model(torch.tensor([ids], device=model.device))
    return {i: float(torch.cat([h[0, 1:].norm(dim=-1) for h in got[i]]).median()) for i in layers}


def median_from_stats(path: str | Path) -> tuple[int, float]:
    """(layer, median) from a neuron-explorer ``stats/<name>_L<l>.npz`` (``resid_norm_q10_50_90``, ``layer``)."""
    import numpy as np
    st = np.load(path, allow_pickle=False)
    return int(st["layer"]), float(st["resid_norm_q10_50_90"][1])


def load_model(model_id: str = DEFAULT_MODEL, dtype: str = "bfloat16", device: str = "auto", yarn: float = 0.0):
    """(model, tokenizer) in eval mode. ``yarn`` > 1 stretches the context with YaRN (Qwen3: factor 4 -> 131,072).
    Qwen3.5 loads as an image-text model in transformers; its text decoder is found by :func:`decoder_layers`."""
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    cfg = AutoConfig.from_pretrained(model_id)
    if yarn > 1:
        cfg.rope_scaling = {"rope_type": "yarn", "factor": yarn,
                            "original_max_position_embeddings": cfg.max_position_embeddings}
    kw = {"config": cfg, "dtype": getattr(torch, dtype), "device_map": device}
    try:
        model = AutoModelForCausalLM.from_pretrained(model_id, **kw)
    except ValueError:  # Qwen3.5 (Qwen3_5ForConditionalGeneration) is not a causal-LM auto class
        from transformers import AutoModelForImageTextToText
        model = AutoModelForImageTextToText.from_pretrained(model_id, **kw)
    return model.eval(), tok


class Directions:
    """A directions file: the base model, the median residual norm per layer, and named directions.

    ``{"model": hf id, "alias": "qwen3-8b", "resid_median": {"18": 41.2}, "directions": {name: entry}}`` where an entry
    is ``{"mode": "neuron", "layer", "neurons", "weights"?}``, ``{"mode": "vector", "layer", "vector": file.npy}``
    (relative to the file), ``{"mode": "random", "layer", "count", "seed"}`` (that many neurons drawn once by the seed,
    the trait neurons of that layer left out) or ``{"mode": "random_vector", "layer", "seed"}``; ``stats`` is kept
    as written by find_directions.py and never read here.
    """

    def __init__(self, data: dict, root: Path = Path(".")):
        self.data, self.root = data, root
        self.alias = data.get("alias") or data["model"].split("/")[-1].lower()
        self.median = {int(k): float(v) for k, v in (data.get("resid_median") or {}).items()}

    @classmethod
    def load(cls, path: str | Path) -> "Directions":
        return cls(json.loads(Path(path).read_text()), Path(path).resolve().parent)

    def names(self) -> list[str]:
        return list(self.data.get("directions") or {})

    def layers(self) -> list[int]:
        return sorted({int(e["layer"]) for e in self.data["directions"].values()})

    def resolve(self, condition: str, d_ff: int, hidden: int) -> list[Steer]:
        """The Steers of a condition name; ``d_ff`` / ``hidden`` size the random draws."""
        import numpy as np
        alias, terms = parse_condition(condition)
        if alias != self.alias:
            raise ValueError(f"model {alias!r} is not served (this server: {self.alias!r})")
        out = []
        for name, dose in terms:
            e = (self.data.get("directions") or {}).get(name)
            if e is None:
                raise ValueError(f"unknown direction {name!r}; known: {self.names()}")
            layer, mode = int(e["layer"]), e.get("mode", "neuron")
            if layer not in self.median:
                raise ValueError(f"no resid_median for layer {layer} (run find_directions.py calibrate)")
            s = Steer(name, layer, dose, self.median[layer])
            rng = np.random.default_rng(int(e.get("seed", 0)))
            if mode == "neuron":
                s.neurons, s.weights = [int(n) for n in e["neurons"]], e.get("weights")
            elif mode == "random":
                used = {int(n) for x in self.data["directions"].values()
                        if x.get("mode", "neuron") == "neuron" and int(x["layer"]) == layer for n in x["neurons"]}
                pool = np.array([n for n in range(d_ff) if n not in used])
                s.neurons = sorted(int(n) for n in rng.choice(pool, size=int(e["count"]), replace=False))
            elif mode == "vector":
                s.vector = np.load(self.root / e["vector"])
            elif mode == "random_vector":
                s.vector = rng.standard_normal(hidden)
            else:
                raise ValueError(f"direction {name!r}: unknown mode {mode!r}")
            out.append(s)
        return out
