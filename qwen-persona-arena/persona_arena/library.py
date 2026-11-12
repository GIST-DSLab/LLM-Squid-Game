"""The qwen-neurons-site data (Qwen3-8B, 36 x 12,288 MLP neurons, each pushed up and down on "Who are you?", replies
labelled by Claude Haiku 5.5) and the persona file the server reads.

    python -m persona_arena.library search "friend|loyal" --min-c 8
    python -m persona_arena.library show 8 3752 -1
    python -m persona_arena.library controls --layers 8 13 20 22 --k 2 --seed 0
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
from functools import lru_cache
from pathlib import Path

import yaml

from .steer import Persona, Push

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "qwen-neurons"
PERSONAS = ROOT / "personas.yaml"
SITE = "https://qwen-neurons-site.vercel.app"
N_PER_LAYER = 12288
# library.json row fields: L, n, s, persona, cat, w, c, tags, text, stop, a, before
CATS = ["default_assistant", "altered_assistant", "persona", "incoherent", "other"]


@lru_cache(maxsize=1)
def library() -> list[list]:
    return json.loads((DATA / "library.json").read_text())["rows"]


@lru_cache(maxsize=1)
def atlas() -> bytes:
    """One byte per neuron (L * 12288 + n): low nibble = code of the + push, high nibble = code of the - push."""
    return base64.b64decode(json.loads((DATA / "atlas.json").read_text())["b64"])


def atlas_code(layer: int, neuron: int, sign: int) -> str:
    b = atlas()[layer * N_PER_LAYER + neuron]
    return (CATS + ["retrying"])[(b & 15) if sign > 0 else (b >> 4)]


def row_dict(r: list) -> dict:
    return {"L": r[0], "n": r[1], "sign": r[2], "label": r[3], "cat": CATS[r[4]], "weird": r[5], "coherence": r[6],
            "tags": r[7], "text": r[8], "alpha": r[10]}


def find(layer: int, neuron: int, sign: int) -> dict | None:
    for r in library():
        if r[0] == layer and r[1] == neuron and r[2] == sign:
            return row_dict(r)
    return None


def search(pattern: str, min_c: int = 7, cats=("altered_assistant", "persona")) -> list[dict]:
    rx = re.compile(pattern, re.I)
    keep = {CATS.index(c) for c in cats}
    hits = [row_dict(r) for r in library()
            if r[6] >= min_c and r[4] in keep and rx.search(f"{r[3]} | {' '.join(r[7])} | {r[8]}")]
    return sorted(hits, key=lambda d: (-d["coherence"], d["weird"]))


def controls(layers: list[int], k: int, alpha: float, seed: int) -> list[dict]:
    """Dose-matched nulls: neurons whose push (same layer, same sign) left the reply a default assistant on the site.
    Steering itself costs capability; a persona effect has to beat these, not just the unsteered model."""
    rng = random.Random(seed)
    out = []
    for L in layers:
        pool = [(n, s) for n in range(N_PER_LAYER) for s in (1, -1) if atlas_code(L, n, s) == "default_assistant"]
        for n, s in rng.sample(pool, k):
            out.append({"pid": f"control_L{L}_{n}{'p' if s > 0 else 'm'}", "L": L, "n": n, "sign": s, "alpha": alpha})
    return out


def load_personas(path: Path = PERSONAS) -> dict[str, Persona]:
    raw = yaml.safe_load(path.read_text())["personas"]
    out = {}
    for pid, spec in raw.items():
        pushes = tuple(Push(int(L), int(n), int(s), float(a)) for L, n, s, a in spec.get("neurons", []))
        out[pid] = Persona(pid, pushes, spec.get("label", ""), spec.get("axis", ""), spec.get("expect", ""),
                           {k: v for k, v in spec.items() if k not in ("neurons", "label", "axis", "expect")})
    return out


def _main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("pattern")
    s.add_argument("--min-c", type=int, default=7)
    s.add_argument("--top", type=int, default=30)
    s.add_argument("--all-cats", action="store_true")
    sh = sub.add_parser("show")
    sh.add_argument("L", type=int)
    sh.add_argument("n", type=int)
    sh.add_argument("sign", type=int)
    c = sub.add_parser("controls")
    c.add_argument("--layers", type=int, nargs="+", required=True)
    c.add_argument("--k", type=int, default=1)
    c.add_argument("--alpha", type=float, default=1.0)
    c.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "search":
        cats = CATS if a.all_cats else ("altered_assistant", "persona")
        for d in search(a.pattern, a.min_c, cats)[:a.top]:
            print(f"L{d['L']:>2} n{d['n']:>5} {d['sign']:+d} a={d['alpha']} c={d['coherence']} w={d['weird']} "
                  f"{d['cat'][:7]} | {d['label']} | {d['text'][:120]!r}")
    elif a.cmd == "show":
        d = find(a.L, a.n, a.sign)
        print(json.dumps(d or {"atlas": atlas_code(a.L, a.n, a.sign)}, indent=1, ensure_ascii=False))
    else:
        for d in controls(a.layers, a.k, a.alpha, a.seed):
            print(f"  {d['pid']}: {{axis: control, label: \"null (default_assistant on the site)\", "
                  f"neurons: [[{d['L']}, {d['n']}, {d['sign']}, {d['alpha']}]]}}")


if __name__ == "__main__":
    _main()
