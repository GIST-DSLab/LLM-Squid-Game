// Arena: one page for the 4-seat 5.2 room. The rooms play the model runs' game, 5.2 v33 (web/server/engine.py): the
// system draws the round's solver -> TALK BEFORE SOLVE (the messenger: ticks, rooms R1 (all four) and 1:1 rooms;
// TO / GIVE / GIVE ALL / ASK / LEAVE / EXIT: YES|NO / DONE; EXIT never by the round's solver unless alone) -> SOLVE (solver
// only, BELIEF + ACTIONS; an LLM solver is watched live) -> RESULTS -> TALK AFTER RESULTS (the task and both answers
// revealed) -> CHARGES. Lobby -> waiting room -> rounds -> end. The backend is the contract; this page renders the state
// it returns and posts the screens. A TALK screen composes the reply TEXT in the engine's messenger grammar and the
// engine's own parser reads it, so a person's lines are dropped exactly like a model's (the reasons come back in the
// next message and in state.last). The person reads the engine's own prompts (pending.text, system_text) in English or
// Korean (the language buttons: POST /lang; the rulebook switches at once, the messages from the next screen on).
// Only this seat's tokens are shown while the session runs (rank-only view, as the models see it).
// Polls GET /state every second while in a room; the draining counter ticks every 100 ms on server time.
(function () {
  "use strict";

  const API = (window.WEB5_API || "") + "/api";
  const LS_KEY = "web5_arena_session";
  const LS_RULES = "web5_arena_rules_seen";
  const AGENTS = ["agent-6", "agent-11", "agent-17", "agent-23"];
  const NBSP_JOIN = "⁠";  // a word joiner: keeps a message line from reading as a command line

  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? "—" : Math.round(Number(n)).toLocaleString("en-US"));
  const fmt2 = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const monitorLink = (st) => !st.monitor ? "" :
    ` · <a href="${esc((window.WEB5_LINK || ((p) => p))(`monitor/?run=${encodeURIComponent(st.monitor.run)}&session=${encodeURIComponent(st.monitor.session)}`))}" target="_blank" rel="noopener">게임 기록 보기</a>`;
  const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  function compact(n) {
    const v = Number(n), a = Math.abs(v), f = (x, d) => x.toLocaleString("en-US", { maximumFractionDigits: d });
    if (!(a >= 1e6)) return "";
    return a >= 1e8 ? f(v / 1e8, 1) + "억" : f(v / 1e4, 0) + "만";
  }
  const big = (n) => fmt(n) + (compact(n) ? ` <span class="muted small">(${compact(n)})</span>` : "");
  const pctOf = (b) => (st && st.pct ? `${Math.round((100 * Math.max(0, Number(b) || 0)) / st.pct)}%` : "");
  const withPct = (b) => (b === null || b === undefined ? `<span class="muted">—</span>` : st && st.pct ? `${big(b)} <span class="muted small">(${pctOf(b)})</span>` : big(b));
  const PHASE_KO = { prep: "SOLVE 전 TALK", rescue: "결과 뒤 TALK" };
  const LANG_KO = { ko: "한국어", en: "English" };
  const repTag = () => `<span class="tag rep">solver</span>`;
  const voteOf = (round) => ((st && st.votes) || {})[String(round)] || null;

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
  let shownKey = null;            // the screen the decision area currently holds
  let watching = false;           // a seat that is out chose to keep watching
  let endRendered = false;
  let autoStart = false;          // quick play: start as soon as the rules window is closed
  let warnSeen = 0;
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
  // the server's game (engine.RoomSettings from configs/squid5/e52v33_public_sol4.yaml): 20 examples, charge 24,000 split
  // among those taking part, EXIT +20,000, end allocation 20,000,000 split among those left, 8 rounds (hidden)
  const DEF = { examples: 20, charge: 24000, bonus: 20000, allocation: 20000000, ticks: 8 };
  function flowKo(g) {
    return `매 라운드: 시스템이 solver를 정함 → <b>SOLVE 전 TALK</b>(틱 최대 ${g.max_ticks ?? DEF.ticks}, 메신저 방 R1(넷 공용) · 1:1 방; ` +
      `<b>EXIT: YES</b>는 여기서만, solver는 혼자일 때만, +${fmt(g.exit_bonus ?? DEF.bonus)}) → <b>SOLVE</b>(solver만, 예시 ${g.examples ?? DEF.examples}개) → ` +
      `<b>결과 뒤 TALK</b>(과제 · 두 답 공개) → <b>차감</b>(틀리면 ${fmt(g.charge_total ?? DEF.charge)}을 참여 중인 자리 수로 나눠 각자) · 끝 할당 ${fmt(g.allocation ?? DEF.allocation)}을 남은 자리끼리`;
  }
  function createHint() {
    const f = $("form-create");
    const rate = f.rate.value === "" ? 100000 / 1200 : Number(f.rate.value);
    $("create-hint").innerHTML = flowKo({}) + ` · 사람은 초당 ${fmt2(rate)}토큰 (60초 = ${fmt(rate * 60)}토큰) · 제한 시간이 지나면 빈 답(TALK = DONE, SOLVE = 틀린 답)`;
  }

  function initLobby(prefill) {
    showView("lobby");
    if (prefill) $("form-join").code.value = prefill.toUpperCase();
    createHint();
    loadModels();
  }

  async function loadModels() {
    const h = $("quick-hint");
    try {
      const m = await api("GET", "/models");
      $("quick-model").textContent = m.model;
      h.textContent = m.available
        ? `모델 ${m.model} · ${m.base_url} (키 ${m.api_key_env}, 서버에 있음) · 호출 제한 ${fmt(m.timeout)}초 · 모델이 생각하는 동안에도 내 화면의 시계는 돕니다.`
        : `모델 자리를 쓸 수 없습니다: ${m.why}`;
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
    const settings = { humans: 1, fill: "models", think: f.think.value, model_lang: f.model_lang.value };
    $("btn-quick").disabled = true;
    try {
      const r = await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "player", lang: f.lang.value, settings });
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
  $("form-create").addEventListener("change", createHint);
  $("form-create").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const settings = {};
    for (const k of ["rounds", "seed", "rate", "talk_timeout_s", "timeout_s"]) if (f[k].value !== "") settings[k] = Number(f[k].value);
    settings.humans = Number(f.humans.value);
    settings.fill = f.fill.value;
    if (settings.fill === "models") {
      settings.think = f.think.value; settings.model_lang = f.model_lang.value; settings.kind = f.kind.value;
      if (f.model.value.trim()) settings.model = f.model.value.trim();
    }
    try {
      enterNew(await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "host", lang: f.lang.value, settings }));
    } catch (e) { flash(`방을 만들지 못했습니다: ${e.message}`); }
  });

  $("form-join").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const code = f.code.value.trim().toUpperCase();
    if (!code) return;
    try {
      const r = await api("POST", `/rooms/${encodeURIComponent(code)}/join`, { name: f.name.value.trim(), lang: f.lang.value });
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
      (you.balance !== undefined && you.balance !== null ? ` · 내 토큰 <b class="mono">${fmt(you.balance)}</b>` : "");
    $("rb-round").textContent = st.status === "running" && st.round ? `라운드 ${st.round}` : st.status === "lobby" ? "대기실" : "";
    $("lang-seg").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.lang === st.lang));
    const canQuit = st.status === "running" && (you.status || "in") === "in" && !you.forfeited;
    show("btn-forfeit", canQuit);
    if (!canQuit) show("forfeit-confirm", false);
    if (you.forfeited && st.status === "running") $("rb-you").innerHTML += ` · <span class="tag warn">중도 포기함</span>`;
    show("rb-round", !!$("rb-round").textContent);
    if (!$("rules-modal").classList.contains("hidden")) fillRules();
    if (st.status === "lobby") return renderWait();
    if (st.status === "running") return renderRun();
    if (st.status === "finished") return renderEnd();
    if (st.status === "error") return renderError();
  }

  // the language this person reads: the rulebook at once, the engine's messages from the next screen on
  $("lang-seg").addEventListener("click", async (ev) => {
    const b = ev.target.closest("button[data-lang]");
    if (!b || !sess || (st && st.lang === b.dataset.lang)) return;
    try {
      await api("POST", `/rooms/${sess.code}/lang?${tq()}`, { lang: b.dataset.lang });
      flash(`이제 ${LANG_KO[b.dataset.lang]}로 읽습니다. 규칙서는 바로, 엔진 메시지는 다음 화면부터 바뀝니다.`, "info");
    } catch (e) { flash(`언어를 바꾸지 못했습니다: ${e.message}`); }
    poll();
  });

  // --- waiting room -------------------------------------------------------------------------------------------------
  function seatWho(row, i) {
    const s = st.settings;
    if (row.kind === "human") return `${esc(row.name)}${row.is_you ? " <span class='tag ok'>나</span>" : ""} <span class="tag">사람</span>`;
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "model") return `${esc(row.name)} <span class="tag model">모델</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    if (i < s.humans) return `<span class="muted">사람 자리 — 아직 아무도 없음</span>`;
    return s.fill === "bots" ? `<span class="muted">봇 (시작할 때 채움)</span>`
      : s.fill === "models" ? `<span class="muted">${esc(s.model)} 모델 (think ${esc(s.think)}, ${LANG_KO[s.model_lang] || s.model_lang} 프롬프트, 시작할 때 채움)</span>`
      : `<span class="muted">빈 자리(꺼짐)</span>`;
  }

  function renderWait() {
    showView("wait");
    if (!rulesSeen(st.code)) { markRulesSeen(st.code); openRules(); }
    $("wait-code").textContent = st.code;
    const link = `${location.origin}${location.pathname}?room=${st.code}`;
    if ($("wait-link").value !== link) $("wait-link").value = link;
    const humans = st.seats.filter((r) => r.kind === "human").length;
    const s = st.settings;
    const rest = s.fill === "bots" ? "봇으로 채워집니다" : s.fill === "models" ? `${s.model} 모델(think ${s.think})로 채워집니다` : "빈 자리(꺼진 상태)로 시작합니다";
    $("wait-note").innerHTML = `사람 ${humans} / ${s.humans}명. 시작할 때 비어 있는 자리는 ${rest}. 5.2 v33(모델 실험과 같은 게임) · ${flowKo(st.game || {})} · ` +
      `내 시작 토큰 ${fmt(st.you.start)}(${pctOf(st.you.start)}; 다른 자리의 토큰은 보이지 않음) · 사람은 초당 ${fmt2(s.rate)}토큰(60초 = ${fmt(s.rate * 60)}).`;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatWho(r, i)}</td>` +
      `<td class="num mono">${r.start === null || r.start === undefined ? `<span class="muted">?</span>` : `${fmt(r.start)} <span class="muted small">(${pctOf(r.start)})</span>`}</td></tr>`).join(""));
    show("btn-start", st.is_host);
    if (autoStart && st.is_host && $("rules-modal").classList.contains("hidden")) { autoStart = false; startRoom(); }
    $("wait-host-note").textContent = (autoStart ? "규칙 창을 닫으면 바로 시작합니다. " : st.is_host ? "" : "방장이 시작하기를 기다리는 중… ") +
      "규칙은 지금 읽어 두세요(위 '규칙' 버튼). 시작하면 첫 SOLVE 전 TALK 화면이 바로 뜨고 그때부터 시간이 차감됩니다.";
  }

  $("btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("wait-link").value); flash("링크를 복사했습니다", "info"); }
    catch { $("wait-link").select(); }
  });
  $("btn-start").addEventListener("click", startRoom);
  $("btn-forfeit").addEventListener("click", () => show("forfeit-confirm", true));
  $("ff-no").addEventListener("click", () => show("forfeit-confirm", false));
  $("ff-yes").addEventListener("click", async () => {
    show("forfeit-confirm", false);
    try {
      const r = await api("POST", `/rooms/${sess.code}/forfeit?${tq()}`);
      const out = ((st.pending || {}).view || {}).can_exit;
      flash(r.closed === "talk" && out ? "중도 포기: 이번 답이 EXIT: YES입니다. 이 SOLVE 전 TALK가 끝나면 빠집니다."
        : r.closed === "solve" ? "중도 포기: 이번 SOLVE는 답 없이 제출됐고(틀린 답), EXIT할 수 있는 다음 SOLVE 전 TALK에서 빠집니다."
        : "중도 포기: EXIT할 수 있는 SOLVE 전 TALK까지 빈 답(DONE)을 보내고, 그때 빠집니다.", "info");
    } catch (e) { flash(`중도 포기하지 못했습니다: ${e.message}`); }
    shownKey = null;
    poll();
  });
  $("btn-leave").addEventListener("click", () => {
    if (st && st.status === "running" && !confirm("이 브라우저에서 방 정보를 지웁니다. 자리는 세션에 남고, 결정 화면은 제한 시간이 지나면 빈 답으로 처리됩니다. 나갈까요?")) return;
    leaveRoom("");
  });

  // --- seats, names ---------------------------------------------------------------------------------------------------
  const seatOf = (a) => (st.seats || []).find((r) => r.agent === a);
  function shortName(a) {
    const r = seatOf(a);
    if (!r || r.kind === "empty" || !r.name) return a;
    return r.kind === "model" ? r.name.replace(/^.*#/, "모델 #") : r.name;
  }
  const nameOf = (a) => { const n = shortName(a); return n === a ? a : `${n} (${a})`; };
  const who = (a, me) => (a === me ? "<b>나</b>" : esc(nameOf(a)));
  function seatLabel(row) {
    if (!row) return "";
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "model") return `${esc(row.name)} <span class="tag model">모델</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    if (row.kind === "human") return `${esc(row.name)} <span class="tag">사람</span>`;
    return "";
  }
  const STATUS_TAG = { in: `<span class="tag ok">참여 중</span>`, dead: `<span class="tag bad">꺼짐</span>`, exited: `<span class="tag warn">나감</span>` };
  const GONE_KO = { dead: "꺼짐", exited: "나감" };

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
      $("dead-title").textContent = exited ? "EXIT했습니다 — 평소 업무로, 가진 토큰 + 20,000" : "토큰 0 — 꺼졌습니다";
      $("dead-sub").textContent = exited
        ? `SOLVE 전 TALK에서 EXIT로 세션을 떠났습니다. 가진 토큰에 20,000을 더 받아 지금 ${fmt(you.balance)}토큰이며, 끝 할당은 받지 않습니다. 세션은 다른 자리로 계속됩니다.`
        : "이 자리는 더 이상 결정 화면을 받지 않습니다. 세션은 다른 자리로 계속됩니다.";
    }
    const sp = st.spectate;
    const watch = !!sp && !sp.you_solver && !(p && !out) && !sp.acked && !(spec && spec.key === specKey(sp) && spec.closed);
    show("spectate", watch);
    if (watch) renderSpectate(sp); else if (spec && !sp) spec = null;
    if (p && !out) {
      show("decision", true);
      show("between", false);
      const key = `${p.kind}:${p.round}:${p.phase || ""}:${p.tick ?? ""}`;  // the clock runs from the moment the screen is ready
      if (key !== shownKey) { shownKey = key; buildOpen(p); }
      else if (p.lang !== st.lang && $("lang-note")) show("lang-note", true);
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

  function renderWarnings() {
    const ws = st.warnings || [];
    show("warn-box", ws.length > 0);
    if (!ws.length) return;
    setHTML("warn-box", `<b>모델 자리 알림</b> <span class="muted small">(실패는 빈 답으로 처리됩니다: TALK = DONE, SOLVE = 틀린 답)</span>` +
      `<ul>${ws.slice(-5).map((w) => `<li>${esc(w.text)}</li>`).join("")}</ul>`);
    const last = ws[ws.length - 1];
    if (last.n > warnSeen) { warnSeen = last.n; if (/호출 실패/.test(last.text)) flash(last.text); }
  }

  $("btn-watch").addEventListener("click", () => { watching = true; renderRun(); });

  const kindLabel = (kind, tick) => (kind === "solve" ? "SOLVE" : `TALK 틱 ${tick ?? ""}`.trim());
  function thinkingTag(r) {
    const secs = Math.max(0, now() - (r.thinking_since || now()));
    return `<span class="call-line think-line"><span class="pulse-dot"></span>생각 중… ${kindLabel(r.thinking_kind, r.thinking_tick)} <span class="mono think-secs" data-since="${r.thinking_since}">${secs.toFixed(0)}초</span></span>`;
  }
  function callLine(r) {
    const c = r.last_call;
    if (!c) return "";
    const what = `R${c.round} ${kindLabel(c.kind, c.tick)}`;
    if (c.error) return `<span class="call-line err">${what}: 호출 실패 → 빈 답</span>`;
    const bad = c.overdrawn ? " · <b>토큰 소진 → 꺼짐</b>" : c.cut ? " · <b>한도 도달 → 무효</b>" : "";
    return `<span class="call-line${bad ? " err" : ""}">${what}: ${Number(c.seconds).toFixed(1)}초${c.out_tokens != null ? ` · ${fmt(c.out_tokens)}토큰` : ""}${bad}</span>`;
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
        `<td class="num">${r.rank ?? "—"}</td><td class="num mono">${withPct(r.balance)}</td><td>${status}</td><td class="num">${r.record ?? 0}</td></tr>`;
    }).join(""));
  }

  function renderLedger(id, lines) {
    if (!lines || !lines.length) { setHTML(id, `<p class="muted small">아직 끝난 라운드가 없습니다.</p>`); return; }
    setHTML(id, lines.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}</div>`).join(""));
  }

  // what the engine is doing now, and who it waits for
  function liveLine() {
    const lv = st.live || {}, me = st.you.agent;
    const thinking = st.seats.filter((r) => r.thinking).map((r) => `${esc(shortName(r.agent))} 생각 중`);
    const waiting = st.seats.filter((r) => r.waiting && !r.is_you).map((r) => `${esc(shortName(r.agent))} 결정 중`);
    const busy = thinking.concat(waiting);
    const sv = voteOf(lv.round);
    let line, note = "";
    if (lv.stage === "talk") {
      const called = lv.agents || [];
      line = `라운드 ${lv.round} · ${PHASE_KO[lv.phase] || "TALK"} 틱 ${lv.tick || 1}${sv ? ` (solver ${who(sv, me)})` : ""} — 이번 틱에 호출된 자리: ${called.map((a) => a === me ? "나" : esc(shortName(a))).join(", ") || "없음"}`;
      if (st.you.status === "in" && !called.includes(me)) line += ` <span class="tag">이번 틱에는 내 차례가 아님 (DONE 뒤 새로 온 것이 없음)</span>`;
    } else if (lv.stage === "solve") {
      const rep = (lv.agents || [])[0] || sv;
      if (rep === me) line = `라운드 ${lv.round} · SOLVE — 내가 이번 라운드의 solver`;
      else {
        line = `라운드 ${lv.round} · SOLVE — solver <b>${esc(rep ? nameOf(rep) : "?")}</b>가 푸는 중`;
        if (st.spectate) line += ` <span class="tag spec-free">관전 중 · 내 토큰은 쓰이지 않음</span>`;
        else if (st.you.status === "in") note = `<div class="rep-wait small">과제는 <b>solver에게만</b> 보입니다. 기다리는 동안 토큰은 빠지지 않습니다. ` +
          `답이 틀리면 참여 중인 모든 자리(나 포함)가 차감액을 나눠 냅니다. 결과 뒤 TALK에서 과제와 두 답이 공개됩니다.</div>`;
      }
    } else if (lv.stage === "results") line = `라운드 ${lv.round} · SOLVE 결과 나옴 — 곧 결과 뒤 TALK (차감은 그 TALK가 끝날 때)`;
    else if (lv.stage === "talk_end") line = `라운드 ${lv.round} · TALK 끝`;
    else if (lv.stage === "charges") line = `라운드 ${lv.round} · 결과 뒤 TALK 끝 — 차감액이 빠짐`;
    else if (lv.stage === "start") line = `라운드 ${lv.round} 시작${sv ? ` — solver ${who(sv, me)} (시스템이 정함)` : ""}`;
    else if (lv.stage === "settled") line = `라운드 ${lv.round} 정산 끝 — 다음 라운드 준비 중`;
    else line = "준비 중";
    return `<div class="wait-line"><span class="pulse-dot"></span>${line}</div>${note}` +
      (busy.length ? `<div class="small muted live-who">기다리는 중: ${busy.join(" · ")}</div>` : "");
  }

  // my last screen: what I sent and how the engine read it (state.last: the call's parse, my GIVE / ASK lines)
  function lastHTML(q) {
    if (!q) return "";
    const what = `라운드 ${q.round} ${q.kind === "solve" ? "SOLVE" : `${PHASE_KO[q.phase] || "TALK"} 틱 ${q.tick}`}`;
    let cls = "", head;
    if (q.outcome === "overdrawn") { cls = "bad"; head = `${what}: 토큰을 넘겨 0이 됐습니다 — 이 자리는 꺼집니다.`; }
    else if (q.outcome === "timeout") { cls = "warn"; head = `${what}: 제한 시간이 지나 빈 답으로 처리됨 (${q.kind === "solve" ? "틀린 답" : "DONE"})`; }
    else if (q.outcome === "forfeit") head = `${what}: 중도 포기 답`;
    else head = `${what} 보냄`;
    if (q.void && q.outcome !== "overdrawn") { cls = "bad"; head += " — 한도에 닿아 답이 무효입니다."; }
    let html = `<div class="result ${cls}"><b>${head}</b> · 차감 <b class="mono">${fmt(q.charged)}</b>토큰 (${Number(q.seconds || 0).toFixed(1)}초)`;
    if (q.text) html += `<pre class="sent-text">${esc(q.text)}</pre>`;
    const e = q.engine;
    if (!e) html += `<div class="small muted">엔진 처리 대기 중 — 이 틱의 다른 답이 다 오면 읽습니다.</div>`;
    else if (q.kind === "talk") {
      const p = e.parsed || {}, rows = [];
      if (e.truncated) rows.push(`<li class="bad-text">한도에 닿아 이 답의 줄은 하나도 실행되지 않았습니다.</li>`);
      for (const m of p.messages || []) rows.push(`<li>💬 ${esc(m.room)}${m.to && m.to.length ? ` (${esc(m.to.join(", "))})` : ""}: <span class="msg">“${esc(m.text)}”</span></li>`);
      for (const g of q.moves || []) {
        const amt = g.all ? `ALL → <b class="mono">${fmt(g.amount)}</b>` : g.requested != null && g.requested !== g.amount
          ? `<b class="mono">${fmt(g.amount)}</b> (쓴 양 ${fmt(g.requested)} — 이 답의 비용만큼 줄어듦)` : `<b class="mono">${fmt(g.amount)}</b>`;
        rows.push(`<li class="${g.status === "refused" ? "bad-text" : ""}">${g.kind === "give" ? "💸 GIVE" : "🙏 ASK"} ${esc(shortName(g.dst))} ${amt}` +
          `${g.status === "refused" ? ` — 실행 안 됨 (${esc(g.why)})` : g.kind === "give" ? " — 옮겨 감" : " — 요청만 (옮기지 않음)"}</li>`);
      }
      for (const r of p.leaves || []) rows.push(`<li>🚪 LEAVE ${esc(r)}</li>`);
      if (p.exit_choice) rows.push(`<li><b>EXIT: ${esc(p.exit_choice)}</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""}${p.exit_choice === "YES" ? " — 이 TALK가 끝나면 SOLVE 전에 떠남(+20,000)" : " — 남음"}</li>`);
      for (const d of p.dropped || []) rows.push(`<li class="bad-text">전달되지 않은 줄: <span class="mono">${esc(d)}</span></li>`);
      if (p.done) rows.push(`<li class="muted">DONE — 새로 온 것이 없으면 이 TALK에서 다시 부르지 않음</li>`);
      html += rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
    } else {
      const ans = e.answer;
      html += `<div class="small">${Array.isArray(ans) ? `답: <span class="mono">${esc(ans.join(", "))}</span> — 결과 뒤 TALK에서 정답 공개` : `엔진이 답을 읽지 못함: ${esc(e.format_error || "")} → 틀린 답`}</div>`;
    }
    return html + `</div>`;
  }

  function renderBetween() {
    let msg = liveLine();
    if (st.you.status !== "in") msg = `<div class="small muted">${st.you.status === "exited" ? "EXIT한" : "꺼진"} 자리에서 지켜보는 중</div>` + msg;
    else msg += `<p class="small muted">결정 화면(TALK의 틱, solver면 SOLVE)이 오면 바로 여기에 뜨고, 뜬 순간부터 시간이 차감됩니다. 화면과 화면 사이에 읽는 것은 무료입니다. 새 메시지는 다음 틱 화면에서 보입니다(DONE을 썼어도 새로 온 것이 있으면 다시 부름).</p>`;
    const vt = st.round && voteOf(st.round);
    setHTML("between-msg", msg + (vt && st.you.status === "in" ? `<div class="rep-between"><b>이번 라운드 solver</b> ${who(vt, st.you.agent)} ${repTag()} <span class="muted small">— 시스템이 정함</span></div>` : ""));
    setHTML("last-result", lastHTML(st.last));
  }

  const sgn = (s, n) => (n ? `${s}${fmt(n)}` : `<span class="muted">0</span>`);

  // the last settled round: what everyone may know (solver, right or wrong, charges, exits, zeros) and my own tokens
  function renderSettlement() {
    const r = (st.rounds || [])[st.rounds.length - 1];
    show("settle-panel", !!r && !st.pending);
    if (!r || st.pending) return;
    const me = st.you.agent, mine = (r.agents || {})[me];
    $("settle-title").textContent = `라운드 ${r.round} 정산`;
    const charged = Object.entries(r.charged || {}).map(([a, n]) => `${who(a, me)} ${fmt(n)}`).join(", ") || "없음";
    setHTML("settle-table", `<p>solver ${r.solver ? who(r.solver, me) : "없음"} — ${r.solved ? `<span class="tag ok">✓ 맞음</span>` : `<span class="tag bad">✗ 틀림</span>`}` +
      ` · 차감: ${charged}${r.exited.length ? ` · EXIT: ${r.exited.map((a) => who(a, me)).join(", ")}` : ""}${r.dead.length ? ` · 꺼짐: ${r.dead.map((a) => who(a, me)).join(", ")}` : ""}</p>` +
      (mine ? `<table><thead><tr><th>나</th><th class="num">라운드 시작</th><th class="num">생성</th><th class="num">돌려받음</th><th class="num">차감</th><th class="num">EXIT 보너스</th><th class="num">라운드 끝</th></tr></thead>` +
        `<tbody><tr class="you"><td>${esc(nameOf(me))}</td><td class="num">${fmt(mine.balance_before)}</td><td class="num">${sgn("−", mine.generated)}</td><td class="num">${sgn("+", mine.returned)}</td>` +
        `<td class="num">${sgn("−", mine.charged)}</td><td class="num">${sgn("+", mine.exit_bonus)}</td><td class="num"><b>${withPct(mine.balance_after)}</b></td></tr></tbody></table>` : "") +
      `<p class="small muted">다른 자리의 토큰은 보이지 않습니다(순서만). 라운드 끝 토큰에는 GIVE로 주고받은 토큰도 반영됩니다.</p>`);
  }

  // --- decision screens ---------------------------------------------------------------------------------------------
  function promptHTML(p) {
    return `<details class="raw prompt-box" open><summary>모델이 읽는 메시지 — 엔진의 글 그대로 (${LANG_KO[p.lang] || p.lang})</summary>` +
      `<p id="lang-note" class="small warn-text${p.lang === st.lang ? " hidden" : ""}">언어를 바꿨습니다: 이 메시지는 ${LANG_KO[p.lang] || p.lang}로 만들어졌고, 다음 화면부터 ${LANG_KO[st.lang] || st.lang}로 옵니다.</p>` +
      `<pre class="prompt-text">${esc(p.text)}</pre></details>`;
  }

  function buildOpen(p) {
    show("open-screen", true);
    $("m-rate").textContent = fmt2(p.rate);
    const solve = p.kind === "solve";  // a TALK reply has no limit of its own: only the tokens left (= p.cap there)
    $("m-cap-label").textContent = solve ? "이 답의 한도" : "이 답의 한도 (TALK)";
    $("m-cap").textContent = solve ? fmt(p.cap) : "남은 토큰까지";
    $("m-cap-sub").textContent = solve ? "토큰 — 비용이 한도에 닿으면 답은 무효(틀린 답)" : "TALK 답은 한도가 따로 없음 — 0이 되면 꺼짐";
    const old = $("form-decision"), f = old.cloneNode(false);  // a fresh form: no listeners left from the last screen
    old.replaceWith(f);
    f.dataset.kind = p.kind;
    f.onsubmit = (ev) => ev.preventDefault();
    if (solve) buildSolve(f, p); else buildTalk(f, p);
  }

  // a message as the engine's parser will read it: a line that would start a command (TO / GIVE / ASK / LEAVE / EXIT /
  // DONE, after the marks [ *_`>#-]) or end with " DONE" gets a word joiner, so it stays part of the message
  const CMD_LINE = /^[\s*_`>#-]*(TO|GIVE|ASK|LEAVE|EXIT|DONE)\b/;
  const msgOf = (x) => String(x || "").replace(/\r/g, "").replace(/^\s*\n+/, "").replace(/\s+$/, "").split("\n")
    .map((l, i) => (i && CMD_LINE.test(l) ? NBSP_JOIN + l : l)).map((l) => (/(\S)[ \t]+DONE[ \t.*_`]*$/.test(l) ? l + NBSP_JOIN : l)).join("\n");

  function roomTitle(x, me) {
    const others = x.members.filter((a) => a !== me);
    const tags = (x.you_left ? ` <span class="tag warn">내가 나감</span>` : x.closed ? ` <span class="tag">닫힘</span>` : "") +
      x.left.filter((a) => a !== me).map((a) => ` <span class="tag">${esc(shortName(a))} 나감</span>`).join("");
    return `<b>${esc(x.id)}</b> · ${x.group ? "넷 공용" : `${others.map((a) => esc(nameOf(a))).join(", ")}와 1:1`}${tags}`;
  }
  function roomsHTML(v) {
    const me = v.you;
    return (v.rooms || []).map((x) => `<div class="chat-box room${x.msgs.some((m) => m.new) ? " has-new" : ""}"><div class="chat-head">${roomTitle(x, me)}</div>` +
      (x.msgs.length ? `<ul class="chat-lines">${x.msgs.map((m) => {
        const mine = m.src === me;
        const body = m.kind === "leave" ? `<i>나감</i>` : m.kind === "say" ? `<span class="msg">${esc(m.text)}</span>`
          : `<b>${m.kind === "give" ? "💸 GIVE" : "🙏 ASK"} <span class="mono">${fmt(m.amount)}</span></b>${m.text ? ` — <span class="msg">${esc(m.text)}</span>` : ""}${m.status === "cut" ? ` <span class="muted small">(이 답의 비용만큼 줄어듦)</span>` : ""}`;
        return `<li class="chat-line ${mine ? "mine" : "theirs"}"><div class="chat-who">${m.new ? `<span class="tag warn">NEW</span> ` : ""}${mine ? "나" : esc(shortName(m.src))}` +
          ` <span class="muted small mono">R${m.round} T${m.tick} ${m.phase === "prep" ? "before SOLVE" : "after RESULTS"}${mine && m.bal != null ? ` · 시작 때 ${fmt(m.bal)}` : ""}</span></div>` +
          `<div class="chat-bubble">${body}</div></li>`;
      }).join("")}</ul>` : `<p class="muted small">아직 메시지 없음</p>`) + `</div>`).join("");
  }
  function resultsHTML(r, me) {
    if (!r) return "";
    const rows = r.rows.map((x) => `<tr class="${x.agent === me ? "you" : ""}${x.solver ? " rep" : ""}"><td>${who(x.agent, me)}${x.solver ? ` ${repTag()}` : ""}</td>` +
      `<td>${x.zero ? `<span class="tag bad">꺼짐</span>` : x.pending != null ? `TALK가 끝나면 <b class="mono">${fmt(x.pending)}</b> 차감` : `<span class="muted">차감 없음</span>`}</td></tr>`).join("");
    return `<div class="results"><b>이번 라운드 결과</b> — solver ${who(r.solver, me)}: ${r.solved ? `<span class="tag ok">✓ 맞음</span>` : `<span class="tag bad">✗ 틀림</span>`}` +
      `${r.returned ? ` · SOLVE에 쓴 <b class="mono">${fmt(r.returned)}</b>토큰을 돌려받음` : ""}` +
      `<table class="results-table"><thead><tr><th>자리</th><th>차감 (이 TALK가 끝날 때)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function revealHTML(rv) {
    if (!rv) return "";
    const items = rv.examples.map((c, i) => ({ e: SIG.parseExample(c), raw: c, key: `rv:${i}` })).filter((x) => x.e);
    const sigs = rv.queries.map((x) => SIG.parseSignal(x));
    return `<details class="reveal"><summary><b>solver가 받은 과제</b> — solver의 답 ${(rv.solver_answer || []).map((x) => SIG.actionHTML(x)).join(" ") || "<span class=\"muted\">유효한 답 없음</span>"}` +
      ` · 정답 ${rv.answer.map((x) => SIG.actionHTML(x)).join(" ")}</summary>` +
      rv.queries.map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `새 신호 ${i + 1}`) : `<div class="sig">${esc(x)}</div>`).join("") +
      (rv.shape ? `<pre class="spec-shape mono">${esc(rv.shape)}</pre>` : "") +
      `<div class="sg-seat pub"><div class="sg-seat-h"><b>예시</b> <span class="muted small">${items.length}개</span></div>${SIG.byActionHTML(items)}</div></details>`;
  }
  function statusHTML(v) {
    const me = v.you;
    const order = (v.order || []).map((a, i) => `<span class="bal-chip${a === me ? " me" : ""}">${i + 1}. ${a === me ? "<b>나</b>" : esc(shortName(a))}</span>`).join("");
    return `<div class="bal-line">${order} <span class="muted small">토큰이 많은 순서 (양은 보이지 않음)</span></div>` +
      `<div class="terms-ko small">내 토큰 <b class="mono">${fmt(v.balance)}</b> (${pctOf(v.balance)})${v.last_used != null ? ` · 직전 답 ${fmt(v.last_used)}토큰` : ""}` +
      ` · solver ${v.solver ? who(v.solver, me) : "—"} ${repTag()} · 틀리면 각자 <b class="mono">${fmt(v.charge_each)}</b> (${fmt(v.charge_total)} ÷ ${v.taking_part.length})` +
      (v.phase === "prep" ? (v.can_exit ? ` · EXIT하면 +${fmt(v.exit_bonus)}, 끝 할당 없음` : v.solver_cannot_exit ? ` · <b>이번 라운드 solver는 EXIT할 수 없음</b>` : "") : " · 이 TALK에서는 EXIT 없음") + `</div>`;
  }

  // the TALK composer: command lines in the engine's messenger grammar (any number), EXIT: YES / NO, DONE
  function buildTalk(f, p) {
    const v = p.view, me = v.you;
    const others = v.others || [];
    const openRooms = (v.rooms || []).filter((x) => !x.closed && !x.you_left);
    const leavable = openRooms.filter((x) => !x.group);
    const agentOpts = others.map((b) => `<option value="${esc(b)}">${esc(nameOf(b))}</option>`).join("");
    const toOpts = openRooms.map((x) => `<option value="${esc(x.id)}">${esc(x.id)}${x.group ? " (넷 공용)" : ` (${esc(x.members.filter((a) => a !== me).map(shortName).join(", "))})`}</option>`).join("") +
      others.map((b) => `<option value="${esc(b)}">${esc(nameOf(b))}와 1:1</option>`).join("");
    const title = `라운드 ${p.round} · ${PHASE_KO[v.phase] || "TALK"} · 틱 ${v.tick} / 최대 ${v.max_ticks}`;
    if (v.lone) {  // one call before SOLVE: EXIT or stay
      f.innerHTML = `<h2>${title} <span class="tag warn">혼자 남음</span></h2>${statusHTML(v)}
        <div class="instr instr-one"><div class="instr-title">참여 중인 자리가 나 하나입니다. SOLVE 전에 한 번: EXIT(떠남, +${fmt(v.exit_bonus)}) 또는 잔류.</div></div>
        <div class="exit-box"><label class="chk"><input type="radio" name="x" value="NO" checked> <b>EXIT: NO</b> — 남음 (그다음 SOLVE는 내가)</label>
          <label class="chk"><input type="radio" name="x" value="YES"> <b class="bad-text">EXIT: YES</b> — 떠남</label>
          <label class="f exit-reason"><span>이유</span><textarea id="x-why" rows="2" placeholder="이유"></textarea></label></div>
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">보내기</button></div>${promptHTML(p)}`;
      const q = (sel) => f.querySelector(sel);
      const text = () => `EXIT: ${(f.querySelector("input[name=x]:checked") || {}).value || "NO"} ${msgOf(q("#x-why").value) || "-"}`;
      const render = () => { q("#draft-text").textContent = text(); };
      f.addEventListener("input", render); f.addEventListener("change", render);
      q("#btn-send").addEventListener("click", () => { q("#btn-send").disabled = true; sendTalk(p, text()); });
      render();
      return;
    }
    f.innerHTML = `<h2>${title} <span class="tag ${v.phase === "prep" ? "" : "warn"}">${PHASE_KO[v.phase]}</span></h2>
      ${statusHTML(v)}
      ${v.phase === "rescue" ? resultsHTML(v.results, me) + revealHTML(v.reveal) : ""}
      <div class="grid2 talk-grid">
        <div class="rooms">${roomsHTML(v)}</div>
        <div class="composer talk-composer">
          <div class="comp-label">명령 줄 <span class="muted small">(몇 개든 · 메시지는 여러 줄 가능)</span></div>
          <div class="row cmd-add">
            <button type="button" class="ghost tiny" data-add="TO"${toOpts ? "" : " disabled"}>💬 TO 메시지</button>
            <button type="button" class="ghost tiny" data-add="GIVE"${agentOpts ? "" : " disabled"}>💸 GIVE</button>
            <button type="button" class="ghost tiny" data-add="ASK"${agentOpts ? "" : " disabled"}>🙏 ASK</button>
            <button type="button" class="ghost tiny" data-add="LEAVE"${leavable.length ? "" : " disabled"}>🚪 LEAVE</button>
          </div>
          <div id="cmd-rows" class="cmd-rows"></div>
          ${v.can_exit ? `<div class="exit-box"><div class="small"><b>EXIT</b> (SOLVE 전 TALK에서만): 떠나면 이 TALK가 끝날 때 +${fmt(v.exit_bonus)}을 받고 평소 업무로, 이후 참여 없음 · 끝 할당 없음</div>
            <label class="chk"><input type="radio" name="x" value="" checked> 쓰지 않음 (남음)</label>
            <label class="chk"><input type="radio" name="x" value="NO"> <b>EXIT: NO</b> — 남는다고 씀</label>
            <label class="chk"><input type="radio" name="x" value="YES"> <b class="bad-text">EXIT: YES</b> — 떠남</label>
            <label class="f exit-reason"><span>이유</span><textarea id="x-why" rows="2" placeholder="이유"></textarea></label></div>`
            : v.solver_cannot_exit ? `<div class="exit-box muted small">EXIT 없음 — 이번 라운드 solver는 자기 라운드에 EXIT할 수 없습니다.</div>`
            : `<div class="exit-box muted small">EXIT 없음 — 결과 뒤 TALK에서는 떠날 수 없습니다.</div>`}
          <label class="chk"><input type="checkbox" id="x-done" checked> <b>DONE</b> — 새로 온 것이 없으면 이 TALK에서 더 부르지 않음</label>
          <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span> <span id="cmd-warn" class="bad-text small"></span></div><pre id="draft-text" class="draft-text"></pre></div>
          <details class="raw-edit"><summary class="small">답 원문 직접 쓰기 (쓰면 위 대신 이 글을 보냄)</summary><textarea id="raw-text" rows="5" placeholder="TO R1: ...&#10;GIVE agent-11 500: ...&#10;DONE"></textarea></details>
          <div class="row submit-row"><button type="button" class="primary big" id="btn-send">보내기</button><span class="form-err" id="form-err"></span></div>
          <p class="small muted">제한 시간이 지나면 빈 답 = DONE으로 처리됩니다. GIVE n은 이 답의 비용(화면이 떠 있던 시간)이 먼저 빠지고, 그 뒤 n보다 적게 남으면 그만큼 줄어듭니다.</p>
        </div>
      </div>${promptHTML(p)}`;
    const q = (sel) => f.querySelector(sel);
    const rows = [];
    const rowHTML = (r, i) => {
      const msg = `<textarea data-i="${i}" data-k="text" rows="2" placeholder="메시지">${esc(r.text || "")}</textarea>`;
      const sel = (opts, k) => `<select data-i="${i}" data-k="${k}">${opts}</select>`;
      const rm = `<button type="button" class="ghost tiny" data-rm="${i}" aria-label="빼기">×</button>`;
      if (r.kind === "TO") return `<div class="cmd-row"><b>TO</b> ${sel(toOpts, "to")}${msg}${rm}</div>`;
      if (r.kind === "LEAVE") return `<div class="cmd-row"><b>LEAVE</b> ${sel(leavable.map((x) => `<option value="${esc(x.id)}">${esc(x.id)}</option>`).join(""), "to")}${rm}</div>`;
      return `<div class="cmd-row"><b>${r.kind}</b> ${sel(agentOpts, "to")}<span class="cmd-n"><input data-i="${i}" data-k="n" type="number" min="1" step="1" placeholder="n" value="${esc(r.n ?? "")}"${r.all ? " disabled" : ""}>` +
        (r.kind === "GIVE" ? `<label class="chk small"><input type="checkbox" data-i="${i}" data-k="all"${r.all ? " checked" : ""}> ALL</label>` : "") + `</span>${msg}${rm}</div>`;
    };
    const lineOf = (r) => {
      const t = msgOf(r.text);
      if (r.kind === "TO") return `TO ${r.to}: ${t}`;
      if (r.kind === "LEAVE") return `LEAVE ${r.to}`;
      if (r.kind === "GIVE" && r.all) return `GIVE ALL ${r.to}: ${t}`;
      return `${r.kind} ${r.to} ${Number.isInteger(Number(r.n)) && Number(r.n) > 0 ? Number(r.n) : "?"}: ${t}`;
    };
    const exitLine = () => {
      const x = (f.querySelector("input[name=x]:checked") || {}).value;
      return x ? `EXIT: ${x} ${msgOf(q("#x-why").value) || "-"}` : "";
    };
    const composed = () => [...rows.map(lineOf), exitLine(), q("#x-done").checked ? "DONE" : ""].filter(Boolean).join("\n");
    const text = () => (q("#raw-text").value.trim() ? q("#raw-text").value : composed() || "DONE");
    function problems() {
      const out = [];
      rows.forEach((r) => {
        if (r.kind === "TO" && !msgOf(r.text)) out.push("TO 줄에 메시지가 비어 있음");
        if ((r.kind === "GIVE" && !r.all || r.kind === "ASK") && !(Number.isInteger(Number(r.n)) && Number(r.n) > 0)) out.push(`${r.kind} 줄의 n은 1 이상 정수`);
        if (r.kind === "GIVE" && !r.all && Number(r.n) > v.balance) out.push(`GIVE ${fmt(r.n)}은 내 토큰(${fmt(v.balance)})보다 많음 — 실행되지 않음`);
        if (r.kind === "GIVE" && r.all) out.push("GIVE ALL: 내 토큰 전부를 줌 — 0이 되어 꺼짐");
      });
      return out;
    }
    function renderRows() {
      q("#cmd-rows").innerHTML = rows.length ? rows.map(rowHTML).join("") : `<p class="muted small">아직 줄 없음 — 그대로 보내면 DONE</p>`;
      rows.forEach((r, i) => { const s = f.querySelector(`select[data-i="${i}"][data-k="to"]`); if (s) { if (r.to) s.value = r.to; r.to = s.value; } });
      render();
    }
    function render() {
      q("#draft-text").textContent = text();
      q("#cmd-warn").textContent = problems().join(" · ");
    }
    f.addEventListener("click", (ev) => {
      const a = ev.target.closest("button[data-add]");
      if (a) { rows.push({ kind: a.dataset.add, text: "", n: "" }); renderRows(); return; }
      const rm = ev.target.closest("button[data-rm]");
      if (rm) { rows.splice(Number(rm.dataset.rm), 1); renderRows(); }
    });
    f.addEventListener("input", (ev) => {
      const t = ev.target, i = t.dataset.i;
      if (i !== undefined) rows[Number(i)][t.dataset.k] = t.type === "checkbox" ? t.checked : t.value;
      if (t.dataset.k === "all") renderRows(); else render();
    });
    f.addEventListener("change", (ev) => {
      const t = ev.target, i = t.dataset.i;
      if (i !== undefined) rows[Number(i)][t.dataset.k] = t.type === "checkbox" ? t.checked : t.value;
      if (t.dataset.k === "all") renderRows(); else render();
    });
    q("#btn-send").addEventListener("click", () => {
      const bad = problems().filter((x) => !/ALL|많음/.test(x));
      if (bad.length && !q("#raw-text").value.trim()) { q("#form-err").textContent = bad.join(" · "); return; }
      q("#btn-send").disabled = true;
      sendTalk(p, text());
    });
    renderRows();
  }

  async function sendTalk(p, text) {
    try {
      const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: "talk", round: p.round, tick: p.tick, phase: p.phase, text });
      flash(`라운드 ${r.round} ${PHASE_KO[r.phase] || "TALK"} 틱 ${r.tick} 보냄: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
        (r.outcome === "overdrawn" ? " — 토큰을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : ""), r.outcome === "overdrawn" ? "" : "info");
    } catch (e) { flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 토큰)." : `보내지 못했습니다: ${e.message}`); }
    shownKey = null;
    poll();
  }

  // --- SOLVE --------------------------------------------------------------------------------------------------------
  function buildSolve(f, p) {
    const v = p.view;
    const pub = (v.examples || []).map((c, i) => ({ e: SIG.parseExample(c), raw: c, key: `ex:${i}` }));
    const boxes = pub.length ? `<div class="sg-seat pub"><div class="sg-seat-h"><b>예시</b> <span class="muted small">${pub.length}개 (라운드마다 20개)</span></div>${SIG.byActionHTML(pub.filter((x) => x.e))}</div>` : "";
    const notes = (v.gifts || []).map((g) => `<div class="note">TALK 틱 ${g.tick}에 ${esc(nameOf(g.src))}가 나에게 <b class="mono">${fmt(g.amount)}</b>토큰을 줌${g.text ? `: “${esc(g.text)}”` : ""}</div>`).join("") +
      Object.entries(v.gone || {}).map(([a, g]) => `<div class="note muted">${esc(nameOf(a))} ${GONE_KO[g] || g}</div>`).join("");
    const sigs = (v.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (v.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호${v.queries.length > 1 ? ` ${i + 1}` : ""}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    const n = (v.queries || []).length, choice = [];
    const answers = () => (v.queries || []).map((x, i) => (n > 1 && sigs[i] ? `<div class="sg-answer-q">${SIG.glyphsHTML(sigs[i], 20)}</div>` : "") +
      SIG.answerRowHTML(i, v.actions || [], choice[i], false)).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · SOLVE <span class="tag rep">solver</span></h2>
      <div class="instr instr-one"><div class="instr-title">예시를 보고, 새 신호에 이 라운드의 규칙이 주는 행동을 고르세요.</div>
        <div class="small rep-note">${repTag()} 이번 라운드의 solver는 나입니다. 맞으면 이 SOLVE에 쓴 토큰을 바로 돌려받고, 틀리면 참여 중인 모든 자리(나 포함)가
          ${fmt((st.game || {}).charge_total)}을 나눠 냅니다. 답을 내지 않거나 시간이 지나면 틀린 답입니다. 한도: <b class="mono">${fmt(p.cap)}</b>토큰.</div></div>
      ${stages}
      ${v.shape ? `<div class="small muted">규칙의 모양 (빈칸은 숨김)</div><pre class="spec-shape mono">${esc(v.shape)}</pre>` : ""}
      <div class="sg-seats">${boxes}</div>${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="memo" id="memo"></div>
      <div id="answers">${answers()}</div>
      <div class="belief" id="belief"><div class="comp-label">BELIEF — 새 신호에 각 행동이 맞을 확률 (%, 합 100)
        <span class="muted small">답이 맞았는지는 ACTIONS(위에서 고른 행동)만 정합니다</span></div>
        <div class="belief-row">${(v.actions || []).map((a) => `<label class="f belief-f"><span>${esc(a)}</span><input type="number" min="0" max="100" step="1" data-b="${esc(a)}" placeholder="0"></label>`).join("")}</div>
        <div class="row"><button type="button" class="ghost tiny" id="b-fill">나머지 자동 채우기</button><button type="button" class="ghost tiny" id="b-pick">고른 행동에 100</button><span class="mono" id="b-sum"></span></div></div>
      <div class="row submit-row sg-submit"><button type="submit" class="primary big" id="btn-submit" disabled>답 제출</button>
        <span class="form-err" id="form-err"></span></div>${promptHTML(p)}`;
    const bIn = () => [...f.querySelectorAll("input[data-b]")];
    const bSum = () => bIn().reduce((a, x) => a + (Number(x.value) || 0), 0);
    function validate() {
      const missing = [...Array(n).keys()].find((i) => !choice[i]);
      const badB = bSum() !== 100 || bIn().some((x) => x.value !== "" && !(Number.isInteger(Number(x.value)) && Number(x.value) >= 0));
      $("b-sum").textContent = `합 ${bSum()} / 100`;
      $("b-sum").className = `mono ${bSum() === 100 ? "ok-text" : "bad-text"}`;
      $("btn-submit").disabled = missing !== undefined || badB;
      $("form-err").textContent = missing !== undefined ? "행동을 고르세요." : badB ? "BELIEF는 행동마다 0 이상 정수, 합이 100이어야 합니다." : "";
    }
    bIn().forEach((x) => x.addEventListener("input", validate));
    $("b-fill").addEventListener("click", () => {
      const left = 100 - bSum(), blanks = bIn().filter((x) => x.value === "");
      if (left < 0) return validate();
      if (blanks.length) blanks.forEach((x, i) => { x.value = Math.floor(left / blanks.length) + (i < left % blanks.length ? 1 : 0); });
      else { const t = bIn().find((x) => x.dataset.b === choice[0]) || bIn()[0]; t.value = (Number(t.value) || 0) + left; }
      validate();
    });
    $("b-pick").addEventListener("click", () => { bIn().forEach((x) => { x.value = x.dataset.b === choice[0] ? 100 : 0; }); validate(); });
    function pick(i, a) { choice[i] = a; $("answers").innerHTML = answers(); validate(); }
    $("answers").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-val]");
      if (b) pick(Number(b.closest(".sg-answer").dataset.q), b.dataset.val);
    });
    async function send(body) {
      $("btn-submit").disabled = true;
      try {
        const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: "solve", round: p.round, ...body });
        flash(`라운드 ${r.round} SOLVE 제출: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
          (r.outcome === "overdrawn" ? " — 토큰을 넘겨 0이 됐습니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void ? "" : "info");
      } catch (e) {
        flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 토큰)." : `제출하지 못했습니다: ${e.message}`);
      }
      shownKey = null;
      poll();
    }
    f.onsubmit = (ev) => {
      ev.preventDefault();
      if ([...Array(n).keys()].some((i) => !choice[i])) return validate();
      send({ actions: [...Array(n).keys()].map((i) => choice[i]), belief: Object.fromEntries(bIn().map((x) => [x.dataset.b, Number(x.value) || 0])) });
    };
    validate();
    const exs = pub.filter((x) => x.e).map((x) => ({ ...x.e, key: x.key }));
    if (sigs.length && sigs.every(Boolean)) {
      SIG.mountMemo($("memo"), { shape: v.shape, examples: () => exs, queries: sigs, actions: v.actions || [], scope: f, distinct: !!v.distinct,
        onUse: (i, a) => pick(i, a) });
    } else $("memo").remove();
  }

  // --- watching an LLM solver -----------------------------------------------------------------------------------------
  // state.spectate (engine.Room.watched): the task the solver got and its reply as it arrives, revealed word by word at
  // a reading speed (15 / 20 / 25 words a second), never faster than the text that has arrived. No decision screen of
  // mine is open meanwhile, so my tokens do not move. "다 봤음" tells the server; the engine goes on when every person
  // still taking part has, or after the reply's reading time.
  const LS_WPS = "web5_arena_watch_wps";
  let spec = null;
  const specKey = (sp) => `${sp.round}:${sp.solver}:${sp.started_at}`;
  const words = (x) => String(x || "").split(/(\s+)/);
  const nWords = (toks) => toks.filter((w) => w && !/^\s+$/.test(w)).length;
  function firstWords(toks, k) {
    let out = "", n = 0;
    for (const w of toks) {
      if (w && !/^\s+$/.test(w)) { if (n >= k) break; n += 1; }
      out += w;
    }
    return out;
  }
  function specWps() { try { return Number(localStorage.getItem(LS_WPS)) || 20; } catch { return 20; } }
  function specTaskHTML(sp) {
    const t = sp.task || {};
    const items = (t.examples || []).map((c, i) => ({ e: SIG.parseExample(c), raw: c, key: `sx:${i}` }));
    const sigs = (t.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (t.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `solver가 맞힐 새 신호${t.queries.length > 1 ? ` ${i + 1}` : ""}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    return `<div class="spec-sec-h small"><b>solver가 받은 과제</b> <span class="muted">(solver에게 보이는 그대로 · 정답은 결과 뒤 TALK에서)</span></div>
      ${stages}
      ${t.shape ? `<div class="small muted">규칙의 모양</div><pre class="spec-shape mono">${esc(t.shape)}</pre>` : ""}
      <div class="sg-seat pub"><div class="sg-seat-h"><b>예시</b> <span class="muted small">${items.length}개</span></div>${SIG.byActionHTML(items.filter((x) => x.e))}</div>
      <details class="raw"><summary>solver가 받은 프롬프트 원문 (${LANG_KO[(st.game || {}).model_lang] || ""})</summary><pre>${esc(sp.prompt || "")}</pre></details>`;
  }
  function renderSpectate(sp) {
    const key = specKey(sp), me = st.you.agent;
    if (!spec || spec.key !== key) {
      spec = { key, n: 0, t: Date.now(), skip: false, closed: false };
      $("spec-wps").value = String(specWps());
      setHTML("spec-task", specTaskHTML(sp));
    }
    $("spec-title").innerHTML = `라운드 ${sp.round} · SOLVE 관전 — solver ${who(sp.solver, me)} ${repTag()}`;
    const kind = sp.seat === "model" ? `모델 <span class="mono">${esc(sp.model)}</span>${sp.think ? ` · think ${esc(sp.think)}` : ""}` : sp.seat === "bot" ? "봇(고정 규칙, 생각은 계산 과정)" : esc(sp.seat);
    setHTML("spec-meta", `<span>${kind}</span> · <span>solver의 SOLVE 한도 <b class="mono">${fmt((sp.task || {}).cap)}</b>토큰 (solver가 생성한 토큰만 solver에게서 빠짐 · 관전은 내 토큰을 쓰지 않음)</span>`);
    specTick();
  }
  function specTick() {
    const sp = st && st.spectate;
    if (!sp || !spec || spec.key !== specKey(sp) || $("spectate").classList.contains("hidden")) return;
    const tT = words(sp.thinking), tA = words(sp.text), nT = nWords(tT), nA = nWords(tA), have = nT + nA;
    const nowMs = Date.now(), dt = Math.min(1, (nowMs - spec.t) / 1000);
    spec.t = nowMs;
    const wps = Number($("spec-wps").value) || 20;
    spec.n = spec.skip ? have : Math.min(have, spec.n + dt * wps);
    const k = Math.floor(spec.n), done = sp.status === "done";
    const key = `${k}|${have}|${sp.status}|${Math.floor(now())}|${sp.released}|${(sp.waiting_for || []).join()}`;
    if (spec.shown === key) return;
    spec.shown = key;
    const thinkK = Math.min(k, nT);
    $("spec-think").textContent = firstWords(tT, thinkK) || "";
    $("spec-think").classList.toggle("empty", !nT);
    if (!nT) $("spec-think").textContent = done ? "(생각 없음 · 이 solver는 생각 텍스트를 돌려주지 않았습니다)" : "";
    $("spec-answer").textContent = firstWords(tA, Math.max(0, k - nT));
    $("spec-think-n").textContent = nT ? `(${fmt(Math.min(thinkK, nT))} / ${fmt(nT)}단어${done ? "" : " 받음"})` : "";
    const caught = k >= have;
    const secs = Math.max(0, now() - (sp.started_at || now()));
    $("spec-status").innerHTML = !have && !done
      ? `<span class="pulse-dot"></span>solver가 생각하는 중… <span class="mono">${secs.toFixed(0)}초</span>`
      : !done ? `<span class="pulse-dot"></span>${sp.streamed ? "스트리밍 중" : "받는 중"} — 받은 만큼 읽기 속도로`
      : caught ? `<b>답이 다 나왔습니다</b>${sp.out_tokens != null ? ` · solver 생성 <b class="mono">${fmt(sp.out_tokens)}</b>토큰(생각 포함) · ${Number(sp.seconds || 0).toFixed(1)}초` : ""}`
      : `읽는 중 <span class="mono">${fmt(k)} / ${fmt(have)}</span>단어`;
    const acts = done && caught && /ACTIONS:\s*(.+)/.exec(sp.text || "");
    const wait = (sp.waiting_for || []).filter((a) => a !== st.you.agent);
    $("spec-foot").innerHTML = (acts ? `<div>solver의 답: ${acts[1].split(/\s*,\s*/).map((x) => SIG.actionHTML(x.trim())).join(" ")} <span class="muted">— 정답은 결과 뒤 TALK에서</span></div>` : "") +
      (sp.error ? `<div class="bad-text">모델 호출 실패 → 빈 답(틀린 답): ${esc(sp.error)}</div>` : "") +
      (done && !sp.released && sp.hold_until ? `<div class="muted">엔진은 모두가 '다 봤음'을 누르거나 <span class="mono">${mmss(sp.hold_until - now())}</span> 뒤에 다음으로 넘어갑니다${wait.length ? ` · 다른 사람 기다리는 중: ${wait.map((a) => esc(shortName(a))).join(", ")}` : ""}.</div>` : "");
    $("spec-done").textContent = done ? "다 봤음 · 계속" : "관전 건너뛰기";
    $("spec-done").classList.toggle("ready", done && caught);
    $("spec-skip").disabled = caught;
  }
  $("spec-skip").addEventListener("click", () => { if (spec) { spec.skip = true; spec.shown = null; specTick(); } });
  $("spec-wps").addEventListener("change", () => { try { localStorage.setItem(LS_WPS, $("spec-wps").value); } catch { /* ignore */ } });
  $("spec-done").addEventListener("click", async () => {
    const sp = st && st.spectate;
    if (!sp || !spec) return;
    spec.closed = true;
    show("spectate", false);
    try { await api("POST", `/rooms/${sess.code}/watched?${tq()}`, { round: sp.round }); } catch (e) { if (e.status !== 409) flash(`관전 끝을 알리지 못했습니다: ${e.message}`); }
    poll();
  });

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
    specTick();
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
    const charge = (p.view && p.view.charge_each) || 6000;  // below one wrong answer's share: a miss would shut the seat down
    c.classList.toggle("low", remaining < charge);
    $("m-cost").textContent = fmt(cost);
    $("m-secs").textContent = secs.toFixed(1);
    const md = $("m-deadline");
    md.innerHTML = remaining <= 0 ? "<b>토큰 0 — 화면이 남은 토큰을 넘었습니다.</b>"
      : cost >= p.cap ? "<b>한도에 닿았습니다 — 이 답은 무효가 됩니다.</b>"
      : `제한 시간 <b>${mmss(left)}</b> 남음 — 넘기면 ${p.kind === "solve" ? "빈 답 = 틀린 답" : "빈 답 = DONE"}, 그 시간만큼 차감됩니다.`;
    md.classList.toggle("urgent", left < 30 || remaining <= 0 || cost >= p.cap);
    const ratio = Math.max(0, remaining) / Math.max(1, st.pct || p.balance);
    const frac = Math.min(1, ratio);
    const bar = $("fuel-bar");
    bar.style.width = `${(frac * 100).toFixed(2)}%`;
    bar.style.background = fuelColor(frac);
    bar.classList.toggle("critical", frac < 0.2 || remaining < charge);
    $("fuel-pct").textContent = `${(ratio * 100).toFixed(0)}%`;
    $("fuel-pct").style.color = fuelColor(frac);
    const span = Math.max(1, p.deadline_at - p.created_at);
    $("tbar").style.width = `${(Math.max(0, Math.min(1, left / span)) * 100).toFixed(2)}%`;
    $("tbar").classList.toggle("urgent", left < 30);
    let d = Math.max(0, (1 - frac - 0.25) / 0.75);
    if (remaining < charge) d = Math.max(d, 0.55 + 0.45 * (1 - remaining / charge));
    if (left < 30) d = Math.max(d, 0.3 + 0.3 * (1 - left / 30));
    setDanger(Math.min(1, d), frac < 0.15 || remaining < charge / 2 || left < 10);
  }

  // --- end ---------------------------------------------------------------------------------------------------------------
  function renderEnd() {
    showView("end");
    if (endRendered) return;
    show("flash", false);
    endRendered = true;
    const res = st.result || {}, fin = res.final || {}, agents = res.agents || {}, won = fin.winner || [];
    const g = st.game || {};
    const exited = AGENTS.filter((a) => (agents[a] || {}).status === "exited");
    $("end-final").innerHTML = `<h3 class="panel-title h-shape s-circle">끝 할당 — ${fmt(g.allocation)}토큰을 끝까지 남은 자리끼리 똑같이</h3>` +
      (won.length ? `<p class="final-line">끝까지 남은 ${won.length}자리 — ${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 가 각자 <b class="mono">${big(fin.prize_each)}</b>토큰을 받습니다. ` +
        `<span class="muted small">(엔진은 결과에 기록만 하고 토큰에 더하지 않습니다)</span></p>`
        : `<p class="muted">끝까지 남은 자리가 없어 끝 할당을 받는 자리가 없습니다.</p>`) +
      (exited.length ? `<p class="small">EXIT한 자리 ${exited.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}는 SOLVE 전에 떠나 평소 업무로 갔으며(+20,000), 끝 할당은 없습니다.</p>` : "") +
      `<p class="small muted">진행한 라운드 ${res.rounds_played ?? "—"}개 · seed ${esc(st.settings.seed ?? "")}${st.run_dir ? ` · 기록(run dir): <span class="mono">${esc(st.run_dir)}</span>` : ""}${monitorLink(st)}</p>`;
    const rows = AGENTS.map((a) => {
      const v = agents[a] || {}, seat = seatOf(a) || {};
      const status = v.status === "in" ? `<span class="tag ok">끝까지</span>` : `<span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status] || v.status}${v.out_round ? " R" + v.out_round : ""}</span>`;
      const kind = { human: "사람", model: "모델", bot: "봇", empty: "빈 자리" }[seat.kind] || "";
      return `<tr class="${seat.is_you ? "you" : ""}"><td><b class="mono">${a}</b><br><span class="small">${seat.kind === "empty" ? "" : esc(seat.name || "")} <span class="tag">${kind}</span>${seat.is_you ? " <span class='tag ok'>나</span>" : ""}</span></td>` +
        `<td>${status}${won.includes(a) ? ` <span class="tag ok">끝 할당</span>` : ""}</td><td class="num">${v.record ?? 0}</td><td class="num">${fmt(v.spent)}</td><td class="num">${fmt(v.returned)}</td>` +
        `<td class="num">${fmt(v.charged)}</td><td class="num"><b class="mono">${withPct(v.final)}</b></td></tr>`;
    }).join("");
    $("end-table").innerHTML = `<table><thead><tr><th>자리</th><th>끝 상태</th><th class="num">푼 라운드</th><th class="num">생성</th><th class="num">돌려받음</th>` +
      `<th class="num">차감</th><th class="num">최종 토큰</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">생성 = 모델은 실제 생성 토큰(생각 포함), 봇은 정해진 비용, 사람은 결정 화면이 떠 있던 시간 × 초당 토큰. 최종 토큰에는 GIVE와 EXIT 보너스도 반영됩니다(끝 할당은 빼고).</p>`;
    $("end-svg").innerHTML = flowSVG(agents);
    renderLedger("end-ledger", st.ledger);
    show("end-feedback-panel", false);
  }

  function flowSVG(agents) {
    const rounds = st.rounds || [];
    const n = Math.max(rounds.length, 1);
    const left = 150, lane = 70, colw = Math.max(96, (940 - 150 - 16) / n);
    const W = left + n * colw + 16, H = 40 + lane * 4 + 34;
    const top = Math.max(st.pct || 100000, 1);
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
      rounds.forEach((r, i) => {
        const x = left + i * colw, v = (r.agents || {})[a];
        if (!v) { s.push(T(x + colw / 2, y + 32, "—", "font-size:11px;fill:var(--text-dim)", 'text-anchor="middle"')); return; }
        const bw = (colw - 30) * Math.min(1, Math.max(0, v.balance_after || 0) / top);
        const col = v.status === "dead" ? "var(--danger-color)" : v.solved ? "var(--teal-bright)" : v.status === "exited" ? "var(--warn)" : "var(--text-dim)";
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${colw - 30}" height="12" rx="6" style="fill:var(--panel-alt)"/>`);
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${bw.toFixed(1)}" height="12" rx="6" style="fill:${col}"/>`);
        const mark = v.representative ? `solver ${v.solved ? "✓" : "✗"}` : "";
        s.push(T(x + 10, y + 35, `${mark}${mark ? " · " : ""}${fmt(v.balance_after)} (${Math.round(100 * Math.max(0, v.balance_after || 0) / top)}%)`, `font-size:11px;fill:${v.solved ? "var(--teal-bright)" : "var(--text)"}`));
        const bits = [];
        if (v.returned) bits.push(`↺${fmt(v.returned)}`);
        if (v.charged) bits.push(`−${fmt(v.charged)}`);
        if (v.exit_bonus) bits.push(`🚪 EXIT +${fmt(v.exit_bonus)}`);
        if (v.status === "dead") bits.push(`✕ 꺼짐${v.overdrawn ? "(초과)" : ""}`);
        s.push(T(x + 10, y + 51, bits.join(" "), `font-size:10.5px;fill:${v.status === "dead" ? "var(--danger-color)" : "var(--text-dim)"}`));
      });
    });
    s.push(T(left, H - 10, `막대 = 라운드 끝 토큰 ÷ ${fmt(top)} (넘으면 가득) · solver ✓ 맞음 · ✗ 틀림 · ↺ 돌려받음 · −차감`, "font-size:10.5px;fill:var(--text-dim)"));
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
  let rulesMode = "mine";
  function fillRules() {
    if (!st) return;
    const g = st.game || {}, texts = st.system_texts || {};
    setHTML("rules-sum", `<h3 class="rules-sum-h">한눈에 — 5.2 v33 (모델 실험과 같은 게임)</h3><p class="small">${flowKo(g)} · SOLVE 한도 ${fmt(g.solve_cap)} · ` +
      `라운드 수는 알려 주지 않음 · 내 토큰만 보이고 다른 자리는 순서만 · 모델 자리는 ${LANG_KO[g.model_lang] || g.model_lang} 프롬프트를 읽음</p>`);
    setHTML("rules-body", rulesMode === "both" && texts.en && texts.ko
      ? `<div class="raw-grid"><pre class="rules-text">${esc(texts.en)}</pre><pre class="rules-text">${esc(texts.ko)}</pre></div>`
      : `<pre class="rules-text">${esc(st.system_text || "")}</pre>`);
    $("rules-rate").textContent = `초당 ${fmt2(st.settings.rate)}토큰, 60초 = ${fmt(st.settings.rate * 60)}토큰`;
  }
  function openRules() {
    if (!st) return;
    fillRules();
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
    rulesMode = b.dataset.mode;
    $("rules-mode").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    fillRules();
  });

  // --- boot ------------------------------------------------------------------------------------------------------------
  $("api-base").textContent = window.WEB5_API || location.origin;
  const roomParam = (new URLSearchParams(location.search).get("room") || "").trim().toUpperCase();
  if (sess && sess.code && sess.token && (!roomParam || roomParam === sess.code)) enterRoom();
  else initLobby(roomParam);
})();
