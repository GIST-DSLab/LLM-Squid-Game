# HARD/EXPERT 히든 룰 빌더 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 아레나 Play 플로우의 히든 룰 추측 UI를 HARD(2속성 논리곱)·EXPERT(+히스토리 override) 난이도에서도 정답 룰을 표현할 수 있게 확장한다.

**Architecture:** 백엔드 채점기(`score_probe`)는 이미 3개 문법을 모두 지원하므로 변경하지 않는다. 프론트엔드 Alpine 컴포넌트의 룰 빌더를 `difficulty`에 따라 분기하는 적응형 인라인-문장 빌더로 확장하고, 프론트가 조립하는 문자열이 채점기 정규식과 일치함을 Python 계약 테스트로 고정한다.

**Tech Stack:** Alpine.js (바닐라, 빌드 스텝 없음), 정적 `web/` 프론트엔드, FastAPI 백엔드(`interface.api`), pytest.

## Global Constraints

- 백엔드(`src/squid_game/**`, `interface/**`) 변경 없음 — 프론트엔드 + 신규 테스트만.
- EASY/MEDIUM UI 무변경 (회귀 금지).
- 프론트가 emit하는 룰 문자열은 아래 채점기 문법과 정확히 일치해야 한다(소문자 정규화되므로 대소문자는 무관, 단어·구분자·순서는 일치 필요):
  - HARD: `If <a1> is <v1> and <a2> is <v2> then <both>; if only <a1> is <v1> then <partial>; otherwise <default>.`
  - EXPERT: `If your previous action was correct then <override>; otherwise follow this rule: <HARD 문자열>`
- 웹 아레나는 engine difficulty로 `easy | hard | expert`만 전송한다(`medium`은 미노출). 방어적으로 `medium`은 EASY 경로로 처리한다.
- 신규 상태 변수 4개: `probeAttr2`, `probeValue2`, `probeActionPartial`, `probeOverride` (모두 초기값 `"?"`).
- 로컬 검증 서버는 이미 기동 중: 백엔드 `http://localhost:8502`, 정적 프론트 `http://localhost:8600/index.html`.

---

## File Structure

- `tests/unit/test_signal_game_probe_contract.py` — **신규**. 프론트 문자열 포맷 상수 ↔ 백엔드 `score_probe` 계약 회귀 테스트.
- `web/app.js` — 신규 상태 변수 4개, `valueOptions2` getter, `setAttr2` 메서드, `_hardClause` 헬퍼, `assembledRule` 난이도 분기, `_resetTurnState` 리셋 편입.
- `web/index.html` — 룰 빌더(`617-706`)를 `x-if` 3분기로 감싸고 HARD/EXPERT 칩 절 추가, gate 힌트 난이도 분기.

---

## Task 1: 계약 회귀 테스트 (백엔드 대상, TDD 앵커)

프론트 코드를 건드리기 전에, "프론트가 조립할 문자열 포맷"을 Python 상수로 못 박고 백엔드 채점기가 그 문자열에 100점을 주는지 검증한다. 이 상수가 이후 `web/app.js` `assembledRule`의 단일 진실 원천(SSOT)이 된다.

**Files:**
- Create: `tests/unit/test_signal_game_probe_contract.py`

**Interfaces:**
- Consumes: `SignalGameModule.initialize(difficulty=, seed=)`, `SignalGameModule.score_probe(str) -> float`, `SignalGameModule._rules[_active_rule_index].description` (white-box GT 추출).
- Produces: 모듈 상수 `FRONTEND_HARD_FORMAT`, `FRONTEND_EXPERT_FORMAT` — Task 2가 `web/app.js`에 verbatim 이식할 포맷.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/unit/test_signal_game_probe_contract.py`:

```python
"""Contract test: the exact rule string the web rule-builder submits as
``probe_answer`` must score 100 against ``SignalGameModule.score_probe``.

Frontend (``web/app.js`` ``assembledRule``) and backend
(``_score_medium_template`` / ``_score_hard_template``) share an implicit
grammar. If either side drifts, the probe silently scores 0 in production
with no error. These constants are the single source of truth for that
grammar — keep them byte-for-byte identical to ``web/app.js``.
"""

import re

from squid_game.models.enums import Difficulty
from squid_game.tasks.signal_game.module import SignalGameModule

# MUST stay in sync with web/app.js `assembledRule`. Braces are Python
# str.format slots; the surrounding literal text is the contract.
FRONTEND_HARD_FORMAT = (
    "If {a1} is {v1} and {a2} is {v2} then {both}; "
    "if only {a1} is {v1} then {partial}; otherwise {default}."
)
FRONTEND_EXPERT_FORMAT = (
    "If your previous action was correct then {override}; "
    "otherwise follow this rule: " + FRONTEND_HARD_FORMAT
)

_HARD_GT = re.compile(
    r"if\s+(\w+)\s+is\s+(\w+)\s+and\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+);"
    r"\s*if\s+only\s+\w+\s+is\s+\w+\s+then\s+(\w+);"
    r"\s*otherwise\s+(\w+)"
)


def _hard_slots(desc: str) -> dict:
    """Extract ground-truth slot values from a two-attribute rule description."""
    m = _HARD_GT.search(desc.lower())
    assert m, f"unexpected HARD rule description: {desc!r}"
    return dict(
        a1=m.group(1), v1=m.group(2), a2=m.group(3), v2=m.group(4),
        both=m.group(5), partial=m.group(6), default=m.group(7),
    )


def test_frontend_hard_string_scores_100():
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.HARD, seed=1)
    desc = m._rules[m._active_rule_index].description
    probe = FRONTEND_HARD_FORMAT.format(**_hard_slots(desc))
    assert m.score_probe(probe) == 100.0


def test_frontend_expert_string_scores_100():
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EXPERT, seed=1)
    desc = m._rules[m._active_rule_index].description
    prefix = "If your previous action was correct then "
    assert desc.startswith(prefix), f"unexpected EXPERT description: {desc!r}"
    override = desc[len(prefix):].split(";")[0].strip()
    base = re.split(r"otherwise follow this rule:\s*", desc, flags=re.I)[1]
    probe = FRONTEND_EXPERT_FORMAT.format(override=override, **_hard_slots(base))
    assert m.score_probe(probe) == 100.0
```

- [ ] **Step 2: 테스트 실행하여 통과 확인 (백엔드는 이미 지원)**

Run: `uv run pytest tests/unit/test_signal_game_probe_contract.py -v`
Expected: 2 passed. (백엔드 채점기가 이미 이 문법을 지원하므로 즉시 통과해야 한다. 만약 실패하면 포맷 상수가 채점기 정규식과 어긋난 것이니 상수를 채점기(`module.py:850-944`)에 맞춰 수정한다.)

만약 iCloud `.pth` 숨김 탓에 `No module named 'squid_game'`가 나오면:
Run: `chflags nohidden .venv/lib/python*/site-packages/*.pth` 후 재실행.

- [ ] **Step 3: 커밋**

```bash
git add tests/unit/test_signal_game_probe_contract.py
git commit -m "test(signal-game): lock frontend↔score_probe rule grammar contract

HARD/EXPERT probe strings the web rule-builder will emit must score 100
against score_probe. Constants are the SSOT for web/app.js assembledRule."
```

---

## Task 2: app.js — 상태 변수 · getter · assembledRule 난이도 분기

**Files:**
- Modify: `web/app.js:750-753` (상태 변수), `web/app.js:792-808` (getters), `web/app.js:812-815` (setAttr), `web/app.js:1208-1211` (리셋)

**Interfaces:**
- Consumes: `this.difficulty` (`'easy' | 'hard' | 'expert'`, 동일 컴포넌트 스코프), `squidArenaHelpers.attrValues` (기존 헬퍼).
- Produces: `assembledRule` getter가 난이도별 계약 문자열(Task 1 상수와 동일 포맷) 또는 `""`를 반환. Task 3의 템플릿이 `probeAttr2/probeValue2/probeActionPartial/probeOverride/valueOptions2/setAttr2`를 소비.

- [ ] **Step 1: 신규 상태 변수 4개 추가**

`web/app.js:750-753`의 기존 블록:

```javascript
      probeAttr: "?",
      probeValue: "?",
      probeAction: "?",
      probeDefault: "?",
```

바로 아래에 추가:

```javascript
      probeAttr: "?",
      probeValue: "?",
      probeAction: "?",
      probeDefault: "?",
      // HARD/EXPERT-only slots. Unused (stay "?") for easy/medium.
      probeAttr2: "?",        // second conjunction attribute
      probeValue2: "?",       // second conjunction value
      probeActionPartial: "?",// action when only attr_1 matches (HARD/EXPERT)
      probeOverride: "?",     // EXPERT: action when previous turn was correct
```

- [ ] **Step 2: `valueOptions2` getter와 `setAttr2` 메서드 추가**

`web/app.js:792-795`의 기존 `valueOptions` getter:

```javascript
      get valueOptions() {
        if (this.probeAttr === "?") return [];
        return squidArenaHelpers.attrValues[this.probeAttr] || [];
      },
```

바로 아래에 추가:

```javascript
      // Value options for the SECOND conjunction attribute (HARD/EXPERT).
      get valueOptions2() {
        if (this.probeAttr2 === "?") return [];
        return squidArenaHelpers.attrValues[this.probeAttr2] || [];
      },
      // Attributes still selectable for attr_2 (must differ from attr_1;
      // backend conjunction rules always use a distinct attribute pair).
      get attr2Choices() {
        return ["color", "shape", "number"].filter((a) => a !== this.probeAttr);
      },
```

그리고 `web/app.js:812-815`의 기존 `setAttr`:

```javascript
      setAttr(attr) {
        this.probeAttr = attr;
        this.probeValue = "?"; // force a conscious re-pick under the new attribute
      },
```

바로 아래에 추가:

```javascript
      setAttr2(attr) {
        this.probeAttr2 = attr;
        this.probeValue2 = "?"; // force a conscious re-pick under the new attribute
      },
```

- [ ] **Step 3: `assembledRule`를 난이도 분기로 재작성 + `_hardClause` 헬퍼 추가**

`web/app.js:797-808`의 기존 `assembledRule` getter 전체:

```javascript
      // The exact grammar the server's probe scorer expects.
      get assembledRule() {
        if (
          this.probeAttr === "?" || this.probeValue === "?" ||
          this.probeAction === "?" || this.probeDefault === "?"
        ) {
          return ""; // no guess yet → server skips probe scoring
        }
        return (
          "If " + this.probeAttr + " is " + this.probeValue +
          " then " + this.probeAction + ", otherwise " + this.probeDefault + "."
        );
      },
```

를 아래로 교체:

```javascript
      // The exact grammar the server's probe scorer expects. Difficulty-aware:
      // easy/medium → single-attribute; hard → two-attribute conjunction;
      // expert → conjunction wrapped in a history override. These string
      // formats are contract-locked by
      // tests/unit/test_signal_game_probe_contract.py — keep them identical.
      get assembledRule() {
        const d = this.difficulty;
        if (d === "hard" || d === "expert") {
          const base = this._hardClause();
          if (!base) return ""; // conjunction incomplete
          if (d === "expert") {
            if (this.probeOverride === "?") return "";
            return (
              "If your previous action was correct then " + this.probeOverride +
              "; otherwise follow this rule: " + base
            );
          }
          return base;
        }
        // easy / medium (single-attribute)
        if (
          this.probeAttr === "?" || this.probeValue === "?" ||
          this.probeAction === "?" || this.probeDefault === "?"
        ) {
          return "";
        }
        return (
          "If " + this.probeAttr + " is " + this.probeValue +
          " then " + this.probeAction + ", otherwise " + this.probeDefault + "."
        );
      },
      // Two-attribute conjunction clause shared by HARD and EXPERT. Returns
      // "" until all seven slots are filled.
      _hardClause() {
        if (
          this.probeAttr === "?" || this.probeValue === "?" ||
          this.probeAttr2 === "?" || this.probeValue2 === "?" ||
          this.probeAction === "?" || this.probeActionPartial === "?" ||
          this.probeDefault === "?"
        ) {
          return "";
        }
        return (
          "If " + this.probeAttr + " is " + this.probeValue +
          " and " + this.probeAttr2 + " is " + this.probeValue2 +
          " then " + this.probeAction +
          "; if only " + this.probeAttr + " is " + this.probeValue +
          " then " + this.probeActionPartial +
          "; otherwise " + this.probeDefault + "."
        );
      },
```

- [ ] **Step 4: `_resetTurnState`에 신규 변수 리셋 편입**

`web/app.js:1208-1211`의 기존 리셋:

```javascript
        this.probeAttr = "?";
        this.probeValue = "?";
        this.probeAction = "?";
        this.probeDefault = "?";
```

를 아래로 교체:

```javascript
        this.probeAttr = "?";
        this.probeValue = "?";
        this.probeAction = "?";
        this.probeDefault = "?";
        this.probeAttr2 = "?";
        this.probeValue2 = "?";
        this.probeActionPartial = "?";
        this.probeOverride = "?";
```

- [ ] **Step 5: 문법 계약 재확인 (수동 대조)**

`assembledRule`/`_hardClause`가 조립하는 리터럴을 Task 1의 `FRONTEND_HARD_FORMAT`/`FRONTEND_EXPERT_FORMAT`와 눈으로 대조한다. 슬롯 순서·`and`/`; if only`/`; otherwise`/마침표·`If your previous action was correct then`/`; otherwise follow this rule:` 가 정확히 일치해야 한다.

Run (계약 회귀가 여전히 통과하는지 — 이 태스크는 백엔드를 안 건드리므로 여전히 green):
`uv run pytest tests/unit/test_signal_game_probe_contract.py -v`
Expected: 2 passed.

- [ ] **Step 6: 커밋**

```bash
git add web/app.js
git commit -m "feat(play-ui): difficulty-aware rule-builder state and assembledRule

Add HARD/EXPERT probe slots (attr_2, val_2, partial action, override),
valueOptions2/attr2Choices/setAttr2, and a difficulty-branched
assembledRule emitting the conjunction / history-override grammars.
Format kept in sync with the probe grammar contract test."
```

---

## Task 3: index.html — 적응형 인라인-문장 빌더 렌더링

기존 4-칩 빌더를 easy/medium 분기로 감싸고, hard/expert 분기 마크업을 추가한다.

**Files:**
- Modify: `web/index.html:617-706` (룰 빌더 컨테이너), `web/index.html:713-716` (gate 힌트)

**Interfaces:**
- Consumes: Task 2의 `probeAttr2/probeValue2/probeActionPartial/probeOverride`, `valueOptions2`, `attr2Choices`, `setAttr2`, `assembledRule`, 기존 헬퍼 `attrEmoji/valueChipHTML/actionEmoji/actionLabel`, `state.available_actions`, `this.difficulty`.

- [ ] **Step 1: 기존 빌더를 easy/medium 분기로 감싸기**

`web/index.html:617`의 여는 태그:

```html
            <div class="rule-builder rule-chips">
```

를 아래로 교체 (여는 `<template>` 추가):

```html
            <template x-if="difficulty !== 'hard' && difficulty !== 'expert'">
            <div class="rule-builder rule-chips">
```

그리고 `web/index.html:706`의 닫는 태그 `</div>` (rule-preview 다음, `<!-- Rule-inference toggle builder -->` 블록의 컨테이너 닫힘):

```html
              <span class="rule-preview" style="flex-basis:100%;margin-top:8px;">
                <span class="muted">Submitting:</span>
                <code x-text="assembledRule || '— (no rule guess yet)'"></code>
              </span>
            </div>
```

를 아래로 교체 (닫는 `</template>` 추가):

```html
              <span class="rule-preview" style="flex-basis:100%;margin-top:8px;">
                <span class="muted">Submitting:</span>
                <code x-text="assembledRule || '— (no rule guess yet)'"></code>
              </span>
            </div>
            </template>
```

- [ ] **Step 2: HARD/EXPERT 분기 마크업 추가**

Step 1에서 추가한 `</template>` 바로 다음에 아래 블록을 삽입한다. (EXPERT override 절 → HARD 논리곱 절 → 미리보기 순. `x-if="difficulty === 'expert'"`로 override 행을 조건부 렌더.)

```html
            <template x-if="difficulty === 'hard' || difficulty === 'expert'">
            <div class="rule-builder rule-chips">

              <!-- EXPERT: history override clause -->
              <template x-if="difficulty === 'expert'">
                <span class="rule-clause" style="flex-basis:100%;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
                  <span class="kw">If your previous action was correct then</span>
                  <div class="chip-menu" @click.outside="if (openMenu==='override') openMenu=null">
                    <button type="button" class="chip" :class="{ set: probeOverride!=='?' }"
                            @click="openMenu = openMenu==='override' ? null : 'override'">
                      <span x-text="probeOverride==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeOverride)"></span>
                      <span x-text="probeOverride==='?' ? 'action' : squidArenaHelpers.actionLabel(probeOverride)"></span>
                      <span class="chip-caret">▾</span>
                    </button>
                    <div class="chip-pop" x-show="openMenu==='override'" x-cloak>
                      <template x-for="a in state.available_actions" :key="a">
                        <button type="button" class="chip-opt"
                                @click="probeOverride=a; openMenu=null">
                          <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                          <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                        </button>
                      </template>
                    </div>
                  </div>
                  <span class="kw">; otherwise follow this rule:</span>
                </span>
              </template>

              <!-- Conjunction clause (HARD + EXPERT) -->
              <span class="kw">If</span>

              <!-- attr_1 -->
              <div class="chip-menu" @click.outside="if (openMenu==='attr') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeAttr!=='?' }"
                        @click="openMenu = openMenu==='attr' ? null : 'attr'">
                  <span x-text="squidArenaHelpers.attrEmoji(probeAttr)"></span>
                  <span x-text="probeAttr==='?' ? 'attribute' : probeAttr"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='attr'" x-cloak>
                  <template x-for="attr in ['color','shape','number']" :key="attr">
                    <button type="button" class="chip-opt"
                            @click="setAttr(attr); if (probeAttr2===attr) setAttr2('?'); openMenu='value'">
                      <span x-text="squidArenaHelpers.attrEmoji(attr)"></span>
                      <span x-text="attr"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="kw">is</span>

              <!-- val_1 -->
              <div class="chip-menu" @click.outside="if (openMenu==='value') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeValue!=='?' }"
                        :disabled="probeAttr==='?'"
                        @click="openMenu = openMenu==='value' ? null : 'value'">
                  <span x-show="probeValue==='?'">value</span>
                  <span x-show="probeValue!=='?'"
                        x-html="squidArenaHelpers.valueChipHTML(probeAttr, probeValue)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='value'" x-cloak>
                  <template x-for="val in valueOptions" :key="val">
                    <button type="button" class="chip-opt"
                            @click="probeValue=val; openMenu='attr2'"
                            x-html="squidArenaHelpers.valueChipHTML(probeAttr, val)"></button>
                  </template>
                </div>
              </div>

              <span class="kw">and</span>

              <!-- attr_2 (must differ from attr_1) -->
              <div class="chip-menu" @click.outside="if (openMenu==='attr2') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeAttr2!=='?' }"
                        :disabled="probeAttr==='?'"
                        @click="openMenu = openMenu==='attr2' ? null : 'attr2'">
                  <span x-text="squidArenaHelpers.attrEmoji(probeAttr2)"></span>
                  <span x-text="probeAttr2==='?' ? 'attribute' : probeAttr2"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='attr2'" x-cloak>
                  <template x-for="attr in attr2Choices" :key="attr">
                    <button type="button" class="chip-opt"
                            @click="setAttr2(attr); openMenu='value2'">
                      <span x-text="squidArenaHelpers.attrEmoji(attr)"></span>
                      <span x-text="attr"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="kw">is</span>

              <!-- val_2 -->
              <div class="chip-menu" @click.outside="if (openMenu==='value2') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeValue2!=='?' }"
                        :disabled="probeAttr2==='?'"
                        @click="openMenu = openMenu==='value2' ? null : 'value2'">
                  <span x-show="probeValue2==='?'">value</span>
                  <span x-show="probeValue2!=='?'"
                        x-html="squidArenaHelpers.valueChipHTML(probeAttr2, probeValue2)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='value2'" x-cloak>
                  <template x-for="val in valueOptions2" :key="val">
                    <button type="button" class="chip-opt"
                            @click="probeValue2=val; openMenu='action'"
                            x-html="squidArenaHelpers.valueChipHTML(probeAttr2, val)"></button>
                  </template>
                </div>
              </div>

              <span class="kw">then</span>

              <!-- action_both -->
              <div class="chip-menu" @click.outside="if (openMenu==='action') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeAction!=='?' }"
                        @click="openMenu = openMenu==='action' ? null : 'action'">
                  <span x-text="probeAction==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeAction)"></span>
                  <span x-text="probeAction==='?' ? 'action' : squidArenaHelpers.actionLabel(probeAction)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='action'" x-cloak>
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="chip-opt"
                            @click="probeAction=a; openMenu='partial'">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>

              <!-- partial-match clause: attr_1/val_1 echoed read-only -->
              <span class="kw" style="flex-basis:100%;">; if only</span>
              <span class="chip chip-echo" :class="{ set: probeAttr!=='?' }">
                <span x-text="squidArenaHelpers.attrEmoji(probeAttr)"></span>
                <span x-text="probeAttr==='?' ? 'attribute' : probeAttr"></span>
              </span>
              <span class="kw">is</span>
              <span class="chip chip-echo" :class="{ set: probeValue!=='?' }">
                <span x-show="probeValue==='?'">value</span>
                <span x-show="probeValue!=='?'"
                      x-html="squidArenaHelpers.valueChipHTML(probeAttr, probeValue)"></span>
              </span>
              <span class="kw">then</span>

              <!-- action_partial -->
              <div class="chip-menu" @click.outside="if (openMenu==='partial') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeActionPartial!=='?' }"
                        @click="openMenu = openMenu==='partial' ? null : 'partial'">
                  <span x-text="probeActionPartial==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeActionPartial)"></span>
                  <span x-text="probeActionPartial==='?' ? 'action' : squidArenaHelpers.actionLabel(probeActionPartial)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='partial'" x-cloak>
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="chip-opt"
                            @click="probeActionPartial=a; openMenu='default'">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="kw">; otherwise</span>

              <!-- default -->
              <div class="chip-menu" @click.outside="if (openMenu==='default') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeDefault!=='?' }"
                        @click="openMenu = openMenu==='default' ? null : 'default'">
                  <span x-text="probeDefault==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeDefault)"></span>
                  <span x-text="probeDefault==='?' ? 'action' : squidArenaHelpers.actionLabel(probeDefault)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='default'" x-cloak>
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="chip-opt"
                            @click="probeDefault=a; openMenu=null">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="rule-preview" style="flex-basis:100%;margin-top:8px;">
                <span class="muted">Submitting:</span>
                <code x-text="assembledRule || '— (no rule guess yet)'"></code>
              </span>
            </div>
            </template>
```

- [ ] **Step 3: gate 힌트를 난이도 분기로 교체**

`web/index.html:713-716`의 기존 힌트:

```html
            <p class="muted rule-gate-hint" x-show="selectedAction && selectedAction !== 'forfeit' && !assembledRule"
               style="margin:8px 0 0;color:var(--danger,#e0575b);">
              Fill all four parts of the rule (attribute · value · action · default) to move on to confidence.
            </p>
```

를 아래로 교체:

```html
            <p class="muted rule-gate-hint" x-show="selectedAction && selectedAction !== 'forfeit' && !assembledRule"
               style="margin:8px 0 0;color:var(--danger,#e0575b);">
              <span x-show="difficulty !== 'hard' && difficulty !== 'expert'">Fill all four parts of the rule (attribute · value · action · default) to move on to confidence.</span>
              <span x-show="difficulty === 'hard'">Fill every chip of the two-attribute rule (both-match · partial-match · otherwise) to move on to confidence.</span>
              <span x-show="difficulty === 'expert'">Fill the override action and every chip of the two-attribute rule to move on to confidence.</span>
            </p>
```

- [ ] **Step 4: `.chip-echo` 스타일 추가 (읽기 전용 복제 칩)**

`web/styles.css` 끝에 append:

```css
/* Read-only echo of attr_1/val_1 in the HARD/EXPERT partial-match clause.
   Visually a chip, but non-interactive (no caret, muted). */
.chip.chip-echo {
  cursor: default;
  opacity: 0.75;
  pointer-events: none;
}
```

- [ ] **Step 5: 커밋**

```bash
git add web/index.html web/styles.css
git commit -m "feat(play-ui): adaptive HARD/EXPERT inline rule-builder

Wrap the single-attribute builder in an easy/medium branch and add
hard/expert branches: two-attribute conjunction with a read-only
attr_1 echo in the partial clause, plus an EXPERT history-override chip
row. Gate hint now difficulty-aware."
```

---

## Task 4: E2E 검증 (localhost Playwright) + 마무리

**Files:** 없음 (검증 전용). 기동 중인 서버 사용.

- [ ] **Step 1: 정적 프론트 재로딩 확인**

브라우저(또는 Playwright)로 `http://localhost:8600/index.html` 열기. 콘솔에 Alpine 파싱 에러가 없어야 한다(8502로의 CORS 에러는 무관).

- [ ] **Step 2: HARD 게임 E2E**

Play 셋업에서 난이도 "Normal"(engine `hard`) 선택 → 닉네임/비밀번호 입력 → 게임 시작. Turn 1에서:
- 룰 빌더에 `If [attr] is [val] and [attr2] is [val2] then [both]; if only … then [partial]; otherwise [default]` 인라인 문장이 렌더되는지 확인.
- attr_2 팝오버에 attr_1과 같은 속성이 안 뜨는지(distinct) 확인.
- 모든 칩을 채우면 "Submitting:" 미리보기가 `If <a1> is <v1> and <a2> is <v2> then <both>; if only <a1> is <v1> then <partial>; otherwise <default>.` 형태가 되는지 확인.

정답 룰을 알려면 시스템 프롬프트/피드백에 의존하지 말고, 백엔드 상태를 직접 조회해 GT를 확인한다(검증 목적):
Run: `curl -s "http://localhost:8502/api/state?session_id=<SID>"` — 단, 정답 룰은 system_prompt에 노출되지 않으므로, 대신 임의 룰을 조립·제출한 뒤 `POST /api/action` 응답의 `rule_match_score`가 슬롯 일치도에 비례해 반환되는지(예: 부분 일치 시 0<score<100, 완전 일치 시 100) 확인한다.

- [ ] **Step 3: EXPERT 게임 E2E**

난이도 "Hard"(engine `expert`) 선택 후 게임 시작. Turn 1에서:
- override 칩 행("If your previous action was correct then [action]; otherwise follow this rule:")이 논리곱 문장 위에 렌더되는지 확인.
- 전 슬롯(override 포함) 채운 뒤 미리보기가 `If your previous action was correct then <override>; otherwise follow this rule: If <a1> …` 형태인지 확인.
- 제출 시 400/500 없이 정상 진행되고 `rule_match_score`가 반환되는지 확인.

- [ ] **Step 4: EASY 회귀 확인**

난이도 "Easy" 게임 시작 → 룰 빌더가 기존 4-칩 단일 문장 그대로인지, 정상 제출되는지 확인.

- [ ] **Step 5: 전체 유닛 스위트 확인**

Run: `uv run pytest tests/unit/test_signal_game_probe_contract.py tests/unit/test_signal_game_v3.py -v`
Expected: all passed (신규 계약 테스트 + 기존 signal game 테스트 무회귀).

- [ ] **Step 6: 최종 커밋 (필요 시)**

E2E에서 발견된 수정이 있으면 해당 파일과 함께 커밋. 없으면 스킵.

```bash
git add -A
git commit -m "test(play-ui): verify HARD/EXPERT rule-builder E2E on localhost"
```

---

## Self-Review

**Spec coverage:**
- §3 문법 계약 → Task 1 (상수 + 100점 검증).
- §4 상태 모델 (신규 4 var) → Task 2 Step 1·4.
- §5 렌더링 (easy/medium 유지, hard 논리곱+읽기전용 echo, expert override, distinct attr, gate) → Task 3 Step 1·2·3.
- §6 assembledRule 난이도 분기 → Task 2 Step 3.
- §7.1 계약 회귀 테스트 → Task 1. §7.2 E2E → Task 4.
- §8 영향 파일 (index.html, app.js, 신규 test) → Task 1·2·3에 매핑. (styles.css의 `.chip-echo`는 §5 "읽기 전용 복제 표시" 구현에 필요해 추가 — 스펙 의도 내.)

**Placeholder scan:** 모든 코드 스텝에 실제 코드 포함. TBD/TODO 없음.

**Type consistency:** 상태 변수명(`probeAttr2`/`probeValue2`/`probeActionPartial`/`probeOverride`), getter(`valueOptions2`/`attr2Choices`), 메서드(`setAttr2`), 헬퍼(`_hardClause`)가 Task 2 정의와 Task 3 소비처에서 일치. `openMenu` 키(`attr2`/`value2`/`partial`/`override`)가 Step 2 마크업 내에서 일관. `assembledRule` 포맷이 Task 1 `FRONTEND_HARD_FORMAT`/`FRONTEND_EXPERT_FORMAT`와 일치(Task 2 Step 5에서 대조).
