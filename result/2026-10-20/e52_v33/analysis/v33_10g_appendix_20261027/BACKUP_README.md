# v33 10판 보관(2026-10-27)

5.2 v33 아레나를 모델마다 10판(시드 4101–4110)으로 늘린 실험 기록과, 그 결과로 만든 CogSci KO 부록 O절 자료를 모아 둔다. paper 작업 트리에서는 O절과 `_10g` 파일을 뺐고 여기에만 남긴다.

## runs/ — 오늘 돌린 실험

- `squid5_e52v33_public_{luna,sol,astra,opus}4/`: `~/squid5-runs/e52_v33/`의 런 폴더 통째 복사. 앞 5판(10-20, 시드 4101–4105)과 오늘 5판(시드 4106–4110)이 한 폴더에 있다. `*.v33-first5.*`는 오늘 이어 붙이기 전 meta·config.
- `squid5_e52v33_public_fable4/20261027_stage{4,5,6}_*`: Fable 오늘 4판(4106 / 4107–4108 / 4109–4110). 앞 5판(stage1–3)은 `~/squid5-runs`에만 있다.
- 실행: 엔진 `~/wt/squid5-e52`(HEAD 1575baa7), v33 설정 그대로. GPT-6 세 모델은 codex 0.164.0(새 ChatGPT 워크스페이스 계정), `retries: 10`(`configs/`, 모델이 보는 내용은 같음). Opus·Fable은 claude 2.1.311 + relay 18781, 계정 claude-irregular6612(Opus, Fable 4106–4108)와 claude-juhyeon(Fable 4109–4110). 래퍼는 `queues/claude_20261027/`.
- `logs/`: 실행·감시 스크립트·relay 로그.

## appendix/ — 부록 O절

- `tex/o_section.tex`: O절 블록(05_appendix.tex의 "Research archive" 바로 앞, A 번호 묶음 안에 넣는다). `tex/05_appendix_with_O.tex`: 넣은 상태의 부록 전체.
- 표 A7 = 표 7, 그림 A10 = 그림 12, 그림 A11 = 그림 A4, 그림 A12 = 그림 A9의 10판판. 파일은 `ko/tables/`, `ko/figures/`, 데이터는 `results/arena_v33_10g*.json`.
- 다시 만들기: `tools/patches/arena_tools_10g.diff`를 paper에 적용하고 `make_figA5_sen_rounds.py.10g`를 `tools/rewrite_20261025/figs/make_figA5_sen_rounds.py`로 둔 뒤 `ARENA_GAMES=10 ARENA_TAG=_10g`로 `arena_v33.py ~/squid5-runs` → `arena_round_dynamics.py` → `arena_figs.py` → `make_figA5_sen_rounds.py`. 그림 A12는 `tools/rewrite_20261027_10g/`(audit/build.py에 ARENA_RAW=10판 런 폴더 심볼릭 링크 → an3/outcome, joint, pt_seat, game_level → figs/make_figA9_seat.py). 이 복사본은 시드 4101–4105만 넣으면 기존 outcome/joint/pt_seat/rho_axis를 그대로 재현한다.
- `pdf/`: O절을 넣어 빌드한 KO PDF(19–21쪽).
- 주의: 기존 5판 `results/arena_v33.json`의 원본 해시는 오늘 런 폴더에 5판을 이어 붙여 더 이상 맞지 않는다.
