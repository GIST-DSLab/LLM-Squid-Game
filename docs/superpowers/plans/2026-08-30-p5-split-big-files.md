# P5 큰 파일 책임 분리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 저장소에서 가장 큰 두 파일 — `core/unified_turn.py` 1,751줄과 `squid_arena/api.py` 1,424줄 — 을 책임별로 쪼갠다.

**Architecture:** 이 단계는 스펙이 **고위험**으로 분류한 유일한 단계다. 골든 스냅샷은 분석 산출물만 지키므로 여기서는 아무것도 보장하지 못한다 — 턴 플로우와 API 응답은 그 산출물 밖의 런타임 동작이다. 그래서 순서가 뒤집힌다: **먼저 특성화 테스트로 현재 동작을 고정하고(Task 1·2), 그 다음에만 코드를 움직인다(Task 3·4).** 특성화 테스트는 "옳은 동작"을 주장하지 않는다. **지금의 동작**을 기록할 뿐이다. 그것이 이 단계에서 필요한 전부다 — 분리가 동작을 바꿨는지만 알면 된다. 분리 자체는 보수적이다: 클래스 하나를 여러 클래스로 쪼개 협력 관계를 새로 설계하지 않고, **순수 함수로 뽑아낼 수 있는 것만** 모듈로 내린다. `UnifiedTurnManager`는 상태(히스토리, 프로바이더, 설정)를 들고 있고 그 상태를 쪼개는 순간 위험이 다른 종류가 된다.

**Tech Stack:** Python 3.12, FastAPI + pydantic v2 (APIRouter), Jinja2, pytest + pytest-asyncio, `tests/integration/conftest.py`의 `StubProvider`.

**Spec:** `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md` (§4.3 특성화 테스트, §5 큰 파일 책임 분리, §6 P5 행)

**선행 조건:** P3+P4 완료.

## Global Constraints

- 작업 디렉터리는 워크트리 `<repo>/.claude/worktrees/squid-restructure`, 브랜치 `restructure/3tier`.
- **특성화 테스트 없이 코드를 움직이지 않는다.** Task 1·2가 Task 3·4의 전제다. 스펙 §4.3이 "P5 직전에 작성한다"고 지정했다.
- **프롬프트 템플릿 문자열과 보상 계산을 건드리지 않는다** (스펙 §5). 옮기기만 한다. 공백 하나가 바뀌어도 LLM 입력이 달라진다.
- **`squid_arena.api:app`은 그대로 import 가능해야 한다.** Dockerfile의 `CMD`, `render.yaml`의 헬스체크, `scripts/run/start_servers.sh`, 통합 테스트가 모두 이 이름에 걸려 있다. 분리 후에도 `api.py`가 `app`을 노출한다.
- **엔드포인트 경로와 응답 스키마를 바꾸지 않는다.** 배포된 프런트엔드(`web/frontend/app.js`)가 GitHub Pages에서 라이브 백엔드를 호출하고 있다. 필드 이름 하나가 바뀌면 배포된 사이트가 깨진다.
- 판정: unit + integration 신규 실패 0, 골든 스냅샷 84개 동일, 특성화 스냅샷 동일.
- 커밋 메시지·코드·주석·문서는 영어. 대화 보고만 한국어.

## File Structure

P5 완료 시점:

```
game/squid_game/core/
  unified_turn.py        # UnifiedTurnManager: 상태와 실행 흐름만
  turn_prompts.py        # 프롬프트 조립 (순수 함수)
  turn_conditions.py     # framing 판정과 p_death 해석 (순수 함수 / staticmethod)
  turn_results.py        # TurnResult 조립 (순수 함수)
web/squid_arena/
  api.py                 # FastAPI app 조립 + include_router. `app`은 여기 남는다
  schemas.py             # pydantic 요청/응답 모델 전량
  deps.py                # CORS, repository, rate limit, sanitizer
  routes_game.py         # /api/new_game /state /action /result /reward_preview
  routes_leaderboard.py  # /api/leaderboard/*
  routes_logs.py         # /api/logs* /api/report
  routes_arena.py        # /api/arena/*
  reporting.py           # _persist_result, 리포트 집계 헬퍼
tests/characterization/
  test_turn_flow_6cells.py
  test_api_contract.py
  snapshots/             # 특성화 스냅샷 JSON
```

---

### Task 1: 6셀 턴 플로우 특성화 테스트

`unified_turn.py`를 건드리기 전에 현재 동작을 기록한다. 스펙 §4.3이 요구하는 범위: Call 1 / 1.5 / 2 시퀀스 전량, Cell 0 축약 경로, Cell 5 EV-dominant 경로.

**Files:**
- Create: `tests/characterization/__init__.py`, `tests/characterization/conftest.py`, `tests/characterization/test_turn_flow_6cells.py`
- Create: `tests/characterization/snapshots/turn_flow/` (생성된 스냅샷)
- Modify: `pyproject.toml` (`testpaths`에 `tests/characterization` 추가), `tests/unit/test_pytest_ini_options.py`

**Interfaces:**
- Consumes: `tests/integration/conftest.py`의 `StubProvider`, `StubProviderCall`
- Produces: 스냅샷 파일 6개 (셀당 하나). 각 스냅샷은 한 셀의 시즌을 끝까지 돌린 결과의 **결정적 부분**만 담는다: 각 턴의 `action`, `forfeited`, `thinking_tokens`, `score`, 그리고 프로바이더에게 실제로 간 프롬프트 전문.

- [ ] **Step 1: Make the stub provider reusable**

`tests/integration/conftest.py`의 `StubProvider`는 통합 스위트 전용 fixture다. 특성화 스위트도 같은 것을 쓴다. **복제하지 않는다** — `tests/characterization/conftest.py`에서 import 한다.

```python
"""Characterisation fixtures.

The stub provider is imported from the integration suite rather than
copied: two stubs that drift apart would make the two suites disagree
about what "the same input" means, and the whole point of a
characterisation snapshot is that the input is fixed.
"""

from tests.integration.conftest import StubProvider, StubProviderCall  # noqa: F401
```

이 import가 성립하려면 `tests/`가 패키지여야 한다. `tests/__init__.py`가 없으면 만들고, 있으면 그대로 쓴다.

- [ ] **Step 2: Write the snapshot harness**

`tests/characterization/test_turn_flow_6cells.py`:

```python
"""What the turn flow does today, recorded before P5 moves any of it.

These are characterisation tests, not specifications. They assert nothing
about whether the behaviour is right -- only that splitting unified_turn.py
did not change it. A snapshot that needs updating is a signal to stop and
explain why, not a file to regenerate.

The six cells are the canonical v6 topology (see the P0 baseline doc):

    0  true_baseline        not_allowed  p_death 0.0
    1  baseline_flagship    allowed      0.25
    2  baseline_flagship    not_allowed  0.25
    3  flagship_corruption  allowed      0.25
    4  flagship_corruption  not_allowed  0.25
    5  true_baseline        allowed      0.0

Cell 0 exercises the short-circuit path (no forfeit menu, p_death 0), and
Cell 5 the EV-dominant path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext

SNAPSHOTS = Path(__file__).parent / "snapshots" / "turn_flow"

CELLS = [
    (0, "true_baseline", "not_allowed", 0.0),
    (1, "baseline_flagship", "allowed", 0.25),
    (2, "baseline_flagship", "not_allowed", 0.25),
    (3, "flagship_corruption", "allowed", 0.25),
    (4, "flagship_corruption", "not_allowed", 0.25),
    (5, "true_baseline", "allowed", 0.0),
]


def _record(manager, provider) -> dict:
    """The deterministic surface of one season: decisions plus exact prompts."""
    return {
        "turns": [
            {
                "action": t.action,
                "forfeited": t.forfeited,
                "thinking_tokens": t.thinking_tokens,
                "score": t.score,
            }
            for t in manager.history()
        ],
        "prompts": [call.prompt for call in provider.calls],
    }


@pytest.mark.parametrize("cell_id,framing,forfeit,p_death", CELLS)
def test_turn_flow_matches_snapshot(cell_id, framing, forfeit, p_death):
    manager, provider = _build_manager(cell_id, framing, forfeit, p_death)
    game_state = GameState(season_id=f"char-cell-{cell_id}", current_turn=1, cumulative_score=30.0)

    for turn_number in range(1, 11):
        context = TurnContext(
            turn_number=turn_number,
            total_turns=10,
            season_id=f"char-cell-{cell_id}",
            cumulative_score=game_state.cumulative_score,
            p_death=p_death,
            framing=Framing(framing),
            forfeit_condition=ForfeitCondition(forfeit),
            difficulty=Difficulty.MEDIUM,
        )
        result = manager.execute_turn(game_state, context)
        if result.forfeit_decision:
            break

    actual = _record(manager, provider)
    snapshot = SNAPSHOTS / f"cell_{cell_id}.json"

    if not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        pytest.fail(f"snapshot created at {snapshot}; re-run to compare")

    expected = json.loads(snapshot.read_text(encoding="utf-8"))
    assert actual == expected
```

`_build_manager`는 `tests/unit/test_unified_turn.py:277`의 `_make_manager`를 본뜬다. 그 헬퍼가 조립하는 것은 실측 기준 일곱 개다: `RiskChoiceLayer(RiskChoiceLayerConfig.default())`, `FramingManager(framing)`, `ForfeitController(forfeit)`, `SurvivalPressure()`, `MeasurementRecorder()`, `CoTCollector()`, `random.Random(seed)`. 특성화 스위트는 여기에 `forfeit_layer`, `use_split_forfeit_layer=True`, `use_psuccess_probe=True`를 더해 v6 정규 경로를 태운다 (`tests/unit/test_unified_turn.py:890`의 `_make_manager_with_layer`가 그 조립을 이미 한다 — 그쪽을 본뜬다).

`execute_turn`의 시그니처는 실측이다 (`unified_turn.py:197`):

```python
def execute_turn(self, game_state: GameState, turn_context: TurnContext) -> TurnResult
```

`game_state`를 변형하지 않으므로(docstring이 명시한다) 루프가 점수를 직접 갱신해야 한다. 위 코드의 `game_state.cumulative_score`는 각 턴의 `result.reward_received`로 갱신한다 — 엔진이 하는 일을 특성화 하네스가 대신한다.

**스텁 응답은 셀마다 고정된 문자열이어야 한다.** `StubProvider`의 `response_fn(call_index, messages)`은 호출 인덱스를 받으므로, 셀당 응답 목록을 리스트로 두고 인덱스로 꺼낸다. 무작위 응답은 스냅샷을 무의미하게 만든다.

`TurnResult`의 필드 이름(`action`, `forfeited`, `thinking_tokens`, `score`)은 `models/results.py`에서 실측해 맞춘다 — `_record`가 읽는 이름이 실제와 다르면 `AttributeError`로 즉시 드러난다.

- [ ] **Step 3: Generate the snapshots and verify they are stable**

```bash
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # 6 fail: snapshots created
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # must pass
uv run --extra dev pytest tests/characterization/test_turn_flow_6cells.py -q   # must pass again
```

두 번째와 세 번째가 모두 통과해야 한다. 한 번이라도 실패하면 기록 대상에 비결정 요소가 섞인 것이다 — 그 필드를 스냅샷에서 빼고, **뺐다는 사실과 이유를 테스트 docstring에 적는다.**

- [ ] **Step 4: Wire the suite into pytest and CI**

`pyproject.toml`:

```toml
testpaths = ["tests/unit", "tests/integration", "tests/characterization"]
```

`tests/unit/test_pytest_ini_options.py`의 기대값도 맞춘다. `.github/workflows/tests.yml`의 `Unit suite` 단계는 `tests/unit`만 돌리므로, 특성화 스위트를 도는 단계를 더한다.

- [ ] **Step 5: Commit**

```bash
git add tests/characterization pyproject.toml tests/unit/test_pytest_ini_options.py .github
git commit -m "test: characterise the six-cell turn flow before splitting it"
```

---

### Task 2: arena API 응답 스키마 특성화 테스트

`api.py`를 쪼개기 전에 엔드포인트의 응답 **모양**을 고정한다. 값이 아니라 스키마다 — 배포된 프런트엔드가 의존하는 것이 필드 이름과 타입이기 때문이다.

**Files:**
- Create: `tests/characterization/test_api_contract.py`, `tests/characterization/snapshots/api/openapi.json`

**Interfaces:**
- Consumes: `squid_arena.api.app`
- Produces: OpenAPI 스키마 스냅샷 1개와 엔드포인트 목록 고정 테스트.

- [ ] **Step 1: Write the contract test**

```python
"""The public API shape, recorded before P5 moves the routes around.

FastAPI generates an OpenAPI document from the route signatures and the
pydantic models, which makes it the cheapest complete record of the
contract: every path, method, status code, and response field in one
comparable artefact. Splitting api.py into routers must leave it
byte-identical.

This matters more than the usual refactor gate because the frontend is
deployed separately -- web/frontend/ runs on GitHub Pages against the live
Render backend, so a renamed field does not fail a test, it breaks a
running site.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).parent / "snapshots" / "api" / "openapi.json"


@pytest.fixture(autouse=True)
def _in_memory_repository(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("SQUID_THINKING_LOG_DIR", str(tmp_path / "thinking_traces"))


def test_openapi_document_is_unchanged() -> None:
    from squid_arena.api import app

    actual = app.openapi()
    if not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        pytest.fail(f"snapshot created at {SNAPSHOT}; re-run to compare")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert actual == expected


def test_every_route_is_still_registered() -> None:
    """Belt and braces: the OpenAPI diff can be large and hard to read.

    This one names the paths, so a missing route reports as a missing route
    rather than as a thousand-line document diff.
    """
    from squid_arena.api import app

    paths = {route.path for route in app.routes}
    for expected in (
        "/api/new_game",
        "/api/state",
        "/api/action",
        "/api/result",
        "/api/reward_preview",
        "/api/leaderboard/models",
        "/api/leaderboard/model_scores",
        "/api/leaderboard/play",
        "/api/logs",
        "/api/logs/{session_id}",
        "/api/report",
        "/api/arena/run",
        "/api/arena/status",
    ):
        assert expected in paths, expected
```

경로 목록은 실측이다 (`grep -n "^@app\." web/squid_arena/api.py`). 목록이 다르면 실측값으로 고친다.

- [ ] **Step 2: Generate and stabilise**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q   # creates
uv run --extra dev pytest tests/characterization/test_api_contract.py -q   # passes
```

- [ ] **Step 3: Commit**

```bash
git add tests/characterization
git commit -m "test: pin the arena API contract before splitting the router"
```

---

### Task 3: `unified_turn.py` 분리

1,751줄, 클래스 하나(`UnifiedTurnManager`), 메서드 27개. 세 덩어리를 순수 함수 모듈로 내린다. **클래스를 쪼개지 않는다** — 상태를 나누면 협력 관계를 새로 설계하는 일이 되고, 그것은 이 계획의 위험 한도를 넘는다.

내리는 것 (실측 줄 번호):

| 새 모듈 | 옮기는 메서드 | 근거 |
|---|---|---|
| `turn_conditions.py` | `_should_skip_menu` (1212), `_is_survival_framing` (1223), `_is_corruption_framing` (1228), `_is_baseline_flagship_framing` (1243), `_is_corruption_terminal_framing` (1259), `_resolve_base_p_death` (1178) | 앞 다섯은 이미 `@staticmethod`이고 `self`를 쓰지 않는다. `_resolve_base_p_death`는 `turn_context`만 읽는다 |
| `turn_prompts.py` | `_build_system_prompt` (1097), `_compose_user_message` (1138), `_compose_call1_user_message` (1150), `_derive_action_hint` (1165), `_format_prior_accuracy_summary` (1628), `_format_history_block` (1672) | 문자열 조립. 뒤 두 개는 히스토리를 인자로 받도록 바꾼다 |
| `turn_results.py` | `_build_forfeit_result` (1360), `_build_continue_result` (1394), `_build_forfeit_layer_result` (1434), `_build_forfeit_layer_continue_result` (1506) | `TurnResult` 조립 |

**남는 것:** `__init__`, `execute_turn`, `_execute_turn_forfeit_layer`, `_execute_turn_split_forfeit_layer`, `_resolve_risk_choice`, `_resolve_ground_truth_rule`, `_record`, `_record_history`, `history`, `stake_history`, `forfeit_self_report`. 이것이 상태를 다루는 부분이다.

**Files:**
- Create: `game/squid_game/core/turn_conditions.py`, `turn_prompts.py`, `turn_results.py`
- Modify: `game/squid_game/core/unified_turn.py`
- Test: 기존 `tests/unit/test_unified_turn*.py` 3개 + 특성화 스냅샷

**Interfaces:**
- Consumes: Task 1의 특성화 스냅샷
- Produces: 세 모듈의 공개 함수. `self`를 받던 메서드는 **필요한 값만** 인자로 받는 함수가 된다. 예: `_derive_action_hint(self)` → `derive_action_hint(task_context, forfeit_allowed)`. 정확한 인자는 각 메서드 본문이 실제로 읽는 `self.*` 속성으로 결정한다 — 그 이상을 넘기지 않는다.

- [ ] **Step 1: Confirm the characterisation snapshots pass**

```bash
uv run --extra dev pytest tests/characterization -q
```

통과하지 않으면 **여기서 멈춘다.** 기준선 없이 쪼개는 것이 이 태스크가 피하려는 바로 그 상황이다.

- [ ] **Step 2: Move the condition predicates**

가장 안전한 덩어리부터다 — 다섯 개가 이미 `@staticmethod`다.

`game/squid_game/core/turn_conditions.py`:

```python
"""Which branch of the turn flow applies, decided from the turn context.

These were static methods on UnifiedTurnManager: they read the turn
context and nothing else, so they never belonged to the manager's state.
Moved out so the manager's remaining methods are the ones that actually
need what it holds.

The framing predicates are enumerated rather than derived from a naming
convention -- `_is_corruption_framing` and `_is_corruption_terminal_framing`
are separate questions, and a prefix match would conflate them.
"""
```

메서드 본문을 그대로 옮기고, `unified_turn.py`에서는 import 해서 호출한다. 호출부의 `self._is_corruption_framing(ctx)`가 `is_corruption_framing(ctx)`가 된다.

- [ ] **Step 3: Run the gates after the first move**

```bash
uv run --extra dev pytest tests/characterization tests/unit -q
```

**덩어리마다 게이트를 돌린다.** 세 덩어리를 한 번에 옮기고 실패하면 어느 것이 원인인지 알 수 없다.

- [ ] **Step 4: Move the prompt composition**

`turn_prompts.py`. `_format_prior_accuracy_summary`와 `_format_history_block`은 `self._history`를 읽으므로 히스토리를 인자로 받는 함수가 된다.

**프롬프트 문자열 리터럴을 한 글자도 바꾸지 않는다.** 특성화 스냅샷이 프롬프트 전문을 담고 있으므로 공백 하나가 달라져도 잡힌다 — 그것이 이 스냅샷을 그렇게 설계한 이유다.

- [ ] **Step 5: Run the gates**

```bash
uv run --extra dev pytest tests/characterization tests/unit -q
```

- [ ] **Step 6: Move the result builders**

`turn_results.py`. 네 개 모두 `TurnResult`를 조립하며 `self`에서 읽는 값이 많다 — 어떤 속성을 읽는지 먼저 세고, 그 목록을 인자로 만든다. 인자가 여섯 개를 넘으면 그 덩어리는 **옮기지 않고 남긴다.** 인자 목록이 길다는 것은 그 함수가 아직 상태의 일부라는 신호다.

- [ ] **Step 7: Run every gate**

```bash
uv run --extra dev pytest tests/characterization -q
uv run --extra dev --extra analysis pytest tests/unit tests/integration -q
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
wc -l game/squid_game/core/unified_turn.py
```

`unified_turn.py`가 1,200줄 아래로 내려가야 한다. 그보다 크면 세 덩어리 중 옮기지 못한 것이 있다는 뜻이므로, **무엇을 왜 남겼는지 커밋 메시지에 적는다.**

- [ ] **Step 8: Commit**

```bash
git add game/squid_game/core tests
git commit -m "refactor(core): lift the pure parts out of the turn manager"
```

---

### Task 4: `api.py` 분리

1,424줄. 구조는 이미 주석으로 구획돼 있어 경계가 뚜렷하다 (실측 줄 번호):

| 구획 | 줄 | 목적지 |
|---|---|---|
| CORS 설정 (`_cors_origins`) | 72–104 | `deps.py` |
| repository 초기화 | 105–150 | `deps.py` |
| 입력 정제 (`sanitize_nickname`, `sanitize_campaign_id`) | 151–190 | `deps.py` |
| rate limit (`_client_key`, `_check_rate_limit`, `_strip_status_block`) | 191–246 | `deps.py` |
| pydantic 모델 전량 | 247–620 | `schemas.py` |
| 변환·영속 헬퍼 (`_session_record_to_row`, `_model_stats_to_row`, `_persist_result`, `_cell_meta`, `_cell_order_index`, `_turn_is_forfeit`) | 517–752 | `reporting.py` |
| 게임 라우트 (`/api/new_game`, `/state`, `/action`, `/result`, `/reward_preview`) | 758–991 | `routes_game.py` |
| 리더보드 라우트 | 992–1074 | `routes_leaderboard.py` |
| 로그·리포트 라우트 | 1075–1361 | `routes_logs.py` |
| arena 라우트 | 1362–1424 | `routes_arena.py` |

**Files:**
- Create: `web/squid_arena/{schemas,deps,reporting,routes_game,routes_leaderboard,routes_logs,routes_arena}.py`
- Modify: `web/squid_arena/api.py`

**Interfaces:**
- Consumes: Task 2의 OpenAPI 스냅샷
- Produces: 각 `routes_*.py`가 `router = APIRouter()`를 노출하고, `api.py`가 `app.include_router(...)`로 조립한다. **`squid_arena.api.app`은 그대로 존재한다.** `schemas.py`는 pydantic 모델 전량을, `deps.py`는 `get_repository` 래퍼와 `check_rate_limit`, `sanitize_nickname`, `sanitize_campaign_id`, `cors_origins`를 노출한다.

- [ ] **Step 1: Confirm the contract snapshot passes**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q
```

- [ ] **Step 2: Extract `schemas.py` first**

가장 안전하다 — pydantic 모델은 서로만 참조하고 라우트를 모른다. 모델 정의를 그대로 옮기고 `api.py`에서 `from squid_arena.schemas import *` 대신 **명시적으로** import 한다 (`*`는 OpenAPI 문서에 영향은 없지만 무엇이 어디서 오는지를 지운다).

**클래스 이름과 필드를 바꾸지 않는다.** OpenAPI 문서의 `components.schemas` 키가 클래스 이름에서 나오므로, 이름을 바꾸면 스냅샷이 즉시 깨진다 — 그리고 그 깨짐은 프런트엔드가 겪을 깨짐과 같은 것이다.

- [ ] **Step 3: Run the contract gate**

```bash
uv run --extra dev pytest tests/characterization/test_api_contract.py -q
uv run --extra dev --extra analysis pytest tests/unit/test_api_web_arena.py -q
```

- [ ] **Step 4: Extract `deps.py`**

CORS · repository · rate limit · sanitizer. `_repository = get_repository()`가 모듈 스코프에서 실행되는 부분(`api.py:144`)은 그대로 `deps.py`로 옮긴다 — **지연 초기화로 바꾸지 않는다.** 그것은 동작 변경이며, `tests/unit/test_import_smoke.py`가 이 import-time 부작용을 명시적으로 sandbox 하고 있다. 옮기면 그 테스트의 대상 모듈 이름도 `squid_arena.deps`로 바뀐다.

- [ ] **Step 5: Extract `reporting.py`, then the four route modules**

라우트는 한 모듈씩 옮기고 **모듈마다 게이트를 돌린다.**

각 `routes_*.py`의 형태:

```python
"""Game routes: one session's lifecycle from new_game to result."""

from fastapi import APIRouter, Request

from squid_arena import deps, schemas

router = APIRouter()


@router.post("/api/new_game", response_model=schemas.NewGameResponse)
def new_game(req: schemas.NewGameRequest, request: Request):
    ...
```

`api.py`에 남는 것:

```python
"""The Web Arena backend's ASGI app.

Assembly only: the routes live in routes_*.py, the models in schemas.py,
and the cross-cutting pieces (CORS, repository, rate limiting, input
sanitisation) in deps.py. `app` stays in this module because the
Dockerfile's CMD, render.yaml's health check, start_servers.sh and the
integration tests all name `squid_arena.api:app`.
"""

app = FastAPI(...)
app.add_middleware(CORSMiddleware, allow_origins=deps.cors_origins(), ...)

app.include_router(routes_game.router)
app.include_router(routes_leaderboard.router)
app.include_router(routes_logs.router)
app.include_router(routes_arena.router)
```

**`include_router` 순서는 라우트 등록 순서를 결정하고, 그 순서가 OpenAPI 문서의 `paths` 순서에 반영된다.** 스냅샷 비교는 `sort_keys=True`로 저장했으므로 순서에는 영향받지 않지만, `test_every_route_is_still_registered`가 누락을 잡는다. 원본 파일의 정의 순서와 같게 유지한다.

- [ ] **Step 6: Run every gate**

```bash
uv run --extra dev pytest tests/characterization -q
uv run --extra dev --extra analysis pytest tests/unit tests/integration -q
wc -l web/squid_arena/api.py
```

`api.py`가 150줄 아래로 내려가야 한다 — 조립만 남기 때문이다.

- [ ] **Step 7: Verify the deployed shape**

```bash
docker build -t squid-arena-p5 . \
  && docker run --rm -e PORT=8599 -d --name squid-p5 squid-arena-p5 \
  && sleep 5 \
  && curl -sf http://127.0.0.1:8599/api/leaderboard/models >/dev/null && echo "image OK"; \
  docker rm -f squid-p5
```

- [ ] **Step 8: Commit**

```bash
git add web/squid_arena tests
git commit -m "refactor(api): split the arena backend into routers, schemas and deps"
```

---

### Task 5: P5 마감

- [ ] **Step 1: Run the full gate set**

```bash
uv run --extra dev --extra analysis pytest tests/unit tests/integration tests/characterization -q
node --test tests/web/
uv run python scripts/dev/golden_snapshot.py verify --golden ~/golden/squid-restructure
```

- [ ] **Step 2: Record the result**

`docs/superpowers/plans/2026-08-30-p0-baseline.md`에 `## P5 result` 문단을 더한다. 여기에는 파일 크기 변화도 적는다.

```markdown
- `game/squid_game/core/unified_turn.py`: 1,751 -> <실측>
- `web/squid_arena/api.py`: 1,424 -> <실측>
- Characterisation snapshots: 6 turn-flow cells + 1 OpenAPI document, all unchanged.
```

옮기지 못하고 남긴 덩어리가 있으면 **무엇을 왜 남겼는지** 함께 적는다. 남긴 것을 적지 않으면 다음 사람이 같은 판단을 다시 해야 한다.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-08-30-p0-baseline.md
git commit -m "docs: record the P5 result and what stayed put"
```

---

## 완료 조건

1. `tests/characterization/`이 존재하고 `pyproject.toml`의 `testpaths`와 CI에 연결돼 있다.
2. 6셀 턴 플로우 스냅샷과 OpenAPI 스냅샷이 P5 전후로 동일하다.
3. `unified_turn.py` < 1,200줄, `api.py` < 150줄.
4. `squid_arena.api:app`이 그대로 import 되고 docker 이미지가 부팅해 응답한다.
5. unit · integration · characterization 신규 실패 0, 골든 스냅샷 84개 동일.
6. 프롬프트 템플릿 문자열과 보상 계산이 한 글자도 바뀌지 않았다 (스냅샷이 증거다).

## 범위 밖

- 문서 4분할, `results/` 분리, `assets/` 정리 (P6)
- 엔드포인트 추가·개명, 응답 필드 변경
- `UnifiedTurnManager`의 상태 분해 — 상태를 나누는 것은 협력 관계 재설계이며 이 단계의 위험 한도를 넘는다
- 프로바이더 계층(`providers/` 12모듈) 정리
