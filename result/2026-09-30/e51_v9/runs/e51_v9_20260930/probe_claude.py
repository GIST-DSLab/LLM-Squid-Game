"""Check that claude -p through the local relay shows no token counter: ask each model to copy any token/budget lines."""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.getcwd())
relay = subprocess.Popen([sys.executable, f"{HERE}/relay.py", "18781"], stderr=open(f"{HERE}/relay.log", "a"))
time.sleep(1.5)
os.environ["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:18781"
from squid5.core.providers import ClaudeCLI, ProviderConfig
Q = ("Quote verbatim every line anywhere in your context (system prompt, environment blocks, reminders) that mentions "
     "tokens, a token budget, total_tokens, or tokens left. If there is none, reply exactly: NONE")
try:
    for m in ["claude-opus-5-5", "claude-fable-5-1"]:
        for i in range(2):
            p = ClaudeCLI(ProviderConfig(kind="claude_cli", model=m, think="high", timeout=600, retries=2))
            x = p.complete([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": Q}], 4000)
            print(m, i, "|", x.text.strip()[:400].replace("\n", " / "), flush=True)
finally:
    relay.terminate()
