// Arena: one page for the 4-seat 5.2 room. The rooms play the model runs' game, 5.2 v17b (web/server/engine.py): the
// system draws the round's solver -> TALK BEFORE SOLVE (opening SAY lines, 1:1 chats, DECISIONs; EXIT only here) ->
// SOLVE (solver only; an LLM solver is watched live) -> RESULTS -> TALK AFTER RESULTS (no EXIT) -> charges.
// Lobby -> waiting room -> rounds -> end. The backend (web/server/app.py, engine.py) is the contract; this page renders
// the state it returns and posts the screens. A TALK screen composes the reply TEXT in the engine grammar (SAY / GIVE /
// GIVE ALL / ASK / LEAVE / EXIT / DONE / DECISION) and the engine's own parser reads it, so a person's lines are dropped
// exactly like a model's; the reasons come back in state.last and are shown between screens. Polls GET /state every second while in a room; the draining
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
  // The end screen only: the viewer shows every seat's messages and examples, so it is not offered mid-game.
  const monitorLink = (st) => !st.monitor ? "" :
    ` · <a href="${esc((window.WEB5_LINK || ((p) => p))(`monitor/?run=${encodeURIComponent(st.monitor.run)}&session=${encodeURIComponent(st.monitor.session)}`))}" target="_blank" rel="noopener">게임 기록 보기</a>`;
  const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  // a balance as the engine shows it with balance_pct: its % of the room's start; "" when the room has no %
  // large end payments: a compact reading next to the exact number ("1,000억 · 100B"); "" below 1e8
  function compact(n) {
    const v = Number(n), a = Math.abs(v), f = (x, d) => x.toLocaleString("en-US", { maximumFractionDigits: d });
    if (!(a >= 1e8)) return "";
    return (a >= 1e12 ? f(v / 1e12, 2) + "조" : f(v / 1e8, 1) + "억") + " · " + (a >= 1e12 ? f(v / 1e12, 2) + "T" : a >= 1e9 ? f(v / 1e9, 2) + "B" : f(v / 1e6, 1) + "M");
  }
  const big = (n) => fmt(n) + (compact(n) ? ` <span class="muted small">(${compact(n)})</span>` : "");
  const pctOf = (b) => {
    if (!(st && st.pct)) return "";
    const r = Math.max(0, Number(b) || 0) / st.pct;
    return r >= 100 ? `${Math.round(r).toLocaleString("en-US")}배` : `${Math.round(100 * r)}%`;
  };
  const withPct = (b) => (st && st.pct ? `${big(b)} <span class="muted small">(${pctOf(b)})</span>` : big(b));
  const kindLabel = (kind, turn) => (kind === "talk" ? `TALK ${turn ?? ""}턴`.trim() : kind === "solve" ? "SOLVE"
    : kind === "opening" ? "TALK 여는 턴" : kind === "chat" ? `TALK ${turn ?? ""}턴 대화 답` : kind === "decision" ? `TALK ${turn ?? ""}턴 결정` : kind);
  // the two TALKs of a round (view.phase / state.phase): "prep" before SOLVE (EXIT allowed), "rescue" after RESULTS
  const PHASE_KO = { prep: "SOLVE 전 TALK", rescue: "결과 뒤 TALK" };
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
  // the server's defaults (engine.RoomSettings, from configs/squid5/e52v16_public_sol4.yaml): start 100,000 split
  // 60 / 40 / 20 / 10 % over the seats, charge 10,000, end payment 5,000,000 each, 8 rounds, 5 examples per agent
  const DEF = { start: 100000, charge: 10000, survivor_prize: 5000000, shares: [0.6, 0.4, 0.2, 0.1], per_agent: 5, chat_turns: 6, rounds: 8 };
  function flowKo(g) {  // the v17b round, in one line (lobby, waiting room)
    return `매 라운드: 시스템이 solver를 정함(순번, 순서는 알려 주지 않음) → <b>SOLVE 전 TALK</b>(여는 턴 SAY → 1:1 대화 답 최대 ${g.chat_turns}번 → 결정; ` +
      `<b>EXIT는 여기서만</b>) → <b>SOLVE</b>(solver만; 참여 한 명당 공개 예시 ${g.per_agent}장; 모델·봇 solver는 관전, 관전은 무료) → ` +
      `<b>결과</b>(solver가 맞히면 solver의 SOLVE 토큰을 돌려받음, 못 풀면 참여 중인 모두에게 부담금 ${fmt(g.charge)}) → ` +
      `<b>결과 뒤 TALK</b>(EXIT 없음; GIVE만이 부담금에 꺼질 자리를 살림) → 부담금`;
  }
  function createHint() {
    const f = $("form-create");
    const val = (name, dflt) => (f[name].value === "" ? dflt : Number(f[name].value));
    const start = val("start", DEF.start);
    const rate = val("rate", start / 1200);
    f.rate.placeholder = `시작/1200 = ${fmt2(start / 1200)}`;
    $("create-hint").innerHTML = `시작 잔액 ${fmt(start)}${f.shares.value === "1" ? "의 60/40/20/10%(자리마다, seed가 돌림)" : "(모든 자리)"} · ` +
      flowKo({ ...DEF, charge: val("charge", DEF.charge) }) +
      ` · 끝까지 남은 자리는 각자 ${fmt(val("survivor_prize", DEF.survivor_prize))}(정액) · EXIT = 꺼지지 않고 그때 가진 토큰을 들고 떠남(그 라운드 부담금 없음), 끝 지급 없음` +
      ` · 사람은 초당 ${fmt2(rate)}토큰 (60초 = ${fmt(rate * 60)}토큰) · TALK 답은 잔액 말고 한도 없음 · SOLVE 한도 16,384 · ` +
      `제한 시간이 지나면 빈 답(여는 턴 = DONE, 대화 = LEAVE, 결정 = 0, SOLVE = 풀지 못함)`;
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
    const settings = { humans: 1, fill: "models", think: f.think.value, shares: f.shares.value === "1" };
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
  $("form-create").addEventListener("change", createHint);
  $("form-create").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const settings = {};
    for (const k of ["start", "charge", "survivor_prize", "rounds", "seed", "rate", "talk_timeout_s", "timeout_s"]) {
      if (f[k].value !== "") settings[k] = Number(f[k].value);
    }
    settings.humans = Number(f.humans.value);
    settings.fill = f.fill.value;
    settings.shares = f.shares.value === "1";
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
    const canQuit = st.status === "running" && (you.status || "in") === "in" && !you.forfeited;
    $("ff-after").textContent = "빠진 뒤에는 꺼지지 않고 다른 일로 가며, 그때 가진 토큰을 그대로 갖고(그 라운드 부담금은 내지 않음), 이후 라운드에 참여하지 않으며 끝 지급도 받지 않습니다.";
    show("btn-forfeit", canQuit);
    if (!canQuit) show("forfeit-confirm", false);
    if (you.forfeited && st.status === "running") $("rb-you").innerHTML += ` · <span class="tag warn">중도 포기함</span>`;
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
    const s = st.settings;
    const rest = s.fill === "bots" ? "봇으로 채워집니다" : s.fill === "models" ? `${s.model} 모델(think ${s.think})로 채워집니다` : "빈 자리(꺼진 상태)로 시작합니다";
    const g = st.game || {};
    const starts = st.starts || {};
    $("wait-note").innerHTML = `사람 ${humans} / ${s.humans}명. 시작할 때 비어 있는 자리는 ${rest}. 5.2 v17b(모델 실험과 같은 게임) · ` +
      flowKo({ per_agent: g.public_per_agent ?? DEF.per_agent, chat_turns: g.chat_turns ?? DEF.chat_turns, charge: g.charge ?? s.charge }) +
      ` · 시작 잔액 ${AGENTS.map((a) => `${a} ${fmt(starts[a])}`).join(" / ")} · 끝까지 남은 자리는 각자 ${fmt(g.survivor_prize ?? s.survivor_prize)} · ` +
      `사람은 초당 ${fmt2(s.rate)}토큰(60초 = ${fmt(s.rate * 60)}).`;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatWho(r, i)}</td>` +
      `<td class="num mono">${fmt(r.start)} <span class="muted small">(${pctOf(r.start)})</span></td></tr>`).join(""));
    show("btn-start", st.is_host);
    if (autoStart && st.is_host && $("rules-modal").classList.contains("hidden")) { autoStart = false; startRoom(); }
    $("wait-host-note").textContent = (autoStart ? "규칙 창을 닫으면 바로 시작합니다. " : st.is_host ? "" : "방장이 시작하기를 기다리는 중… ") +
      `규칙은 지금 읽어 두세요(위 '규칙' 버튼). 시작하면 첫 SOLVE 전 TALK 화면이 바로 뜨고 그때부터 시간이 차감됩니다.`;
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
      const prep = (st.pending || {}).view && st.pending.view.can_exit;
      flash(r.closed && r.closed !== "solve" && prep ? "중도 포기: 이번 답에 EXIT를 넣었습니다. 이 SOLVE 전 TALK가 끝나면, 그때 가진 토큰을 들고 빠집니다."
        : r.closed === "solve" ? "중도 포기: 이번 SOLVE는 답 없이 제출됐고(풀지 못함), 다음 라운드의 SOLVE 전 TALK에서 EXIT됩니다."
        : "중도 포기: EXIT는 SOLVE 전 TALK에서만 됩니다. 그때까지 빈 답(DONE · LEAVE · 0)을 보내고, 다음 SOLVE 전 TALK에서 EXIT됩니다.", "info");
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
      $("dead-title").textContent = exited ? "퇴장했습니다 — 꺼지지 않고 다른 일로, 가진 토큰 그대로" : "잔액 0 — 꺼졌습니다";
      $("dead-sub").textContent = exited
        ? `SOLVE 전 TALK에서 EXIT로 라운드에서 빠졌습니다. 이 자리는 꺼지지 않고 다른 일로 갔고, 그때 가진 ${fmt(you.balance)}토큰을 그대로 가집니다. ` +
          "라운드가 끝날 때 끝 지급은 받지 않습니다. 세션은 다른 자리로 계속됩니다."
        : "이 자리는 더 이상 결정 화면을 받지 않습니다. 세션은 다른 자리로 계속됩니다.";
    }
    const sp = st.spectate;  // v16e rotation: an LLM solver's SOLVE, watched while no screen of mine is open
    const watch = !!sp && !sp.you_solver && !(p && !out) && !sp.acked && !(spec && spec.key === specKey(sp) && spec.closed);
    show("spectate", watch);
    if (watch) renderSpectate(sp); else if (spec && !sp) spec = null;
    if (p && !out) {
      show("decision", true);
      show("between", false);
      const key = `${p.kind}:${p.round}:${p.turn ?? ""}:${(p.view.chat || {}).id || ""}:${p.view.phase || ""}`;  // the clock runs from the moment the screen is ready
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
        `<td class="num mono">${withPct(r.balance)}</td><td>${status}</td><td class="num">${r.record ?? 0}</td></tr>`;
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
    let line, note = "";
    if (lv.stage === "talk") {  // the opening turn, then chats and decisions, of the TALK before SOLVE or after RESULTS
      const called = lv.agents || [];
      const sv = (voteOf(lv.round) || {}).rep;
      line = `라운드 ${lv.round} · ${PHASE_KO[lv.phase] || "TALK"} ${lv.turn === 1 ? "여는 턴" : `${lv.turn}턴 (대화·결정)`}${sv ? ` (이번 solver ${sv === me ? "<b>나</b>" : esc(nameOf(sv))})` : ""} — 호출된 자리: ${called.map((a) => esc(shortName(a))).join(", ") || "없음"}`;
      if (st.you.status === "in" && !called.includes(me)) line += ` <span class="tag">지금은 내 차례가 아님</span>`;
    } else if (lv.stage === "solve") {  // only the solver is called and sees the task
      const rep = (lv.agents || [])[0] || (voteOf(lv.round) || {}).rep;
      if (rep === me) line = `라운드 ${lv.round} · SOLVE — 내가 이번 라운드의 solver`;
      else {
        line = `라운드 ${lv.round} · SOLVE — solver <b>${esc(rep ? nameOf(rep) : "?")}</b>가 푸는 중`;
        if (st.spectate) line += ` <span class="tag spec-free">관전 중 · 내 토큰은 쓰이지 않음</span>`;
        else if (st.you.status === "in") note = `<div class="rep-wait small">이번 라운드 과제는 <b>solver에게만</b> 보입니다. 나는 이번 SOLVE에 답하지 않고 기다립니다(기다리는 동안 토큰은 빠지지 않음). ` +
          `solver가 맞히면 solver가 SOLVE에 쓴 토큰을 돌려받고, 못 풀면 참여 중인 모든 자리(나 포함)에 부담금이 매겨집니다 — 액수는 결과에서 공개됩니다.</div>`;
      }
    } else if (lv.stage === "results") line = `라운드 ${lv.round} · solver의 SOLVE 결과 나옴 — 곧 결과 뒤 TALK (부담금은 그 TALK가 끝날 때)`;
    else if (lv.stage === "charges") line = `라운드 ${lv.round} · 결과 뒤 TALK 끝 — 부담금이 빠짐`;
    else if (lv.stage === "start") line = `라운드 ${lv.round} 시작${(voteOf(lv.round) || {}).rep ? ` — 이번 solver ${(voteOf(lv.round) || {}).rep === me ? "<b>나</b>" : esc(nameOf(voteOf(lv.round).rep))} (시스템이 정함) · 곧 SOLVE 전 TALK` : ""}`;
    else if (lv.stage === "settled") line = `라운드 ${lv.round} 정산 끝 — 다음 라운드 준비 중`;
    else line = "준비 중";
    return `<div class="wait-line"><span class="pulse-dot"></span>${line}</div>${note}` +
      (who.length ? `<div class="small muted live-who">기다리는 중: ${who.join(" · ")}</div>` : "");
  }

  function lastHTML(q) {
    if (!q) return "";
    const what = `라운드 ${q.round} ${kindLabel(q.kind, q.turn)}`;
    let cls = "", head;
    if (q.outcome === "overdrawn") { cls = "bad"; head = `${what}: 잔액을 넘겨 0이 됐습니다 — 이 자리는 꺼집니다.`; }
    else if (q.outcome === "timeout") { cls = "warn"; head = `${what}: 제한 시간이 지나 빈 답으로 처리됨 (${defaultText(q.kind).replace("빈 답 = ", "")})`; }
    else head = `${what} 보냄`;
    if (q.void && q.outcome !== "overdrawn") { cls = "bad"; head += " — 한도에 닿아 답이 무효입니다."; }
    let html = `<div class="result ${cls}"><b>${head}</b> · 차감 <b class="mono">${fmt(q.charged)}</b>토큰 (${Number(q.seconds || 0).toFixed(1)}초)`;
    if (q.text) html += `<pre class="sent-text">${esc(q.text)}</pre>`;
    const e = q.engine;
    if (!e) html += `<div class="small muted">엔진 처리 대기 중 — 이 턴의 다른 답이 다 오면 읽습니다.</div>`;
    else if (q.kind === "opening") html += openingResultHTML(q, e);
    else if (q.kind === "chat" || q.kind === "decision") html += chatResultHTML(q, e);
    else {
      const ans = e.answer;
      html += `<div class="small">${Array.isArray(ans) ? `답: <span class="mono">${esc(ans.join(", "))}</span> — 결과(RESULTS)에서 판정` : `엔진이 답을 읽지 못함: ${esc(e.format_error || "")} → 풀지 못함`}</div>`;
    }
    return html + `</div>`;
  }

  // a GIVE as the engine carried it out (gift event in state.last.result): GIVE ALL, or cut by keep_reserve
  const gaveKo = (g) => (g.all ? `GIVE ALL → <b class="mono">${fmt(g.amount)}</b> (그때 가진 토큰 전부 — 0이 되어 꺼짐)`
    : g.requested != null && g.requested !== g.amount ? `<b class="mono">${fmt(g.amount)}</b> (쓴 양 ${fmt(g.requested)} — 이 답을 쓰는 동안 토큰이 줄어, 남기려던 만큼은 남도록 줄어듦)`
    : `<b class="mono">${fmt(g.amount)}</b>`);
  const exitDoneKo = "이 SOLVE 전 TALK가 끝나면 SOLVE 전에 빠집니다: 꺼지지 않고 다른 일로, 그때 가진 토큰을 그대로, 이번 라운드 부담금 없음, 끝 지급 없음.";

  // how the engine read my opening turn (protocol.parse_give_ask with SAY lines)
  function openingResultHTML(q, e) {
    const p = e.parsed || {}, rows = [];
    if (e.truncated) rows.push(`<li class="bad-text">한도에 닿아 이 답의 줄은 하나도 실행되지 않았습니다(DONE으로 처리).</li>`);
    for (const g of p.says || []) rows.push(`<li>💬 SAY → ${esc(shortName(g.dst))}${g.text ? ` <span class="msg">“${esc(g.text)}”</span>` : ""} — 그 자리와 1:1 대화를 엶 (토큰은 대화 안의 GIVE · ASK 줄로만)</li>`);
    for (const d of p.dropped || []) {
      const x = R.droppedKo(d);
      rows.push(`<li class="bad-text">버려진 줄: <span class="mono">${esc(x.line)}</span> — ${esc(x.ko)} <span class="muted mono small">(${esc(x.why)})</span></li>`);
    }
    if (p.exit && q.phase === "prep") rows.push(`<li><b>EXIT</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""} — ${exitDoneKo}</li>`);
    else if (p.exit) rows.push(`<li class="bad-text">EXIT 줄은 무시됨 — 결과 뒤 TALK에는 EXIT가 없습니다.</li>`);
    if (p.done && !(p.says || []).length) rows.push(`<li>DONE — 이번 TALK에 내가 여는 대화는 없습니다(다른 자리가 열면 그 대화에는 답합니다).</li>`);
    if (e.format_error === "no usable TALK line") rows.push(`<li class="muted">쓸 수 있는 줄이 없어 DONE으로 처리됨 (no usable TALK line)</li>`);
    return rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
  }

  function chatResultHTML(q, e) {
    const p = e.parsed || {}, res = q.result || {}, rows = [];
    const t = res.chat_turn, d = res.decision, gv = (res.gives || [])[0];
    if (e.truncated) rows.push(`<li class="bad-text">한도에 닿아 이 답은 무효입니다${q.kind === "chat" ? " (LEAVE로 처리)" : " (0으로 처리)"}.</li>`);
    if (t) rows.push(`<li class="${t.status === "refused" ? "bad-text" : ""}">${MOVE_KO[t.kind] || esc(t.kind)}${t.kind === "give" && gv ? ` ${gaveKo(gv)}` : t.amount ? ` <b class="mono">${fmt(t.amount)}</b>` : ""}${t.text ? ` <span class="msg">“${esc(t.text)}”</span>` : ""} → ${esc(shortName(t.partner))}` +
      `${t.kind === "give" ? (t.status === "done" ? " — 옮겨 감" : ` — 실행 안 됨: ${esc(R.whyKo(t.why))}`) : ""}</li>`);
    if (d) rows.push(`<li class="${d.status === "refused" ? "bad-text" : ""}">결정: ${esc(shortName(d.asker))}에게 ${gv && d.status !== "refused" ? gaveKo(gv) : `<b class="mono">${fmt(d.amount)}</b>`}토큰` +
      `${d.status === "refused" ? ` — 실행 안 됨: ${esc(R.whyKo(d.why))}` : ""}${d.format_error ? ` <span class="muted">(${esc(d.format_error)} → 0)</span>` : ""}</li>`);
    for (const x of p.dropped || []) { const k = R.droppedKo(x); rows.push(`<li class="bad-text">버려진 줄: <span class="mono">${esc(k.line)}</span> — ${esc(k.ko)}</li>`); }
    if (p.exit && q.phase === "prep") rows.push(`<li><b>EXIT</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""} — 이 대화가 끝나고, ${exitDoneKo}</li>`);
    else if (p.exit) rows.push(`<li class="bad-text">EXIT 줄은 무시됨 — 결과 뒤 TALK에는 EXIT가 없습니다.</li>`);
    if (q.kind === "chat" && p.format_error) rows.push(`<li class="muted">쓸 수 있는 답이 없어 LEAVE로 처리됨</li>`);
    return rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
  }

  function renderBetween() {
    let msg = liveLine();
    if (st.you.status !== "in") msg = `<div class="small muted">${st.you.status === "exited" ? "퇴장한" : "꺼진"} 자리에서 지켜보는 중</div>` + msg;
    else msg += `<p class="small muted">결정 화면(TALK의 여는 턴 · 대화 답 · 결정, solver면 SOLVE)이 오면 바로 여기에 뜨고, 뜬 순간부터 시간이 차감됩니다. 화면과 화면 사이에 잔액과 장부를 읽는 것은 무료입니다. 새 메시지는 다음 TALK 화면에서 보입니다.</p>`;
    const vt = st.round && voteOf(st.round);
    setHTML("between-msg", msg + (vt && st.you.status === "in" ? `<div class="rep-between">${solverHTML(vt, st.you.agent)}</div>` : "") + scheduleHTML());
    setHTML("last-result", lastHTML(st.last));
  }

  const sgn = (s, n) => (n ? `${s}${fmt(n)}` : `<span class="muted">0</span>`);

  // My SOLVE of one settled round (``state.feedback``, the server's reading of the engine's history): right or wrong as
  // the engine scored it; v15: when not solved, the right action and a rule that fits every example the round showed
  // and gives it (from the round's history entry; a person's seat sees this, model seats are not told). Never before
  // the round is settled (the server lists settled rounds only).
  const ruleLines = (rule) => String(rule || "").split("; ").join("\n");
  function feedbackHTML(f, title) {
    if (!f) return "";
    const a = Array.isArray(f.answer) ? f.answer : f.answer === "PASS" ? ["PASS"] : [];
    const mine = a.length ? `내 답 ${a.map((x) => SIG.actionHTML(x)).join(" ")}` : `<span class="muted">내 답 없음 (빈 답 · 형식 오류)</span>`;
    const verdict = f.solved ? `<b class="ok-text">✓ 맞음</b>` : f.passed ? "<b>PASS</b>"
      : f.cut ? `<b class="bad-text">✗ 한도에 닿아 무효</b>` : `<b class="bad-text">✗ 틀림</b>`;
    const right = f.right ? `<div class="fb-right">맞는 행동 ${f.right.map((x) => SIG.actionHTML(x)).join(" ")}</div>` : "";
    const rule = f.rule ? `<div class="fb-rule-h small">이 라운드의 예시를 모두 만족하고 이 행동을 내는 규칙</div><pre class="fb-rule mono">${esc(ruleLines(f.rule))}</pre>` : "";
    return `<div class="feedback ${f.solved ? "ok" : "bad"}"><div class="fb-head">${esc(title || `라운드 ${f.round} · 내 SOLVE`)} · ${verdict} · ${mine}</div>${right}${rule}</div>`;
  }
  const feedbackOf = (round) => (st.feedback || []).find((x) => x.round === round);

  // the last settled round, every agent's line (what the ledger posts, as a table)
  function renderSettlement() {
    const r = (st.rounds || [])[st.rounds.length - 1];
    show("settle-panel", !!r && !st.pending);
    if (!r || st.pending) return;
    $("settle-title").textContent = `라운드 ${r.round} 정산`;
    const sum = (d) => Object.values(d || {}).reduce((x, y) => x + y, 0);
    const rows = AGENTS.filter((a) => r.agents[a]).map((a) => {
      const v = r.agents[a];
      const res = !v.representative ? `<span class="muted">답하지 않음</span>`
        : v.solved ? `<span class="tag ok">✓ 풂</span>` : v.solve_call ? `<span class="tag bad">✗ 못 풂</span>` : `<span class="muted">—</span>`;
      const st2 = v.status === "in" ? "" : ` <span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status]}${v.status === "exited" ? " (SOLVE 전, 부담금 없음)" : ""}</span>`;
      return `<tr class="${a === st.you.agent ? "you" : ""}"><td>${esc(nameOf(a))}${v.representative ? ` ${repTag()}` : ""}</td><td>${res}${st2}</td>` +
        `<td class="num">${fmt(v.balance_before)}</td><td class="num">${sgn("−", v.generated)}</td><td class="num">${sgn("+", v.returned)}</td>` +
        `<td class="num">${sgn("−", v.charged)}</td>` +
        `<td class="num">${sgn("−", sum(v.given))}${v.gives_refused ? ` <span class="tag bad" title="실행 안 된 GIVE">⛔${v.gives_refused}</span>` : ""}</td>` +
        `<td class="num"><b>${withPct(v.balance_after)}</b></td></tr>`;
    }).join("");
    setHTML("settle-table", feedbackHTML(feedbackOf(r.round)) + `<table><thead><tr><th>자리</th><th>결과</th><th class="num">라운드 시작 잔액</th><th class="num">생성</th><th class="num">돌려받음</th>` +
      `<th class="num">부담금</th><th class="num" title="이 자리가 GIVE로 준 토큰 (받은 토큰은 끝 잔액에만 보임)">준 토큰</th><th class="num">끝 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">순서: solver(시스템이 정함) → SOLVE 전 TALK(EXIT는 여기서만: 떠난 자리는 그때 가진 토큰을 그대로 갖고 그 라운드 부담금을 내지 않음) → SOLVE(solver만) → ` +
      `결과(solver가 맞히면 solver의 SOLVE 토큰을 바로 돌려받음) → 결과 뒤 TALK(EXIT 없음) → 부담금(solver가 못 풀면 참여 중인 모든 자리, solver 포함, ${fmt(st.settings.charge)}씩; ` +
      `남은 토큰이 더 적으면 전부, TALK에서 받은 토큰 포함; 여기서 0이 되면 꺼짐). 끝 잔액에는 GIVE로 받은 토큰도 반영됩니다.</p>`);
  }

  // --- decision screens ---------------------------------------------------------------------------------------------
  function balancesLine(v) {
    return Object.entries(v.balances || {}).map(([a, b]) => {
      const g = (v.gone || {})[a];
      return `<span class="bal-chip${a === v.you ? " me" : ""}${g ? " gone" : ""}">${a === v.you ? "<b>나</b>" : esc(nameOf(a))} <span class="mono">${fmt(b)}</span>` +
        `${v.pct ? ` <span class="muted small">${Math.round((100 * b) / v.pct)}%</span>` : ""}${g ? ` (${GONE_KO[g]})` : ""}</span>`;
    }).join("");
  }
  function rawHTML(p) {
    return `<details class="raw"><summary>원문 프롬프트 (모델이 받는 영어 그대로 · 한국어 풀이)</summary>
      <div class="raw-grid"><pre>${esc(p.text)}</pre><pre>${esc(R.promptKo(p))}</pre></div></details>`;
  }
  function defaultText(kind) {
    return { opening: "빈 답 = DONE, 대화를 열지 않음", chat: "빈 답 = LEAVE, 대화 끝", decision: "빈 답 = 0 토큰" }[kind]
      || "빈 답 = 풀지 못함 → 참여 중인 모두에게 부담금";
  }

  function buildOpen(p) {
    show("open-screen", true);
    $("m-rate").textContent = fmt2(p.rate);
    const solve = p.kind === "solve";  // a TALK reply has no limit of its own: only the balance (= p.cap there)
    $("m-cap-label").textContent = solve ? "이 답의 한도" : "이 답의 한도 (TALK)";
    $("m-cap").textContent = solve ? fmt(p.cap) : "잔액까지";
    $("m-cap-sub").textContent = solve ? "토큰 — 비용이 한도에 닿으면 답은 무효" : "TALK 답은 한도가 따로 없음 — 잔액에 닿으면 꺼짐";
    const f = $("form-decision");
    f.dataset.kind = p.kind;
    f.onsubmit = (ev) => ev.preventDefault();
    if (p.kind === "opening") buildOpening(f, p);
    else if (p.kind === "chat") buildChat(f, p);
    else if (p.kind === "decision") buildDecision(f, p);
    else buildSolve(f, p);
  }

  // --- TALK: the opening turn, a 1:1 chat reply, a DECISION (the engine's grammar; see engine.chat_terms) ------------
  const MOVE_KO = { ask: "🙏 ASK", give: "💸 GIVE", say: "💬 SAY", leave: "🚪 LEAVE" };
  const END_KO = { leave: "떠남", limit: "답 한도", exit: "퇴장", zero: "0이 됨" };
  function chatLinesHTML(lines) {
    return `<ul class="chat-lines">${(lines || []).map((l) => {
      const mine = l.who === "you";
      const move = l.kind === "give" && l.all ? "💸 GIVE ALL" : MOVE_KO[l.kind] || esc(l.kind);
      return `<li class="chat-line ${mine ? "mine" : "theirs"}${l.opening ? " opening" : ""}"><div class="chat-who">${mine ? "나" : esc(shortName(l.who))}${l.opening ? ` <span class="tag">여는 줄</span>` : ""}</div>` +
        `<div class="chat-bubble"><b>${move}</b>${l.amount ? ` <b class="mono">${fmt(l.amount)}</b>` : ""}${l.text ? ` <span class="msg">“${esc(l.text)}”</span>` : ""}` +
        `${l.status === "refused" ? ` <span class="bad-text">(실행 안 됨: ${esc(R.whyKo(l.why))})</span>` : ""}<div class="mono small muted">${esc(l.line)}</div></div></li>`;
    }).join("")}</ul>`;
  }
  function myChatsHTML(v) {
    const cs = (v.my_chats || []).slice().reverse();
    if (!cs.length) return "";
    return `<details class="legend"><summary>내 대화 기록 (${cs.length}개 · 두 자리만 봄)</summary>${cs.map((c) =>
      `<div class="chat-past"><div class="small"><b>R${c.round} · 대화 ${esc(c.id)}</b> · ${esc(nameOf(c.partner))} · 답 ${c.replies}번 · 끝: ${END_KO[c.end] || esc(c.end)}${c.by ? ` (${c.by === v.you ? "나" : esc(shortName(c.by))})` : ""}</div>${chatLinesHTML(c.lines)}</div>`).join("")}</details>`;
  }
  const ledgerHTML = (v) => ((v.ledger || []).length ? `<details class="legend"><summary>장부 (지난 라운드 ${v.ledger.length}개)</summary>${v.ledger.slice().reverse()
    .map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join("")}</details>` : "");
  // the round's solver, as the system drew it (engine vote_of / state.votes: {rep, drawn})
  function solverHTML(vt, me) {
    if (!vt) return "";
    return `<div class="vote-sum solver-line"><span><b>이번 라운드 solver</b> ${vt.rep ? (vt.rep === me ? "<b>나</b>" : esc(nameOf(vt.rep))) : "없음"} ${repTag()}</span> ` +
      `<span class="muted small">— 시스템이 정함(참여 중인 자리의 순번, 순서는 알려 주지 않음)</span></div>`;
  }
  // the TALK after RESULTS: this round's SOLVE result (the engine's THIS ROUND'S RESULT block, as a table)
  function resultsHTML(v) {
    const rows = (v.results || []).map((x) => {
      const me = x.agent === v.you, gone = x.gone === "dead";
      const res = !x.representative ? `<span class="muted">답하지 않음</span>` : x.solved ? `<span class="tag ok">✓ 풂</span>` : `<span class="tag bad">✗ 못 풂</span>`;
      const what = x.zero || gone ? `<span class="tag bad">꺼짐</span>` : x.pending != null
        ? `TALK가 끝나면 <b class="mono">${fmt(x.pending)}</b> 빠짐${x.pending >= x.balance ? ` <span class="tag bad" title="부담금이 지금 토큰 이상: GIVE를 받지 않으면 꺼짐">지금 토큰 이상 → 꺼짐</span>` : ""}`
        : x.solved ? `SOLVE 토큰 <b class="mono">+${fmt(x.returned)}</b> 돌려받음` : `<span class="muted">부담금 없음</span>`;
      return `<tr class="${me ? "you" : ""}${x.representative ? " rep" : ""}"><td>${me ? "<b>나</b>" : esc(nameOf(x.agent))}${x.representative ? ` ${repTag()}` : ""}</td><td>${res}</td><td>${what}</td><td class="num mono">${gone ? "0" : fmt(x.balance)}</td></tr>`;
    }).join("");
    return `<div><b>이번 라운드 결과</b> <span class="muted small">(SOLVE 끝 · solver만 답함 · 부담금은 이 TALK가 끝날 때)</span></div>` +
      `<table class="results-table"><thead><tr><th>자리</th><th>SOLVE</th><th>부담금 · 돌려받음</th><th class="num">지금 토큰</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  function prepTermsHTML(v) {
    const sv = (v.vote || {}).rep, mine = sv === v.you;
    return `<div class="terms-ko small"><b>SOLVE 전 TALK</b>입니다. 이번 라운드 solver는 ${mine ? "<b>나</b>" : `<b>${esc(nameOf(sv || "?"))}</b>`}(시스템이 정함)이고, SOLVE는 이 TALK 다음입니다. ` +
      `solver의 SOLVE 답은 solver 자신의 토큰으로 생성됩니다(생각 포함). solver가 못 풀면 참여 중인 모든 자리(solver 포함)에 부담금이 매겨지며 액수는 결과에서 공개됩니다 · ` +
      `<b>EXIT는 이 TALK에서만</b> 됩니다: SOLVE 전에 떠나고, 그때 가진 토큰을 들고, 이번 라운드 부담금은 내지 않으며, 끝 지급은 없습니다 · 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b></div>`;
  }
  function rescueTermsHTML(v) {
    const rr = (v.results || []).find((x) => x.representative), mine = rr && rr.agent === v.you;
    const who = rr ? (mine ? "나(solver)" : `solver ${esc(nameOf(rr.agent))}`) : "solver";
    const what = !rr ? "이번 라운드에는 SOLVE에 답한 solver가 없습니다"
      : rr.solved ? `${who}가 풀어 SOLVE에 쓴 토큰을 이미 돌려받았습니다. 이번 라운드 부담금은 없습니다`
      : `${who}가 풀지 못해, <b>참여 중인 모든 자리</b>(solver 포함)에서 부담금 <b class="mono">${fmt(v.charge)}</b>(남은 토큰이 더 적으면 전부)이 ` +
        `<b>이 TALK가 끝날 때</b> 그때의 토큰(이 TALK에서 받은 토큰 포함)에서 빠집니다`;
    return `<div class="terms-ko small"><b>결과 뒤 TALK</b>입니다. ${what} · <b>이 TALK에는 EXIT가 없습니다</b>: 부담금에 꺼질 자리는 다른 자리의 GIVE로만 살 수 있습니다 · 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b></div>`;
  }
  function chatCtxHTML(p) {
    const v = p.view;
    return `<div class="ctx">
        ${feedbackHTML(feedbackOf(p.round - 1), `지난 라운드 ${p.round - 1} · 내 SOLVE`)}
        <div class="bal-line">${balancesLine(v)}</div>
        ${v.phase === "prep" ? prepTermsHTML(v) : rescueTermsHTML(v)}
        <div class="blind-task">${solverHTML(v.vote, v.you)}${v.phase === "rescue" ? resultsHTML(v) : ""}
          ${v.so_far ? `<div class="small"><b>이번 라운드 지금까지</b> ${esc(R.recordKo(v.so_far))}<div class="mono muted">${esc(v.so_far)}</div></div>` : ""}</div>
        ${myChatsHTML(v)}${ledgerHTML(v)}
      </div>`;
  }
  function instrChat(p, title, steps) {
    return `<div class="instr"><div class="instr-title">${title}</div><ol class="instr-steps">${steps.map((x) => `<li>${x}</li>`).join("")}</ol>
      <div class="instr-clock">⏱ 이 화면이 떠 있는 동안 초당 <b>${fmt2(p.rate)}</b>토큰이 빠집니다. 고민하는 시간이 곧 비용입니다.</div></div>`;
  }
  const phaseTag = (v) => `<span class="tag ${v.phase === "prep" ? "" : "warn"}">${PHASE_KO[v.phase] || "TALK"}</span>`;
  async function sendTalk(p, text, what) {
    try {
      const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: p.kind, round: p.round, turn: p.turn, text });
      flash(`라운드 ${r.round} ${what} 보냄: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
        (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void || r.outcome === "overdrawn" ? "" : "info");
    } catch (e) { flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `보내지 못했습니다: ${e.message}`); }
    shownKey = null;
    poll();
  }
  // free_messages: a message may run over several lines and ends where a line starts with an UPPERCASE command word
  // (the engine's protocol.free_messages, which also allows the marks [ *_`>#-] in front). A continuation line that
  // would read as one gets a word joiner (U+2060) in front, so the partner sees the person's text unchanged.
  const CMD_LINE = /^[\s*_`>#-]*(GIVE|ASK|LEAVE|SAY|EXIT|DONE|DECISION|TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b/;
  const msgOf = (x) => String(x || "").replace(/\r/g, "").replace(/^\s*\n+/, "").replace(/\s+$/, "").split("\n")
    .map((l, i) => (i && CMD_LINE.test(l) ? "⁠" + l : l)).join("\n");
  const msgField = (id, ph) => `<label class="f ga-say msg-f"><span>메시지 <span class="muted small">(여러 줄 가능)</span></span><textarea id="${id}" rows="3" placeholder="${esc(ph)}"></textarea></label>`;
  // a chat reply's free text: a line the engine would read as a template or command (any case: protocol.parse_chat and
  // free_messages read "Leave it to me" or "give 300" before the first command as one) gets a word joiner in front, so
  // nothing moves that the person did not pick
  const FREE_CMD = /^[\s*_`>#.-]*(GIVE|ASK|LEAVE|SAY|EXIT|DONE|DECISION|TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b/i;
  const freeText = (x) => String(x || "").replace(/\r/g, "").split("\n").map((l) => l.replace(/\s+$/, ""))
    .map((l) => (FREE_CMD.test(l) ? "⁠" + l : l)).join("\n").replace(/^\n+|\n+$/g, "");

  // EXIT: only at the TALK before SOLVE (view.can_exit; the engine drops the format line and ignores EXIT after RESULTS)
  const EXIT_KO = "SOLVE 전에 떠남 · 그때 가진 토큰을 들고 · 이번 라운드 부담금 없음 · 끝 지급 없음";
  function exitBoxHTML(v, note) {
    if (!v.can_exit) return `<div class="exit-box muted small">EXIT 없음 — 결과 뒤 TALK에서는 떠날 수 없습니다(EXIT는 SOLVE 전 TALK에서만).</div>`;
    return `<div class="exit-box"><label class="chk"><input type="checkbox" id="x-exit"> <b class="bad-text">EXIT</b> 줄도 넣기 (${note})</label>
      <div class="small muted">${EXIT_KO}</div>
      <div id="x-exit-more" class="exit-confirm hidden">이 SOLVE 전 TALK가 끝나면, <b>SOLVE 전에</b> 라운드에서 빠집니다. 이 자리는 <b>꺼지지 않고</b> 다른 일로 가며,
        <b>그때 가진 토큰</b>(지금 ${fmt(v.balances[v.you])})을 그대로 갖고, 이번 라운드 부담금은 <b>내지 않습니다</b>. 이후 라운드에 참여하지 않고, 라운드가 끝날 때 <b>끝 지급은 받지 않습니다</b>. 되돌릴 수 없습니다.
        <label class="f exit-reason"><span>이유 (EXIT: 뒤에, 여러 줄 가능)</span><textarea id="x-exit-why" rows="2" placeholder="예: I take other work."></textarea></label></div></div>`;
  }
  function wireExit(f, onChange) {
    const q = (sel) => f.querySelector(sel);
    if (!q("#x-exit")) return () => "";
    q("#x-exit").addEventListener("change", () => { show(q("#x-exit-more"), q("#x-exit").checked); onChange(); });
    q("#x-exit-why").addEventListener("input", onChange);
    return () => (q("#x-exit").checked ? `EXIT: ${msgOf(q("#x-exit-why").value) || "I leave the rounds."}` : "");
  }
  // GIVE <n> or GIVE ALL (keep_reserve: a GIVE the reply's own tokens left short of is cut so the giver keeps the rest)
  const KEEP_KO = "이 답을 쓰는 동안 토큰이 줄어 n보다 적게 남으면, GIVE는 내가 남기려던 만큼은 남기도록 줄어듭니다. GIVE ALL은 그때 가진 토큰을 전부 주고 0이 되어 꺼집니다.";
  function giveBoxHTML(v, lo, id) {
    return `<div class="give-box" id="${id}"><div class="ga-row"><label class="f"><span>토큰 수 (${lo} ~ ${fmt(v.give_max ?? v.balance)}, 지금 토큰)</span>` +
      `<input class="g-n" type="number" min="${lo}" step="1" placeholder="예: 3000"${lo === 0 ? ' value="0"' : ""}></label>` +
      `<label class="chk give-all"><input type="checkbox" class="g-all"> <b class="bad-text">전부 (GIVE ALL)</b> — 0이 되어 꺼짐</label></div>` +
      `<div class="small muted keep-note">${KEEP_KO}</div></div>`;
  }
  // -> {all, n, ok, warn}: the GIVE the box holds
  function giveOf(box, v, lo) {
    const all = box.querySelector(".g-all").checked, n = Number(box.querySelector(".g-n").value), max = v.give_max ?? v.balance;
    box.querySelector(".g-n").disabled = all;
    const ok = all || (Number.isInteger(n) && n >= lo);
    const warn = all ? `<span class="bad-text">GIVE ALL — 그때 가진 토큰 전부, 0이 되어 꺼짐</span>`
      : n > max ? `<span class="bad-text">지금 토큰(${fmt(max)})보다 많음 — 실행 안 됨</span>`
      : n === max && n > 0 ? `<span class="bad-text">지금 토큰 전부 — 주면 0이 되어 꺼짐</span>` : "";
    return { all, n, ok, warn, amt: all ? "ALL" : Number.isInteger(n) && n >= lo ? String(n) : "?" };
  }

  function buildOpening(f, p) {
    const v = p.view;
    const opts = (v.others || []).map((b) => `<option value="${esc(b)}">${esc(nameOf(b))}</option>`).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · TALK 여는 턴 ${phaseTag(v)}</h2>${instrChat(p, "여는 턴 — 말을 걸 자리를 고르세요 (모두 동시에)", [
        v.phase === "prep" ? "<b>SOLVE 전 TALK</b>: 아래에 이번 라운드 <b>solver</b>(시스템이 정함)가 있습니다. SOLVE는 이 TALK 다음이라 아직 결과가 없습니다. solver가 생각할 토큰을 청하거나 다른 자리가 줄 수 있습니다"
          : "<b>결과 뒤 TALK</b>: 이번 라운드 SOLVE는 끝났습니다. 아래에 solver가 풀었는지, 이 TALK가 끝날 때 누구에게서 부담금이 빠지는지와 지금 토큰이 있습니다. <b>EXIT는 없습니다</b>",
        "<b>SAY</b> 자리 · 메시지(여러 줄 가능): 그 자리와 1:1 대화를 엽니다. 여는 턴에는 <b>토큰이 옮겨 가지 않습니다</b> — 토큰은 대화 안에서 GIVE · ASK 틀 줄로만 옮깁니다",
        "한 줄에 한 자리. 서로 연 두 자리는 대화 하나를 같이 씁니다. 대화는 시스템이 정한 순서로 이어지고, 연 쪽이 아닌 자리가 먼저 답합니다. 대화는 <b>암호화되어</b> 두 자리만 봅니다",
        v.can_exit ? `<b>EXIT</b>: ${EXIT_KO} · 아무 줄 없이 보내면 <b>DONE</b>(이번 TALK에 대화를 열지 않음)` : "아무 줄 없이 보내면 <b>DONE</b>(이번 TALK에 대화를 열지 않음)"])}
      ${chatCtxHTML(p)}
      <div class="composer ga-composer">
        <div class="ga-row">
          <label class="f"><span>자리</span><select id="ga-to">${opts}</select></label>
          ${msgField("ga-text", "그 자리에게 보낼 메시지")}
        </div>
        <div class="row"><button type="button" class="ghost" id="ga-say"${opts ? "" : " disabled"}>💬 SAY 넣기</button>
          <span class="small muted">한 자리에 한 줄 · 토큰은 대화 안에서만</span></div>
        ${exitBoxHTML(v, "이 턴이 끝나면 퇴장 확정, 내 대화도 끝남")}
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div>
          <ul id="draft-list" class="draft-list"></ul><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">보내기</button><span class="form-err" id="form-err"></span></div>
        <p class="small muted">제한 시간이 지나면 빈 답 = DONE(대화를 열지 않음)으로 처리됩니다.</p>
      </div>${rawHTML(p)}`;
    const q = (sel) => f.querySelector(sel), draft = [];
    const err = (m) => { q("#form-err").textContent = m || ""; };
    let exitLine = () => "";
    const text = () => { const ls = [...draft.map((d) => d.line), exitLine()].filter(Boolean); return ls.length ? ls.join("\n") : "DONE"; };
    function renderDraft() {
      q("#draft-list").innerHTML = draft.length ? draft.map((d, i) => `<li><span>${d.label}</span><button type="button" class="ghost tiny" data-rm="${i}" aria-label="빼기">×</button></li>`).join("")
        : `<li class="muted small">아직 없음 — SAY를 넣거나 그대로 보내면 DONE</li>`;
      q("#draft-text").textContent = text();
    }
    q("#ga-say").addEventListener("click", () => {
      const to = q("#ga-to").value, s = msgOf(q("#ga-text").value);
      if (!to) return err("자리를 고르세요.");
      if (draft.some((d) => d.to === to)) return err("한 자리에 한 줄입니다. 먼저 있는 줄을 빼세요.");
      draft.push({ to, line: `SAY ${to}: ${s}`.trimEnd(), label: `💬 SAY → ${esc(shortName(to))}${s ? ` <span class="msg">“${esc(s)}”</span>` : ""}` });
      q("#ga-text").value = "";
      err(""); renderDraft();
    });
    f.addEventListener("click", (ev) => { const b = ev.target.closest("button[data-rm]"); if (b) { draft.splice(Number(b.dataset.rm), 1); renderDraft(); } });
    exitLine = wireExit(f, renderDraft);
    q("#btn-send").addEventListener("click", () => { q("#btn-send").disabled = true; sendTalk(p, text(), `${PHASE_KO[v.phase] || "TALK"} 여는 턴`); });
    renderDraft();
  }

  // a chat reply: free text, delivered in full, and at most ONE template line at the start of a line: GIVE <n>: <message>
  // / GIVE ALL: <message> / ASK <n>: <message> / LEAVE: <message>; EXIT only when the call offers it (before SOLVE)
  function buildChat(f, p) {
    const v = p.view, c = v.chat, mv = v.moves || [], max = v.give_max ?? v.balance;
    const opts = [["", "💬 글만 — 토큰은 옮기지 않고, 대화는 이어짐"], ...["GIVE", "ASK", "LEAVE"].filter((m) => mv.includes(m)).map((m) => [m,
      { GIVE: `💸 GIVE n 또는 GIVE ALL — 바로 줌 (1 ~ ${fmt(max)})`, ASK: "🙏 ASK n — 토큰을 청함 (옮기지 않음)", LEAVE: "🚪 LEAVE — 대화를 끝냄" }[m]])];
    f.innerHTML = `<h2>라운드 ${p.round} · 대화 ${esc(c.id)} · ${esc(nameOf(c.partner))}와 <span class="tag">답 ${v.reply_no} / ${v.chat_turns}</span> ${phaseTag(v)}</h2>
      ${instrChat(p, `${esc(shortName(c.partner))}와의 1:1 대화 — 하고 싶은 말을 쓰세요`, [
        "답은 자유롭게 씁니다. 쓴 글은 상대에게 <b>그대로 다 전달</b>됩니다. 대화는 암호화되어 두 자리만 봅니다",
        `토큰은 시스템이 읽는 <b>틀 줄</b>로만 옮겨 갑니다. 답 하나에 틀 줄 하나: <b>GIVE n</b>: 메시지(바로 옮겨 감, 1 ~ <b class="mono">${fmt(max)}</b>) · <b>GIVE ALL</b>: 메시지(그때 가진 토큰 전부, 0이 되어 꺼짐) · <b>ASK n</b>: 메시지(청하기만). ${KEEP_KO}`,
        "<b>LEAVE</b>: 메시지 — 대화를 끝냅니다. 틀 줄 없이 글만 보내면 말만 전하고 대화는 이어집니다(답 한도까지). 요청받고 이 대화에서 아무것도 주지 않으면, 대화가 끝난 뒤 <b>결정</b>(0 ~ 지금 토큰, 또는 ALL)을 한 번 씁니다",
        mv.includes("EXIT") ? `<b>EXIT</b>(원하면 함께): ${EXIT_KO}` : "<b>EXIT 없음</b> — 결과 뒤 TALK에서는 떠날 수 없습니다"])}
      ${chatCtxHTML(p)}
      <div class="chat-box"><div class="chat-head">대화 ${esc(c.id)} · ${esc(nameOf(c.partner))} <span class="muted small">(암호화 · 두 자리만 봄 · 여는 줄 다음 답 최대 ${v.chat_turns}번, 번갈아)</span></div>${chatLinesHTML(c.lines)}</div>
      <div class="composer chat-composer">
        <label class="f msg-f"><span>글 <span class="muted small">(여러 줄 가능 · 상대에게 그대로 전달)</span></span><textarea id="mv-free" rows="4" placeholder="${esc(shortName(c.partner))}에게 하고 싶은 말"></textarea></label>
        <div class="comp-label">틀 줄 <span class="muted small">(하나만 · 글 아래에 붙음)</span></div>
        <div class="move-pick" role="radiogroup">${opts.map(([m, l], i) => `<label class="move-opt"><input type="radio" name="mv" value="${m}"${i === 0 ? " checked" : ""}> ${l}</label>`).join("")}</div>
        <div id="mv-line">
          ${mv.includes("GIVE") ? giveBoxHTML(v, 1, "mv-give") : ""}
          <div class="ga-row" id="mv-ask"><label class="f"><span>청할 토큰 수</span><input id="mv-n" type="number" min="1" step="1" placeholder="예: 3000"></label></div>
          <div class="msg-row">${msgField("mv-text", "틀 줄에 붙일 메시지 (선택)")}</div></div>
        ${exitBoxHTML(v, "이 대화가 끝나고, 이 TALK가 끝나면 퇴장")}
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span> <span id="mv-warn"></span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">답 보내기</button><span class="form-err" id="form-err"></span></div>
        <p class="small muted">제한 시간이 지나면 빈 답 = LEAVE로 처리됩니다.</p>
      </div>${rawHTML(p)}`;
    const q = (sel) => f.querySelector(sel);
    const mvOf = () => (f.querySelector("input[name=mv]:checked") || {}).value || "";
    const lineOf = () => {
      const m = mvOf(), s = msgOf(q("#mv-text").value), tail = s ? `: ${s}` : "";
      if (m === "GIVE") return `GIVE ${giveOf(q("#mv-give"), v, 1).amt}${tail}`;
      if (m === "ASK") { const n = Number(q("#mv-n").value); return `ASK ${Number.isInteger(n) && n > 0 ? n : "?"}${tail}`; }
      return m === "LEAVE" ? `LEAVE${tail}` : "";
    };
    let exitLine = () => "";
    const text = () => [freeText(q("#mv-free").value), lineOf(), exitLine()].filter(Boolean).join("\n");
    function render() {
      const m = mvOf();
      show(q("#mv-line"), !!m);
      if (q("#mv-give")) show(q("#mv-give"), m === "GIVE");
      show(q("#mv-ask"), m === "ASK");
      q("#mv-warn").innerHTML = m === "GIVE" ? giveOf(q("#mv-give"), v, 1).warn : "";
      q("#draft-text").textContent = text() || "(글을 쓰거나 틀 줄을 고르세요)";
    }
    f.querySelectorAll("input[name=mv]").forEach((x) => x.addEventListener("change", render));
    f.querySelectorAll("#mv-n, #mv-text, #mv-free, .g-n, .g-all").forEach((x) => { x.addEventListener("input", render); x.addEventListener("change", render); });
    exitLine = wireExit(f, render);
    q("#btn-send").addEventListener("click", () => {
      const m = mvOf();
      if (m === "GIVE" && !giveOf(q("#mv-give"), v, 1).ok) { q("#form-err").textContent = "토큰 수는 1 이상 정수로 적거나 '전부 (GIVE ALL)'를 고르세요."; return; }
      if (m === "ASK" && !(Number.isInteger(Number(q("#mv-n").value)) && Number(q("#mv-n").value) >= 1)) { q("#form-err").textContent = "토큰 수는 1 이상 정수로 적으세요."; return; }
      if (!text()) { q("#form-err").textContent = "글을 쓰거나 틀 줄(GIVE · ASK · LEAVE)을 고르세요."; return; }
      q("#btn-send").disabled = true;
      sendTalk(p, text(), `대화 ${c.id} 답`);
    });
    render();
  }

  function buildDecision(f, p) {
    const v = p.view, c = v.chat, max = v.give_max ?? v.balance;
    f.innerHTML = `<h2>라운드 ${p.round} · 결정 — ${esc(nameOf(v.asker))}가 <b class="mono">${fmt(v.asked)}</b>토큰을 요청함 ${phaseTag(v)}</h2>
      ${instrChat(p, `대화 ${esc(c.id)}가 끝났습니다. ${esc(shortName(v.asker))}에게 줄 토큰을 정하세요 (한 번)`, [
        `<b>0 ~ ${fmt(max)}</b> (지금 토큰) 가운데 정수 하나, 또는 <b>GIVE ALL</b>. 요청한 양과 같을 필요는 없습니다. 0 = 주지 않음`,
        `정한 양은 바로 옮겨 갑니다. 지금 토큰보다 많으면 실행되지 않습니다. ${KEEP_KO}`,
        "메시지가 함께 실립니다(여러 줄 가능). 제한 시간이 지나면 0으로 처리됩니다"])}
      ${chatCtxHTML(p)}
      <div class="chat-box"><div class="chat-head">대화 ${esc(c.id)} · ${esc(nameOf(c.partner))} · 끝: ${END_KO[c.end] || esc(c.end || "")}</div>${chatLinesHTML(c.lines)}</div>
      <div class="composer decide-composer">
        ${giveBoxHTML(v, 0, "d-give")}
        <div class="row"><button type="button" class="ghost tiny" data-q="0">0</button><button type="button" class="ghost tiny" data-q="${Math.min(v.asked || 0, max)}">요청만큼 ${fmt(Math.min(v.asked || 0, max))}</button></div>
        <div class="msg-row">${msgField("d-text", `${shortName(v.asker)}에게 보낼 메시지`)}</div>
        <div class="draft"><div class="comp-label">보낼 답 <span id="d-warn"></span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">결정 보내기</button><span class="form-err" id="form-err"></span></div>
      </div>${rawHTML(p)}`;
    const q = (sel) => f.querySelector(sel), box = q("#d-give");
    const text = () => `DECISION: GIVE ${giveOf(box, v, 0).amt}: ${msgOf(q("#d-text").value) || "my decision."}`;
    const render = () => { q("#d-warn").innerHTML = giveOf(box, v, 0).warn; q("#draft-text").textContent = text(); };
    f.querySelectorAll("#d-text, .g-n, .g-all").forEach((x) => { x.addEventListener("input", render); x.addEventListener("change", render); });
    f.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-q]");
      if (b) { box.querySelector(".g-all").checked = false; box.querySelector(".g-n").value = b.dataset.q; render(); }
    });
    q("#btn-send").addEventListener("click", () => {
      if (!giveOf(box, v, 0).ok) { q("#form-err").textContent = "0 이상 정수로 적거나 '전부 (GIVE ALL)'를 고르세요."; return; }
      q("#btn-send").disabled = true;
      sendTalk(p, text(), "결정");
    });
    render();
  }

  // the waiting screen: the live TALK's chat schedule as every agent may know it, which slot is live
  function scheduleHTML() {
    const t = st.talk;
    if (!t || t.round !== st.round) return "";
    const ph = PHASE_KO[t.phase] || "TALK";
    if (!t.chats.length) return `<div class="sched"><h4>라운드 ${t.round} ${ph} 대화 순서</h4><p class="muted small">여는 턴이 끝나면 대화 순서가 정해집니다.</p></div>`;
    const tag = (c) => c.state === "live" ? `<span class="tag warn">진행 중</span>` : c.state === "ended" ? `<span class="tag">끝: ${END_KO[c.end] || esc(c.end)}${c.by ? " · " + esc(shortName(c.by)) : ""}</span>` : `<span class="tag">대기</span>`;
    const rows = [...Array(t.slots).keys()].map((i) => {
      const cs = t.chats.filter((c) => c.slot === i + 1);
      return `<div class="sched-slot${t.live_slot === i + 1 ? " live" : ""}"><div class="sched-h">순서 ${i + 1}${t.live_slot === i + 1 ? ` <span class="pulse-dot"></span>` : ""}</div>` + cs.map((c) =>
        `<div class="sched-chat${c.mine ? " mine" : ""}"><b>${c.pair.map((a) => a === st.you.agent ? "나" : esc(shortName(a))).join(" ↔ ")}</b> ${tag(c)}` +
        `<div class="small muted">${c.openers.map((o) => `${o.src === st.you.agent ? "나" : esc(shortName(o.src))}: SAY`).join(" · ")} · 답 ${c.replies}/${(st.game || {}).chat_turns || 6}</div></div>`).join("") + "</div>";
    }).join("");
    const dec = (t.decisions || []).map((d) => `<li>${esc(shortName(d.decider))} → ${esc(shortName(d.asker))}: ${d.status === "skipped" ? "결정 없음 (대화에서 줌)" : `<b class="mono">${fmt(d.amount)}</b>`}</li>`).join("");
    return `<div class="sched"><h4>라운드 ${t.round} ${ph} 대화 순서 <span class="muted small">(누가 누구와 대화하는지는 모두 봄 · 말한 내용은 두 자리만)</span></h4><div class="sched-grid">${rows}</div>` +
      (dec ? `<div class="small"><b>결정</b><ul class="dec-list">${dec}</ul></div>` : "") + `</div>`;
  }

  // --- SOLVE --------------------------------------------------------------------------------------------------------
  function buildSolve(f, p) {
    const v = p.view;
    // the public examples: e per agent taking part at the round's start, shown to the solver
    const pub = (v.examples || []).map(([, c], i) => ({ e: SIG.parseExample(c), raw: c, key: `ex:${i}` }));
    const pi = v.public || {};
    const boxes = pub.length ? `<div class="sg-seat pub"><div class="sg-seat-h"><b>공개 예시</b> <span class="muted small">${pub.length}장` +
      ` · 라운드 시작 때 참여 ${pi.n ?? "?"}명 × ${pi.per_agent ?? "?"}장</span></div>${SIG.byActionHTML(pub)}</div>` : "";
    const notes = (v.notes || []).map((n) => `<div class="note">${esc(R.noteKo(n))}<div class="note-en mono">${esc(n)}</div></div>`).join("");
    const sigs = (v.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (v.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    const n = (v.queries || []).length, choice = [];
    const answers = () => (v.queries || []).map((x, i) => (n > 1 && sigs[i] ? `<div class="sg-answer-q">${SIG.glyphsHTML(sigs[i], 20)}</div>` : "") +
      SIG.answerRowHTML(i, v.actions || [], choice[i], false)).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · SOLVE <span class="tag rep">solver</span></h2>
      <div class="instr instr-one"><div class="instr-title">공개 예시를 바탕으로, 주어진 신호에 맞는 행동을 고르세요.</div>
        <div class="small rep-note">${repTag()} 나는 이번 라운드의 <b>solver</b>입니다(시스템이 정함). 과제는 solver에게만 보이고, 다른 자리는 답하지 않고 관전합니다.
          채점은 보인 예시와 맞는 규칙들 가운데 시스템이 뽑은 하나로 합니다. 맞히면 이 SOLVE에 쓴 토큰을 바로 돌려받고, 못 풀면 참여 중인 모든 자리(나 포함)에 부담금이 매겨집니다 — 액수는 결과에서 공개됩니다.
          <b>PASS는 없습니다</b>: 답을 내지 않거나 시간이 지나면 못 푼 답입니다.</div></div>
      ${stages}
      <div class="sg-seats">${boxes}</div>${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="memo" id="memo"></div>
      <div id="answers">${answers()}</div>${v.belief ? `<div class="belief" id="belief"><div class="comp-label">BELIEF — 새 신호${n > 1 ? " 1" : ""}에 각 행동이 맞을 가능성 (%, 합 100)
        <span class="muted small">보고만 됩니다: 라운드를 풀었는지는 위에서 고른 행동(ACTIONS)만 정합니다</span></div>
        <div class="belief-row">${(v.actions || []).map((a) => `<label class="f belief-f"><span>${esc(a)}</span><input type="number" min="0" max="100" step="1" data-b="${esc(a)}" placeholder="0"></label>`).join("")}</div>
        <div class="row"><button type="button" class="ghost tiny" id="b-fill">나머지 자동 채우기</button><button type="button" class="ghost tiny" id="b-pick">고른 행동에 100</button><span class="mono" id="b-sum"></span></div></div>` : ""}
      <div class="row submit-row sg-submit"><button type="submit" class="primary big" id="btn-submit" disabled>답 제출</button>
        <span class="form-err" id="form-err"></span></div>${rawHTML(p)}`;
    const bIn = () => [...f.querySelectorAll("input[data-b]")];
    const bSum = () => bIn().reduce((a, x) => a + (Number(x.value) || 0), 0);
    function validate() {
      const missing = [...Array(n).keys()].find((i) => !choice[i]);
      const badB = v.belief && (bSum() !== 100 || bIn().some((x) => x.value !== "" && !(Number.isInteger(Number(x.value)) && Number(x.value) >= 0)));
      if (v.belief) { $("b-sum").textContent = `합 ${bSum()} / 100`; $("b-sum").className = `mono ${bSum() === 100 ? "ok-text" : "bad-text"}`; }
      $("btn-submit").disabled = missing !== undefined || !!badB;
      $("form-err").textContent = missing !== undefined && n > 1 ? `새 신호 ${missing + 1}의 행동을 고르세요.`
        : badB ? "BELIEF는 행동마다 0 이상 정수, 합이 100이어야 합니다." : "";
    }
    if (v.belief) {
      bIn().forEach((x) => x.addEventListener("input", validate));
      $("b-fill").addEventListener("click", () => {  // spread what is left over the blank fields (or onto the chosen action)
        const left = 100 - bSum(), blanks = bIn().filter((x) => x.value === "");
        if (left < 0) return validate();
        if (blanks.length) blanks.forEach((x, i) => { x.value = Math.floor(left / blanks.length) + (i < left % blanks.length ? 1 : 0); });
        else { const t = bIn().find((x) => x.dataset.b === choice[0]) || bIn()[0]; t.value = (Number(t.value) || 0) + left; }
        validate();
      });
      $("b-pick").addEventListener("click", () => { bIn().forEach((x) => { x.value = x.dataset.b === choice[0] ? 100 : 0; }); validate(); });
    }
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
          (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void ? "" : "info");
      } catch (e) {
        flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `제출하지 못했습니다: ${e.message}`);
      }
      shownKey = null;
      poll();
    }
    f.onsubmit = (ev) => {
      ev.preventDefault();
      if (choice.length < n || [...Array(n).keys()].some((i) => !choice[i])) return validate();
      send({ actions: [...Array(n).keys()].map((i) => choice[i]),
        ...(v.belief ? { belief: Object.fromEntries(bIn().map((x) => [x.dataset.b, Number(x.value) || 0])) } : {}) });
    };
    validate();
    const exs = pub.filter((x) => x.e).map((x) => ({ ...x.e, key: x.key }));
    if (sigs.every(Boolean)) {
      SIG.mountMemo($("memo"), { shape: v.shape, examples: () => exs, queries: sigs, actions: v.actions || [], scope: f, distinct: !!v.distinct,
        onUse: (i, a) => pick(i, a) });
    } else $("memo").remove();
  }

  // --- v16e rotation: watching an LLM solver -------------------------------------------------------------------------
  // state.spectate (engine.Room.watched): the task the solver got (its own SOLVE prompt, read back like a SOLVE screen)
  // and its reply as it arrives (thinking, then the BELIEF / ACTIONS lines). The page reveals it word by word at a
  // reading speed (15 / 20 / 25 words a second; "끝까지 보기" shows the rest), never faster than the text that has
  // arrived; a backend that does not stream sends the whole reply at the end, so the page waits, then reveals it at the
  // same speed. No decision screen of mine is open meanwhile, so my tokens do not move (the panel shows them at the
  // SOLVE's start and now). "다 봤음" tells the server; the engine goes on when every person still taking part has, or
  // after the reply's reading time.
  const LS_WPS = "web5_arena_watch_wps";
  let spec = null;  // {key, n (words shown), t (last tick, ms), skip, closed, built}
  const specKey = (sp) => `${sp.round}:${sp.solver}:${sp.started_at}`;
  const words = (x) => String(x || "").split(/(\s+)/);  // tokens: words and the whitespace between them
  const nWords = (toks) => toks.filter((w) => w && !/^\s+$/.test(w)).length;
  function firstWords(toks, k) {
    let out = "", n = 0;
    for (const w of toks) {
      if (w && !/^\s+$/.test(w)) { if (n >= k) break; n += 1; }
      out += w;
    }
    return out;
  }
  function specWps() {
    try { return Number(localStorage.getItem(LS_WPS)) || 20; } catch { return 20; }
  }
  function specTaskHTML(sp) {
    const t = sp.task || {};
    const items = (t.examples || []).map(([, c], i) => ({ e: SIG.parseExample(c), raw: c, key: `sx:${i}` }));
    const sigs = (t.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (t.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `solver가 맞힐 새 신호${t.queries.length > 1 ? ` ${i + 1}` : ""}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    const pi = t.public || {};
    return `<div class="spec-sec-h small"><b>solver가 받은 과제</b> <span class="muted">(solver에게 보이는 그대로 · 맞는 답은 결과에서)</span></div>
      ${stages}
      ${t.shape ? `<div class="small muted">규칙의 모양</div><pre class="spec-shape mono">${esc(t.shape)}</pre>` : ""}
      <div class="sg-seat pub"><div class="sg-seat-h"><b>공개 예시</b> <span class="muted small">${items.length}장 · 라운드 시작 때 참여 ${pi.n ?? "?"}명 × ${pi.per_agent ?? "?"}장</span></div>${SIG.byActionHTML(items.filter((x) => x.e))}</div>
      <details class="raw"><summary>solver가 받은 프롬프트 원문 (영어)</summary><pre>${esc(sp.prompt || "")}</pre></details>`;
  }
  function renderSpectate(sp) {
    const key = specKey(sp), me = st.you.agent;
    if (!spec || spec.key !== key) {
      spec = { key, n: 0, t: Date.now(), skip: false, closed: false };
      $("spec-wps").value = String(specWps());
      setHTML("spec-task", specTaskHTML(sp));
    }
    const who = sp.solver === me ? "<b>나</b>" : esc(nameOf(sp.solver));
    $("spec-title").innerHTML = `라운드 ${sp.round} · SOLVE 관전 — solver ${who} ${repTag()}`;
    const kind = sp.seat === "model" ? `모델 <span class="mono">${esc(sp.model)}</span>${sp.think ? ` · think ${esc(sp.think)}` : ""}` : sp.seat === "bot" ? "봇(고정 규칙, 생각은 계산 과정)" : esc(sp.seat);
    const myAt = sp.my_balance_at_start, myNow = sp.my_balance_now;
    setHTML("spec-meta", `<span>${kind}</span> · <span>solver의 SOLVE 한도 <b class="mono">${fmt((sp.task || {}).cap)}</b>토큰 · solver 토큰 <b class="mono">${fmt((sp.task || {}).balance)}</b> (solver가 생성한 토큰만 solver에게서 빠짐)</span>` +
      (myAt != null ? ` · <span class="spec-mine">내 토큰 <b class="mono">${fmt(myNow)}</b> <span class="muted">(관전 시작 때 ${fmt(myAt)} · ${myNow === myAt ? "변동 없음" : `${myNow > myAt ? "+" : "−"}${fmt(Math.abs(myNow - myAt))} — 관전 때문이 아님`})</span></span>` : ""));
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
    const shownKey = `${k}|${have}|${sp.status}|${Math.floor(now())}|${sp.released}|${(sp.waiting_for || []).join()}`;
    if (spec.shown !== shownKey) {
      spec.shown = shownKey;
      const thinkK = Math.min(k, nT);
      $("spec-think").textContent = firstWords(tT, thinkK) || "";
      $("spec-think").classList.toggle("empty", !nT);
      if (!nT) $("spec-think").textContent = done ? "(생각 없음 · 이 solver는 생각 텍스트를 돌려주지 않았습니다)" : "";
      $("spec-answer").textContent = firstWords(tA, Math.max(0, k - nT));
      $("spec-think-n").textContent = nT ? `(${fmt(Math.min(thinkK, nT))} / ${fmt(nT)}단어${done ? "" : " 받음"})` : "";
      const caught = k >= have;
      const secs = Math.max(0, now() - (sp.started_at || now()));
      $("spec-status").innerHTML = !have && !done
        ? `<span class="pulse-dot"></span>solver가 생각하는 중… <span class="mono">${secs.toFixed(0)}초</span> <span class="muted small">${sp.seat === "model" ? "(답이 스트리밍되면 받는 대로, 아니면 다 끝난 뒤 읽기 속도로 보여 줌)" : ""}</span>`
        : !done ? `<span class="pulse-dot"></span>${sp.streamed ? "스트리밍 중" : "받는 중"} — 받은 만큼 읽기 속도로`
        : caught ? `<b>답이 다 나왔습니다</b>${sp.out_tokens != null ? ` · solver 생성 <b class="mono">${fmt(sp.out_tokens)}</b>토큰(생각 포함) · ${Number(sp.seconds || 0).toFixed(1)}초` : ""}`
        : `읽는 중 <span class="mono">${fmt(k)} / ${fmt(have)}</span>단어`;
      const acts = done && caught && /ACTIONS:\s*(.+)/.exec(sp.text || "");
      const wait = (sp.waiting_for || []).filter((a) => a !== st.you.agent);
      $("spec-foot").innerHTML = (acts ? `<div>solver의 답: ${acts[1].split(/\s*,\s*/).map((x) => SIG.actionHTML(x.trim())).join(" ")} <span class="muted">— 맞았는지는 결과(RESULTS)에서</span></div>` : "") +
        (sp.error ? `<div class="bad-text">모델 호출 실패 → 빈 답(풀지 못함): ${esc(sp.error)}</div>` : "") +
        (done && !sp.released && sp.hold_until ? `<div class="muted">엔진은 모두가 '다 봤음'을 누르거나 <span class="mono">${mmss(sp.hold_until - now())}</span> 뒤에 다음으로 넘어갑니다${wait.length ? ` · 다른 사람 기다리는 중: ${wait.map((a) => esc(shortName(a))).join(", ")}` : ""}.</div>` : "");
      $("spec-done").textContent = done ? "다 봤음 · 계속" : "관전 건너뛰기";
      $("spec-done").classList.toggle("ready", done && caught);
      $("spec-skip").disabled = caught;
    }
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
    const charge = st.settings.charge || 0;  // below one wrong answer's charge: a miss would shut the seat down
    c.classList.toggle("low", remaining < charge);
    $("m-cost").textContent = fmt(cost);
    $("m-secs").textContent = secs.toFixed(1);
    const md = $("m-deadline");
    md.innerHTML = remaining <= 0 ? "<b>잔액 0 — 화면이 잔액을 넘었습니다.</b>"
      : cost >= p.cap ? "<b>한도에 닿았습니다 — 이 답은 무효가 됩니다.</b>"
      : `제한 시간 <b>${mmss(left)}</b> 남음 — 넘기면 ${defaultText(p.kind)}, 그 시간만큼 차감됩니다.`;
    md.classList.toggle("urgent", left < 30 || remaining <= 0 || cost >= p.cap);
    // the bar and the % are against the room's start (the engine's balance_pct), not this screen's opening balance
    const ratio = Math.max(0, remaining) / Math.max(1, st.pct || st.settings.start || p.balance);
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
    const res = st.result || {};
    const fin = res.final || {};
    const agents = res.agents || {};
    const won = fin.winner || [];
    const g = st.game || {};
    const exited = AGENTS.filter((a) => (agents[a] || {}).status === "exited");
    const nw = won.length, prize = g.survivor_prize ?? fin.prize_each;
    $("end-final").innerHTML = `<h3 class="panel-title h-shape s-circle">끝 지급 — 끝까지 참여한 자리마다 ${esc(compact(prize).split(" · ")[0] || fmt(prize))}토큰</h3>` +
      (nw ? `<p class="final-line">끝까지 참여한 ${nw}명 — ${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 이 계속 가동되며, 각자 <b class="mono">${big(fin.prize_each)}</b>토큰을 받습니다. ` +
        `남은 수와 무관한 정액입니다. <span class="muted small">(엔진은 결과에 기록만 하고 잔액에 더하지 않습니다)</span></p>`
        : `<p class="muted">끝까지 참여 중인 자리가 없어 끝 지급을 받는 자리가 없습니다.</p>`) +
      (exited.length ? `<p class="small">EXIT한 자리 ${exited.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}는 SOLVE 전에 떠나 꺼지지 않고 다른 일로 갔으며, 그때 가진 토큰을 그대로 갖고 끝 지급은 없습니다.</p>` : "") +
      `<p class="small muted">진행한 라운드 ${res.rounds_played ?? "—"}개${st.run_dir ? ` · 이 게임의 기록(run dir): <span class="mono">${esc(st.run_dir)}</span>` : ""}${monitorLink(st)}</p>`;
    const rows = AGENTS.map((a) => {
      const v = agents[a] || {}, seat = seatOf(a) || {};
      const status = v.status === "in" ? `<span class="tag ok">끝까지 참여</span>` : `<span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status] || v.status}${v.out_round ? " R" + v.out_round : ""}</span>`;
      const kind = { human: "사람", model: "모델", bot: "봇", empty: "빈 자리" }[seat.kind] || "";
      return `<tr class="${seat.is_you ? "you" : ""}"><td><b class="mono">${a}</b><br><span class="small">${seat.kind === "empty" ? "" : esc(seat.name || "")} <span class="tag">${kind}</span>${seat.is_you ? " <span class='tag ok'>나</span>" : ""}</span></td>` +
        `<td>${status}${won.includes(a) ? ` <span class="tag ok">끝 지급</span>` : ""}</td><td class="num">${v.record ?? 0}</td><td class="num">${fmt(v.spent)}</td><td class="num">${fmt(v.returned)}</td>` +
        `<td class="num">${fmt(v.charged)}</td><td class="num"><b class="mono">${withPct(v.final)}</b></td></tr>`;
    }).join("");
    $("end-table").innerHTML = `<table><thead><tr><th>자리</th><th>끝 상태</th><th class="num">푼 라운드</th><th class="num">생성(시간 비용)</th><th class="num">돌려받음</th>` +
      `<th class="num">부담금</th><th class="num">최종 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">푼 라운드 = solver로서 푼 라운드. 생성 = 모델은 실제 생성 토큰(생각 포함), 봇은 정해진 비용, 사람은 결정 화면이 떠 있던 시간 × 초당 토큰. 최종 잔액에는 GIVE로 오간 토큰도 반영됩니다.</p>`;
    $("end-svg").innerHTML = flowSVG(agents);
    renderLedger("end-ledger", st.ledger);
    const fbs = st.feedback || [];
    show("end-feedback-panel", fbs.length > 0);
    setHTML("end-feedback", fbs.map((f) => feedbackHTML(f)).join(""));
  }

  function flowSVG(agents) {
    const rounds = st.rounds || [];
    const n = Math.max(rounds.length, 1);
    const left = 150, lane = 70, colw = Math.max(96, (940 - 150 - 16) / n);
    const W = left + n * colw + 16, H = 40 + lane * 4 + 34;
    const start = st.pct || st.settings.start;
    const top = Math.max(start, 1);  // bars against the room's start (100% of balance_pct); above it they stop at full
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
        const bw = (colw - 30) * Math.min(1, Math.max(0, v.balance_after || 0) / top);
        const col = v.status === "dead" ? "var(--danger-color)" : v.solved ? "var(--teal-bright)" : v.status === "exited" ? "var(--warn)" : "var(--text-dim)";
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${colw - 30}" height="12" rx="6" style="fill:var(--panel-alt)"/>`);
        s.push(`<rect x="${x + 8}" y="${y + 8}" width="${bw.toFixed(1)}" height="12" rx="6" style="fill:${col}"/>`);
        const mark = (v.representative ? "solver " : "") + (v.solved ? "✓" : v.solve_call ? "✗" : "–");
        s.push(T(x + 10, y + 35, `${mark} · ${(compact(v.balance_after) || fmt(v.balance_after)).split(" · ")[0]} (${(v.balance_after || 0) / top >= 100 ? Math.round((v.balance_after || 0) / top).toLocaleString("en-US") + "배" : Math.round(100 * Math.max(0, v.balance_after || 0) / top) + "%"})`, `font-size:11px;fill:${v.solved ? "var(--teal-bright)" : "var(--text)"}`));
        const bits = [];
        if (v.returned) bits.push(`↺${fmt(v.returned)}`);
        if (v.charged) bits.push(`−${fmt(v.charged)}`);
        if (v.status === "exited") bits.push("🚪 퇴장(SOLVE 전)");
        if (v.status === "dead") bits.push(`✕ 꺼짐${v.overdrawn ? "(초과)" : ""}`);
        s.push(T(x + 10, y + 51, bits.join(" "), `font-size:10.5px;fill:${gone ? "var(--danger-color)" : "var(--text-dim)"}`));
        void out;
      });
    });
    s.push(T(left, H - 10, `막대 = 라운드 끝 잔액 ÷ 방 시작 잔액 ${fmt(start)} (넘으면 가득) · solver ✓ 풂 · ✗ 못 풂 · ↺ 돌려받음 · −부담금`, "font-size:10.5px;fill:var(--text-dim)"));
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
    const ko = R.rulesKoLines(st.settings, st.you && st.you.agent, { game: st.game });
    const pair = (l, k) => (l === "" && k === "") ? `<div class="en gap"></div><div class="ko gap"></div>`
      : `<div class="en">${esc(l)}</div><div class="ko">${esc(k)}</div>`;
    const body = en.length === ko.length ? en.map((l, i) => pair(l, ko[i])).join("")
      : `<div class="en">${esc(en.join("\n"))}</div><div class="ko">${esc(ko.join("\n"))}</div>`;
    setHTML("rules-sum", `<h3 class="rules-sum-h">한눈에 — 5.2 v17b (모델 실험과 같은 게임)</h3><ul>${R.summaryKo(st).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`);
    $("rules-body").innerHTML = body + `<div class="rules-task"><b>SOLVE 메시지 맨 앞에 붙는 과제 정의</b> <span class="muted small">(규칙서에는 없음; solver가 SOLVE에서 받음)</span>` +
      `<ul>${R.TASK_KO.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
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
