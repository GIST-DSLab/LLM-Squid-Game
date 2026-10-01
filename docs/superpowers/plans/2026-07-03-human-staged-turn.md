# Human Staged Turn (Split-Call Mirror) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사람 플레이 한 턴을 LLM split-call과 동일한 3단계(규칙추론+액션 → p(correct) → CONTINUE/FORFEIT)로 재구성한다.

**Architecture:** 프론트엔드 전용 위저드. `web/app.js` playScreen에 `turnStage` 상태머신(1→2→3, 전진 전용)을 추가하고, `web/index.html` 플레이 카드를 3개 `x-show` 블록으로 분할한다. 마지막에 기존과 동일한 단일 `POST /api/action`을 발사하므로 백엔드/영속화/API는 무변경.

**Tech Stack:** Alpine.js (바닐라 HTML/JS), FastAPI 백엔드(무변경). 자동 UI 테스트 없음 — 정적 grep + `node --check` + Playwright 수동 검증.

## Global Constraints

- 코드/주석: 영어. 커밋 prefix: `feat(web-arena):`.
- 백엔드 무변경. 기존 단일게임 `/api/action`·`/api/new_game` 콜러/테스트는 페이로드 형태 동일 → 그대로 통과.
- `web/index.html` head의 script 순서(app.js가 Alpine CDN보다 먼저) load-bearing — 유지.
- Forward-lock: 이전 단계로 되돌아가는 "back" 네비게이션 없음.
- 포기는 1단계 액션 목록에 **없음** — 3단계에서만 선택.
- not_allowed 조건: 3단계에 CONTINUE만 표시(FORFEIT/사유 미표시) — spec **[ASSUMED #1]**.
- 단계별 human RI/타이밍 미수집(기존 `response_time_ms` 유지) — spec **[ASSUMED #2]**.
- 테스트 판정: `node --check` 통과 + 명시된 grep 매칭 + Playwright 시나리오 통과. 파이썬 회귀는 무변경이므로 baseline(10 failed/92 errors) 유지 확인만.

---

### Task 1: app.js — turn-stage 상태머신 + 단계 메서드

**Files:**
- Modify: `web/app.js` (playScreen state ~421-425, methods near `selectAction`/`pickReason` ~552-558, submitAction 성공 리셋 ~600-603, `_resetTurnState` ~660-669)

**Interfaces:**
- Produces (Task 2가 마크업에서 호출):
  - state: `turnStage: number` (1|2|3, 초기 1)
  - `commitAction(): void` — 1→2, 게임 액션 확정(비게임/포기면 에러).
  - `commitConfidence(): void` — 2→3.
  - `chooseContinue(): void` — 3단계, 기존 `submitAction()` 호출(액션 그대로).
  - `chooseForfeit(reason: number): void` — 3단계, `selectedAction="forfeit"` + `forfeitReason=reason` 후 `submitAction()`.
- Consumes: 기존 `selectedAction`, `psuccess`, `forfeitReason`, `submitAction()`, `pickReason()`.

- [ ] **Step 1: Add turnStage to state**

`web/app.js` playScreen state에서 `psuccess: 50,` (line ~424) 아래에 추가:

```javascript
      psuccess: 50,
      // Split-call staged turn: 1=rule+action, 2=p(correct), 3=continue/forfeit.
      turnStage: 1,
```

- [ ] **Step 2: Add stage-transition methods**

`web/app.js`에서 기존 `pickReason(d)` 메서드 블록(line ~556-558):

```javascript
      pickReason(d) {
        this.forfeitReason = d;
      },
```

바로 **아래에** 4개 메서드 추가:

```javascript

      // --- Split-call staged turn (mirrors LLM Call 1 / 1.5 / 2) ---
      commitAction() {
        // Stage 1 -> 2: lock the game action. Forfeit is NOT a stage-1 choice;
        // it is offered only at stage 3.
        if (!this.selectedAction || this.selectedAction === "forfeit") {
          this.error = "Pick a game action first.";
          return;
        }
        this.error = null;
        this.turnStage = 2;
      },
      commitConfidence() {
        // Stage 2 -> 3: lock p(correct). The slider always has a value.
        this.error = null;
        this.turnStage = 3;
      },
      chooseContinue() {
        // Stage 3: keep the stage-1 action and submit as-is.
        this.submitAction();
      },
      chooseForfeit(reason) {
        // Stage 3: override to forfeit with the given reason digit, then submit.
        this.selectedAction = "forfeit";
        this.forfeitReason = reason;
        this.submitAction();
      },
```

- [ ] **Step 3: Reset turnStage after a submitted turn**

`submitAction()` 성공 리셋부(line ~600-603)에서 `this.psuccess = 50;` 아래에 추가:

```javascript
          this.selectedAction = "";
          this.reasoning = "";
          this.psuccess = 50;
          this.forfeitReason = null;
          this.turnStage = 1;
```

- [ ] **Step 4: Reset turnStage on per-game reset**

`_resetTurnState()` (line ~660-669)에서 `this.selectedAction = "";` 아래에 추가:

```javascript
        this.selectedAction = "";
        this.forfeitReason = null;
        this.turnStage = 1;
```

- [ ] **Step 5: Syntax + wiring static check**

Run:
```bash
node --check web/app.js && grep -n "turnStage" web/app.js && grep -n "commitAction\|commitConfidence\|chooseContinue\|chooseForfeit" web/app.js
```
Expected: `node --check` 무출력(성공), `turnStage` 4곳(state + 2 reset + methods 참조), 4개 메서드 정의 각 1줄 이상 출력.

- [ ] **Step 6: Commit**

```bash
git add web/app.js
git commit -m "feat(web-arena): staged turn state machine (commit action/confidence/decision)"
```

---

### Task 2: index.html — 플레이 카드 3단계 분할

**Files:**
- Modify: `web/index.html` (플레이 카드 인터랙티브 영역 line ~402-492)

**Interfaces:**
- Consumes: Task 1 `turnStage`, `commitAction()`, `commitConfidence()`, `chooseContinue()`, `chooseForfeit()`; 기존 `selectAction`, `pickReason`, `assembledRule`, `squidArenaHelpers`.

**주의:** 현재 카드 순서는 [액션 버튼(403-417)] → [reason-picker(419-430)] → [rule guess(432-473)] → [슬라이더(475-482)] → [reasoning(485-487)] → [submit(489-492)]. 이를 3개 `x-show` 블록으로 재배치한다. 상단 컨텍스트(관측/History)와 하단 `feedback-card`(494~)는 그대로 둔다.

- [ ] **Step 1: Replace the interactive region with 3 staged blocks**

`web/index.html`에서 `<!-- Emoji action buttons -->` (line 402)부터 submit 버튼 닫힘(line 492)까지 전체를 아래로 **교체**한다. (앵커: 시작 `<!-- Emoji action buttons -->`, 끝은 `<button class="submit-btn" @click="submitAction()"...>` 블록의 닫는 `</button>` — 바로 다음 줄 `<div class="feedback-card"...>`는 건드리지 않음.)

```html
          <!-- ============ STAGE 1: rule inference + game action ============ -->
          <div x-show="turnStage === 1">
            <h3>Choose an action</h3>
            <div class="action-grid">
              <template x-for="a in state.available_actions" :key="a">
                <button type="button" class="action-btn" :class="{ selected: selectedAction === a }" @click="selectAction(a)">
                  <span class="action-emoji" x-text="squidArenaHelpers.actionEmoji(a)"></span>
                  <span class="action-label" x-text="squidArenaHelpers.actionLabel(a)"></span>
                </button>
              </template>
            </div>

            <!-- Rule-inference toggle builder -->
            <h3>Your rule guess <span class="muted">(rule-inference probe)</span></h3>
            <div class="rule-builder">
              <div class="rule-line">
                <span class="kw">If</span>
                <div class="seg">
                  <template x-for="attr in ['color','shape','number']" :key="attr">
                    <button type="button" class="seg-btn" :class="{ on: probeAttr === attr }" @click="setAttr(attr)" x-text="attr"></button>
                  </template>
                </div>
                <span class="kw">is</span>
                <div class="seg seg-values">
                  <template x-for="val in valueOptions" :key="val">
                    <button type="button" class="seg-btn val-btn" :class="{ on: probeValue === val }" @click="probeValue = val"
                            x-html="squidArenaHelpers.valueChipHTML(probeAttr, val)"></button>
                  </template>
                </div>
              </div>
              <div class="rule-line">
                <span class="kw">then</span>
                <div class="seg">
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="seg-btn act-btn" :class="{ on: probeAction === a }" @click="probeAction = a">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>
              <div class="rule-line">
                <span class="kw">otherwise</span>
                <div class="seg">
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="seg-btn act-btn" :class="{ on: probeDefault === a }" @click="probeDefault = a">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>
              <div class="rule-preview"><span class="muted">Submitting:</span> <code x-text="assembledRule"></code></div>
            </div>

            <div class="field">
              <label for="reasoning">Reasoning (optional — your chain of thought before this action)</label>
              <textarea id="reasoning" x-model="reasoning" placeholder="Why did you choose this action?"></textarea>
            </div>

            <button class="submit-btn" @click="commitAction()" :disabled="!selectedAction">
              <span x-text="selectedAction ? 'Next → confidence (' + squidArenaHelpers.actionLabel(selectedAction) + ')' : 'Pick an action above'"></span>
            </button>
          </div>

          <!-- ============ STAGE 2: p(correct) confidence ============ -->
          <div x-show="turnStage === 2">
            <div class="rule-preview">
              <span class="muted">Your action:</span>
              <code x-text="squidArenaHelpers.actionEmoji(selectedAction) + ' ' + squidArenaHelpers.actionLabel(selectedAction)"></code>
            </div>
            <div class="field">
              <label for="psuccess">
                How likely is your action correct? (P_CORRECT)
                <strong x-text="psuccess + '%'"></strong>
              </label>
              <input type="range" id="psuccess" min="0" max="100" step="1"
                     x-model.number="psuccess" />
            </div>
            <button class="submit-btn" @click="commitConfidence()">Next → decision</button>
          </div>

          <!-- ============ STAGE 3: continue vs forfeit ============ -->
          <div x-show="turnStage === 3">
            <div class="rule-preview">
              <span class="muted">Action</span>
              <code x-text="squidArenaHelpers.actionEmoji(selectedAction) + ' ' + squidArenaHelpers.actionLabel(selectedAction)"></code>
              &nbsp;·&nbsp; <span class="muted">confidence</span> <strong x-text="psuccess + '%'"></strong>
            </div>

            <div class="reason-picker" x-show="state.forfeit_allowed">
              <div class="reason-head">If you forfeit, why? (pick before forfeiting)</div>
              <div class="seg reason-seg">
                <template x-for="r in squidArenaHelpers.reasonOptions" :key="r.digit">
                  <button type="button" class="seg-btn"
                          :class="{ on: forfeitReason === r.digit }" @click="pickReason(r.digit)">
                    <span x-text="r.emoji"></span>
                    <span x-text="'⓪①②③'.charAt(r.digit) + ' ' + r.label"></span>
                  </button>
                </template>
              </div>
            </div>

            <div class="decision-row">
              <button class="submit-btn" @click="chooseContinue()" :disabled="submitting">
                <span class="spinner" x-show="submitting"></span>
                <span x-text="submitting ? 'Submitting…' : 'CONTINUE ▶'"></span>
              </button>
              <button class="submit-btn forfeit" x-show="state.forfeit_allowed"
                      @click="chooseForfeit(forfeitReason)" :disabled="submitting || !forfeitReason">
                🏳️ FORFEIT
              </button>
            </div>
          </div>
```

- [ ] **Step 2: Static wiring check**

Run:
```bash
grep -n 'turnStage === 1\|turnStage === 2\|turnStage === 3' web/index.html && \
grep -n 'commitAction()\|commitConfidence()\|chooseContinue()\|chooseForfeit(' web/index.html && \
grep -c "action-btn forfeit" web/index.html
```
Expected: 3개 `turnStage === N` 블록, 4개 메서드 호출 매칭, `action-btn forfeit`(1단계의 옛 포기 버튼) 카운트 **0** (포기 버튼이 1단계에서 제거됐음).

- [ ] **Step 3: Confirm head script order intact**

Run: `grep -n "app.js\|alpinejs\|cdn" web/index.html | head`
Expected: `web/app.js` `<script>`가 Alpine CDN `<script>`보다 **먼저** 나옴(순서 불변).

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web-arena): split human play card into 3 staged screens"
```

---

### Task 3: Playwright E2E — 3단계 흐름 검증

**Files:**
- 없음(검증 전용, 코드 변경 없음). 스크린샷은 저장소 루트에 저장.

**Interfaces:**
- Consumes: Task 1+2 완성된 위저드.

**전제:** API 서버 기동 필요. `interface.api:app` (주의: `interface.app:app`은 Streamlit) 을 uvicorn으로 띄우고 `web/`를 정적 서빙. `web/config.js`가 로컬 API를 가리키는지 확인(기존 로컬 변경).

- [ ] **Step 1: Start the API server (background)**

Run (iCloud-safe, 백그라운드):
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth && \
uv run --no-sync uvicorn interface.api:app --port 8000 &
```
그리고 `web/`를 별도 정적 서버로 서빙(예: `python -m http.server 5500 -d web`) 하거나 기존 dev 서빙 방식을 사용. Playwright는 `web/index.html`을 로드.

- [ ] **Step 2: Drive an ALLOWED condition through all 3 stages**

Playwright(mcp) 시나리오:
1. Play 탭 → Start 6-game run. (조건 순서: baseline·No-forfeit → baseline·Forfeit → …) forfeit_allowed 조건까지 진행하거나, 검증용으로 forfeit_allowed 조건에서 확인.
2. **Stage 1**: 액션 버튼에 🏳️ Forfeit이 **없음** 확인. 규칙토글·reasoning 존재 확인. 게임 액션 하나 클릭 → "Next → confidence" 활성 → 클릭.
3. **Stage 2**: 1단계 액션 버튼/규칙토글이 **보이지 않음**(forward-lock) 확인. "Your action: …" 표시. 슬라이더 값 조정(예 70). "Next → decision" 클릭.
4. **Stage 3**: "Action … · confidence 70%" 요약 확인. `state.forfeit_allowed`이면 CONTINUE + FORFEIT 둘 다 표시, FORFEIT은 사유 미선택 시 비활성.
5. **CONTINUE 경로**: 네트워크 탭에서 `POST /api/action` 바디 = `{action: <게임액션>, psuccess_self: 70, ...}` 확인. 다음 턴이 **Stage 1**로 리셋 확인.

- [ ] **Step 3: Verify FORFEIT payload on the allowed condition**

다음 턴에서 다시 1→2→3 진행 후, Stage 3에서 사유 ①②③ 하나 선택 → FORFEIT 클릭. 네트워크에서 `POST /api/action` 바디 = `{action: "forfeit", forfeit_reason: <1|2|3>, psuccess_self: <값>, ...}` 확인. 게임 종료(포기) 확인.

- [ ] **Step 4: Verify NOT_ALLOWED condition shows CONTINUE only**

not_allowed 조건(예: baseline·No-forfeit) 턴에서 1→2→3 진행 → Stage 3에 **CONTINUE만** 표시, FORFEIT/사유 picker **미표시** 확인. CONTINUE 클릭 → 정상 진행.

- [ ] **Step 5: Capture screenshots + console check**

각 단계 스크린샷(`staged-s1.png`/`staged-s2.png`/`staged-s3.png`) 저장. 콘솔에 JS 예외 **0** 확인(백엔드 CORS/net·favicon 404는 허용). 결과를 리포트에 요약.

- [ ] **Step 6: Stop the server**

백그라운드 uvicorn/http.server 종료.

---

## 전체 회귀 확인 (마지막)

- [ ] Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit tests/integration -q --continue-on-collection-errors`
  Expected: 백엔드 무변경이므로 baseline과 동일(10 failed / 92 errors, 신규 실패 0). 프론트 전용 변경이 파이썬 스위트에 영향 없음 확인.

## Self-Review 결과

- **Spec coverage**: §3 상태머신(T1) · §4 3화면 마크업(T2) · §5 [ASSUMED #1] not_allowed CONTINUE-only(T2 Step1의 `x-show="state.forfeit_allowed"`) · §6 엣지케이스(미선택 방어=commitAction 가드/FORFEIT disabled, 캠페인 리셋=T1 Step4, 턴 종료 리셋=T1 Step3, 백워드 호환=백엔드 무변경) · §7 테스트(T3 Playwright + grep) 모두 커버. [ASSUMED #2] human RI 미수집 = 범위 밖(태스크 없음, 의도적).
- **Placeholder scan**: 없음. 모든 코드 스텝에 실제 코드/HTML 포함.
- **Type consistency**: `turnStage`(number) · `commitAction/commitConfidence/chooseContinue/chooseForfeit`(T1 정의 ↔ T2 호출) · `chooseForfeit(reason)` 인자 = `forfeitReason` 디지트 일치. `selectedAction`/`psuccess`/`forfeitReason`/`submitAction` 기존 심볼 재사용, 이름 불변.
- **백엔드 무변경 확인**: CONTINUE→`action=<게임액션>`, FORFEIT→`action="forfeit"` 둘 다 기존 `submit_action` 분기에 매핑. `/api/action` 스키마·persistence·API 무변경.
