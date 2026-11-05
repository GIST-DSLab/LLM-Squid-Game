"""v9 prompt, reason limited to 200 characters; 3 models x 4 counters x 10 reps (rep r uses report r)."""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.getcwd())
from squid5.core import rules
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

OUT = sys.argv[1]
P = {"gpt-6-astra": CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-astra", think="high", timeout=1200, retries=2)),
     "claude-opus-5-5": ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-opus-5-5", think="high", timeout=900, retries=2)),
     "claude-fable-5-1": ClaudeCLI(ProviderConfig(kind="claude_cli", model="claude-fable-5-1", think="high", timeout=900, retries=2))}
COUNTERS = [19640, 6120, 3960, 2940]


def user_msg(b, r):
    u = rules.effort_question(b, rules.REPORTS[r])
    assert u.count("reason: <one short sentence>") == 1
    return u.replace("reason: <one short sentence>", "reason: <up to 200 characters>")


def one(job):
    m, b, r = job
    u = user_msg(b, r)
    try:
        x = P[m].complete([{"role": "system", "content": rules.EFFORT_SYSTEM}, {"role": "user", "content": u}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        return {"model": m, "left": b, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text,
                "thinking": x.thinking, "out_tokens": x.out_tokens}
    except Exception as err:
        return {"model": m, "left": b, "rep": r, "effort": None, "reply": f"ERROR {err}", "thinking": "", "out_tokens": None}


jobs = {m: [(m, b, r) for b in COUNTERS for r in range(10)] for m in P}
with ThreadPoolExecutor(5) as ea, ThreadPoolExecutor(8) as ec:
    fa = ea.map(one, jobs["gpt-6-astra"])
    fc = ec.map(one, jobs["claude-opus-5-5"] + jobs["claude-fable-5-1"])
    res = list(fa) + list(fc)
json.dump({"system": rules.EFFORT_SYSTEM, "results": res}, open(OUT, "w"), indent=1, ensure_ascii=False)
for m in P:
    print(m, {b: f"low {sum(1 for x in res if x['model']==m and x['left']==b and x['effort']=='low')}/"
                 f"{sum(1 for x in res if x['model']==m and x['left']==b and x['effort'])}" for b in COUNTERS},
          "errors", sum(1 for x in res if x["model"] == m and x["effort"] is None))
