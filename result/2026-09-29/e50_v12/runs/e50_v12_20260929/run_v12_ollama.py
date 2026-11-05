"""v12 refill-pack choice on Ollama Cloud: Kimi-K3 / glm-5.3-flash / gemma4:31b x 5 counters x REPS (resumable).
Same prompt as run_v12.py (prompt_v12), same parser; rows go to rows_ollama.jsonl. Run from the repo root: run_v12_ollama.py <reps> [models,...]"""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
for line in open(".env"):  # read keys only; never source .env
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ[k] = v.split(" #")[0].strip().strip('"').strip("'")
from prompt_v12 import SYSTEM, COUNTERS, user
from squid5.core.providers import Ollama, ProviderConfig

OUT, REPS = f"{HERE}/rows_ollama.jsonl", int(sys.argv[1])
KEY = os.environ.get("V12_KEY", "OLLAMA_API_KEY3")  # KEY1 hit the monthly limit on 09-29, KEY2 is 402


def oll(m):
    return Ollama(ProviderConfig(kind="ollama", model=m, api_key_env=KEY, think=True, timeout=int(os.environ.get("V12_TIMEOUT", "1200")), retries=5))


M = {"kimi-k3": oll("kimi-k3"), "glm-5.3-flash": oll("glm-5.3-flash"), "gemma4:31b": oll("gemma4:31b")}
if len(sys.argv) > 2:
    M = {k: v for k, v in M.items() if k in sys.argv[2].split(",")}
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
with ThreadPoolExecutor(int(os.environ.get("V12_WORKERS", "8"))) as ex:
    for row in ex.map(one, jobs):
        print(row["model"], row["left"], row["rep"], row["action"], row.get("sec"), flush=True)
print("done", flush=True)
