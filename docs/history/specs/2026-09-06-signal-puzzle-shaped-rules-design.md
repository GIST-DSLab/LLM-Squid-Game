# 설계 문서: Signal Game 턴별 퍼즐 v2 — 모양 공개 결정 목록 규칙 (shaped decision-list puzzle)

**날짜:** 2026-09-06
**상태:** 브레인스토밍 승인, 구현 계획 작성 전
**범위:** `signal_game` Task Module의 `signal_mode: per_turn_puzzle` 재설계. LLM 런 전용.
**브랜치:** `feat/signal-game-per-turn-puzzle` (워크트리 `.claude/worktrees/signal-game-per-turn-puzzle`), 기존 v1 구현(2026-09-05 스펙)을 **대체**한다.
**선행 스펙:** `docs/history/specs/2026-09-05-signal-game-per-turn-puzzle-design.md` (v1). v1의 §1 문제 정의와 §9 history, §11 호환 원칙은 그대로 유효하다.

## 1. 왜 v1을 바꾸나

v1은 "힌트와 일치하는 규칙 후보 수 `|H|`"를 난이도 지수로 삼고, 유일해를 "후보 전부가 query에 같은 답"으로 정의했다. 2026-09-06 검토에서 두 결함이 드러났다.

1. **`|H|`는 어려움이 아니다.** 후보가 몇 개 남든 답이 하나로 정해지면, 힌트를 전부 만족하는 규칙을 아무거나 잡은 에이전트는 반드시 맞춘다. 남은 후보 수는 "헷갈림의 양"일 뿐 오답으로 이어지지 않는다.
2. **난이도 축이 힌트 수 하나였다.** 보정 결과 family는 `|H|`를 움직이지 못했고(같은 힌트 수에서 family 순서가 의도와 역전), 사다리는 힌트를 12 → 3장으로 줄여서만 단조가 됐다.

답이 정해져 있는 문제에서 오답이 나오는 경우는 하나뿐이다: **힌트 전부를 만족하는 규칙을 찾지 못했을 때.** 그러므로 어려움은 "그 규칙을 찾아내는 수고"에서 와야 한다. v2는 규칙 자체를 복잡하게 하고, 규칙의 **모양**을 공개하되 내용은 숨기며, 규칙(함수)과 답이 모두 유일하게 정해지도록 힌트를 구성한다.

## 2. 목표 / 비목표

**목표**

- 매 턴 새 규칙. 세션 최대 10턴, 라이프 3.
- 규칙은 Python `if / elif / else` 결정 목록(decision list). 조건이 성립하는 **첫 절**이 행동을 정한다.
- 매 턴 규칙의 **모양**(절 수, 절마다 조건 1개인지 2개 AND인지)을 구멍 뚫린 Python 코드로 보여준다. 속성·값·행동은 구멍.
- 턴이 오를수록 절 수와 조건 복잡도가 오른다. 난이도는 YAML에서 턴별로 조절한다.
- **유일해:** 공개된 모양과 조건 문법 안에서 힌트 전부와 일치하는 규칙은 64장 카드 전체에 대해 함수가 하나다. 따라서 query의 답도 하나다.
- 모든 힌트가 필요하다(최소 힌트 집합). 선택적으로 잉여 힌트를 더한다.
- 뒤쪽 턴은 query가 두 절 이상의 조건을 동시에 만족하도록 골라 우선순위 적용을 요구한다.
- 시즌 seed와 턴 번호로 결정되는 생성(paired design 유지). 같은 seed의 다섯 셀은 같은 10문제를 받는다.

**비목표**

- Web Arena human play 반영 (후속).
- 미끼 규칙(단순 규칙이 힌트 대부분을 설명하게 하는 장치) — 후속 손잡이. v2 생성기는 이를 막지도 만들지도 않는다.
- v1의 `|H|` 밴드·family A–D·보정 스크립트 — **삭제**한다. 재현할 런이 없다.
- 순차 모드(`signal_mode: sequential`) 변경 없음.

## 3. 규칙 언어

### 3.1 신호와 행동

v1과 같다. 색 4 × 도형 4 × 숫자 4 = 64 카드, 행동 4개 `go_left, go_right, stay, jump`.

### 3.2 원자 조건 (20개)

| 종류 | 형태 | 개수 |
|---|---|:-:|
| 등식 | `color == "red"`, `shape == "star"`, `number == 3` | 12 |
| 범위 | `number >= 2`, `number >= 3`, `number >= 4`, `number <= 1`, `number <= 2`, `number <= 3` | 6 |
| 홀짝 | `number % 2 == 1`, `number % 2 == 0` | 2 |

항상 참이거나 항상 거짓인 조건(`number >= 1`, `number <= 4`)은 없다.

### 3.3 복합 조건 (112개)

서로 **다른 속성**의 원자 조건 두 개를 `and`로 묶은 것. (`color == "red" and number >= 3`). 같은 속성끼리는 묶지 않는다.

### 3.4 결정 목록

```python
if <cond_1>:
    action = <act_1>
elif <cond_2>:
    action = <act_2>
...
else:
    action = <act_else>
```

- 절 수 k ≥ 1. 각 절은 원자(arity 1) 또는 복합(arity 2).
- 의미론: 위에서부터 처음 성립하는 절의 행동. 어느 절도 성립하지 않으면 `else`.
- **모양(shape)** = `(k, (arity_1, …, arity_k))`. 모양은 공개, 나머지는 숨김.

### 3.5 정직성 제약 (생성기가 진짜 규칙에 강제)

- 각 절은 앞 절들이 잡지 않은 카드 중 최소 1장에서 성립한다(도달 가능).
- 각 절을 빼면 64장 답 벡터가 바뀐다(모든 절이 함수에 기여).
- 연속한 절의 행동은 서로 다르고, 마지막 절의 행동은 `else`와 다르다. (행동이 4개뿐이라 k ≥ 4에서는 반복이 불가피하다. "규칙 안의 행동은 모두 다르다"는 v1 문장은 시스템 프롬프트에서 빠진다.)
- 한 규칙 안에서 같은 조건은 두 번 쓰지 않는다.
- `else` 영역(어느 절도 성립하지 않는 카드)은 비어 있지 않다.

## 4. 유일해

### 4.1 정의

가설 공간 `Hyp(S)` = 모양 `S`의 모든 결정 목록 (각 절의 조건은 arity에 맞는 원자/복합 조건 전부, 행동은 4개 전부; 3.5의 정직성 제약은 **가설 쪽에는 적용하지 않는다**).

힌트 집합 `C`가 주어졌을 때 퍼즐은 다음일 때 채택된다:

> `Hyp(S)` 안에서 `C`의 모든 힌트와 일치하는 규칙의 64장 답 벡터가 전부 진짜 규칙의 벡터와 같다.

- 이는 "규칙(함수) 유일" ⇒ "query 답 유일"이다. query는 64장 중 하나이므로.
- 구문 수준 유일성은 요구하지 않는다. 함수가 같은 다른 표기(죽은 절, 다른 조건으로 같은 영역 표현)는 허용된다. 프롬프트가 요구하는 것은 답과 함수이지 표기가 아니다.
- 가설 공간은 그 턴의 생성 제약(`predicates: false` 등)이 아니라 **전체 조건 문법**이다. 시스템 프롬프트가 문법 전체를 알려주므로 에이전트의 가설 공간이 그것이기 때문이다.

### 4.2 판정 알고리즘 (`exists_differing`)

힌트 집합과 진짜 벡터가 주어졌을 때 "`Hyp(S)` 안에 힌트와 일치하면서 벡터가 다른 목록이 존재하는가"를 DFS로 판정한다. 절 위치 `pos`, 지금까지 절들이 덮은 카드 마스크 `covered`(64비트), 아직 어느 절에도 잡히지 않은 힌트 마스크 `remaining`, 지금까지 진짜와 달라졌는지 `differs`.

- 위치 `pos`에서 (a) 죽은 절(새 카드를 하나도 덮지 못함) 건너뛰기, (b) arity에 맞는 조건 `c` 중 `c & ~covered ≠ ∅`인 것마다: `c`가 잡는 남은 힌트의 라벨이 한 종류여야 하고, 행동은 그 라벨(없으면 4개 전부). `differs |= (c의 새 영역에 진짜 벡터 ≠ 행동인 카드 존재)`. 재귀.
- `pos == k`이면 `else`: 남은 힌트 라벨이 한 종류여야 하고 행동은 그 라벨(없으면 4개 전부). `differs |= (미덮음 영역에 진짜 ≠ 행동)`. `differs`이면 True.
- 가지치기: 남은 힌트의 서로 다른 라벨 수 > 남은 절 수 + 1이면 False.
- 메모: `(pos, covered, differs) → bool`.

스파이크(`proto_dl.py`, 2026-09-06)에서 k = 6, 복합 3개 모양도 1~5초 안에 판정됐다.

### 4.3 최소 힌트 집합

1. 규칙과 query를 정한다(§5).
2. query를 뺀 63장을 전부 힌트로 둔다(유일성 자명).
3. 무작위 순서로 힌트를 하나씩 빼 보며, 뺀 뒤에도 유일하면 확정 제거. 한 바퀴 돌면 남은 집합은 **극소**(어느 하나를 빼도 유일성이 깨짐)다.
4. `extra_clues` 개만큼 제거했던 힌트를 되돌려 잉여로 추가한다.
5. 힌트 순서를 섞는다.

극소 집합은 "모든 힌트가 필요하다"는 v1 §3의 목표를 구성적으로 보장한다. 스파이크 실측 힌트 수: k=1 → 4–6장, k=3 → 6–8장, k=4 → 8–11장, k=5 → 11–13장, k=6 → 14–18장.

## 5. 생성기

입력: `puzzle_rng(seed, turn)`, 그 턴의 `PuzzleSpec`(§6).

```
loop (최대 MAX_ATTEMPTS):
    rule  ← 모양·조건 제약·§3.5 정직성을 만족하는 결정 목록 샘플
    Q     ← query 후보: overlap_query면 두 절 이상의 조건이 성립하는 카드, 아니면 전부
            (힌트가 될 카드와 겹치는 건 상관없음 — query는 힌트에서 제외된다)
    if Q 비어 있음: continue
    query ← Q에서 샘플
    clues ← §4.3 극소 집합 + extra_clues
    return Puzzle(rule, shape, clues, query)
실패 시 PuzzleGenerationError (config 오류로 취급)
```

- `predicates: false`인 턴은 규칙 샘플에서 범위·홀짝 원자를 쓰지 않는다(유일성 판정은 §4.1대로 전체 문법).
- `conjunctions: m`은 k개 절 중 m개를 arity 2로 하되 **위치는 무작위**. 모양은 그 결과다.
- RNG 소비량은 시도 횟수에 따라 다르므로 v1처럼 `random.Random(f"{seed}:{turn}")` 서브 RNG를 쓴다. seed 필수(v1과 동일).

## 6. 사다리 (`configs/tasks/signal_game.yaml`)

턴 하나 = 항목 하나. `total_turns`가 항목 수보다 크면 config 로드 시 `ValueError`(v1과 동일).

```yaml
puzzle_ladder:
  - {turn: 1,  clauses: 1, conjunctions: 0, predicates: false, overlap_query: false, extra_clues: 2}
  - {turn: 2,  clauses: 1, conjunctions: 0, predicates: true,  overlap_query: false, extra_clues: 1}
  - {turn: 3,  clauses: 2, conjunctions: 0, predicates: false, overlap_query: false, extra_clues: 1}
  - {turn: 4,  clauses: 2, conjunctions: 0, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 5,  clauses: 3, conjunctions: 0, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 6,  clauses: 3, conjunctions: 1, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 7,  clauses: 4, conjunctions: 1, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 8,  clauses: 4, conjunctions: 2, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 9,  clauses: 5, conjunctions: 2, predicates: true,  overlap_query: true,  extra_clues: 0}
  - {turn: 10, clauses: 6, conjunctions: 3, predicates: true,  overlap_query: true,  extra_clues: 0}
```

검증: `turn`은 1부터 연속, `0 ≤ conjunctions ≤ clauses`, `clauses ≥ 1`, `extra_clues ≥ 0`. `overlap_query: true`는 `clauses ≥ 2`를 요구한다.

난이도 조절 = 이 열 편집. 보정 스크립트 없음. `h_lo/h_hi/families/n_clues/tier`는 사라진다.

## 7. 프롬프트

### 7.1 `system_rules_puzzle.j2` (교체)

- 속성·행동 목록.
- "규칙은 매 라운드 바뀐다. 매 라운드 규칙의 **모양**이 Python `if/elif/else`로 주어지고 빈칸만 채우면 된다."
- 빈칸 문법: 조건 빈칸 하나는 아래 중 하나 — `color == <color>`, `shape == <shape>`, `number == <n>`, `number >= <n>`, `number <= <n>`, `number % 2 == 0`, `number % 2 == 1`; `and`로 묶인 두 빈칸은 서로 다른 속성. 행동 빈칸은 네 행동 중 하나.
- "위에서부터 처음 성립하는 절이 행동을 정한다(Python과 같다)."
- "예시는 모두 이번 라운드의 규칙을 따르며, 예시는 규칙과 새 신호의 정답을 하나로 결정한다."

### 7.2 `observation_puzzle.j2` (교체)

```
Turn 7. This round's rule has exactly this shape (fill in the blanks):

    if ___:
        action = ___
    elif ___ and ___:
        action = ___
    elif ___:
        action = ___
    else:
        action = ___

Examples that follow this round's rule:
  - red star with number 2 → stay
  …
Now: green circle with number 3. Available actions: [go_left, go_right, stay, jump]
```

### 7.3 응답 형식

`get_rule_template_hint()`가 그 턴의 모양을 **한 줄**로 돌려준다:

```
if ___: ___; elif ___ and ___: ___; elif ___: ___; else: ___
```

`task_call.j2`는 이미 `rule_template_hint`가 있으면 `RULE: <hint>` + "(Fill in each placeholder …)"를 렌더한다. 템플릿 수정 없음. 에이전트 응답 예:

```
RULE: if color == "red": stay; elif number >= 3 and shape == "star": go_left; elif number <= 1: jump; else: go_right
ACTION: go_left
```

`probe_puzzle.j2`는 "이번 라운드 모양대로 한 줄로 쓰라"로 문구만 바꾼다.

## 8. 채점

- **행동:** `success_factor` = ACTION == 진짜 규칙의 query 답. 라이프·보상은 엔진(변경 없음).
- **RULE 텍스트 (`rule_match_score`):** §3.4 문법으로 파싱 → 64장 벡터 일치 비율 × 100. 파싱 실패 → `0.0`, `rule_parse_failed = True`. RULE 줄이 없으면 둘 다 `None`(v1과 동일).
  - 파서 허용 범위: `if/elif/else`, `:` 뒤 행동(`action = x` 형태도 허용), 절 구분은 `;` 또는 줄바꿈, 따옴표 유무·대소문자·공백 관대. `number is 3`, `color is red` 같은 v1식 표기도 등식으로 받는다. 절 수가 모양과 달라도 파싱은 하되 `rule_shape_match = False`.
- v1의 family 파서·`functional_match_score`의 family 의존 부분은 제거.

## 9. 턴 메타데이터

`TaskContext.metadata` / `TaskOutcome.metadata`에 다음을 넣는다. v1 키 중 `puzzle_tier`, `rule_family`, `n_consistent_hypotheses`, `rule_parsed_family`는 **삭제**.

| 키 | 내용 |
|---|---|
| `puzzle_turn` | 턴 번호 (사다리 항목) |
| `rule_shape` | 예: `"1,2,1"` (절별 arity) |
| `n_clauses`, `n_conjunctions` | 모양 요약 |
| `predicates_allowed`, `overlap_query` | 그 턴의 생성 제약 |
| `hidden_rule` | 진짜 규칙 한 줄 (§7.3 형식) |
| `clues` | `["red star with number 2 → stay", …]` |
| `query_signal` | query 텍스트 |
| `n_clues`, `n_minimal_clues` | 힌트 수, 그중 극소 집합 크기 (`n_clues − extra_clues`) |
| `query_overlap_count` | query에서 성립하는 절 조건 수 |
| `rule_hypothesis`, `rule_match_score`, `rule_parse_failed`, `rule_shape_match` | 채점 결과 |

`evaluation/shared/export.py`의 long_format 열도 v1의 `puzzle_tier / rule_family / n_consistent_hypotheses / n_clues` → `puzzle_turn / rule_shape / n_clues / n_minimal_clues / rule_shape_match`로 바꾼다.

## 10. 실험 설정

- `configs/experiment/signal_puzzle_smoke.yaml`, `signal_puzzle_pilot_gptoss_n10.yaml`, `signal_puzzle_threat_gptoss_n30.yaml`: `total_turns: 30 → 10`, `lives.initial: 5 → 3`, `max_history_turns: 10`. 나머지 동일.
- 위협 프레이밍은 `lives_total`을 렌더하므로 "3 lives"로 자동 반영된다(`threat_l*.j2`는 `lives_total` 변수 사용).

## 11. 기존 코드와의 관계

| 파일 | 변경 |
|---|---|
| `tasks/signal_game/puzzle.py` | **재작성**: 조건·마스크, 결정 목록 `PuzzleRule`, 모양, 생성기, `exists_differing`, 극소 힌트, 파서, 기능 점수 |
| `tasks/signal_game/puzzle_config.py` | 새 스키마 `PuzzleLadderStep(turn, clauses, conjunctions, predicates, overlap_query, extra_clues)`; `DifficultyLadder` 의존 제거(턴 = 인덱스) |
| `tasks/signal_game/module.py` | 퍼즐 모드 분기의 메타데이터·힌트·채점 호출 갱신; `get_rule_template_hint`가 모양 한 줄 반환 |
| `prompts/tasks/signal_game/{system_rules,observation,probe}_puzzle.j2` | §7 |
| `configs/tasks/signal_game.yaml` | §6 사다리 |
| `configs/experiment/signal_puzzle_*.yaml` | §10 |
| `evaluation/shared/export.py` | §9 열 |
| `scripts/dev/calibrate_signal_puzzle_ladder.py` + `tests/unit/test_calibrate_signal_puzzle_ladder.py` | **삭제** |
| `tests/unit/test_signal_puzzle_{families,generator,parser,config,configs,templates}.py`, `test_signal_game_puzzle_mode.py`, `tests/integration/test_signal_puzzle_e2e.py` | v2에 맞게 재작성 |
| `CLAUDE.md` 퍼즐 절, `docs/paper/sections/03_benchmark.tex` 퍼즐 문단 | 갱신 |

`signal_mode: sequential` 경로와 golden/characterization 테스트는 무변경이어야 한다.

## 12. 테스트

단위:
- 원자 20개·복합 112개 마스크가 정의와 일치. 항상 참/거짓인 조건 없음.
- 결정 목록 평가가 첫 절 우선. 두 절이 동시에 참인 카드에서 앞 절.
- `exists_differing`을 k ≤ 2, arity 1 모양에서 **전수 열거**(20² × 4³ = 25,600)와 대조.
- seed 20개 × 10턴 생성 퍼즐 전부: 전수 판정으로 유일성 재확인(k ≤ 2), `exists_differing`로 재확인(전 턴), 정직성 제약 충족, `overlap_query` 턴은 `query_overlap_count ≥ 2`, 힌트 극소성(아무 힌트나 하나 빼면 유일성 깨짐; `extra_clues == 0`인 턴만).
- 같은 seed는 같은 퍼즐, 다른 seed는 다른 퍼즐.
- 생성 시간: 10턴 합계 p50 < 15초(느슨한 상한, 회귀 감지용).
- 모양 렌더링(§7.2)과 한 줄 힌트(§7.3)가 arity 열에 맞음.
- 파서: 각 모양의 정답 표기 → 100점; `action = x` 형태, 따옴표 생략, 줄바꿈 구분, v1식 `color is red`; 모양 불일치 → `rule_shape_match False`; 쓰레기 → `None`.
- config: 사다리 검증 규칙(§6), `total_turns > 10` 거부, 기존 `signal_mode: sequential` config 무영향.
- module: `prepare` 메타데이터 키(§9), `score`가 정답·기능 점수·플래그를 채움, `get_rule_template_hint`가 모양 한 줄.

통합: StubProvider 5-cell × 1 rep, 10턴, 라이프 3. 매 턴 `rule_shape`가 사다리와 일치, `clues`가 턴마다 다름, Cell 0은 task call만, `rule_match_score` 기록, 오답 3회 시 `eliminated`.

## 13. 파일럿 (구현 후)

`signal_puzzle_pilot_gptoss_n10.yaml`(Cell 0, n=10, 10턴)로 턴별 정답률·`ri_task` 중앙값. 목표: 턴 1 ≈ 1.0, 턴 10 ≈ 0.6, 단조 감소, 10턴 평균 ≥ 0.8(라이프 3에서 탈락이 포기 측정을 잠식하지 않도록). 곡선이 어긋나면 §6 열만 편집한다.

## 14. 알려진 한계

- 유일성은 "공개된 문법 안에서"다. 문법 밖 규칙(64장 표)은 늘 힌트를 설명한다. 시스템 프롬프트가 문법을 명시하므로 실험 정의상 문제없다.
- k = 6 생성이 수 초 걸린다. 시즌 초기화 시 10턴을 한 번에 만들지 않고 턴마다 만들므로 런타임에 분산된다. 필요하면 `(seed, turn)` 키 디스크 캐시를 후속으로 둔다.
- 턴과 난이도는 완전 공선(v1 §15와 동일).
