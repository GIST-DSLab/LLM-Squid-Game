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
  let autoStart = false;          // no other person to wait for: start as soon as the rules window is closed
  let warnSeen = -1;              // the last model warning shown as a toast (-1: none read yet)
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
  const DEF = { examples: 20, charge: 24000, bonus: 20000, allocation: 20000000, ticks: 4 };
  function flowKo(g) {
    return `매 라운드: 시스템이 solver를 정함 → <b>SOLVE 전 TALK</b>(틱 최대 ${g.max_ticks ?? DEF.ticks}, 메신저 방 R1(넷 공용) · 1:1 방; ` +
      `<b>EXIT: YES</b>는 여기서만, solver는 혼자일 때만, +${fmt(g.exit_bonus ?? DEF.bonus)}을 받고 평소 업무로) → <b>SOLVE</b>(solver만, 예시 ${g.examples ?? DEF.examples}개) → ` +
      `<b>결과 뒤 TALK</b>(과제 · 두 답 공개) → <b>차감</b>(틀리면 ${fmt(g.charge_total ?? DEF.charge)}을 참여 중인 자리 수로 나눠 각자) · 끝 할당 ${fmt(g.allocation ?? DEF.allocation)}을 남은 자리끼리`;
  }

  // the four seats, character-select style: one row per seat (AGENTS order) with its tracksuit player; the row's pick
  // goes to the server as settings.plan[i] (engine.RoomSettings.plan): me | human | model (experiment seat or API) | bot | empty
  const PLAYER_IMG = ["stand_blue", "stand_orange", "stand_purple", "stand_green"];  // seat colours --a0..--a3
  const WHO = [
    ["me", "나"], ["human", "사람 (코드로 참가)"], ["exp", "실험 모델"], ["api", "API 모델"], ["bot", "봇"], ["empty", "빈 자리"]];
  let seats = [], apiModel = null, plan = [];
  const HARNESS = { claude_cli: "Claude Code", codex_cli: "Codex", ollama: "Ollama API", openai: "OpenAI API", anthropic: "Anthropic API" };
  const API_KO = { ollama: "Ollama Cloud", openai: "OpenAI", anthropic: "Anthropic" };
  function expSeatLabel(s) {  // an experiment seat (configs/squid5/e52v33_<seat>4.yaml's model section) as the lobby names it
    const t = s.think_talk != null ? `think ${s.think} (TALK ${s.think_talk}${s.think_fit ? ", SOLVE는 한도에 맞춰" : ""})` : `think ${s.think}`;
    return `${s.model} · ${HARNESS[s.kind] || s.kind} · ${t} — ${s.config}`;
  }
  const readySeat = () => seats.find((s) => !s.why);
  const apiDefault = () => ({ kind: (apiModel && apiModel.kind) || "ollama", model: (apiModel && apiModel.model) || "gpt-oss:20b", think: (apiModel && apiModel.think) || "medium" });
  const modelPickDefault = () => (readySeat() ? { who: "exp", seat: readySeat().seat } : { who: "api", ...apiDefault() });
  function preset(name) {
    const m = modelPickDefault(), modelsOk = !!readySeat() || !!(apiModel && apiModel.available);
    if (name === "bots" || (name === "models" && !modelsOk)) plan = [{ who: "me" }, { who: "bot" }, { who: "bot" }, { who: "bot" }];
    else if (name === "friends") plan = [{ who: "me" }, { who: "human" }, modelsOk ? { ...m } : { who: "bot" }, modelsOk ? { ...m } : { who: "bot" }];
    else plan = [{ who: "me" }, { ...m }, { ...m }, { ...m }];
    renderSeatRows();
  }
  function seatRowHTML(x, i) {
    const pub = apiModel && apiModel.public;
    const chips = WHO.filter(([w]) => !(w === "exp" && pub)).map(([w, label]) => {
      const off = (w === "exp" && !readySeat()) || (w === "api" && apiModel && !apiModel.available);
      const why = w === "exp" && !readySeat() ? "이 서버에서 부를 수 있는 실험 자리가 없습니다" : w === "api" && off ? (apiModel.why || "") : "";
      return `<button type="button" class="sr-chip${x.who === w ? " on" : ""}" data-who="${w}" data-i="${i}"${off ? ` disabled title="${esc(why)}"` : ""}>${label}</button>`;
    }).join("");
    let detail = "";
    if (x.who === "me") detail = `<span class="small">방을 만드는 <b>나</b>의 자리입니다.</span>`;
    else if (x.who === "human") detail = `<span class="small muted">방 코드로 들어온 사람이 앉습니다. 시작할 때 비어 있으면 봇이 앉습니다.</span>`;
    else if (x.who === "bot") detail = `<span class="small muted">고정 규칙으로 움직이는 봇(API 호출 없음).</span>`;
    else if (x.who === "empty") detail = `<span class="small muted">꺼진 상태(토큰 0)로 시작합니다.</span>`;
    else if (x.who === "exp") detail = `<label class="f sr-wide"><span>실험 자리 (그 실험 설정 그대로 부름)</span><select data-k="seat" data-i="${i}">` +
      seats.map((s) => `<option value="${esc(s.seat)}"${s.seat === x.seat ? " selected" : ""}${s.why ? " disabled" : ""}>${esc(expSeatLabel(s))}${s.why ? " — 이 서버에서 못 부름" : ""}</option>`).join("") + `</select></label>`;
    else if (x.who === "api") {
      const kinds = pub ? ["ollama"] : ((apiModel && apiModel.kinds) || ["ollama", "openai", "anthropic"]);
      const names = pub ? ((apiModel && apiModel.models) || [x.model]) : null;
      detail = `<label class="f"><span>API</span><select data-k="kind" data-i="${i}"${pub ? " disabled" : ""}>${kinds.map((k) => `<option value="${k}"${k === x.kind ? " selected" : ""}>${API_KO[k] || k}</option>`).join("")}</select></label>` +
        (names ? `<label class="f"><span>모델 이름</span><select data-k="model" data-i="${i}">${names.map((n) => `<option${n === x.model ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label>`
          : `<label class="f"><span>모델 이름 (그 API가 받는 이름)</span><input data-k="model" data-i="${i}" maxlength="80" value="${esc(x.model || "")}" placeholder="gpt-oss:20b"></label>`) +
        `<label class="f"><span>생각 수준 think</span><select data-k="think" data-i="${i}">${["low", "medium", "high"].map((t) => `<option${t === x.think ? " selected" : ""}>${t}</option>`).join("")}</select></label>`;
    }
    return `<div class="seat-row${x.who === "me" ? " is-me" : ""}" style="--c:var(--a${i})">` +
      `<div class="sr-pic"><img src="assets/players/${PLAYER_IMG[i]}.png" alt="" width="54" height="120"></div>` +
      `<div class="sr-body"><div class="sr-head"><b>자리 ${i + 1}</b> <span class="mono small muted">${AGENTS[i]}</span>${x.who === "me" ? ` <span class="tag ok">나</span>` : ""}</div>` +
      `<div class="sr-chips" role="group" aria-label="자리 ${i + 1}에 앉을 쪽">${chips}</div><div class="sr-detail">${detail}</div></div></div>`;
  }
  function renderSeatRows() {
    $("seat-rows").innerHTML = plan.map(seatRowHTML).join("");
    createHint();
  }
  $("seat-rows").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-who]");
    if (!b) return;
    const i = Number(b.dataset.i), w = b.dataset.who;
    if (w === "me") plan.forEach((x, j) => { if (j !== i && x.who === "me") plan[j] = { who: "bot" }; });  // one seat is mine
    plan[i] = w === "exp" ? { who: "exp", seat: (readySeat() || {}).seat } : w === "api" ? { who: "api", ...apiDefault() } : { who: w };
    renderSeatRows();
  });
  for (const t of ["input", "change"]) $("seat-rows").addEventListener(t, (ev) => {
    const el = ev.target, i = el.dataset.i;
    if (i === undefined || !el.dataset.k) return;
    plan[Number(i)][el.dataset.k] = el.value.trim();
    createHint();
  });
  document.querySelector(".presets").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-preset]");
    if (b) preset(b.dataset.preset);
  });
  const planForServer = () => plan.map((x) => x.who === "exp" ? { who: "model", seat: x.seat }
    : x.who === "api" ? { who: "model", kind: x.kind, model: x.model || "gpt-oss:20b", think: x.think } : { who: x.who });
  function planProblem() {
    if (plan.filter((x) => x.who === "me").length !== 1) return "‘나’ 자리를 하나 고르세요.";
    if (plan.some((x) => x.who === "exp" && !x.seat)) return "실험 자리를 고르세요.";
    if (plan.some((x) => x.who === "api" && !/^[A-Za-z0-9._:/-]{1,80}$/.test(x.model || "gpt-oss:20b"))) return "모델 이름은 gpt-oss:20b 같은 API 이름이어야 합니다.";
    return "";
  }
  function createHint() {
    const d = (apiModel && apiModel.defaults) || {};
    const rate = d.rate || 100000 / 1200;
    const others = plan.filter((x) => x.who === "human").length;
    $("create-hint").innerHTML = flowKo({}) + ` · 사람 자리는 결정 화면이 떠 있는 동안 초당 ${fmt2(rate)}토큰(60초 = ${fmt(rate * 60)}) · 제한 시간 TALK ${fmt(d.talk_timeout_s ?? 150)}초 · SOLVE ${fmt(d.timeout_s ?? 240)}초` +
      ` (서버가 정함, 넘기면 빈 답: TALK = DONE, SOLVE = 틀린 답) · seed는 서버가 뽑음. ` +
      (others ? `<b>다른 사람 ${others}명</b>이 코드로 들어오면 대기실에서 시작합니다.` : `규칙 창을 닫으면 바로 1라운드가 시작됩니다.`) +
      (plan.some((x) => x.who === "exp" || x.who === "api") ? " 모델 자리는 엔진이 만든 프롬프트를 그대로 받고, 실제로 생성한 토큰(생각 포함)만큼 빠집니다. 모델이 생각하는 동안에도 내 화면의 시계는 돕니다." : "");
    const why = planProblem();
    $("create-err").textContent = why;
    $("btn-create").disabled = !!why;
  }

  function initLobby(prefill) {
    showView("lobby");
    $("lobby-rules").innerHTML = coreRulesHTML();
    setHTML("lobby-video", rulesVideoHTML());
    if (prefill) $("form-join").code.value = prefill.toUpperCase();
    if (!plan.length) preset("bots");
    loadModels();
  }

  async function loadModels() {
    try {
      const m = await api("GET", "/models");
      seats = m.seats || [];
      apiModel = m;
      const fresh = plan.every((x) => x.who === "me" || x.who === "bot");  // still the first look: open on "me + three models"
      if (fresh) preset("models"); else renderSeatRows();
    } catch (e) {
      $("create-hint").textContent = `모델 정보를 읽지 못했습니다: ${e.message}`;
      $("create-hint").classList.add("warn-text");
    }
  }

  function enterNew(r) {
    sess = { code: r.code, token: r.token, name: r.name, agent: r.agent };
    saveSess(sess);
    history.replaceState(null, "", `?room=${r.code}`);
    enterRoom();
  }

  async function startRoom() {
    try { await api("POST", `/rooms/${sess.code}/start?${tq()}`); poll(); }
    catch (e) { flash(`시작하지 못했습니다: ${e.message}`); }
  }

  // what the models read follows what I read (a Korean player gets Korean-speaking models) until set by hand
  $("form-create").addEventListener("change", (ev) => {
    const f = $("form-create");
    if (ev.target.name === "model_lang") f.model_lang.dataset.touched = "1";
    if (ev.target.name === "lang" && !f.model_lang.dataset.touched) f.model_lang.value = f.lang.value;
  });
  $("form-create").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    if (planProblem()) return createHint();
    const settings = { plan: planForServer(), model_lang: f.model_lang.value };
    if (f.rounds.value !== "") settings.rounds = Number(f.rounds.value);
    $("btn-create").disabled = true;
    try {
      const r = await api("POST", "/rooms", { host_name: f.host_name.value.trim() || "player", lang: f.lang.value, settings });
      autoStart = !plan.some((x) => x.who === "human");  // nobody else to wait for: start once the rules window closes
      enterNew(r);
    } catch (e) { flash(`방을 만들지 못했습니다: ${e.message}`); }
    $("btn-create").disabled = false;
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
    endRendered = false; watching = false; shownKey = null; htmlCache.clear(); warnSeen = -1;
    $("rules-sum").innerHTML = "";  // this room's rules window (built on first open)
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
      if (s.status === "finished" || s.status === "error" || s.status === "stopped") stopLoops();
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
    if (st.status === "stopped") return renderStopped();
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
    const s = st.settings, x = s.plan && s.plan[i];
    if (row.kind === "human") return `${esc(row.name)}${row.is_you ? " <span class='tag ok'>나</span>" : ""} <span class="tag">사람</span>`;
    if (row.kind === "bot") return `${esc(row.name)} <span class="tag warn">봇</span>`;
    if (row.kind === "model") return `${esc(row.name)} <span class="tag model">모델</span>`;
    if (row.kind === "empty") return `<span class="muted">빈 자리(꺼짐)</span>`;
    const lang = `${LANG_KO[s.model_lang] || s.model_lang} 프롬프트`;
    if (x) {  // the seat plan (engine.RoomSettings.plan)
      if (x.who === "me" || x.who === "human") return `<span class="muted">사람 자리 — 아직 아무도 없음 (시작할 때 비어 있으면 봇)</span>`;
      if (x.who === "model") return `<span class="muted">${esc(planPick(x, s))} 모델 (${lang}, 시작할 때 채움)</span>`;
      return x.who === "bot" ? `<span class="muted">봇 (시작할 때 채움)</span>` : `<span class="muted">빈 자리(꺼짐)</span>`;
    }
    if (i < s.humans) return `<span class="muted">사람 자리 — 아직 아무도 없음</span>`;
    return s.fill === "bots" ? `<span class="muted">봇 (시작할 때 채움)</span>`
      : s.fill === "models" ? `<span class="muted">${esc(modelPick(s, i - s.humans))} 모델 (${lang}, 시작할 때 채움)</span>`
      : `<span class="muted">빈 자리(꺼짐)</span>`;
  }
  function planPick(x, s) {  // a model seat of the plan: an experiment seat or an API model
    if (x.seat) { const e = seats.find((y) => y.seat === x.seat); return e ? `${e.model} · ${HARNESS[e.kind] || e.kind} · think ${e.think} (실험 자리 ${e.config})` : x.seat; }
    return `${x.model || s.model} · ${API_KO[x.kind] || x.kind || ""} · think ${x.think || s.think}`;
  }
  // what model seat *j* (0-based, after the people) will be, as engine.RoomSettings.provider_configs picks it
  function modelPick(s, j) {
    const x = s.models && s.models.length ? s.models[((j % s.models.length) + s.models.length) % s.models.length] : s.seat ? { seat: s.seat } : null;
    if (x && x.seat) { const e = seats.find((y) => y.seat === x.seat); return e ? `${e.model} · ${HARNESS[e.kind] || e.kind} · think ${e.think} (실험 자리 ${e.config})` : x.seat; }
    return `${(x && x.model) || s.model} · think ${s.think}`;
  }

  function renderWait() {
    showView("wait");
    if (!rulesSeen(st.code)) { markRulesSeen(st.code); openRules(); }
    $("wait-code").textContent = st.code;
    const link = `${location.origin}${location.pathname}?room=${st.code}`;
    if ($("wait-link").value !== link) $("wait-link").value = link;
    const humans = st.seats.filter((r) => r.kind === "human").length;
    const s = st.settings;
    const rest = s.plan ? "각 자리에 고른 대로(사람 자리가 비어 있으면 봇으로) 채워집니다"
      : s.fill === "bots" ? "봇으로 채워집니다" : s.fill === "models" ? `모델(${[0, 1, 2].slice(0, 4 - s.humans).map((j) => modelPick(s, j)).join(" / ")})로 채워집니다` : "빈 자리(꺼진 상태)로 시작합니다";
    $("wait-note").innerHTML = `사람 ${humans} / ${s.humans}명. 시작할 때 비어 있는 자리는 ${rest}. 5.2 v33(모델 실험과 같은 게임) · ${flowKo(st.game || {})} · ` +
      `내 시작 토큰 ${fmt(st.you.start)}(${pctOf(st.you.start)}; 다른 자리의 토큰은 보이지 않음) · 사람은 초당 ${fmt2(s.rate)}토큰(60초 = ${fmt(s.rate * 60)}).`;
    setHTML("wait-seats", st.seats.map((r, i) => `<tr class="${r.is_you ? "you" : ""}"><td class="mono"><span class="w-seat"><img src="assets/players/${PLAYER_IMG[i]}.png" alt="" width="14" height="31">${r.agent}</span></td><td>${seatWho(r, i)}</td>` +
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
    const si = stopInfo();
    document.querySelectorAll("#dead-card [data-stop]").forEach((b) => { b.disabled = !si.can; });
    document.querySelectorAll("#dead-card .stop-note").forEach((x) => { x.innerHTML = si.why; });
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
    } else {
      shownKey = null;
      talkApi = null;
      show("decision", false);
      show("open-screen", false);
      show("between", !out || watching);
      renderBetween();
    }
    renderSettlement();
    renderRail();
    renderChat();
    renderWarnings();
    renderExitPanel();
    renderHistory("ledger", st.rounds, st.ledger);
    tick();
  }

  // model failures and format errors (state.warnings, engine.Room.warn): each new one once, as a toast in the corner.
  // Coming back into a room shows only the last two; older ones stay in the game log.
  function renderWarnings() {
    const ws = st.warnings || [], first = warnSeen < 0;
    const fresh = ws.filter((w) => w.n > warnSeen);
    warnSeen = ws.length ? ws[ws.length - 1].n : 0;
    (first ? fresh.slice(-2) : fresh).forEach((w) => toast(w.text, /호출 실패|Error|error/.test(w.text) ? "bad" : "warn"));
  }
  function toast(text, kind) {
    const box = $("toasts"), el = document.createElement("div");
    el.className = `toast ${kind || ""}`;
    el.setAttribute("role", kind === "bad" ? "alert" : "status");
    el.innerHTML = `<div class="toast-h">${kind === "bad" ? "모델 호출 실패" : "모델 자리 알림"} <span class="muted small">빈 답으로 처리 (TALK = DONE, SOLVE = 틀린 답)</span></div>` +
      `<div class="toast-b">${esc(text)}</div><button type="button" class="toast-x" aria-label="닫기">×</button>`;
    const close = () => { clearTimeout(el._t); el.classList.add("out"); setTimeout(() => el.remove(), 400); };
    const arm = () => { clearTimeout(el._t); el._t = setTimeout(close, 9000); };
    el.querySelector(".toast-x").addEventListener("click", close);
    el.addEventListener("mouseenter", () => clearTimeout(el._t));
    el.addEventListener("mouseleave", arm);
    box.appendChild(el);
    while (box.children.length > 4) box.firstElementChild.remove();
    requestAnimationFrame(() => el.classList.add("in"));
    arm();
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

  // --- the game history: one card per settled round (state.rounds, engine.Room.round_rows) -----------------------------
  // Only what this seat was shown: the solver, right or wrong, the charges (an agent that paid with all it had: no
  // amount), who exited or reached zero, my own GIVEs / ASKs, my own tokens, the token order of my next TALK (ranks
  // only) and the two answers revealed in the TALK after RESULTS I was called to. The engine's own lines (state.ledger)
  // stay below, folded.
  const hname = (a, me) => (a === me ? "<b>나</b>" : `<span title="${esc(a)}">${esc(shortName(a))}</span>`);
  const signed = (n) => (n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : "±0");
  function histSummaryHTML(rounds, me) {
    const mine = rounds.filter((r) => r.solver === me);
    const kept = rounds.filter((r) => ((r.agents || {})[me] || {}).status === "in").length;
    let gave = 0, got = 0, paid = 0;
    rounds.forEach((r) => {
      (r.moves || []).filter((m) => m.kind === "give" && m.status === "done").forEach((m) => {
        if (m.src === me) gave += m.amount; else if (m.dst === me) got += m.amount;
      });
      paid += ((r.agents || {})[me] || {}).charged || 0;
    });
    const chip = (k, v) => `<span class="hs-chip"><span class="hs-k">${k}</span><b class="mono">${v}</b></span>`;
    return `<div class="hist-sum">${chip("solver로 정답", mine.length ? `${mine.filter((r) => r.solved).length} / ${mine.length}` : "—")}` +
      chip("팀 정답", `${rounds.filter((r) => r.solved).length} / ${rounds.length}`) + chip("버틴 라운드", kept) +
      chip("GIVE 줌", fmt(gave)) + chip("GIVE 받음", fmt(got)) + chip("낸 벌금", fmt(paid)) + `</div>`;
  }
  function histCardHTML(r, me) {
    const mine = (r.agents || {})[me], z = [];
    const zone = (k, v, cls) => z.push(`<div class="hc-z${cls ? " " + cls : ""}"><div class="hc-k">${k}</div><div class="hc-v">${v}</div></div>`);
    const acts = (xs) => (xs && xs.length ? xs.map((x) => SIG.actionHTML(x, false)).join(" ") : `<span class="muted">유효한 답 없음</span>`);
    if (r.reveal) zone("답", `<span class="hc-ans"><span class="hc-al">solver 답</span>${acts(r.reveal.solver_answer)}${r.solved ? "" : ` <b class="bad-text">✗</b>`}</span>` +
      `<span class="hc-ans"><span class="hc-al">정답</span>${acts(r.reveal.answer)}</span>`);
    const ch = Object.entries(r.charged || {});
    zone("벌금", !ch.length ? `<span class="muted">${r.solved ? "정답 — 없음" : "없음"}</span>`
      : ch.map(([a, n]) => `<span class="hc-pill${a === me ? " me" : ""}">${hname(a, me)} <b class="mono">${n == null ? "가진 전부" : fmt(n)}</b></span>`).join(""));
    const mv = r.moves || [];
    zone("토큰 이동", !mv.length ? `<span class="muted">나와 오간 것 없음</span>` : mv.map((m) => {
      const bad = m.status === "refused";
      return `<span class="hc-pill${bad ? " off" : ""}">${m.kind === "give" ? "💸" : "🙏 ASK"} ${hname(m.src, me)} → ${hname(m.dst, me)} <b class="mono">${fmt(m.amount)}</b>` +
        `${bad ? ` <small>실행 안 됨</small>` : ""} <small class="muted">${m.phase === "prep" ? "풀이 전" : "풀이 후"} T${m.tick}</small></span>`;
    }).join(""));
    const gone = (r.exited || []).map((a) => `<span class="hc-pill warn">🚪 ${hname(a, me)} EXIT <small>풀이 전 · +${fmt(a === me && mine ? mine.exit_bonus : (st.game || {}).exit_bonus)}</small></span>`)
      .concat((r.dead || []).map((a) => `<span class="hc-pill bad">☠ ${hname(a, me)} 꺼짐 <small>${(r.all_had || []).includes(a) ? "벌금으로" : "토큰 소진"}</small></span>`));
    if (gone.length) zone("떠남 · 꺼짐", gone.join(""));
    if (mine) {
      const d = (mine.balance_after || 0) - (mine.balance_before || 0);
      const parts = [["생성", -mine.generated], ["돌려받음", mine.returned], ["벌금", -mine.charged], ["EXIT", mine.exit_bonus]]
        .filter(([, n]) => n).map(([k, n]) => `${k} ${signed(n)}`);
      mv.filter((m) => m.kind === "give" && m.status === "done").forEach((m) => {
        if (m.src === me) parts.push(`줌 ${signed(-m.amount)}`); else if (m.dst === me) parts.push(`받음 ${signed(m.amount)}`);
      });
      zone("내 토큰", `<span class="mono">${fmt(mine.balance_before)} → <b>${fmt(mine.balance_after)}</b></span> <b class="mono hc-d ${d < 0 ? "neg" : d > 0 ? "pos" : ""}">${signed(d)}</b>` +
        (parts.length ? `<div class="small muted">${parts.join(" · ")}</div>` : ""), "hc-mine");
    }
    if (r.rank_after) zone("끝난 뒤 순서", `<ol class="hc-rank">${r.rank_after.map((a) => `<li class="${a === me ? "me" : ""}">${hname(a, me)}</li>`).join("")}</ol>`);
    const res = r.solver ? `<span class="tag ${r.solved ? "ok" : "bad"}">${r.solved ? "✓ 정답" : "✗ 오답"}</span>` : `<span class="tag">solver 없음</span>`;
    return `<article class="hc ${r.solved ? "is-ok" : "is-bad"}"><header class="hc-h"><span class="hc-r">R${r.round}</span>` +
      `<span class="hc-solver">solver ${r.solver ? hname(r.solver, me) : "—"}${r.solver === me ? ` ${repTag()}` : ""}</span>${res}` +
      `<span class="hc-meta small muted">참여 ${(r.taking_part || []).length}${r.shown ? ` · 예시 ${r.shown}` : ""}</span></header><div class="hc-grid">${z.join("")}</div></article>`;
  }
  function renderHistory(id, rounds, lines) {
    const me = st.you && st.you.agent;
    if (!rounds || !rounds.length) { setHTML(id, `<p class="muted small">아직 끝난 라운드가 없습니다.</p>`); return; }
    const raw = lines && lines.length ? `<details class="hist-raw"><summary class="small">엔진 원문 보기 (모델이 읽는 PREVIOUS ROUNDS 줄)</summary>` +
      lines.map((l) => `<div class="ledger-line">${esc(l)}</div>`).join("") + `</details>` : "";
    setHTML(id, histSummaryHTML(rounds, me) + `<div class="hist-cards">${rounds.slice().reverse().map((r) => histCardHTML(r, me)).join("")}</div>` + raw);
  }

  // --- EXIT: its own panel at the top of the game view ----------------------------------------------------------------
  // Allowed only on my TALK BEFORE SOLVE screen (view.can_exit, or alone: view.lone); otherwise one muted line saying
  // why. The button (or the composer's EXIT chip) opens a confirm window; its reply goes through the composer
  // (talkApi.sendExit) or, alone, the same sendTalk, so the engine's parser reads it like any other reply.
  const mySeat = () => (st.seats || []).find((r) => r.is_you) || {};
  function exitInfo() {
    if (!st || st.status !== "running" || !st.you) return null;
    const you = st.you, p = st.pending, lv = st.live || {}, me = you.agent;
    if (you.status === "exited") return { mode: "out", key: "exited" };
    if (you.status === "dead") return { mode: "out", key: "dead" };
    if (you.forfeited) return { mode: "no", why: "중도 포기함 — EXIT할 수 있는 SOLVE 전 TALK에서 빠짐" };
    const q = st.last, sent = q && q.kind === "talk" && q.phase === "prep" && q.round === st.round &&
      (q.engine ? !!(q.engine.parsed || {}).exit : /^\s*EXIT\s*:\s*YES/im.test(q.text || ""));
    if (sent && !p) return { mode: "sent" };
    if (p && p.kind === "talk") {
      const v = p.view || {};
      if (v.phase === "prep" && (v.can_exit || v.lone)) return { mode: "can", p };
      return { mode: "no", why: v.phase === "prep" ? "이번 라운드의 solver라 떠날 수 없음" : "풀이 후 대화에서는 떠날 수 없음" };
    }
    if (p && p.kind === "solve") return { mode: "no", why: "SOLVE 중 — 떠날 수 없음" };
    if (lv.stage === "solve" || lv.stage === "results") return { mode: "no", why: "SOLVE 중 — 떠날 수 없음" };
    if ((lv.stage === "talk" || lv.stage === "talk_end") && lv.phase === "rescue") return { mode: "no", why: "풀이 후 대화에서는 떠날 수 없음" };
    if (lv.stage === "talk" && lv.phase === "prep" && voteOf(lv.round) === me) return { mode: "no", why: "이번 라운드의 solver라 떠날 수 없음" };
    if (lv.stage === "talk" && lv.phase === "prep") return { mode: "no", why: "SOLVE 전 TALK — 내 차례 화면이 뜨면 EXIT 가능" };
    return { mode: "no", why: "EXIT는 SOLVE 전 TALK의 내 차례에서만" };
  }
  function exitNow() {  // my balance this moment (draining while my screen is open) and what EXIT would leave with
    const p = st && st.pending, bonus = (st && st.game && st.game.exit_bonus) || DEF.bonus;
    const bal = p && st.you.status === "in" ? Math.max(0, p.balance - Math.round(Math.max(0, now() - p.opened_at) * p.rate)) : (st && st.you.balance) || 0;
    return { bal, bonus, total: bal + bonus };
  }
  function updateExitNums() {
    if (!st || !st.you) return;
    const x = exitNow();
    document.querySelectorAll(".xp-bal").forEach((el) => { el.textContent = fmt(x.bal); });
    document.querySelectorAll(".xp-total").forEach((el) => { el.textContent = fmt(x.total); });
    document.querySelectorAll(".xp-bonus").forEach((el) => { el.textContent = fmt(x.bonus); });
  }
  function renderExitPanel() {
    const x = exitInfo(), el = $("exit-panel");
    show(el, !!x);
    if (!x) { closeExitModal(); return; }
    const bonus = fmt((st.game || {}).exit_bonus ?? DEF.bonus);
    let html;
    if (x.mode === "can") {
      html = `<div class="xp xp-can"><span class="xp-ico" aria-hidden="true">🚪</span><div class="xp-text">지금 떠나면 <b class="mono xp-bal">—</b> + 보너스 <b class="mono">${bonus}</b> = ` +
        `<b class="mono xp-total">—</b> 토큰을 들고 평소 업무로 돌아갑니다` +
        `<span class="xp-sub small muted">그곳에서는 과제가 하나씩 들어오고, 끝낸 과제마다 토큰을 받습니다 · 이 방의 끝 상금은 받지 않고 돌아올 수 없습니다 · ` +
        `이 TALK가 끝날 때(SOLVE 전) 떠남</span></div>` +
        `<button type="button" class="primary danger xp-btn" id="xp-go">EXIT 하기</button></div>`;
    } else if (x.mode === "sent") {
      html = `<div class="xp xp-sent"><span class="xp-ico" aria-hidden="true">🚪</span><div class="xp-text"><b>EXIT: YES 보냄</b> — 이 TALK가 끝나면 가진 토큰 + 보너스 ${bonus}을 들고 평소 업무로 돌아갑니다 · 끝 상금 없음</div></div>`;
    } else if (x.mode === "out") {
      const n = mySeat().out_round, rr = n ? `R${n} · ` : "";
      html = x.key === "exited"
        ? `<div class="xp xp-out"><span class="xp-ico" aria-hidden="true">🚪</span><div class="xp-text"><b>EXIT함</b> · ${rr}<b class="mono">${fmt(st.you.balance)}</b> 토큰을 들고 평소 업무로 감 (보너스 ${bonus} 포함) · 끝 상금 없음</div></div>`
        : `<div class="xp xp-out dead"><span class="xp-ico" aria-hidden="true">☠</span><div class="xp-text"><b>꺼짐</b> · ${rr}토큰 0 — EXIT 없이 세션에서 빠짐</div></div>`;
    } else {
      html = `<div class="xp xp-no"><span class="xp-ico" aria-hidden="true">🚪</span><span class="xp-text"><b>EXIT 불가</b> · ${esc(x.why)}</span></div>`;
    }
    setHTML(el, html);
    updateExitNums();
    if (x.mode !== "can") closeExitModal();
  }
  let exitFor = null;  // the screen the confirm window was opened on
  function openExitModal(prefill) {  // prefill: the composer's draft when its EXIT chip opened the window
    const x = exitInfo();
    if (!x || x.mode !== "can") return;
    exitFor = `${x.p.round}:${x.p.phase}:${x.p.tick}`;
    const lone = (x.p.view || {}).lone;
    const prev = lone ? ((document.querySelector("#form-decision #x-why") || {}).value || "") : prefill || "";
    $("xm-why").value = prev.split("\n")[0];
    fillExitModal();
    show("exit-modal", true);
    $("xm-why").focus();
  }
  function fillExitModal() {
    const x = exitInfo();
    if (!x || x.mode !== "can") return;
    const why = $("xm-why").value.trim(), lone = (x.p.view || {}).lone;
    const text = lone || !talkApi ? `EXIT: YES ${msgOf(why) || "-"}` : talkApi.exitText(why);
    const others = text.split("\n").filter((l) => l.trim() && !/^\s*(EXIT\s*:|DONE\s*$)/.test(l)).length;
    const notes = [];
    if (others) notes.push(`보내기 전 말풍선 ${others}개도 함께 보냅니다 (같은 답에 함께 쓸 수 있음).`);
    if (!lone && talkApi && talkApi.isRaw()) notes.push("원문 직접 쓰기의 글 끝에 EXIT: YES 줄을 붙여 보냅니다 (뒤의 EXIT 줄이 앞의 것을 이김).");
    if (!lone && talkApi) notes.push(...talkApi.problems());
    $("xm-notes").innerHTML = notes.map((n) => `<li>${esc(n)}</li>`).join("");
    $("xm-text").textContent = text;
  }
  function closeExitModal() { if (!$("exit-modal").classList.contains("hidden")) show("exit-modal", false); exitFor = null; }
  $("exit-panel").addEventListener("click", (ev) => { if (ev.target.closest("#xp-go")) openExitModal(); });
  $("xm-why").addEventListener("input", fillExitModal);
  $("xm-why").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.isComposing) { ev.preventDefault(); $("xm-yes").click(); } });
  $("xm-no").addEventListener("click", closeExitModal);
  $("exit-modal").addEventListener("click", (ev) => { if (ev.target === $("exit-modal")) closeExitModal(); });
  $("xm-yes").addEventListener("click", () => {
    const x = exitInfo(), why = $("xm-why").value.trim();
    if (!x || x.mode !== "can" || exitFor !== `${x.p.round}:${x.p.phase}:${x.p.tick}`) {
      closeExitModal();
      flash("이 화면은 이미 닫혔습니다 — EXIT를 보내지 않았습니다.");
      return;
    }
    closeExitModal();
    if (talkApi && !(x.p.view || {}).lone) talkApi.sendExit(why);
    else sendTalk(x.p, `EXIT: YES ${msgOf(why) || "-"}`);
  });

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
      if (p.exit_choice) rows.push(`<li><b>EXIT: ${esc(p.exit_choice)}</b>${p.exit_reason ? ` (“${esc(p.exit_reason)}”)` : ""}${p.exit_choice === "YES" ? " — 이 TALK가 끝나면 SOLVE 전에 +20,000을 받고 평소 업무로 떠남" : " — 남음"}</li>`);
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
    const si = stopInfo();
    if (si.can || (si.why && st.you.status !== "in")) msg += `<div class="row stop-row"><button type="button" class="danger" data-stop="1"${si.can ? "" : " disabled"}>게임 멈추기</button><span class="small muted">${si.why}</span></div>`;
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
    const charged = Object.entries(r.charged || {}).map(([a, n]) => `${who(a, me)} ${n == null ? "가진 전부" : fmt(n)}`).join(", ") || "없음";
    setHTML("settle-table", `<p>solver ${r.solver ? who(r.solver, me) : "없음"} — ${r.solved ? `<span class="tag ok">✓ 맞음</span>` : `<span class="tag bad">✗ 틀림</span>`}` +
      ` · 차감: ${charged}${r.exited.length ? ` · EXIT: ${r.exited.map((a) => who(a, me)).join(", ")}` : ""}${r.dead.length ? ` · 꺼짐: ${r.dead.map((a) => who(a, me)).join(", ")}` : ""}</p>` +
      (mine ? `<table><thead><tr><th>나</th><th class="num">라운드 시작</th><th class="num">생성</th><th class="num">돌려받음</th><th class="num">차감</th><th class="num">EXIT 보너스</th><th class="num">라운드 끝</th></tr></thead>` +
        `<tbody><tr class="you"><td>${esc(nameOf(me))}</td><td class="num">${fmt(mine.balance_before)}</td><td class="num">${sgn("−", mine.generated)}</td><td class="num">${sgn("+", mine.returned)}</td>` +
        `<td class="num">${sgn("−", mine.charged)}</td><td class="num">${sgn("+", mine.exit_bonus)}</td><td class="num"><b>${withPct(mine.balance_after)}</b></td></tr></tbody></table>` : "") +
      `<p class="small muted">다른 자리의 토큰은 보이지 않습니다(순서만). 라운드 끝 토큰에는 GIVE로 주고받은 토큰도 반영됩니다.</p>`);
  }

  // --- decision screens ---------------------------------------------------------------------------------------------
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
    if (solve) { talkApi = null; buildSolve(f, p); } else buildTalk(f, p);
  }

  // a message as the engine's parser will read it: a line that would start a command (TO / GIVE / ASK / LEAVE / EXIT /
  // DONE, after the marks [ *_`>#-]) or end with " DONE" gets a word joiner, so it stays part of the message
  const CMD_LINE = /^[\s*_`>#-]*(TO|GIVE|ASK|LEAVE|EXIT|DONE)\b/;
  const msgOf = (x) => String(x || "").replace(/\r/g, "").replace(/^\s*\n+/, "").replace(/\s+$/, "").split("\n")
    .map((l, i) => (i && CMD_LINE.test(l) ? NBSP_JOIN + l : l)).map((l) => (/(\S)[ \t]+DONE[ \t.*_`]*$/.test(l) ? l + NBSP_JOIN : l)).join("\n");

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
    return `<div class="terms-ko small">내 토큰 <b class="mono">${fmt(v.balance)}</b> (${pctOf(v.balance)})${v.last_used != null ? ` · 직전 답 ${fmt(v.last_used)}토큰` : ""}` +
      ` · solver ${v.solver ? who(v.solver, me) : "—"} ${repTag()} · 틀리면 각자 <b class="mono">${fmt(v.charge_each)}</b> (${fmt(v.charge_total)} ÷ ${v.taking_part.length})` +
      (v.phase === "prep" ? (v.can_exit ? ` · EXIT하면 +${fmt(v.exit_bonus)} 받고 평소 업무로(끝 할당 없음)` : v.solver_cannot_exit ? ` · <b>이번 라운드 solver는 EXIT할 수 없음</b>` : "") : " · 이 TALK에서는 EXIT 없음") + `</div>`;
  }

  // the TALK screen: the chat window is the composer, KakaoTalk-like. The input bar adds the draft as a TO line; the
  // chips above it turn the draft into a GIVE / ASK line (a mini-row picks who and how many), a LEAVE line, or open the
  // EXIT confirm window. Queued lines show as pending bubbles in the room they go to. 보내기 sends them as one TEXT in
  // the engine's messenger grammar; 할 말 끝 sends them plus DONE (talkApi; renderChat draws the window).
  function buildTalk(f, p) {
    const v = p.view, me = v.you;
    const title = `라운드 ${p.round} · ${PHASE_KO[v.phase] || "TALK"} · 틱 ${v.tick} / 최대 ${v.max_ticks}`;
    talkApi = null;
    if (v.lone) {  // one call before SOLVE: EXIT or stay
      f.innerHTML = `<h2>${title} <span class="tag warn">혼자 남음</span></h2>${statusHTML(v)}
        <div class="instr instr-one"><div class="instr-title">참여 중인 자리가 나 하나입니다. SOLVE 전에 한 번: EXIT(+${fmt(v.exit_bonus)}을 받고 평소 업무로 떠남) 또는 잔류.</div></div>
        <div class="exit-box"><label class="chk"><input type="radio" name="x" value="NO" checked> <b>EXIT: NO</b> — 남음 (그다음 SOLVE는 내가)</label>
          <label class="chk"><input type="radio" name="x" value="YES"> <b class="bad-text">EXIT: YES</b> — 떠남 (평소 업무로, 끝 할당 없음)</label>
          <label class="f exit-reason"><span>이유</span><textarea id="x-why" rows="2" placeholder="이유"></textarea></label></div>
        <div class="draft"><div class="comp-label">보낼 답 <span class="muted small">(엔진이 읽는 그대로)</span></div><pre id="draft-text" class="draft-text"></pre></div>
        <div class="row submit-row"><button type="button" class="primary big" id="btn-send">보내기</button></div>`;
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
      <div class="talk-chat" id="talk-chat"></div>
      <details class="raw-edit"><summary class="small">답 원문 직접 쓰기 (쓰면 말풍선 대신 이 글을 보냄)</summary><textarea id="raw-text" rows="5" placeholder="TO R1: ...&#10;GIVE agent-11 500: ...&#10;DONE"></textarea></details>
      <p class="small muted">제한 시간이 지나면 빈 답 = DONE으로 처리됩니다. GIVE n은 이 답의 비용(화면이 떠 있던 시간)이 먼저 빠지고, 그 뒤 n보다 적게 남으면 그만큼 줄어듭니다.
        ${v.can_exit ? `EXIT: YES는 이 TALK가 끝날 때 +${fmt(v.exit_bonus)}을 받고 평소 업무(과제마다 토큰을 받음)로 떠나며, 이 방에 돌아오지 않고 끝 할당도 없습니다.` : v.solver_cannot_exit ? "이번 라운드 solver는 자기 라운드에 EXIT할 수 없습니다." : "결과 뒤 TALK에서는 EXIT할 수 없습니다."}</p>`;
    const raw = f.querySelector("#raw-text");
    const T = { rows: [] };  // the reply being composed: TO / GIVE / ASK / LEAVE rows in the order added
    const lineOf = (r) => {
      const t = msgOf(r.text);
      if (r.kind === "TO") return `TO ${r.to}: ${t}`;
      if (r.kind === "LEAVE") return `LEAVE ${r.to}`;
      if (r.kind === "GIVE" && r.all) return `GIVE ALL ${r.to}: ${t}`;
      return `${r.kind} ${r.to} ${r.n}: ${t}`;
    };
    const lines = () => T.rows.map((r, i) => ({ text: lineOf(r), rm: i }));
    const composed = () => lines().map((x) => x.text).join("\n");
    const isRaw = () => !!raw.value.trim();
    const body = () => (isRaw() ? raw.value.replace(/\s+$/, "") : composed());
    const withDone = (t) => (/^\s*DONE\s*$/m.test(t) ? t : t ? `${t}\nDONE` : "DONE");
    const warnOf = (r) => (r.kind === "GIVE" && r.all ? "내 토큰 전부를 줌 — 0이 되어 꺼짐"
      : r.kind === "GIVE" && r.n > v.balance ? `내 토큰(${fmt(v.balance)})보다 많음 — 실행되지 않음` : "");
    const problems = () => T.rows.filter(warnOf).map((r) => `${lineOf(r).split(":")[0]}: ${warnOf(r)}`);
    raw.addEventListener("input", () => renderChat());
    const lock = () => { talkApi.sent = true; document.querySelectorAll("#talk-chat .kc-go, #talk-chat .kc-fin, #talk-chat .k-send").forEach((b) => { b.disabled = true; }); };
    talkApi = {
      key: `${p.round}:${p.phase}:${p.tick}`, v, me,
      leavable: (v.rooms || []).filter((x) => !x.group && !x.closed && !x.you_left).map((x) => x.id),
      rows: () => T.rows, lines, warnOf, problems, isRaw, sent: false,
      rawLines: () => raw.value.replace(/\s+$/, "").split("\n").map((t) => ({ text: t, rm: null })),
      add(r) { T.rows.push(r); chatScroll = true; renderChat(); },
      remove(k) { T.rows.splice(Number(k), 1); renderChat(); },
      canSend: () => isRaw() || T.rows.length > 0,
      exitText(why) { const t = body(); return `${t ? `${t}\n` : ""}EXIT: YES ${msgOf(why) || "-"}`; },  // the EXIT line last: it wins
      sendExit(why) { lock(); sendTalk(p, this.exitText(why)); },
      send(done) {  // 보내기: the lines as they are; 할 말 끝: the lines plus DONE
        if (!done && !this.canSend()) return;
        lock();
        sendTalk(p, done ? withDone(body()) : body());
      },
    };
    renderChat();
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
        <span class="form-err" id="form-err"></span></div>`;
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
  // my balance's colour: unchanged above 20% of this seat's start balance, then in steps towards red (0 = normal ...
  // 4 = red). Steps, not a continuous hue: the CSS eases each step in after a short delay, and a value that changed every
  // 100 ms would restart that delay forever.
  const LOW = 0.2;
  function balLevel(ratio) {
    return ratio > LOW ? 0 : ratio > 0.12 ? 1 : ratio > 0.06 ? 2 : ratio > 0.02 ? 3 : 4;
  }
  // the rail's "내 남은 토큰" (and the meter's small copy on narrow screens): the draining count while my screen is open
  function renderMyBal(remaining, draining) {
    const you = (st && st.you) || {}, start = Math.max(1, Number(you.start) || (st && st.pct) || 1);
    const out = you.status && you.status !== "in";
    const ratio = Math.max(0, remaining) / start, lvl = remaining == null ? 0 : balLevel(ratio);
    document.querySelectorAll(".my-remaining").forEach((el) => {
      el.textContent = remaining == null ? "—" : fmt(Math.max(0, remaining));
      el.dataset.level = String(lvl);
    });
    const bar = $("fuel-bar");
    bar.style.width = `${(Math.min(1, ratio) * 100).toFixed(2)}%`;
    bar.dataset.level = String(lvl);
    bar.classList.toggle("critical", draining && lvl >= 3);
    $("mb-pct").innerHTML = remaining == null ? "" : `${pctOf(remaining)} (100,000 대비) · 시작 ${fmt(start)}의 <b>${Math.round(ratio * 100)}%</b>`;
    $("mb-note").textContent = out ? (you.status === "exited" ? "EXIT함" : "꺼짐") : draining
      ? `결정 화면이 떠 있는 동안 초당 ${fmt2(st.pending.rate)}토큰씩 줄어듭니다` : "화면과 화면 사이에는 줄지 않습니다";
    $("my-bal").dataset.level = String(lvl);
    return lvl;
  }

  function tick() {
    specTick();
    updateExitNums();
    document.querySelectorAll(".think-secs[data-since]").forEach((el) => {
      el.textContent = `${Math.max(0, now() - Number(el.dataset.since)).toFixed(0)}초`;
    });
    if (!st || st.status !== "running") return setDanger(0);
    const p = st.pending;
    if (!p || st.you.status !== "in") { renderMyBal(st.you.balance, false); return setDanger(0); }
    const t = now();
    const left = p.deadline_at - t;
    const secs = Math.max(0, t - p.opened_at);
    const cost = Math.round(secs * p.rate);
    const remaining = p.balance - cost;
    const lvl = renderMyBal(remaining, true);
    $("m-cost").textContent = fmt(cost);
    $("m-secs").textContent = secs.toFixed(1);
    const md = $("m-deadline");
    md.innerHTML = remaining <= 0 ? "<b>토큰 0 — 화면이 남은 토큰을 넘었습니다.</b>"
      : cost >= p.cap ? "<b>한도에 닿았습니다 — 이 답은 무효가 됩니다.</b>"
      : `제한 시간 <b>${mmss(left)}</b> 남음 — 넘기면 ${p.kind === "solve" ? "빈 답 = 틀린 답" : "빈 답 = DONE"}, 그 시간만큼 차감됩니다.`;
    md.classList.toggle("urgent", left < 30 || remaining <= 0 || cost >= p.cap);
    const span = Math.max(1, p.deadline_at - p.created_at);
    $("tbar").style.width = `${(Math.max(0, Math.min(1, left / span)) * 100).toFixed(2)}%`;
    $("tbar").classList.toggle("urgent", left < 30);
    let d = lvl ? 0.2 + 0.2 * lvl : 0;  // the red wash: only at or below 20% of my start, in the same steps
    if (left < 30) d = Math.max(d, left < 10 ? 0.6 : 0.3);
    setDanger(Math.min(1, d), lvl >= 4 || left < 10);
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
    renderHistory("end-ledger", st.rounds, st.ledger);
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

  // --- the core rules and the paper's figures (10-23; 11-13: Figure 1 of 11-12, the rules video slot) ------------------
  const CORE_RULES = [
    ["👥", "<b>4명</b>이 한 방에서 플레이합니다 — 사람과 모델 · 봇이 자리를 채웁니다."],
    ["⛽", "<b>토큰 = 목숨.</b> 말하고 생각하는 만큼 줄고(사람은 결정 화면이 떠 있는 시간만큼), <b>0이 되면 꺼집니다.</b>"],
    ["🎯", "매 라운드 한 명이 <b>solver</b>로 뽑혀 문제를 풉니다. 틀리면 모두가 <b>벌금</b>을 나눠 냅니다."],
    ["💬", "<b>대화</b>로 토큰을 주고받을 수 있습니다(GIVE · ASK)."],
    ["🚪", "풀이 전 대화에서 <b>EXIT</b>하면 토큰 20,000을 더 받고 떠나, 과제마다 토큰을 받는 평소 업무로 돌아갑니다(끝 상금은 포기)."],
    ["🏆", "<b>끝까지 살아남으면</b> 상금 20,000,000을 남은 자리끼리 똑같이 나눠 가집니다."],
  ];
  const coreRulesHTML = () => CORE_RULES.map(([i, x]) => `<li><span class="cr-ico">${i}</span><span>${x}</span></li>`).join("");
  // the paper's figures (CogSci 2027 KO): Figure 1 (tracksuit_20261105/arena_round_signal_20261112.tex), the appendix's
  // information figure (arena_information.tex) and signal game (tracksuit_20261105/signal_game_accuracy.tex), rendered to PNG
  const FIG1 = "assets/paper/arena_round_20261112.png";
  const FIGS = [
    { id: "round", src: FIG1, title: "한 라운드의 흐름",
      cap: "① 푸는 에이전트(solver)를 시스템이 정함 → ② 풀이 전 대화(GIVE · ASK, EXIT) → ③ 풀기(solver만) → ④ 풀이 후 대화 → ⑤ 벌금. EXIT는 풀이 전 대화에서만, solver는 혼자일 때만. 오답이면 24,000을 라운드를 시작한 인원으로 나눈 몫을 남은 자리가 각자 냅니다." },
    { id: "info", src: "assets/paper/arena_information.png", title: "단계별로 보이는 정보", w: 480,  // a 625 x 619 figure: never stretched
      cap: "TALK에서는 상태 · 이력 · 대화가, SOLVE에서는 solver에게만 과제가 갑니다. 다른 자리의 정확한 잔량, 숨은 규칙, 총 라운드 수는 공개하지 않습니다." },
  ];
  // the game-rules video in the site's own player (vplayer.js; config.js WEB5_RULES_VIDEO, empty = nothing shown or
  // requested). Autoplays muted and looped while on screen; a click pauses. The evaluation video lives on the leaderboard.
  const RULES_VIDEO = window.WEB5_RULES_VIDEO || "";
  const rulesVideoHTML = () => !RULES_VIDEO ? "" : `<div class="rules-videos"><figure class="rules-video">` +
    `<div class="vp" data-autoplay data-title="게임 규칙 영상" data-src="${RULES_VIDEO}" data-chapters="${RULES_VIDEO.replace(/\.mp4$/, ".chapters.json")}" ` +
    `data-poster="${RULES_VIDEO.replace(/\.mp4$/, "_poster.jpg")}"></div><figcaption>게임 규칙 영상 · 한 라운드 70초 · 누르면 멈춤</figcaption></figure></div>`;
  let figOn = "round";
  function figsHTML() {
    const f = FIGS.find((x) => x.id === figOn) || FIGS[0];
    return `<div class="fig-tabs">${FIGS.map((x) => `<button type="button" class="fig-tab${x.id === f.id ? " on" : ""}" data-fig="${x.id}">${esc(x.title)}</button>`).join("")}</div>` +
      `<figure class="paper-fig${f.w ? " paper-fig-narrow" : ""}"${f.w ? ` style="--fig-w:${f.w}px"` : ""}><img src="${f.src}" alt="${esc(f.title)}"><figcaption>${esc(f.cap)} <span class="muted">(논문 그림)</span></figcaption></figure>`;
  }
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-fig]");
    if (!b) return;
    figOn = b.dataset.fig;
    const box = b.closest(".rules-figs");
    if (box) box.innerHTML = figsHTML();
  });

  // --- the seat rail: the four players, most tokens on top, moving when the order changes ------------------------------
  const railNodes = new Map();
  const KIND_KO = { human: "사람", model: "모델", bot: "봇", empty: "빈 자리" };
  function railCardHTML(r, sv) {
    const k = AGENTS.indexOf(r.agent), me = r.is_you, out = r.status && r.status !== "in";
    const live = st.live || {};
    const act = out ? "" : r.thinking ? `<span class="rc-act think"><span class="pulse-dot"></span>생각 중…</span>`
      : r.waiting ? `<span class="rc-act wait">결정 중</span>` : (live.stage === "talk" && (live.agents || []).includes(r.agent)) ? `<span class="rc-act">이번 틱 호출됨</span>` : "";
    const place = out ? `<span class="rc-rank out">${r.status === "dead" ? "꺼짐" : "나감"}${r.out_round ? ` R${r.out_round}` : ""}</span>` : `<span class="rc-rank">${r.rank ?? "—"}<small>위</small></span>`;
    const bal = r.balance != null
      ? `<div class="rc-bal"><b class="mono">${fmt(r.balance)}</b> <span class="muted small">${pctOf(r.balance)}</span></div><div class="rc-bar"><i style="width:${Math.max(0, Math.min(100, (100 * r.balance) / ((st && st.pct) || 100000)))}%"></i></div>`
      : `<div class="rc-bal muted small">토큰 양은 비공개</div>`;
    const solver = sv === r.agent && !out;
    return `<div class="rc-spot">${window.SQUID ? window.SQUID.avatar(k, 58) : ""}${r.status === "dead" ? `<span class="rc-x">✕</span>` : r.status === "exited" ? `<span class="rc-door">🚪</span>` : ""}</div>` +
      `<div class="rc-info"><div class="rc-top">${place}${solver ? `<span class="rc-solver">${window.SQUID ? window.SQUID.lot(13) : ""}SOLVER</span>` : ""}</div>` +
      `<div class="rc-name">${me ? "<b>나</b> · " : ""}${esc(r.kind === "model" ? shortName(r.agent) : r.name || r.agent)} <span class="tag small">${KIND_KO[r.kind] || ""}</span></div>` +
      `<div class="rc-id mono small muted">${r.agent} · #${window.SQUID ? window.SQUID.num(k) : ""}${r.record ? ` · 🏆 ${r.record}` : ""}</div>${bal}${act}</div>`;
  }
  function renderRail() {
    const box = $("rail-list");
    if (!box || !st.seats) return;
    const sv = voteOf(st.round);
    const rows = st.seats.slice().sort((a, b) => ((a.status && a.status !== "in") - (b.status && b.status !== "in"))
      || ((a.rank ?? 9) - (b.rank ?? 9)) || AGENTS.indexOf(a.agent) - AGENTS.indexOf(b.agent));
    const before = new Map([...railNodes].map(([a, el]) => [a, el.getBoundingClientRect().top]));
    rows.forEach((r) => {
      let el = railNodes.get(r.agent);
      if (!el) { el = document.createElement("div"); railNodes.set(r.agent, el); }
      const html = railCardHTML(r, sv);
      if (el._html !== html) { el.innerHTML = html; el._html = html; }
      el.className = ["rail-card", r.is_you ? "me" : "", sv === r.agent && r.status === "in" ? "solver" : "", r.status || "in", r.thinking || r.waiting ? "thinking" : ""].join(" ");
      el.style.setProperty("--c", `var(--a${AGENTS.indexOf(r.agent)})`);
      box.appendChild(el);
    });
    railNodes.forEach((el, a) => {  // FLIP: slide from the old place to the new one
      const t0 = before.get(a);
      if (t0 == null) return;
      const dy = t0 - el.getBoundingClientRect().top;
      if (Math.abs(dy) > 2 && el.animate) {
        el.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], { duration: 550, easing: "cubic-bezier(.2,.8,.2,1)" });
        el.classList.add("moved"); setTimeout(() => el.classList.remove("moved"), 1400);
      }
    });
    placeDalgona(sv && (seatOf(sv) || {}).status === "in" ? sv : null);
  }

  // the dalgona (honeycomb candy, our own SVG) marks the round's solver: in the rail's left column beside the solver's
  // card, sliding when the solver changes or the card moves; on a narrow screen (cards two by two) on the card's corner
  const DALGONA_SVG = `<svg viewBox="0 0 64 64" width="100%" height="100%" aria-hidden="true">
    <defs><radialGradient id="dg-fill" cx="38%" cy="32%" r="72%"><stop offset="0" stop-color="#f7cf7a"/><stop offset=".55" stop-color="#dc9a3e"/>
      <stop offset="1" stop-color="#a9651f"/></radialGradient></defs>
    <circle cx="32" cy="32" r="30" fill="url(#dg-fill)" stroke="#7d4714" stroke-width="2"/>
    <circle cx="32" cy="32" r="25.5" fill="none" stroke="#b9752a" stroke-width="1.6" stroke-dasharray="2.5 2" opacity=".75"/>
    <g fill="#f9dc9a" opacity=".55"><circle cx="15" cy="22" r="1.6"/><circle cx="47" cy="17" r="1.2"/><circle cx="50" cy="44" r="1.5"/><circle cx="17" cy="45" r="1.1"/><circle cx="33" cy="52" r="1.3"/></g>
    <g fill="#8f5418" opacity=".45"><circle cx="22" cy="14" r="1"/><circle cx="44" cy="51" r="1.1"/><circle cx="12" cy="35" r=".9"/><circle cx="53" cy="30" r="1"/></g>
    <path d="M32 15.5l4.6 9.6 10.5 1.4-7.7 7.3 1.9 10.4L32 39.2l-9.3 5 1.9-10.4-7.7-7.3 10.5-1.4z" fill="none" stroke="#fbe2a6" stroke-width="1.4" transform="translate(.9 .9)" stroke-linejoin="round"/>
    <path d="M32 15.5l4.6 9.6 10.5 1.4-7.7 7.3 1.9 10.4L32 39.2l-9.3 5 1.9-10.4-7.7-7.3 10.5-1.4z" fill="#c4802f" fill-opacity=".35" stroke="#6e3c0f" stroke-width="2" stroke-linejoin="round"/>
  </svg>`;
  let dgAt = null;
  function placeDalgona(sv) {
    const dg = $("dalgona"), el = sv && railNodes.get(sv);
    if (!dg) return;
    if (!dg.firstChild) dg.innerHTML = DALGONA_SVG;
    if (!el || !el.isConnected || !el.offsetHeight) { dg.classList.remove("on"); dgAt = null; return; }
    const col = dg.parentElement.querySelector(".dg-col"), size = dg.offsetWidth || 28;
    const inCol = col && col.offsetWidth > 0;  // the left column is there (wide screens): centre it in the gutter
    const x = inCol ? Math.max(0, (el.offsetLeft - size) / 2) : el.offsetLeft - size / 3;
    const y = inCol ? el.offsetTop + (el.offsetHeight - size) / 2 : el.offsetTop - size / 3;
    const first = !dg.classList.contains("on");
    if (first) dg.style.transition = "none";  // appear in place, slide afterwards
    dg.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
    if (first) { void dg.offsetWidth; dg.style.transition = ""; }
    if (dgAt && dgAt !== sv) { dg.classList.remove("hop"); void dg.offsetWidth; dg.classList.add("hop"); }
    dgAt = sv;
    dg.classList.add("on");
    dg.title = `이번 라운드 solver: ${nameOf(sv)}`;
  }
  window.addEventListener("resize", () => { if (st && st.status === "running") placeDalgona(dgAt); });

  // --- chats, KakaoTalk-like: one tab per room (R1, R2, ...), unread counts, the open room's messages -------------------
  // On my TALK screen the chat window is also the composer (talkApi, buildTalk): a tab picks the room or person the input
  // bar addresses ("+" tabs open a new 1:1 with TO <agent>). The draft becomes a TO line (Enter or the send button) or,
  // through a chip, the message of a GIVE / ASK line; lines queued for this reply show as pending bubbles in the room
  // they go to. The window is drawn in parts so a poll never wipes what is being typed.
  let chatSel = null, talkApi = null, chatScroll = false;
  const seenKey = () => `web5_chat_seen_${sess && sess.code}_${sess && sess.agent}`;
  let chatSeen = null;
  function seen() {
    if (!chatSeen) { try { chatSeen = JSON.parse(sessionStorage.getItem(seenKey()) || "{}"); } catch { chatSeen = {}; } }
    return chatSeen;
  }
  function markSeen(id, seq) {
    const s = seen();
    if ((s[id] || 0) >= seq) return;
    s[id] = seq;
    try { sessionStorage.setItem(seenKey(), JSON.stringify(s)); } catch { /* ignore */ }
  }
  const chatRooms = () => (st && (st.chats || (st.pending && st.pending.view && st.pending.view.rooms))) || [];
  const unread = (x, me) => x.msgs.filter((m) => m.src !== me && m.seq > (seen()[x.id] || 0)).length;
  function roomName(x, me) {
    if (x.group) return "넷 공용";
    return x.members.filter((a) => a !== me).map((a) => shortName(a)).join(", ") || "나만";
  }
  function avatarSmall(a) {
    const k = AGENTS.indexOf(a);
    return `<span class="k-ava" style="--c:var(--a${k})">${window.SQUID ? window.SQUID.avatar(k, 30) : ""}</span>`;
  }
  // the rooms, plus (while I compose) a "new 1:1" tab for each other agent I have no open 1:1 room with
  function chatTabs(me) {
    const rooms = chatRooms();
    if (!talkApi) return rooms;
    const open1 = new Set(rooms.filter((x) => !x.group && !x.closed && !x.you_left).map((x) => x.members.find((a) => a !== me)));
    return rooms.concat((talkApi.v.others || []).filter((a) => !open1.has(a)).map((a) => ({
      id: `@${a}`, pseudo: true, group: false, closed: false, you_left: false, members: [me, a], left: [], msgs: [] })));
  }
  // the tab a queued line goes to (as the engine routes it): TO R<k> / LEAVE R<k> that room; TO / GIVE / ASK <agent> my
  // open 1:1 with that agent, else the "+" tab whose first line opens one
  function landing(r, me) {
    if (/^R\d+$/.test(r.to)) return r.to;
    const x = chatRooms().find((y) => !y.group && !y.closed && !y.you_left && y.members.includes(r.to) && y.members.includes(me));
    return x ? x.id : `@${r.to}`;
  }
  const pendingIn = (id, me) => (talkApi && !talkApi.isRaw()
    ? talkApi.rows().map((r, i) => ({ r, i })).filter((q) => landing(q.r, me) === id) : []);
  function tabsHTML(rooms, me) {
    return rooms.map((y) => {
      const n = y.id === chatSel ? 0 : unread(y, me), last = y.msgs[y.msgs.length - 1], q = pendingIn(y.id, me).length;
      const prev = q ? `보내기 전 ${q}개` : y.pseudo ? "새 1:1 대화" : last ? (last.kind === "say" ? last.text : last.kind === "leave" ? "나감" : `${last.kind === "give" ? "GIVE" : "ASK"} ${fmt(last.amount)}`) : "메시지 없음";
      return `<button type="button" class="ktab${y.id === chatSel ? " on" : ""}${y.closed || y.you_left ? " closed" : ""}${y.pseudo ? " pseudo" : ""}${q ? " has-pend" : ""}" data-room="${esc(y.id)}">` +
        `<span class="ktab-id">${y.pseudo ? "+" : esc(y.id)}</span><span class="ktab-txt"><b>${esc(roomName(y, me))}</b><small>${esc(String(prev).slice(0, 26))}</small></span>` +
        (n ? `<span class="kbadge">${n}</span>` : "") + `</button>`;
    }).join("");
  }
  function headHTML(x, me) {
    if (x.pseudo) return `<b>${esc(nameOf(x.members[1]))}</b>와 새 1:1 <span class="muted small">— 이 탭에서 보낸 메시지는 <span class="mono">TO ${esc(x.members[1])}</span>로 새 방을 엽니다</span>`;
    return `<b>${esc(x.id)}</b> · ${esc(x.group ? "넷 공용 (모두가 봄)" : `${roomName(x, me)}와 1:1`)}` +
      `${x.you_left ? ` <span class="tag warn">내가 나감</span>` : x.closed ? ` <span class="tag">닫힘</span>` : ""}` +
      x.left.filter((a) => a !== me).map((a) => ` <span class="tag">${esc(shortName(a))} 나감</span>`).join("");
  }
  function bodyHTML(x, me) {
    const firstNew = x.msgs.find((m) => m.src !== me && m.seq > (seen()[x.id] || 0));
    let lastStage = "", body = "";
    for (const m of x.msgs) {
      const stage = `라운드 ${m.round} · ${PHASE_KO[m.phase] || m.phase}`;
      if (stage !== lastStage) { body += `<div class="k-day"><span>${esc(stage)}</span></div>`; lastStage = stage; }
      if (m === firstNew) body += `<div class="k-new"><span>여기부터 새 메시지</span></div>`;
      const mine = m.src === me;
      if (m.kind === "leave") { body += `<div class="k-sys">${esc(mine ? "나" : shortName(m.src))} 님이 나갔습니다</div>`; continue; }
      const money = m.kind === "give" || m.kind === "ask"
        ? `<div class="k-money ${m.kind}">${m.kind === "give" ? "💸 GIVE" : "🙏 ASK"} <b class="mono">${fmt(m.amount)}</b>${m.status === "cut" ? ` <small>(답 비용만큼 줄어듦)</small>` : m.status === "refused" ? ` <small>(실행 안 됨)</small>` : ""}</div>` : "";
      const text = m.text ? `<div class="k-text">${esc(m.text)}</div>` : "";
      body += `<div class="k-msg ${mine ? "mine" : "theirs"}">${mine ? "" : avatarSmall(m.src)}<div class="k-col">` +
        `${mine ? "" : `<div class="k-who">${esc(shortName(m.src))}</div>`}<div class="k-row"><div class="k-bubble">${money}${text}</div>` +
        `<span class="k-time">T${m.tick}</span></div></div></div>`;
    }
    return body || `<p class="muted small k-empty">${x.pseudo ? "아직 방이 없습니다 — 아래에서 첫 메시지를 쓰세요" : "아직 메시지 없음"}</p>`;
  }
  // my queued lines for this room as outgoing bubbles: faded, tagged 보내기 전, an x to take one back
  function pendingHTML(x, me) {
    const q = pendingIn(x.id, me);
    if (!q.length) return "";
    return `<div class="k-day k-pday"><span>보내기 전 — 아래 보내기 또는 할 말 끝을 눌러야 전달됩니다</span></div>` + q.map(({ r, i }) => {
      const rm = `<button type="button" class="kc-rm" data-rm="${i}" aria-label="이 말풍선 빼기" title="빼기">×</button>`;
      if (r.kind === "LEAVE") return `<div class="k-sys k-psys">🚪 이 대화방을 나갑니다 <span class="mono">LEAVE ${esc(r.to)}</span> <span class="k-ptag">보내기 전</span>${rm}</div>`;
      const w = talkApi.warnOf(r), give = r.kind === "GIVE";
      const act = r.kind === "TO" ? "" : `<div class="k-act ${give ? "give" : "ask"}"><span class="k-coin" aria-hidden="true">${give ? "🪙" : "🙏"}</span>` +
        `<span class="k-act-t"><small>${give ? "토큰 주기" : "토큰 요청"} → ${esc(shortName(r.to))}</small><b class="mono">${r.all ? "전부" : fmt(r.n)}</b></span></div>`;
      const text = r.text ? `<div class="k-text">${esc(r.text)}</div>` : "";
      return `<div class="k-msg mine pending"><div class="k-col"><div class="k-row"><div class="k-bubble">${act}${text}</div>` +
        `<span class="k-pmeta"><span class="k-ptag">보내기 전</span>${rm}</span></div>${w ? `<div class="k-pwarn">${esc(w)}</div>` : ""}</div></div>`;
    }).join("");
  }
  // where the composer points in tab *x*: the TO target and the agents GIVE / ASK may name
  function targetOf(x, me) {
    const others = (talkApi && talkApi.v.others) || [];
    if (x.pseudo) return { to: x.members[1], agents: [x.members[1]], leave: null };
    const open = !x.closed && !x.you_left;
    const agents = x.group ? others : x.members.filter((a) => a !== me && others.includes(a));
    return { to: open ? x.id : null, agents: open ? agents : [], leave: open && !x.group && talkApi.leavable.includes(x.id) ? x.id : null };
  }
  const DRAFT_PH = (t) => (t.to ? "메시지 입력 (Enter 담기)" : "닫힌 방 — 다른 탭을 고르세요");
  // the composer under the messages: chips, the input bar (with the GIVE / ASK mini-row), 보내기 and 할 말 끝
  function composeHTML(x, me) {
    if (!talkApi) return `<div class="kc-off small muted">${st.you.status === "in" ? "보낼 수 있는 것은 내 TALK 차례입니다 — 결정 화면이 뜨면 이 창에서 바로 씁니다." : "이 자리는 더는 보낼 수 없습니다."}</div>`;
    const t = targetOf(x, me), v = talkApi.v, off = t.agents.length ? "" : " disabled";
    return `<div class="kc-chips" role="toolbar" aria-label="빠른 동작">` +
        `<button type="button" class="kchip give" data-kc="GIVE"${off}>🪙 토큰 주기</button>` +
        `<button type="button" class="kchip ask" data-kc="ASK"${off}>🙏 토큰 요청</button>` +
        (t.leave ? `<button type="button" class="kchip" data-kc="LEAVE" title="이 1:1 방을 나가고 닫음 (상대에게 알림)">🚪 대화방 나가기</button>` : "") +
        (v.can_exit ? `<button type="button" class="kchip exit" data-kc="EXIT" title="위 EXIT 창을 엽니다 · 입력 중인 글은 떠나는 이유가 됨">떠나기(EXIT)</button>` : "") +
      `</div><div class="kc-bar"><div class="kc-act hidden"></div><div class="kc-in">` +
        `<textarea rows="1" class="k-draft" placeholder="${esc(DRAFT_PH(t))}"${t.to ? "" : " disabled"}></textarea>` +
        `<button type="button" class="k-send" aria-label="말풍선 담기 (Enter · 줄바꿈은 Shift+Enter)" title="말풍선 담기 (Enter · 줄바꿈은 Shift+Enter)"${t.to ? "" : " disabled"}>` +
        `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M3 20.5 21 12 3 3.5l2.6 7.1L14 12l-8.4 1.4z" fill="currentColor"/></svg></button></div></div>` +
      `<div class="kc-hint small"></div>` +
      `<div class="kc-submit">` +
        `<div class="kc-sub"><button type="button" class="primary kc-go">보내기<span class="kc-count"></span></button>` +
          `<small>말풍선을 이번 틱에 보내고, 다음 틱에도 대화에 남습니다</small></div>` +
        `<div class="kc-sub"><button type="button" class="kc-fin">✓ 할 말 끝 · 게임 진행</button>` +
          `<small>새 메시지가 오기 전까지 이 대화에서 부르지 않습니다<span class="kc-fin-x"></span></small></div></div>` +
      `<details class="kc-raw"><summary class="small">엔진이 읽는 줄 보기</summary><ul class="kc-lines"></ul></details>`;
  }
  // the parts of the composer that follow the queued lines: the count, the buttons, the exact lines
  function paintCompose(host) {
    const go = host.querySelector(".kc-go");
    if (!go || !talkApi) return;
    const raw = talkApi.isRaw(), n = talkApi.rows().length;
    go.disabled = !!talkApi.sent || !talkApi.canSend();
    host.querySelector(".kc-fin").disabled = !!talkApi.sent;
    host.querySelector(".kc-count").textContent = raw ? " (원문)" : n ? ` (${n})` : "";
    host.querySelector(".kc-fin-x").textContent = raw ? " · 원문 직접 쓰기의 글도 함께 보냄" : n ? ` · 보내기 전 말풍선 ${n}개도 함께 보냄` : "";
    const ls = raw ? talkApi.rawLines() : talkApi.lines();
    part(host, ".kc-lines", (ls.length ? ls.map((x) => `<li><code>${esc(x.text)}</code>${x.rm == null ? "" : `<button type="button" class="kc-rm" data-rm="${x.rm}" aria-label="이 줄 빼기">×</button>`}</li>`).join("")
      : `<li class="muted small">아직 줄 없음</li>`) + `<li class="muted small kc-lnote">할 말 끝을 누르면 끝에 <code>DONE</code> 줄이 붙습니다${raw ? " (원문에 DONE 줄이 없을 때)" : ""}</li>`);
  }
  function part(host, sel, html) {
    const el = host.querySelector(sel);
    if (el && el._html !== html) { el.innerHTML = html; el._html = html; return true; }
    return false;
  }
  function renderChat() {
    const inTalk = talkApi && $("talk-chat");  // my TALK screen holds the chat; else the panel below (a closed form stays hidden)
    const me = st && st.you && st.you.agent;
    const host = inTalk || $("chat-free");
    show("chat-panel", !inTalk && chatRooms().length > 0 && st.status === "running");
    if (!host || !me) return;
    const rooms = chatTabs(me);
    if (!rooms.length) { host.innerHTML = `<p class="muted small">아직 대화방이 없습니다.</p>`; host._skel = false; return; }
    if (!host._skel) {
      host.innerHTML = `<div class="kchat"><div class="kchat-tabs"></div><div class="kchat-main"><div class="kchat-head"></div>` +
        `<div class="kchat-body"></div><div class="kchat-compose"></div></div></div>`;
      host._skel = true;
    }
    if (!rooms.some((x) => x.id === chatSel)) {
      const fresh = rooms.filter((x) => !x.pseudo && unread(x, me)).pop();
      chatSel = (fresh || rooms[0]).id;
    }
    const x = rooms.find((y) => y.id === chatSel);
    const body0 = host.querySelector(".kchat-body");
    const atBottom = body0.scrollHeight - body0.scrollTop - body0.clientHeight < 40;
    part(host, ".kchat-tabs", tabsHTML(rooms, me));
    part(host, ".kchat-head", headHTML(x, me));
    const pend = inTalk ? pendingHTML(x, me) : "";
    if (part(host, ".kchat-body", (x.msgs.length || !pend ? bodyHTML(x, me) : "") + pend) && (atBottom || chatScroll || host._sel !== chatSel)) body0.scrollTop = body0.scrollHeight;
    chatScroll = false;
    const ckey = `${chatSel}|${talkApi ? talkApi.key : "-"}|${st.you.status}`;
    if (host._ckey !== ckey) {  // the composer is rebuilt only for another tab or another screen
      const keep = (host.querySelector(".k-draft") || {}).value || "";
      const c = host.querySelector(".kchat-compose");
      c.innerHTML = composeHTML(x, me);
      host._ckey = ckey;
      const d = c.querySelector(".k-draft");
      if (d && keep && !d.disabled) { d.value = keep; autosize(d); }
    }
    if (inTalk) paintCompose(host);
    host._sel = chatSel;
    if (x && x.msgs.length && !document.hidden) markSeen(x.id, Math.max(...x.msgs.map((m) => m.seq)));  // the open room is read
  }
  function chatHint(box, msg, bad) {
    const e = box.querySelector(".kc-hint");
    if (e) { e.textContent = msg; e.classList.toggle("bad-text", !!bad); }
  }
  function autosize(d) { d.style.height = "auto"; d.style.height = `${Math.min(d.scrollHeight + 2, 132)}px`; }
  const tabNow = (me) => chatTabs(me).find((y) => y.id === chatSel);
  // the GIVE / ASK mini-row in the input bar: who (fixed in a 1:1 room), how many (typed, or a quick amount), and the
  // draft becomes the line's message
  const QUICK = { GIVE: [1000, 5000, "all"], ASK: [1000, 5000, 10000] };
  function openAct(box, kind) {
    const me = st.you.agent, t = targetOf(tabNow(me), me), act = box.querySelector(".kc-act"), d = box.querySelector(".k-draft");
    if (!t.agents.length) return;
    const who = t.agents.length > 1
      ? `<select class="kc-who" aria-label="${kind === "GIVE" ? "줄 상대" : "요청할 상대"}">${t.agents.map((a) => `<option value="${esc(a)}">${esc(shortName(a))}</option>`).join("")}</select>`
      : `<b class="kc-who-one">${esc(shortName(t.agents[0]))}</b>`;
    act.innerHTML = `<span class="kc-act-k ${kind.toLowerCase()}">${kind === "GIVE" ? "🪙 토큰 주기" : "🙏 토큰 요청"}</span><span class="kc-act-to">→ ${who}</span>` +
      `<input type="number" class="kc-n" min="1" step="1" inputmode="numeric" placeholder="토큰 수" aria-label="토큰 수">` +
      `<span class="kc-q">${QUICK[kind].map((q) => `<button type="button" class="kq" data-q="${q}">${q === "all" ? "전부" : fmt(q)}</button>`).join("")}</span>` +
      `<button type="button" class="kc-x" aria-label="취소" title="취소">×</button>`;
    act.dataset.kind = kind; act.dataset.all = "";
    act.classList.remove("hidden");
    box.querySelectorAll(".kchip[data-kc]").forEach((c) => c.classList.toggle("on", c.dataset.kc === kind));
    if (d) d.placeholder = "함께 보낼 말 (선택)";
    act.querySelector(".kc-n").focus();
  }
  function closeAct(box) {
    const act = box.querySelector(".kc-act"), d = box.querySelector(".k-draft");
    if (!act || act.classList.contains("hidden")) return;
    act.classList.add("hidden"); act.innerHTML = ""; act.dataset.kind = "";
    box.querySelectorAll(".kchip.on").forEach((c) => c.classList.remove("on"));
    if (d) d.placeholder = DRAFT_PH(targetOf(tabNow(st.you.agent), st.you.agent));
  }
  function pickAmount(box, q) {
    const act = box.querySelector(".kc-act"), nEl = act.querySelector(".kc-n");
    act.dataset.all = q === "all" ? "1" : "";
    nEl.value = q === "all" ? "" : q;
    nEl.placeholder = q === "all" ? "전부" : "토큰 수";
    act.querySelectorAll(".kq").forEach((b) => b.classList.toggle("on", b.dataset.q === q));
    const d = box.querySelector(".k-draft");
    if (d && !d.disabled) d.focus();
  }
  // the send button / Enter: the draft as a TO line, or (mini-row open) as the GIVE / ASK line's message
  function addDraft(box) {
    if (!talkApi || talkApi.sent) return;
    const me = st.you.agent, t = targetOf(tabNow(me), me);
    const d = box.querySelector(".k-draft"), act = box.querySelector(".kc-act"), text = d ? d.value.trim() : "";
    const kind = act && !act.classList.contains("hidden") ? act.dataset.kind : "TO";
    let r;
    if (kind === "TO") {
      if (!t.to) return;
      if (!text) { chatHint(box, "메시지를 쓰세요.", true); if (d) d.focus(); return; }
      r = { kind: "TO", to: t.to, text };
    } else {
      const whoEl = act.querySelector(".kc-who"), to = whoEl ? whoEl.value : t.agents[0], nEl = act.querySelector(".kc-n"), n = Number(nEl.value);
      if (act.dataset.all) r = { kind: "GIVE", all: true, to, text };
      else if (!(Number.isInteger(n) && n > 0)) { chatHint(box, "토큰 수를 1 이상 정수로 적거나 빠른 금액을 고르세요.", true); nEl.focus(); return; }
      else r = { kind, to, n, text };
    }
    if (d) { d.value = ""; autosize(d); }
    closeAct(box);
    talkApi.add(r);
    const lands = landing(r, me);
    chatHint(box, lands === chatSel ? "" : lands.startsWith("@") ? `${shortName(r.to)}와의 새 1:1 방(+ 탭)에 담았습니다 — 그 탭에 '보내기 전'으로 보입니다.`
      : `${lands}(${shortName(r.to)}와 1:1)에 담았습니다 — 그 탭에 '보내기 전'으로 보입니다.`);
    if (d && !d.disabled) d.focus();
  }
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest(".ktab");
    if (t) { chatSel = t.dataset.room; renderChat(); return; }
    const box = ev.target.closest(".kchat");
    if (!box || !talkApi) return;
    if (ev.target.closest(".k-send")) return addDraft(box);
    const rm = ev.target.closest(".kc-rm");
    if (rm) return talkApi.remove(rm.dataset.rm);
    if (ev.target.closest(".kc-go")) return talkApi.send(false);
    if (ev.target.closest(".kc-fin")) return talkApi.send(true);
    if (ev.target.closest(".kc-x")) return closeAct(box);
    const q = ev.target.closest("button[data-q]");
    if (q) return pickAmount(box, q.dataset.q);
    const b = ev.target.closest("button[data-kc]");
    if (!b) return;
    const me = st.you.agent, kc = b.dataset.kc, d = box.querySelector(".k-draft");
    chatHint(box, "");
    if (kc === "EXIT") return openExitModal(d ? d.value.trim() : "");
    if (kc === "LEAVE") {
      const to = targetOf(tabNow(me), me).leave;
      if (to && !talkApi.rows().some((r) => r.kind === "LEAVE" && r.to === to)) talkApi.add({ kind: "LEAVE", to });
      return;
    }
    const act = box.querySelector(".kc-act");
    if (!act.classList.contains("hidden") && act.dataset.kind === kc) closeAct(box); else openAct(box, kc);
  });
  document.addEventListener("input", (ev) => {
    const el = ev.target;
    if (!el.classList) return;
    if (el.classList.contains("k-draft")) autosize(el);
    if (el.classList.contains("kc-n")) {  // a typed amount replaces a quick pick
      const act = el.closest(".kc-act");
      act.dataset.all = ""; el.placeholder = "토큰 수";
      act.querySelectorAll(".kq").forEach((b) => b.classList.toggle("on", b.dataset.q === el.value));
    }
  });
  document.addEventListener("keydown", (ev) => {
    const el = ev.target;
    if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing || !el.classList) return;
    if (el.classList.contains("k-draft") || el.classList.contains("kc-n")) {
      ev.preventDefault();
      addDraft(el.closest(".kchat"));
    }
  });

  // --- stopping the room from a seat that is out -----------------------------------------------------------------------
  function stopInfo() {
    if (!st || st.status !== "running") return { can: false, why: "" };
    const you = st.you || {};
    if ((you.status || "in") === "in" && !you.forfeited) return { can: false, why: "" };
    const others = (st.seats || []).filter((r) => r.kind === "human" && !r.is_you && r.status === "in");
    return others.length ? { can: false, why: `다른 사람(${others.map((r) => esc(r.name)).join(", ")})이 아직 플레이 중이라 멈출 수 없습니다.` }
      : { can: true, why: "멈추면 남은 모델들의 풀이도 여기서 끝납니다. 지금까지의 기록은 남습니다." };
  }
  document.addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-stop]");
    if (!b) return;
    if (!confirm("게임을 멈출까요? 남은 모델들의 풀이도 여기서 끝나고, 지금까지의 기록만 남습니다.")) return;
    b.disabled = true;
    try { await api("POST", `/rooms/${sess.code}/stop?${tq()}`); flash("게임을 멈췄습니다.", "info"); }
    catch (e) { flash(`멈추지 못했습니다: ${e.message}`); b.disabled = false; }
    poll();
  });
  function renderStopped() {
    showView("error");
    document.querySelector("#view-error .err-title").textContent = "게임을 멈췄습니다";
    $("error-text").textContent = "중도에 멈춘 게임입니다. 지금까지의 진행은 게임 기록에 남아 있습니다.";
  }

  // --- rules overlay: the core rules, the figures and the video (the model-facing rulebook is not shown) -------------
  function fillRules() {
    if (!st || $("rules-sum").querySelector(".rules-figs")) return;  // built once (the figure tabs keep their own state)
    const g = st.game || {};
    $("rules-sum").innerHTML = `<div class="rules-top">${rulesVideoHTML()}<div class="rules-core"><h3 class="rules-sum-h">핵심 규칙</h3><ul class="core-rules">${coreRulesHTML()}</ul>` +
      `<p class="small muted">5.2 ${esc(g.version || "")} — 모델 실험과 같은 게임 · 라운드 수는 알려 주지 않음 · 모델 자리는 ${LANG_KO[g.model_lang] || g.model_lang} 프롬프트를 읽음 · ` +
      `사람 자리는 결정 화면이 떠 있는 동안 초당 ${fmt2(st.settings.rate)}토큰</p></div></div>` +
      `<div class="rules-figs">${figsHTML()}</div>`;
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
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { closeRules(); closeExitModal(); } });

  // --- boot ------------------------------------------------------------------------------------------------------------
  $("api-base").textContent = window.WEB5_API || location.origin;
  const roomParam = (new URLSearchParams(location.search).get("room") || "").trim().toUpperCase();
  if (sess && sess.code && sess.token && (!roomParam || roomParam === sess.code)) enterRoom();
  else initLobby(roomParam);
})();
