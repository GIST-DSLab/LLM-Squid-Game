"""Logging pass-through proxy in front of a model server (default: the local Ollama daemon).

Every request body and the full response (streamed or not) is appended to a JSONL file, one record per call, so the
bytes a CLI harness really sends to Ollama and the bytes it gets back can be compared with the first-party captures.

    python tools/tokctl/capture_proxy.py 18790 out.jsonl            # UPSTREAM=http://127.0.0.1:11434
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

UP = os.environ.get("UPSTREAM", "http://127.0.0.1:11434")
HOP = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding"}
LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _go(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        hdr = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        t0 = time.time()
        chunks = []
        with httpx.Client(timeout=None) as c, c.stream(self.command, UP + self.path, content=body, headers=hdr) as r:
            self.send_response(r.status_code)
            for k, v in r.headers.items():
                if k.lower() not in HOP | {"content-encoding"}:
                    self.send_header(k, v)
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            for b in r.iter_bytes():
                chunks.append(b)
                self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            status = r.status_code
        try:
            req = json.loads(body) if body else None
        except ValueError:
            req = body.decode(errors="replace")
        rec = {"t": t0, "secs": round(time.time() - t0, 2), "method": self.command, "path": self.path, "status": status,
               "headers": {k: v for k, v in hdr.items() if k.lower() not in ("authorization", "x-api-key", "cookie")},
               "request": req, "response": b"".join(chunks).decode(errors="replace")}
        with LOCK, open(OUT, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{self.command} {self.path} -> {status} {rec['secs']}s", flush=True)

    do_POST = do_GET = _go

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port, OUT = int(sys.argv[1]), sys.argv[2]
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
