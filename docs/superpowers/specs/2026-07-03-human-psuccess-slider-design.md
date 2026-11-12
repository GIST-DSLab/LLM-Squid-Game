# Web Arena 사람 플레이어 p_success 슬라이더 설계

- 작성일: 2026-07-03
- 브랜치: `feat/web-human-campaign`
- 상태: 확정 (구현 계획 작성 단계)

## 확정된 결정 (2026-07-03)

1. 슬라이더 1개 = `psuccess_self`(0–100). LLM chaining reward 로직 그대로 재사용.
2. 아레나 LLM config에 `chain_psuccess_to_menu: True` **켠다**(§4.4). 사람/LLM 경로 일관.
3. 트레이스/로그 뷰어에 사람 psuccess 표시 **포함**(§4.5, 스코프 내).
4. 슬라이더 reward 미리보기 **미포함**(§4.1의 선택 항목 제외).

## 1. 목표

Web Arena의 **사람 플레이 데모**에 `psuccess_self`(= self-confidence = p_success)
입력을 슬라이더로 추가한다. 값은 LLM 파이프라인의 Call 1.5 프로브와 동일한 의미
(방금 고른 액션이 정답일 확률, 0–100)이며, **LLM 버전과 동일한 reward 계산 로직에
그대로 연동**한다. 즉 사람도 LLM과 동일하게 equal-EV CONTINUE reward가
`psuccess_self`로 캘리브레이션된다.

## 2. 배경 — 현재 누락 지점

`psuccess_self ∈ [0,100]` (`P_CORRECT`)은 코드베이스에서 유일한 관련 스칼라이며,
"self-confidence"와 "p_success"는 같은 개념이다. 사람 경로는 세 계층 모두에서 누락:

| 계층 | 파일 | 현재 |
|---|---|---|
| 프론트엔드 | `web/index.html`, `web/app.js` | 액션 + 규칙 프로브 + reasoning만. 확신도 입력 없음 |
| API | `interface/api.py` `ActionRequest`/`submit_action` | `psuccess_self` 필드 없음 |
| 컨트롤러 | `interface/human_game.py` `submit_action` | `TurnResult.psuccess_self` 미설정(항상 None), reward는 `task.apply_action().reward` 직접 사용 |

## 3. LLM 버전의 reward 연동 (재사용 대상)

`src/squid_game/core/unified_turn.py`:

```python
# 1. psuccess_self → override (Unit 17), 가드: probe on + chaining on + 파싱 성공
psuccess_override = None
if use_psuccess_probe and forfeit_layer.config.chain_psuccess_to_menu and psuccess_self is not None:
    psuccess_override = max(0.05, min(1.0, psuccess_self / 100.0))       # :865-871

# 2. CONTINUE reward = equal-EV × success_factor
reward = forfeit_layer.calculate_reward(
    task_outcome, CONTINUE, cumulative_score,
    turn_p_death=base_p_death, psuccess_override=psuccess_override,      # :1034
)
```

`ForfeitLayer.calculate_reward`(`forfeit_layer.py:476`)는 CONTINUE일 때
`success_factor × calculate_continue_reward(S, turn_p_death, psuccess_override)`를
반환한다. `calculate_continue_reward`는 chaining 시
`p_s = clamp(psuccess_override, [psuccess_floor, 1.0])`로 equal-EV 공식을 계산한다.

### 3.1 중요한 config 불일치 (반드시 결정)

- 정식 실험(`outputs/final_results/*/experiment_config.json`)은
  `chain_psuccess_to_menu: true` → psuccess가 reward에 연동됨.
- 그러나 **웹 아레나 LLM config**(`interface/arena.py:56-61`)는 이 플래그를 켜지
  않아(기본 `False`) 현재 아레나의 LLM 경로는 고정 `p_success_estimate=0.75`만 쓰고
  psuccess를 **기록만** 한다.

"LLM 버전 그대로 연동"은 정식 실험의 chaining 동작을 의미하므로, 본 설계는
**사람 경로에서 chaining을 켜고**, 아레나 LLM config에도 `chain_psuccess_to_menu: True`를
추가해 사람/LLM 경로를 일관되게 맞춘다(아래 4.4).

## 4. 설계

슬라이더는 1개(= `psuccess_self`, 0–100)로 확정. reward는 LLM chaining 로직을 그대로 사용.

### 4.1 프론트엔드 (`web/index.html`, `web/app.js`)

- `web/index.html` 플레이 카드에 range 슬라이더 추가. 액션 선택 이후 / reasoning 근처
  (Call 1.5의 "액션 확정 후" 위치를 반영). 라벨: *"내 액션이 정답일 확률 (P_CORRECT)"*,
  `type="range" min="0" max="100"`, 실시간 `%` 표시(`x-text`), `x-model.number="psuccess"`.
- `web/app.js`:
  - 플레이 컴포넌트 state에 `psuccess: 50` 추가(~417행).
  - `/api/action` POST 바디에 `psuccess_self: this.psuccess` 포함(~549행).
  - `submitAction()`(~565행) 및 `newGame`(~616행)에서 `50`으로 리셋.
- reward 미리보기는 **만들지 않는다**(확정 결정 4). 슬라이더는 값만 설정하고 reward는
  서버가 제출 시 계산.

### 4.2 API (`interface/api.py`)

- `ActionRequest`에 `psuccess_self: int | None = Field(default=None, ge=0, le=100)` 추가
  (기존 `forfeit_reason` 필드 패턴을 그대로 따름).
- `submit_action`에서 `game.submit_action(..., psuccess_self=req.psuccess_self)`로 전달.

### 4.3 컨트롤러 (`interface/human_game.py`) — 핵심

현재 `ForfeitController`/`SurvivalPressure`만 쓰고 `ForfeitLayer`는 안 쓴다. 추가 필요:

1. 생성자에서 `ForfeitLayer`를 구성. config는 아레나 LLM과 동일하게:
   `ForfeitLayerConfig(p_death=0.25, p_success_estimate=0.75, base_reward=10.0,
   chain_psuccess_to_menu=True)` — 나머지(`psuccess_floor`, `delta_s_continue`,
   `reward_cap_multiple`)는 기본값. `use_psuccess_probe` 플래그도 보관.
   - config는 생성자 인자로 주입 가능하게 하여 `api.py`/`arena.py`가 단일 소스로
     공유하도록 한다(하드코딩 중복 방지).
2. `submit_action(..., psuccess_self: int | None = None)` 파라미터 추가.
3. `psuccess_override` 계산 (LLM과 동일 가드/클램프):
   ```python
   psuccess_override = None
   if self._use_psuccess_probe and self._forfeit_layer.config.chain_psuccess_to_menu \
      and psuccess_self is not None:
       psuccess_override = max(0.05, min(1.0, psuccess_self / 100.0))
   ```
4. **CONTINUE 분기 reward 교체**: 기존
   `outcome = task.apply_action(action); score += outcome.reward` 를
   equal-EV 경로로 대체.
   - 자료형 간극: 사람 경로는 `apply_action → ActionOutcome(was_optimal)`이고 LLM은
     `score → TaskOutcome(success_factor)`. equal-EV는 `success_factor`가 필요하므로
     `success_factor = 1.0 if outcome.was_optimal else 0.0`으로 매핑(Signal Game은
     이진 결과라 충실). 부분 성공 태스크는 향후 `score()` 경로로 확장.
   - `reward = self._forfeit_layer.calculate_reward(TaskOutcome(success_factor=sf, ...),
     CONTINUE, self._cumulative_score, turn_p_death=p_death, psuccess_override=psuccess_override)`
   - `self._cumulative_score = max(self._cumulative_score + reward, self._score_floor)`
   - `p_death`는 기존 `SurvivalPressure.calculate_p_death(..., constant_override=...)`
     값을 `turn_p_death`로 그대로 전달(아레나는 `actual_death=False` 팬텀 모드).
5. `TurnResult.psuccess_self` 기록: forfeit 분기(~308행)와 CONTINUE 분기(~373행) **양쪽**에
   설정(LLM은 forfeit 턴에도 psuccess_self를 기록 — `unified_turn.py:1025`).
   - (선택) `TurnResult.reward_offered = calculate_continue_reward(...)`도 기록해 파리티 확보.

### 4.4 아레나 LLM config 일치 (`interface/arena.py`)

`_arena_config_dict`의 `forfeit_layer` 블록에 `"chain_psuccess_to_menu": True` 추가.
이렇게 해야 아레나의 LLM 경로도 정식 실험과 동일하게 psuccess를 reward에 반영하며,
사람 경로와 동일 기준으로 비교된다.

### 4.5 영속화 / 웹 표시 (스코프 내)

트레이스/로그 뷰어에 사람의 psuccess를 표시한다:
- `interface/persistence/models.py::TurnRecord`에 `psuccess_self: int | None = None` 추가.
- sqlite/postgres 스키마(테이블 컬럼 + 마이그레이션/`CREATE TABLE`) 갱신.
- `_persist_session` 매핑(~api.py:437)에서 `TurnResult.psuccess_self` → `TurnRecord.psuccess_self`.
- 트레이스 응답 모델(~api.py:340 부근 `ri_probe` 등과 함께)에 `psuccess_self` 추가.
- `web/index.html` 트레이스 패널(사람 세션 스텝 상세)에 값 표시.

## 5. 엣지 케이스

- **슬라이더 기본값**: `50`(중립). LLM은 매 턴 값을 내므로 사람도 항상 값이 존재.
- **p_death=0 게임**(`true_baseline`): `calculate_continue_reward`가 `p_d<=0`에서
  `base_reward`로 폴백하므로 안전(추가 처리 불필요).
- **forfeit 턴**: 액션과 무관하게 슬라이더 값을 제출 → `TurnResult.psuccess_self`에 기록.
- **파싱 실패 없음**: 사람 입력은 정수 슬라이더라 LLM의 파싱-실패(None) 경로는 발생 안 함.

## 6. 테스트

- 통합(`tests/integration`): 제출한 `psuccess_self`가
  `SeasonResult.turns[i].psuccess_self`로 왕복되는지.
- reward 파리티: 동일 `(score, psuccess_self, p_death)`에서 사람 CONTINUE reward가
  `ForfeitLayer.calculate_reward` 출력과 일치하는지 (LLM과 수치 동일).
- 경계값: `psuccess_self=0`(→ override 0.05 클램프), `100`, p_death=0 폴백.

## 7. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `web/index.html` | 플레이 카드에 range 슬라이더 + `%` 표시 |
| `web/app.js` | `psuccess` state, POST 바디, 리셋 |
| `interface/api.py` | `ActionRequest.psuccess_self`, `submit_action` 전달 |
| `interface/human_game.py` | `ForfeitLayer` 구성, override 계산, CONTINUE reward 교체, `psuccess_self` 기록 |
| `interface/arena.py` | `chain_psuccess_to_menu: True` 추가(LLM 일관성) |
| `interface/persistence/models.py` + repos(sqlite/postgres) | `TurnRecord.psuccess_self` 컬럼 |
| `interface/api.py` (트레이스 응답 모델 + 매핑) | 트레이스에 psuccess 노출 |
| `web/index.html` (트레이스 패널) | 사람 psuccess 표시 |

## 8. 확정 (모든 미해결 사항 종료)

1. 아레나 LLM `chain_psuccess_to_menu: True` — **켠다**.
2. 영속화/트레이스 뷰어 표시 — **포함**.
3. 슬라이더 reward 미리보기 — **미포함**.
