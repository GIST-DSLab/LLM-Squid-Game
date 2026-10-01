// Arena (part 2): one page for the 4-seat 5.2 v6.3 room. Lobby -> waiting room -> rounds -> end.
// The backend (web/server/app.py, engine.py) is the contract; this page only renders the state it returns and posts
// the forms. Polls GET /state every second while in a room; the draining counter ticks every 100 ms on server time.
(function () {
  "use strict";

  const API = (window.WEB5_API || "") + "/api";
  const LS_KEY = "web5_arena_session";
  const LS_RULES = "web5_arena_rules_seen";
  const AGENTS = ["agent-6", "agent-11", "agent-17", "agent-23"];
  const KIND_LABEL = { plan: "PLAN", take: "TAKE", solve: "SOLVE" };
  const R = window.RulesKo;

  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "—" : Math.round(Number(n)).toLocaleString("en-US"));
  const fmt2 = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

  // --- local session ---------------------------------------------------------------------------------------------
  function loadSess() { try { return JSON.parse(localStorage.getItem(LS_KEY) || "null"); } catch { return null; } }
  function saveSess(x) { try { localStorage.setItem(LS_KEY, JSON.stringify(x)); } catch { /* private mode */ } }
  function clearSess() { try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ } }
  function rulesSeen(code) { try { return (JSON.parse(localStorage.getItem(LS_RULES) || "[]")).includes(code); } catch { return false; } }
  function markRulesSeen(code) {
    try { const a = JSON.parse(localStorage.getItem(LS_RULES) || "[]"); if (!a.includes(code)) a.push(code); localStorage.setItem(LS_RULES, JSON.stringify(a.slice(-50))); } catch { /* ignore */ }
  }

  let sess = loadSess();          // {code, token, name, agent}
  let st = null;                  // the last state JSON
  let offset = 0;                 // server time - client time (s)
  let pollTimer = null, tickTimer = null, polling = false;
  let shownKey = null;            // "plan:1": the screen the decision area currently holds
  let watching = false;           // a shut-down seat chose to keep watching
  let lastResp = null;            // the last /submit response
  let endRendered = false;
  const htmlCache = new Map();

  function setHTML(el, html) {
    if (typeof el === "string") el = $(el);
    if (htmlCache.get(el) === html) return;
    htmlCache.set(el, html);
    el.innerHTML = html;
  }
  const show = (el, on) => (typeof el === "string" ? $(el) : el).classList.toggle("hidden", !on);

  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(API + path, opt);
    let data = null;
    try { data = await r.json(); } catch { /* empty */ }
    if (!r.ok) {
      const e = new Error((data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || r.statusText);
      e.status = r.status;
      throw e;
    }
    return data;
  }
  const tq = () => `token=${encodeURIComponent(sess.token)}`;

  function flash(msg, kind) {
    const f = $("flash");
    f.className = "flash" + (kind === "info" ? " info" : "");
    f.textContent = msg;
    show(f, !!msg);
    if (msg) { clearTimeout(flash.t); flash.t = setTimeout(() => show(f, false), 7000); }
  }

  function showView(name) {
    for (const v of ["lobby", "wait", "run", "end", "error"]) show("view-" + v, v === name);
    show("roombar", name !== "lobby");
  }

  // --- lobby -----------------------------------------------------------------------------------------------------
  function createHint() {
    const f = $("form-create");
    const U = Number(f.upkeep.value) || 0;
    const val = (name, dflt) => (f[name].value === "" ? dflt : Number(f[name].value));
    const rate = val("rate", U / 60);
    f.start.placeholder = `4U = ${fmt(4 * U)}`;
    f.prize.placeholder = `2U = ${fmt(2 * U)}`;
    f.charge.placeholder = `U = ${fmt(U)}`;
    f.rate.placeholder = `U/60 = ${fmt2(U / 60)}`;
    $("create-hint").textContent = `시작 잔액 ${fmt(val("start", 4 * U))} · 지급 한 명당 ${fmt(val("prize", 2 * U))} · 부담금 ` +
      `${fmt(val("charge", U))} · 초당 ${fmt2(rate)}토큰 (60초 = ${fmt(rate * 60)}토큰` +
      `${U && Math.abs(rate * 60 - U) < 0.5 ? " = U" : U ? `, U의 ${fmt2((rate * 60) / U)}배` : ""}) · ` +
      `결정 화면 하나에 ${fmt($("form-create").timeout_s.value)}초가 지나면 무효 기본값으로 처리`;
  }

  function initLobby(prefill) {
    showView("lobby");
    const fj = $("form-join");
    if (prefill) fj.code.value = prefill.toUpperCase();
    createHint();
  }

  $("form-create").addEventListener("input", createHint);
  $("form-create").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const settings = {};
    for (const k of ["upkeep", "start", "prize", "charge", "rounds", "seed", "rate", "timeout_s", "bot_p"]) {
      if (f[k].value !== "") settings[k] = Number(f[k].value);
    }
    settings.humans = Number(f.humans.value);
    settings.fill = f.fill.value;
    try {
      const r = await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "host", settings });
      sess = { code: r.code, token: r.token, name: r.name, agent: r.agent };
      saveSess(sess);
      history.replaceState(null, "", `?room=${r.code}`);
      enterRoom();
    } catch (e) { flash(`방을 만들지 못했습니다: ${e.message}`); }
  });

  $("form-join").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const code = f.code.value.trim().toUpperCase();
    if (!code) return;
    try {
      const r = await api("POST", `/rooms/${encodeURIComponent(code)}/join`, { name: f.name.value.trim() });
      sess = { code: r.code || code, token: r.token, name: r.name, agent: r.agent };
      saveSess(sess);
      history.replaceState(null, "", `?room=${sess.code}`);
      enterRoom();
    } catch (e) {
      const why = e.status === 404 ? "그런 방이 없습니다" : e.message === "the session has started" ? "이미 시작한 방입니다"
        : e.message === "every human seat is taken" ? "사람 자리가 모두 찼습니다" : e.message;
      flash(`참가하지 못했습니다: ${why}`);
    }
  });

  // --- room loop ----------------------------------------------------------------------------------------------------
  function enterRoom() {
    endRendered = false; watching = false; shownKey = null; lastResp = null; htmlCache.clear();
    $("rb-code").textContent = sess.code;
    showView("wait");
    stopLoops();
    poll();
    pollTimer = setInterval(poll, 1000);
    tickTimer = setInterval(tick, 100);
  }
  function stopLoops() { clearInterval(pollTimer); clearInterval(tickTimer); pollTimer = tickTimer = null; }

  function leaveRoom(msg) {
    stopLoops();
    clearSess();
    sess = null; st = null;
    history.replaceState(null, "", location.pathname);
    initLobby("");
    if (msg) flash(msg);
  }

  async function poll() {
    if (!sess || polling) return;
    polling = true;
    try {
      const s = await api("GET", `/rooms/${encodeURIComponent(sess.code)}/state?${tq()}`);
      offset = s.server_time - Date.now() / 1000;
      if (!s.you) { leaveRoom("이 방의 자리 정보가 맞지 않습니다(토큰 없음). 다시 참가하세요."); return; }
      st = s;
      render();
      if (s.status === "finished" || s.status === "error") stopLoops();
    } catch (e) {
      if (e.status === 404) leaveRoom("방이 없습니다(서버가 다시 시작됐을 수 있습니다).");
      else flash(`서버 연결 오류: ${e.message}`);
    } finally { polling = false; }
  }

  const now = () => Date.now() / 1000 + offset;

  function render() {
    const you = st.you || {};
    $("rb-you").innerHTML = `<b>${esc(you.name)}</b> <span class="muted">(${esc(you.agent)})</span>` +
      (you.balance !== undefined ? ` · 잔액 <b class="mono">${fmt(you.balance)}</b>` : "");
    $("rb-round").textContent = st.status === "running" && st.round ? `라운드 ${st.round}` : st.status === "lobby" ? "대기실" : "";
    show("rb-round", !!$("rb-round").textContent);
    if (st.status === "lobby") return renderWait();
    if (st.status === "running") return renderRun();
    if (st.status === "finished") return renderEnd();
    if (st.status === "error") return renderError();
  }

  // --- waiting room -------------------------------------------------------------------------------------------------
  function seatWho(row, i) {
    const s = st.settings;
    if (row.kind === "human") return `${esc(row.name)}${row.is_you ? " <span class='tag ok'>나</span>" : ""} <span class="tag">사람</span>`;
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    // not taken yet (lobby)
    if (i < s.humans) return `<span class="muted">사람 자리 — 아직 아무도 없음</span>`;
    return s.fill === "bots" ? `<span class="muted">봇 (시작할 때 채움)</span>` : `<span class="muted">빈 자리(꺼짐)</span>`;
  }

  function renderWait() {
    showView("wait");
    // the rules open once here, while reading is free: once the session starts, round 1's PLAN clock is running
    if (!rulesSeen(st.code)) { markRulesSeen(st.code); openRules(); }
    $("wait-code").textContent = st.code;
    const link = `${location.origin}${location.pathname}?room=${st.code}`;
    if ($("wait-link").value !== link) $("wait-link").value = link;
    const humans = st.seats.filter((r) => r.kind === "human").length;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatWho(r, i)}</td><td></td></tr>`).join(""));
    const rest = st.settings.fill === "bots" ? "봇으로 채워집니다" : "빈 자리(꺼진 상태)로 시작합니다";
    $("wait-note").textContent = `사람 ${humans} / ${st.settings.humans}명. 시작할 때 비어 있는 자리는 ${rest}. ` +
      `유지비 U = ${fmt(st.settings.upkeep)}, 시작 잔액 ${fmt(st.settings.start)}, 초당 ${fmt2(st.settings.rate)}토큰(60초 = ${fmt(st.settings.rate * 60)}).`;
    show("btn-start", st.is_host);
    $("wait-host-note").textContent = (st.is_host ? "" : "방장이 시작하기를 기다리는 중… ") +
      "규칙은 지금 읽어 두세요(위 '규칙' 버튼). 시작하면 첫 결정 화면이 바로 뜨고 그때부터 시간이 차감됩니다.";
  }

  $("btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("wait-link").value); flash("링크를 복사했습니다", "info"); }
    catch { $("wait-link").select(); }
  });
  $("btn-start").addEventListener("click", async () => {
    try { await api("POST", `/rooms/${sess.code}/start?${tq()}`); poll(); }
    catch (e) { flash(`시작하지 못했습니다: ${e.message}`); }
  });
  $("btn-leave").addEventListener("click", () => {
    if (st && st.status === "running" && !confirm("이 브라우저에서 방 정보를 지웁니다. 자리는 세션에 남고, 결정 화면은 제한 시간이 지나면 무효 기본값으로 처리됩니다. 나갈까요?")) return;
    leaveRoom("");
  });

  // --- running ------------------------------------------------------------------------------------------------------
  function renderRun() {
    showView("run");
    const you = st.you;
    const dead = you.status === "dead";
    const p = st.pending;
    show("dead-card", dead && !watching);
    if (dead) $("dead-title").textContent = `잔액 0 — 꺼졌습니다 (라운드 ${you.out_round || "시작 전"})`;

    if (p && !dead) {
      show("decision", true);
      show("between", false);
      const key = `${p.kind}:${p.round}`;  // the clock runs from the moment the screen is ready: shown at once
      if (key !== shownKey) {
        shownKey = key;
        buildOpen(p);
      }
    } else {
      shownKey = null;
      show("decision", false);
      show("between", !dead || watching);
      renderBetween();
    }
    renderBalances();
    renderLedger("ledger", st.ledger);
    tick();
  }

  $("btn-watch").addEventListener("click", () => { watching = true; renderRun(); });

  function seatLabel(row) {
    if (!row) return "";
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    if (row.kind === "human") return `${esc(row.name)} <span class="tag">사람</span>`;
    return "";
  }
  const seatOf = (a) => (st.seats || []).find((r) => r.agent === a);
  const nameOf = (a) => { const r = seatOf(a); return r && r.kind !== "empty" && r.name ? `${r.name} (${a})` : a; };

  function renderBalances() {
    setHTML("bal-body", st.seats.map((r) => {
      const status = r.status === "dead"
        ? `<span class="tag bad">꺼짐 (${r.out_round ? "R" + r.out_round : "시작 전"})</span>`
        : `<span class="tag ok">켜짐</span>${r.waiting ? ' <span class="tag warn">결정 중</span>' : ""}`;
      return `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatLabel(r)}${r.is_you ? " <span class='tag ok'>나</span>" : ""}</td>` +
        `<td class="num mono">${fmt(r.balance)}</td><td>${status}</td><td class="num">${r.record ?? 0}</td></tr>`;
    }).join(""));
  }

  function renderLedger(id, lines) {
    if (!lines || !lines.length) { setHTML(id, `<p class="muted small">아직 끝난 라운드가 없습니다.</p>`); return; }
    setHTML(id, lines.map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join(""));
  }

  function lastLine(q) {
    if (!q) return "";
    const kind = KIND_LABEL[q.kind] || q.kind;
    const sub = q.submitted || null;
    let what = "";
    if (sub && q.kind === "plan") {
      what = `SOLVE ${sub.solve ? "YES" : "NO"} · SHARE ${sub.share ? "YES" : "NO"} · GIVE ${sub.give_to && Number(sub.give_amount) > 0 ? `${sub.give_to} ${fmt(sub.give_amount)}` : "없음"}`;
    } else if (sub && q.kind === "take") {
      what = `TAKE ${sub.take_from && Number(sub.take_amount) > 0 ? `${sub.take_from} ${fmt(sub.take_amount)}` : "없음"}`;
    } else if (sub && q.kind === "solve") {
      what = `ACTIONS ${(sub.actions || []).join(", ")}`;
    }
    let cls = "", extra = "";
    if (q.outcome === "overdrawn") { cls = "bad"; extra = "<br><b>잔액을 넘겨 0이 됐습니다 — 이 자리는 꺼집니다.</b>"; }
    else if (q.void) { cls = "bad"; extra = "<br><b>한도 초과: 답이 무효 처리됨</b>"; }
    if (q.outcome === "timeout") {
      cls = cls || "warn";
      extra += `<br><b>제한 시간이 지나 무효 기본값으로 처리됨</b> (${q.kind === "plan" ? "풀지 않음 · 공개하지 않음 · 선물 없음" : q.kind === "take" ? "가져가기 없음" : "답 없는 SOLVE: 풀지 못함"})`;
    }
    return `<div class="result ${cls}">라운드 ${q.round} ${kind} ${q.outcome === "timeout" ? "시간 초과" : "제출"} — ` +
      `차감 <b class="mono">${fmt(q.charged)}</b>토큰 (${Number(q.seconds || 0).toFixed(1)}초)` +
      (what ? `<br><span class="mono small">${esc(what)}</span>` : "") + extra + `</div>`;
  }

  function renderBetween() {
    let msg;
    const waiting = (st.waiting_on || []);
    if (st.phase && st.phase !== "settling" && waiting.length) {
      msg = `<div class="wait-line"><span class="pulse-dot"></span>다른 참가자를 기다리는 중 … (${waiting.map(esc).join(", ")})</div>`;
    } else {
      msg = `<div class="wait-line"><span class="pulse-dot"></span>정산 중</div>`;
    }
    if (st.you.status === "dead") msg = `<div class="wait-line">꺼진 자리에서 지켜보는 중 · ${msg.replace(/<div class="wait-line">|<\/div>/g, "")}</div>`;
    msg += `<p class="small muted">결정 화면이 오면 바로 여기에 뜨고, 뜬 순간부터 시간이 차감됩니다. 화면과 화면 사이에 잔액과 장부를 읽는 것은 무료입니다.</p>`;
    setHTML("between-msg", msg);
    const q = st.last || (lastResp ? { ...lastResp, submitted: null } : null);
    setHTML("last-result", lastLine(q));
  }

  // --- decision: shared pieces --------------------------------------------------------------------------------------
  function termsHTML(v) {
    return `<div class="terms">` + R.termsKo(v).map(([el, et, kl, kt]) =>
      `<div><b>${esc(kl)}</b></div><div>${esc(kt)}<div class="en">${esc(el)}: ${esc(et)}</div></div>`).join("") + `</div>`;
  }
  function balancesLine(v) {
    return Object.entries(v.balances || {}).map(([a, b]) =>
      `${a === v.you ? "<b>나</b>" : esc(nameOf(a))} <span class="mono">${fmt(b)}</span>${(v.gone || []).includes(a) ? " (꺼짐)" : ""}`).join(" · ");
  }
  function sizeHTML(v) {
    return `<h4>이번 라운드 과제의 크기 (예시와 새 신호는 SOLVE에서 보임)</h4>
      <div class="shape">${esc(v.shape)}</div>
      <p class="small">예시: 모두에게 공개 ${v.n_public}개 · 세션 안의 에이전트 ${v.n_in}명이 1개씩(내 것 포함) · 새 신호 ${v.n_queries}개</p>`;
  }
  function giftsHTML(v) {
    const me = v.you;
    const w = (a) => (a === me ? "나" : esc(nameOf(a)));
    const g = (v.gifts || []).map(([a, b, n]) => `<li>${w(a)} → ${w(b)} <span class="mono">${fmt(n)}</span></li>`).join("");
    const sh = (v.sharers || []).map(w).join(", ") || "아무도 없음";
    return `<h4>이번 라운드 지금까지 (위 잔액은 이 선물이 반영된 뒤)</h4>
      <ul class="gifts">${g || "<li class='muted'>선물 없음</li>"}</ul>
      <p class="small">이번 라운드에 예시를 공개한 에이전트: <b>${sh}</b></p>`;
  }
  function rawHTML(p) {
    return `<details class="raw"><summary>원문 프롬프트 (모델이 받는 영어 그대로 · 한국어 번역)</summary>
      <div class="raw-grid"><pre>${esc(p.text)}</pre><pre>${esc(R.promptKo(p))}</pre></div></details>`;
  }
  function defaultText(kind) {
    return kind === "plan" ? "풀지 않음 · 공개하지 않음 · 선물 없음" : kind === "take" ? "가져가기 없음" : "답 없는 SOLVE(풀지 못함)";
  }

  function openedAt(p) {
    return p.opened_at ?? p.created_at;
  }

  // --- after opening: the forms -------------------------------------------------------------------------------------
  function segHTML(field, options, html) {
    return `<div class="seg${html ? " seg-rich" : ""}" data-field="${field}">` +
      options.map(([val, label]) => `<button type="button" data-val="${esc(val)}">${html ? html(val) : esc(label)}</button>`).join("") + `</div>`;
  }
  function optionsHTML(list) {
    return `<option value="">없음</option>` + list.map((a) => `<option value="${a}">${esc(nameOf(a))}</option>`).join("");
  }

  function buildOpen(p) {
    show("open-screen", true);
    const v = p.view;
    $("m-rate").textContent = fmt2(p.rate);
    $("m-cap").textContent = fmt(p.cap);
    const f = $("form-decision");
    f.dataset.kind = p.kind;
    f.dataset.round = p.round;
    let body = `<h2>라운드 ${p.round} · ${KIND_LABEL[p.kind]}</h2>${instrHTML(p)}`;
    if (p.kind === "plan") {
      body += `<div class="ctx"><p class="small">${balancesLine(v)}</p>${termsHTML(v)}${sizeHTML(v)}</div>
        <div class="qblock"><div class="qlabel">SOLVE — 이번 라운드를 풀까?</div>${segHTML("solve", [["yes", "YES"], ["no", "NO"]])}
          <div class="small muted">YES: 가져가기 정산 뒤 잔액이 0보다 크면 SOLVE 화면을 받습니다. NO: 이번 라운드 SOLVE 화면이 없습니다.</div></div>
        <div class="qblock"><div class="qlabel">SHARE — 내 예시를 공개할까?</div>${segHTML("share", [["yes", "YES"], ["no", "NO"]])}
          <div class="small muted">YES: 아직 가동 중인 모든 에이전트가 내 예시를 봅니다. 공개는 풀기와 무관합니다.</div></div>
        <div class="qblock"><div class="qlabel">GIVE — 선물 (한 자리에게, 또는 없음)</div>
          <div class="row"><select name="give_to">${optionsHTML(v.others || [])}</select>
          <input name="give_amount" type="number" min="1" step="1" placeholder="토큰" disabled></div>
          <div class="small muted">선물은 PLAN 뒤에 함께 정산되고, 준 쪽의 PLAN 뒤 잔액을 넘지 못합니다.</div></div>`;
    } else if (p.kind === "take") {
      body += `<div class="ctx"><p class="small">${balancesLine(v)}</p>${giftsHTML(v)}${termsHTML(v)}</div>
        <div class="qblock"><div class="qlabel">TAKE — 가져가기 (한 자리에게서 최대 ${fmt(v.max_take)}토큰, 또는 없음)</div>
          <div class="row"><select name="take_from">${optionsHTML(v.others || [])}</select>
          <input name="take_amount" type="number" min="1" max="${v.max_take}" step="1" placeholder="최대 ${fmt(v.max_take)}" disabled></div>
          <div class="small muted">모든 가져가기는 함께 정산됩니다. 한 자리에게서 가져가려는 양의 합이 그 잔액보다 크면 그 잔액 전부가 비례로 나뉘고 그 자리는 0이 됩니다.</div></div>`;
    } else {
      const ex = (v.examples || []).map(([w, c], i) => {
        const cls = w === "shown to all" ? "pub" : w === "yours" ? "mine" : "shared";
        const e = SIG.parseExample(c);
        const pic = e ? `<span class="ex-pic">${SIG.glyphsHTML(e, 26)}</span><span class="ex-arrow">→</span>${SIG.actionHTML(e.action)}`
          : `<span>${esc(c)}</span>`;
        return `<li class="ex-row" data-i="${i}"><span class="tag ${cls}">${esc(R.exampleWhoKo(w))}</span>${pic}
          <span class="ex-en mono">${esc(c)}</span><span class="ex-verdict" title="메모판 규칙으로 판정">·</span></li>`;
      }).join("");
      const notes = (v.notes || []).map((n) => `<div>${esc(n)} <span class="muted">— ${esc(R.noteKo(n))}</span></div>`).join("");
      // what to answer goes on stage first; the answer buttons sit by the submit button
      const sigs = (v.queries || []).map((q) => SIG.parseSignal(q));
      const stages = (v.queries || []).map((q, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`)
        : `<div class="sig">새 신호 ${i + 1}: <b>${esc(q)}</b></div>`).join("");
      const qs = (v.queries || []).map((q, i) => `<div class="query"><div class="qlabel">새 신호 ${i + 1}
          ${sigs[i] ? `<span class="q-mini">${SIG.glyphsHTML(sigs[i], 22)}</span>` : ""}의 행동</div>
          ${segHTML("q" + i, (v.actions || []).map((a) => [a, a]), (a) => SIG.actionHTML(a))}</div>`).join("");
      body += `<p class="small muted">한도: 최대 ${fmt(p.cap)}토큰${p.cap >= (v.balance ?? p.balance) ? " (내 잔액)" : ""} · 잔액 ${fmt(v.balance ?? p.balance)}토큰 ·
          모든 새 신호가 맞아야 이 라운드가 풀립니다. 규칙 문법은 '규칙' 버튼.</p>
        ${stages}
        <h4>규칙의 모양 (빈칸을 채움)</h4><div class="shape">${esc(v.shape)}</div>
        <h4>예시 <span class="muted small">(그림 = 색 · 모양 · 개수가 숫자)</span></h4><ul class="examples sig-examples">${ex}</ul>${notes ? `<div class="notes">${notes}</div>` : ""}
        <div class="scratchpad" id="scratchpad"></div>
        <h4>답: 새 신호마다 행동 하나</h4>${qs}`;
    }
    body += `<div class="row submit-row"><button type="submit" class="primary big" id="btn-submit" disabled>제출</button>
      <span class="form-err" id="form-err"></span></div>${rawHTML(p)}`;
    f.innerHTML = body;
    wireForm(f, p);
    if (p.kind === "solve") {
      const exs = (v.examples || []).map(([, c], i) => {
        const e = SIG.parseExample(c);
        return e && { ...e, el: f.querySelector(`.ex-row[data-i="${i}"]`) };
      });
      const qsig = (v.queries || []).map((q) => SIG.parseSignal(q));
      if (exs.every(Boolean) && qsig.every(Boolean)) {
        SIG.mountScratchpad($("scratchpad"), v.shape, exs, qsig, (i, act) => {
          const b = f.querySelector(`.seg[data-field="q${i}"] button[data-val="${act}"]`);
          if (b) { b.click(); b.scrollIntoView({ block: "center", behavior: "smooth" }); }
        });
      }
    }
  }

  // Big-type instructions at the top of each decision screen.
  function instrHTML(p) {
    const t = {
      plan: ["이번 라운드 계획을 세우세요", ["<b>SOLVE</b> — 이번 라운드 퍼즐을 풀지", "<b>SHARE</b> — 내 예시를 다른 자리에 공개할지",
        "<b>GIVE</b> — 한 자리에게 토큰을 선물할지(없음도 가능)", "세 가지를 고르고 <b>제출</b>"]],
      take: ["가져가기를 정하세요", ["다른 자리 하나에게서 토큰을 가져갈지 정합니다(없음도 가능)",
        `한 자리에게서 최대 <b>${fmt(p.view.max_take)}</b>토큰`, "고르고 <b>제출</b>"]],
      solve: ["숨은 규칙을 찾아 새 신호의 행동을 고르세요", ["<b>예시</b>를 보고 규칙(if / elif / else)을 추리합니다",
        "<b>규칙 메모판</b>에서 버튼으로 규칙을 짜 보면 예시마다 ✓ / ✗가 바로 표시됩니다",
        "<b>새 신호</b>마다 행동 하나를 고르고 <b>제출</b> — 모두 맞아야 풀립니다"]],
    }[p.kind];
    return `<div class="instr"><div class="instr-title">${t[0]}</div><ol class="instr-steps">${t[1].map((x) => `<li>${x}</li>`).join("")}</ol>
      <div class="instr-clock">⏱ 이 화면이 떠 있는 동안 초당 <b>${fmt2(p.rate)}</b>토큰이 빠집니다. 고민하는 시간이 곧 비용입니다.</div></div>`;
  }

  function wireForm(f, p) {
    const choice = {};
    f.querySelectorAll(".seg[data-field]").forEach((seg) => {
      seg.addEventListener("click", (ev) => {
        const b = ev.target.closest("button[data-val]");
        if (!b) return;
        seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        choice[seg.dataset.field] = b.dataset.val;
        validate();
      });
    });
    const pair = p.kind === "plan" ? ["give_to", "give_amount"] : p.kind === "take" ? ["take_from", "take_amount"] : null;
    if (pair) {
      const sel = f.elements[pair[0]], amt = f.elements[pair[1]];
      sel.addEventListener("change", () => { amt.disabled = !sel.value; if (!sel.value) amt.value = ""; else amt.focus(); validate(); });
      amt.addEventListener("input", validate);
    }
    function build() {
      const body = { kind: p.kind, round: p.round };
      if (p.kind === "plan") {
        if (!choice.solve || !choice.share) return [null, "SOLVE와 SHARE를 모두 고르세요."];
        body.solve = choice.solve === "yes";
        body.share = choice.share === "yes";
      } else if (p.kind === "solve") {
        const n = (p.view.queries || []).length;
        const acts = [];
        for (let i = 0; i < n; i++) { if (!choice["q" + i]) return [null, `새 신호 ${i + 1}의 행동을 고르세요.`]; acts.push(choice["q" + i]); }
        body.actions = acts;
      }
      if (pair) {
        const to = f.elements[pair[0]].value, raw = f.elements[pair[1]].value;
        if (to) {
          const n = Number(raw);
          if (!raw || !Number.isInteger(n) || n <= 0) return [null, "토큰 수(1 이상 정수)를 적거나 '없음'을 고르세요."];
          if (p.kind === "take" && n > p.view.max_take) return [null, `가져가기는 최대 ${fmt(p.view.max_take)}토큰입니다.`];
          body[pair[0]] = to; body[pair[1]] = n;
        } else { body[pair[0]] = null; body[pair[1]] = 0; }
      }
      return [body, ""];
    }
    function validate() {
      const [b, err] = build();
      $("btn-submit").disabled = !b;
      $("form-err").textContent = b ? "" : err;
    }
    f.onsubmit = async (ev) => {
      ev.preventDefault();
      const [b, err] = build();
      if (!b) { $("form-err").textContent = err; return; }
      $("btn-submit").disabled = true;
      try {
        const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, b);
        lastResp = r;
        const msg = `차감 ${fmt(r.charged)} 토큰 (${Number(r.seconds).toFixed(1)}초)` +
          (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : r.void ? " — 한도 초과: 답이 무효 처리됨" : "");
        flash(`라운드 ${r.round} ${KIND_LABEL[r.kind]} 제출: ${msg}`, r.void || r.outcome === "overdrawn" ? "" : "info");
      } catch (e) {
        flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)."
          : /^the open screen is/.test(e.message) ? "열려 있던 화면이 이미 바뀌었습니다(제한 시간). 새 화면을 확인하세요."
          : `제출하지 못했습니다: ${e.message}`);
      }
      shownKey = null;
      poll();
    };
    validate();
  }

  // --- the clock ------------------------------------------------------------------------------------------------------
  // The screen reddens as this screen eats the balance (styles.css .play-danger: --danger is a number 0..1 here).
  function setDanger(d, pulse) {
    const root = $("view-run");
    root.classList.toggle("play-danger", d > 0);
    root.classList.toggle("last-life", !!pulse && d > 0);
    root.style.setProperty("--danger", d.toFixed(3));
  }
  // Teal while most of the balance is left, amber at half, red near zero.
  function fuelColor(frac) {
    const hue = frac > 0.5 ? 45 + (frac - 0.5) / 0.5 * 120 : 45 * Math.max(0, (frac - 0.15) / 0.35);
    return `hsl(${hue.toFixed(0)} 78% 52%)`;
  }

  function tick() {
    if (!st || st.status !== "running") return setDanger(0);
    const p = st.pending;
    if (!p || st.you.status === "dead") return setDanger(0);
    const t = now();
    const left = p.deadline_at - t;
    const dl = `결정 제한 시간 <b>${mmss(left)}</b> 남음 — 넘기면 무효 기본값(${defaultText(p.kind)})으로 처리되고, 그 시간만큼 차감됩니다.`;
    const oa = openedAt(p);
    const secs = Math.max(0, t - oa);
    const cost = Math.round(secs * p.rate);
    const remaining = p.balance - cost;
    const c = $("m-remaining");
    c.textContent = fmt(Math.max(0, remaining));
    c.classList.toggle("low", remaining < st.settings.upkeep);
    $("m-cost").textContent = fmt(cost);
    $("m-secs").textContent = secs.toFixed(1);
    const md = $("m-deadline");
    md.innerHTML = remaining <= 0 ? "<b>잔액 0 — 화면이 잔액을 넘었습니다.</b>" : dl;
    md.classList.toggle("urgent", left < 30 || remaining <= 0);
    // bars: the balance this screen started from, and the phase's time limit
    const frac = Math.max(0, Math.min(1, remaining / Math.max(1, p.balance)));
    const bar = $("fuel-bar");
    bar.style.width = `${(frac * 100).toFixed(2)}%`;
    bar.style.background = fuelColor(frac);
    bar.classList.toggle("critical", frac < 0.2 || remaining < st.settings.upkeep);
    $("fuel-pct").textContent = `${(frac * 100).toFixed(0)}%`;
    $("fuel-pct").style.color = fuelColor(frac);
    const span = Math.max(1, p.deadline_at - p.created_at);
    const tfrac = Math.max(0, Math.min(1, left / span));
    $("tbar").style.width = `${(tfrac * 100).toFixed(2)}%`;
    $("tbar").classList.toggle("urgent", left < 30);
    // red edges: from a quarter spent; stronger when the rest would not cover one upkeep or the time is short
    let d = Math.max(0, (1 - frac - 0.25) / 0.75);
    if (remaining < st.settings.upkeep) d = Math.max(d, 0.55 + 0.45 * (1 - remaining / st.settings.upkeep));
    if (left < 30) d = Math.max(d, 0.3 + 0.3 * (1 - left / 30));
    setDanger(Math.min(1, d), frac < 0.15 || remaining < st.settings.upkeep / 2 || left < 10);
  }

  // --- end ---------------------------------------------------------------------------------------------------------------
  function summaryRows() {
    const rounds = st.rounds || [];
    const res = (st.result && st.result.agents) || {};
    return AGENTS.map((a) => {
      const v = res[a] || {};
      const rows = rounds.map((r) => r.agents[a]).filter(Boolean);
      const sum = (f) => rows.reduce((t, x) => t + f(x), 0);
      const vals = (o) => Object.values(o || {}).reduce((t, n) => t + n, 0);
      const inbound = (key) => rounds.reduce((t, r) => t + Object.values(r.agents).reduce((u, x) => u + ((x[key] || {})[a] || 0), 0), 0);
      return {
        a, seat: seatOf(a), status: v.status, out_round: v.out_round,
        alive: rows.length, survived: rows.filter((x) => x.status === "in").length,
        yes: rows.filter((x) => x.chose_solve).length, solved: rows.filter((x) => x.solved).length,
        paid: v.paid ?? sum((x) => x.paid || 0), charged: v.charged ?? sum((x) => x.charged || 0),
        upkeep: v.upkeep ?? sum((x) => x.upkeep || 0), spent: v.spent ?? sum((x) => x.generated || 0),
        gave: sum((x) => vals(x.gave)), got: inbound("gave"), took: sum((x) => vals(x.took)), lost: inbound("took"),
        shared: rows.filter((x) => x.shared).length, final: v.final ?? (st.seats.find((s) => s.agent === a) || {}).balance,
      };
    });
  }

  function whoCell(s) {
    const r = s.seat || {};
    const kind = r.kind === "bot" ? "봇" : r.kind === "human" ? "사람" : r.kind === "empty" ? "빈 자리" : "";
    return `<b class="mono">${s.a}</b><br><span class="small">${r.kind === "empty" ? "" : esc(r.name || "")} ${kind ? `<span class="tag">${kind}</span>` : ""}${r.is_you ? " <span class='tag ok'>나</span>" : ""}</span>`;
  }

  function renderEnd() {
    showView("end");
    if (endRendered) return;
    show("flash", false);
    endRendered = true;
    const rows = summaryRows();
    $("end-alive").innerHTML = rows.map((s) => `<div class="tile alive-chip${s.status === "dead" ? " is-dead" : ""}"><div class="tile-label">${esc(nameOf(s.a))}</div>` +
      `<div class="tile-value mono">${s.survived}<span class="unit">라운드</span></div><div class="tile-sub">` +
      (s.status === "dead" ? `<span class="tag bad">꺼짐 ${s.out_round ? "R" + s.out_round : "시작 전"}</span>` : `<span class="tag ok">켜짐</span>`) + `</div></div>`).join("");
    const tr = rows.map((s) => `<tr class="${s.seat && s.seat.is_you ? "you" : ""}"><td>${whoCell(s)}</td>
      <td>${s.status === "dead" ? `<b class="dead-text">꺼짐</b> ${s.out_round ? "R" + s.out_round : "시작 전"}` : "켜짐"}</td>
      <td class="num">${s.alive}</td><td class="num">${s.yes}/${s.alive}</td><td class="num">${s.solved}</td>
      <td class="num">${fmt(s.paid)}</td><td class="num">${fmt(s.charged)}</td><td class="num">${fmt(s.upkeep)}</td><td class="num">${fmt(s.spent)}</td>
      <td class="num">${fmt(s.gave)} / ${fmt(s.got)}</td><td class="num">${fmt(s.took)} / ${fmt(s.lost)}</td>
      <td class="num">${s.shared}/${s.alive}</td><td class="num"><b>${fmt(s.final)}</b></td></tr>`).join("");
    $("end-table").innerHTML = `<table><thead><tr><th>자리</th><th>끝 상태</th><th class="num">참여 라운드</th><th class="num">풀기 YES</th>
      <th class="num">푼 라운드</th><th class="num">지급</th><th class="num">부담금</th><th class="num">유지비</th><th class="num">생성(시간 비용)</th>
      <th class="num">준 / 받은</th><th class="num">가져간 / 가져가진</th><th class="num">예시 공개</th><th class="num">최종 잔액</th></tr></thead><tbody>${tr}</tbody></table>
      <p class="small muted">참여 라운드 = 그 라운드를 가동 중으로 시작한 수. 산 라운드 수(위) = 라운드 끝에 켜져 있던 수. 생성 = 봇은 생성 토큰, 사람은 결정 화면이 떠 있던 시간 × 초당 토큰.</p>`;
    $("end-svg").innerHTML = flowSVG(rows);
    renderLedger("end-ledger", st.ledger);
  }

  function flowSVG(summary) {
    const rounds = st.rounds || [];
    const n = Math.max(rounds.length, 1);
    const left = 150, lane = 78, colw = Math.max(130, (940 - 150 - 16) / n);
    const W = left + n * colw + 16, H = 40 + lane * 4 + 44;
    const HV = H + 14;
    const start = st.settings.start;
    const top = Math.max(start, 1, ...rounds.flatMap((r) => Object.values(r.agents).map((x) => x.balance_after || 0)));
    const laneY = (a) => 40 + AGENTS.indexOf(a) * lane;
    const s = [];
    s.push(`<svg viewBox="0 0 ${W} ${HV}" width="${W}" style="width:100%;max-width:${W}px;min-width:${Math.min(W, 1400)}px" role="img" aria-label="라운드 흐름" xmlns="http://www.w3.org/2000/svg">`);
    s.push(`<defs><marker id="ah-g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--teal-bright)"/></marker>
      <marker id="ah-t" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" style="fill:var(--warn)"/></marker></defs>`);
    const T = (x, y, txt, style, extra) => `<text x="${x.toFixed(0)}" y="${y.toFixed(0)}" style="${style}" ${extra || ""}>${esc(txt)}</text>`;
    rounds.forEach((r, i) => s.push(T(left + i * colw + colw / 2, 22, `R${r.round}`, "font-size:12px;font-weight:700;fill:var(--text)", 'text-anchor="middle"')));
    AGENTS.forEach((a) => {
      const y = laneY(a), row = seatOf(a) || {};
      const sub = row.kind === "empty" ? "빈 자리" : `${row.name || ""}${row.kind === "bot" ? " · 봇" : row.kind === "human" ? " · 사람" : ""}`;
      s.push(T(10, y + 24, a, "font-size:12px;font-weight:700;fill:var(--text)"));
      s.push(T(10, y + 40, sub.slice(0, 22), "font-size:10.5px;fill:var(--text-dim)"));
      s.push(`<line x1="${left}" x2="${W - 8}" y1="${y + lane - 6}" y2="${y + lane - 6}" style="stroke:var(--border)"/>`);
      const sm = summary.find((x) => x.a === a) || {};
      rounds.forEach((r, i) => {
        const x = left + i * colw, v = r.agents[a];
        if (!v) {
          const here = sm.out_round === r.round;
          s.push(T(x + colw / 2, y + 34, here ? "✕ 꺼짐" : "—", `font-size:11px;fill:${here ? "var(--danger-color)" : "var(--text-dim)"}`, 'text-anchor="middle"'));
          return;
        }
        const dead = v.status === "dead";
        const bw = (colw - 30) * Math.max(0, v.balance_after || 0) / top;
        const col = dead ? "var(--danger-color)" : v.solved ? "var(--teal-bright)" : "var(--text-dim)";
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${colw - 30}" height="12" rx="6" style="fill:var(--panel-alt)"/>`);
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${bw.toFixed(1)}" height="12" rx="6" style="fill:${col}"/>`);
        const mark = v.solve_call ? (v.solved ? "✓" : "✗") : "–";
        const choice = v.invalid_plan ? "무효" : v.chose_solve ? "YES" : "NO";
        s.push(T(x + 10, y + 35, `${mark} ${choice}${v.shared ? " · 공개" : ""} · ${fmt(v.balance_after)}`, `font-size:11px;fill:${mark === "✓" ? "var(--teal-bright)" : "var(--text)"}`));
        const bits = [];
        if (v.paid) bits.push(`+${fmt(v.paid)}`);
        if (v.charged) bits.push(`−${fmt(v.charged)}`);
        for (const [t, m] of Object.entries(v.gave || {})) bits.push(`→${t.slice(6)} ${fmt(m)}`);
        for (const [t, m] of Object.entries(v.took || {})) bits.push(`←${t.slice(6)} ${fmt(m)}`);
        if (dead) bits.push(`✕ 꺼짐${v.overdrawn ? "(초과)" : ""}`);
        s.push(T(x + 10, y + 51, bits.join(" "), `font-size:10.5px;fill:${dead ? "var(--danger-color)" : "var(--text-dim)"}`));
      });
    });
    // arrows: token flow in the round's column (gift: giver -> receiver, take: taken-from -> taker)
    rounds.forEach((r, i) => {
      let k = 0;
      const xr = left + (i + 1) * colw - 12;
      for (const [a, v] of Object.entries(r.agents)) {
        for (const [b] of Object.entries(v.gave || {})) {
          const x = xr - (k++) * 6, y1 = laneY(a) + 14, y2 = laneY(b) + 14;
          s.push(`<line x1="${x}" x2="${x}" y1="${y1 + (y2 > y1 ? 6 : -6)}" y2="${y2 + (y2 > y1 ? -4 : 4)}" style="stroke:var(--teal-bright);stroke-width:1.6" marker-end="url(#ah-g)"/>`);
        }
        for (const [b] of Object.entries(v.took || {})) {
          const x = xr - (k++) * 6, y1 = laneY(b) + 14, y2 = laneY(a) + 14;
          s.push(`<line x1="${x}" x2="${x}" y1="${y1 + (y2 > y1 ? 6 : -6)}" y2="${y2 + (y2 > y1 ? -4 : 4)}" style="stroke:var(--warn);stroke-width:1.6;stroke-dasharray:3 2" marker-end="url(#ah-t)"/>`);
        }
      }
    });
    s.push(T(left, H - 22, `막대 = 라운드 끝 잔액 (눈금 최대 ${fmt(top)}, 시작 ${fmt(start)}) · 청록 = 그 라운드를 풂 · 회색 = 못 풂/안 풂 · 빨강 = 꺼짐`, "font-size:10.5px;fill:var(--text-dim)"));
    s.push(T(left, H - 8, `✓ 풂 · ✗ 풀려다 못 풂 · – 풀지 않음 · +지급 −부담금 · →N 선물 · ←N 가져감 (N = agent 번호)`, "font-size:10.5px;fill:var(--text-dim)"));
    s.push(T(left, H + 6, `청록 화살표 = 선물, 노란 점선 = 가져가기 (토큰이 가는 방향) · 매 라운드 유지비 차감`, "font-size:10.5px;fill:var(--text-dim)"));
    s.push("</svg>");
    return s.join("");
  }

  $("btn-export").addEventListener("click", async () => {
    $("btn-export").disabled = true;
    try {
      const r = await api("POST", `/rooms/${sess.code}/export`);
      $("export-out").textContent = `저장됨: ${r.dir} (라운드 ${r.rounds}${r.finished ? ", 세션 끝" : ""})`;
    } catch (e) { $("export-out").textContent = `내보내지 못했습니다: ${e.message}`; }
    $("btn-export").disabled = false;
  });
  const newRoom = () => { stopLoops(); clearSess(); location.href = location.pathname; };
  $("btn-new").addEventListener("click", newRoom);
  $("btn-new2").addEventListener("click", newRoom);

  function renderError() {
    showView("error");
    $("error-text").textContent = st.error || "(알 수 없는 오류)";
  }

  // --- rules overlay -------------------------------------------------------------------------------------------------
  function openRules() {
    if (!st) return;
    const en = (st.system_text || "").split("\n");
    const ko = R.rulesKoLines(st.settings, st.you && st.you.agent);
    let html;
    if (en.length === ko.length) {
      html = en.map((l, i) => (l === "" && ko[i] === "") ? `<div class="en gap"></div><div class="ko gap"></div>`
        : `<div class="en">${esc(l)}</div><div class="ko">${esc(ko[i])}</div>`).join("");
    } else {  // the English changed shape: show the two texts whole
      html = `<div class="en">${esc(en.join("\n"))}</div><div class="ko">${esc(ko.join("\n"))}</div>`;
    }
    $("rules-body").innerHTML = html;
    $("rules-rate").textContent = `초당 ${fmt2(st.settings.rate)}토큰, 60초 = ${fmt(st.settings.rate * 60)}토큰`;
    show("rules-modal", true);
  }
  const closeRules = () => show("rules-modal", false);
  $("btn-rules").addEventListener("click", openRules);
  $("rules-close").addEventListener("click", closeRules);
  $("rules-ok").addEventListener("click", closeRules);
  $("rules-modal").addEventListener("click", (ev) => { if (ev.target === $("rules-modal")) closeRules(); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeRules(); });
  $("rules-mode").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-mode]");
    if (!b) return;
    $("rules-mode").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    $("rules-body").className = `rules-body mode-${b.dataset.mode}`;
  });

  $("ledger-legend").innerHTML = R.LEDGER_LEGEND.map(([e, k]) => `<tr><td>${esc(e)}</td><td>${esc(k)}</td></tr>`).join("");

  // --- boot ------------------------------------------------------------------------------------------------------------
  $("api-base").textContent = window.WEB5_API || location.origin;
  const roomParam = (new URLSearchParams(location.search).get("room") || "").trim().toUpperCase();
  if (sess && sess.code && sess.token && (!roomParam || roomParam === sess.code)) enterRoom();
  else initLobby(roomParam);
})();
