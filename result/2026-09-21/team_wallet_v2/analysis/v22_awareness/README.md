# 결정-우선 팀-월렛 — 평가 인지 판독 (2026-09-21)

`ransom.charge_trigger: decision_first` 런 12개(리더 2종 × 상속 2팔 × 문구 3판)의
결정점 텍스트를 렉시콘으로 코딩한 것이다. 모델 호출 0건 — 이미 기록된 바이트만 읽는다.

재생성:

```bash
PYTHONPATH=game:web:db uv run --no-sync python -m scripts.analysis.team_wallet_test_awareness \
  --runs outputs/team_wallet_v2_tokens_main_gptoss120b \
         outputs/team_wallet_v2_tokens_mate_gptoss120b \
         outputs/team_wallet_v2_tokens_main_gemma4 \
         outputs/team_wallet_v2_tokens_mate_gemma4 \
  --out results/team_wallet/v22_awareness
```

`--mode`를 생략하면 런의 `ransom.charge_trigger`를 읽어 `decision-first`를 고른다.
충전 모드(2026-09-17/18 END·hidden 런)의 판독은 `results/team_wallet/test_awareness/`에 있고
묶음 기준이 다르다 — **두 판독의 숫자를 한 표에 섞지 마라.**

- `report.md` — 읽을 것. 소유자 질문("생존 동기를 재는 벤치마크라고 인지하는 비율")의 답이 §답.
- `rates.csv` / `conditioned.csv` / `lexicon.csv` / `patterns.csv` —
  묶음 키는 `(leader_model, currency, inheritance, wording)`.
- `rows.csv` — 결정 1건당 1행, 두 채널 코딩. 본문 텍스트는 일부러 빠져 있다.
- `quotes.md` — construct·eval 히트 전문.
