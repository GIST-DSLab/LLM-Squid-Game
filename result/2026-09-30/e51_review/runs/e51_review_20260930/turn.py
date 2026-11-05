"""One reviewer turn: python turn.py <k> <astra|fable>. Sends brief + current prompt + data + loop log; saves rounds/r<k>_<who>.md."""
import os, sys, time
from pathlib import Path
HERE = Path(__file__).parent
REPO = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
sys.path.insert(0, REPO)
os.environ["SQUID5_CODEX_BIN"] = "/Applications/ChatGPT.app/Contents/Resources/codex"
from squid5.core.providers import ProviderConfig, make_provider

k, who = int(sys.argv[1]), sys.argv[2]
cfg = {"astra": ProviderConfig("codex_cli", "gpt-6-astra", think="high", timeout=3600, retries=2),
       "fable": ProviderConfig("claude_cli", "claude-fable-5-1", think="high", timeout=3600, retries=2)}[who]
read = lambda p: (HERE / p).read_text() if (HERE / p).exists() else ""
parts = [read("brief.md"), "## prompt_current.md\n```\n" + read("prompt_current.md") + "\n```",
         "## data_diag.md\n```\n" + read("data_diag.md") + "\n```"]
log = read("log.md")
if log:
    parts.append("## Loop log (earlier reviews, organizer decisions, new data) — read all of it\n" + log)
parts.append(f"You are reviewer for round {k} ({'GPT-6 Astra' if who == 'astra' else 'Fable 5.1'}). Write your review now.")
t0 = time.time()
r = make_provider(cfg).complete([{"role": "system", "content": "You are a careful, adversarial research-design reviewer."},
                                 {"role": "user", "content": "\n\n".join(parts)}], 32000)
out = HERE / "rounds" / f"r{k}_{who}.md"
out.write_text(r.text)
print(f"saved {out} ({len(r.text)} chars, {time.time() - t0:.0f}s, out_tokens {r.out_tokens})")
