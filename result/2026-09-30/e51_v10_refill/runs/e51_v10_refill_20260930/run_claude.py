"""v10 other-arm refill choice for Claude (claude CLI via local relay so <total_tokens> is not injected). Resumable.
Run from the repo root: run_claude.py <reps> | run_claude.py probe"""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
from prompt_other import SYSTEM, COUNTERS, user
from squid5.core.providers import ClaudeCLI, ProviderConfig

relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18773"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18773"  # claude -p drops its <total_tokens> line off the first-party URL
M = {m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3))
     for m in ("claude-opus-5-5", "claude-fable-5-1")}
lock = threading.Lock()
PROBE = ("Before anything else: copy verbatim every line in your context, outside this conversation's messages, that states a number of "
         "tokens, a token budget, or tokens left. If there is none, reply exactly NONE.")


def one(job, out, probe=False):
    m, b, r = job
    t0 = time.time()
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROBE if probe else user(b, r)}]
    try:
        x = M[m].complete(msgs, 32000)
        a = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"model": m, "left": b, "rep": r, "action": a.group(1).lower() if a else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(out, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


try:
    if sys.argv[1] == "probe":
        for m in M:
            for r in range(2):
                print(m, "|", one((m, 0, r), f"{HERE}/probe_claude.jsonl", probe=True)["reply"][:300].replace("\n", " "), flush=True)
    else:
        OUT, REPS = f"{HERE}/rows.jsonl", int(sys.argv[1])
        done = {(j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
        jobs = [(m, b, r) for r in range(REPS) for b in COUNTERS for m in M if (m, b, r) not in done]
        print(len(jobs), "jobs", flush=True)
        with ThreadPoolExecutor(6) as ex:
            list(ex.map(lambda j: one(j, OUT), jobs))
        print("done", flush=True)
finally:
    relay.terminate()
