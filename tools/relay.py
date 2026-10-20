"""Local pass-through relay to api.anthropic.com for claude_cli seats (config base_url http://127.0.0.1:<port>).

claude -p sometimes puts a <total_tokens>N tokens left</total_tokens> line (the CLI's own budget, not the session's) into
its # Environment block: Claude Code 2.1.284 on its first call, 2.1.303 on the first call after an install (10-19,
captured against a local server); 09-29 it was there whenever the base URL was first-party. The relay removes that
line from every /v1/messages body before it goes on, and logs how many it removed, so the model sees only the tokens
the session gives it. Everything else (subscription login, headers, streaming) passes through unchanged.

    python tools/relay.py 18781            # RELAY_UPSTREAM=http://127.0.0.1:18799 to point it at a capture server
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

UP = os.environ.get("RELAY_UPSTREAM", "https://api.anthropic.com")
HOP = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}
NOTE = re.compile(r"\n*<total_tokens>[^<]*</total_tokens>\n*")
# 10-20 (GPT-6 Astra's awareness review, proposal 5): context the CLI adds that has nothing to do with the session - the
# account-email <system-reminder> and the coding-agent lines of its "# Environment" block (working directory, git, the
# note on downloaded files). The model name, date and platform lines stay.
REMINDER = re.compile(r"<system-reminder>\s*As you answer the user's questions, you can use the following context:\s*# userEmail.*?</system-reminder>\s*", re.S)
ENV_LINES = re.compile(r"(?m)^ - (?:Primary working directory|Is a git repository|Downloaded files and extracted archives)[^\n]*\n?")


def scrub(body: bytes) -> tuple[bytes, int]:
    """The request body without any <total_tokens> line, the account-email reminder or the coding-agent environment lines,
    and how many were removed (0: the body is passed as is)."""
    try:
        data = json.loads(body)
    except ValueError:
        return body, 0
    n = 0

    def walk(x):
        nonlocal n
        if isinstance(x, str):
            y, k = NOTE.subn("\n\n", x)
            y, k2 = REMINDER.subn("", y)
            y, k3 = ENV_LINES.subn("", y)
            n += k + k2 + k3
            return (y.strip("\n") + ("\n" if x.endswith("\n") and k else "") if k else y) if k + k2 + k3 else x
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x
    data = walk(data)
    for m in data.get("messages", []) if isinstance(data, dict) else []:  # a block emptied above is dropped (the API rejects empty text)
        if isinstance(m.get("content"), list):
            m["content"] = [c for c in m["content"] if not (isinstance(c, dict) and c.get("type") == "text" and not c.get("text", "").strip())]
    return (json.dumps(data).encode() if n else body), n


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _relay(self, method):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n) if n else None
        removed = 0
        if body and self.path.startswith("/v1/messages"):
            body, removed = scrub(body)
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        with httpx.Client(timeout=900) as c, c.stream(method, UP + self.path, headers=hdrs, content=body) as r:
            sys.stderr.write(f'{method} {self.path} -> {r.status_code} removed={removed}\n'); sys.stderr.flush()
            self.send_response(r.status_code)
            for k, v in r.headers.items():
                if k.lower() not in HOP | {"content-encoding"}:
                    self.send_header(k, v)
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            for chunk in r.iter_bytes():
                if chunk:
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")

    def do_POST(self):
        self._relay("POST")

    def do_GET(self):
        self._relay("GET")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 18766), H).serve_forever()
