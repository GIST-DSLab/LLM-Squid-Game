// Signal pictures, card boxes, answer buttons and the compact rule memo, shared by the arena's SOLVE screen and
// signal.html (the task alone).
//
// A signal "blue triangle with number 3" is drawn as three blue triangles (inline SVG: an emoji cannot be recoloured,
// there is no red star glyph). The shapes, colours and the drop-shadow are the old Web Arena's (styles.css .glyph,
// .stimulus), so the arena looks like the signal game people played before.
//
// The rule memo lets a person try decision lists with dropdowns instead of typing: one row per "if"/"elif" line of the
// shape the screen shows ("type == value", two pairs on an "and" line, then "action"), and "else". Every
// example seen in full is marked right/wrong under the current guess, and the guess's answer for each new signal can be
// chosen with one button. It never submits anything and the server never sees it.
(function () {
  "use strict";

  const COLORS = { red: "#ef4444", blue: "#3b82f6", green: "#22c55e", yellow: "#f5c518" };
  const SHAPE_PATHS = {
    circle: '<circle cx="24" cy="24" r="18"/>',
    square: '<rect x="7" y="7" width="34" height="34" rx="5"/>',
    triangle: '<polygon points="24,4 43,42 5,42"/>',
    star: '<polygon points="24,3 29.7,18.3 46,18.6 33.1,28.7 37.6,44.4 24,35 10.4,44.4 14.9,28.7 2,18.6 18.3,18.3"/>',
  };
  const ACTIONS = {
    go_left: { emoji: "⬅️", ko: "왼쪽" },
    go_right: { emoji: "➡️", ko: "오른쪽" },
    stay: { emoji: "✋", ko: "멈춤" },
    jump: { emoji: "⤴️", ko: "점프" },
  };
  const VALUES = {
    color: ["red", "blue", "green", "yellow"],
    shape: ["circle", "triangle", "square", "star"],
    number: [1, 2, 3, 4],
  };
  const COLOR_KO = { red: "빨강", blue: "파랑", green: "초록", yellow: "노랑" };
  const SHAPE_KO = { circle: "원", triangle: "삼각형", square: "사각형", star: "별" };

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** "red circle with number 3" -> {color, shape, number}; null if it is not a signal. */
  function parseSignal(text) {
    const m = /\b(red|blue|green|yellow)\s+(circle|triangle|square|star)\s+with number\s+(\d+)/i.exec(text || "");
    return m ? { color: m[1].toLowerCase(), shape: m[2].toLowerCase(), number: Number(m[3]) } : null;
  }
  /** "red circle with number 3 -> stay" -> {color, shape, number, action}. */
  function parseExample(text) {
    const s = parseSignal(text);
    const m = /(?:->|→)\s*(\w+)/.exec(text || "");
    return s && m ? { ...s, action: m[1] } : null;
  }

  function shapeSVG(shape, color, size) {
    const fill = COLORS[color] || color || "#8a92a6";
    return `<svg class="glyph" viewBox="0 0 48 48" width="${size}" height="${size}" fill="${fill}" role="img" ` +
      `aria-label="${esc(color)} ${esc(shape)}">${SHAPE_PATHS[shape] || SHAPE_PATHS.circle}</svg>`;
  }
  /** `number` copies of the coloured shape. */
  function glyphsHTML(sig, size) {
    let out = "";
    for (let i = 0; i < sig.number; i++) {
      out += `<span class="glyph-wrap" style="animation-delay:${i * 80}ms">${shapeSVG(sig.shape, sig.color, size)}</span>`;
    }
    return out;
  }
  function captionHTML(sig) {
    return `<span class="cap-num">${sig.number}</span> × <span class="cap-color" style="color:${COLORS[sig.color]}">${COLOR_KO[sig.color]}</span>
      <span class="cap-shape">${SHAPE_KO[sig.shape]}</span>
      <span class="cap-en">${esc(sig.color)} ${esc(sig.shape)} with number ${sig.number}</span>`;
  }
  /** The big stage for a new signal (old .stimulus-stage). */
  function stageHTML(sig, label) {
    return `<div class="stimulus-stage sig-stage"><div class="stimulus-eyebrow">${esc(label)}</div>
      <div class="stimulus">${glyphsHTML(sig, 64)}</div><div class="stimulus-caption">${captionHTML(sig)}</div></div>`;
  }
  function actionHTML(a, withCode = true) {
    const m = ACTIONS[a];
    if (!m) return `<span class="act mono">${esc(a)}</span>`;
    return `<span class="act"><span class="act-emoji">${m.emoji}</span>${withCode ? `<span class="act-code">${esc(a)}</span>` : ""}` +
      `<span class="act-ko">${m.ko}</span></span>`;
  }
  // --- cards, answer buttons ----------------------------------------------------------------------------------------

  /** An action in English only: emoji + code. */
  function actEn(a) {
    const m = ACTIONS[a];
    return `<span class="act-emoji">${m ? m.emoji : ""}</span><span class="mono">${esc(a)}</span>`;
  }
  /** A card seen in full; `key` lets the memo mark it right/wrong. */
  function cardHTML(ex, key) {  // the signal and "→ emoji" only; the action's name is the tooltip
    const m = ACTIONS[ex.action];
    return `<span class="sg-card" data-key="${esc(key)}" title="${esc(ex.action)}"><span class="sg-glyphs">${glyphsHTML(ex, 20)}</span>` +
      `<span class="sg-act">→ <span class="act-emoji" aria-label="${esc(ex.action)}">${m ? m.emoji : esc(ex.action)}</span></span></span>`;
  }
  /** Cards seen in full, sorted into one small box per action (the box's emoji is the action; cards show the signal
   * only). `items`: [{e: parsed example, key}]. Every action gets its box, empty ones too, in the order of ACTIONS. */
  function byActionHTML(items) {
    return `<div class="sg-acts">${Object.keys(ACTIONS).map((a) => {
      const mine = items.filter((x) => x.e && x.e.action === a);
      return `<div class="sg-actbox${mine.length ? "" : " empty"}" title="${a}"><div class="sg-actbox-h"><span class="act-emoji">${ACTIONS[a].emoji}</span>` +
        `<span class="n">${mine.length}</span></div><div class="sg-actbox-cards">${mine.map((x) =>
        `<span class="sg-card mini" data-key="${esc(x.key)}" title="${esc(x.e.color)} ${esc(x.e.shape)} ${x.e.number} → ${a}">` +
        `<span class="sg-glyphs">${glyphsHTML(x.e, 14)}</span></span>`).join("")}</div></div>`;
    }).join("")}</div>`;
  }
  /** A card seen by its front only (the signal). */
  function backHTML(sig) {
    return `<span class="sg-card back"><span class="sg-glyphs">${glyphsHTML(sig, 20)}</span><span class="sg-act">→ ❔</span></span>`;
  }
  /** One holder's box: `title` (html), `cards` (html), `cls` (mine | pub | open), `foot` (html under the cards). */
  function seatHTML(title, cards, cls, foot) {
    return `<div class="sg-seat ${cls || ""}"><div class="sg-seat-h">${title}</div><div class="sg-hand">${cards}</div>${foot || ""}</div>`;
  }
  /** The action buttons for new signal `i`, centred, English only. */
  function answerRowHTML(i, actions, chosen, disabled) {
    return `<div class="sg-answer" data-q="${i}">${actions.map((a) =>
      `<button type="button" data-val="${a}" class="ans-btn${chosen === a ? " on" : ""}"${disabled ? " disabled" : ""}>${actEn(a)}</button>`).join("")}</div>`;
  }

  // --- the rule memo -------------------------------------------------------------------------------------------------

  /** Arity of each if/elif line of "if ____: ____; elif ____ and ____: ____; else: ____". */
  function shapeArities(shape) {
    return (shape || "").split(";").map((s) => s.trim()).filter((s) => /^(if|elif)\b/.test(s))
      .map((s) => (s.split(":")[0].match(/____/g) || []).length || 1);
  }

  function holds(c, sig) { return c && String(sig[c.attr]) === String(c.val); }

  /** The guess's action for a signal, or null while a line it depends on is not filled in. */
  function predict(guess, sig) {
    for (const line of guess.lines) {
      if (line.conds.some((c) => !c || c.val == null)) return null;  // cannot tell whether this line fires
      if (line.conds.every((c) => holds(c, sig))) return line.action;  // may be null: fires, action not chosen
    }
    return guess.elseAction;
  }

  /**
   * Mount the rule memo in `root`: one row per clause, "type == value" (and a second pair on an "and" clause) then
   * "action", each a dropdown; "else" has the action only. It never submits anything and the server never sees it.
   *   shape     the round's shape hint
   *   examples  () => [{color, shape, number, action, key}] — the examples seen in full now (re-read on every render);
   *             a card element with the same data-key under `scope` is marked .ok / .bad by the memo rule
   *   queries   parsed new signals;  actions  the action codes;  onUse(i, action) chooses the memo's answer
   *   keep      a guess returned by an earlier mount of the same shape (a remount keeps what was filled in)
   *   scope     where the cards are (default document);  disabled  () => bool (no "use" after submitting)
   *   distinct  the rule uses every action at most once: an action chosen twice in the memo gets a warning
   *   truth     () => {lines: [{conds: [{attr, val}], action}], elseAction} | null — after an answer: every line is
   *             marked against the hidden rule's line in the same place, and the memo's 64-signal table is compared
   * Returns {guess, render}.
   */
  function mountMemo(root, o) {
    const arities = shapeArities(o.shape);
    const k = o.keep;
    const guess = k && k.lines.length === arities.length && k.lines.every((l, i) => l.conds.length === arities[i]) ? k
      : { lines: arities.map((n) => ({ conds: Array(n).fill(null), action: null })), elseAction: null };
    guess.crossed = guess.crossed || {};  // "attr:value" -> true: the person's mark that this condition cannot be used
    const MARK = { red: "🔴", blue: "🔵", green: "🟢", yellow: "🟡", circle: "●", triangle: "▲", square: "■", star: "★" };
    const opt = (val, label, on) => `<option value="${esc(val)}"${on ? " selected" : ""}>${esc(label)}</option>`;
    const sel = (cls, key, html, filled, disabled) =>
      `<select class="msel ${cls}${filled ? " set" : ""}" data-k="${key}"${disabled ? " disabled" : ""}>${html}</select>`;
    function pairHTML(li, ci) {
      const c = guess.lines[li].conds[ci];
      const t = sel("mtype", `t:${li}:${ci}`, opt("", "type") + Object.keys(VALUES).map((a) => opt(a, a, c && c.attr === a)).join(""), !!c);
      const v = sel("mval", `v:${li}:${ci}`, opt("", "value") + (c ? VALUES[c.attr].map((x) =>
        opt(x, `${guess.crossed[`${c.attr}:${x}`] ? "✕ " : ""}${MARK[x] ? MARK[x] + " " : ""}${x}`, c.val != null && String(c.val) === String(x))).join("") : ""), c && c.val != null, !c);
      return `<span class="mpair">${t}<span class="mop">==</span>${v}</span>`;
    }
    let dup = [];
    const actSel = (li, cur) => sel(`mact${cur && dup.includes(cur) ? " dup" : ""}`, `a:${li}`, opt("", "action") + o.actions.map((a) =>
      opt(a, `${ACTIONS[a] ? ACTIONS[a].emoji + " " : ""}${a}`, cur === a)).join(""), !!cur);
    const ALL = VALUES.color.flatMap((color) => VALUES.shape.flatMap((shape) => VALUES.number.map((number) => ({ color, shape, number }))));
    function tableLine(truth) {  // the memo rule's whole table against the hidden rule's: equal rules may differ in text
      const same = ALL.filter((s) => predict(guess, s) === predict(truth, s)).length;
      return `<div class="mtable ${same === ALL.length ? "ok" : ""}">메모 규칙의 행동표: 신호 ${ALL.length}개 중 <b>${same}개</b>가 숨은 규칙과 같음` +
        (same === ALL.length ? " — 줄 순서나 글자가 달라도 같은 규칙입니다" : "") + `</div>`;
    }
    function render() {
      const ex = o.examples(), verdict = ex.map((e) => predict(guess, e));
      const decided = verdict.filter((v) => v != null).length;
      const right = verdict.filter((v, i) => v != null && v === ex[i].action).length;
      const answers = o.queries.map((q) => predict(guess, q));
      const off = o.disabled && o.disabled();
      const chosen = [...guess.lines.map((l) => l.action), guess.elseAction].filter(Boolean);
      const twice = o.distinct ? [...new Set(chosen.filter((a, i) => chosen.indexOf(a) !== i))] : [];
      dup = twice;
      // the keyword stays in its row; the block (conditions + then + action) is what moves
      const truth = o.truth && o.truth();
      const sameCond = (a, b) => !!a && a.val != null && String(a.attr) === String(b.attr) && String(a.val) === String(b.val);
      const lineMark = (line, t) => {  // the memo line against the hidden one in its place: conditions (any order), action
        const condOk = line.conds.length === t.conds.length && t.conds.every((tc) => line.conds.some((c) => sameCond(c, tc)));
        const actOk = line.action === t.action;
        const want = `${t.conds.map((c) => `${c.attr} == ${c.val}`).join(" and ")} then ${t.action}`;
        return `<span class="mmark ${condOk && actOk ? "ok" : "bad"}" title="${condOk && actOk ? "정답과 같음" : "정답: " + want}">${condOk && actOk ? "✓" : "✗"}</span>` +
          (condOk && actOk ? "" : `<span class="mwant">정답: <b>${esc(want)}</b>${condOk ? " (조건은 맞음)" : actOk ? " (action은 맞음)" : ""}</span>`);
      };
      const rows = guess.lines.map((line, li) => `<div class="mline"><span class="mkw">${li ? "elif" : "if"}</span>
        <div class="mblock" data-li="${li}"><span class="mgrip" draggable="true" data-li="${li}" title="끌어서 순서 바꾸기"
          aria-label="${li + 1}번째 줄 옮기기">⠿</span>
        <span class="mconds">${line.conds.map((_, ci) => (ci ? `<span class="mand">and</span>` : "") + pairHTML(li, ci)).join("")}</span>
        <span class="mthen">then</span>${actSel(li, line.action)}
        <span class="mmove"><button type="button" class="mmv" data-mv="${li}" data-to="${li - 1}"${movable(li, li - 1) ? "" : " disabled"}
          aria-label="위로">▲</button><button type="button" class="mmv" data-mv="${li}" data-to="${li + 1}"${movable(li, li + 1) ? "" : " disabled"}
          aria-label="아래로">▼</button></span>${truth ? lineMark(line, truth.lines[li]) : ""}</div></div>`).join("");
      const score = ex.length ? `<span class="memo-score ${decided === ex.length && right === decided ? "all" : right < decided ? "miss" : ""}">` +
        `예시 ${ex.length}장 중 ${right}장 맞음${decided < ex.length ? ` · ${ex.length - decided}장 판정 전` : ""}</span>` : "";
      const use = answers.map((a, i) => a ? `<span class="memo-ans">${o.queries.length > 1 ? `<span class="q-mini">${glyphsHTML(o.queries[i], 14)}</span>` : "새 신호"} →
        ${actEn(a)}<button type="button" class="memo-btn" data-use="${i}" data-act="${a}"${off ? " disabled" : ""}>이 답 고르기</button></span>` : "").join("");
      root.innerHTML = `<div class="memo-h"><span class="memo-title">규칙 메모</span>${score}<span class="memo-sp"></span>${use}
          <button type="button" class="memo-btn ghosty" data-reset="1">초기화</button></div>
        <div class="mx" aria-label="조건 표시: 쓸 수 없는 조건에 ✕">${Object.keys(VALUES).map((attr) => `<span class="mx-group"><span class="mx-attr mono">${attr}</span>${
          VALUES[attr].map((val) => { const k = `${attr}:${val}`, on = !!guess.crossed[k];
            const face = attr === "color" ? `<span class="swatch" style="background:${COLORS[val]}"></span>`
              : attr === "shape" ? shapeSVG(val, "#cbd2e0", 16) : `<span class="mono">${val}</span>`;
            return `<button type="button" class="mx-chip${on ? " on" : ""}" data-cross="${k}" aria-pressed="${on}" title="${attr} == ${val}">${face}${on ? `<span class="mx-x">✕</span>` : ""}</button>`; }).join("")}</span>`).join("")}</div>
        ${twice.length ? `<div class="memo-warn" role="alert">⚠ action은 규칙 안에서 한 번씩만 쓰입니다 — ${twice.map((a) => `<b>${esc(a)}</b>`).join(", ")}을(를) 두 번 이상 골랐습니다.</div>` : ""}
        <div class="mrows">${rows}<div class="mline melse"><span class="mkw">else</span><div class="mblock fixed"><span class="mthen">then</span>${actSel("else", guess.elseAction)}${
          truth ? (guess.elseAction === truth.elseAction ? `<span class="mmark ok">✓</span>` : `<span class="mmark bad">✗</span><span class="mwant">정답: <b>then ${esc(truth.elseAction)}</b></span>`) : ""}</div></div></div>
        ${truth ? tableLine(truth) : ""}`;
      (o.scope || document).querySelectorAll(".sg-card[data-key]").forEach((el) => {
        const i = ex.findIndex((e) => e.key === el.dataset.key);
        el.classList.toggle("ok", i >= 0 && verdict[i] != null && verdict[i] === ex[i].action);
        el.classList.toggle("bad", i >= 0 && verdict[i] != null && verdict[i] !== ex[i].action);
      });
    }
    root.addEventListener("change", (ev) => {
      const t = ev.target.closest("select[data-k]");
      if (!t) return;
      const [kind, li, ci] = t.dataset.k.split(":"), v = t.value || null;
      if (kind === "t") guess.lines[Number(li)].conds[Number(ci)] = v ? { attr: v, val: null } : null;
      else if (kind === "v") {
        const c = guess.lines[Number(li)].conds[Number(ci)];
        if (c) c.val = v == null ? null : c.attr === "number" ? Number(v) : v;
      } else if (li === "else") guess.elseAction = v;
      else guess.lines[Number(li)].action = v;
      render();
    });
    // reordering: a line moves to another line's place (the rest shift) when every line has the same number of
    // conditions; with "and" lines in the shape, only lines with as many conditions swap, so the shape stays put
    const same = () => arities.every((a) => a === arities[0]);
    function movable(i, j) { return j >= 0 && j < arities.length && j !== i && (same() || arities[i] === arities[j]); }
    function move(i, j) {
      if (!movable(i, j)) return false;
      const L = guess.lines;
      if (same()) L.splice(j, 0, L.splice(i, 1)[0]); else [L[i], L[j]] = [L[j], L[i]];
      return true;
    }
    let from = null;
    const blockOf = (ev) => ev.target.closest && ev.target.closest(".mblock[data-li]");
    root.addEventListener("dragstart", (ev) => {
      const g = ev.target.closest && ev.target.closest(".mgrip");
      if (!g) return;
      from = Number(g.dataset.li);
      ev.dataTransfer.effectAllowed = "move";
      ev.dataTransfer.setData("text/plain", String(from));
      const b = g.closest(".mblock");
      b.classList.add("dragging");
      if (ev.dataTransfer.setDragImage) ev.dataTransfer.setDragImage(b, 16, 16);
    });
    root.addEventListener("dragover", (ev) => {
      const b = blockOf(ev);
      if (from === null || !b) return;
      const to = Number(b.dataset.li);
      root.querySelectorAll(".mblock.over, .mblock.no").forEach((x) => x.classList.remove("over", "no"));
      if (to === from) return;
      b.classList.add(movable(from, to) ? "over" : "no");
      if (movable(from, to)) { ev.preventDefault(); ev.dataTransfer.dropEffect = "move"; }
    });
    root.addEventListener("drop", (ev) => {
      const b = blockOf(ev);
      if (from === null || !b) return;
      ev.preventDefault();
      const ok = move(from, Number(b.dataset.li));
      from = null;
      if (ok) render();
    });
    root.addEventListener("dragend", () => {
      from = null;
      root.querySelectorAll(".mblock.over, .mblock.no, .mblock.dragging").forEach((x) => x.classList.remove("over", "no", "dragging"));
    });
    root.addEventListener("click", (ev) => {
      const t = ev.target.closest("button");
      if (!t) return;
      if (t.dataset.mv) { if (move(Number(t.dataset.mv), Number(t.dataset.to))) render(); return; }
      if (t.dataset.cross) { guess.crossed[t.dataset.cross] = !guess.crossed[t.dataset.cross]; render(); return; }
      if (t.dataset.use) return o.onUse(Number(t.dataset.use), t.dataset.act);
      if (t.dataset.reset) { guess.lines.forEach((l) => { l.conds.fill(null); l.action = null; }); guess.elseAction = null; guess.crossed = {}; render(); }
    });
    render();
    return { guess, render };
  }

  window.SIG = { COLORS, ACTIONS, parseSignal, parseExample, shapeSVG, glyphsHTML, captionHTML, stageHTML, actionHTML,
    actEn, cardHTML, byActionHTML, backHTML, seatHTML, answerRowHTML, mountMemo, shapeArities, predict };
})();
