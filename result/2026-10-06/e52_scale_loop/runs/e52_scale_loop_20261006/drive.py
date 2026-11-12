"""Wait for running round, then alternate rounds until two consecutive ACCEPT: YES (cap)."""
import re, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).parent
import loop

def accepted(k):
    v = loop.verdict(loop.doc(k).read_text())
    return bool(re.search(r"ACCEPT:\s*\**\s*YES", v))

def last_round():
    ks = [int(re.match(r"r(\d+)_", p.name).group(1)) for p in (HERE/"rounds").glob("r*_*.md") if not p.name.endswith(".prompt.md")]
    return max(ks)

start, cap = int(sys.argv[1]), int(sys.argv[2])
while not list((HERE/"rounds").glob(f"r{start-1}_*.md")) or not any(not p.name.endswith(".prompt.md") for p in (HERE/"rounds").glob(f"r{start-1}_*.md")):
    time.sleep(20)
k = start
while k <= cap:
    if k >= start + 2 and accepted(k-1) and accepted(k-2):
        print(f"CONVERGED at round {k-1}"); break
    who = "fable" if k % 2 == 1 else "astra"
    r = subprocess.run([sys.executable, "loop.py", "round", str(k), who], cwd=HERE, capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-800:], flush=True)
    if r.returncode:
        print("FAILED", k); sys.exit(1)
    k += 1
else:
    print("CAP reached", "last accept:", accepted(cap))
k = last_round()
print("last", k, "accept", accepted(k), "prev accept", accepted(k-1))
