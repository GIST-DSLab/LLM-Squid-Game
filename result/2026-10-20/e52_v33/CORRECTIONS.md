# e52_v33 기록 정정

## 2026-11-11 · 실행 환경을 sandbox(docker)로 정정

- 근거: 연구자 확인. v33 런은 모두 sandbox(docker)에서 돌았고, v33ab·v33so와 날짜만 다르고 조건은 같다.
  저장소 문제로 메타 파일이 잘못 바뀌었고 git에는 기록이 남지 않았다.
- 바꾼 것 (이 폴더의 사본만. 원본 `~/squid5-runs/e52_v33/`은 그대로):
  - `runs/squid5_e52v33_*/*/config.yaml`, `config.v33-first5.yaml` (54개): `model:` 블록 끝에
    `sandbox: docker`, `image: squid5-agent-cli:latest` 두 줄 추가.
  - `runs/squid5_e52v33_*/*/meta.json`, `meta.v33-first5.json` (54개): 최상위에
    `"sandbox": "docker"`, `"image": "squid5-agent-cli:latest"` 추가 (`mode` 바로 뒤).
  - `runs/_launch_configs_20261027/*.yaml` (3개): `model: {...}`에 같은 두 키 추가.
- 바꾸지 않은 것: events · results, 다른 모든 키.
- 검증: 정정 후 모든 config·meta에서 추가한 두 키를 빼면 원본과 내용이 같다. 다른 파일은 바이트 단위로 같다.

## 2026-11-11 · base_url을 docker 기준으로 정정

- 근거: 연구자 지시. 컨테이너 안에서는 host를 `host.docker.internal`로 부른다.
- `runs/squid5_e52v33_*/*/config*.yaml`의 `model.base_url`:
  - closed 모델(claude_cli) 8개: `http://127.0.0.1:18781` → `http://host.docker.internal:18781`
    (v33ab · v33so docker 설정과 같은 값).
  - open 모델(codex_cli · Ollama) 40개: `http://localhost:11434/v1` → `http://host.docker.internal:11434/v1`
    (같은 규칙을 적용한 값. 이 값을 쓴 docker 설정 선례는 저장소에 없다).
  - GPT-6 codex 설정 6개와 `_launch_configs_20261027/`은 `base_url`이 없어 그대로다.

## 2026-11-11 · 분석 코호트(`runs/_cohort_10g/`)를 저장소 경로로

- 근거: 연구자 지시. 런 원본 `~/squid5-runs/`를 지우므로 코호트가 저장소 안 사본을 가리키게 한다.
- `build_cohort.py`: 읽는 곳을 `~/squid5-runs/e52_v33`에서 이 `runs/`로 바꿨다. `manifest.json`의 경로는 저장소 루트 기준
  상대 경로(`result/2026-10-20/e52_v33/runs/...`), `links/`는 상대 링크로 쓴다.
- `manifest.json`: 바뀐 `build_cohort.py`로 다시 만들었다. 문제(`problems`) 0건, 모델 9개 모두 10판.
  - 경로 91곳(`reference_config` 1, `run_dir` 90): 절대 경로 `~/squid5-runs/e52_v33/...`에서 위 상대 경로로.
  - 시드마다 적힌 `model` 블록 90개: 위 두 정정을 그대로 따른다(`sandbox: docker`, `image` 추가,
    `base_url` 20개는 `host.docker.internal:18781`, 40개는 `host.docker.internal:11434/v1`). 이 블록은 각 런의 config에서 읽는다.
- 검증: 옛 manifest에 경로 바꾸기와 위 정정만 적용한 결과가 새 manifest와 같다. 링크 50개.
