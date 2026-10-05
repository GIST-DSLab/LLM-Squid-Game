"""Serve the web app locally with the Ollama key for model seats (gpt-oss:20b) in the server environment.

    python3 web/tools/serve_local.py [--port 8600] [--host 127.0.0.1] [--env-file PATH] [--key-var OLLAMA_API_KEY3]

Reads ONLY the ``OLLAMA_API_KEY3=`` line (or ``--key-var``) of the root repo's ``.env`` (an inline ``# comment`` and
surrounding spaces or quotes are stripped; the file is never sourced), puts that one value into the child process
environment and runs ``uvicorn web.server.app:app`` from the repo root on the first free port from ``--port``.
The key value is never printed or written anywhere.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ENV = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.env"


def read_key(path: Path, var: str) -> str:
    """The value of ``var`` in a dotenv file, or '' if absent; no other line is kept."""
    if not path.is_file():
        return ""
    pat = re.compile(rf"^\s*(?:export\s+)?{re.escape(var)}\s*=(.*)$")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value[:1] in ("'", '"') and value[:1] in value[1:]:
            value = value[1:value.index(value[0], 1)]
        else:
            value = value.split("#", 1)[0].strip()
        return value
    return ""


def free_port(host: str, start: int) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                continue
            return port
    raise SystemExit(f"no free port in {start}..{start + 99}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8600, help="first port to try (default 8600)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--env-file", type=Path, default=Path(os.environ.get("WEB5_ENV_FILE") or DEFAULT_ENV))
    ap.add_argument("--key-var", default="OLLAMA_API_KEY3")
    a = ap.parse_args(argv)
    key = read_key(a.env_file, a.key_var)
    if not key:
        print(f"warning: {a.key_var} not found in {a.env_file}; model seats will be refused", file=sys.stderr)
    port = free_port(a.host, a.port)
    env = dict(os.environ)
    if key:
        env[a.key_var] = key
    shown = "localhost" if a.host in ("127.0.0.1", "0.0.0.0") else a.host
    print(f"squid5 web arena: http://{shown}:{port}/arena.html  ({a.key_var}: {'set' if key else 'MISSING'})",
          flush=True)
    cmd = [sys.executable, "-m", "uvicorn", "web.server.app:app", "--host", a.host, "--port", str(port)]
    try:
        return subprocess.call(cmd, cwd=str(REPO), env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
