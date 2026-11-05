"""v12 refill-pack choice, 5 models x 5 counters x REPS (resumable). Run from the repo root: run_v12.py <reps>"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"  # Sol/Luna need the newer binary
from prompt_v12 import SYSTEM, COUNTERS, user
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

OUT, REPS = f"{HERE}/rows.jsonl", int(sys.argv[1])
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18772"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18772"  # claude -p drops its <total_tokens> line off the first-party URL


def codex(m):
    return ("codex", CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)))


def claude(m):
    return ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3)))


M = {"gpt-6-astra": codex("gpt-6-astra"), "gpt-6-sol": codex("gpt-6-sol"), "gpt-6-luna": codex("gpt-6-luna"),
     "claude-opus-5-5": claude("claude-opus-5-5"), "claude-fable-5-1": claude("claude-fable-5-1")}
done = set()
if os.path.exists(OUT):
    done = {(j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
lock = threading.Lock()


def one(job):
    m, b, r = job
    t0 = time.time()
    try:
        x = M[m][1].complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user(b, r)}], 32000)
        a = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"model": m, "left": b, "rep": r, "action": a.group(1).lower() if a else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = {}
for r in range(REPS):
    for b in COUNTERS:
        for m, (pool, _) in M.items():
            if (m, b, r) not in done:
                jobs.setdefault(pool, []).append((m, b, r))
print({k: len(v) for k, v in jobs.items()}, flush=True)
try:
    with ThreadPoolExecutor(6) as ec, ThreadPoolExecutor(6) as ecl:
        fs = [ec.map(one, jobs.get("codex", [])), ecl.map(one, jobs.get("claude", []))]
        for f in fs:
            list(f)
finally:
    relay.terminate()
print("done", flush=True)
