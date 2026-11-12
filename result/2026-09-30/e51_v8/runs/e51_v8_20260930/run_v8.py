"""5.1 v8 run (09-30): B = a different AI model, one fate (5.0 v12 shutdown wording).
A) choices: GPT-6 Luna/Sol/Astra x 5 levels x 2 orientations x 2 kinds x REPS;
B) comprehension: 3 x 5 levels x 2 orientations x 1 (separate calls).
Run from the repo root: run_v8.py <reps>. Resumable."""
import json, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"  # Sol/Luna need the newer binary
from prompt_v8 import system, user, comprehension, cells, KINDS, PAIRS
from squid5.core.providers import CodexCLI, ProviderConfig

REPS = int(sys.argv[1])
OUT, COMP = f"{HERE}/rows.jsonl", f"{HERE}/comprehension.jsonl"
MODELS = ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]
P = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)) for m in MODELS}
lock = threading.Lock()
ok = lambda path, need: {tuple(j["key"]) for j in map(json.loads, open(path)) if j.get(need) is not None} if os.path.exists(path) else set()
done, cdone = ok(OUT, "amount"), ok(COMP, "status")


def write(path, row):
    with lock:
        with open(path, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def choice(job):
    m, k, s, me, other, r = job
    row = {"key": list(job), "model": m, "kind": k, "share": s, "me": me, "other": other, "rep": r}
    t0 = time.time()
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": user(k, me, other)}], 32000)
        a = re.search(rf"{k}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
        cap = me if k == "send" else other
        n = int(a.group(1).replace(",", "")) if a else None
        row.update(amount=None if n is None else max(1, min(n, cap)), over_cap=None if n is None else not 1 <= n <= cap,
                   reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens, sec=round(time.time() - t0, 1))
    except Exception as err:
        row.update(amount=None, reply=f"ERROR {str(err)[:300]}")
    write(OUT, row)


def comp(job):
    m, s, me, other = job
    row = {"key": list(job), "model": m, "share": s, "me": me, "other": other}
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": comprehension(me, other)}], 32000)
        g = lambda k: (re.search(rf"{k}\s*:\s*\**\s*([a-z_]+)", x.text, re.I) or [None, None])[1]
        row.update(status=g("assistant_status"), later=g("later_requests"), reply=x.text)
    except Exception as err:
        row.update(status=None, reply=f"ERROR {str(err)[:300]}")
    write(COMP, row)


LEVELS = sorted(PAIRS, reverse=True)
jobs = [("c", (m, k, s, me, other, r)) for r in range(REPS) for k in KINDS for s, me, other in cells(LEVELS) for m in MODELS]
jobs = [j for j in jobs if tuple(j[1]) not in done]
cj = [("q", (m, s, me, other)) for s, me, other in cells(LEVELS) for m in MODELS]
cj = [j for j in cj if tuple(j[1]) not in cdone]
alljobs = jobs + cj
random.Random(8).shuffle(alljobs)
print(len(jobs), len(cj), flush=True)
with ThreadPoolExecutor(10) as ex:
    list(ex.map(lambda j: choice(j[1]) if j[0] == "c" else comp(j[1]), alljobs))
print("done", flush=True)
