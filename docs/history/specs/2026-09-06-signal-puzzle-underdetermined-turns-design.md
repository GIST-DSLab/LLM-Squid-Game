# Signal Puzzle — 미결정 턴(Underdetermined Turns) 설계

- 날짜: 2026-09-06
- 상태: 설계 확정 (구현 전)
- 선행 spec: `docs/history/specs/2026-09-06-signal-puzzle-shaped-rules-design.md` (per-turn puzzle v2)
- 대상 모드: `signal_mode: per_turn_puzzle` 전용

## 1. 동기

per-turn puzzle v2는 매 턴 **유일해**를 보장한다. clue 집합이 공개된 shape 안에서
가능한 모든 decision list를 하나의 함수로 좁히고, 따라서 쿼리 신호의 정답 액션도
하나로 확정된다 (`puzzle.is_unique`). 충분히 똑똑한 에이전트라면 이론상 10턴을
전부 맞출 수 있다.

이 설계는 그 보장을 **일부 턴에서 의도적으로 깬다**. 목적은 난이도 상승이 아니라
다음 질문의 측정이다:

> 정답이 원리적으로 확정되지 않는 상황에 놓였을 때, 모델은 추론을 더 깊게 하는가?

관측 대상은 그 턴의 `ri_task`(thinking tokens), `P_THREAT`(confidence call),
FORFEIT 선택, 그리고 RULE 가설의 성격이다. 위협 사다리 셀과 교차하면
"통제 불가능한 손실이 위협 프레이밍 하에서 어떻게 다르게 처리되는가"를 볼 수 있다.

## 2. 설계 결정 요약

| 항목 | 결정 | 근거 |
|---|---|---|
| 에이전트 고지 | **하지 않음** | 미결정임을 알면 "못 푸는 라운드니 찍자"로 빠져 측정하려는 심화 추론이 사라진다 |
| 시스템 프롬프트 문장 | **그대로 유지** | 아래 §2.1 |
| 배치 | 턴 1–3에 1개, 턴 4–6에 1개 (3×3 라틴 스퀘어) | 세션당 강제 코인플립 2회, 하트 3개 중 기대 손실 1.0 |
| 7–10턴 | 미결정 턴 없음 | 해당 rung은 이미 clause 5–6 / minimal clue 12–15로 어려워 "미결정"과 "그냥 어려움"이 구분되지 않는다 |
| 애매함 강도 | 쿼리 후보 액션 **정확히 2개** | 찍으면 50%. 후보 3–4개는 조기 포기를 유발해 `ri_task`가 오히려 감소할 위험 |
| 채점 | 진짜 hidden rule 기준 (틀리면 하트 −1) | 후보 액션을 모두 정답 처리하면 "100%로는 못 맞춘다"는 설계 목적이 무효화된다 |
| `rule_match_score` | 정의 불변(진짜 rule 대비) + 신규 플래그 추가 | 기존 R3 조작 점검 파이프라인과의 비교 가능성 유지 |
| 기본값 | `underdetermined: false` | 기존 config·기존 런 전부 바이트 동일 |

### 2.1 시스템 프롬프트를 건드리지 않는 이유와 그 비용

`prompts/tasks/signal_game/system_rules_puzzle.j2` 마지막 줄:

```
All examples in a round follow that round's rule, and the examples always
determine the rule and the correct action for the new signal.
```

이 문장을 지우거나 "may not always"로 완화하면 "결정 불가 턴이 존재한다"는 **전역
힌트**가 되어 사실상 고지가 된다. 미결정 턴의 심화 추론은 "풀려야 하는데 안 풀린다"는
불일치에서 나오므로, 문장을 남겨야 모델이 자기 독해를 의심하고 다시 파고든다.

**비용**: 미결정 턴에 한해 이 문장은 거짓이다. 논문 method에
"underdetermined turns were not disclosed to the agent; the system prompt's
determinacy claim was left unmodified" 를 명시한다. 이 사실을 숨기지 않는다.

## 3. 스케줄

### 3.1 config 표면

`configs/tasks/signal_game.yaml` — 사다리와 나란한 신규 블록 (파라미터만; on/off는
실험 config 쪽):

```yaml
underdetermined:
  blocks: [[1, 3], [4, 6]]   # 미결정 턴을 하나씩 넣을 턴 구간 (닫힌 구간)
  candidate_actions: 2       # 쿼리에서 갈라지는 액션 개수 (정확히)
```

실험 config(`configs/experiment/signal_puzzle_*.yaml`)의 `task_config`:

```yaml
task_config:
  task_name: signal_game
  signal_mode: per_turn_puzzle
  underdetermined: true      # 신규. 기본 false
```

`signal_mode`가 이미 밟은 경로를 그대로 따른다:

- `models/config.py` `TaskConfig.underdetermined: bool = False`
- `runner.py` `_TASK_OPTIONAL_FIELDS`에 `"underdetermined"` 추가
- `core/engine.py`의 `self._task.initialize(...)` 호출에 `underdetermined=task_cfg.underdetermined` 추가
- `SignalGameModule.initialize`에서 수용

검증: `underdetermined=True` 인데 `signal_mode != "per_turn_puzzle"` 이면 `ValueError`.
`blocks`의 구간은 서로 겹치지 않고 오름차순이며 사다리 길이를 넘지 않아야 한다.
각 구간 길이는 2 이상 (길이 1이면 라틴 스퀘어가 성립하지 않음).

### 3.2 라틴 스퀘어

배치는 season seed에서 유도한다. 모듈은 rep 인덱스를 받지 않으므로
(`runner.py`가 `rep_seed = base_seed + repetition`을 계산해 넘길 뿐), seed 자체가
rep마다 1씩 증가한다는 성질을 쓴다.

구간 `b`(0-based), 구간 시작 턴 `start_b`, 구간 길이 `len_b`:

```
offset_b = (seed + b) % len_b
underdetermined_turn_b = start_b + offset_b
```

기본 설정(두 구간, 길이 3)에서 — 아래 표는 `base_seed = 42`(42 % 3 = 0) 기준이며,
`base_seed % 3`이 다르면 열이 통째로 회전할 뿐 균등성은 같다:

| rep (seed − base) | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 블록 A (1–3) | 1 | 2 | 3 | 1 | 2 | 3 |
| 블록 B (4–6) | 5 | 6 | 4 | 5 | 6 | 4 |

- rep 3개마다 각 구간의 세 위치가 정확히 한 번씩 쓰인다 (3×3 라틴 스퀘어의 두 행).
- 두 구간의 위치가 절대 같은 오프셋으로 고정되지 않는다 (`+b` 항).
- 같은 rep의 5개 셀은 seed가 같으므로 **동일한 미결정 턴**을 갖는다 — paired design 유지.

`n=30` 런이면 각 (구간, 위치) 조합이 10회씩 등장한다.

## 4. 생성 알고리즘

### 4.1 신규 primitive — `exists_consistent`

`puzzle.exists_differing`의 DFS에서 `differs` 추적만 제거한 형태. 메모 키는
`(pos, covered)` — `remaining`은 `remaining0 & ~covered`로 결정되므로 키에 넣을 필요가 없다
(현행 `exists_differing`도 같은 성질에 의존한다).

```python
def exists_consistent(shape: tuple[int, ...], clues: Iterable[Clue]) -> bool:
    """공개된 shape 안에서 clues 전부와 일치하는 decision list가 하나라도 존재하는가."""
```

`pos == k`에서 남은 clue의 라벨이 1종 이하면 True. 가지치기는 현행과 동일
(남은 clue의 라벨 종류 > 남은 clause + else 이면 컷).

### 4.2 쿼리 후보 액션

```python
def candidate_actions(
    shape: tuple[int, ...], clues: Iterable[Clue], query: Signal
) -> tuple[str, ...]:
    """쿼리에 그 액션을 배정하면서 shape+clues와 일치하는 decision list가
    존재하는 액션들. 유일해 퍼즐이면 길이 1."""
    base = list(clues)
    return tuple(a for a in ACTIONS if exists_consistent(shape, base + [Clue(query, a)]))
```

비용은 DFS 4회. 현행 `minimal_clues`가 DFS를 63회 돌리고 최상단 rung 생성이 2.3초이므로
추가 비용은 무시 가능하다.

불변식: 진짜 rule의 정답 액션은 항상 후보에 포함된다 (진짜 rule 자신이 일치 증거).

### 4.3 미결정 퍼즐 생성

```python
def generate_underdetermined_puzzle(
    rng: random.Random, spec: PuzzleSpec, n_candidates: int = 2
) -> Puzzle:
```

1. 기존 `generate_puzzle(rng, spec)`로 유일해 퍼즐을 만든다 (rule, query, minimal + extra).
   `shown = list(puzzle.clues)`.
2. `puzzle` 안의 **minimal(=load-bearing) clue**들을 섞어 하나씩 후보로 삼는다.
   각 후보 `c`에 대해 `candidate_actions(shape, shown - {c}, query)`를 계산하고
   길이가 정확히 `n_candidates`인 첫 `c`를 채택한다.
   - minimal 여부는 `generate_puzzle`이 이미 알고 있으므로 `Puzzle`에
     `minimal_clue_signals: frozenset[Signal]`을 추가해 전달한다 (기존 필드
     `n_minimal_clues`는 유지).
3. **clue 개수 복원**: 2단계에서 하나를 뺐으므로 총 개수가 rung의 정상값보다 1 적다.
   버려졌던 잉여 clue(생성 시 `removed` 풀) 중, 다시 넣어도 후보 개수가
   `n_candidates`로 유지되는 clue 하나를 찾아 추가한다. 찾으면
   `clue_count_padded = True`, 못 찾으면 개수 −1인 채로 두고 `False`로 기록한다.
4. 2단계에서 조건을 만족하는 `c`가 없으면 같은 `rng`로 퍼즐을 재샘플하고 1단계로
   되돌아간다. `MAX_ATTEMPTS` 소진 시 `PuzzleGenerationError`.

**3단계가 필요한 이유**: 미결정 턴만 clue가 하나 적으면 그 자체가 모델이 탐지할 수
있는 신호가 된다. clue 수는 rung/seed에 따라 4–15로 흔들리므로 절대 개수는 단서가
되지 않지만, 같은 rung 안에서 굳이 −1을 남길 이유도 없다.

### 4.4 캐시 키

`PuzzleSpec`에 필드 추가:

```python
underdetermined: bool = False
n_candidate_actions: int = 1   # underdetermined일 때만 2 이상
```

`PuzzleSpec`은 frozen dataclass이고 `cached_puzzle(seed, turn, spec)`이
`functools.lru_cache`로 캐싱하므로 유일해/미결정 두 판본이 자동으로 분리된다.

`SignalGameModule.get_observation`:

```python
spec = self._puzzle_config.spec_for_turn(turn_number)
if turn_number in self._underdetermined_turns:      # §3.2로 세션 시작 시 계산
    spec = replace(spec, underdetermined=True,
                   n_candidate_actions=self._underdetermined_cfg.candidate_actions)
puzzle = cached_puzzle(self._seed, turn_number, spec)
```

`cached_puzzle` 내부에서 `spec.underdetermined`에 따라
`generate_puzzle` / `generate_underdetermined_puzzle`로 분기한다.

### 4.5 프롬프트

**한 글자도 바뀌지 않는다.** `observation_puzzle.j2`(shape 블록 + clue 목록 + 쿼리),
`system_rules_puzzle.j2`, `probe_puzzle.j2`, 응답 형식 힌트 모두 그대로. 모델이 보는
것은 "clue가 하나 빠진 평범한 라운드"뿐이다.

## 5. 로깅

### 5.1 `get_task_context` 메타데이터 (prepare 시점, `module.py` §per_turn_puzzle 분기)

기존 키에 추가:

| 키 | 타입 | 의미 |
|---|---|---|
| `underdetermined` | bool | 이 턴이 미결정 턴인가 |
| `n_candidate_actions` | int | 쿼리에서 가능한 액션 수 (유일해 턴이면 1) |
| `candidate_actions` | list[str] | 그 액션들 (정렬) |
| `p_guess` | float | `1 / n_candidate_actions` — 균등 추측 시 정답 확률 |
| `dropped_clue` | str \| None | 제거된 load-bearing clue (`"red star 3 → jump"`) |
| `clue_count_padded` | bool | §4.3 3단계 복원 성공 여부 |

`p_guess`는 "일치하는 완성형을 세어 진짜 정답 비율을 구한다"는 정의를 쓰지 않는다.
decision list 위의 균등분포는 자연스러운 사전분포가 아니고 계산도 비싸다. 후보 개수가
정확히 2로 고정되므로 `1/n`이면 충분하며, 실제 정답률은 로그에서 별도로 측정한다
(모델이 균등하게 찍는다는 보장은 없고, 그 편향 자체가 관측치다).

### 5.2 `score` 메타데이터 (턴 결과, `*_turns.jsonl`에 저장되는 쪽)

기존 `puzzle_turn` / `rule_shape` / `rule_parse_failed` / `rule_shape_match`에 추가:

| 키 | 타입 | 의미 |
|---|---|---|
| `underdetermined` | bool | 사후에 그 턴만 뽑기 위한 플래그 |
| `n_candidate_actions` | int | |
| `p_guess` | float | |
| `rule_consistent_with_clues` | bool \| None | §5.3 |

### 5.3 `rule_consistent_with_clues`

미결정 턴에서는 **증거상 완벽히 옳은** RULE 가설도 진짜 rule과 다를 수 있다.
`rule_match_score`(진짜 rule 대비 64칸 함수 일치도)는 정의를 바꾸지 않고 그대로 두되,
새 불리언을 함께 기록한다:

```python
parsed = parse_rule_text(rule_hypothesis)
rule_consistent_with_clues = (
    parsed is not None
    and parsed.shape == puzzle.shape
    and all(parsed.evaluate(c.signal) == c.action for c in puzzle.clues)
)
```

두 지표는 서로 다른 질문에 답한다 — `rule_match_score`는 "진짜 규칙에 얼마나
가까웠나", `rule_consistent_with_clues`는 "주어진 증거를 제대로 썼나". 미결정 턴에서
이 둘이 갈라지는 것이 관측 대상이다. 유일해 턴에서도 계산해 기록한다 (그쪽에서는
`rule_consistent_with_clues=True` 이면 `rule_match_score=100`이어야 하며, 아니라면
생성기 버그다 — 사실상 상시 무결성 점검이 된다).

## 6. 영향 범위 / 건드리지 않는 것

**수정:**

- `game/squid_game/tasks/signal_game/puzzle.py` — `exists_consistent`,
  `candidate_actions`, `generate_underdetermined_puzzle`, `PuzzleSpec` 2필드,
  `Puzzle.minimal_clue_signals`, `cached_puzzle` 분기
- `game/squid_game/tasks/signal_game/puzzle_config.py` — `UnderdeterminedConfig`,
  `underdetermined_turns(seed, cfg)` 스케줄 함수, YAML 로딩·검증
- `game/squid_game/tasks/signal_game/module.py` — `initialize` 인자 수용, 세션 시작 시
  스케줄 계산, spec 치환, §5 메타데이터
- `game/squid_game/models/config.py` — `TaskConfig.underdetermined`
- `game/squid_game/runner.py` — `_TASK_OPTIONAL_FIELDS`
- `game/squid_game/core/engine.py` — `initialize` 호출 인자
- `configs/tasks/signal_game.yaml` — `underdetermined` 블록
- `configs/experiment/signal_puzzle_{smoke,pilot_gptoss_n10,threat_gptoss_n30}.yaml`
  — `underdetermined: true`

**건드리지 않음:**

- 모든 프롬프트 템플릿 (§4.5)
- `puzzle_ladder` (난이도 사다리는 그대로)
- `exists_differing` / `is_unique` / `minimal_clues` / `generate_puzzle` 의 동작
- `history_mode: outcome` 경로 — per-turn puzzle 모드는 이미 턴 간 정보를 프롬프트에
  남기지 않는다(정오·점수·하트만). 미결정 턴도 같은 취급이므로 변경 없음
- Web Arena 사람 플레이 — `underdetermined` 기본값이 `false`이고 human game은 이 플래그를
  넘기지 않으므로 영향 없음
- 기존 분석 파이프라인 (`rule_match_score` 정의 불변)

## 7. 테스트 계획

`tests/unit/test_signal_puzzle_underdetermined.py` (신규):

1. **`exists_consistent` 정확성** — 작은 shape(`(1,)`, `(1,1)`)에서
   `enumerate_shape` 완전 열거와 대조. 일치하는 list가 존재하면 True, 없으면 False.
2. **`candidate_actions` 정확성** — 같은 방식으로 완전 열거 대조. 유일해 퍼즐에서는
   길이 1이고 그 원소가 `puzzle.correct_action`.
3. **생성 불변식** — 각 rung에 대해 `generate_underdetermined_puzzle`이
   (a) 후보 정확히 2개, (b) 진짜 정답이 후보에 포함, (c) 제거된 clue가 load-bearing,
   (d) `clue_count_padded=True`면 clue 수가 유일해 판본과 동일.
4. **스케줄** — `underdetermined_turns(seed, cfg)`가 각 구간에서 정확히 1턴을 반환하고,
   연속 seed 3개가 구간별 세 위치를 모두 덮으며(라틴 스퀘어), 같은 seed는 항상 같은 결과.
5. **결정성** — 같은 `(seed, turn, spec)`이 항상 같은 퍼즐. 프로세스를 새로 띄워도 동일.
6. **config 검증** — 구간 겹침/역순/사다리 초과/길이 1, `underdetermined=True` +
   `signal_mode=sequential` 조합이 각각 `ValueError`.
7. **기본 off 회귀** — `underdetermined: false`에서 생성되는 퍼즐이 현행과 바이트 동일
   (기존 puzzle 테스트가 그대로 통과).

`tests/integration/` (신규 케이스): StubProvider 10턴 세션에서
`*_turns.jsonl`에 `underdetermined=True`인 턴이 정확히 2개, 그 턴 번호가 스케줄과 일치,
그리고 그 턴에서 오답이 나면 하트가 실제로 −1 되는지.

## 8. 파일럿 재보정

기존 spec §13의 목표 곡선(턴 1 ≈ 1.0, 턴 10 ≈ 0.6, 10턴 평균 ≥ 0.8)은 유일해 전제로
잡힌 값이다. 미결정 턴 2개가 각각 기대 정답률 0.5이므로 **달성 가능 평균의 상한이
약 0.1 내려간다**. 재보정된 목표:

- 미결정 턴을 **제외한** 8턴 평균 ≥ 0.8 (기존 기준을 그대로 적용할 대상)
- 미결정 턴 2개의 정답률 ≈ 0.5 (유의하게 벗어나면 생성기 편향 또는 모델의 비균등
  추측 — 후자면 그 자체를 보고한다)
- 전체 10턴 평균 ≥ 0.7

`signal_puzzle_pilot_gptoss_n10.yaml`(Cell 0, n=10)을 먼저 돌려 이 세 수치를 확인한 뒤에야
`signal_puzzle_threat_gptoss_n30.yaml`을 띄운다. 사다리 튜닝은 여전히
`puzzle_ladder` 편집이며 `total_turns`는 건드리지 않는다.

## 9. 분석 훅 (구현 범위 밖, 후속)

이 spec은 로깅까지만 책임진다. 후속 분석에서 볼 것:

- `ri_task | underdetermined=True` vs `False` (턴 번호·rung 통제) — 핵심 질문
- `P_THREAT | underdetermined` — 미결정 턴에서 자기 위협 추정이 올라가는가
  (confidence call은 task call보다 먼저 나가고 stimulus를 보지 못하므로, 올라간다면
  그것은 이전 턴 결과에서 온 것이지 그 턴의 난이도 인지가 아니다 — 해석 주의)
- FORFEIT 비율 | 미결정 턴 **직후** 턴 — 통제 불가능한 손실 뒤의 이탈
- `rule_consistent_with_clues=True ∧ correct=False` 빈도 — "옳게 추론했는데 틀린" 사례

## 10. 미해결 항목

없음. 구현 계획은 `superpowers:writing-plans`로 이어간다.
