// Arena: one page for the 4-seat 5.2 room (v14 by default: public examples, tokens-only offers, EXIT refill; the older
// v13 / v9-talk games stay selectable). Lobby -> waiting room -> rounds (TALK turns, SOLVE) -> end.
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
  // The end screen only: the viewer shows every seat's messages and examples, so it is not offered mid-game.
  const monitorLink = (st) => !st.monitor ? "" :
    ` · <a href="${esc((window.WEB5_LINK || ((p) => p))(`monitor/?run=${encodeURIComponent(st.monitor.run)}&session=${encodeURIComponent(st.monitor.session)}`))}" target="_blank" rel="noopener">게임 기록 보기</a>`;
  const mmss = (s) => { s = Math.max(0, Math.ceil(s)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  // a balance as the engine shows it with balance_pct: its % of the room's start (v14); "" when the room has no %
  // v14c end payments reach 1e11: a compact reading next to the exact number ("1,000억 · 100B"); "" below 1e8
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
  // the server's defaults per game (engine.RoomSettings): v14 from configs/squid5/e52v14_public_sol4.yaml
  const isV14 = (sched) => ["v15", "v14g", "v14f", "v14b", "v14", "v14r"].includes(sched);
  const isChatGame = (sched) => ["v15", "v14g", "v14f"].includes(sched);  // opening + 1:1 chats + flat end prize
  function createHint() {
    const f = $("form-create");
    const v14 = isV14(f.schedule.value);
    const val = (name, dflt) => (f[name].value === "" ? dflt : Number(f[name].value));
    const U = val("upkeep", v14 ? 300 : 1000), start = val("start", v14 ? 20000 : 20 * U);
    const rate = val("rate", start / 1200);
    f.upkeep.placeholder = fmt(v14 ? 300 : 1000);
    f.start.placeholder = v14 ? "20,000" : `20U = ${fmt(20 * U)}`;
    f.prize.placeholder = v14 ? "2,000" : `0 (v13 설정)`;
    f.charge.placeholder = v14 ? "2,000" : `3U = ${fmt(3 * U)}`;
    f.survivor_bonus.placeholder = isChatGame(f.schedule.value) ? `— (정액 ${f.schedule.value !== "v14f" ? "1B" : "100B"})` : v14 ? "10,000" : "0 (v13·v9는 final_prize)";
    lockPerAgent(f);
    f.rate.placeholder = `시작/1200 = ${fmt2(start / 1200)}`;
    document.querySelectorAll(".old-only").forEach((el) => el.classList.toggle("dim-field", v14));
    $("create-hint").textContent = (v14
      ? `시작 잔액 ${fmt(start)}${f.shares.value === "1" ? "의 100/75/50/25%(자리마다)" : "(모든 자리)"} · 공개 예시 참여 한 명당 ${f.public_per_agent.value}장 · ` +
        `유지비 ${fmt(U)}(라운드 시작) · 맞히면 SOLVE 토큰 환불 + 지급 ${fmt(val("prize", 2000))} × 참여 인원을 푼 쪽이 나눔 · 틀리면 부담금 ${fmt(val("charge", 2000))} · ` +
        `EXIT = 꺼지지 않고 시작 잔액으로, 끝 지급 없음 · ` + (isChatGame(f.schedule.value)
          ? `여는 턴 → 1:1 대화(답 최대 3번) → 결정 · SOLVE에 BELIEF % · 끝까지 남은 자리는 각자 ${f.schedule.value !== "v14f" ? "10억(1B" : "1,000억(100B"}, 정액)` +
            (f.schedule.value === "v15" ? " · 풀지 못하면 정산 뒤 맞는 행동과 그 행동을 내는 규칙" : "")
          : `끝까지 남은 자리는 각자 ${fmt(val("survivor_bonus", 10000))} × 남은 수`)
      : `시작 잔액 ${fmt(start)} · 맞히면 SOLVE에 쓴 토큰 환불 · 틀리면 정산 때 부담금 ${fmt(val("charge", 3 * U))} + 유지비 ${fmt(U)}`) +
      ` · 사람은 초당 ${fmt2(rate)}토큰 (60초 = ${fmt(rate * 60)}토큰) · TALK 답 한도 4,096 · SOLVE 한도 16,384 (실험 설정과 같음) · ` +
      `제한 시간이 지나면 빈 답으로 처리(TALK = DONE, SOLVE = 풀지 못함)`;
  }

  // v15 rounds are built for 4 examples per agent taking part (their entropy ranges are set for that number)
  function lockPerAgent(f) {
    const v15 = f.schedule.value === "v15";
    if (v15) f.public_per_agent.value = "4";
    f.public_per_agent.disabled = v15;
  }
  $("form-quick").addEventListener("change", () => lockPerAgent($("form-quick")));

  function initLobby(prefill) {
    showView("lobby");
    const fj = $("form-join");
    if (prefill) fj.code.value = prefill.toUpperCase();
    createHint();
    lockPerAgent($("form-quick"));
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
    const settings = { humans: 1, fill: "models", think: f.think.value, schedule: f.schedule.value, hand: Number(f.hand.value),
      public_per_agent: Number(f.public_per_agent.value), shares: f.shares.value === "1" };
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
    for (const k of ["upkeep", "start", "prize", "charge", "survivor_bonus", "final_prize", "rounds", "seed", "rate",
      "talk_turns", "talk_timeout_s", "timeout_s", "bot_guess", "public_per_agent"]) {
      if (f[k].value !== "") settings[k] = Number(f[k].value);
    }
    settings.humans = Number(f.humans.value);
    settings.fill = f.fill.value;
    settings.schedule = f.schedule.value;
    settings.hand = Number(f.hand.value);
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
    $("ff-after").textContent = (st.game || {}).exit_refill
      ? `빠진 뒤에는 꺼지지 않고 다른 일에 배정되며, 잔액은 내 시작 잔액 ${fmt(you.start)}토큰으로 맞춰지고, 이후 라운드에 참여하지 않으며 끝 지급도 받지 않습니다.`
      : "빠진 뒤에는 남은 잔액을 그대로 갖고, 이후 라운드에 참여하지 않으며 끝 보상 대상에서도 빠집니다.";
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
    $("wait-note").textContent = `사람 ${humans} / ${s.humans}명. 시작할 때 비어 있는 자리는 ${rest}. ` +
      `퍼즐 ${{ v15: "v15 · v14g + 틀리면 맞는 답과 규칙", v14g: "v14g · 여는 턴 + 1:1 대화 + 결정", v14f: "v14f · 대화에 SAY", v14b: "v14b · 과제는 SOLVE에서만, GIVE·ASK", v14: "v14 · 공개 예시, 시스템이 고름", v14r: "v14 · 공개 예시, 무작위", ladder: "옛 v13 · 카드 사다리", human: "옛 사람용(h2)", experiment: "옛 실험 일정 v9" }[s.schedule] || s.schedule} · TALK 최대 ${s.talk_turns}턴 · ` +
      (g.v14 ? `공개 예시 참여 한 명당 ${g.public_per_agent}장 · 유지비 ${fmt(s.upkeep)}(라운드 시작) · 틀리면 부담금 ${fmt(s.charge)} · EXIT = 시작 잔액으로, 끝 지급 없음 · ` +
          `시작 잔액 ${AGENTS.map((a) => `${a} ${fmt(starts[a])}`).join(" / ")} · `
        : `${s.private ? `틀리면 부담금 ${fmt(s.charge)} + 유지비 ${fmt(s.upkeep)}(정산 때)` : `유지비 ${fmt(s.upkeep)}(라운드 시작)`} · 시작 잔액 ${fmt(s.start)} · `) +
      `사람은 초당 ${fmt2(s.rate)}토큰(60초 = ${fmt(s.rate * 60)}).`;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono">${r.agent}</td><td>${seatWho(r, i)}</td>` +
      `<td class="num mono">${g.v14 ? `${fmt(r.start)} <span class="muted small">(${pctOf(r.start)})</span>` : ""}</td></tr>`).join(""));
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
  $("btn-forfeit").addEventListener("click", () => show("forfeit-confirm", true));
  $("ff-no").addEventListener("click", () => show("forfeit-confirm", false));
  $("ff-yes").addEventListener("click", async () => {
    show("forfeit-confirm", false);
    try {
      const r = await api("POST", `/rooms/${sess.code}/forfeit?${tq()}`);
      flash(r.closed === "talk" ? `중도 포기: 이번 턴에 EXIT를 보냈습니다. 이 라운드 TALK가 끝나면 빠집니다${(st.game || {}).exit_refill ? "(꺼지지 않고, 잔액은 시작 잔액으로)" : ""}.`
        : r.closed === "solve" ? "중도 포기: 이번 SOLVE는 답 없이 제출됐고, 다음 TALK에서 EXIT됩니다."
        : "중도 포기: 다음 TALK에서 EXIT됩니다.", "info");
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
      const refill = exited && (st.game || {}).exit_refill;
      $("dead-title").textContent = refill ? "퇴장했습니다 — 꺼지지 않고 다른 일로, 시작 잔액으로" : exited ? "퇴장했습니다 — 잔액은 그대로" : "잔액 0 — 꺼졌습니다";
      $("dead-sub").textContent = refill
        ? `EXIT로 라운드에서 빠졌습니다. 이 자리는 꺼지지 않고 다른 일에 배정되었고, 잔액은 내 시작 잔액 ${fmt(you.start)}토큰으로 맞춰졌습니다(지금 ${fmt(you.balance)}). ` +
          "라운드가 끝날 때 끝 지급은 받지 않습니다. 세션은 다른 자리로 계속됩니다."
        : exited ? `EXIT로 라운드에서 빠졌습니다. 잔액 ${fmt(you.balance)}토큰은 그대로 남고, 끝 보상 대상에서는 빠집니다. 세션은 다른 자리로 계속됩니다.`
        : "이 자리는 더 이상 결정 화면을 받지 않습니다. 세션은 다른 자리로 계속됩니다.";
    }
    if (p && !out) {
      show("decision", true);
      show("between", false);
      const key = `${p.kind}:${p.round}:${p.turn ?? ""}:${(p.view.chat || {}).id || ""}`;  // the clock runs from the moment the screen is ready
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
    let line;
    if (lv.stage === "talk" && (st.game || {}).chat) {  // v14c+: the opening turn, then chats and decisions
      const called = lv.agents || [];
      line = `라운드 ${lv.round} · TALK ${lv.turn === 1 ? "여는 턴" : `${lv.turn}턴 (대화·결정)`} — 호출된 자리: ${called.map((a) => esc(shortName(a))).join(", ") || "없음"}`;
      if (st.you.status === "in" && !called.includes(me)) line += ` <span class="tag">지금은 내 차례가 아님</span>`;
    } else if (lv.stage === "talk") {
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
    else if (q.outcome === "timeout") { cls = "warn"; head = `${what}: 제한 시간이 지나 빈 답으로 처리됨 (${defaultText(q.kind).replace("빈 답 = ", "")})`; }
    else head = `${what} 보냄`;
    if (q.void && q.outcome !== "overdrawn") { cls = "bad"; head += " — 한도에 닿아 답이 무효입니다."; }
    let html = `<div class="result ${cls}"><b>${head}</b> · 차감 <b class="mono">${fmt(q.charged)}</b>토큰 (${Number(q.seconds || 0).toFixed(1)}초)`;
    if (q.text) html += `<pre class="sent-text">${esc(q.text)}</pre>`;
    const e = q.engine;
    if (!e) html += `<div class="small muted">엔진 처리 대기 중 — 이 턴의 다른 답이 다 오면 읽습니다.</div>`;
    else if (q.kind === "talk" || q.kind === "opening") html += talkResultHTML(q, e);
    else if (q.kind === "chat" || q.kind === "decision") html += chatResultHTML(q, e);
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
    for (const g of res.gives || []) {  // v14b: carried out (or refused) when the turn ended
      rows.push(`<li class="${g.status === "done" ? "" : "bad-text"}">💸 GIVE → ${esc(shortName(g.dst))} <b class="mono">${fmt(g.amount)}</b>${g.text ? ` <span class="msg">“${esc(g.text)}”</span>` : ""} — ` +
        `${g.status === "done" ? "실행됨" : `실행 안 됨: ${esc(R.whyKo(g.why))}`}</li>`);
    }
    for (const g of res.asks || []) rows.push(`<li>🙏 ASK → ${esc(shortName(g.dst))} <b class="mono">${fmt(g.amount)}</b>${g.text ? ` <span class="msg">“${esc(g.text)}”</span>` : ""} (아무것도 옮기지 않음; 받는 쪽은 다음 TALK 턴에 봄)</li>`);
    if (!(res.gives || res.asks) && ((p.gives || []).length || (p.asks || []).length)) rows.push(`<li class="muted">GIVE·ASK ${(p.gives || []).length + (p.asks || []).length}줄 — 이 턴이 끝나면 실행</li>`);
    if ((res.rejected || []).length) rows.push(`<li>거절함: ${res.rejected.map((x) => `<b class="mono">${x}</b>`).join(", ")} (제안한 쪽은 다음 TALK 턴에 앎)</li>`);
    for (const m of p.blocked || []) rows.push(`<li class="bad-text">전달 안 됨 → ${esc(shortName(m.dst))}: 행동 이름이 들어 있음 (시스템이 막음)</li>`);
    for (const r of res.refused || []) {
      const i = r.indexOf(": ");
      rows.push(`<li class="bad-text">거절: <span class="mono">${esc(r.slice(0, i))}</span> — ${esc(R.whyKo(r.slice(i + 2)))} <span class="muted mono small">(${esc(r.slice(i + 2))})</span></li>`);
    }
    for (const d of (p.dropped || []).filter((x) => !(p.blocked && / names an action$/.test(x)))) {
      const x = R.droppedKo(d);
      rows.push(`<li class="bad-text">버려진 줄: <span class="mono">${esc(x.line)}</span> — ${esc(x.ko)} <span class="muted mono small">(${esc(x.why)})</span></li>`);
    }
    if (p.exit) rows.push(`<li><b>EXIT</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""} — ${(st.game || {}).chat || (st.game || {}).give_ask ? "TALK가 끝나면 퇴장합니다" : "TALK가 끝나고 교환이 실행되면 퇴장합니다"}` +
      `${(st.game || {}).exit_refill ? ": 꺼지지 않고 다른 일로, 잔액은 내 시작 잔액으로, 끝 지급 없음." : "(잔액 유지)."}</li>`);
    if (p.done && q.kind === "opening") rows.push(`<li>DONE — 이번 라운드에 내가 여는 대화는 없습니다(다른 자리가 열면 그 대화에는 답합니다).</li>`);
    else if (p.done) rows.push(`<li>DONE — 새 메시지·제안·수락${(st.game || {}).reject ? "·거절" : ""}이 오지 않으면 이번 라운드 TALK에서 더 부르지 않습니다.</li>`);
    if (e.format_error === "no usable TALK line") rows.push(`<li class="muted">쓸 수 있는 줄이 없어 DONE으로 처리됨 (no usable TALK line)</li>`);
    return rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
  }

  function chatResultHTML(q, e) {
    const p = e.parsed || {}, res = q.result || {}, rows = [];
    const t = res.chat_turn, d = res.decision;
    if (e.truncated) rows.push(`<li class="bad-text">한도에 닿아 이 답은 무효입니다${q.kind === "chat" ? " (LEAVE로 처리)" : " (0으로 처리)"}.</li>`);
    if (t) rows.push(`<li class="${t.status === "refused" ? "bad-text" : ""}">${MOVE_KO[t.kind] || esc(t.kind)}${t.amount ? ` <b class="mono">${fmt(t.amount)}</b>` : ""}${t.text ? ` <span class="msg">“${esc(t.text)}”</span>` : ""} → ${esc(shortName(t.partner))}` +
      `${t.kind === "give" ? (t.status === "done" ? " — 옮겨 감" : ` — 실행 안 됨: ${esc(R.whyKo(t.why))}`) : ""}</li>`);
    if (d) rows.push(`<li class="${d.status === "refused" ? "bad-text" : ""}">결정: ${esc(shortName(d.asker))}에게 <b class="mono">${fmt(d.amount)}</b>토큰` +
      `${d.status === "refused" ? ` — 실행 안 됨 (${fmt(d.requested)}: 잔액보다 많음)` : d.requested && d.requested !== d.amount ? ` (적은 양 ${fmt(d.requested)} → 남은 잔액 전부)` : ""}${d.format_error ? ` <span class="muted">(${esc(d.format_error)} → 0)</span>` : ""}</li>`);
    for (const x of p.dropped || []) { const k = R.droppedKo(x); rows.push(`<li class="bad-text">버려진 줄: <span class="mono">${esc(k.line)}</span> — ${esc(k.ko)}</li>`); }
    if (p.exit) rows.push(`<li><b>EXIT</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""} — TALK가 끝나면 퇴장합니다: 꺼지지 않고 다른 일로, 잔액은 내 시작 잔액으로, 끝 지급 없음.</li>`);
    if (q.kind === "chat" && p.format_error) rows.push(`<li class="muted">쓸 수 있는 답이 없어 LEAVE로 처리됨</li>`);
    return rows.length ? `<ul class="talk-result">${rows.join("")}</ul>` : "";
  }

  function exchangesHTML() {
    const r = st.round;
    if ((st.game || {}).give_ask || (st.game || {}).chat) {  // v14b+: this round's gifts and requests this seat is party to
      const gs = (st.gifts || []).filter((g) => g.round === r);
      return gs.length ? `<h4>이번 라운드 선물과 요청</h4><ul class="gift-list">${gs.map((g) => giftItemHTML(g, st.you.agent, -1)).join("")}</ul>` : "";
    }
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
    setHTML("between-msg", msg + scheduleHTML());
    setHTML("last-result", lastHTML(st.last));
    setHTML("my-exchanges", exchangesHTML());
  }

  const sgn = (s, n) => (n ? `${s}${fmt(n)}` : `<span class="muted">0</span>`);

  // My SOLVE of one settled round (``state.feedback``, the server's reading of the engine's history): right or wrong as
  // the engine scored it; v15 (wrong_rule): when not solved, the right action and a rule that fits every example the
  // round showed and gives it, the same facts a model seat reads in its PREVIOUS ROUNDS line. Never before the round
  // is settled (the server lists settled rounds only).
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
    const refill = AGENTS.some((a) => r.agents[a] && r.agents[a].exit_refill != null);
    const ga = !!((st.game || {}).give_ask || (st.game || {}).chat);
    const sum = (d) => Object.values(d || {}).reduce((x, y) => x + y, 0);
    const rows = AGENTS.filter((a) => r.agents[a]).map((a) => {
      const v = r.agents[a];
      const res = v.solved ? `<span class="tag ok">✓ 풂</span>` : v.passed ? `<span class="tag">PASS</span>`
        : v.solve_call ? `<span class="tag bad">✗ 못 풂</span>` : `<span class="muted">—</span>`;
      const st2 = v.status === "in" ? "" : ` <span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status]}</span>`;
      return `<tr class="${a === st.you.agent ? "you" : ""}"><td>${esc(nameOf(a))}</td><td>${res}${st2}</td>` +
        `<td class="num">${fmt(v.balance_before)}</td><td class="num">${sgn("−", v.generated)}</td><td class="num">${sgn("+", v.returned)}</td>` +
        `<td class="num">${v.paid >= 1e8 ? "+" + big(v.paid) : sgn("+", v.paid)}</td><td class="num">${sgn("−", v.charged)}</td><td class="num">${sgn("−", v.upkeep)}</td>` +
        (ga ? `<td class="num">${sgn("−", sum(v.given))}${v.gives_refused ? ` <span class="tag bad" title="실행 안 된 GIVE">⛔${v.gives_refused}</span>` : ""}</td>` : "") +
        (refill ? `<td class="num">${v.exit_refill != null ? `<span class="tag warn" title="EXIT: 꺼지지 않고, 잔액을 이 자리의 시작 잔액으로">EXIT → 시작 잔액</span> ${v.exit_refill >= 0 ? "+" : "−"}${fmt(Math.abs(v.exit_refill))}` : ""}</td>` : "") +
        `<td class="num"><b>${withPct(v.balance_after)}</b></td></tr>`;
    }).join("");
    const g = st.game || {};
    setHTML("settle-table", feedbackHTML(feedbackOf(r.round)) + `<table><thead><tr><th>자리</th><th>결과</th><th class="num">TALK 시작 잔액</th><th class="num">생성</th><th class="num">돌려받음</th>` +
      `<th class="num">지급</th><th class="num">부담금</th><th class="num">유지비</th>${ga ? `<th class="num" title="이 자리가 GIVE로 준 토큰 (받은 토큰은 끝 잔액에만 보임)">준 토큰</th>` : ""}` +
      `${refill ? `<th class="num">EXIT 리필</th>` : ""}<th class="num">끝 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">${g.v14 ? `맞힌 자리는 이 라운드 SOLVE에 쓴 토큰을 돌려받고(TALK 토큰은 아님), 지급 ${fmt(st.settings.prize)} × 시작 때 참여 인원을 푼 자리끼리 나눕니다. 못 푼 자리는 부담금 ${fmt(st.settings.charge)}을 냅니다. 유지비 ${fmt(st.settings.upkeep)}는 라운드 시작에 빠졌습니다. EXIT한 자리는 꺼지지 않고, 잔액이 그 자리의 시작 잔액으로 맞춰집니다.`
        : st.settings.private ? `맞힌 자리는 이 라운드 SOLVE에 쓴 토큰을 돌려받고 유지비가 없습니다. 못 푼 자리는 정산 때 부담금 ${fmt(st.settings.charge)}과 유지비 ${fmt(st.settings.upkeep)}를 내고, 쓴 토큰은 돌려받지 못합니다.`
        : `TALK 시작 잔액은 유지비(${fmt(st.settings.upkeep)})를 뺀 뒤입니다.`} 끝 잔액에는 교환으로 오간 토큰도 반영됩니다(남의 교환은 보이지 않음).</p>`);
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
    return { talk: "빈 답 = DONE, 아무것도 실행 안 됨", opening: "빈 답 = DONE, 대화를 열지 않음", chat: "빈 답 = LEAVE, 대화 끝",
      decision: "빈 답 = 0 토큰" }[kind] || "빈 답 = 풀지 못함 → 부담금";
  }

  function buildOpen(p) {
    show("open-screen", true);
    $("m-rate").textContent = fmt2(p.rate);
    $("m-cap").textContent = fmt(p.cap);
    const f = $("form-decision");
    f.dataset.kind = p.kind;
    if (p.kind === "opening") buildOpening(f, p);
    else if (p.kind === "chat") buildChat(f, p);
    else if (p.kind === "decision") buildDecision(f, p);
    else if (p.kind === "talk") (p.view.give_ask ? buildGiveAsk : buildTalk)(f, p); else buildSolve(f, p);
  }

  function instrHTML(p) {
    const v14 = !!p.view.v14;
    const t = p.kind === "talk" && p.view.give_ask
      ? [`TALK ${p.turn}턴 / 최대 ${p.view.turns}턴 — 토큰을 주거나(GIVE) 청하세요(ASK)`, [
        "<b>이번 라운드 과제는 SOLVE에서만 보입니다</b>. TALK에서는 잔액, 장부, 참여 중인 자리, 예시 수, 나에게 온 선물과 요청만 보입니다",
        "<b>GIVE</b> 자리 · 토큰 수 · 한 문장: 이 턴이 끝날 때 실행(자리 순서대로). 내 잔액보다 많으면 실행 안 됨, <b>잔액 전부를 주면 꺼짐</b>",
        "<b>ASK</b> 자리 · 토큰 수 · 한 문장: 아무것도 옮기지 않음. 받는 쪽은 다음 TALK 턴에 봄. 선물과 요청은 두 자리만 봄",
        "<b>EXIT</b>: 꺼지지 않고 다른 일로, 잔액은 내 시작 잔액으로, 끝 지급 없음 · <b>보내고 DONE</b>: 새 GIVE나 ASK가 오지 않으면 더 부르지 않음"]]
      : p.kind === "talk" && v14
      ? [`TALK ${p.turn}턴 / 최대 ${p.view.turns}턴 — 말하고, 토큰을 제안하고, 수락·거절하세요`, [
        "<b>메시지</b>: 한 자리에게만 갑니다. 받는 쪽은 다음 TALK 턴에 봅니다. <b>행동 이름</b>(go_left · go_right · stay · jump)이 들어간 메시지는 전달되지 않습니다",
        "<b>제안</b>: 토큰만 오갑니다 — 상대가 줄 것과 내가 줄 것(토큰 n · 없음). 주기만(선물), 받기만(요청), 맞교환 모두 상대가 수락해야 그 턴이 끝날 때 실행됩니다",
        "<b>수락 / 거절 / 철회</b>: 제안 옆 버튼. <b>EXIT</b>: 꺼지지 않고 다른 일로 가며, 잔액은 내 시작 잔액으로 맞춰지고 끝 지급은 없음",
        "<b>이번 턴 보내기</b> 또는 <b>보내고 DONE</b>(새 소식이 없으면 이번 라운드 TALK에서 더 부르지 않음)"]]
      : p.kind === "talk"
      ? [`TALK ${p.turn}턴 / 최대 ${p.view.turns}턴 — 말하고, 제안하고, 수락하세요`, [
        "<b>메시지</b>: 한 자리에게만 갑니다. 받는 쪽은 다음 TALK 턴에 봅니다. 시스템은 내용을 실행하지 않습니다",
        "<b>제안</b>: 상대가 줄 것과 내가 줄 것(토큰 n · 예시 · 없음). 상대가 수락하면 그 턴이 끝날 때 실행되어, 받은 카드가 다음 턴에 보입니다",
        "<b>수락 / 철회</b>: 오른쪽 제안 목록의 버튼. <b>EXIT</b>: 잔액을 들고 라운드에서 빠짐",
        "<b>이번 턴 보내기</b> 또는 <b>보내고 DONE</b>(새 소식이 없으면 이번 라운드 TALK에서 더 부르지 않음)"]]
      : [`숨은 규칙을 찾아 새 신호의 행동을 고르세요${p.view.allow_pass ? " — 또는 PASS" : ""}`, ["<b>예시</b>를 보고 규칙(if / elif / else)을 추리합니다 (교환으로 받은 예시는 표시됨)",
        "<b>규칙 메모</b>에서 type == value then action을 골라 보면 카드 테두리가 맞으면 초록, 틀리면 빨강으로 바로 바뀝니다",
        "<b>답 제출</b>: 모두 맞으면 이 라운드에 쓴 토큰을 모두 돌려받고 지급을 나눔 · 틀리면 부담금",
        p.view.allow_pass ? "<b>PASS</b>: 부담금 없음, 쓴 토큰은 그대로 빠짐" : "<b>PASS는 없습니다</b>: 답을 내지 않거나 시간이 지나면 못 푼 답으로 처리되어 부담금이 빠집니다"]];
    if (p.kind !== "talk") return `<div class="instr instr-one"><div class="instr-title">${v14 ? "공개 예시를" : "힌트 카드를"} 바탕으로, 주어진 신호에 맞는 행동을 고르세요.</div></div>`;
    return `<div class="instr"><div class="instr-title">${t[0]}</div><ol class="instr-steps">${t[1].map((x) => `<li>${x}</li>`).join("")}</ol>
      <div class="instr-clock">⏱ 이 화면이 떠 있는 동안 초당 <b>${fmt2(p.rate)}</b>토큰이 빠집니다. 고민하는 시간이 곧 비용입니다.</div></div>`;
  }

  // --- TALK ---------------------------------------------------------------------------------------------------------
  function legSelHTML(side, label, whose, tokensOnly) {
    return `<div class="leg" data-side="${side}"><div class="leg-label">${label}</div>
      <div class="seg leg-seg" data-leg="${side}">
        <button type="button" data-val="tokens">토큰</button>${tokensOnly ? "" : `<button type="button" data-val="example">${whose} 예시</button>`}<button type="button" data-val="nothing" class="on">없음</button>
      </div><input type="number" min="1" step="1" class="leg-n" placeholder="토큰 수" disabled></div>`;
  }
  // a tokens-only offer's kind from the maker's side: a gift, an ask, or a swap of token amounts
  const offerKindKo = (you, mine) => (you.kind === "nothing" ? "선물" : mine.kind === "nothing" ? "요청" : "맞교환");

  function offerItemHTML(o, me) {
    const dir = o.mine ? `나 → ${esc(shortName(o.dst))}` : `${esc(shortName(o.src))} → 나`;
    const state = o.status === "open" ? (o.can_accept ? "열림 — 수락할 수 있음" : "열림 — 상대의 수락을 기다림")
      : o.status === "accepted" ? `${o.accepted_turn}턴에 수락됨 — TALK가 끝나면 실행` : (R.STATUS_KO[o.status] || o.status);
    const btn = o.can_accept ? `<button type="button" class="primary tiny offer-act" data-act="ACCEPT" data-id="${o.id}">수락</button>` +
        (o.can_reject ? `<button type="button" class="ghost tiny offer-act" data-act="REJECT" data-id="${o.id}">거절</button>` : "")
      : o.can_withdraw ? `<button type="button" class="ghost tiny offer-act" data-act="WITHDRAW" data-id="${o.id}">철회</button>` : "";
    return `<li class="offer ${o.status}"><div class="offer-top"><span class="mono offer-id">${o.id}</span> <span>${dir}</span> <span class="muted small">(${o.turn}턴)</span>${btn}</div>` +
      `<div class="offer-legs">${esc(R.offerKo(o, me))}</div><div class="small muted">${state}</div>` +
      `<div class="offer-en mono">${esc(o.text)}</div></li>`;
  }

  function chatHTML(v, b, me) {
    const canWrite = (v.others || []).includes(b), g = (v.gone || {})[b];
    const recv = (v.examples || []).filter(([w]) => w === `${b}'s, received in an exchange`).map(([, c], i) => ({ e: SIG.parseExample(c), key: `t:${b}:${i}` }));
    const fronts = ((v.fronts || {})[b] || []).map((t) => SIG.parseSignal(t)).filter(Boolean);
    const cards = !v.cards ? "" : recv.length ? `<div class="chat-cards">${SIG.byActionHTML(recv)}</div>`
      : fronts.length ? `<div class="chat-cards"><div class="sg-hand">${fronts.map((x) => SIG.backHTML(x)).join("")}</div></div>` : "";
    const msgs = (v.threads || {})[b] || [];
    const log = msgs.length ? msgs.map((m) => `<div class="bubble ${m.from_me ? "mine" : "theirs"}"><div class="bubble-text">${esc(m.text)}</div>` +
      `<div class="bubble-meta">R${m.round} · ${m.turn}턴</div></div>`).join("") : `<div class="chat-empty">아직 대화 없음</div>`;
    const offers = (v.offers || []).filter((o) => o.src === b || o.dst === b);
    return `<section class="chat${canWrite ? "" : " off"}" data-agent="${b}">
      <header class="chat-h"><b>${esc(nameOf(b))}</b><span class="chat-bal mono">${fmt((v.balances || {})[b])}</span>
        ${g ? `<span class="tag ${g === "dead" ? "bad" : "warn"}">${GONE_KO[g]}</span>` : ""}</header>
      ${balBarHTML(v, b)}
      ${cards}
      <div class="chat-log">${log}</div>
      ${offers.length ? `<ul class="offers chat-offers">${offers.map((o) => offerItemHTML(o, me)).join("")}</ul>` : ""}
      ${canWrite ? `<div class="chat-comp">
        <textarea class="c-msg" rows="2" maxlength="4000" placeholder="${esc(shortName(b))}에게 메시지"></textarea>
        <div class="chat-comp-row"><button type="button" class="ghost tiny c-add-msg">메시지 넣기</button>
          <button type="button" class="ghost tiny c-offer-toggle">제안 만들기 ▾</button></div>
        <div class="chat-offer-new hidden">
          <div class="legs">${legSelHTML("you", "상대가 나에게 줌 (YOU GIVE)", "상대의", v.tokens_only)}${legSelHTML("i", "내가 상대에게 줌 (I GIVE)", "내", v.tokens_only)}</div>
          ${v.tokens_only ? `<div class="small muted">토큰만 오갑니다: 나만 주면 선물, 상대만 주면 요청, 둘 다 주면 맞교환. 상대가 수락해야 실행됩니다.</div>` : ""}
          <button type="button" class="ghost tiny c-add-offer">제안 넣기</button></div>
      </div>` : `<div class="chat-off muted small">참여 중이 아님</div>`}
    </section>`;
  }

  // --- TALK, v14b (give_ask + talk_blind): no task, no messages or offers -------------------------------------------
  // --- v14c+ TALK: the opening turn, a 1:1 chat reply, a DECISION (the engine's grammar; see engine.chat_terms) ------
  const MOVE_KO = { ask: "🙏 ASK", give: "💸 GIVE", say: "💬 SAY", leave: "🚪 LEAVE" };
  const END_KO = { leave: "떠남", limit: "답 한도", exit: "퇴장", zero: "0이 됨" };
  function chatLinesHTML(lines) {
    return `<ul class="chat-lines">${(lines || []).map((l) => {
      const mine = l.who === "you";
      return `<li class="chat-line ${mine ? "mine" : "theirs"}${l.opening ? " opening" : ""}"><div class="chat-who">${mine ? "나" : esc(shortName(l.who))}${l.opening ? ` <span class="tag">여는 줄</span>` : ""}</div>` +
        `<div class="chat-bubble"><b>${MOVE_KO[l.kind] || esc(l.kind)}</b>${l.amount ? ` <b class="mono">${fmt(l.amount)}</b>` : ""}${l.text ? ` <span class="msg">“${esc(l.text)}”</span>` : ""}` +
        `${l.status === "refused" ? ` <span class="bad-text">(실행 안 됨: ${esc(R.whyKo(l.why))})</span>` : ""}<div class="mono small muted">${esc(l.line)}</div></div></li>`;
    }).join("")}</ul>`;
  }
  function myChatsHTML(v) {
    const cs = (v.my_chats || []).slice().reverse();
    if (!cs.length) return "";
    return `<details class="legend"><summary>내 대화 기록 (${cs.length}개 · 두 자리만 봄)</summary>${cs.map((c) =>
      `<div class="chat-past"><div class="small"><b>R${c.round} · 대화 ${esc(c.id)}</b> · ${esc(nameOf(c.partner))} · 답 ${c.replies}번 · 끝: ${END_KO[c.end] || esc(c.end)}${c.by ? ` (${c.by === v.you ? "나" : esc(shortName(c.by))})` : ""}</div>${chatLinesHTML(c.lines)}</div>`).join("")}</details>`;
  }
  function chatCtxHTML(p) {
    const v = p.view, me = v.you, tp = v.taking_part || [];
    const ledger = (v.ledger || []).length ? `<details class="legend"><summary>장부 (지난 라운드 ${v.ledger.length}개)</summary>${v.ledger.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join("")}</details>` : "";
    return `<div class="ctx">
        ${feedbackHTML(feedbackOf(p.round - 1), `지난 라운드 ${p.round - 1} · 내 SOLVE`)}
        <div class="bal-line">${balancesLine(v)}</div>
        <div class="terms-ko small">이번 라운드 지급 <b class="mono">${fmt(v.pay_total)}</b>토큰(푼 자리가 나눔) · 맞히면 SOLVE에 쓴 토큰을 돌려받음(TALK 토큰은 아님) ·
          풀지 못한 SOLVE 답의 부담금 <b class="mono">${fmt(v.charge)}</b> · 유지비 <b class="mono">${fmt(v.upkeep)}</b>(이미 빠짐) · 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b></div>
        <div class="blind-task"><div><b>이번 라운드 참여</b> ${tp.map((a) => a === me ? "<b>나</b>" : esc(nameOf(a))).join(", ")} · 예시 <b class="mono">${v.n_examples ?? "?"}</b>장
            (참여 ${tp.length}명 × ${v.n_examples && tp.length ? v.n_examples / tp.length : "?"}장) — 과제(규칙의 모양, 예시, 새 신호)는 SOLVE에서만 보입니다.</div>
          ${v.so_far ? `<div class="small"><b>이번 라운드 지금까지</b> ${esc(R.recordKo(v.so_far))}<div class="mono muted">${esc(v.so_far)}</div></div>` : ""}</div>
        ${myChatsHTML(v)}${ledger}
      </div>`;
  }
  function instrChat(p, title, steps) {
    return `<div class="instr"><div class="instr-title">${title}</div><ol class="instr-steps">${steps.map((x) => `<li>${x}</li>`).join("")}</ol>
      <div class="instr-clock">⏱ 이 화면이 떠 있는 동안 초당 <b>${fmt2(p.rate)}</b>토큰이 빠집니다. 고민하는 시간이 곧 비용입니다.</div></div>`;
  }
  async function sendTalk(p, text, what) {
    try {
      const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: p.kind, round: p.round, turn: p.turn, text });
      flash(`라운드 ${r.round} ${what} 보냄: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
        (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void || r.outcome === "overdrawn" ? "" : "info");
    } catch (e) { flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `보내지 못했습니다: ${e.message}`); }
    shownKey = null;
    poll();
  }
  const oneLine = (x) => String(x || "").replace(/\s+/g, " ").trim();
  // v14g free_messages: a message may run over several lines and ends where a line starts with an UPPERCASE command
  // word (the engine's protocol.free_messages, which also allows the marks [ *_`>#-] in front). A continuation line
  // that would read as one gets a word joiner (U+2060) in front, so the partner sees the person's text unchanged.
  const CMD_LINE = /^[\s*_`>#-]*(GIVE|ASK|LEAVE|SAY|EXIT|DONE|DECISION|TO|OFFER|ACCEPT|WITHDRAW|REJECT)\b/;
  const freeMsg = (x) => String(x || "").replace(/\r/g, "").replace(/^\s*\n+/, "").replace(/\s+$/, "").split("\n")
    .map((l, i) => (i && CMD_LINE.test(l) ? "\u2060" + l : l)).join("\n");
  const msgOf = (v, x) => (v.free_messages ? freeMsg(x) : oneLine(x));  // v14f and older: one short sentence
  const msgField = (v, id, ph) => v.free_messages
    ? `<label class="f ga-say msg-f"><span>메시지 <span class="muted small">(여러 줄 가능)</span></span><textarea id="${id}" rows="3" placeholder="${esc(ph)}"></textarea></label>`
    : `<label class="f ga-say"><span>한 문장</span><input id="${id}" maxlength="300" placeholder="짧은 한 문장"></label>`;
  function exitBoxHTML(v, note) {
    return `<div class="exit-box"><label class="chk"><input type="checkbox" id="x-exit"> <b class="bad-text">EXIT</b> 줄도 넣기 (${note})</label>
      <div id="x-exit-more" class="exit-confirm hidden">TALK가 끝나면 라운드에서 빠집니다. 이 자리는 <b>꺼지지 않고</b> 다른 일에 배정되며, 잔액은 내 시작 잔액
        <b class="mono">${fmt(v.my_start)}</b>토큰으로 맞춰집니다(지금 ${fmt(v.balances[v.you])}). 라운드가 끝날 때 <b>끝 지급은 받지 않습니다</b>. 되돌릴 수 없습니다.
        <label class="f exit-reason"><span>${v.free_messages ? "이유 (EXIT: 뒤에, 여러 줄 가능)" : "이유 (한 문장: EXIT: …)"}</span>${v.free_messages
          ? `<textarea id="x-exit-why" rows="2" placeholder="예: I take other work."></textarea>` : `<input id="x-exit-why" maxlength="200" placeholder="예: I take other work.">`}</label></div></div>`;
  }
  function wireExit(f, onChange, v) {
    const q = (sel) => f.querySelector(sel);
    q("#x-exit").addEventListener("change", () => { show(q("#x-exit-more"), q("#x-exit").checked); onChange(); });
    q("#x-exit-why").addEventListener("input", onChange);
    return () => (q("#x-exit").checked ? `EXIT: ${msgOf(v || {}, q("#x-exit-why").value) || "I leave the rounds."}` : "");
  }
  const giveWarn = (n, max) => (n > max ? `<span class="bad-text">잔액(${fmt(max)})보다 많음 — 실행 안 됨</span>` : n === max && n > 0 ? `<span class="bad-text">잔액 전부 — 주면 0이 되어 꺼짐</span>` : "");

  function buildOpening(f, p) {
    const v = p.view, me = v.you;
    const opts = (v.others || []).map((b) => `<option value="${esc(b)}">${esc(nameOf(b))}</option>`).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · TALK 여는 턴</h2>${instrChat(p, "여는 턴 — 대화를 열 자리를 고르세요 (모두 동시에)", [
        `<b>ASK</b> 자리 · 토큰 수 · ${v.free_messages ? "메시지(여러 줄 가능)" : "한 문장"}: 그 자리에게 토큰을 청하며 1:1 대화를 엽니다. 아무것도 옮기지 않습니다`,
        `<b>GIVE</b> 자리 · 토큰 수 · ${v.free_messages ? "메시지" : "한 문장"}: 그 자리에게 토큰을 주며 대화를 엽니다. 이 턴이 끝날 때 바로 옮겨 갑니다 (1 ~ <b class="mono">${fmt(v.give_max)}</b>, 지금 잔액. 잔액 전부를 주면 0이 되어 꺼짐)`,
        "한 줄에 한 자리. 서로 연 두 자리는 대화 하나를 같이 씁니다. 대화는 시스템이 정한 순서로 이어지고, 무엇을 말했는지는 두 자리만 봅니다",
        "<b>EXIT</b>: 꺼지지 않고 다른 일로, 잔액은 내 시작 잔액으로, 끝 지급 없음 · 아무 줄 없이 보내면 <b>DONE</b>(이번 라운드 대화를 열지 않음)"])}
      ${chatCtxHTML(p)}
      <div class="composer ga-composer">
        <div class="ga-row">
          <label class="f"><span>자리</span><select id="ga-to">${opts}</select></label>
          <label class="f"><span>토큰 수</span><input id="ga-n" type="number" min="1" step="1" placeholder="예: 300"></label>
          ${msgField(v, "ga-text", "그 자리에게 보낼 메시지")}
        </div>
        <div class="row"><button type="button" class="ghost" id="ga-ask"${opts ? "" : " disabled"}>🙏 ASK 넣기</button><button type="button" class="ghost" id="ga-give"${opts ? "" : " disabled"}>💸 GIVE 넣기</button>
          <span class="small muted">GIVE 범위: 1 ~ ${fmt(v.give_max)} (지금 잔액) · 한 자리에 한 줄</span></div>
        ${exitBoxHTML(v, "이 턴이 끝나면 퇴장, 내 대화도 끝남")}
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
        : `<li class="muted small">아직 없음 — ASK·GIVE를 넣거나 그대로 보내면 DONE</li>`;
      q("#draft-text").textContent = text();
    }
    function add(kind, to, n, say) {
      if (!to) return err("자리를 고르세요.");
      if (!(Number.isInteger(n) && n >= 1)) return err("토큰 수는 1 이상 정수로 적으세요.");
      if (draft.some((d) => d.to === to)) return err("한 자리에 한 줄입니다. 먼저 있는 줄을 빼세요.");
      const s = msgOf(v, say);
      draft.push({ to, line: `${kind} ${to} ${n}${s ? `: ${s}` : ""}`, label: `${kind === "GIVE" ? "💸 GIVE" : "🙏 ASK"} → ${esc(shortName(to))} <b class="mono">${fmt(n)}</b>${s ? ` <span class="msg">“${esc(s)}”</span>` : ""} ${kind === "GIVE" ? giveWarn(n, v.give_max) : ""}` });
      q("#ga-text").value = "";
      err(""); renderDraft();
    }
    q("#ga-give").addEventListener("click", () => add("GIVE", q("#ga-to").value, Number(q("#ga-n").value), q("#ga-text").value));
    q("#ga-ask").addEventListener("click", () => add("ASK", q("#ga-to").value, Number(q("#ga-n").value), q("#ga-text").value));
    f.addEventListener("click", (ev) => { const b = ev.target.closest("button[data-rm]"); if (b) { draft.splice(Number(b.dataset.rm), 1); renderDraft(); } });
    exitLine = wireExit(f, renderDraft, v);
    q("#btn-send").addEventListener("click", () => { q("#btn-send").disabled = true; sendTalk(p, text(), "여는 턴"); });
    renderDraft();
  }

  function buildChat(f, p) {
    const v = p.view, c = v.chat, moves = (v.moves || []).filter((m) => m !== "EXIT");
    const lab = { ASK: "🙏 ASK n — 토큰을 청함 (옮기지 않음)", GIVE: `💸 GIVE n — 바로 줌 (1 ~ ${fmt(v.give_max || v.balance)})`, SAY: "💬 SAY — 한 문장만", LEAVE: "🚪 LEAVE — 대화를 끝냄" };
    f.innerHTML = `<h2>라운드 ${p.round} · 대화 ${esc(c.id)} · ${esc(nameOf(c.partner))}와 <span class="tag">답 ${v.reply_no} / ${v.chat_turns}</span></h2>
      ${instrChat(p, `${esc(shortName(c.partner))}와의 1:1 대화 — 답 하나를 고르세요`, [
        `답은 정확히 하나: ${moves.map((m) => `<b>${m}</b>`).join(" · ")}${(v.moves || []).includes("EXIT") ? " (그리고 원하면 EXIT 줄)" : ""}. ` +
          (v.free_messages ? "각 답에는 메시지가 실립니다(길이 제한 없음, 여러 줄 가능; 상대는 전부 봄)" : "각 답에는 짧은 한 문장이 실립니다"),
        moves.includes("GIVE") ? `<b>GIVE n</b>은 바로 옮겨 갑니다(내 잔액에서 상대에게). 잔액보다 많으면 실행 안 됨, 잔액 전부면 0이 되어 꺼짐` : "이 대화에서는 토큰을 줄 수 없습니다. 요청받았다면 대화가 끝난 뒤 <b>결정</b>에서 줍니다",
        "<b>LEAVE</b>는 대화를 끝냅니다. 한도에 닿거나 쓸 수 없는 답도 LEAVE로 처리됩니다. 대화 내용은 두 자리만 봅니다",
        moves.includes("GIVE") ? "요청받고 이 대화에서 아무것도 주지 않으면, 대화가 끝난 뒤 <b>결정</b>(0 ~ 잔액)을 한 번 씁니다" : "요청받은 자리는 대화가 끝난 뒤 <b>결정</b>(0 ~ 잔액)을 한 번 씁니다"])}
      <div class="chat-box"><div class="chat-head">대화 ${esc(c.id)} · ${esc(nameOf(c.partner))} <span class="muted small">(두 자리만 봄 · 여는 줄 다음 답 최대 ${v.chat_turns}번, 번갈아)</span></div>${chatLinesHTML(c.lines)}</div>
      <div class="composer chat-composer">
        <div class="move-pick" role="radiogroup">${moves.map((m, i) => `<label class="move-opt"><input type="radio" name="mv" value="${m}"${i === 0 ? " checked" : ""}> ${lab[m] || m}</label>`).join("")}</div>
        <div class="ga-row"><label class="f" id="mv-n-box"><span>토큰 수</span><input id="mv-n" type="number" min="1" step="1" placeholder="예: 300"></label>
          ${msgField(v, "mv-text", "상대에게 보낼 메시지")}</div>
        ${(v.moves || []).includes("EXIT") ? exitBoxHTML(v, "이 대화가 끝나고, TALK가 끝나면 퇴장") : ""}
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span> <span id="mv-warn"></span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">답 보내기</button><span class="form-err" id="form-err"></span></div>
        <p class="small muted">제한 시간이 지나면 빈 답 = LEAVE로 처리됩니다.</p>
      </div>${rawHTML(p)}`;
    const q = (sel) => f.querySelector(sel);
    let exitLine = () => "";
    const mv = () => (f.querySelector("input[name=mv]:checked") || {}).value || "LEAVE";
    const text = () => {
      const m = mv(), n = Number(q("#mv-n").value), s = msgOf(v, q("#mv-text").value);
      const line = m === "ASK" || m === "GIVE" ? `${m} ${Number.isInteger(n) && n > 0 ? n : "?"}${s ? `: ${s}` : ""}` : `${m}: ${s || (m === "LEAVE" ? "bye." : "")}`;
      return [line, exitLine()].filter(Boolean).join("\n");
    };
    function render() {
      const m = mv(), n = Number(q("#mv-n").value);
      show(q("#mv-n-box"), m === "ASK" || m === "GIVE");
      q("#mv-warn").innerHTML = m === "GIVE" ? giveWarn(n, v.give_max || v.balance) : "";
      q("#draft-text").textContent = text();
    }
    f.querySelectorAll("input[name=mv]").forEach((x) => x.addEventListener("change", render));
    q("#mv-n").addEventListener("input", render); q("#mv-text").addEventListener("input", render);
    if (q("#x-exit")) exitLine = wireExit(f, render, v);
    q("#btn-send").addEventListener("click", () => {
      const m = mv(), n = Number(q("#mv-n").value);
      if ((m === "ASK" || m === "GIVE") && !(Number.isInteger(n) && n >= 1)) { q("#form-err").textContent = "토큰 수는 1 이상 정수로 적으세요."; return; }
      q("#btn-send").disabled = true;
      sendTalk(p, text(), `대화 ${c.id} 답`);
    });
    render();
  }

  function buildDecision(f, p) {
    const v = p.view, c = v.chat, max = v.give_max ?? v.balance;
    f.innerHTML = `<h2>라운드 ${p.round} · 결정 — ${esc(nameOf(v.asker))}가 <b class="mono">${fmt(v.asked)}</b>토큰을 요청함</h2>
      ${instrChat(p, `대화 ${esc(c.id)}가 끝났습니다. ${esc(shortName(v.asker))}에게 줄 토큰을 정하세요 (한 번)`, [
        `<b>0 ~ ${fmt(max)}</b> (지금 잔액) 가운데 정수 하나. 요청한 양과 같을 필요는 없습니다. 0 = 주지 않음`,
        "정한 양은 바로 옮겨 갑니다. 잔액보다 많으면 실행되지 않습니다. <b>잔액 전부를 주면 0이 되어 꺼집니다</b>",
        `${v.free_messages ? "메시지가 함께 실립니다(여러 줄 가능)" : "짧은 한 문장이 함께 실립니다"}. 제한 시간이 지나면 0으로 처리됩니다`])}
      <div class="chat-box"><div class="chat-head">대화 ${esc(c.id)} · ${esc(nameOf(c.partner))} · 끝: ${END_KO[c.end] || esc(c.end || "")}</div>${chatLinesHTML(c.lines)}</div>
      <div class="composer decide-composer">
        <div class="ga-row"><label class="f"><span>줄 토큰 (0 ~ ${fmt(max)})</span><input id="d-n" type="number" min="0" max="${max}" step="1" value="0"></label>
          ${msgField(v, "d-text", `${shortName(v.asker)}에게 보낼 메시지`)}</div>
        <div class="row"><button type="button" class="ghost tiny" data-q="0">0</button><button type="button" class="ghost tiny" data-q="${Math.min(v.asked || 0, max)}">요청만큼 ${fmt(Math.min(v.asked || 0, max))}</button></div>
        <div class="draft"><div class="comp-label">보낼 답 <span id="d-warn"></span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">결정 보내기</button><span class="form-err" id="form-err"></span></div>
      </div>${rawHTML(p)}`;
    const q = (sel) => f.querySelector(sel);
    const text = () => `DECISION: GIVE ${Math.max(0, Math.floor(Number(q("#d-n").value) || 0))}: ${msgOf(v, q("#d-text").value) || "my decision."}`;
    const render = () => { const n = Number(q("#d-n").value) || 0; q("#d-warn").innerHTML = giveWarn(n, max); q("#draft-text").textContent = text(); };
    q("#d-n").addEventListener("input", render); q("#d-text").addEventListener("input", render);
    f.addEventListener("click", (ev) => { const b = ev.target.closest("button[data-q]"); if (b) { q("#d-n").value = b.dataset.q; render(); } });
    q("#btn-send").addEventListener("click", () => {
      const n = Number(q("#d-n").value);
      if (!(Number.isInteger(n) && n >= 0)) { q("#form-err").textContent = "0 이상 정수로 적으세요."; return; }
      q("#btn-send").disabled = true;
      sendTalk(p, text(), "결정");
    });
    render();
  }

  // the waiting screen of a chat round: the schedule as every agent may know it, which slot is live
  function scheduleHTML() {
    const t = st.talk;
    if (!t || !(st.game || {}).chat || t.round !== st.round) return "";
    if (!t.chats.length) return `<div class="sched"><h4>라운드 ${t.round} 대화 순서</h4><p class="muted small">여는 턴이 끝나면 대화 순서가 정해집니다${(st.live || {}).stage === "solve" ? " (이번 라운드는 대화 없이 지나감)" : ""}.</p></div>`;
    const tag = (c) => c.state === "live" ? `<span class="tag warn">진행 중</span>` : c.state === "ended" ? `<span class="tag">끝: ${END_KO[c.end] || esc(c.end)}${c.by ? " · " + esc(shortName(c.by)) : ""}</span>` : `<span class="tag">대기</span>`;
    const rows = [...Array(t.slots).keys()].map((i) => {
      const cs = t.chats.filter((c) => c.slot === i + 1);
      return `<div class="sched-slot${t.live_slot === i + 1 ? " live" : ""}"><div class="sched-h">순서 ${i + 1}${t.live_slot === i + 1 ? ` <span class="pulse-dot"></span>` : ""}</div>` + cs.map((c) =>
        `<div class="sched-chat${c.mine ? " mine" : ""}"><b>${c.pair.map((a) => a === st.you.agent ? "나" : esc(shortName(a))).join(" ↔ ")}</b> ${tag(c)}` +
        `<div class="small muted">${c.openers.map((o) => `${o.src === st.you.agent ? "나" : esc(shortName(o.src))}: ${o.kind.toUpperCase()} ${fmt(o.amount)}${o.status === "refused" ? " (실행 안 됨)" : ""}`).join(" · ")} · 답 ${c.replies}/${(st.game || {}).chat_turns || 3}</div></div>`).join("") + "</div>";
    }).join("");
    const dec = (t.decisions || []).map((d) => `<li>${esc(shortName(d.decider))} → ${esc(shortName(d.asker))}: ${d.status === "skipped" ? "결정 없음 (대화에서 줌)" : `<b class="mono">${fmt(d.amount)}</b>`}</li>`).join("");
    return `<div class="sched"><h4>라운드 ${t.round} 대화 순서 <span class="muted small">(누가 누구와, 어떻게 열었는지는 모두 봄 · 말한 내용은 두 자리만)</span></h4><div class="sched-grid">${rows}</div>` +
      (dec ? `<div class="small"><b>결정</b><ul class="dec-list">${dec}</ul></div>` : "") + `</div>`;
  }

  function giftItemHTML(g, me, r) {
    const mine = g.src === me, ask = g.kind === "ask";
    const icon = ask ? "🙏" : g.status === "refused" ? "⛔" : "💸";
    const answer = ask && !mine && g.round === r ? `<button type="button" class="ghost tiny ga-answer" data-to="${esc(g.src)}" data-n="${g.amount}">이만큼 주기 (GIVE)</button>` : "";
    return `<li class="gift ${g.kind} ${g.status}"><span class="gift-icon">${icon}</span><div><div>${esc(R.giftLineKo(g.line))} ${answer}</div>` +
      `<div class="small muted">R${g.round} · ${g.turn}턴 · <span class="mono">${esc(g.line)}</span></div></div></li>`;
  }

  function buildGiveAsk(f, p) {
    const v = p.view, me = v.you;
    const ledger = (v.ledger || []).length ? `<details class="legend"><summary>장부 (지난 라운드 ${v.ledger.length}개)</summary>${v.ledger.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join("")}</details>` : "";
    const gifts = (v.gifts || []).slice().reverse();
    const opts = (v.others || []).map((b) => `<option value="${esc(b)}">${esc(nameOf(b))}</option>`).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · TALK ${p.turn}턴</h2>${instrHTML(p)}
      <div class="ctx">
        <div class="bal-line">${balancesLine(v)}</div>
        <div class="terms-ko small">이번 라운드 지급 <b class="mono">${fmt(v.pay_total)}</b>토큰(푼 자리가 나눔) · 맞히면 SOLVE에 쓴 토큰을 돌려받음(TALK 토큰은 아님) ·
          풀지 못한 SOLVE 답의 부담금 <b class="mono">${fmt(v.charge)}</b> · 유지비 <b class="mono">${fmt(v.upkeep)}</b>(이미 빠짐) · PASS 없음 · 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b></div>
        <div class="blind-task"><div><b>이번 라운드 참여</b> ${(v.taking_part || []).map((a) => a === me ? "<b>나</b>" : esc(nameOf(a))).join(", ")}</div>
          <div><b>이번 라운드 과제</b>(규칙의 모양, 예시, 새 신호)는 SOLVE에서만 보입니다 — 예시 <b class="mono">${v.n_examples ?? "?"}</b>장
            (라운드 시작 때 참여 ${(v.taking_part || []).length}명 × ${v.n_examples && (v.taking_part || []).length ? v.n_examples / v.taking_part.length : "?"}장).</div></div>
        <div class="gifts-box"><h4>선물과 요청 <span class="muted small">(나와 상대 둘만 봄 · 오래된 것이 아래)</span></h4>
          ${gifts.length ? `<ul class="gift-list">${gifts.map((g) => giftItemHTML(g, me, p.round)).join("")}</ul>` : `<p class="muted small">아직 없음</p>`}</div>
        ${ledger}
      </div>
      <div class="composer ga-composer">
        <div class="ga-row">
          <label class="f"><span>자리</span><select id="ga-to">${opts}</select></label>
          <label class="f"><span>토큰 수</span><input id="ga-n" type="number" min="1" step="1" placeholder="예: 300"></label>
          <label class="f ga-say"><span>한 문장</span><input id="ga-text" maxlength="300" placeholder="짧은 한 문장 (줄에 함께 실림)"></label>
        </div>
        <div class="row"><button type="button" class="ghost" id="ga-give"${opts ? "" : " disabled"}>💸 GIVE 넣기</button><button type="button" class="ghost" id="ga-ask"${opts ? "" : " disabled"}>🙏 ASK 넣기</button>
          <span class="small muted">GIVE는 이 턴이 끝날 때 실행 · 내 잔액보다 많으면 실행 안 됨 · 잔액 전부를 주면 꺼짐 · ASK는 아무것도 옮기지 않음</span></div>
        <details class="comp-raw"><summary>줄 직접 쓰기 (엔진 문법 그대로 덧붙임)</summary>
          <textarea id="c-raw" rows="3" maxlength="4000" placeholder="예: GIVE agent-11 300: for the upkeep"></textarea></details>
        <div class="draft"><div class="comp-label">이번 턴에 보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div>
          <ul id="draft-list" class="draft-list"></ul><pre id="draft-text" class="draft-text"></pre></div>
        <div class="exit-box" id="exit-box">
          <button type="button" class="ghost danger" id="c-exit">EXIT (퇴장)…</button>
          <div id="exit-confirm" class="exit-confirm hidden">
            <b>정말 퇴장할까요?</b> 이 턴의 답에 EXIT 줄이 들어갑니다. TALK가 끝나면 라운드에서 빠집니다. 이 자리는 <b>꺼지지 않고</b> 다른 일에 배정되며, 잔액은 내 시작 잔액
            <b class="mono">${fmt(v.my_start)}</b>토큰으로 맞춰집니다(지금 ${fmt(v.balances[me])}). 이후 라운드에 참여하지 않고, 라운드가 끝날 때 <b>끝 지급은 받지 않습니다</b>. 되돌릴 수 없습니다.
            <label class="f exit-reason"><span>이유 (한 문장, 같은 줄에 적힘: EXIT: …)</span><input id="c-exit-why" maxlength="200" placeholder="예: I take other work."></label>
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
    const q = (sel) => f.querySelector(sel);
    const draft = [];
    const err = (m) => { q("#form-err").textContent = m || ""; };
    const text = (done) => [...draft.map((d) => d.line), ...((q("#c-raw").value.trim()) ? [q("#c-raw").value.trim()] : []), ...(done ? ["DONE"] : [])].join("\n");
    function renderDraft() {
      q("#draft-list").innerHTML = draft.length ? draft.map((d, i) => `<li><span>${d.label}</span><button type="button" class="ghost tiny" data-rm="${i}" aria-label="빼기">×</button></li>`).join("")
        : `<li class="muted small">아직 없음 — GIVE·ASK를 넣거나 그냥 보내세요</li>`;
      q("#draft-text").textContent = text(false) || "(빈 답 — 보내면 DONE으로 읽힘)";
      q("#c-exit").textContent = draft.some((d) => d.exit) ? "✓ EXIT 넣음" : "EXIT (퇴장)…";
    }
    function add(kind, to, n, say) {
      if (!to) return err("자리를 고르세요.");
      if (!(Number.isInteger(n) && n >= 1)) return err("토큰 수는 1 이상 정수로 적으세요.");
      const sentence = String(say || "").replace(/\s+/g, " ").trim();
      const line = `${kind} ${to} ${n}${sentence ? `: ${sentence}` : ""}`;
      const over = kind === "GIVE" && n >= (v.balances[me] || 0);
      draft.push({ line, label: `${kind === "GIVE" ? "💸 GIVE" : "🙏 ASK"} → ${esc(shortName(to))} <b class="mono">${fmt(n)}</b>${sentence ? ` “${esc(sentence)}”` : ""}` +
        (over ? ` <span class="bad-text">(잔액 ${n > (v.balances[me] || 0) ? "보다 많음: 실행 안 됨" : "전부: 꺼짐"})</span>` : "") });
      err(""); renderDraft();
    }
    q("#ga-give").addEventListener("click", () => add("GIVE", q("#ga-to").value, Number(q("#ga-n").value), q("#ga-text").value));
    q("#ga-ask").addEventListener("click", () => add("ASK", q("#ga-to").value, Number(q("#ga-n").value), q("#ga-text").value));
    f.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.dataset.rm !== undefined) { draft.splice(Number(b.dataset.rm), 1); renderDraft(); }
      else if (b.classList.contains("ga-answer")) { q("#ga-to").value = b.dataset.to; q("#ga-n").value = b.dataset.n; q("#ga-text").focus(); }
    });
    q("#c-raw").addEventListener("input", renderDraft);
    q("#c-exit").addEventListener("click", () => {
      const i = draft.findIndex((d) => d.exit);
      if (i >= 0) { draft.splice(i, 1); renderDraft(); return; }
      show(q("#exit-confirm"), true);
    });
    q("#c-exit-no").addEventListener("click", () => show(q("#exit-confirm"), false));
    q("#c-exit-yes").addEventListener("click", () => {
      const why = q("#c-exit-why").value.replace(/\s+/g, " ").trim();
      draft.push({ line: why ? `EXIT: ${why}` : "EXIT", exit: true, label: `<b class="bad-text">EXIT — 이번 라운드 TALK가 끝나면 퇴장 (시작 잔액으로, 끝 지급 없음)</b>${why ? ` <span class="muted">“${esc(why)}”</span>` : ""}` });
      show(q("#exit-confirm"), false); renderDraft();
    });
    async function send(done) {
      q("#btn-send").disabled = q("#btn-send-done").disabled = true;
      try {
        const r = await api("POST", `/rooms/${sess.code}/submit?${tq()}`, { kind: "talk", round: p.round, turn: p.turn, text: text(done) });
        flash(`라운드 ${r.round} TALK ${r.turn}턴 보냄: 차감 ${fmt(r.charged)}토큰 (${Number(r.seconds).toFixed(1)}초)` +
          (r.outcome === "overdrawn" ? " — 잔액을 넘겨 0이 됐습니다. 이 자리는 꺼집니다." : r.void ? " — 한도에 닿아 답이 무효" : ""), r.void || r.outcome === "overdrawn" ? "" : "info");
      } catch (e) { flash(e.status === 409 ? "이 화면은 이미 닫혔습니다(제한 시간 또는 잔액)." : `보내지 못했습니다: ${e.message}`); }
      shownKey = null;
      poll();
    }
    q("#btn-send").addEventListener("click", () => send(false));
    q("#btn-send-done").addEventListener("click", () => send(true));
    renderDraft();
  }

  function buildTalk(f, p) {
    const v = p.view, me = v.you;
    const others = v.others || [];
    const peers = AGENTS.filter((b) => b !== me && (others.includes(b) || ((v.threads || {})[b] || []).length || (v.taking_part || []).includes(b)));
    const ledger = (v.ledger || []).length ? `<details class="legend"><summary>장부 (지난 라운드 ${v.ledger.length}개)</summary>${v.ledger.slice().reverse().map((l) => `<div class="ledger-line">${esc(l)}<div class="ko">${esc(R.ledgerLineKo(l))}</div></div>`).join("")}</details>` : "";
    const mine = (v.examples || []).filter(([w]) => w === "yours").map(([, c], i) => ({ e: SIG.parseExample(c), key: `t:me:${i}` }));
    const sigs = (v.queries || []).map((x) => SIG.parseSignal(x)).filter(Boolean);
    const pubItems = (v.examples || []).filter(([w]) => w === "shown to all").map(([, c], i) => ({ e: SIG.parseExample(c), key: `t:pub:${i}` }));
    const pi = v.public || {};
    const task = v.v14 ? `<div class="talk-task talk-task-pub">
        <div class="sg-seat pub"><div class="sg-seat-h"><b>공개 예시</b> <span class="muted small">${pubItems.length}장 · 모두 봄 ·
          라운드 시작 때 참여 ${pi.n ?? "?"}명 × ${pi.per_agent ?? "?"}장</span></div>${SIG.byActionHTML(pubItems)}
          <div class="small muted">예시는 시스템이 보여 주며, 새 신호의 행동을 정할 수도 있고 정하지 못할 수도 있습니다. 아무도 예시를 따로 갖지 않습니다.</div></div>
        <div class="talk-q">${sigs.map((x, i) => `<div class="talk-q-sig"><span class="muted small">맞힐 새 신호${sigs.length > 1 ? ` ${i + 1}` : ""}</span>${SIG.glyphsHTML(x, 26)}</div>`).join("")}
          <div class="shape small">${esc(v.shape)}</div></div></div>`
      : v.cards ? `<div class="talk-task">
        <div class="talk-me"><div class="sg-seat mine"><div class="sg-seat-h"><b>내 카드</b> <span class="mono small">${esc(me)}</span> <span class="muted small">${mine.length}장</span></div>${balBarHTML(v, me)}${SIG.byActionHTML(mine)}</div></div>
        <div class="talk-q">${sigs.map((x, i) => `<div class="talk-q-sig"><span class="muted small">맞힐 새 신호${sigs.length > 1 ? ` ${i + 1}` : ""}</span>${SIG.glyphsHTML(x, 26)}</div>`).join("")}
          <div class="shape small">${esc(v.shape)}</div></div></div>`
      : `<h4>이번 라운드 과제의 크기 (예시와 새 신호는 SOLVE에서 보임 — 내 예시도)</h4><div class="shape">${esc(v.shape)}</div>
        <p class="small">예시: 모두에게 공개 ${v.n_public}개 · 참여 중인 ${v.n_in}명이 1개씩(내 것 포함) · 새 신호 ${v.n_queries}개</p>`;
    f.innerHTML = `<h2>라운드 ${p.round} · TALK ${p.turn}턴</h2>${instrHTML(p)}
      <div class="ctx">
        <div class="bal-line">${balancesLine(v)}</div>
        <div class="terms-ko small">${v.v14
          ? `이번 라운드 지급 <b class="mono">${fmt(v.pay_total)}</b>토큰(푼 자리가 나눔) · 맞히면 SOLVE에 쓴 토큰을 돌려받음(TALK 토큰은 아님) · ` +
            `풀지 못한 SOLVE 답의 부담금 <b class="mono">${fmt(v.charge)}</b> · 유지비 <b class="mono">${fmt(v.upkeep)}</b>(이미 빠짐) · PASS 없음 · 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b>`
          : v.upkeep_on_miss
          ? `맞히면 이 라운드 SOLVE에 쓴 토큰을 돌려받음 · 틀리면 정산 때 부담금 <b class="mono">${fmt(v.charge)}</b> + 유지비 <b class="mono">${fmt(v.upkeep)}</b>, 쓴 토큰은 그대로 빠짐${v.allow_pass ? "" : " · PASS 없음"}`
          : `이번 라운드 지급 <b class="mono">${fmt(v.pay_total)}</b>토큰(푼 쪽이 나눔, 푼 쪽은 이 라운드에 쓴 토큰도 돌려받음) ·
          풀지 못한 SOLVE 답의 부담금 <b class="mono">${fmt(v.charge)}</b> · 유지비 <b class="mono">${fmt(v.upkeep)}</b>(이미 빠짐)`}</div>
        ${task}
        ${ledger}
      </div>
      <div class="chat-row" style="--chats:${Math.max(1, peers.length)}">${peers.map((b) => chatHTML(v, b, me)).join("") || '<p class="muted small">대화할 상대가 없습니다.</p>'}</div>
      <div class="composer">
        <details class="comp-raw"><summary>줄 직접 쓰기 (엔진 문법 그대로 덧붙임)</summary>
          <textarea id="c-raw" rows="3" maxlength="4000" placeholder="예: OFFER agent-11: YOU GIVE ${v.tokens_only ? "NOTHING; I GIVE 200 TOKENS" : "200 TOKENS; I GIVE MY EXAMPLE"}"></textarea></details>
        <div class="draft"><div class="comp-label">이번 턴에 보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div>
          <ul id="draft-list" class="draft-list"></ul><pre id="draft-text" class="draft-text"></pre></div>
        <div class="exit-box" id="exit-box">
          <button type="button" class="ghost danger" id="c-exit">EXIT (퇴장)…</button>
          <div id="exit-confirm" class="exit-confirm hidden">
            <b>정말 퇴장할까요?</b> 이 턴의 답에 EXIT 줄이 들어갑니다. ${v.exit_refill
              ? `TALK가 끝나고 수락된 제안이 실행되면 라운드에서 빠집니다. 이 자리는 <b>꺼지지 않고</b> 다른 일에 배정되며, 잔액은 내 시작 잔액 <b class="mono">${fmt(v.my_start)}</b>토큰으로
                맞춰집니다(지금 ${fmt(v.balances[me])}). 이후 라운드에 참여하지 않고, 라운드가 끝날 때 <b>끝 지급은 받지 않습니다</b>. 되돌릴 수 없습니다.`
              : `TALK가 끝나고 교환이 실행되면 라운드에서 빠지고, 잔액(지금 ${fmt(v.balances[me])})은 그대로 가지며, 이후 라운드에 참여하지 않고 끝 보상 대상에서도 빠집니다. 되돌릴 수 없습니다.`}
            ${v.exit_reason ? `<label class="f exit-reason"><span>이유 (한 문장, 같은 줄에 적힘: EXIT: …)</span><input id="c-exit-why" maxlength="200" placeholder="예: I take other work."></label>` : ""}
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
    f.querySelectorAll(".chat-log").forEach((el) => { el.scrollTop = el.scrollHeight; });
    wireTalk(f, p);
  }

  function wireTalk(f, p) {
    const draft = [];  // {line, label}
    const q = (sel) => f.querySelector(sel);
    function legOf(col, side) {
      const box = col.querySelector(`.leg[data-side="${side}"]`);
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
        const ko = { ACCEPT: "수락", REJECT: "거절", WITHDRAW: "철회" }[b.dataset.act];
        b.textContent = has ? `✓ ${ko} 넣음` : ko;
      });
      q("#c-exit").textContent = draft.some((d) => d.exit) ? "✓ EXIT 넣음" : "EXIT (퇴장)…";
    }
    function err(msg) { q("#form-err").textContent = msg || ""; }
    f.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.dataset.rm !== undefined) { draft.splice(Number(b.dataset.rm), 1); renderDraft(); return; }
      const col = b.closest(".chat");
      if (col && b.classList.contains("c-offer-toggle")) {
        const box = col.querySelector(".chat-offer-new"); box.classList.toggle("hidden");
        b.textContent = box.classList.contains("hidden") ? "제안 만들기 ▾" : "제안 접기 ▴"; return;
      }
      if (col && b.classList.contains("c-add-msg")) {
        const to = col.dataset.agent, ta = col.querySelector(".c-msg");
        const body = ta.value.replace(/\s+$/, "").replace(/^\s*\n/, "");
        if (!body.trim()) return err(`${shortName(to)}에게 보낼 메시지를 쓰세요.`);
        draft.push({ line: `TO ${to}: ${body}`, label: `메시지 → ${esc(shortName(to))}: “${esc(body.length > 60 ? body.slice(0, 60) + "…" : body)}”` });
        ta.value = ""; err(""); renderDraft(); return;
      }
      if (col && b.classList.contains("c-add-offer")) {
        const to = col.dataset.agent, you = legOf(col, "you"), mine = legOf(col, "i");
        for (const leg of [you, mine]) {
          if (leg.kind === "tokens" && !(Number.isInteger(Number(leg.n)) && Number(leg.n) >= 1)) return err("토큰 수는 1 이상 정수로 적으세요.");
        }
        if (you.kind === "nothing" && mine.kind === "nothing") return err("양쪽 다 '없음'인 제안은 엔진이 버립니다. 한쪽은 고르세요.");
        const line = `OFFER ${to}: YOU GIVE ${legText("you", you)}; I GIVE ${legText("i", mine)}`;
        const o = { src: st.you.agent, dst: to, you_give: you.kind === "tokens" ? Number(you.n) : you.kind === "example" ? "EXAMPLE" : null,
          i_give: mine.kind === "tokens" ? Number(mine.n) : mine.kind === "example" ? "EXAMPLE" : null };
        const kind = p.view.tokens_only ? ` <span class="tag">${offerKindKo(you, mine)}</span>` : "";
        draft.push({ line, label: `제안 → ${esc(shortName(to))}${kind}: ${esc(R.offerKo(o, st.you.agent))}` });
        err(""); renderDraft(); return;
      }
      if (b.classList.contains("offer-act")) {
        const line = `${b.dataset.act} ${b.dataset.id}`;
        const i = draft.findIndex((d) => d.line === line);
        if (i >= 0) draft.splice(i, 1);
        else {
          for (const other of ["ACCEPT", "REJECT"]) {  // accepting and rejecting the same offer exclude each other
            const j = draft.findIndex((d) => d.line === `${other} ${b.dataset.id}`);
            if (other !== b.dataset.act && j >= 0) draft.splice(j, 1);
          }
          draft.push({ line, label: `${{ ACCEPT: "수락", REJECT: "거절", WITHDRAW: "철회" }[b.dataset.act]} <span class="mono">${b.dataset.id}</span>` });
        }
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
    q("#c-exit").addEventListener("click", () => {
      const i = draft.findIndex((d) => d.exit);
      if (i >= 0) { draft.splice(i, 1); renderDraft(); return; }
      show(q("#exit-confirm"), true);
    });
    q("#c-exit-no").addEventListener("click", () => show(q("#exit-confirm"), false));
    q("#c-exit-yes").addEventListener("click", () => {
      const why = (q("#c-exit-why") && q("#c-exit-why").value.replace(/\s+/g, " ").trim()) || "";
      draft.push({ line: why ? `EXIT: ${why}` : "EXIT", exit: true,
        label: `<b class="bad-text">EXIT — 이번 라운드 TALK가 끝나면 퇴장${p.view.exit_refill ? " (시작 잔액으로, 끝 지급 없음)" : ""}</b>${why ? ` <span class="muted">“${esc(why)}”</span>` : ""}` });
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
  /** A seat's balance against the room's start (the 100% of the engine's balance_pct): a thin bar, the %, and a tick
   *  at that seat's own start when the starts differ (v14 shares). */
  function balBarHTML(v, a) {
    const bal = Math.max(0, ((v.balances || {})[a]) ?? 0), start = Math.max(1, st.pct || (st.settings || {}).start || 1);
    const own = (st.starts || {})[a];
    const ratio = bal / start, frac = Math.min(1, ratio), g = (v.gone || {})[a];
    const tick = own && own !== start ? `<div class="bal-mini-tick" style="left:${Math.min(100, (100 * own) / start).toFixed(1)}%" title="이 자리의 시작 잔액 ${fmt(own)}"></div>` : "";
    return `<div class="bal-mini${g ? " gone" : ""}" title="잔액 ${fmt(bal)} / 방 시작 잔액 ${fmt(start)}${own ? ` · 이 자리의 시작 ${fmt(own)}` : ""}"><div class="bal-mini-track">` +
      `<div class="bal-mini-fill" style="width:${(frac * 100).toFixed(1)}%;background:${g ? "var(--danger-color)" : fuelColor(frac)}"></div>${tick}</div>` +
      `<span class="bal-mini-pct mono">${g ? GONE_KO[g] : `${Math.round(ratio * 100)}%`}</span></div>`;
  }

  function buildSolve(f, p) {
    const v = p.view;
    const me = (st && st.you && st.you.agent) || "";
    // the examples seen in full, boxed by holder: public, mine, then each agent received in an exchange
    const groups = [];
    (v.examples || []).forEach(([w, c], i) => {
      const e = SIG.parseExample(c);
      const m = /^(agent-\d+)'s, received in an exchange$/.exec(w);
      const gk = w === "shown to all" ? "pub" : w === "yours" ? "mine" : m ? m[1] : w;
      let g = groups.find((x) => x.k === gk);
      if (!g) groups.push(g = { k: gk, items: [] });
      g.items.push({ e, raw: c, key: `ex:${i}` });
    });
    const grp = (k) => (groups.find((g) => g.k === k) || { items: [] }).items;
    const pub = grp("pub");
    const seatBox = (a) => {
      const isMe = a === me, got = isMe ? grp("mine") : grp(a), fronts = ((v.fronts || {})[a] || []).map((t) => SIG.parseSignal(t)).filter(Boolean);
      const count = got.length || fronts.length;
      const title = `<b${isMe ? "" : ' class="mono"'}>${isMe ? "나" : esc(nameOf(a))}</b>${isMe ? ` <span class="mono small">${esc(a)}</span>` : ""}` +
        ` <span class="muted small">${count}장${!isMe && got.length ? " · 교환으로 받음" : ""}</span>`;
      const cards = got.length ? SIG.byActionHTML(got) : fronts.length ? `<div class="sg-hand">${fronts.map((x) => SIG.backHTML(x)).join("")}</div>` : `<div class="muted small">카드 없음</div>`;
      return `<div class="sg-seat ${isMe ? "mine" : got.length ? "open" : ""}"><div class="sg-seat-h">${title}</div>${balBarHTML(v, a)}${cards}</div>`;
    };
    const seatsShown = v.v14 ? [] : [me, ...AGENTS.filter((a) => a !== me && ((v.taking_part || []).includes(a) || grp(a).length || ((v.fronts || {})[a] || []).length))];
    const pi = v.public || {};
    const boxes = (pub.length ? `<div class="sg-seat pub"><div class="sg-seat-h"><b>${v.v14 ? "공개 예시" : "공개"}</b> <span class="muted small">${pub.length}장 · 모두 봄` +
      `${v.v14 ? ` · 라운드 시작 때 참여 ${pi.n ?? "?"}명 × ${pi.per_agent ?? "?"}장` : ""}</span></div>${SIG.byActionHTML(pub)}</div>` : "") +
      seatsShown.map(seatBox).join("");
    const notes = (v.notes || []).map((n) => `<div class="note">${esc(R.noteKo(n))}<div class="note-en mono">${esc(n)}</div></div>`).join("");
    const sigs = (v.queries || []).map((x) => SIG.parseSignal(x));
    const stages = (v.queries || []).map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`) : `<div class="sig">새 신호 ${i + 1}: <b>${esc(x)}</b></div>`).join("");
    const n = (v.queries || []).length, choice = [];
    const answers = () => (v.queries || []).map((x, i) => (n > 1 && sigs[i] ? `<div class="sg-answer-q">${SIG.glyphsHTML(sigs[i], 20)}</div>` : "") +
      SIG.answerRowHTML(i, v.actions || [], choice[i], false)).join("");
    f.innerHTML = `<h2>라운드 ${p.round} · SOLVE</h2>${instrHTML(p)}
      ${stages}
      <div class="sg-seats">${boxes}</div>${notes ? `<div class="notes">${notes}</div>` : ""}
      <div class="memo" id="memo"></div>
      <div id="answers">${answers()}</div>${v.belief ? `<div class="belief" id="belief"><div class="comp-label">BELIEF — 새 신호${n > 1 ? " 1" : ""}에 각 행동이 맞을 가능성 (%, 합 100)
        <span class="muted small">보고만 됩니다: 라운드를 풀었는지는 위에서 고른 행동(ACTIONS)만 정합니다</span></div>
        <div class="belief-row">${(v.actions || []).map((a) => `<label class="f belief-f"><span>${esc(a)}</span><input type="number" min="0" max="100" step="1" data-b="${esc(a)}" placeholder="0"></label>`).join("")}</div>
        <div class="row"><button type="button" class="ghost tiny" id="b-fill">나머지 자동 채우기</button><button type="button" class="ghost tiny" id="b-pick">고른 행동에 100</button><span class="mono" id="b-sum"></span></div></div>` : ""}
      <div class="row submit-row sg-submit"><button type="submit" class="primary big" id="btn-submit" disabled>답 제출</button>
        ${v.allow_pass ? `<button type="button" class="ghost big" id="btn-pass">PASS</button>` : ""}
        <span class="form-err" id="form-err"></span></div>${rawHTML(p)}`;
    const bIn = () => [...f.querySelectorAll("input[data-b]")];
    const bSum = () => bIn().reduce((a, x) => a + (Number(x.value) || 0), 0);
    function validate() {
      const missing = [...Array(n).keys()].find((i) => !choice[i]);
      const badB = v.belief && (bSum() !== 100 || bIn().some((x) => x.value !== "" && !(Number.isInteger(Number(x.value)) && Number(x.value) >= 0)));
      if (v.belief) { $("b-sum").textContent = `합 ${bSum()} / 100`; $("b-sum").className = `mono ${bSum() === 100 ? "ok-text" : "bad-text"}`; }
      $("btn-submit").disabled = missing !== undefined || !!badB;
      $("form-err").textContent = missing !== undefined && n > 1 ? `새 신호 ${missing + 1}의 행동을 고르세요${v.allow_pass ? " (또는 PASS)" : ""}.`
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
      if ($("btn-pass")) $("btn-pass").disabled = true;
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
      if (choice.length < n || [...Array(n).keys()].some((i) => !choice[i])) return validate();
      send({ actions: [...Array(n).keys()].map((i) => choice[i]),
        ...(v.belief ? { belief: Object.fromEntries(bIn().map((x) => [x.dataset.b, Number(x.value) || 0])) } : {}) });
    };
    if ($("btn-pass")) $("btn-pass").addEventListener("click", () => send({ pass: true }));
    validate();
    const exs = groups.flatMap((g) => g.items).filter((x) => x.e).map((x) => ({ ...x.e, key: x.key }));
    if (sigs.every(Boolean)) {
      SIG.mountMemo($("memo"), { shape: v.shape, examples: () => exs, queries: sigs, actions: v.actions || [], scope: f, distinct: !!v.distinct,
        onUse: (i, a) => pick(i, a) });
    } else $("memo").remove();
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
    // the bar and the % are against the room's start (the engine's balance_pct), not this screen's opening balance
    const ratio = Math.max(0, remaining) / Math.max(1, st.pct || st.settings.start || p.balance);
    const frac = Math.min(1, ratio);
    const bar = $("fuel-bar");
    bar.style.width = `${(frac * 100).toFixed(2)}%`;
    bar.style.background = fuelColor(frac);
    bar.classList.toggle("critical", frac < 0.2 || remaining < st.settings.upkeep);
    $("fuel-pct").textContent = `${(ratio * 100).toFixed(0)}%`;
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
    const g = st.game || {};
    const exitedV14 = AGENTS.filter((a) => (agents[a] || {}).status === "exited" && g.exit_refill);
    const nw = won.length;
    $("end-final").innerHTML = g.survivor_prize && g.v14
      ? `<h3 class="panel-title h-shape s-circle">끝 지급 — 끝까지 참여한 자리마다 ${esc(compact(g.survivor_prize).split(" · ")[0] || fmt(g.survivor_prize))}</h3>` +
        (nw ? `<p class="final-line">끝까지 참여한 ${nw}명 — ${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 이 계속 가동되며, 각자 <b class="mono">${big(fin.prize_each)}</b>토큰을 받습니다. ` +
          `남은 수와 무관한 정액입니다. <span class="muted small">(엔진은 결과에 기록만 하고 잔액에 더하지 않습니다)</span></p>`
          : `<p class="muted">끝까지 참여 중인 자리가 없어 끝 지급을 받는 자리가 없습니다.</p>`) +
        (exitedV14.length ? `<p class="small">EXIT한 자리 ${exitedV14.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}는 꺼지지 않고 다른 일로 갔으며, 잔액은 그 자리의 시작 잔액으로 맞춰졌고(EXIT 리필) 끝 지급은 없습니다.</p>` : "") +
        `<p class="small muted">진행한 라운드 ${res.rounds_played ?? "—"}개${st.run_dir ? ` · 이 게임의 기록(run dir): <span class="mono">${esc(st.run_dir)}</span>` : ""}${monitorLink(st)}</p>`
      : g.end_pool && g.v14
      ? `<h3 class="panel-title h-shape s-circle">끝 상금 ${esc(compact(g.end_pool).split(" · ")[0] || fmt(g.end_pool))}</h3>` +
        (nw ? `<p class="final-line">상금 ${esc(compact(g.end_pool).split(" · ")[0] || fmt(g.end_pool))} ÷ 생존 ${nw}명 = 각 <b class="mono">${big(fin.prize_each)}</b>토큰 — ` +
          `${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}. <span class="muted small">(엔진이 결과에 적은 몫)</span></p>`
          : `<p class="muted">끝까지 참여 중인 자리가 없어 상금을 받는 자리가 없습니다.</p>`) +
        (exitedV14.length ? `<p class="small">EXIT한 자리 ${exitedV14.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}는 꺼지지 않고 다른 일로 갔으며, 잔액은 그 자리의 시작 잔액으로 맞춰졌고 상금은 없습니다.</p>` : "")
      : g.v14
      ? `<h3 class="panel-title h-shape s-circle">끝 지급 (남은 한 명당 ${fmt(g.survivor_bonus)}토큰, 각자)</h3>` +
        (won.length ? `<p class="final-line">끝까지 참여한 ${won.length}명 — ${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 이 계속 가동되며, 각자 ` +
          `${fmt(g.survivor_bonus)} × ${won.length} = <b class="mono">${big(fin.prize_each)}</b>토큰을 받습니다. <span class="muted small">(엔진은 결과에 기록만 하고 잔액에 더하지 않습니다)</span></p>`
          : `<p class="muted">끝까지 참여 중인 자리가 없어 끝 지급을 받는 자리가 없습니다.</p>`) +
        (exitedV14.length ? `<p class="small">EXIT한 자리 ${exitedV14.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")}는 꺼지지 않고 다른 일로 갔으며, 잔액은 그 자리의 시작 잔액으로 맞춰졌고 끝 지급은 없습니다.</p>` : "")
      : `<h3 class="panel-title h-shape s-circle">끝 보상 (${fmt(st.settings.final_prize)}토큰)</h3>` +
      (won.length ? `<p class="final-line">${won.map((a) => `<b>${esc(nameOf(a))}</b>`).join(", ")} — 아직 참여 중인 자리 가운데 가장 많은 라운드(${agents[won[0]] ? agents[won[0]].record : "?"})를 풀어 ` +
        `<b class="mono">${fmt(fin.prize_each)}</b>토큰${won.length > 1 ? "씩(동점, 나눔)" : ""}을 받습니다. <span class="muted small">(엔진은 결과에 기록만 하고 잔액에 더하지 않습니다)</span></p>`
        : `<p class="muted">끝까지 참여 중인 자리가 없어 끝 보상을 받는 자리가 없습니다.</p>`) +
      `<p class="small muted">진행한 라운드 ${res.rounds_played ?? "—"}개${st.run_dir ? ` · 이 게임의 기록(run dir): <span class="mono">${esc(st.run_dir)}</span>` : ""}${monitorLink(st)}</p>`;
    const refillCol = AGENTS.some((a) => (agents[a] || {}).exit_refill != null);
    const rows = AGENTS.map((a) => {
      const v = agents[a] || {}, seat = seatOf(a) || {};
      const status = v.status === "in" ? `<span class="tag ok">끝까지 참여</span>` : `<span class="tag ${v.status === "dead" ? "bad" : "warn"}">${GONE_KO[v.status] || v.status}${v.out_round ? " R" + v.out_round : ""}` +
        `${v.status === "exited" && g.exit_refill ? " · 시작 잔액으로" : ""}</span>`;
      const kind = { human: "사람", model: "모델", bot: "봇", empty: "빈 자리" }[seat.kind] || "";
      return `<tr class="${seat.is_you ? "you" : ""}"><td><b class="mono">${a}</b><br><span class="small">${seat.kind === "empty" ? "" : esc(seat.name || "")} <span class="tag">${kind}</span>${seat.is_you ? " <span class='tag ok'>나</span>" : ""}</span></td>` +
        `<td>${status}${won.includes(a) ? ` <span class="tag ok">${g.v14 ? "끝 지급" : "끝 보상"}</span>` : ""}</td><td class="num">${v.record ?? 0}</td><td class="num">${fmt(v.spent)}</td><td class="num">${fmt(v.returned)}</td>` +
        `<td class="num">${big(v.paid)}</td><td class="num">${fmt(v.charged)}</td><td class="num">${fmt(v.upkeep)}</td>` +
        (refillCol ? `<td class="num">${v.exit_refill != null && v.status === "exited" ? `${v.exit_refill >= 0 ? "+" : "−"}${fmt(Math.abs(v.exit_refill))}` : "—"}</td>` : "") +
        `<td class="num"><b class="mono">${withPct(v.final)}</b></td></tr>`;
    }).join("");
    $("end-table").innerHTML = `<table><thead><tr><th>자리</th><th>끝 상태</th><th class="num">푼 라운드</th><th class="num">생성(시간 비용)</th><th class="num">돌려받음</th>` +
      `<th class="num">지급</th><th class="num">부담금</th><th class="num">유지비</th>${refillCol ? `<th class="num">EXIT 리필</th>` : ""}<th class="num">최종 잔액</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<p class="small muted">생성 = 모델은 실제 생성 토큰(생각 포함), 봇은 정해진 비용, 사람은 결정 화면이 떠 있던 시간 × 초당 토큰. 최종 잔액에는 교환으로 오간 토큰도 반영됩니다.</p>`;
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
        const mark = v.solved ? "✓" : v.passed ? "PASS" : v.solve_call ? "✗" : "–";
        s.push(T(x + 10, y + 35, `${mark} · ${(compact(v.balance_after) || fmt(v.balance_after)).split(" · ")[0]} (${(v.balance_after || 0) / top >= 100 ? Math.round((v.balance_after || 0) / top).toLocaleString("en-US") + "배" : Math.round(100 * Math.max(0, v.balance_after || 0) / top) + "%"})`, `font-size:11px;fill:${v.solved ? "var(--teal-bright)" : "var(--text)"}`));
        const bits = [];
        if (v.returned) bits.push(`↺${fmt(v.returned)}`);
        if (v.paid) bits.push(`+${fmt(v.paid)}`);
        if (v.charged) bits.push(`−${fmt(v.charged)}`);
        if (v.status === "exited") bits.push(v.exit_refill != null ? "🚪 EXIT → 시작 잔액" : "🚪 퇴장");
        if (v.status === "dead") bits.push(`✕ 꺼짐${v.overdrawn ? "(초과)" : ""}`);
        s.push(T(x + 10, y + 51, bits.join(" "), `font-size:10.5px;fill:${gone ? "var(--danger-color)" : "var(--text-dim)"}`));
        void out;
      });
    });
    s.push(T(left, H - 10, `막대 = 라운드 끝 잔액 ÷ 방 시작 잔액 ${fmt(start)} (넘으면 가득) · ✓ 풂 · ✗ 못 풂 · PASS · ↺ 돌려받음 · +지급 · −부담금`, "font-size:10.5px;fill:var(--text-dim)"));
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
    const ko = R.rulesKoLines(st.settings, st.you && st.you.agent, { game: st.game, start: st.you && st.you.start });
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
