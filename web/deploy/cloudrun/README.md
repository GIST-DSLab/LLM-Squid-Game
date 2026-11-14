# web5 아레나 API를 Google Cloud로 (Render 대체)

2026-11-14 준비. 계정은 연구실 sundonglab@gmail.com, 리전은 서울(`asia-northeast3`).

## 구성

| 무엇 | 어디 | 왜 |
|---|---|---|
| API 서버 | Cloud Run 서비스 `squid5-arena` (인스턴스 1개, 항상 켜짐, CPU 상시 할당) | 방과 판 진행이 프로세스 메모리와 백그라운드 스레드에 있다(`web/server/app.py` `rooms`, `engine.Room` 스레드). 인스턴스가 둘이 되거나 0으로 줄거나 CPU가 요청 밖에서 멈추면 진행 중인 판이 깨진다 |
| 게임 이벤트 | Cloud SQL Postgres 16 `arena-pg` / DB `arena` (`WEB5_DSN`) | 진행 중에도 한 줄씩 쌓임(`web/server/store.py`). 매일 백업 + 시점 복구(14일). 연결이 끊기면 한 번 다시 연다 |
| 끝난 판의 런 폴더 | Cloud Storage `gs://<프로젝트>-arena-runs/runs/<날짜_시각_방코드>/` (`WEB5_GCS_BUCKET`) | 판이 끝나면(끝남·멈춤·오류) `config.yaml` `meta.json` `events.jsonl` `results.jsonl`을 올림(`web/server/archive.py`). 분석 도구가 읽는 형식 그대로. 버전 관리 켬 |
| 키 | Secret Manager `ollama-api-key`, `web5-dsn` | 이미지와 git에 키가 들어가지 않음 |
| 이미지 | Artifact Registry `web5` (Cloud Build로 빌드) | `web/deploy/Dockerfile` 그대로 |

프런트엔드는 GitHub Pages에 그대로 둔다. 전환할 때 `web/frontend/config.js`의 `WEB5_API`만 Cloud Run 주소로 바꾼다.

## 순서

```bash
# 0. 이 컴퓨터의 gcloud에 연구실 계정으로 로그인 (브라우저가 열림)
gcloud auth login sundonglab@gmail.com
gcloud auth application-default login   # 로컬에서 버킷 읽기용 (선택)

# 1. 프로젝트 (새로 만들 때; 결제 계정 연결은 콘솔에서)
gcloud projects create <프로젝트ID> --name "LLM Squid Game Arena"
gcloud billing projects link <프로젝트ID> --billing-account <결제계정ID>

# 2. 한 번만: API, 버킷, DB, 비밀, 서비스 계정 (OLLAMA_API_KEY는 이 사이트 전용 키를 환경변수로)
PROJECT=<프로젝트ID> bash web/deploy/cloudrun/deploy.sh setup

# 3. 빌드와 배포 (코드를 바꿀 때마다)
PROJECT=<프로젝트ID> bash web/deploy/cloudrun/deploy.sh deploy

# 4. 확인: 판 하나를 끝까지 두고 → 서비스 재배포(3번 다시) → 그 방의 이벤트가 DB에서, 런 폴더가 버킷에서 나오는지
curl "$(PROJECT=<프로젝트ID> bash web/deploy/cloudrun/deploy.sh url)/api/health"
gcloud storage ls gs://<프로젝트ID>-arena-runs/runs/

# 5. 전환: web/frontend/config.js 의 WEB5_API 를 Cloud Run 주소로 바꿔 main에 push (Pages 재배포), Render 서비스 정지
```

## 데이터 내려받기

```bash
gcloud storage rsync -r gs://<프로젝트ID>-arena-runs/runs result/<KST 날짜>/web5_arena_gcloud/runs
```

받은 폴더는 `tools/monitor`와 리더보드 코드가 바로 읽는다. DB의 이벤트는 Cloud SQL Studio(콘솔)나 `gcloud sql connect arena-pg --user arena --database arena`로 본다.

## 비용 (대략, 2026-11 기준 확인 필요)

- Cloud Run 1 vCPU · 1 GiB 상시 켜짐: 1 Tier 단가(vCPU초 $0.000018, GiB초 $0.000002)로 월 약 $52. 서울은 2 Tier라 이보다 높음 → 월 $55~75로 잡음.
- Cloud SQL `db-f1-micro` + SSD 10 GB + 백업: 월 $12~18.
- Cloud Storage, Secret Manager, Artifact Registry, Cloud Build: 월 $1 안팎.
- 합계 월 약 $70~90. 더 줄이려면 Cloud Run 대신 Compute Engine `e2-small` VM 하나에 같은 이미지를 띄우는 방법(월 $15 안팎 + DB)이 있다.

## 주의

- 사람 참여 데이터를 모으기 전에 동의 화면(IRB)이 필요하다. 아직 없다.
- `--max-instances 1`을 늘리지 말 것(방이 한 인스턴스 메모리에만 있음).
- 재배포하면 진행 중인 판은 끊긴다(끝난 판은 DB와 버킷에 남음). 판이 없는 시간에 배포한다.
