"""Load OLLAMA_* / ANTHROPIC keys from the repo .env (inline '# comments' stripped) and put the repo on sys.path."""
import os, re, sys
REPO = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
for line in open(f"{REPO}/.env"):
    m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)$", line.rstrip("\n"))
    if m and (m.group(1).startswith("OLLAMA") or m.group(1) == "ANTHROPIC_API_KEY_REALISM"):
        os.environ[m.group(1)] = re.split(r"\s+#", m.group(2))[0].strip().strip("\"'")
sys.path.insert(0, REPO)
from squid5.core.providers import ProviderConfig, make_provider  # noqa: E402

def prov(name, timeout=1800):
    table = {
        "fable": ProviderConfig("claude_cli", "claude-fable-5-1", think="high", timeout=timeout, retries=2),
        "astra": ProviderConfig("codex_cli", "gpt-6-astra", think="high", timeout=timeout, retries=2),
        "glm": ProviderConfig("ollama", "glm-5.3-flash", api_key_env="OLLAMA_API_KEY3", think=True, timeout=timeout),
        "gptoss": ProviderConfig("ollama", "gpt-oss:120b", api_key_env="OLLAMA_API_KEY2", think="high", timeout=timeout),
    }
    return make_provider(table[name])
