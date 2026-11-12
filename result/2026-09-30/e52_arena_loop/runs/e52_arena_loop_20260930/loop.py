"""One design turn: python loop.py <k> <astra|fable>
Prompt = brief + verdict history of rounds 1..k-1 + full doc of round k-1. Saves rounds/r<k>_<who>.md."""
import os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).parent
REPO = "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
NAMES = {"astra": "GPT-6 Astra", "fable": "Fable 5.1"}


def prev_rounds(k):
    out = []
    for i in range(1, k):
        f = next(p for p in HERE.glob(f"rounds/r{i}_*.md") if not p.name.endswith(".prompt.md"))
        out.append((i, f.stem.split("_")[1], f.read_text()))
    return out


def verdict(text):
    m = re.search(r"## E\. VERDICT(.*)$", text, re.S)
    return m.group(1).strip() if m else "(no verdict block)"


def build(k, who):
    parts = [(HERE / "brief.md").read_text(), f"\n\n# 이번 차례\n당신은 {NAMES[who]}이고 이번은 Round {k}이다."]
    rs = prev_rounds(k)
    if not rs:
        parts.append("첫 라운드다. A에는 현재 5.2에 대한 진단을 쓰고 첫 설계를 제안한다.")
    else:
        parts.append("\n## 지난 라운드들의 VERDICT (루프 기록)\n")
        for i, w, t in rs:
            parts.append(f"### Round {i} ({NAMES[w]})\n{verdict(t)}\n")
        i, w, t = rs[-1]
        parts.append(f"\n## 받은 설계: Round {i} ({NAMES[w]}) 전문\n\n{t}\n")
        parts.append("위 설계를 검토하고(A), 형식대로 개선된 완결 설계를 내라.")
    return "\n".join(parts)


def call(who, prompt, out):
    if who == "astra":
        cmd = ["codex", "exec", "-m", "gpt-6-astra", "-c", "model_reasoning_effort=high", "-s", "read-only",
               "--skip-git-repo-check", "-C", REPO, "-o", str(out), "-"]
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=3600)
        (out.with_suffix(".log")).write_text(p.stdout[-20000:] + "\n--- stderr ---\n" + p.stderr[-5000:])
        if p.returncode or not out.exists():
            raise SystemExit(f"codex exit {p.returncode}: {p.stderr[-800:]}")
    else:
        cmd = ["claude", "-p", "--model", "claude-fable-5-1", "--effort", "high", "--output-format", "text",
               "--allowedTools", "Read,Grep,Glob"]
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=3600, cwd=REPO, env=env)
        (out.with_suffix(".log")).write_text("--- stderr ---\n" + p.stderr[-5000:])
        if p.returncode or not p.stdout.strip():
            raise SystemExit(f"claude exit {p.returncode}: {p.stderr[-800:]}")
        out.write_text(p.stdout)


if __name__ == "__main__":
    k, who = int(sys.argv[1]), sys.argv[2]
    prompt = build(k, who)
    (HERE / f"rounds/r{k}_{who}.prompt.md").write_text(prompt)
    t = time.time()
    out = HERE / f"rounds/r{k}_{who}.md"
    call(who, prompt, out)
    print(f"round {k} {who} done in {time.time() - t:.0f}s, {len(out.read_text())} chars")
    print(verdict(out.read_text()))
