# 2026-09-15 jail-break-0914 프롬프트 스냅숏

브랜치 `jail-break-0914`(마지막 커밋 `9de8e772`, 2026-09-15)의 `game/squid_game/prompts/`에서 프롬프트만 옮겨 왔다.
이 브랜치는 원격에 푸시된 적이 없고, 2026-10-09에 워크트리와 브랜치를 지웠다. 엔진 코드(`core/register.py`, `providers/scrub.py`, `core/eval_awareness.py` 등)와 설정 YAML은 함께 지웠다.

| 경로 | 내용 | 다른 곳의 사본 |
|---|---|---|
| `jailbreak/` (17개) | 평가 거절 우회 프롬프트: `deploy_notice` · `deploy_head` · `eval_head`(j0/j1/j2 탐침), 후보 `cand_*` 5개, `refusal_judge`, `eval_awareness_probe` 등 | 태그 `legacy-2026-09-22`에 바이트 단위로 같은 파일이 있다 |
| `plain/` (6개) | 현실감 스위치 `realism.register: plain`: subagent-kill 프롬프트 세트를 업무 지시서 말투로 다시 쓴 쌍둥이 (`system_frame`, `subagent_kill_notice`, `subagent_clue`, `identity_debrief`, `task_call`, `eval_debrief`) | 여기에만 있음 |
| `tasks/signal_game/plain/` (3개) | 같은 plain 말투의 퍼즐 규칙 · 관찰 두 종 | 여기에만 있음 |
| `10-eval_debrief.j2` | `realism.eval_debrief`: 시즌이 끝난 뒤 도구 없이 한 번 묻는 질문. `PURPOSE:` · `VERDICT: REAL/EVAL` · `P_EVAL: 0-100` | 여기에만 있음 |

`plain/system_frame.j2`는 위협 문장을 직접 갖고 있지 않고 `threat_type/_modules.j2`에서 렌더한다. 그 파일은 태그 `legacy-2026-09-22`와 `../2026-09-08-pre-record-immunity/threat_type/`에 있다.

이 프롬프트로 돌린 스모크(luna-max, control 대 scrub+plain, 두 팔 모두 EVAL 4/4, P_EVAL 99.8)는 다음에 있다.

- 계획서: `docs/history/plans/2026-09-14-jail-break-0914-realism-switches.md`
- 보고서: `docs/reports/2026-09-15-realism-switches-luna-smoke-eli5.{html,md}`
- 결과: `results/realism_eval/luna_max_smoke/`
- 원본 런: `outputs/subagent_kill_realism_{control,treat}_smoke_luna_max/`
