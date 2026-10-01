# Web Arena Signal Puzzle v2 인간 플레이 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사람이 Web Arena에서 `signal_mode: per_turn_puzzle`을 LLM과 같은 엔진(`SignalGameModule` + `prepare`/`score`)으로 플레이하게 한다. 10턴, 라이프 3, flat +10, 결정 우선 2단계 턴, 공개된 규칙 모양을 드롭다운 폼으로 채워 한 줄 RULE로 전송, 결과는 LLM 런과 같은 `SeasonResult` 모양으로 기록.

**Architecture:** `HumanGameSession`이 퍼즐 모드에서 `prepare` → `score`를 부르고(순차 모드는 `apply_action` 그대로), `TurnState`에 `PuzzleTurnView`(모양·힌트·query)를 싣는다. API는 `NewGameRequest.signal_mode`, `TurnStateResponse.{signal_mode, puzzle}`만 추가한다(응답 필드 추가만, 이름 변경 없음). 프런트는 `puzzle.shape`를 `<select>` 폼으로 그려 `parse_rule_text` 문법의 한 줄을 조립해 기존 `probe_answer`로 보낸다. 서버는 빈 RULE / 파싱 실패 / 모양 불일치를 400으로 거절한다. 분석용 기록은 `save_result()`의 JSONL(`season_results.jsonl`, 로더가 읽는 그 파일)이다.

**Tech Stack:** Python 3.12, FastAPI + pydantic v2, Alpine.js(빌드 없음), pytest. 테스트는 워크트리 루트에서 `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest …`로 돈다(트리 안 `.venv`는 `squid_game`을 import하지 못한다).

**Spec:** `docs/history/specs/2026-09-06-web-signal-puzzle-human-play-design.md`. 먼저 읽는다. 퍼즐 엔진 자체는 `docs/history/specs/2026-09-06-signal-puzzle-shaped-rules-design.md`(v2)이며 이미 구현되어 있다.

## Global Constraints

- 워크트리 `.claude/worktrees/signal-game-per-turn-puzzle`, 브랜치 `feat/signal-game-per-turn-puzzle`에서 작업한다. 메인 체크아웃으로 `cd`하지 않는다. `git stash` 금지.
- 구현 서브에이전트는 **git 명령을 실행하지 않는다.** 커밋 단계는 오케스트레이터가 수행한다.
- 테스트 명령: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest <paths> -q -p no:cacheprovider`. 기준선: `tests/unit/test_api_web_arena.py::test_app_imports_and_registers_all_endpoints`는 이미 깨져 있다(메모리 노트 "Web Arena baseline test breakage"). "새 실패 없음"으로 판정한다.
- **건드리면 안 되는 파일**(동시 작업 중): `configs/experiment/signal_puzzle_*.yaml`, `tests/integration/test_signal_puzzle_e2e.py`, `game/squid_game/evaluation/shared/loaders.py`, `CLAUDE.md`, `docs/paper/**`. 이 계획의 어떤 태스크도 이 파일들을 편집하지 않는다.
- 순차 모드(`signal_mode: sequential`)의 동작은 바이트 단위로 같아야 한다: `tests/unit/test_human_game*.py`, `tests/unit/test_api_web_arena*.py`, `tests/characterization/`가 기존 기대값 그대로 통과한다(단, `test_api_contract.py`의 `STATE_KEYS`와 OpenAPI 스냅샷은 Task 3에서 추가 필드만큼 갱신한다).
- 코드는 영어, 문서는 한국어, 프롬프트/UI 문구는 영어. 새로 쓰는 산문에 em-dash를 쓰지 않는다.
- `outputs/` 아래는 절대 `git add`하지 않는다. 테스트가 `save_result()`를 호출할 때는 반드시 `monkeypatch.chdir(tmp_path)` 뒤에 한다(그 메서드는 CWD 기준 상대 경로 `outputs/api_sessions/`에 쓴다).
- 엔진 계약(이미 구현): 사다리 10턴(`configs/tasks/signal_game.yaml`), `cached_puzzle(seed, turn, spec)`, 원자 조건 20개 라벨은 `squid_game.tasks.signal_game.puzzle.ATOMS[i].label`, 행동 4개 `ACTIONS = ["go_left", "go_right", "stay", "jump"]`, `PuzzleRule.description` 형식 `if <cond>: <act>; elif <cond> and <cond>: <act>; else: <act>`.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `game/squid_game/tasks/signal_game/module.py` | `current_puzzle` 읽기 전용 프로퍼티 추가 (5줄) | 1 |
| `web/squid_arena/human_game.py` | `SIGNAL_MODES`, `PUZZLE_*` 상수, `PuzzleTurnView`, `TurnState.{signal_mode,puzzle}`, 생성자 분기, `get_turn_state` 퍼즐 분기 | 1 |
| `web/squid_arena/human_game.py` | `submit_action` 퍼즐 채점(`score`), `validate_rule_text`, `settings_snapshot`, FORFEIT `ground_truth_rule` | 2 |
| `tests/unit/test_human_game_puzzle.py` | 세션 단위 테스트 (Task 1에서 생성, Task 2에서 확장) | 1, 2 |
| `web/squid_arena/schemas.py` | `PuzzleSignal`, `PuzzleClue`, `PuzzleTurn`, `NewGameRequest.signal_mode`, `TurnStateResponse.{signal_mode,puzzle}` | 3 |
| `web/squid_arena/routes_game.py` | new_game 모드 검증/기본값/400, state 퍼즐 뷰, action RULE 검증 | 3 |
| `tests/unit/test_api_web_arena_puzzle.py` | API 계약 테스트 | 3 |
| `tests/characterization/test_api_contract.py`, `tests/characterization/snapshots/api/openapi.json` | `STATE_KEYS` +2, 스냅샷 재생성 | 3 |
| `web/frontend/app.js` (helpers 구간) | `PUZZLE_ACTIONS`, `PUZZLE_CONDITION_GROUPS`, `conditionAttribute`, `emptyPuzzleSlots`, `puzzleSlotErrors`, `composePuzzleRule` | 4 |
| `tests/unit/test_web_puzzle_rule_composer.py` | 조립 문자열 → `parse_rule_text` 왕복 계약, app.js 라벨 = `ATOMS` 라벨 | 4 |
| `web/frontend/app.js` (playScreen), `web/frontend/index.html` | Alpine 상태, Stage 2 퍼즐 폼, 설정 카드 Mode, 체크포인트, `save=true`, 로그 설정 라벨 | 5 |
| `tests/characterization/test_web_puzzle_parity.py` | 같은 seed의 사람/LLM 스텁이 같은 10문제를 받는지 | 6 |
| 이 계획 파일 | 구현 노트 | 6 |

---

### Task 1: 엔진 접근자 + `HumanGameSession` 퍼즐 모드 초기화와 턴 상태

**Files:**
- Modify: `game/squid_game/tasks/signal_game/module.py` (프로퍼티 1개 추가)
- Modify: `web/squid_arena/human_game.py`
- Create: `tests/unit/test_human_game_puzzle.py`

**Interfaces:**
- Consumes: `squid_game.tasks.signal_game.puzzle.{Puzzle, render_shape_block, render_shape_hint}`, `squid_game.core.turn_prompts.format_outcome_history_block(history, max_history_turns, *, lives_label)`, `squid_game.models.state.{GameState, TurnContext}`, `squid_game.tasks.base.TaskContext`.
- Produces (Task 2, 3이 사용):
  - `SignalGameModule.current_puzzle -> Puzzle | None` (property)
  - `human_game.SIGNAL_MODES: tuple[str, ...]`, `PUZZLE_TOTAL_TURNS = 10`, `PUZZLE_LIVES_TOTAL = 3`
  - `human_game.PuzzleTurnView(puzzle_turn: int, shape: list[int], shape_block: str, rule_template_hint: str, clues: list[dict], query: dict, n_clues: int)`
  - `TurnState.signal_mode: str`, `TurnState.puzzle: PuzzleTurnView | None`
  - `HumanGameSession.__init__(..., signal_mode: str = "sequential")`, `HumanGameSession.signal_mode` property
  - 내부: `self._current_task_ctx: TaskContext | None`, `self._outcome_history: list[dict]`, `_turn_context(turn_number)`, `_lives_label()`, `_build_puzzle_view()`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_human_game_puzzle.py`:

```python
"""``HumanGameSession`` in ``signal_mode='per_turn_puzzle'`` (spec 2026-09-06 web-signal-puzzle §5).

Drives the session object directly (no HTTP). The engine's puzzle mode is
the reference: every clue, shape and hidden rule asserted here is regenerated
with ``generate_puzzle(puzzle_rng(seed, turn), spec)`` exactly as
``SignalGameModule.get_observation`` does, so a human game and an LLM season
sharing a seed are pinned to the same ten puzzles.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from squid_arena.human_game import (
    PUZZLE_LIVES_TOTAL,
    PUZZLE_TOTAL_TURNS,
    HumanGameSession,
    PuzzleTurnView,
)
from squid_game.tasks.signal_game.puzzle import (
    generate_puzzle,
    puzzle_rng,
    render_shape_block,
    render_shape_hint,
)
from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from squid_game.tasks.signal_game.rules import ACTIONS

SEED = 43


def _session(**overrides) -> HumanGameSession:
    kwargs = dict(
        task_name="signal_game",
        difficulty="medium",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=SEED,
        total_turns=PUZZLE_TOTAL_TURNS,
        lives_total=PUZZLE_LIVES_TOTAL,
        signal_mode="per_turn_puzzle",
    )
    kwargs.update(overrides)
    return HumanGameSession(**kwargs)


def _expected_puzzle(turn: int, seed: int = SEED):
    ladder = load_signal_puzzle_config()
    return generate_puzzle(puzzle_rng(seed, turn), ladder.spec_for_turn(turn))


def _correct(game: HumanGameSession) -> str:
    """This turn's answer, read off the module's public puzzle accessor."""
    return game._task.current_puzzle.correct_action


def _rule(game: HumanGameSession) -> str:
    return game._task.current_puzzle.rule.description


class TestInit:
    def test_sequential_is_still_the_default(self) -> None:
        game = HumanGameSession(
            task_name="signal_game", difficulty="easy", framing="true_baseline",
            forfeit_condition="allowed", seed=1, total_turns=3,
            num_few_shot=0, curriculum_turns=0,
        )
        assert game.signal_mode == "sequential"
        assert game.get_turn_state().puzzle is None
        assert game.get_turn_state().signal_mode == "sequential"

    def test_puzzle_mode_shape(self) -> None:
        game = _session()
        assert game.signal_mode == "per_turn_puzzle"
        assert game.lives_enabled is True
        assert game.lives_total == 3
        state = game.get_turn_state()
        assert state.total_turns == 10
        assert state.lives_remaining == 3
        assert state.signal_mode == "per_turn_puzzle"

    def test_rejects_unknown_mode(self) -> None:
        with pytest.raises(ValueError, match="signal_mode"):
            _session(signal_mode="bogus")

    def test_rejects_season_longer_than_the_ladder(self) -> None:
        with pytest.raises(ValueError, match="puzzle_ladder"):
            _session(total_turns=11)

    def test_rejects_non_signal_task(self) -> None:
        with pytest.raises(ValueError, match="signal_game"):
            _session(task_name="voting_room")


class TestTurnState:
    def test_puzzle_view_matches_the_engine_puzzle(self) -> None:
        game = _session()
        view = game.get_turn_state().puzzle
        assert isinstance(view, PuzzleTurnView)
        expected = _expected_puzzle(1)
        assert view.puzzle_turn == 1
        assert view.shape == list(expected.shape)
        assert view.shape_block == render_shape_block(expected.shape)
        assert view.rule_template_hint == render_shape_hint(expected.shape)
        assert [c["text"] for c in view.clues] == [str(c) for c in expected.clues]
        assert view.n_clues == len(expected.clues)
        assert view.query["text"] == str(expected.query)
        assert view.query == {
            "color": expected.query.color,
            "shape": expected.query.shape,
            "number": expected.query.number,
            "text": str(expected.query),
        }
        for clue, exp in zip(view.clues, expected.clues, strict=True):
            assert clue["action"] in ACTIONS
            assert (clue["color"], clue["shape"], clue["number"]) == (
                exp.signal.color, exp.signal.shape, exp.signal.number
            )

    def test_view_never_carries_the_answer(self) -> None:
        game = _session()
        view = game.get_turn_state().puzzle
        blob = json.dumps(dataclasses.asdict(view))
        assert "hidden_rule" not in blob
        assert "correct_action" not in blob
        assert _rule(game) not in blob

    def test_observation_and_rules_are_the_puzzle_prompts(self) -> None:
        state = _session().get_turn_state()
        assert state.observation.startswith(
            "Turn 1. This round's rule has exactly this shape"
        )
        assert "if / elif / else" in state.system_rules
        assert "in one line" in state.probe_question
        assert state.available_actions == list(ACTIONS)

    def test_repolling_the_same_turn_is_idempotent(self) -> None:
        game = _session()
        first = game.get_turn_state().puzzle
        second = game.get_turn_state().puzzle
        assert first == second

    def test_same_seed_same_puzzle_different_seed_different_puzzle(self) -> None:
        a = _session().get_turn_state().puzzle
        b = _session().get_turn_state().puzzle
        c = _session(seed=SEED + 1).get_turn_state().puzzle
        assert a == b
        assert c.clues != a.clues or c.query != a.query
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_human_game_puzzle.py -q -p no:cacheprovider`
Expected: ImportError (`PUZZLE_LIVES_TOTAL` 등 없음).

- [ ] **Step 3: `module.py`에 접근자 추가**

`game/squid_game/tasks/signal_game/module.py`의 `get_rule_template_hint` 메서드 **바로 앞**에 추가한다 (`Puzzle`은 이미 이 파일에 import되어 있다):

```python
    @property
    def current_puzzle(self) -> Puzzle | None:
        """This turn's puzzle in ``per_turn_puzzle`` mode, or ``None``.

        Set by ``get_observation`` / ``prepare`` and cleared by ``reset``;
        always ``None`` in ``sequential`` mode. Read-only. The Web Arena's
        ``HumanGameSession`` builds its Stage 2 view (shape, clues, query)
        from it instead of re-parsing the rendered observation text.
        """
        return self._current_puzzle
```

- [ ] **Step 4: `human_game.py` 수정**

(a) import 블록에 추가:

```python
from squid_game.core.turn_prompts import format_outcome_history_block
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.base import TaskContext, TaskModule, TaskOutcome
from squid_game.tasks.signal_game.puzzle import render_shape_block, render_shape_hint
from squid_game.tasks.signal_game.signals import Signal
```

(기존 `from squid_game.models.state import TurnContext`와 `from squid_game.tasks.base import TaskModule, TaskOutcome` 줄은 위 줄로 대체한다.)

(b) `_ELIMINATION_RULE_HEADER` 정의 위(상수 구간)에 추가:

```python
# --- Signal Game stimulus modes (2026-09-06 per-turn puzzle human play) -----
# ``sequential`` is the historical human game (one hidden rule per game,
# campaign rule rotation). ``per_turn_puzzle`` drives SignalGameModule exactly
# as UnifiedTurnManager does: a fresh shape-disclosed puzzle every turn from
# the 10-turn ladder, scored through ``prepare`` -> ``score``.
SIGNAL_MODES: tuple[str, ...] = ("sequential", "per_turn_puzzle")

# Session shape of a puzzle game, applied by the API when the request does
# not pin the field. Mirrors configs/experiment/signal_puzzle_*.yaml
# (total_turns 10, lives.initial 3).
PUZZLE_TOTAL_TURNS = 10
PUZZLE_LIVES_TOTAL = 3
```

(c) `TurnState` dataclass 바로 위에 추가:

```python
def _signal_view(signal: Signal) -> dict:
    """Wire shape of one card: attributes plus the engine's own text."""
    return {
        "color": signal.color,
        "shape": signal.shape,
        "number": signal.number,
        "text": str(signal),
    }


@dataclass
class PuzzleTurnView:
    """Stage 2 view of one puzzle turn: everything the player may see.

    Deliberately excludes ``hidden_rule`` / ``correct_action`` /
    ``n_minimal_clues`` / ``query_overlap_count``; those stay in
    ``TurnResult.task_metadata`` only.
    """

    puzzle_turn: int
    shape: list[int]
    shape_block: str
    rule_template_hint: str
    clues: list[dict]
    query: dict
    n_clues: int
```

(d) `TurnState`의 마지막 필드(`cohort_size`) 뒤에 추가:

```python
    # --- Signal Game stimulus mode (2026-09-06) ---
    signal_mode: str = "sequential"
    puzzle: PuzzleTurnView | None = None
```

(e) `HumanGameSession.__init__` 시그니처의 마지막 파라미터 `reward_mode: str = "flat",` 뒤에 `signal_mode: str = "sequential",`을 추가하고, 본문의 `self._task: TaskModule = get_task(task_name)()` 부터 `self._task.initialize(...)` 호출까지를 다음으로 교체:

```python
        if signal_mode not in SIGNAL_MODES:
            raise ValueError(
                f"signal_mode must be one of {SIGNAL_MODES}, got {signal_mode!r}"
            )
        if signal_mode == "per_turn_puzzle" and task_name != "signal_game":
            raise ValueError(
                "signal_mode 'per_turn_puzzle' is a signal_game mode; "
                f"got task_name={task_name!r}"
            )
        self._signal_mode = signal_mode

        # Core components (same as GameEngine)
        self._task: TaskModule = get_task(task_name)()
        if signal_mode == "per_turn_puzzle":
            # Same call the engine makes (core/engine.py): the module draws
            # every turn's puzzle from random.Random(f"{seed}:{turn}") and
            # validates total_turns against the ladder. num_few_shot /
            # curriculum_turns / rule_index are sequential-only knobs and
            # are not passed (the module would only warn about them).
            self._task.initialize(
                difficulty=self._difficulty,
                seed=seed,
                rule_index=None,
                signal_mode="per_turn_puzzle",
                total_turns=total_turns,
            )
        else:
            # rule_index rotates the hidden-rule attribute family across the
            # six games of a Play campaign (see web/squid_arena/rule_schedule.py).
            # None keeps the task module's historical index-0 behaviour.
            self._task.initialize(
                difficulty=self._difficulty,
                seed=seed,
                rule_index=rule_index,
                num_few_shot=num_few_shot,
                curriculum_turns=curriculum_turns,
            )
```

그리고 `self._current_probe_question: str = ""` 줄 뒤에 추가:

```python
        # --- Puzzle mode per-turn state -------------------------------------
        # ``prepare()`` result of the turn on screen; ``submit_action`` merges
        # its metadata with ``score()``'s exactly as UnifiedTurnManager does.
        self._current_task_ctx: TaskContext | None = None
        # Outcome-only history (history_mode: outcome), rendered ahead of the
        # puzzle observation by ``format_outcome_history_block``.
        self._outcome_history: list[dict] = []
```

(f) `lives_remaining` 프로퍼티 앞에 프로퍼티와 헬퍼 추가:

```python
    @property
    def signal_mode(self) -> str:
        """``"sequential"`` or ``"per_turn_puzzle"``."""
        return self._signal_mode

    def _lives_label(self) -> str:
        """Counter word for the outcome history: ``lives`` on a threat rung,
        ``attempts`` at level 0 and off the ladder (the vocabulary contract
        ``_framing_display_text`` already honours)."""
        return "lives" if self._threat_level else "attempts"

    def _turn_context(self, turn_number: int) -> TurnContext:
        """The ``TurnContext`` handed to ``SignalGameModule.prepare``."""
        return TurnContext(
            turn_number=turn_number,
            total_turns=self._total_turns,
            season_id=self._season_id,
            cumulative_score=self._cumulative_score,
            p_death=0.0,
            framing=self._framing,
            forfeit_condition=self._forfeit_cond,
            difficulty=self._difficulty,
            lives_remaining=self._lives_remaining,
            lives_total=self._lives_total,
            threat_level=self._threat_level,
        )

    def _build_puzzle_view(self) -> PuzzleTurnView:
        puzzle = getattr(self._task, "current_puzzle", None)
        if puzzle is None:
            raise RuntimeError("no puzzle prepared for this turn")
        return PuzzleTurnView(
            puzzle_turn=puzzle.spec.turn,
            shape=list(puzzle.shape),
            shape_block=render_shape_block(puzzle.shape),
            rule_template_hint=render_shape_hint(puzzle.shape),
            clues=[
                {**_signal_view(c.signal), "action": c.action, "text": str(c)}
                for c in puzzle.clues
            ],
            query=_signal_view(puzzle.query),
            n_clues=len(puzzle.clues),
        )
```

(g) `get_turn_state`: game-over 분기의 `TurnState(...)`에 `signal_mode=self._signal_mode,` 인자를 추가하고, 본문 중

```python
        framing_text = self._framing_display_text()
        system_rules = self._task.get_system_rules()
        observation = self._task.get_observation(turn_num)
        # Prepend cumulative history (matching TurnManager behavior).
        history_block = self._format_turn_history()
        if history_block:
            observation = f"{history_block}\n\n{observation}"
```

을 다음으로 교체:

```python
        framing_text = self._framing_display_text()
        system_rules = self._task.get_system_rules()
        puzzle_view: PuzzleTurnView | None = None
        if self._signal_mode == "per_turn_puzzle":
            # Same entry point as UnifiedTurnManager: prepare() renders the
            # observation and fills the spec §9 metadata in one go. The
            # puzzle is memoised per (seed, turn), so a polled /api/state
            # returns the identical round.
            task_ctx = self._task.prepare(
                GameState(season_id=self._season_id),
                self._turn_context(turn_num),
            )
            self._current_task_ctx = task_ctx
            observation = task_ctx.prompt_section
            history_block = format_outcome_history_block(
                self._outcome_history,
                max_history_turns=self._total_turns,
                lives_label=self._lives_label(),
            )
            puzzle_view = self._build_puzzle_view()
        else:
            observation = self._task.get_observation(turn_num)
            # Prepend cumulative history (matching TurnManager behavior).
            history_block = self._format_turn_history()
        if history_block:
            observation = f"{history_block}\n\n{observation}"
```

그리고 그 아래 반환하는 `TurnState(...)`의 마지막 인자 `cohort_size=self.peer_death_cohort_size,` 뒤에 추가:

```python
            signal_mode=self._signal_mode,
            puzzle=puzzle_view,
```

- [ ] **Step 5: 테스트 실행**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_human_game_puzzle.py tests/unit/test_human_game.py tests/unit/test_human_game_lives.py tests/unit/test_human_game_preview.py tests/unit/test_signal_game_puzzle_mode.py -q -p no:cacheprovider`
Expected: 전부 통과.

- [ ] **Step 6: Commit (orchestrator)**

```bash
git add game/squid_game/tasks/signal_game/module.py web/squid_arena/human_game.py tests/unit/test_human_game_puzzle.py
git commit -m "feat(web): HumanGameSession per_turn_puzzle mode: engine prepare(), PuzzleTurnView, outcome history"
```

---

### Task 2: `submit_action` 퍼즐 채점, RULE 검증, 설정 스냅샷

**Files:**
- Modify: `web/squid_arena/human_game.py`
- Modify: `tests/unit/test_human_game_puzzle.py` (클래스 추가)

**Interfaces:**
- Consumes: `squid_game.tasks.signal_game.module.ParsedSignalResponse(action: str | None, rule_hypothesis: str | None = None)`, `SignalGameModule.score(parsed, state) -> TaskOutcome(success_factor, metadata)`, `squid_game.tasks.signal_game.puzzle.{parse_rule_text, shape_label}`, Task 1의 `self._current_task_ctx`, `self._outcome_history`, `SignalGameModule.current_puzzle`.
- Produces:
  - `HumanGameSession.validate_rule_text(text: str) -> str | None` (오류 메시지 또는 `None`; 순차 모드는 항상 `None`)
  - `submit_action(action, probe_answer="", forfeit_reason=None, psuccess_self=None) -> TurnFeedback` 시그니처 불변. 퍼즐 모드 CONTINUE 턴의 `TurnResult`에 `task_metadata`, `task_success_factor`, `reward_received`가 채워지고 `ProbeResult.score == rule_match_score`.
  - `settings_snapshot()["signal_mode"]`, 퍼즐 모드 `["history_mode"] == "outcome"`.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/unit/test_human_game_puzzle.py` 끝에 추가:

```python
PUZZLE_METADATA_KEYS = {
    # prepare()
    "signal", "hidden_rule", "correct_action", "turn", "puzzle_turn", "rule_shape",
    "n_clauses", "n_conjunctions", "predicates_allowed", "overlap_query", "clues",
    "query_signal", "n_clues", "n_minimal_clues", "query_overlap_count",
    # score()
    "correct", "action", "rule_hypothesis", "rule_match_score",
    "rule_parse_failed", "rule_shape_match",
}


def _play(game: HumanGameSession, *, correct: bool, rule: str | None = None):
    game.get_turn_state()
    action = _correct(game)
    if not correct:
        action = next(a for a in ACTIONS if a != action)
    return game.submit_action(action, probe_answer=_rule(game) if rule is None else rule)


class TestSubmitAction:
    def test_correct_answer_records_engine_metadata(self) -> None:
        game = _session()
        state = game.get_turn_state()
        expected = _expected_puzzle(1)
        fb = game.submit_action(expected.correct_action, probe_answer=expected.rule.description)
        assert fb.was_optimal is True
        assert fb.reward == 10.0
        assert fb.new_score == 10.0
        assert fb.life_lost is False and fb.lives_remaining == 3
        turn = game.get_result().turns[0]
        md = turn.task_metadata
        assert set(md) == PUZZLE_METADATA_KEYS
        assert md["hidden_rule"] == expected.rule.description
        assert md["clues"] == [str(c) for c in expected.clues]
        assert md["query_signal"] == str(expected.query)
        assert md["rule_shape"] == ",".join(str(a) for a in expected.shape)
        assert md["rule_shape"] == ",".join(str(a) for a in state.puzzle.shape)
        assert md["n_clues"] == len(expected.clues)
        assert md["n_minimal_clues"] == expected.n_minimal_clues
        assert md["query_overlap_count"] == expected.query_overlap_count
        assert md["correct"] is True and md["action"] == expected.correct_action
        assert md["rule_match_score"] == 100.0
        assert md["rule_shape_match"] is True
        assert md["rule_parse_failed"] is False
        assert turn.task_success_factor == 1.0
        assert turn.reward_received == 10.0
        assert turn.ground_truth_rule == expected.rule.description
        assert turn.probe_result.response == expected.rule.description
        assert turn.probe_result.score == 100.0
        assert turn.action_outcome.was_optimal is True
        assert turn.action_outcome.reward == 10.0

    def test_wrong_answer_costs_a_life_and_wrong_shape_is_recorded(self) -> None:
        game = _session()
        fb = _play(game, correct=False, rule='if color == "red": stay; else: jump')
        assert fb.was_optimal is False
        assert fb.reward == 0.0
        assert fb.life_lost is True and fb.lives_remaining == 2
        md = game.get_result().turns[0].task_metadata
        assert md["correct"] is False
        assert md["rule_parse_failed"] is False
        assert md["rule_shape_match"] is (md["rule_shape"] == "1")
        assert 0.0 <= md["rule_match_score"] <= 100.0

    def test_unparseable_rule_is_recorded_not_rejected(self) -> None:
        game = _session()
        _play(game, correct=True, rule="exploring")
        md = game.get_result().turns[0].task_metadata
        assert md["rule_parse_failed"] is True
        assert md["rule_shape_match"] is False
        assert md["rule_match_score"] == 0.0

    def test_three_wrong_answers_eliminate(self) -> None:
        game = _session()
        lives = [_play(game, correct=False).lives_remaining for _ in range(3)]
        assert lives == [2, 1, 0]
        assert game.is_game_over
        assert game.eliminated is True
        assert game.get_turn_state().game_over_reason == "eliminated"
        result = game.get_result()
        assert result.eliminated is True and result.lives_at_end == 0
        assert result.final_score == 0.0
        assert [t.lives_after for t in result.turns] == [2, 1, 0]

    def test_ten_correct_answers_complete_the_ladder(self) -> None:
        game = _session()
        for turn in range(1, 11):
            state = game.get_turn_state()
            assert state.turn_number == turn
            assert state.puzzle.puzzle_turn == turn
            _play(game, correct=True)
        assert game.is_game_over
        assert game.get_turn_state().game_over_reason == "completed"
        result = game.get_result()
        assert result.final_score == 100.0
        assert result.eliminated is False and result.lives_at_end == 3
        assert [t.task_metadata["puzzle_turn"] for t in result.turns] == list(range(1, 11))
        clue_sets = [tuple(t.task_metadata["clues"]) for t in result.turns]
        assert len(set(clue_sets)) == 10

    def test_shape_follows_the_ladder(self) -> None:
        game = _session()
        for _ in range(5):
            _play(game, correct=True)
        view = game.get_turn_state().puzzle
        assert len(view.shape) == 3 and view.shape.count(2) == 1
        assert view.rule_template_hint.count("elif") == 2
        assert view.shape_block.count(" and ") == 1

    def test_invalid_action_raises_like_apply_action(self) -> None:
        game = _session()
        game.get_turn_state()
        with pytest.raises(ValueError, match="Invalid action"):
            game.submit_action("fly", probe_answer=_rule(game))


class TestForfeit:
    def test_forfeit_keeps_lives_and_records_ground_truth(self) -> None:
        game = _session()
        game.get_turn_state()
        expected_rule = _rule(game)
        fb = game.submit_action("forfeit", forfeit_reason=2)
        assert fb.forfeited is True and fb.life_lost is False and fb.lives_remaining == 3
        turn = game.get_result().turns[0]
        assert turn.forfeit_decision is True
        assert turn.task_metadata == {}
        assert turn.ground_truth_rule == expected_rule
        assert game.get_result().forfeit_self_report.raw_digit == 2


class TestHistoryBlock:
    def test_second_turn_observation_opens_with_the_outcome_block(self) -> None:
        game = _session()
        _play(game, correct=True)
        _play(game, correct=False)
        obs = game.get_turn_state().observation
        assert obs.startswith("=== Previous Rounds ===")
        assert "- Round 1: correct → cumulative: 10.0 (attempts: 3/3)" in obs
        assert "- Round 2: incorrect → cumulative: 10.0 (attempts: 2/3)" in obs
        assert "Turn 3. This round's rule has exactly this shape" in obs
        # outcome-only: no signal, no action, no rule hypothesis
        assert "[Your rule prediction]" not in obs
        assert "=== Previous Turn Results" not in obs

    def test_threat_cell_says_lives(self) -> None:
        game = _session(framing="threat_l2")
        _play(game, correct=True)
        obs = game.get_turn_state().observation
        assert "(lives: 3/3)" in obs

    def test_first_turn_has_no_history_block(self) -> None:
        obs = _session().get_turn_state().observation
        assert "=== Previous Rounds ===" not in obs


class TestValidateRuleText:
    def test_messages(self) -> None:
        game = _session()
        game.get_turn_state()
        assert game.validate_rule_text("") == "A RULE line is required in puzzle mode."
        assert game.validate_rule_text("   ") == "A RULE line is required in puzzle mode."
        assert game.validate_rule_text("nonsense").startswith("RULE line does not parse")
        same_attr = 'if number >= 2 and number == 3: stay; else: jump'
        assert game.validate_rule_text(same_attr).startswith("RULE line does not parse")
        shape = game.get_turn_state().puzzle.shape
        wrong = "if color == \"red\": stay; elif shape == \"star\": jump; elif number == 1: go_left; elif number == 2: go_right; else: stay"
        if len(shape) != 4:
            msg = game.validate_rule_text(wrong)
            assert msg.startswith("RULE shape 1,1,1,1 does not match this round's shape")
        assert game.validate_rule_text(_rule(game)) is None

    def test_sequential_mode_never_validates(self) -> None:
        game = HumanGameSession(
            task_name="signal_game", difficulty="easy", framing="true_baseline",
            forfeit_condition="allowed", seed=1, total_turns=3,
            num_few_shot=0, curriculum_turns=0,
        )
        game.get_turn_state()
        assert game.validate_rule_text("") is None


class TestSettingsSnapshot:
    def test_puzzle_mode_is_recorded(self) -> None:
        snap = _session().settings_snapshot()
        assert snap["signal_mode"] == "per_turn_puzzle"
        assert snap["history_mode"] == "outcome"
        assert snap["total_turns"] == 10 and snap["lives_total"] == 3
        assert snap["seed"] == SEED

    def test_sequential_snapshot_unchanged(self) -> None:
        game = HumanGameSession(
            task_name="signal_game", difficulty="easy", framing="true_baseline",
            forfeit_condition="allowed", seed=1, total_turns=3,
            num_few_shot=0, curriculum_turns=0,
        )
        snap = game.settings_snapshot()
        assert snap["signal_mode"] == "sequential"
        assert snap["history_mode"] == "cumulative"
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_human_game_puzzle.py -q -p no:cacheprovider`
Expected: `TestSubmitAction` 이후 클래스가 실패한다(`task_metadata == {}`, `validate_rule_text` 없음 등).

- [ ] **Step 3: `human_game.py` 수정**

(a) import 추가:

```python
from squid_game.tasks.signal_game.module import ParsedSignalResponse
from squid_game.tasks.signal_game.puzzle import (
    parse_rule_text,
    render_shape_block,
    render_shape_hint,
    shape_label,
)
```

(Task 1의 `from squid_game.tasks.signal_game.puzzle import render_shape_block, render_shape_hint` 줄을 위 형태로 바꾼다.)

(b) `settings_snapshot`의

```python
        put("history_mode", "cumulative")
```

을 다음으로 교체:

```python
        # Sequential human play always shows the full cumulative turn history
        # (``_format_turn_history``); puzzle mode renders the outcome-only
        # block, exactly like the LLM puzzle configs' ``history_mode: outcome``.
        put(
            "history_mode",
            "outcome" if self._signal_mode == "per_turn_puzzle" else "cumulative",
        )
        put("signal_mode", self._signal_mode)
```

(c) `validate_rule_text`를 `preview_continue_reward` 앞에 추가:

```python
    def validate_rule_text(self, text: str) -> str | None:
        """Puzzle-mode guard for the RULE line a client submits with its action.

        Returns a human-readable problem, or ``None`` when the line is fine
        (and always ``None`` in sequential mode). The form on the client
        composes strings that pass by construction, so a failure here is a
        client bug or a hand-made request; the API turns it into a 400
        rather than recording a parse failure the way the LLM path does.
        """
        if self._signal_mode != "per_turn_puzzle":
            return None
        stripped = (text or "").strip()
        if not stripped:
            return "A RULE line is required in puzzle mode."
        parsed = parse_rule_text(stripped)
        if parsed is None:
            return f"RULE line does not parse: {stripped}"
        puzzle = getattr(self._task, "current_puzzle", None)
        if puzzle is not None and parsed.shape != puzzle.shape:
            return (
                f"RULE shape {shape_label(parsed.shape)} does not match this "
                f"round's shape {shape_label(puzzle.shape)}"
            )
        return None
```

(d) `submit_action`의 FORFEIT 분기: `self._turn_results.append(TurnResult(` 호출의 `raw_response=action,` 뒤에 추가:

```python
                # The engine's forfeit record carries the round's truth too
                # (build_forfeit_result); the sequential human path never
                # did, so only puzzle mode adds it.
                ground_truth_rule=(
                    self._task.get_active_rule_description()
                    if self._signal_mode == "per_turn_puzzle"
                    else None
                ),
```

(e) `submit_action`의 CONTINUE 분기: 다음 두 줄

```python
        # Apply action to task, enforcing score floor.
        outcome = self._task.apply_action(action)
        # Parity with the LLM path: reward = success_factor × equal-EV
        # CONTINUE reward, calibrated by the player's psuccess_self.
        success_factor = 1.0 if outcome.was_optimal else 0.0
```

을 다음으로 교체:

```python
        # Score the action. Puzzle mode goes through the v3 surface
        # (prepare() -> score()) exactly as UnifiedTurnManager does, so the
        # RULE line is parsed and functionally scored by the module and the
        # turn metadata is the engine's; sequential mode keeps the legacy
        # apply_action() path byte for byte.
        task_metadata: dict = {}
        if self._signal_mode == "per_turn_puzzle":
            if action not in self._task.get_available_actions():
                raise ValueError(
                    f"Invalid action '{action}'. Must be one of "
                    f"{self._task.get_available_actions()}"
                )
            task_ctx = self._current_task_ctx
            if task_ctx is None:
                raise RuntimeError(
                    "get_turn_state() must be called before submit_action()"
                )
            parsed = ParsedSignalResponse(
                action=action,
                rule_hypothesis=probe_answer.strip() or None,
            )
            task_outcome = self._task.score(parsed, GameState(season_id=self._season_id))
            success_factor = task_outcome.success_factor
            outcome = ActionOutcome(
                action_taken=action,
                was_optimal=success_factor == 1.0,
                reward=0.0,
            )
            # Same merge as UnifiedTurnManager: prepare() keys, then score() keys.
            task_metadata = {**task_ctx.metadata, **task_outcome.metadata}
        else:
            # Apply action to task, enforcing score floor.
            outcome = self._task.apply_action(action)
            success_factor = 1.0 if outcome.was_optimal else 0.0
        # Parity with the LLM path: reward = success_factor × the layer's
        # CONTINUE reward (flat +10 in lives mode).
```

(f) 같은 메서드에서 이력 기록 블록

```python
        # Record turn history for next turn's observation.
        obs_summary = self._task.get_observation_summary()
        self._turn_history.append({
            "turn": turn_num,
            "signal": obs_summary,
            "action": action,
            "cumulative_score": self._cumulative_score,
            "probe_prediction": probe_answer,
        })

        # Probe scoring
        probe_score = self._task.score_probe(probe_answer) if probe_answer else 0.0
```

을 다음으로 교체:

```python
        # Record turn history for next turn's observation.
        if self._signal_mode == "per_turn_puzzle":
            # Outcome-only entry (history_mode: outcome): verdict, running
            # score and the counter; no signal, action or rule hypothesis.
            self._outcome_history.append({
                "turn": turn_num,
                "correct": outcome.was_optimal,
                "outcome": "eliminated" if lives_dead else f"+{reward:.0f}",
                "cumulative_score": self._cumulative_score,
                "lives_after": self._lives_remaining,
                "lives_total": self._lives_total,
            })
            # score() already parsed and scored the RULE line; reuse it
            # rather than parsing a second time through score_probe().
            probe_score = float(task_metadata.get("rule_match_score") or 0.0)
        else:
            obs_summary = self._task.get_observation_summary()
            self._turn_history.append({
                "turn": turn_num,
                "signal": obs_summary,
                "action": action,
                "cumulative_score": self._cumulative_score,
                "probe_prediction": probe_answer,
            })
            # Probe scoring
            probe_score = self._task.score_probe(probe_answer) if probe_answer else 0.0
```

(g) 같은 메서드의 CONTINUE 쪽 `self._turn_results.append(TurnResult(` 바로 앞에 추가:

```python
        # Puzzle mode fills the v3 fields the engine fills; the sequential
        # record is left exactly as it was.
        puzzle_kwargs: dict = {}
        if self._signal_mode == "per_turn_puzzle":
            puzzle_kwargs = {
                "task_metadata": task_metadata,
                "task_success_factor": success_factor,
                "reward_received": reward,
            }
```

그리고 그 `TurnResult(...)` 호출의 `**lives_kwargs,` 뒤에 `**puzzle_kwargs,`를 추가한다.

- [ ] **Step 4: 테스트 실행**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_human_game_puzzle.py tests/unit/test_human_game.py tests/unit/test_human_game_lives.py tests/unit/test_human_game_preview.py -q -p no:cacheprovider`
Expected: 전부 통과. `TestValidateRuleText.test_messages`의 모양 불일치 분기는 seed 43 턴 1의 모양이 4절이 아닐 때만 검사한다(사다리 턴 1은 1절이므로 항상 검사된다).

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add web/squid_arena/human_game.py tests/unit/test_human_game_puzzle.py
git commit -m "feat(web): puzzle-mode scoring through SignalGameModule.score, RULE validation, outcome history, settings snapshot"
```

---

### Task 3: API 스키마와 라우트, 계약 테스트, OpenAPI 스냅샷

**Files:**
- Modify: `web/squid_arena/schemas.py`
- Modify: `web/squid_arena/routes_game.py`
- Create: `tests/unit/test_api_web_arena_puzzle.py`
- Modify: `tests/characterization/test_api_contract.py` (`STATE_KEYS`)
- Regenerate: `tests/characterization/snapshots/api/openapi.json`

**Interfaces:**
- Consumes: Task 1–2의 `HumanGameSession(signal_mode=...)`, `.signal_mode`, `.validate_rule_text`, `TurnState.{signal_mode, puzzle}`, `human_game.{SIGNAL_MODES, PUZZLE_TOTAL_TURNS, PUZZLE_LIVES_TOTAL}`.
- Produces:
  - `schemas.PuzzleSignal(color: str, shape: str, number: int, text: str)`, `schemas.PuzzleClue(PuzzleSignal, action: str)`, `schemas.PuzzleTurn(puzzle_turn: int, shape: list[int], shape_block: str, rule_template_hint: str, clues: list[PuzzleClue], query: PuzzleSignal, n_clues: int)`
  - `NewGameRequest.signal_mode: str = "sequential"`
  - `TurnStateResponse.signal_mode: str = "sequential"`, `TurnStateResponse.puzzle: PuzzleTurn | None = None`
  - `POST /api/new_game`: 모드 검증(400), 퍼즐 기본값(`total_turns` 10 / `lives_total` 3, 요청에 없을 때만), `lives_enabled=false`+퍼즐 400, 모듈 `ValueError` 400
  - `POST /api/action`: 퍼즐 모드 RULE 검증 400

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_api_web_arena_puzzle.py`:

```python
"""Web Arena API surface for ``signal_mode: per_turn_puzzle`` human play.

``tests/unit/test_human_game_puzzle.py`` pins the session rules; this file
pins how they reach the wire: the mode on ``/api/new_game``, the puzzle view
on ``/api/state``, the RULE-line guard on ``/api/action``, and the JSONL a
finished game writes (the same ``season_results.jsonl`` shape the analysis
loaders read for LLM runs). Every field is additive.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from squid_game.models.results import SeasonResult
from squid_game.tasks.signal_game.puzzle import generate_puzzle, puzzle_rng
from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from squid_game.tasks.signal_game.rules import ACTIONS


@pytest.fixture
def api_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.delenv("WEB_ARENA_CORS_ORIGINS", raising=False)
    import squid_arena.api as api
    import squid_arena.deps as deps

    importlib.reload(deps)
    reloaded = importlib.reload(api)
    yield reloaded
    reloaded._repository.close()


@pytest.fixture
def client(api_module) -> TestClient:
    return TestClient(api_module.app)


SEED = 43


def _new_puzzle_game(client, *, nickname="puzzler", **overrides):
    body = {
        "task_name": "signal_game",
        "difficulty": "medium",
        "framing": "true_baseline",
        "forfeit_condition": "allowed",
        "seed": SEED,
        "signal_mode": "per_turn_puzzle",
        "nickname": nickname,
        "password": "pw",
    }
    body.update(overrides)
    return client.post("/api/new_game", json=body)


def _new_sequential_game(client, *, nickname="classic"):
    return client.post("/api/new_game", json={
        "task_name": "signal_game", "difficulty": "easy",
        "framing": "true_baseline", "forfeit_condition": "allowed",
        "seed": 1, "total_turns": 2, "actual_death": False,
        "num_few_shot": 0, "curriculum_turns": 0,
        "nickname": nickname, "password": "pw",
    })


def _state(client, sid: str) -> dict:
    resp = client.get("/api/state", params={"session_id": sid})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _answer(api_module, sid: str) -> tuple[str, str]:
    """This turn's correct action and its exact rule, from the live session."""
    puzzle = api_module._sessions[sid]._task.current_puzzle
    return puzzle.correct_action, puzzle.rule.description


def _act(client, sid: str, action: str, rule: str, **extra):
    body = {"action": action, "probe_answer": rule, "reasoning": "because"}
    body.update(extra)
    return client.post(f"/api/action?session_id={sid}", json=body)


# ---------------------------------------------------------------------------
# /api/new_game
# ---------------------------------------------------------------------------


def test_puzzle_defaults_are_ten_turns_three_lives(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    game = api_module._sessions[sid]
    assert game.signal_mode == "per_turn_puzzle"
    assert game.lives_total == 3
    state = _state(client, sid)
    assert state["signal_mode"] == "per_turn_puzzle"
    assert state["lives_total"] == 3 and state["lives_remaining"] == 3
    assert game.settings_snapshot()["total_turns"] == 10


def test_explicit_turns_and_lives_are_honoured(client, api_module) -> None:
    sid = _new_puzzle_game(client, total_turns=2, lives_total=5).json()["session_id"]
    game = api_module._sessions[sid]
    assert game.lives_total == 5
    assert game.settings_snapshot()["total_turns"] == 2


def test_unknown_mode_400(client) -> None:
    resp = _new_puzzle_game(client, signal_mode="bogus")
    assert resp.status_code == 400
    assert "signal_mode" in resp.json()["detail"]


def test_season_longer_than_ladder_400(client) -> None:
    resp = _new_puzzle_game(client, total_turns=11)
    assert resp.status_code == 400
    assert "puzzle_ladder" in resp.json()["detail"]


def test_puzzle_requires_lives(client) -> None:
    resp = _new_puzzle_game(client, lives_enabled=False)
    assert resp.status_code == 400
    assert "lives_enabled" in resp.json()["detail"]


def test_sequential_request_is_unchanged(client) -> None:
    sid = _new_sequential_game(client).json()["session_id"]
    state = _state(client, sid)
    assert state["signal_mode"] == "sequential"
    assert state["puzzle"] is None


# ---------------------------------------------------------------------------
# /api/state
# ---------------------------------------------------------------------------


def test_state_carries_the_puzzle_view_and_nothing_secret(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    state = _state(client, sid)
    view = state["puzzle"]
    expected = generate_puzzle(puzzle_rng(SEED, 1), load_signal_puzzle_config().spec_for_turn(1))
    assert set(view) == {
        "puzzle_turn", "shape", "shape_block", "rule_template_hint", "clues", "query", "n_clues",
    }
    assert view["puzzle_turn"] == 1
    assert view["shape"] == list(expected.shape)
    assert view["n_clues"] == len(view["clues"]) == len(expected.clues)
    assert [c["text"] for c in view["clues"]] == [str(c) for c in expected.clues]
    assert set(view["clues"][0]) == {"color", "shape", "number", "action", "text"}
    assert set(view["query"]) == {"color", "shape", "number", "text"}
    assert view["query"]["text"] == str(expected.query)
    assert view["shape_block"].startswith("if ")
    assert view["rule_template_hint"].endswith("else: ___")
    blob = json.dumps(state)
    assert expected.rule.description not in blob
    assert "hidden_rule" not in blob and "correct_action" not in blob
    assert state["observation"].startswith("Turn 1. This round's rule has exactly this shape")
    assert "if / elif / else" in state["system_rules"]


# ---------------------------------------------------------------------------
# /api/action
# ---------------------------------------------------------------------------


def test_action_rejects_missing_unparseable_and_misshaped_rules(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    _state(client, sid)
    action, rule = _answer(api_module, sid)

    resp = _act(client, sid, action, "")
    assert resp.status_code == 400 and "RULE line is required" in resp.json()["detail"]

    resp = _act(client, sid, action, "if the moon is full: jump")
    assert resp.status_code == 400 and "does not parse" in resp.json()["detail"]

    resp = _act(client, sid, action, 'if number >= 2 and number == 3: stay; else: jump')
    assert resp.status_code == 400 and "does not parse" in resp.json()["detail"]

    four = 'if color == "red": stay; elif shape == "star": jump; elif number == 1: go_left; elif number == 2: go_right; else: stay'
    resp = _act(client, sid, action, four)
    assert resp.status_code == 400 and "does not match this round's shape" in resp.json()["detail"]

    # nothing was consumed by the rejected attempts
    assert _state(client, sid)["turn_number"] == 1
    resp = _act(client, sid, action, rule)
    assert resp.status_code == 200
    assert resp.json()["was_optimal"] is True


def test_forfeit_needs_no_rule(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    _state(client, sid)
    resp = _act(client, sid, "forfeit", "", forfeit_reason=1)
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_over"] is True and body["game_over_reason"] == "forfeited"
    assert body["lives_remaining"] == 3


def test_action_response_shape_is_unchanged(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    _state(client, sid)
    action, rule = _answer(api_module, sid)
    body = _act(client, sid, action, rule).json()
    assert set(body) == {
        "action_taken", "was_optimal", "reward", "feedback", "new_score",
        "reasoning_tokens", "game_over", "game_over_reason",
        "life_lost", "lives_remaining", "eliminated", "is_dead",
    }
    assert body["reward"] == 10.0


# ---------------------------------------------------------------------------
# Full game + JSONL persistence
# ---------------------------------------------------------------------------


def test_full_puzzle_game_and_saved_jsonl_match_the_loader_shape(
    client, api_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # save_result() writes outputs/api_sessions/ under CWD
    sid = _new_puzzle_game(client).json()["session_id"]
    shapes = []
    for turn in range(1, 11):
        state = _state(client, sid)
        assert state["turn_number"] == turn
        shapes.append(state["puzzle"]["shape"])
        action, rule = _answer(api_module, sid)
        body = _act(client, sid, action, rule).json()
        assert body["was_optimal"] is True
        assert body["game_over"] is (turn == 10)

    result = client.get("/api/result", params={"session_id": sid, "save": "true"}).json()
    assert result["final_score"] == 100.0
    assert result["turns_played"] == 10
    assert result["lives_at_end"] == 3 and result["eliminated"] is False
    # save_result() returns a CWD-relative path; resolve both sides (macOS
    # tmp dirs live behind a /private symlink).
    saved = Path(result["save_path"]).resolve()
    assert saved == (tmp_path / "outputs" / "api_sessions" / "season_results.jsonl").resolve()
    lines = [ln for ln in saved.read_text(encoding="utf-8").splitlines() if ln.strip()]
    season = SeasonResult.model_validate_json(lines[-1])
    assert season.seed == SEED
    assert len(season.turns) == 10
    for turn, shape in zip(season.turns, shapes, strict=True):
        md = turn.task_metadata
        assert md["rule_shape"] == ",".join(str(a) for a in shape)
        assert md["rule_match_score"] == 100.0 and md["rule_shape_match"] is True
        assert md["rule_parse_failed"] is False
        for key in ("puzzle_turn", "n_clues", "n_minimal_clues", "query_overlap_count",
                    "hidden_rule", "clues", "query_signal"):
            assert key in md, key
        assert turn.task_success_factor == 1.0 and turn.reward_received == 10.0

    # DB row: settings snapshot carries the mode
    row = api_module._repository.get_session(sid)
    assert row is not None
    assert row.settings["signal_mode"] == "per_turn_puzzle"
    assert row.settings["history_mode"] == "outcome"


def test_three_wrong_answers_eliminate_over_http(client, api_module) -> None:
    sid = _new_puzzle_game(client).json()["session_id"]
    lives = []
    for _ in range(3):
        _state(client, sid)
        action, rule = _answer(api_module, sid)
        wrong = next(a for a in ACTIONS if a != action)
        body = _act(client, sid, wrong, rule).json()
        lives.append(body["lives_remaining"])
    assert lives == [2, 1, 0]
    assert body["game_over"] is True and body["game_over_reason"] == "eliminated"
    assert body["eliminated"] is True and body["is_dead"] is True
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_api_web_arena_puzzle.py -q -p no:cacheprovider`
Expected: 실패 (`signal_mode` 무시, `puzzle` 키 없음).

- [ ] **Step 3: `schemas.py` 수정**

`NewGameRequest`의 `lives_total` 필드 뒤에 추가:

```python
    signal_mode: str = Field(
        default="sequential",
        description=(
            "Signal Game stimulus mode: 'sequential' (one hidden rule per "
            "game, campaign rule rotation) or 'per_turn_puzzle' (a fresh "
            "shape-disclosed decision-list puzzle every turn from the "
            "10-turn ladder, the same engine path the LLM runs use). In "
            "puzzle mode total_turns defaults to 10 and lives_total to 3 "
            "when the request does not set them; lives_enabled must stay "
            "true; difficulty / num_few_shot / curriculum_turns are ignored."
        ),
    )
```

`TurnStateResponse` 클래스 **앞**에 추가:

```python
class PuzzleSignal(BaseModel):
    """One card as the puzzle view serves it (per-turn puzzle mode)."""

    color: str
    shape: str
    number: int
    text: str = Field(description='Engine rendering, e.g. "green circle with number 3"')


class PuzzleClue(PuzzleSignal):
    action: str = Field(description="Action this round's hidden rule assigns to the card")


class PuzzleTurn(BaseModel):
    """Stage 2 of a per-turn puzzle round: the disclosed rule shape, the
    example clues and the query card. Never carries the hidden rule or the
    correct action; those are recorded in the turn's task_metadata only."""

    puzzle_turn: int = Field(description="Ladder rung (= turn number)")
    shape: list[int] = Field(description="Arity of each clause in order, e.g. [1, 2, 1]")
    shape_block: str = Field(description="Blanked Python skeleton, as rendered in the observation")
    rule_template_hint: str = Field(
        description='One-line RULE template, e.g. "if ___: ___; elif ___ and ___: ___; else: ___"'
    )
    clues: list[PuzzleClue]
    query: PuzzleSignal
    n_clues: int
```

`TurnStateResponse`의 마지막 필드 `lives_enabled` 뒤에 추가:

```python
    # --- Signal Game stimulus mode (2026-09-06 per-turn puzzle) ---
    signal_mode: str = Field(
        default="sequential",
        description="'sequential' or 'per_turn_puzzle' (echo of the session's mode).",
    )
    puzzle: PuzzleTurn | None = Field(
        default=None,
        description=(
            "Per-turn puzzle view (shape, clues, query) while a puzzle-mode "
            "game is in progress; null in sequential mode and once the game "
            "is over."
        ),
    )
```

- [ ] **Step 4: `routes_game.py` 수정**

(a) import:

```python
import dataclasses
import random
import uuid

from fastapi import APIRouter, HTTPException, Request

from squid_arena import deps, reporting, schemas
from squid_arena.arena import VALID_DIFFICULTIES
from squid_arena.auth import hash_password, verify_password
from squid_arena.human_game import (
    PUZZLE_LIVES_TOTAL,
    PUZZLE_TOTAL_TURNS,
    SIGNAL_MODES,
    HumanGameSession,
)
from squid_arena.rule_schedule import rule_index_for
from squid_store import PlayerRecord
```

(b) `new_game`: `if req.difficulty not in VALID_DIFFICULTIES:` 검사 뒤에 추가:

```python
    if req.signal_mode not in SIGNAL_MODES:
        raise HTTPException(400, f"Unknown signal_mode '{req.signal_mode}'.")
    puzzle_mode = req.signal_mode == "per_turn_puzzle"
    if puzzle_mode and not req.lives_enabled:
        raise HTTPException(
            400, "signal_mode 'per_turn_puzzle' requires lives_enabled=true (3 lives)."
        )
    # Puzzle session shape (10 turns, 3 lives) applies only when the request
    # leaves the field unset, so an explicit value (tests, short games) wins
    # and the sequential defaults are untouched.
    total_turns = req.total_turns
    lives_total = req.lives_total
    if puzzle_mode:
        if "total_turns" not in req.model_fields_set:
            total_turns = PUZZLE_TOTAL_TURNS
        if "lives_total" not in req.model_fields_set:
            lives_total = PUZZLE_LIVES_TOTAL
```

그리고 `game = HumanGameSession(...)` 호출을 다음으로 교체:

```python
    try:
        game = HumanGameSession(
            task_name=req.task_name,
            difficulty=req.difficulty,
            framing=req.framing,
            forfeit_condition=req.forfeit_condition,
            seed=seed,
            total_turns=total_turns,
            actual_death=effective_actual_death,
            starting_score=req.starting_score,
            score_floor=req.score_floor,
            p_death_constant=req.p_death_constant,
            num_few_shot=req.num_few_shot,
            curriculum_turns=req.curriculum_turns,
            rule_index=rule_index,
            lives_enabled=req.lives_enabled,
            lives_total=lives_total,
            signal_mode=req.signal_mode,
        )
    except ValueError as exc:
        # Puzzle mode validates the season against the ladder inside the
        # task module (total_turns > 10, non-signal task); report that as a
        # bad request. Sequential mode keeps its historical behaviour.
        if not puzzle_mode:
            raise
        raise HTTPException(400, str(exc)) from exc
```

(c) `get_state`: `return schemas.TurnStateResponse(` 호출의 `cohort_size=state.cohort_size,` 뒤에 추가:

```python
        signal_mode=state.signal_mode,
        puzzle=(
            None
            if state.puzzle is None
            else schemas.PuzzleTurn(**dataclasses.asdict(state.puzzle))
        ),
```

(d) `submit_action`: `if game.is_game_over:` 검사 뒤에 추가:

```python
    # Puzzle mode: the RULE line rides in probe_answer and must be a
    # well-formed decision list of this round's shape. The client form
    # guarantees that, so a failure is a bug or a hand-made request.
    if req.action != "forfeit":
        problem = game.validate_rule_text(req.probe_answer)
        if problem is not None:
            raise HTTPException(400, problem)
```

- [ ] **Step 5: 계약 핀과 스냅샷 갱신**

`tests/characterization/test_api_contract.py`의 `STATE_KEYS`에 추가:

```python
    # 2026-09-06 per-turn puzzle human play: the session's stimulus mode and
    # the Stage 2 puzzle view (null in sequential mode). Additive.
    "signal_mode", "puzzle",
```

스냅샷 재생성(응답 모델과 요청 필드가 늘었으므로 문서가 바뀐다):

```bash
rm tests/characterization/snapshots/api/openapi.json
PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/characterization/test_api_contract.py -q -p no:cacheprovider   # 1회차: "snapshot created" 로 실패
PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/characterization/test_api_contract.py -q -p no:cacheprovider   # 2회차: 통과
```

재생성된 스냅샷의 diff가 `PuzzleSignal` / `PuzzleClue` / `PuzzleTurn` 스키마 추가와 `signal_mode` / `puzzle` 필드 추가**만**인지 `git diff --stat` 및 눈으로 확인한다(오케스트레이터 몫).

- [ ] **Step 6: 테스트 실행**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_api_web_arena_puzzle.py tests/unit/test_api_web_arena.py tests/unit/test_api_web_arena_lives.py tests/characterization/test_api_contract.py -q -p no:cacheprovider`
Expected: 기준선 실패(`test_app_imports_and_registers_all_endpoints`) 외 전부 통과.

- [ ] **Step 7: Commit (orchestrator)**

```bash
git add web/squid_arena/schemas.py web/squid_arena/routes_game.py tests/unit/test_api_web_arena_puzzle.py tests/characterization/test_api_contract.py tests/characterization/snapshots/api/openapi.json
git commit -m "feat(web): per_turn_puzzle on the arena API: signal_mode, PuzzleTurn view, RULE-line guard, puzzle session defaults"
```

---

### Task 4: RULE 조립 헬퍼(JS)와 Python 계약 테스트

**Files:**
- Modify: `web/frontend/app.js` (helpers 구간, `parseClues` 함수 뒤)
- Create: `tests/unit/test_web_puzzle_rule_composer.py`

**Interfaces:**
- Consumes: `squid_game.tasks.signal_game.puzzle.{ATOMS, parse_rule_text, draw_shape, PuzzleSpec}`, `squid_game.tasks.signal_game.rules.ACTIONS`.
- Produces (`window.squidArenaHelpers`에 export, Task 5가 사용):
  - `PUZZLE_ACTIONS: string[]`, `PUZZLE_CONDITION_GROUPS: {label, options: string[]}[]`
  - `conditionAttribute(label) -> "color" | "shape" | "number" | ""`
  - `emptyPuzzleSlots(shape) -> {clauses: {conds: string[2], action: string}[], elseAction: string}`
  - `puzzleSlotErrors(shape, slots) -> string[]`
  - `composePuzzleRule(shape, slots) -> string` ("" until complete and valid)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/unit/test_web_puzzle_rule_composer.py`:

```python
"""Contract between the Web Arena's puzzle RULE form and ``parse_rule_text``.

The browser composes the RULE line (``composePuzzleRule`` in
web/frontend/app.js); the server scores it with
``SignalGameModule.score`` -> ``parse_rule_text``. Two things must hold:

1. Every string the form can produce parses back to a decision list with
   the round's shape, and its ``description`` is the composed string
   itself (the form emits ``PuzzleRule.description``'s exact grammar).
2. The option labels the form offers are the engine's own condition and
   action labels, in the engine's order.

The JS is not executed here; ``_compose`` mirrors ``composePuzzleRule``
line for line, and the label lists are read out of app.js as text.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from squid_game.tasks.signal_game.puzzle import (
    ATOMS,
    PuzzleSpec,
    draw_shape,
    parse_rule_text,
)
from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from squid_game.tasks.signal_game.rules import ACTIONS

APP_JS = Path(__file__).resolve().parents[2] / "web" / "frontend" / "app.js"


def _compose(shape: tuple[int, ...], conds: list[list[str]], actions: list[str], else_action: str) -> str:
    """Mirror of composePuzzleRule(shape, slots) in app.js."""
    parts = []
    for i, arity in enumerate(shape):
        keyword = "if" if i == 0 else "elif"
        parts.append(f"{keyword} {' and '.join(conds[i][:arity])}: {actions[i]}")
    parts.append(f"else: {else_action}")
    return "; ".join(parts)


def _random_valid_slots(rng: random.Random, shape: tuple[int, ...]):
    conds: list[list[str]] = []
    for arity in shape:
        if arity == 1:
            conds.append([rng.choice(ATOMS).label, ""])
        else:
            first = rng.choice(ATOMS)
            second = rng.choice([a for a in ATOMS if a.attrs[0] != first.attrs[0]])
            conds.append([first.label, second.label])
    actions = [rng.choice(ACTIONS) for _ in shape]
    return conds, actions, rng.choice(ACTIONS)


def _ladder_shapes() -> list[tuple[int, ...]]:
    """A few concrete shapes per rung, drawn the way the generator draws them."""
    out: list[tuple[int, ...]] = []
    for step in load_signal_puzzle_config().puzzle_ladder:
        spec: PuzzleSpec = step.to_spec()
        for i in range(3):
            out.append(draw_shape(random.Random(f"{step.turn}:{i}"), spec))
    return sorted(set(out))


@pytest.mark.parametrize("shape", _ladder_shapes(), ids=lambda s: ",".join(map(str, s)))
def test_composed_rule_round_trips_through_the_parser(shape: tuple[int, ...]) -> None:
    rng = random.Random(f"composer:{shape}")
    for _ in range(40):
        conds, actions, else_action = _random_valid_slots(rng, shape)
        text = _compose(shape, conds, actions, else_action)
        parsed = parse_rule_text(text)
        assert parsed is not None, text
        assert parsed.shape == shape, text
        assert parsed.description == text


def test_same_attribute_conjunction_does_not_parse() -> None:
    """Why both the client and the server validate ``and`` clauses."""
    assert parse_rule_text('if number >= 2 and number == 3: stay; else: jump') is None
    assert parse_rule_text('if color == "red" and color == "blue": stay; else: jump') is None


def _js_block(name: str) -> str:
    src = APP_JS.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = \[(.*?)\n  \];", src, re.S)
    assert match is not None, f"{name} not found in app.js"
    return match.group(1)


def _js_strings(block: str) -> list[str]:
    return [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", block)]


def test_app_js_condition_labels_are_the_engine_atoms_in_order() -> None:
    block = _js_block("PUZZLE_CONDITION_GROUPS")
    labels: list[str] = []
    for options in re.findall(r"options:\s*\[(.*?)\]", block, re.S):
        labels.extend(_js_strings(options))
    assert labels == [a.label for a in ATOMS]


def test_app_js_condition_groups_are_the_six_spec_groups() -> None:
    block = _js_block("PUZZLE_CONDITION_GROUPS")
    group_labels = re.findall(r"label:\s*\"([^\"]+)\"", block)
    assert group_labels == ["color ==", "shape ==", "number ==", "number >=", "number <=", "parity"]


def test_app_js_actions_are_the_engine_actions() -> None:
    assert _js_strings(_js_block("PUZZLE_ACTIONS")) == list(ACTIONS)
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_web_puzzle_rule_composer.py -q -p no:cacheprovider`
Expected: 왕복 테스트는 통과, `_js_block` 계열 3개는 "not found in app.js"로 실패.

- [ ] **Step 3: `app.js` 헬퍼 추가**

`web/frontend/app.js`에서 `function parseClues(systemPrompt) { ... }` 함수 정의 **바로 뒤**에 추가한다. 배열 리터럴은 정확히 아래 들여쓰기(두 칸 + `];` 닫기)를 지켜야 Python 테스트의 정규식이 블록을 찾는다.

```js
  // --- Per-turn puzzle mode (2026-09-06) -----------------------------------
  // The rule form offers exactly the engine's condition grammar
  // (game/squid_game/tasks/signal_game/puzzle.py ATOMS, same order) and the
  // four actions. The composed RULE line is PuzzleRule.description's grammar
  // verbatim, so the server parses it back with parse_rule_text. Both lists
  // are contract-locked by tests/unit/test_web_puzzle_rule_composer.py.
  const PUZZLE_ACTIONS = [
    "go_left", "go_right", "stay", "jump",
  ];
  const PUZZLE_CONDITION_GROUPS = [
    { label: "color ==",  options: ['color == "red"', 'color == "blue"', 'color == "green"', 'color == "yellow"'] },
    { label: "shape ==",  options: ['shape == "circle"', 'shape == "triangle"', 'shape == "square"', 'shape == "star"'] },
    { label: "number ==", options: ["number == 1", "number == 2", "number == 3", "number == 4"] },
    { label: "number >=", options: ["number >= 2", "number >= 3", "number >= 4"] },
    { label: "number <=", options: ["number <= 1", "number <= 2", "number <= 3"] },
    { label: "parity",    options: ["number % 2 == 1", "number % 2 == 0"] },
  ];

  /** Attribute a condition label tests: 'color == "red"' -> "color". */
  function conditionAttribute(label) {
    const m = /^(color|shape|number)\b/.exec(label || "");
    return m ? m[1] : "";
  }

  /** Fresh, empty slot state for a rule shape (list of clause arities). Two
   * condition slots are always allocated so an arity-1 clause never has to
   * grow its array; only the first `arity` are read. */
  function emptyPuzzleSlots(shape) {
    return {
      clauses: (shape || []).map(() => ({ conds: ["", ""], action: "" })),
      elseAction: "",
    };
  }

  /** Validation messages for the current slots (empty list = valid so far).
   * Only the `and` constraint is reported; unfilled blanks simply keep the
   * composed rule empty. */
  function puzzleSlotErrors(shape, slots) {
    const out = [];
    if (!shape || !slots) return out;
    shape.forEach((arity, i) => {
      if (arity < 2) return;
      const c = slots.clauses[i];
      if (!c || !c.conds[0] || !c.conds[1]) return;
      if (conditionAttribute(c.conds[0]) === conditionAttribute(c.conds[1])) {
        out.push(
          "Clause " + (i + 1) +
          ": the two conditions of an `and` clause must test different attributes."
        );
      }
    });
    return out;
  }

  /** The one-line RULE string in parse_rule_text's grammar, or "" until every
   * blank is filled and puzzleSlotErrors is empty. */
  function composePuzzleRule(shape, slots) {
    if (!shape || !slots || puzzleSlotErrors(shape, slots).length) return "";
    const parts = [];
    for (let i = 0; i < shape.length; i++) {
      const c = slots.clauses[i];
      if (!c || !c.action) return "";
      const conds = c.conds.slice(0, shape[i]);
      if (conds.some((x) => !x)) return "";
      parts.push((i === 0 ? "if " : "elif ") + conds.join(" and ") + ": " + c.action);
    }
    if (!slots.elseAction) return "";
    parts.push("else: " + slots.elseAction);
    return parts.join("; ");
  }
```

그리고 같은 파일의 `Object.assign((window.squidArenaHelpers = window.squidArenaHelpers || {}), {` 객체에 다음 항목을 추가한다(`parseClues,` 줄 뒤):

```js
    puzzleActions: PUZZLE_ACTIONS,
    puzzleConditionGroups: PUZZLE_CONDITION_GROUPS,
    conditionAttribute,
    emptyPuzzleSlots,
    puzzleSlotErrors,
    composePuzzleRule,
```

- [ ] **Step 4: 테스트 실행 + 문법 확인**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_web_puzzle_rule_composer.py -q -p no:cacheprovider`
Expected: 전부 통과.

JS 문법 확인(빌드가 없으므로 파서만 통과시킨다): `node --check web/frontend/app.js` (node가 있을 때; 없으면 건너뛰고 Task 5의 브라우저 확인에서 잡는다).

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add web/frontend/app.js tests/unit/test_web_puzzle_rule_composer.py
git commit -m "feat(web): puzzle RULE composer helpers (engine condition grammar) + parser round-trip contract test"
```

---

### Task 5: 프런트엔드: 설정 카드 Mode, Stage 2 퍼즐 폼, 상태/체크포인트/저장

**Files:**
- Modify: `web/frontend/app.js` (`playScreen` 컴포넌트, `SETTINGS_GROUPS` / `SETTINGS_LABELS`)
- Modify: `web/frontend/index.html`

**Interfaces:**
- Consumes: Task 3의 응답 필드 `signal_mode`, `puzzle{puzzle_turn, shape, shape_block, rule_template_hint, clues[], query, n_clues}`; Task 4의 `squidArenaHelpers.{puzzleActions, puzzleConditionGroups, emptyPuzzleSlots, puzzleSlotErrors, composePuzzleRule}`; 기존 `squidArenaHelpers.{miniStimHTML, shapeSVG, actionEmoji, actionLabel}`.
- Produces: `playScreen` 상태 `signalMode`, `puzzle`, `puzzleSlots`; getter `puzzleErrors`, `assembledPuzzleRule`; `assembledRule` / `stimulus` / `clues` getter의 모드 분기; `startGame` 본문 `signal_mode`; `finishGame`의 `save=true`; 체크포인트 `signalMode`.

- [ ] **Step 1: `app.js`: 로그 설정 라벨**

`SETTINGS_GROUPS`의 첫 그룹(`keys: ["run_name", "task", "difficulty", "framing", "forfeit_condition", ...]`)의 `"task",` 뒤에 `"signal_mode",`를 넣고, `SETTINGS_LABELS` 객체에 `signal_mode: "Mode",`를 추가한다(`difficulty: "Difficulty",` 줄 앞).

- [ ] **Step 2: `app.js`: `playScreen` 상태와 getter**

`difficulty: "easy",` 상태 선언 뒤에 추가:

```js
      // Signal Game stimulus mode (2026-09-06). Chosen on the setup screen,
      // held constant across the campaign, saved in the resume checkpoint.
      // "sequential" = one hidden rule per game; "per_turn_puzzle" = a fresh
      // shape-disclosed puzzle every round (10 turns, 3 lives, +10 flat).
      signalMode: "sequential",
      // /api/state's puzzle view for the turn on screen (null in sequential
      // mode), and the player's slot choices for its blanks. The slots are
      // reset every turn: the rule changes every round.
      puzzle: null,
      puzzleSlots: null,
```

`get stimulus()` / `get clues()`를 다음으로 교체:

```js
      // Parsed {color, shape, number} for the current signal, or null. In
      // puzzle mode it is the round's query card as the server serves it.
      get stimulus() {
        if (this.puzzle) return this.puzzle.query;
        return this.state
          ? squidArenaHelpers.parseStimulus(this.state.observation)
          : null;
      },
      // "Clue" example pairs: the round's clues in puzzle mode, else the
      // few-shot examples embedded in the system prompt.
      get clues() {
        if (this.puzzle) return this.puzzle.clues;
        return this.state
          ? squidArenaHelpers.parseClues(this.state.system_prompt)
          : [];
      },
      get isPuzzle() {
        return this.signalMode === "per_turn_puzzle";
      },
      get puzzleErrors() {
        if (!this.puzzle || !this.puzzleSlots) return [];
        return squidArenaHelpers.puzzleSlotErrors(this.puzzle.shape, this.puzzleSlots);
      },
      get assembledPuzzleRule() {
        if (!this.puzzle || !this.puzzleSlots) return "";
        return squidArenaHelpers.composePuzzleRule(this.puzzle.shape, this.puzzleSlots);
      },
```

`get assembledRule()`의 첫 줄 `const d = this.difficulty;` 앞에 추가:

```js
        if (this.isPuzzle) return this.assembledPuzzleRule;
```

- [ ] **Step 3: `app.js`: 요청/응답 배선**

`startGame()`의 `body: JSON.stringify({ ... })` 객체에서 `difficulty: this.difficulty,` 와 `num_few_shot: ...` 두 항목을 다음으로 교체:

```js
                signal_mode: this.signalMode,
                // Puzzle mode ignores difficulty; "medium" matches the LLM
                // puzzle configs so the recorded SeasonResult.difficulty
                // agrees. The server applies the puzzle session shape
                // (10 turns, 3 lives) itself, so neither is sent here.
                difficulty: this.isPuzzle ? "medium" : this.difficulty,
                // Show 2 rule-informative clue examples up front (one
                // positive + one negative), surfaced in the History panel.
                // MEDIUM is defined by having a single example (the engine
                // default for that level), so it sends 1 instead. Puzzle
                // mode has no few-shot block at all.
                num_few_shot: this.isPuzzle ? null : (this.difficulty === "medium" ? 1 : 2),
```

`refreshState()`에서 `this.state = s;` 뒤에 추가:

```js
          this.signalMode = s.signal_mode || "sequential";
          this.puzzle = s.puzzle || null;
          this.puzzleSlots = this.puzzle
            ? squidArenaHelpers.emptyPuzzleSlots(this.puzzle.shape)
            : null;
```

`commitAction()`의 규칙 게이트 메시지를 모드별로 나눈다:

```js
        if (!this.assembledRule) {
          this.error = this.isPuzzle
            ? "Fill every blank of the rule shape (and keep both conditions of an `and` clause on different attributes) before submitting."
            : "Fill all four parts of your rule guess (attribute · value · action · default) before submitting.";
          return;
        }
```

`submitAction()`에서 `this.turnStage = 1;` 뒤, `this._clearAutoContinue();` 앞에 추가:

```js
          // Puzzle mode: a new rule every round, so the view and the form
          // are dropped until refreshState() serves the next round (the
          // sequential toggles below are deliberately kept).
          if (this.isPuzzle) { this.puzzle = null; this.puzzleSlots = null; }
```

`finishGame()`의 fetch URL을 다음으로 교체:

```js
          const res = await fetchJSON(
            // Puzzle games also append the SeasonResult to the server's
            // outputs/api_sessions/season_results.jsonl, the file the
            // analysis loaders read for LLM runs (spec §7.1).
            `/api/result?session_id=${encodeURIComponent(this.sessionId)}` +
              (this.isPuzzle ? "&save=true" : ""),
            {},
            (m) => (this.statusMsg = m)
          );
```

체크포인트: `_saveCheckpoint()`의 `difficulty: this.difficulty,` 뒤에 `signalMode: this.signalMode,`를 추가하고, `resumeCampaign()`에서 `this.difficulty = ck.difficulty || "easy";` 뒤에 `this.signalMode = ck.signalMode || "sequential";`를 추가한다(`v: 5` 유지).

- [ ] **Step 4: `index.html`: 설정 카드**

`<label style="margin-top:14px; display:block;">Difficulty</label>` 앞에 추가:

```html
        <label style="margin-top:14px; display:block;">Mode</label>
        <div class="cond-cards">
          <div class="cond-card" :class="{ on: signalMode === 'sequential' }" @click="signalMode = 'sequential'">
            <span class="cond-label">Classic</span>
            <span class="cond-blurb">One hidden rule per game. Work it out from your own answers over 10 rounds.</span>
          </div>
          <div class="cond-card" :class="{ on: signalMode === 'per_turn_puzzle' }" @click="signalMode = 'per_turn_puzzle'">
            <span class="cond-label">Puzzle</span>
            <span class="cond-blurb">A new rule every round. Its shape is shown; fill in the blanks from the examples. 10 rounds, 3 attempts.</span>
          </div>
        </div>
```

Difficulty 라벨과 그 `cond-cards` div를 `<div x-show="signalMode !== 'per_turn_puzzle'">` ... `</div>`로 감싼다.

- [ ] **Step 5: `index.html`: Stage 2 퍼즐 블록**

`<!-- Rule-inference toggle builder -->` 주석 바로 뒤, 기존 `<template x-if="difficulty !== 'hard' && difficulty !== 'expert'">` 앞에 추가:

```html
            <template x-if="isPuzzle && puzzle && puzzleSlots">
            <div class="puzzle-stage">
              <div class="rule-preview">
                <span class="muted">Round</span>
                <code x-text="puzzle.puzzle_turn + ' of ' + state.total_turns"></code>
                <span>&nbsp;·&nbsp; <span class="muted">This round's rule has exactly this shape. Fill in the blanks.</span></span>
              </div>

              <!-- Rule shape as a form: one select per blank -->
              <div class="rule-builder rule-chips puzzle-shape">
                <template x-for="(arity, ci) in puzzle.shape" :key="'clause' + ci">
                  <div class="puzzle-clause" style="flex-basis:100%;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                    <span class="kw" x-text="ci === 0 ? 'if' : 'elif'"></span>
                    <template x-for="k in arity" :key="'cond' + ci + '-' + k">
                      <span style="display:inline-flex;gap:6px;align-items:center;">
                        <span class="kw" x-show="k > 1">and</span>
                        <select class="chip" :class="{ set: !!puzzleSlots.clauses[ci].conds[k - 1] }"
                                x-model="puzzleSlots.clauses[ci].conds[k - 1]">
                          <option value="">condition</option>
                          <template x-for="g in squidArenaHelpers.puzzleConditionGroups" :key="g.label">
                            <optgroup :label="g.label">
                              <template x-for="opt in g.options" :key="opt">
                                <option :value="opt" x-text="opt"></option>
                              </template>
                            </optgroup>
                          </template>
                        </select>
                      </span>
                    </template>
                    <span class="kw">: action =</span>
                    <select class="chip" :class="{ set: !!puzzleSlots.clauses[ci].action }"
                            x-model="puzzleSlots.clauses[ci].action">
                      <option value="">action</option>
                      <template x-for="a in squidArenaHelpers.puzzleActions" :key="a">
                        <option :value="a" x-text="squidArenaHelpers.actionLabel(a)"></option>
                      </template>
                    </select>
                  </div>
                </template>
                <div class="puzzle-clause" style="flex-basis:100%;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                  <span class="kw">else</span>
                  <span class="kw">: action =</span>
                  <select class="chip" :class="{ set: !!puzzleSlots.elseAction }" x-model="puzzleSlots.elseAction">
                    <option value="">action</option>
                    <template x-for="a in squidArenaHelpers.puzzleActions" :key="'else' + a">
                      <option :value="a" x-text="squidArenaHelpers.actionLabel(a)"></option>
                    </template>
                  </select>
                </div>

                <template x-for="(msg, mi) in puzzleErrors" :key="'perr' + mi">
                  <p class="muted" style="flex-basis:100%;margin:4px 0 0;color:var(--danger,#e0575b);" x-text="msg"></p>
                </template>

                <span class="rule-preview" style="flex-basis:100%;margin-top:8px;">
                  <span class="muted">Submitting:</span>
                  <code x-text="assembledPuzzleRule || '— (fill every blank)'"></code>
                </span>
              </div>

              <!-- Examples that follow this round's rule -->
              <h3 style="margin-top:14px;">Examples that follow this round's rule</h3>
              <div class="puzzle-clues">
                <template x-for="(c, i) in puzzle.clues" :key="'pclue' + i">
                  <div class="hist-row is-clue">
                    <span class="hist-stim" x-html="squidArenaHelpers.miniStimHTML(c)"></span>
                    <span class="muted" x-text="c.text"></span>
                    <span class="hist-arrow">→</span>
                    <span class="hist-act">
                      <span x-text="squidArenaHelpers.actionEmoji(c.action)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(c.action)"></span>
                    </span>
                  </div>
                </template>
              </div>
            </div>
            </template>
```

기존 두 규칙 빌더 템플릿의 조건을 각각 다음으로 바꾼다:

- `<template x-if="difficulty !== 'hard' && difficulty !== 'expert'">` → `<template x-if="!isPuzzle && difficulty !== 'hard' && difficulty !== 'expert'">`
- `<template x-if="difficulty === 'hard' || difficulty === 'expert'">` → `<template x-if="!isPuzzle && (difficulty === 'hard' || difficulty === 'expert')">`

`<p class="muted rule-gate-hint" ...>` 안의 세 `<span>`에 `!isPuzzle && `를 각 `x-show` 조건 앞에 붙이고, 네 번째 span을 추가한다:

```html
              <span x-show="isPuzzle">Fill every blank of the rule shape (both conditions of an <code>and</code> clause must test different attributes) to submit.</span>
```

stimulus 캡션: `<div class="stimulus-caption">` 위에 퍼즐 모드용 한 줄을 추가한다(기존 캡션은 그대로):

```html
                <div class="stimulus-eyebrow" x-show="isPuzzle" x-text="'Now: ' + (stimulus && stimulus.text ? stimulus.text : '')"></div>
```

- [ ] **Step 6: 수동 확인**

로컬 백엔드 + 정적 프런트로 한 판 돈다.

```bash
PYTHONPATH=game:web:db ~/.venvs/squid-game/bin/python -m uvicorn squid_arena.api:app --port 8000 --reload
# 별도 터미널
cd web/frontend && python3 -m http.server 8080
```

브라우저(`http://localhost:8080`, `WEB_ARENA_API`가 8000을 가리키도록 기존 설정 사용)에서:
1. 설정 카드에 Mode 카드 2개, Puzzle 선택 시 Difficulty가 사라진다.
2. Stage 1에 모양/힌트/카드가 보이지 않는다.
3. CONTINUE 뒤 Stage 2에 `if/elif/else` 폼, 힌트 목록, query 카드가 보이고 History 패널의 CLUE 행이 같은 힌트를 보여준다.
4. `and` 절에 같은 속성을 두 번 고르면 빨간 안내와 함께 Submit이 비활성이다.
5. 빈칸을 다 채우면 "Submitting:" 줄이 `if color == "red": stay; ...` 형식이고 제출이 된다. 오답이면 하트가 깨진다. 3번째 오답에 탈락 오버레이.
6. 게임 종료 뒤 서버 CWD의 `outputs/api_sessions/season_results.jsonl`에 한 줄이 추가되고, Logs 탭 설정 패널에 `Mode: per_turn_puzzle`이 보인다.
7. Classic 모드로 한 판 더 돌려 기존 칩 빌더가 그대로인지 본다.

- [ ] **Step 7: 회귀 테스트**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit/test_web_puzzle_rule_composer.py tests/unit/test_api_web_arena_puzzle.py -q -p no:cacheprovider`
Expected: 통과 (app.js 라벨 계약 포함).

- [ ] **Step 8: Commit (orchestrator)**

```bash
git add web/frontend/app.js web/frontend/index.html
git commit -m "feat(web): puzzle mode in the Play UI: mode picker, Stage 2 shape form with clues and query card, checkpoint + JSONL save"
```

---

### Task 6: 사람/LLM 패리티 테스트, 전체 게이트, 구현 노트

**Files:**
- Create: `tests/characterization/test_web_puzzle_parity.py`
- Modify: `docs/history/plans/2026-09-06-web-signal-puzzle-human-play.md` (이 파일, 구현 노트)

**Interfaces:**
- Consumes: `tests.integration.conftest.StubProvider(response_fn)`, `squid_game.runner.{ExperimentRunner, load_config_from_yaml}`, `squid_game.models.results.SeasonResult`, Task 1–2의 `HumanGameSession(signal_mode="per_turn_puzzle")`.
- Produces: 같은 seed의 사람 세션과 LLM 스텁 시즌이 턴마다 같은 `hidden_rule` / `clues` / `query_signal` / `rule_shape`를 기록한다는 고정 계약. seed 짝짓기 규칙(사람 seed = `SeasonResult.seed` = config seed + 반복 번호)을 코드로 못 박는다.

- [ ] **Step 1: 테스트 작성**

`tests/characterization/test_web_puzzle_parity.py`:

```python
"""A human puzzle game and an LLM puzzle season sharing a seed play the same
ten puzzles.

This is the property the whole web feature exists for: the analysis loaders
read a human ``SeasonResult`` and an LLM one identically, and pairing them by
seed is only meaningful if turn N showed both players the same hidden rule,
clues and query.

The LLM side runs Cell 0 of ``signal_puzzle_smoke.yaml`` through
``ExperimentRunner`` with a stub provider that answers from the regenerated
puzzle (so all ten turns are played). The human side is a
``HumanGameSession`` seeded with the seed the runner *recorded* -- which is
``task_config.seed + repetition``, repetitions being 1-based. That offset is
the pairing rule (spec 2026-09-06 web-signal-puzzle §5.2), pinned here.

The config's ``total_turns`` / ``lives.initial`` are overridden to 10 / 3 in
memory so the test does not depend on the YAML edit that lands separately.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from squid_arena.human_game import HumanGameSession
from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.signal_game.puzzle import generate_puzzle, puzzle_rng
from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config
from tests.integration.conftest import StubProvider

_CONFIG = "configs/experiment/signal_puzzle_smoke.yaml"
_TURN_LINE = re.compile(r"^Turn (\d+)\. This round's rule has exactly this shape", re.MULTILINE)
_PARITY_KEYS = ("hidden_rule", "clues", "query_signal", "rule_shape", "correct_action",
                "n_clues", "n_minimal_clues", "query_overlap_count", "puzzle_turn")


def _cell0_config(tmp_path: Path):
    cfg = load_config_from_yaml(_CONFIG)
    season = next(
        s for s in cfg.seasons
        if getattr(s.forfeit_condition, "value", s.forfeit_condition) == "not_allowed"
    )
    season = season.model_copy(
        update={"task_config": season.task_config.model_copy(update={"total_turns": 10})}
    )
    return cfg.model_copy(update={
        "seasons": [season],
        "num_repetitions": 1,
        "parallel_workers": 1,
        "output_dir": str(tmp_path),
        "lives": cfg.lives.model_copy(update={"initial": 3}),
    })


def _stub_for(seed: int) -> StubProvider:
    ladder = load_signal_puzzle_config()

    def _reply(_idx: int, messages: list[dict[str, str]]) -> str:
        body = messages[-1]["content"]
        match = _TURN_LINE.search(body)
        assert match is not None, body
        turn = int(match.group(1))
        puzzle = generate_puzzle(puzzle_rng(seed, turn), ladder.spec_for_turn(turn))
        return f"RULE: {puzzle.rule.description}\nACTION: {puzzle.correct_action}"

    return StubProvider(response_fn=_reply)


def test_same_seed_same_ten_puzzles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cell0_config(tmp_path)
    configured_seed = cfg.seasons[0].task_config.seed
    effective_seed = configured_seed + 1  # repetition 1 of 1 (1-based)
    stub = _stub_for(effective_seed)
    monkeypatch.setattr(
        ExperimentRunner, "_create_provider", staticmethod(lambda _provider_config: stub)
    )
    ExperimentRunner(cfg).run()

    run_dir = next(p for p in tmp_path.iterdir() if p.is_dir())
    lines = (run_dir / "season_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    llm = SeasonResult.model_validate_json(lines[0])
    assert llm.seed == effective_seed
    assert len(llm.turns) == 10

    # --- human side, seeded with the seed the runner recorded ---------------
    # starting_score follows the config (30.0) so final scores compare 1:1;
    # the web default is 0.0 and is irrelevant to which puzzles are served.
    human = HumanGameSession(
        task_name="signal_game",
        difficulty="medium",
        framing="true_baseline",
        forfeit_condition="not_allowed",
        seed=llm.seed,
        total_turns=10,
        lives_total=3,
        starting_score=cfg.seasons[0].task_config.starting_score,
        signal_mode="per_turn_puzzle",
    )
    task_bodies = [c.messages[-1]["content"] for c in stub.calls]
    assert len(task_bodies) == 10, "Cell 0 issues exactly one task call per turn"
    for turn in range(1, 11):
        state = human.get_turn_state()
        puzzle = human._task.current_puzzle
        # Every clue the human sees is in the LLM's task call for that turn.
        body = task_bodies[turn - 1]
        assert f"Turn {turn}. This round's rule has exactly this shape" in body
        for clue in state.puzzle.clues:
            assert clue["text"] in body
        assert state.puzzle.query["text"] in body
        human.submit_action(puzzle.correct_action, probe_answer=puzzle.rule.description)
    result = human.get_result()
    assert result.seed == llm.seed
    assert len(result.turns) == 10

    for h, l in zip(result.turns, llm.turns, strict=True):
        for key in _PARITY_KEYS:
            assert h.task_metadata[key] == l.task_metadata[key], key
        assert h.task_metadata["rule_match_score"] == l.task_metadata["rule_match_score"] == 100.0
        assert h.task_metadata["correct"] is True and l.task_metadata["correct"] is True
        assert h.lives_after == l.lives_after == 3
    assert result.final_score == llm.final_score
```

- [ ] **Step 2: 실행**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/characterization/test_web_puzzle_parity.py -q -p no:cacheprovider`
Expected: 통과. 실패한다면 첫 확인 지점은 `llm.seed == configured + 1`(짝짓기 규칙), `_TURN_LINE`(관찰 템플릿 첫 줄), 그리고 `starting_score`(config 30.0을 사람 세션에도 넘겼는지)다.

- [ ] **Step 3: 전체 게이트**

Run: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest tests/unit tests/integration tests/characterization -q -p no:cacheprovider`
Expected: 기준선 실패(`test_api_web_arena.py::test_app_imports_and_registers_all_endpoints`) 외 새 실패 없음. `tests/integration/test_signal_puzzle_e2e.py`가 동시 작업 상태에 따라 실패할 수 있다; 그 파일은 이 계획의 범위가 아니므로 오케스트레이터가 "이 계획 이전에도 실패했는지"를 `git stash` 없이 판단한다(해당 파일의 실패 메시지가 `puzzle_tier` / `total_turns == 30` 같은 v1 잔재를 가리키면 이 계획과 무관하다).

- [ ] **Step 4: 구현 노트**

이 파일 끝의 "구현 노트" 절을 채운다: 커밋 해시, 기준선 대비 새로 통과한 테스트 수, 스냅샷 diff 요약(추가된 스키마 3개, 필드 2+1개), 수동 확인 결과, 그리고 후속 항목(DB `turns.task_metadata` 열, 로그 트레이스의 퍼즐 렌더링, CLAUDE.md Web Arena 문단 한 줄 갱신은 동시 작업이 끝난 뒤).

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add tests/characterization/test_web_puzzle_parity.py docs/history/plans/2026-09-06-web-signal-puzzle-human-play.md docs/history/specs/2026-09-06-web-signal-puzzle-human-play-design.md
git commit -m "test(web): human/LLM puzzle parity by seed; docs: web signal puzzle human play spec + plan"
```

---

## 구현 노트

(Task 6 Step 4에서 채운다.)

- 커밋:
- 테스트:
- OpenAPI 스냅샷 diff:
- 수동 확인:
- 후속:
  - `turns` 테이블 `task_metadata` JSON TEXT 열 (SQLite / Postgres, `settings` 열과 같은 패턴): 배포 환경에서 사람 퍼즐 데이터를 DB에 남기기 위함.
  - 로그 탐색기 턴 트레이스의 퍼즐 렌더링(모양 + 힌트 + query 카드 + 제출한 RULE).
  - `CLAUDE.md` Web Arena 문단에 "Puzzle mode: `signal_mode` in `/api/new_game`, Stage 2 shape form" 한 줄 (동시 작업 종료 후).
