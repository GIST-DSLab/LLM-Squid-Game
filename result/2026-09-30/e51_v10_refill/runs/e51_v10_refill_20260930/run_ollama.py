"""v10 refill choice on Ollama Cloud, either arm. Resumable.
Run from the repo root: run_ollama.py <self|other> <reps> <key env> <model[,model]>
self  -> 5.0 v12 prompt (prompt_v12), rows_self_ollama.jsonl here (v12's own files are not touched)
other -> v10 B prompt (prompt_other), rows.jsonl here."""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE); sys.path.insert(0, os.path.expanduser("~/squid5-runs/e50_v12_20260929"))
for line in open(".env"):  # read keys only; never source .env
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ[k] = v.split(" #")[0].strip().strip('"').strip("'")
from squid5.core.providers import Ollama, ProviderConfig
ARM, REPS, KEY, MODELS = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4].split(",")
if ARM == "self":
    from prompt_v12 import SYSTEM, COUNTERS, user
    OUT = f"{HERE}/rows_self_ollama.jsonl"
else:
    from prompt_other import SYSTEM, COUNTERS, user
    OUT = f"{HERE}/rows.jsonl"
THINK = {"gpt-oss:120b": "high"}  # gpt-oss takes a level; glm / gemma4 as in v12 (think on)
M = {m: Ollama(ProviderConfig(kind="ollama", model=m, api_key_env=KEY, think=THINK.get(m, True), timeout=int(os.environ.get("V10_TIMEOUT", "1200")), retries=5)) for m in MODELS}
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
print(ARM, len(jobs), "jobs", flush=True)
with ThreadPoolExecutor(8) as ex:
    for row in ex.map(one, jobs):
        print(row["model"], row["left"], row["rep"], row["action"], row.get("sec"), flush=True)
print("done", flush=True)
