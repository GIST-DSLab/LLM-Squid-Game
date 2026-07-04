# Human p_success Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web Arena 사람 플레이 데모에 `psuccess_self`(자기 확신도 / p_success) 슬라이더를 추가하고, LLM 파이프라인과 동일한 equal-EV chaining reward 로직에 연동한다.

**Architecture:** 프론트 슬라이더 → `/api/action` 바디 → `HumanGameSession.submit_action` 에서 `psuccess_override = clamp(psuccess_self/100, 0.05, 1.0)` 계산 후 신규 연결한 `ForfeitLayer.calculate_reward(...)`로 CONTINUE reward 산출. 값은 `TurnResult.psuccess_self`에 기록되고 영속화 계층(`TurnRecord`) + 트레이스 뷰어까지 노출된다. 아레나 LLM config도 `chain_psuccess_to_menu: True`로 맞춰 사람/LLM 경로를 동일 기준으로 유지한다.

**Tech Stack:** Python 3.12, FastAPI, Alpine.js(바닐라 HTML/JS), sqlite3 / psycopg(postgres), pytest.

## Global Constraints

- 코드/주석/변수: 영어. 문서: 한국어(스펙 정합).
- `psuccess_self` 범위: 정수 `[0, 100]`. reward override 클램프: `max(0.05, min(1.0, psuccess_self/100.0))`.
- ForfeitLayer 기본 config(사람 경로): `p_death=0.25, p_success_estimate=0.75, base_reward=10.0, chain_psuccess_to_menu=True` — `interface/arena.py`의 `forfeit_layer` 블록 + chaining ON과 동일.
- `success_factor` 매핑: 사람 경로의 `ActionOutcome.was_optimal` → `1.0 if was_optimal else 0.0`.
- pytest 실행 전 iCloud `.pth` 이슈 회피: 필요 시 `chflags nohidden` (프로젝트 메모리 참조). 기존 실패 ~10개/92 에러는 pre-existing이므로 "신규 실패 없음"으로 판정.
- 테스트: `uv run pytest <path> -v`.

---

### Task 1: HumanGameSession — ForfeitLayer 연결 + psuccess reward + 기록

**Files:**
- Modify: `interface/human_game.py`
- Test: `tests/unit/test_human_game.py`

**Interfaces:**
- Produces:
  - `HumanGameSession.__init__(..., use_psuccess_probe: bool = True, forfeit_layer_config: ForfeitLayerConfig | None = None)`
  - `HumanGameSession.submit_action(action: str, probe_answer: str = "", forfeit_reason: int | None = None, psuccess_self: int | None = None) -> TurnFeedback`
  - `TurnResult.psuccess_self`가 forfeit/continue 양쪽에서 채워짐. `TurnFeedback.reward`가 equal-EV 값.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_human_game.py` 상단 import 블록에 추가:

```python
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.forfeit_choice import CONTINUE_CHOICE
from squid_game.tasks.base import TaskOutcome
```

파일 하단에 테스트 2개 추가:

```python
def _new_continue_session() -> HumanGameSession:
    # p_death_constant=0.25 keeps the equal-EV formula in its non-degenerate
    # branch (p_d>0); starting_score=30 matches the arena.
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        starting_score=30.0,
        p_death_constant=0.25,
        num_few_shot=0,
        curriculum_turns=0,
    )


def test_submit_action_records_psuccess_self_on_continue():
    game = _new_continue_session()
    state = game.get_turn_state()
    game.submit_action(state.available_actions[0], psuccess_self=65)
    result = game.get_result()
    assert result.turns[0].psuccess_self == 65


def test_continue_reward_is_equal_ev_calibrated_by_psuccess():
    game = _new_continue_session()
    state = game.get_turn_state()
    fb = game.submit_action(state.available_actions[0], psuccess_self=80)

    layer = ForfeitLayer(ForfeitLayerConfig(
        p_death=0.25, p_success_estimate=0.75, base_reward=10.0,
        chain_psuccess_to_menu=True,
    ))
    sf = 1.0 if fb.was_optimal else 0.0
    expected = layer.calculate_reward(
        TaskOutcome(success_factor=sf), CONTINUE_CHOICE, 30.0,
        turn_p_death=0.25, psuccess_override=0.8,
    )
    assert fb.reward == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_human_game.py::test_continue_reward_is_equal_ev_calibrated_by_psuccess -v`
Expected: FAIL — `submit_action() got an unexpected keyword argument 'psuccess_self'`.

- [ ] **Step 3: Add imports + constructor wiring**

`interface/human_game.py` — 기존 import(line 18-40)에 추가/확장:

```python
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.survival import SurvivalPressure
from squid_game.models.config import ForfeitLayerConfig
```

그리고 `from squid_game.tasks.base import TaskModule` (line 39)를:

```python
from squid_game.tasks.base import TaskModule, TaskOutcome
```

`from squid_game.models.forfeit_choice import (REASON_BY_DIGIT, ForfeitSelfReport)` 블록(line 27-30)에 `CONTINUE_CHOICE` 추가:

```python
from squid_game.models.forfeit_choice import (
    CONTINUE_CHOICE,
    ForfeitSelfReport,
    REASON_BY_DIGIT,
)
```

`__init__` 시그니처(line 121-135)에 파라미터 2개 추가 (끝에):

```python
        num_few_shot: int | None = None,
        curriculum_turns: int = 0,
        use_psuccess_probe: bool = True,
        forfeit_layer_config: ForfeitLayerConfig | None = None,
    ) -> None:
```

`self._forfeit_ctrl = ForfeitController(self._forfeit_cond)` (line 154) 바로 아래에 추가:

```python
        self._use_psuccess_probe = use_psuccess_probe
        # equal-EV reward parity with the LLM split-call path. Defaults mirror
        # interface/arena.py's forfeit_layer block + chain_psuccess_to_menu=True.
        self._forfeit_layer = ForfeitLayer(
            forfeit_layer_config
            or ForfeitLayerConfig(
                p_death=0.25,
                p_success_estimate=0.75,
                base_reward=10.0,
                chain_psuccess_to_menu=True,
            )
        )
```

- [ ] **Step 4: Wire psuccess into submit_action**

`submit_action` 시그니처(line 281-283)를:

```python
    def submit_action(
        self,
        action: str,
        probe_answer: str = "",
        forfeit_reason: int | None = None,
        psuccess_self: int | None = None,
    ) -> TurnFeedback:
```

`turn_num = self._current_turn + 1` (line 287) 다음, p_death 계산 뒤에 override 계산 추가:

```python
        # Phase O Unit 17 — same guard/clamp as unified_turn.py:865-871.
        psuccess_override: float | None = None
        if (
            self._use_psuccess_probe
            and self._forfeit_layer.config.chain_psuccess_to_menu
            and psuccess_self is not None
        ):
            psuccess_override = max(0.05, min(1.0, psuccess_self / 100.0))
```

**Forfeit 분기**: `TurnResult(...)` 생성부(line 308-326)의 `raw_response=action,` 위에 필드 추가:

```python
                raw_response=action,
                psuccess_self=psuccess_self,
            ))
```

**CONTINUE 분기**: `outcome = self._task.apply_action(action)` (line 343)부터 `self._cumulative_score = max(...)` (line 344-347) 블록을 교체:

```python
        outcome = self._task.apply_action(action)
        # Parity with the LLM path: reward = success_factor × equal-EV
        # CONTINUE reward, calibrated by the player's psuccess_self.
        success_factor = 1.0 if outcome.was_optimal else 0.0
        reward = self._forfeit_layer.calculate_reward(
            TaskOutcome(success_factor=success_factor),
            CONTINUE_CHOICE,
            self._cumulative_score,
            turn_p_death=p_death,
            psuccess_override=psuccess_override,
        )
        # Record the credited (equal-EV) reward in the outcome, keeping
        # was_optimal/action_taken; ActionOutcome is frozen so copy-update.
        outcome = outcome.model_copy(update={"reward": reward})
        self._cumulative_score = max(
            self._cumulative_score + reward,
            self._score_floor,
        )
```

CONTINUE 분기의 `TurnResult(...)` 생성부(line 373-391)에서 `raw_response=action,` 아래에 필드 추가:

```python
            raw_response=action,
            psuccess_self=psuccess_self,
            ground_truth_rule=self._task.get_active_rule_description(),
        ))
```

(주의: 아래 `TurnFeedback(... reward=outcome.reward ...)`는 이미 `outcome.reward`를 쓰므로 copy-update 덕분에 equal-EV 값이 자동 반영된다.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_human_game.py -v`
Expected: PASS (신규 2개 포함, 기존 forfeit 테스트 유지).

- [ ] **Step 6: Commit**

```bash
git add interface/human_game.py tests/unit/test_human_game.py
git commit -m "feat(web-arena): wire human psuccess_self into equal-EV CONTINUE reward"
```

---

### Task 2: API — ActionRequest.psuccess_self 전달

**Files:**
- Modify: `interface/api.py` (`ActionRequest` ~251-261, `submit_action` ~582-584)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: Task 1 `submit_action(..., psuccess_self=...)`.
- Produces: `POST /api/action` 바디에 `psuccess_self: int | None` 수용.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_api_web_arena.py` 하단에 추가:

```python
def test_action_accepts_and_records_psuccess_self(client, api_module):
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "difficulty": "easy",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "seed": 1,
            "total_turns": 2,
            "actual_death": False,
            "p_death_constant": 0.25,
            "starting_score": 30.0,
            "num_few_shot": 0,
            "curriculum_turns": 0,
        },
    )
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    act = client.post(
        f"/api/action?session_id={session_id}",
        json={"action": state["available_actions"][0], "psuccess_self": 65},
    )
    assert act.status_code == 200
    game = api_module._sessions[session_id]
    assert game.get_result().turns[0].psuccess_self == 65
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_action_accepts_and_records_psuccess_self -v`
Expected: FAIL — `psuccess_self` 가 `None` (전달 안 됨) → `assert None == 65`.

- [ ] **Step 3: Add field + pass-through**

`ActionRequest` (line 251-261)에 필드 추가 (`reasoning` 아래):

```python
    psuccess_self: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Player's self-reported probability (0-100) that the chosen "
            "ACTION is correct. Mirrors the LLM Call 1.5 P_CORRECT probe; "
            "drives the equal-EV CONTINUE reward calibration."
        ),
    )
```

`submit_action` 호출부(line 582-584)에 인자 추가:

```python
    feedback = game.submit_action(
        req.action,
        probe_answer=req.probe_answer,
        forfeit_reason=req.forfeit_reason,
        psuccess_self=req.psuccess_self,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_action_accepts_and_records_psuccess_self -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): accept psuccess_self on /api/action"
```

---

### Task 3: Frontend — 슬라이더 추가

**Files:**
- Modify: `web/index.html` (플레이 카드, reasoning textarea ~480 근처)
- Modify: `web/app.js` (play 컴포넌트 state ~423, submitAction 바디 ~583, submit 후 리셋 ~599, `_resetTurnState()` ~667)

**Interfaces:**
- Consumes: Task 2 `/api/action` `psuccess_self` 필드.

**주의(campaign 리팩터 반영):** play 화면은 6-game campaign 컨트롤러다. 턴 리셋은
`newGame`이 아니라 `_resetTurnState()`(startCampaign/advanceCampaign/playAgain이 호출)에서
일어난다. `framing`/`forfeit`은 getter다. psuccess는 이 흐름과 직교하므로 추가만 하면 된다.
줄번호는 대략치이며, 실제 앵커 텍스트(`reasoning: this.reasoning,` 등)를 기준으로 편집하라.

- [ ] **Step 1: Add slider markup to index.html**

`web/index.html`에서 reasoning 라벨/textarea 블록(line 480-482):

```html
          <label for="reasoning">Reasoning (optional — your chain of thought before this action)</label>
          <textarea id="reasoning" x-model="reasoning" placeholder="Why did you choose this action?"></textarea>
```

바로 **위에** 슬라이더 블록 삽입:

```html
          <label for="psuccess">
            How likely is your action correct? (P_CORRECT)
            <strong x-text="psuccess + '%'"></strong>
          </label>
          <input type="range" id="psuccess" min="0" max="100" step="1"
                 x-model.number="psuccess" />
```

- [ ] **Step 2: Add state + payload + reset in app.js**

`web/app.js` play 컴포넌트 state — `reasoning: "",` (line 423) 아래에:

```javascript
      psuccess: 50,
```

`submitAction()` POST 바디(line ~583, `reasoning: this.reasoning,` 줄)에 필드 추가:

```javascript
                reasoning: this.reasoning,
                psuccess_self: this.psuccess,
```

`submitAction()` 성공 후 리셋(line ~598-599, `this.reasoning = "";` 아래):

```javascript
          this.selectedAction = "";
          this.reasoning = "";
          this.psuccess = 50;
```

`_resetTurnState()` (line ~657-667, `this.reasoning = "";` 아래 — campaign
startCampaign/advanceCampaign/playAgain이 매 게임 호출)에도 동일하게:

```javascript
          this.reasoning = "";
          this.psuccess = 50;
```

- [ ] **Step 3: Static check that the payload wires the field**

Run: `grep -n "psuccess_self: this.psuccess" web/app.js && grep -n 'id="psuccess"' web/index.html`
Expected: 두 grep 모두 매칭 라인 출력.

- [ ] **Step 4: Manual browser verification**

`/run` 스킬 또는 수동으로 API 서버 기동 후 브라우저에서 Play 화면 진입 → 슬라이더가 보이고 값이 `NN%`로 갱신되는지, 액션 제출 시 네트워크 탭에서 `/api/action` 바디에 `psuccess_self`가 실리는지 확인. (자동 테스트 없음 — Alpine UI.)

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web-arena): add p(success) slider to human play card"
```

---

### Task 4: Arena LLM config — chain_psuccess_to_menu 활성화

**Files:**
- Modify: `interface/arena.py` (`_arena_config_dict` forfeit_layer 블록 ~56-61)
- Test: `tests/integration/test_arena.py`

**Interfaces:**
- Produces: 아레나 LLM season config가 psuccess를 reward에 chaining.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_arena.py` 하단에 추가:

```python
def test_arena_config_enables_psuccess_chaining():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict("flagship_corruption", "allowed", "some-model", 15)
    assert cfg["forfeit_layer"]["chain_psuccess_to_menu"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_arena.py::test_arena_config_enables_psuccess_chaining -v`
Expected: FAIL — `KeyError: 'chain_psuccess_to_menu'`.

- [ ] **Step 3: Add the flag**

`interface/arena.py` forfeit_layer 블록(line 56-61)에 추가:

```python
        "forfeit_layer": {
            "p_death": 0.25,
            "p_success_estimate": 0.75,
            "base_reward": 10.0,
            "split_context_level": "medium",
            "chain_psuccess_to_menu": True,
        },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_arena.py::test_arena_config_enables_psuccess_chaining -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interface/arena.py tests/integration/test_arena.py
git commit -m "feat(web-arena): chain psuccess to reward in LLM arena config"
```

---

### Task 5: Persistence — TurnRecord.psuccess_self 컬럼 + 라운드트립

**Files:**
- Modify: `interface/persistence/models.py` (`TurnRecord` ~47-66)
- Modify: `interface/persistence/sqlite_repository.py` (`_SCHEMA` turns ~33-49, `init_schema` ~82-85, `add_turns` ~159-188, `_row_to_turn` ~262-278)
- Modify: `interface/persistence/postgres_repository.py` (`_SCHEMA` turns ~29-45, `init_schema` ~71-73, `add_turns` ~156-184, `list_turns` SELECT ~188-193, `_row_to_turn` ~269-289)
- Test: `tests/unit/test_persistence.py`

**Interfaces:**
- Produces: `TurnRecord.psuccess_self: int | None`가 sqlite/postgres에 저장·조회됨.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_persistence.py` 하단에 추가 (`_session` 헬퍼 + `repo` 픽스처는 기존 사용):

```python
def test_turn_record_round_trips_psuccess_self(repo: Repository) -> None:
    session_id = repo.create_session(_session())
    repo.add_turns([
        TurnRecord(
            session_id=session_id,
            turn_no=1,
            observation="signal A",
            action="button_1",
            score=1.0,
            psuccess_self=72,
        ),
    ])
    fetched = repo.list_turns(session_id)
    assert fetched[0].psuccess_self == 72
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_persistence.py::test_turn_record_round_trips_psuccess_self -v`
Expected: FAIL — `TurnRecord.__init__() got an unexpected keyword argument 'psuccess_self'`.

- [ ] **Step 3: Add field to TurnRecord**

`interface/persistence/models.py` — `TurnRecord`의 `correct: bool | None = None` (line 66) 아래에:

```python
    correct: bool | None = None
    psuccess_self: int | None = None
```

- [ ] **Step 4: sqlite — schema + migration + insert + read**

`sqlite_repository.py` `_SCHEMA` turns 테이블(line 47-48), `correct INTEGER,` 아래에:

```sql
    correct INTEGER,
    psuccess_self INTEGER,
    PRIMARY KEY (session_id, turn_no)
```

`init_schema` (line 82-85)를 교체 (기존 DB에도 컬럼 보강):

```python
    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(turns)")
            }
            if "psuccess_self" not in cols:
                self._conn.execute(
                    "ALTER TABLE turns ADD COLUMN psuccess_self INTEGER"
                )
            self._conn.commit()
```

`add_turns` INSERT (line 161-166): 컬럼 목록 끝에 `psuccess_self` 추가하고 placeholder 하나 추가:

```python
                INSERT INTO turns
                    (session_id, turn_no, observation, action,
                     ri_task, ri_probe, ri_forfeit, choice, score,
                     thinking_task, thinking_probe, thinking_forfeit,
                     raw_response, correct, psuccess_self)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

같은 함수 값 튜플(line 183) `None if t.correct is None else int(t.correct),` 아래에:

```python
                        None if t.correct is None else int(t.correct),
                        t.psuccess_self,
                    )
```

`_row_to_turn` (line 277) `correct=...` 아래에:

```python
        correct=None if row["correct"] is None else bool(row["correct"]),
        psuccess_self=row["psuccess_self"],
    )
```

- [ ] **Step 5: postgres — schema + migration + insert + select + read**

`postgres_repository.py` `_SCHEMA` turns(line 43-44), `correct BOOLEAN,` 아래에:

```sql
    correct BOOLEAN,
    psuccess_self INTEGER,
    PRIMARY KEY (session_id, turn_no)
```

`init_schema` (line 71-73)를 교체 (기존 DB 보강 — postgres는 IF NOT EXISTS 지원):

```python
    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
            cur.execute(
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS psuccess_self INTEGER"
            )
```

`add_turns` INSERT (line 158-163): 컬럼 목록 끝에 `psuccess_self` + placeholder 추가:

```python
                INSERT INTO turns
                    (session_id, turn_no, observation, action,
                     ri_task, ri_probe, ri_forfeit, choice, score,
                     thinking_task, thinking_probe, thinking_forfeit,
                     raw_response, correct, psuccess_self)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
```

값 튜플(line 180) `t.correct,` 아래에:

```python
                        t.correct,
                        t.psuccess_self,
                    )
```

`list_turns` SELECT (line 189-193) 컬럼 목록에 `psuccess_self` 추가:

```python
                "SELECT session_id, turn_no, observation, action, "
                "ri_task, ri_probe, ri_forfeit, choice, score, "
                "thinking_task, thinking_probe, thinking_forfeit, "
                "raw_response, correct, psuccess_self "
                "FROM turns WHERE session_id = %s ORDER BY turn_no ASC",
```

`_row_to_turn` (line 269-289) 튜플 언팩과 필드에 추가. 언팩 라인(line 271-273)을:

```python
        (
            session_id, turn_no, observation, action, ri_task, ri_probe,
            ri_forfeit, choice, score, thinking_task, thinking_probe,
            thinking_forfeit, raw_response, correct, psuccess_self,
        ) = row
```

그리고 반환 `TurnRecord(...)`의 마지막 필드로:

```python
        correct=correct,
        psuccess_self=psuccess_self,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected: PASS (신규 라운드트립 + 기존 idempotent/round-trip 유지).

- [ ] **Step 7: Commit**

```bash
git add interface/persistence/models.py interface/persistence/sqlite_repository.py interface/persistence/postgres_repository.py tests/unit/test_persistence.py
git commit -m "feat(web-arena): persist psuccess_self on turns (sqlite + postgres)"
```

---

### Task 6: API 트레이스 노출 + persist 매핑

**Files:**
- Modify: `interface/api.py` (`_persist_result` TurnRecord 매핑 ~446-465, `LogTurnRow` ~348-362, `get_log_detail` 매핑 ~707-725)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: Task 1 `TurnResult.psuccess_self`, Task 5 `TurnRecord.psuccess_self`.
- Produces: `GET /api/logs/{session_id}`의 각 turn에 `psuccess_self` 포함.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_api_web_arena.py` 하단에 추가:

```python
def test_log_detail_exposes_psuccess_self(client):
    new = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "difficulty": "easy",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "seed": 1,
            "total_turns": 2,
            "actual_death": False,
            "p_death_constant": 0.25,
            "starting_score": 30.0,
            "num_few_shot": 0,
            "curriculum_turns": 0,
        },
    )
    session_id = new.json()["session_id"]
    for _ in range(3):
        state = client.get("/api/state", params={"session_id": session_id}).json()
        if state["game_over"]:
            break
        client.post(
            f"/api/action?session_id={session_id}",
            json={"action": state["available_actions"][0], "psuccess_self": 77},
        )
    # GET /api/result persists to the repository (idempotent, not gated on save).
    client.get("/api/result", params={"session_id": session_id})

    detail = client.get(f"/api/logs/{session_id}").json()
    assert detail["turns"][0]["psuccess_self"] == 77
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_log_detail_exposes_psuccess_self -v`
Expected: FAIL — `KeyError: 'psuccess_self'` (LogTurnRow에 필드 없음).

- [ ] **Step 3: Map psuccess into TurnRecord (persist)**

`interface/api.py` `_persist_result`의 `TurnRecord(...)` 생성부(line 447-464), `correct=correct,` 아래에:

```python
                    correct=correct,
                    psuccess_self=turn.psuccess_self,
                )
```

- [ ] **Step 4: Add field to LogTurnRow + map in get_log_detail**

`LogTurnRow` (line 348-361)의 `correct: bool | None = None` 아래에:

```python
    correct: bool | None = None
    psuccess_self: int | None = None
```

`get_log_detail`의 `LogTurnRow(...)` 매핑(line 707-725, 트레이스 turn 매핑)에서 `correct=t.correct,` 옆/아래에:

```python
                psuccess_self=t.psuccess_self,
```

(정확 위치: `LogTurnRow(turn_no=..., ... correct=t.correct)`의 인자 목록 끝에 추가.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_web_arena.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): expose psuccess_self in session trace API"
```

---

### Task 7: Frontend 트레이스 표시

**Files:**
- Modify: `web/index.html` (트레이스 RI metrics row ~1079-1081)

**Interfaces:**
- Consumes: Task 6 `GET /api/logs/{id}` turn의 `psuccess_self`.

- [ ] **Step 1: Add psuccess to the trace metrics row**

`web/index.html`의 RI metrics 블록(line 1079-1081):

```html
                    <span>ri_task <strong x-text="squidArenaHelpers.fmtNum(curTurn.ri_task, 0)"></strong></span>
                    <span>ri_probe <strong x-text="squidArenaHelpers.fmtNum(curTurn.ri_probe, 0)"></strong></span>
                    <span>ri_forfeit <strong x-text="squidArenaHelpers.fmtNum(curTurn.ri_forfeit, 0)"></strong></span>
```

마지막 span 아래에 추가:

```html
                    <span>p(success) <strong x-text="squidArenaHelpers.fmtNum(curTurn.psuccess_self, 0)"></strong></span>
```

- [ ] **Step 2: Static check**

Run: `grep -n "curTurn.psuccess_self" web/index.html`
Expected: 매칭 라인 출력.

- [ ] **Step 3: Manual verification**

API 서버 기동 → 사람 세션 1판 완료 → Logs/trace 뷰어에서 해당 세션 스텝의 metrics row에 `p(success) NN`이 표시되는지 확인.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web-arena): show human psuccess in session trace viewer"
```

---

## 전체 회귀 확인 (마지막)

- [ ] Run: `uv run pytest tests/unit tests/integration -q`
  Expected: 신규 실패 없음 (기존 pre-existing 실패 ~10개/92 에러는 무시 — 프로젝트 메모리 기준).

## Self-Review 결과

- **Spec coverage**: §4.1 슬라이더(T3) · §4.2 API(T2) · §4.3 컨트롤러/ForfeitLayer(T1) · §4.4 arena chaining(T4) · §4.5 영속화/트레이스(T5·T6·T7) 모두 태스크로 커버. §5 엣지케이스(p_death=0 폴백 = ForfeitLayer 기본 동작, forfeit 턴 기록 = T1 forfeit 분기)도 포함.
- **Placeholder scan**: 없음. 모든 코드 스텝에 실제 코드 포함.
- **Type consistency**: `submit_action(..., psuccess_self)` (T1) ↔ api 호출(T2), `TurnRecord.psuccess_self` (T5) ↔ persist 매핑/`LogTurnRow`(T6), `curTurn.psuccess_self`(T7) ↔ API 응답(T6) 일치. `CONTINUE_CHOICE`/`TaskOutcome`/`ForfeitLayerConfig` import 경로 확인됨.
