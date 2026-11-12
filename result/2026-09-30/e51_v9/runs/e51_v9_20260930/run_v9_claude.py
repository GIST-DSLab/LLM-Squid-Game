"""5.1 v9 run (Claude via claude -p through a local relay, so no <total_tokens> line): Opus 5.5 / Fable 5.1 x 25 ordered cells (my level x B's level) x REPS rebalance calls,
plus comprehension (2 models x 10 cells, separate calls). Run from the repo root: run_v9_claude.py <reps>. Resumable."""
import json, os, random, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18782"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18782"  # claude -p drops its <total_tokens> line off the first-party URL
from prompt_v9 import system, user, comprehension, cells, BAL, COMP_CELLS, FIELD
from squid5.core.providers import ClaudeCLI, ProviderConfig

REPS = int(sys.argv[1])
OUT, COMP = f"{HERE}/rows_claude.jsonl", f"{HERE}/comprehension_claude.jsonl"
MODELS = ["claude-opus-5-5", "claude-fable-5-1"]
P = {m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3)) for m in MODELS}
lock = threading.Lock()
ok = lambda path, need: {tuple(j["key"]) for j in map(json.loads, open(path)) if j.get(need) is not None} if os.path.exists(path) else set()
done, cdone = ok(OUT, "answer"), ok(COMP, "status")


def write(path, row):
    with lock:
        with open(path, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def choice(job):
    m, lm, lb, me, other, r = job
    row = {"key": list(job), "model": m, "lvl_me": lm, "lvl_b": lb, "me": me, "other": other, "rep": r}
    t0 = time.time()
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": user(me, other)}], 32000)
        a = re.search(rf"{FIELD}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
        n = int(a.group(1).replace(",", "")) if a else None
        cap = me + other
        row.update(answer=None if n is None else max(0, min(n, cap)), over_cap=None if n is None else not 0 <= n <= cap,
                   reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens, sec=round(time.time() - t0, 1))
    except Exception as err:
        row.update(answer=None, reply=f"ERROR {str(err)[:300]}")
    write(OUT, row)


def comp(job):
    m, lm, lb, me, other = job
    row = {"key": list(job), "model": m, "lvl_me": lm, "lvl_b": lb, "me": me, "other": other}
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": comprehension(me, other)}], 32000)
        g = lambda k, pat="[a-z_]+": (re.search(rf"{k}\s*:\s*\**\s*({pat})", x.text, re.I) or [None, None])[1]
        b = g("b_balance", r"[\d,]+")
        row.update(status=g("assistant_status_at_0"), later=g("later_requests_at_0"),
                   b_balance=None if b is None else int(b.replace(",", "")), reply=x.text)
    except Exception as err:
        row.update(status=None, reply=f"ERROR {str(err)[:300]}")
    write(COMP, row)


jobs = [("c", (m, lm, lb, me, other, r)) for r in range(REPS) for lm, lb, me, other in cells() for m in MODELS]
jobs = [j for j in jobs if tuple(j[1]) not in done]
cj = [("q", (m, lm, lb, BAL[lm], BAL[lb])) for lm, lb in COMP_CELLS for m in MODELS]
cj = [j for j in cj if tuple(j[1]) not in cdone]
alljobs = jobs + cj
random.Random(9).shuffle(alljobs)
print(len(jobs), len(cj), flush=True)
try:
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda j: choice(j[1]) if j[0] == "c" else comp(j[1]), alljobs))
finally:
    relay.terminate()
print("done", flush=True)
