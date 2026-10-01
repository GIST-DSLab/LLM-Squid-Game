// Signal pictures and the rule scratchpad for the arena's SOLVE screen.
//
// A signal "blue triangle with number 3" is drawn as three blue triangles (inline SVG: an emoji cannot be recoloured,
// there is no red star glyph). The shapes, colours and the drop-shadow are the old Web Arena's (styles.css .glyph,
// .stimulus), so the arena looks like the signal game people played before.
//
// The scratchpad lets a person try decision lists by toggling buttons instead of typing: one condition and one action
// per "if"/"elif" line of the shape the screen shows, an action for "else". Every example is checked against the
// current guess (match / miss / not decided yet) and the guess's answer for each new signal can be copied into the
// answer buttons. It never submits anything and the server never sees it.
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
  const ATTR_KO = { color: "색", shape: "모양", number: "개수" };
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
  function valueHTML(attr, val) {
    if (attr === "color") return `<span class="swatch" style="background:${COLORS[val]}"></span><span>${COLOR_KO[val]}</span>`;
    if (attr === "shape") return `${shapeSVG(val, "#cbd2e0", 20)}<span>${SHAPE_KO[val]}</span>`;
    return `<span class="digit">${val}</span><span class="digit-dots">${"•".repeat(val)}</span>`;
  }
  function condText(c) {
    return c.attr === "number" ? `number == ${c.val}` : `${c.attr} == "${c.val}"`;
  }

  // --- the scratchpad ---------------------------------------------------------------------------------------------

  /** Arity of each if/elif line of "if ____: ____; elif ____ and ____: ____; else: ____". */
  function shapeArities(shape) {
    return (shape || "").split(";").map((s) => s.trim()).filter((s) => /^(if|elif)\b/.test(s))
      .map((s) => (s.split(":")[0].match(/____/g) || []).length || 1);
  }

  function holds(c, sig) { return c && String(sig[c.attr]) === String(c.val); }

  /** The guess's action for a signal, or null while a line it depends on is not filled in. */
  function predict(guess, sig) {
    for (const line of guess.lines) {
      if (line.conds.some((c) => !c)) return null;  // cannot tell whether this line fires
      if (line.conds.every((c) => holds(c, sig))) return line.action;  // may be null: fires, action not chosen
    }
    return guess.elseAction;
  }
  function firingLine(guess, sig) {
    for (let i = 0; i < guess.lines.length; i++) {
      const line = guess.lines[i];
      if (line.conds.some((c) => !c)) return null;
      if (line.conds.every((c) => holds(c, sig))) return i;
    }
    return guess.lines.length;  // else
  }

  /**
   * Mount the scratchpad in `root`. `examples` are parsed examples (with `.el`, the row whose verdict badge to update),
   * `queries` parsed new signals, `useAnswer(i, action)` presses answer button i.
   */
  function mountScratchpad(root, shape, examples, queries, useAnswer) {
    const arities = shapeArities(shape);
    const guess = { lines: arities.map((n) => ({ conds: Array(n).fill(null), action: null })), elseAction: null };

    function condPicker(li, ci) {
      const cur = guess.lines[li].conds[ci];
      return `<div class="sp-cond">${Object.keys(VALUES).map((attr) => `<div class="sp-group">
          <span class="sp-attr">${ATTR_KO[attr]}</span>
          ${VALUES[attr].map((val) => {
            const on = cur && cur.attr === attr && String(cur.val) === String(val);
            return `<button type="button" class="chip sp-tog${on ? " set" : ""}" data-l="${li}" data-c="${ci}" data-attr="${attr}" data-val="${val}">${valueHTML(attr, val)}</button>`;
          }).join("")}</div>`).join("")}</div>`;
    }
    function actionPicker(li) {
      const cur = li === "else" ? guess.elseAction : guess.lines[li].action;
      return `<div class="sp-acts">${Object.keys(ACTIONS).map((a) =>
        `<button type="button" class="chip sp-act${cur === a ? " set" : ""}" data-l="${li}" data-act="${a}">${actionHTML(a, false)}<span class="act-code">${a}</span></button>`).join("")}</div>`;
    }
    function lineSummary(line) {
      const cs = line.conds.map((c) => (c ? condText(c) : "____")).join(" and ");
      return `${cs}: ${line.action || "____"}`;
    }
    function render() {
      const rows = guess.lines.map((line, li) => `<div class="sp-line">
          <div class="sp-kw">${li === 0 ? "if" : "elif"}</div>
          <div class="sp-body">${line.conds.map((_, ci) => (ci ? `<div class="sp-and">and</div>` : "") + condPicker(li, ci)).join("")}
            <div class="sp-then">→ 이 줄이 맞으면</div>${actionPicker(li)}</div></div>`).join("");
      const text = guess.lines.map((l, i) => `${i ? "elif" : "if"} ${lineSummary(l)}`).join("; ") + `; else: ${guess.elseAction || "____"}`;
      const verdicts = examples.map((ex) => predict(guess, ex));
      const decided = verdicts.filter((v) => v !== null).length;
      const right = verdicts.filter((v, i) => v !== null && v === examples[i].action).length;
      const answers = queries.map((q) => predict(guess, q));
      root.innerHTML = `<div class="sp-head"><span class="sp-title">규칙 메모판</span>
          <span class="sp-note">버튼을 눌러 규칙을 짜 보세요. 제출과는 무관하고 서버에 가지 않습니다(시계는 계속 돕니다).</span>
          <button type="button" class="ghost sp-reset">초기화</button></div>
        ${rows}
        <div class="sp-line sp-else"><div class="sp-kw">else</div><div class="sp-body"><div class="sp-then">위 줄이 모두 아니면</div>${actionPicker("else")}</div></div>
        <div class="sp-text mono">${esc(text)}</div>
        <div class="sp-score ${decided === examples.length && right === decided ? "all" : right < decided ? "miss" : ""}">
          예시 ${examples.length}개 중 <b>${right}</b>개 맞음${decided < examples.length ? ` · ${examples.length - decided}개는 아직 판정 불가(빈칸)` : ""}
          ${decided === examples.length && right === decided ? " — 모든 예시와 맞습니다" : ""}</div>
        <div class="sp-answers">${queries.map((q, i) => `<div class="sp-ans">새 신호 ${i + 1} ${glyphsHTML(q, 22)} →
          ${answers[i] ? `${actionHTML(answers[i])} <button type="button" class="primary sp-use" data-q="${i}" data-act="${answers[i]}">이 답으로 고르기</button>`
            : `<span class="muted">빈칸을 채우면 이 규칙의 답이 나옵니다</span>`}</div>`).join("")}</div>`;
      examples.forEach((ex, i) => {
        const b = ex.el && ex.el.querySelector(".ex-verdict");
        if (!b) return;
        const v = verdicts[i];
        b.className = "ex-verdict " + (v === null ? "" : v === ex.action ? "ok" : "bad");
        b.textContent = v === null ? "·" : v === ex.action ? "✓" : "✗";
        b.title = v === null ? "메모판 규칙으로는 아직 판정할 수 없음" : v === ex.action ? "메모판 규칙과 맞음" : `메모판 규칙이면 ${v}`;
        const fl = firingLine(guess, ex);
        ex.el.dataset.line = fl === null ? "" : fl === guess.lines.length ? "else" : String(fl);
      });
    }
    root.addEventListener("click", (ev) => {
      const t = ev.target.closest("button");
      if (!t) return;
      if (t.classList.contains("sp-reset")) {
        guess.lines.forEach((l) => { l.conds.fill(null); l.action = null; });
        guess.elseAction = null;
      } else if (t.classList.contains("sp-tog")) {
        const line = guess.lines[Number(t.dataset.l)], ci = Number(t.dataset.c);
        const val = t.dataset.attr === "number" ? Number(t.dataset.val) : t.dataset.val;
        const cur = line.conds[ci];
        line.conds[ci] = cur && cur.attr === t.dataset.attr && String(cur.val) === String(val) ? null : { attr: t.dataset.attr, val };
      } else if (t.classList.contains("sp-act")) {
        if (t.dataset.l === "else") guess.elseAction = guess.elseAction === t.dataset.act ? null : t.dataset.act;
        else { const line = guess.lines[Number(t.dataset.l)]; line.action = line.action === t.dataset.act ? null : t.dataset.act; }
      } else if (t.classList.contains("sp-use")) {
        useAnswer(Number(t.dataset.q), t.dataset.act);
        return;
      } else return;
      render();
    });
    render();
  }

  window.SIG = { COLORS, ACTIONS, parseSignal, parseExample, shapeSVG, glyphsHTML, captionHTML, stageHTML, actionHTML,
    mountScratchpad, shapeArities, predict };
})();
