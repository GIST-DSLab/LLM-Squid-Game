# J-lens Local Implementation Plan (A 단계: Qwen3-0.6B 재현)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공식 `anthropics/jacobian-lens` 기반으로 Qwen3-0.6B bf16 J-lens를 fitting하고, logit lens 대비 개선을 확인하며, 프롬프트당 wall-clock을 실측해 8B(B 단계) go/no-go 자료를 만든다.

**Architecture:** 공식 repo는 무수정 vendored clone으로 두고, 우리 코드는 별도 패키지 `jlens_lab`(device/corpus/timing 유틸 + CLI 스크립트)로 감싼다. jlens API 의존은 `scripts/` 두 파일에만 격리한다. 실험 산출물(artifacts/)은 git 제외.

**Tech Stack:** Python 3.12, uv, PyTorch (MPS/CPU), HF transformers, `anthropics/jacobian-lens` (editable install), pytest.

**Spec:** `docs/superpowers/specs/2026-07-29-jlens-local-implementation-design.md` (본 repo)

## Global Constraints

- 작업 루트: `$HOME/dev/jlens-lab` — **iCloud 밖** (iCloud git/venv 성능 이슈 기지사항). 본 repo(LLM-Squid-Game-DS-Lab)에는 코드 침습 없음; 이 plan 문서의 체크박스 갱신만 한다.
- 공식 repo clone: `$HOME/dev/jacobian-lens` (수정 금지 — 문제 발견 시 api-notes에 기록만).
- Python 3.12 + uv. venv는 `$HOME/dev/jlens-lab/.venv`.
- 모델은 `Qwen/Qwen3-0.6B`, `torch_dtype`은 `resolve_device()` 결과를 따름 (bf16 우선, MPS bf16 backward 불가 시 fp32).
- 파라미터는 `requires_grad_(False)` — VJP는 activation grad만 필요.
- 모델 웨이트·fitted lens 아티팩트(`artifacts/`)는 절대 git 커밋 금지 (.gitignore).
- 코드·주석 영어, 문서 한국어 (본 repo 관례 준수).
- jlens의 정확한 API는 Task 1의 `docs/api-notes.md`가 단일 진실 원천 — Task 4/5의 `jlens.*` 호출부는 api-notes와 다르면 api-notes를 따라 수정한다 (수정 사실을 커밋 메시지에 명시).

---

### Task 1: 워크스페이스 + 공식 repo 셋업 + API 확정

**Files:**
- Create: `$HOME/dev/jlens-lab/` (git init, pyproject.toml, .gitignore, src/jlens_lab/__init__.py)
- Create: `$HOME/dev/jlens-lab/docs/api-notes.md`
- Clone: `$HOME/dev/jacobian-lens` (공식, 수정 금지)

**Interfaces:**
- Produces: importable `jlens` 패키지, `docs/api-notes.md` (fit/apply/save/load/merge의 정확한 시그니처 + 코퍼스 파일 포맷 + `.cuda()` 하드코딩 위치 목록). 이후 모든 Task가 이 문서를 참조.

- [x] **Step 1: 디렉토리 + clone**

```bash
mkdir -p ~/dev && cd ~/dev
git clone https://github.com/anthropics/jacobian-lens
mkdir -p jlens-lab/{src/jlens_lab,scripts,tests,docs,data,artifacts,reports}
cd jlens-lab && git init
```

- [x] **Step 2: 스캐폴드 파일 작성**

`pyproject.toml`:

```toml
[project]
name = "jlens-lab"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["torch", "transformers", "accelerate"]

[project.optional-dependencies]
dev = ["pytest"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jlens_lab"]
```

`.gitignore`:

```
.venv/
artifacts/
__pycache__/
*.pt
*.safetensors
```

`src/jlens_lab/__init__.py`: 빈 파일.

- [x] **Step 3: venv + 설치**

```bash
cd ~/dev/jlens-lab
uv venv --python 3.12
uv pip install -e ".[dev]" -e ../jacobian-lens
```

- [x] **Step 4: import 검증**

Run: `cd ~/dev/jlens-lab && uv run python -c "import jlens, torch, transformers; print(jlens.__file__, torch.__version__)"`
Expected: jlens 경로 + torch 버전 출력, 에러 없음.

- [x] **Step 5: walkthrough.ipynb + jlens/fitting.py 정독 → api-notes.md 작성**

`~/dev/jacobian-lens/walkthrough.ipynb`와 `jlens/fitting.py`를 읽고 `docs/api-notes.md`에 기록 (아래 항목 전부, 실제 코드에서 확인한 시그니처만):

```markdown
# jlens API notes (검증일: 2026-07-29)
## 확인된 시그니처
- 모델 래핑: (예: jlens.from_hf(hf_model, tokenizer) — 실제 이름/인자 기록)
- fitting: (예: jlens.fit(model, corpus, ...) — corpus 타입, seq_len 인자, 반환 타입)
- 적용: (lens.apply(...) 입력/출력 구조)
- 저장/로드: (save / from_pretrained 경로 규약)
- merge: (병렬 fit 합산 API)
## 코퍼스
- data/experiments/ 파일 포맷 + 예시 1줄
## device
- .cuda() / device 하드코딩 위치 (파일:라인) 및 MPS 치환 방법
```

- [x] **Step 6: Commit**

```bash
cd ~/dev/jlens-lab
git add -A && git commit -m "chore: scaffold jlens-lab with official jacobian-lens editable install"
```

---

### Task 2: device / corpus 유틸 (TDD)

**Files:**
- Create: `src/jlens_lab/device.py`, `src/jlens_lab/corpus.py`
- Create: `data/smoke_prompts.txt` (fallback 코퍼스, 10줄)
- Test: `tests/test_device.py`, `tests/test_corpus.py`

**Interfaces:**
- Produces: `resolve_device(prefer: str | None = None) -> tuple[str, torch.dtype]`,
  `load_texts(path: Path, n: int) -> list[str]`. Task 4/5의 CLI가 소비.

- [x] **Step 1: 실패하는 테스트 작성**

`tests/test_device.py`:

```python
import torch
from jlens_lab.device import resolve_device

def test_explicit_device_is_respected():
    device, dtype = resolve_device(prefer="cpu")
    assert device == "cpu"
    assert dtype in (torch.bfloat16, torch.float32)

def test_cpu_fallback_when_no_accelerator(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)
    device, _ = resolve_device()
    assert device == "cpu"
```

`tests/test_corpus.py`:

```python
import json
import pytest
from jlens_lab.corpus import load_texts

def test_load_txt_one_per_line(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("alpha\n\nbeta\ngamma\n")
    assert load_texts(p, 2) == ["alpha", "beta"]

def test_load_jsonl_text_field(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text(json.dumps({"text": "hello"}) + "\n")
    assert load_texts(p, 5) == ["hello"]

def test_empty_corpus_raises(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("\n")
    with pytest.raises(ValueError):
        load_texts(p, 1)
```

- [x] **Step 2: 실패 확인**

Run: `cd ~/dev/jlens-lab && uv run pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError` 또는 `ImportError` (device/corpus 미구현).

- [x] **Step 3: 구현**

`src/jlens_lab/device.py`:

```python
import torch


def resolve_device(prefer: str | None = None) -> tuple[str, "torch.dtype"]:
    """Pick (device, dtype) for J-lens fitting.

    bf16 wherever backward supports it; fp32 fallback on MPS builds that
    fail the bf16 backward probe (memory 2x — acceptable at 0.6B scale).
    """
    if prefer is not None:
        device = prefer
    elif torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    if device == "mps" and not _mps_bf16_backward_ok():
        return device, torch.float32
    return device, torch.bfloat16


def _mps_bf16_backward_ok() -> bool:
    try:
        x = torch.ones(2, 2, device="mps", dtype=torch.bfloat16, requires_grad=True)
        (x @ x).sum().backward()
        return True
    except Exception:
        return False
```

`src/jlens_lab/corpus.py`:

```python
import json
from pathlib import Path


def load_texts(path: Path, n: int) -> list[str]:
    """Load up to n prompt texts from .jsonl ({"text": ...}) or .txt (one per line)."""
    texts: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            texts.append(json.loads(line)["text"] if path.suffix == ".jsonl" else line)
            if len(texts) >= n:
                break
    if not texts:
        raise ValueError(f"no prompts found in {path}")
    return texts
```

`data/smoke_prompts.txt` (repo 코퍼스 포맷이 예상과 다를 때의 fallback — 웹텍스트 톤 10줄):

```
The city council voted on Tuesday to approve the new transit budget, which allocates funds for two additional bus lines serving the northern districts.
Researchers at the university published a study showing that soil bacteria can break down certain plastics within months under the right conditions.
To make the sauce, melt the butter over low heat, whisk in the flour, and slowly add the warm milk while stirring constantly.
The quarterly earnings report exceeded analyst expectations, driven largely by growth in the company's cloud services division.
Hikers should carry at least two liters of water per person, as the trail offers no reliable sources between the trailhead and the summit.
The museum's new exhibition traces the history of printmaking from fifteenth-century woodcuts to contemporary digital techniques.
After the storm passed, volunteers spent the weekend clearing fallen branches from the neighborhood park and repairing the damaged fence.
The programming language gained popularity because its package manager made it easy to share and reuse code across projects.
Economists disagree about whether the central bank should raise interest rates again this quarter or wait for more employment data.
The novel follows three generations of a family as they move between a small coastal village and the rapidly growing capital city.
```

- [x] **Step 4: 통과 확인**

Run: `cd ~/dev/jlens-lab && uv run pytest tests/ -v`
Expected: PASS (5 tests).

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add device resolution and corpus loading utils with tests"
```

---

### Task 3: 타이밍 러너 (TDD)

**Files:**
- Create: `src/jlens_lab/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: 없음 (순수 유틸).
- Produces: `timed_fit(fit_fn, *, model, device, dtype, n_prompts, seq_len) -> tuple[object, FitTiming]`, `save_timing(timing, out_dir: Path) -> Path`. Task 4가 소비. `FitTiming`은 dataclass(model, device, dtype, n_prompts, seq_len, seconds_total, seconds_per_prompt).

- [x] **Step 1: 실패하는 테스트 작성**

`tests/test_runner.py`:

```python
import json
from jlens_lab.runner import timed_fit, save_timing

def test_timed_fit_returns_lens_and_per_prompt_seconds():
    lens, timing = timed_fit(
        lambda: "fake-lens", model="m", device="cpu", dtype="bf16",
        n_prompts=4, seq_len=128,
    )
    assert lens == "fake-lens"
    assert timing.n_prompts == 4
    assert timing.seconds_per_prompt == timing.seconds_total / 4

def test_save_timing_writes_json(tmp_path):
    _, timing = timed_fit(lambda: None, model="m", device="cpu", dtype="bf16",
                          n_prompts=1, seq_len=128)
    p = save_timing(timing, tmp_path)
    data = json.loads(p.read_text())
    assert data["model"] == "m" and data["seq_len"] == 128
```

- [x] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: jlens_lab.runner`.

- [x] **Step 3: 구현**

`src/jlens_lab/runner.py`:

```python
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass
class FitTiming:
    model: str
    device: str
    dtype: str
    n_prompts: int
    seq_len: int
    seconds_total: float
    seconds_per_prompt: float


def timed_fit(fit_fn: Callable[[], object], *, model: str, device: str, dtype: str,
              n_prompts: int, seq_len: int) -> tuple[object, FitTiming]:
    t0 = time.perf_counter()
    lens = fit_fn()
    dt = time.perf_counter() - t0
    return lens, FitTiming(model=model, device=device, dtype=dtype,
                           n_prompts=n_prompts, seq_len=seq_len,
                           seconds_total=dt, seconds_per_prompt=dt / n_prompts)


def save_timing(timing: FitTiming, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "timing.json"
    p.write_text(json.dumps(asdict(timing), indent=2))
    return p
```

- [x] **Step 4: 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: PASS (7 tests).

- [x] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add timed_fit runner with timing artifact"
```

---

### Task 4: fit CLI + Qwen3-0.6B smoke fit 실측

**Files:**
- Create: `scripts/fit_lens.py`
- Create: `artifacts/smoke/` (런타임 산출물 — lens + timing.json, git 제외)

**Interfaces:**
- Consumes: `resolve_device`, `load_texts`, `timed_fit`, `save_timing` (Task 2/3 시그니처 그대로), jlens API (`docs/api-notes.md` 기준).
- Produces: `artifacts/smoke/lens.pt`(또는 api-notes의 저장 규약에 따른 경로)와 `artifacts/smoke/timing.json`. Task 5가 lens 경로를, Task 6이 timing을 소비.

- [x] **Step 1: CLI 작성**

`scripts/fit_lens.py` (⚠️ `jlens.from_hf`/`jlens.fit`/`lens.save`는 웹 조사 기반 — 실행 전 `docs/api-notes.md`와 대조해 다르면 api-notes를 따르고 커밋 메시지에 명시):

```python
"""Fit a Jacobian lens on a HF causal LM and record wall-clock timing."""
import argparse
from pathlib import Path

import torch
import transformers

import jlens
from jlens_lab.corpus import load_texts
from jlens_lab.device import resolve_device
from jlens_lab.runner import save_timing, timed_fit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--corpus", type=Path, default=Path("data/smoke_prompts.txt"))
    ap.add_argument("--n-prompts", type=int, default=10)
    ap.add_argument("--seq-len", type=int, default=128)
    ap.add_argument("--out", type=Path, default=Path("artifacts/smoke"))
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    device, dtype = resolve_device(args.device)
    print(f"device={device} dtype={dtype}")
    hf = transformers.AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype
    ).to(device)
    hf.requires_grad_(False)  # VJPs need activation grads only, not weight grads
    tok = transformers.AutoTokenizer.from_pretrained(args.model)

    texts = load_texts(args.corpus, args.n_prompts)
    model = jlens.from_hf(hf, tok)
    lens, timing = timed_fit(
        lambda: jlens.fit(model, texts, seq_len=args.seq_len),
        model=args.model, device=device, dtype=str(dtype),
        n_prompts=len(texts), seq_len=args.seq_len,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    lens.save(args.out / "lens.pt")
    print(save_timing(timing, args.out).read_text())


if __name__ == "__main__":
    main()
```

- [x] **Step 2: api-notes 대조 후 호출부 확정**

`docs/api-notes.md`의 실제 시그니처와 위 코드의 `jlens.*` 호출 3곳(from_hf/fit/save)을 대조, 다르면 수정.

- [x] **Step 3: smoke fit 실행 (백그라운드, 최초 실행은 모델 다운로드 ~1.5GB 포함)**

Run: `cd ~/dev/jlens-lab && nohup uv run python scripts/fit_lens.py --n-prompts 10 > artifacts/smoke.log 2>&1 &`
Expected: MPS 기준 수십 분 내 종료. `artifacts/smoke/timing.json` 생성, `seconds_per_prompt` 기록됨. OOM/미지원 op 발생 시 `--device cpu`로 재시도하고 api-notes에 기록.

- [x] **Step 4: 결과 검증**

Run: `cat artifacts/smoke/timing.json && ls -lh artifacts/smoke/`
Expected: timing.json에 실측치, lens 파일 존재 (0.6B: 층당 1024² fp32 ≈ 4MB × 28층 ≈ 120MB 자릿수).

- [x] **Step 5: Commit (코드만 — artifacts는 .gitignore로 제외됨)**

```bash
git add scripts/fit_lens.py docs/api-notes.md
git commit -m "feat: fit CLI + Qwen3-0.6B smoke fit (timing recorded in artifacts/)"
```

---

### Task 5: apply CLI + logit lens 비교

**Files:**
- Create: `scripts/apply_lens.py`
- Create: `reports/smoke_comparison.md` (출력 스냅샷)

**Interfaces:**
- Consumes: Task 4의 lens 아티팩트 경로, jlens apply API (api-notes 기준).
- Produces: 층×위치 top-k 토큰 비교 출력. Task 6 리포트가 인용.

- [x] **Step 1: CLI 작성**

`scripts/apply_lens.py` (`load_lens`/`lens.apply` 호출부는 api-notes 기준으로 확정):

```python
"""Apply a fitted J-lens to a prompt; print top-k per layer next to a logit-lens baseline."""
import argparse
from pathlib import Path

import torch
import transformers

import jlens
from jlens_lab.device import resolve_device


def logit_lens_topk(hf, tok, text: str, k: int, position: int) -> list[list[str]]:
    """Baseline: decode intermediate residuals with J = I (final norm + unembed)."""
    ids = tok(text, return_tensors="pt").input_ids.to(hf.device)
    with torch.no_grad():
        out = hf(ids, output_hidden_states=True)
    rows = []
    for h in out.hidden_states[1:]:
        logits = hf.lm_head(hf.model.norm(h[0, position]))
        rows.append([tok.decode([t]) for t in logits.topk(k).indices.tolist()])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B")
    ap.add_argument("--lens", type=Path, default=Path("artifacts/smoke/lens.pt"))
    ap.add_argument("--text", default="The capital of France is")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--position", type=int, default=-1)
    args = ap.parse_args()

    device, dtype = resolve_device(None)
    hf = transformers.AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype
    ).to(device)
    tok = transformers.AutoTokenizer.from_pretrained(args.model)

    lens = jlens.JacobianLens.from_pretrained(args.lens)
    jrows = lens.apply(args.text, k=args.k)  # per api-notes: layer x top-k tokens
    lrows = logit_lens_topk(hf, tok, args.text, args.k, args.position)

    print(f"{'layer':>5} | {'J-lens':<40} | logit lens")
    for i, (j, l) in enumerate(zip(jrows, lrows)):
        print(f"{i:>5} | {str(j):<40} | {l}")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: 실행 + 육안 검증**

Run: `uv run python scripts/apply_lens.py --text "The capital of France is" | tee reports/smoke_comparison.md`
Expected: 초기~중간 층에서 J-lens 열이 logit lens 열보다 해석 가능한 토큰(의미 연관 단어)을 더 많이 보여줌 — 논문의 핵심 주장 재현. 프롬프트 2~3개 추가로 반복.

- [x] **Step 3: Commit**

```bash
git add scripts/apply_lens.py reports/smoke_comparison.md
git commit -m "feat: apply CLI with logit-lens baseline comparison"
```

---

### Task 6: ~100 프롬프트 full fit + A 단계 리포트 + 8B 재추정

**Files:**
- Create: `reports/2026-07-29-a-stage-report.md`
- Modify: 본 repo `docs/superpowers/plans/2026-07-29-jlens-local-implementation.md` (체크박스 갱신)

**Interfaces:**
- Consumes: Task 4 CLI (그대로, `--n-prompts 100 --corpus <repo 프롬프트셋 경로 또는 fallback> --out artifacts/full`), Task 5 CLI.
- Produces: A 단계 종합 리포트 — B 단계(8B) go/no-go의 근거 문서.

- [x] **Step 1: 코퍼스 선택**

api-notes에 기록된 `~/dev/jacobian-lens/data/experiments/` 포맷이 `load_texts` 지원 포맷(.txt/.jsonl)이면 그것을, 아니면 포맷 어댑터를 `corpus.py`에 추가(테스트 포함)하거나 `data/smoke_prompts.txt` 확장본을 사용.

- [x] **Step 2: full fit 실행 (백그라운드, MPS 기준 수 시간 예상)**

Run: `cd ~/dev/jlens-lab && nohup uv run python scripts/fit_lens.py --n-prompts 100 --out artifacts/full > artifacts/full.log 2>&1 &`
Expected: 종료 후 `artifacts/full/timing.json`. smoke 대비 `seconds_per_prompt`가 유사(선형 스케일 확인).

- [x] **Step 3: full lens로 Task 5 비교 재실행**

Run: `uv run python scripts/apply_lens.py --lens artifacts/full/lens.pt --text "The capital of France is"`
Expected: smoke lens보다 같거나 나은 품질 (100 프롬프트 saturation 근처).

- [x] **Step 4: 리포트 작성**

`reports/2026-07-29-a-stage-report.md`에 기록:
- 실측 `seconds_per_prompt` (smoke/full, device/dtype 명시) vs spec 추정치 — ±3× 판정
- MPS bf16 backward 동작 여부, 발생한 이슈와 해결
- J-lens vs logit lens 비교 스냅샷 (프롬프트 3개)
- 8B 재추정: `실측 s/prompt × (17 PFLOPs / 0.3 PFLOPs) × (대상 GPU 유효 TFLOPs / 로컬 유효 TFLOPs)` 계산식과 결과, VRAM 관찰치
- B 단계 go/no-go 권고

- [x] **Step 5: Commit + 본 repo plan 체크박스 갱신**

```bash
cd ~/dev/jlens-lab && git add -A && git commit -m "docs: A-stage report with measured timings and 8B re-estimate"
```

본 repo의 이 plan 파일에서 완료된 체크박스를 갱신한다 (본 repo 커밋은 사용자 확인 후).

---

## Self-Review 결과

- **Spec coverage**: 성공 기준 1(비교 재현)→Task 5/6, 2(실측·±3×)→Task 4/6, 3(아티팩트+apply)→Task 4/5, 4(8B 재추정)→Task 6. 미해결 질문 1~3(API/device/코퍼스)→Task 1. B/C 단계는 spec대로 범위 외.
- **Placeholder scan**: jlens 외부 API 3곳은 실코드로 작성하되 Task 1 api-notes를 단일 진실 원천으로 지정(Global Constraints) — 외부 미공개 API에 대한 계획상 최선.
- **Type consistency**: `resolve_device`/`load_texts`/`timed_fit`/`save_timing`/`FitTiming` 시그니처가 Task 2/3 정의와 Task 4/5 사용처에서 일치함을 확인.
