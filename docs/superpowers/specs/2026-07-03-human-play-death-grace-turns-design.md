# 사람 플레이: 4턴부터 죽음 적용 (안전 구간) — 설계

- 날짜: 2026-07-03
- 브랜치: `feat/human-play-10turns-death-impl`
- 대상: 웹 아레나 사람 플레이(`HumanGameSession`)만. LLM 경로 불변.

## 배경

현재 웹 아레나의 사람 플레이는 `interface/api.py`가 `HumanGameSession`을
`actual_death=True`, `total_turns=10`, `p_death_constant=0.15`로 생성한다.
그 결과 **1턴부터** 매 턴 `p_death=0.15`로 죽음 주사위를 굴린다
(`interface/human_game.py:408-414`). 초반부터 죽어 게임이 조기 종료되면
학습·점수 누적 구간이 사라진다.

LLM 경로는 `interface/arena.py`가 `actual_death=False`로 세션을 만들고,
실험 파이프라인은 별도의 `GameEngine.run_season()`을 쓰므로 이 문서의 변경과
완전히 분리되어 있다.

## 목표

사람 플레이에서 죽음 판정을 **4턴부터** 적용한다(1-indexed). 1·2·3턴은
"안전 구간"으로 죽음 주사위를 굴리지 않는다. **사람 플레이에서만.** LLM 코드는
수정하지 않는다.

## 설계 결정 (확정)

### D1. 안전 구간 동작 — "주사위만 스킵"
1~3턴에는 **죽음 주사위만** 건너뛴다. 다음은 **그대로 유지**한다:

- **보상 계산**: `calculate_reward` / `preview_continue_reward`에 넘기는
  `turn_p_death`는 실제 `p_death`(0.15)를 그대로 사용한다. → 초반 보상이 현재와
  동일하고, LLM 경로와의 equal-EV 보상 패리티가 유지된다.
- **UI 표시값**: `get_turn_state()`가 반환하는 `TurnState.p_death`도 실제
  0.15를 그대로 노출한다. 즉 1~3턴은 "15%로 표시되지만 실제로는 죽지 않는"
  안전 구간이다.

대안(안전 구간에 p_death를 0으로 표시/보상까지 0 처리)은 초반 보상을 왜곡하고
패리티를 깨므로 채택하지 않는다.

### D2. 설정 가능성 — 생성자 파라미터 (기본 4)
`HumanGameSession.__init__`에 `death_start_turn: int = 4`를 추가하고,
죽음 판정을 `turn_num >= self._death_start_turn`으로 게이트한다. `api.py`는
기본값(4)을 그대로 쓰므로 `NewGameRequest` 등 API 요청 표면은 변하지 않는다.

## 변경 범위

### 파일 1개: `interface/human_game.py`

**(a) 생성자 파라미터 추가**

```python
def __init__(self, ..., death_start_turn: int = 4, ...):
    ...
    self._death_start_turn = death_start_turn
```

`total_turns`/`actual_death` 등 기존 인자 근처에 배치한다.

**(b) 죽음 판정 게이트 (현재 408-414행)**

```python
# Death check (skipped in Phantom Death mode, and during the early
# grace turns before death_start_turn).
is_dead = False
if self._actual_death and turn_num >= self._death_start_turn:
    is_dead = self._survival.apply_death_check(p_death, self._rng)
    if is_dead:
        self._is_alive = False
        self._cumulative_score = 0.0
```

`turn_num = self._current_turn + 1`은 1-indexed이므로 `>= 4`는 곧
"1·2·3턴 면역, 4턴부터 판정"이다.

### 명시적으로 바꾸지 않는 것

- `interface/api.py` — 요청 모델/기본값 변경 없음(세션은 기본 `death_start_turn=4`).
- `src/squid_game/core/survival.py` — LLM과 공유되므로 절대 수정하지 않음.
- 보상 로직, `TurnState.p_death` 표시값 — D1에 따라 불변.
- LLM 경로(`arena.py`, `GameEngine`) — 불변.

## 테스트 (`tests/unit/test_human_game.py`)

`p_death_constant=1.0`(무조건 죽는 값)으로 세션을 만들어 게이트를 직접 검증한다.

- **T1. 안전 구간 면역**: 1·2·3턴에서 최적 행동 제출 시 `is_dead=False`,
  `is_game_over` 아님, 게임 계속.
- **T2. 4턴부터 죽음**: 1~3턴 통과 후 4턴 제출 시 `is_dead=True`,
  `game_over_reason="eliminated"`, 점수 0으로 리셋.
- **T3. 보상 패리티**: 안전 구간(예: 2턴) 최적 행동 보상이 게이트 도입 전과
  동일한 값(실제 p_death 기반 equal-EV)인지 확인.
- **T4. 기본값**: `death_start_turn` 미지정 시 기본 4가 적용되는지 확인.

## 리스크 / 비고

- `p_death_constant`(로짓 스케줄이 아닌 상수 경로)를 쓰므로 게이트는 상수
  0.15와 무관하게 턴 번호만으로 동작한다. 향후 스케줄 경로로 바꿔도 게이트는
  그대로 유효하다.
- 세션 재시작·resume 로직은 이 변경과 무관(턴 카운터 `_current_turn` 사용).
