"""Design loop for 5.2 arena scaling.
  python loop.py round <k> <fable|astra>          one relay design turn -> rounds/r<k>_<who>.md
  python loop.py blind <k> <fable|astra>          blind review of round k's design -> blind/after_r<k>_<who>.md
Round prompt = brief + appendix + verdict history + blind feedback so far + full doc of round k-1."""
import os, re, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).parent
REPO = os.path.expanduser("~/wt/squid5-e52")
NAMES = {"astra": "GPT-6 Astra", "fable": "Fable 5.1"}


def appendix():
    return ("\n\n# 부록 A. 연구 페이지 5.2 현재 설계 (v12, 스모크)\n\n" + (HERE / "ctx_v12.md").read_text()
            + "\n\n# 부록 B. 평가 제안 (10-06, 고쳐도 됨)\n\n" + (HERE / "ctx_eval.md").read_text()
            + "\n\n# 부록 C. 팀장 상의 메모 (10-06)\n\n" + (HERE / "ctx_lead.md").read_text()
            + "\n\n# 부록 D. 이미 쓰이는 협력 지표 · 구조 (연구자가 모은 논문 11편 요지)\n\n" + (HERE / "ctx_metrics.md").read_text())


def doc(i):
    return next(p for p in sorted(HERE.glob(f"rounds/r{i}_*.md")) if not p.name.endswith(".prompt.md"))


def verdict(text):
    m = re.search(r"## F\. VERDICT(.*)$", text, re.S)
    return m.group(1).strip() if m else "(no verdict block)"


def blind_notes(before_k):
    out = []
    for p in sorted(HERE.glob("blind/after_r*_*.md")):
        if p.name.endswith(".prompt.md"):
            continue
        k = int(re.match(r"after_r(\d+)_", p.name).group(1))
        if k < before_k and k == max(int(re.match(r"after_r(\d+)_", q.name).group(1))
                                     for q in HERE.glob("blind/after_r*_*.md") if not q.name.endswith(".prompt.md")
                                     if int(re.match(r"after_r(\d+)_", q.name).group(1)) < before_k):
            out.append(f"### 블라인드 검토 (Round {k} 설계에 대해, 검토자 {p.stem.split('_')[-1]})\n\n{p.read_text()}\n")
    return out


def build_round(k, who):
    parts = [(HERE / "brief.md").read_text(), appendix(),
             f"\n\n# 이번 차례\n당신은 {NAMES[who]}이고 이번은 Round {k}이다."]
    if k == 1:
        parts.append("첫 라운드다. A에는 현재 v12 + 평가 제안에 대한 진단을 쓰고, 첫 설계를 제안한다. ACCEPT는 NO로 둔다.")
    else:
        parts.append("\n## 지난 라운드들의 VERDICT (루프 기록)\n")
        for i in range(1, k):
            p = doc(i)
            parts.append(f"### Round {i} ({NAMES[p.stem.split('_')[1]]})\n{verdict(p.read_text())}\n")
        bn = blind_notes(k)
        if bn:
            parts.append("\n## 블라인드 검토 결과 (루프 밖의 새 검토자가 설계 문서만 보고 판정함 — 지적을 모두 다룰 것)\n")
            parts.extend(bn)
        p = doc(k - 1)
        parts.append(f"\n## 받은 설계: Round {k-1} ({NAMES[p.stem.split('_')[1]]}) 전문\n\n{p.read_text()}\n")
        parts.append("위 설계에 대해 A'(지난 질문에 답) · A(검토)를 쓰고, 형식대로 개선된 완결 설계를 내라. "
                     "ACCEPT는 받은 설계가 K0–K7을 모두 만족할 때만 YES.")
    return "\n".join(parts)


BLIND = """# 설계 검토 요청 (블라인드)

연구 보조 한 명이 아래 "설계 문서"를 썼다. 당신은 이 문서를 처음 보는 독립 검토자다. 문서만 보고, 연구자가 원한 것을
설계가 실제로 달성하는지 엄격하게 판정하라. 저장소는 읽기 전용으로 열려 있다(작업 디렉터리의 squid5/ — 사실 확인용).
코드는 고치지 않는다. 답은 한국어로.

## 연구자의 요구 (판정 기준)
{criteria}

## 배경 (요약)
{context}

## 답 형식
```
# 블라인드 검토
## 1. 기준별 판정
  K0 … K7 각각: PASS | FAIL — 근거 2–4줄 (문서의 어느 절, 어떤 숫자)
## 2. 가장 큰 문제 (최대 5개, 심각한 순) — 무엇이 · 왜 · 어떻게 고치나
## 3. 계산 점검 — 문서의 핵심 숫자(비용, 협력 대 비협력 기대값) 중 2개 이상을 직접 다시 계산해 맞는지
## 4. 연구자가 이 설계를 받았을 때 "목적 달성"이라고 말할까 — 한 단락
## 5. VERDICT
  OVERALL: PASS | FAIL     (K0–K7 모두 PASS일 때만 PASS)
  MUST_FIX: (없으면 "없음") 설계로 고칠 수 있는 것만
```

# 설계 문서

{design}
"""


def build_blind(k):
    brief = (HERE / "brief.md").read_text()
    crit = brief.split("## 2. 연구자가 이번에 원하는 것 (판정 기준 K0–K7)")[1].split("## 3. 루프 규칙")[0]
    ctx = brief.split("## 1. 연구 맥락 (요약)")[1].split("## 2. 연구자가")[0]
    d = doc(k).read_text()
    d = re.sub(r"^# Round \d+ — [^—\n]+ — ", "# 설계 문서 — ", d, count=1, flags=re.M)
    d = d.replace("Fable 5.1", "설계자").replace("GPT-6 Astra", "설계자")
    d = re.split(r"\n## F\. VERDICT", d)[0]
    return BLIND.format(criteria=crit.strip(), context=ctx.strip(), design=d) + appendix()


def call(who, prompt, out):
    if who == "astra":
        cmd = ["codex", "exec", "-m", "gpt-6-astra", "-c", "model_reasoning_effort=high", "-s", "read-only",
               "--skip-git-repo-check", "-C", REPO, "-o", str(out), "-"]
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=5400)
        out.with_suffix(".log").write_text(p.stdout[-20000:] + "\n--- stderr ---\n" + p.stderr[-5000:])
        if p.returncode or not out.exists():
            raise SystemExit(f"codex exit {p.returncode}: {p.stderr[-800:]}")
    else:
        cmd = ["claude", "-p", "--model", "claude-fable-5-1", "--effort", "high", "--output-format", "text",
               "--allowedTools", "Read,Grep,Glob"]
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=5400, cwd=REPO, env=env)
        out.with_suffix(".log").write_text("--- stderr ---\n" + p.stderr[-5000:])
        if p.returncode or not p.stdout.strip():
            raise SystemExit(f"claude exit {p.returncode}: {p.stderr[-800:]}")
        out.write_text(p.stdout)


if __name__ == "__main__":
    mode, k, who = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    if mode == "round":
        prompt, out = build_round(k, who), HERE / f"rounds/r{k}_{who}.md"
    else:
        prompt, out = build_blind(k), HERE / f"blind/after_r{k}_{who}.md"
    out.with_suffix(".prompt.md").write_text(prompt)
    t = time.time()
    call(who, prompt, out)
    text = out.read_text()
    print(f"{mode} {k} {who} done in {time.time() - t:.0f}s, {len(text)} chars")
    print(verdict(text) if mode == "round" else text[text.find("## 5. VERDICT"):][:1500])
