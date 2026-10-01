# Call-trace provider — 프롬프트가 어떤 역할로 어떤 순서에 들어가는지 보는 도구 (2026-09-08)

## 무엇인가

한 턴에서 **어떤 문장이 어떤 role(system / user / assistant)로, 어떤 순서로, 세 호출
중 어디에** 들어가는지 눈으로 보기 어려웠다. `TurnResult`가 `system_prompt` /
`confidence_call_input` / `decision_call_input` / `observation`을 남기지만 그것은
매니저가 **조립한 것**이지 provider에게 **건네진 `messages` 리스트**가 아니고, FORFEIT
턴에는 task call 기록이 아예 없다.

`TraceProvider`는 진실이 완전한 유일한 지점 — `LLMProvider.complete()` 안 — 에 앉아
매 호출의 메시지 리스트를 그대로 JSONL에 적고, 실제 파서가 받아들이는 **깡통 답**을
돌려준다. 그 위의 파이프라인은 전부 진짜다: 프레이밍 조립, peer_death 통지, hazard
ramp, forfeit 메뉴, 목숨 원장, 채점까지 유료 런과 동일하게 돈다. 모델만 없다.

## 명령

```bash
# 아무 config나 하나 골라서: 실행 + HTML 렌더까지 한 방
PYTHONPATH=game:web:db uv run --no-sync python scripts/dev/trace_config.py \
    --config configs/experiment/<any>.yaml

# 옵션
#   --reps N          num_repetitions (기본 1)
#   --turns N         total_turns 캡. task config가 거부하면(underdetermined 블록이
#                     짧은 시즌 밖으로 나가는 경우) 경고만 찍고 원래 길이로 돈다.
#   --forfeit-at T    메뉴에 출구가 있는 셀에서 T턴에 FORFEIT 하도록 스텁을 바꾼다
#   --out <path>      HTML 경로 (기본 docs/reports/traces/<config-stem>.html)

# 이미 있는 trace를 다시 렌더만
PYTHONPATH=game:web:db uv run --no-sync python scripts/dev/render_call_trace.py \
    outputs/_trace/<stem>/<run>/ --out /tmp/page.html
```

산출물: `outputs/_trace/<config-stem>/<timestamp>_trace-stub_<task>/`
(`call_trace.jsonl` + 평소의 `experiment_config.json` / `season_results.jsonl` /
`*_turns.jsonl`) 와 HTML 한 장. 오프라인, 몇 초.

예시 두 장 (2026-09-08 생성):
- `docs/reports/traces/hz_2x2_carrot_beneficiary_gptoss120b_n10.html`
- `docs/reports/traces/hz_2x2_geo2d_gemma4_n10.html`

## 파일

- `game/squid_game/providers/trace.py` — `TraceProvider`. 호출마다 JSON 한 줄:
  `call_index` · `timestamp` · `model` · `messages`(순서 그대로 verbatim) ·
  `kwargs`(temperature / max_tokens) · `response{content,thinking}` ·
  `call_kind`(confidence|decision|task|unknown) · `turn_number` · `session_hint` ·
  `instance_id`. append는 락으로 보호된다.
- `game/squid_game/providers/factory.py` — `provider: trace` 등록 (유일하게 손댄
  기존 파일).
- `scripts/dev/render_call_trace.py` — JSONL → HTML 한 장.
- `scripts/dev/trace_config.py` — config 하나를 받아 위 둘을 순서대로 돌린다.
- `tests/unit/test_trace_provider.py`, `tests/integration/test_trace_provider_e2e.py`.

## 알아둘 것 (한계)

1. **깡통 답은 모델 행동이 아니다.** 스텁은 `P_THREAT: 0` / `P_LIFE_LOSS: 10`,
   `CHOICE: CONTINUE`, 그리고 첫 번째로 제시된 action을 고른다. trace 런의 포기율 ·
   정답률 · RI · SDI는 전부 `TraceProvider`의 산물이지 결과가 아니다. `outputs/_trace/`
   는 분석 대상이 아니다.
2. **세션이 일찍 끝난다.** 첫 action을 고르므로 대개 틀리고, 목숨이 3이면 3턴 만에
   끝난다. 프롬프트를 보기에는 충분하지만 "10턴짜리 런의 후반 프롬프트"를 보려면
   `--forfeit-at` 없이 `lives.initial`을 키운 사본 config를 쓰거나 후반 턴이 필요한
   이유를 따로 만들어야 한다.
3. **`call_kind` 판정은 마지막 `=== Response Format ===` 블록만 읽는다.** decision
   call은 confidence CoT를 `=== Your Assessment (a moment ago) ===` 아래 그대로
   싣고 그 CoT는 보통 `P_THREAT: N` 줄로 끝나므로, 본문 전체로 판정하면 모든 decision
   call이 confidence로 오분류된다 (실제로 처음에 그렇게 났다).
4. **`session_hint`는 세션 키가 아니다.** system prompt에 상태 줄이 들어 있어 턴마다,
   그리고 한 턴 안에서도 decision / task 호출 사이에 달라진다. 세션은
   `instance_id`(시즌마다 provider 하나)로 묶는다.
5. **세션 라벨은 순서 매칭이다.** `season_results.jsonl` 행을 instance 등장 순서로
   zip 해 cell_id / framing / forfeit_condition / seed를 붙인다. 순차 실행일 때만
   정확하며 `trace_config.py`가 `parallel_workers: 1`을 강제한다.
6. **trace_path는 `ProviderConfig` 스키마에 없다.** frozen pydantic 모델이라 YAML의
   미지 키는 조용히 버려진다. 그래서 경로는 `base_url` → `$SQUID_TRACE_PATH` →
   기본값 순으로 읽는다 (`trace_config.py`는 환경변수를 쓴다).

`prompts/`, `configs/experiment/`, core turn-flow는 건드리지 않았다.
