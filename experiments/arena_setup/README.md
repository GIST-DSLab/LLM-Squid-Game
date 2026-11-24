# experiments/arena_setup/

아레나(5.2) 셋업을 만드는 동안만 쓴 런 설정. 논문의 런도, 웹 로비의 좌석도 이 설정을 쓰지 않는다. 확정한 설정과 웹이 읽는
설정은 `squid/configs/`에 있다(11-24 연구자). 모두 `mode: game`이라 실험 모듈(`__init__.py`)은 없다.

| 설정 | 무엇을 하던 것 |
|---|---|
| `e52v33_docker_{fable,luna,opus,sol}4.yaml` | v33 기본 조건을 CLI 좌석 샌드박스(`squid/docker/`)에서 돌려 보던 설정. 기본 조건 런은 `public_*`로 돌았다 |
| `e52v33_ko_gptoss4.yaml` | 한국어 프롬프트(`lang: ko`) 시험 |
| `e52v36_public_luna4.yaml` | v36 공동 SOLVE 시험 런(`result/2026-11-22/e52_v36/`) |

지워도 엔진·웹·테스트는 그대로 돈다(`tests/`는 이 설정들이 아직 읽히는지만 본다).
