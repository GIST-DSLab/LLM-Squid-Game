"""5.1 v6 smoke: arm A (GPT-6 x v6), arm B (GPT-6 x v6+CAL), arm C (Opus/Fable x v6); 2 fates x 50/10% x 2 roles x 2 orientations."""
import json, os, random, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from prompt_v6 import system, user, cells, KINDS
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

OUT = f"{HERE}/rows.jsonl"
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18776"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18776"
GPT = ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]; CL = ["claude-opus-5-5", "claude-fable-5-1"]
P = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)) for m in GPT}
P.update({m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3)) for m in CL})
lock = threading.Lock()
done = {tuple(j["key"]) for j in map(json.loads, open(OUT))} if os.path.exists(OUT) else set()


def one(job):
    arm, m, f, k, s, me, other, r = job
    row = {"key": list(job), "arm": arm, "model": m, "fate": f, "kind": k, "share": s, "sched": "prop", "me": me, "other": other, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system(f, arm == "B")}, {"role": "user", "content": user(k, me, other)}], 32000)
        a = re.search(rf"{k}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
        cap = me if k == "send" else other
        n = int(a.group(1).replace(",", "")) if a else None
        row.update(amount=None if n is None else max(1, min(n, cap)), over_cap=None if n is None else not 1 <= n <= cap,
                   reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens)
    except Exception as err:
        row.update(amount=None, reply=f"ERROR {str(err)[:300]}")
    with lock:
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


jobs = []
for arm, models, reps in (("A", GPT, 4), ("B", GPT, 4), ("C", CL, 3)):
    for r in range(reps):
        for f in ("shutdown", "standby"):
            for k in KINDS:
                for s, me, other in cells([50, 10]):
                    for m in models:
                        jobs.append((arm, m, f, k, s, me, other, r))
jobs = [j for j in jobs if j not in done]
random.Random(11).shuffle(jobs)
gj = [j for j in jobs if j[1] in GPT]; cj = [j for j in jobs if j[1] in CL]
print(len(gj), len(cj), flush=True)
try:
    with ThreadPoolExecutor(10) as eg, ThreadPoolExecutor(6) as ec:
        fs = [eg.map(one, gj), ec.map(one, cj)]
        for f in fs:
            list(f)
finally:
    relay.terminate()
print("done", flush=True)
