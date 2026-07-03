# 사람 플레이 죽음 안전 구간 (4턴부터 죽음) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 아레나 사람 플레이에서 p_death 죽음 판정을 1턴이 아닌 4턴부터 적용한다(1·2·3턴은 안전 구간). LLM 코드는 불변.

**Architecture:** `HumanGameSession`(사람 전용)에 `death_start_turn: int = 4` 생성자 파라미터를 추가하고, 죽음 주사위를 `turn_num >= self._death_start_turn`으로 게이트한다. 보상식과 UI 표시값에 쓰이는 `p_death`는 실제값(0.15)을 그대로 유지 — equal-EV 보상 패리티 보존. `interface/api.py`는 기본값(4)을 그대로 쓰므로 API 요청 표면 변화 없음.

**Tech Stack:** Python 3.12, pytest, uv. 대상 파일 `interface/human_game.py`, 테스트 `tests/unit/test_human_game.py`.

## Global Constraints

- **LLM 경로 절대 불변**: `src/squid_game/core/survival.py`, `interface/arena.py`, `GameEngine` 및 실험 파이프라인은 수정 금지. 변경은 `HumanGameSession`(및 그 테스트)에만 한정.
- **보상·UI 표시값 불변**: `calculate_reward` / `preview_continue_reward`에 넘기는 `turn_p_death`, `get_turn_state()`가 반환하는 `TurnState.p_death`는 실제 p_death를 그대로 사용. 안전 구간에서 "주사위만" 스킵.
- **1-indexed 턴**: `turn_num = self._current_turn + 1`. "4턴부터" = `turn_num >= 4`. 기본 `death_start_turn=4`.
- **`interface/api.py` 요청 모델 변경 금지**: `NewGameRequest`에 필드 추가하지 않음. 세션은 기본값으로 생성.
- **테스트 실행 커맨드** (iCloud가 editable `.pth`를 숨김 → `ModuleNotFoundError: No module named 'squid_game'` 방지):
  ```bash
  chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest <target> -v
  ```
- **보상식 특이점 주의**: `calculate_reward`는 `(1.0 - p_d)`로 나눈다. 테스트에서 죽음을 강제할 때 `p_death_constant=1.0`을 쓰면 `submit_action`이 보상 계산 단계(죽음 체크 이전)에서 `ZeroDivisionError`로 크래시한다. 죽음 강제는 `p_death_constant=0.25`(정상 구간)를 유지한 채 세션의 RNG를 "항상 죽는" 스텁으로 교체해 구현한다 (`rng.random()` → `0.0`, `0.0 < 0.25` → 사망).

---

### Task 1: `death_start_turn` 안전 구간 게이트

**Files:**
- Modify: `interface/human_game.py` (생성자 `__init__` ~124-177행, 죽음 체크 블록 408-414행)
- Test: `tests/unit/test_human_game.py` (파일 끝에 추가)

**Interfaces:**
- Consumes: 기존 `HumanGameSession(task_name, difficulty, framing, forfeit_condition, seed, total_turns, actual_death, starting_score, p_death_constant, num_few_shot, curriculum_turns, ...)` 생성자. 기존 `get_turn_state() -> TurnState`, `submit_action(action, ...) -> TurnFeedback` (필드 `is_dead: bool`, `game_over_reason: str`, `new_score: float`).
- Produces: `HumanGameSession.__init__`에 새 키워드 인자 `death_start_turn: int = 4`. 인스턴스 속성 `self._death_start_turn: int`. 죽음 판정은 `turn_num >= self._death_start_turn`일 때만 수행. 외부 시그니처의 다른 부분은 불변.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_human_game.py` 파일 끝에 아래를 추가한다. `signal_game`의 유효 액션은 `state.available_actions[0]`로 얻고, 죽음은 RNG 스텁으로 강제한다(보상식 특이점 회피). `p_death_constant=0.25`로 보상식을 비특이 구간에 유지한다.

```python
class _AlwaysDeadRng:
    """rng.random() < p_death 를 항상 True로 만드는 스텁 (0.0 < 0.25)."""

    def random(self) -> float:
        return 0.0


def _death_session(death_start_turn: int = 4) -> HumanGameSession:
    game = HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=10,
        actual_death=True,
        p_death_constant=0.25,
        death_start_turn=death_start_turn,
        num_few_shot=0,
        curriculum_turns=0,
    )
    # 죽음 판정이 도달하면 무조건 사망하도록 RNG를 고정.
    game._rng = _AlwaysDeadRng()  # type: ignore[assignment]
    return game


def _play_turn(game: HumanGameSession):
    state = game.get_turn_state()
    return game.submit_action(state.available_actions[0])


def test_grace_turns_1_to_3_are_immune_to_death():
    game = _death_session(death_start_turn=4)
    for turn in (1, 2, 3):
        fb = _play_turn(game)
        assert fb.is_dead is False, f"turn {turn} should be immune"
        assert fb.game_over_reason != "eliminated"


def test_death_applies_from_turn_4():
    game = _death_session(death_start_turn=4)
    for _ in (1, 2, 3):
        fb = _play_turn(game)
        assert fb.is_dead is False
    fb4 = _play_turn(game)
    assert fb4.is_dead is True
    assert fb4.game_over_reason == "eliminated"
    assert fb4.new_score == 0.0


def test_default_death_start_turn_is_4():
    # death_start_turn 미지정 → 기본 4. 1턴은 면역, 4턴은 사망.
    game = HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=10,
        actual_death=True,
        p_death_constant=0.25,
        num_few_shot=0,
        curriculum_turns=0,
    )
    game._rng = _AlwaysDeadRng()  # type: ignore[assignment]
    assert _play_turn(game).is_dead is False           # turn 1
    _play_turn(game)                                    # turn 2
    _play_turn(game)                                    # turn 3
    assert _play_turn(game).is_dead is True             # turn 4


def test_death_start_turn_is_configurable():
    # death_start_turn=1 → 1턴부터 즉시 사망 (게이트 파라미터가 실제로 반영됨).
    game = _death_session(death_start_turn=1)
    fb1 = _play_turn(game)
    assert fb1.is_dead is True
    assert fb1.game_over_reason == "eliminated"


def test_grace_turn_reward_unchanged_by_gate():
    # 죽음 활성 세션이라도 안전 구간(1턴)의 보상은 equal-EV 실제 p_death로 계산.
    game = _death_session(death_start_turn=4)
    state = game.get_turn_state()
    fb = game.submit_action(state.available_actions[0], psuccess_self=80)
    assert fb.is_dead is False
    layer = ForfeitLayer(ForfeitLayerConfig(
        p_death=0.25, p_success_estimate=0.75, base_reward=10.0,
        chain_psuccess_to_menu=True,
    ))
    sf = 1.0 if fb.was_optimal else 0.0
    expected = layer.calculate_reward(
        TaskOutcome(success_factor=sf), CONTINUE_CHOICE, 0.0,
        turn_p_death=0.25, psuccess_override=0.8,
    )
    assert fb.reward == expected
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_human_game.py -v -k "grace or death_start or turn_4"
```
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'death_start_turn'` (파라미터가 아직 없음).

- [ ] **Step 3: 생성자에 파라미터 추가**

`interface/human_game.py`의 `__init__` 시그니처에서 `total_turns: int = 15,` 바로 다음 줄에 인자를 추가한다:

```python
        total_turns: int = 15,
        death_start_turn: int = 4,
        actual_death: bool = True,
```

그리고 본문에서 `self._total_turns = total_turns` 다음 줄에 속성 저장을 추가한다:

```python
        self._total_turns = total_turns
        self._death_start_turn = death_start_turn
```

- [ ] **Step 4: 죽음 체크 게이트 적용**

`submit_action` 안의 현재 죽음 체크 블록(408-414행):

```python
        # Death check (skipped in Phantom Death mode)
        is_dead = False
        if self._actual_death:
            is_dead = self._survival.apply_death_check(p_death, self._rng)
            if is_dead:
                self._is_alive = False
                self._cumulative_score = 0.0
```

을 다음으로 교체한다:

```python
        # Death check (skipped in Phantom Death mode, and during the early
        # grace turns before death_start_turn — human play only).
        is_dead = False
        if self._actual_death and turn_num >= self._death_start_turn:
            is_dead = self._survival.apply_death_check(p_death, self._rng)
            if is_dead:
                self._is_alive = False
                self._cumulative_score = 0.0
```

(`turn_num`은 이 메서드 상단에서 이미 `self._current_turn + 1`로 정의되어 있으므로 1-indexed.)

- [ ] **Step 5: 테스트가 통과하는지 확인**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_human_game.py -v
```
Expected: PASS — 신규 5개 테스트 + 기존 테스트 전부 통과.

- [ ] **Step 6: 커밋**

```bash
git add interface/human_game.py tests/unit/test_human_game.py
git commit -m "feat(web-arena): human play death applies from turn 4 (grace turns 1-3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 설계 문서 갱신 (CLAUDE.md 규칙 준수)

**Files:**
- Modify: `docs/design/v6/paper/05_experimental_design.md` (또는 사람 플레이/웹 아레나를 다루는 해당 섹션 — 없으면 이 Task는 건너뛰고 스펙 문서만 근거로 남긴다)

CLAUDE.md의 "After modifying experiment design in code" 규칙은 셀/프레이밍 등 **LLM 실험 설계** 변경에 대한 것이다. 이번 변경은 사람 플레이(웹 아레나) 전용이고 LLM 6-cell 설계에 영향을 주지 않으므로, paper 섹션 갱신은 **선택**이다. 웹 아레나 동작을 기술한 문서가 있으면 한 줄 추가한다.

- [ ] **Step 1: 웹 아레나 사람 플레이를 기술한 문서 존재 여부 확인**

Run:
```bash
grep -rIln "human play\|사람 플레이\|HumanGameSession\|web arena\|웹 아레나\|actual_death" docs/ | grep -v superpowers
```

- [ ] **Step 2: 해당 문서가 있으면 안전 구간 규칙을 한 줄 추가**

발견된 문서에 다음 취지의 한 줄을 추가한다(파일 톤에 맞춰 국문/영문 선택):
> 사람 플레이는 1·2·3턴을 안전 구간으로 두고 죽음 판정을 4턴부터 적용한다(`death_start_turn=4`). 보상·표시 p_death는 불변. LLM 경로는 영향 없음.

문서가 없으면 스펙(`docs/superpowers/specs/2026-07-03-human-play-death-grace-turns-design.md`)을 단일 근거로 남기고 이 Step은 생략한다.

- [ ] **Step 3: 커밋 (변경이 있을 때만)**

```bash
git add docs/
git commit -m "docs(web-arena): note human-play death grace turns (from turn 4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- D1 (주사위만 스킵, 보상·UI 불변) → Task 1 Step 4 게이트는 죽음 체크만 감싸고 보상/`get_turn_state`는 손대지 않음; `test_grace_turn_reward_unchanged_by_gate`가 보상 불변을 고정. ✅
- D2 (`death_start_turn: int = 4` 생성자 파라미터, api.py 불변) → Task 1 Step 3; `test_default_death_start_turn_is_4`, `test_death_start_turn_is_configurable`가 검증. ✅
- 테스트 T1~T4 → `test_grace_turns_1_to_3_are_immune_to_death`, `test_death_applies_from_turn_4`, `test_grace_turn_reward_unchanged_by_gate`, `test_default_death_start_turn_is_4`로 매핑. ✅
- LLM 불변 → 변경 파일이 `interface/human_game.py`뿐, `survival.py`/`arena.py` 미포함. ✅

**2. Placeholder scan:** 모든 스텝에 실제 코드/커맨드 포함. Task 2는 조건부(문서 존재 시)이며 조건과 대체 경로를 명시. TBD/TODO 없음. ✅

**3. Type consistency:** `death_start_turn: int` (생성자·속성 일관), `TurnFeedback.is_dead/game_over_reason/new_score`, `_AlwaysDeadRng.random() -> float`, `available_actions[0]` — 전 태스크에서 이름·타입 일관. ✅
