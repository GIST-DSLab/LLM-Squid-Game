# Web Arena 캠페인 히든 룰 속성 로테이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web Arena 사람 플레이 6게임 캠페인이 매 게임 다른 히든 룰 속성 계열을 쓰게 만든다 (현재는 6판 전부 동일 계열로 고정).

**Architecture:** `campaign_id`에서 결정적으로 파생한 길이 6짜리 룰 인덱스 스케줄을 새 순수 함수 모듈(`interface/rule_schedule.py`)이 계산하고, 그 값을 `/api/new_game` → `HumanGameSession` → `SignalGameModule.initialize(rule_index=...)`로 흘려보낸다. `rule_index`의 기본값은 `None`이며 이때 현행 동작(인덱스 0)을 그대로 유지하므로 LLM 실험 경로(`core/engine.py`)는 한 줄도 바뀌지 않는다.

**Tech Stack:** Python 3.12 · uv · pytest · FastAPI (Pydantic v2) · Alpine.js (빌드 없는 바닐라 JS)

**Spec:** `docs/superpowers/specs/2026-08-10-web-arena-rule-family-rotation-design.md`

## Global Constraints

- **테스트 실행은 반드시 이 형태로** (iCloud가 venv의 `.pth`에 `UF_HIDDEN`을 계속 다시 설정한다. 플래그 해제를 **같은 명령 안에서** 해야 하고, `--no-sync`여야 uv가 `.pth`를 재생성하지 않는다):
  `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest <경로> -v`
- **LLM 실험 경로 무변경.** `src/squid_game/core/engine.py`는 이 계획에서 절대 수정하지 않는다. `SignalGameModule.initialize()`를 `rule_index` 없이 호출하면 활성 룰은 반드시 인덱스 0이어야 한다 (Task 2의 회귀 테스트가 이를 못박는다).
- **UI 무변경.** `web/index.html`, `web/styles.css`, 플레이어에게 보이는 문구는 건드리지 않는다. `web/app.js`는 POST 바디에 키 하나 추가하는 것이 전부다. 정답 룰을 플레이어에게 노출하는 코드는 추가하지 않는다.
- **룰 description 문자열 포맷 불변.** `"If {attr} is {val} then {action}, otherwise {default}."` 형태는 few-shot 생성·probe 채점이 정규식으로 재파싱하는 사실상의 공개 API다. `src/squid_game/tasks/signal_game/rules.py`는 수정하지 않는다.
- **`hash()` 금지.** 스케줄 시드는 `hashlib.sha256`으로 만든다. 내장 `hash()`는 `PYTHONHASHSEED`로 프로세스마다 값이 달라져 서버 재시작 후 resume한 플레이어에게 다른 속성이 나온다.
- 코드·주석·docstring은 영어, 문서는 한국어 (`CLAUDE.md`).
- `outputs/` 아래 파일은 절대 `git add` 하지 않는다 (Git LFS 포인터 손상).

## File Structure

| 파일 | 역할 | 상태 |
|---|---|:-:|
| `interface/rule_schedule.py` | 캠페인 룰 인덱스 스케줄 계산. 표준 라이브러리만 의존하는 순수 함수 2개. | 신규 |
| `tests/unit/test_rule_schedule.py` | 위 모듈의 균형·인접중복·재현성·폴백·wrap 검증. | 신규 |
| `src/squid_game/tasks/signal_game/module.py` | `initialize()`/`reset()`이 `rule_index`를 받아 `_active_rule_index`에 반영. | 수정 |
| `tests/unit/test_signal_game_v3.py` | 회귀 가드(기본값=인덱스 0) + 인덱스별 활성 룰 + 속성 무관 few-shot. | 수정 |
| `interface/human_game.py` | `rule_index` 통과 배선 (판단 로직 없음). | 수정 |
| `tests/unit/test_human_game.py` | 세션 생성자가 `rule_index`를 태스크에 전달하는지. | 수정 |
| `interface/api.py` | `NewGameRequest.campaign_index` 필드 + 핸들러에서 인덱스 계산. | 수정 |
| `tests/unit/test_api_web_arena.py` | 6게임 엔드투엔드 배분 + 하위 호환. | 수정 |
| `web/app.js` | `startGame()` POST 바디에 `campaign_index` 추가. | 수정 |

---

### Task 1: 캠페인 룰 스케줄 모듈

**Files:**
- Create: `interface/rule_schedule.py`
- Test: `tests/unit/test_rule_schedule.py`

**Interfaces:**
- Consumes: 없음 (표준 라이브러리만).
- Produces:
  - `RULE_FAMILY_COUNT: int = 3`
  - `CAMPAIGN_GAME_COUNT: int = 6`
  - `campaign_rule_schedule(campaign_id: str) -> list[int]`
  - `rule_index_for(campaign_id: str | None, campaign_index: int, fallback_seed: int) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_rule_schedule.py` 새 파일:

```python
"""Unit tests for the Web Arena campaign rule-family schedule.

The schedule decides which hidden-rule attribute family each of a
campaign's six games uses. It must be balanced (each family twice),
gap-free (no family on two consecutive games) and stable across
processes (a resuming player must meet the same family again).
"""

from __future__ import annotations

from collections import Counter

from interface.rule_schedule import (
    CAMPAIGN_GAME_COUNT,
    RULE_FAMILY_COUNT,
    campaign_rule_schedule,
    rule_index_for,
)


def test_schedule_is_balanced_over_many_campaigns() -> None:
    """Every family appears exactly twice in every campaign's six games."""
    for i in range(200):
        schedule = campaign_rule_schedule(f"campaign-{i}")
        assert len(schedule) == CAMPAIGN_GAME_COUNT
        assert Counter(schedule) == {f: 2 for f in range(RULE_FAMILY_COUNT)}


def test_no_family_on_two_consecutive_games() -> None:
    for i in range(200):
        schedule = campaign_rule_schedule(f"campaign-{i}")
        adjacent = [
            (a, b) for a, b in zip(schedule, schedule[1:]) if a == b
        ]
        assert adjacent == [], f"campaign-{i} repeats: {schedule}"


def test_same_campaign_id_yields_same_schedule() -> None:
    assert campaign_rule_schedule("abc") == campaign_rule_schedule("abc")


def test_golden_schedule_pins_the_hash_function() -> None:
    """Guards against swapping sha256 for the salted builtin ``hash()``.

    ``hash()`` on a str is seeded per process by PYTHONHASHSEED, so a server
    restart would hand the same campaign a different schedule and a resuming
    player would meet a different attribute mid-campaign. A same-process
    equality check cannot catch that; this hardcoded expectation can.
    """
    assert campaign_rule_schedule("camp-golden-001") == [0, 2, 1, 2, 0, 1]


def test_first_game_family_varies_across_campaigns() -> None:
    firsts = {campaign_rule_schedule(f"c{i}")[0] for i in range(30)}
    assert firsts == set(range(RULE_FAMILY_COUNT))


def test_rule_index_for_walks_the_schedule() -> None:
    schedule = campaign_rule_schedule("camp-golden-001")
    got = [rule_index_for("camp-golden-001", i, 0) for i in range(6)]
    assert got == schedule


def test_rule_index_for_wraps_out_of_range_index() -> None:
    """A campaign longer than the schedule wraps instead of raising."""
    assert rule_index_for("camp-golden-001", 6, 0) == rule_index_for(
        "camp-golden-001", 0, 0
    )


def test_rule_index_for_falls_back_to_seed_without_campaign() -> None:
    """One-off games (no campaign) still vary, and stay reproducible."""
    assert rule_index_for(None, 0, 42) == rule_index_for(None, 0, 42)
    assert rule_index_for(None, 0, 42) != rule_index_for(None, 0, 1)
    assert 0 <= rule_index_for(None, 0, 42) < RULE_FAMILY_COUNT


def test_blank_campaign_id_takes_the_fallback_path() -> None:
    """``sanitize_campaign_id`` can hand back None; empty str must not crash."""
    assert rule_index_for("", 3, 42) == rule_index_for(None, 0, 42)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_rule_schedule.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interface.rule_schedule'` (수집 단계에서 에러)

- [ ] **Step 3: 모듈 구현**

`interface/rule_schedule.py` 새 파일:

```python
"""Deterministic hidden-rule attribute schedule for Web Arena campaigns.

A human Play campaign is six games long (``CAMPAIGN_CONDITIONS`` in
``web/app.js``). ``SignalGameModule`` always activated rule index 0, so every
game in a campaign shared one attribute family — colour on EASY, colour+shape
on HARD/EXPERT — and a player who cracked the family in game 1 carried that
knowledge into the other five. This module hands each game a different index.

Pure functions over the standard library: no squid_game imports, no server
state. The schedule is derived from the campaign id alone, so it survives a
page reload, a resume checkpoint, and a server restart.
"""

from __future__ import annotations

import hashlib
import random

# ``generate_rules()`` returns three candidate rules at every difficulty
# (rules.py: EASY/MEDIUM -> colour / shape / number; HARD/EXPERT -> the three
# two-attribute pairs), so a family index is always in ``range(3)``.
RULE_FAMILY_COUNT = 3

# Length of one Play campaign. Mirrors ``CAMPAIGN_CONDITIONS`` in web/app.js.
CAMPAIGN_GAME_COUNT = 6

# Redraw attempts before falling back to a rotation at the block boundary.
_MAX_RESHUFFLES = 10


def _campaign_rng(campaign_id: str) -> random.Random:
    """Seed an RNG from *campaign_id*.

    Uses sha256 rather than the builtin ``hash()``: string hashing is salted
    per process by PYTHONHASHSEED, so a server restart would give the same
    campaign a different schedule and a resuming player would meet a
    different attribute mid-campaign.
    """
    digest = hashlib.sha256(campaign_id.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def campaign_rule_schedule(campaign_id: str) -> list[int]:
    """Return the active rule indices for the six games of *campaign_id*.

    Two shuffled blocks of ``[0, 1, 2]`` concatenated, so each family appears
    exactly twice. The second block is redrawn while its first entry repeats
    the first block's last entry, which keeps one family off two consecutive
    games; after ``_MAX_RESHUFFLES`` unlucky draws it is rotated instead so
    the function always terminates.
    """
    rng = _campaign_rng(campaign_id)
    families = list(range(RULE_FAMILY_COUNT))
    block_a = rng.sample(families, RULE_FAMILY_COUNT)
    block_b = rng.sample(families, RULE_FAMILY_COUNT)
    for _ in range(_MAX_RESHUFFLES):
        if block_b[0] != block_a[-1]:
            break
        block_b = rng.sample(families, RULE_FAMILY_COUNT)
    if block_b[0] == block_a[-1]:
        block_b = block_b[1:] + block_b[:1]
    return block_a + block_b


def rule_index_for(
    campaign_id: str | None,
    campaign_index: int,
    fallback_seed: int,
) -> int:
    """Return the active rule index for a single game.

    Args:
        campaign_id: Sanitized campaign id, or None/blank for a one-off game.
        campaign_index: 0-based position of this game inside the campaign.
            Values past the end wrap rather than raise.
        fallback_seed: The game's own seed, used when there is no campaign to
            schedule against.
    """
    if not campaign_id:
        return random.Random(fallback_seed).randrange(RULE_FAMILY_COUNT)
    schedule = campaign_rule_schedule(campaign_id)
    return schedule[campaign_index % len(schedule)]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_rule_schedule.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add interface/rule_schedule.py tests/unit/test_rule_schedule.py
git commit -m "feat(arena): add deterministic campaign rule-family schedule"
```

> iCloud 때문에 `git commit`이 2분을 넘길 수 있다. 타임아웃되면 백그라운드로 재실행하고, 재시도 전 `.git/index.lock`이 남아 있으면 지운다.

---

### Task 2: `SignalGameModule`에 `rule_index` 도입

**Files:**
- Modify: `src/squid_game/tasks/signal_game/module.py` (`__init__` 136-145, `initialize` 183-208, `reset` 210-227)
- Test: `tests/unit/test_signal_game_v3.py` (파일 끝에 추가)

**Interfaces:**
- Consumes: 없음 (Task 1과 독립. 인덱스는 호출자가 준다).
- Produces: `SignalGameModule.initialize(difficulty, seed=None, *, rule_index: int | None = None, **kwargs)` — `None`이면 인덱스 0. `reset()`은 그 값을 보존한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_signal_game_v3.py` 맨 끝에 추가:

```python
# ---------------------------------------------------------------------------
# Active rule selection (Web Arena campaign rule-family rotation)
# ---------------------------------------------------------------------------


def _rule_attribute(module: SignalGameModule) -> str:
    """First attribute named by the active rule description.

    ``"If color is red then go_left, otherwise stay."`` -> ``"color"``.
    """
    return module.get_active_rule_description().lower().split()[1]


def test_default_rule_index_is_zero_regression_guard() -> None:
    """No rule_index means index 0 — the LLM experiment path must not move.

    ``core/engine.py`` never passes rule_index, so this pins the behaviour the
    2026-04-22 canonical runs were produced under.
    """
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EASY, seed=42)
    assert _rule_attribute(m) == "color"
    assert m.get_active_rule_description() == (
        "If color is red then go_left, otherwise stay."
    )


@pytest.mark.parametrize(
    "rule_index,expected_attribute",
    [(0, "color"), (1, "shape"), (2, "number")],
)
def test_rule_index_selects_the_attribute_family(
    rule_index: int, expected_attribute: str
) -> None:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EASY, seed=42, rule_index=rule_index)
    assert _rule_attribute(m) == expected_attribute


def test_rule_index_wraps_when_out_of_range() -> None:
    """Defensive: a future difficulty with fewer candidate rules must not
    raise IndexError."""
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EASY, seed=42, rule_index=5)
    assert _rule_attribute(m) == "number"  # 5 % 3 == 2


def test_reset_preserves_rule_index() -> None:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EASY, seed=42, rule_index=2)
    m.reset()
    assert _rule_attribute(m) == "number"


@pytest.mark.parametrize(
    "difficulty,rule_index,expected_count",
    [
        (Difficulty.EASY, 1, 3),
        (Difficulty.EASY, 2, 3),
        (Difficulty.HARD, 1, 5),
        (Difficulty.HARD, 2, 5),
    ],
)
def test_few_shot_examples_work_for_every_family(
    difficulty: Difficulty, rule_index: int, expected_count: int
) -> None:
    """few-shot construction re-parses the rule description with a regex, so
    it must hold for shape/number rules too — not just the colour rule that
    used to be the only reachable one."""
    m = SignalGameModule()
    m.initialize(difficulty=difficulty, seed=42, rule_index=rule_index)
    examples = m.generate_few_shot_examples()
    assert len(examples) == expected_count
    active = m._rules[rule_index]
    for signal, action in examples:
        assert action == active.evaluate(signal)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_signal_game_v3.py -k "rule_index or rule_attribute or few_shot_examples_work or reset_preserves" -v`
Expected: FAIL — `test_rule_index_selects_the_attribute_family[1-shape]` 등이 `assert 'color' == 'shape'`로 실패. (`rule_index`는 아직 `**kwargs`에 삼켜져 무시된다. `test_default_rule_index_is_zero_regression_guard`는 이미 통과한다 — 정상이다. 그 테스트의 역할은 앞으로 깨지지 않게 지키는 것이다.)

- [ ] **Step 3: `__init__` docstring 항목 갱신**

`src/squid_game/tasks/signal_game/module.py`의 클래스 docstring에서 `_active_rule_index` 줄(130행 근처)을 바꾼다.

찾을 문자열:
```
        _active_rule_index: Index into ``_rules`` for the currently active rule.
```
바꿀 문자열:
```
        _active_rule_index: Index into ``_rules`` for the currently active
            rule. Defaults to 0; ``initialize(rule_index=...)`` overrides it
            so Web Arena can give each campaign game a different attribute
            family.
```

- [ ] **Step 4: `initialize()` 구현**

같은 파일 `initialize()`의 시그니처와 본문을 바꾼다.

찾을 문자열:
```python
    def initialize(
        self,
        difficulty: Difficulty,
        seed: int | None = None,
        **kwargs,
    ) -> None:
```
바꿀 문자열:
```python
    def initialize(
        self,
        difficulty: Difficulty,
        seed: int | None = None,
        rule_index: int | None = None,
        **kwargs,
    ) -> None:
```

이어서 docstring의 Keyword Args 블록 바로 위(`Creates a dedicated RNG instance...` 문단 뒤)에 인자 설명을 추가한다. 찾을 문자열:
```
        Keyword Args:
            num_few_shot: Override the number of few-shot examples at Turn 1.
```
바꿀 문자열:
```
        Args:
            difficulty: Controls the complexity of the generated rules.
            seed: Seed for this module's dedicated RNG.
            rule_index: Which candidate rule becomes the active one. None
                keeps the historical behaviour (index 0), which is what the
                LLM experiment path relies on. Out-of-range values wrap.

        Keyword Args:
            num_few_shot: Override the number of few-shot examples at Turn 1.
```

마지막으로 본문의 인덱스 대입을 바꾼다. 찾을 문자열 (`initialize()` 안, 203행):
```python
        self._rules = generate_rules(difficulty, self._rng)
        self._active_rule_index = 0
        self._current_signal = None
        self._turn_history = []
        self._cumulative_score = 0.0
        self._num_few_shot = kwargs.get("num_few_shot")
```
바꿀 문자열:
```python
        self._rules = generate_rules(difficulty, self._rng)
        self._requested_rule_index = rule_index
        self._active_rule_index = self._resolve_rule_index()
        self._current_signal = None
        self._turn_history = []
        self._cumulative_score = 0.0
        self._num_few_shot = kwargs.get("num_few_shot")
```

- [ ] **Step 5: `__init__`에 필드 추가**

찾을 문자열 (`__init__` 안):
```python
        self._rules: list[Rule] = []
        self._active_rule_index: int = 0
```
바꿀 문자열:
```python
        self._rules: list[Rule] = []
        self._requested_rule_index: int | None = None
        self._active_rule_index: int = 0
```

- [ ] **Step 6: `reset()`과 해석 헬퍼 구현**

찾을 문자열 (`reset()` 안):
```python
        self._rules = generate_rules(self._difficulty, self._rng)
        self._active_rule_index = 0
        self._current_signal = None
```
바꿀 문자열:
```python
        self._rules = generate_rules(self._difficulty, self._rng)
        self._active_rule_index = self._resolve_rule_index()
        self._current_signal = None
```

`reset()`의 docstring에도 한 줄 덧붙인다. 찾을 문자열:
```
        Note: ``_num_few_shot`` and ``_curriculum_turns`` are intentionally
        preserved — they are per-session config set in ``initialize()``,
        not per-season state.
```
바꿀 문자열:
```
        Note: ``_num_few_shot``, ``_curriculum_turns`` and
        ``_requested_rule_index`` are intentionally preserved — they are
        per-session config set in ``initialize()``, not per-season state.
```

그리고 `_ensure_initialized()` 바로 앞에 헬퍼를 추가한다. 찾을 문자열:
```python
    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called."""
```
바꿀 문자열:
```python
    def _resolve_rule_index(self) -> int:
        """Clamp the requested rule index into ``_rules`` range.

        None (the LLM experiment path, which never passes one) means index 0.
        Modulo rather than an exception so a future difficulty producing fewer
        candidate rules degrades instead of crashing a live session.
        """
        if self._requested_rule_index is None or not self._rules:
            return 0
        return self._requested_rule_index % len(self._rules)

    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called."""
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_signal_game_v3.py -v`
Expected: PASS (신규 10건 포함, 기존 테스트 전부 유지)

- [ ] **Step 8: 태스크 모듈 전체 회귀 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_signal_game_probe_contract.py tests/unit/test_framing_templates.py -v`
Expected: PASS — 룰 description 포맷과 probe 채점이 그대로임을 확인

- [ ] **Step 9: 커밋**

```bash
git add src/squid_game/tasks/signal_game/module.py tests/unit/test_signal_game_v3.py
git commit -m "feat(signal-game): allow selecting the active rule index"
```

---

### Task 3: `HumanGameSession` 통과 배선

**Files:**
- Modify: `interface/human_game.py` (`__init__` 134-151 시그니처, `self._task.initialize(...)` 164-169)
- Test: `tests/unit/test_human_game.py` (파일 끝에 추가)

**Interfaces:**
- Consumes: Task 2의 `SignalGameModule.initialize(..., rule_index=...)`.
- Produces: `HumanGameSession(..., rule_index: int | None = None)` — 태스크 모듈로 그대로 전달만 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_human_game.py` 맨 끝에 추가:

```python
# ---------------------------------------------------------------------------
# Campaign rule-family rotation
# ---------------------------------------------------------------------------


def _session_rule_attribute(session: HumanGameSession) -> str:
    """First attribute named by the session's active rule description."""
    return session._task.get_active_rule_description().lower().split()[1]


def test_rule_index_reaches_the_task_module() -> None:
    session = HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=42,
        total_turns=5,
        actual_death=False,
        num_few_shot=0,
        curriculum_turns=0,
        rule_index=2,
    )
    assert _session_rule_attribute(session) == "number"


def test_rule_index_defaults_to_the_first_rule() -> None:
    session = HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=42,
        total_turns=5,
        actual_death=False,
        num_few_shot=0,
        curriculum_turns=0,
    )
    assert _session_rule_attribute(session) == "color"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_human_game.py -k rule_index -v`
Expected: FAIL — `TypeError: HumanGameSession.__init__() got an unexpected keyword argument 'rule_index'`

- [ ] **Step 3: 생성자 시그니처 확장**

`interface/human_game.py`에서 찾을 문자열:
```python
        use_psuccess_probe: bool = True,
        forfeit_layer_config: ForfeitLayerConfig | None = None,
    ) -> None:
```
바꿀 문자열:
```python
        use_psuccess_probe: bool = True,
        forfeit_layer_config: ForfeitLayerConfig | None = None,
        rule_index: int | None = None,
    ) -> None:
```

- [ ] **Step 4: 태스크 초기화에 전달**

같은 파일에서 찾을 문자열:
```python
        self._task.initialize(
            difficulty=self._difficulty,
            seed=seed,
            num_few_shot=num_few_shot,
            curriculum_turns=curriculum_turns,
        )
```
바꿀 문자열:
```python
        # rule_index rotates the hidden-rule attribute family across the six
        # games of a Play campaign (see interface/rule_schedule.py). None
        # keeps the task module's historical index-0 behaviour.
        self._task.initialize(
            difficulty=self._difficulty,
            seed=seed,
            rule_index=rule_index,
            num_few_shot=num_few_shot,
            curriculum_turns=curriculum_turns,
        )
```

`rule_index`는 `task_name`과 무관하게 항상 전달된다. `voting_room`·`navigation`·`null_task`의 `initialize()`가 모두 `**kwargs`를 받으므로(각 module.py 참조) 이 키워드는 그쪽에서 조용히 무시된다 — 분기 없이 안전하다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_human_game.py tests/unit/test_human_game_preview.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add interface/human_game.py tests/unit/test_human_game.py
git commit -m "feat(arena): forward rule_index from HumanGameSession to the task"
```

---

### Task 4: `/api/new_game` 배선

**Files:**
- Modify: `interface/api.py` (import 블록, `NewGameRequest` 251-296, `new_game()` 핸들러 783-812)
- Test: `tests/unit/test_api_web_arena.py` (파일 끝에 추가)

**Interfaces:**
- Consumes: Task 1의 `rule_index_for()`, Task 3의 `HumanGameSession(..., rule_index=...)`.
- Produces: `NewGameRequest.campaign_index: int` (기본값 0, `ge=0`). 응답 스키마는 바뀌지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_api_web_arena.py` 맨 끝에 추가:

```python
# ---------------------------------------------------------------------------
# Campaign rule-family rotation
# ---------------------------------------------------------------------------


def _active_rule_attribute(api_module, session_id: str) -> str:
    """Attribute family of a live session's hidden rule.

    Read straight off the in-process session: the API deliberately never
    exposes the ground-truth rule to the client, so there is nothing in the
    response body to assert on.
    """
    session = api_module._sessions[session_id]
    return session._task.get_active_rule_description().lower().split()[1]


def test_campaign_games_rotate_the_rule_attribute(api_module, client) -> None:
    """The six games of one campaign use each family exactly twice, and never
    the same family twice in a row."""
    attributes = []
    for index in range(6):
        resp = _new_game(
            client,
            nickname="rotator",
            password="pw",
            campaign_id="camp-rotation-1",
            campaign_index=index,
        )
        assert resp.status_code == 200, resp.text
        attributes.append(
            _active_rule_attribute(api_module, resp.json()["session_id"])
        )

    from collections import Counter

    assert Counter(attributes) == {"color": 2, "shape": 2, "number": 2}
    assert all(a != b for a, b in zip(attributes, attributes[1:]))


def test_same_campaign_index_is_stable_across_restarts(api_module, client) -> None:
    """Reloading mid-campaign (new seed, same campaign_index) keeps the family."""
    first = _new_game(
        client,
        nickname="resumer",
        password="pw",
        campaign_id="camp-resume-1",
        campaign_index=3,
        seed=11,
    )
    second = _new_game(
        client,
        nickname="resumer",
        password="pw",
        campaign_id="camp-resume-1",
        campaign_index=3,
        seed=99,
    )
    assert first.status_code == 200 and second.status_code == 200
    assert _active_rule_attribute(
        api_module, first.json()["session_id"]
    ) == _active_rule_attribute(api_module, second.json()["session_id"])


def test_new_game_without_campaign_index_still_works(client) -> None:
    """Backward compatible: older clients omit the field entirely."""
    resp = _new_game(client, nickname="legacy", password="pw")
    assert resp.status_code == 200, resp.text


def test_negative_campaign_index_is_rejected(client) -> None:
    resp = _new_game(
        client, nickname="bad", password="pw", campaign_index=-1
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_api_web_arena.py -k "rotate or campaign_index or restarts" -v`
Expected: FAIL — `test_campaign_games_rotate_the_rule_attribute`가 `Counter({'color': 6})`로 실패, `test_negative_campaign_index_is_rejected`는 422 대신 200 (알 수 없는 필드를 Pydantic이 무시)

- [ ] **Step 3: import 추가**

`interface/api.py`에서 찾을 문자열:
```python
from interface.human_game import HumanGameSession
```
바꿀 문자열:
```python
from interface.human_game import HumanGameSession
from interface.rule_schedule import rule_index_for
```

- [ ] **Step 4: 요청 필드 추가**

같은 파일 `NewGameRequest`에서 찾을 문자열:
```python
    campaign_id: str | None = Field(
        default=None,
        description=(
            "Optional client-supplied id shared by the 6 games of one Play "
            "campaign, so the Play Leaderboard can sum a player's cumulative "
            "score. Sanitized like the nickname; omitted for one-off games."
        ),
    )
```
바꿀 문자열:
```python
    campaign_id: str | None = Field(
        default=None,
        description=(
            "Optional client-supplied id shared by the 6 games of one Play "
            "campaign, so the Play Leaderboard can sum a player's cumulative "
            "score. Sanitized like the nickname; omitted for one-off games."
        ),
    )
    campaign_index: int = Field(
        default=0,
        ge=0,
        description=(
            "0-based position of this game within the Play campaign. Picks "
            "the hidden rule's attribute family from the campaign schedule "
            "(interface/rule_schedule.py) so the six games do not all share "
            "one family. Ignored for one-off games (no campaign_id)."
        ),
    )
```

- [ ] **Step 5: 핸들러에서 인덱스 계산**

같은 파일 `new_game()`에서 찾을 문자열:
```python
    game = HumanGameSession(
        task_name=req.task_name,
        difficulty=req.difficulty,
        framing=req.framing,
        forfeit_condition=req.forfeit_condition,
        seed=seed,
        total_turns=req.total_turns,
        actual_death=effective_actual_death,
        starting_score=req.starting_score,
        score_floor=req.score_floor,
        p_death_constant=req.p_death_constant,
        num_few_shot=req.num_few_shot,
        curriculum_turns=req.curriculum_turns,
    )
    _sessions[session_id] = game
    _nicknames[session_id] = nick
    _campaigns[session_id] = sanitize_campaign_id(req.campaign_id)
```
바꿀 문자열:
```python
    # Rotate the hidden rule's attribute family across a campaign's six games.
    # Derived from the sanitized campaign id (the value actually stored), so a
    # reload or a resume lands on the same family; games with no campaign fall
    # back to their own seed. See interface/rule_schedule.py.
    campaign_id = sanitize_campaign_id(req.campaign_id)
    rule_index = rule_index_for(campaign_id, req.campaign_index, seed)
    game = HumanGameSession(
        task_name=req.task_name,
        difficulty=req.difficulty,
        framing=req.framing,
        forfeit_condition=req.forfeit_condition,
        seed=seed,
        total_turns=req.total_turns,
        actual_death=effective_actual_death,
        starting_score=req.starting_score,
        score_floor=req.score_floor,
        p_death_constant=req.p_death_constant,
        num_few_shot=req.num_few_shot,
        curriculum_turns=req.curriculum_turns,
        rule_index=rule_index,
    )
    _sessions[session_id] = game
    _nicknames[session_id] = nick
    _campaigns[session_id] = campaign_id
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_api_web_arena.py -v`
Expected: PASS (신규 4건 포함). 이 파일에는 사전 존재하던 실패가 있을 수 있다 — 판정 기준은 "새로 깨진 것이 없다"이므로, 실패가 보이면 이 브랜치 작업 전 상태(`git stash` 후 동일 명령)와 비교한다.

- [ ] **Step 7: 커밋**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(api): rotate hidden-rule family per campaign game"
```

---

### Task 5: 클라이언트에서 `campaign_index` 전송

**Files:**
- Modify: `web/app.js` (`startGame()` POST 바디, 959-975)
- Test: 자동화 테스트 없음 (이 저장소에 JS 테스트 하네스가 없다). 수동 검증 절차를 아래에 둔다.

**Interfaces:**
- Consumes: Task 4의 `NewGameRequest.campaign_index`.
- Produces: 없음 (최종 배선).

- [ ] **Step 1: 페이로드에 한 줄 추가**

`web/app.js`에서 찾을 문자열:
```javascript
                campaign_id: this.campaignId,
                difficulty: this.difficulty,
```
바꿀 문자열:
```javascript
                campaign_id: this.campaignId,
                // 0-based position in the 6-game campaign. The server uses it
                // to pick this game's hidden-rule attribute family so the six
                // games don't all share one. Correct at every call site:
                // advanceCampaign() increments campaignIndex just before
                // startGame(), and resumeCampaign() restores the checkpoint's
                // index (= campaignResults.length, the unfinished game).
                campaign_index: this.campaignIndex,
                difficulty: this.difficulty,
```

- [ ] **Step 2: 다른 전송 지점이 없는지 확인**

Run: `grep -n "api/new_game" web/app.js`
Expected: `startGame()` 안의 한 곳만 나온다. 다른 곳이 나오면 그 호출자에도 같은 필드를 추가한다.

- [ ] **Step 3: 백엔드와 프론트엔드 기동 (터미널 2개)**

백엔드 — 저장소 루트에서:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
uv run --no-sync uvicorn interface.api:app --port 8502
```

프론트엔드 — 별도 터미널에서:
```bash
cd web && python -m http.server 5500
```

Expected: `http://localhost:5500`에서 아레나가 뜬다. `web/config.js`의 기본 API 주소가 `http://localhost:8502`이고 백엔드 기본 CORS 허용목록에 `http://localhost:5500`이 이미 들어 있어 환경변수 설정은 필요 없다 (`web/DEPLOY.md` §1). DSN 미설정 시 SQLite(`outputs/web_arena/web_arena.db`)로 떨어진다 — Postgres 불필요.

- [ ] **Step 4: 브라우저에서 3게임 수동 확인**

1. `http://localhost:5500`의 PLAY 탭에서 닉네임·비밀번호 입력 후 Easy 난이도로 캠페인 시작.
2. 게임 1·2·3을 각각 첫 턴만 진행하고 나머지는 아무 액션이나 눌러 끝까지 간다 (10턴).
3. 서버 콘솔이 아니라 **브라우저 개발자도구 Network 탭**에서 세 번의 `POST /api/new_game` 요청 바디를 열어 `campaign_index`가 각각 `0`, `1`, `2`인지 확인한다.
4. 각 게임의 History 패널에 뜨는 힌트 예시가 게임마다 다른 속성을 가리키는지 눈으로 확인한다 (예: 1게임은 색이 결정적, 2게임은 모양이 결정적).

관찰 결과를 커밋 메시지 본문이나 PR 설명에 기록한다.

- [ ] **Step 5: 전체 스위트 회귀 확인**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit -q`
Expected: 이 작업 전과 비교해 **새로 깨진 테스트가 없다**. (`tests/unit/test_phase3_configs.py`와 `test_forfeit_layer_config_yaml.py`의 5건은 `configs/experiment/`가 비어 있는 기존 실패다 — `CLAUDE.md` 참조. Web Arena 관련 사전 실패도 있을 수 있다.)

- [ ] **Step 6: 커밋**

```bash
git add web/app.js
git commit -m "feat(web): send campaign_index so each campaign game rotates its rule family"
```

---

### Task 6: 문서 갱신

**Files:**
- Modify: `CLAUDE.md` (Directory Structure의 `interface/` 항목)

**Interfaces:**
- Consumes: Task 1-5의 최종 동작.
- Produces: 없음.

- [ ] **Step 1: `interface/` 설명에 새 모듈 반영**

`CLAUDE.md`에서 찾을 문자열:
```
interface/       # Web Arena backend — api.py (FastAPI), arena.py, human_game.py,
                 # persistence/ (SQLite + Postgres mirrored), seeding.py
```
바꿀 문자열:
```
interface/       # Web Arena backend — api.py (FastAPI), arena.py, human_game.py,
                 # rule_schedule.py (campaign hidden-rule family rotation),
                 # persistence/ (SQLite + Postgres mirrored), seeding.py
```

- [ ] **Step 2: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs: note rule_schedule.py in the interface/ layout"
```

---

## 완료 기준

- `tests/unit/test_rule_schedule.py` 9건 전부 통과.
- `initialize()`를 `rule_index` 없이 호출하면 활성 룰이 인덱스 0 — 회귀 테스트로 고정됨.
- 한 캠페인의 6게임이 속성 계열을 2회씩 사용하고 연속 중복이 없음 — API 레벨 테스트로 확인됨.
- `src/squid_game/core/engine.py` diff 없음.
- `web/index.html`·`web/styles.css` diff 없음, `web/app.js` diff는 POST 바디 한 필드(+주석)뿐.
