import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import run
D = os.path.dirname(os.path.abspath(__file__))
srv = subprocess.Popen([sys.executable, f"{D}/relay.py", "18766"]); time.sleep(1.5)
try:
    for m in ("claude-opus-5-5", "claude-fable-5-1"):
        for i in (1, 2):
            out = run(m, {}, "http://127.0.0.1:18766")
            print(f"\n### {m} via relay #{i} sees total_tokens: {'total_tokens' in out}\n" + out[-600:])
finally:
    srv.terminate()
