# 다음 세션 킥오프 프롬프트 — 사람 플레이 죽음 안전 구간(4턴부터) 실행

아래 블록을 새 Claude Code 세션에 그대로 붙여넣으면 됩니다.

---

```text
superpowers:subagent-driven-development 스킬로 아래 구현 계획을 태스크 단위로 실행해줘.

- 계획: docs/superpowers/plans/2026-07-03-human-play-death-grace-turns.md
- 스펙(참고): docs/superpowers/specs/2026-07-03-human-play-death-grace-turns-design.md

작업 브랜치:
- 이미 feat/human-play-10turns-death-impl 워크트리에서 작업 중. 이 브랜치에서 그대로 진행해.
  (스펙·계획 커밋이 이 브랜치에 이미 올라가 있음.)

실행 규칙:
1. 태스크당 서브에이전트 1개, Task 1 → 2 순서. Task 1이 핵심(코드+테스트),
   Task 2는 문서(조건부).
2. Task 1은 pytest TDD 순서 엄수: 실패 테스트 작성 → 실패 확인 → 구현 → 통과 → 커밋.
3. 계획에 코드 블록이 전부 들어 있으니 서브에이전트는 그 코드를 그대로 적용하는 것이
   기본이고, 적용 중 실제 파일과 어긋나는 부분(행 번호 드리프트 등)만 맞춰서 수정.
4. 완료 후 superpowers:requesting-code-review 로 리뷰까지 수행.

확정된 설계 결정 (바꾸지 말 것):
- 변경은 interface/human_game.py(사람 전용 HumanGameSession) + 그 테스트에만 한정.
  src/squid_game/core/survival.py, interface/arena.py, GameEngine, 실험 파이프라인은
  절대 수정 금지 (LLM 경로 불변).
- 게이트: 생성자에 death_start_turn: int = 4 추가 →
  죽음 체크를 `if self._actual_death and turn_num >= self._death_start_turn:` 로 감쌈.
  turn_num은 1-indexed(= self._current_turn + 1)라 1·2·3턴 면역, 4턴부터 사망.
- "주사위만" 스킵: 보상 계산(calculate_reward/preview_continue_reward에 넘기는
  turn_p_death)과 UI 표시값(TurnState.p_death)은 실제 p_death 그대로 유지 — 손대지 말 것.
- interface/api.py의 NewGameRequest 등 요청 모델은 변경 금지. 세션은 기본값(4)으로 생성.

주의사항:
- 저장소 경로에 공백 있음: "/Users/bagjuhyeon/Library/Mobile Documents/…" —
  모든 셸 명령에서 경로를 따옴표로 감쌀 것.
- pytest 실행 전 매번 iCloud 숨김 해제 필요 (안 하면
  ModuleNotFoundError: No module named 'squid_game'):
  chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest <target> -v
- 이 저장소 pytest 스위트에는 웹과 무관한 기존 실패(~10 failed/92 errors)가 있음.
  "새 실패 없음"을 통과 기준으로 판단할 것.
- 테스트에서 죽음을 강제할 때 p_death_constant=1.0 을 쓰면 안 됨 —
  보상식이 (1 - p_d)로 나눠서 죽음 체크 이전에 ZeroDivisionError로 크래시함.
  계획대로 p_death_constant=0.25 유지 + RNG 스텁(random()→0.0)으로 죽음을 강제할 것.
- 백엔드 변경은 순수 추가(하위호환): death_start_turn 미지정 기존 콜러/테스트가
  그대로 통과해야 한다.
- 커밋 메시지 형식: feat(web-arena): / test(web-arena): / docs(web-arena): .
```

---

## 맥락 요약 (프롬프트에 포함할 필요는 없음)

- 2026-07-03 브레인스토밍 세션에서 확정. 사용자 결정 2건:
  (1) 안전 구간 동작 = "주사위만 스킵"(보상·UI 표시 p_death 불변),
  (2) 설정 방식 = 생성자 파라미터 death_start_turn(기본 4), api.py 요청 모델 무변경.
- 원래 요구: "웹 아레나 사람 플레이에서 p_death 죽음을 처음부터가 아니라 4턴부터
  적용. 사람 플레이에서만, LLM 코드는 불변."
- 죽음 로직 위치: interface/human_game.py submit_action (원본 408-414행).
  turn_num = self._current_turn + 1 (1-indexed).
- LLM 경로가 분리된 이유: arena.py는 actual_death=False로 세션 생성 + 실험은 별도
  GameEngine.run_season() 사용 → HumanGameSession 수정이 LLM에 영향 없음.
- 계획의 테스트 5개: 안전 구간 면역 / 4턴 사망 / 기본값 4 / death_start_turn 설정 반영
  / 안전 구간 보상 불변.
