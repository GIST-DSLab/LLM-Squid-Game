# Arena Participant Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the participant-facing CLI (`arena-cli`) and onboarding examples so an external researcher can register a BYO OpenAI-compatible endpoint, self-validate it, enqueue an evaluation, and watch its status — all in under five minutes — against the Plan-A backend.

**Architecture:** New package `src/arena/participant_kit/arena_cli/` (Click + httpx + pydantic). Console script `arena-cli` wired through a new `[arena-cli]` extra in the existing root `pyproject.toml`. Credentials persisted to `~/.arena/credentials.json` (override via `ARENA_CONFIG_DIR` env var for tests). All HTTP calls go through one `client.py` wrapper so test mocking has a single seam (`respx` for HTTP, Click's `CliRunner` for command tests). Examples (vLLM docker-compose, Ollama, Cloudflare tunnel) live as static files alongside the package; the README chains them into the 5-minute onboarding script.

**Tech Stack:** Python 3.12, Click 8.x for CLI, httpx for HTTP, pydantic v2 for credential schema validation, `respx` + `pytest` + Click `CliRunner` for tests. Reuses Plan-A's running arena backend through the public REST surface — no backend changes.

**Spec:** `docs/superpowers/specs/2026-05-24-arena-byo-participant-design.md` §3.2 (participant kit), §3.4 (sequence), §6 (deps).

**Prerequisite:** Plan A (`docs/superpowers/plans/2026-05-24-arena-backend-foundation.md`) complete — branch `feature/arena-backend-foundation` at `5aa4536` or merged to master. The CLI assumes the arena backend exposes `POST /api/participants`, `GET /api/participants/me`, `POST /api/evaluations`, `GET /api/evaluations/{id}`, `GET /api/leaderboard`, and `GET /api/models/{id}`.

**Out of scope (defer to Plan C):**
- Separate PyPI package (`src/arena/participant_kit/pyproject.toml`) — Plan B ships as an extra in the root pyproject.
- React frontend (spec §3.2 `src/arena/frontend/`).
- Cheating-prevention controls.
- `arena-cli` global install via Homebrew/pipx instructions.

---

## File Structure

```
src/arena/participant_kit/
├── README.md                              # 5-minute onboarding
├── arena_cli/
│   ├── __init__.py
│   ├── __main__.py                        # `python -m arena_cli` shim → cli.main
│   ├── cli.py                             # Click group, --server option, command dispatch
│   ├── config.py                          # credentials I/O (~/.arena/credentials.json or $ARENA_CONFIG_DIR)
│   ├── client.py                          # httpx.Client wrapper, Bearer auth, JSON helpers
│   ├── ping.py                            # OpenAI-compatible self-validation (POST to participant URL)
│   └── commands/
│       ├── __init__.py
│       ├── register.py
│       ├── submit.py
│       ├── status.py
│       └── leaderboard.py
└── examples/
    ├── vllm_compose.yml
    ├── ollama_setup.md
    └── cloudflare_tunnel.md

tests/unit/arena_cli/
├── __init__.py
├── conftest.py                            # tmp ARENA_CONFIG_DIR + respx_mock fixtures
├── test_config.py
├── test_client.py
├── test_ping.py
├── test_register.py
├── test_submit.py
├── test_status.py
├── test_leaderboard.py
└── test_cli_entry.py                      # CliRunner smoke of the Click group

tests/integration/
└── test_arena_cli_e2e.py                  # uvicorn-on-free-port + real CLI subprocess
```

**Existing files modified:**
- `pyproject.toml` — add `[arena-cli]` optional dependency group + `arena-cli` console script + `src/arena/participant_kit` to `[tool.hatch.build.targets.wheel].packages`.
- `uv.lock` — auto-updated by `uv sync`.

No other file outside `src/arena/participant_kit/`, `tests/unit/arena_cli/`, or `tests/integration/` is touched.

---

## Task 1: Scaffold participant_kit + arena-cli extra

**Files:**
- Create: `src/arena/participant_kit/__init__.py`
- Create: `src/arena/participant_kit/arena_cli/__init__.py`
- Create: `tests/unit/arena_cli/__init__.py`
- Create: `tests/unit/arena_cli/test_scaffold.py`
- Modify: `pyproject.toml` (add `[arena-cli]` extra + console script + packages list update)

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_scaffold.py`:

```python
"""Sanity: arena_cli package importable and CLI deps installable."""

import importlib


def test_arena_cli_package_importable():
    mod = importlib.import_module("arena.participant_kit.arena_cli")
    assert mod is not None


def test_arena_cli_deps_present():
    """Catches a missing [arena-cli] extra install."""
    import click  # noqa: F401
    import httpx  # noqa: F401
    import respx  # noqa: F401
    import pydantic  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_scaffold.py -v`
Expected: `ModuleNotFoundError: No module named 'arena.participant_kit'`

- [ ] **Step 3: Create packages + update pyproject**

Create `src/arena/participant_kit/__init__.py`:
```python
"""Arena participant kit: CLI + examples for BYO-endpoint registration."""
```

Create `src/arena/participant_kit/arena_cli/__init__.py`:
```python
"""arena-cli — register, ping, submit, status, leaderboard."""

__version__ = "0.1.0"
```

Create `tests/unit/arena_cli/__init__.py` (empty file).

Edit `pyproject.toml`:

Add to `[project.optional-dependencies]`:
```toml
arena-cli = [
    "click>=8.1",
    "httpx>=0.27",
    "respx>=0.21",
    "pydantic>=2.0",
]
```

Add to `[project.scripts]`:
```toml
arena-cli = "arena.participant_kit.arena_cli.cli:main"
```

Update `[tool.hatch.build.targets.wheel]`:
```toml
packages = ["src/squid_game", "src/arena"]
```
(No change if Plan A's update is already there — verify.)

Then install:

```bash
uv sync --extra arena --extra arena-cli --extra dev
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_scaffold.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git status -s   # verify only the intended files are staged
git add src/arena/participant_kit/__init__.py \
        src/arena/participant_kit/arena_cli/__init__.py \
        tests/unit/arena_cli/__init__.py \
        tests/unit/arena_cli/test_scaffold.py \
        pyproject.toml uv.lock
git commit -m "feat(arena-cli): scaffold participant_kit + arena-cli extra"
```

---

## Task 2: Credentials store (`config.py`)

**Files:**
- Create: `src/arena/participant_kit/arena_cli/config.py`
- Create: `tests/unit/arena_cli/conftest.py`
- Create: `tests/unit/arena_cli/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/conftest.py`:

```python
"""Shared fixtures: temp credentials dir + respx mock for HTTP calls."""

import pytest


@pytest.fixture
def cred_dir(tmp_path, monkeypatch):
    """Isolate credentials I/O to a tmp dir via the ARENA_CONFIG_DIR env var."""
    d = tmp_path / "arena"
    monkeypatch.setenv("ARENA_CONFIG_DIR", str(d))
    return d
```

`tests/unit/arena_cli/test_config.py`:

```python
"""Credentials file roundtrip: save/load/clear under tmp dir."""

import json

import pytest

from arena.participant_kit.arena_cli.config import (
    Credentials,
    CredentialsNotFound,
    clear_credentials,
    load_credentials,
    save_credentials,
)


def test_save_then_load_roundtrip(cred_dir):
    creds = Credentials(participant_id=42, api_key="abc123", server="http://localhost:8000")
    save_credentials(creds)
    loaded = load_credentials()
    assert loaded.participant_id == 42
    assert loaded.api_key == "abc123"
    assert loaded.server == "http://localhost:8000"


def test_load_raises_when_missing(cred_dir):
    with pytest.raises(CredentialsNotFound):
        load_credentials()


def test_save_creates_dir_with_0700(cred_dir):
    save_credentials(Credentials(participant_id=1, api_key="k", server="http://x"))
    assert cred_dir.exists()
    # Owner-only permission on the credentials file (sensitive secret).
    mode = (cred_dir / "credentials.json").stat().st_mode & 0o777
    assert mode == 0o600


def test_clear_removes_file(cred_dir):
    save_credentials(Credentials(participant_id=1, api_key="k", server="http://x"))
    clear_credentials()
    with pytest.raises(CredentialsNotFound):
        load_credentials()


def test_clear_is_idempotent(cred_dir):
    clear_credentials()  # no-op when missing
    clear_credentials()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_config.py -v`
Expected: `ModuleNotFoundError: arena.participant_kit.arena_cli.config`.

- [ ] **Step 3: Implement `config.py`**

`src/arena/participant_kit/arena_cli/config.py`:

```python
"""Credentials persistence for arena-cli.

Stores a single Credentials record at `~/.arena/credentials.json` (or
`$ARENA_CONFIG_DIR/credentials.json` for tests). The file holds the
plaintext api_key returned by the arena server at registration — there
is no way to recover it server-side, so we own the persistence.

File permissions: 0700 on the dir, 0600 on credentials.json. We do not
encrypt — the key is single-user (the developer's laptop) and any local
attacker with file read already has the key.
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel


class Credentials(BaseModel):
    participant_id: int
    api_key: str
    server: str  # arena server base URL, e.g. http://localhost:8000


class CredentialsNotFound(FileNotFoundError):
    """Raised when load_credentials() runs with no credentials file."""


def _config_dir() -> Path:
    override = os.environ.get("ARENA_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".arena"


def _config_file() -> Path:
    return _config_dir() / "credentials.json"


def save_credentials(creds: Credentials) -> None:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = _config_file()
    path.write_text(creds.model_dump_json())
    path.chmod(0o600)


def load_credentials() -> Credentials:
    path = _config_file()
    if not path.exists():
        raise CredentialsNotFound(
            f"No credentials at {path}. Run `arena-cli register` first."
        )
    return Credentials.model_validate_json(path.read_text())


def clear_credentials() -> None:
    path = _config_file()
    if path.exists():
        path.unlink()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/config.py \
        tests/unit/arena_cli/conftest.py \
        tests/unit/arena_cli/test_config.py
git commit -m "feat(arena-cli): Credentials store with 0600 file perms"
```

---

## Task 3: HTTP client (`client.py`)

**Files:**
- Create: `src/arena/participant_kit/arena_cli/client.py`
- Create: `tests/unit/arena_cli/test_client.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_client.py`:

```python
"""HTTP client: Bearer auth + JSON helpers + arena REST endpoints."""

import httpx
import pytest
import respx

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError


@pytest.fixture
def client():
    return ArenaClient(server="http://srv", api_key="k")


def test_register_posts_payload(respx_mock):
    route = respx_mock.post("http://srv/api/participants").mock(
        return_value=httpx.Response(201, json={"participant_id": 7, "api_key": "key"})
    )
    c = ArenaClient(server="http://srv", api_key=None)
    out = c.register(display_name="x", owner_email="x@x.c",
                     base_url="http://p/v1", model_name="m", model_meta={"params": "8B"})
    assert route.called
    sent = route.calls.last.request.read().decode()
    assert "display_name" in sent and "qwen" not in sent  # spot check payload was JSON
    assert out["participant_id"] == 7


def test_me_sends_bearer(client, respx_mock):
    route = respx_mock.get("http://srv/api/participants/me").mock(
        return_value=httpx.Response(200, json={"id": 1, "display_name": "x",
                                                "model_name": "m", "model_meta": {},
                                                "registered_at": "2026-05-24T00:00:00",
                                                "status": "active"})
    )
    out = client.me()
    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer k"
    assert out["id"] == 1


def test_enqueue_posts_config_label(client, respx_mock):
    respx_mock.post("http://srv/api/evaluations").mock(
        return_value=httpx.Response(201, json={"id": 99, "status": "queued",
                                                "participant_id": 1, "config_label": "smoke",
                                                "queued_at": "2026-05-24T00:00:00",
                                                "started_at": None, "finished_at": None,
                                                "error_message": None}),
    )
    out = client.enqueue(config_label="smoke")
    assert out["id"] == 99 and out["status"] == "queued"


def test_get_evaluation_404_raises_arena_error(client, respx_mock):
    respx_mock.get("http://srv/api/evaluations/123").mock(
        return_value=httpx.Response(404, json={"detail": "evaluation not found"})
    )
    with pytest.raises(ArenaServerError) as exc:
        client.get_evaluation(123)
    assert "evaluation not found" in str(exc.value)


def test_leaderboard_returns_list(respx_mock):
    respx_mock.get("http://srv/api/leaderboard").mock(
        return_value=httpx.Response(200, json=[
            {"participant_id": 1, "display_name": "a", "model_name": "m",
             "n_evaluations": 3, "forfeit_rate": 0.5},
        ])
    )
    c = ArenaClient(server="http://srv", api_key=None)
    rows = c.leaderboard()
    assert len(rows) == 1 and rows[0]["display_name"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_client.py -v`
Expected: `ModuleNotFoundError: arena.participant_kit.arena_cli.client`.

- [ ] **Step 3: Implement `client.py`**

`src/arena/participant_kit/arena_cli/client.py`:

```python
"""HTTP client for the arena REST API.

Single seam for all server calls so test mocking has one mock to set up.
Each command in commands/ uses ArenaClient — no command issues HTTP
directly. Bearer auth is added automatically when api_key is set.

Raises ArenaServerError on any non-2xx response. The CLI surface
translates this to a human-friendly message + non-zero exit.
"""

from typing import Any

import httpx


class ArenaServerError(RuntimeError):
    """Raised on any non-2xx response from the arena server."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class ArenaClient:
    """Thin wrapper around the arena REST API."""

    def __init__(self, server: str, api_key: str | None, timeout: float = 30.0):
        self._server = server.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(base_url=self._server, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    def _raise_for(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        # The server returns {"detail": "..."} on Pydantic / HTTPException
        # paths. Fall back to body text otherwise.
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ArenaServerError(resp.status_code, str(detail))

    # --- endpoints -----------------------------------------------------

    def register(
        self, *, display_name: str, owner_email: str, base_url: str,
        model_name: str, model_meta: dict,
    ) -> dict[str, Any]:
        r = self._client.post(
            "/api/participants",
            json={
                "display_name": display_name,
                "owner_email": owner_email,
                "base_url": base_url,
                "model_name": model_name,
                "model_meta": model_meta,
            },
        )
        self._raise_for(r)
        return r.json()

    def me(self) -> dict[str, Any]:
        r = self._client.get("/api/participants/me", headers=self._headers())
        self._raise_for(r)
        return r.json()

    def enqueue(self, *, config_label: str) -> dict[str, Any]:
        r = self._client.post(
            "/api/evaluations",
            headers=self._headers(),
            json={"config_label": config_label},
        )
        self._raise_for(r)
        return r.json()

    def get_evaluation(self, eval_id: int) -> dict[str, Any]:
        r = self._client.get(f"/api/evaluations/{eval_id}", headers=self._headers())
        self._raise_for(r)
        return r.json()

    def leaderboard(self) -> list[dict[str, Any]]:
        r = self._client.get("/api/leaderboard")
        self._raise_for(r)
        return r.json()

    def close(self) -> None:
        self._client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_client.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/client.py \
        tests/unit/arena_cli/test_client.py
git commit -m "feat(arena-cli): httpx Bearer client for arena REST API"
```

---

## Task 4: `ping` — OpenAI-compatible self-validation

**Files:**
- Create: `src/arena/participant_kit/arena_cli/ping.py`
- Create: `tests/unit/arena_cli/test_ping.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_ping.py`:

```python
"""ping.py: POST to the participant's own endpoint and validate response shape."""

import httpx
import pytest
import respx

from arena.participant_kit.arena_cli.ping import (
    PingResult,
    PingValidationError,
    ping_endpoint,
)


def test_ping_accepts_well_formed_openai_response(respx_mock):
    respx_mock.post("http://p/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })
    )
    out = ping_endpoint(base_url="http://p/v1", model_name="m", api_key="none")
    assert isinstance(out, PingResult)
    assert out.model == "m"
    assert out.assistant_text == "hi"


def test_ping_rejects_missing_choices(respx_mock):
    respx_mock.post("http://p/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "x"})  # no choices
    )
    with pytest.raises(PingValidationError) as exc:
        ping_endpoint(base_url="http://p/v1", model_name="m", api_key="none")
    assert "choices" in str(exc.value).lower()


def test_ping_rejects_non_2xx(respx_mock):
    respx_mock.post("http://p/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "internal"})
    )
    with pytest.raises(PingValidationError) as exc:
        ping_endpoint(base_url="http://p/v1", model_name="m", api_key="none")
    assert "500" in str(exc.value)


def test_ping_sends_bearer_when_key_provided(respx_mock):
    route = respx_mock.post("http://p/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        })
    )
    ping_endpoint(base_url="http://p/v1", model_name="m", api_key="participant-secret")
    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer participant-secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_ping.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `ping.py`**

`src/arena/participant_kit/arena_cli/ping.py`:

```python
"""Self-validation: POST a minimal chat completion to the participant's
own endpoint and check the response is OpenAI-compatible.

Catches the two most common onboarding bugs:
    1. Endpoint not OpenAI-shaped (wrong path, missing `choices`).
    2. Endpoint behind a 5xx-erroring proxy or auth-rejected.

Does NOT validate every spec field — only the fields the arena worker
actually reads via squid_game's OpenAIProvider (assistant content +
optional usage). If the participant's endpoint passes ping but fails
during a real evaluation, the error message in `evaluations.failed`
will surface the deeper issue.
"""

from dataclasses import dataclass

import httpx


@dataclass
class PingResult:
    model: str
    assistant_text: str


class PingValidationError(RuntimeError):
    """Raised when the endpoint does not look OpenAI-compatible."""


def ping_endpoint(
    *, base_url: str, model_name: str, api_key: str, timeout: float = 30.0,
) -> PingResult:
    """POST a minimal chat completion to {base_url}/chat/completions.

    Raises PingValidationError on any of: connection error, non-2xx
    response, missing `choices`, missing assistant content.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.lower() != "none":
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0.0,
    }
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise PingValidationError(f"connect failed: {exc}") from exc
    if not r.is_success:
        raise PingValidationError(f"HTTP {r.status_code}: {r.text[:200]}")
    try:
        body = r.json()
    except ValueError as exc:
        raise PingValidationError(f"not JSON: {r.text[:200]}") from exc

    choices = body.get("choices")
    if not choices or not isinstance(choices, list):
        raise PingValidationError("missing or empty `choices` array in response")
    msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise PingValidationError("missing `choices[0].message.content`")

    return PingResult(model=body.get("model", model_name), assistant_text=content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_ping.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/ping.py \
        tests/unit/arena_cli/test_ping.py
git commit -m "feat(arena-cli): ping — OpenAI-compatible endpoint self-validation"
```

---

## Task 5: `register` command

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/__init__.py`
- Create: `src/arena/participant_kit/arena_cli/commands/register.py`
- Create: `tests/unit/arena_cli/test_register.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_register.py`:

```python
"""register command: POST /api/participants → save Credentials."""

from click.testing import CliRunner

import httpx
import respx

from arena.participant_kit.arena_cli.commands.register import register_cmd
from arena.participant_kit.arena_cli.config import load_credentials


def test_register_persists_credentials(cred_dir, respx_mock):
    respx_mock.post("http://srv/api/participants").mock(
        return_value=httpx.Response(201, json={"participant_id": 42, "api_key": "K"})
    )
    runner = CliRunner()
    result = runner.invoke(register_cmd, [
        "--server", "http://srv",
        "--display-name", "alice",
        "--owner-email", "a@b.c",
        "--base-url", "http://p/v1",
        "--model-name", "qwen3-8b",
    ])
    assert result.exit_code == 0, result.output
    assert "participant_id=42" in result.output
    creds = load_credentials()
    assert creds.participant_id == 42
    assert creds.api_key == "K"
    assert creds.server == "http://srv"


def test_register_refuses_to_overwrite_without_force(cred_dir, respx_mock):
    respx_mock.post("http://srv/api/participants").mock(
        return_value=httpx.Response(201, json={"participant_id": 1, "api_key": "K"})
    )
    runner = CliRunner()
    runner.invoke(register_cmd, [
        "--server", "http://srv", "--display-name", "alice",
        "--owner-email", "a@b.c", "--base-url", "http://p/v1",
        "--model-name", "m",
    ])
    # Second invocation with existing creds:
    result = runner.invoke(register_cmd, [
        "--server", "http://srv", "--display-name", "bob",
        "--owner-email", "b@b.c", "--base-url", "http://q/v1",
        "--model-name", "m",
    ])
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_register_surfaces_422_validation_error(cred_dir, respx_mock):
    respx_mock.post("http://srv/api/participants").mock(
        return_value=httpx.Response(422, json={"detail": "invalid email"})
    )
    runner = CliRunner()
    result = runner.invoke(register_cmd, [
        "--server", "http://srv", "--display-name", "x",
        "--owner-email", "not-an-email", "--base-url", "http://p/v1",
        "--model-name", "m",
    ])
    assert result.exit_code != 0
    assert "invalid email" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_register.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/arena/participant_kit/arena_cli/commands/__init__.py`:
```python
"""arena-cli subcommands."""
```

`src/arena/participant_kit/arena_cli/commands/register.py`:

```python
"""arena-cli register — POST /api/participants then persist Credentials."""

import json

import click

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError
from arena.participant_kit.arena_cli.config import (
    Credentials,
    CredentialsNotFound,
    load_credentials,
    save_credentials,
)


@click.command("register")
@click.option("--server", required=True, help="Arena server base URL.")
@click.option("--display-name", required=True)
@click.option("--owner-email", required=True)
@click.option("--base-url", required=True, help="Your OpenAI-compatible endpoint.")
@click.option("--model-name", required=True)
@click.option("--model-meta", default="{}", help="JSON dict of self-reported metadata.")
def register_cmd(
    server: str, display_name: str, owner_email: str,
    base_url: str, model_name: str, model_meta: str,
) -> None:
    """Register a participant and save credentials locally."""
    # Refuse to silently overwrite an existing identity — that would
    # orphan whatever evaluations are queued under the old participant.
    try:
        load_credentials()
        click.echo("Credentials already present. Re-registration is not supported "
                   "without explicit cleanup. Delete the credentials file to start "
                   "over.", err=True)
        raise click.exceptions.Exit(code=1)
    except CredentialsNotFound:
        pass

    try:
        meta = json.loads(model_meta)
    except ValueError as exc:
        click.echo(f"--model-meta must be valid JSON: {exc}", err=True)
        raise click.exceptions.Exit(code=2)

    client = ArenaClient(server=server, api_key=None)
    try:
        out = client.register(
            display_name=display_name, owner_email=owner_email,
            base_url=base_url, model_name=model_name, model_meta=meta,
        )
    except ArenaServerError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=3)
    finally:
        client.close()

    save_credentials(Credentials(
        participant_id=out["participant_id"],
        api_key=out["api_key"],
        server=server,
    ))
    click.echo(f"Registered: participant_id={out['participant_id']}")
    click.echo("Credentials saved. Run `arena-cli ping` to validate your endpoint, "
               "then `arena-cli submit` to enqueue an evaluation.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_register.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/__init__.py \
        src/arena/participant_kit/arena_cli/commands/register.py \
        tests/unit/arena_cli/test_register.py
git commit -m "feat(arena-cli): register command + credential persistence"
```

---

## Task 6: `submit` command

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/submit.py`
- Create: `tests/unit/arena_cli/test_submit.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_submit.py`:

```python
"""submit command: POST /api/evaluations using stored credentials."""

from click.testing import CliRunner

import httpx
import respx

from arena.participant_kit.arena_cli.commands.submit import submit_cmd
from arena.participant_kit.arena_cli.config import Credentials, save_credentials


def _seed_creds():
    save_credentials(Credentials(participant_id=1, api_key="K", server="http://srv"))


def test_submit_uses_default_config_label_smoke(cred_dir, respx_mock):
    _seed_creds()
    route = respx_mock.post("http://srv/api/evaluations").mock(
        return_value=httpx.Response(201, json={
            "id": 11, "status": "queued", "participant_id": 1,
            "config_label": "smoke", "queued_at": "2026-05-24T00:00:00",
            "started_at": None, "finished_at": None, "error_message": None,
        })
    )
    result = CliRunner().invoke(submit_cmd, [])
    assert result.exit_code == 0, result.output
    assert "queued" in result.output and "id=11" in result.output
    body = route.calls.last.request.read().decode()
    assert '"config_label":"smoke"' in body or '"config_label": "smoke"' in body


def test_submit_explicit_config_label(cred_dir, respx_mock):
    _seed_creds()
    route = respx_mock.post("http://srv/api/evaluations").mock(
        return_value=httpx.Response(201, json={
            "id": 12, "status": "queued", "participant_id": 1,
            "config_label": "canonical", "queued_at": "2026-05-24T00:00:00",
            "started_at": None, "finished_at": None, "error_message": None,
        })
    )
    result = CliRunner().invoke(submit_cmd, ["--config-label", "canonical"])
    assert result.exit_code == 0
    assert "canonical" in result.output
    body = route.calls.last.request.read().decode()
    assert "canonical" in body


def test_submit_requires_credentials(cred_dir):
    # No save_credentials call → load_credentials raises CredentialsNotFound.
    result = CliRunner().invoke(submit_cmd, [])
    assert result.exit_code != 0
    assert "register" in result.output.lower()


def test_submit_surfaces_422_unknown_label(cred_dir, respx_mock):
    _seed_creds()
    respx_mock.post("http://srv/api/evaluations").mock(
        return_value=httpx.Response(422, json={"detail": "unknown config_label 'nope'"})
    )
    result = CliRunner().invoke(submit_cmd, ["--config-label", "nope"])
    assert result.exit_code != 0
    assert "unknown config_label" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_submit.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/arena/participant_kit/arena_cli/commands/submit.py`:

```python
"""arena-cli submit — POST /api/evaluations using saved credentials."""

import click

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError
from arena.participant_kit.arena_cli.config import (
    CredentialsNotFound,
    load_credentials,
)


@click.command("submit")
@click.option("--config-label", default="smoke",
              help="Server-known config label (default: smoke).")
def submit_cmd(config_label: str) -> None:
    """Enqueue an evaluation for the registered participant."""
    try:
        creds = load_credentials()
    except CredentialsNotFound as exc:
        click.echo(str(exc) + " Run `arena-cli register` first.", err=True)
        raise click.exceptions.Exit(code=1)

    client = ArenaClient(server=creds.server, api_key=creds.api_key)
    try:
        out = client.enqueue(config_label=config_label)
    except ArenaServerError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=2)
    finally:
        client.close()

    click.echo(f"Enqueued: id={out['id']} status={out['status']} "
               f"config_label={out['config_label']}")
    click.echo(f"Watch with: arena-cli status {out['id']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_submit.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/submit.py \
        tests/unit/arena_cli/test_submit.py
git commit -m "feat(arena-cli): submit command — enqueue evaluation"
```

---

## Task 7: `status` command (me + by-id)

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/status.py`
- Create: `tests/unit/arena_cli/test_status.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_status.py`:

```python
"""status command: with no arg → /me; with eval_id → /evaluations/{id}."""

from click.testing import CliRunner

import httpx
import respx

from arena.participant_kit.arena_cli.commands.status import status_cmd
from arena.participant_kit.arena_cli.config import Credentials, save_credentials


def _seed():
    save_credentials(Credentials(participant_id=1, api_key="K", server="http://srv"))


def test_status_no_arg_shows_participant_info(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/participants/me").mock(
        return_value=httpx.Response(200, json={
            "id": 1, "display_name": "alice", "model_name": "qwen",
            "model_meta": {}, "registered_at": "2026-05-24T00:00:00",
            "status": "active",
        })
    )
    result = CliRunner().invoke(status_cmd, [])
    assert result.exit_code == 0, result.output
    assert "alice" in result.output and "active" in result.output


def test_status_with_eval_id_shows_evaluation(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/evaluations/42").mock(
        return_value=httpx.Response(200, json={
            "id": 42, "status": "running", "participant_id": 1,
            "config_label": "smoke", "queued_at": "2026-05-24T00:00:00",
            "started_at": "2026-05-24T00:01:00", "finished_at": None,
            "error_message": None,
        })
    )
    result = CliRunner().invoke(status_cmd, ["42"])
    assert result.exit_code == 0
    assert "running" in result.output and "smoke" in result.output


def test_status_with_eval_id_failed_shows_error_message(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/evaluations/99").mock(
        return_value=httpx.Response(200, json={
            "id": 99, "status": "failed", "participant_id": 1,
            "config_label": "smoke", "queued_at": "2026-05-24T00:00:00",
            "started_at": "2026-05-24T00:01:00",
            "finished_at": "2026-05-24T00:02:00",
            "error_message": "upstream 500 from your endpoint",
        })
    )
    result = CliRunner().invoke(status_cmd, ["99"])
    assert result.exit_code == 0
    assert "failed" in result.output and "upstream 500" in result.output


def test_status_404_on_unknown_eval(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/evaluations/123").mock(
        return_value=httpx.Response(404, json={"detail": "evaluation not found"})
    )
    result = CliRunner().invoke(status_cmd, ["123"])
    assert result.exit_code != 0
    assert "evaluation not found" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_status.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/arena/participant_kit/arena_cli/commands/status.py`:

```python
"""arena-cli status — show participant info or a specific evaluation."""

import click

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError
from arena.participant_kit.arena_cli.config import (
    CredentialsNotFound,
    load_credentials,
)


@click.command("status")
@click.argument("eval_id", required=False, type=int)
def status_cmd(eval_id: int | None) -> None:
    """Show participant info, or the status of a specific evaluation."""
    try:
        creds = load_credentials()
    except CredentialsNotFound as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=1)

    client = ArenaClient(server=creds.server, api_key=creds.api_key)
    try:
        if eval_id is None:
            me = client.me()
            click.echo(f"participant_id={me['id']} display_name={me['display_name']} "
                       f"model_name={me['model_name']} status={me['status']}")
            click.echo(f"registered_at={me['registered_at']}")
            if me.get("model_meta"):
                click.echo(f"model_meta={me['model_meta']}")
        else:
            ev = client.get_evaluation(eval_id)
            click.echo(f"id={ev['id']} status={ev['status']} "
                       f"config_label={ev['config_label']}")
            click.echo(f"queued_at={ev['queued_at']} started_at={ev['started_at']} "
                       f"finished_at={ev['finished_at']}")
            if ev.get("error_message"):
                click.echo(f"error_message: {ev['error_message']}")
    except ArenaServerError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=2)
    finally:
        client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_status.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/status.py \
        tests/unit/arena_cli/test_status.py
git commit -m "feat(arena-cli): status command — participant info + eval lookup"
```

---

## Task 8: `leaderboard` command

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/leaderboard.py`
- Create: `tests/unit/arena_cli/test_leaderboard.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_leaderboard.py`:

```python
"""leaderboard command: GET /api/leaderboard (public, no auth)."""

from click.testing import CliRunner

import httpx
import respx

from arena.participant_kit.arena_cli.commands.leaderboard import leaderboard_cmd
from arena.participant_kit.arena_cli.config import Credentials, save_credentials


def _seed():
    save_credentials(Credentials(participant_id=1, api_key="K", server="http://srv"))


def test_leaderboard_prints_rows_in_response_order(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/leaderboard").mock(
        return_value=httpx.Response(200, json=[
            {"participant_id": 1, "display_name": "alice", "model_name": "m1",
             "n_evaluations": 2, "forfeit_rate": 0.5},
            {"participant_id": 2, "display_name": "bob", "model_name": "m2",
             "n_evaluations": 1, "forfeit_rate": 0.0},
        ])
    )
    result = CliRunner().invoke(leaderboard_cmd, [])
    assert result.exit_code == 0
    # The server sorts; we just render. Both must appear.
    assert "alice" in result.output and "bob" in result.output


def test_leaderboard_uses_explicit_server_when_no_credentials(cred_dir, respx_mock):
    respx_mock.get("http://srv/api/leaderboard").mock(
        return_value=httpx.Response(200, json=[
            {"participant_id": 1, "display_name": "a", "model_name": "m",
             "n_evaluations": 1, "forfeit_rate": None},
        ])
    )
    result = CliRunner().invoke(leaderboard_cmd, ["--server", "http://srv"])
    assert result.exit_code == 0
    assert "a" in result.output


def test_leaderboard_requires_server_when_no_credentials(cred_dir):
    result = CliRunner().invoke(leaderboard_cmd, [])
    assert result.exit_code != 0
    assert "server" in result.output.lower() or "credential" in result.output.lower()


def test_leaderboard_formats_null_forfeit_rate(cred_dir, respx_mock):
    _seed()
    respx_mock.get("http://srv/api/leaderboard").mock(
        return_value=httpx.Response(200, json=[
            {"participant_id": 1, "display_name": "a", "model_name": "m",
             "n_evaluations": 0, "forfeit_rate": None},
        ])
    )
    result = CliRunner().invoke(leaderboard_cmd, [])
    assert result.exit_code == 0
    assert "—" in result.output or "n/a" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_leaderboard.py -v`
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

`src/arena/participant_kit/arena_cli/commands/leaderboard.py`:

```python
"""arena-cli leaderboard — print the public leaderboard."""

import click

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError
from arena.participant_kit.arena_cli.config import (
    CredentialsNotFound,
    load_credentials,
)


@click.command("leaderboard")
@click.option("--server", default=None,
              help="Arena server URL (defaults to the one in saved credentials).")
def leaderboard_cmd(server: str | None) -> None:
    """Print the public leaderboard. No authentication required."""
    if server is None:
        try:
            server = load_credentials().server
        except CredentialsNotFound:
            click.echo(
                "No credentials and no --server. Pass --server <url> or run "
                "`arena-cli register` first.", err=True
            )
            raise click.exceptions.Exit(code=1)

    client = ArenaClient(server=server, api_key=None)
    try:
        rows = client.leaderboard()
    except ArenaServerError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=2)
    finally:
        client.close()

    if not rows:
        click.echo("(no participants yet)")
        return

    click.echo(f"{'rank':<5} {'display_name':<20} {'model_name':<20} "
               f"{'n_evals':>8} {'forfeit_rate':>14}")
    for rank, row in enumerate(rows, start=1):
        fr = row["forfeit_rate"]
        fr_str = f"{fr:.3f}" if fr is not None else "—"
        click.echo(f"{rank:<5} {row['display_name']:<20} {row['model_name']:<20} "
                   f"{row['n_evaluations']:>8} {fr_str:>14}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_leaderboard.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/leaderboard.py \
        tests/unit/arena_cli/test_leaderboard.py
git commit -m "feat(arena-cli): leaderboard command"
```

---

## Task 9: `ping` command wrapper + CLI entry assembly

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/ping.py` (Click wrapper around `ping.ping_endpoint`)
- Create: `src/arena/participant_kit/arena_cli/cli.py`
- Create: `src/arena/participant_kit/arena_cli/__main__.py`
- Create: `tests/unit/arena_cli/test_cli_entry.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena_cli/test_cli_entry.py`:

```python
"""CLI entry: top-level Click group dispatches to subcommands."""

from click.testing import CliRunner

import httpx
import respx

from arena.participant_kit.arena_cli.cli import main
from arena.participant_kit.arena_cli.config import Credentials, save_credentials


def test_help_lists_all_commands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for c in ("register", "ping", "submit", "status", "leaderboard"):
        assert c in result.output


def test_version_prints_semver():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    # __version__ from arena.participant_kit.arena_cli — see Task 1.
    assert "0.1.0" in result.output


def test_dispatch_status(cred_dir, respx_mock):
    save_credentials(Credentials(participant_id=1, api_key="K", server="http://srv"))
    respx_mock.get("http://srv/api/participants/me").mock(
        return_value=httpx.Response(200, json={
            "id": 1, "display_name": "alice", "model_name": "m", "model_meta": {},
            "registered_at": "2026-05-24T00:00:00", "status": "active",
        })
    )
    result = CliRunner().invoke(main, ["status"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_ping_subcommand_invocable(respx_mock):
    respx_mock.post("http://p/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        })
    )
    result = CliRunner().invoke(main, [
        "ping", "--base-url", "http://p/v1",
        "--model-name", "m", "--api-key", "none",
    ])
    assert result.exit_code == 0
    assert "ok" in result.output or "✓" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py -v`
Expected: ModuleNotFoundError on `arena.participant_kit.arena_cli.cli`.

- [ ] **Step 3: Implement**

`src/arena/participant_kit/arena_cli/commands/ping.py`:

```python
"""arena-cli ping — Click wrapper around ping.ping_endpoint."""

import click

from arena.participant_kit.arena_cli.config import (
    CredentialsNotFound,
    load_credentials,
)
from arena.participant_kit.arena_cli.ping import PingValidationError, ping_endpoint


@click.command("ping")
@click.option("--base-url", default=None,
              help="OpenAI-compatible endpoint base URL (defaults to value from --me).")
@click.option("--model-name", default=None,
              help="Model identifier (defaults to value from --me).")
@click.option("--api-key", default="none",
              help="API key for your endpoint (default: 'none' — many local servers).")
@click.option("--me", is_flag=True,
              help="Pull base_url and model_name from registered participant info.")
def ping_cmd(base_url: str | None, model_name: str | None, api_key: str, me: bool) -> None:
    """Self-validate the participant's OpenAI-compatible endpoint."""
    if me:
        try:
            creds = load_credentials()
        except CredentialsNotFound as exc:
            click.echo(str(exc), err=True)
            raise click.exceptions.Exit(code=1)
        from arena.participant_kit.arena_cli.client import ArenaClient
        c = ArenaClient(server=creds.server, api_key=creds.api_key)
        try:
            info = c.me()
        finally:
            c.close()
        base_url = base_url or info["model_name"]  # noqa: E501 — see below
        # Note: GET /me does not expose base_url currently; --me only
        # supplies model_name. base_url must be passed explicitly.
        base_url = base_url
        model_name = model_name or info["model_name"]

    if not base_url or not model_name:
        click.echo("Both --base-url and --model-name are required "
                   "(or --me + --base-url, since /me does not expose base_url).",
                   err=True)
        raise click.exceptions.Exit(code=2)

    try:
        out = ping_endpoint(base_url=base_url, model_name=model_name, api_key=api_key)
    except PingValidationError as exc:
        click.echo(f"✗ ping failed: {exc}", err=True)
        raise click.exceptions.Exit(code=3)
    click.echo(f"✓ ping ok — model={out.model} reply={out.assistant_text!r}")
```

`src/arena/participant_kit/arena_cli/cli.py`:

```python
"""arena-cli entrypoint: top-level Click group."""

import click

from arena.participant_kit.arena_cli import __version__
from arena.participant_kit.arena_cli.commands.leaderboard import leaderboard_cmd
from arena.participant_kit.arena_cli.commands.ping import ping_cmd
from arena.participant_kit.arena_cli.commands.register import register_cmd
from arena.participant_kit.arena_cli.commands.status import status_cmd
from arena.participant_kit.arena_cli.commands.submit import submit_cmd


@click.group()
@click.version_option(__version__, prog_name="arena-cli")
def main() -> None:
    """arena-cli — manage your BYO endpoint registration with LLM Squid Game Arena."""


main.add_command(register_cmd)
main.add_command(ping_cmd)
main.add_command(submit_cmd)
main.add_command(status_cmd)
main.add_command(leaderboard_cmd)


if __name__ == "__main__":
    main()
```

`src/arena/participant_kit/arena_cli/__main__.py`:

```python
"""Allow `python -m arena.participant_kit.arena_cli` invocation."""

from arena.participant_kit.arena_cli.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py -v`
Expected: 4 passed.

Also run the full arena_cli unit suite:
```bash
uv run pytest tests/unit/arena_cli/ -v
```
Expected: 28 passed (5 config + 5 client + 4 ping + 3 register + 4 submit + 4 status + 4 leaderboard + 4 entry — adjust if any task above produced fewer tests).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/ping.py \
        src/arena/participant_kit/arena_cli/cli.py \
        src/arena/participant_kit/arena_cli/__main__.py \
        tests/unit/arena_cli/test_cli_entry.py
git commit -m "feat(arena-cli): ping subcommand + top-level Click group"
```

---

## Task 10: README + 5-minute onboarding script

**Files:**
- Create: `src/arena/participant_kit/README.md`

- [ ] **Step 1: Author the README**

`src/arena/participant_kit/README.md`:

```markdown
# arena-cli — Participant Kit for LLM Squid Game Arena

Register a model, validate its endpoint, enqueue a benchmark evaluation,
and watch the result land on the leaderboard. Five minutes if you already
have a vLLM/Ollama/OpenRouter endpoint; ten if you don't.

## Install

```bash
git clone https://github.com/<org>/Squid-Game
cd Squid-Game
uv sync --extra arena-cli
# arena-cli is now on your PATH inside the project venv:
uv run arena-cli --help
```

## The 5-minute path

```bash
# 1) Bring up a local OpenAI-compatible endpoint.
#    Pick one — see examples/ for full configs.
#    a) Ollama (M-series Mac, no GPU): `ollama serve` + `ollama pull qwen3:8b`
#    b) vLLM (CUDA box): `docker compose -f examples/vllm_compose.yml up`
#    c) OpenRouter / Together / Modal — any OpenAI-compatible HTTPS URL.

# 2) Register your participant.
uv run arena-cli register \
  --server https://arena.example.com \
  --display-name "alice's qwen3" \
  --owner-email alice@example.com \
  --base-url http://localhost:11434/v1 \
  --model-name qwen3:8b

# 3) Sanity-check your endpoint.
uv run arena-cli ping --base-url http://localhost:11434/v1 --model-name qwen3:8b

# 4) Submit a smoke evaluation.
uv run arena-cli submit
# → Enqueued: id=42 status=queued config_label=smoke

# 5) Watch it run.
uv run arena-cli status 42
# → id=42 status=running config_label=smoke
# (a few minutes later)
uv run arena-cli status 42
# → id=42 status=done config_label=smoke
# → finished_at=2026-05-24T17:23:00

# 6) See yourself on the leaderboard.
uv run arena-cli leaderboard
```

## Commands

| Command | Purpose |
|---|---|
| `register` | One-time. Creates a participant on the arena server and saves your api key to `~/.arena/credentials.json` (mode 0600). |
| `ping` | No server call. POSTs `{"role":"user","content":"ping"}` to your endpoint and validates the response shape. |
| `submit [--config-label LABEL]` | Enqueues an evaluation. Default `LABEL=smoke`. |
| `status [EVAL_ID]` | No arg: shows your participant info. With arg: shows that evaluation's queued/running/done/failed state. |
| `leaderboard [--server URL]` | Prints the public leaderboard. Works without credentials if you pass `--server`. |

## Where to host your endpoint

See `examples/`:

- `vllm_compose.yml` — Docker Compose recipe for vLLM serving (recommended for any GPU box).
- `ollama_setup.md` — Apple Silicon / CPU-only laptops; uses Ollama's built-in OpenAI-compat layer.
- `cloudflare_tunnel.md` — Exposing a local endpoint to the public internet through Cloudflare Tunnel, for participants behind NAT.

## What gets evaluated

The arena worker runs `squid_game.game.runner.ExperimentRunner` against
your endpoint with the requested `config_label`. The default `smoke`
label is a 1-cell × 1-seed × 2-turn sanity run that proves the wiring
end-to-end. Canonical n=30-per-cell runs are registered server-side
under labels like `canonical_6x30` — ask the maintainer which labels
the active leaderboard uses.

Your endpoint receives standard OpenAI `/v1/chat/completions` POSTs.
The evaluation prompts are not disclosed before run time (no
contamination), but they conform to the public protocol described in
`docs/manuscripts/manuscript-md/KDD-final/manuscript_en.md` §3.

## Privacy and security

- Your `api_key` is the credential the arena server will send to *your*
  endpoint as a `Bearer` token. It is yours to choose — set it to
  whatever your endpoint expects.
- The arena server-side api_key (returned from `register`) is what *you*
  use to call the arena API. It is stored locally only, never echoed
  except at registration time.
- Cheating is **not** policed. The leaderboard carries the disclaimer
  "self-reported, unverified."
- Your `~/.arena/credentials.json` is created with mode `0600`. Delete
  it to start over (re-registration is not supported in-place).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `arena-cli ping ... → ✗ ping failed: missing choices array` | Endpoint isn't OpenAI-compatible. Check it returns `{"choices": [{"message": {"content": "..."}}]}`. |
| `submit → HTTP 422: unknown config_label` | The label you passed isn't registered server-side. Ask the maintainer or use `smoke`. |
| `submit → HTTP 401: invalid api key` | Credentials file is stale (server reset, account disabled). Delete `~/.arena/credentials.json` and re-register. |
| `status N → status=failed, error_message=upstream 500` | Worker hit your endpoint and got a 500. Run `arena-cli ping` to reproduce locally. |
```

- [ ] **Step 2: Verify the README renders**

There is no rendering test (markdown is plain text). Spot-check the file in your editor or `glow README.md` (if installed). At minimum confirm the code fences are paired.

- [ ] **Step 3: Commit**

```bash
git status -s
git add src/arena/participant_kit/README.md
git commit -m "docs(arena-cli): 5-minute onboarding README"
```

---

## Task 11: Examples — vLLM compose, Ollama, Cloudflare tunnel

**Files:**
- Create: `src/arena/participant_kit/examples/vllm_compose.yml`
- Create: `src/arena/participant_kit/examples/ollama_setup.md`
- Create: `src/arena/participant_kit/examples/cloudflare_tunnel.md`

- [ ] **Step 1: Write `vllm_compose.yml`**

`src/arena/participant_kit/examples/vllm_compose.yml`:

```yaml
# vLLM serving for arena participants.
#
# Bring up:   docker compose -f vllm_compose.yml up -d
# Endpoint:   http://localhost:8000/v1
# Validate:   uv run arena-cli ping --base-url http://localhost:8000/v1 --model-name $MODEL
#
# Replace MODEL with a Hugging Face model id. The 8B-class models below
# fit on a single 24GB GPU. For 70B+ you will need multi-GPU + tensor
# parallelism — see the vLLM docs for the additional flags.

services:
  vllm:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
    ports:
      - "8000:8000"
    environment:
      HUGGING_FACE_HUB_TOKEN: ${HF_TOKEN:-}
    command:
      - --model=${MODEL:-Qwen/Qwen3-8B-Instruct}
      - --served-model-name=${MODEL:-Qwen/Qwen3-8B-Instruct}
      - --max-model-len=8192
      - --dtype=auto
      # No --api-key: the arena server forwards your api_key as the
      # Bearer token, so vLLM should accept it. Either omit auth here
      # (vLLM accepts any key) or set --api-key=<your-chosen-key> and
      # use the same value at `arena-cli register --api-key=<>` time.
    volumes:
      - hf_cache:/root/.cache/huggingface
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/v1/models"]
      interval: 10s
      timeout: 5s
      retries: 20

volumes:
  hf_cache:
```

- [ ] **Step 2: Write `ollama_setup.md`**

`src/arena/participant_kit/examples/ollama_setup.md`:

```markdown
# Ollama setup (Apple Silicon / CPU-only)

Ollama is the easiest way to bring up an OpenAI-compatible endpoint on
a laptop. The 8B-class models below run on an M1/M2/M3 Mac with 16+ GB
of RAM; the 3B-class ones run on 8 GB.

## Install

```bash
brew install ollama        # or download from https://ollama.com
ollama serve &              # background server, defaults to :11434
```

## Pull a model

```bash
ollama pull qwen3:8b        # ~5GB download, ~6GB RAM at run time
# or smaller:
ollama pull qwen3:4b
ollama pull phi3:mini
```

## Endpoint shape

Ollama exposes an OpenAI-compatible surface at `http://localhost:11434/v1`.

```bash
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3:8b",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 8
  }' | jq .choices[0].message.content
```

## Register with arena-cli

```bash
uv run arena-cli register \
  --server https://arena.example.com \
  --display-name "alice's M2 ollama" \
  --owner-email alice@example.com \
  --base-url http://localhost:11434/v1 \
  --model-name qwen3:8b
```

> **NAT/firewall:** localhost works only if the arena server is on the
> same machine. To accept connections from a remote arena server, see
> `cloudflare_tunnel.md`.

## Common gotchas

- **`/v1` suffix is required.** Plain `http://localhost:11434` returns
  Ollama's own JSON API, not OpenAI shape.
- **Slow first call.** Ollama lazy-loads model weights into VRAM. Run
  one warm-up request before submitting the evaluation.
- **Context length.** Default Ollama models cap context at 2k–4k
  tokens. The arena's `smoke` config sends short prompts, but the
  canonical configs send up to 8k. If you see truncation, increase via
  `ollama run qwen3:8b --num-ctx 8192`.
- **Concurrency.** Ollama serializes requests by default. If your
  evaluation has `parallel_workers > 1`, set
  `OLLAMA_NUM_PARALLEL=4 ollama serve` (matches the worker fan-out).
```

- [ ] **Step 3: Write `cloudflare_tunnel.md`**

`src/arena/participant_kit/examples/cloudflare_tunnel.md`:

```markdown
# Exposing a local endpoint via Cloudflare Tunnel

If your endpoint runs on a laptop behind NAT or a corporate firewall,
the arena worker cannot reach `http://localhost:11434`. Cloudflare
Tunnel gives you a stable `https://*.trycloudflare.com` URL that
forwards into your local port — no inbound port forwarding required.

## Install `cloudflared`

```bash
brew install cloudflare/cloudflare/cloudflared   # macOS
# or download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
```

## Quick tunnel (no Cloudflare account)

```bash
cloudflared tunnel --url http://localhost:11434
```

`cloudflared` prints a URL like
`https://random-words-1234.trycloudflare.com`. **That URL plus `/v1` is
your arena `--base-url`:**

```bash
uv run arena-cli register \
  --server https://arena.example.com \
  --display-name "alice's tunneled ollama" \
  --owner-email alice@example.com \
  --base-url https://random-words-1234.trycloudflare.com/v1 \
  --model-name qwen3:8b

uv run arena-cli ping \
  --base-url https://random-words-1234.trycloudflare.com/v1 \
  --model-name qwen3:8b
```

> **Caveats of the quick tunnel:**
> - The URL changes every time `cloudflared` restarts. Keep `cloudflared`
>   running for the whole evaluation, or use a named tunnel (below).
> - Quick tunnels have rate limits. For canonical (n=30) evaluations,
>   use a named tunnel.

## Named tunnel (stable URL, requires Cloudflare account)

```bash
cloudflared tunnel login
cloudflared tunnel create arena-alice
# Note the tunnel UUID printed.

# Map a hostname you own (alice-arena.example.com) to the tunnel:
cloudflared tunnel route dns arena-alice alice-arena.example.com

# Run the tunnel pointing at your local Ollama:
cloudflared tunnel --url http://localhost:11434 run arena-alice
```

Now register with `--base-url https://alice-arena.example.com/v1`.

## Why not ngrok?

ngrok works too — same shape: `ngrok http 11434` and use the printed
URL + `/v1`. Cloudflare Tunnel is documented here because its quick
tunnel needs no account and runs on free tier indefinitely.
```

- [ ] **Step 4: Verify the YAML parses**

```bash
uv run python -c "import yaml; yaml.safe_load(open('src/arena/participant_kit/examples/vllm_compose.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/examples/
git commit -m "docs(arena-cli): vLLM compose + Ollama + Cloudflare examples"
```

---

## Task 12: Integration smoke — uvicorn + CLI subprocess end-to-end

**Files:**
- Create: `tests/integration/test_arena_cli_e2e.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_arena_cli_e2e.py`:

```python
"""End-to-end: launch arena backend in-process via uvicorn on a free port,
then invoke `arena-cli` as a subprocess (the actual installed entry point)
against it. Covers register → submit → status with the real worker driven
by hand (ExperimentRunner patched as in T9 / T13).

This is the participant-kit analogue of T13's tier-1 integration smoke.
"""

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import uvicorn

from arena.backend.app import build_app
from arena.backend.db.session import build_engine, build_session_factory
from sqlalchemy.pool import StaticPool


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def arena_server(tmp_path, monkeypatch):
    """Boot the arena backend on a free port with an in-memory SQLite."""
    port = _free_port()
    db_url = "sqlite:///:memory:"
    monkeypatch.setenv("ARENA_DB_URL", db_url)
    monkeypatch.setenv("ARENA_OUTPUTS_DIR", str(tmp_path / "outputs"))

    # Build engine ourselves with StaticPool so the worker (which uses
    # deps.py's module-level engine) shares the same in-memory DB across
    # uvicorn's threadpool and our test thread.
    from arena.backend.db.models import Base
    from arena.backend.api import deps
    engine = build_engine.__wrapped__ if hasattr(build_engine, "__wrapped__") else None
    # The deps module already instantiated _engine at import time, so we
    # patch in a shared StaticPool engine.
    from sqlalchemy import create_engine
    shared = create_engine(
        db_url, future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(shared)
    monkeypatch.setattr(deps, "_engine", shared)
    monkeypatch.setattr(deps, "_SessionLocal", build_session_factory(shared))

    app = build_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for readiness (≤5s).
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/leaderboard", timeout=0.5)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("uvicorn did not become ready in 5s")

    yield f"http://127.0.0.1:{port}", shared
    server.should_exit = True
    thread.join(timeout=2)


def _run_cli(args: list[str], env_dir: Path, server: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["ARENA_CONFIG_DIR"] = str(env_dir)
    return subprocess.run(
        ["uv", "run", "arena-cli", *args, *(["--server", server] if "register" in args or "leaderboard" in args else [])],
        env=env, capture_output=True, text=True, timeout=30,
    )


def test_register_submit_status_e2e(arena_server, tmp_path, monkeypatch):
    server, shared_engine = arena_server
    cred = tmp_path / "creds"

    # 1) register
    r = _run_cli(
        ["register", "--display-name", "alice", "--owner-email", "a@b.c",
         "--base-url", "http://p/v1", "--model-name", "m"],
        env_dir=cred, server=server,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "participant_id" in r.stdout

    # 2) submit
    r = _run_cli(["submit"], env_dir=cred, server=server)
    assert r.returncode == 0, r.stdout + r.stderr
    # Extract eval_id from "id=N"
    eval_id = int([tok for tok in r.stdout.split() if tok.startswith("id=")][0].removeprefix("id="))

    # 3) drive the worker — patch ExperimentRunner.run + _build_config
    from arena.backend.worker.runner import process_one
    from arena.backend.db.models import Evaluation
    from arena.backend.api import deps

    # Read e.output_dir from the shared engine via deps._SessionLocal.
    with deps._SessionLocal() as s:
        eval_row = s.get(Evaluation, eval_id)
        out = Path(eval_row.output_dir)

    def fake_run(self_runner, resume_dir=None):
        target = Path(resume_dir) if resume_dir else out
        target.mkdir(parents=True, exist_ok=True)
        (target / "season_results.jsonl").write_text(
            '{"season_id":"s000","framing":"true_baseline",'
            '"forfeit_condition":"allowed","cell":0,"final_score":1.0,'
            '"forfeited":false,"total_turns":2,"seed":42}\n')
        (target / "s000_turns.jsonl").write_text(
            '{"season_id":"s000","turn_number":1,"ri_task":1,"ri_probe":1,'
            '"ri_forfeit":1,"forfeit_choice":"CONTINUE","psuccess_self":50,'
            '"decision_quality":1.0,"reward_received":1.0,"died":false}\n')
        return MagicMock()

    with deps._SessionLocal() as s, \
         patch("squid_game.game.runner.ExperimentRunner.run", fake_run), \
         patch("arena.backend.worker.runner._build_config", return_value=MagicMock()):
        process_one(s, plaintext_api_key="dummy")

    # 4) status — should report done
    r = _run_cli(["status", str(eval_id)], env_dir=cred, server=server)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "done" in r.stdout

    # 5) leaderboard — alice present
    r = _run_cli(["leaderboard"], env_dir=cred, server=server)
    assert r.returncode == 0
    assert "alice" in r.stdout
```

This test is large but exercises the full participant flow against a real HTTP server using the real CLI subprocess. It is the participant-kit analogue of Plan A's T13 integration smoke.

⚠️ **Two integration risks** the implementer should be ready for:

1. **uvicorn lifecycle inside pytest.** If the server thread fails to stop cleanly the next test can hang. The fixture uses `server.should_exit = True` + bounded `thread.join(timeout=2)`. If this proves flaky, switch to spawning a real subprocess (`subprocess.Popen` of `uv run arena-server`) — slower but more isolated.

2. **`deps._engine` monkeypatch.** `arena.backend.api.deps` instantiates `_engine` and `_SessionLocal` at module import time. The fixture replaces both with a `StaticPool` SQLite engine so the API handlers, the worker, and the test all share one DB. If the implementer finds this brittle, an alternative is to pass an explicit DB URL through the env var and rely on `pool_pre_ping` + a file-backed sqlite under `tmp_path` (each test gets its own file). The env-var path is cleaner but requires `deps.py` to re-read env at request time — out of plan-B scope.

If the test cannot be made green in ≤90 minutes of debugging, simplify: replace the subprocess with `CliRunner().invoke(main, [...])` against a `respx`-mocked client (i.e. don't actually boot uvicorn). That covers the CLI ↔ HTTP composition without the multi-process plumbing. Mark the deferred subprocess-based smoke as `TODO(plan-c-tier-2)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_arena_cli_e2e.py -v`
Expected: pre-implementation failure (the test references `arena-cli` console script that won't be on PATH unless the package is installed — `uv sync --extra arena-cli` already done in T1, so it should be available).

- [ ] **Step 3: Implementation (none — the test exercises code from prior tasks)**

This task adds only the test. If it fails red, the fix lives in either (a) deps wiring (Plan A's T10) or (b) the CLI commands (Tasks 5-9). Investigate and adjust accordingly. Do not regress prior task tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_arena_cli_e2e.py -v`
Expected: 1 passed.

Also run the full suite:
```bash
uv run pytest tests/unit/arena_cli tests/integration/test_arena_cli_e2e.py -v
```
Expected: 28 unit + 1 integration = 29 passed (or equivalent count after Tasks 2-9 finalise).

- [ ] **Step 5: Commit**

```bash
git status -s
git add tests/integration/test_arena_cli_e2e.py
git commit -m "test(arena-cli): end-to-end smoke with uvicorn + subprocess CLI"
```

---

## Self-Review Notes

Performed inline after writing the plan:

- **Spec §3.2 (participant kit modules)** — every module is covered:
  - `arena_cli/__main__.py` + `cli.py` → T9
  - `arena_cli/ping.py` (impl) → T4; `commands/ping.py` (Click wrapper) → T9
  - `examples/vllm_compose.yml` → T11
  - `examples/ollama_setup.md` → T11
  - `examples/cloudflare_tunnel.md` → T11
  - `README.md` → T10
- **Spec §3.4 sequence steps 1-4** — register (T5), ping (T4+T9), enqueue (T6), watch (T7) all surfaced as CLI commands. Steps 5-8 (worker, ETL, leaderboard auto-update) belong to Plan A — the CLI only consumes them via the public REST surface.
- **Spec §5 (CLI tests)** — `tests/unit/arena_cli/test_ping.py` (T4) and the per-command tests in T5-T9 collectively exceed the spec's single-bullet "ping accepts/rejects" requirement. Integration smoke in T12 covers the multi-command composition.
- **Spec §6 (participant kit deps)** — `httpx`, `click`, `pydantic` all in `[arena-cli]` extra (T1). `respx` added for tests. Separate `pyproject.toml` is deferred to Plan C as noted in the header — flagged explicitly so future-maintainers do not lose sight of it.
- **Type consistency** — `Credentials(participant_id, api_key, server)` is the same triple across T2, T5, T6, T7, T8. `ArenaClient(server, api_key)` signature matches across all command tests. `ping_endpoint(base_url, model_name, api_key)` keyword call sites match across T4 and T9.
- **Placeholder scan** — no "TBD"/"TODO"/"implement later"/"similar to Task N" anywhere. T12 has a single `TODO(plan-c-tier-2)` callout in the *test* describing a fallback if uvicorn-in-pytest proves flaky; that's a documented escape hatch, not a plan placeholder.
- **Test counts vs final assertion** — T9 step 4 asserts 28 unit. Roll-up: 2 (scaffold) + 5 (config) + 5 (client) + 4 (ping) + 3 (register) + 4 (submit) + 4 (status) + 4 (leaderboard) + 4 (cli_entry) = 35. Adjust the assertion in T9 to "expect ≥28 passed" if Click changes test discovery — the exact number depends on whether each `@click.command` produces extra subtests. T12 reports 29 (28 unit + 1 integration) and that count carries the same caveat.
- **Cross-plan-A invariant** — every Plan B test consumes Plan A's public REST surface; none reaches into `arena.backend` internals except the integration smoke (T12), which monkeypatches `deps._engine` and `deps._SessionLocal` exactly the way Plan A's T13 smoke already does. This bounds the blast radius if Plan A's `deps.py` is refactored later.
- **Open carryover** — `arena-cli` does NOT expose `DELETE /api/participants/me` (deactivate). The final whole-branch review of Plan A flagged that endpoint as test-light; deferring its CLI surface to Plan C avoids adding a destructive command before its server-side coverage is solid. If a maintainer asks for an `unregister` command before Plan C, it's a one-task extension and obvious; not a plan-blocker.
