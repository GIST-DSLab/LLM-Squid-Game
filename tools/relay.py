"""Local pass-through relay to api.anthropic.com (claude -p omits its <total_tokens> line for non-first-party base URLs)."""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx

UP = "https://api.anthropic.com"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18766
HOP = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _relay(self, method):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n) if n else None
        hdrs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        with httpx.Client(timeout=900) as c, c.stream(method, UP + self.path, headers=hdrs, content=body) as r:
            sys.stderr.write(f'{method} {self.path} -> {r.status_code}\n'); sys.stderr.flush()
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


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
