"""A deterministic stand-in for Ollama, for local tests only (``MODEL_STUB = "on"`` in .dev.vars; never in production).

It answers the engine's own formats without a network: DONE at the opening turn, LEAVE in a chat, GIVE 0 at a
decision, and at SOLVE the first action with a BELIEF line; 40 tokens a reply. Streaming yields the thinking, the
answer and the final counts as Ollama's NDJSON does, so the watched-SOLVE path is exercised too.
"""

from __future__ import annotations

import json

from squid5.core.puzzle import ACTIONS
from web.server import engine as E


def answer(user: str) -> str:
    ph = E.phase_of(user)
    text = {"opening": "DONE", "chat": "LEAVE: ok", "decision": "DECISION: GIVE 0: no"}.get(ph)
    if text is None:
        text = ("BELIEF: " + ", ".join(f"{a} {100 if a == ACTIONS[0] else 0}" for a in ACTIONS) +
                "\nACTIONS: " + ACTIONS[0])
    return text


async def transport(url, headers, payload, timeout, stream):
    text = answer(payload["messages"][-1]["content"])
    if not stream:
        return {"message": {"content": text, "thinking": "stub"}, "eval_count": 40, "prompt_eval_count": 10,
                "done_reason": "stop"}

    async def lines():
        yield json.dumps({"message": {"thinking": "stub thinking "}})
        yield json.dumps({"message": {"content": text}})
        yield json.dumps({"done": True, "eval_count": 40, "prompt_eval_count": 10, "done_reason": "stop"})
    return lines()
