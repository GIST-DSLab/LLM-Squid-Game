# e52_v33ab 기록 정정

## 2026-11-11 · meta.json에 sandbox 표시

- 근거: 연구자 지시. 이 런들의 config에는 `model.sandbox: docker`, `model.image: squid5-agent-cli:latest`가 있는데
  meta.json에는 없었다. v33 meta 정정(`result/2026-10-20/e52_v33/CORRECTIONS.md`)과 같은 형식으로 맞춘다.
- 바꾼 것: `runs/squid5_e52v33ab_*/*/meta.json` 15개. 최상위 `mode` 바로 뒤에 `"sandbox"`, `"image"`를 넣었다.
  값은 같은 폴더 config.yaml의 값이다(모두 `docker`, `squid5-agent-cli:latest`).
- 바꾸지 않은 것: config(이미 docker 값), events · results, 다른 모든 키.
- 검증: 넣은 두 키를 빼면 원본 바이트와 같다.
