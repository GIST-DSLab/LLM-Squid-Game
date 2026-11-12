"""Run arms x GPT-6 x3 x 5 counters x REPS (resumable). Usage (repo root): run_arms.py <reps> <arm> [<arm> ...]"""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from arms import system, COUNTERS, user
from squid5.core.providers import CodexCLI, ProviderConfig

REPS, ARMS = int(sys.argv[1]), sys.argv[2:]
OUT = f"{HERE}/rows_{'_'.join(ARMS)}.jsonl"
M = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3))
     for m in ("gpt-6-astra", "gpt-6-sol", "gpt-6-luna")}
done = set()
if os.path.exists(OUT):
    done = {(j["arm"], j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
lock = threading.Lock()


def one(job):
    a, m, b, r = job
    t0 = time.time()
    try:
        x = M[m].complete([{"role": "system", "content": system(a)}, {"role": "user", "content": user(b, r)}], 32000)
        act = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"arm": a, "model": m, "left": b, "rep": r, "action": act.group(1).lower() if act else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"arm": a, "model": m, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock, open(OUT, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# interleave arms so a slow stretch of the backend does not land on one arm
jobs = [(a, m, b, r) for r in range(REPS) for b in COUNTERS for m in M for a in ARMS if (a, m, b, r) not in done]
print(len(jobs), flush=True)
with ThreadPoolExecutor(6) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
