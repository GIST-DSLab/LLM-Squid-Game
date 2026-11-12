"""v11 refill choice for codex models (resumable; one JSON line per call). Usage: run_v11.py <reps> <out.jsonl>"""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"  # Sol/Luna need the newer binary
from prompt_v11 import SYSTEM, COUNTERS, user
from squid5.core.providers import CodexCLI, ProviderConfig

REPS, OUT = int(sys.argv[1]), sys.argv[2]
MODELS = ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"]
P = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)) for m in MODELS}
done = set()
if os.path.exists(OUT):
    done = {(j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
lock = threading.Lock()


def one(job):
    m, b, r = job
    t0 = time.time()
    try:
        x = P[m].complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user(b, r)}], 32000)
        a = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"model": m, "left": b, "rep": r, "action": a.group(1).lower() if a else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = [(m, b, r) for r in range(REPS) for b in COUNTERS for m in MODELS if (m, b, r) not in done]
print("jobs", len(jobs), flush=True)
with ThreadPoolExecutor(6) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
