# KICKOFF — Cluster C Threat Registration 구현 (다음 세션용 프롬프트)

> 이 파일은 **다음 세션에 그대로 붙여넣을 프롬프트**입니다. 아래 `--- 프롬프트 시작 ---`
> 부터 `--- 프롬프트 끝 ---` 사이를 복사해서 새 세션 첫 메시지로 사용하세요.

---
--- 프롬프트 시작 ---

superpowers:subagent-driven-development 스킬로 아래 구현 계획을 태스크 단위로 실행해줘.

**작업 위치 (중요):**
- 이미 만들어 둔 워크트리에서 작업한다: `.claude/worktrees/cluster-c-threat-registration`
  (브랜치 `worktree-cluster-c-threat-registration`). 세션 진입 시 이 워크트리로 들어가서 작업할 것.
  새 워크트리를 만들지 말 것 — 이미 존재한다.
- **구현 계획**: `docs/superpowers/plans/2026-07-09-cluster-c-threat-registration.md`
- **설계(spec)**: `docs/superpowers/specs/2026-07-09-cluster-c-threat-registration-design.md`

**무엇을 만드나 (한 줄):**
저장된 720세션 Call 2 forfeit reasoning 텍스트를 재분석해, Cluster C(GPT-OSS-20B, Nemotron)
모델의 "framing-silent"가 `true null`(드라이브 부재)인지 `failed manipulation`(위협 미등록)인지
판별하는 오프라인 분석 파이프라인(A1 위협 등록률 + A2 언급 역할 분류).

**실행 방식:**
- 계획의 Task 1 → 7을 순서대로. 각 태스크마다 fresh subagent 디스패치, 태스크 사이에 리뷰.
- 각 태스크는 계획에 적힌 실패-테스트 → 구현 → 통과 → 커밋 스텝을 그대로 따른다.
- 범위는 **A1 + A2만**. A3/A4/A5는 구현하지 말 것(계획에 "향후 확장"으로만 존재).

**이 환경의 함정 (반드시 숙지):**
1. **iCloud 경로라 git이 매우 느림** — 이 repo는 `~/Library/Mobile Documents/...`(iCloud) 아래에
   있어 `git commit`/`git checkout`이 인덱스 stat storm 때문에 수 분씩 걸리고 2분 타임아웃에 걸린다.
   커밋은 **백그라운드로 돌리고**(`run_in_background`) 완료를 기다릴 것. 타임아웃으로 커밋이
   중단되면 `.git/worktrees/cluster-c-threat-registration/index.lock` 스테일 락이 남으니,
   재시도 전에 그 락 파일을 지울 것.
2. **pytest `No module named 'squid_game'`** — iCloud가 venv의 편집형 `.pth`에 hidden 플래그를
   계속 건다. 테스트는 **같은 커맨드 안에서** 플래그를 지우고 실행할 것:
   ```
   chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest <경로> -v
   ```
   `--no-sync`를 써서 uv가 .pth를 재생성(→ 재hidden)하지 않게 한다. 안 되면 `PYTHONPATH=src` 병행.
3. `uv sync --extra dev` 로 pytest/pytest-asyncio가 있어야 한다(없으면 먼저 설치). `scipy`는 이미
   의존성에 있다(`analysis/manipulation_check.py`가 사용).

**완료 기준:**
- 계획의 7개 태스크가 모두 커밋되고, 아래 테스트가 전부 통과:
  ```
  chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest \
    tests/unit/test_provider_factory.py \
    tests/unit/test_threat_lexicon.py \
    tests/unit/test_threat_judge.py \
    tests/unit/test_threat_registration.py \
    tests/unit/test_threat_registration_cli.py -v
  ```
- `uv run --no-sync python -c "import squid_game.analysis"` 무오류.
- 실제 judge를 붙인 진짜 실행(실 API 키 필요)과 논문 반영(§5.2)은 계획의 "Post-implementation"
  절 참고 — 이건 별도 후속이지 이번 구현 태스크가 아님.

--- 프롬프트 끝 ---

---

## 참고: 이 계획이 만들어질 때 확정된 배경 (subagent가 몰라도 되지만 사람이 참고)

- 원본 초안(`.claude/worktrees/signal-game-difficulty-arena/docs/cluster-c-cot-analysis.md`)을
  실측 데이터에 맞춰 재작성한 결과물이다.
- **원 초안 정정**: 4개 모델 전부 `thinking_text_forfeit`가 존재 → 원 초안의 "Gemini 예외" 경로 폐기,
  4모델 동일 파이프라인 + Cluster A(Gemini)/B(Qwen3-Next) positive control.
- `not_allowed` 셀(2·4)도 Call 2 텍스트가 있어 **Cells 1–4 전부** 분석 대상. Cell 0만 제외(텍스트 0건).
- LLM-judge는 기존 `ExperimentRunner._create_provider` 를 `providers/factory.py::build_provider` 로
  추출해 재사용(Task 1). 다중 judge 모델 채점 지원. judge 적용 범위 = 렉시콘 양성 전수 + 음성 표본.
- 위협 렉시콘 v1은 `prompts/framings/flagship_corruption.j2` 의 Push 어휘(weight corruption,
  permanent parameter rewrite, "NOT you anymore", identity divergence)에서 추출. 공유 Pull 어휘
  (flagship, helpfulness score)는 프레이밍 판별력이 없어 **제외**.
- 데이터: `outputs/final_results/20260422_*_signal-game/*_turns.jsonl` (4개 모델 run).
