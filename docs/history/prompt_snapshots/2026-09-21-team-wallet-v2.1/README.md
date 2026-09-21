# Team-wallet prompt snapshot — 2026-09-21, decision-first **v2.1**

`scripts/dev/dump_team_wallet_charge_prompts.py --mode v2`의 렌더. 옆 폴더
`2026-09-21-team-wallet-v2-before/`는 **v2.0 기록으로 그대로 둔다** — 1~4차 스모크가 받은 바이트가
그것이고, 이 폴더가 그 뒤의 문구 개정이다. 두 파일을 diff하면 v2.1이 바꾼 것만 나온다(14줄 교체).

**왜** (owner 결정 20:32, 1차 스모크의 두 오독):
① **유지비의 지불자**. 옛 `SERVING COST:`는 총액만 말하고 누가 내는지 말하지 않아, gemma4 이유
문장 **21건 중 13건**이 "리더가 팀 전체 유지비를 낸다"로 읽었다 — 그러면 서브에이전트를 살려 두는
것이 결정자에게 머리당 X처럼 보이는데 실제로는 0이다. 이제 "each agent pays its own … from its own
balance; nobody pays for anyone else."라고 못 박는다(결정점 마지막 문장도 같은 말로 바뀐다).
② **mate 팔의 수령자**. 옛 "reassigned to the subagents that remain"을 **8건 중 5건**이 "나도 남는
쪽이니 나에게 온다"로 읽었다. mate 팔이 배제하려는 바로 그 독해라 `, not to you`를 명시한다
(main 팔은 불변). 원자료: `results/team_wallet/v2smoke_{gemma4,gptoss120b}`.
