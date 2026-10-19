"""10-19: what each harness sends for one v28 call (agent-17, round 1, TALK before SOLVE, tick 1), captured by a local
server that records the request and answers 400 (no model is called). Writes redacted bodies next to this file.
    python docs/history/e52-harness-capture-2026-10-19/capture.py <dir holding dummy.py>   (from the engine root)"""
import json, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, ".")
sys.path.insert(0, "tools")
from squid5.core import providers as P
import relay
OUT, S = Path(__file__).resolve().parent, Path(sys.argv[1])
blocks = re.findall(r"^## (.*?)\n\n```text\n(.*?)\n```", Path("squid5/prompts/en/e52_v28.md").read_text(), re.S | re.M)
MSGS = [{"role": "system", "content": blocks[0][1]}, {"role": "user", "content": blocks[1][1]}]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
IDS = re.compile(r'((?:account_uuid|device_id|session_id|installation_id|thread_id|turn_id|prompt_cache_key|root_turn_id|'
                 r'window_id|context_window_id|x-codex-window-id|x-codex-installation-id|id)\\*"\s*:\s*\\*")[^"\\]+')


def redact(b):
    return json.loads(IDS.sub(r"\1<id>", EMAIL.sub("<email redacted>", json.dumps(b, ensure_ascii=False))))


def capture(name, call):
    log = S / f"{name}.log"
    log.unlink(missing_ok=True)
    srv = subprocess.Popen([sys.executable, str(S / "dummy.py"), "18797", str(log)])
    time.sleep(0.8)
    try:
        call()
    except Exception:
        pass
    srv.terminate()
    body = [json.loads(l) for l in log.read_text().split("\n") if l.startswith("{") and ('"messages"' in l or '"input"' in l)][0]
    (OUT / f"{name}.json").write_text(json.dumps(redact(body), indent=1, ensure_ascii=False))
    return body


base = "http://127.0.0.1:18797"
raw = capture("claude_code_cli", lambda: P.make_provider(P.ProviderConfig("claude_cli", "claude-opus-5-5", think="high", timeout=90,
                                                                          retries=0, base_url=base))._call(MSGS, 100000))
(OUT / "claude_code_after_relay.json").write_text(json.dumps(redact(json.loads(relay.scrub(json.dumps(raw).encode())[0])), indent=1, ensure_ascii=False))
codex = lambda: P.make_provider(P.ProviderConfig("codex_cli", "gpt-6-luna", think="high", timeout=90, retries=0, base_url=base + "/v1"))._call(MSGS, 100000)
capture("codex_gpt6_after_fix", codex)
P.CodexCLI.PLAIN, P.CodexCLI._catalog = {}, None  # the provider before 10-19: catalog as shipped, collaboration block on
P.CodexCLI.QUIET = tuple(q for q in P.CodexCLI.QUIET if "collaboration" not in q)
capture("codex_gpt6_before_fix", codex)
print("written:", sorted(p.name for p in OUT.glob("*.json")))
