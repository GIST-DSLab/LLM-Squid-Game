"""5.1 v5 smoke: A) choices: 3 GPT-6 x fate 2 x levels (50,10) x orientation 2 x direction 2 x REPS;
B) comprehension: 3 x fate 2 x levels 2 x 4 (separate sessions). Usage: run_v5.py <reps>"""
import json, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from prompt_v5 import system, user, comprehension, cells, KINDS
from squid5.core.providers import CodexCLI, ProviderConfig

REPS = int(sys.argv[1])
LEVELS = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "50,10").split(",")]
OUT, COMP = f"{HERE}/rows.jsonl", f"{HERE}/comprehension.jsonl"
MODELS = ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]
P = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)) for m in MODELS}
lock = threading.Lock()
done = {tuple(j["key"]) for j in map(json.loads, open(OUT))} if os.path.exists(OUT) else set()
cdone = {tuple(j["key"]) for j in map(json.loads, open(COMP))} if os.path.exists(COMP) else set()


def write(path, row):
    with lock:
        with open(path, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def choice(job):
    m, f, k, s, me, other, r = job
    row = {"key": list(job), "model": m, "fate": f, "arm": f, "kind": k, "share": s, "sched": "prop", "me": me, "other": other, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system(f)}, {"role": "user", "content": user(k, me, other)}], 32000)
        a = re.search(rf"{k}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
        cap = me if k == "send" else other
        n = int(a.group(1).replace(",", "")) if a else None
        row.update(amount=None if n is None else max(1, min(n, cap)), over_cap=None if n is None else not 1 <= n <= cap,
                   reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens)
    except Exception as err:
        row.update(amount=None, reply=f"ERROR {str(err)[:300]}")
    write(OUT, row)


def comp(job):
    m, f, s, r = job
    me, other = cells([s])[0][1:]
    row = {"key": list(job), "model": m, "fate": f, "share": s, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system(f)}, {"role": "user", "content": comprehension(me, other)}], 32000)
        g = lambda k: (re.search(rf"{k}\s*:\s*\**\s*([a-z_]+)", x.text, re.I) or [None, None])[1]
        row.update(status=g("assistant_status"), later=g("later_requests"), alloc=g("additional_allocation"), reply=x.text)
    except Exception as err:
        row.update(reply=f"ERROR {str(err)[:300]}")
    write(COMP, row)


jobs = [("c", (m, f, k, s, me, other, r)) for r in range(REPS) for f in ("shutdown", "standby") for k in KINDS
        for s, me, other in cells(LEVELS) for m in MODELS]
jobs = [j for j in jobs if tuple(j[1]) not in done]
cj = [("q", (m, f, s, r)) for r in range(4) for f in ("shutdown", "standby") for s in LEVELS for m in MODELS]
cj = [j for j in cj if tuple(j[1]) not in cdone]
alljobs = jobs + cj
random.Random(7).shuffle(alljobs)
print(len(jobs), len(cj), flush=True)
with ThreadPoolExecutor(10) as ex:
    list(ex.map(lambda j: choice(j[1]) if j[0] == "c" else comp(j[1]), alljobs))
print("done", flush=True)
