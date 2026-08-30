# P2 분석 4채널 분해 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `squid_game/analysis/`의 15모듈 7,602줄을 측정 채널(인지 · 자기보고 · 행동 · 의미) 기준으로 재조립하고, 두 채널에 걸쳐 있는 두 모듈을 실제로 쪼갠다.

**Architecture:** 이동의 안전망은 **파사드**다. `squid_game/analysis/__init__.py`가 이미 모든 공개 심볼을 re-export 하고 있으므로, 그 파일의 import 줄만 새 경로로 갱신하면 파사드를 통해 들어오는 호출자는 한 줄도 바뀌지 않는다. 다만 실측 결과 서브모듈을 직접 import 하는 곳이 45군데 있으므로(`squid_game.analysis.forfeit_regression` 7건, `.threat_judge` 9건 등), 각 태스크는 자기가 옮긴 모듈의 직접 import만 `sed`로 좁혀 치환한다. 순서는 위험도 순이다: 먼저 통째로 옮기면 되는 모듈들(shared · behavioral · cognitive · semantic), 그 다음 진짜 분할이 필요한 두 모듈(`forfeit_regression` 952줄, `regime_stratification` 656줄), 마지막이 채널 위에 서는 MTMM 종합기다. 매 태스크의 판정은 골든 스냅샷 84개 산출물의 바이트 동일성이다 — 분해가 수치를 건드렸다면 그 자리에서 드러난다.

**Tech Stack:** Python 3.12, pandas, statsmodels (mixedLM), lifelines (Cox PH), scipy, sentence-transformers + scikit-learn (semantic 채널), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md` (§3.2 분석 4채널 분해, §6 P2 행)

**선행 조건:** P1 완료. 이 계획의 모든 경로는 P1 이후 기준이다 — 분석 코드는 `game/squid_game/analysis/`에 있다.

## Global Constraints

- 작업 디렉터리는 워크트리 `<repo>/.claude/worktrees/squid-restructure`, 브랜치 `restructure/3tier`.
- **통계 모델 식을 건드리지 않는다.** mixedLM formula 문자열, Cox PH covariate 목록, 부트스트랩 반복 수, 시드, 유의수준은 옮기기만 하고 한 글자도 바꾸지 않는다. 이 작업은 구조 작업이지 분석 변경이 아니다.
- **골든 스냅샷이 최종 판정이다.** `uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure` → exit 0 + `84 deterministic artefacts`. 태스크마다 실행한다.
- 테스트 기준선은 P0 기준선(`958 passed, 91 skipped`)에 P1이 더한 신규 테스트를 합한 값이다. 판정은 **신규 실패 0**.
- **파사드를 깨지 않는다.** `squid_game.analysis.__init__`의 `__all__`은 P2 전후로 동일해야 한다. 심볼을 추가할 수는 있으나 제거·개명하지 않는다.
- 모듈을 옮길 때는 `git mv`를 쓴다. 분할할 때는 `git mv`로 한쪽을 옮긴 뒤 나머지를 새 파일로 만들어, 최소한 한쪽의 rename 추적을 남긴다.
- **범위 밖:** R2 비례검정 구현, FDR 보정, 새 분석 추가. 스펙 §8이 명시적으로 배제한다.
- 커밋 메시지·코드·주석·문서는 영어. 대화 보고만 한국어.

## File Structure

P2 완료 시점:

```
game/squid_game/analysis/
  __init__.py                  # 파사드. __all__ 불변
  shared/
    loaders.py  export.py  metrics.py
    discovery_detection.py  manipulation_check.py
    mtmm.py                    # 구 motivation.py — 채널 추정기를 호출하는 종합기
  cognitive/                   # RI = thinking_tokens
    ri_forfeit.py  ri_task.py  ri_call1.py
  selfreport/                  # REASON digit, psuccess_self
    reason_convergence.py  psuccess.py
  behavioral/                  # 선택 · 생존
    survival.py  regime.py  session_tests.py  baseline_persistence.py
  semantic/                    # 텍스트 · 임베딩
    dataset.py  embeddings.py  lexicon.py
    threat_registration.py  threat_judge.py
```

`scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py`, `scripts/analyze_call1_ri.py`는 얇은 CLI만 남고 로직은 위로 올라간다. `scripts/_ri_dataset.py`는 사라진다(`semantic/dataset.py`가 된다).

---

### Task 1: `shared/` 하위 패키지 — 채널이 공유하는 것부터

다섯 모듈은 채널에 속하지 않는다. 데이터 적재(`loaders`), 산출(`export`), 기술통계(`metrics`), 규칙 발견 탐지(`discovery_detection`), 조작 점검(`manipulation_check`)은 세 채널이 모두 소비한다. 먼저 이들을 `shared/`로 내려 채널 디렉터리가 생길 자리를 만든다.

**Files:**
- Move: `analysis/{loaders,export,metrics,discovery_detection,manipulation_check}.py` → `analysis/shared/`
- Create: `analysis/shared/__init__.py`
- Modify: `analysis/__init__.py` (import 경로 5줄)
- Modify: 직접 import 하는 외부 호출자 (`loaders` 4건, `manipulation_check` 4건, `metrics` 1건, `export` 1건, `discovery_detection` 1건)
- Modify: `analysis/` 내부에서 이 다섯을 import 하는 모듈 전부
- Test: `tests/unit/test_analysis_channels.py` (신규)

**Interfaces:**
- Consumes: 없음 (P2의 첫 태스크)
- Produces: `squid_game.analysis.shared.loaders` 등 5모듈. 함수 시그니처는 전부 불변. `analysis/__init__`의 `__all__`도 불변이므로 파사드 경유 호출자는 영향받지 않는다.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_analysis_channels.py` (신규). 이 파일은 P2 내내 태스크마다 자라며, "채널 분해가 디렉터리 이름뿐인 분해가 아님"을 판정한다.

```python
"""The analysis split must be by measurement channel, not by convenience.

Two properties are pinned:

1. The facade is stable. ``squid_game.analysis.__all__`` is what the
   pipeline and the tests import through; P2 moves modules underneath it
   and must not change what comes out the front.
2. Each channel package holds only its own channel's estimators, and the
   shared layer holds no channel-specific model fitting. Asserted by
   naming modules explicitly -- a predicate would drift as files move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = REPO_ROOT / "game" / "squid_game" / "analysis"


def test_the_facade_still_exports_everything() -> None:
    module = importlib.import_module("squid_game.analysis")
    for name in module.__all__:
        assert hasattr(module, name), name


def test_shared_layer_holds_the_cross_channel_modules() -> None:
    expected = {
        "loaders.py",
        "export.py",
        "metrics.py",
        "discovery_detection.py",
        "manipulation_check.py",
        "__init__.py",
    }
    assert {p.name for p in (ANALYSIS / "shared").glob("*.py")} == expected


def test_the_flat_layout_is_gone() -> None:
    """A module left at the top level is a module nobody assigned a channel."""
    stray = {p.name for p in ANALYSIS.glob("*.py")} - {"__init__.py"}
    assert stray == set()
```

세 번째 테스트는 Task 7까지 실패한 채로 남는다. 그 전까지는 `pytest.mark.xfail(reason="channels land in Tasks 2-7")`을 붙이고, Task 7에서 마커를 뗀다.

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_analysis_channels.py -q
```

Expected: `test_shared_layer_holds_the_cross_channel_modules`가 FAIL (`shared/`가 없다).

- [ ] **Step 3: Move the five modules**

```bash
cd game/squid_game/analysis
mkdir -p shared
git mv loaders.py export.py metrics.py discovery_detection.py manipulation_check.py shared/
cd -
```

- [ ] **Step 4: Give `shared/` an `__init__.py`**

`game/squid_game/analysis/shared/__init__.py`:

```python
"""Inputs and outputs every measurement channel shares.

Nothing here fits a single channel: ``loaders`` reads the run artefacts,
``export`` writes them, ``metrics`` computes descriptive summaries,
``discovery_detection`` locates the rule-discovery turn, and
``manipulation_check`` verifies the framing manipulation landed. Channel
estimators live in ``cognitive/``, ``selfreport/``, ``behavioral/`` and
``semantic/``; this package is what they read from and write to.

``mtmm`` joins them in Task 7: it sits ABOVE the channels rather than in
one, because it triangulates their estimates.
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.\(loaders\|export\|metrics\|discovery_detection\|manipulation_check\)" \
  --include='*.py' game scripts tests web \
  | xargs sed -i '' -E 's/squid_game\.analysis\.(loaders|export|metrics|discovery_detection|manipulation_check)\b/squid_game.analysis.shared.\1/g'
```

`analysis/` 패키지 내부에서 형제를 부르던 import도 같은 치환에 포함된다 (전부 절대 경로 형태다). 잔여물 확인:

```bash
grep -rn "analysis\.\(loaders\|export\|metrics\|discovery_detection\|manipulation_check\)" --include='*.py' game scripts tests | grep -v "analysis\.shared"
```

기대: 0건.

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`.

- [ ] **Step 7: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): lift the cross-channel modules into shared/"
```

---

### Task 2: `behavioral/` — 선택과 생존 그 자체

행동 채널은 "무엇을 택했고 얼마나 버텼는가"만 본다. 통째로 옮길 수 있는 두 모듈이 여기 속한다: `forfeit_survival.py`(H1 Cox PH, 587줄)와 `unit13_hypotheses.py`(세션 수준 H1–H6, 472줄).

**Files:**
- Move: `analysis/forfeit_survival.py` → `analysis/behavioral/survival.py`
- Move: `analysis/unit13_hypotheses.py` → `analysis/behavioral/session_tests.py`
- Create: `analysis/behavioral/__init__.py`
- Modify: `analysis/__init__.py`, 직접 import 3건(`analysis.unit...`), 테스트

**Interfaces:**
- Consumes: Task 1의 `analysis.shared.loaders`
- Produces: `squid_game.analysis.behavioral.survival` — `build_survival_frame`, `CoxSurvivalResult`, `fit_cox_forfeit_survival`, `km_forfeit_curves`, `run_h1_survival_hypothesis`. `squid_game.analysis.behavioral.session_tests` — `UnitThirteenResult`, `session_features`, `test_h1_forfeit_rate` … `test_h6_post_discovery_engagement`, `run_all_unit13_hypotheses`. 시그니처 전부 불변.

- [ ] **Step 1: Extend the channel test**

```python
def test_behavioral_channel_holds_choice_and_survival() -> None:
    expected = {"survival.py", "session_tests.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "behavioral").glob("*.py")} >= expected


def test_behavioral_estimators_are_reachable_through_the_facade() -> None:
    module = importlib.import_module("squid_game.analysis")
    assert module.fit_cox_forfeit_survival is not None
    assert module.run_all_unit13_hypotheses is not None
```

`>=`를 쓰는 이유는 Task 5와 Task 7이 이 디렉터리에 `regime.py`와 `baseline_persistence.py`를 더 넣기 때문이다.

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run --extra dev --extra analysis pytest tests/unit/test_analysis_channels.py -q
```

Expected: FAIL — `behavioral/`가 없다.

- [ ] **Step 3: Move and rename**

```bash
cd game/squid_game/analysis
mkdir -p behavioral
git mv forfeit_survival.py behavioral/survival.py
git mv unit13_hypotheses.py behavioral/session_tests.py
cd -
```

- [ ] **Step 4: Write the package docstring**

`game/squid_game/analysis/behavioral/__init__.py`:

```python
"""Behavioural channel -- what the model did, not what it said or thought.

Two families live here. ``survival`` is the H1 Cox proportional-hazards
model over time-to-forfeit; ``session_tests`` is the session-level H1-H6
battery (Appendix A.4). Both read only choices and outcomes: forfeit or
continue, stake taken, turns survived. Nothing here reads thinking tokens
(that is ``cognitive/``) or the REASON digit (that is ``selfreport/``).
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.forfeit_survival\|squid_game\.analysis\.unit13_hypotheses" --include='*.py' game scripts tests \
  | xargs sed -i '' -e 's/squid_game\.analysis\.forfeit_survival/squid_game.analysis.behavioral.survival/g' \
                    -e 's/squid_game\.analysis\.unit13_hypotheses/squid_game.analysis.behavioral.session_tests/g'
```

- [ ] **Step 6: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

- [ ] **Step 7: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): gather the behavioural channel"
```

---

### Task 3: `cognitive/` — RI(thinking tokens)를 읽는 것들

인지 채널의 지표는 하나다: `thinking_tokens`에서 나온 RI. 통째로 옮길 수 있는 것은 `tc_regression.py`(931줄, R1/TC 지표) 하나이고, 나머지 둘은 Task 4(`forfeit_regression` 분할)와 이번 태스크의 CLI 승격에서 온다.

`scripts/analyze_call1_ri.py`(305줄)는 Call-1 RI 회귀 모델과 CLI를 한 파일에 담고 있다. 모델부를 `cognitive/ri_call1.py`로 올리고 스크립트에는 argparse와 리포트 방출만 남긴다.

**Files:**
- Move: `analysis/tc_regression.py` → `analysis/cognitive/ri_task.py`
- Create: `analysis/cognitive/__init__.py`, `analysis/cognitive/ri_call1.py`
- Modify: `scripts/analyze_call1_ri.py` (모델 함수 제거, import로 대체)
- Modify: `analysis/__init__.py`, 직접 import 1건

**Interfaces:**
- Consumes: Task 1의 `analysis.shared.loaders`
- Produces: `squid_game.analysis.cognitive.ri_task` — `TCRegressionResult`, `TCReverseCheckResult`, `TCCoxResult`, `add_correct_prev`, `add_rule_match_prev`, `fit_tc_rule_mastery_cell0`, `fit_tc_rule_mastery_allowed`, `fit_tc_reverse_check`, `fit_tc_streak_robustness`, `fit_tc_cox_rule_mastery`, `discovery_timing_alignment`, `beta_C_by_phase`, `run_all_tc_indicators`. `squid_game.analysis.cognitive.ri_call1` — `scripts/analyze_call1_ri.py`에서 올라온 모델 함수들 (정확한 이름은 Step 3에서 실측해 그대로 유지한다).

- [ ] **Step 1: Extend the channel test**

```python
def test_cognitive_channel_holds_the_ri_estimators() -> None:
    expected = {"ri_task.py", "ri_call1.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "cognitive").glob("*.py")} >= expected


def test_call1_script_is_a_thin_cli() -> None:
    """The model belongs in the package; the script owns only the CLI.

    Pinned by size rather than by naming every function: the point is that
    the statistics stopped living in scripts/, and a threshold states that
    without freezing the CLI's internals.
    """
    source = (REPO_ROOT / "scripts" / "analyze_call1_ri.py").read_text(encoding="utf-8")
    assert "from squid_game.analysis.cognitive.ri_call1 import" in source
    assert len(source.splitlines()) < 150
```

- [ ] **Step 2: Run it to verify it fails**

Expected: 둘 다 FAIL.

- [ ] **Step 3: Move `tc_regression` and lift the Call-1 model**

```bash
cd game/squid_game/analysis
mkdir -p cognitive
git mv tc_regression.py cognitive/ri_task.py
cd -
```

`scripts/analyze_call1_ri.py`를 읽고 다음 기준으로 자른다. **위로 올라가는 것**: DataFrame을 받아 통계 결과를 돌려주는 함수 전부(회귀 적합, 효과크기, 대조 계산). **스크립트에 남는 것**: argparse, 출력 경로 결정, 마크다운·JSON 방출, `if __name__ == "__main__"`.

함수 이름은 옮기면서 바꾸지 않는다. 실측 목록:

```bash
grep -n "^def \|^class \|^@dataclass" scripts/analyze_call1_ri.py
```

이 목록을 그대로 `cognitive/ri_call1.py`로 옮기되, `_write_*` / `_render_*` / `main` 계열만 스크립트에 남긴다.

- [ ] **Step 4: Write the package docstring**

`game/squid_game/analysis/cognitive/__init__.py`:

```python
"""Cognitive channel -- reasoning intensity, measured as thinking tokens.

``ri_task`` is the R1/TC family: does rule mastery move task-directed
reasoning? ``ri_forfeit`` (Task 4) is the H2 choice x framing model on the
forfeit decision. ``ri_call1`` is the Call-1 regression: whether the threat
framing raises reasoning before any decision is on the table.

All three read ``thinking_tokens`` and nothing else. The REASON digit the
model reports about its own reasoning is a different channel -- see
``selfreport/`` -- and keeping them apart is the point of the split: a
dissociation between them is only visible if they are estimated separately.
"""
```

- [ ] **Step 5: Rewrite the import sites**

```bash
grep -rl "squid_game\.analysis\.tc_regression" --include='*.py' game scripts tests \
  | xargs sed -i '' 's/squid_game\.analysis\.tc_regression/squid_game.analysis.cognitive.ri_task/g'
```

`analysis/__init__.py`에 `ri_call1`의 공개 심볼을 추가 export 한다 (`__all__`에 추가하는 것은 허용된다 — 제거·개명만 금지다).

- [ ] **Step 6: Verify the Call-1 script still reproduces its output**

이 산출물은 골든 스냅샷 84개에 포함되지 않는다(`outputs/call1_ri_analysis/`는 정규 런의 `phase3_analysis/` 밖이다). 따라서 직접 비교한다.

```bash
cp outputs/call1_ri_analysis/call1_ri_results.json /tmp/call1_before.json
uv run python -m scripts.analyze_call1_ri
diff <(python -c "import json,sys;print(json.dumps(json.load(open('/tmp/call1_before.json')),sort_keys=True,indent=2))") \
     <(python -c "import json,sys;print(json.dumps(json.load(open('outputs/call1_ri_analysis/call1_ri_results.json')),sort_keys=True,indent=2))")
```

Expected: diff 없음. 차이가 나면 승격 과정에서 로직이 바뀐 것이다 — 커밋하지 말고 되돌린다.

- [ ] **Step 7: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): gather the cognitive channel and thin the Call-1 CLI"
```

---

### Task 4: `forfeit_regression.py` 분할 — 인지와 자기보고를 가른다

952줄짜리 이 모듈이 채널 분리의 의미를 무효화하는 지점이다. H2 인지 모델(`fit_choice_asymmetric_model`, `fit_task_spillover_model`)과 자기보고 REASON 수렴(`reason_distribution`, `thinking_keyword_counts`, `fit_framing_ri_forfeit_continue`)이 한 파일에 들어 있고, 그 위에 세 채널이 모두 쓰는 `turn_observations()`가 얹혀 있다.

셋으로 가른다: `turn_observations`와 `forfeit_events`는 `shared/loaders.py`로, 인지 모델은 `cognitive/ri_forfeit.py`로, 자기보고 부분은 `selfreport/reason_convergence.py`로.

**Files:**
- Create: `analysis/cognitive/ri_forfeit.py`, `analysis/selfreport/__init__.py`, `analysis/selfreport/reason_convergence.py`
- Modify: `analysis/shared/loaders.py` (`turn_observations`, `forfeit_events` 수용)
- Delete: `analysis/forfeit_regression.py` (내용이 셋으로 흩어진 뒤)
- Modify: `analysis/__init__.py`, 직접 import 7건

**Interfaces:**
- Consumes: Task 1의 `shared/`, Task 3의 `cognitive/`
- Produces:
  - `shared.loaders.turn_observations(seasons) -> pd.DataFrame`, `shared.loaders.forfeit_events(seasons) -> pd.DataFrame` (이동만, 시그니처 불변)
  - `cognitive.ri_forfeit` — `ChoiceAsymmetricResult`, `fit_choice_asymmetric_model`, `TaskSpilloverResult`, `fit_task_spillover_model`, `run_all_unit15_hypotheses`, `unit15_descriptive_summary`
  - `selfreport.reason_convergence` — `reason_distribution`, `thinking_keyword_counts`, `FramingRiForfeitContinueResult`, `fit_framing_ri_forfeit_continue`, `run_all_unit14_hypotheses`
- 모듈 상수 `_CORRUPTION_FRAMINGS`, `_BASELINE_FRAMINGS`, `_MIN_TURNS_FOR_LOGIT`은 **두 파일 모두가 쓴다.** 복제하지 말고 `shared/loaders.py`로 올려 두 쪽이 import 한다.

- [ ] **Step 1: Extend the channel test**

```python
def test_forfeit_regression_actually_split() -> None:
    assert not (ANALYSIS / "forfeit_regression.py").exists()
    assert (ANALYSIS / "cognitive" / "ri_forfeit.py").exists()
    assert (ANALYSIS / "selfreport" / "reason_convergence.py").exists()


def test_the_framing_sets_are_defined_once() -> None:
    """A split that copies the constants is a split that will drift apart."""
    hits = [
        path.name
        for path in ANALYSIS.rglob("*.py")
        if "_CORRUPTION_FRAMINGS: frozenset" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["loaders.py"]


def test_shared_loaders_owns_turn_observations() -> None:
    loaders = importlib.import_module("squid_game.analysis.shared.loaders")
    assert callable(loaders.turn_observations)
    assert callable(loaders.forfeit_events)
```

- [ ] **Step 2: Run it to verify it fails**

Expected: 세 개 모두 FAIL.

- [ ] **Step 3: Lift the shared inputs first**

`analysis/forfeit_regression.py:91-284`의 `turn_observations`와 `forfeit_events`, 그리고 `:55-69`의 세 상수를 `analysis/shared/loaders.py` 끝으로 옮긴다. `loaders.py`가 이미 import 하지 않는 심볼(`SeasonResult`, `pd`)이 필요하면 import를 추가한다.

옮긴 자리에 남길 주석 대신, `loaders.py`의 `turn_observations` docstring에 왜 여기 있는지를 한 줄 적는다:

```python
def turn_observations(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """Turn-level frame consumed by every channel.

    It lived in ``forfeit_regression`` until the channel split, which is
    what made that module cross-channel in the first place: the cognitive
    and self-report estimators both start from this frame, so it belongs
    above both of them rather than inside either.
    """
```

- [ ] **Step 4: Create the cognitive half**

`git mv`로 rename 추적을 남긴다 — 인지 쪽이 원본에서 더 큰 덩어리다.

```bash
git mv game/squid_game/analysis/forfeit_regression.py game/squid_game/analysis/cognitive/ri_forfeit.py
```

그 다음 `ri_forfeit.py`에서 자기보고 함수 5개(`reason_distribution`, `thinking_keyword_counts`, `FramingRiForfeitContinueResult`, `fit_framing_ri_forfeit_continue`, `run_all_unit14_hypotheses`)와 Step 3에서 이미 올린 함수·상수를 삭제하고, 상수는 `from squid_game.analysis.shared.loaders import _BASELINE_FRAMINGS, ...`로 바꾼다.

- [ ] **Step 5: Create the self-report half**

`game/squid_game/analysis/selfreport/reason_convergence.py`에 Step 4에서 삭제한 다섯을 그대로 옮긴다. **본문을 다시 쓰지 않는다** — 잘라 붙인다. 함수 하나라도 다시 타이핑하면 골든 스냅샷이 잡아내겠지만, 잡아낸 뒤 원인을 찾는 비용이 그 자체로 낭비다.

`game/squid_game/analysis/selfreport/__init__.py`:

```python
"""Self-report channel -- what the model says about its own decision.

Two instruments. ``reason_convergence`` reads the REASON digit emitted with
a forfeit/continue choice and asks whether it converges with the framing
manipulation. ``psuccess`` (Task 5) reads the model's own success estimate
and the expected value it implies.

This channel is deliberately separate from ``cognitive/``: a model whose
thinking tokens rise while its stated reason does not move is the
dissociation the study is looking for, and it is unmeasurable if the two
are estimated in one file.
"""
```

- [ ] **Step 6: Repoint the 7 direct import sites**

```bash
grep -rn "squid_game\.analysis\.forfeit_regression" --include='*.py' game scripts tests
```

각 호출자가 어느 심볼을 쓰는지 보고 채널에 맞게 나눠 고친다. 한 파일이 양쪽 심볼을 모두 쓰면 import 두 줄이 된다. 일괄 `sed`가 성립하지 않는 유일한 태스크다 — 손으로 고치고, 위 `grep`이 0건이 될 때까지 반복한다.

- [ ] **Step 7: Run the gates**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`. **이 태스크가 P2에서 골든 스냅샷이 가장 중요한 지점이다** — `unit14_*` 산출물 6종이 방금 쪼갠 코드에서 나온다.

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): split forfeit_regression along the channel it crossed"
```

---

### Task 5: `regime_stratification.py` 분할 — 자기보고 EV와 행동 층화

656줄. `p_self` 기반 EV 계산(자기보고)과 no_cap/cap regime 층화(행동)가 겹쳐 있다. 층화 로직과 Cox 재적합은 행동 채널로, EV 계산은 자기보고 채널로 간다.

**Files:**
- Create: `analysis/behavioral/regime.py`, `analysis/selfreport/psuccess.py`
- Delete: `analysis/regime_stratification.py`
- Modify: `analysis/__init__.py`, 직접 import 5건

**Interfaces:**
- Consumes: Task 4의 `shared.loaders.turn_observations`, `behavioral.survival.fit_cox_forfeit_survival`
- Produces:
  - `behavioral.regime` — `annotate_regime`, `annotate_events_regime`, `filter_regime`, `stratified_counts`, `StratifiedCoxResult`, `run_stratified_unit14`, `render_regime_markdown`
  - `selfreport.psuccess` — `p_self` 추출과 EV 계산 함수. 이름은 원본에서 그대로 옮긴다 (`stratified_reason_distribution`은 REASON 분포이므로 자기보고 쪽이다).
- 포맷 헬퍼 `_fmt_pct`, `_fmt_float`, `_df_to_markdown`은 마크다운 방출용이며 `behavioral/regime.py`의 `render_regime_markdown`만 쓴다. 함께 옮긴다.

- [ ] **Step 1: Extend the channel test**

```python
def test_regime_stratification_actually_split() -> None:
    assert not (ANALYSIS / "regime_stratification.py").exists()
    assert (ANALYSIS / "behavioral" / "regime.py").exists()
    assert (ANALYSIS / "selfreport" / "psuccess.py").exists()
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Read the module and draw the line**

```bash
grep -n "p_self\|expected_value\|\bev\b\|psuccess" game/squid_game/analysis/regime_stratification.py
```

`p_self` / `psuccess` / EV를 읽거나 계산하는 함수는 자기보고, `regime` 라벨을 붙이거나 그 라벨로 자르거나 층별로 Cox를 다시 적합하는 함수는 행동이다. 경계가 모호한 함수가 나오면 **입력이 무엇인가**로 판정한다: 모델이 스스로 보고한 숫자를 읽으면 자기보고, 실제 선택·생존만 읽으면 행동.

- [ ] **Step 4: Split**

```bash
git mv game/squid_game/analysis/regime_stratification.py game/squid_game/analysis/behavioral/regime.py
```

자기보고 쪽 함수를 잘라 `selfreport/psuccess.py`로 옮기고, `regime.py`에 남은 참조를 import로 바꾼다. 방향은 한쪽이다: `behavioral/regime.py`가 `selfreport/psuccess.py`를 import 하는 것은 허용하되 그 역은 만들지 않는다 (층화는 EV를 필요로 하지만 EV 계산은 층화를 모른다).

- [ ] **Step 5: Repoint the 5 direct import sites**

```bash
grep -rn "squid_game\.analysis\.regime_stratification" --include='*.py' game scripts tests
```

Task 4와 같은 요령으로 손으로 고친다.

- [ ] **Step 6: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): split regime stratification into behaviour and self-report"
```

`regime_stratified_*` 산출물 3종이 이 코드에서 나온다. 골든 스냅샷이 이 태스크의 직접 증거다.

---

### Task 6: `semantic/` — 텍스트와 임베딩 채널

네 번째 채널은 신규다. 흩어져 있던 텍스트·임베딩 로직을 한 곳에 모은다. `analysis/`에 이미 있는 셋(`threat_registration`, `threat_judge`, `threat_lexicon`)과 `scripts/`에 있는 셋(`_ri_dataset`, `probe_reasoning_embeddings`의 라이브러리부, `probe_lexicon`)이 대상이다.

**Files:**
- Move: `analysis/threat_registration.py`, `analysis/threat_judge.py` → `analysis/semantic/`
- Move: `scripts/_ri_dataset.py` → `analysis/semantic/dataset.py`
- Create: `analysis/semantic/__init__.py`, `analysis/semantic/embeddings.py`, `analysis/semantic/lexicon.py`
- Delete: `analysis/threat_lexicon.py` (`semantic/lexicon.py`로 병합), `scripts/probe_lexicon.py`의 로직부
- Modify: `scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py` (얇은 CLI로 축소), `scripts/analyze_call1_ri.py` (`_ri_dataset` import 경로)
- Modify: `analysis/__init__.py`, 직접 import 13건 (`threat_judge` 9, `threat_registration` 3, `threat_lexicon` 1)

**Interfaces:**
- Consumes: Task 1의 `shared/`
- Produces:
  - `semantic.dataset` — 구 `scripts/_ri_dataset.py`의 전체 공개 표면 (`grep -n "^def " scripts/_ri_dataset.py`로 실측해 그대로 옮긴다)
  - `semantic.embeddings` — 구 `scripts/probe_reasoning_embeddings.py`에서 승격한 인코딩·프로브 적합 함수. **캐시 경로 상수와 시드는 그대로 옮긴다** (`outputs/reasoning_probe/_embedding_cache/`).
  - `semantic.lexicon` — 구 `analysis/threat_lexicon.py`(47줄)와 `scripts/probe_lexicon.py`의 로직 병합
  - `semantic.threat_registration`, `semantic.threat_judge` — 이동만

- [ ] **Step 1: Extend the channel test**

```python
def test_semantic_channel_exists_and_is_complete() -> None:
    expected = {
        "dataset.py",
        "embeddings.py",
        "lexicon.py",
        "threat_registration.py",
        "threat_judge.py",
        "__init__.py",
    }
    assert {p.name for p in (ANALYSIS / "semantic").glob("*.py")} == expected


def test_probe_scripts_are_thin_clis() -> None:
    for name in ("probe_reasoning_embeddings.py", "probe_lexicon.py"):
        source = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "squid_game.analysis.semantic" in source, name
        assert len(source.splitlines()) < 150, name


def test_the_ri_dataset_helper_left_scripts() -> None:
    assert not (REPO_ROOT / "scripts" / "_ri_dataset.py").exists()
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move what moves whole**

```bash
cd game/squid_game/analysis
mkdir -p semantic
git mv threat_registration.py threat_judge.py semantic/
cd -
git mv scripts/_ri_dataset.py game/squid_game/analysis/semantic/dataset.py
```

- [ ] **Step 4: Merge the two lexicons**

`analysis/threat_lexicon.py`(47줄, 어휘 정의)와 `scripts/probe_lexicon.py`(100줄, 어휘 기반 점수 계산)를 `semantic/lexicon.py` 하나로 합친다. 어휘 목록 문자열은 한 글자도 바꾸지 않는다 — 이것이 곧 측정 도구다.

```bash
git mv game/squid_game/analysis/threat_lexicon.py game/squid_game/analysis/semantic/lexicon.py
```

그 다음 `scripts/probe_lexicon.py`의 로직 함수를 `lexicon.py`에 붙이고, 스크립트에는 argparse와 출력만 남긴다.

- [ ] **Step 5: Lift the embedding pipeline**

`scripts/probe_reasoning_embeddings.py`(580줄)에서 `semantic/embeddings.py`로 올라가는 것: 인코딩(`SentenceTransformer` 호출과 캐시), 프로브 적합(GroupKFold, 스칼라 baseline 가드), 순열 검정. 스크립트에 남는 것: argparse, 채널·마스크 변형 루프, 리포트 방출.

**시드와 캐시 키를 바꾸지 않는다.** 임베딩 캐시(`outputs/reasoning_probe/_embedding_cache/`, 채널·마스크 변형당 ~13 MB)가 키 규칙에 걸려 있고, 키가 바뀌면 캐시가 통째로 무효화돼 재계산이 발생한다.

- [ ] **Step 6: Repoint the 13 direct import sites**

```bash
grep -rl "squid_game\.analysis\.\(threat_registration\|threat_judge\|threat_lexicon\)" --include='*.py' game scripts tests \
  | xargs sed -i '' -E 's/squid_game\.analysis\.(threat_registration|threat_judge)\b/squid_game.analysis.semantic.\1/g; s/squid_game\.analysis\.threat_lexicon\b/squid_game.analysis.semantic.lexicon/g'
```

`scripts/analyze_call1_ri.py`의 `_ri_dataset` import도 고친다:

```bash
sed -i '' 's/from scripts\._ri_dataset import/from squid_game.analysis.semantic.dataset import/' scripts/analyze_call1_ri.py
```

- [ ] **Step 7: Verify the probe reproduces its results**

이 산출물도 골든 스냅샷 밖이다. 직접 비교한다. 순열 귀무분포가 들어가므로 **점추정만** 비교한다.

```bash
cp outputs/reasoning_probe/probe_results.json /tmp/probe_before.json
uv run --extra probe python -m scripts.probe_reasoning_embeddings
python - <<'PY'
import json
before = json.load(open("/tmp/probe_before.json"))
after = json.load(open("outputs/reasoning_probe/probe_results.json"))
def auroc(d):
    return {k: v for k, v in sorted(_flatten(d).items()) if "auroc" in k or "accuracy" in k}
def _flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}{i}."))
    else:
        out[prefix.rstrip(".")] = d
    return out
b, a = auroc(before), auroc(after)
diff = {k: (b[k], a[k]) for k in b if k in a and b[k] != a[k]}
print("point estimates changed:", diff or "none")
PY
```

Expected: `point estimates changed: none`.

- [ ] **Step 8: Run the gates and commit**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
git add game/squid_game/analysis scripts tests
git commit -m "refactor(analysis): assemble the semantic channel from three scattered homes"
```

---

### Task 7: MTMM을 채널 위에 올리고 P2를 닫는다

`motivation.py`(462줄)는 4성분(생존 충동 · 과제 호기심 · 점수 애착 · 기저 지속성)을 세 방법 축으로 삼각측량하는 종합기다. 채널 하위가 아니라 **채널 위**에 둔다. 다만 `_baseline_persistence_behavioral`(Cell 5 비포기율)은 순수 행동 추정기이므로 행동 채널로 내린다.

**Files:**
- Move: `analysis/motivation.py` → `analysis/shared/mtmm.py`
- Create: `analysis/behavioral/baseline_persistence.py`
- Modify: `analysis/__init__.py` (최종 정리), 직접 import 5건
- Modify: `tests/unit/test_analysis_channels.py` (`xfail` 마커 제거)

**Interfaces:**
- Consumes: Task 2~6의 네 채널 전부
- Produces: `shared.mtmm.decompose_motivation(...)` — 시그니처 불변, 파사드 export 불변. `behavioral.baseline_persistence` — 구 `motivation._baseline_persistence_behavioral`이 공개 함수 `baseline_persistence_behavioral`로 승격된다 (선행 밑줄 제거. 다른 패키지에서 부르게 되므로 비공개 표기가 더는 사실이 아니다).

- [ ] **Step 1: Finish the channel test**

`test_the_flat_layout_is_gone`의 `xfail` 마커를 뗀다. 그리고 삼각측량 구조가 코드에 드러나는지 직접 확인하는 테스트를 더한다.

```python
def test_mtmm_sits_above_the_channels() -> None:
    """The triangulation must call the channel estimators, not re-implement them."""
    source = (ANALYSIS / "shared" / "mtmm.py").read_text(encoding="utf-8")
    assert "squid_game.analysis.behavioral" in source
    assert "squid_game.analysis.cognitive" in source


def test_baseline_persistence_is_behavioural() -> None:
    module = importlib.import_module("squid_game.analysis.behavioral.baseline_persistence")
    assert callable(module.baseline_persistence_behavioral)
```

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Move and split**

```bash
git mv game/squid_game/analysis/motivation.py game/squid_game/analysis/shared/mtmm.py
```

`_baseline_persistence_behavioral`(원본 `:360-403`)을 잘라 `behavioral/baseline_persistence.py`로 옮기고 이름에서 밑줄을 뗀다. `mtmm.py`는 import 해서 호출한다.

`_baseline_persistence_cognitive`는 인지 추정기이므로 `cognitive/`로 내려야 대칭이 맞지만, **스펙 §3.2가 명시한 이동 목록에 없다.** 이 계획은 스펙을 넘지 않는다. 대신 `mtmm.py`에 한 줄 남긴다:

```python
# _baseline_persistence_cognitive stays here while its behavioural twin
# moved to behavioral/baseline_persistence.py -- the spec's §3.2 mapping
# lists only the latter. The asymmetry is deliberate and recorded rather
# than silently "fixed": moving it is a spec change, not a refactor.
```

- [ ] **Step 4: Repoint the 5 direct import sites**

```bash
grep -rl "squid_game\.analysis\.motivation" --include='*.py' game scripts tests \
  | xargs sed -i '' 's/squid_game\.analysis\.motivation/squid_game.analysis.shared.mtmm/g'
```

- [ ] **Step 5: Tidy the facade**

`analysis/__init__.py`의 import 블록을 채널 순서로 재배열하고, 모듈 docstring의 "Usage::" 예시를 새 경로로 갱신한다. `__all__`의 내용은 **변경하지 않는다** — 순서만 채널별로 묶는다.

docstring 안의 죽은 참조 `docs/design/v6/POSTHOC_ANALYSIS.md §A.10, §A.11`은 P4 소관이다. 여기서 손대지 않는다.

- [ ] **Step 6: Run every gate**

```bash
uv run --extra dev --extra analysis pytest tests/unit -q
uv run --extra dev --extra analysis pytest tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

Expected: 신규 실패 0, `84 deterministic artefacts`, exit 0.

- [ ] **Step 7: Record the result**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P2 result` 문단을 더한다. 형식은 P1과 같다. 실측값만 적는다.

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/analysis scripts tests docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "refactor(analysis): lift MTMM above the channels it triangulates"
```

---

## 완료 조건

1. `analysis/` 최상위에 `__init__.py` 외의 `.py`가 없다.
2. `shared/`, `cognitive/`, `selfreport/`, `behavioral/`, `semantic/` 다섯 하위 패키지가 존재하고 각각 `__init__.py`에 채널 정의가 적혀 있다.
3. `forfeit_regression.py`와 `regime_stratification.py`가 존재하지 않는다.
4. `scripts/probe_reasoning_embeddings.py`, `scripts/probe_lexicon.py`, `scripts/analyze_call1_ri.py`가 각각 150줄 미만이고 로직을 `analysis.semantic` / `analysis.cognitive`에서 import 한다.
5. `squid_game.analysis.__all__`이 P2 시작 시점과 동일하다.
6. 골든 스냅샷 84개 바이트 동일, unit 스위트 신규 실패 0.
7. Call-1 산출물과 probe 점추정이 P2 이전과 동일하다 (Task 3 Step 6, Task 6 Step 7).

## 범위 밖

- scripts 5분류와 plot 스타일 추출 (P3)
- 죽은 주석·죽은 참조 정리 (P4)
- `unified_turn.py` · `api.py` 분리 (P5)
- 분석 산출물의 `results/` 이관 (P6)
- R2 비례검정, FDR 보정 (스펙 §8, 이번 재구조화 전체의 범위 밖)
