"""squid5's Ollama provider (squid5/core/providers.py ``Ollama`` + web/server/engine.py ``StreamingOllama``) for the
browser engine: the same payload and the same ``Reply``, made with ``fetch`` instead of httpx, and async. The browser
calls the thin Worker's Ollama-compatible ``<worker>/llm/api/chat`` with the game token as the Bearer value; the
Worker swaps in the key (web/cloudflare/src/keys.py) and passes Ollama's answer (or its NDJSON stream) through.

- Without ``on_delta``: ``"stream": false``, one JSON answer (the provider's call).
- With ``on_delta``: ``"stream": true`` (NDJSON); each piece of thinking / answer goes to ``on_delta(kind, piece)``,
  ``"reset"`` when an attempt starts. The returned Reply is what the non-streaming call returns: content,
  ``eval_count`` (generated tokens, thinking included; what the engine charges), ``prompt_eval_count``, thinking and
  ``done_reason == "length"``.
- Retries as ``Provider.complete``: ``retries`` more attempts after a failed one, sleeping min(30, 2**attempt) s, with
  THE SAME KEY. There is no other key to fall back to (keys.py). A ``Fatal`` error (the Worker refused the call: a
  per-game or per-IP limit, a bad or expired token, a model not on the allow-list, key 3 out of quota = 402) is not
  retried; its message is the Worker's Korean ``detail``.

``transport(url, headers, payload, timeout, stream)`` is injectable: ``js_transport`` in the Worker, a fake in tests.
It returns a dict (stream False) or an async iterator of decoded lines (stream True), and raises ``OllamaError`` on
an HTTP error status.
"""

from __future__ import annotations

import asyncio
import json

from squid5.core.providers import Reply

BASE_URL = "https://ollama.com"


class OllamaError(RuntimeError):
    pass


class Fatal(OllamaError):
    """Not worth retrying: the Worker said no (limits, token, model, quota)."""


FATAL_STATUS = (400, 401, 402, 403, 404, 413)


def http_error(status: int, body: str) -> OllamaError:
    """The error for an HTTP failure: the Worker's JSON ``{"detail", "code"}`` when there is one."""
    detail, code = body[:300], ""
    try:
        j = json.loads(body)
        if isinstance(j, dict):
            detail, code = str(j.get("detail") or j.get("error") or detail)[:300], str(j.get("code") or "")
    except ValueError:
        pass
    cls = Fatal if status in FATAL_STATUS or code.startswith("limit") else OllamaError
    return cls(f"HTTP {status}: {detail}")


def payload_of(model: str, messages: list[dict], cap: int, think, temperature: float, stream: bool) -> dict:
    p = {"model": model, "messages": messages, "stream": stream, "options": {"temperature": temperature, "num_predict": cap}}
    if think is not None:
        p["think"] = think
    return p


async def _attempt(transport, url, headers, payload, timeout, on_delta) -> Reply:
    if on_delta is None:
        j = await transport(url, headers, payload, timeout, False)
        msg = j.get("message") or {}
        return Reply(msg.get("content") or "", int(j.get("eval_count") or 0), int(j.get("prompt_eval_count") or 0),
                     msg.get("thinking") or "", j.get("done_reason") == "length")
    content, thinking, last = [], [], {}
    lines = await transport(url, headers, payload, timeout, True)
    on_delta("reset", "")
    async for line in lines:
        if not line.strip():
            continue
        j = json.loads(line)
        if j.get("error"):
            raise OllamaError(f"ollama stream: {j['error']}")
        msg = j.get("message") or {}
        for key, buf in (("thinking", thinking), ("content", content)):
            if msg.get(key):
                buf.append(msg[key])
                on_delta("text" if key == "content" else "thinking", msg[key])
        if j.get("done"):
            last = j
    return Reply("".join(content), int(last.get("eval_count") or 0), int(last.get("prompt_eval_count") or 0),
                 "".join(thinking), last.get("done_reason") == "length")


async def complete(transport, key: str, model: str, messages: list[dict], cap: int, think=None, temperature=1.0,
                   timeout: float = 300.0, retries: int = 2, on_delta=None, base_url: str = "", sleep=asyncio.sleep
                   ) -> Reply:
    url = (base_url or BASE_URL) + "/api/chat"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = payload_of(model, messages, cap, think, temperature, on_delta is not None)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await _attempt(transport, url, headers, payload, timeout, on_delta)
        except Fatal:
            raise
        except Exception as err:  # noqa: BLE001 - HTTP status, network, a stream error: retried like the provider
            last = err
            if attempt < retries:
                await sleep(min(30, 2 ** attempt))
    raise OllamaError(f"ollama:{model} failed after retries: {last}")


# --- the browser's transport (Pyodide in a Web Worker only) -------------------------------------------------------------

async def js_transport(url: str, headers: dict, payload: dict, timeout: float, stream: bool):
    import js
    from pyodide.ffi import to_js

    opts = to_js({"method": "POST", "headers": headers, "body": json.dumps(payload),
                  "signal": js.AbortSignal.timeout(int(timeout * 1000))}, dict_converter=js.Object.fromEntries)
    resp = await js.fetch(url, opts)
    if not resp.ok:
        raise http_error(int(resp.status), (await resp.text())[:2000])
    if not stream:
        return json.loads(await resp.text())
    return _lines(resp.body.getReader())


async def _lines(reader):
    import codecs

    dec, buf = codecs.getincrementaldecoder("utf-8")(), ""
    while True:
        chunk = await reader.read()
        if chunk.done:
            break
        buf += dec.decode(chunk.value.to_bytes())
        *done, buf = buf.split("\n")
        for line in done:
            yield line
    buf += dec.decode(b"", final=True)
    if buf:
        yield buf
