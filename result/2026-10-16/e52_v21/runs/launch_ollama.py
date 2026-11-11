"""Run one squid5 config with every OLLAMA_API_KEY* taken from the repo .env (inline # comments stripped; nothing printed)."""
import os, subprocess, sys
ENV = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/.env"
for line in open(ENV):
    line = line.strip().removeprefix("export ")
    if line.startswith("OLLAMA_API_KEY"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
assert all(os.environ.get(k) for k in ("OLLAMA_API_KEY", "OLLAMA_API_KEY2", "OLLAMA_API_KEY3")), "an Ollama key is missing in .env"
sys.exit(subprocess.call([sys.executable, "-m", "squid5", "run", sys.argv[1]], cwd=os.path.expanduser("~/wt/squid5-e52")))
