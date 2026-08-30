# Web Arena 캠페인 히든 룰 속성 로테이션 — 설계 스펙

> 작성일: 2026-08-10 · 대상: `interface/`, `web/app.js`, `src/squid_game/tasks/signal_game/module.py`
> 관련 스펙: `docs/superpowers/specs/2026-07-05-human-play-difficulty-and-db-tag-design.md` (캠페인 단위 난이도 선택)

## 배경

Web Arena의 사람 플레이(`PLAY` 탭)는 한 번 시작하면 6게임 캠페인을 연속으로 진행한다. 6게임은 `web/app.js`의 `CAMPAIGN_CONDITIONS`(`web/app.js:193-200`)에 따라 framing × forfeit 조건만 바뀌고, 게임마다 서버가 새 랜덤 seed를 부여한다(`interface/api.py:789`).

문제는 히든 룰의 **속성 계열이 6게임 내내 고정**된다는 점이다.

- `SignalGameModule.initialize()`가 `_active_rule_index = 0`으로 하드코딩되어 있고(`module.py:203`, 재설정 경로인 `module.py:224`도 동일), 저장소 전체에서 이 필드에 다른 값을 대입하는 코드가 없다.
- `generate_rules()`가 돌려주는 후보 리스트는 순서가 고정이다. EASY/MEDIUM은 `[color 룰, shape 룰, number 룰]`(`rules.py:182-201`), HARD는 `[color+shape, color+number, shape+number]`(`rules.py:217-251`), EXPERT는 HARD 결과를 history override로 감싼 것(`rules.py:254-268`)이라 순서가 같다.
- 따라서 인덱스 0은 언제나 color가 관여하는 룰이다. seed는 어떤 color 값인지(red/blue/green/yellow)와 액션 배정만 바꾼다.

결과적으로 Easy 난이도 캠페인은 6판 모두 "색이 X면 …" 형태이고, Normal(hard)은 6판 모두 "색 AND 모양" 형태다. 첫 판에서 속성 계열을 알아낸 플레이어는 나머지 다섯 판에서 탐색 부담이 사라지므로, 조건(framing × forfeit) 간 점수 차이에 **학습 전이라는 교란 변수**가 섞인다.

### 다행인 점

룰 생성 이후의 하위 시스템이 이미 속성에 무관하게 일반화되어 있다. few-shot 예시 구성(`module.py:316-362`, `module.py:364-417`), 커리큘럼 신호 생성(`module.py:1015-1099`), probe 채점(`module.py:739-985`)이 전부 룰 `description` 문자열을 정규식으로 다시 파싱해 속성명을 복구하고, 속성값 테이블은 `_ATTR_VALUES` 딕셔너리로 조회한다. 즉 **활성 룰 인덱스만 게임마다 다르게 주면 나머지 파이프라인은 수정 없이 동작한다.**

이 설계의 대가는 룰 description 문자열 포맷(`"If {attr} is {val} then {action}, otherwise {default}."`)이 사실상 공개 API라는 것이다. 이번 변경은 그 포맷을 건드리지 않는다.

## 목표

1. 한 캠페인의 6게임이 서로 다른 히든 룰 속성 계열을 갖게 한다.
2. 배분을 균형 있게 한다 — 계열 3종이 각각 정확히 2회, 연속으로 같은 계열이 나오지 않게.
3. 같은 `campaign_id`면 항상 같은 스케줄이 나오게 한다(새로고침·resume 체크포인트 복원 시 재현).
4. LLM 실험 경로의 동작을 **한 바이트도 바꾸지 않는다**.

## Non-Goals

- **플레이어에게 알리지 않는다.** 사전 안내 문구도, 게임 종료 리포트의 정답 룰 공개도 하지 않는다. UI는 현행 그대로 유지한다(사용자 결정, 2026-08-10).
- **LLM 실험 경로 배선 제외.** `core/engine.py:164`는 `rule_index`를 넘기지 않으며 기본값이 현행 동작이므로 2026-04-22 canonical run과의 재현성이 보존된다. LLM 경로의 속성 편향은 아래 "알려진 제한"에 기록만 하고 별도 과제로 남긴다.
- **속성 풀 확장 제외.** 단일 속성 3종과 2속성 조합 3종을 한 캠페인에 섞지 않는다. 난이도 경계(Easy = 단일 속성, Normal = 2속성)를 그대로 유지한다.
- **난이도 캠페인 중간 변경 제외.** 난이도는 기존대로 캠페인 단위 고정이다.

## 결정 사항 (사용자 승인)

| 결정 | 선택 |
|---|---|
| 6게임 속성 배분 | **균형 2회씩 + 연속 중복 금지** (`[0,1,2]` 셔플 블록 2개 이어붙임) |
| 스케줄 결정 주체 | **서버가 `campaign_id`에서 파생** (순수 함수, 서버 상태 없음) |
| 변경 범위 | **Web Arena 사람 플레이만** (LLM 경로 기본값 = 현행 동작) |
| 플레이어 노출 | **없음** (사전 안내·사후 공개 모두 안 함, UI 무변경) |

---

## 아키텍처

새 순수 함수 모듈 하나와 기존 3개 지점의 파라미터 배선으로 구성한다.

```
web/app.js  startGame()
     │  campaign_id + campaign_index
     ▼
POST /api/new_game  (interface/api.py)
     │  rule_index_for(campaign_id, campaign_index, fallback_seed)
     ▼
interface/rule_schedule.py   ← 신규, 순수 함수, 단독 테스트 가능
     │  rule_index: int
     ▼
HumanGameSession(rule_index=N)     (interface/human_game.py)
     │
     ▼
SignalGameModule.initialize(rule_index=N)
     │
     ▼
_active_rule_index = N
```

스케줄 계산을 API 핸들러와 게임 세션 양쪽에서 분리해 별도 모듈에 두는 이유는, 배분 정책(균형·중복 회피·재현성)이 테스트하기 가장 까다로운 부분이면서 HTTP나 게임 상태와 아무 의존이 없기 때문이다.

### 컴포넌트 1 — `interface/rule_schedule.py` (신규)

```python
RULE_FAMILY_COUNT = 3          # generate_rules()가 모든 난이도에서 3개를 반환
CAMPAIGN_GAME_COUNT = 6        # web/app.js의 CAMPAIGN_CONDITIONS 길이와 일치

def campaign_rule_schedule(campaign_id: str) -> list[int]:
    """캠페인 6게임의 활성 룰 인덱스 스케줄. 길이 6, 각 계열 정확히 2회."""

def rule_index_for(
    campaign_id: str | None,
    campaign_index: int,
    fallback_seed: int,
) -> int:
    """이번 게임에 쓸 활성 룰 인덱스."""
```

**의존:** 표준 라이브러리(`hashlib`, `random`)뿐. squid_game 패키지 import 없음.

### 컴포넌트 2 — `SignalGameModule.initialize()` 확장

`rule_index: int | None = None` 키워드를 받는다. `None`이면 `0`을 써서 현행 동작을 유지한다. 값이 있으면 `rule_index % len(self._rules)`로 정규화해 대입한다. `reset()`은 `initialize()`에서 받은 값을 보존한다 — `_num_few_shot` / `_curriculum_turns`와 같은 성격의 세션 설정이지 시즌 상태가 아니기 때문이다(`module.py:210-227`의 기존 주석 참조).

### 컴포넌트 3 — `HumanGameSession` 통과 배선

`__init__`에 `rule_index: int | None = None`을 추가하고 `self._task.initialize(...)` 호출(`human_game.py:164`)에 그대로 전달한다. 세션 자체는 이 값으로 아무 판단도 하지 않는다.

### 컴포넌트 4 — API 요청 필드

`NewGameRequest`에 필드 하나를 추가한다.

```python
campaign_index: int = Field(
    default=0, ge=0,
    description="0-based 캠페인 내 게임 순번. 캠페인 없는 일회성 게임은 무시된다.",
)
```

기본값 0이라 이 필드를 안 보내는 기존 클라이언트(테스트 포함)는 동작이 바뀌지 않는다.

`new_game()` 핸들러는 seed를 정한 직후(`api.py:789` 다음) 룰 인덱스를 계산해 `HumanGameSession`에 넘긴다. `campaign_id`는 이미 `sanitize_campaign_id()`로 정규화된 값(`api.py:814`)을 쓴다 — 정규화 전후 값이 다르면 스케줄이 갈라지므로 **반드시 정규화된 값 기준으로 계산한다.**

### 컴포넌트 5 — 클라이언트

`web/app.js`의 `startGame()` POST 바디(`web/app.js:959-975`)에 `campaign_index: this.campaignIndex` 한 줄을 추가한다. `campaignIndex`는 이미 캠페인 진행·체크포인트 복원에서 관리되는 상태라 새 상태를 만들지 않는다. UI 마크업과 문구는 변경하지 않는다.

`startGame()` 호출 시점에 `campaignIndex`가 **시작하려는 게임의 0-based 순번**과 일치하는지가 이 배선의 유일한 전제인데, 두 진입 경로 모두 성립한다. `advanceCampaign()`은 `campaignIndex += 1` 직후에 호출하고(`web/app.js:1228-1234`), `resumeCampaign()`은 체크포인트의 `campaignIndex`(= 저장 시점의 `campaignResults.length`, 즉 아직 끝나지 않은 게임의 순번)를 복원한 뒤 호출한다(`web/app.js:1236-1250`).

부수 효과로, 게임 도중 새로고침 후 resume하면 seed는 새로 뽑히지만(`api.py:789`) 룰 계열은 같은 인덱스라 유지된다. 중단 지점에서 속성이 갑자기 바뀌지 않는다.

---

## 스케줄 알고리즘

```
seed_int = int.from_bytes(sha256(campaign_id.encode("utf-8")).digest()[:8], "big")
rng = random.Random(seed_int)

block_a = rng.sample([0, 1, 2], 3)
block_b = rng.sample([0, 1, 2], 3)
재추첨: block_b[0] == block_a[-1] 인 동안 rng.sample 재호출, 최대 10회
        10회 후에도 같으면 block_b를 왼쪽으로 1칸 회전 (결정적 탈출)
schedule = block_a + block_b        # 길이 6
```

**성질:**
- 각 인덱스가 정확히 2회 등장한다.
- 인접한 두 게임의 인덱스가 절대 같지 않다(블록 내부는 `sample`이라 자명하고, 경계는 재추첨/회전이 보장한다).
- 같은 `campaign_id` → 항상 같은 스케줄.

**`hash()`를 쓰지 않는 이유:** Python 내장 `hash()`는 문자열에 대해 `PYTHONHASHSEED` 기반으로 프로세스마다 다른 값을 낸다. 서버가 재시작되면 같은 `campaign_id`가 다른 스케줄을 내고, resume 체크포인트로 캠페인 중간에 복귀한 플레이어가 이미 지나온 판과 다른 속성을 만나게 된다. `sha256`은 프로세스에 무관하게 안정적이다.

### 난이도별 인덱스 의미

룰 리스트 길이는 모든 난이도에서 3이므로 스케줄은 그대로 쓰이고, 인덱스가 가리키는 룰 형태만 달라진다.

| index | Easy (`easy`) | Normal (`hard`) | Hard (`expert`) |
|:-:|---|---|---|
| 0 | color | color + shape | color + shape + history override |
| 1 | shape | color + number | color + number + history override |
| 2 | number | shape + number | shape + number + history override |

Normal/Hard에서는 세 조합이 속성을 공유하므로("모두 다른 속성"이 아니라 "모두 다른 조합"), 완전한 계열 분리는 Easy에서만 성립한다. 그래도 6판 전부 동일 조합이던 현행보다는 탐색 부담이 유지된다.

---

## 에러 처리 / 엣지 케이스

| 상황 | 처리 |
|---|---|
| `campaign_id`가 `None`(일회성 게임, 정규화 결과 빈 문자열 포함) | `random.Random(fallback_seed).randrange(RULE_FAMILY_COUNT)` — 게임의 자체 seed로 인덱스를 뽑는다. 캠페인이 아니므로 균형 보장은 없지만 color 고정은 여기서도 사라진다. |
| `campaign_index >= 6` (클라이언트 버그, 캠페인 길이 변경) | `schedule[campaign_index % len(schedule)]` — 예외 대신 순환. |
| `campaign_index < 0` | Pydantic `ge=0`이 HTTP 422로 거부. |
| `rule_index >= len(self._rules)` | `module.py`에서 `% len(self._rules)`로 정규화. 룰 후보가 3개보다 적은 미래의 난이도에서도 IndexError가 나지 않는다. |
| `campaign_index` 미전송 (구버전 클라이언트, 기존 테스트) | 기본값 0 → 캠페인 첫 게임 인덱스. 예외 없음. |

---

## 테스트 전략

### 신규 유닛 — `tests/unit/test_rule_schedule.py`

1. **균형** — 임의의 campaign_id 여러 개에 대해 `campaign_rule_schedule()` 결과의 `Counter`가 `{0: 2, 1: 2, 2: 2}`.
2. **인접 중복 없음** — 모든 `i`에 대해 `schedule[i] != schedule[i+1]`.
3. **재현성** — 같은 campaign_id를 두 번 호출하면 같은 리스트. (같은 프로세스 내 호출이므로 `hash()` 회귀는 못 잡는다. sha256 사용은 코드 리뷰로 강제하고, 대신 알려진 campaign_id 하나에 대한 **하드코딩 기대값**을 골든 테스트로 둔다 — 해시 함수가 바뀌면 실패한다.)
4. **분산** — 서로 다른 campaign_id 30개의 첫 게임 인덱스에 0/1/2가 모두 등장한다.
5. **fallback 경로** — `campaign_id=None`일 때 `fallback_seed`가 다르면 인덱스가 갈리고, 같으면 같다.
6. **modulo 안전** — `campaign_index=7`이 예외 없이 `schedule[1]`을 돌려준다.

### 기존 유닛 확장 — `tests/unit/test_signal_game_v3.py`

7. **회귀 가드** — `initialize(difficulty=EASY, seed=42)`(rule_index 미지정)의 `get_active_rule_description()`이 `"if color is"`로 시작한다. LLM 경로 무변경을 코드로 못박는다.
8. **인덱스 반영** — 같은 seed로 `rule_index=1` → shape 룰, `rule_index=2` → number 룰.
9. **속성 무관 few-shot** — `rule_index=2`(number 룰)로 초기화한 뒤 `generate_few_shot_examples()`가 빈 리스트가 아니고, 반환된 각 `(signal, action)` 쌍의 action이 `rule.evaluate(signal)`과 일치한다. `_construct_easy_examples()`의 정규식 파싱이 color 외 속성에서도 성립함을 실증한다. HARD 난이도에서 `rule_index=2`(shape+number)로 같은 검사를 반복한다.
10. **`reset()` 보존** — `initialize(rule_index=2)` 후 `reset()`을 호출해도 활성 룰이 여전히 number 계열이다.

### 통합 — `tests/integration/` 또는 `tests/unit/test_api_web_arena.py`

11. **엔드투엔드 배분** — 같은 `campaign_id`로 `campaign_index` 0..5를 보내 6세션을 만들고, 각 세션의 활성 룰 description에서 속성 계열을 추출해 각 계열이 2회씩 등장하고 인접 중복이 없음을 확인한다. description은 서버 프로세스 안의 `HumanGameSession`을 직접 조회(`_task.get_active_rule_description()`)해 얻는다 — API가 정답 룰을 노출하지 않으므로(그리고 노출해서도 안 되므로) 응답 본문으로는 검증할 수 없다.
12. **하위 호환** — `campaign_index`를 뺀 `/api/new_game` 요청이 200을 반환한다.

---

## 알려진 제한

- **LLM 실험 경로는 여전히 color 고정이다.** `core/engine.py:164`가 `rule_index`를 넘기지 않으므로 모든 LLM 세션의 히든 룰은 EASY에서 color, HARD/EXPERT에서 color+shape이다. 이는 의도된 범위 제한(canonical run 재현성 보존)이며, 속성 편향이 모델 간 비교에 영향을 준다면 별도 과제로 다뤄야 한다. 그때는 config에 플래그를 노출하고 전체 재실행이 필요하다.
- **Normal/Hard 난이도는 계열이 아니라 조합만 달라진다.** 세 조합이 속성을 둘씩 공유하므로 "6판 모두 다른 속성"은 Easy에서만 성립한다.
- **캠페인당 6게임이라는 가정이 두 곳에 있다.** `web/app.js`의 `CAMPAIGN_CONDITIONS`(길이 6)와 `rule_schedule.CAMPAIGN_GAME_COUNT`. 캠페인 길이를 바꾸면 스케줄 길이도 함께 조정해야 한다(현재는 modulo로 크래시만 막는다).
- **플레이어는 속성 전환을 사전에 알 수 없다.** 이는 의도된 설계이지만, 이전 판의 가설을 계속 밀어붙이다 초반 턴을 낭비하는 플레이어가 생길 수 있다. 조건 간 비교는 6게임 모두 같은 규칙 아래 있으므로 편향되지 않는다.

## 구현 순서 (요약)

1. `interface/rule_schedule.py` 작성 + `tests/unit/test_rule_schedule.py` (테스트 우선).
2. `SignalGameModule.initialize()` / `reset()`에 `rule_index` 배선 + 회귀 가드 포함 유닛 테스트.
3. `HumanGameSession.__init__` 통과 배선.
4. `NewGameRequest.campaign_index` 추가 + `new_game()` 핸들러 계산 배선 + API 테스트.
5. `web/app.js` `startGame()` 페이로드 한 줄 추가.
6. 통합 테스트로 6게임 배분 확인.
