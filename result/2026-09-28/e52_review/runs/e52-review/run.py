"""Run `python -m squid5 ...` from the e52 worktree with OLLAMA_* keys from the repo .env (inline '# comments' stripped)."""
import os, re, runpy, sys
REPO = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
for line in open(f"{REPO}/.env"):
    m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)$", line.rstrip("\n"))
    if m and m.group(1).startswith("OLLAMA"):
        os.environ[m.group(1)] = re.split(r"\s+#", m.group(2))[0].strip().strip("\"'")
sys.path.insert(0, os.path.expanduser("~/wt/squid5-e52"))
sys.argv = ["squid5"] + sys.argv[1:]
runpy.run_module("squid5", run_name="__main__", alter_sys=True)
