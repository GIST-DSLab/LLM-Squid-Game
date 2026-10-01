# 설계 문서: Web Arena에서 Signal Game v2 턴별 퍼즐 인간 플레이

**날짜:** 2026-09-06
**상태:** 설계 확정, 구현 계획 작성 완료 (`docs/history/plans/2026-09-06-web-signal-puzzle-human-play.md`)
**범위:** `web/squid_arena` (FastAPI) + `web/frontend` (Alpine.js)에서 사람이 `signal_mode: per_turn_puzzle`을 LLM과 같은 엔진으로 플레이하게 한다.
**브랜치:** `feat/signal-game-per-turn-puzzle` (워크트리 `.claude/worktrees/signal-game-per-turn-puzzle`)
**선행 스펙:** `docs/history/specs/2026-09-06-signal-puzzle-shaped-rules-design.md` (퍼즐 v2, 이하 "v2 스펙"). v2 스펙 §2 비목표의 첫 항목 "Web Arena human play 반영 (후속)"이 이 문서다.

## 1. 문제

퍼즐 v2는 LLM 런 전용으로 구현됐다. `SignalGameModule`은 `signal_mode="per_turn_puzzle"`에서 10턴 사다리를 `cached_puzzle(seed, turn, spec)`으로 뽑고, `prepare`가 v2 스펙 §9의 턴 메타데이터를 채우며, `score`가 Python 형식 RULE 줄을 `parse_rule_text`로 파싱해 64장 기능 일치율(`rule_match_score`)과 `rule_shape_match`, `rule_parse_failed`를 기록한다.

Web Arena의 인간 플레이(`HumanGameSession`)는 여전히 순차 모드만 돈다. 구체적으로:

- `HumanGameSession.__init__`은 `signal_mode`를 넘기지 않아 모듈이 항상 `sequential`로 초기화된다.
- `get_turn_state`는 `get_observation`만 부르고 `prepare`는 부르지 않으므로 v2 메타데이터(`clues`, `rule_shape` 등)를 얻을 길이 없다.
- `submit_action`은 `self._task.apply_action(action)`(레거시 경로)로 채점한다. `score()`를 부르지 않으니 `rule_match_score`도, `task_metadata`도 기록되지 않는다. RULE 추측은 `score_probe(probe_answer)`로 따로 채점해 `ProbeResult.score`에만 남는다.
- 프런트엔드의 규칙 입력 UI는 순차 모드의 난이도별 템플릿("If color is red then stay, otherwise jump.")을 칩 드롭다운으로 조립한다. 퍼즐 v2의 규칙 문법(`if/elif/else` 결정 목록, 20개 원자 조건, `and` 복합 조건)과 맞지 않는다.

그래서 같은 seed를 받은 사람과 LLM을 같은 10문제로 비교할 수 없고, 사람의 결과를 분석 로더(`evaluation/shared/loaders.py`)가 LLM 결과와 같은 열로 읽을 수도 없다.

## 2. 목표 / 비목표

**목표**

- 같은 엔진. 인간 세션이 `SignalGameModule`을 `signal_mode="per_turn_puzzle"`로 초기화하고, 매 턴 `prepare` → `score`를 `UnifiedTurnManager`와 같은 순서로 부른다. 같은 seed의 사람과 LLM은 같은 10문제(`hidden_rule`, `clues`, `query_signal`)를 받는다.
- 세션 모양: 최대 10턴, 라이프 3 (오답 1개당 1개, FORFEIT는 라이프를 소모하지 않음), 정답 flat +10.
- 기존 2단계 턴 유지. Stage 1은 결정만(이번 라운드에 대한 정보 없음), Stage 2에서 규칙 모양 + 예시 힌트 + query 카드를 보여주고 빈칸을 채워 행동을 고른다.
- 규칙 입력은 공개된 모양을 그대로 폼으로 그린다. 빈칸 하나당 드롭다운 하나. 조건 빈칸은 원자 조건 20개(6개 그룹), 행동 빈칸은 행동 4개. `and` 절의 두 조건은 속성이 달라야 한다(클라이언트 + 서버 검증).
- 클라이언트가 `parse_rule_text`가 받는 문법 그대로 한 줄 RULE 문자열을 조립해 보내고, 서버는 `SignalGameModule.score`로만 채점한다. 사람 전용 채점 경로는 없다.
- 결과는 LLM 런과 같은 `SeasonResult` 모양으로 저장한다. 턴마다 `task_metadata`에 `puzzle_turn, rule_shape, n_clues, n_minimal_clues, query_overlap_count, rule_match_score, rule_shape_match, rule_parse_failed, hidden_rule, clues, query_signal`이 들어간다.
- 순차 모드(캠페인 규칙 회전 포함)는 바이트 단위로 그대로 동작한다.

**비목표**

- 프레이밍, "Attempts/Lives" 어휘, 위협 문구의 재설계. `HumanGameSession`이 프레이밍별로 렌더하는 텍스트는 그대로 쓴다.
- 리더보드 재설계. 퍼즐 모드 게임은 지금의 캠페인/리더보드 의미론에 최소한으로 얹는다(§7.3).
- BYOE LLM arena(`/api/arena/run`)의 퍼즐 모드. 그 경로는 `arena.py`가 별도 config를 만들며, 이번 범위 밖이다.
- 로그 탐색기의 퍼즐 전용 트레이스 렌더링(§9).
- DB 스키마 변경. `turns` 테이블에 `task_metadata` 열을 추가하는 일은 후속으로 남긴다(§7.2, §9).

## 3. 사용자 흐름 (턴 하나)

### 3.1 설정 화면

기존 설정 카드(닉네임, 비밀번호, 게임, 난이도)에 **Mode** 선택이 추가된다. 두 카드:

- `sequential` "Classic": 게임마다 숨은 규칙 하나, 지금의 난이도 선택이 그대로 보인다.
- `per_turn_puzzle` "Puzzle": 라운드마다 새 규칙, 규칙의 모양이 공개된다. 난이도 카드는 숨긴다(퍼즐 모드는 난이도를 쓰지 않는다).

모드는 캠페인 단위로 고정된다(6게임 동안 같은 모드). 재개 체크포인트에도 저장된다.

### 3.2 Stage 1 (결정)

지금과 같다. 화면에는 라운드 번호, 이번 턴 정답 시 보상(+10), 현재 점수, 하트(라이프 3개), FORFEIT 가능 여부(불가 셀은 3초 자동 진행)만 있다. 이번 라운드의 규칙 모양, 힌트, query 카드는 **아무것도** 보이지 않는다. 이것은 LLM의 decision call이 stimulus 없이 나가는 것과 같다.

FORFEIT를 고르면 REASON 숫자(1|2|3)를 고르고 즉시 제출되며 세션이 끝난다. 카드는 끝까지 보여주지 않는다.

### 3.3 Stage 2 (답변) 화면 내용

CONTINUE를 누르면 Stage 2가 열린다. 위에서부터:

1. **라운드 헤더**: `Round 7 of 10`, 그리고 문장 "This round's rule has exactly this shape. Fill in the blanks."
2. **규칙 모양(blank form)**: 서버가 준 `puzzle.shape`(절별 arity, 예: `[1, 2, 1]`)를 그대로 Python 코드 모양으로 그린다. 각 줄은 키워드와 드롭다운으로 구성된다.

   ```
   if   [condition ▾]                       :  action = [action ▾]
   elif [condition ▾] and [condition ▾]     :  action = [action ▾]
   elif [condition ▾]                       :  action = [action ▾]
   else                                     :  action = [action ▾]
   ```

   조건 드롭다운은 그룹 6개로 나뉜다(순서 고정, 라벨은 엔진 `ATOMS` 라벨과 동일):
   - `color ==`: `color == "red"`, `"blue"`, `"green"`, `"yellow"`
   - `shape ==`: `shape == "circle"`, `"triangle"`, `"square"`, `"star"`
   - `number ==`: `number == 1`, `2`, `3`, `4`
   - `number >=`: `number >= 2`, `3`, `4`
   - `number <=`: `number <= 1`, `2`, `3`
   - parity: `number % 2 == 1`, `number % 2 == 0`

   행동 드롭다운은 `go_left`, `go_right`, `stay`, `jump`.

   `and` 절에서 두 조건의 속성(`color` / `shape` / `number`)이 같으면 그 줄 아래에 빨간 안내 "The two conditions of an `and` clause must test different attributes."가 뜨고 제출이 막힌다.
3. **예시 힌트(clues)**: "Examples that follow this round's rule" 아래에 힌트를 한 줄씩. 각 줄은 미니 카드 SVG(`miniStimHTML`) + 텍스트(`red star with number 2`) + 화살표 + 행동 이모지/라벨. 오른쪽 History 패널의 CLUE 행도 같은 목록을 보여준다.
4. **query 카드**: 기존 stimulus 영역에 `puzzle.query`를 큰 카드로 렌더한다(색·도형·개수). 캡션 "Now: green circle with number 3".
5. **행동 선택**: 기존 4개 행동 버튼.
6. **제출 미리보기**: "Submitting:" 뒤에 조립된 RULE 한 줄. 예: `if color == "red": stay; elif number >= 3 and shape == "star": go_left; elif number <= 1: jump; else: go_right`.
7. **Reasoning(선택)** textarea, 기존과 같다.
8. **Submit 버튼**: 행동이 골라지고 RULE이 완성(모든 빈칸 채움 + `and` 검증 통과)됐을 때만 활성.

제출 후 피드백 카드는 지금과 같이 `correct/incorrect`, 보상, 점수만 보여준다. 정답 행동이나 숨은 규칙, `rule_match_score`는 **플레이 중 보여주지 않는다**(LLM도 `feedback.j2`로 정오만 받는다). 오답이면 하트 하나가 깨진다. 3개째 오답에서 탈락 오버레이가 뜬다.

다음 턴은 다시 Stage 1로 돌아간다. 규칙 폼은 **초기화**된다(순차 모드는 한 추측을 다듬으라고 칩을 유지하지만, 퍼즐은 라운드마다 규칙이 바뀐다).

### 3.4 이전 라운드 정보

Stage 2의 observation 텍스트 앞에 붙는 이력 블록은 `history_mode: outcome`과 같은 `format_outcome_history_block`을 쓴다:

```
=== Previous Rounds ===
- Round 1: correct → cumulative: 10.0 (lives: 3/3)
- Round 2: incorrect → cumulative: 10.0 (lives: 2/3)
```

`true_baseline`과 사다리 밖 프레이밍(`baseline_flagship`)은 `lives` 대신 `attempts`를 쓴다(§5.6). 이 블록은 `TurnResult.observation`에 기록되며, 화면에서는 History 패널의 턴 행(T1 ✓ / T2 ✗)이 같은 정보를 보여준다.

## 4. API 변경

모든 변경은 추가(additive)다. 기존 필드의 이름과 의미는 바뀌지 않는다. OpenAPI 스냅샷(`tests/characterization/snapshots/api/openapi.json`)과 키 집합 핀(`STATE_KEYS`)은 갱신한다.

### 4.1 `POST /api/new_game` 요청 (`NewGameRequest`)

| 필드 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `signal_mode` | `str` | `"sequential"` | `"sequential"` 또는 `"per_turn_puzzle"`. 그 외는 400. |

퍼즐 모드에서 서버가 적용하는 기본값(요청에 그 필드가 **명시되지 않았을 때만**, `model_fields_set` 기준):

- `total_turns` → `10` (`PUZZLE_TOTAL_TURNS`)
- `lives_total` → `3` (`PUZZLE_LIVES_TOTAL`)

명시된 값은 그대로 존중한다(테스트에서 2턴 게임을 돌리는 용도). `total_turns > 10`이면 모듈 `initialize`가 던지는 `ValueError`를 400으로 돌려준다. `lives_enabled: false`와 `signal_mode: per_turn_puzzle`의 조합은 허용하지 않는다(400; 라이프 3이 세션 모양의 일부다).

`difficulty`, `num_few_shot`, `curriculum_turns`, `campaign_index`(규칙 회전)는 퍼즐 모드에서 받되 무시된다. `difficulty`는 `SeasonResult.difficulty`에 그대로 기록된다(클라이언트는 LLM config와 맞춰 `"medium"`을 보낸다).

### 4.2 `GET /api/state` 응답 (`TurnStateResponse`)

| 필드 | 타입 | 기본 | 설명 |
|---|---|---|---|
| `signal_mode` | `str` | `"sequential"` | 세션 모드 에코. |
| `puzzle` | `PuzzleTurn \| null` | `null` | 퍼즐 모드에서 게임이 진행 중일 때만 채워진다. 게임 종료 응답과 순차 모드에서는 `null`. |

새 모델:

```python
class PuzzleSignal(BaseModel):
    color: str
    shape: str
    number: int
    text: str            # "green circle with number 3" (Signal.__str__)

class PuzzleClue(PuzzleSignal):
    action: str          # go_left | go_right | stay | jump

class PuzzleTurn(BaseModel):
    puzzle_turn: int             # 사다리 항목 번호 (= 턴 번호)
    shape: list[int]             # 절별 arity, 예 [1, 2, 1]
    shape_block: str             # render_shape_block(shape) 그대로
    rule_template_hint: str      # render_shape_hint(shape) 한 줄, 예 "if ___: ___; elif ___ and ___: ___; else: ___"
    clues: list[PuzzleClue]
    query: PuzzleSignal
    n_clues: int
```

`hidden_rule`, `correct_action`, `n_minimal_clues`, `query_overlap_count`는 **응답에 넣지 않는다**(정답 누설). 이들은 `task_metadata`에만 기록된다.

`observation`은 지금처럼 이력 블록 + 퍼즐 관찰 텍스트(`observation_puzzle.j2` 렌더 결과)이고, `system_rules`는 `system_rules_puzzle.j2`다. `probe_question`은 `probe_puzzle.j2` 문장이다.

### 4.3 `POST /api/action` 요청 (`ActionRequest`)

필드 추가 없음. RULE 한 줄은 기존 `probe_answer`에 담는다(순차 모드도 이 필드로 규칙 추측을 보낸다).

퍼즐 모드 서버 검증(`action != "forfeit"`일 때):

- `probe_answer`가 비어 있으면 400 `"A RULE line is required in puzzle mode."`
- `parse_rule_text(probe_answer)`가 `None`이면 400 `"RULE line does not parse: <text>"` (같은 속성 `and` 포함)
- 파싱된 모양이 이번 라운드 모양과 다르면 400 `"RULE shape 1,1 does not match this round's shape 1,2,1"`

폼이 조립한 문자열은 항상 통과한다. 이 검증은 클라이언트 버그나 임의 요청을 막는 방어선이지, 채점 규칙이 아니다(LLM은 파싱 실패도 `rule_parse_failed=True`로 기록만 한다).

### 4.4 `POST /api/action` 응답 (`ActionResponse`)

필드 추가 없음. `rule_match_score` 등은 플레이 중 노출하지 않는다(§3.3).

### 4.5 `GET /api/result`

필드 추가 없음. 퍼즐 모드에서 클라이언트는 `save=true`를 붙여 호출한다(§7.1).

## 5. 서버 변경: `HumanGameSession` (`web/squid_arena/human_game.py`)

### 5.1 상수와 생성자

```python
SIGNAL_MODES: tuple[str, ...] = ("sequential", "per_turn_puzzle")
PUZZLE_TOTAL_TURNS = 10
PUZZLE_LIVES_TOTAL = 3
```

`__init__(..., signal_mode: str = "sequential")`. 검증 후 모듈 초기화가 갈린다:

```python
if self._signal_mode == "per_turn_puzzle":
    self._task.initialize(
        difficulty=self._difficulty, seed=seed, rule_index=None,
        signal_mode="per_turn_puzzle", total_turns=total_turns,
    )
else:
    self._task.initialize(
        difficulty=self._difficulty, seed=seed, rule_index=rule_index,
        num_few_shot=num_few_shot, curriculum_turns=curriculum_turns,
    )
```

퍼즐 모드에서는 `num_few_shot` / `curriculum_turns`를 넘기지 않는다(넘기면 모듈이 경고 로그를 남긴다). `rule_index`는 `None`(퍼즐 모드는 `_rules`를 보지 않는다).

### 5.2 seed

seed는 지금과 같은 경로로 온다. `routes_game.new_game`이 요청의 `seed`를 쓰고, 없으면 `random.randint(1, 2**31 - 1)`을 뽑는다. `HumanGameSession`은 항상 `int` seed를 받으므로 모듈의 "seed 필수" 검사를 통과한다. 기록 위치는 세 곳: `SeasonResult.seed`, `SessionRecord.seed`, `settings_snapshot()["seed"]`.

**LLM과의 짝짓기 규칙**: `ExperimentRunner`는 반복 r(1부터)에서 `task_config.seed + r`을 효과 seed로 모듈에 넘긴다. 따라서 config seed 42의 1회 반복(`SeasonResult.seed == 43`)과 같은 문제를 받으려면 사람 게임의 `seed`를 **43**으로 보내야 한다. 사람 쪽에는 덧셈이 없다. 이 규칙은 §8.4의 패리티 테스트가 고정한다.

### 5.3 새 상태

```python
self._current_task_ctx: TaskContext | None = None   # prepare 결과, submit_action이 task_metadata 병합에 씀
self._outcome_history: list[dict] = []              # format_outcome_history_block 입력
```

`TurnState`에 `signal_mode: str = "sequential"`, `puzzle: PuzzleTurnView | None = None` 추가. `PuzzleTurnView`는 `human_game.py`의 dataclass(§4.2의 `PuzzleTurn`과 같은 필드; `clues` / `query`는 dict).

### 5.4 `get_turn_state` (퍼즐 분기)

```python
turn_ctx = TurnContext(
    turn_number=turn_num, total_turns=self._total_turns, season_id=self._season_id,
    cumulative_score=self._cumulative_score, p_death=0.0,
    framing=self._framing, forfeit_condition=self._forfeit_cond, difficulty=self._difficulty,
    lives_remaining=self._lives_remaining, lives_total=self._lives_total,
    threat_level=self._threat_level,
)
task_ctx = self._task.prepare(GameState(season_id=self._season_id), turn_ctx)
self._current_task_ctx = task_ctx
observation = task_ctx.prompt_section
history_block = format_outcome_history_block(
    self._outcome_history, max_history_turns=self._total_turns, lives_label=self._lives_label(),
)
```

`prepare`는 안에서 `get_observation`을 부르므로 관찰 텍스트와 메타데이터가 한 번에 나온다. `/api/state`는 폴링되지만 `cached_puzzle(seed, turn, spec)`은 결정적이라 재호출이 무해하다(순차 모드의 "폴링마다 신호 재추첨"과 달리 퍼즐은 같은 문제를 돌려준다).

퍼즐 뷰는 모듈에 추가하는 읽기 전용 프로퍼티로 만든다:

```python
# game/squid_game/tasks/signal_game/module.py
@property
def current_puzzle(self) -> Puzzle | None:
    """This turn's puzzle after prepare()/get_observation() in puzzle mode; None otherwise."""
    return self._current_puzzle
```

`_build_puzzle_view()`는 `puzzle.shape`, `render_shape_block`, `render_shape_hint`, `puzzle.clues[i].signal.{color,shape,number}` + `.action` + `str(clue)`, `puzzle.query`를 읽는다. 힌트 문자열을 정규식으로 되파싱하지 않는다.

`system_rules`, `available_actions`, `probe_question`, `forfeit_*`, peer-death 필드는 기존 코드 그대로다.

### 5.5 `submit_action` (퍼즐 분기)

FORFEIT 분기: 기존과 같되 `ground_truth_rule=self._task.get_active_rule_description()`을 넣는다(엔진의 `build_forfeit_result`도 FORFEIT 턴에 `ground_truth_rule`을 쓰고 `task_metadata={}`를 남긴다).

CONTINUE 분기:

```python
if self._signal_mode == "per_turn_puzzle":
    if action not in self._task.get_available_actions():
        raise ValueError(f"Invalid action '{action}'.")       # apply_action과 같은 계약
    task_ctx = self._current_task_ctx
    if task_ctx is None:
        raise RuntimeError("get_turn_state() must be called before submit_action()")
    parsed = ParsedSignalResponse(action=action, rule_hypothesis=probe_answer.strip() or None)
    task_outcome = self._task.score(parsed, GameState(season_id=self._season_id))
    success_factor = task_outcome.success_factor
    outcome = ActionOutcome(action_taken=action, was_optimal=success_factor == 1.0, reward=0.0)
    task_metadata = {**task_ctx.metadata, **task_outcome.metadata}    # UnifiedTurnManager와 같은 병합
    probe_score = task_outcome.metadata.get("rule_match_score") or 0.0
else:
    outcome = self._task.apply_action(action)                          # 기존 경로 그대로
    success_factor = 1.0 if outcome.was_optimal else 0.0
    task_metadata = {}
    probe_score = self._task.score_probe(probe_answer) if probe_answer else 0.0
```

보상(`calculate_reward`, flat +10), 라이프 장부, 점수 갱신, `decision_quality`, `feedback_text`는 두 모드가 같은 코드를 탄다.

이력: 순차 모드는 `_turn_history`, 퍼즐 모드는 `_outcome_history`에 다음을 넣는다.

```python
{"turn": turn_num, "correct": outcome.was_optimal,
 "outcome": "eliminated" if lives_dead else f"+{reward:.0f}",
 "cumulative_score": self._cumulative_score,
 "lives_after": self._lives_remaining, "lives_total": self._lives_total}
```

`TurnResult`: 퍼즐 모드에서만 `task_metadata=task_metadata`, `task_success_factor=success_factor`, `reward_received=reward`를 추가로 채운다. `ProbeResult.response`는 RULE 문자열, `score`는 `rule_match_score`다(재파싱 없음). 순차 모드의 `TurnResult`는 한 바이트도 바뀌지 않는다.

`task_metadata` 결과 키(엔진과 동일): `signal, hidden_rule, correct_action, turn, puzzle_turn, rule_shape, n_clauses, n_conjunctions, predicates_allowed, overlap_query, clues, query_signal, n_clues, n_minimal_clues, query_overlap_count`(prepare) + `correct, action, correct_action, signal, rule_hypothesis, rule_match_score, puzzle_turn, rule_shape, rule_parse_failed, rule_shape_match`(score).

### 5.6 라이프 어휘

`_lives_label()`: `"lives" if self._threat_level else "attempts"`. `threat_level`이 `None`(사다리 밖)이거나 0(`true_baseline`)이면 `attempts`다. `_framing_display_text`가 사다리 밖 프레이밍에 level-0 attempts 문장을 주는 것과 같은 판단이다.

### 5.7 `validate_rule_text(text) -> str | None`

§4.3의 세 검사를 수행해 오류 문자열 또는 `None`을 돌려준다. 라우트가 400으로 변환한다. `self._task.current_puzzle.shape`와 비교한다.

### 5.8 `settings_snapshot`

`put("signal_mode", self._signal_mode)`, `history_mode`는 퍼즐 모드에서 `"outcome"`, 순차 모드에서 기존 `"cumulative"`. 로그 탐색기의 설정 패널에 `Mode` 행으로 보인다(`SETTINGS_GROUPS`의 game 그룹에 `signal_mode` 키 추가, 라벨 "Mode").

### 5.9 그대로인 것

`preview_continue_reward`(flat 10), peer-death 스케줄러, `get_result`, `save_result`, `set_self_report`.

## 6. 클라이언트 변경 (`web/frontend/app.js`, `index.html`)

### 6.1 헬퍼 상수/함수 (`squidArenaHelpers`)

```js
const PUZZLE_ACTIONS = ["go_left", "go_right", "stay", "jump"];
const PUZZLE_CONDITION_GROUPS = [
  { label: "color ==",  options: ['color == "red"', 'color == "blue"', 'color == "green"', 'color == "yellow"'] },
  { label: "shape ==",  options: ['shape == "circle"', 'shape == "triangle"', 'shape == "square"', 'shape == "star"'] },
  { label: "number ==", options: ["number == 1", "number == 2", "number == 3", "number == 4"] },
  { label: "number >=", options: ["number >= 2", "number >= 3", "number >= 4"] },
  { label: "number <=", options: ["number <= 1", "number <= 2", "number <= 3"] },
  { label: "parity",    options: ["number % 2 == 1", "number % 2 == 0"] },
];
function conditionAttribute(label)            // "color == \"red\"" -> "color"
function emptyPuzzleSlots(shape)              // {clauses: [{conds: ["", ""], action: ""}, ...], elseAction: ""}
function puzzleSlotErrors(shape, slots)       // ["Clause 2: the two conditions of an `and` clause must test different attributes."]
function composePuzzleRule(shape, slots)      // "" until complete + valid; else the one-line RULE
```

`composePuzzleRule`의 출력 형식은 `PuzzleRule.description`과 문자 단위로 같다: 절은 `"; "`로, 조건은 `" and "`로 잇고, `if <cond>: <action>` / `elif ...` / `else: <action>`. 라벨은 그룹 옵션 문자열 그대로 쓴다. 이 계약은 §8.1의 Python 테스트가 고정한다.

### 6.2 Alpine 상태 (`playScreen`)

```js
signalMode: "sequential",   // 설정 카드에서 선택, 캠페인 동안 고정, 체크포인트에 저장
puzzle: null,               // /api/state의 puzzle 뷰
puzzleSlots: null,          // emptyPuzzleSlots(puzzle.shape), 턴마다 초기화
get puzzleErrors()          // puzzleSlotErrors(...)
get assembledPuzzleRule()   // composePuzzleRule(...)
get assembledRule()         // 퍼즐 모드면 assembledPuzzleRule, 아니면 기존 로직
get stimulus()              // 퍼즐 모드면 puzzle.query, 아니면 parseStimulus(observation)
get clues()                 // 퍼즐 모드면 puzzle.clues, 아니면 parseClues(system_prompt)
```

`startGame()` 본문에 `signal_mode: this.signalMode` 추가. 퍼즐 모드면 `difficulty: "medium"`을 보내고 `num_few_shot`은 보내지 않는다. `total_turns` / `lives_total`은 보내지 않아 서버 기본값(10 / 3)이 단일 진실이 된다.

`refreshState()`에서 `this.signalMode = s.signal_mode || "sequential"; this.puzzle = s.puzzle || null; this.puzzleSlots = this.puzzle ? emptyPuzzleSlots(this.puzzle.shape) : null;`.

`submitAction()` 성공 후 퍼즐 모드면 `puzzleSlots`를 다시 비운다(순차 모드는 기존대로 칩 유지). `finishGame()`은 퍼즐 모드에서 `/api/result?...&save=true`를 부른다.

`_saveCheckpoint` / `_loadCheckpoint`: `signalMode` 필드 추가, 버전은 `v: 5` 유지(구 체크포인트는 필드가 없으면 `"sequential"`로 복원).

### 6.3 마크업 (`index.html`)

- 설정 카드: Difficulty 위에 Mode 카드 2개(`cond-cards`). Difficulty 블록은 `x-show="signalMode !== 'per_turn_puzzle'"`.
- Stage 2: 기존 규칙 빌더 두 `<template x-if>`의 조건에 `signalMode !== 'per_turn_puzzle'`을 추가하고, 그 앞에 `<template x-if="signalMode === 'per_turn_puzzle' && puzzle">` 블록을 넣는다. 블록 내용은 §3.3의 2번(모양 폼: `x-for` 절 → arity만큼 `<select>` + 행동 `<select>`; else 줄), 3번(힌트 목록), 6번(미리보기)이다. query 카드(4번)는 기존 stimulus 영역이 `stimulus` getter를 통해 그대로 렌더한다.
- 게이트 안내 문구: 퍼즐 모드용 한 줄 "Fill every blank of the rule shape (and keep both conditions of an `and` clause on different attributes) to submit."
- 로그 설정 패널: `SETTINGS_GROUPS` game 그룹에 `signal_mode`, `SETTINGS_LABELS`에 `signal_mode: "Mode"`.

CSS는 기존 `.rule-chips`, `.kw`, `.observation-box`, `.hist-row` 클래스를 재사용한다. 네이티브 `<select>`에 `.chip` 클래스를 붙인다.

## 7. 영속화

### 7.1 분석용 기록 (JSONL)

`HumanGameSession.save_result()`가 `SeasonResult.model_dump_json()`을 `outputs/api_sessions/season_results.jsonl`에 append한다. 이 파일은 `evaluation.shared.loaders.load_seasons` / `discover_season_jsonl`이 LLM 런에서 읽는 `season_results.jsonl`과 같은 모양이다. 퍼즐 턴의 `task_metadata`가 §5.5의 키를 갖추므로 `to_long_dataframe`의 `puzzle_turn / rule_shape / n_clues / n_minimal_clues / rule_shape_match / rule_match_score` 열이 사람 데이터에도 채워진다. 클라이언트가 퍼즐 모드에서 `save=true`를 보내므로 별도 조작 없이 기록된다.

### 7.2 DB (`squid_store`)

스키마 변경 없음. `SessionRecord.settings`(JSON)에 `signal_mode`와 `history_mode: outcome`이 들어간다. `TurnRecord`는 기존 열만 채운다(`correct`, `lives_*`, `thinking_task` 등). `task_metadata`는 DB에 저장되지 않는다(§9).

### 7.3 캠페인 / 리더보드

- 캠페인은 지금의 6개 조건(3 프레이밍 × 2 forfeit)을 같은 순서로 돈다. 모드는 캠페인 전체에 하나다.
- Play 리더보드는 `campaign_id`별 평균 점수를 모드 구분 없이 낸다. 두 모드 모두 10턴 × +10이 만점이라 점수 척도는 같다. 모드별 분리는 하지 않는다.
- `rule_index_for`는 여전히 계산되지만 퍼즐 세션은 `rule_index=None`으로 초기화되어 무시된다.
- 로그 탐색기 목록/트레이스 헤더는 `settings.signal_mode`로 모드를 보여준다.

## 8. 테스트

테스트 명령: `PYTHONPATH=game ~/.venvs/squid-game/bin/python -m pytest <paths> -q -p no:cacheprovider`.

### 8.1 RULE 조립 계약 (Python): `tests/unit/test_web_puzzle_rule_composer.py`

- Python으로 같은 조립 규칙을 재현하는 `compose(shape, conds, actions)`를 테스트 안에 두고, 사다리 10턴의 모양마다 무작위 슬롯 200개를 조립해 `parse_rule_text(text)`가 `None`이 아니고 `.shape == shape`, `.description == text`(왕복 동일)를 확인한다.
- `app.js`를 텍스트로 읽어 `PUZZLE_CONDITION_GROUPS`의 옵션 문자열 20개가 `[a.label for a in ATOMS]`와 순서까지 같고, `PUZZLE_ACTIONS`가 `ACTIONS`와 같음을 확인한다(언어 간 계약).
- 같은 속성 `and`(`number >= 2 and number == 3`)는 `parse_rule_text`가 `None`을 돌려줌을 확인한다(클라이언트/서버 검증이 필요한 이유를 문서화).

### 8.2 세션 단위: `tests/unit/test_human_game_puzzle.py`

- 퍼즐 모드 초기화: 라이프 3, 10턴, `settings_snapshot()["signal_mode"] == "per_turn_puzzle"`, `history_mode == "outcome"`; `total_turns=11`은 `ValueError`; 알 수 없는 모드는 `ValueError`.
- `get_turn_state().puzzle`: `shape`가 사다리 spec과 일치(턴 6은 절 3, 그중 `and` 1), `shape_block`/`rule_template_hint`가 `render_shape_block`/`render_shape_hint`와 같음, `clues`가 `generate_puzzle(puzzle_rng(seed, turn), spec)`의 힌트와 같음, `query.text == "... with number N"`, 뷰에 `hidden_rule`이 없음.
- `submit_action(correct, probe_answer=hidden_rule)`: `TurnResult.task_metadata`에 §5.5의 키 전부, `rule_match_score == 100.0`, `rule_shape_match is True`, `rule_parse_failed is False`, `task_success_factor == 1.0`, `reward_received == 10.0`, `ProbeResult.score == 100.0`.
- 오답 3회 → `lives_after == [2, 1, 0]`, `eliminated`, 점수 0. 정답 10회 → 100점, 완주.
- FORFEIT: 라이프 유지, `ground_truth_rule`이 그 턴의 퍼즐 규칙, `task_metadata == {}`.
- 이력 블록: 2턴째 `observation`이 `"=== Previous Rounds ==="`로 시작하고 `true_baseline`은 `attempts`, `threat_l2`는 `lives`.
- `validate_rule_text`: 빈 문자열, 파싱 실패, 모양 불일치 각각 메시지; 정답 규칙은 `None`.
- 순차 모드 무변경: 기존 `test_human_game*.py`가 그대로 통과한다.

### 8.3 API 계약: `tests/unit/test_api_web_arena_puzzle.py` + `tests/characterization/test_api_contract.py`

- `signal_mode: per_turn_puzzle` new_game → state에 `puzzle` 있음, `signal_mode` 에코, 응답 JSON 어디에도 `hidden_rule` 문자열이 없음.
- 기본값: 요청에 `total_turns`/`lives_total`을 빼면 `lives_total == 3`, 명시하면 존중. `total_turns: 11` → 400. `signal_mode: bogus` → 400. `lives_enabled: false` + 퍼즐 → 400.
- action: `probe_answer` 빈 값 / 파싱 실패 / 모양 불일치 → 400. 정답 규칙 + 정답 행동으로 10턴 완주 → result `final_score == 100`. `save=true` → 파일이 생기고 `load_seasons`로 읽힌 `SeasonResult.turns[i].task_metadata["rule_shape"]`가 state의 `shape`와 일치.
- 순차 모드 요청(기존 `_new_game` 헬퍼)은 `signal_mode == "sequential"`, `puzzle is None`.
- `STATE_KEYS`에 `signal_mode`, `puzzle` 추가. OpenAPI 스냅샷 재생성(파일 삭제 후 두 번 실행).

### 8.4 사람/LLM 패리티: `tests/characterization/test_web_puzzle_parity.py`

`configs/experiment/signal_puzzle_smoke.yaml`의 첫 시즌(Cell 0)만 남긴 config로 `ExperimentRunner`를 `StubProvider`(정답을 재생성해 답함)로 돌리고, 기록된 `SeasonResult.seed`로 `HumanGameSession(signal_mode="per_turn_puzzle", seed=<that seed>, framing="true_baseline", forfeit_condition="not_allowed")`를 정답으로 10턴 플레이한다. 턴마다 두 쪽의 `task_metadata["hidden_rule"]`, `["clues"]`, `["query_signal"]`, `["rule_shape"]`가 같고, 사람 쪽 `observation`이 LLM task call 본문의 퍼즐 관찰 텍스트를 포함함을 확인한다. `StubProvider`는 `tests.integration.conftest`에서 import한다(`tests`는 패키지).

## 9. 알려진 한계

- **DB에는 `task_metadata`가 없다.** Render의 디스크는 임시라 `outputs/api_sessions/season_results.jsonl`은 재배포 때 사라진다. 배포 환경에서 사람 퍼즐 데이터를 분석하려면 `turns` 테이블에 `task_metadata` JSON TEXT 열을 추가하는 후속(기존 `settings` 열과 같은 패턴, SQLite/Postgres 양쪽)이 필요하다. 이번 범위에서는 로컬 백엔드(`outputs/api_sessions/`)가 분석 경로다.
- 로그 탐색기의 턴 트레이스는 순차 모드의 "You see a ..." 관찰을 파싱해 카드를 그린다. 퍼즐 턴은 파싱이 실패해 관찰 원문 상자로 떨어진다(정보는 다 보이지만 카드/폼 렌더는 없다).
- 사람 쪽 `ri_task`는 지금처럼 자유 텍스트 reasoning의 토큰 수다. LLM의 `thinking_tokens`와 같은 의미가 아니다(기존 한계).
- 캠페인 재개 체크포인트는 게임 경계에서만 저장된다. 퍼즐 게임 도중 새로고침하면 그 게임의 진행은 사라진다(기존 동작).
- `get_turn_state`가 폴링될 때 `prepare`가 다시 불린다. 퍼즐은 결정적이라 결과는 같지만 `_turn_start_time`은 리셋된다(기존 동작과 동일).
- BYOE LLM arena(`/api/arena/run`)는 퍼즐 모드를 모른다.

## 10. 내가 대신 내린 결정

1. **채점 경로**: 프롬프트는 "서버는 `SignalGameModule.score`로 채점"이라 했지만 현재 `HumanGameSession.submit_action`은 `apply_action`(레거시)을 쓴다. 퍼즐 모드만 `prepare` → `score`로 바꾸고 순차 모드는 `apply_action`을 유지한다. 두 모드가 같은 보상/라이프 코드를 공유한다.
2. **RULE 전송 필드**: 새 요청 필드 대신 기존 `probe_answer`에 RULE 한 줄을 담는다(순차 모드도 규칙 추측을 이 필드로 보내며, `ProbeResult.response`에 그대로 기록된다).
3. **서버 검증은 400**: 빈 RULE, 파싱 실패, 모양 불일치를 400으로 거절한다. LLM은 같은 상황을 `rule_parse_failed`로 기록만 하지만, 사람 쪽은 폼이 문자열을 만들므로 실패는 클라이언트 버그이거나 임의 요청이다.
4. **플레이 중 정보 노출 없음**: `ActionResponse`에 `rule_match_score` / 정답을 추가하지 않는다. LLM도 정오만 받는다(`feedback.j2`).
5. **퍼즐 뷰 접근자**: 힌트 문자열을 되파싱하는 대신 `SignalGameModule.current_puzzle` 읽기 전용 프로퍼티 5줄을 추가한다(module.py는 동시 작업 대상이 아니다).
6. **기본값의 위치**: `total_turns=10`, `lives_total=3`은 `NewGameRequest` 기본값을 바꾸지 않고 라우트에서 `model_fields_set`으로 "명시되지 않았을 때만" 적용한다. 순차 모드 기본값(10턴, 5라이프)은 그대로다. `lives_enabled: false` + 퍼즐은 거절한다.
7. **seed 짝짓기**: 사람 seed에 덧셈을 하지 않는다. LLM 반복 r의 효과 seed(`config seed + r`)를 그대로 보내는 것이 짝짓기 규칙이며 패리티 테스트가 이를 고정한다.
8. **이력 블록**: 퍼즐 모드는 `format_outcome_history_block`(LLM 퍼즐 config의 `history_mode: outcome`)을 쓰고 `attempts/lives` 라벨은 `threat_level`이 참일 때만 `lives`다. 순차 모드의 누적 이력은 그대로다.
9. **난이도**: 퍼즐 모드는 난이도 카드를 숨기고 `"medium"`(LLM 퍼즐 config와 동일)을 보낸다. 서버는 값을 기록만 한다.
10. **캠페인/리더보드**: 모드는 캠페인 단위, 리더보드는 모드를 섞는다(점수 척도가 같다). 모드별 보드는 만들지 않는다.
11. **영속화**: DB 스키마는 손대지 않고 JSONL(`save=true`)이 분석 경로다. 배포 환경의 한계는 §9에 적었다.
12. **체크포인트 버전**: `v: 5`를 유지하고 `signalMode` 필드를 추가한다. 없으면 `"sequential"`.
13. **패리티 테스트 위치**: `tests/characterization/`에 두되 `StubProvider`는 `tests.integration.conftest`에서 import한다(픽스처 `patch_runner_provider`는 integration 디렉터리 전용이라 `monkeypatch`로 같은 패치를 직접 건다).
14. **`test_signal_puzzle_e2e.py`, `loaders.py`, `CLAUDE.md`, 논문은 건드리지 않는다**(동시 작업 중). CLAUDE.md의 Web Arena 설명 갱신은 그 작업이 끝난 뒤 한 줄 추가로 남긴다(계획 Task 6 참고).
