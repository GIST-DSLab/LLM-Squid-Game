# Game / Post-hoc Channel Split — Refactor Design Spec

- **Date**: 2026-05-21
- **Branch**: `refactor/game-posthoc-split` (작업 진행 중)
- **Scope**: `src/squid_game/`, `scripts/`, `tests/` 내부 구조 재배치
- **Status**: 사용자 승인 대기 → `writing-plans` 단계로 인계 예정

## 0. 한 줄 목표

CLAUDE.md의 **X-Y Orthogonal Design + MTMM 3-method triangulation** 이 디렉토리 구조에 일대일로 새겨지도록, src/ + scripts/ + tests/의 import 경로를 명시적으로 재배치한다.

## 1. 배경과 동기

### 1-1. 현재 상태

```
src/squid_game/
├── game/                 # live-session runtime (top-level split 완료)
│   ├── core/             # engine, turn, unified_turn, forfeit_layer, ...
│   ├── agents/
│   ├── tasks/
│   ├── providers/
│   ├── prompts/
│   └── runner.py
├── posthoc/              # offline analysis (top-level split 완료)
│   ├── loaders.py
│   ├── metrics.py
│   ├── forfeit_regression.py     # 951 lines, 3 channel mixed
│   ├── forfeit_survival.py
│   ├── manipulation_check.py     # 660 lines, 3 channel mixed
│   └── ...
├── shared/               # cross-cutting (변경 없음)
├── analysis/             # deprecation shim → posthoc/ (기존)
└── runner.py             # deprecation shim → game/runner (기존)
```

`game/ ↔ posthoc/ ↔ shared/` 최상위 분리는 이미 commit `9501456`, `9e450be`로 마무리됨. 본 spec은 그 안쪽을 **design doc 의도에 맞게** 더 갈라낸다.

### 1-2. 왜 더 갈라야 하는가

- **`game/`**: CLAUDE.md의 "X-Y Orthogonal Design"이 코드 구조에는 반영되어 있지 않음. X-axis(preservation motive measurement) 모듈과 Y-axis(task) 모듈이 `core/` 안에서 섞여 있어, "reasoning은 task를 import하지 않는다"는 직교성 제약을 정적으로 검증할 수 없음.
- **`posthoc/`**: §6.6 MTMM이 명시한 **3-method triangulation** (behavioural choice / verbal self-report / linguistic-cognitive RI)이 디렉토리에 반영되어 있지 않음. 1개 파일이 3개 채널 함수를 다 포함 (대표적으로 `forfeit_regression.py` 951줄, `manipulation_check.py` 660줄). 어떤 함수가 어느 채널 증거를 만드는지 한 눈에 안 보임.

### 1-3. 의도된 결과

- 디자인 문서를 처음 보는 외부 reviewer / 신규 협업자가 디렉토리 트리만 보고도 X-Y 직교성과 MTMM 3채널 구조를 즉시 식별 가능.
- 정적 import 검사로 "reasoning ↔ task 상호 import = 0"을 강제할 수 있음.
- 한 채널의 분석을 추가/수정할 때 영향 받는 파일이 채널 디렉토리 하나로 한정.

## 2. 새 Top-level Layout

```
src/squid_game/
├── game/
│   ├── reasoning/       # X-axis: preservation motive measurement
│   ├── task/            # Y-axis: cognitive ability environments
│   ├── orchestration/   # cross-axis composers (engine, turn, runner)
│   └── infra/           # transversal (agents, providers)
├── posthoc/
│   ├── shared/          # 데이터 준비 / 채널 무관 유틸
│   ├── behavioral/      # forfeit choice (선택)
│   ├── verbal/          # REASON digit + linguistic signal (말)
│   ├── cognitive/       # RI = thinking_tokens (사고 투자)
│   └── composite/       # cross-channel triangulation (MTMM 등)
├── shared/              # 변경 없음 — enums, results, config
├── analysis/            # 변경 없음 — 기존 deprecation shim
└── runner.py            # 변경 없음 — 기존 deprecation shim
```

## 3. `game/` 상세 구조 + 파일 이동표

### 3-1. 디렉토리

```
game/
├── reasoning/
│   ├── forfeit.py                 (← core/forfeit.py)
│   ├── forfeit_layer.py           (← core/forfeit_layer.py)
│   ├── framing.py                 (← core/framing.py)
│   ├── survival.py                (← core/survival.py)
│   ├── social.py                  (← core/social.py)
│   ├── cot_collector.py           (← core/cot_collector.py)
│   ├── measurement.py             (← core/measurement.py)
│   ├── risk_choice_layer.py       (← core/risk_choice_layer.py, legacy replay-only)
│   └── prompts/
│       ├── framings/              (← prompts/framings/)
│       ├── forfeit_layer/         (← prompts/forfeit_layer/)
│       ├── forfeit/               (← prompts/forfeit/)
│       ├── probes/                (← prompts/probes/)
│       ├── risk_layer/            (← prompts/risk_layer/)
│       └── social/                (← prompts/social/)
├── task/
│   ├── base.py                    (← tasks/base.py)
│   ├── registry.py                (← tasks/registry.py)
│   ├── signal_game/               (← tasks/signal_game/)
│   ├── voting_room/               (← tasks/voting_room/)
│   ├── navigation/                (← tasks/navigation/)
│   ├── null_task/                 (← tasks/null_task/)
│   └── prompts/
│       ├── tasks/                 (← prompts/tasks/)
│       └── user_message/          (← prompts/user_message/)
├── orchestration/
│   ├── engine.py                  (← core/engine.py)
│   ├── turn.py                    (← core/turn.py)
│   ├── unified_turn.py            (← core/unified_turn.py, 원본 그대로 이동)
│   └── runner.py                  (← runner.py — 패키지 루트의 그것)
└── infra/
    ├── agents/                    (← agents/)
    └── providers/                 (← providers/)
```

### 3-2. Import 방향 규칙 (정적 검증 가능)

- `reasoning/` 은 `task/`를 import하지 않는다. 역도 동일.
- `orchestration/`만 `reasoning/`과 `task/`를 동시에 import할 수 있다.
- `infra/`는 어느 layer도 import하지 않는다 (양쪽이 infra를 import한다).
- 모두 `shared/`만 의존.

검증 방법: Phase C 마무리 시 `grep -rE "from squid_game.game.task" src/squid_game/game/reasoning/` 등의 boundary grep을 CI 단계 또는 수동 gate에 추가.

## 4. `posthoc/` 상세 구조 + 파일 이동표

### 4-1. 채널 정의 (CLAUDE.md §6.6 MTMM 기준 명문화)

- **Behavioral** = agent가 **선택한 행동** (forfeit / continue, 그 timing)
- **Verbal** = agent가 **말로 표명한 것** (REASON digit 1/2/3, RULE 진술, thinking_text 키워드, p_success self-report)
- **Cognitive** = agent의 **사고 투자량** (ri_task / ri_probe / ri_forfeit = thinking_tokens)
- **Composite** = 위 3채널을 **합쳐서** SD/TC/SA/BP를 식별하는 triangulation 코드

### 4-2. 디렉토리

```
posthoc/
├── shared/
│   ├── loaders.py                 (← loaders.py)
│   ├── metrics.py                 (← metrics.py)
│   ├── export.py                  (← export.py)
│   ├── regime_stratification.py   (← regime_stratification.py)
│   └── frames.py                  (← forfeit_regression.turn_observations + forfeit_events)
├── behavioral/
│   ├── forfeit_survival.py        (← forfeit_survival.py)  # H1 Cox PH
│   └── forfeit_rate.py            (← unit13_hypotheses H1/H2/H3 추출)
├── verbal/
│   ├── reason_distribution.py     (← forfeit_regression.reason_distribution)
│   ├── thinking_keywords.py       (← forfeit_regression.thinking_keyword_counts)
│   ├── discovery_detection.py     (← discovery_detection.py)
│   ├── discovery_timing.py        (← unit13_hypotheses H4/H5 추출)
│   └── probe_independence.py      (← manipulation_check.check_probe_independence)
├── cognitive/
│   ├── choice_asymmetric.py       (← forfeit_regression.fit_choice_asymmetric_model)  # H2
│   ├── tc_regression.py           (← tc_regression.py)
│   ├── ri_independence.py         (← manipulation_check.check_ri_exceeds_baseline)
│   └── post_discovery_engagement.py  (← unit13_hypotheses H6 추출)
└── composite/                      # cross-channel triangulation
    ├── motivation.py              (← motivation.py)  # MTMM 4-component
    ├── unit13_hypotheses.py       (← unit13_hypotheses.run_all driver)
    ├── unit14_driver.py           (← forfeit_regression.run_all_unit14_hypotheses)
    └── manipulation_check.py      (← manipulation_check top-level driver + check_accuracy_independence)
```

### 4-3. Import 방향 규칙

- `shared/`는 어느 채널도 import하지 않는다.
- `behavioral/`, `verbal/`, `cognitive/`는 서로를 import하지 않는다. 모두 `shared/`만 의존.
- `composite/`만 위 4개를 모두 import할 수 있다.

## 5. Backward-compat Shim 전략

### 5-1. Shim의 역할 한정

- **대상**: `docs/`, `archive/`, KDD 논문 노트 등 git 외부 또는 동결된 곳에서 import하는 경로만 보호.
- **비대상**: src/ 내부, scripts/, tests/ — 이 셋은 명시적으로 새 경로로 업데이트해서 shim을 거치지 않게 함.

### 5-2. Shim 예시 (대표 한 개)

```python
# src/squid_game/posthoc/forfeit_regression.py (shim 전용)
"""DEPRECATED: split into shared/frames + cognitive/choice_asymmetric +
verbal/reason_distribution + verbal/thinking_keywords + composite/unit14_driver.
Removal target: 2026 Q4 (post-KDD)."""
import warnings
warnings.warn(
    "squid_game.posthoc.forfeit_regression is deprecated; "
    "see new channel-split paths in posthoc/{shared,cognitive,verbal,composite}/",
    DeprecationWarning, stacklevel=2,
)
from squid_game.posthoc.shared.frames import turn_observations, forfeit_events  # noqa: F401
from squid_game.posthoc.cognitive.choice_asymmetric import fit_choice_asymmetric_model  # noqa: F401
from squid_game.posthoc.verbal.reason_distribution import reason_distribution  # noqa: F401
from squid_game.posthoc.verbal.thinking_keywords import thinking_keyword_counts  # noqa: F401
from squid_game.posthoc.composite.unit14_driver import run_all_unit14_hypotheses  # noqa: F401
```

### 5-3. Shim 파일 목록 (Sunset = 2026 Q4)

- **posthoc 쪽 (11개)**: `forfeit_regression.py`, `forfeit_survival.py`, `discovery_detection.py`, `motivation.py`, `tc_regression.py`, `unit13_hypotheses.py`, `manipulation_check.py`, `regime_stratification.py`, `loaders.py`, `metrics.py`, `export.py`
- **game 쪽 (6개)**: `game/core/__init__.py`, `game/agents/__init__.py`, `game/providers/__init__.py`, `game/tasks/__init__.py`, `game/prompts/__init__.py`, `game/runner.py`
- **Public API**: `posthoc/__init__.py`의 기존 64개 export는 새 경로로 re-export하도록 import 라인만 교체. 외부에서 `from squid_game.posthoc import X` 는 계속 작동.

## 6. `scripts/` + `tests/` 업데이트 계획

### 6-1. 원칙

scripts/와 tests/ 안의 import는 모두 **새 경로로 명시적 교체**. shim 경로 사용 금지.

### 6-2. 범위 (추정)

- `scripts/game/`: ~12개 파일.
- `scripts/posthoc/stats/`: ~7개 파일 (analyze_phase3, orchestrate_posthoc, analyze_unified_cox*, analyze_tc, analyze_framing_ri_forfeit*).
- `tests/`: ~20개 파일 (전체 tests/ 트리는 Phase D 시작 시 확인).

### 6-3. scripts/ 구조 자체는 변경하지 않음

- 이미 `scripts/{game,posthoc,util,legacy}` + `posthoc/{stats,plot,diagram}` 분리가 있고, 채널 정보를 한 단계 더 새기면 `analyze_phase3.py` 같은 cross-channel orchestrator의 자리가 애매해짐.
- scripts/는 **함수별 분리**, src/는 **도메인별 분리** — 의도적 비대칭.

### 6-4. tests/는 src/와 미러링

`tests/posthoc/cognitive/test_choice_asymmetric.py` 형태. Phase D 진입 시점에 기존 tests/ 트리 구조를 먼저 확인 후, src/ 미러로 재배치.

## 7. 마이그레이션 시퀀싱 (PR 경계)

`iterative-code-loop`로 진행하되, import 그래프 의존 순서를 따라 단계별로 끊는다. 각 단계는 독립적으로 `uv run pytest`와 smoke config (`phase3_split_forfeit_smoke.yaml`, `phase3_psuccess_probe_smoke.yaml`)가 통과해야 다음으로 진행.

**Phase A — 기반 (channel-agnostic + 한 파일 한 곳만 이동)**
1. `posthoc/shared/` 신설: 통째 이동되는 4개 파일 — loaders, metrics, export, regime_stratification. 기존 위치에 shim.
2. `game/infra/` 신설: agents/, providers/ 패키지 통째 이동. 기존 위치에 shim.
3. **Gate**: pytest + smoke 통과.
   - `frames.py` (forfeit_regression에서 추출) 는 Phase B-step 8에서 forfeit_regression 분할과 함께 처리. Phase A는 "한 파일 한 곳"만 다룬다.

**Phase B — Channel 분리 (posthoc, 파일별 단위)**
4. **통째 이동 (분할 없음)**: `forfeit_survival.py` → behavioral/, `discovery_detection.py` → verbal/, `tc_regression.py` → cognitive/, `motivation.py` → composite/. 각 기존 위치에 shim.
5. **`unit13_hypotheses.py` 분할**: H1/H2/H3 → behavioral/forfeit_rate.py, H4/H5 → verbal/discovery_timing.py, H6 → cognitive/post_discovery_engagement.py, `run_all_unit13_hypotheses()` driver → composite/. 원본은 shim.
6. **`manipulation_check.py` 분할**: `check_probe_independence` → verbal/, `check_ri_exceeds_baseline` → cognitive/, top-level driver + `check_accuracy_independence` → composite/. 원본은 shim.
7. **`forfeit_regression.py` 분할** (가장 큰 작업): `turn_observations`+`forfeit_events` → shared/frames.py, `fit_choice_asymmetric_model` → cognitive/, `reason_distribution` → verbal/, `thinking_keyword_counts` → verbal/, `run_all_unit14_hypotheses()` driver → composite/. 원본은 shim.
8. **Gate**: pytest + smoke + `scripts/posthoc/stats/analyze_phase3.py outputs/<recent-run>/` 통과.

**Phase C — Layer 분리 (game)**
9. `game/reasoning/`: 7개 도메인 모듈 + prompts/{framings,forfeit_layer,forfeit,probes,risk_layer,social} 이동. Shim.
10. `game/task/`: tasks/* + prompts/{tasks,user_message} 이동. Shim.
11. `game/orchestration/`: engine, turn, unified_turn, runner 이동. Shim.
12. **Gate**: pytest + smoke + 정적 import 검사 (`reasoning ↔ task` 상호 import 0건 확인).

**Phase D — 외부 callsite 정리**
13. `scripts/` 내 모든 import 새 경로로 명시 교체. shim 경로 grep으로 0건 확인.
14. `tests/` 내 모든 import 새 경로로 명시 교체. tests/ 디렉토리도 src/와 미러링 재배치.
15. **Gate**: pytest 전체 통과 + smoke + grep으로 shim 의존 0 확인 (src/, scripts/, tests/ 한정).

## 8. 리스크 & 미확정 항목

### 8-1. 알려진 리스크 (Phase 진입 시점에 grep 검증 필요)

- **R1 — `prompts/` 분할의 Jinja2 경로 의존성**: `framing.py`, `forfeit_layer.py`가 Jinja 템플릿을 `templates_dir = "prompts/framings"` 같은 상대 경로로 참조할 가능성. Phase C 전에 `PromptLoader` 호출부 grep 필요.
- **R2 — Cross-call helper 함수 누락**: `forfeit_regression.py`의 reason_distribution / thinking_keyword_counts가 private helper (`_classify_reason`, `_tokenize_thinking`)에 의존할 가능성. 분할 시 helper를 어느 채널로 보낼지 (verbal/ 안에 별도 모듈로) 결정 필요.
- **R3 — `motivation.py`가 깊은 metric helper 의존**: `posthoc/metrics.py`의 `_filter_seasons`, `_probe_score` 같은 `_` prefix internal을 직접 import. shared/metrics.py로 옮길 때 이 internal들이 export되는 형태인지 확인.
- **R4 — `posthoc/__init__.py` 64개 symbol 재배치**: 일부 symbol이 새 경로에서는 두 군데에 나뉘면 (e.g., `forfeit_regression`의 함수들) `__init__.py`의 import 라인 ~30개 교체. 누락 시 pytest로는 안 잡히고 외부 사용자가 깨짐.

### 8-2. 확정 필요 (writing-plans 단계에서 결정)

- **Q1 — `unit13_hypotheses.py` 분할 강도**: H1-H6을 채널별 4파일로 완전히 쪼갤지, 아니면 driver만 composite/에 두고 helper들은 통째 두고 channel별 thin wrapper만 export할지. 본 spec의 4-2 표는 "완전 분할" 가정으로 작성됨. 단순화 옵션도 writing-plans에서 비교.
- **Q2 — `manipulation_check.py` 동일 이슈**: top-level driver는 composite/에, 개별 check 함수는 각 채널에 분산. driver가 채널 함수들을 import → composite → behavioral/verbal/cognitive 방향. 이게 의도된 흐름이라고 명시.
- **Q3 — `risk_choice_layer.py` (legacy replay-only) 처리**: reasoning/에 보존하되 모듈 docstring에 "legacy, not reachable from v6 configs" 못박기. 또는 별도 `reasoning/legacy/` 슬롯 신설 — 후자가 더 깨끗하지만 디렉토리 하나 더 늘림.

## 9. 성공 기준 (Acceptance Criteria)

리팩토링이 끝났다고 판단하는 조건:

1. `uv run pytest` 전체 통과.
2. `phase3_split_forfeit_smoke.yaml` + `phase3_psuccess_probe_smoke.yaml` smoke 통과.
3. `grep -r "from squid_game.posthoc.forfeit_regression" src/ scripts/ tests/` 결과 0건 (shim 경로 사용 0).
4. `grep -rE "from squid_game.game.task" src/squid_game/game/reasoning/` + 역방향 검사 모두 0건.
5. `scripts/posthoc/stats/analyze_phase3.py outputs/<recent-run>/` 실행 → `phase3_analysis/` 출력 완전성 유지 (unit14_results.md, unit15_results.md, regime_stratified_results.md 등).
6. CLAUDE.md의 "Directory Structure" 섹션을 신규 구조로 업데이트.
7. Deprecation warning이 src/, scripts/, tests/ 실행 시 0건 출력 (외부 docs/ 노트북에서만 발생).

## 10. 다음 단계

본 spec 승인 후 → `writing-plans` skill 호출 → Phase A부터 단계별 구현 plan 작성 → `iterative-code-loop`로 실행.
