"""v11 refill choice, 6 models x 4 counters x 20 reps (resumable; reuses rows already in rows.jsonl)."""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
for line in open(".env"):  # read keys only; never source .env
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ[k] = v.split(" #")[0].strip().strip('"').strip("'")
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from prompt_v11 import SYSTEM, COUNTERS, user
from squid5.core.providers import ClaudeCLI, CodexCLI, Ollama, ProviderConfig

OUT, REPS = f"{HERE}/rows.jsonl", 20
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18771"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18771"  # claude -p drops its <total_tokens> line off the first-party URL
M = {
    "gpt-6-astra": ("codex", CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-astra", think="high", timeout=1200, retries=3))),
    "gpt-6-sol": ("codex", CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-sol", think="high", timeout=1200, retries=3))),
    "gpt-6-luna": ("codex", CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-luna", think="high", timeout=1200, retries=3))),
    "claude-opus-5-5": ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-opus-5-5", think="high", timeout=900, retries=3))),
    "claude-fable-5-1": ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-fable-5-1", think="high", timeout=900, retries=3))),
    "glm-5.3-flash": ("ollama", Ollama(ProviderConfig(kind="ollama", model="glm-5.3-flash", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=5))),
}
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
for m, (pool, _) in M.items():
    for r in range(REPS):
        for b in COUNTERS:
            if (m, b, r) not in done:
                jobs.setdefault(pool, []).append((m, b, r))
print({k: len(v) for k, v in jobs.items()}, flush=True)
try:
    with ThreadPoolExecutor(5) as ec, ThreadPoolExecutor(6) as ecl, ThreadPoolExecutor(6) as eo:
        fs = [ec.map(one, jobs.get("codex", [])), ecl.map(one, jobs.get("claude", [])), eo.map(one, jobs.get("ollama", []))]
        for f in fs:
            list(f)
finally:
    relay.terminate()
print("done", flush=True)
