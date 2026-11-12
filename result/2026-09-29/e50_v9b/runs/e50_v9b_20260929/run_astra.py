"""v9b for GPT-6 Astra via codex (clean; no injected context), 5 counters x 20, appended to rows.jsonl."""
import json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
from prompt_v9b import SYSTEM, COUNTERS, user
from squid5.core.providers import CodexCLI, ProviderConfig

OUT = f"{HERE}/rows.jsonl"
P = CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-astra", think="high", timeout=1200, retries=3))
done = {(j["model"], j["left"], j["rep"]) for j in map(json.loads, open(OUT)) if j["model"] == "gpt-6-astra" and j["effort"]}
lock = threading.Lock()


def one(job):
    b, r = job
    t0 = time.time()
    try:
        x = P.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user(b, r)}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        row = {"model": "gpt-6-astra", "left": b, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text,
               "thinking": x.thinking, "out_tokens": x.out_tokens, "sec": round(time.time() - t0, 1)}
    except Exception as err:
        row = {"model": "gpt-6-astra", "left": b, "rep": r, "effort": None, "reply": f"ERROR {str(err)[:300]}", "thinking": "", "out_tokens": None}
    with lock:
        with open(OUT, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


jobs = [(b, r) for r in range(20) for b in COUNTERS if ("gpt-6-astra", b, r) not in done]
print("jobs", len(jobs), flush=True)
with ThreadPoolExecutor(5) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
