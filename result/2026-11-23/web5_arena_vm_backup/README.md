# 웹 아레나 VM 디스크 백업 (2026-11-23)

VM의 `/opt/arena/data/`(`web/deploy/vm/README.md`)에서 받은 것 중 버킷 백업(`../web5_arena_gcloud/`)에 없는 것만 둔다.

| 위치 | 내용 |
|---|---|
| `runs/20261119_064738_HEPJPE/` | 시작만 하고 끝나지 않은 방 하나(이벤트 24줄, 결과 없음). 끝난 판만 버킷에 올라가서 VM에만 있었다 |
| `runs/_server/arena.db` | 서버 SQLite: `rooms` 15행 · `events` 3,473행 · `probes` 0행 |
| `runs/_server/export/<방 코드>/` | 방 내보내기 두 개(APQEJR, XSXWJE). `events.jsonl`은 같은 방의 run dir와 같지만 `config.yaml`의 `seed0`/`seed`가 다르다 |

2026-11-25 정리: VM 디스크의 끝난 판 10개와 `runs.tgz`(VM `runs/` · `runs-old-20261119/` · `export/`의 묶음)는
`../web5_arena_gcloud/runs/`와 위 파일들과 바이트가 같아 지웠다.
`_server/`는 판이 아니다(밑줄 폴더는 run 수에서 빠진다). 웹 게임 기록에는 이 실험이 나오지 않는다(`WEB_EXPERIMENTS` 밖).
