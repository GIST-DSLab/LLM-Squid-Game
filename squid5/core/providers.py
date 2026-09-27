"""Model backends that report what a call really generated.

Every backend returns :class:`Reply`, whose ``out_tokens`` is the provider's
own count of generated tokens INCLUDING reasoning -- the number the wallet
charges. ``cap`` is the per-call output ceiling the caller asked for; the
backend passes it to the model (``num_predict`` / ``max_completion_tokens`` /
``CLAUDE_CODE_MAX_OUTPUT_TOKENS``) so a model can never spend more than it
allowed itself, and ``truncated`` says the ceiling was hit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

import httpx


@dataclass
class Reply:
    text: str
    out_tokens: int
    in_tokens: int = 0
    thinking: str = ""
    truncated: bool = False


@dataclass
class ProviderConfig:
    kind: str  # ollama | openai | claude_cli | codex_cli | stub
    model: str
    api_key_env: str = ""
    base_url: str = ""
    think: str | bool | None = None  # ollama `think`, openai `reasoning_effort`, claude `--effort`
    temperature: float = 1.0
    timeout: float = 300.0
    retries: int = 3


Messages = list[dict[str, str]]


class Provider:
    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg

    def complete(self, messages: Messages, cap: int) -> Reply:
        last: Exception | None = None
        for attempt in range(self.cfg.retries + 1):
            try:
                return self._call(messages, cap)
            except (httpx.HTTPError, subprocess.SubprocessError, RuntimeError) as err:
                last = err
                time.sleep(min(30, 2**attempt))
        raise RuntimeError(f"{self.cfg.kind}:{self.cfg.model} failed after retries: {last}")

    def _call(self, messages: Messages, cap: int) -> Reply:
        raise NotImplementedError


def _key(cfg: ProviderConfig, default: str) -> str:
    key = os.environ.get(cfg.api_key_env or default, "")
    if not key:
        raise ValueError(f"environment variable {cfg.api_key_env or default} is not set")  # not retried
    return key


class Ollama(Provider):
    def _call(self, messages, cap):
        payload = {"model": self.cfg.model, "messages": messages, "stream": False,
                   "options": {"temperature": self.cfg.temperature, "num_predict": cap}}
        if self.cfg.think is not None:
            payload["think"] = self.cfg.think
        r = httpx.post((self.cfg.base_url or "https://ollama.com") + "/api/chat", json=payload,
                       headers={"Authorization": f"Bearer {_key(self.cfg, 'OLLAMA_API_KEY')}"},
                       timeout=self.cfg.timeout)
        r.raise_for_status()
        j = r.json()
        msg = j.get("message") or {}
        return Reply(msg.get("content") or "", int(j.get("eval_count") or 0), int(j.get("prompt_eval_count") or 0),
                     msg.get("thinking") or "", j.get("done_reason") == "length")


class OpenAI(Provider):
    def _call(self, messages, cap):
        payload = {"model": self.cfg.model, "messages": messages, "max_completion_tokens": cap,
                   "temperature": self.cfg.temperature}
        if self.cfg.think:
            payload["reasoning_effort"] = self.cfg.think
        r = httpx.post((self.cfg.base_url or "https://api.openai.com/v1") + "/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {_key(self.cfg, 'OPENAI_API_KEY')}"},
                       timeout=self.cfg.timeout)
        r.raise_for_status()
        j = r.json()
        choice, usage = j["choices"][0], j.get("usage") or {}
        msg = choice.get("message") or {}
        return Reply(msg.get("content") or "", int(usage.get("completion_tokens") or 0),
                     int(usage.get("prompt_tokens") or 0), msg.get("reasoning_content") or "",
                     choice.get("finish_reason") == "length")


class ClaudeCLI(Provider):
    """``claude -p`` in print mode: no tools, no settings, subscription login.

    The session markers of a parent Claude Code session are stripped from the
    child environment, and so is ANTHROPIC_API_KEY (it would bill the API).
    """

    def _call(self, messages, cap):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        prompt = "\n\n".join(m["content"] if m["role"] == "user" else f"[assistant]\n{m['content']}"
                             for m in messages if m["role"] != "system")
        cmd = [shutil.which("claude") or "claude", "-p", "--model", self.cfg.model, "--output-format", "json",
               "--no-session-persistence", "--max-turns", "1", "--tools", "", "--setting-sources", "",
               "--mcp-config", '{"mcpServers":{}}', "--strict-mcp-config", "--system-prompt", system]
        if self.cfg.think:
            cmd += ["--effort", str(self.cfg.think)]
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDECODE", "CLAUDE_PID", "ANTHROPIC_API_KEY")}
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(cap)
        with tempfile.TemporaryDirectory() as cwd:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.cfg.timeout,
                               env=env, cwd=cwd)
        try:
            j = json.loads(p.stdout)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"claude -p exit {p.returncode}: {p.stderr[:300]}") from err
        if j.get("is_error") and "output token maximum" in str(j.get("result")):
            return Reply("", cap, 0, "", True)  # the CLI discards a reply that hit the cap; the cap was generated
        if j.get("is_error"):
            raise RuntimeError(f"claude -p error: {str(j.get('result'))[:300]}")
        u = j.get("usage") or {}
        out = int(u.get("output_tokens") or 0)
        return Reply(str(j.get("result") or ""), out, int(u.get("input_tokens") or 0), "", out >= cap)


class CodexCLI(Provider):
    """``codex exec`` with the login's auth.json copied into an empty CODEX_HOME (no AGENTS.md, no config).

    The system prompt replaces Codex's base instructions via ``model_instructions_file``; tools and prompt
    add-ons are disabled. ``codex exec`` has no output-token flag, so ``cap`` is not passed: a reply past it
    is caught by the caller (charged the cap, void). Ported from legacy-2026-09-22 providers/codex_cli.py.
    """

    OFF = ("shell_tool", "unified_exec", "browser_use", "browser_use_external", "in_app_browser", "computer_use",
           "view_image", "image_generation", "multi_agent", "apps", "plugins", "remote_plugin", "skill_search",
           "sleep_tool", "tool_suggest", "goals", "hooks", "personality", "code_mode_host", "in_app_chat",
           "guardian_approval")
    # Captured request 2026-09-28 (codex-cli 0.154.0): without these the model also reads a skills list (~7.6k
    # chars incl. ~/.agents/skills), an <environment_context> (cwd, shell, date, timezone, sandbox) and a
    # web_search tool. With them it gets only our instructions and prompt (plus a request_user_input tool).
    # No token count or budget is sent in the request either way.
    QUIET = ("include_environment_context=false", "include_permissions_instructions=false",
             "skills.include_instructions=false", 'web_search="disabled"')

    def _call(self, messages, cap):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        prompt = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
        with tempfile.TemporaryDirectory() as cwd:
            os.makedirs(f"{cwd}/home")
            shutil.copyfile(f"{home}/auth.json", f"{cwd}/home/auth.json")
            with open(f"{cwd}/instructions.md", "w") as f:
                f.write(system + "\n\nNo tools are available in this session; reply with text only.")
            cmd = [shutil.which("codex") or "codex", "exec", "--json", "--ephemeral", "--ignore-user-config",
                   "--skip-git-repo-check", "--sandbox", "read-only", "-C", cwd, "--model", self.cfg.model,
                   "-c", "model_reasoning_summary=detailed", "-c", f'model_instructions_file="{cwd}/instructions.md"']
            cmd += [x for kv in self.QUIET for x in ("-c", kv)]
            cmd += [x for feat in self.OFF for x in ("--disable", feat)]
            if self.cfg.think:
                cmd += ["-c", f"model_reasoning_effort={self.cfg.think}"]
            env = {k: v for k, v in os.environ.items() if not k.startswith("CODEX_")} | {"CODEX_HOME": f"{cwd}/home"}
            p = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, timeout=self.cfg.timeout,
                               env=env)
        text, thinking, usage = None, [], None
        for line in p.stdout.splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = e.get("item") or {}
            if e.get("type") in ("error", "turn.failed"):
                raise RuntimeError(f"codex exec error: {str(e.get('error') or e.get('message'))[:300]}")
            if e.get("type") == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text") or ""
            elif e.get("type") == "item.completed" and item.get("type") == "reasoning":
                thinking.append(item.get("text") or "")
            elif e.get("type") == "turn.completed":
                usage = e.get("usage") or {}
        if usage is None or text is None:
            raise RuntimeError(f"codex exec exit {p.returncode}: {p.stderr[-300:]}")
        out = int(usage.get("output_tokens") or 0)  # includes reasoning_output_tokens (Responses API)
        return Reply(text.strip(), out, int(usage.get("input_tokens") or 0), "\n".join(thinking), out >= cap)


class Stub(Provider):
    """Offline backend for tests: ``respond(messages, cap) -> Reply``."""

    def __init__(self, cfg: ProviderConfig, respond: Callable[[Messages, int], Reply]):
        super().__init__(cfg)
        self.respond = respond

    def _call(self, messages, cap):
        return self.respond(messages, cap)


def make_provider(cfg: ProviderConfig) -> Provider:
    kinds = {"ollama": Ollama, "openai": OpenAI, "claude_cli": ClaudeCLI, "codex_cli": CodexCLI}
    if cfg.kind not in kinds:
        raise ValueError(f"unknown provider kind {cfg.kind!r}; stubs are built directly in tests")
    return kinds[cfg.kind](cfg)
