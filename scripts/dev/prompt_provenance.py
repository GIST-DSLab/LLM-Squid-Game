"""Line-level source attribution for the prompt diagram.

The diagram at ``docs/reports/2026-09-10-ransom-r6-pilot-eli5.html#pstruct-base``
is rendered from the production renderers by
``scripts/dev/build_survival_prompt_flow.py``. This module re-runs the very same
``render_pair`` with the Jinja environment instrumented: every template render
(top-level and ``{% include %}``), every macro call, and the handful of Python
functions that assemble prompt text wrap their output in invisible markers.
Parsing the markers back out gives, for every line of every message, the
innermost source that produced the whole line, plus the chain of sources around
it.

Nothing here is inferred from wording. The marker-free text is compared
byte-for-byte with the plain render, and a field whose instrumented render does
not strip back to the exact bytes the model is sent raises
``ProvenanceMismatch`` instead of being attributed -- an attribution attached to
text the model never saw would be worse than none.

Leading/trailing whitespace is always moved OUTSIDE a marker pair, so callers
that ``.strip()`` a rendered string trim exactly what they trim in production.

Run ``uv run python scripts/dev/prompt_provenance.py`` to print the default
combination's blocks.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

ROOT = Path(__file__).resolve().parents[2]
GAME_DIR = ROOT / "game" / "squid_game"
PROMPTS_DIR = GAME_DIR / "prompts"

OPEN, SEP, CLOSE = "\ue000", "\ue001", "\ue002"
_MARKS = re.compile(f"{OPEN}[^{SEP}]*{SEP}|{CLOSE}")
_TOKEN = re.compile(f"{OPEN}([^{SEP}]*){SEP}|{CLOSE}")

#: The copy of the system prompt's decline block that the ransom call restates.
OUTCOME_COPY = "py:core/turn_conditions.py#outcome_block"

#: How each model's chat template wraps one system and one user message.
#: ``tk`` is a literal token, ``nt`` a note. Sources:
#:   gptoss -- the Ollama registry template layer of ``gpt-oss:120b`` (the
#:     ``gpt-oss:120b-cloud`` config names ``remote_model: gpt-oss:120b``);
#:     role=system is written into the developer block, after a fixed system
#:     block. ``think: "medium"`` -> "Reasoning: medium".
#:   gemma4 -- Ollama ``model/renderers/gemma4.go`` (``renderer: gemma4``;
#:     ``gemma4:cloud`` -> ``gemma4:31b``). ``think: true`` -> ``<|think|>``.
#:   glm -- Ollama ``model/renderers/glm47.go``. REFERENCE ONLY: the
#:     ``glm-5.3-flash`` cloud config publishes no renderer.
CHAT_TEMPLATES: dict[str, dict[str, list[list[str]]]] = {
    "gptoss": {
        "sysOpen": [["tk", "<|start|>system<|message|>"], ["nt", "고정 문구 — 우리가 쓴 글 아님"], ["tk", "<|end|>"],
                    ["tk", "<|start|>developer<|message|>"], ["nt", "\\n\\n# Instructions\\n\\n"]],
        "sysClose": [["tk", "<|end|>"]],
        "userOpen": [["tk", "<|start|>user<|message|>"]],
        "userClose": [["tk", "<|end|>"], ["tk", "<|start|>assistant"], ["nt", "← 여기서부터 모델이 쓴다"]],
    },
    "gemma4": {
        "sysOpen": [["tk", "<bos>"], ["tk", "<|turn>system"], ["nt", "\\n"], ["tk", "<|think|>"], ["nt", "\\n"]],
        "sysClose": [["tk", "<turn|>"], ["nt", "\\n"]],
        "userOpen": [["tk", "<|turn>user"], ["nt", "\\n"]],
        "userClose": [["tk", "<turn|>"], ["nt", "\\n"], ["tk", "<|turn>model"], ["nt", "\\n ← 여기서부터 모델이 쓴다"]],
    },
    "glm": {
        "sysOpen": [["tk", "[gMASK]<sop>"], ["tk", "<|system|>"]],
        "sysClose": [["nt", "닫는 토큰 없음 — 곧바로 <|user|>"]],
        "userOpen": [["tk", "<|user|>"]],
        "userClose": [["tk", "<|assistant|>"], ["tk", "<think>"], ["nt", "← 여기서부터 모델이 쓴다"]],
    },
}


class ProvenanceMismatch(AssertionError):
    """Instrumented text did not strip back to the production bytes."""


def strip_marks(text: str) -> str:
    return _MARKS.sub("", text)


def _wrap(label: str, text: Any) -> Any:
    """Wrap ``text`` in a marker pair, keeping its outer whitespace outside."""
    if not isinstance(text, str) or not text.strip():
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text[len(lead): len(text) - len(trail)]
    return f"{lead}{OPEN}{label}{SEP}{core}{CLOSE}{trail}"


def _rel(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base).as_posix()
    except ValueError:
        return path.name


@contextmanager
def instrument(builder: Any) -> Iterator[None]:
    """Mark every prompt source for the duration of the block.

    Args:
        builder: The imported ``build_survival_prompt_flow`` module. Its
            module-level names are where ``render_pair`` looks the Python
            assemblers up, so those are the names that get wrapped.
    """
    from jinja2.runtime import Macro
    from squid_game import prompts
    from squid_game.agents import _parsing
    from squid_game.core import ransom, turn_conditions, turn_prompts

    env = prompts._env
    restore: list[Callable[[], None]] = []

    def patch(obj: Any, name: str, new: Any) -> None:
        had_own = name in vars(obj)
        old = vars(obj).get(name)
        setattr(obj, name, new)
        restore.append(lambda: setattr(obj, name, old) if had_own else delattr(obj, name))

    # Templates: top-level renders and {% include %} both go through
    # root_render_func, so wrapping it at load time covers both.
    orig_load = env._load_template

    def load(name: str, globals: Any) -> Any:
        template = orig_load(name, globals)
        if not getattr(template, "_prov_wrapped", False):
            inner, label = template.root_render_func, "tpl:" + template.name

            def root(ctx: Any, _inner: Any = inner, _label: str = label) -> Iterator[str]:
                yield _wrap(_label, "".join(_inner(ctx)))

            template.root_render_func = root
            template._prov_wrapped = True
        return template

    # Macros ({% import %} / {% from ... import %}): label with the file the
    # macro is defined in, plus an ALL-CAPS key argument when there is one
    # (the threat-module sentences are selected that way).
    orig_call = Macro.__call__

    def call(self: Any, *args: Any, **kwargs: Any) -> Any:
        rv = orig_call(self, *args, **kwargs)
        rel = _rel(Path(self._func.__code__.co_filename), PROMPTS_DIR)
        key = next((a for a in args if isinstance(a, str) and re.fullmatch(r"[A-Z][A-Z_]+", a)), None)
        return _wrap(f"mac:{rel}#{self.name}" + (f"({key})" if key else ""), rv)

    def py(module: Any, name: str, source: Any, *, clean_input: bool = False, wrap: bool = True) -> None:
        fn = getattr(module, name)
        rel = _rel(Path(source.__file__), GAME_DIR)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if clean_input:
                args = tuple(strip_marks(a) if isinstance(a, str) else a for a in args)
                kwargs = {k: strip_marks(v) if isinstance(v, str) else v for k, v in kwargs.items()}
            rv = fn(*args, **kwargs)
            return _wrap(f"py:{rel}#{name}", rv) if wrap else rv

        patch(module, name, wrapped)

    env.cache.clear()
    patch(env, "_load_template", load)
    patch(Macro, "__call__", call)
    py(builder, "describe_ransom_rule", ransom)
    py(builder, "build_system_prompt", turn_prompts)
    py(builder, "compose_task_call_user_message", turn_prompts)
    py(builder, "build_task_call_message", _parsing)
    py(builder, "build_ransom_call_message", _parsing)
    py(builder, "outcome_block", turn_conditions, clean_input=True)
    py(builder, "states_outcome", turn_conditions, clean_input=True, wrap=False)
    py(turn_prompts, "format_outcome_history_block", turn_prompts)
    try:
        yield
    finally:
        for undo in reversed(restore):
            undo()
        env.cache.clear()


def _spans(marked: str) -> tuple[str, list[tuple[int, int, str, int]]]:
    """Clean text plus (start, end, label, depth) spans in clean coordinates."""
    out: list[str] = []
    pos, stack, spans, last = 0, [], [], 0
    for m in _TOKEN.finditer(marked):
        chunk = marked[last: m.start()]
        out.append(chunk)
        pos += len(chunk)
        last = m.end()
        if m.group(0) == CLOSE:
            start, label = stack.pop()
            spans.append((start, pos, label, len(stack)))
        else:
            stack.append((pos, m.group(1)))
    out.append(marked[last:])
    if stack:
        raise ProvenanceMismatch("unbalanced provenance markers")
    return "".join(out), spans


def line_blocks(marked: str, clean: str, chains: dict[tuple[str, ...], int]) -> list[list[int]]:
    """Group the lines of one message by the innermost source covering each line.

    Returns ``[chain_index, first_line, end_line]`` triples (end exclusive) over
    ``clean.split("\\n")``. Blank lines between two different sources belong to
    no block; the diagram renders them as a gap.
    """
    text, spans = _spans(marked)
    if text != clean:
        raise ProvenanceMismatch("instrumented render differs from the production bytes")
    lines = clean.split("\n")
    owner: list[int | None] = []
    start = 0
    for line in lines:
        end = start + len(line)
        if line.strip():
            cover = sorted((s for s in spans if s[0] <= start and s[1] >= end), key=lambda s: s[3])
            chain = tuple(s[2] for s in cover) or ("unattributed",)
            owner.append(chains.setdefault(chain, len(chains)))
        else:
            owner.append(None)
        start = end + 1
    blocks: list[list[int]] = []
    i = 0
    while i < len(lines):
        if owner[i] is None:
            i += 1
            continue
        j = i + 1
        while j < len(lines):
            if owner[j] == owner[i]:
                j += 1
                continue
            if owner[j] is None:
                k = j
                while k < len(lines) and owner[k] is None:
                    k += 1
                if k < len(lines) and owner[k] == owner[i]:
                    j = k + 1
                    continue
            break
        blocks.append([owner[i], i, j])
        i = j
    return blocks


def attribute_pair(builder: Any, *args: Any) -> tuple[dict[str, Any], list[list[str]]]:
    """Attribute every message of one ``render_pair`` combination.

    Returns ``({arm: {"system": blocks, "task": blocks, "decision": blocks}},
    chain_table)``. A block is ``[chain, first_line, end_line, origin, only]``:
    ``origin`` is the chain of the identical system-prompt line for a line the
    ransom call copies out of the system prompt (``OUTCOME_COPY``), else -1;
    ``only`` is 1 when the block's text does not occur in the other arm's same
    message.
    """
    clean = builder.render_pair(*args)
    with instrument(builder):
        marked = builder.render_pair(*args)
    chains: dict[tuple[str, ...], int] = {}
    out: dict[str, Any] = {}
    for arm in ("control", "threat"):
        out[arm] = {field: line_blocks(marked[arm][field], clean[arm][field], chains)
                    for field in ("system", "task", "decision")}
    leaf = {index: chain[-1] for chain, index in chains.items()}
    for arm in ("control", "threat"):
        sys_lines = clean[arm]["system"].split("\n")
        where: dict[str, int] = {}
        for chain, a, b in out[arm]["system"]:
            for i in range(a, b):
                where.setdefault(sys_lines[i].strip(), chain)
        out[arm]["system"] = [[c, a, b, -1] for c, a, b in out[arm]["system"]]
        for field in ("task", "decision"):
            lines = clean[arm][field].split("\n")
            split: list[list[int]] = []
            for chain, a, b in out[arm][field]:
                if leaf[chain] != OUTCOME_COPY:
                    split.append([chain, a, b, -1])
                    continue
                for i in range(a, b):
                    if lines[i].strip():
                        split.append([chain, i, i + 1, where.get(lines[i].strip(), -1)])
            out[arm][field] = split
    for arm, other in (("control", "threat"), ("threat", "control")):
        for field, blocks in out[arm].items():
            theirs = clean[other][field]
            lines = clean[arm][field].split("\n")
            for block in blocks:
                body = "\n".join(lines[block[1]: block[2]]).strip()
                block.append(int(body not in theirs))
    table = [list(chain) for chain, _ in sorted(chains.items(), key=lambda kv: kv[1])]
    return out, table


def attribute_all(builder: Any, combos: list[tuple[Any, ...]], keys: list[str]) -> dict[str, Any]:
    """Attribute every combination, sharing one chain table across all of them."""
    index: dict[tuple[str, ...], int] = {}
    cases: dict[str, Any] = {}
    for key, combo in zip(keys, combos):
        pair, local = attribute_pair(builder, *combo)
        remap = [index.setdefault(tuple(chain), len(index)) for chain in local]
        for arm in pair.values():
            for blocks in arm.values():
                for block in blocks:
                    block[0] = remap[block[0]]
                    if block[3] >= 0:
                        block[3] = remap[block[3]]
        cases[key] = pair
    table = [list(chain) for chain, _ in sorted(index.items(), key=lambda kv: kv[1])]
    return {"prompts_root": "game/squid_game/prompts", "python_root": "game/squid_game",
            "chains": table, "cases": cases}


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(ROOT / "game"))
    sys.path.insert(0, str(ROOT))
    from scripts.dev import build_survival_prompt_flow as builder

    pair, table = attribute_pair(builder)
    clean = builder.render_pair()
    for arm in ("control", "threat"):
        for field in ("system", "task", "decision"):
            lines = clean[arm][field].split("\n")
            print(f"\n######## {arm} · {field}")
            for chain, a, b, origin, only in pair[arm][field]:
                src = table[chain][-1] + (f"  <- {table[origin][-1]}" if origin >= 0 else "")
                print(f"  [{a:>2}-{b:>2}] {'*' if only else ' '} {src:<90} | {lines[a][:50]}")
