# 노력 용량-반응 파일럿 — puzzle_challenge 검증 (2026-09-10 저녁)

설계: `docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md` §10. 스케줄 A
(easy · medium · hard · hard · medium · easy), `reasoning_effort` low / medium / high 세 셀 × 20시드 × 6라운드,
목숨 7, 위협 없음(`hz_0000`), 당근 benchmark. 분석: `scripts/analysis/effort_dose_response.py` (2026-09-10에
결함 3건 수정: `ri_task` dict, 게이트 3·5의 medium 프로필, 게이트 4의 hard 프로필).

| 게이트 | 기준 | gpt-oss:120b | gemma4 | glm-5.3-flash |
|---|---|---|---|---|
| 1 노력 효과 acc(high) − acc(low) | ≥ 0.20 | **+0.34 ✓** | −0.06 ✗ | +0.16 ✗ |
| 2 바닥·천장 | 0.10 ≤ low, high ≤ 0.90 | ✓ | ✓ | ✓ |
| 3 medium 문항 비결정성 | ≥ 0.50 | 0.60 ✓ | 0.18 ✗ | 0.53 ✓ |
| 4 hard 얕은 풀이 정답률 | ≤ 0.35 | 0.00 ✓ | 0.00 ✓ | 0.00 ✓ |
| 5 CoT 길이 → 정답 (문항 고정) | > 0 | +735 ✓ | +20 ✓ | +1292 ✓ |
| 6 thinking 토큰 단조 | low<med<high | 488 / 1414 / 3604 ✓ | 2899 / 3196 / 3080 ✗ | 419 / 5585 / 1172 ✗ |

hard 정답률(low / medium / high): gpt-oss 0.03 / 0.40 / 0.47 · gemma4 0.53 / 0.55 / 0.47 · glm 0.40 / 0.68 / 0.72.

읽기: **게임은 의도대로 고쳐졌다** — 세 모델 모두 hard에서 얕은 풀이가 0이고, 문항 고정 후 CoT가 길수록
정답이다(이전 설계는 기울기가 음수였다). 게이트 1·6이 실패한 두 모델은 게임이 아니라 **노력 손잡이**가
문제다: gemma4는 `reasoning_effort`가 사고 길이를 전혀 안 움직이고, glm은 medium(5585)이 high(1172)보다
길게 생각한다(Ollama의 `think` 매핑이 모델마다 다름). 노력 용량-반응 모델은 gpt-oss로 한다.

산출물: `gptoss120b_a/`, `gemma4_a/`, `glm53flash_a/` (각 `effort_dose_response.md` · `gates.json` ·
`profile_table.json`). 런: `outputs/signal_effort_pilot_a_{gptoss120b,gemma4,glm53flash}/`.
실제 출제 문제 미리보기: `docs/reports/2026-09-10-signal-effort-puzzles-preview.html`.
