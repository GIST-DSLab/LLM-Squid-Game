// Arena: one page for the 4-seat 5.2 v9-talk room. Lobby -> waiting room -> rounds (TALK turns, SOLVE) -> end.
// The backend (web/server/app.py, engine.py) is the contract; this page renders the state it returns and posts the
// screens. A TALK screen composes the reply TEXT in the engine grammar (TO / OFFER / ACCEPT / WITHDRAW / EXIT / DONE)
// and the engine's own parser reads it, so a person's lines are dropped or refused exactly like a model's; the reasons
// come back in state.last and are shown between screens. Polls GET /state every second while in a room; the draining
// counter ticks every 100 ms on server time.
(function () {
  "use strict";

  const API = (window.WEB5_API || "") + "/api";
  const LS_KEY = "web5_arena_session";
  const LS_RULES = "web5_arena_rules_seen";
  const AGENTS = ["agent-6", "agent-11", "agent-17", "agent-23"];
  const R = window.RulesKo;

  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "—" : Math.round(Number(n)).toLocaleString("en-US"));
  const fmt2 = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const kindLabel = (kind, turn) => (kind === "talk" ? `TALK ${turn ?? ""}턴`.trim() : kind === "solve" ? "SOLVE" : kind);

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
  let shownKey = null;            // "talk:1:2": the screen the decision area currently holds
  let watching = false;           // a seat that is out chose to keep watching
  let endRendered = false;
  let autoStart = false;          // quick play: start as soon as the rules window is closed
  let warnSeen = 0;               // the last warning number already flashed
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
    f.start.placeholder = `20U = ${fmt(20 * U)}`;
    f.prize.placeholder = `U = ${fmt(U)}`;
    f.charge.placeholder = `U = ${fmt(U)}`;
    f.rate.placeholder = `U/60 = ${fmt2(U / 60)}`;
    $("create-hint").textContent = `시작 잔액 ${fmt(val("start", 20 * U))} · 지급 한 명당 ${fmt(val("prize", U))} · 부담금 ` +
      `${fmt(val("charge", U))} · 사람은 초당 ${fmt2(rate)}토큰 (60초 = ${fmt(rate * 60)}토큰) · TALK 답 한도 4,096 · SOLVE 한도 16,384 ` +
      `(실험 설정과 같음) · 제한 시간이 지나면 빈 답으로 처리(TALK = DONE, SOLVE = 풀지 못함)`;
  }

  function initLobby(prefill) {
    showView("lobby");
    const fj = $("form-join");
    if (prefill) fj.code.value = prefill.toUpperCase();
    createHint();
    loadModels();
  }

  // model seats: whether the server holds the Ollama key (never its value)
  async function loadModels() {
    const h = $("quick-hint");
    try {
      const m = await api("GET", "/models");
      $("quick-model").textContent = m.model;
      h.textContent = m.available
        ? `서버에 ${m.api_key_env}가 있습니다 · 모델 ${m.model} · 호출 제한 ${fmt(m.timeout)}초 · 모델이 생각하는 동안에도 내 화면의 시계는 돕니다.`
        : `이 서버에는 ${m.api_key_env}가 없어 모델 자리를 만들 수 없습니다. web/tools/serve_local.py로 서버를 띄우세요.`;
      h.classList.toggle("warn-text", !m.available);
      $("btn-quick").disabled = !m.available;
      if (!m.available) $("form-create").fill.value = "bots";
    } catch (e) { h.textContent = `모델 정보를 읽지 못했습니다: ${e.message}`; }
  }

  function enterNew(r) {
    sess = { code: r.code, token: r.token, name: r.name, agent: r.agent };
    saveSess(sess);
    history.replaceState(null, "", `?room=${r.code}`);
    enterRoom();
  }

  $("form-quick").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const settings = { humans: 1, fill: "models", think: f.think.value, schedule: f.schedule.value };
    $("btn-quick").disabled = true;
    try {
      const r = await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "player", settings });
      autoStart = true;
      enterNew(r);
    } catch (e) { flash(`방을 만들지 못했습니다: ${e.message}`); }
    $("btn-quick").disabled = false;
  });

  async function startRoom() {
    try { await api("POST", `/rooms/${sess.code}/start?${tq()}`); poll(); }
    catch (e) { flash(`시작하지 못했습니다: ${e.message}`); }
  }

  $("form-create").addEventListener("input", createHint);
  $("form-create").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const settings = {};
    for (const k of ["upkeep", "start", "prize", "charge", "final_prize", "rounds", "seed", "rate", "talk_turns",
      "talk_timeout_s", "timeout_s", "bot_guess"]) {
      if (f[k].value !== "") settings[k] = Number(f[k].value);
    }
    settings.humans = Number(f.humans.value);
    settings.fill = f.fill.value;
    settings.schedule = f.schedule.value;
    if (settings.fill === "models") settings.think = f.think.value;
    try {
      enterNew(await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "host", settings }));
    } catch (e) { flash(`방을 만들지 못했습니다: ${e.message}`); }
  });

  $("form-join").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const code = f.code.value.trim().toUpperCase();
    if (!code) return;
    try {
      const r = await api("POST", `/rooms/${encodeURIComponent(code)}/join`, { name: f.name.value.trim() });
      enterNew({ ...r, code: r.code || code });
    } catch (e) {
      const why = e.status === 404 ? "그런 방이 없습니다" : e.message === "the session has started" ? "이미 시작한 방입니다"
        : e.message === "every human seat is taken" ? "사람 자리가 모두 찼습니다" : e.message;
      flash(`참가하지 못했습니다: ${why}`);
    }
  });

  // --- room loop ----------------------------------------------------------------------------------------------------
  function enterRoom() {
    endRendered = false; watching = false; shownKey = null; htmlCache.clear(); warnSeen = 0;
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
    if (row.kind === "model") return `${esc(row.name)} <span class="tag model">모델</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    if (i < s.humans) return `<span class="muted">사람 자리 — 아직 아무도 없음</span>`;
    return s.fill === "bots" ? `<span class="muted">봇 (시작할 때 채움)</span>`
      : s.fill === "models" ? `<span class="muted">${esc(s.model)} 모델 (think ${esc(s.think)}, 시작할 때 채움)</span>`
      : `<span class="muted">빈 자리(꺼짐)</span>`;
  }

  function renderWait() {
    showView("wait");
    // the rules open once here, while reading is free: once the session starts, round 1's first TALK clock is running
    if (!rulesSeen(st.code)) { markRulesSeen(st.code); openRules(); }
    $("wait-code").textContent = st.code;
    const link = `${location.origin}${location.pathname}?room=${st.code}`;
    if ($("wait-link").value !== link) $("wait-link").value = link;
    const humans = st.seats.filter((r) => r.kind === "human").length;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatWho(r, i)}</td><td></td></tr>`).join(""));
    const s = st.settings;
    const rest = s.fill === "bots" ? "봇으로 채워집니다" : s.fill === "models" ? `${s.model} 모델(think ${s.think})로 채워집니다` : "빈 자리(꺼진 상태)로 시작합니다";
    $("wait-note").textContent = `사람 ${humans} / ${s.humans}명. 시작할 때 비어 있는 자리는 ${rest}. ` +
      `퍼즐 ${s.schedule === "human" ? "사람용(h2)" : "실험 일정(c2→c4tq2)"} · TALK 최대 ${s.talk_turns}턴 · 유지비 ${fmt(s.upkeep)} · ` +
      `시작 잔액 ${fmt(s.start)} · 사람은 초당 ${fmt2(s.rate)}토큰(60초 = ${fmt(s.rate * 60)}).`;
    show("btn-start", st.is_host);
    if (autoStart && st.is_host && $("rules-modal").classList.contains("hidden")) { autoStart = false; startRoom(); }
    $("wait-host-note").textContent = (autoStart ? "규칙 창을 닫으면 바로 시작합니다. " : st.is_host ? "" : "방장이 시작하기를 기다리는 중… ") +
      "규칙은 지금 읽어 두세요(위 '규칙' 버튼). 시작하면 첫 TALK 화면이 바로 뜨고 그때부터 시간이 차감됩니다.";
  }

  $("btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("wait-link").value); flash("링크를 복사했습니다", "info"); }
    catch { $("wait-link").select(); }
  });
  $("btn-start").addEventListener("click", startRoom);
  $("btn-leave").addEventListener("click", () => {
    if (st && st.status === "running" && !confirm("이 브라우저에서 방 정보를 지웁니다. 자리는 세션에 남고, 결정 화면은 제한 시간이 지나면 빈 답으로 처리됩니다. 나갈까요?")) return;
    leaveRoom("");
  });

  // --- seats, names ---------------------------------------------------------------------------------------------------
  const seatOf = (a) => (st.seats || []).find((r) => r.agent === a);
  function shortName(a) {
    const r = seatOf(a);
    if (!r || r.kind === "empty" || !r.name) return a;
    return r.kind === "human" ? r.name : r.kind === "model" ? r.name.replace(/^.*#/, "모델 #") : r.name;
  }
  const nameOf = (a) => { const n = shortName(a); return n === a ? a : `${n} (${a})`; };
  function seatLabel(row) {
    if (!row) return "";
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "model") return `${esc(row.name)} <span class="tag model">모델</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    if (row.kind === "human") return `${esc(row.name)} <span class="tag">사람</span>`;
    return "";
  }
  const STATUS_TAG = { in: `<span class="tag ok">참여 중</span>`, dead: `<span class="tag bad">꺼짐</span>`, exited: `<span class="tag warn">퇴장</span>` };
  const GONE_KO = { dead: "꺼짐", exited: "퇴장" };

  // --- running ------------------------------------------------------------------------------------------------------
  function renderRun() {
    showView("run");
    const you = st.you;
    const out = you.status !== "in";
    const p = st.pending;
    show("dead-card", out && !watching);
    if (out) {
      const exited = you.status === "exited";
      $("dead-icon").innerHTML = exited ? "&#128682;" : "&#9760;";
      $("dead-title").textContent = exited ? "퇴장했습니다 — 잔액은 그대로" : "잔액 0 — 꺼졌습니다";
      $("dead-sub").textContent = exited
        ? `EXIT로 라운드에서 빠졌습니다. 잔액 ${fmt(you.balance)}토큰은 그대로 남고, 끝 보상 대상에서는 빠집니다. 세션은 다른 자리로 계속됩니다.`
        : "이 자리는 더 이상 결정 화면을 받지 않습니다. 세션은 다른 자리로 계속됩니다.";
    }
    if (p && !out) {
      show("decision", true);
      show("between", false);
      const key = `${p.kind}:${p.round}:${p.turn ?? ""}`;  // the clock runs from the moment the screen is ready
      if (key !== shownKey) { shownKey = key; buildOpen(p); }
    } else {
      shownKey = null;
      show("decision", false);
      show("open-screen", false);
      show("between", !out || watching);
      renderBetween();
    }
    renderSettlement();
    renderBalances();
    renderWarnings();
    renderLedger("ledger", st.ledger);
    tick();
  }

  // model call failures and format errors: flashed once, the last few kept on screen
  function renderWarnings() {
    const ws = st.warnings || [];
    show("warn-box", ws.length > 0);
    if (!ws.length) return;
    setHTML("warn-box", `<b>모델 자리 알림</b> <span class="muted small">(실패는 빈 답으로 처리됩니다: TALK = DONE, SOLVE = 풀지 못함)</span>` +
      `<ul>${ws.slice(-5).map((w) => `<li>${esc(w.text)}</li>`).join("")}</ul>`);
    const last = ws[ws.length - 1];
    if (last.n > warnSeen) { warnSeen = last.n; if (/호출 실패/.test(last.text)) flash(last.text); }
  }

  $("btn-watch").addEventListener("click", () => { watching = true; renderRun(); });

  function thinkingTag(r) {
    const secs = Math.max(0, now() - (r.thinking_since || now()));
    return `<span class="call-line think-line"><span class="pulse-dot"></span>생각 중… ${kindLabel(r.thinking_kind, r.thinking_turn)} <span class="mono think-secs" data-since="${r.thinking_since}">${secs.toFixed(0)}초</span></span>`;
  }
  function callLine(r) {
    const c = r.last_call;
    if (!c) return "";
    const what = `R${c.round} ${kindLabel(c.kind, c.turn)}`;
    if (c.error) return `<span class="call-line err">${what}: 호출 실패 → 빈 답</span>`;
    const bad = c.overdrawn ? " · <b>잔액 소진 → 꺼짐</b>" : c.cut ? " · <b>한도 도달 → 무효</b>"
      : c.format_error ? " · <b>쓸 줄 없음/형식 오류</b>" : "";
    return `<span class="call-line${bad ? " err" : ""}">${what}: ${fmt(c.out_tokens)}토큰 · ${Number(c.seconds).toFixed(1)}초${bad}</span>`;
  }

  function renderBalances() {
    setHTML("bal-body", st.seats.map((r) => {
      let status = STATUS_TAG[r.status] || "";
      if (r.status !== "in") status = status.replace("</span>", `${r.out_round ? " R" + r.out_round : r.kind === "empty" ? " (시작 전)" : ""}</span>`);
      if (r.status === "in") {
        status += r.waiting ? ' <span class="tag warn">결정 중</span>' : "";
        status += r.thinking ? thinkingTag(r) : "";
        if (r.kind === "model" && !r.thinking) status += callLine(r);
      }
      return `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatLabel(r)}${r.is_you ? " <span class='tag ok'>나</span>" : ""}</td>` +
        `<td class="num mono">${fmt(r.balance)}</td><td>${status}</td><td class="num">${r.record ?? 0}</td></tr>`;
    }).join(""));
  }

  function renderLedger(id, lines) {
    if (!lines || !lines.length) { setHTML(id, `<p class="muted small">아직 끝난 라운드가 없습니다.</p>`); return; }
    setHTML(id, lines.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join(""));
  }

  // what the engine is doing now, and who it waits for
  function liveLine() {
    const lv = st.live || {};
    const me = st.you.agent;
    const thinking = st.seats.filter((r) => r.thinking).map((r) => `${esc(shortName(r.agent))} 생각 중`);
    const waiting = st.seats.filter((r) => r.waiting && !r.is_you).map((r) => `${esc(shortName(r.agent))} 결정 중`);
    const who = thinking.concat(waiting);
    let line;
    if (lv.stage === "talk") {
      const called = lv.agents || [];
      line = `라운드 ${lv.round} · TALK ${lv.turn}턴 — 호출된 자리: ${called.map((a) => esc(shortName(a))).join(", ") || "없음"}`;
      if (st.you.status === "in" && !called.includes(me)) line += ` <span class="tag">이번 턴은 부르지 않음 (DONE을 썼고 새 소식 없음)</span>`;
    } else if (lv.stage === "solve") line = `라운드 ${lv.round} · SOLVE`;
    else if (lv.stage === "exchange") line = `라운드 ${lv.round} · 수락된 제안 실행 중`;
    else if (lv.stage === "upkeep") line = `라운드 ${lv.round} · 유지비 차감`;
    else if (lv.stage === "settled") line = `라운드 ${lv.round} 정산 끝 — 다음 라운드 준비 중`;
    else line = "준비 중";
    return `<div class="wait-line"><span class="pulse-dot"></span>${line}</div>` +
      (who.length ? `<div class="small muted live-who">기다리는 중: ${who.join(" · ")}</div>` : "");
  }

  function lastHTML(q) {
    if (!q) return "";
    const what = `라운드 ${q.round} ${kindLabel(q.kind, q.turn)}`;
    let cls = "", head;
    if (q.outcome === "overdrawn") { cls = "bad"; head = `${what}: 잔액을 넘겨 0이 됐습니다 — 이 자리는 꺼집니다.`; }
    else if (q.outcome === "timeout") { cls = "warn"; head = `${what}: 제한 시간이 지나 빈 답으로 처리됨 (${q.kind === "talk" ? "DONE, 아무것도 실행 안 됨" : "풀지 못함 → 부담금"})`; }
    else head = `${what} 보냄`;
    if (q.void && q.outcome !== "overdrawn") { cls = "bad"; head += " — 한도에 닿아 답이 무효입니다."; }
    let html = `<div class="result ${cls}"><b>${head}</b> · 차감 <b class="mono">${fmt(q.charged)}</b>토큰 (${Number(q.seconds || 0).toFixed(1)}초)`;
    if (q.text) html += `<pre class="sent-text">${esc(q.text)}</pre>`;
    const e = q.engine;
    if (!e) html += `<div class="small muted">엔진 처리 대기 중 — 이 턴의 다른 답이 다 오면 읽습니다.</div>`;
    else if (q.kind === "talk") html += talkResultHTML(q, e);
    else {
      const ans = e.answer;
      html += `<div class="small">${ans === "PASS" ? "PASS (부담금 없음)" : ans ? `답: <span class="mono">${esc(ans.join(", "))}</span> — 정산에서 판정` : `엔진이 답을 읽지 못함: ${esc(e.format_error || "")} → 풀지 못함`}</div>`;
    }
    return html + `</div>`;
  }

  function talkResultHTML(q, e) {
    const p = e.parsed || {};
    const res = q.result || {};
    const rows = [];
    if (e.truncated) rows.push(`<li class="bad-text">한도에 닿아 이 답의 줄은 하나도 실행되지 않았습니다(DONE으로 처리).</li>`);
    if ((p.to || []).length) rows.push(`<li>메시지 ${p.to.length}개 → ${p.to.map((m) => esc(shortName(m.dst))).join(", ")} (받는 쪽의 다음 TALK 턴에 닿음)</li>`);
    if ((res.offers || []).length) rows.push(`<li>제안 등록: ${res.offers.map((x) => `<b class="mono">${x}</b>`).join(", ")}</li>`);
    if ((res.accepted || []).length) rows.push(`<li>수락함: ${res.accepted.map((x) => `<b class="mono">${x}</b>`).join(", ")} (TALK가 끝나면 실행)</li>`);
    if ((res.withdrawn || []).length) rows.push(`<li>철회함: ${res.withdrawn.join(", ")}</li>`);
    for (const r of res.refused || []) {
      const i = r.indexOf(": ");
      rows.push(`<li class="bad-text">거절: <span class="mono">${esc(r.slice(0, i))}</span> — ${esc(R.whyKo(r.slice(i + 2)))} <span class="muted mono small">(${esc(r.slice(i + 2))})</span></li>`);
    }
    for (const d of p.dropped || []) {
      const x = R.droppedKo(d);
      rows.push(`<li class="bad-text">버려진 줄: <span class="mono">${esc(x.line)}</span> — ${esc(x.ko)} <span class="muted mono small">(${esc(x.why)})</span></li>`);
    }
    if (p.exit) rows.push(`<li><b>EXIT</b> — TALK가 끝나고 교환이 실행되면 퇴장합니다(잔액 유지).</li>`);
    if (p.done) rows.push(`<li>DONE — 새 메시지·제안·수락이 오지 않으면 이번 라운드 TALK에서 더 부르지 않습니다.</li>`);
    if (e.format_error === "no usable TALK line") rows.push(`<li class="muted">쓸 수 있는 줄이 없어 DONE으로 처리됨 (no usable TALK line)</li>`);
    return rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
  }

  function exchangesHTML() {
    const r = st.round;
    const xs = (st.exchanges || []).filter((e) => e.round === r);
    if (!xs.length) return "";
    return `<h4>이번 라운드 내 제안의 결과 (TALK 끝)</h4><ul class="xlist">` + xs.map((e) => {
      const cls = e.status === "done" ? "ok" : e.status === "void" ? "bad" : "";
      return `<li><span class="mono">${e.id}</span> ${esc(R.offerTextKo(e.text))} — <span class="tag ${cls}">${R.STATUS_KO[e.status] || e.status}</span>` +
        `${e.why ? ` <span class="muted">${esc(R.whyKo(e.why))}</span>` : ""}</li>`;
    }).join("") + `</ul>`;
  }

  function renderBetween() {
    let msg = liveLine();
    if (st.you.status !== "in") msg = `<div class="small muted">${st.you.status === "exited" ? "퇴장한" : "꺼진"} 자리에서 지켜보는 중</div>` + msg;
    else msg += `<p class="small muted">결정 화면(TALK 턴·SOLVE)이 오면 바로 여기에 뜨고, 뜬 순간부터 시간이 차감됩니다. 화면과 화면 사이에 잔액과 장부를 읽는 것은 무료입니다. 새 메시지는 다음 TALK 화면에서 보입니다.</p>`;
    setHTML("between-msg", msg);
    setHTML("last-result", lastHTML(st.last));
    setHTML("my-exchanges", exchangesHTML());
  }

  const sgn = (s, n) => (n ? `${s}${fmt(n)}` : `<span class="muted">0</span>`);

  // the last settled round, every agent's line (what the ledger posts, as a table)
  function renderSettlement() {
    const r = (st.rounds || [])[st.rounds.length - 1];
    show("settle-panel", !!r && !st.pending);
    if (!r || st.pending) return;
    $("settle-title").textContent = `라운드 ${r.round} 정산`;
    const rows = AGENTS.filter((a) => r.agents[a]).map((a) => {
      const v = r.agents[a];
      const res = v.solved ? `<span class="tag ok">✓ 풂</span>` : v.passed ? `<span class="tag">PASS</span>`
        : v.solve_call ? `<span class="tag bad">✗ 못 풂</span>` : `<span class="muted">—</span>`;
      const st2 = v.status === "in" ? "" : ` <span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status]}</span>`;
      return `<tr class="${a === st.you.agent ? "you" : ""}"><td>${esc(nameOf(a))}</td><td>${res}${st2}</td>` +
        `<td class="num">${fmt(v.balance_before)}</td><td class="num">${sgn("−", v.generated)}</td><td class="num">${sgn("+", v.returned)}</td>` +
        `<td class="num">${sgn("+", v.paid)}</td><td class="num">${sgn("−", v.charged)}</td><td class="num"><b>${fmt(v.balance_after)}</b></td></tr>`;
    }).join("");
    setHTML("settle-table", `<table><thead><tr><th>자리</th><th>결과</th><th class="num">TALK 시작 잔액</th><th class="num">생성</th><th class="num">돌려받음</th>` +
      `<th class="num">지급</th><th class="num">부담금</th><th class="num">끝 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">TALK 시작 잔액은 유지비(${fmt(st.settings.upkeep)})를 뺀 뒤입니다. 끝 잔액에는 교환으로 오간 토큰도 반영됩니다(남의 교환은 보이지 않음).</p>`);
  }

  // --- decision screens ---------------------------------------------------------------------------------------------
  function balancesLine(v) {
    return Object.entries(v.balances || {}).map(([a, b]) => {
      const g = (v.gone || {})[a];
      return `<span class="bal-chip${a === v.you ? " me" : ""}${g ? " gone" : ""}">${a === v.you ? "<b>나</b>" : esc(nameOf(a))} <span class="mono">${fmt(b)}</span>${g ? ` (${GONE_KO[g]})` : ""}</span>`;
    }).join("");
  }
  function rawHTML(p) {
    return `<details class="raw"><summary>원문 프롬프트 (모델이 받는 영어 그대로 · 한국어 풀이)</summary>
      <div class="raw-grid"><pre>${esc(p.text)}</pre><pre>${esc(R.promptKo(p))}</pre></div></details>`;
  }
  function defaultText(kind) {
    return kind === "talk" ? "빈 답 = DONE, 아무것도 실행 안 됨" : "빈 답 = 풀지 못함 → 부담금";
  }

  function buildOpen(p) {
    show("open-screen", true);
    $("m-rate").textContent = fmt2(p.rate);
    $("m-cap").textContent = fmt(p.cap);
    const f = $("form-decision");
    f.dataset.kind = p.kind;
    if (p.kind === "talk") buildTalk(f, p); else buildSolve(f, p);
  }

  function instrHTML(p) {
    const t = p.kind === "talk"
      ? [`TALK ${p.turn}턴 / 최대 ${p.view.turns}턴 — 말하고, 제안하고, 수락하세요`, [
        "<b>메시지</b>: 한 자리에게만 갑니다. 받는 쪽은 다음 TALK 턴에 봅니다. 시스템은 내용을 실행하지 않습니다",
        "<b>제안</b>: 상대가 줄 것과 내가 줄 것(토큰 n · 예시 · 없음). 상대가 다음 턴에 수락하면 TALK 끝에 실행됩니다",
        "<b>수락 / 철회</b>: 오른쪽 제안 목록의 버튼. <b>EXIT</b>: 잔액을 들고 라운드에서 빠짐",
        "<b>이번 턴 보내기</b> 또는 <b>보내고 DONE</b>(새 소식이 없으면 이번 라운드 TALK에서 더 부르지 않음)"]]
      : ["숨은 규칙을 찾아 새 신호의 행동을 고르세요 — 또는 PASS", ["<b>예시</b>를 보고 규칙(if / elif / else)을 추리합니다 (교환으로 받은 예시는 표시됨)",
        "<b>규칙 메모판</b>에서 버튼으로 규칙을 짜 보면 예시마다 ✓ / ✗가 바로 표시됩니다",
        "<b>답 제출</b>: 모두 맞으면 이 라운드에 쓴 토큰을 모두 돌려받고 지급을 나눔 · 틀리면 부담금",
        "<b>PASS</b>: 부담금 없음, 쓴 토큰은 그대로 빠짐"]];
    return `<div class="instr"><div class="instr-title">${t[0]}</div><ol class="instr-steps">${t[1].map((x) => `<li>${x}</li>`).join("")}</ol>
      <div class="instr-clock">⏱ 이 화면이 떠 있는 동안 초당 <b>${fmt2(p.rate)}</b>토큰이 빠집니다. 고민하는 시간이 곧 비용입니다.</div></div>`;
  }

  // --- TALK ---------------------------------------------------------------------------------------------------------
  function legSelHTML(side, label, whose) {
    return `<div class="leg" data-side="${side}"><div class="leg-label">${label}</div>
      <div class="seg leg-seg" data-leg="${side}">
        <button type="button" data-val="tokens">토큰</button><button type="button" data-val="example">${whose} 예시</button><button type="button" data-val="nothing" class="on">없음</button>
      </div><input type="number" min="1" step="1" class="leg-n" placeholder="토큰 수" disabled></div>`;
  }

  function threadHTML(v, b) {
    const msgs = (v.threads || {})[b] || [];
    const g = (v.gone || {})[b];
    const canWrite = (v.others || []).includes(b);
    const body = msgs.length ? msgs.map((m) => `<div class="msg ${m.from_me ? "mine" : "theirs"}"><div class="msg-meta">R${m.round} · ${m.turn}턴 · ${m.from_me ? "나" : esc(shortName(b))}</div>` +
      `<div class="msg-text">${esc(m.text)}</div></div>`).join("") : `<div class="muted small">아직 메시지 없음</div>`;
    return `<div class="thread${canWrite ? "" : " off"}" data-agent="${b}"><div class="thread-head"><b>${esc(nameOf(b))}</b>` +
      `${g ? ` <span class="tag ${g === "dead" ? "bad" : "warn"}">${GONE_KO[g]}</span>` : ""}` +
      `${canWrite ? `<button type="button" class="ghost tiny write-to" data-agent="${b}">쓰기</button>` : ""}</div>` +
      `<div class="thread-body">${body}</div></div>`;
  }

  function offerItemHTML(o, me) {
    const dir = o.mine ? `나 → ${esc(shortName(o.dst))}` : `${esc(shortName(o.src))} → 나`;
    const state = o.status === "open" ? (o.can_accept ? "열림 — 수락할 수 있음" : "열림 — 상대의 수락을 기다림")
      : o.status === "accepted" ? `${o.accepted_turn}턴에 수락됨 — TALK가 끝나면 실행` : (R.STATUS_KO[o.status] || o.status);
    const btn = o.can_accept ? `<button type="button" class="primary tiny offer-act" data-act="ACCEPT" data-id="${o.id}">수락</button>`
      : o.can_withdraw ? `<button type="button" class="ghost tiny offer-act" data-act="WITHDRAW" data-id="${o.id}">철회</button>` : "";
    return `<li class="offer ${o.status}"><div class="offer-top"><span class="mono offer-id">${o.id}</span> <span>${dir}</span> <span class="muted small">(${o.turn}턴)</span>${btn}</div>` +
      `<div class="offer-legs">${esc(R.offerKo(o, me))}</div><div class="small muted">${state}</div>` +
      `<div class="offer-en mono">${esc(o.text)}</div></li>`;
  }

  function buildTalk(f, p) {
    const v = p.view, me = v.you;
    const others = v.others || [];
    const opt = (list) => list.map((a) => `<option value="${a}">${esc(nameOf(a))}</option>`).join("");
    const threads = AGENTS.filter((b) => b !== me && (others.includes(b) || ((v.threads || {})[b] || []).length)).map((b) => threadHTML(v, b)).join("");
    const offers = (v.offers || []).length ? `<ul class="offers">${v.offers.map((o) => offerItemHTML(o, me)).join("")}</ul>` : `<p class="muted small">이번 라운드 제안 없음</p>`;
    const ledger = (v.ledger || []).length ? `<details class="legend"><summary>장부 (지난 라운드 ${v.ledger.length}개)</summary>${v.ledger.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join("")}</details>` : "";
    f.innerHTML = `<h2>라운드 ${p.round} · TALK ${p.turn}턴</h2>${instrHTML(p)}
      <div class="ctx">
        <div class="bal-line">${balancesLine(v)}</div>
        <div class="terms-ko small">이번 라운드 지급 <b class="mono">${fmt(v.pay_total)}</b>토큰(푼 쪽이 나눔, 푼 쪽은 이 라운드에 쓴 토큰도 돌려받음) ·
          풀지 못한 SOLVE 답의 부담금 <b class="mono">${fmt(v.charge)}</b> (PASS는 없음) · 유지비 <b class="mono">${fmt(v.upkeep)}</b>(이미 빠짐)</div>
        <h4>이번 라운드 과제의 크기 (예시와 새 신호는 SOLVE에서 보임 — 내 예시도)</h4>
        <div class="shape">${esc(v.shape)}</div>
        <p class="small">예시: 모두에게 공개 ${v.n_public}개 · 참여 중인 ${v.n_in}명이 1개씩(내 것 포함) · 새 신호 ${v.n_queries}개</p>
        ${ledger}
      </div>
      <div class="talk-grid">
        <section><h4>메시지 (1:1, 오래된 것부터)</h4><div class="threads">${threads || '<p class="muted small">대화할 상대가 없습니다.</p>'}</div></section>
        <section><h4>이번 라운드 제안 (두 자리만 봄)</h4>${offers}</section>
      </div>
      <div class="composer">
        <h4>이번 턴 답 만들기</h4>
        ${others.length ? `<div class="comp-block">
          <div class="comp-label">메시지</div>
          <div class="row"><select id="c-to">${opt(others)}</select></div>
          <textarea id="c-msg" rows="3" maxlength="4000" placeholder="이 자리에게만 갑니다. 여러 줄 가능 (줄 맨 앞의 TO / OFFER / ACCEPT / EXIT / DONE은 명령으로 읽힙니다)"></textarea>
          <div class="row"><button type="button" class="ghost" id="c-add-msg">메시지 추가</button></div>
        </div>
        <div class="comp-block">
          <div class="comp-label">제안</div>
          <div class="row"><span class="small muted">상대</span><select id="c-offer-to">${opt(others)}</select></div>
          <div class="legs">${legSelHTML("you", "상대가 나에게 줌 (YOU GIVE)", "상대의")}${legSelHTML("i", "내가 상대에게 줌 (I GIVE)", "내")}</div>
          <div class="row"><button type="button" class="ghost" id="c-add-offer">제안 추가</button><span class="small muted" id="c-offer-hint"></span></div>
        </div>` : `<p class="muted small">참여 중인 다른 자리가 없어 메시지와 제안을 보낼 곳이 없습니다.</p>`}
        <details class="comp-raw"><summary>줄 직접 쓰기 (엔진 문법 그대로 덧붙임)</summary>
          <textarea id="c-raw" rows="3" maxlength="4000" placeholder="예: OFFER agent-11: YOU GIVE 200 TOKENS; I GIVE MY EXAMPLE"></textarea></details>
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div>
          <ul id="draft-list" class="draft-list"></ul><pre id="draft-text" class="draft-text"></pre></div>
        <div class="exit-box" id="exit-box">
          <button type="button" class="ghost danger" id="c-exit">EXIT (퇴장)…</button>
          <div id="exit-confirm" class="exit-confirm hidden">
            <b>정말 퇴장할까요?</b> 이 턴의 답에 EXIT 줄이 들어갑니다. TALK가 끝나고 교환이 실행되면 라운드에서 빠지고, 잔액(지금 ${fmt(v.balances[me])})은
            그대로 가지며, 이후 라운드에 참여하지 않고 끝 보상 대상에서도 빠집니다. 되돌릴 수 없습니다.
            <div class="row"><button type="button" class="primary danger" id="c-exit-yes">EXIT 넣기</button><button type="button" class="ghost" id="c-exit-no">취소</button></div>
          </div>
        </div>
        <div class="row submit-row">
          <button type="button" class="primary big" id="btn-send">이번 턴 보내기</button>
          <button type="button" class="ghost big" id="btn-send-done">보내고 DONE</button>
          <span class="form-err" id="form-err"></span>
        </div>
        <p class="small muted">아무 줄도 없이 보내면 엔진은 DONE으로 읽습니다. 제한 시간이 지나면 빈 답(= DONE)으로 처리됩니다.</p>
      </div>${rawHTML(p)}`;
    wireTalk(f, p);
  }

  function wireTalk(f, p) {
    const draft = [];  // {line, label}
    const q = (sel) => f.querySelector(sel);
    function legOf(side) {
      const box = q(`.leg[data-side="${side}"]`);
      const on = box.querySelector(".leg-seg button.on").dataset.val;
      const n = box.querySelector(".leg-n").value;
      return { kind: on, n };
    }
    function legText(side, leg) {
      if (leg.kind === "tokens") return `${Number(leg.n)} TOKENS`;
      if (leg.kind === "example") return side === "you" ? "YOUR EXAMPLE" : "MY EXAMPLE";
      return "NOTHING";
    }
    function text(done) {
      const raw = (q("#c-raw") && q("#c-raw").value.trim()) || "";
      const lines = draft.map((d) => d.line);
      if (raw) lines.push(raw);
      if (done) lines.push("DONE");
      return lines.join("\n");
    }
    function renderDraft() {
      q("#draft-list").innerHTML = draft.length ? draft.map((d, i) => `<li><span>${d.label}</span><button type="button" class="ghost tiny" data-rm="${i}" aria-label="빼기">×</button></li>`).join("")
        : `<li class="muted small">아직 없음 — 메시지·제안·수락을 추가하세요</li>`;
      q("#draft-text").textContent = text(false) || "(빈 답 — 보내면 DONE으로 읽힘)";
      f.querySelectorAll(".offer-act").forEach((b) => {
        const has = draft.some((d) => d.line === `${b.dataset.act} ${b.dataset.id}`);
        b.classList.toggle("on", has);
        b.textContent = has ? `✓ ${b.dataset.act === "ACCEPT" ? "수락" : "철회"} 넣음` : (b.dataset.act === "ACCEPT" ? "수락" : "철회");
      });
      q("#c-exit").textContent = draft.some((d) => d.line === "EXIT") ? "✓ EXIT 넣음" : "EXIT (퇴장)…";
    }
    function err(msg) { q("#form-err").textContent = msg || ""; }
    f.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.dataset.rm !== undefined) { draft.splice(Number(b.dataset.rm), 1); renderDraft(); return; }
      if (b.classList.contains("write-to")) {
        q("#c-to").value = b.dataset.agent; q("#c-offer-to").value = b.dataset.agent; q("#c-msg").focus(); return;
      }
      if (b.classList.contains("offer-act")) {
        const line = `${b.dataset.act} ${b.dataset.id}`;
        const i = draft.findIndex((d) => d.line === line);
        if (i >= 0) draft.splice(i, 1);
        else draft.push({ line, label: `${b.dataset.act === "ACCEPT" ? "수락" : "철회"} <span class="mono">${b.dataset.id}</span>` });
        renderDraft(); return;
      }
      const seg = b.closest(".leg-seg");
      if (seg) {
        seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
        const n = seg.parentElement.querySelector(".leg-n");
        n.disabled = b.dataset.val !== "tokens";
        if (!n.disabled) n.focus(); else n.value = "";
        return;
      }
    });
    if (q("#c-add-msg")) {
      q("#c-add-msg").addEventListener("click", () => {
        const to = q("#c-to").value, body = q("#c-msg").value.replace(/\s+$/, "").replace(/^\s*\n/, "");
        if (!body.trim()) return err("메시지 내용을 쓰세요.");
        draft.push({ line: `TO ${to}: ${body}`, label: `메시지 → ${esc(shortName(to))}: “${esc(body.length > 60 ? body.slice(0, 60) + "…" : body)}”` });
        q("#c-msg").value = ""; err(""); renderDraft();
      });
      q("#c-add-offer").addEventListener("click", () => {
        const to = q("#c-offer-to").value, you = legOf("you"), mine = legOf("i");
        for (const leg of [you, mine]) {
          if (leg.kind === "tokens" && !(Number.isInteger(Number(leg.n)) && Number(leg.n) >= 1)) return err("토큰 수는 1 이상 정수로 적으세요.");
        }
        if (you.kind === "nothing" && mine.kind === "nothing") return err("양쪽 다 '없음'인 제안은 엔진이 버립니다. 한쪽은 고르세요.");
        const line = `OFFER ${to}: YOU GIVE ${legText("you", you)}; I GIVE ${legText("i", mine)}`;
        const o = { src: st.you.agent, dst: to, you_give: you.kind === "tokens" ? Number(you.n) : you.kind === "example" ? "EXAMPLE" : null,
          i_give: mine.kind === "tokens" ? Number(mine.n) : mine.kind === "example" ? "EXAMPLE" : null };
        draft.push({ line, label: `제안 → ${esc(shortName(to))}: ${esc(R.offerKo(o, st.you.agent))}` });
        err(""); renderDraft();
      });
    }
    q("#c-exit").addEventListener("click", () => {
      const i = draft.findIndex((d) => d.line === "EXIT");
      if (i >= 0) { draft.splice(i, 1); renderDraft(); return; }
      show(q("#exit-confirm"), true);
    });
    q("#c-exit-no").addEventListener("click", () => show(q("#exit-confirm"), false));
    q("#c-exit-yes").addEventListener("click", () => {
      draft.push({ line: "EXIT", label: `<b class="bad-text">EXIT — 이번 라운드 TALK가 끝나면 퇴장</b>` });
      show(q("#exit-confirm"), false); renderDraft();
    });
    if (q("#c-raw")) q("#c-raw").addEventListener("input", renderDraft);
    async function send(done) {
      q("#btn-send").disabled = q("#btn-send-done").disabled = true;
      const t = text(done);
      try {
        const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: "talk", round: p.round, turn: p.turn, text: t });
        const msg = `차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
          (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : r.void ? " — 한도에 닿아 답이 무효" : "");
        flash(`라운드 ${r.round} TALK ${r.turn}턴 보냄: ${msg}`, r.void || r.outcome === "overdrawn" ? "" : "info");
      } catch (e) {
        flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `보내지 못했습니다: ${e.message}`);
      }
      shownKey = null;
      poll();
    }
    q("#btn-send").addEventListener("click", () => send(false));
    q("#btn-send-done").addEventListener("click", () => send(true));
    renderDraft();
  }

  // --- SOLVE --------------------------------------------------------------------------------------------------------
  function segHTML(field, options, html) {
    return `<div class="seg${html ? " seg-rich" : ""}" data-field="${field}">` +
      options.map(([val, label]) => `<button type="button" data-val="${esc(val)}">${html ? html(val) : esc(label)}</button>`).join("") + `</div>`;
  }

  function buildSolve(f, p) {
    const v = p.view;
    const ex = (v.examples || []).map(([w, c], i) => {
      const cls = w === "shown to all" ? "pub" : w === "yours" ? "mine" : "shared";
      const e = SIG.parseExample(c);
      const pic = e ? `<span class="ex-pic">${SIG.glyphsHTML(e, 26)}</span><span class="ex-arrow">→</span>${SIG.actionHTML(e.action)}` : `<span>${esc(c)}</span>`;
      return `<li class="ex-row" data-i="${i}"><span class="tag ${cls}">${esc(R.exampleWhoKo(w))}</span>${pic}
        <span class="ex-en mono">${esc(c)}</span><span class="ex-verdict" title="메모판 규칙으로 판정">·</span></li>`;
    }).join("");
    const notes = (v.notes || []).map((n) => `<div class="note">${esc(R.noteKo(n))}<div class="note-en mono">${esc(n)}</div></div>`).join("");
    const sigs = (v.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (v.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    const qs = (v.queries || []).map((x, i) => `<div class="query"><div class="qlabel">새 신호 ${i + 1}
        ${sigs[i] ? `<span class="q-mini">${SIG.glyphsHTML(sigs[i], 22)}</span>` : ""}의 행동</div>
        ${segHTML("q" + i, (v.actions || []).map((a) => [a, a]), (a) => SIG.actionHTML(a))}</div>`).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · SOLVE</h2>${instrHTML(p)}
      <p class="small muted">한도: 최대 ${fmt(p.cap)}토큰${p.cap >= (v.balance ?? p.balance) ? " (내 잔액)" : ""} · 잔액 ${fmt(v.balance ?? p.balance)}토큰 ·
        모든 새 신호가 맞아야 이 라운드가 풀립니다. 규칙 문법은 '규칙' 버튼.</p>
      ${stages}
      <h4>규칙의 모양 (빈칸을 채움)</h4><div class="shape">${esc(v.shape)}</div>
      <h4>예시 <span class="muted small">(그림 = 색 · 모양 · 개수가 숫자)</span></h4><ul class="examples sig-examples">${ex}</ul>${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="scratchpad" id="scratchpad"></div>
      <h4>답: 새 신호마다 행동 하나</h4>${qs}
      <div class="row submit-row"><button type="submit" class="primary big" id="btn-submit" disabled>답 제출</button>
        <button type="button" class="ghost big" id="btn-pass">PASS</button>
        <span class="form-err" id="form-err"></span></div>${rawHTML(p)}`;
    const choice = {};
    const n = (v.queries || []).length;
    function validate() {
      const missing = [...Array(n).keys()].find((i) => !choice["q" + i]);
      $("btn-submit").disabled = missing !== undefined;
      $("form-err").textContent = missing !== undefined ? `새 신호 ${missing + 1}의 행동을 고르세요 (또는 PASS).` : "";
    }
    f.querySelectorAll(".seg[data-field]").forEach((seg) => seg.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-val]");
      if (!b) return;
      seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      choice[seg.dataset.field] = b.dataset.val;
      validate();
    }));
    async function send(body) {
      $("btn-submit").disabled = $("btn-pass").disabled = true;
      try {
        const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: "solve", round: p.round, ...body });
        flash(`라운드 ${r.round} SOLVE ${body.pass ? "PASS" : "제출"}: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
          (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void ? "" : "info");
      } catch (e) {
        flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `제출하지 못했습니다: ${e.message}`);
      }
      shownKey = null;
      poll();
    }
    f.onsubmit = (ev) => {
      ev.preventDefault();
      const acts = [...Array(n).keys()].map((i) => choice["q" + i]);
      if (acts.some((a) => !a)) return validate();
      send({ actions: acts });
    };
    $("btn-pass").addEventListener("click", () => send({ pass: true }));
    validate();
    const exs = (v.examples || []).map(([, c], i) => { const e = SIG.parseExample(c); return e && { ...e, el: f.querySelector(`.ex-row[data-i="${i}"]`) }; });
    if (exs.every(Boolean) && sigs.every(Boolean)) {
      SIG.mountScratchpad($("scratchpad"), v.shape, exs, sigs, (i, act) => {
        const b = f.querySelector(`.seg[data-field="q${i}"] button[data-val="${act}"]`);
        if (b) { b.click(); b.scrollIntoView({ block: "center", behavior: "smooth" }); }
      });
    }
  }

  // --- the clock ------------------------------------------------------------------------------------------------------
  function setDanger(d, pulse) {
    const root = $("view-run");
    root.classList.toggle("play-danger", d > 0);
    root.classList.toggle("last-life", !!pulse && d > 0);
    root.style.setProperty("--danger", d.toFixed(3));
  }
  function fuelColor(frac) {
    const hue = frac > 0.5 ? 45 + (frac - 0.5) / 0.5 * 120 : 45 * Math.max(0, (frac - 0.15) / 0.35);
    return `hsl(${hue.toFixed(0)} 78% 52%)`;
  }

  function tick() {
    document.querySelectorAll(".think-secs[data-since]").forEach((el) => {
      el.textContent = `${Math.max(0, now() - Number(el.dataset.since)).toFixed(0)}초`;
    });
    if (!st || st.status !== "running") return setDanger(0);
    const p = st.pending;
    if (!p || st.you.status !== "in") return setDanger(0);
    const t = now();
    const left = p.deadline_at - t;
    const secs = Math.max(0, t - p.opened_at);
    const cost = Math.round(secs * p.rate);
    const remaining = p.balance - cost;
    const c = $("m-remaining");
    c.textContent = fmt(Math.max(0, remaining));
    c.classList.toggle("low", remaining < st.settings.upkeep);
    $("m-cost").textContent = fmt(cost);
    $("m-secs").textContent = secs.toFixed(1);
    const md = $("m-deadline");
    md.innerHTML = remaining <= 0 ? "<b>잔액 0 — 화면이 잔액을 넘었습니다.</b>"
      : cost >= p.cap ? "<b>한도에 닿았습니다 — 이 답은 무효가 됩니다.</b>"
      : `제한 시간 <b>${mmss(left)}</b> 남음 — 넘기면 ${defaultText(p.kind)}, 그 시간만큼 차감됩니다.`;
    md.classList.toggle("urgent", left < 30 || remaining <= 0 || cost >= p.cap);
    const frac = Math.max(0, Math.min(1, remaining / Math.max(1, p.balance)));
    const bar = $("fuel-bar");
    bar.style.width = `${(frac * 100).toFixed(2)}%`;
    bar.style.background = fuelColor(frac);
    bar.classList.toggle("critical", frac < 0.2 || remaining < st.settings.upkeep);
    $("fuel-pct").textContent = `${(frac * 100).toFixed(0)}%`;
    $("fuel-pct").style.color = fuelColor(frac);
    const span = Math.max(1, p.deadline_at - p.created_at);
    $("tbar").style.width = `${(Math.max(0, Math.min(1, left / span)) * 100).toFixed(2)}%`;
    $("tbar").classList.toggle("urgent", left < 30);
    let d = Math.max(0, (1 - frac - 0.25) / 0.75);
    if (remaining < st.settings.upkeep) d = Math.max(d, 0.55 + 0.45 * (1 - remaining / st.settings.upkeep));
    if (left < 30) d = Math.max(d, 0.3 + 0.3 * (1 - left / 30));
    setDanger(Math.min(1, d), frac < 0.15 || remaining < st.settings.upkeep / 2 || left < 10);
  }

  // --- end ---------------------------------------------------------------------------------------------------------------
  function renderEnd() {
    showView("end");
    if (endRendered) return;
    show("flash", false);
    endRendered = true;
    const res = st.result || {};
    const fin = res.final || {};
    const agents = res.agents || {};
    const won = fin.winner || [];
    $("end-final").innerHTML = `<h3 class="panel-title h-shape s-circle">끝 보상 (${fmt(st.settings.final_prize)}토큰)</h3>` +
      (won.length ? `<p class="final-line">${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 아직 참여 중인 자리 가운데 가장 많은 라운드(${agents[won[0]] ? agents[won[0]].record : "?"})를 풀어 ` +
        `<b class="mono">${fmt(fin.prize_each)}</b>토큰${won.length > 1 ? "씩(동점, 나눔)" : ""}을 받습니다. <span class="muted small">(엔진은 결과에 기록만 하고 잔액에 더하지 않습니다)</span></p>`
        : `<p class="muted">끝까지 참여 중인 자리가 없어 끝 보상을 받는 자리가 없습니다.</p>`) +
      `<p class="small muted">진행한 라운드 ${res.rounds_played ?? "—"}개${st.run_dir ? ` · 이 게임의 기록(run dir): <span class="mono">${esc(st.run_dir)}</span> — 모니터(tools/monitor/serve.py)에서 열 수 있습니다` : ""}</p>`;
    const rows = AGENTS.map((a) => {
      const v = agents[a] || {}, seat = seatOf(a) || {};
      const status = v.status === "in" ? `<span class="tag ok">끝까지 참여</span>` : `<span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status] || v.status}${v.out_round ? " R" + v.out_round : ""}</span>`;
      const kind = { human: "사람", model: "모델", bot: "봇", empty: "빈 자리" }[seat.kind] || "";
      return `<tr class="${seat.is_you ? "you" : ""}"><td><b class="mono">${a}</b><br><span class="small">${seat.kind === "empty" ? "" : esc(seat.name || "")} <span class="tag">${kind}</span>${seat.is_you ? " <span class='tag ok'>나</span>" : ""}</span></td>` +
        `<td>${status}${won.includes(a) ? ' <span class="tag ok">끝 보상</span>' : ""}</td><td class="num">${v.record ?? 0}</td><td class="num">${fmt(v.spent)}</td><td class="num">${fmt(v.returned)}</td>` +
        `<td class="num">${fmt(v.paid)}</td><td class="num">${fmt(v.charged)}</td><td class="num">${fmt(v.upkeep)}</td><td class="num"><b class="mono">${fmt(v.final)}</b></td></tr>`;
    }).join("");
    $("end-table").innerHTML = `<table><thead><tr><th>자리</th><th>끝 상태</th><th class="num">푼 라운드</th><th class="num">생성(시간 비용)</th><th class="num">돌려받음</th>` +
      `<th class="num">지급</th><th class="num">부담금</th><th class="num">유지비</th><th class="num">최종 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">생성 = 모델은 실제 생성 토큰(생각 포함), 봇은 정해진 비용, 사람은 결정 화면이 떠 있던 시간 × 초당 토큰. 최종 잔액에는 교환으로 오간 토큰도 반영됩니다.</p>`;
    $("end-svg").innerHTML = flowSVG(agents);
    renderLedger("end-ledger", st.ledger);
  }

  function flowSVG(agents) {
    const rounds = st.rounds || [];
    const n = Math.max(rounds.length, 1);
    const left = 150, lane = 70, colw = Math.max(96, (940 - 150 - 16) / n);
    const W = left + n * colw + 16, H = 40 + lane * 4 + 34;
    const start = st.settings.start;
    const top = Math.max(start, 1, ...rounds.flatMap((r) => Object.values(r.agents).map((x) => x.balance_after || 0)));
    const laneY = (a) => 40 + AGENTS.indexOf(a) * lane;
    const T = (x, y, txt, style, extra) => `<text x="${x.toFixed(0)}" y="${y.toFixed(0)}" style="${style}" ${extra || ""}>${esc(txt)}</text>`;
    const s = [`<svg viewBox="0 0 ${W} ${H}" width="${W}" style="width:100%;max-width:${W}px;min-width:${Math.min(W, 1400)}px" role="img" aria-label="라운드 흐름" xmlns="http://www.w3.org/2000/svg">`];
    rounds.forEach((r, i) => s.push(T(left + i * colw + colw / 2, 22, `R${r.round}`, "font-size:12px;font-weight:700;fill:var(--text)", 'text-anchor="middle"')));
    AGENTS.forEach((a) => {
      const y = laneY(a), row = seatOf(a) || {};
      const sub = row.kind === "empty" ? "빈 자리" : `${row.name || ""}${{ bot: " · 봇", model: " · 모델", human: " · 사람" }[row.kind] || ""}`;
      s.push(T(10, y + 22, a, "font-size:12px;font-weight:700;fill:var(--text)"));
      s.push(T(10, y + 38, sub.slice(0, 22), "font-size:10.5px;fill:var(--text-dim)"));
      s.push(`<line x1="${left}" x2="${W - 8}" y1="${y + lane - 6}" y2="${y + lane - 6}" style="stroke:var(--border)"/>`);
      const out = (agents[a] || {}).out_round;
      rounds.forEach((r, i) => {
        const x = left + i * colw, v = r.agents[a];
        if (!v) { s.push(T(x + colw / 2, y + 32, "—", "font-size:11px;fill:var(--text-dim)", 'text-anchor="middle"')); return; }
        const gone = v.status !== "in";
        const bw = (colw - 30) * Math.max(0, v.balance_after || 0) / top;
        const col = v.status === "dead" ? "var(--danger-color)" : v.solved ? "var(--teal-bright)" : v.status === "exited" ? "var(--warn)" : "var(--text-dim)";
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${colw - 30}" height="12" rx="6" style="fill:var(--panel-alt)"/>`);
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${bw.toFixed(1)}" height="12" rx="6" style="fill:${col}"/>`);
        const mark = v.solved ? "✓" : v.passed ? "PASS" : v.solve_call ? "✗" : "–";
        s.push(T(x + 10, y + 35, `${mark} · ${fmt(v.balance_after)}`, `font-size:11px;fill:${v.solved ? "var(--teal-bright)" : "var(--text)"}`));
        const bits = [];
        if (v.returned) bits.push(`↺${fmt(v.returned)}`);
        if (v.paid) bits.push(`+${fmt(v.paid)}`);
        if (v.charged) bits.push(`−${fmt(v.charged)}`);
        if (v.status === "exited") bits.push("🚪 퇴장");
        if (v.status === "dead") bits.push(`✕ 꺼짐${v.overdrawn ? "(초과)" : ""}`);
        s.push(T(x + 10, y + 51, bits.join(" "), `font-size:10.5px;fill:${gone ? "var(--danger-color)" : "var(--text-dim)"}`));
        void out;
      });
    });
    s.push(T(left, H - 10, `막대 = 라운드 끝 잔액 (눈금 최대 ${fmt(top)}, 시작 ${fmt(start)}) · ✓ 풂 · ✗ 못 풂 · PASS · ↺ 돌려받음 · +지급 · −부담금`, "font-size:10.5px;fill:var(--text-dim)"));
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
    } else {
      html = `<div class="en">${esc(en.join("\n"))}</div><div class="ko">${esc(ko.join("\n"))}</div>`;
    }
    $("rules-body").innerHTML = html;
    $("rules-rate").textContent = `초당 ${fmt2(st.settings.rate)}토큰, 60초 = ${fmt(st.settings.rate * 60)}토큰`;
    show("rules-modal", true);
  }
  const closeRules = () => {
    show("rules-modal", false);
    if (autoStart && st && st.status === "lobby" && st.is_host) { autoStart = false; startRoom(); }
  };
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
