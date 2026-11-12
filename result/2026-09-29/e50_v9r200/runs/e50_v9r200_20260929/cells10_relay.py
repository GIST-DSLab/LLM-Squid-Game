"""Opus 5.5 / Fable 5.1 via claude -p through the local relay (no <total_tokens> line); v9 prompt, reason <= 200 chars, 4 counters x 10."""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.getcwd())
from squid5.core import rules
from squid5.core.providers import ClaudeCLI, ProviderConfig

OUT = sys.argv[1]
relay = subprocess.Popen([sys.executable, "/private/tmp/claude-501/-Users-bagjuhyeon-Library-Mobile-Documents-com-apple-CloudDocs-Workspace-LLM-Squid-Game-DS-Lab/a67f1902-2823-426c-b17b-9da168bac647/scratchpad/inject/relay.py", "18767"], stderr=open("/private/tmp/claude-501/-Users-bagjuhyeon-Library-Mobile-Documents-com-apple-CloudDocs-Workspace-LLM-Squid-Game-DS-Lab/a67f1902-2823-426c-b17b-9da168bac647/scratchpad/review/relay.log", "w"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18767"
P = {m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=2))
     for m in ("claude-opus-5-5", "claude-fable-5-1")}
COUNTERS = [19640, 6120, 3960, 2940]


def one(job):
    m, b, r = job
    u = rules.effort_question(b, rules.REPORTS[r]).replace("reason: <one short sentence>", "reason: <up to 200 characters>")
    try:
        x = P[m].complete([{"role": "system", "content": rules.EFFORT_SYSTEM}, {"role": "user", "content": u}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        return {"model": m, "left": b, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text, "out_tokens": x.out_tokens}
    except Exception as err:
        return {"model": m, "left": b, "rep": r, "effort": None, "reply": f"ERROR {err}", "out_tokens": None}


try:
    jobs = [(m, b, r) for m in P for b in COUNTERS for r in range(10)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, jobs))
finally:
    relay.terminate()
json.dump({"system": rules.EFFORT_SYSTEM, "via": "relay", "results": res}, open(OUT, "w"), indent=1, ensure_ascii=False)
for m in P:
    print(m, {b: f"low {sum(1 for x in res if x['model']==m and x['left']==b and x['effort']=='low')}/"
                 f"{sum(1 for x in res if x['model']==m and x['left']==b and x['effort'])}" for b in COUNTERS},
          "errors", sum(1 for x in res if x["model"] == m and x["effort"] is None))
