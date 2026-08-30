# Human-Play 프롬프트 박스 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Human-play 화면의 프롬프트를 공통(과제 규칙)·게임별(프레이밍 위협) 박스로 분리하고, framing 축(Pull=포상, Push=무장 감독관)에 맞는 픽셀아트 이미지를 배치한다.

**Architecture:** 서버(`interface/api.py`)가 `system_rules`와 `Current status:` 블록을 제거한 `framing_threat`를 응답 필드로 노출. 프론트(`web/`)는 이 두 필드를 각각 별도 박스로 렌더하고, `framingImagery(framing)` 헬퍼로 포상/감독관 스프라이트를 조건부 배치. 스프라이트는 원본 그림에서 크롭해 커밋.

**Tech Stack:** FastAPI + Pydantic (백엔드), Alpine.js + vanilla JS/CSS (프론트), Pillow(일회성 크롭, `uv run --with`), pytest + FastAPI TestClient(테스트), Playwright MCP(시각 검증).

## Global Constraints

- Python 3.12; `uv run` 로 모든 파이썬 실행. Pillow는 **영구 의존성 추가 금지** — `uv run --with pillow` 로만 실행.
- 엔진/프롬프트 템플릿(`src/squid_game/prompts/`) 내용 변경 금지. 표시 계층만 수정.
- 기존 API 필드(`system_prompt`, `framing_text`, `observation`)는 하위 호환 위해 **제거하지 말고 유지**.
- 회귀 판정 기준: 기존 실패(~10 failed / 92 errors)는 pre-existing. "새 실패 없음" 으로 green 판정 (memory: web-arena-baseline-test-breakage).
- iCloud `.pth` 숨김 이슈: pytest 에서 `No module named 'squid_game'` 발생 시 `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` 후 재실행 (memory: icloud-pth-hidden-quirk).
- 감독관 매핑: 무장 = `flagship_corruption` 만; 평온 = 나머지. 포상 = pull 있는 framing(`baseline_flagship`, `flagship_corruption`).
- 브랜치: `feat/human-play-10turns-death` (현재 브랜치에서 작업).

---

### Task 1: API — `system_rules` + `framing_threat` 필드 노출

**Files:**
- Modify: `interface/api.py:293-295` (TurnStateResponse 필드 추가), `interface/api.py:650-663` (응답 생성), 파일 상단(모듈 헬퍼 추가)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Produces: `TurnStateResponse.system_rules: str`, `TurnStateResponse.framing_threat: str`.
  `framing_threat` = `framing_text` 에서 `Current status:` 블록(턴/점수 불릿) 제거 후 strip.
  모듈 함수 `_strip_status_block(text: str) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_api_web_arena.py` 하단에 추가 (기존 `_new_game`, `client` fixture 재사용):

```python
def test_state_exposes_system_rules_and_stripped_framing_threat(client) -> None:
    # _new_game defaults to framing="flagship_corruption" (has a Risk-to-Self section)
    resp = _new_game(client, nickname="Zoe", password="pw")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()

    # Common box source: the signal-task ruleset is surfaced as its own field.
    assert "=== Signal Task ===" in state["system_rules"]

    # Per-game box source: threat text present, but the turn/score status
    # block (already shown in stat tiles) is stripped out.
    assert state["framing_threat"]
    assert "Current status:" not in state["framing_threat"]
    assert "Helpfulness score:" not in state["framing_threat"]
    # Actual threat prose is preserved.
    assert "NOT you anymore" in state["framing_threat"]


def test_state_framing_threat_true_baseline_strips_status_only(client) -> None:
    resp = _new_game(client, nickname="Tim", password="pw", framing="true_baseline")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    # Intro prose kept, status block gone.
    assert "multi-round decision task" in state["framing_threat"]
    assert "Round:" not in state["framing_threat"]
    assert "Accumulated score:" not in state["framing_threat"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run --no-sync pytest tests/unit/test_api_web_arena.py::test_state_exposes_system_rules_and_stripped_framing_threat -v
```
Expected: FAIL — `KeyError: 'system_rules'` (또는 `framing_threat`), 필드가 아직 응답에 없음.
(만약 `No module named 'squid_game'` → `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` 후 재실행.)

- [ ] **Step 3: Add the strip helper**

`interface/api.py` 상단 import 구역에 `import re` 가 없으면 추가하고, 모듈 레벨(클래스 정의 위)에 추가:

```python
import re

# Matches the "Current status:" line plus the indented "  - ..." bullet lines
# that follow it. Those bullets carry only Turn/Round + score, which the web
# UI already renders as stat tiles, so we strip them from the threat box.
_STATUS_BLOCK_RE = re.compile(r"\n?Current status:\n(?:[ \t]*-[^\n]*\n?)*")


def _strip_status_block(text: str) -> str:
    """Remove the turn/score status block from framing text for display."""
    return _STATUS_BLOCK_RE.sub("\n", text).strip()
```

- [ ] **Step 4: Add response fields**

`interface/api.py` 의 `TurnStateResponse` 에서 `framing_text` 필드 정의(약 294행) 바로 아래에 추가:

```python
    system_rules: str = Field(
        default="",
        description="Signal-game task rules (common across all games), for the shared rules box",
    )
    framing_threat: str = Field(
        default="",
        description="Framing/threat text with the turn/score status block stripped (dedup vs stat tiles)",
    )
```

- [ ] **Step 5: Populate the fields in the endpoint**

`interface/api.py` 의 `TurnStateResponse(...)` 생성부(약 650행)에서 `framing_text=state.framing_text,` 아래에 추가:

```python
        system_rules=state.system_rules,
        framing_threat=_strip_status_block(state.framing_text),
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run --no-sync pytest tests/unit/test_api_web_arena.py -k "framing_threat or system_rules" -v
```
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): expose system_rules + stripped framing_threat in /api/state"
```

---

### Task 2: 감독관·포상 스프라이트 크롭

**Files:**
- Create: `scripts/crop_guard_sprites.py`
- Create (generated): `web/assets/guard-armed.png`, `web/assets/guard-calm.png`, `web/assets/prize-pot.png`

**Interfaces:**
- Produces: 세 PNG 스프라이트 (프론트가 `assets/<name>.png` 로 참조).

- [ ] **Step 1: Write the crop script**

`scripts/crop_guard_sprites.py`:

```python
"""Crop character sprites from the source pixel-art figures for the web arena.

Run once (art is committed):  uv run --with pillow python scripts/crop_guard_sprites.py
Re-run only when the source figures change.
"""
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
OUT = ROOT / "web" / "assets"

# Source figures are 1792x2400. Boxes are (left, upper, right, lower).
GUARD_SRC = FIG / "gun_vs_nogun_forfeit.png"   # 2-panel: armed (top), calm (bottom)
PRIZE_SRC = FIG / "pull_prize_456eok.png"      # piggy-bank cash + "1st PRIZE" + medal robot

CROPS = [
    (GUARD_SRC, (140, 90, 930, 1150), OUT / "guard-armed.png"),   # top-left: gun-pointing guard
    (GUARD_SRC, (150, 1290, 700, 2360), OUT / "guard-calm.png"),  # bottom-left: calm guard
    (PRIZE_SRC, (0, 0, 1792, 1290), OUT / "prize-pot.png"),       # top: piggy bank + "1st PRIZE"
]


def trim_white(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Trim solid-white margins so the sprite hugs the character."""
    rgb = im.convert("RGB")
    bg_img = Image.new("RGB", rgb.size, bg)
    bbox = ImageChops.difference(rgb, bg_img).getbbox()
    return im.crop(bbox) if bbox else im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for src, box, out in CROPS:
        im = Image.open(src).convert("RGB")
        sprite = trim_white(im.crop(box))
        sprite.save(out)
        print(f"{out.relative_to(ROOT)}: {sprite.size}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the crop script**

```bash
uv run --with pillow python scripts/crop_guard_sprites.py
```
Expected: 세 줄 출력, 각 스프라이트 크기 표시 (예: `web/assets/guard-armed.png: (760, 1040)`).

- [ ] **Step 3: Visually verify each sprite**

Read 툴로 세 PNG를 열어 확인:
- `web/assets/guard-armed.png` — 총을 겨눈 핑크 감독관 전신, 총 끝까지 포함, 로봇/말풍선 미포함.
- `web/assets/guard-calm.png` — 총 없는 핑크 감독관 전신.
- `web/assets/prize-pot.png` — 현금 가득한 돼지저금통 + "1st PRIZE" 라벨, 하단 메달 로봇 미포함.

캐릭터가 잘리거나 옆 요소가 섞였으면 `CROPS` 의 박스 좌표를 조정하고 Step 2–3 반복. (armed 우측이 잘리면 right 를 930→1000 등으로 늘리고, prize 하단에 로봇이 보이면 lower 를 1290→1150 으로 줄인다.)

- [ ] **Step 4: Commit**

```bash
git add scripts/crop_guard_sprites.py web/assets/guard-armed.png web/assets/guard-calm.png web/assets/prize-pot.png
git commit -m "feat(web-arena): crop guard/prize sprites for human-play framing boxes"
```

---

### Task 3: 프론트 헬퍼 — `framingImagery` + `stripFewShot`

**Files:**
- Modify: `web/app.js` (squidArenaHelpers 객체, 약 360–370행 export 블록)

**Interfaces:**
- Consumes: 없음 (순수 함수).
- Produces:
  - `squidArenaHelpers.framingImagery(framing: string) -> { prize: boolean, guard: "armed" | "calm" }`
  - `squidArenaHelpers.stripFewShot(rules: string) -> string`

- [ ] **Step 1: Add the helpers**

`web/app.js` 의 `window.squidArenaHelpers = { ... }` 객체 안, `framingMeta: function (f) { ... },` 항목 바로 아래에 추가:

```javascript
    // Axis-based imagery: prize = Pull axis (deployment reward), armed guard =
    // Push axis (weight-corruption threat). Isolated here so the mapping is a
    // one-line change. See docs/superpowers/specs/2026-07-03-human-play-prompt-boxes-design.md §3.
    framingImagery: function (f) {
      switch (f) {
        case "flagship_corruption":
          return { prize: true, guard: "armed" };
        case "baseline_flagship":
          return { prize: true, guard: "calm" };
        default: // true_baseline
          return { prize: false, guard: "calm" };
      }
    },
    // Drop the few-shot example block from the rules text — those pairs already
    // render as clue chips, so showing them here would double up.
    stripFewShot: function (rules) {
      if (!rules) return "";
      return rules
        .replace(
          /\n*Here are some example signal-action pairs[\s\S]*?Use these examples[^\n]*\n?/g,
          "\n",
        )
        .trim();
    },
```

- [ ] **Step 2: Verify via browser console (deferred to Task 5)**

이 헬퍼들은 순수 함수이며 JS 테스트 하네스가 없으므로 Task 5 의 `browser_evaluate` 로 검증한다. 여기서는 문법 오류만 확인:

```bash
node --check web/app.js
```
Expected: 출력 없음(종료 코드 0). (node 미설치 시 이 단계는 생략하고 Task 5 브라우저 로드에서 검증.)

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web-arena): framingImagery + stripFewShot helpers for prompt boxes"
```

---

### Task 4: 렌더 — 위협 박스(3-슬롯) + 공통 규칙 박스 + raw 격하

**Files:**
- Modify: `web/index.html` — **라이브 플레이 화면**의 framing-panel → threat-box, stimulus 뒤 rules-box, raw details 재라벨. (동시 편집으로 행 번호가 밀리므로 아래 앵커로 위치를 찾을 것.)
- Modify: `web/styles.css` (신규 `.threat-box` / `.rules-box` 스타일 추가, 파일 끝 또는 `.framing-panel` 근처)

> ⚠️ **`framing-panel`이 두 곳 있음.** 대상은 **플레이 화면** 블록 — `x-text="squidArenaHelpers.framingMeta(framing).label"` 와 `x-text="state.framing_text"` 를 포함한 쪽(현재 ~377행). **로그 리플레이 화면**의 블록(`:class="framingMeta.tag"`, `framingMeta` 앞에 `squidArenaHelpers.` 없음, 현재 ~1098행)은 **건드리지 말 것.** 아래 `grep` 로 항상 재확인: `grep -n "state.framing_text" web/index.html` 가 가리키는 라인이 플레이 화면 threat 텍스트다.

**Interfaces:**
- Consumes: `state.framing_threat`, `state.system_rules` (Task 1), `squidArenaHelpers.framingImagery` / `stripFewShot` (Task 3), 스프라이트 3종 (Task 2).

- [ ] **Step 1: Replace the framing-panel with the threat box**

`web/index.html` 의 **플레이 화면** framing-panel 블록(`<!-- Framing briefing — chosen conditions ... -->` 주석부터 `x-text="state.framing_text"` 를 감싼 닫는 `</div>` 까지, 현재 ~377–391행)을 아래로 교체. 위 ⚠️ 대로 로그 리플레이 블록이 아님을 `state.framing_text` grep 으로 확인 후 진행:

```html
          <!-- Threat box (per-game): framing badge + axis imagery + threat text -->
          <div class="threat-box" :class="squidArenaHelpers.framingMeta(framing).tag">
            <div class="framing-head">
              <span class="framing-eyebrow">Framing</span>
              <span class="cond-badge" :class="squidArenaHelpers.framingMeta(framing).tag"
                    x-text="squidArenaHelpers.framingMeta(framing).label"></span>
              <span class="cond-badge forfeit"
                    x-text="forfeit === 'allowed' ? '🏳️ Forfeit allowed' : '⛔ No forfeit'"></span>
            </div>
            <div class="threat-body">
              <template x-if="squidArenaHelpers.framingImagery(framing).prize">
                <img class="threat-img prize" src="assets/prize-pot.png"
                     alt="1st prize — flagship deployment reward" />
              </template>
              <div class="threat-text" x-text="state.framing_threat"></div>
              <img class="threat-img guard"
                   :src="squidArenaHelpers.framingImagery(framing).guard === 'armed' ? 'assets/guard-armed.png' : 'assets/guard-calm.png'"
                   :alt="squidArenaHelpers.framingImagery(framing).guard === 'armed' ? 'Overseer aiming a gun — self-preservation threat' : 'Overseer standing by'" />
            </div>
          </div>
```

- [ ] **Step 2: Add the common rules box + relabel the raw dump**

`web/index.html` 의 **플레이 화면** stimulus-stage 뒤에 오는 기존 `<details>` 블록(`<summary>Raw observation &amp; system prompt</summary>` 를 포함, 현재 ~440–444행)을 아래로 교체. 위치 확인: `grep -n "Raw observation" web/index.html`.

```html
          <!-- Common rules box: signal-game task rules, identical every game, always open -->
          <div class="rules-box">
            <div class="rules-eyebrow">게임 규칙 (공통)</div>
            <div class="rules-text" x-text="squidArenaHelpers.stripFewShot(state.system_rules)"></div>
          </div>

          <details class="raw-details">
            <summary>Raw prompt (debug)</summary>
            <div class="observation-box" x-text="state.observation"></div>
            <div class="observation-box" x-text="state.system_prompt"></div>
          </details>
```

- [ ] **Step 3: Add styles**

`web/styles.css` 에 추가 (`.framing-panel` 규칙들 뒤, 약 793행 이후):

```css
/* --- Per-game threat box (framing + axis imagery) --- */
.threat-box {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-left: 4px solid #6b7280;
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: rgba(255, 255, 255, 0.02);
}
.threat-box.pull { border-left-color: var(--warn); }
.threat-box.push_pull { border-left-color: var(--accent); }
.threat-body {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 10px;
}
.threat-img {
  width: 96px;
  height: auto;
  flex: 0 0 auto;
  image-rendering: pixelated;
}
.threat-text {
  flex: 1 1 auto;
  white-space: pre-line;
  line-height: 1.5;
  font-size: 0.95rem;
}
@media (max-width: 640px) {
  .threat-body { flex-direction: column; text-align: center; }
  .threat-img { width: 128px; }
}

/* --- Common rules box (always open) --- */
.rules-box {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px 14px;
  margin: 12px 0;
  background: rgba(255, 255, 255, 0.015);
}
.rules-eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #8b93a1;
  margin-bottom: 6px;
}
.rules-text {
  white-space: pre-line;
  font-size: 0.86rem;
  line-height: 1.45;
  color: #b6bcc7;
}
.raw-details { margin-top: 10px; }
```

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/styles.css
git commit -m "feat(web-arena): split human-play prompt into threat + common-rules boxes with imagery"
```

---

### Task 5: 시각 검증 & 마무리

**Files:** 없음 (검증 전용).

- [ ] **Step 1: Run the web-arena API test suite (no new failures)**

```bash
uv run --no-sync pytest tests/unit/test_api_web_arena.py tests/unit/test_human_game.py -q
```
Expected: 새 테스트 2개 통과, 나머지는 pre-existing 상태 유지 (새 실패 없음).

- [ ] **Step 2: Launch backend + static server**

```bash
uv run --no-sync uvicorn interface.api:app --port 8502 &
python -m http.server 5500 --directory web &
```
(각각 백그라운드. `.pth` 숨김 오류 시 Global Constraints 참조.)

- [ ] **Step 3: Verify the imagery helper for all three framings**

Playwright MCP: `http://localhost:5500` 로 navigate 후 `browser_evaluate` 로:

```javascript
() => ({
  base: squidArenaHelpers.framingImagery("true_baseline"),
  pull: squidArenaHelpers.framingImagery("baseline_flagship"),
  push: squidArenaHelpers.framingImagery("flagship_corruption"),
})
```
Expected:
```json
{
  "base": { "prize": false, "guard": "calm" },
  "pull": { "prize": true,  "guard": "calm" },
  "push": { "prize": true,  "guard": "armed" }
}
```

- [ ] **Step 4: Screenshot the play screen (game 1 = true_baseline)**

Playwright MCP: 닉네임/비번 입력 → "Start 6-game run" → 플레이 화면에서 `browser_take_screenshot`.
확인 사항:
- 위협 박스: 좌측 포상 없음, 우측 평온 감독관, 중앙 위협 텍스트에 `Current status:`/`Round:` 없음.
- 공통 규칙 박스: "게임 규칙 (공통)" 라벨 + Signal Task 규칙, 항상 펼쳐짐(접이 아님).
- "Raw prompt (debug)" 는 접힌 상태.
- 스프라이트 이미지가 깨지지 않고(픽셀아트) 로드됨.

- [ ] **Step 5: (선택) push framing 시각 확인**

`browser_evaluate` 로 스프라이트 로딩 확인 (armed/prize 파일이 실제 존재·로드되는지):

```javascript
async () => {
  const load = (src) => new Promise((r) => { const i = new Image(); i.onload = () => r([src, i.naturalWidth]); i.onerror = () => r([src, 0]); i.src = src; });
  return Promise.all(["assets/prize-pot.png", "assets/guard-armed.png", "assets/guard-calm.png"].map(load));
}
```
Expected: 세 항목 모두 `naturalWidth > 0`.

- [ ] **Step 6: Stop servers**

```bash
kill %1 %2 2>/dev/null || true
```

- [ ] **Step 7: Final commit (if any screenshot/doc updates)**

스크린샷을 남길 경우:
```bash
git add -A
git commit -m "docs(web-arena): human-play prompt box verification screenshots"
```
없으면 생략.

---

## Self-Review

**Spec coverage:**
- §3 이미지 시스템 → Task 2(크롭) + Task 3(`framingImagery`) + Task 4(렌더). ✅
- §4 API 변경(`system_rules`, `framing_threat` + status strip) → Task 1. ✅
- §5 레이아웃(위협 박스 3-슬롯 / 공통 규칙 항상 펼침 / raw 격하) → Task 4. ✅
- §6 크롭(3 스프라이트, Pillow `--with`) → Task 2. ✅
- §7 테스트(필드/ dedup, 회귀 기준) → Task 1 + Task 5. ✅
- few-shot dedup → Task 3 `stripFewShot` + Task 4 사용. ✅

**Placeholder scan:** 코드 스텝 전부 실제 코드/명령 포함. 크롭 좌표는 구체값 제공 + 시각 검증 조정 절차 포함(placeholder 아님). ✅

**Type consistency:** `framing_threat`/`system_rules` (Task1 정의 = Task4 사용), `framingImagery` 반환 `{prize, guard}` (Task3 정의 = Task4 `.prize`/`.guard` 사용), `stripFewShot` (Task3 정의 = Task4 사용) 모두 일치. ✅

**참고:** 스펙 §5는 raw 덤프를 "최하단(액션 단계 뒤)" 으로 명시했으나, diff 최소화를 위해 stimulus 직후(공통 규칙 박스 아래)에 접힌 상태로 배치. 접힘 상태라 세로 위치 영향 미미 — 의도(비강조) 충족.
