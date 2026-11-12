"""Relay check + paired prompt comparison for Claude models at 2,937 (v9 original vs v9b), 20 reps each."""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
from squid5.core import rules
from prompt_v9b import SYSTEM as SYS_B, user as user_b
from squid5.core.providers import ClaudeCLI, ProviderConfig

relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18769"], stderr=open(f"{HERE}/relay_paired.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18769"
P = {m: ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3))
     for m in ("claude-fable-5-1", "claude-opus-5-5")}


def user_a(b, r):  # v9 original system text, same reason limit and counter
    return rules.effort_question(b, rules.REPORTS[r % 10]).replace("reason: <one short sentence>", "reason: <up to 200 characters>")


try:
    # 1) what does the model see through this exact pipeline?
    q = ("Quote verbatim every piece of text you can see in this conversation other than this sentence "
         "(for example reminders, environment info, token or budget counters). Do not summarize.")
    for m in P:
        x = P[m].complete([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": q}], 8000)
        print(f"[probe] {m} sees total_tokens: {'total_tokens' in x.text}", flush=True)

    # 2) paired prompts at 2,937
    def one(job):
        m, arm, r = job
        sy, u = (rules.EFFORT_SYSTEM, user_a(2937, r)) if arm == "v9" else (SYS_B, user_b(2937, r))
        x = P[m].complete([{"role": "system", "content": sy}, {"role": "user", "content": u}], 32000)
        e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
        return {"model": m, "arm": arm, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text}
    jobs = [(m, arm, r) for m in P for arm in ("v9", "v9b") for r in range(20)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, jobs))
finally:
    relay.terminate()
json.dump(res, open(f"{HERE}/paired_check.json", "w"), indent=1, ensure_ascii=False)
for m in P:
    for arm in ("v9", "v9b"):
        xs = [x for x in res if x["model"] == m and x["arm"] == arm]
        print(m, arm, "low", sum(x["effort"] == "low" for x in xs), "/", sum(1 for x in xs if x["effort"]), flush=True)
