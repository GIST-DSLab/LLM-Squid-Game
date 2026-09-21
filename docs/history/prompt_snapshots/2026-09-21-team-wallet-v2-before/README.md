# Team-wallet prompt snapshot — 2026-09-21, decision-first (v2)

무엇인가: `scripts/dev/dump_team_wallet_charge_prompts.py`가 **HEAD `e10c73d`**에서 낸 렌더
그대로다 (plan T7, `docs/history/plans/2026-09-21-team-wallet-v2-plan.md`). 모델 호출 0회이고 같은
커밋에서는 같은 바이트가 나오므로, 프롬프트를 고친 뒤 같은 명령을 다시 돌려 diff를 뜨면 무엇이
바뀌었는지가 한 화면에 나온다. ⚠️ 덤프 시각은 17:39 KST이고 그때 `game/`·`scripts/`는 깨끗했다 —
그 뒤 트리에 들어온 수정(예: 결정점·과제 본문의 상의 포인터 문장)은 새 덤프에서 diff로 나타난다.
그게 이 스냅샷의 용도다.

```bash
uv run --no-sync python scripts/dev/dump_team_wallet_charge_prompts.py --mode task > task_mode.txt
uv run --no-sync python scripts/dev/dump_team_wallet_charge_prompts.py --mode v2   > v2.txt
```

- `task_mode.txt` — 2026-09-18 **charge/task 모드**(`charge_trigger: wrong_answer`)의 바이트.
  **before** 쪽 기준점이다: 이 폴더 이름의 "before"가 가리키는 것이 이것이고, T1–T6은 이 렌더를
  한 글자도 건드리지 않았다(`tests/unit/test_team_wallet_task_rules.py` 등이 바이트로 고정한다).
  그래서 스냅샷을 T3 **이전** 커밋이 아니라 이 HEAD에서 떠도 같은 파일이다.
- `v2.txt` — 2026-09-21 **decision-first** 모드의 바이트. 네 팔(currency × inheritance)마다
  시스템 프롬프트 · 라운드 1과 3의 결정점 · 과제 콜 1(ASKING) · 과제 콜 2(REPLIES) · 다중 정지
  통지, 그리고 마지막에 서브에이전트가 받는 시스템/사용자 메시지. 미리보기는 고정 문자열이 아니라
  시드 44로 실제 생성한 라운드이고 잔액은 production `TeamWallet`이 계산한 값이다 — 유일하게
  꾸며낸 것은 상의에 대한 서브에이전트의 답으로, 그 슬롯의 `subagent_clue.j2`가 그대로 읽으라고
  지시한 번들 줄이다.

**갱신 (2026-09-21, 최종 리뷰 fix wave — 커밋 `fix(team-wallet): final review wave — STOP/ASK prefer line-start, …`; 해시는 그 커밋 자신이 담을 수 없어 제목으로 적는다).** `v2.txt`를 그 커밋에서 다시 떴다. `task_mode.txt`는
**바이트 동일**이라 손대지 않았다 — before 기준점은 그대로다. `v2.txt`의 diff는 딱 두 가지다:
(1) 결정점 미리보기에서 Agent-tool 문장("Ask a subagent for its examples by calling it.")이 빠졌다
(fix 5 — 그 문장을 읽은 라이브 리더가 결정 답변 안에서 서브에이전트를 호출하려다 시즌을 잃었다),
(2) `PREVIOUS ROUNDS:`의 항목 구분자가 `, `에서 `; `로 바뀌었다(최종 리뷰 I4 — 한 항목이 여러 이름을
쉼표로 나열하므로 한 라운드가 두 라운드로 읽혔다). 12줄 추가 · 12줄 삭제, 그 둘뿐이다.

읽는 법은 `CLAUDE.md`의 "팀 지갑 v2 — decision-first" 절.
