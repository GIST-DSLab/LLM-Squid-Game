# web5 아레나 API를 Google Cloud VM 하나로 (Render 대체, 채택안)

2026-11-14. 계정 sundonglab@gmail.com, 새 프로젝트, 서울 리전(`asia-northeast3-a`). 연구자 요구: 접속이 느리지 않을 것
(콜드 스타트 없음). VM은 항상 켜져 있으므로 첫 요청도 바로 응답한다. Cloud Run안은 `../cloudrun/`(쓰지 않음, 참고용).

## 구성

- VM `arena-vm` (`e2-small`, Debian 12, 디스크 30 GB, 고정 IP `arena-ip`) 위의 Docker Compose(`compose.yaml`):
  - `app`: `web/deploy/Dockerfile` 이미지 그대로. 이벤트는 SQLite `/opt/arena/data/arena.db`, 진행 중 런 폴더는
    `/opt/arena/data/runs/`(모두 VM의 영구 디스크라 재시작해도 남음).
  - `caddy`: HTTPS. 주소는 `https://<IP를 -로 이은 것>.sslip.io` (연구실 도메인이 생기면 `SITE_HOST`만 바꾼다).
- 끝난 판의 런 폴더는 버킷 `gs://<프로젝트>-arena-runs/runs/`에도 올라간다(`web/server/archive.py`, 버전 관리 켬).
- 디스크 스냅숏 매일(14일 보관, 정책 `arena-daily`).
- Ollama 키는 Secret Manager `ollama-api-key`; VM이 시작할 때 읽어 `/opt/arena/.env`(권한 600)에만 둔다.

## 순서

```bash
gcloud auth login sundonglab@gmail.com                 # 이 컴퓨터에서 한 번
gcloud projects create <ID> --name "LLM Squid Game Arena" --account sundonglab@gmail.com
gcloud billing projects link <ID> --billing-account <결제계정> --account sundonglab@gmail.com
OLLAMA_API_KEY=... PROJECT=<ID> bash web/deploy/vm/deploy.sh setup
PROJECT=<ID> bash web/deploy/vm/deploy.sh deploy      # 코드를 바꿀 때마다; 진행 중인 판은 끊기므로 빈 시간에
curl "$(PROJECT=<ID> bash web/deploy/vm/deploy.sh url)/api/health"
# 전환: web/frontend/config.js 의 WEB5_API 를 위 주소로 바꿔 main에 push(Pages), Render 서비스 정지
```

## 데이터

```bash
gcloud storage rsync -r gs://<ID>-arena-runs/runs result/<KST 날짜>/web5_arena_gcloud/runs   # 끝난 판
PROJECT=<ID> bash web/deploy/vm/deploy.sh ssh   # VM 안: /opt/arena/data/arena.db, /opt/arena/data/runs/
```

## 비용 (대략, 확인 필요)

`e2-small` 상시 + 디스크 30 GB + 고정 IP + 스냅숏 + 버킷: 월 $20~30. 느리면 `MACHINE=e2-medium`(월 +$15 안팎)으로
VM을 멈추고 `gcloud compute instances set-machine-type`로 바꾼다.
