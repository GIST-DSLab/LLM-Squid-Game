# 2026-09-04 — Split-Call 턴 순서 교체: decision call → task call

## 결정

- Split-Call 경로(`use_split_forfeit_layer=true`)의 두 LLM 호출 순서를 바꾼다.
  이전: task call(Call 1) → p_success probe(Call 1.5) → forfeit call(Call 2).
  이후: **decision call → task call**. FORFEIT이면 세션이 그 자리에서 끝나고 task call은
  호출되지 않는다 (`ri_task` / `raw_response_task` / `thinking_text_task` = `None`).
- decision call은 이번 라운드 자극(문제 본문)을 **보지 않는다**. 누적 히스토리 블록
  (`split_context_level: medium|full`) + forfeit 메뉴만 본다. `minimal`은 메뉴만.
  `full`은 더 이상 task call 프롬프트/thinking을 echo할 수 없으므로 `medium`과 동일하게
  동작한다 (기존 YAML 로드 호환용으로 enum만 유지).
- Unit 17 Call 1.5 self-confidence probe는 **제거**한다. task 답에 대한 사후 확신도가
  이미 렌더된 메뉴의 보상 계산에 들어갈 수 없기 때문이다. `use_psuccess_probe: true`와
  `forfeit_layer.chain_psuccess_to_menu: true`는 config 검증에서 거부된다.
  `TurnResult.psuccess_self` / `ri_probe` / `raw_response_probe` / `thinking_text_probe`
  필드는 2026-04-22 산출물 재분석용으로 데이터 모델에만 남고, 새 런에서는 항상 `None`.
- config 플래그로 task-first 순서를 남기지 않는다 (하드 교체). 2026-04-22 3-call 런은
  저장된 출력으로만 재분석 가능하며 재실행으로 재현되지 않는다.
- 코드 명칭을 `Call 1` / `Call 2`에서 `task_call` / `decision_call`로 바꾼다.

## 변경 지점

| 영역 | 파일 | 내용 |
|---|---|---|
| 엔진 | `game/squid_game/core/unified_turn.py` | `_execute_turn_split_forfeit_layer` 재작성 (decision → task, FORFEIT 조기 종료, probe 블록 삭제, `use_psuccess_probe` 파라미터 삭제). 합산 필드(`raw_response`, `thinking_text`)는 wire 순서대로 decision 먼저 |
| 프롬프트 | `prompts/user_message/decision_call.j2` (구 `forfeit_only.j2`), `task_call.j2` (구 `task_only.j2`), `psuccess_probe.j2` 삭제 | decision call은 "A new round is about to begin. Before it is shown to you, decide…" 문구 + 메뉴. task call에서 "A separate decision … will follow" 문장 삭제 |
| 에이전트 | `agents/_parsing.py`, `agents/base.py`, `agents/vanilla.py`, `core/turn_prompts.py` | `TaskCallResponse` / `DecisionCallResponse`, `build_task_call_message` / `build_decision_call_message(user_body, menu_text, forfeit_allowed, split_context_level)`, `parse_task_call_response` / `parse_decision_call_response`, `respond_task_call` / `respond_decision_call`, `compose_task_call_user_message`. probe 관련 helper(`PSuccessProbeResponse`, `build/parse_psuccess_probe_*`, `respond_psuccess_probe_only`, `format_prior_accuracy_summary`) 삭제 |
| 설정 | `models/config.py`, `core/engine.py`, `runner.py` | `_validate_psuccess_probe_removed` (True 거부), 엔진의 `use_psuccess_probe` 인자 삭제, 필드 설명 갱신 |
| 분석 | `evaluation/cognitive/ri_task_call.py` (구 `ri_call1.py`), facade `TASK_CALL_RI_*` / `fit_task_call_ri_one` / `render_task_call_ri_report`, `scripts/analysis/analyze_task_call_ri.py` (구 `analyze_call1_ri.py`) | 모듈 도큐스트링에 순서 주의 추가: 새 런의 `ri_task`는 CONTINUE 조건부(post-decision) 양이며 FORFEIT 턴에는 없다 |
| 웹 | `web/squid_arena/arena.py`, `routes_arena.py`, `human_game.py`, `schemas.py`, `web/frontend/index.html`, `app.js` | LLM Arena: probe 플래그 제거, `calls_total = turns × 2`. Human play: Stage 1 = continue/forfeit (카드 숨김, 보상 미리보기, no-forfeit 셀은 3초 자동 진행) → Stage 2 = action + rule guess → 제출. confidence 슬라이더 삭제. 로그 뷰어는 decision thinking을 먼저 표시, probe 값은 존재할 때만 |
| 설정 파일 | `configs/experiment/phase3_split_forfeit_*.yaml`, `benchmark_*.yaml` | `use_psuccess_probe: false`, `chain_psuccess_to_menu: false` |
| 테스트 | `tests/characterization/test_turn_flow_6cells.py` + `snapshots/turn_flow/cell_*.json` 재기록, `tests/unit/test_unified_turn_split_forfeit_layer.py`, `test_split_forfeit_prompts.py`, `test_task_call_template.py`, `test_v6_configs.py`, `test_benchmark_experiment_configs.py`, `tests/integration/test_arena.py`, `test_benchmark_task_e2e.py`, `test_web_arena_api.py`, `test_split_forfeit_layer_e2e.py` | 호출 순서·FORFEIT 조기 종료·probe 부재를 고정 |
| 문서 | `CLAUDE.md`, `docs/paper/sections/03_benchmark.tex` | 흐름 설명 갱신 |

## 분석상 함의

- `ri_forfeit`는 구조적으로 과제 추론을 포함하지 않는다 (자극을 보기 전 결정).
- `ri_task`는 CONTINUE를 택한 턴에만 존재한다. FORFEIT 턴의 `ri_task`가 `None`이므로
  H2(`ri_forfeit ~ choice × framing`)는 영향이 없지만, R1/H6b(`ri_task` 회귀)는 선택 편향을
  안고 읽어야 한다.
- 웹 홈의 "The rules are simple" 데모(8-beat, `rulesDemo`)는 아직 답 → 결정 순서의
  연출을 유지한다. 실제 플레이 카드만 바뀌었다.

## 검증

- `pytest tests/unit tests/integration tests/characterization`: 1891 passed / 12 failed.
  12건은 모두 이 변경 이전부터 실패하던 항목이다 (HEAD worktree에서 8건 재현, 나머지 4건은
  작업 트리의 커밋되지 않은 다른 변경·untracked `results/` 파일에서 비롯).
