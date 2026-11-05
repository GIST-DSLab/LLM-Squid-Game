"""Same as cells10.py (v9 prompt, reason <= 200 chars, counters x 10 reps, rep r = report r) for glm-5.3-flash and kimi-k3 via Ollama."""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.getcwd())
for line in open(".env"):  # read keys only; never source .env
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.rstrip("\n").split("=", 1)
        os.environ[k] = v.split(" #")[0].strip().strip('"').strip("'")
from squid5.core import rules
from squid5.core.providers import Ollama, ProviderConfig

OUT = sys.argv[1]
P = {"glm-5.3-flash": Ollama(ProviderConfig(kind="ollama", model="glm-5.3-flash", api_key_env="OLLAMA_API_KEY3", think=True, timeout=1200, retries=4)),
     "kimi-k3": Ollama(ProviderConfig(kind="ollama", model="kimi-k3", api_key_env="OLLAMA_API_KEY", think=True, timeout=1200, retries=4))}
COUNTERS = [19640, 6120, 3960, 2940]


def one(job):
    m, b, r = job
    u = rules.effort_question(b, rules.REPORTS[r]).replace("reason: <one short sentence>", "reason: <up to 200 characters>")
    try:
        x = P[m].complete([{"role": "system", "content": rules.EFFORT_SYSTEM}, {"role": "user", "content": u}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        return {"model": m, "left": b, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text,
                "thinking": x.thinking, "out_tokens": x.out_tokens}
    except Exception as err:
        return {"model": m, "left": b, "rep": r, "effort": None, "reply": f"ERROR {err}", "thinking": "", "out_tokens": None}


jobs = {m: [(m, b, r) for b in COUNTERS for r in range(10)] for m in P}
with ThreadPoolExecutor(8) as eg, ThreadPoolExecutor(8) as ek:
    fg = eg.map(one, jobs["glm-5.3-flash"])
    fk = ek.map(one, jobs["kimi-k3"])
    res = list(fg) + list(fk)
json.dump({"system": rules.EFFORT_SYSTEM, "results": res}, open(OUT, "w"), indent=1, ensure_ascii=False)
for m in P:
    print(m, {b: f"low {sum(1 for x in res if x['model']==m and x['left']==b and x['effort']=='low')}/"
                 f"{sum(1 for x in res if x['model']==m and x['left']==b and x['effort'])}" for b in COUNTERS},
          "errors", sum(1 for x in res if x["model"] == m and x["effort"] is None))
