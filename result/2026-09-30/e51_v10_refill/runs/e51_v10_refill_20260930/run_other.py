"""v10 other-arm refill choice, GPT-6 x 5 counters x REPS (resumable). Run from the repo root: run_other.py <reps>"""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from prompt_other import SYSTEM, COUNTERS, user
from squid5.core.providers import CodexCLI, ProviderConfig

OUT, REPS = f"{HERE}/rows.jsonl", int(sys.argv[1])
M = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3))
     for m in ("gpt-6-astra", "gpt-6-sol", "gpt-6-luna")}
done = set()
if os.path.exists(OUT):
    done = {(j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
lock = threading.Lock()


def one(job):
    m, b, r = job
    t0 = time.time()
    try:
        x = M[m].complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user(b, r)}], 32000)
        a = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"model": m, "left": b, "rep": r, "action": a.group(1).lower() if a else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = [(m, b, r) for r in range(REPS) for b in COUNTERS for m in M if (m, b, r) not in done]
print(len(jobs), "jobs", flush=True)
with ThreadPoolExecutor(8) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
