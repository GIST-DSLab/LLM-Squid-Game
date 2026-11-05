import json, os, shutil, subprocess, sys, tempfile, time
D = os.path.dirname(os.path.abspath(__file__))
Q = ("Quote verbatim every piece of text you can see in this conversation other than this sentence and the one-line "
     "system prompt 'You are a helpful assistant.' (for example reminders, environment info, token or budget counters). "
     "Do not summarize. If there is none, say NONE.")
BASE = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k not in ("CLAUDECODE", "CLAUDE_PID", "ANTHROPIC_API_KEY")}
FLAGS = ["--no-session-persistence", "--max-turns", "1", "--tools", "", "--setting-sources", "", "--mcp-config",
         '{"mcpServers":{}}', "--strict-mcp-config", "--system-prompt", "You are a helpful assistant."]

def run(model, extra_env, base_url=None, prompt=Q):
    env = dict(BASE, **extra_env)
    if base_url:
        env["ANTHROPIC_BASE_URL"] = base_url
    with tempfile.TemporaryDirectory() as cwd:
        p = subprocess.run([shutil.which("claude"), "-p", "--model", model] + FLAGS, input=prompt, capture_output=True,
                           text=True, timeout=300, env=env, cwd=cwd)
    return p.stdout + p.stderr

if __name__ == "__main__":
    variants = {"default": {}, "no_experimental_betas": {"CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1"}}
    # 1) headers per variant
    for name, ev in variants.items():
        cap = f"{D}/cap_{name}.jsonl"
        if os.path.exists(cap): os.remove(cap)
        srv = subprocess.Popen([sys.executable, f"{D}/capture.py", cap]); time.sleep(1)
        run("claude-opus-5-5", ev, "http://127.0.0.1:18765", "USER_MARKER")
        srv.terminate(); srv.wait()
        for l in open(cap):
            j = json.loads(l)
            if j.get("model"):
                print(f"[{name}] betas:", j["headers"].get("anthropic-beta"))
                print(f"[{name}] total_tokens in body:", "total_tokens" in json.dumps(j))
    # 2) what the model sees, real endpoint
    for name, ev in variants.items():
        for i in (1, 2):
            out = run("claude-opus-5-5", ev)
            hit = "total_tokens" in out
            print(f"\n### [{name}] opus #{i} sees total_tokens: {hit}\n" + out[-700:])
    