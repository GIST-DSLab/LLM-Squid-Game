# Web Arena — Logs 그룹 리포트 + 턴 게이트 설계

- 날짜: 2026-07-04
- 대상: `interface/api.py`, `interface/persistence/*`, `web/app.js`, `web/index.html`, `web/styles.css`
- 관련 스펙: `docs/superpowers/specs/2026-07-02-web-arena-design.md`

## 배경 / 목표

사람이 플레이하는 Web Arena에 대해 네 가지를 확인/구현한다.

1. **6게임 캠페인의 게임별 규칙 차등** — (검증) 이미 충족.
2. **접속/게임마다 seed 초기화** — (검증) 이미 충족.
3. **턴 내 게이트** — 규칙 추측(rule-guess)이 미완성이면 p_success 슬라이더 화면으로 넘어가지 못하게 한다.
4. **Logs 재구조화** — 세션 flat 목록을 사람/LLM 주체 단위로 그룹핑하고, 주체 클릭 시 통계 리포트를 보여준다.

## 1. 검증 결과 (코드 변경 없음)

### 1.1 게임별 규칙 차등
- 캠페인 6게임은 `web/app.js`의 `CAMPAIGN_CONDITIONS`가 2(forfeit) × 3(framing) 팩토리얼로 고정한다:
  `true_baseline / baseline_flagship / flagship_corruption` × `not_allowed / allowed`.
  → framing·forfeit 규칙이 게임마다 다르다.
- hidden rule(signal→action 매핑)은 `HumanGameSession`이 `seed`로 task를 초기화하며 결정된다
  (`signal_game/module.py`의 signals·`_active_rule_index`가 seed 종속). 게임마다 seed가 다르면 hidden rule 인스턴스도 다르다.

### 1.2 seed 초기화
- `interface/api.py`의 `new_game`에서 `seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)`.
- 클라이언트는 seed를 전송하지 않으므로 매 `new_game`(= 캠페인 각 게임, 매 새 접속)마다 새 랜덤 seed가 배정된다.
- 캠페인 6게임 각각이 별도 `new_game`을 호출하므로 6개의 서로 다른 seed가 쓰인다.

→ 1.1, 1.2는 이미 요구대로 동작하므로 **변경하지 않는다**. 본 문서는 근거만 남긴다.

## 2. 턴 내 게이트 (프론트엔드)

### 현재 동작
- Stage 1(규칙 추측 + action 선택) → `commitAction()` → Stage 2(p_success 슬라이더).
- 규칙 추측은 4슬롯 rule builder(`probeAttr` / `probeValue` / `probeAction` / `probeDefault`, 기본값 `"?"`)로 구성.
- `assembledRule` getter는 슬롯 중 하나라도 `"?"`이면 `""`(빈 문자열)을 반환한다.
- `commitAction()`은 현재 `selectedAction`만 검사하고 규칙 완성 여부는 검사하지 않는다.

### 변경
- `commitAction()`에 가드 추가: `assembledRule`이 비어 있으면(= 4슬롯 중 `"?"` 잔존)
  `error`에 안내 메시지를 세팅하고 `turnStage`를 2로 올리지 않는다.
- `index.html` Stage 1의 "다음" 버튼에 `:disabled="!selectedAction || selectedAction === 'forfeit' || !assembledRule"` 바인딩.
- 규칙 미완성 시 인라인 힌트(예: "규칙의 4칸(속성·값·행동·기본행동)을 모두 채워야 다음으로 넘어갈 수 있어요")를 노출.
- **턴 진행 방식(10턴 고정)·캠페인 진행 로직은 변경하지 않는다.**

## 3. Logs 재구조화

### 3.1 계층 구조
- **사람 (3계층)**: nickname 그룹 카드 → 캠페인 목록 → (캠페인 리포트 + 캠페인 세션 6개) → 세션 트레이스.
- **LLM (2계층)**: model_label 그룹 카드 → (집계 리포트 + 세션 목록) → 세션 트레이스.
- 세션 트레이스(3단계 말단)는 현재 `logsScreen`의 detail 뷰를 그대로 재사용한다.

LLM은 각 세션이 단일 게임(단일 framing/forfeit)이며 campaign 개념이 없으므로 캠페인 계층이 없다.

### 3.2 백엔드

#### Repository 메서드 추가 (driver-agnostic; sqlite + postgres 양쪽 구현)
- `list_sessions(..., nickname: str | None = None)` — 기존 시그니처에 `nickname` 필터 추가(키워드 인자, 기본 `None`).
- `list_turns_for_sessions(session_ids: list[str]) -> list[TurnRecord]` — `WHERE session_id IN (...)` 단일 쿼리로 여러 세션의 턴을 한 번에 조회(집계용, N+1 방지). `turn_no` 오름차순. 빈 리스트 입력 시 빈 리스트 반환.

#### 신규 엔드포인트: `GET /api/report`
쿼리: `source` (`human|llm`), `key` (nickname 또는 model_label).

응답(공통):
```
{
  "source": "human" | "llm",
  "key": "<nickname|model_label>",
  "n_sessions": int,
  "sessions": [ SessionSummaryRow ],   // 그 주체의 세션(newest-first)
  // --- human 전용 ---
  "campaigns": [
    {
      "campaign_id": str,
      "created_at": str | null,        // 캠페인 내 최신 세션 시각
      "total_score": float,
      "games": [                        // 캠페인 조건 순서(canonical 6-cell)로 정렬
        {
          "session_id": str,
          "framing": str, "forfeit": str, "tag": str, "label": str,
          "final_score": float, "forfeited": bool, "forfeit_reason": str | null,
          "turns_survived": int, "total_turns": int,
          "cells": [ {"turn_no": int, "state": "ok"|"no"|"forfeit"|"empty"} ]
        }
      ]
    }
  ],
  // --- llm 전용 ---
  "conditions": [                        // canonical 6-cell 순서
    {
      "framing": str, "forfeit": str, "tag": str, "label": str,
      "n_sessions": int, "avg_final_score": float, "forfeit_rate": float,
      "cells": [ {"turn_no": int, "correct_rate": float, "n": int} ]
    }
  ],
  "model_stats": ModelStatsRecord | null   // list_model_stats에서 key로 매칭
}
```

- **집계 로직은 API 레이어(Python)** 에서 수행한다. SQL은 단순 조회만.
  - human: `list_sessions(source="human", nickname=key)` → campaign_id로 그룹 →
    `list_turns_for_sessions(ids)`로 세션별 턴 조회 → 게임별 `cells`(정답 ✓ / 오답 ✗ / forfeit 🏳️ / 미도달 empty) 구성.
  - llm: `list_sessions(source="llm", nickname=key)` → `list_turns_for_sessions(ids)` →
    (framing, forfeit, turn_no)별 정답률 집계.
- 조건 순서·tag·label은 `interface/api.py`에 canonical 6-cell 매핑 상수를 두어 프론트 `CAMPAIGN_CONDITIONS`와 일치시킨다.
- `total_turns`는 세션 턴 수(=`len(turns)`)로 계산(휴먼 캠페인은 게임별 동일 길이 가정, 다르면 각 게임의 실제 턴 수 사용).

### 3.3 프론트엔드 (`logsScreen`)
`view` 상태를 확장한다: `groups`(1단계) · `campaigns`(사람 2단계) · `report`(LLM 2단계 / 사람 캠페인 리포트) · `detail`(트레이스).

- **groups**: `/api/logs`를 받아 `nickname`(human) / `nickname`(=model_label, llm)로 그룹 → 카드 목록.
  카드: 이름, 세션 수, (human) 캠페인 수·최고 캠페인 점수, (llm) 평균 점수·SD pass 요약, 최근 플레이 시각.
- **사람 그룹 클릭 → campaigns**: `/api/report?source=human&key=...` 호출.
  캠페인 카드 목록(총점·게임 수·플레이 시각)을 보여준다.
- **캠페인 클릭 → report(human)**: 기존 종료-리포트 카드(`report-table` + `heatmap`) 컴포넌트를 재사용해
  해당 캠페인의 6게임을 렌더. 각 게임의 세션 행에서 세션 트레이스로 이동 가능.
- **LLM 그룹 클릭 → report(llm)**: `/api/report?source=llm&key=...` 호출.
  - 조건(6셀) × 턴 **정답률 히트맵**(셀 색 강도 = correct_rate, 툴팁 = rate·n).
  - `model_stats` 카드: Cox β(`beta_framing_is_FC`), HR + CI, p, SD 3채널 pass(behavior·verbal·cognitive) 체크마크.
  - 아래에 세션 목록 → 세션 클릭 시 트레이스.
- **트레이스(detail)**: 기존 뷰 그대로. `back()`은 직전 계층으로 복귀하도록 스택형 내비게이션.

### 3.4 디자인
- 기존 토큰/클래스 재사용: `cond-badge`(tag별 색), `heatmap`/`hm-*`, `report-table`, `tile`, `pill`, `log-item`.
- LLM 정답률 히트맵은 기존 이산 `hm-ok/hm-no` 대신 rate 기반 배경(예: `background: rgba(accent, rate)`)을 인라인 스타일로 부여하되, 범례를 추가.
- 그룹 카드는 `log-item` 스타일을 확장한 `group-card`로 통일감 유지.

## 4. 테스트
- `interface/persistence`: `list_turns_for_sessions`(다중/빈 입력), `list_sessions(nickname=...)` 필터 — sqlite 단위 테스트.
- `interface/api`: `GET /api/report` human(캠페인 그룹화·cells 상태) / llm(정답률·model_stats 조인) — `test_api_web_arena.py`에 fixture 기반 추가.
- 프론트: 수동 검증(플레이 → 규칙 미완성 시 다음 차단, Logs 3/2계층 내비게이션, 리포트 렌더). `web/`은 자동 테스트 없음.
- 회귀 기준: 기존 web-arena 테스트의 pre-existing 실패(약 10 failed/92 errors) 대비 **신규 실패 0**.

## 5. 범위 밖 (YAGNI)
- LLM 통계 재계산(엔드포인트는 저장된 `model_stats`만 읽음).
- 페이지네이션·검색 고도화.
- 캠페인 진행/턴 수/death 메커니즘 변경.
