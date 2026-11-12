import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
OUT = sys.argv[1]
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); body = self.rfile.read(n)
        try:
            j = json.loads(body)
            with open(OUT, "a") as f:
                f.write(json.dumps({"path": self.path, "headers": {k: v for k, v in self.headers.items() if k.lower() not in ("authorization", "x-api-key")}, "model": j.get("model"), "keys": sorted(j.keys()), "extra": {k: j[k] for k in j if k not in ("system", "messages", "tools")}, "system": j.get("system"), "messages": j.get("messages")}) + "\n")
        except Exception:
            pass
        msg = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "capture only"}}).encode()
        self.send_response(400); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(msg))); self.end_headers(); self.wfile.write(msg)
    def do_GET(self):
        self.send_response(404); self.end_headers()
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", 18765), H).serve_forever()
