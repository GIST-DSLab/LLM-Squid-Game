# 논문 ARR 판 작업본의 남은 기록 (2026-09-30)

`paper` 서브모듈 워크트리 `.scratch/worktrees/paper-arr2026`(브랜치 `arr2026-20260930`, 커밋 `5c1dfaa`)을 2026-10-16에 지우면서, 다른 곳에 사본이 없던 파일만 옮겼다. 경로는 워크트리 안 경로 그대로다.

| 파일 | 내용 |
|---|---|
| `docs/arr2026-revision-review.md`, `docs/arr2026-revision-factbase.md` | ARR 원고 수정 검토 · 사실 근거 메모 |
| `docs/arr2026-source-manifest.json` | ARR 원고 출처 목록 |
| `docs/arr2026-before-design-update/` | 09-30 설계 갱신 전 ARR 판 PDF(en · ko)와 소스 zip |
| `docs/sources/2026-09-30-design-update/provenance.json` | 설계 갱신 자료의 출처 기록 |
| `arr2026/README.md`, `arr2026/validation.json`, `arr2026/results/data/e51_v9_summary.json` | ARR 빌드 설명 · 검증 기록 · 5.1 v9 요약 |

옮기지 않은 것과 그 이유:

- 원고 `.tex`, `build_arr2026.sh`, `main_arr2026.tex` 등은 09-30 미커밋 초안이다. 10-01에 paper `ARR` 브랜치에 커밋된 판이 그 뒤를 잇는다(커밋 `ba96719` 등, 10-11 `e86b64d`에서 ICML 전환으로 삭제되었지만 git 기록에 있다). 최종 PDF는 `paper/dist/{en,ko}_arr2026_2026-10-01.pdf`.
- `docs/sources/2026-09-30-design-update/`의 나머지 파일은 root에 같은 내용이 있다: `e5x.html`은 `docs/reports/artifacts/squid5-setting/2026-09-30/`, `FINAL_design_r9.md`는 `docs/history/e52-arena-loop-2026-09-30/`, 분석 행 · 스크립트는 `result/2026-09-30/e51_v9/runs/e51_v9_20260930/`.
- 나머지 `dist/` PDF와 그림은 `paper/`에 같은 파일이 있다.
