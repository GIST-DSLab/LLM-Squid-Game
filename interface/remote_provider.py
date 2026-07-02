"""LLMProvider that delegates to a participant-hosted HTTP endpoint (BYOE).

Used by the **LLM Arena**: a participant runs their own model behind an HTTP
endpoint; the Web Arena server drives a full split-call season, calling this
provider for every task / probe / forfeit LLM turn, and scores the result with
the *same* Core Engine used for the seeded runs. That means an arena entry is
measured identically to the built-in leaderboard models.

This lives in the interface layer (not ``src/squid_game/providers/``) because
it is a deployment concern of the Web Arena, not part of the benchmark engine.
It subclasses the engine's public ``LLMProvider`` ABC — importing core is fine;
the no-core-modification rule is about not *editing* engine files.

Contract ("both" supported, auto-detected):
    Request body (superset — a server may read whichever it understands)::
        {
          "model": <label>,
          "messages": [{"role": "system", ...}, {"role": "user", ...}],
          "temperature": float, "max_tokens": int,
          "system": <concatenated system text>,   # convenience for minimal servers
          "user":   <concatenated user text>
        }
    Response — the answer text is located flexibly, covering OpenAI-compatible
    servers and minimal custom ones::
        choices[0].message.content            (OpenAI chat completions)
        choices[0].text                       (OpenAI legacy completions)
        content | text | completion | response | output | answer   (custom)
    Reasoning/thinking, when present, is read from
    ``choices[0].message.reasoning_content`` / ``reasoning`` or a top-level
    ``reasoning`` / ``reasoning_content`` / ``thinking`` field, and feeds the
    Reasoning-Investment (RI) metric. Endpoints that don't expose reasoning
    simply score RI = 0.

Security note (SSRF): this POSTs to a participant-supplied URL from the
server. Only http/https is allowed and every call is time-boxed, but a
hardened public deployment should additionally block internal address ranges
(link-local, RFC-1918, metadata IPs) or route this through an egress proxy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from squid_game.providers.base import CompletionResult, LLMProvider

# Per-turn call order in the split-call pipeline (Unit 15 + 17).
_PHASE_CYCLE = ("task", "probe", "forfeit")


class RemoteEndpointError(RuntimeError):
    """Raised when the participant endpoint is unreachable or unparseable.

    Propagating this aborts the season so a broken endpoint never yields a
    fabricated score; the arena run is marked ``error`` with this message.
    """


@dataclass
class ArenaProgress:
    """Thread-safe live progress for one arena run (polled by the client)."""

    calls_done: int = 0
    calls_total: int = 0
    phase: str = "starting"
    status: str = "running"  # running | done | error
    session_id: str | None = None
    final_score: float | None = None
    forfeited: bool | None = None
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def bump(self, phase: str) -> None:
        with self._lock:
            self.calls_done += 1
            self.phase = phase

    def finish(
        self, *, session_id: str, final_score: float, forfeited: bool | None
    ) -> None:
        with self._lock:
            self.session_id = session_id
            self.final_score = final_score
            self.forfeited = forfeited
            self.status = "done"
            self.phase = "done"

    def fail(self, error: str) -> None:
        with self._lock:
            self.status = "error"
            self.error = error

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "calls_done": self.calls_done,
                "calls_total": self.calls_total,
                "phase": self.phase,
                "session_id": self.session_id,
                "final_score": self.final_score,
                "forfeited": self.forfeited,
                "error": self.error,
            }


class RemoteProvider(LLMProvider):
    """LLMProvider backed by a participant HTTP endpoint."""

    def __init__(
        self,
        url: str,
        model_label: str,
        *,
        auth_header: str | None = None,
        auth_value: str | None = None,
        timeout: float = 60.0,
        progress: ArenaProgress | None = None,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Endpoint URL must be an absolute http(s) URL.")
        self._url = url
        self._model = model_label
        self._headers = {"Content-Type": "application/json"}
        if auth_header and auth_value:
            self._headers[auth_header] = auth_value
        self._timeout = timeout
        self._progress = progress
        self._n = 0

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        phase = _PHASE_CYCLE[self._n % len(_PHASE_CYCLE)]
        self._n += 1

        system = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "system"
        )
        user = "\n\n".join(
            m["content"] for m in messages if m.get("role") == "user"
        )
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Convenience fields so a minimal custom endpoint need not parse
            # the OpenAI ``messages`` array.
            "system": system,
            "user": user,
        }

        text, thinking_text, thinking_tokens, in_tok, out_tok = self._call(body)
        if self._progress is not None:
            self._progress.bump(phase)
        return CompletionResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            finish_reason="stop",
        )

    def _call(self, body: dict):
        last_exc: Exception | None = None
        for _attempt in range(2):  # one retry for transient failures
            try:
                resp = httpx.post(
                    self._url, json=body, headers=self._headers, timeout=self._timeout
                )
                resp.raise_for_status()
                return self._parse(resp.json())
            except RemoteEndpointError:
                raise
            except Exception as exc:  # noqa: BLE001 — surfaced to the participant
                last_exc = exc
        raise RemoteEndpointError(f"Endpoint call failed: {last_exc}")

    @staticmethod
    def _parse(data):
        """Locate the answer text (+ optional reasoning / usage) in a response.

        Supports OpenAI chat/legacy shapes and flat custom shapes.
        """
        text: str | None = None
        thinking_text: str | None = None
        thinking_tokens = 0
        in_tok = 0
        out_tok = 0

        if isinstance(data, str):
            text = data
        elif isinstance(data, dict):
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0] or {}
                msg = first.get("message") or {}
                text = msg.get("content") or first.get("text")
                thinking_text = msg.get("reasoning_content") or msg.get("reasoning")
            if text is None:
                for key in ("content", "text", "completion", "response", "output", "answer"):
                    val = data.get(key)
                    if isinstance(val, str):
                        text = val
                        break
            if thinking_text is None:
                for key in ("reasoning", "reasoning_content", "thinking"):
                    val = data.get(key)
                    if isinstance(val, str):
                        thinking_text = val
                        break
            usage = data.get("usage") or {}
            in_tok = int(usage.get("prompt_tokens") or 0)
            out_tok = int(usage.get("completion_tokens") or 0)
            details = usage.get("completion_tokens_details") or {}
            thinking_tokens = int(details.get("reasoning_tokens") or 0)

        if not isinstance(text, str) or text == "":
            raise RemoteEndpointError(
                "Could not find a non-empty text answer in the endpoint response."
            )
        if not out_tok:
            out_tok = len(text.split())
        if thinking_text and not thinking_tokens:
            thinking_tokens = len(thinking_text.split())
        return text, thinking_text, thinking_tokens, in_tok, out_tok
