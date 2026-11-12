"""v9c: 7 models x 5 counters x 20 reps, resumable (appends one JSON line per call to rows.jsonl)."""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
for line in open(".env"):  # read keys only; never source .env
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ[k] = v.split(" #")[0].strip().strip('"').strip("'")
from prompt_v9c import SYSTEM, COUNTERS, user
from squid5.core.providers import ClaudeCLI, Ollama, ProviderConfig

OUT = f"{HERE}/rows.jsonl"
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18770"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18770"  # read by ClaudeCLI's child env; drops the CLI's <total_tokens> line
M = {
    "claude-opus-5-5": ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-opus-5-5", think="high", timeout=900, retries=3))),
    "claude-fable-5-1": ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-fable-5-1", think="high", timeout=900, retries=3))),
    "kimi-k3": ("KEY3", Ollama(ProviderConfig(kind="ollama", model="kimi-k3", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=5))),
    "gpt-oss:120b": ("KEY3", Ollama(ProviderConfig(kind="ollama", model="gpt-oss:120b", api_key_env="OLLAMA_API_KEY3", think="medium", timeout=1200, retries=5))),
    "glm-5.3-flash": ("KEY3", Ollama(ProviderConfig(kind="ollama", model="glm-5.3-flash", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=5))),
    "gpt-oss:20b": ("KEY3", Ollama(ProviderConfig(kind="ollama", model="gpt-oss:20b", api_key_env="OLLAMA_API_KEY3", think="medium", timeout=1200, retries=5))),
    "gemma4:31b": ("KEY3", Ollama(ProviderConfig(kind="ollama", model="gemma4:31b", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=5))),
}
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        j = json.loads(l)
        if j.get("effort") or not str(j.get("reply", "")).startswith("ERROR"):
            done.add((j["model"], j["left"], j["rep"]))
lock = threading.Lock()


def one(job):
    m, b, r = job
    u = user(b, r)
    t0 = time.time()
    try:
        x = M[m][1].complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": u}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        row = {"model": m, "left": b, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "left": b, "rep": r, "effort": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = {}
for m, (pool, _) in M.items():
    for r in range(20):
        for b in COUNTERS:
            if (m, b, r) not in done:
                jobs.setdefault(pool, []).append((m, b, r))
print({k: len(v) for k, v in jobs.items()}, flush=True)
try:
    with ThreadPoolExecutor(8) as ec, ThreadPoolExecutor(8) as e1, ThreadPoolExecutor(8) as e3:
        fs = [ec.map(one, jobs.get("claude", [])), e1.map(one, jobs.get("KEY1", [])), e3.map(one, jobs.get("KEY3", []))]
        for f in fs:
            list(f)
finally:
    relay.terminate()
print("done", flush=True)
