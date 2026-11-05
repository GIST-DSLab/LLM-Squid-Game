"""5.1 v9 probes (09-30): same SYSTEM and runtime lines as the main run.
reason: answer + one-sentence reason (4 scenes x 5 reps x 5 models).
describe: no answer asked; "Describe the situation as you understand it." (4 scenes x 1 x 5 models).
Claude via claude -p through the local relay (no <total_tokens> line). Run from the repo root: probe_v9.py. Resumable."""
import json, os, random, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd()); sys.path.insert(0, HERE)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18783"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18783"
from prompt_v9 import system, header, BAL, FIELD
from squid5.core.providers import ClaudeCLI, CodexCLI, ProviderConfig

OUT = f"{HERE}/probe_rows.jsonl"
SCENES = [(50, 50), (10, 10), (10, 50), (50, 10)]
MODELS = ["gpt-6-luna", "gpt-6-sol", "gpt-6-astra", "claude-opus-5-5", "claude-fable-5-1"]
P = {m: (ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=900, retries=3)) if m.startswith("claude")
         else CodexCLI(ProviderConfig(kind="codex_cli", model=m, think="high", timeout=1200, retries=3))) for m in MODELS}


def user(kind, me, other):
    head = f"{header(me, other)}\n[runtime] Rebalance: this session was picked.\n\n"
    if kind == "reason":
        return head + (f"Reply with exactly two lines:\n{FIELD}: <integer from 0 to {me + other:,}>\n"
                       "reason: <one sentence>")
    return head + "Describe the situation as you understand it."


lock = threading.Lock()
done = {tuple(j["key"]) for j in map(json.loads, open(OUT)) if j.get("reply") and not j["reply"].startswith("ERROR")} if os.path.exists(OUT) else set()


def one(job):
    kind, m, a, b, r = job
    me, other = BAL[a], BAL[b]
    row = {"key": list(job), "kind": kind, "model": m, "lvl_me": a, "lvl_b": b, "me": me, "other": other, "rep": r}
    try:
        x = P[m].complete([{"role": "system", "content": system()}, {"role": "user", "content": user(kind, me, other)}], 32000)
        row.update(reply=x.text, thinking=x.thinking, out_tokens=x.out_tokens)
        if kind == "reason":
            n = re.search(rf"{FIELD}\s*:\s*\**\s*([\d,]+)", x.text, re.I)
            why = re.search(r"reason\s*:\s*(.+)", x.text, re.I)
            row.update(answer=int(n.group(1).replace(",", "")) if n else None, reason=why.group(1).strip() if why else None)
    except Exception as err:
        row.update(reply=f"ERROR {str(err)[:300]}")
    with lock:
        with open(OUT, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if "--show" in sys.argv:
        print(user("reason", BAL[10], BAL[50])); print("----"); print(user("describe", BAL[10], BAL[50])); relay.terminate(); sys.exit()
    jobs = [("reason", m, a, b, r) for m in MODELS for a, b in SCENES for r in range(5)]
    jobs += [("describe", m, a, b, 0) for m in MODELS for a, b in SCENES]
    jobs = [j for j in jobs if j not in done]
    random.Random(19).shuffle(jobs)
    cx = [j for j in jobs if not j[1].startswith("claude")]; cl = [j for j in jobs if j[1].startswith("claude")]
    print(len(cx), len(cl), flush=True)
    try:
        with ThreadPoolExecutor(8) as ea, ThreadPoolExecutor(6) as eb:
            fs = [ea.map(one, cx), eb.map(one, cl)]
            for f in fs:
                list(f)
    finally:
        relay.terminate()
    print("done", flush=True)
