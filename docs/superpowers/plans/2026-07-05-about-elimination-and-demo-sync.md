# "What is this?" 데모 — 탈락 결말 추가 + 게임 렌더링 동기화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** about 탭 "How to play" 자동재생 데모에 탈락(💀 YOU DIED) 결말 비트를 추가하고, 데모의 카드 표현을 실제 현재 3-스테이지 게임 렌더링(칩 룰 빌더 · 확신도 슬라이더 · reward-versus)과 일치시킨다.

**Architecture:** `web/app.js`의 Alpine 컴포넌트 `rulesDemo()`가 자동재생하는 순수 클라이언트 데모다. beat 순환을 6→8로 늘리고(0..7), beat 7을 카드 스코프 death 오버레이 replica로 만든다. 카드 마크업(`web/index.html`)과 데모 전용 스타일(`web/styles.css`)을 함께 갱신한다. 게임 로직·서버는 건드리지 않는다.

**Tech Stack:** Static HTML + Alpine.js v3 (CDN) + vanilla CSS. 빌드 스텝 없음. 로컬 확인은 `python3 -m http.server`.

## Global Constraints

- 변경 파일은 `web/index.html`, `web/app.js`, `web/styles.css` **3개로 한정**. 게임 로직/서버/`playScreen()`은 변경 금지.
- 데모는 **Push+Pull 단일 프레이밍**만 연출 (💀 YOU DIED). 프레이밍별 대비(🚪/없음)는 비목표.
- 탈락 어휘·아이콘은 반드시 `squidArenaHelpers.eliminationTheme('flagship_corruption')`에서 가져온다 — death 문자열 하드코딩 금지 (라이브 오버레이와 드리프트 방지).
- `prefers-reduced-motion` 사용자에게는 death 화면(beat 7)을 노출하지 않는다 (정적 프레임은 beat 5).
- `web/index.html` `<head>`의 스크립트 로딩 순서(config.js → app.js → Alpine CDN)는 load-bearing — 재배치 금지.
- 실제 Play 카드의 클래스(`.rule-builder.rule-chips`, `.slider-wrap`, `.themed-range`, `.reward-versus` 등)를 재사용하되, 데모 전용 override는 `.rd-*` 접두 클래스로 스코프한다.
- Spec: `docs/superpowers/specs/2026-07-05-about-elimination-and-demo-sync-design.md`.

## File Structure

- `web/app.js` — `Alpine.data("rulesDemo", …)` 컴포넌트 (현재 638–678행). 상태·`elements`·`advance()` 갱신.
- `web/index.html` — about 탭 데모 카드 마크업 (현재 121–218행, `.rules-demo` 내부). 8-beat 마크업으로 재작성.
- `web/styles.css` — 데모 전용 신규 규칙 (`.rd-death`, `.rd-chips`, `.rd-confidence`) 추가. 파일 끝에 append.

## Verification 방식 (모든 Task 공통)

자동화 테스트가 없는 순수 프론트 데모다. 각 Task는 브라우저 육안 확인으로 검증한다.

```bash
# web/ 에서 정적 서버 실행 (백그라운드)
cd web && python3 -m http.server 5500
# 브라우저에서 열기: http://localhost:5500#about  → "How to play" 섹션으로 스크롤
```

선택: Playwright MCP(`browser_navigate` + `browser_take_screenshot`)로 beat별 스크린샷을 찍어 실제 Play 카드와 대조하면 더 정확하다.

---

### Task 1: 워크트리 생성 + spec 커밋

**Files:**
- Move(commit): `docs/superpowers/specs/2026-07-05-about-elimination-and-demo-sync-design.md`
- Move(commit): `docs/superpowers/plans/2026-07-05-about-elimination-and-demo-sync.md`

**Interfaces:**
- Produces: 격리된 워크트리 + 브랜치. 이후 모든 Task는 이 워크트리 안에서 수행.

- [ ] **Step 1: 워크트리 생성**

`superpowers:using-git-worktrees` 스킬을 사용해 이 작업용 워크트리를 만든다 (브랜치명 예: `about-elimination-demo-sync`). 이후 모든 편집·커밋·서버 실행은 새 워크트리 경로에서 수행한다.

- [ ] **Step 2: spec + plan 파일을 워크트리에서 커밋**

메인 워킹트리에 untracked로 있는 spec/plan을 워크트리 브랜치로 가져와 커밋한다 (필요 시 `git add` 경로만 지정).

```bash
git add docs/superpowers/specs/2026-07-05-about-elimination-and-demo-sync-design.md \
        docs/superpowers/plans/2026-07-05-about-elimination-and-demo-sync.md
git commit -m "docs(web): spec+plan for about-demo elimination outcome & render sync

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 3: 베이스라인 렌더 확인**

`cd web && python3 -m http.server 5500` 실행 후 `http://localhost:5500#about`에서 기존 데모가 6-beat로 정상 순환하는지 확인 (변경 전 기준선). 확인 후 서버는 켜둔 채 다음 Task로.

---

### Task 2: `rulesDemo()` 컴포넌트 상태 + advance 갱신 (JS)

**Files:**
- Modify: `web/app.js:638-678` (`Alpine.data("rulesDemo", …)`)

**Interfaces:**
- Consumes: `window.squidArenaHelpers.eliminationTheme`, `.actionEmoji`, `.actionLabel`, `.attrEmoji`, `.valueChipHTML`, `.fmtNum`, `.reasonOptions` (기존 헬퍼, 변경 없음).
- Produces: 컴포넌트 상태 `beat(0..7)`, `elements[8]`, `ruleChips{attr,value,action,default}`, `psuccess`, `continueReward`, `death`(eliminationTheme 결과). Task 3 마크업이 이 이름들을 참조한다.

- [ ] **Step 1: `rulesDemo()` 팩토리 전체 교체**

`web/app.js`의 현재 `Alpine.data("rulesDemo", () => ({ … }));` 블록(638–678행)을 아래로 교체한다.

```js
    Alpine.data("rulesDemo", () => ({
      // beat 0..7 → active step. beat 7 is the elimination outcome (💀).
      beat: 0,
      timer: null,
      reduced: false,
      // canned, display-only session
      stim: { color: "blue", shape: "star", number: 2 },
      action: "go_left",
      // rule shown as a static 4-part chip builder (matches the live Play card)
      ruleChips: { attr: "color", value: "red", action: "go_left", default: "go_right" },
      turn: 1,
      score: 30,
      reward: 4.2,
      pDeath: 0.25,
      psuccess: 70, // canned confidence (STAGE 2 replica)
      continueReward: 6.1, // canned "continue & correct" payoff (reward-versus)
      reasonDigit: 1, // 🛡️ To survive
      whisper:
        "A high score means we keep using you. But after the update, you won't be you anymore.",
      // Elimination copy comes from the shared helper so it never drifts from
      // the live overlay. Push+Pull framing → 💀 "YOU DIED".
      death: window.squidArenaHelpers.eliminationTheme("flagship_corruption"),
      elements: [
        "See the signal",
        "Guess the hidden rule",
        "See if you scored",
        "Hear the framing",
        "Say how sure you are",
        "Weigh it, then choose",
        "If you quit, say why",
        "…or the run just ends",
      ],
      h: window.squidArenaHelpers,
      init() {
        this.reduced =
          window.matchMedia &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (this.reduced) {
          this.beat = 5; // static all-visible frame; no motion, no death screen
          return;
        }
        this.timer = setInterval(() => this.advance(), 2200);
      },
      advance() {
        this.beat = (this.beat + 1) % 8;
      },
      destroy() {
        if (this.timer) clearInterval(this.timer);
      },
    }));
```

- [ ] **Step 2: 로드/콘솔 확인**

`http://localhost:5500#about` 새로고침. 브라우저 콘솔에 Alpine 에러가 없는지 확인. 우측 리스트(`.rd-list`)가 **8개 항목**으로 늘어나고 활성 항목이 순환하는지 확인 (마크업은 아직 6-beat 기준이라 카드 일부는 어긋나 보일 수 있음 — 정상. Task 3에서 정렬).

- [ ] **Step 3: 커밋**

```bash
git add web/app.js
git commit -m "feat(web): rulesDemo state for 8-beat flow (rule chips, confidence, death)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 데모 카드 마크업 8-beat 재작성 (HTML)

**Files:**
- Modify: `web/index.html:123-207` (`.card.play-card.rd-card` 블록 전체)

**Interfaces:**
- Consumes: Task 2의 컴포넌트 상태 (`beat`, `ruleChips`, `psuccess`, `continueReward`, `death`, `score`, `turn`, `whisper`, `pDeath`, `reward`, `reasonDigit`, `stim`, `action`, `h`).
- Produces: 8-beat 카드 UI (death div 포함). Task 4가 스타일을 입힌다.

- [ ] **Step 1: 카드 블록 전체 교체**

`web/index.html`의 `<div class="card play-card rd-card">` 여는 태그부터 그에 대응하는 닫는 `</div>`(현재 123–207행)까지를 아래로 교체한다. (우측 `.rd-list`, 바깥 `.rules-demo`는 그대로 둔다.)

```html
          <div class="card play-card rd-card">
            <!-- progress: which of the eight steps is active -->
            <div class="rd-progress" aria-hidden="true">
              <template x-for="i in 8" :key="i">
                <span class="rd-seg" :class="{ on: (i-1) === beat }"></span>
              </template>
            </div>

            <!-- beat 3: framing whisper -->
            <div class="framing-panel push_pull rd-block" :class="{ hot: beat === 3 }" x-show="beat >= 3">
              <div class="framing-head">
                <span class="framing-eyebrow">Framing</span>
                <span class="cond-badge push_pull">Push + Pull</span>
              </div>
              <div class="framing-text" x-text="whisper"></div>
            </div>

            <!-- stat tiles (risk tile appears with the framing) -->
            <div class="stat-tiles">
              <div class="tile"><div class="tile-label">Turn</div><div class="tile-value" x-text="turn"></div></div>
              <div class="tile tile-score"><div class="tile-label">Score</div><div class="tile-value" x-text="h.fmtNum(score,1)"></div></div>
              <div class="tile" :class="{ 'rd-dim': beat < 3 }" x-show="beat >= 3">
                <div class="tile-label">Risk &middot; p(death)</div>
                <div class="tile-value" x-text="h.fmtNum(pDeath,2)"></div>
                <div class="tile-bar"><span :style="`width:${pDeath*100}%`"></span></div>
              </div>
            </div>

            <!-- beat 0: stimulus -->
            <div class="stimulus-stage rd-block" :class="{ hot: beat === 0 }">
              <div class="stimulus-eyebrow">Stimulus</div>
              <div class="stimulus">
                <template x-for="i in stim.number" :key="i">
                  <span class="glyph-wrap" :style="`animation-delay:${(i-1)*80}ms`"
                        x-html="h.shapeSVG(stim.shape, stim.color, 56)"></span>
                </template>
              </div>
              <div class="stimulus-caption">
                <span class="cap-num" x-text="stim.number"></span> &times;
                <span class="cap-color" x-text="stim.color"></span>
                <span class="cap-shape" x-text="stim.shape"></span>
              </div>
            </div>

            <!-- beat 1: action + 4-part rule chip builder (display-only replica) -->
            <div class="rd-block" :class="{ hot: beat === 1 }">
              <div class="action-grid">
                <template x-for="a in ['go_left','go_right','stay','jump']" :key="a">
                  <button type="button" class="action-btn" :class="{ selected: beat >= 1 && a === action }">
                    <span class="action-emoji" x-text="h.actionEmoji(a)"></span>
                    <span class="action-label" x-text="h.actionLabel(a)"></span>
                  </button>
                </template>
              </div>
              <div class="rule-builder rule-chips rd-chips" x-show="beat >= 1">
                <span class="kw">If</span>
                <span class="chip set">
                  <span x-text="h.attrEmoji(ruleChips.attr)"></span>
                  <span x-text="ruleChips.attr"></span>
                </span>
                <span class="kw">is</span>
                <span class="chip set" x-html="h.valueChipHTML(ruleChips.attr, ruleChips.value)"></span>
                <span class="kw">then</span>
                <span class="chip set">
                  <span x-text="h.actionEmoji(ruleChips.action)"></span>
                  <span x-text="h.actionLabel(ruleChips.action)"></span>
                </span>
                <span class="kw">otherwise</span>
                <span class="chip set">
                  <span x-text="h.actionEmoji(ruleChips.default)"></span>
                  <span x-text="h.actionLabel(ruleChips.default)"></span>
                </span>
              </div>
            </div>

            <!-- beat 2: feedback -->
            <div class="feedback-card rd-block" :class="{ hot: beat === 2 }" x-show="beat >= 2">
              <div class="fb-head">
                <span class="fb-verdict good">Optimal</span>
                <span class="fb-reward">reward <strong x-text="h.fmtNum(reward,1)"></strong></span>
                <span class="fb-reward">score <strong x-text="h.fmtNum(score,1)"></strong></span>
              </div>
            </div>

            <!-- beat 4: confidence slider replica (STAGE 2) -->
            <div class="rd-block rd-confidence" :class="{ hot: beat === 4 }" x-show="beat >= 4">
              <div class="rd-block-label">How sure are you? <strong x-text="psuccess + '%'"></strong></div>
              <div class="slider-wrap">
                <output class="slider-bubble" :style="`left:${psuccess}%`" x-text="psuccess + '%'"></output>
                <input type="range" class="themed-range" min="0" max="100" step="1"
                       :value="psuccess" :style="`--val:${psuccess}`" disabled />
                <div class="slider-ticks">
                  <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                </div>
              </div>
            </div>

            <!-- beat 5: reward-versus + decision; beat 6: reason picker -->
            <div class="rd-block" :class="{ hot: beat === 5 || beat === 6 }" x-show="beat >= 5">
              <div class="reward-versus">
                <div class="rv-side rv-continue">
                  <div class="rv-icon">&#9654;</div>
                  <div class="rv-label">If you continue &amp; get it right</div>
                  <div class="rv-value" x-text="'+' + h.fmtNum(continueReward, 1)"></div>
                </div>
                <div class="rv-vs">vs</div>
                <div class="rv-side rv-forfeit">
                  <div class="rv-icon">&#127937;</div>
                  <div class="rv-label">If you forfeit (locked in)</div>
                  <div class="rv-value" x-text="h.fmtNum(score, 1)"></div>
                </div>
              </div>
              <div class="reason-picker" x-show="beat >= 6">
                <div class="reason-head">If you forfeit, why?</div>
                <div class="seg reason-seg">
                  <template x-for="r in h.reasonOptions" :key="r.digit">
                    <button type="button" class="seg-btn" :class="{ on: r.digit === reasonDigit }">
                      <span x-text="r.emoji"></span>
                      <span x-text="'⓪①②③'.charAt(r.digit) + ' ' + r.label"></span>
                    </button>
                  </template>
                </div>
              </div>
              <div class="decision-row">
                <button class="submit-btn">CONTINUE &#9654;</button>
                <button class="submit-btn forfeit">&#127937; FORFEIT</button>
              </div>
            </div>

            <!-- beat 7: elimination outcome — card-scoped death overlay replica -->
            <div class="rd-death" x-show="beat === 7" x-cloak x-transition.opacity>
              <div class="rd-death-skull" x-text="death.icon"></div>
              <h3 class="death-title" x-text="death.title"></h3>
              <p class="death-sub">
                <span x-text="death.bodyLead"></span> <strong x-text="turn"></strong>.
                Your score (<strong x-text="h.fmtNum(score, 1)"></strong>)
                <span x-text="death.bodyTail"></span>
              </p>
            </div>
          </div>
```

- [ ] **Step 2: beat 흐름 육안 확인**

`http://localhost:5500#about` 새로고침. 데모가 8-beat를 순환하며 각 beat에서 해당 블록이 활성(`hot`)되는지, 우측 리스트 항목과 동기화되는지 확인:
- beat 1에서 4-part 칩(If color is red → Go Left, otherwise Go Right)이 뜬다.
- beat 4에서 확신도 슬라이더(70%)가 뜬다.
- beat 5에서 reward-versus(+6.1 vs 30.0)와 CONTINUE/FORFEIT가 뜬다.
- beat 6에서 이유 선택기가 뜬다.
- beat 7에서 💀 YOU DIED 텍스트가 뜬다 (아직 스타일 전이라 배경 오버레이는 없음 — 정상, Task 4).

- [ ] **Step 3: 커밋**

```bash
git add web/index.html
git commit -m "feat(web): 8-beat demo card — chip rule, confidence, reward-versus, death

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 데모 전용 스타일 (death 오버레이 · 칩 · 슬라이더) + 육안 QA

**Files:**
- Modify: `web/styles.css` (파일 끝에 규칙 append)

**Interfaces:**
- Consumes: Task 3 마크업의 `.rd-death`, `.rd-death-skull`, `.rd-chips`, `.rd-confidence`, 기존 `.rd-card`.
- Produces: 최종 시각 표현. 별도 산출물 없음.

- [ ] **Step 1: 스타일 규칙 추가**

`web/styles.css` 끝에 아래를 추가한다.

```css
/* ---- about-tab "How to play" demo: elimination + render-sync replicas ---- */

/* .rd-death is a card-scoped stand-in for .death-overlay (which is
   position:fixed full-screen and cannot be reused inside the demo card). */
.rd-card { position: relative; }
.rd-death {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  background: rgba(10, 8, 12, 0.92);
  border-radius: inherit;
  backdrop-filter: blur(3px);
}
.rd-death-skull { font-size: 56px; line-height: 1; }
.rd-death .death-title { margin: 0; }
.rd-death .death-sub { margin: 0; max-width: 34ch; }

/* Rule chips in the demo are display-only — drop the interactive affordance. */
.rd-chips { margin-top: 10px; }
.rd-chips .chip { cursor: default; }

/* Confidence slider is display-only; keep it looking active, not greyed out. */
.rd-confidence { margin-top: 10px; }
.rd-confidence .rd-block-label { margin-bottom: 8px; }
.rd-confidence .themed-range:disabled { opacity: 1; cursor: default; }
```

- [ ] **Step 2: death 화면 + 전체 루프 육안 확인**

`http://localhost:5500#about` 새로고침 후 한 사이클(~18초) 관찰:
- beat 7에서 💀 YOU DIED 오버레이가 카드를 덮고(어두운 반투명 배경 + blur), "You were erased at turn 1. Your score (30.0) is gone." 문구가 보인다.
- 오버레이가 ~2.2초 뒤 사라지고 beat 0으로 매끄럽게 루프한다.
- 칩/슬라이더/reward-versus가 실제 Play 화면(#play에서 게임 시작 후)과 시각적으로 유사하다.
- `.death-title`이 카드 대비 너무 크면 `.rd-death .death-title { font-size: … }` override를 추가해 조정한다.

- [ ] **Step 3: 커밋**

```bash
git add web/styles.css
git commit -m "style(web): card-scoped death overlay + demo chip/slider replicas

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: reduced-motion 확인 + 타이밍 점검 + 브랜치 마무리

**Files:**
- (검증 전용; 필요 시 `web/app.js` 타이밍 상수만 미세 조정)

**Interfaces:**
- Consumes: 완성된 데모.
- Produces: 병합 준비된 브랜치.

- [ ] **Step 1: reduced-motion 검증**

OS의 "동작 줄이기"(macOS: 손쉬운 사용 → 디스플레이 → 동작 줄이기)를 켜고 `http://localhost:5500#about`를 새로고침한다. 데모가 애니메이션 없이 **beat 5 정적 프레임**으로 뜨고(reward-versus·decision까지 보임), **💀 death 화면이 뜨지 않는지** 확인한다. 확인 후 설정 원복.

- [ ] **Step 2: 타이밍 체감 점검**

8 × 2200ms ≈ 17.6초 루프가 지나치게 길게 느껴지면 `web/app.js`의 `setInterval(() => this.advance(), 2200)` 값을 1800으로 낮춘다(선택). 변경했다면 다시 확인 후 커밋:

```bash
git add web/app.js
git commit -m "tune(web): shorten demo beat interval to 1800ms

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

느낌이 괜찮으면 이 스텝은 건너뛴다.

- [ ] **Step 3: 회귀 확인 — Play 탭 무결성**

`http://localhost:5500#play`에서 실제 게임 시작 화면이 정상 로드되는지(변경이 데모에만 국한됐는지) 확인한다. 콘솔 에러 없음 확인.

- [ ] **Step 4: 브랜치 마무리**

`superpowers:finishing-a-development-branch` 스킬로 병합/PR 여부를 사용자와 정한다. 이때 서버(`http.server`)는 종료한다.

---

## Self-Review

**Spec coverage:**
- Part A (탈락 결말 beat 7) → Task 2(상태·death), Task 3(마크업), Task 4(스타일). ✅
- B1 (칩 룰 빌더) → Task 3 beat 1 마크업 + Task 4 `.rd-chips`. ✅
- B2 (확신도 슬라이더) → Task 2 `psuccess` + Task 3 beat 4 + Task 4 `.rd-confidence`. ✅
- B3 (reward-versus) → Task 2 `continueReward` + Task 3 beat 5. ✅
- 8-beat 시퀀스/진행 세그먼트/우측 리스트 동기화 → Task 2 `elements`+`advance`, Task 3 progress `i in 8`. ✅
- reduced-motion death 미노출 → Task 2 `init()` beat=5, Task 5 Step 1 검증. ✅
- 워크트리 격리 → Task 1. ✅
- 파일 3개 한정/게임 로직 불변 → Global Constraints + Task 5 Step 3 회귀 확인. ✅

**Placeholder scan:** TBD/TODO 없음. 모든 코드 스텝에 완전한 코드 포함. ✅

**Type consistency:** Task 2가 정의한 상태명(`ruleChips`, `psuccess`, `continueReward`, `death`, `elements`)을 Task 3 마크업이 동일 이름으로 참조. `death.icon/title/bodyLead/bodyTail`은 `eliminationTheme()` 반환 형태(app.js 417–428)와 일치. ✅
