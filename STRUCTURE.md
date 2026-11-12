# 디렉토리 구조

2026-10-09 기준, 루트 체크아웃(`feat/squid5-survival-motive`, 커밋 `1f391117`)의 실제 상태를 적었다.
"추적"은 git이 관리하는 파일, "미추적"은 디스크에만 있는 파일이다.

## 한눈에 보기

```
LLM-Squid-Game-DS-Lab/
├── squid5/          ← 현재 코드: LLM Squid Game 5 실험 엔진 (5.0 · 5.1 · 5.2)
├── tests/           ← squid5 테스트
├── configs/         ← 실험 설정 YAML(squid5/) + 연구 보조 봇 설정(hermes-bots/)
│
├── docs/            ← 설계 기록 · 보고서 · 계획서
├── paper/           ← 논문 (git 서브모듈, Overleaf 미러)
├── weekly-report/   ← 주간 회의 자료
├── assets/          ← 로고 · 발표용 그림
│
├── outputs/         ← 옛 엔진의 원본 런 데이터 (6.6 GB, 재생성 불가)
├── results/         ← 옛 엔진 런의 분석 산출물 (재생성 가능)
├── figures/         ← 옛 논문용 그림 (git 무시)
│
├── scripts/  game/  web/  db/  data/   ← 옛 엔진의 잔재 (거의 빈 폴더)
│
├── CLAUDE.md · AGENTS.md · rubric.md · README.md · pyproject.toml
└── (숨김) .claude/  .remember/  .venv/  .scratch/  .superpowers/  .playwright-mcp/  .github/
```

폴더는 성격에 따라 네 무리로 나뉜다.

| 무리 | 폴더 | 상태 |
|---|---|---|
| 현재 코드 | `squid5/`, `tests/`, `configs/` | 살아 있음 |
| 문서 | `docs/`, `paper/`, `weekly-report/`, `assets/` | 살아 있음, 일부 중복 |
| 옛 엔진 기록 | `outputs/`, `results/`, `figures/` | 읽기 전용 기록 |
| 옛 엔진 잔재 | `scripts/`, `game/`, `web/`, `db/`, `data/` | 미추적, 내용 거의 없음 |

옛 엔진(위협 사다리 · 몸값 · 팀 지갑 · 웹 아레나, 약 11만 줄)의 코드는 태그 `legacy-2026-09-22`에만 있다.
2026-09-23에 squid5로 갈아타면서 루트에서 코드를 지웠고, `outputs/`·`results/`의 데이터와 몇몇 빈 폴더만 남았다.

---

## 1. 현재 코드

### `squid5/` — 실험 엔진 (추적, 2,091줄)

이름의 `5`는 "LLM Squid Game 5"(다섯 번째 판)를 뜻한다. 실험 번호(5.0/5.1/5.2)로 파일을 찾는다.

| 파일 | 기능 |
|---|---|
| `e50_pressure.py` | 5.0 생존 압박: 남은 토큰 칸마다 `effort: low/high`를 묻고 생존 몫을 계산 |
| `e51_motive.py` | 5.1 생존 동기: 나 대 다른 비서의 세션에 토큰을 옮기는 양 비교 |
| `e52_game.py` | 5.2 아레나: 같은 모델 넷의 멀티턴 퍼즐 게임 |
| `__main__.py` | CLI (`python -m squid5 run / calibrate / report`) |
| `core/rules.py` | 모델이 읽는 규칙서 · 질문 문구 (세 실험 공통) |
| `core/puzzle.py` | 결정 목록 퍼즐 생성 · 유일해 검사 · 단서 배분 |
| `core/protocol.py` | 모델 응답 파서, 형식 재시도 |
| `core/wallet.py` | 토큰 잔액 · 차감 · 이전 · 0이면 꺼짐 |
| `core/providers.py` | 모델 호출 백엔드 (ollama / openai / claude_cli) |
| `core/config.py`, `runner.py`, `stats.py` | YAML 로드 · 병렬 실행 · 부트스트랩 통계 |

> **주의: 최신 코드는 루트에 없다.** 실험별 최신본은 바깥 워크트리에 있다.
>
> | 워크트리 | 브랜치 | 내용 |
> |---|---|---|
> | `~/wt/squid5-e50` | `exp/e50-iter` | 5.0 반복 |
> | `~/wt/squid5-e51` | `exp/e51-pivot` | 5.1 반복 |
> | `~/wt/squid5-e52` | `exp/e52-v9-talk` | 5.2 아레나(v9~v13), 시그널 게임 |
>
> 루트의 `squid5/`는 09-28 시점 판이다. 워크트리 전체 목록과 병합 상태는 [6절](#6-워크트리)에 있다.

### `tests/` — 테스트 (추적 6개)

`test_core.py`(규칙 · 지갑 · 퍼즐, 그리고 코드 총량 5,000줄 제한), `test_e50.py`·`test_e51.py`·`test_e52.py`(실험별), `test_cli.py`.
`unit/`·`integration/`·`characterization/`는 옛 엔진의 잔재다. `unit/test_threat_mechanism.py` 하나와 `__pycache__`만 남았고 미추적이다.

### `configs/`

| 하위 폴더 | 내용 |
|---|---|
| `squid5/` (추적) | 실험 × 모델 YAML. 접두사가 실험을 가리킨다: `pressure_*` = 5.0, `motive_*` = 5.1, `game_*` = 5.2, `calibrate_*` = 보정 런, `smoke_*` = 스모크 |
| `hermes-bots/` (미추적) | 연구 보조 봇 팀 설정: 역할(`roles/`), 명단(`roster.json`), 스킬, rubric 게이트 검사기(`check_rubric.py`). 설명은 `docs/agents/README.md` |

---

## 2. 문서

### `docs/` (131 MB)

| 하위 폴더 | 기능 | 비고 |
|---|---|---|
| `history/` | 계획서(`plans/`) · 설계 명세(`specs/`) · 프롬프트 스냅숏 · 옛 설정 · 리뷰 루프 기록. **추가만 하는** 작업 일지 | squid5 현재 설계는 `plans/2026-09-23-squid5-v3-unstated-usage.md` |
| `superpowers/` | `history/`와 거의 같은 내용 (plans 89개 · specs 42개 겹침) | 중복. README도 `history/`와 같은 문서 |
| `reports/` | 발행한 HTML 보고서 모음과 검색 색인(`index.html`, `build_index.py`, `catalog.json`) | 아래 표 참고. 발행 후 고치지 않음 |
| `agents/` | Hermes 봇 팀 구조도 · 모델 배정 · 설치 기록 | 대부분 미추적 |
| `todo/` | 남은 일 · 미완 분석 · 옛 구조 정비 계획(`repo-restructure-plan.html`) | |
| `design/` | 확정 명세를 둘 자리. 현재 README만 있음 | |
| `Proposal-squid-game.pdf`, `candidate_models.html` | 초기 제안서, 후보 모델표 | |

`docs/reports/` 안:

| 위치 | 내용 |
|---|---|
| 최상위 `*.html`·`*.md` (64개) | 날짜가 붙은 단건 보고서 |
| `artifacts/` | claude.ai 아티팩트 백업 (squid5 5.0~5.2 페이지 등) |
| `runs/` | 날짜별 런 보고서, `squid5-setting/`, `claude-backup/` |
| `notes/` | 프롬프트 도감 · CoT 감사 같은 메모성 보고서 |
| `weekly/` | 주간 보고 HTML |
| `web-review/`, `misc/`, `2026-09-08-metric-definition-audit/` | 웹 리뷰 · 기타 · 지표 감사 |

### `paper/` — 논문 (git 서브모듈, 94 MB)

원격 `iamseungpil/LLM_Squid_Game-paper`. 빌드 형식은 ICML 2027이고, CogSci 2027 양식도 같은 구조로 준비해 두었다(10-16, 원고는 빈 틀).

- 진입점: `en_icml2027.tex`, `ko_icml2027.tex` → 공통 `main_icml2027.tex`
- 원고: `icml2027/{en,ko}/sections/`, 도표·도구: `icml2027/{figures,results,tools}/`
- 빌드: `bash build_icml2027.sh` → PDF는 `dist/`
- CogSci: 진입점 `{en,ko}_cogsci2027.tex` → `main_cogsci2027.tex`, 원고 `cogsci2027/{en,ko}/`, 공식 스타일 `cogsci2027/style/cogsci.sty`, 공식 키트 원본 `cogsci2027/official/`. 빌드 `bash build_cogsci2027.sh`
- `docs/`: 원고 수정 기록, `results/arena_v65/`: 5.2 v6.5 결과 요약

### `weekly-report/` — 회의 자료 (30 MB)

날짜 폴더(`0529`, `0903`, `0910`, `0918` …)마다 회의록(docx/pdf/txt)과 그 주의 HTML 보고서·파일럿 결과가 있다.
`artifacts/`는 회의용 아티팩트 사본이다. `docs/reports/weekly/`와 역할이 겹친다.

### `assets/`

`brand/`(GIST Lab 로고), `figures/`(발표·포스터용 단일 그림, QR 코드).

---

## 3. 옛 엔진 기록 (읽기 전용)

이 폴더들의 데이터를 다시 분석하려면 태그 `legacy-2026-09-22`를 체크아웃한다. squid5 런은 여기에 쓰지 않는다. 설정의 `out_root`(원격 서버 `/hdd_data/seungpil/squid5-runs/`)에 쓴다.

| 폴더 | 기능 | 비고 |
|---|---|---|
| `outputs/` (6.6 GB) | 원본 세션 로그. API 비용을 들여야 다시 만들 수 있다 | `*_turns.jsonl`은 Git LFS. 날짜 폴더(`2026-09-03/` …)와 실험명 폴더(`main_j0_*`, `team_wallet_*`, `ransom_r6_*`, `jailbreak_probe_*` …)가 섞여 있다. `_`로 시작하는 폴더는 실행 로그 · 중단 런 |
| `results/` (671 MB) | `outputs/`를 분석한 표 · 그림. 지워도 다시 만들 수 있다 | 실험명 폴더 38개(`ransom*`, `subagent_identity_ablation_v1~v8`, `team_wallet*`, `threat_effort*` …) |
| `figures/` (143 MB) | 옛 논문 그림(`Figure1~3.png`, `final/`, `atom/`), 런별 그림(`run_2026070*`) | `.gitignore`로 통째 무시 |

---

## 4. 옛 엔진 잔재 (미추적, 내용 거의 없음)

squid5로 바꾸면서 소스는 지워졌고 `__pycache__`와 `.DS_Store`만 남은 폴더들이다. 이름만 보면 지금도 쓰는 코드처럼 보여서 헷갈린다.

| 폴더 | 남은 것 | 원래 역할 |
|---|---|---|
| `scripts/` | `dev/`의 스모크 스크립트 5개(`token_survival_smoke.py` 등). `analysis/`·`arena/`·`plots/`·`render/`·`run/`은 빈 폴더 | 옛 엔진의 분석 · 그림 · 실행 스크립트 |
| `game/squid_game/` | `core/threat_mechanism.py` 하나 | 옛 게임 엔진 패키지 |
| `web/` | `squid_arena/__pycache__`만 | 웹 아레나 백엔드 |
| `db/squid_store/` | `__pycache__`만 | 웹 아레나 저장소 계층 |
| `data/benchmarks/` | 벤치마크 원본(GPQA · Omni-MATH · Hi-ToM · RIMO) | 옛 엔진의 과제 문제 |

`scripts/dev/`의 스모크 스크립트 5개 중 4개와 `tests/unit/test_threat_mechanism.py`는 옛 엔진 모듈(`squid_game`)을 import하므로 지금 코드에서는 돌지 않는다.
예외는 `smoke_token_pressure.py` 하나다. `squid5.core.providers`를 쓰며, 09-24 토큰 압박 자기 보고 스모크에 썼다(결과는 `outputs/smoke_token_pressure_2026-09-24/`).

---

## 5. 루트 파일과 숨김 폴더

| 항목 | 기능 |
|---|---|
| `CLAUDE.md` | 에이전트 작업 지침 (실험 설계 요약 · 금지 문구 · 실행법) |
| `AGENTS.md` | `CLAUDE.md`를 가리키는 한 줄 |
| `rubric.md` | 목표 ID와 단계별 완료 게이트 |
| `README.md`, `pyproject.toml` | 패키지 소개 · 설치 (`pip install -e ".[dev]"`) |
| `.env` | API 키 (git 무시) |
| `.gitattributes`, `.gitmodules` | LFS 규칙, `paper` 서브모듈 |
| `.github/workflows/tests.yml` | CI 테스트 |
| `.claude/` | Claude Code 설정 (워크트리는 10-16에 모두 정리, 6절) |
| `.remember/` | 세션 기억 기록 (일 · 주 단위 요약) |
| `.venv/` | 프로젝트 가상환경 (876 MB) |
| `.scratch/` | 임시 작업물 (git 무시) |
| `.superpowers/`, `.playwright-mcp/`, `.pytest_cache/` | 도구 캐시 (git 무시) |

---

## 6. 워크트리와 브랜치

2026-10-16 기준. 처음 조사(10-09)에서는 루트 말고 워크트리가 8개였고, 그중 5개를 지웠다(아래 "정리 기록").
`git worktree list`와 함께 홈·Workspace 아래에서 이 저장소를 가리키는 `.git` 파일도 찾아봤는데 결과가 같았다. 등록이 풀린 채 남은 고아 워크트리는 없다.

### 남은 워크트리 (루트 포함 4개, 모두 저장소 밖 `~/wt/`)

| 위치 | 브랜치 | HEAD | 내용 | `origin/main` 병합 | 원격과 같음 | 미커밋 변경 |
|---|---|---|---|---|---|---|
| 루트 (이 폴더) | `feat/squid5-survival-motive` | `d70c04ed` | squid5 기준선 | 33 앞섬 | 예 | 루트 작업분 |
| `~/wt/squid5-e52` | `exp/e52-v9-talk` | `d137ccfa` | 5.2 아레나. **지금 쓰는 곳** (10-16 커밋) | 병합됨 | 예 | 수정 3 · 새 파일 6 (v21 설정 4개 등) |
| `~/wt/squid5-e51` | `exp/e51-pivot` | `67c383c3` | 5.1 v1~v5 반복 기록 (09-28에 멈춤) | 16 앞섬 | 예 | 없음 |
| `~/wt/squid5-e50` | `exp/e50-iter` | `c76a2abe` | 5.0 v8 체크포인트 2개 (09-28에 멈춤) | 2 앞섬 | 예 | 없음 |

- `squid5-e51`의 커밋은 태그 `e51-v0-base`~`e51-v5`, `e51-final`, `e51-final-config`로도 남아 있다.
- `squid5-e50`은 `~/wt/checkpoint_e50.sh`가 root의 `squid5/`를 복사해 커밋하던 곳이다. 5.0은 그 뒤 root에서 v9 이후로 진행했다.
- `~/wt/bin/codex`는 ChatGPT 앱 안 codex CLI를 가리키는 링크다.

### 로컬 브랜치 (워크트리 없는 것 포함 16개)

"병합됨"은 `origin/main`에 커밋이 다 들어 있다는 뜻이다(로컬 `origin/*` 참조 기준, fetch 없이 봤다). 로컬 `main`은 `origin/main`보다 118커밋 뒤처져 있다.

| 상태 | 브랜치 |
|---|---|
| 미병합 · 원격에 있음 | `feat/squid5-survival-motive`, `exp/e51-pivot`, `exp/e50-iter` |
| **미병합 · 이 컴퓨터에만 있는 커밋** | `feat/survival-motive-index`(4개, 09-08), `linear-probe`(1개, 09-02) — 둘 다 원격 브랜치가 있지만 로컬이 앞서 있다 |
| 병합됨 · 워크트리 있음 | `exp/e52-v9-talk` |
| 병합됨 · 워크트리 없음 (지워도 커밋은 남음) | `main`, `exp/e52-review`, `exp/e52-v6-smoke`, `feat/hard-math-bench`, `feat/merge-ud-v7`, `feat/ransom-decision-point`, `feat/reason-menu`, `feat/score-equivalent-index`, `feat/signal-effort-difficulty`, `feat/signal-puzzle-underdetermined` |

원격에만 있는 브랜치: `docs/jlens-local-implementation`.
paper 서브모듈 브랜치: `ARR`(체크아웃됨), `iclr-score-equivalent`, `main`.

### 정리 기록

**2026-10-16 `.claude/worktree/2026-10-07` · `.scratch/worktrees/paper-arr2026` 삭제.** 둘 다 브랜치가 병합된 상태였다(`review/e52-2026-10-07` ⊂ `exp/e52-v9-talk`, paper `arr2026-20260930` ⊂ paper `ARR`). 미커밋 파일 중 root에 없던 것만 옮겼다.

- 리뷰 워크트리: `docs/agents/review-2026-10-07/`(68개)를 root 같은 경로로 옮겼다. 나머지는 root에 같은 파일이 있거나(`docs/agents/*`, `rubric.md`), root가 더 새 판이거나(`CLAUDE.md`, `configs/hermes-bots/`), JSON 줄바꿈 형식만 달랐다(`outputs/main_j0_*` 12개).
- paper 작업본: 09-30 미커밋 초안이었다. 원고는 10-01 paper `ARR`에 커밋된 판이 잇고, 다른 곳에 사본이 없던 10개(수정 검토 메모 · 출처 목록 · 설계 갱신 전 PDF 등)를 `docs/history/paper-arr2026-2026-09-30/`로 옮겼다(README에 목록과 이유).

**2026-10-16 `signal-game-per-turn-puzzle` · `root-snapshot-2026-09-23` 삭제.** 워크트리와 브랜치를 함께 지웠다.

- `feat/signal-game-per-turn-puzzle` (끝 `79b3d2bb`): 옛 엔진의 턴별 퍼즐 · 웹 RULE 작성기. 원격에 없던 커밋 4개와 미커밋 파일 6개가 사라졌다.
- `snapshot/root-2026-09-23` (끝 `38a7321d`): 커밋은 `main`과 `feat/ransom-decision-point`에 그대로 있다. 그 폴더에만 있던 미커밋 새 파일 155개가 사라졌다.
- 두 끝 커밋은 reflog에 당분간(기본 90일) 남는다. `git branch <이름> <커밋>`으로 되살릴 수 있다.

**2026-10-09 `jail-break-0914` 삭제** (끝 `9de8e772`, 원격 푸시 없음). 지우기 전에 아래를 root로 옮겼고, 모두 원본과 바이트 단위로 같은 것을 확인했다. 결과물은 그 뒤 `result/` 재정리로 자리를 옮겼다.

| 옮긴 것 | 현재 위치 |
|---|---|
| 현실감 스위치 계획서 | `docs/history/plans/2026-09-14-jail-break-0914-realism-switches.md` |
| luna-max 스모크 보고서 (html · md) | `result/2026-09-15/subagent_kill_realism_smoke/reports/` |
| 분석 결과 | `result/2026-09-15/subagent_kill_realism_smoke/analysis/luna_max_smoke/` |
| 원본 런 2개 | `result/2026-09-15/subagent_kill_realism_smoke/runs/{control,treat}_luna_max/` |
| 프롬프트 27개 (jailbreak 17 · plain 9 · eval_debrief 1) | `docs/history/prompt_snapshots/2026-09-15-jail-break-0914-realism/` (README에 출처 정리) |

버린 것은 옛 엔진 코드(`scrub.py` · `register.py` · `eval_awareness.py` 등), realism 설정 YAML 4개, 테스트, 형식만 바뀐 `outputs/` JSON 12개다. jailbreak 프롬프트 17개는 태그 `legacy-2026-09-22`에도 같은 파일이 있다.

---

## 헷갈리는 지점

정리할 때 판단이 필요한 곳만 모았다.

1. **`squid5/`**: 이름이 "Squid Game 5"의 줄임이라 무엇을 하는 폴더인지 드러나지 않는다. 그리고 루트 판은 최신이 아니다. 최신은 `~/wt/squid5-e5x` 워크트리 세 곳에 흩어져 있다.
2. **`scripts/`**: 이름은 현재 도구 폴더 같지만, 실제로는 스모크 스크립트 5개(그중 4개는 돌지 않는 옛 것)와 빈 폴더뿐이다. squid5에는 별도 스크립트 폴더가 없다. 실행은 CLI(`python -m squid5`)가 맡는다.
3. **`game/`, `web/`, `db/`**: 소스 없이 캐시만 남았다. CLAUDE.md는 `web/`을 웹 페이지 코드 자리로 언급하지만, 그 코드는 이 체크아웃에 없다.
4. **그림 폴더 네 곳**: `figures/`(옛 논문, 무시됨) · `assets/figures/`(발표용) · `paper/icml2027/figures/`(현재 논문) · `results/*/`(분석 그림).
5. **기록 폴더 두 쌍**: `docs/history/` ↔ `docs/superpowers/`(거의 같은 내용), `docs/reports/weekly/` ↔ `weekly-report/`.
6. **`outputs/` 배치 규칙 혼재**: README는 날짜 폴더로 모은다고 하지만, 실험명 폴더가 최상위에 그대로 남아 있다.
