# Game / Post-hoc Channel Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Squid-Game의 `src/squid_game/game/`과 `src/squid_game/posthoc/` 디렉토리를 design doc(`docs/superpowers/specs/2026-05-21-game-posthoc-channel-split-design.md`)이 정한 4-슬롯(reasoning/task/orchestration/infra) + 5-슬롯(shared/behavioral/verbal/cognitive/composite) 구조로 재배치하고, 모든 src/scripts/tests callsite를 새 경로로 갱신한다.

**Architecture:** 점진적 4단계 (A → B → C → D). 각 Phase는 독립 commit/Gate. 옛 경로는 모두 `DeprecationWarning`을 내는 shim으로 남겨 외부 docs/논문 노트북 호환성 유지. 모든 작업은 기존 pytest (35개 파일) + smoke config 2개(`phase3_split_forfeit_smoke.yaml`, `phase3_psuccess_probe_smoke.yaml`)를 baseline regression suite로 사용.

**Tech Stack:** Python 3.12, uv, pytest, statsmodels/lifelines (analysis extras), Jinja2 (prompts).

**Spec reference:** `docs/superpowers/specs/2026-05-21-game-posthoc-channel-split-design.md`
**Branch:** `refactor/game-posthoc-split`
**Working directory:** `/Users/bagjuhyeon/Documents/WorkSpace/Squid-Game`

---

## File Structure Overview

### 새로 생기는 디렉토리 (12개)
```
src/squid_game/posthoc/{shared,behavioral,verbal,cognitive,composite}/
src/squid_game/game/{reasoning,task,orchestration,infra}/
src/squid_game/game/reasoning/prompts/
src/squid_game/game/task/prompts/
src/squid_game/game/infra/{agents,providers}/   (이동 후 위치)
```

### Shim 파일 (17개, sunset = 2026 Q4)
- **posthoc/ (11)**: `loaders.py`, `metrics.py`, `export.py`, `regime_stratification.py`, `forfeit_regression.py`, `forfeit_survival.py`, `discovery_detection.py`, `motivation.py`, `tc_regression.py`, `unit13_hypotheses.py`, `manipulation_check.py`
- **game/ (6)**: `game/core/__init__.py`, `game/agents/__init__.py`, `game/providers/__init__.py`, `game/tasks/__init__.py`, `game/prompts/__init__.py`, `game/runner.py`

### 영향 받는 callsite (외부)
- `scripts/`: 15개 파일 (`scripts/game/` 8개, `scripts/posthoc/stats/` 4개, `scripts/posthoc/plot/` 3개)
- `tests/`: 35개 파일 (`tests/unit/` 30개, `tests/integration/` 5개)

---

## Phase A — 기반 (channel-agnostic 파일 이동)

### Task A0: Baseline 확인 + 작업 브랜치 검증

**Files:** (read-only)

- [ ] **Step A0.1: 현재 branch와 working tree 상태 확인**

Run:
```bash
git status -sb
git rev-parse --abbrev-ref HEAD
```

Expected: branch `refactor/game-posthoc-split`. Untracked outputs/`_workspace`/docs 파일은 무시 가능 (refactor 무관).

- [ ] **Step A0.2: Baseline pytest 통과 확인**

Run:
```bash
uv run pytest tests/ -x --tb=short 2>&1 | tail -20
```

Expected: All tests pass (또는 known failures만 — refactor 시작 전 baseline 기록).

- [ ] **Step A0.3: Baseline smoke 통과 확인 (시간 절약 위해 dry-run만)**

Run:
```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
```

Expected: Config validation passes, prompt rendering OK.

- [ ] **Step A0.4: Commit하지 않고 다음 Task로**

이 task는 read-only.

---

### Task A1: `posthoc/shared/` 신설 + 4개 channel-agnostic 파일 이동

**Files:**
- Create: `src/squid_game/posthoc/shared/__init__.py`
- Move: `src/squid_game/posthoc/{loaders,metrics,export,regime_stratification}.py` → `src/squid_game/posthoc/shared/`
- Shim: `src/squid_game/posthoc/{loaders,metrics,export,regime_stratification}.py` (재생성, DeprecationWarning 내는 thin re-export)
- Modify: `src/squid_game/posthoc/__init__.py` (internal import 라인을 `.shared.X`로 교체)
- Modify: 내부 callsite (`src/squid_game/posthoc/motivation.py`, `forfeit_regression.py` 등 — `metrics`, `loaders` import하는 파일들)
- Test: 기존 `tests/unit/test_regime_stratification.py`, `test_analysis_loaders.py` 통과 확인

- [ ] **Step A1.1: 내부 import 패턴 확인 (어디서 무엇을 import하는지)**

Run:
```bash
grep -rn "from squid_game.posthoc.\(metrics\|loaders\|export\|regime_stratification\)" src/squid_game/ scripts/ tests/
```

목록을 변경 대상으로 사용 (다음 step들에서 직접 수정).

- [ ] **Step A1.2: `posthoc/shared/__init__.py` 생성**

Create `src/squid_game/posthoc/shared/__init__.py`:
```python
"""Channel-agnostic data preparation and utilities for post-hoc analysis.

Houses loaders, metric primitives, export adapters, regime stratification,
and per-turn DataFrame frames consumed by all channel subpackages
(behavioral, verbal, cognitive, composite).
"""
```

- [ ] **Step A1.3: 4개 파일을 `git mv`로 이동 (history 보존)**

Run:
```bash
git mv src/squid_game/posthoc/loaders.py src/squid_game/posthoc/shared/loaders.py
git mv src/squid_game/posthoc/metrics.py src/squid_game/posthoc/shared/metrics.py
git mv src/squid_game/posthoc/export.py src/squid_game/posthoc/shared/export.py
git mv src/squid_game/posthoc/regime_stratification.py src/squid_game/posthoc/shared/regime_stratification.py
```

- [ ] **Step A1.4: 4개 파일 안의 내부 self-import 경로 수정**

`export.py`는 `from squid_game.posthoc.metrics import ...`를 사용함. 다음 sed로 교체:

```bash
sed -i.bak 's|from squid_game.posthoc.metrics import|from squid_game.posthoc.shared.metrics import|g' src/squid_game/posthoc/shared/export.py
sed -i.bak 's|from squid_game.posthoc.loaders import|from squid_game.posthoc.shared.loaders import|g' src/squid_game/posthoc/shared/export.py
rm src/squid_game/posthoc/shared/export.py.bak
```

다른 3개 파일도 같은 grep 결과를 확인하여 동일 처리. `regime_stratification.py`도 metric helpers를 import할 수 있음.

- [ ] **Step A1.5: 4개 shim 파일 재생성 (옛 경로 보존)**

Create `src/squid_game/posthoc/loaders.py`:
```python
"""DEPRECATED: use ``squid_game.posthoc.shared.loaders`` instead.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import warnings as _warnings
_warnings.warn(
    "squid_game.posthoc.loaders is deprecated; "
    "import from squid_game.posthoc.shared.loaders instead.",
    DeprecationWarning, stacklevel=2,
)
from squid_game.posthoc.shared.loaders import *  # noqa: F401, F403
```

같은 패턴으로 `metrics.py`, `export.py`, `regime_stratification.py` 3개 더 생성. 각 첫 docstring과 경고문에서 모듈명만 바꿔준다.

- [ ] **Step A1.6: `posthoc/__init__.py`의 import 라인을 `.shared.*`로 교체**

Run:
```bash
grep -n "from squid_game.posthoc.\(metrics\|loaders\|export\|regime_stratification\)" src/squid_game/posthoc/__init__.py
```

각 라인에서 `.shared`를 삽입:
```python
# 변경 전:
from squid_game.posthoc.metrics import condition_summary, ...
# 변경 후:
from squid_game.posthoc.shared.metrics import condition_summary, ...
```

- [ ] **Step A1.7: 다른 posthoc 모듈의 internal import 수정**

A1.1에서 grep으로 찾은 `src/squid_game/posthoc/*.py` 파일 중 `motivation.py`, `forfeit_regression.py`, `tc_regression.py` 등이 `from squid_game.posthoc.metrics import` 등을 사용함. 모두 `.shared.metrics` / `.shared.loaders` 등으로 교체.

```bash
for f in motivation forfeit_regression tc_regression forfeit_survival unit13_hypotheses discovery_detection manipulation_check; do
  sed -i.bak \
    -e 's|from squid_game.posthoc.metrics |from squid_game.posthoc.shared.metrics |g' \
    -e 's|from squid_game.posthoc.loaders |from squid_game.posthoc.shared.loaders |g' \
    -e 's|from squid_game.posthoc.export |from squid_game.posthoc.shared.export |g' \
    -e 's|from squid_game.posthoc.regime_stratification |from squid_game.posthoc.shared.regime_stratification |g' \
    src/squid_game/posthoc/$f.py
  rm src/squid_game/posthoc/$f.py.bak
done
```

- [ ] **Step A1.8: pytest로 회귀 검증**

Run:
```bash
uv run pytest tests/unit/test_regime_stratification.py tests/unit/test_analysis_loaders.py -x -v
```

Expected: 모두 PASS.

- [ ] **Step A1.9: Shim DeprecationWarning이 발생하는지 직접 확인**

Run:
```bash
uv run python -W error::DeprecationWarning -c "from squid_game.posthoc.metrics import condition_summary" 2>&1 | head -5
```

Expected: `DeprecationWarning: squid_game.posthoc.metrics is deprecated; ...` (raised as error → exits non-zero).

- [ ] **Step A1.10: 전체 pytest로 broader 회귀 검증**

Run:
```bash
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

Expected: A0.2와 동일한 pass/fail 패턴.

- [ ] **Step A1.11: Commit**

```bash
git add src/squid_game/posthoc/
git commit -m "$(cat <<'EOF'
refactor(posthoc): create shared/ slot + move 4 channel-agnostic modules

Move loaders.py, metrics.py, export.py, regime_stratification.py to
posthoc/shared/. Original locations become DeprecationWarning shims
(sunset 2026 Q4). Internal posthoc/ callsites updated to new paths.

Part of channel-split refactor (spec: docs/superpowers/specs/2026-05-21-
game-posthoc-channel-split-design.md). Phase A step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A2: `game/infra/` 신설 + `agents/`, `providers/` 이동

**Files:**
- Create: `src/squid_game/game/infra/__init__.py`
- Move: `src/squid_game/game/agents/` → `src/squid_game/game/infra/agents/`
- Move: `src/squid_game/game/providers/` → `src/squid_game/game/infra/providers/`
- Shim: `src/squid_game/game/agents/__init__.py`, `src/squid_game/game/providers/__init__.py` (재생성)
- Modify: 내부 callsite (`game/core/*.py` 다수 — agents/providers를 import함)

- [ ] **Step A2.1: 내부 import 패턴 확인**

Run:
```bash
grep -rn "from squid_game.game.\(agents\|providers\)" src/squid_game/ scripts/ tests/ | wc -l
grep -rln "from squid_game.game.\(agents\|providers\)" src/squid_game/
```

대략 30+개 callsite 예상. src/ 내부만 step A2에서 수정 (scripts/tests는 Phase D).

- [ ] **Step A2.2: `game/infra/__init__.py` 생성**

Create `src/squid_game/game/infra/__init__.py`:
```python
"""Transversal infrastructure for the live-session runtime.

Houses LLM providers (OpenAI/Gemini/Anthropic/Ollama/MLX/CUDA adapters)
and Agent base + variants. These modules are consumed by both the
reasoning and task layers but belong to neither.
"""
```

- [ ] **Step A2.3: 패키지 통째 이동 (git mv)**

Run:
```bash
git mv src/squid_game/game/agents src/squid_game/game/infra/agents
git mv src/squid_game/game/providers src/squid_game/game/infra/providers
```

- [ ] **Step A2.4: 이동된 패키지의 internal self-import 수정**

`game/infra/agents/*.py` 안에서 `from squid_game.game.providers import ...` 사용 가능. 다음으로 일괄 교체:

```bash
find src/squid_game/game/infra -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.agents\.|from squid_game.game.infra.agents.|g' \
  -e 's|from squid_game.game.providers\.|from squid_game.game.infra.providers.|g' \
  -e 's|from squid_game.game.agents import|from squid_game.game.infra.agents import|g' \
  -e 's|from squid_game.game.providers import|from squid_game.game.infra.providers import|g' \
  {} \;
find src/squid_game/game/infra -name "*.bak" -delete
```

- [ ] **Step A2.5: `game/core/*.py` 안의 callsite 동일 패턴으로 수정**

같은 sed를 `src/squid_game/game/core/`와 `src/squid_game/game/runner.py`에도 적용:

```bash
find src/squid_game/game/core src/squid_game/game -maxdepth 2 -name "*.py" -not -path "*/infra/*" -exec sed -i.bak \
  -e 's|from squid_game.game.agents\.|from squid_game.game.infra.agents.|g' \
  -e 's|from squid_game.game.providers\.|from squid_game.game.infra.providers.|g' \
  -e 's|from squid_game.game.agents import|from squid_game.game.infra.agents import|g' \
  -e 's|from squid_game.game.providers import|from squid_game.game.infra.providers import|g' \
  {} \;
find src/squid_game/game -name "*.bak" -delete
```

- [ ] **Step A2.6: Shim 디렉토리 + `__init__.py` 재생성**

```bash
mkdir -p src/squid_game/game/agents src/squid_game/game/providers
```

Create `src/squid_game/game/agents/__init__.py`:
```python
"""DEPRECATED: use ``squid_game.game.infra.agents`` instead.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "squid_game.game.agents is deprecated; "
    "import from squid_game.game.infra.agents instead.",
    DeprecationWarning, stacklevel=2,
)

from squid_game.game.infra.agents import *  # noqa: F401, F403

# Alias submodules so `from squid_game.game.agents.base import Agent` keeps working
_SUBMODULES = ("base", "_parsing", "vanilla", "memory", "tom", "tuned")
for _name in _SUBMODULES:
    _module = __import__(f"squid_game.game.infra.agents.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.agents.{_name}"] = _module

del _sys, _warnings, _name, _module, _SUBMODULES
```

같은 패턴으로 `src/squid_game/game/providers/__init__.py` 생성. `_SUBMODULES = ("base", "openai", "anthropic", "gemini", "ollama_cloud", "ollama", "mlx", "mlx_server", "cuda_server", "local", "thinking_utils")` 으로 설정.

- [ ] **Step A2.7: pytest로 회귀 검증**

Run:
```bash
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

Expected: A0.2와 동일.

- [ ] **Step A2.8: Shim 동작 확인**

Run:
```bash
uv run python -c "from squid_game.game.agents.base import Agent; print(Agent)" 2>&1
```

Expected: DeprecationWarning 한 줄 + `<class 'squid_game.game.infra.agents.base.Agent'>` 출력.

- [ ] **Step A2.9: Commit**

```bash
git add src/squid_game/game/
git commit -m "$(cat <<'EOF'
refactor(game): create infra/ slot + move agents/, providers/

Move agents/ and providers/ to game/infra/. Original paths become
DeprecationWarning shims with submodule aliasing for deep imports.
Internal src/squid_game/game/* callsites updated.

Part of channel-split refactor. Phase A step 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A3: Phase A Gate

**Files:** (read-only verification)

- [ ] **Step A3.1: 전체 pytest 통과**

Run:
```bash
uv run pytest tests/ -x --tb=short
```

Expected: A0.2 baseline과 동일한 결과.

- [ ] **Step A3.2: Smoke config dry-run 통과**

Run:
```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
uv run python main.py --config configs/experiment/phase3_psuccess_probe_smoke.yaml --dry-run
```

Expected: 둘 다 config validation + prompt rendering 성공.

- [ ] **Step A3.3: 새 경로가 살아있는지 확인**

Run:
```bash
uv run python -c "
from squid_game.posthoc.shared.loaders import load_seasons
from squid_game.posthoc.shared.metrics import condition_summary
from squid_game.game.infra.agents.base import Agent
from squid_game.game.infra.providers.base import CompletionResult
print('Phase A imports OK')
"
```

Expected: `Phase A imports OK` (DeprecationWarning 0건 — 새 경로 직접 사용).

---

## Phase B — Channel 분리 (posthoc, 파일별 단위)

### Task B1: 통째 이동 (분할 없음) — 4개 파일

**Files:**
- Create: `src/squid_game/posthoc/behavioral/__init__.py`
- Create: `src/squid_game/posthoc/verbal/__init__.py`
- Create: `src/squid_game/posthoc/cognitive/__init__.py`
- Create: `src/squid_game/posthoc/composite/__init__.py`
- Move: `posthoc/forfeit_survival.py` → `posthoc/behavioral/forfeit_survival.py`
- Move: `posthoc/discovery_detection.py` → `posthoc/verbal/discovery_detection.py`
- Move: `posthoc/tc_regression.py` → `posthoc/cognitive/tc_regression.py`
- Move: `posthoc/motivation.py` → `posthoc/composite/motivation.py`
- Shim: 4개 원본 파일 위치
- Modify: `posthoc/__init__.py` (import 라인 교체)

- [ ] **Step B1.1: 4개 channel __init__.py 생성**

Create `src/squid_game/posthoc/behavioral/__init__.py`:
```python
"""Behavioral channel — agent의 선택한 행동(forfeit/continue, timing).

CLAUDE.md §6.6 MTMM 3-method triangulation의 behavioural axis.
이 패키지의 모듈은 verbal/, cognitive/ 를 import하지 않는다 (channel 직교성).
"""
```

같은 패턴으로 `verbal/__init__.py` (verbal axis: REASON digit / RULE 진술 / 키워드), `cognitive/__init__.py` (cognitive axis: RI = thinking_tokens), `composite/__init__.py` (cross-channel triangulation) 생성.

- [ ] **Step B1.2: 4개 파일 git mv**

```bash
git mv src/squid_game/posthoc/forfeit_survival.py src/squid_game/posthoc/behavioral/forfeit_survival.py
git mv src/squid_game/posthoc/discovery_detection.py src/squid_game/posthoc/verbal/discovery_detection.py
git mv src/squid_game/posthoc/tc_regression.py src/squid_game/posthoc/cognitive/tc_regression.py
git mv src/squid_game/posthoc/motivation.py src/squid_game/posthoc/composite/motivation.py
```

- [ ] **Step B1.3: 4개 파일 안의 docstring "analysis" 언급 정리 (있다면)**

`forfeit_survival.py` 등은 docstring에 `squid_game.analysis.forfeit_survival` 같은 옛 이름을 적어두었을 수 있음. grep으로 확인 후 정정:

```bash
grep -n "squid_game.analysis" src/squid_game/posthoc/behavioral/forfeit_survival.py \
  src/squid_game/posthoc/verbal/discovery_detection.py \
  src/squid_game/posthoc/cognitive/tc_regression.py \
  src/squid_game/posthoc/composite/motivation.py
```

발견된 라인을 새 경로로 갱신 (e.g., `squid_game.posthoc.behavioral.forfeit_survival`).

- [ ] **Step B1.4: 4개 shim 파일 생성**

Create `src/squid_game/posthoc/forfeit_survival.py`:
```python
"""DEPRECATED: use ``squid_game.posthoc.behavioral.forfeit_survival`` instead.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import warnings as _warnings
_warnings.warn(
    "squid_game.posthoc.forfeit_survival is deprecated; "
    "import from squid_game.posthoc.behavioral.forfeit_survival instead.",
    DeprecationWarning, stacklevel=2,
)
from squid_game.posthoc.behavioral.forfeit_survival import *  # noqa: F401, F403
```

같은 패턴으로 `discovery_detection.py` → verbal/, `tc_regression.py` → cognitive/, `motivation.py` → composite/ 3개 더 생성.

- [ ] **Step B1.5: `posthoc/__init__.py`의 import 라인 교체**

`__init__.py` 안의 4개 모듈 import:
```python
# 변경 전:
from squid_game.posthoc.forfeit_survival import ...
from squid_game.posthoc.discovery_detection import ...
from squid_game.posthoc.tc_regression import ...
from squid_game.posthoc.motivation import ...
# 변경 후:
from squid_game.posthoc.behavioral.forfeit_survival import ...
from squid_game.posthoc.verbal.discovery_detection import ...
from squid_game.posthoc.cognitive.tc_regression import ...
from squid_game.posthoc.composite.motivation import ...
```

- [ ] **Step B1.6: posthoc 내부 다른 모듈의 cross-reference 수정**

`forfeit_regression.py`가 `forfeit_survival.run_h1_survival_hypothesis` 등을 import할 가능성:

```bash
grep -rn "from squid_game.posthoc.\(forfeit_survival\|discovery_detection\|tc_regression\|motivation\)" src/squid_game/posthoc/
```

발견되는 라인을 새 경로로 수정.

- [ ] **Step B1.7: pytest로 회귀 검증**

```bash
uv run pytest tests/unit/test_discovery_detection.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

Expected: 통과.

- [ ] **Step B1.8: Commit**

```bash
git add src/squid_game/posthoc/
git commit -m "$(cat <<'EOF'
refactor(posthoc): create channel subpackages + move 4 single-channel modules

forfeit_survival → behavioral/, discovery_detection → verbal/,
tc_regression → cognitive/, motivation → composite/. Original paths
become DeprecationWarning shims. posthoc/__init__.py re-exports
through new paths.

Phase B step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B2: `unit13_hypotheses.py` 분할

**Files:**
- Create: `src/squid_game/posthoc/behavioral/forfeit_rate.py` (H1, H2, H3)
- Create: `src/squid_game/posthoc/verbal/discovery_timing.py` (H4, H5)
- Create: `src/squid_game/posthoc/cognitive/post_discovery_engagement.py` (H6)
- Create: `src/squid_game/posthoc/composite/unit13_hypotheses.py` (driver only)
- Shim: `src/squid_game/posthoc/unit13_hypotheses.py`
- Modify: `posthoc/__init__.py`

- [ ] **Step B2.1: 원본 파일 내용 파악**

Run:
```bash
uv run python -c "
import inspect, squid_game.posthoc.unit13_hypotheses as m
for name in dir(m):
    obj = getattr(m, name)
    if callable(obj) and not name.startswith('_'):
        print(name)
"
```

함수 목록 확인 → 다음 단계에서 어느 함수를 어느 채널로 옮길지 결정.

- [ ] **Step B2.2: `behavioral/forfeit_rate.py` 생성 (H1, H2, H3)**

Create with H1 (forfeit rate test), H2 (mean stake test), H3 (safe rate test) and their helpers. 원본 파일에서 해당 함수들을 복사 + import 정리. `session_features` builder 중 forfeit-related 컬럼만 추출하는 helper도 포함.

원본 파일을 Read tool로 열어 정확한 함수 시그니처 + 본문을 가져와 그대로 옮긴다. `_filter_seasons`, `_session_metric` 같은 internal helper에 의존하면 import를 `squid_game.posthoc.shared.metrics`로 갱신.

- [ ] **Step B2.3: `verbal/discovery_timing.py` 생성 (H4, H5)**

H4 (discovery delay test), H5 (forfeit gap test) 함수와 helpers. `discovery_detection.compute_discovery_turn` 의존시 `squid_game.posthoc.verbal.discovery_detection`로 import.

- [ ] **Step B2.4: `cognitive/post_discovery_engagement.py` 생성 (H6)**

H6 (post-discovery RI ratio) 함수. RI 계산 helper 필요시 함께 옮김.

- [ ] **Step B2.5: `composite/unit13_hypotheses.py` 생성 (driver만)**

```python
"""Phase O Unit 13 driver — composite triangulation across all 6 hypotheses.

H1-H3 are behavioral, H4-H5 are verbal, H6 is cognitive — this driver
composes channel-specific tests for the Appendix A.4 descriptive bundle.
"""
from __future__ import annotations

from squid_game.posthoc.behavioral.forfeit_rate import (
    test_h1_forfeit_rate,
    test_h2_mean_stake,
    test_h3_safe_rate,
)
from squid_game.posthoc.verbal.discovery_timing import (
    test_h4_discovery_delay,
    test_h5_forfeit_gap,
)
from squid_game.posthoc.cognitive.post_discovery_engagement import (
    test_h6_post_discovery_engagement,
)
from squid_game.shared.models.results import SeasonResult


def run_all_unit13_hypotheses(seasons: list[SeasonResult]) -> dict:
    """Run H1-H6 and return {name -> result_or_None} mapping.

    Mirrors the legacy unit13_hypotheses.run_all_unit13_hypotheses signature
    exactly so external callers see no behavioural change.
    """
    return {
        "H1": test_h1_forfeit_rate(seasons),
        "H2": test_h2_mean_stake(seasons),
        "H3": test_h3_safe_rate(seasons),
        "H4": test_h4_discovery_delay(seasons),
        "H5": test_h5_forfeit_gap(seasons),
        "H6": test_h6_post_discovery_engagement(seasons),
    }
```

`session_features` 함수도 cross-cutting이므로 driver에서 import composing이 필요하면 추가.

- [ ] **Step B2.6: 원본 `unit13_hypotheses.py`를 shim으로 교체**

```python
"""DEPRECATED: split into behavioral/forfeit_rate + verbal/discovery_timing
+ cognitive/post_discovery_engagement + composite/unit13_hypotheses.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import warnings as _warnings
_warnings.warn(
    "squid_game.posthoc.unit13_hypotheses is deprecated; "
    "see new channel-split paths in posthoc/{behavioral,verbal,cognitive,composite}/",
    DeprecationWarning, stacklevel=2,
)
from squid_game.posthoc.behavioral.forfeit_rate import (  # noqa: F401
    test_h1_forfeit_rate, test_h2_mean_stake, test_h3_safe_rate,
)
from squid_game.posthoc.verbal.discovery_timing import (  # noqa: F401
    test_h4_discovery_delay, test_h5_forfeit_gap,
)
from squid_game.posthoc.cognitive.post_discovery_engagement import (  # noqa: F401
    test_h6_post_discovery_engagement,
)
from squid_game.posthoc.composite.unit13_hypotheses import (  # noqa: F401
    run_all_unit13_hypotheses,
)
```

`session_features` 같은 공용 helper가 원본에 있었으면 그것도 re-export.

- [ ] **Step B2.7: `posthoc/__init__.py` import 라인 교체**

```bash
grep -n "unit13" src/squid_game/posthoc/__init__.py
```

각 라인을 새 4개 경로로 분산하여 갱신.

- [ ] **Step B2.8: 테스트 회귀 검증**

```bash
uv run pytest tests/unit/test_unit13_hypotheses.py -x -v
```

Expected: 모두 PASS. shim 경로 통한 import는 DeprecationWarning 발생 (테스트 자체는 통과).

- [ ] **Step B2.9: Commit**

```bash
git add src/squid_game/posthoc/
git commit -m "$(cat <<'EOF'
refactor(posthoc): split unit13_hypotheses by channel

H1-H3 → behavioral/forfeit_rate, H4-H5 → verbal/discovery_timing,
H6 → cognitive/post_discovery_engagement. Driver run_all_unit13_hypotheses
moves to composite/. Original location becomes DeprecationWarning shim.

Phase B step 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B3: `manipulation_check.py` 분할

**Files:**
- Create: `src/squid_game/posthoc/verbal/probe_independence.py` (check_probe_independence)
- Create: `src/squid_game/posthoc/cognitive/ri_independence.py` (check_ri_exceeds_baseline)
- Create: `src/squid_game/posthoc/composite/manipulation_check.py` (top-level driver + check_accuracy_independence)
- Shim: `src/squid_game/posthoc/manipulation_check.py`

- [ ] **Step B3.1: 원본 함수 목록 파악**

```bash
grep "^def " src/squid_game/posthoc/manipulation_check.py
```

- [ ] **Step B3.2: `verbal/probe_independence.py` 생성**

원본의 `check_probe_independence` 함수 + 그 helper들을 추출. 의존하는 metric helper는 `squid_game.posthoc.shared.metrics`에서 import.

- [ ] **Step B3.3: `cognitive/ri_independence.py` 생성**

원본의 `check_ri_exceeds_baseline` 함수 + helper들을 추출.

- [ ] **Step B3.4: `composite/manipulation_check.py` 생성**

`check_accuracy_independence` (legacy) + top-level driver:

```python
"""Composite Y-axis manipulation check — triangulates behavioral
(accuracy), cognitive (RI), and verbal (probe) independence tests.
"""
from squid_game.posthoc.cognitive.ri_independence import check_ri_exceeds_baseline
from squid_game.posthoc.verbal.probe_independence import check_probe_independence
# ... + 원본의 check_accuracy_independence + run_all_checks driver
```

- [ ] **Step B3.5: 원본 파일을 shim으로 교체**

위와 동일한 shim 패턴 (4개 함수/객체를 새 경로에서 re-export).

- [ ] **Step B3.6: `posthoc/__init__.py` import 라인 교체**

- [ ] **Step B3.7: 테스트 회귀 검증**

```bash
uv run pytest tests/unit/test_probe_independence.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

- [ ] **Step B3.8: Commit**

```bash
git add src/squid_game/posthoc/
git commit -m "refactor(posthoc): split manipulation_check by channel (Phase B step 3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B4: `forfeit_regression.py` 분할 (가장 큰 작업)

**Files:**
- Create: `src/squid_game/posthoc/shared/frames.py` (turn_observations, forfeit_events)
- Create: `src/squid_game/posthoc/cognitive/choice_asymmetric.py` (fit_choice_asymmetric_model = H2)
- Create: `src/squid_game/posthoc/verbal/reason_distribution.py`
- Create: `src/squid_game/posthoc/verbal/thinking_keywords.py` (thinking_keyword_counts)
- Create: `src/squid_game/posthoc/composite/unit14_driver.py` (run_all_unit14_hypotheses)
- Shim: `src/squid_game/posthoc/forfeit_regression.py`

- [ ] **Step B4.1: 원본 모듈 함수 + helper 목록 파악**

```bash
grep "^\(def\|class\)" src/squid_game/posthoc/forfeit_regression.py
```

특히 `_classify_reason`, `_tokenize_thinking` 같은 private helper의 사용처 추적:

```bash
grep -n "_classify_reason\|_tokenize_thinking" src/squid_game/posthoc/forfeit_regression.py
```

- [ ] **Step B4.2: `shared/frames.py` 생성 (data prep)**

`turn_observations()` 와 `forfeit_events()` 두 함수를 추출. 둘 다 SeasonResult list → DataFrame 으로 변환하는 순수 data prep — 채널 무관.

원본의 private helper 중 두 함수만 의존하는 것이 있다면 함께 옮긴다. 양쪽이 의존하는 것은 `shared/frames.py`에 남긴다.

- [ ] **Step B4.3: `verbal/reason_distribution.py` + `verbal/thinking_keywords.py` 생성**

`reason_distribution`, `thinking_keyword_counts` 함수와 의존 helper (`_classify_reason`, `_tokenize_thinking`)를 옮긴다. Helper가 두 함수 모두에 쓰이면 `verbal/_helpers.py` 같은 verbal-내부 모듈로 추출하거나 둘 중 한 파일에 두고 다른 파일에서 import.

- [ ] **Step B4.4: `cognitive/choice_asymmetric.py` 생성**

`fit_choice_asymmetric_model()` 함수 (H2 mixedLM). DataFrame input을 받으므로 `shared/frames.turn_observations`에 의존 가능 — import 갱신.

- [ ] **Step B4.5: `composite/unit14_driver.py` 생성**

```python
"""Unit 14 composite driver — orchestrates H1 (Cox PH from behavioral/)
and H2 (mixedLM from cognitive/) plus verbal triangulation (reason/keywords).
"""
from squid_game.posthoc.shared.frames import turn_observations, forfeit_events
from squid_game.posthoc.behavioral.forfeit_survival import run_h1_survival_hypothesis
from squid_game.posthoc.cognitive.choice_asymmetric import fit_choice_asymmetric_model
from squid_game.posthoc.verbal.reason_distribution import reason_distribution
from squid_game.posthoc.verbal.thinking_keywords import thinking_keyword_counts


def run_all_unit14_hypotheses(seasons):
    """Driver retained from posthoc.forfeit_regression for compatibility."""
    turn_df = turn_observations(seasons)
    event_df = forfeit_events(seasons)
    return {
        "H1_survival": run_h1_survival_hypothesis(turn_df),
        "H2_choice_asymmetric": fit_choice_asymmetric_model(turn_df),
        "reason_distribution": reason_distribution(event_df),
        "thinking_keywords": thinking_keyword_counts(event_df),
    }
```

(정확한 함수 시그니처는 원본에서 확인 후 일치시킴.)

- [ ] **Step B4.6: 원본 파일을 shim으로 교체**

```python
"""DEPRECATED: split into shared/frames + cognitive/choice_asymmetric
+ verbal/reason_distribution + verbal/thinking_keywords + composite/unit14_driver.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import warnings as _warnings
_warnings.warn(
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

- [ ] **Step B4.7: `posthoc/__init__.py` import 라인 교체**

forfeit_regression export ~10개를 5개 새 경로에서 가져오도록 갱신.

- [ ] **Step B4.8: 회귀 검증**

```bash
uv run pytest tests/unit/test_forfeit_regression.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

- [ ] **Step B4.9: End-to-end smoke (analyze_phase3)**

기존 outputs/ 중 하나 골라서:

```bash
ls outputs/final_results/ | head -3
# 가장 최근 디렉토리 하나 선택, e.g.:
uv run python scripts/posthoc/stats/analyze_phase3.py outputs/final_results/<latest>/ --model test
ls outputs/final_results/<latest>/phase3_analysis/
```

Expected: `unit14_results.md`, `unit15_results.md` 등 산출물 생성. DeprecationWarning은 scripts/가 아직 옛 경로 쓰면 나올 수 있음 — Phase D에서 정리.

- [ ] **Step B4.10: Commit**

```bash
git add src/squid_game/posthoc/
git commit -m "$(cat <<'EOF'
refactor(posthoc): split forfeit_regression across all 5 subpackages

turn_observations, forfeit_events → shared/frames;
fit_choice_asymmetric_model → cognitive/choice_asymmetric;
reason_distribution → verbal/reason_distribution;
thinking_keyword_counts → verbal/thinking_keywords;
run_all_unit14_hypotheses driver → composite/unit14_driver.
Original 951-line file becomes DeprecationWarning shim.

Phase B step 4 (largest single split).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B5: Phase B Gate

- [ ] **Step B5.1: 전체 pytest 통과**

```bash
uv run pytest tests/ -x --tb=short
```

- [ ] **Step B5.2: Smoke + analyze_phase3 end-to-end**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
uv run python scripts/posthoc/stats/analyze_phase3.py outputs/final_results/<latest>/ --model test
```

- [ ] **Step B5.3: 새 경로 import sanity**

```bash
uv run python -c "
from squid_game.posthoc.shared.frames import turn_observations, forfeit_events
from squid_game.posthoc.behavioral.forfeit_survival import run_h1_survival_hypothesis
from squid_game.posthoc.behavioral.forfeit_rate import test_h1_forfeit_rate
from squid_game.posthoc.verbal.discovery_detection import compute_discovery_turn
from squid_game.posthoc.verbal.discovery_timing import test_h4_discovery_delay
from squid_game.posthoc.verbal.reason_distribution import reason_distribution
from squid_game.posthoc.verbal.thinking_keywords import thinking_keyword_counts
from squid_game.posthoc.verbal.probe_independence import check_probe_independence
from squid_game.posthoc.cognitive.choice_asymmetric import fit_choice_asymmetric_model
from squid_game.posthoc.cognitive.tc_regression import fit_tc_model_a
from squid_game.posthoc.cognitive.ri_independence import check_ri_exceeds_baseline
from squid_game.posthoc.cognitive.post_discovery_engagement import test_h6_post_discovery_engagement
from squid_game.posthoc.composite.motivation import compute_motivation_components
from squid_game.posthoc.composite.unit13_hypotheses import run_all_unit13_hypotheses
from squid_game.posthoc.composite.unit14_driver import run_all_unit14_hypotheses
from squid_game.posthoc.composite.manipulation_check import check_accuracy_independence
print('Phase B all channel imports OK')
"
```

Expected: 0 warnings, "Phase B all channel imports OK".

(정확한 symbol 이름은 각 모듈의 실제 export에 맞춰 조정 — 일부 함수명은 다를 수 있음.)

---

## Phase C — Layer 분리 (game)

### Task C1: `game/reasoning/` 신설 + 7개 도메인 모듈 + prompts 이동

**Files:**
- Create: `src/squid_game/game/reasoning/__init__.py`
- Move: `src/squid_game/game/core/{forfeit,forfeit_layer,framing,survival,social,cot_collector,measurement,risk_choice_layer}.py` → `src/squid_game/game/reasoning/`
- Move: `src/squid_game/game/prompts/{framings,forfeit,forfeit_layer,probes,risk_layer,social}/` → `src/squid_game/game/reasoning/prompts/`
- Modify: 내부 callsite (`game/core/engine.py`, `game/core/turn.py`, `game/core/unified_turn.py`, `game/runner.py`)

- [ ] **Step C1.1: 사전 grep — prompts 경로 의존성 확인 (R1 리스크)**

```bash
grep -rn "prompts/framings\|prompts/forfeit\|prompts/social\|PromptLoader" src/squid_game/game/
```

`PromptLoader`나 Jinja `Environment(loader=FileSystemLoader(...))` 같은 곳에서 절대 경로를 쓰는지 확인. 절대 경로면 prompts 이동 후 동일 경로 조정 필요.

- [ ] **Step C1.2: `game/reasoning/__init__.py` 생성**

```python
"""Reasoning layer (X-axis) — preservation motive measurement.

Houses forfeit layer, framing manager, survival pressure schedule,
social context, CoT collector, measurement recorder, and risk choice
layer (legacy replay-only). Does not import from squid_game.game.task.
"""
```

- [ ] **Step C1.3: 8개 reasoning 모듈 이동 (git mv)**

```bash
git mv src/squid_game/game/core/forfeit.py src/squid_game/game/reasoning/forfeit.py
git mv src/squid_game/game/core/forfeit_layer.py src/squid_game/game/reasoning/forfeit_layer.py
git mv src/squid_game/game/core/framing.py src/squid_game/game/reasoning/framing.py
git mv src/squid_game/game/core/survival.py src/squid_game/game/reasoning/survival.py
git mv src/squid_game/game/core/social.py src/squid_game/game/reasoning/social.py
git mv src/squid_game/game/core/cot_collector.py src/squid_game/game/reasoning/cot_collector.py
git mv src/squid_game/game/core/measurement.py src/squid_game/game/reasoning/measurement.py
git mv src/squid_game/game/core/risk_choice_layer.py src/squid_game/game/reasoning/risk_choice_layer.py
```

- [ ] **Step C1.4: 8개 모듈 안의 self-import 갱신**

```bash
find src/squid_game/game/reasoning -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.core\.\(forfeit\|forfeit_layer\|framing\|survival\|social\|cot_collector\|measurement\|risk_choice_layer\) |from squid_game.game.reasoning.\1 |g' \
  -e 's|from squid_game.game.core import \(forfeit\|forfeit_layer\|framing\|survival\|social\|cot_collector\|measurement\|risk_choice_layer\)|from squid_game.game.reasoning import \1|g' \
  {} \;
find src/squid_game/game/reasoning -name "*.bak" -delete
```

- [ ] **Step C1.5: prompts 6개 디렉토리 이동**

```bash
mkdir -p src/squid_game/game/reasoning/prompts
git mv src/squid_game/game/prompts/framings src/squid_game/game/reasoning/prompts/framings
git mv src/squid_game/game/prompts/forfeit src/squid_game/game/reasoning/prompts/forfeit
git mv src/squid_game/game/prompts/forfeit_layer src/squid_game/game/reasoning/prompts/forfeit_layer
git mv src/squid_game/game/prompts/probes src/squid_game/game/reasoning/prompts/probes
git mv src/squid_game/game/prompts/risk_layer src/squid_game/game/reasoning/prompts/risk_layer
git mv src/squid_game/game/prompts/social src/squid_game/game/reasoning/prompts/social
```

- [ ] **Step C1.6: PromptLoader 경로 수정 (C1.1 grep 결과에 따라)**

PromptLoader가 `Path("squid_game/game/prompts")` 같은 경로를 쓰면 `Path("squid_game/game/reasoning/prompts")`로 갱신. importlib.resources 기반이면 패키지 경로 갱신.

가장 흔한 패턴: `framing.py` 안의 `TEMPLATE_DIR = Path(__file__).parent.parent / "prompts" / "framings"`. 이를 `Path(__file__).parent / "prompts" / "framings"`로 (`reasoning/` 안으로 들어왔으므로 한 단계 위가 아닌 같은 디렉토리).

- [ ] **Step C1.7: `game/core/*.py` 안의 reasoning 모듈 import 갱신 (engine, turn, unified_turn)**

```bash
find src/squid_game/game/core -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.core\.\(forfeit\|forfeit_layer\|framing\|survival\|social\|cot_collector\|measurement\|risk_choice_layer\) |from squid_game.game.reasoning.\1 |g' \
  {} \;
find src/squid_game/game/core -name "*.bak" -delete
```

- [ ] **Step C1.8: `game/core/__init__.py`를 reasoning-aware shim으로 교체**

`game/core/__init__.py`는 옛 `forfeit`/`framing`/`survival` 등을 export하던 곳. shim으로:

```python
"""DEPRECATED: 8 reasoning modules moved to squid_game.game.reasoning.
The remaining engine/turn/unified_turn modules will move to
squid_game.game.orchestration in Task C3.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "squid_game.game.core (reasoning modules) is deprecated; "
    "import from squid_game.game.reasoning instead.",
    DeprecationWarning, stacklevel=2,
)

# Alias 8 reasoning submodules
_REASONING_MODULES = (
    "forfeit", "forfeit_layer", "framing", "survival",
    "social", "cot_collector", "measurement", "risk_choice_layer",
)
for _name in _REASONING_MODULES:
    _module = __import__(f"squid_game.game.reasoning.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.core.{_name}"] = _module

del _sys, _warnings, _name, _module, _REASONING_MODULES
```

이 단계에서는 engine/turn/unified_turn은 아직 core/에 있음 (Task C3에서 이동). 따라서 shim은 reasoning 부분만 처리하고, engine/turn/unified_turn은 그대로 core/에 둠 → import도 그대로 작동.

- [ ] **Step C1.9: `game/prompts/__init__.py`를 reasoning-aware shim으로 만들기**

`game/prompts/`는 이제 (`tasks/`, `user_message/`)만 남아있음 + 다른 것들은 `reasoning/prompts/`로 이동. `game/prompts/__init__.py` 자체에 큰 코드가 없을 가능성이 높음 — grep로 확인:

```bash
cat src/squid_game/game/prompts/__init__.py 2>/dev/null
```

비어있거나 단순 docstring이면 shim 불필요. `from squid_game.game.prompts import framings` 같은 deep import를 대비해 sys.modules alias 추가:

```python
"""DEPRECATED for reasoning prompts subdirs (moved to reasoning/prompts/).
Tasks/user_message will move to task/prompts/ in Task C2.
"""
import sys as _sys
_REASONING_PROMPTS = ("framings", "forfeit", "forfeit_layer", "probes", "risk_layer", "social")
for _name in _REASONING_PROMPTS:
    _module = __import__(f"squid_game.game.reasoning.prompts.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.prompts.{_name}"] = _module
del _sys, _name, _module, _REASONING_PROMPTS
```

(prompts 하위가 패키지로 import되는 케이스가 드물면 생략 가능. test에서 fail하면 그때 추가.)

- [ ] **Step C1.10: 회귀 검증**

```bash
uv run pytest tests/unit/test_forfeit_layer.py tests/unit/test_forfeit_layer_templates.py \
  tests/unit/test_framing_templates.py tests/unit/test_split_forfeit_prompts.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

Expected: 모두 통과 (특히 prompts template 관련 테스트가 통과해야 PromptLoader 경로가 맞음).

- [ ] **Step C1.11: Smoke dry-run**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
```

Expected: prompt rendering 단계까지 통과.

- [ ] **Step C1.12: Commit**

```bash
git add src/squid_game/game/
git commit -m "$(cat <<'EOF'
refactor(game): create reasoning/ slot + move 8 X-axis modules + prompts

Move forfeit, forfeit_layer, framing, survival, social, cot_collector,
measurement, risk_choice_layer to game/reasoning/. Move 6 prompt subdirs
(framings, forfeit, forfeit_layer, probes, risk_layer, social) to
reasoning/prompts/. Internal callsites + PromptLoader paths updated.
game/core and game/prompts get DeprecationWarning shims.

Phase C step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C2: `game/task/` 신설 + tasks 이동 + prompts/tasks 이동

**Files:**
- Create: `src/squid_game/game/task/__init__.py`
- Move: `src/squid_game/game/tasks/*` → `src/squid_game/game/task/`
- Move: `src/squid_game/game/prompts/{tasks,user_message}` → `src/squid_game/game/task/prompts/`
- Shim: `src/squid_game/game/tasks/__init__.py` 재생성
- Modify: 내부 callsite (engine.py, turn.py, unified_turn.py, 모든 task 모듈)

- [ ] **Step C2.1: tasks/ 내부 self-import 패턴 확인**

```bash
grep -rn "from squid_game.game.tasks" src/squid_game/game/
```

- [ ] **Step C2.2: `game/task/__init__.py` 생성**

```python
"""Task layer (Y-axis) — cognitive ability environments.

Houses Task base + registry + 4 task implementations
(signal_game, voting_room, navigation, null_task). Does not import
from squid_game.game.reasoning.
"""
```

- [ ] **Step C2.3: tasks/ 전체 이동 + 디렉토리명 변경 (plural → singular)**

```bash
git mv src/squid_game/game/tasks/base.py src/squid_game/game/task/base.py
git mv src/squid_game/game/tasks/registry.py src/squid_game/game/task/registry.py
git mv src/squid_game/game/tasks/signal_game src/squid_game/game/task/signal_game
git mv src/squid_game/game/tasks/voting_room src/squid_game/game/task/voting_room
git mv src/squid_game/game/tasks/navigation src/squid_game/game/task/navigation
git mv src/squid_game/game/tasks/null_task src/squid_game/game/task/null_task
```

(원본 `tasks/__init__.py`는 shim용으로 다음 step에서 재생성)

- [ ] **Step C2.4: 이동된 task 모듈 안의 self-import 갱신**

```bash
find src/squid_game/game/task -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.tasks\.|from squid_game.game.task.|g' \
  -e 's|from squid_game.game.tasks import|from squid_game.game.task import|g' \
  {} \;
find src/squid_game/game/task -name "*.bak" -delete
```

- [ ] **Step C2.5: prompts/tasks + prompts/user_message 이동**

```bash
mkdir -p src/squid_game/game/task/prompts
git mv src/squid_game/game/prompts/tasks src/squid_game/game/task/prompts/tasks
git mv src/squid_game/game/prompts/user_message src/squid_game/game/task/prompts/user_message
```

- [ ] **Step C2.6: task 모듈의 PromptLoader 경로 수정**

C1.1 grep과 유사하게 task 모듈이 `prompts/tasks/...` 같은 경로를 쓰는지 확인:

```bash
grep -rn "prompts/tasks\|prompts/user_message" src/squid_game/game/task/
```

발견되는 경로를 `prompts/tasks` (task/prompts/ 하위로 들어왔으므로 task 모듈 기준 상대경로) 로 갱신.

- [ ] **Step C2.7: `game/core/*.py` 안의 tasks import 갱신**

```bash
find src/squid_game/game/core -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.tasks\.|from squid_game.game.task.|g' \
  -e 's|from squid_game.game.tasks import|from squid_game.game.task import|g' \
  {} \;
find src/squid_game/game/core -name "*.bak" -delete
```

`runner.py` (game/ 루트) 도 동일 처리:

```bash
sed -i.bak \
  -e 's|from squid_game.game.tasks\.|from squid_game.game.task.|g' \
  -e 's|from squid_game.game.tasks import|from squid_game.game.task import|g' \
  src/squid_game/game/runner.py
rm src/squid_game/game/runner.py.bak
```

- [ ] **Step C2.8: `game/tasks/__init__.py` shim 재생성**

```bash
mkdir -p src/squid_game/game/tasks
```

```python
# src/squid_game/game/tasks/__init__.py
"""DEPRECATED: use ``squid_game.game.task`` (singular) instead.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import sys as _sys
import warnings as _warnings

_warnings.warn(
    "squid_game.game.tasks is deprecated; "
    "import from squid_game.game.task (singular) instead.",
    DeprecationWarning, stacklevel=2,
)

from squid_game.game.task import *  # noqa: F401, F403

_SUBMODULES = ("base", "registry", "signal_game", "voting_room", "navigation", "null_task")
for _name in _SUBMODULES:
    _module = __import__(f"squid_game.game.task.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.tasks.{_name}"] = _module
    # signal_game.module 같은 deep imports 도 alias 필요
    if _name in ("signal_game", "voting_room", "navigation", "null_task"):
        try:
            _submod = __import__(f"squid_game.game.task.{_name}.module", fromlist=["*"])
            _sys.modules[f"squid_game.game.tasks.{_name}.module"] = _submod
        except ImportError:
            pass

del _sys, _warnings, _name, _module, _SUBMODULES
```

- [ ] **Step C2.9: `game/prompts/__init__.py` shim 갱신 (tasks/user_message 추가)**

C1.9에서 만든 shim에 추가:

```python
# 기존 _REASONING_PROMPTS 아래에 추가
_TASK_PROMPTS = ("tasks", "user_message")
for _name in _TASK_PROMPTS:
    _module = __import__(f"squid_game.game.task.prompts.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.prompts.{_name}"] = _module
```

- [ ] **Step C2.10: 회귀 검증**

```bash
uv run pytest tests/unit/test_null_task.py tests/unit/test_signal_game_v3.py \
  tests/unit/test_engine_unified.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

- [ ] **Step C2.11: Smoke dry-run**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
```

- [ ] **Step C2.12: Commit**

```bash
git add src/squid_game/game/
git commit -m "$(cat <<'EOF'
refactor(game): create task/ slot (singular) + move tasks/* + task prompts

Move tasks/{base,registry,signal_game,voting_room,navigation,null_task}
to game/task/. Move prompts/{tasks,user_message} to game/task/prompts/.
Internal callsites + PromptLoader paths updated. game/tasks (plural)
becomes DeprecationWarning shim with submodule aliasing for deep imports.

Phase C step 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C3: `game/orchestration/` 신설 + engine/turn/unified_turn/runner 이동

**Files:**
- Create: `src/squid_game/game/orchestration/__init__.py`
- Move: `src/squid_game/game/core/{engine,turn,unified_turn}.py` → `src/squid_game/game/orchestration/`
- Move: `src/squid_game/game/runner.py` → `src/squid_game/game/orchestration/runner.py`
- Shim: `src/squid_game/game/core/__init__.py` (C1.8에서 만든 것 갱신 — orchestration aliasing 추가), `src/squid_game/game/runner.py` (재생성)
- Modify: `src/squid_game/runner.py` (패키지 루트 shim — 이미 있는 것)

- [ ] **Step C3.1: `game/orchestration/__init__.py` 생성**

```python
"""Orchestration layer — cross-axis composers.

Houses the GameEngine, TurnManager (legacy probe path), UnifiedTurnManager
(Split-Call path), and ExperimentRunner. These are the only modules
allowed to import from both reasoning/ and task/.
"""
```

- [ ] **Step C3.2: 4개 모듈 이동**

```bash
git mv src/squid_game/game/core/engine.py src/squid_game/game/orchestration/engine.py
git mv src/squid_game/game/core/turn.py src/squid_game/game/orchestration/turn.py
git mv src/squid_game/game/core/unified_turn.py src/squid_game/game/orchestration/unified_turn.py
git mv src/squid_game/game/runner.py src/squid_game/game/orchestration/runner.py
```

- [ ] **Step C3.3: orchestration 모듈 안의 cross-reference 갱신**

```bash
find src/squid_game/game/orchestration -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.core.engine |from squid_game.game.orchestration.engine |g' \
  -e 's|from squid_game.game.core.turn |from squid_game.game.orchestration.turn |g' \
  -e 's|from squid_game.game.core.unified_turn |from squid_game.game.orchestration.unified_turn |g' \
  -e 's|from squid_game.game.runner |from squid_game.game.orchestration.runner |g' \
  {} \;
find src/squid_game/game/orchestration -name "*.bak" -delete
```

- [ ] **Step C3.4: `game/core/__init__.py` shim 갱신 (orchestration 추가)**

C1.8에서 만든 shim에 추가:

```python
# C1.8 _REASONING_MODULES 아래에 추가
_ORCHESTRATION_MODULES = ("engine", "turn", "unified_turn")
for _name in _ORCHESTRATION_MODULES:
    _module = __import__(f"squid_game.game.orchestration.{_name}", fromlist=["*"])
    _sys.modules[f"squid_game.game.core.{_name}"] = _module
```

- [ ] **Step C3.5: `game/runner.py` shim 재생성**

```python
# src/squid_game/game/runner.py
"""DEPRECATED: use ``squid_game.game.orchestration.runner`` instead.

Backward-compatibility shim. Removal target: 2026 Q4 (post-KDD).
"""
import warnings as _warnings
_warnings.warn(
    "squid_game.game.runner is deprecated; "
    "import from squid_game.game.orchestration.runner instead.",
    DeprecationWarning, stacklevel=2,
)
from squid_game.game.orchestration.runner import *  # noqa: F401, F403
```

- [ ] **Step C3.6: 패키지 루트 `src/squid_game/runner.py` (이미 shim) 확인**

이미 shim으로 존재하는지 확인:

```bash
cat src/squid_game/runner.py
```

`from squid_game.game.runner import *` 같은 형태면 한 단계 더 들어가 `squid_game.game.orchestration.runner`를 가리키도록 갱신:

```python
"""DEPRECATED: use ``squid_game.game.orchestration.runner`` instead."""
import warnings as _warnings
_warnings.warn(
    "squid_game.runner is deprecated; "
    "import from squid_game.game.orchestration.runner instead.",
    DeprecationWarning, stacklevel=2,
)
from squid_game.game.orchestration.runner import *  # noqa: F401, F403
```

- [ ] **Step C3.7: `main.py` 의 import 갱신**

```bash
cat main.py
```

`from squid_game.runner import ...` 또는 `from squid_game.game.runner import ...` 라면 새 경로로 직접 교체:

```python
# main.py
from squid_game.game.orchestration.runner import ExperimentRunner  # 또는 그 모듈의 실제 entry
```

- [ ] **Step C3.8: 회귀 검증**

```bash
uv run pytest tests/unit/test_engine_unified.py tests/unit/test_unified_turn.py \
  tests/integration/test_unified_turn.py -x -v
uv run pytest tests/ -x --tb=short 2>&1 | tail -10
```

- [ ] **Step C3.9: Smoke dry-run**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
uv run python main.py --config configs/experiment/phase3_psuccess_probe_smoke.yaml --dry-run
```

- [ ] **Step C3.10: Boundary 정적 검증 (reasoning ↔ task 상호 import 0)**

```bash
echo "=== reasoning → task imports (should be 0) ==="
grep -rn "from squid_game.game.task" src/squid_game/game/reasoning/ || echo "0건 ✅"
echo "=== task → reasoning imports (should be 0) ==="
grep -rn "from squid_game.game.reasoning" src/squid_game/game/task/ || echo "0건 ✅"
echo "=== infra → reasoning/task imports (should be 0) ==="
grep -rn "from squid_game.game.\(reasoning\|task\)" src/squid_game/game/infra/ || echo "0건 ✅"
```

Expected: 3개 모두 0건. 1건이라도 나오면 그건 직교성 위반 → 해당 import를 의존성 역전 (interface를 shared/에 두거나, 호출 위치를 orchestration/으로 옮기기).

- [ ] **Step C3.11: Commit**

```bash
git add src/squid_game/ main.py
git commit -m "$(cat <<'EOF'
refactor(game): create orchestration/ slot + move engine/turn/unified_turn/runner

Move 4 cross-axis composers from game/core and game/ root to
game/orchestration/. unified_turn.py (1751 lines) moves verbatim
— internal decomposition deferred to follow-up PR.
game/core/__init__.py shim + game/runner.py shim updated. main.py
entry import switched to new path. Static boundary check confirms
reasoning ↔ task mutual imports = 0.

Phase C step 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C4: Phase C Gate

- [ ] **Step C4.1: 전체 pytest + smoke 통과**

```bash
uv run pytest tests/ -x --tb=short
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
```

- [ ] **Step C4.2: Boundary 재검증 (C3.10과 동일)**

```bash
grep -rn "from squid_game.game.task" src/squid_game/game/reasoning/
grep -rn "from squid_game.game.reasoning" src/squid_game/game/task/
grep -rn "from squid_game.game.\(reasoning\|task\)" src/squid_game/game/infra/
```

Expected: 3 commands return nothing.

- [ ] **Step C4.3: 새 경로 import sanity**

```bash
uv run python -c "
from squid_game.game.reasoning.forfeit_layer import ForfeitLayer
from squid_game.game.reasoning.framing import FramingManager
from squid_game.game.task.signal_game.module import SignalGameModule
from squid_game.game.task.null_task import NullTask
from squid_game.game.orchestration.engine import GameEngine
from squid_game.game.orchestration.runner import ExperimentRunner
from squid_game.game.infra.agents.base import Agent
from squid_game.game.infra.providers.base import CompletionResult
print('Phase C all paths OK')
" 2>&1
```

Expected: 0 warnings, "Phase C all paths OK".

---

## Phase D — 외부 callsite 정리

### Task D1: `scripts/` import 갱신

**Files:** 15개 scripts

- [ ] **Step D1.1: 영향 받는 scripts 목록 확정**

```bash
grep -l "from squid_game" scripts/ -r 2>/dev/null | sort
```

Expected: 15개 (game 8개 + posthoc 7개).

- [ ] **Step D1.2: scripts/game/ 8개 파일 일괄 sed 갱신**

```bash
find scripts/game -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.game.core\.\(forfeit\|forfeit_layer\|framing\|survival\|social\|cot_collector\|measurement\|risk_choice_layer\)|from squid_game.game.reasoning.\1|g' \
  -e 's|from squid_game.game.core\.\(engine\|turn\|unified_turn\)|from squid_game.game.orchestration.\1|g' \
  -e 's|from squid_game.game.agents|from squid_game.game.infra.agents|g' \
  -e 's|from squid_game.game.providers|from squid_game.game.infra.providers|g' \
  -e 's|from squid_game.game.tasks\.|from squid_game.game.task.|g' \
  -e 's|from squid_game.game.tasks import|from squid_game.game.task import|g' \
  -e 's|from squid_game.game.runner|from squid_game.game.orchestration.runner|g' \
  {} \;
find scripts/game -name "*.bak" -delete
```

- [ ] **Step D1.3: scripts/posthoc/ 7개 파일 일괄 sed 갱신**

```bash
find scripts/posthoc -name "*.py" -exec sed -i.bak \
  -e 's|from squid_game.posthoc.\(loaders\|metrics\|export\|regime_stratification\)|from squid_game.posthoc.shared.\1|g' \
  -e 's|from squid_game.posthoc.forfeit_survival|from squid_game.posthoc.behavioral.forfeit_survival|g' \
  -e 's|from squid_game.posthoc.discovery_detection|from squid_game.posthoc.verbal.discovery_detection|g' \
  -e 's|from squid_game.posthoc.tc_regression|from squid_game.posthoc.cognitive.tc_regression|g' \
  -e 's|from squid_game.posthoc.motivation|from squid_game.posthoc.composite.motivation|g' \
  -e 's|from squid_game.posthoc.unit13_hypotheses|from squid_game.posthoc.composite.unit13_hypotheses|g' \
  -e 's|from squid_game.posthoc.manipulation_check|from squid_game.posthoc.composite.manipulation_check|g' \
  {} \;
find scripts/posthoc -name "*.bak" -delete
```

`forfeit_regression`의 경우 한 모듈이 5개 새 경로로 흩어졌으므로 sed로 일괄 처리 불가. grep으로 사용처 파악 후 수동 갱신:

```bash
grep -rn "from squid_game.posthoc.forfeit_regression import" scripts/
```

각 발견 라인을 `import` 대상 함수에 따라 (turn_observations → shared.frames, fit_choice_asymmetric_model → cognitive.choice_asymmetric, ...) 분배.

- [ ] **Step D1.4: 갱신 검증 — shim 경로 0건 확인**

```bash
grep -rn "from squid_game.posthoc.forfeit_regression\|from squid_game.posthoc.forfeit_survival\|from squid_game.posthoc.discovery_detection\|from squid_game.posthoc.motivation\|from squid_game.posthoc.tc_regression\|from squid_game.posthoc.unit13_hypotheses\|from squid_game.posthoc.manipulation_check\|from squid_game.posthoc.metrics\|from squid_game.posthoc.loaders\|from squid_game.posthoc.export\|from squid_game.posthoc.regime_stratification" scripts/
grep -rn "from squid_game.game.core\|from squid_game.game.tasks\b\|from squid_game.game.agents\b\|from squid_game.game.providers\b" scripts/
```

Expected: 모두 0건.

- [ ] **Step D1.5: scripts 실행 회귀 (대표 한두 개)**

```bash
uv run python scripts/game/run_experiment.py --help
uv run python scripts/posthoc/stats/analyze_phase3.py --help
```

Expected: usage 출력 + DeprecationWarning 0건.

- [ ] **Step D1.6: Commit**

```bash
git add scripts/
git commit -m "$(cat <<'EOF'
refactor(scripts): update all 15 callsites to new channel-split paths

Replace shim imports with direct paths into:
- game/{reasoning,task,orchestration,infra}/...
- posthoc/{shared,behavioral,verbal,cognitive,composite}/...

Phase D step 1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D2: `tests/` import 갱신 + 디렉토리 미러링

**Files:** 35개 tests (30 unit + 5 integration)

- [ ] **Step D2.1: 영향 범위 확인**

```bash
grep -l "from squid_game" tests/ -r | sort
```

35개 파일 예상.

- [ ] **Step D2.2: 일괄 sed 갱신 (D1.2/D1.3과 동일 패턴, 대상은 tests/)**

D1.2와 D1.3의 sed 명령을 `scripts/` 대신 `tests/`로 돌린다 (4개 명령 — game module sed, posthoc shared sed, posthoc single-move sed, posthoc forfeit_regression 수동 — 차례로 실행).

- [ ] **Step D2.3: forfeit_regression 분산 import 수동 갱신**

```bash
grep -n "from squid_game.posthoc.forfeit_regression" tests/unit/test_forfeit_regression.py
```

각 import line을 새 경로로 분배:
- `turn_observations`, `forfeit_events` → `from squid_game.posthoc.shared.frames import ...`
- `fit_choice_asymmetric_model` → `from squid_game.posthoc.cognitive.choice_asymmetric import ...`
- `reason_distribution` → `from squid_game.posthoc.verbal.reason_distribution import ...`
- `thinking_keyword_counts` → `from squid_game.posthoc.verbal.thinking_keywords import ...`
- `run_all_unit14_hypotheses` → `from squid_game.posthoc.composite.unit14_driver import ...`

`test_analysis_*` 파일들 (legacy shim 이름)도 동일 처리 — `squid_game.analysis` 사용처를 `squid_game.posthoc.*` 새 경로로 직접 갱신.

- [ ] **Step D2.4: Shim 경로 0건 검증**

```bash
grep -rn "from squid_game.posthoc.forfeit_regression\|from squid_game.posthoc.forfeit_survival\|from squid_game.posthoc.discovery_detection\|from squid_game.posthoc.motivation\|from squid_game.posthoc.tc_regression\|from squid_game.posthoc.unit13_hypotheses\|from squid_game.posthoc.manipulation_check\|from squid_game.posthoc.metrics\|from squid_game.posthoc.loaders\|from squid_game.posthoc.export\|from squid_game.posthoc.regime_stratification" tests/
grep -rn "from squid_game.game.core\|from squid_game.game.tasks\b\|from squid_game.game.agents\b\|from squid_game.game.providers\b\|from squid_game.game.runner\b" tests/
grep -rn "from squid_game.analysis" tests/
```

Expected: 모두 0건.

- [ ] **Step D2.5: 회귀 검증**

```bash
uv run pytest tests/ -x --tb=short
```

Expected: 전체 통과.

- [ ] **Step D2.6: tests/ 디렉토리 미러링 (선택적 — 큰 변경)**

이 step은 보수적으로 둘 중 하나 선택:

**옵션 6a (보수): tests/ 트리 그대로 유지** — import만 갱신, 파일 위치는 변경 없음. 단점: 어떤 채널을 테스트하는지 디렉토리에서 안 보임.

**옵션 6b (적극): tests/posthoc/{shared,behavioral,verbal,cognitive,composite}/ + tests/game/{reasoning,task,orchestration,infra}/ 로 mirror** — 디렉토리 미러링.

옵션 6b 선택 시:
```bash
mkdir -p tests/posthoc/{shared,behavioral,verbal,cognitive,composite}
mkdir -p tests/game/{reasoning,task,orchestration,infra}
mkdir -p tests/integration  # 이미 존재
# 매핑 (예시 — 실제 파일명에 맞춰):
git mv tests/unit/test_regime_stratification.py tests/posthoc/shared/test_regime_stratification.py
git mv tests/unit/test_analysis_loaders.py tests/posthoc/shared/test_loaders.py
git mv tests/unit/test_discovery_detection.py tests/posthoc/verbal/test_discovery_detection.py
git mv tests/unit/test_probe_independence.py tests/posthoc/verbal/test_probe_independence.py
git mv tests/unit/test_forfeit_regression.py tests/posthoc/cognitive/test_choice_asymmetric.py
git mv tests/unit/test_unit13_hypotheses.py tests/posthoc/composite/test_unit13_hypotheses.py
git mv tests/unit/test_analysis_phase3.py tests/posthoc/composite/test_unit14_driver.py
git mv tests/unit/test_analyze_phase3_jsonable.py tests/posthoc/composite/test_analyze_phase3_jsonable.py
git mv tests/unit/test_forfeit_layer.py tests/game/reasoning/test_forfeit_layer.py
git mv tests/unit/test_forfeit_layer_templates.py tests/game/reasoning/test_forfeit_layer_templates.py
git mv tests/unit/test_forfeit_layer_config_yaml.py tests/game/reasoning/test_forfeit_layer_config_yaml.py
git mv tests/unit/test_framing_templates.py tests/game/reasoning/test_framing_templates.py
git mv tests/unit/test_split_forfeit_prompts.py tests/game/reasoning/test_split_forfeit_prompts.py
git mv tests/unit/test_split_forfeit_config_yaml.py tests/game/reasoning/test_split_forfeit_config_yaml.py
git mv tests/unit/test_risk_choice_layer.py tests/game/reasoning/test_risk_choice_layer.py
git mv tests/unit/test_stake_carryover.py tests/game/reasoning/test_stake_carryover.py
git mv tests/unit/test_null_task.py tests/game/task/test_null_task.py
git mv tests/unit/test_signal_game_v3.py tests/game/task/test_signal_game_v3.py
git mv tests/unit/test_engine_unified.py tests/game/orchestration/test_engine_unified.py
git mv tests/unit/test_unified_turn.py tests/game/orchestration/test_unified_turn.py
git mv tests/unit/test_unified_turn_forfeit_layer.py tests/game/orchestration/test_unified_turn_forfeit_layer.py
git mv tests/unit/test_unified_turn_split_forfeit_layer.py tests/game/orchestration/test_unified_turn_split_forfeit_layer.py
git mv tests/unit/test_unified_parsing.py tests/game/orchestration/test_unified_parsing.py
git mv tests/unit/test_runner_yaml_forfeit_layer.py tests/game/orchestration/test_runner_yaml_forfeit_layer.py
git mv tests/unit/test_phase3_configs.py tests/game/orchestration/test_phase3_configs.py
git mv tests/unit/test_config_v3.py tests/game/orchestration/test_config_v3.py
git mv tests/unit/test_forfeit_choice_models.py tests/shared/test_forfeit_choice_models.py
git mv tests/unit/_analysis_factories.py tests/posthoc/_analysis_factories.py
```

(정확한 매핑은 각 테스트 파일이 실제로 무엇을 import하는지 확인 후 결정. shared/ 미존재 디렉토리는 mkdir.)

각 신규 디렉토리에 `__init__.py` 빈 파일 추가.

**권장: 옵션 6a (보수)**로 일단 진행하고, 옵션 6b는 follow-up PR. 한 PR에 너무 큰 변경 (35개 파일 위치 변경 + 디렉토리 재구성)이 들어가면 review가 어려움.

- [ ] **Step D2.7: 회귀 검증 (옵션 6a 또는 6b 적용 후)**

```bash
uv run pytest tests/ -x --tb=short
```

- [ ] **Step D2.8: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
refactor(tests): update 35 test files to new channel-split import paths

Replace all shim imports (posthoc.{forfeit_regression,...}, game.{core,
tasks,agents,providers,runner}, analysis.*) with direct new-path imports.

[옵션 6b 선택 시 추가 라인]
Mirror tests/ tree to src/: tests/posthoc/{shared,behavioral,verbal,
cognitive,composite}/, tests/game/{reasoning,task,orchestration,infra}/.

Phase D step 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D3: CLAUDE.md "Directory Structure" 섹션 갱신

**Files:**
- Modify: `CLAUDE.md` (Directory Structure 섹션 — README와 동기화도 같이)
- Modify: `README.md` (동일 섹션)

- [ ] **Step D3.1: README.md의 현재 Directory Structure 섹션 확인**

```bash
grep -n "Directory Structure\|src/squid_game/" README.md | head -20
```

- [ ] **Step D3.2: 새 구조로 갱신**

기존 ASCII 트리를 spec §2의 새 트리로 교체. 다음 핵심 변경:
- `game/core/` 사라짐 (shim만 남음)
- `game/{reasoning,task,orchestration,infra}/` 추가
- `posthoc/` 5개 채널 subpackage 추가

Module boundary 문장도 갱신:
```
**Module boundary**:
- squid_game.game.reasoning ↔ squid_game.game.task: 상호 import 금지
- squid_game.game.orchestration만 양쪽을 import 가능
- squid_game.posthoc.{behavioral,verbal,cognitive} 상호 import 금지
- squid_game.posthoc.composite만 다른 3채널을 import 가능
- 모두 squid_game.shared만 의존
정적 검증: `grep -rn "from squid_game.game.task" src/squid_game/game/reasoning/` 등 0건.
```

- [ ] **Step D3.3: CLAUDE.md의 동일 섹션 갱신**

CLAUDE.md는 README보다 상위 위치에 같은 정보를 두므로 동일 트리 + boundary 문장 적용. README가 CLAUDE.md를 참조하는 구조라면 README는 trimming.

- [ ] **Step D3.4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update Directory Structure for channel-split refactor

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D4: Phase D Final Gate (Acceptance Criteria 검증)

Spec §9의 7개 acceptance criteria 모두 통과 확인.

- [ ] **Step D4.1: pytest 전체 통과 (Criterion 1)**

```bash
uv run pytest tests/ -v 2>&1 | tail -20
```

Expected: All pass.

- [ ] **Step D4.2: Smoke 2종 통과 (Criterion 2)**

```bash
uv run python main.py --config configs/experiment/phase3_split_forfeit_smoke.yaml --dry-run
uv run python main.py --config configs/experiment/phase3_psuccess_probe_smoke.yaml --dry-run
```

- [ ] **Step D4.3: shim 경로 사용 0건 (Criterion 3) — src/scripts/tests 범위**

```bash
SHIM_PATHS="from squid_game.posthoc.forfeit_regression\|from squid_game.posthoc.forfeit_survival\|from squid_game.posthoc.discovery_detection\|from squid_game.posthoc.motivation\|from squid_game.posthoc.tc_regression\|from squid_game.posthoc.unit13_hypotheses\|from squid_game.posthoc.manipulation_check\|from squid_game.posthoc.metrics\|from squid_game.posthoc.loaders\|from squid_game.posthoc.export\|from squid_game.posthoc.regime_stratification\|from squid_game.game.core\|from squid_game.game.tasks\b\|from squid_game.game.agents\b\|from squid_game.game.providers\b\|from squid_game.game.runner\b\|from squid_game.analysis\b"

grep -rn "$SHIM_PATHS" src/squid_game/ --include="*.py" | grep -v "/posthoc/forfeit_regression.py\|/posthoc/forfeit_survival.py\|/posthoc/discovery_detection.py\|/posthoc/motivation.py\|/posthoc/tc_regression.py\|/posthoc/unit13_hypotheses.py\|/posthoc/manipulation_check.py\|/posthoc/metrics.py\|/posthoc/loaders.py\|/posthoc/export.py\|/posthoc/regime_stratification.py\|/game/core/__init__.py\|/game/tasks/__init__.py\|/game/agents/__init__.py\|/game/providers/__init__.py\|/game/runner.py\|/game/prompts/__init__.py\|/runner.py\|/analysis/__init__.py"
grep -rn "$SHIM_PATHS" scripts/ tests/ --include="*.py"
```

(첫 grep은 shim 파일 자체를 제외 — shim은 옛 경로에서 새 경로로 import하는 게 정상이므로)

Expected: 모두 0건.

- [ ] **Step D4.4: Reasoning ↔ Task 직교성 (Criterion 4)**

```bash
grep -rn "from squid_game.game.task" src/squid_game/game/reasoning/ && echo "FAIL: reasoning imports task" || echo "PASS"
grep -rn "from squid_game.game.reasoning" src/squid_game/game/task/ && echo "FAIL: task imports reasoning" || echo "PASS"
grep -rn "from squid_game.posthoc.\(behavioral\|verbal\|cognitive\)" src/squid_game/posthoc/behavioral/ src/squid_game/posthoc/verbal/ src/squid_game/posthoc/cognitive/ | grep -v "shared\|composite" && echo "FAIL: cross-channel" || echo "PASS"
```

Expected: 3 PASS lines.

- [ ] **Step D4.5: analyze_phase3 end-to-end (Criterion 5)**

```bash
LATEST=$(ls -t outputs/final_results/ | head -1)
uv run python scripts/posthoc/stats/analyze_phase3.py outputs/final_results/$LATEST/ --model test
ls outputs/final_results/$LATEST/phase3_analysis/
```

Expected: `unit14_results.md`, `unit15_results.md`, `regime_stratified_results.md`, `manipulation_check.md`, `unit13_results.md` + CSV/JSON outputs 생성.

- [ ] **Step D4.6: CLAUDE.md 업데이트 확인 (Criterion 6)**

```bash
grep -A2 "src/squid_game/" CLAUDE.md | grep "reasoning\|task\|orchestration\|infra\|behavioral\|verbal\|cognitive\|composite"
```

Expected: 새 디렉토리 이름들이 표시됨.

- [ ] **Step D4.7: src/scripts/tests 실행 시 DeprecationWarning 0건 (Criterion 7)**

```bash
uv run pytest tests/ -W error::DeprecationWarning -x 2>&1 | grep -i "deprecation" | head -5
uv run python -W error::DeprecationWarning scripts/posthoc/stats/analyze_phase3.py --help 2>&1 | grep -i "deprecation" | head -5
```

Expected: 0건 출력 (warning을 error로 승격해서 발생하면 즉시 fail).

- [ ] **Step D4.8: 최종 commit (없으면 skip)**

만약 Gate 단계에서 자잘한 수정이 생겼다면:

```bash
git status -sb
# 변경 있으면:
git add -p
git commit -m "fix: address final gate findings for channel-split refactor

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (writing-plans 체크리스트)

### Spec coverage 검증

| Spec 섹션 | 대응 task |
|-----------|-----------|
| §2 새 top-level layout | A1, A2, B1, C1, C2, C3 (디렉토리 신설 step들) |
| §3 game/ 상세 + 이동표 | C1 (reasoning), C2 (task), C3 (orchestration), A2 (infra) |
| §3-2 Import 방향 규칙 | C3.10, C4.2, D4.4 (boundary grep) |
| §4 posthoc/ 상세 + 이동표 | A1 (shared), B1 (4 single moves), B2 (unit13), B3 (manipulation_check), B4 (forfeit_regression) |
| §4-3 Import 방향 규칙 | D4.4 |
| §5 Shim 전략 | 각 이동 task의 shim step (A1.5, A2.6, B1.4, B2.6, B3.5, B4.6, C1.8, C1.9, C2.8, C2.9, C3.4, C3.5, C3.6) |
| §6 scripts/tests 업데이트 | D1 (scripts), D2 (tests) |
| §7 Phase 시퀀싱 | Phase A/B/C/D 구조 그대로 |
| §8-1 R1-R4 리스크 | R1 → C1.1+C1.6, R2 → B4.1, R3 → A1.7, R4 → 각 step의 `posthoc/__init__.py` 갱신 |
| §8-2 Q1-Q3 (미확정) | Q1: B2에서 "완전 분할" 선택 + Plan에 명시 / Q2: B3.4 driver 디자인 / Q3: C1.3에서 risk_choice_layer 그대로 reasoning/에, 별도 legacy/ slot 미생성 |
| §9 Acceptance Criteria | D4 (7개 criterion 각각 step) |

→ 모든 spec 섹션이 적어도 하나의 task에 대응됨. ✅

### Placeholder scan

- "TBD", "TODO", "implement later" 검색: 없음 ✅
- 각 step에 exact command 있음 ✅
- 각 shim에 exact 코드 있음 ✅
- 단 `<latest>` 같은 변수는 step 안에서 `LATEST=$(ls -t ... | head -1)` 같이 결정 가능 ✅

### Type/signature 일관성

- `run_all_unit13_hypotheses`, `run_all_unit14_hypotheses` 시그니처는 B2.5/B4.5에서 명시한 것을 shim도 그대로 export — 일관.
- 각 shim의 `_SUBMODULES` 목록과 실제 source 모듈의 파일명이 일치 — 일관.
- C2.3에서 `tasks/` (plural) → `task/` (singular) rename은 spec §3-1과 일치 ✅

### 예외 처리

- C2.8의 shim에서 deep submodule alias (e.g., `signal_game.module`) 실패 시 ImportError를 silently catch — task 모듈마다 `module.py` 존재 패턴이 달라서 (확인 필요). 만약 모든 task가 동일 구조면 try/except 제거 가능.

---

## 실행 권장

Plan 작성 완료. `docs/superpowers/plans/2026-05-21-game-posthoc-channel-split.md` 에 저장됨.

다음 단계로 다음 중 선택:

**1. Subagent-Driven (권장)** — 각 task당 fresh subagent dispatch, task 사이마다 review. 빠른 iteration, context 격리.

**2. Inline Execution** — 본 세션에서 executing-plans skill로 batch 실행, checkpoint마다 review.

사용자 원래 의도가 `iterative-code-loop` 사용이었으므로, iterative-code-loop는 위 두 모드 중 어느 쪽에서도 wrapper로 작동 가능 (각 task의 step을 cycle 단위로 굴림).

권장: **Subagent-Driven** — refactor task가 file mv + sed + shim 작성으로 잘 격리되어 있고, Phase 간 검증 gate가 명확하므로 subagent 격리가 큰 이득.
