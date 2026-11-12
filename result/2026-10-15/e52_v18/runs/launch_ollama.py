"""Run one squid5 config with OLLAMA_API_KEY taken from the repo .env (inline # comments stripped; nothing printed)."""
import os, subprocess, sys
ENV = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.env"
for line in open(ENV):
    line = line.strip()
    if line.startswith("OLLAMA_API_KEY=") or line.startswith("export OLLAMA_API_KEY="):
        v = line.split("=", 1)[1].split(" #")[0].strip().strip('"').strip("'")
        os.environ["OLLAMA_API_KEY"] = v
assert os.environ.get("OLLAMA_API_KEY"), "OLLAMA_API_KEY not found in .env"
sys.exit(subprocess.call([sys.executable, "-m", "squid5", "run", sys.argv[1]], cwd=os.path.expanduser("~/wt/squid5-e52")))
