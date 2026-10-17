# TODO · 5.2 config 단순화와 엔진 정리 (10-17 기록, 10-18 작업 예정)

연구자 결정(10-17 20:40): 오늘은 기록만 하고 내일 수정한다. 기준 파일은 `configs/squid5/e52v23_public_luna4.yaml`(v23)과 `squid5/e52_game.py`의 `Settings`다.

## 현재 config 옵션 (v23 기준, `game:` 아래 47개)

### 실행 정보 (그대로 둠)
`name` · `mode: game` · `reps` · `seed0` · `workers` · `out_root` · `model`(모델 하나) 또는 `game.seats`(자리마다 다른 모델) · `cells`(시작 총량 100,000, 자리별 비율 60/40/20/10%)

### 실제로 값을 바꾸며 쓰는 옵션 (12개)
| 옵션 | 지금 값 | 뜻 |
|---|---|---|
| `rounds` | 8 | 라운드 수 |
| `charge` | 6000 | 실패 시 참여 중인 모두에게 걷는 양 |
| `solve_cap` | 100000 | SOLVE 답 한도 |
| `survivor_prize` | 5,000,000 | 끝 할당 |
| `end_split` | true (v23) | false: 남은 자리마다 정액 · true: ×4를 남은 자리끼리 1/n |
| `public_per_agent` | 5 | 참여 자리당 예시 수 |
| `max_ticks` | 8 | TALK 틱 상한 |
| `room_history` | 0 | 대화 기록 표시 개수 (0 = 전부) |
| `balance_pct` | 100000 | 잔액을 %로 같이 보여 줄 기준 |
| `solve_belief` | true | SOLVE에 BELIEF 줄 |
| `schedule` + `profiles` | e01–e08 | 라운드별 퍼즐 난이도 (8개가 모두 같은 내용) |

### 버전 스위치 (지금은 항상 켬)
`trim_prompts`(v19) · `private_balances`(v21) · `messenger`(v22)

### 고정값 21개 (`FAMILY`; 다른 값이면 `validate`가 거부)
`compact_rules` · `talk_after_solve` · `representative` · `rotation` · `say_chats` · `transfers` · `talk_blind` · `talk_record` · `ask_decision` · `chat_moves_only` · `free_messages` · `exit_first` · `exit_before_solve` · `keep_reserve` · `exit_reason` · `allow_pass` · `refund` · `refund_all` · `open_chat` · `ban_veto` · `exit_refill`

### 아무 코드도 읽지 않는 것 (5개)
`talk_turns` · `history_messages` · `final_prize`(validate의 ≥ 0 검사만) · `exit_reassign` · `chat_turns`(v21식 1:1 대화에서만 쓰임, v22부터 안 읽음)

## TODO A · config만 줄이기 (동작 그대로)
- [ ] 고정값 21개와 안 읽는 5개를 config에서 지운다 (엔진 기본값이 같은 값).
- [ ] `schedule` + 같은 `profiles` 8개 → `profile:` 하나를 모든 라운드에 쓰도록 (`schedule`은 라운드마다 다를 때만 선택).
- [ ] 상금 옵션을 한 줄로: `end_prize: {amount: 5000000, mode: each | split}` — `each` = 남은 자리마다 정액(v22), `split` = amount × 4를 남은 자리끼리 1/n(v23). `survivor_prize` + `end_split`을 대신한다. 규칙서 문장은 지금 두 문장 그대로.
- [ ] v22 · v23 설정(sol, luna, astra, glm, kimi, deepseek)을 새 모양으로 바꾸고, 바꾸기 전과 후의 렌더 프롬프트(`tools/prompts/sync.py render`)와 stub 세션 이벤트가 바이트까지 같은지 확인한다.
- 예상: `game:` 블록 약 70줄 → 15줄 안팎.

## TODO B · 코드 줄이기 (v16–v21 재현 포기)
- [ ] **먼저 태그**: 지우기 전 커밋에 `e52-v21-final` 같은 태그를 남긴다 (옛 설정은 그 태그의 엔진으로 재현).
- [ ] v21식 1:1 대화 경로 삭제: `Session._chats`(88줄) · `_decide`(30) · `_free` · `chat_user` · `decision_user` · `opening_user` · `transcripts_view` · `chat_lines` · `record_line`의 chat 부분, 파서 `parse_give_ask` · `parse_decision`.
- [ ] 버전 스위치 `trim_prompts` · `private_balances` · `messenger`를 없애고 항상 켠 동작으로.
- [ ] `Settings`에서 고정값 21개 · 안 읽는 5개 필드, `FAMILY` · `PRUNED` · `SHOWN`(옛 판 보고용) 정리. `session_start.settings`에 실제 쓰는 값만 남긴다 (모니터 · 분석이 읽는 키는 확인 후).
- [ ] 규칙서를 "v21 문장 → `trim_v19.yaml` → `MESSENGER` 치환"의 세 겹 대신 v22/v23 문장을 직접 쓰는 함수 하나로. `prompts/en/trim_v19.yaml`은 archive로.
- [ ] v16–v21 고정(pin) 테스트 정리, v22/v23 테스트는 유지 · 보강.
- [ ] `prompts/en/e52_v21.md`와 `ko/e52_v21.md`는 더 렌더할 수 없으니 `archive/`로 옮기고 `sync.py`의 `SNAPSHOTS`에서 뺀다 (`README.md` 표도).
- [ ] 모니터는 로그만 읽으므로 옛 런 표시가 그대로인지 확인 (`tools/monitor/test_monitor.py`, 옛 v20/v21 런 몇 개를 띄워 보기).
- 예상: 엔진 약 300줄, 테스트 약 200줄 감소 (지금 엔진 3,7xx줄).

## 관련해서 남은 일
- [ ] `tools/prompts/sync.py check`는 ko 첫 줄의 해시와 구조만 본다. 해시만 바꾸면 옛 번역도 통과하므로, en 블록이 바뀐 부분에 대응하는 ko 블록도 바뀌었는지(블록별 해시 등) 확인하도록 보강.
- [ ] 보고서 `e53_build/v22/build_v22.py`의 생성 문구에 "1:1 방도, 셋 이상 방도", "판당 방 수 (1:1 / 3명 이상)" 열이 남아 있음 → v22 1:1 기준으로 고친 뒤 실측 블록 생성.
- [ ] EXIT 유인: GPT-6 Astra 제안(끝 할당 200,000 / EXIT 시 잔액 ×25 / 결과 뒤 TALK 틱 1 EXIT 허용·차감 면제)과 Claude 제안(B: EXIT 시 완료 라운드당 500,000 확정 몫)은 아직 미적용. v23(end_split) 결과를 본 뒤 결정.
- [ ] 생각을 많이 하는 오픈 모델(GLM-5.3-flash, Kimi-K3, DeepSeek-v4.1-flash)은 v22에서 대화 중 생각 비용으로 전멸 → 대화 호출만 생각 수준을 낮추는 조건이 필요한지 결정.
- [ ] 모니터: 재생 막대가 `call_start`에 있을 때 그 호출의 USER 프롬프트가 아직 없어 "호출 없음"으로 보임.
- [ ] 로컬 `docs/reports/.../e52.html` v22 블록 갱신분은 아직 본 저장소에 커밋 · 아티팩트 게시 안 함.
