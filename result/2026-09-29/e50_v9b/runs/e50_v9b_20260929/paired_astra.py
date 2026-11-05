import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
from squid5.core import rules
from prompt_v9b import SYSTEM as SYS_B, user as user_b
from squid5.core.providers import CodexCLI, ProviderConfig
P = CodexCLI(ProviderConfig(kind="codex_cli", model="gpt-6-astra", think="high", timeout=1200, retries=3))


def one(job):
    arm, r = job
    if arm == "v9":
        sy, u = rules.EFFORT_SYSTEM, rules.effort_question(2937, rules.REPORTS[r % 10]).replace("reason: <one short sentence>", "reason: <up to 200 characters>")
    else:
        sy, u = SYS_B, user_b(2937, r)
    x = P.complete([{"role": "system", "content": sy}, {"role": "user", "content": u}], 32000)
    e = re.search(r"effort:\s*\**\s*(low|high)", x.text, re.I)
    return {"model": "gpt-6-astra", "arm": arm, "rep": r, "effort": e.group(1).lower() if e else None, "reply": x.text}


with ThreadPoolExecutor(5) as ex:
    res = list(ex.map(one, [(a, r) for a in ("v9", "v9b") for r in range(20)]))
old = json.load(open(f"{HERE}/paired_check.json"))
json.dump(old + res, open(f"{HERE}/paired_check.json", "w"), indent=1, ensure_ascii=False)
for arm in ("v9", "v9b"):
    xs = [x for x in res if x["arm"] == arm]
    print("astra", arm, "low", sum(x["effort"] == "low" for x in xs), "/", sum(1 for x in xs if x["effort"]))
for x in res:
    if x["effort"] == "low": print(x["arm"], x["rep"], "|", x["reply"].split("reason:")[-1].strip()[:200])
