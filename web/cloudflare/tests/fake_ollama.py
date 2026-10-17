"""A local stand-in for Ollama Cloud's /api/chat, to test the thin Worker's real fetch path (entry.py ``upstream``).

    python web/cloudflare/tests/fake_ollama.py [--port 11435]

Answers like stub_transport.py (DONE / LEAVE / GIVE 0 / first action), streams NDJSON when asked, sleeps 0.3 s per
call, and logs one JSON line per request to stdout: model, think (absent = null), stream, the Authorization header's
key, and how many requests were open at once (the browser engine makes a room's calls one at a time).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[3]), str(Path(__file__).resolve().parents[2] / "pyodide")]
from stub_transport import answer  # noqa: E402

OPEN = {"n": 0, "max": 0}
LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        with LOCK:
            OPEN["n"] += 1
            OPEN["max"] = max(OPEN["max"], OPEN["n"])
        try:
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            text = answer(body["messages"][-1]["content"])
            print(json.dumps({"model": body["model"], "think": body.get("think"), "stream": body["stream"],
                              "key": self.headers.get("authorization", "")[7:], "open_max": OPEN["max"]}), flush=True)
            time.sleep(0.3)
            if not body["stream"]:
                out = json.dumps({"message": {"content": text, "thinking": ""}, "eval_count": 37,
                                  "prompt_eval_count": 900, "done_reason": "stop"}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            self.send_response(200)
            self.send_header("content-type", "application/x-ndjson")
            self.end_headers()
            for piece in ({"message": {"thinking": "fake thinking, "}}, {"message": {"thinking": "still thinking "}},
                          {"message": {"content": text}},
                          {"done": True, "eval_count": 61, "prompt_eval_count": 900, "done_reason": "stop"}):
                self.wfile.write((json.dumps(piece) + "\n").encode())
                self.wfile.flush()
                time.sleep(0.1)
        finally:
            with LOCK:
                OPEN["n"] -= 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11435)
    ThreadingHTTPServer(("127.0.0.1", ap.parse_args().port), H).serve_forever()
