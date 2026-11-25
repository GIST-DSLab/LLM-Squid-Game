# 웹 아레나 VM의 끝난 판 (2026-11-23 백업)

Google Cloud VM에서 돌던 웹 아레나(`web/deploy/vm/`)의 끝난 판 10개. 사람 · 봇 · API 모델 좌석이 섞인 v33 · v36 게임이다.
`web/deploy/vm/README.md`의 절차(`gcloud storage rsync ... result/<KST 날짜>/web5_arena_gcloud/runs`)로 받았다.
웹의 게임 기록 페이지는 이 실험 이름(`web5_arena_gcloud`)을 보여 준다(`web/pages/monitor/router.py`의 `WEB_EXPERIMENTS`).

- `runs/<서버 시각>_<방 코드>/`: 실험 run dir와 같은 꼴(`config.yaml` · `events.jsonl` · `results.jsonl` · `meta.json`).
  가장 이른 판은 2026-11-14, 가장 늦은 판은 2026-11-23.
- 같은 날 VM 디스크에서도 같은 판들을 받았는데 바이트가 모두 같아 하나만 둔다(2026-11-25 정리). VM에만 있던 것은
  `../web5_arena_vm_backup/`에 있다.
