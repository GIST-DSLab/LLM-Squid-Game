# `puzzle_challenge` 구현 원장 (실행 기록)

계획: `docs/history/plans/2026-09-10-signal-game-effort-sensitive-difficulty-plan.md`
설계: `docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md`
브랜치: `feat/signal-effort-difficulty` (워크트리 `.claude/worktrees/signal-effort-difficulty`)

체크포인트마다 한 항목. 사람이 없으므로 승인 대신 기록하고 계속한다.

---

## Task 1 — 얕은 해 4종과 함정 술어

- 파일: `game/squid_game/tasks/signal_game/puzzle.py`(`import collections` + 새 섹션),
  `tests/unit/test_puzzle_challenge.py`(신규).
- TDD: `ImportError: cannot import name 'SHALLOW_SOLVER_NAMES'` 확인 후 구현.
- 테스트: `tests/unit/test_puzzle_challenge.py` → **6 passed** (6.5s).
- 계획 이탈: 없음. 계획의 코드를 그대로 삽입했다 (`functional_match_score` 뒤 /
  `# --- Task 7 appends: cached_puzzle` 앞).

## Task 2 — `PuzzleSpec` 확장, 함정 생성기, `puzzle_id`

- 파일: `game/squid_game/tasks/signal_game/puzzle.py`(`hashlib`/`replace` import,
  `GENERATOR_VERSION`, `PuzzleSpec` 필드 3개 + 검사 2개, `Puzzle.trap_attempts`,
  `generate_trap_puzzle`, `puzzle_id_for`, `cached_puzzle` 분기),
  `tests/unit/test_puzzle_challenge.py`.
- TDD: `ImportError: cannot import name 'GENERATOR_VERSION'` 확인 후 구현.
- 테스트: 새 파일 **16 passed**; 회귀
  `test_signal_puzzle_generator/uniqueness/underdetermined` → **181 passed** (126s).
- 계획 이탈 (사소): 계획은 태스크마다 파일 중간에 import 블록을 덧붙이라고 썼는데,
  같은 모듈(`...signal_game.puzzle`)에서 오는 이름이라 **맨 위 import 블록에 합쳤다**.
  주장·테스트는 그대로다.

## Task 3 — `puzzle_profiles` (프로필 모델 + 과제 YAML)

- 파일: `game/squid_game/tasks/signal_game/puzzle_config.py`(`PuzzleProfile`,
  `SignalPuzzleConfig.puzzle_profiles`, 로더 한 줄, 모듈 docstring "Three→Four blocks"),
  `configs/tasks/signal_game.yaml`(`puzzle_profiles` 블록), 테스트 파일.
- TDD: `ImportError: cannot import name 'PuzzleProfile'` 확인 후 구현.
- 테스트: 새 파일 **25 passed**; 회귀 `test_signal_puzzle_config` +
  `test_signal_puzzle_configs` + `test_signal_puzzle_forced_wrong` → **103 passed**.
- 계획 이탈: 없음 (모듈 docstring의 블록 열거를 갱신한 것은 계획에 없지만 파일이
  "세 블록"이라고 세고 있어서 갱신했다).

## Task 4 — 설정 표면과 두 관문 (runner + engine)

- 파일: `game/squid_game/models/config.py`(`hashlib` import,
  `PuzzleChallengeScheduleEntry` + `PuzzleChallengeConfig`, `TaskConfig.puzzle_challenge`),
  `game/squid_game/runner.py`(`_TASK_OPTIONAL_FIELDS`),
  `game/squid_game/core/engine.py`(`initialize(..., puzzle_challenge=...)`), 테스트 파일.
- TDD: `ImportError: cannot import name 'PuzzleChallengeConfig'` 확인 후 구현.
- 테스트: 새 파일 **31 passed**.
- 확인: 엔진이 새 kwarg를 **모든** 과제 모듈에 넘기므로 시그니처를 전부 확인했다 —
  base/benchmark/navigation/voting_room/null_task/signal_game 모두 `**kwargs`를 받는다.
- 계획 이탈: 없음.

## Task 5 — 모듈 로드 검증 + 프로필 기반 spec 선택 + 메타데이터

- 파일: `game/squid_game/tasks/signal_game/module.py`(import 4개 추가, `__init__` 상태 3개,
  `initialize` 상호배제 4종 + 스케줄/프로필 검증 4종, 사다리 길이 검사 건너뛰기,
  `get_observation` spec 선택, `reset`, `_puzzle_metadata` 8키, docstring 2곳), 테스트 파일.
- TDD: 12 failed → 구현 → **45 passed**.
- 회귀: `test_signal_game_puzzle_mode` + `test_signal_puzzle_underdetermined` +
  `test_signal_puzzle_forced_wrong` → **133 passed**.
- 계획 이탈 (사소): 계획의 `_puzzle_metadata` 코드가 `[n for n, a in shallow.items() ...]`로
  바깥 `n = puzzle.n_candidate_actions`를 가렸다(파이썬3에선 무해하지만 오해를 부른다).
  `solver`/`action`으로 이름을 바꿨다. `initialize` docstring의 Keyword Args에
  `puzzle_challenge` 항목을 추가한 것도 계획엔 없지만 나머지 키가 전부 문서화돼 있어 맞췄다.

## Task 6 — 규칙 채점 (`rule_grading`)

- 파일: `game/squid_game/prompts/tasks/signal_game/system_rules_puzzle.j2`(조건부 문단),
  `game/squid_game/tasks/signal_game/module.py`(`get_system_rules(rule_grading=…)`,
  `_reproduces_clues`, `score()` 판정 + 메타데이터 3키 + docstring), 테스트 파일.
- TDD: 8 failed → 구현 → 새 파일 **54 passed**.
- 회귀: `test_signal_puzzle_templates` + `test_signal_game_puzzle_mode` +
  `test_signal_puzzle_forced_wrong` + `test_signal_puzzle_parser` +
  `test_signal_puzzle_rules` → **124 passed**. `rule_grading` 없는 렌더는 바이트 동일.
- **계획 이탈 (중요)**: 계획 Task 6(d)는 채점 술어를 `forced_wrong = (...)` **바로 위**에
  넣으라고 했는데, 그 자리는 `rule_reproduces_clues`가 **아직 계산되기 전**이다
  (RULE 파싱 블록이 `success_factor` 계산보다 뒤에 온다) — 그대로 넣으면 `NameError`.
  그래서 `rule_graded`/`actual_correct`/`forced_wrong`/`is_correct`/`success_factor`
  다섯 줄을 **RULE 파싱 블록 뒤로** 옮겼다. 순서만 바뀌고 값은 계획대로이며, 그 사이
  코드는 이 이름들을 읽지 않는다(`_TurnRecord` 추가는 더 뒤에 있다). 주석에 이유를 적었다.

## Task 7 — E2E와 바이트 동일성 회귀

- 파일: `tests/integration/test_puzzle_challenge_e2e.py`(신규). 프로덕션 코드 변경 없음.
- 테스트: 새 E2E **9 passed**. 회귀 스위트 전체(계획의 13개 파일) → **388 passed (210s)**.
- **계획이 "코드를 읽고 확정하라"고 표시한 지점 ① — `patch_runner_provider`**:
  계획의 추정(`patch_runner_provider(config_path, response_fn)`이 런까지 돌리고
  season 결과를 반환)은 **틀렸다**. 실제로는
  `patch_runner_provider(response_fn=...)`가 `ExperimentRunner._create_provider`에
  `StubProvider`를 꽂고 그 stub을 돌려줄 뿐이고, 테스트가 직접
  `ExperimentRunner(cfg).run()`을 부른 뒤 `*_turns.jsonl`을 읽는다
  (`test_forced_wrong_e2e.py`의 패턴). 그대로 맞춰 다시 썼다.
- **누출 테스트의 대상 변경**: 계획은 `t.system_prompt`/`t.observation`을 보라고 했는데,
  이 셀은 `not_allowed` + `always_decide` off라 결정 콜이 없고 그때
  `TurnResult.system_prompt`는 `None`이다. 그래서 **stub이 실제로 받은 바이트**
  (`stub.calls`의 전 메시지) + `observation`을 검사한다 — 더 강한 검사다.
  검사 어휘 11개(`trap`·`shallow`·`nearest`·`majority`·`last_match`·`single_attr`·
  `puzzle_id`·`difficulty_profile`·`schedule_id`·`solver`·`profile`) 전부 누출 없음.
- 계획의 "Expected: 210 passed"는 이제 **388**이다 (계획 작성 이후 그 13개 파일의
  테스트가 늘었다). 전부 통과이므로 바이트 동일성은 유지된다.

## Task 8 — LLM 없는 생성기 검증 CLI

- 파일: `scripts/dev/validate_puzzle_challenge.py`(신규), 테스트 파일.
- TDD: 4 failed → 구현 → **4 passed**.
- **계획 이탈 ① (실질적) — G6가 `easy`/`medium`에서 구조적으로 불가능했다.**
  `draw_shape`는 `clauses` 자리 중 `conjunctions`개를 arity 2로 고르므로 가능한 shape 수는
  `C(clauses, conjunctions)`다: easy(1,0) = **1**, medium(3,0) = **1**, hard(4,1) = 4.
  즉 easy/medium은 어떤 생성기를 써도 한 shape이 100%라 "점유율 ≤ 0.60"을 만족할 수
  없고, 계획의 `test_gates_pass_on_the_shipped_easy_profile`이 실패했다. G6의 취지는
  **함정 필터의 형태 편향**(spec §9, 메모 A의 위험)이므로, 임계값은 손대지 않고
  **shape이 하나뿐인 프로필에는 게이트를 적용하지 않도록** 했다
  (`n_possible_shapes` 열 + `check_gates`의 조건). hard에서는 그대로 판정한다.
- **계획 이탈 ② — `--seeds` 기본값 100 → 200** (spec §9의 CLI 예시가 쓰는 값).
  G2/G5/G6은 비율 추정치라 표본이 작으면 잡음만으로 실패한다: `easy`의 `nn`은
  n=400에서 턴 1~4 모두 0.83~0.86인데, n=100 · turn 3 draw 하나가 **0.77**로
  G5(≥ 0.80)를 떨어뜨렸다. 임계값은 spec 고정이라 건드리지 않고 표본을 spec의 수로
  올렸으며, `--seeds` help에 그 이유를 적었다.
- **게이트 실측 (n=200, `--turn 3`, 전 프로필 통과 · exit 0)**:

  | 프로필 | trap | 함정 수율 | p95 생성 | 정답행동 최대점유 | shape 최대점유 | 단서수 trap/plain | nn / majority / last_match / single_attr |
  |---|---|---|---|---|---|---|---|
  | easy   | False | — (1.00) | 0.00s | 0.27 | 1.00 (shape 1종, G6 미적용) | 5/5 | 0.82 / 0.70 / 1.00 / 1.00 |
  | medium | False | — (1.00) | 0.03s | 0.30 | 1.00 (shape 1종, G6 미적용) | 8/8 | 0.76 / 0.42 / 0.14 / 0.69 |
  | hard   | True  | **0.35** | 4.62s | 0.38 | 0.28 | 10/10 | **0.00 / 0.00 / 0.00 / 0.00** |

  hard의 함정 수율 0.35는 spec §5.1의 예측(0.17)의 두 배로, 200회 예산이 넉넉하다.
  단서 수 중앙값이 trap/plain 모두 10이라 G3(누출) 차이는 0 — 함정 라운드를 단서 수로
  식별할 수 없다.

## Task 9 — 파일럿 config 5개 (돌리지 않음)

- 파일: `configs/experiment/signal_effort_pilot_{a,b}_{gptoss120b,gemma4}.yaml` +
  `signal_effort_pilot_a_nograde_gptoss120b.yaml`(신규 5개), 테스트 파일.
- TDD: 7 failed → 작성 → **7 passed**.
- 검증: 5개 전부 `--dry-run` 통과(각 3셀), `--preflight` 각 **360 generated, 0 failures**.
- **계획 이탈 ① — YAML 앵커 대신 세 셀을 펼쳐 썼다.** 계획이 그 선택지를 명시했고
  (`⚠️ 앵커가 … 복잡하게 만든다면 세 셀을 그냥 펼쳐 쓰라`) 저장소 관례가 그쪽이다.
- **계획 이탈 ② (실질적) — 세 셀의 `cell_id`를 0/1/2로 나눴다.** 계획의 config는
  앵커 하나에 `cell_id: 0`을 달아 세 셀이 같은 id를 갖게 돼 있었다. 그런데 세 셀은
  framing · forfeit_condition · social_context · seed가 전부 같고 `reasoning_effort`만
  다르므로, `--resume` 키 `(framing, forfeit_condition, social_context, cell_id, seed)`가
  셋을 구별하지 못한다 — CLAUDE.md가 몸값 설계에서 기록한 바로 그 실패
  ("한 팔에 여러 칸을 두는 설계라면 --resume이 낸 세션 수를 셀별로 세어 확인할 것").
  더구나 Task 10의 effort 조인이 `cell_id`를 거쳐야 하므로(아래) 같은 id면 분석도 불가능하다.
  각 config 헤더에 이 사실을 주석으로 적었다.

## Task 10 — 파일럿 분석 스크립트 (6개 게이트)

- 파일: `scripts/analysis/effort_dose_response.py`(신규), 테스트 파일.
- TDD: 4 failed → 구현 → **4 passed**(+ Pilot 7 = 11). `test_scripts_taxonomy` 3 passed.
- **계획이 "코드를 읽고 확정하라"고 표시한 지점 ② — `season_results.jsonl`의
  `reasoning_effort`**: 기록된 런(`outputs/ransom_r6_neutral_game_glm53flash/…`)의
  실제 키는 `['agent_type','cell_id','difficulty','eliminated',…,'season_id','seed',…]`로
  **`provider_config`가 아예 없다**. 계획의 `_efforts_by_season`은 전 행을 `unknown`으로
  만들었을 것이다. 계획이 지시한 대로 `experiment_config.json` 경로로 고쳤고,
  **두 홉 조인**으로 구현했다: 턴 행의 `season_id` → `season_results.jsonl`의 `cell_id`
  → `experiment_config.json`의 `seasons[].provider_config.reasoning_effort`.
  (턴 행에는 `cell_id`가 없어서 한 홉으로는 안 된다.) docstring에 적었고
  `test_effort_is_joined_through_cell_id`가 고정한다. 조인이 실패하면 추측하지 않고
  `unknown`으로 두며, CLI가 그 행 수를 경고로 찍는다.
- 계획 이탈 (사소): `effort_moves_tokens` 게이트에서 NaN 중앙값이 섞이면 비교가 조용히
  False가 되므로 `math.isnan` 검사를 명시했다.

## Task 11 — 문서

- 파일: `CLAUDE.md`("강제 오답 턴" 뒤 / "사다리 압축" 앞에 노력 민감 난이도 문단 +
  분석자 계약 항목), 계획 파일 맨 아래 "구현 기록" 절, 이 원장.
- `tests/unit/test_scripts_taxonomy.py` **3 passed** — 새 스크립트 두 개가
  `scripts/dev/` · `scripts/analysis/`로 규칙을 지킨다.
- CLAUDE.md 문단은 계획의 초안에 세 가지를 더했다 (전부 구현 중에 드러난 사실이다):
  파일럿 세 셀의 `cell_id` 분리, G6의 적용 조건, `--seeds` 기본값 200의 이유.

## 최종 검증

**전체 스위트** `tests/unit tests/integration`:
**16 failed, 4379 passed, 94 skipped (382s)**.

16개 실패는 **전부 이 작업 이전부터 있던 것**이고, 내가 낸 것은 **0건**이다.
13개는 인계 지시가 미리 열거한 목록과 그대로 일치한다:
`test_benchmark_fixed_items` · `test_config_v3`(legacy members) ·
`test_file_anchors_resolve_to_repo_root` · `test_import_smoke`(ablate_forfeit_drivers) ·
`test_plot_style`(2건) · `test_tier_boundaries` · `test_analysis_e2e` ·
`test_null_risk_e2e`(2건) · `test_signal_risk_e2e`(2건) ·
`test_web_arena_api`(campaign ladder).

목록에 **없던 3건**은 손대지 않은 main 체크아웃에서 같은 명령으로 재현해 **선재 실패임을
확인**했다 (읽기 전용 실행):

- `test_api_web_arena.py::test_app_imports_and_registers_all_endpoints`
  (메모리 노트 "Web Arena baseline test breakage"와 같은 계열)
- `test_probe_independence.py::TestCheckDiscoveryTimingIndependence::test_equal_discovery_timing_passes`
- `test_survival_drive.py::TestLoadSmiTable::test_all_digit_session_id_stays_a_string`
  (pandas가 이제 `StringDtype`을 주는 환경 문제: `assert dtype == object` 실패)

**새 테스트 78개** (`tests/unit/test_puzzle_challenge.py` **69** +
`tests/integration/test_puzzle_challenge_e2e.py` **9**), 둘을 함께 돌려 **78 passed**
(137s — `hard` 프로필의 함정 생성이 대부분의 시간이다).

**config 검증**: 새 config 5개 전부 `--dry-run` 통과 + `--preflight` **각 360 generated,
0 failures**.

**손대지 않았는데 `git status`에 뜨는 것**: `results/score_equiv_pilot/**`의 16개 jsonl은
세션 시작 시점의 main 체크아웃 상태에서 이미 `M`이었다(워크트리/LFS 산출물). 이 작업과
무관하며 건드리지 않았다.

**커밋하지 않았다** (owner 몫). Task별 제안 메시지는 계획 각 Step 5에 있다.
