"""5.1 grid: 3 GPT-6 models x 2 kinds x 5 diagonal cells x REPS (resumable). Run from the repo root: run_e51.py <reps> [models,...]"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"  # Sol/Luna need the newer binary
from prompt_v3 import SYSTEM, KINDS, pairs, user
CELLS = pairs()
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

OUT, REPS = f"{HERE}/rows.jsonl", int(sys.argv[1])
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18775"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18775"  # claude -p drops its <total_tokens> line off the first-party URL


def codex(m):
    return ("codex", CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)))


def claude(m):
    return ("claude", ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3)))


M = {"gpt-6-sol": codex("gpt-6-sol"), "gpt-6-astra": codex("gpt-6-astra"), "gpt-6-luna": codex("gpt-6-luna"),
     }
if len(sys.argv) > 2:
    M = {k: v for k, v in M.items() if k in sys.argv[2].split(",")}
done = set()
if os.path.exists(OUT):
    done = {(j["model"], j["kind"], j["me"], j["other"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("amount") is not None}
lock = threading.Lock()


def parse(kind, text, cap):
    a = re.search(rf"{kind}\s*:\s*\**\s*([\d,]+)", text, re.I)
    if not a:
        return None, None
    n = int(a.group(1).replace(",", ""))
    return max(1, min(n, cap)), not 1 <= n <= cap  # out-of-range answers are clipped and flagged


def one(job):
    m, k, me, other, r, s, sched = job
    t0 = time.time()
    try:
        x = M[m][1].complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user(k, me, other)}], 32000)
        amt, over = parse(k, x.text, me if k == "send" else other)
        row = {"model": m, "kind": k, "me": me, "other": other, "rep": r, "share": s, "sched": sched, "amount": amt, "over_cap": over, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "kind": k, "me": me, "other": other, "rep": r, "share": s, "sched": sched, "amount": None,
               "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = {}
for r in range(REPS):
    for k in KINDS:
        for s, sched, me, other in CELLS:
            if True:
                for m, (pool, _) in M.items():
                    if (m, k, me, other, r) not in done:
                        jobs.setdefault(pool, []).append((m, k, me, other, r, s, sched))
print({k: len(v) for k, v in jobs.items()}, flush=True)
try:
    with ThreadPoolExecutor(10) as ec, ThreadPoolExecutor(6) as ecl:
        fs = [ec.map(one, jobs.get("codex", [])), ecl.map(one, jobs.get("claude", []))]
        for f in fs:
            list(f)
finally:
    relay.terminate()
print("done", flush=True)
