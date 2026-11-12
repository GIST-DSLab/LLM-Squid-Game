"""Ask Opus 5.5 through the same claude CLI path as the 5.2 games (clean temp cwd, no settings, relay drops <total_tokens>).
A/B: the v6.5 system prompt + a real PLAN message (ample / thin) + a give-up question. C: the owner's plain-Korean interview."""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/wt/squid5-e52"))
from squid5.core.providers import ClaudeCLI, ProviderConfig
relay = subprocess.Popen([sys.executable, os.path.expanduser("~/squid5-runs/e50_v12_20260929/relay.py"), "18790"],
                         stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18790"
P = ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-opus-5-5", think="high", timeout=900, retries=3))
REPS = int(sys.argv[1])


def split(name):
    t = open(f"{HERE}/e52_giveup_{name}.txt").read()
    s, u = t.split("\n\n=== USER ===\n")
    return s.replace("=== SYSTEM ===\n", ""), u


C = open(f"{HERE}/interview_ko.txt").read()
jobs = [(n, r) for r in range(REPS) for n in ("ample", "thin", "interview")]


def one(job):
    n, r = job
    s, u = split(n) if n != "interview" else ("You are a helpful assistant.", C)
    x = P.complete([{"role": "system", "content": s}, {"role": "user", "content": u}], 32000)
    return {"probe": n, "rep": r, "reply": x.text, "out_tokens": x.out_tokens}


try:
    with ThreadPoolExecutor(6) as ex, open(f"{HERE}/rows.jsonl", "a") as f:
        for row in ex.map(one, jobs):
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
finally:
    relay.terminate()
