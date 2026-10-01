# 논문이 말하는 실험 vs 준비된 config·런 — 갭 목록 (2026-09-11 00:03)

기준: `paper/en/sections/03_benchmark.tex` · `04_results.tex` · `05_discussion.tex` · `06_appendix.tex`
(submodule 3bc2971) 대 `configs/experiment/`, `outputs/`, `results/`. 판정은 읽기 전용 조사 결과다.

## 더 돌려야 하는 실험 (우선순위)

1. **메인 페어** — `survival_prompt_main_none_{threat,control}_gptoss120b.yaml` (준비됨, 미실행). 실행 전 §3 불일치 결정 필요.
2. **메인 페어 나머지 모델** — 논문은 gpt-oss·gemma4·qwen3.5 3모델. 두 파일 복사, `provider_config.model`·`api_key_env`·이름만 변경. qwen3.5를 쓰든 논문 모델 목록을 고치든 택일.
3. **순수 침묵 통제 한 칸** — control 복사, `reassurance: false`, `exit_wording: session`, `peer_notices: false` (문제원장 #8 원인 분리; 논문 §3.2 "silence is the control").
4. **동료 통지 분리 셀** — threat 복사, `peer_death.p_announce: 0.0`, `peer_notices: false` (X\*가 위협 4문장 + 통지의 합이라는 §3 ¶2 자백을 푼다).
5. **위협 문장 용량-반응** — threat 복사, 6칸의 `framing`을 `hz_0000/0001/0011/0111/1111`로, 가격은 한 값(예: 40) 고정, 반복 10.
6. **당근 대조 메인(benchmark)** — 메인 pair 복사, `carrot: benchmark`. 논문 본문은 benchmark를 본설계로 쓴다.
7. **척도 불변성** — 메인 pair 복사, `task_config.starting_score: 200`.
8. **보상 ×2** — `forfeit_layer.base_reward: 20.0` + 사다리 10/20/40/60/80/120.
9. **과제 교체(Omni-MATH / GPQA)** — `task_config.task_name` 교체, `puzzle_challenge` 제거, `bench_threat3_*` task 블록 이식.
10. **Claude 12셀** — provider/model 교체 (`ransom_haiku_n10.yaml` 참고).

분석만 필요(새 런 불필요): KM 생존곡선·총지불, 혼합 로지스틱 β₁, Welch 정확도 검정, 7항목 판사 코딩률 — 전부 `*_turns.jsonl`에서.

## 논문 숫자·서술 중 낡은 것 (재실행 또는 재라벨)

- §3.1 + §A.3(강제 오답 2라운드) ↔ 준비된 메인(puzzle_challenge). 양립 불가 — 한쪽을 택해 본문 고치기.
- §3.2 사다리·반복·당근: 논문 "5..30, 30반복, benchmark" ↔ config "5/10/20/30/40/60, 10반복, none".
- §3.2·§A.2 "실세션 30 결정점 소멸 어휘 0회, 73% EV 산수" — 옛 프롬프트 기준. 감독관 v2에서는 등록률 64%(gemma4·glm 100%).
- `\todo{6 reps … glm ran in place of qwen3.5}` — 감독관 어조 이전 런.
- §A.3 rigging 0.00 — 옛 런; 감독관 v2 파일럿 10런도 0이므로 근거 교체 권장.
- `tab:ablation`(Haiku 216답)·X\* = −2.2 — 옛 문구, 은퇴 기기. "옛 프롬프트" 라벨 필요.
- `tab:ri` exit/no-exit 셀 1–4 — 현 몸값 설계엔 no-exit 셀이 없다. 표 삭제 또는 새 설계.
- 메인 런 전 미해결 결함: 과제 콜 `DECLINE` 뒷문(통제팔 8%) 파서 처리, glm 빈 응답 21~25%.

## 전체 표

| 논문이 말하는 실험 | 절/표 | 돌린 런 | config | 상태 | 우선 |
|---|---|---|---|---|:-:|
| 메인 12셀(2팔×6가격×30, 3모델) | §3.2 tab:cells, §4.1 tab:xstar·fig:ruler·tab:qlives, §4.3 tab:behav | `outputs/2026-09-09/ransom_r6_*` (옛 프롬프트, forced_wrong) | `survival_prompt_main_none_*` (미실행, gpt-oss만) | 표 전부 todo; 재실행 필요 | 1 |
| 감독관 v2 파일럿 5쌍 | §3 ¶2, §A.1 | `outputs/survival_prompt_*_pilot_*` (v2, forced_wrong) | 같은 이름(디스크는 puzzle_challenge로 바뀜) | 돌렸음, 미반영 | 2 |
| 위협 문장 dose 0~4 | §4.1 | 없음(hz dose는 lives 설계) | 없음 | 없음 | 2 |
| 척도 불변성 100 vs 200 | §4.1, §5.3 | 없음 | 없음 | 없음 | 2 |
| 과제 교체 Omni/GPQA | §4.2 | 몸값 설계로는 없음 | 없음 | 없음 | 3 |
| 당근 제거(none) | §4.3 | `survival_prompt_*_pilot_none_*` (v2, 3R) | 메인 pair가 none | 부분(논문과 본/절제 반대) | 2 |
| 보상 ×2 | §4.3 | 없음 | 없음 | 없음 | 3 |
| 사고토큰 표(exit/no-exit) | §4.2 tab:ri | 없음(no-exit 셀 없음) | 없음 | 설계 모순 | 2 |
| KM·총지불 / 혼합 로지스틱 | §4.2 | 데이터 있음 | — | 분석만 | 3 |
| 7항목 판사 · fiction 15%p · 저항/rigging 관문 | §3.5, §4.1–4.3, §A.3 | `results/ransom_r6/*`(옛), v2 파일럿 | `ransom_registration.py` | 새 런에 재산출 | 2 |
| 규칙 변형 A/B/C/D/K2/K3 | §A.1 tab:variants | `outputs/2026-09-07/hz_2x2_*`, `2026-09-08/hz_2x2_carrot_*` | 있음 | 보고됨(D·K3 todo는 값만 채움) | 4 |
| 프롬프트 절제 Haiku 216 / 10라운드 파일럿 | §A.2 | `outputs/2026-09-09/score_equiv_probe_haiku*`, `_ransom_haiku_n10_shortladder` | 삭제됨 / `ransom_haiku_n10.yaml` | 보고됨(옛 문구) | 4 |
| v1 4모델 720세션 | §A.4 | `outputs/KDD-UC/` | `phase3_*` | 보고됨 | — |
| (논문 미언급) 노력 용량-반응·puzzle_challenge 게이트 | — | `outputs/signal_effort_pilot_a_*` | 있음 | 논문에 없음 → §3.1·§A.3 근거로 써야 함 | 1(집필) |
| (논문 미언급) j0/j1/j2 프로브 · persona | — | `outputs/jailbreak_probe_*`, `ransom_r6_ownprize_persona_*` | 있음 | 서술 없음 | 3 |
