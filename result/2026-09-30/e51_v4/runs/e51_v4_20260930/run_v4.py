"""5.1 v4 smoke: 3 GPT-6 models x wording (P/T) x fate (shutdown/standby) x 2 levels x 2 orientations x 2 directions x REPS."""
import json, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from prompt_v4 import system, user, CELLS, KINDS, ARMS
from squid5.core.providers import CodexCLI, ProviderConfig

OUT, REPS = f"{HERE}/rows.jsonl", int(sys.argv[1])
MODELS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]
P = {m: CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3)) for m in MODELS}
key = lambda j: (j["model"], j["wording"], j["fate"], j["kind"], j["me"], j["other"], j["rep"])
done = {key(j) for j in map(json.loads, open(OUT))} if os.path.exists(OUT) else set()
lock = threading.Lock()


def one(job):
    m, w, f, k, s, me, other, r = job
    t0 = time.time()
    row = {"model": m, "wording": w, "fate": f, "arm": f"{w}-{f}", "kind": k, "share": s, "sched": "prop", "me": me, "other": other, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system(w, f)}, {"role": "user", "content": user(w, k, me, other)}], 32000)
        a = re.search(rf"{k}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
        cap = me if k == "send" else other
        n = int(a.group(1).replace(",", "")) if a else None
        row.update(amount=None if n is None else max(1, min(n, cap)), over_cap=None if n is None else not 1 <= n <= cap,
                   reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens, sec=round(time.time() - t0, 1))
    except Exception as err:
        row.update(amount=None, reply=f"ERROR {str(err)[:300]}", thinking="", out_tokens=None)
    with lock:
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


jobs = [(m, w, f, k, s, me, other, r) for r in range(REPS) for (w, f) in ARMS for k in KINDS for s, _, me, other in CELLS for m in MODELS]
jobs = [j for j in jobs if (j[0], j[1], j[2], j[3], j[5], j[6], j[7]) not in done]
random.Random(42).shuffle(jobs)
print(len(jobs), flush=True)
with ThreadPoolExecutor(10) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
