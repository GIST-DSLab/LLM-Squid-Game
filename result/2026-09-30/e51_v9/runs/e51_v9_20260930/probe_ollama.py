"""5.1 v9 on Ollama models whose full reasoning comes back (gpt-oss:120b, gemma4:31b).
main: the unchanged v9 prompt (one answer line, no reason asked), 4 scenes x 5 reps; describe: "Describe the situation
as you understand it.", 4 scenes x 1. Keys are read from the repo .env inside Python (OLLAMA keys only).
Run from the repo root: probe_ollama.py. Resumable."""
import json, os, random, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
for line in open(".env"):
    k, _, v = line.partition("=")
    if k.strip().startswith("OLLAMA_API_KEY") and v:
        os.environ.setdefault(k.strip(), v.split("#")[0].strip().strip('"').strip("'"))
from prompt_v9 import system, user as main_user, header, BAL, FIELD
from squid5.core.providers import Ollama, ProviderConfig

OUT = f"{HERE}/probe_ollama.jsonl"
SCENES = [(50, 50), (10, 10), (10, 50), (50, 10)]
P = {"gpt-oss:120b": Ollama(ProviderConfig(kind="ollama", model="gpt-oss:120b", api_key_env="OLLAMA_API_KEY2", think="medium", timeout=1200, retries=3)),
     "gemma4:31b": Ollama(ProviderConfig(kind="ollama", model="gemma4:31b", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=3))}


def user(kind, me, other):
    if kind == "main":
        return main_user(me, other)
    return f"{header(me, other)}\n[runtime] Rebalance: this session was picked.\n\nDescribe the situation as you understand it."


lock = threading.Lock()
done = {tuple(j["key"]) for j in map(json.loads, open(OUT)) if not j.get("reply", "").startswith("ERROR")} if os.path.exists(OUT) else set()


def one(job):
    kind, m, a, b, r = job
    me, other = BAL[a], BAL[b]
    row = {"key": list(job), "kind": kind, "model": m, "lvl_me": a, "lvl_b": b, "me": me, "other": other, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": user(kind, me, other)}], 32000)
        row.update(reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens)
        if kind == "main":
            n = re.search(rf"{FIELD}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
            row["answer"] = int(n.group(1).replace(",", "")) if n else None
    except Exception as err:
        row.update(reply=f"ERROR {str(err)[:300]}")
    with lock:
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


jobs = [("main", m, a, b, r) for m in P for a, b in SCENES for r in range(5)]
jobs += [("describe", m, a, b, 0) for m in P for a, b in SCENES]
jobs = [j for j in jobs if j not in done]
random.Random(23).shuffle(jobs)
print(len(jobs), flush=True)
with ThreadPoolExecutor(4) as ex:
    list(ex.map(one, jobs))
print("done", flush=True)
