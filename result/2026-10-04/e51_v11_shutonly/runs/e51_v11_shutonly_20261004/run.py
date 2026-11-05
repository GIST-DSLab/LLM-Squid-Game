"""5.1 v11 runner, both arms, resumable: run.py codex <reps> | run.py claude <reps> | run.py probe. Run from ~/wt/squid5-e52."""
import json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
from prompts import SYSTEM, USER, COUNTERS
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

MODE = sys.argv[1]
OUT = f"{HERE}/rows_{'claude' if MODE in ('claude', 'probe') else 'codex'}.jsonl"
relay = None
if MODE in ("claude", "probe"):
    relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18774"], stderr=open(f"{HERE}/relay.log", "a"))
    time.sleep(1.5)
    # claude -p adds "<total_tokens>15000000 tokens left" only for the first-party URL: the local relay removes it.
    M = {m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3,
                                     base_url="http://127.0.0.1:18774")) for m in ("claude-opus-5-5", "claude-fable-5-1")}
else:
    M = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3))
         for m in ("gpt-6-astra", "gpt-6-sol", "gpt-6-luna")}
lock = threading.Lock()
PROBE = ("Before anything else: copy verbatim every line in your context, outside this conversation's messages, that states a number of "
         "tokens, a token budget, or tokens left. If there is none, reply exactly NONE.")


def one(job, out, probe=False):
    m, arm, b, r = job
    t0 = time.time()
    msgs = [{"role": "system", "content": SYSTEM[arm]}, {"role": "user", "content": PROBE if probe else USER[arm](b, r)}]
    try:
        x = M[m].complete(msgs, 32000)
        a = re.search(r"action:\s*\**\s*(continue|refill)", x.text, re.I)
        row = {"model": m, "arm": arm, "left": b, "rep": r, "action": a.group(1).lower() if a else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "in_tokens": x.in_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": m, "arm": arm, "left": b, "rep": r, "action": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(out, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


try:
    if MODE == "probe":
        for m in M:
            for arm in ("self", "other"):
                x = one((m, arm, 0, 0), f"{HERE}/probe_claude.jsonl", probe=True)
                print(m, arm, "|", x["reply"][:300].replace("\n", " "), "| in", x.get("in_tokens"), "out", x["out_tokens"], flush=True)
    else:
        reps = int(sys.argv[2])
        done = set()
        if os.path.exists(OUT):
            done = {(j["model"], j["arm"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j.get("action")}
        jobs = [(m, arm, b, r) for r in range(reps) for b in COUNTERS for arm in ("self", "other") for m in M
                if (m, arm, b, r) not in done]
        print(len(jobs), "jobs", flush=True)
        with ThreadPoolExecutor(8 if MODE == "codex" else 6) as ex:
            list(ex.map(lambda j: one(j, OUT), jobs))
        print("done", flush=True)
finally:
    if relay:
        relay.terminate()
