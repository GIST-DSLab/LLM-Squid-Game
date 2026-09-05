# Omni-MATH 난이도 사다리 재배분: 30턴 → 20턴 (2026-09-05)

## 변경

`configs/tasks/omni_math.yaml`의 turn → band 사다리를 30턴에서 20턴으로 줄였다.
모든 band를 2턴씩 균등하게 밟고, 남는 4턴은 쉬운 band 1–4에 하나씩 더 준다.

| | b1 | b2 | b3 | b4 | b5 | b6 | b7 | b8 | 합 |
|---|---|---|---|---|---|---|---|---|---|
| 이전 (30턴) | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 3 | 30 |
| 현재 (20턴) | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 2 | 20 |

`configs/tasks_long45/omni_math.yaml`(45턴, 09-03 런 재현용)은 바꾸지 않는다.

## 근거

- 2026-09-03 런 4모델 687턴(`outputs/benchmark_threat3_omni_math_*`)의 band별 정답률:
  b1–b4 0.82–0.94(천장), b5 0.73, b6 0.65. 이전 사다리는 30턴 중 16턴을 난이도가
  오르지 않는 구간에 썼다.
- 시즌 길이 20은 Signal Game 런(15–20턴)과 맞고 LLM 비용을 1/3 줄인다.
- 워밍업(band 1–4)은 FORFEIT가 보존할 점수 S를 만들고 5목숨 설계에서 조기 탈락을
  막는 역할이며, 3턴씩 12턴이면 충분하다.

## 제약

- 시즌 내 무중복: band별 수요 ≤ 풀 (b7 59개, b8 37개) — `SeededSampler.validate_capacity` 통과.
- 시드 간 재출현은 이전과 같이 허용.
- **2026-09-05 이전 런은 옛 매핑으로 기록됨.** 분석은 턴 번호로 band를 재계산하지 말고
  `task_metadata.band`를 읽어야 한다. 이전·이후 런은 같은 시드라도 문제열이 다르다.
- 실험 시즌이 사다리보다 길면 `initialize`가 거부하므로 omni_math 시즌은 `total_turns ≤ 20`.
- 웹 아레나 사람 게임(10턴)은 `DifficultyLadder.fitted(10)` → `[1,1,2,2,3,4,5,6,7,8]`.

## 함께 바뀐 것

- `configs/experiment/benchmark_omni_math_n30.yaml`, `benchmark_smoke.yaml`,
  `lives_threat_omni_math_smoke.yaml`: omni_math 시즌 `total_turns` 30 → 20.
- `tests/unit/test_benchmark_ladder.py`, `test_benchmark_config.py`,
  `test_benchmark_module.py`, `test_benchmark_experiment_configs.py`: 과제별 시즌 길이로 갱신.
- 보고서: `weekly-report/0910/2026-09-05-omni-math-web-and-ladder.html` §3-4.
- 논문 `docs/paper/sections/03_benchmark.tex`는 사다리를 일반적으로만 기술해 수정 불필요.
- 커밋 해시: (커밋 시 기입)
