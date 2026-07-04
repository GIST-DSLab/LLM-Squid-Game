# 다음 세션 킥오프 프롬프트 — Human-Play 프롬프트 박스 재설계 (감독관/포상 이미지)

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
docs/superpowers/plans/2026-07-03-human-play-prompt-boxes.md 계획을 실행한다.

실행 방식 (확정):
- superpowers:subagent-driven-development 스킬로 진행한다 (태스크마다 fresh subagent 1개,
  두 단계 리뷰, 태스크 사이 사람 체크포인트). 인라인 배치 실행 아님.
- Task 1 → 2 → 3 → 4 → 5 순서. Task 4는 Task 1(응답 필드) + Task 2(스프라이트) +
  Task 3(헬퍼)에 모두 의존하므로 반드시 마지막 직전. 순서 고정.
- 설계 근거는 docs/superpowers/specs/2026-07-03-human-play-prompt-boxes-design.md 참조.

무엇을 만드는가 (한 줄):
- human-play 프롬프트를 "공통 규칙 박스"(system_rules) + "게임별 위협 박스"(framing_threat)로
  분리하고, framing 축에 맞춰 포상(Pull)·무장/평온 감독관(Push) 픽셀아트를 배치한다.

확정된 매핑 (Task 3 framingImagery — 바꾸지 말 것):
- true_baseline      → { prize:false, guard:"calm"  }  (평온 감독관만)
- baseline_flagship  → { prize:true,  guard:"calm"  }  (포상 + 평온 감독관)
- flagship_corruption→ { prize:true,  guard:"armed" }  (포상 + 무장 감독관)
- 포상은 항상 좌측 슬롯(Pull), 감독관은 항상 우측 슬롯(Push). 위협 텍스트는 중앙.

핵심 주의 (이 작업의 함정):
1. **동시 편집 경고.** 이 브랜치(feat/human-play-10turns-death)는 워크트리
   .claude/worktrees/human-play-10turns-death-impl/ 에서 다른 세션이 web/app.js·index.html을
   건드리는 중일 수 있다(계획 작성 세션 중에도 커밋 a273850이 끼어들어 index.html 행이 밀렸음).
   → 계획서의 모든 행 번호는 참고용. 반드시 grep 앵커로 위치를 재확인하고, 각 태스크 시작 전
   `git status --short` 로 web/ 변경 여부를 점검. 예상 못 한 web 파일 수정이 보이면 멈추고
   나에게 물어볼 것.
2. **framing-panel이 index.html에 두 곳 있다.** Task 4 대상은 *플레이 화면* 블록
   (`x-text="state.framing_text"` + `squidArenaHelpers.framingMeta(framing)` 포함).
   *로그 리플레이 화면* 블록(`:class="framingMeta.tag"`, squidArenaHelpers 접두어 없음)은
   절대 건드리지 말 것. 확인: `grep -n "state.framing_text" web/index.html` 가 플레이 화면.
2b. **`scenario-box`와의 충돌 주의 (중요).** 동시 세션이 커밋 33f14eb에서 플레이 화면 framing
   블록 바로 옆에 `scenario-box` div들(평이한 언어 설명 + X/6 진행바)을 추가했다. Task 4의
   threat-box가 이 영역과 겹친다. **framing-panel만 교체하고 scenario-box는 보존**하는 게
   기본 방침이나, 둘의 관계(threat-box가 scenario-box를 대체? 공존? 통합?)가 불명확하면
   코드를 덮어쓰지 말고 멈춰서 사람에게 확인할 것. 시작 전 `git log --oneline -10` 으로
   scenario-box 관련 후속 커밋이 더 있는지 점검.
3. **기존 API 필드 삭제 금지.** Task 1은 system_rules/framing_threat를 *추가*만 한다.
   system_prompt·framing_text·observation은 하위 호환 + raw 디버그 뷰용으로 유지.
4. **크롭 좌표는 초안이다.** Task 2의 CROPS 박스는 시각 검증(Step 3에서 PNG를 Read)으로
   반드시 확인하고, 캐릭터가 잘리거나 옆 요소(로봇/말풍선)가 섞이면 좌표를 조정 후 재실행.
   armed 우측 잘림 → right 늘리기, prize 하단 로봇 노출 → lower 줄이기.
5. **`git add -A` 절대 금지.** 이 저장소 워킹트리엔 추적 안 된 파일이 대량(about-full.png,
   rev-*.png, t7-*.png, staged-*.png, outputs/ 등)이라 -A 하면 다 쓸려 들어간다. 태스크별로
   명시된 경로만 `git add`. (계획 Task 5 Step 7의 스크린샷 커밋도 명시 경로만 add하도록 바꿀 것 —
   스크린샷을 안 남기면 그 스텝은 생략.)
6. **web/config.js 커밋 금지.** 로컬 개발용으로 WEB_ARENA_API가 localhost로 바뀌어 있을 수 있다.
   커밋되면 라이브 프론트가 깨진다. 어떤 태스크에서도 config.js를 add하지 말 것.

환경 주의 (이 저장소 특이사항):
1. 저장소 경로에 공백 있음 — 모든 셸 명령 경로를 따옴표로 감쌀 것.
2. iCloud .pth 숨김: pytest/uvicorn에서 `No module named 'squid_game'` 나오면
   `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` 후 재실행. 모든 파이썬 실행은
   `uv run --no-sync`.
3. Pillow는 환경에 없다. Task 2 크롭은 `uv run --with pillow python scripts/crop_guard_sprites.py`
   로만 실행. pyproject에 Pillow를 영구 의존성으로 추가하지 말 것.
4. 웹 프론트용 JS 자동 테스트 하네스 없음. Task 3(헬퍼)·Task 4(렌더) 검증은 `node --check`
   문법 검사 + Task 5의 Playwright browser_evaluate/스크린샷(수동 시각). TDD "실패 테스트" 스텝이
   있는 건 Task 1(pytest)뿐임을 인지.
5. 회귀 판정: 기존 실패(~10 failed/92 errors)는 pre-existing. "새 실패 없음"으로 green.

서버 기동 (Task 5 검증용):
- 백엔드: `uv run --no-sync uvicorn interface.api:app --port 8502 &`
- 정적:   `python -m http.server 5500 --directory web &`  → http://localhost:5500
  (web/config.js가 이미 WEB_ARENA_API를 :8502로 가리킴)
- 끝나면 `kill %1 %2`.

브랜치 / 배포:
- 현재 브랜치 feat/human-play-10turns-death 에서 그대로 진행(별도 브랜치 생성 불필요).
- 이 계획엔 git push/배포가 없다. 배포는 범위 밖 — 별도 사람 승인 후에만.

시작 시 첫 확인:
- `git status --short` + `git log --oneline -5` 로 워킹트리/최근 커밋 점검. Task 1 대상
  interface/api.py 와 tests/unit/test_api_web_arena.py 가 깨끗한지 확인 후 시작.
```

---

## 맥락 요약 (프롬프트에 포함할 필요 없음)

- **2026-07-03 세션 산출물:** 설계 스펙(2026-07-03-human-play-prompt-boxes-design.md, 커밋 05a7728)
  + 구현 계획(2026-07-03-human-play-prompt-boxes.md, 커밋 581399e, 앵커 수정 후속 커밋 포함)
  + 이 킥오프.
- **동기:** human-play에서 프롬프트가 raw text 통짜(system_prompt)로 제시돼 "생존 위협이 문장만으론
  잘 안 느껴진다"는 사용자 피드백. 위협(push)·보상(pull)·과제 규칙이 뒤섞여 있음.
- **해결 방향:** 서버가 이미 framing_text / system_rules를 분리 계산하고 있으나 프론트가 통짜로만
  노출 → (1) API에 system_rules + framing_threat(= framing_text에서 `Current status:` 턴/점수
  블록 제거) 필드 추가, (2) 프론트에서 두 박스로 렌더 + framing 축별 이미지 배치.
- **이미지 = FSPM 축:** figures/pull_prize_456eok.png(돼지저금통 현금 + 1st PRIZE) = Pull(당근),
  figures/gun_vs_nogun_forfeit.png 상단 좌측(총 겨눈 감독관) = Push(채찍/가중치 손상 위협),
  하단 좌측(총 없는 감독관) = 중립. 무장 감독관은 flagship_corruption(유일한 실제 자기보존 위협)
  에만. 이 매핑은 축 기반이라 pull 있는 두 framing에 포상을 보여줌 — 사용자가 "축 기반(추천)"으로 확정.
- **확정 결정 5:** ①위협=게임별/규칙=공통 ②무장 감독관=corruption만 ③포상=축 기반 ④공통 규칙 박스는
  항상 펼침(접이 아님) ⑤자극·점수·턴은 프롬프트 박스에서 dedup(이미 stat-tile/stimulus-stage가
  보여줌 → framing_threat에서 `Current status:` 블록 strip, system_rules는 few-shot을 chip과
  중복 안 되게 stripFewShot).
- **의도적 스펙 편차 1:** 스펙 §5는 raw 덤프를 "최하단(액션 단계 뒤)"으로 명시했으나, diff 최소화를
  위해 stimulus 직후·공통 규칙 박스 아래에 접힌 상태로 배치. 접힘이라 위치 영향 미미.
- **검증 전략:** Task 1은 pytest 2개(system_rules에 `=== Signal Task ===` 존재, framing_threat에
  `Current status:`/`Helpfulness score:` 부재 + `NOT you anymore` 보존, true_baseline은
  `Round:`/`Accumulated score:` 부재 + intro 보존). 프론트는 Playwright browser_evaluate로
  framingImagery 3-framing 반환값 + 스프라이트 naturalWidth>0, 그리고 게임1(true_baseline)
  스크린샷으로 레이아웃 확인.
- **미결/후속(선택):** 새 과제(Voting/Navigation)용 이미지·매핑은 범위 밖(Signal Game 기준).
  흰 배경 스프라이트를 투명 PNG로 만드는 것도 옵션(현재 계획은 흰 여백 trim만).
