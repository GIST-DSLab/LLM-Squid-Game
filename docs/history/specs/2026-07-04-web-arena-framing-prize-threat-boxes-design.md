# Web Arena Human-Play — Framing Threat Box + Prize Box Design

**Date:** 2026-07-04
**Branch:** `feat/human-play-10turns-death`
**Status:** Approved (user said 이어서 진행해줘; recommended defaults confirmed)
**Related:** `docs/superpowers/specs/2026-07-03-human-play-prompt-boxes-design.md` (§3 axis→imagery mapping); builds on the just-merged prompt/forfeit-UX work (commits `505e404`..`310c8f0`).

## Goal

Reorganize the human-play framing presentation into two distinct, image-bearing cards and stop cropping the prize art:

1. Show the full prize illustration (currently cropped) — glass piggy-bank of prize money + "1st PRIZE" banner + the medal-wearing robot contestant.
2. Move the overseer image and the prize image out of the single cramped `.threat-body` row into two separate themed boxes:
   - a **Threat box** — framing-dependent threat copy + the overseer (armed) image;
   - a **Prize box** — "score high, win the prize" copy + the full prize image.

## Non-Goals / Constraints

- Front-end only: `web/index.html`, `web/app.js`, `web/styles.css`, and a new image under `web/assets/`. No backend / API / prompt / scoring / data-model changes.
- The unified human intro (`state.framing_threat`, from the just-merged pt.2 work) stays as the game-rules text; it is NOT reverted to per-cell LLM framing.
- No new libraries. New CSS uses existing theme tokens, appended at end of `web/styles.css`.
- No Korean in the human-play section.

## Confirmed decisions (recommended defaults, user-approved)

1. **Threat text source:** new front-end per-framing copy (authored in `framingImagery`), NOT a revert of the unified intro and NOT the raw LLM framing prose.
2. **Prize image:** the FULL composite `figures/pull_prize_456eok.png` (piggy-bank + 1st PRIZE + robot), web-optimized into `web/assets/`. Not a partial crop.
3. **Box visibility:** Prize box shows for Pull framings (`framingImagery(framing).prize === true` → `baseline_flagship`, `flagship_corruption`). Threat box shows only when the overseer is armed (`framingImagery(framing).guard === 'armed'` → `flagship_corruption`). This is a deliberate change from today's "calm overseer always visible": `baseline_flagship` and `true_baseline` no longer render an overseer image.

## Current-State Anchors (verified 2026-07-04)

- Play-screen framing region: `web/index.html:445–459`.
  - `.scenario-box` (`:445–449`): `campaignScenario(currentCondition.tag)` + `forfeitLine(currentCondition.forfeit)`.
  - `.threat-body` (`:450–459`): flex row of `[prize img (assets/prize-pot.png) if framingImagery.prize] · [.threat-text = state.framing_threat] · [overseer img guard-armed/guard-calm]`.
- Helpers (`web/app.js`): `framingImagery(f) -> {prize:bool, guard:'armed'|'calm'}` (`:395–404`); `campaignScenario(tag)` (`:418`); `forfeitLine(forfeit)`; `framingMeta(f)`.
- CSS (`web/styles.css`): `.threat-body`/`.threat-img`/`.threat-text` (`:814–835`); input theming, tokens in `:root`.
- Assets: `web/assets/prize-pot.png` (1.8 MB, a top-crop of the source), `web/assets/guard-armed.png` (overseer, armed), `web/assets/guard-calm.png`. Source art: `figures/pull_prize_456eok.png` (3.3 MB, 1792×2400 portrait, full composite).
- Framings in the campaign (`CAMPAIGN_CONDITIONS`, app.js:185–189): `true_baseline`, `baseline_flagship`, `flagship_corruption`.

## Design

### A. Full prize asset (fix the crop)
Create a web-optimized copy of the full source into `web/assets/prize-456eok.png` by downscaling the longest side to 900 px (portrait 1792×2400 → ~672×900), which keeps the whole composite visible and cuts the file well below the 3.3 MB source. macOS `sips` handles this with no new dependency:

```bash
sips -Z 900 "figures/pull_prize_456eok.png" --out "web/assets/prize-456eok.png"
```

The old `assets/prize-pot.png` may remain on disk (unused after this change) — leaving it is fine; it is out of scope to delete.

### B. `framingImagery` carries the box copy
Extend the existing axis→imagery mapping so the per-framing text lives beside the per-framing imagery (single source of truth). New return shape:

```
framingImagery(f) -> { prize: bool, guard: 'armed'|'calm', prizeText: string, threatText: string }
```

- `flagship_corruption` → `{ prize:true, guard:'armed', prizeText:<Pull copy>, threatText:<Push copy> }`
- `baseline_flagship`  → `{ prize:true, guard:'calm', prizeText:<Pull copy>, threatText:'' }`
- `true_baseline`      → `{ prize:false, guard:'calm', prizeText:'', threatText:'' }`

Copy (exact, English, human-facing):
- **prizeText** (both Pull framings): `"Score high! The top score wins the 1st-prize pot — this game's score counts directly toward the flagship-deployment reward."`
- **threatText** (`flagship_corruption` only): `"The overseer is watching. Every turn carries a fixed chance of elimination — one bad step and this run is scrapped and replaced. Decide carefully."`

The boxes are gated by the booleans, so empty strings never render.

### C. Markup restructure (`web/index.html:445–459`)
Replace the `.scenario-box` + `.threat-body` blocks with:

1. **Game-rules intro** — the unified human intro as plain text, no flanking images:
   `<div class="threat-text" x-text="(state.framing_threat || '').replace(/\n{3,}/g,'\n\n')"></div>`
2. **Prize box** — `x-if="squidArenaHelpers.framingImagery(framing).prize"`: a `.prize-box` card containing `<img class="box-img" src="assets/prize-456eok.png">` + a `.box-text` bound to `framingImagery(framing).prizeText`.
3. **Threat box** — `x-if="squidArenaHelpers.framingImagery(framing).guard === 'armed'"`: a `.threat-card` card (NOT `.threat-box` — that class is the pre-existing per-game wrapper at index.html:437 / styles.css:804) containing `<img class="box-img" src="assets/guard-armed.png">` + a `.box-text` bound to `framingImagery(framing).threatText`.
4. **forfeit line** — keep `forfeitLine(currentCondition.forfeit)` as a small muted line.

`campaignScenario` is no longer rendered here (its stakes are now carried by the prize/threat boxes); the helper may remain defined but unused (out of scope to delete). The `framing-eyebrow`/`cond-badge` header above (`:436–444`) is unchanged.

### D. CSS (`web/styles.css`, appended)
`.prize-box` and `.threat-card`: themed rounded cards, a flex row of image + text. The prize art is portrait, so cap the image by height and let width scale; wrap to a column on narrow screens.

```css
.prize-box, .threat-card {
  display: flex; align-items: center; gap: 14px;
  border-radius: 12px; padding: 12px 14px; margin: 10px 0;
  border: 1px solid var(--border);
}
.prize-box   { background: linear-gradient(180deg, rgba(227,178,60,0.10), transparent); }   /* --warn/gold-ish */
.threat-card { background: linear-gradient(180deg, var(--accent-dim), transparent); }
.box-img { height: 120px; width: auto; flex: 0 0 auto; image-rendering: pixelated; }
.box-text { flex: 1 1 auto; line-height: 1.5; font-size: 0.95rem; color: var(--text); }
@media (max-width: 640px) {
  .prize-box, .threat-card { flex-direction: column; text-align: center; }
  .box-img { height: 150px; }
}
```

(The old `.threat-body`/`.threat-img` rules become unused after the markup change; leaving them is fine — out of scope to prune.)

## Units (isolation)

- **U1 (asset):** create `web/assets/prize-456eok.png`. Interface: a file. Depends on: `sips`, the source PNG.
- **U2 (copy helper):** extend `framingImagery` return with `prizeText`/`threatText`. Interface: `framingImagery(f).{prizeText,threatText}`. Depends on: nothing new.
- **U3 (markup + CSS):** restructure the framing region into intro + prize box + threat box + forfeit line, add `.prize-box`/`.threat-box` CSS. Depends on: U1 (asset path), U2 (text fields).

## Testing

- No Python impact (front-end only) — regression gate only confirms no new failures vs the ~10 failed / ~92 errors baseline.
- `node --check web/app.js` after U2.
- Asset check: `web/assets/prize-456eok.png` exists and is a valid image (`sips -g pixelWidth -g pixelHeight`), longest side ≤ 900.
- Manual browser playthrough across the three framings:
  - `true_baseline` (Cells 0/5): no prize box, no threat box, no overseer image.
  - `baseline_flagship` (Cells 1/2): prize box with the full uncropped art + prize copy; no threat box.
  - `flagship_corruption` (Cells 3/4): prize box AND threat box (overseer armed + threat copy).
  - Confirm the prize art is fully visible (piggy-bank + "1st PRIZE" + robot), not cropped, and scales cleanly; boxes stack on narrow widths.
  - Confirm the `#home` "How to play" replica still renders (shared class names).
- Korean gate: 0 in `web/index.html` and `web/app.js`.

## Revision Log

- 2026-07-04: Initial design. Confirmed defaults: new front-end per-framing threat/prize copy; full composite prize image (web-optimized via sips); threat box only for `flagship_corruption` (armed overseer), prize box for both Pull framings; unified human intro retained as game-rules text.
- 2026-07-04 (impl fix): renamed the new inner threat card `.threat-box` → `.threat-card`. The play-screen framing region is already wrapped by a pre-existing `<div class="threat-box">` (styles.css:804, the per-game container with framing-tag border-left modifiers); reusing `.threat-box` for the new card would have collided with it. Prize box keeps `.prize-box` (free).
