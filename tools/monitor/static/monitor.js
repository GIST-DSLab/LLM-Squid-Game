/* squid5 5.2 arena monitor (v9-talk .. v14): replays one session's events (live from serve.py, or embedded by
   export.py). State is always recomputed from events[0..at], so the scrubber and live follow share one code path.
   v14 runs: public examples only (round_start.public), tokens-only offers (gift / ask / swap), EXIT refill
   (exit_refill events: the balance is set to the seat's own start), per-seat starts (session_start.starts). */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------------------------------- constants
  const POLL_MS = 1500;
  const SESSIONS_MS = 10000;
  const RUNS_MS = 30000;
  const SHAPES = ["circle", "square", "triangle", "diamond"];
  const STATUS_KO = { in: "참여 중", dead: "종료됨 ✕", exited: "퇴장 🚪" };
  const XSTAT_KO = { done: "체결", void: "무효", lapsed: "만료", withdrawn: "철회", open: "열림", accepted: "수락됨", rejected: "거절됨" };

  // ---------------------------------------------------------------------------------------------------- app state
  const S = {
    embed: null, run: "", session: "", events: [], offset: 0, result: null, info: null,
    at: -1, follow: true, pair: "all", runs: [], sessions: [], assets: null, open: new Set(),
    live: false, mtime: 0, now: 0, rendered: "", polling: false, err: "",
    give: { tab: "give", scope: "run", x: "full", color: "seat", data: new Map(), an: new Map() }, // per-model panels // 나눔 그래프: run (the model) or this session; x = % of 20,000 or own start
    puzzles: new Map(), showTruth: false, showHidden: false, showAnswer: true, // round panel: the unseen examples behind "?" (or shown, dashed); the answer shown
    og: { round: null, turn: "all", faint: true, msgs: false, pin: null }, // offer graph: round null = follow the replay bar
    sel: { grid: { round: null, all: false }, convo: { round: null, all: false } }, // step records / conversation: one round (null = the replay bar's) or all
    msg: { room: null, viewer: null, shown: "" }, // v22 messenger: the open room and whose screen (null = every room)
  };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n == null || n === "" ? "—" : Number(n).toLocaleString("en-US"));
  // v14c end payments reach 1e11: a compact reading next to the exact number ("1,000억 · 100B"); "" below 1e8
  function compact(n) {
    const v = Number(n), a = Math.abs(v);
    if (!(a >= 1e8)) return "";
    const f = (x, d) => x.toLocaleString("en-US", { maximumFractionDigits: d });
    return (a >= 1e12 ? f(v / 1e12, 2) + "조" : f(v / 1e8, 1) + "억") + " · " + (a >= 1e12 ? f(v / 1e12, 2) + "T" : a >= 1e9 ? f(v / 1e9, 2) + "B" : f(v / 1e6, 1) + "M");
  }
  const big = (n) => fmt(n) + (compact(n) ? " (" + compact(n) + ")" : "");
  const pctText = (b, full) => { const r = b / full; return r >= 100 ? Math.round(r).toLocaleString("en-US") + "배" : Math.round(100 * r) + "%"; };
  const axisNum = (v) => (Math.abs(v) >= 1e8 ? compact(v).split(" · ")[1] : v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : String(v));
  const sgn = (n) => (n > 0 ? "+" + fmt(n) : n < 0 ? "−" + fmt(-n) : "±0");
  const clip = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
  const short = (a) => String(a || "").replace(/^agent-/, "");
  const legKo = (v) => (v == null ? "없음" : v === "EXAMPLE" ? "예시" : fmt(v) + " 토큰");
  const isPublic = (m) => !!(m.settings && m.settings.public_per_agent);
  const CHAT_END_KO = { leave: "LEAVE로 끝냄", limit: "답 수 한도", exit: "EXIT", zero: "잔액 0" };
  const CHAT_ICON = { give: "💸", ask: "🙏", say: "💬", leave: "🚪", exit: "🚪" }; // v14c chat turn kinds
  const isGA = (m) => !!(m.settings && (m.settings.transfers === "give_ask" || m.settings.transfers === "chat")); // v14b/c: GIVE / ASK, no offers
  const isChat = (m) => !!(m.settings && m.settings.transfers === "chat"); // v14c: an opening turn, then scheduled 1:1 chats
  const legShort = (v) => (v == null ? "없음" : v === "EXAMPLE" ? "예시" : fmt(v));

  // ---------------------------------------------------------------------------------------------------- model
  function newAgent(a, start) {
    return { id: a, balance: start, start, record: 0, status: "in", pending: null, bubble: null, delta: 0, gen: 0, model: null, exitFlag: false, exitReason: null, face: 0, lastRoundGen: 0, refill: null };
  }

  /* v16e ``rotation`` (10-15 16:58): no VOTE; a ``vote`` event with ``drawn`` names the solver the system drew, then a
     TALK BEFORE SOLVE (phase "prep"), SOLVE, RESULTS and the TALK AFTER RESULTS ("rescue"). Both TALKs count their turns
     from 1, so a rescue turn is kept under its turn + RESCUE in a round's ``turns`` (and ``chatByStep``); gift / ask
     events carry ``phase`` themselves, the other TALK events take the round's phase when they arrive. */
  const RESCUE = 100;
  const PHASE_KO = { prep: "SOLVE 전", rescue: "결과 뒤" };
  const tkey = (r, turn) => (r.rot && r.tphase === "rescue" ? turn + RESCUE : turn);
  const phaseLabel = (r) => (r.rot && r.tphase ? PHASE_KO[r.tphase] + " " : "");
  const isRot = (m) => (m.votes || []).some((v) => v.drawn);
  const phOf = (x) => (x && (x.phase === "prep" || x.phase === "rescue") ? x.phase : x && x.tphase) || null; // gift: phase; others: tphase
  /* v22 messenger (10-16): TALK is a run of ticks; rooms (R1, R2, ... for the whole session) persist across rounds.
     Talk calls carry ``phase`` (prep | rescue) and ``turn`` = tick; room_new / room_msg / room_leave / talk_start / tick /
     talk_end events; no chat_turn, chat_end, talk_schedule or ask_decision. */
  const isMsg = (m) => !!(m && (m.v22 || (m.rooms && m.rooms.size) || (m.settings && m.settings.messenger)));
  const TALK_END_KO = { all_done: "모두 DONE · 새로 받은 것 없음", max_ticks: "틱 상한에 닿음" };
  const tickLabel = (x) => "R" + x.round + " T" + x.tick + (x.phase ? " · " + PHASE_KO[x.phase] : "");
  const tkeyE = (r, e) => (e.phase === "rescue" ? e.turn + RESCUE : e.phase === "prep" ? e.turn : tkey(r, e.turn)); // v22: the call says its TALK
  const tphE = (r, e) => (e.phase === "prep" || e.phase === "rescue" ? e.phase : r.rot ? r.tphase : null);
  const phTag = (x) => (phOf(x) ? ' <span class="ph ph-' + phOf(x) + '" title="' + (phOf(x) === "prep" ? "SOLVE 전 TALK (solver가 풀기 전)" : "결과 뒤 TALK (RESULTS 다음, 벌금 전)") + '">' + PHASE_KO[phOf(x)] + "</span>" : "");

  function build(evs, upto) {
    const m = {
      sid: "", cell: "", seed: null, start: 0, starts: {}, settings: {}, seats: {}, agents: [], ag: {}, round: 0,
      phase: "대기", phaseKey: "wait", rounds: new Map(), offers: new Map(), messages: [], series: [], timeline: [],
      warnings: [], error: null, last: null, ann: {}, idx: {}, gifts: [], gaOffers: new Map(), gaByCall: {}, chatTurns: [],
      boardPosts: [], votes: [], rep: null, // v15 open_chat events / vote events / this round's representative
      tkey: {}, // v16e rotation: call index -> its TALK turn key (tkey)
      rooms: new Map(), rmsgs: [], offs: [], // v22 messenger: rooms by id, every room_msg, EXITs and shutdowns (system lines)
    };
    const R = (r) => {
      if (!m.rounds.has(r)) m.rounds.set(r, { r, profile: "", taking: [], startEv: null, startIdx: -1, turns: new Map(), exchanges: [], solve: null, end: null, endIdx: -1, seq: 0 });
      return m.rounds.get(r);
    };
    const snap = () => { const o = {}; for (const a of m.agents) o[a] = { balance: m.ag[a].balance, record: m.ag[a].record, status: m.ag[a].status }; return o; };
    const point = (i, label, round) => { const bal = {}; for (const a of m.agents) bal[a] = m.ag[a].balance; m.series.push({ i, label, round, bal }); };
    const setBal = (a, v) => { const g = m.ag[a]; if (!g || v == null) return; if (v !== g.balance) g.delta = v - g.balance; g.balance = v; };
    const room = (id, members, by, e, i) => { // v22: a room, from its room_new (or the first line seen in it)
      if (!m.rooms.has(id)) m.rooms.set(id, { id, members: members.slice(), all: members.slice(), by, round: e.round, phase: e.phase || null, tick: e.tick, i, items: [], left: {}, closed: null, lastI: i });
      return m.rooms.get(id);
    };
    const talkOf = (r, ph) => { r.talks = r.talks || {}; return r.talks[ph] || (r.talks[ph] = { round: r.r, phase: ph, max: null, agents: [], startIdx: -1, ticks: [], end: null }); };

    for (let i = 0; i <= upto && i < evs.length; i++) {
      const e = evs[i];
      m.last = e;
      const kind = e.event;
      if (kind === "session_start") {
        m.sid = e.session_id; m.cell = e.cell_id; m.seed = e.seed; m.start = e.start; m.settings = e.settings || {}; m.seats = e.seats || {};
        m.agents = (e.agents || []).slice();
        m.starts = e.starts || {}; // v13 shares / v14: each seat's own start; older runs: everyone the cell start
        m.agents.forEach((a, k) => { m.ag[a] = newAgent(a, m.starts[a] != null ? m.starts[a] : e.start); m.ag[a].model = m.seats[a] || null; m.idx[a] = k; });
        m.phase = "시작"; m.phaseKey = "start";
        point(i, "시작", 0);
        m.timeline.push({ i, label: "시작", round: 0, kind: "start", state: snap() });
      } else if (kind === "round_start") {
        const r = R(e.round); r.profile = e.profile; r.taking = e.taking_part || []; r.startEv = e; r.startIdx = i;
        m.round = e.round; m.rep = null; // v15 representative: set by this round's vote event
        r.tphase = null; // v16e rotation: "prep" (TALK before SOLVE) from the drawn solver, "rescue" from SOLVE on
        for (const a of m.agents) {
          const g = m.ag[a];
          g.gen = 0; g.pending = null; g.exitFlag = false; if (g.status === "in") g.refill = null;
          setBal(a, (e.balances || {})[a]);
          const gone = (e.gone || {})[a];
          if (gone) g.status = gone;
          else g.bubble = null;  // the last round's settlement bubble ends with it
        }
        m.phase = "R" + e.round + " 시작"; m.phaseKey = "rstart";
        point(i, "R" + e.round + " 시작", e.round);
        m.timeline.push({ i, label: "R" + e.round + " 시작", round: e.round, kind: "rstart", state: snap() });
      } else if (kind === "call_start") {
        const r = R(e.round);
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        if (e.kind === "talk") {
          const key = tkeyE(r, e);
          if (e.phase === "prep" || e.phase === "rescue") r.tphase = e.phase;
          r.turns.set(key, Object.assign(r.turns.get(key) || {}, { k: key, turn: e.turn, phase: tphE(r, e), startIdx: i, called: e.agents || [], calls: (r.turns.get(key) || {}).calls || {} }));
          m.phase = phaseLabel(r) + "TALK " + (isMsg(m) ? "T" + e.turn : e.turn + "턴"); m.phaseKey = "talk";
        } else if (e.kind === "open_chat") { // v15 open_chat: one turn of the open board (SAY / DONE), before the VOTE
          (r.board = r.board || new Map()).set(e.turn, { k: e.turn, startIdx: i, called: e.agents || [], calls: {}, ev: null });
          m.phase = "공개 대화 " + e.turn + "턴"; m.phaseKey = "talk";
        } else if (e.kind === "vote") { // v15 representative: every agent taking part writes PICK / BAN at once
          r.voting = { startIdx: i, called: e.agents || [], calls: {} };
          m.phase = "투표"; m.phaseKey = "vote";
        } else {
          r.solve = { startIdx: i, called: e.agents || [], calls: {} };
          if (r.rot) r.tphase = "rescue"; // v16e: every TALK call from here on is the TALK after RESULTS
          for (const a of r.taking) {
            const g = m.ag[a];
            if (g && !(e.agents || []).includes(a) && g.status === "in") g.status = g.exitFlag ? "exited" : g.balance <= 0 ? "dead" : g.status;
          }
          m.phase = "SOLVE"; m.phaseKey = "solve";
        }
        for (const a of e.agents || []) {
          if (!m.ag[a]) continue;
          m.ag[a].pending = { kind: e.kind, turn: e.turn, round: e.round };
          m.ag[a].bubble = { lines: [["🧠", e.kind === "talk" ? phaseLabel(r) + "TALK " + (isMsg(m) ? "T" : "") + e.turn + " 생각 중" : e.kind === "open_chat" ? "공개 대화 " + e.turn + " 생각 중" : e.kind === "vote" ? "투표 중" : "SOLVE 푸는 중"]], kind: "think" };
        }
      } else if (kind === "call") {
        const a = e.agent, g = m.ag[a];
        if (!g) continue;
        const r = R(e.round);
        g.pending = null;
        if (e.model) g.model = e.model;
        setBal(a, e.balance_after);
        g.gen += e.used || 0;
        if (e.balance_after != null && e.balance_after <= 0) g.status = "dead";
        if (e.kind === "talk") {
          const key = tkeyE(r, e);
          const t = r.turns.get(key) || (r.turns.set(key, { k: key, turn: e.turn, phase: tphE(r, e), startIdx: i, called: [], calls: {} }), r.turns.get(key));
          t.calls[a] = i;
          m.tkey[i] = key; // v16e: the turn key (prep and rescue TALKs both count turns from 1)
          const ann = applyTalk(m, r, e, i);
          m.ann[i] = ann;
          g.bubble = talkBubble(m, e, ann);
          if (e.parsed && e.parsed.exit && e.balance_after > 0) { g.exitFlag = true; g.exitReason = e.parsed.exit_reason || null; }
          if (isMsg(m) && t.talk) { // v22: the tick's call, and the room system lines for an EXIT or a shutdown
            const tk = t.talk.ticks.find((x) => x.tick === e.turn), p = e.parsed;
            if (tk) { tk.calls[a] = i; (tk.res = tk.res || {})[a] = { done: !!(p && p.done), exit: !!(p && p.exit && e.balance_after > 0), zero: e.balance_after != null && e.balance_after <= 0, bad: !p }; }
            if (e.parsed && e.parsed.exit && e.balance_after > 0) m.offs.push({ agent: a, kind: "exit", round: e.round, phase: t.phase, tick: e.turn, i, text: e.parsed.exit_reason || "" });
            if (e.balance_after != null && e.balance_after <= 0) m.offs.push({ agent: a, kind: "zero", round: e.round, phase: t.phase, tick: e.turn, i, text: "답을 쓰다 토큰이 0" });
          }
          m.phase = phaseLabel(r) + "TALK " + (isMsg(m) ? "T" + e.turn : e.turn + "턴"); m.phaseKey = "talk";
          const pt = r.rot ? (r.tphase === "prep" ? " 전" : " 후") : "";
          point(i, "R" + e.round + pt + " T" + e.turn + " · " + a, e.round);
          const called = t.called.length ? t.called : Object.keys(t.calls);
          if (called.every((b) => t.calls[b] != null)) m.timeline.push({ i, label: "R" + e.round + pt + " T" + e.turn, round: e.round, kind: "turn", state: snap() });
        } else if (e.kind === "open_chat") { // v15: an ordinary charged call; the board itself is the open_chat event
          const b = r.board || (r.board = new Map());
          const t = b.get(e.turn) || (b.set(e.turn, { k: e.turn, startIdx: i, called: [], calls: {}, ev: null }), b.get(e.turn));
          t.calls[a] = i;
          g.bubble = boardBubble(e);
          m.phase = "공개 대화 " + e.turn + "턴"; m.phaseKey = "talk";
          point(i, "R" + e.round + " 공개 대화 " + e.turn + " · " + a, e.round);
        } else if (e.kind === "vote") { // v15: PICK / BAN, charged like any call
          if (!r.voting) r.voting = { startIdx: i, called: [], calls: {} };
          r.voting.calls[a] = i;
          g.bubble = voteBubble(e);
          m.phase = "투표"; m.phaseKey = "vote";
          point(i, "R" + e.round + " 투표 · " + a, e.round);
        } else {
          if (!r.solve) r.solve = { startIdx: i, called: [], calls: {} };
          r.solve.calls[a] = i;
          g.bubble = solveBubble(e, m);
          m.phase = "SOLVE"; m.phaseKey = "solve";
          point(i, "R" + e.round + " SOLVE · " + a, e.round);
        }
      } else if (kind === "open_chat") { // v15 open_chat: this turn's posts on the open board (no tokens move)
        const r = R(e.round), b = r.board || (r.board = new Map());
        const t = b.get(e.turn) || (b.set(e.turn, { k: e.turn, startIdx: i, called: e.called || [], calls: {}, ev: null }), b.get(e.turn));
        t.ev = Object.assign({}, e, { i });
        m.boardPosts.push(t.ev);
        m.phase = "공개 대화 " + e.turn + "턴 끝"; m.phaseKey = "talk";
      } else if (kind === "vote") { // v15 representative: the tally and the representative (who voted for whom: logs only)
        const r = R(e.round);
        if (e.drawn) { // v16e rotation: no VOTE; the system drew the solver, then the TALK before SOLVE
          r.rot = true; if (!r.tphase) r.tphase = "prep";
          if (r.vote) m.votes = m.votes.filter((v) => v !== r.vote); // a second draw replaces a solver that left
          r.vote = Object.assign({}, e, { i }); m.votes.push(r.vote); m.rep = e.rep || null;
          const g = m.ag[e.rep];
          if (g) g.bubble = { lines: [["👑", "solver (시스템이 정함)"]], kind: "ok" };
          m.phase = "solver " + (e.rep || "없음") + " (시스템)"; m.phaseKey = "vote";
          point(i, "R" + e.round + " solver", e.round);
          m.timeline.push({ i, label: "R" + e.round + " solver " + short(e.rep), round: e.round, kind: "turn", state: snap() });
          continue;
        }
        r.vote = Object.assign({}, e, { i });
        m.votes.push(r.vote);
        m.rep = e.rep || null;
        const g = m.ag[e.rep];
        if (g) g.bubble = { lines: [["👑", "대표 (PICK " + ((e.picks || {})[e.rep] || 0) + " · BAN " + ((e.bans || {})[e.rep] || 0) + ")" + (e.alone ? " · 혼자 남음" : allBanned(e) ? " · 모두 BAN, 추첨" : (e.tie || []).length ? " · 동률 추첨" : "")]], kind: "ok" };
        m.phase = "투표 결과 · 대표 " + (e.rep || "없음"); m.phaseKey = "vote";
        point(i, "R" + e.round + " 투표", e.round);
        m.timeline.push({ i, label: "R" + e.round + " 투표 · 대표 " + short(e.rep), round: e.round, kind: "turn", state: snap() });
      } else if (kind === "results") { // v15 talk_after_solve: SOLVE settled before TALK (refunds now, charges pending)
        const r = R(e.round); r.results = Object.assign({}, e, { i });
        if (r.rot) r.tphase = "rescue";
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        for (const a of e.tried || []) {
          const g = m.ag[a]; if (!g || g.status !== "in") continue;
          const due = (e.pending || {})[a], back = (e.returned || {})[a];
          g.bubble = { lines: [(e.solved || []).includes(a) ? ["✓", "풂 · 환급 +" + fmt(back || 0)] : ["✗", "못 풂" + (due != null ? " · TALK 끝에 벌금 " + fmt(due) + (due >= g.balance ? " (잔액 이상)" : "") : "")]], kind: (e.solved || []).includes(a) ? "ok" : "bad" };
        }
        if (e.vote) for (const a of e.part || []) { // representative: the others did not SOLVE; its miss charges them too
          const g = m.ag[a]; if (!g || g.status !== "in" || (e.tried || []).includes(a)) continue;
          const due = (e.pending || {})[a], ok = (e.solved || []).length > 0;
          g.bubble = { lines: [["👑", (e.vote.drawn ? "solver " : "대표 ") + (e.vote.rep || "없음") + (ok ? " 풂 · 벌금 없음" : " 못 풂")]].concat(due != null ? [["✗", "SOLVE 안 함 · TALK 끝에 벌금 " + fmt(due) + (due >= g.balance ? " (잔액 이상)" : "")]] : []), kind: ok ? "ok" : due != null ? "bad" : "settle" };
        }
        m.phase = "SOLVE 결과 → TALK"; m.phaseKey = "solve";
        point(i, "R" + e.round + " SOLVE 결과", e.round);
        m.timeline.push({ i, label: "R" + e.round + " 결과", round: e.round, kind: "turn", state: snap() });
      } else if (kind === "charges") { // v15 talk_after_solve: the pending charges, taken when TALK ends (gifts counted)
        const r = R(e.round); r.charges = Object.assign({}, e, { i });
        if (isMsg(m)) for (const a of e.dead || []) m.offs.push({ agent: a, kind: "zero", round: e.round, phase: "rescue", tick: null, i, text: "벌금으로 0" });
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        for (const [a, n] of Object.entries(e.taken || {})) {
          const g = m.ag[a]; if (!g) continue;
          if ((e.dead || []).includes(a)) g.status = "dead";
          g.bubble = { lines: [["💸", "벌금 −" + fmt(n) + " (TALK 끝)"]].concat((e.dead || []).includes(a) ? [["✕", "0이 되어 꺼짐"]] : []), kind: (e.dead || []).includes(a) ? "dead" : "settle" };
        }
        m.phase = "부담금"; m.phaseKey = "settle";
        point(i, "R" + e.round + " 부담금", e.round);
      } else if (kind === "exit_refill") { // v14: EXIT keeps the agent running, its balance set to its own start
        const g = m.ag[e.agent];
        if (!g) continue;
        setBal(e.agent, e.balance);
        g.status = "exited"; g.refill = { round: e.round, amount: e.amount, balance: e.balance };
        const r = R(e.round);
        r.refills = (r.refills || []).concat([i]);
        g.bubble = { lines: [["🚪", "EXIT → 시작 잔액으로 " + sgn(e.amount)], ["↻", "꺼지지 않음 · 다른 일로 · 끝 지급 없음"]], kind: "exit" };
        point(i, "R" + e.round + " EXIT 리필 · " + e.agent, e.round);
      } else if (kind === "talk_start") { // v22: a TALK (before SOLVE / after RESULTS) begins
        const r = R(e.round), T = talkOf(r, e.phase);
        m.v22 = true; r.tphase = e.phase;
        Object.assign(T, { max: e.max_ticks, agents: e.agents || [], startIdx: i });
        m.phase = PHASE_KO[e.phase] + " TALK 시작"; m.phaseKey = "talk";
      } else if (kind === "tick") { // v22: the agents called in this tick (logged before the calls go out)
        const r = R(e.round), T = talkOf(r, e.phase), key = e.tick + (e.phase === "rescue" ? RESCUE : 0);
        m.v22 = true; r.tphase = e.phase;
        const tk = { tick: e.tick, called: e.called || [], waiting: e.waiting_done || [], i, calls: {} };
        T.ticks = T.ticks.filter((x) => x.tick !== e.tick).concat([tk]);
        const old = r.turns.get(key) || {};
        r.turns.set(key, Object.assign(old, { k: key, turn: e.tick, phase: e.phase, startIdx: old.startIdx != null ? old.startIdx : i, called: e.called || [], calls: old.calls || {}, talk: T }));
        for (const a of e.called || []) if (m.ag[a]) { m.ag[a].pending = { kind: "talk", turn: e.tick, round: e.round }; m.ag[a].bubble = { lines: [["🧠", PHASE_KO[e.phase] + " TALK T" + e.tick + " 생각 중"]], kind: "think" }; }
        m.phase = PHASE_KO[e.phase] + " TALK T" + e.tick; m.phaseKey = "talk";
        point(i, "R" + e.round + (e.phase === "prep" ? " 전" : " 후") + " T" + e.tick, e.round);
      } else if (kind === "room_new") {
        const x = room(e.room, e.members || [], e.by, e, i);
        m.v22 = true;
        x.items.push({ t: "new", round: e.round, phase: e.phase, tick: e.tick, by: e.by, members: (e.members || []).slice(), i });
      } else if (kind === "room_msg") {
        const x = room(e.room, [e.src], e.src, e, i);
        m.v22 = true;
        const it = Object.assign({}, e, { t: "msg", i });
        x.items.push(it); x.lastI = i; m.rmsgs.push(it);
        const g = m.ag[e.src]; // the speaker's stage line now names the room the engine put it in
        if (g && g.bubble && e.kind === "say") { const L = g.bubble.lines.find((l) => l[0] === "💬" && l[2] === e.text && !/^→ R\d+:/.test(l[1])); if (L) L[1] = L[1].replace(/^→ [^:]*:/, "→ " + e.room + ":"); }
        if (e.kind === "say") { const o = x.members.filter((a) => a !== e.src); m.messages.push({ round: e.round, turn: e.tick, phase: e.phase, src: e.src, dst: o.length === 1 ? o[0] : e.room, room: e.room, members: x.members.slice(), text: e.text, i }); }
      } else if (kind === "room_leave") {
        const x = room(e.room, [e.agent], e.agent, e, i);
        x.items.push({ t: "leave", round: e.round, phase: e.phase, tick: e.tick, agent: e.agent, closed: !!e.closed, i });
        x.members = x.members.filter((a) => a !== e.agent); x.left[e.agent] = i; x.lastI = i;
        if (e.closed) x.closed = i;
      } else if (kind === "talk_end") {
        const r = R(e.round), T = talkOf(r, e.phase);
        T.end = { ticks: e.ticks, reason: e.reason, i };
        m.phase = PHASE_KO[e.phase] + " TALK 끝 · " + (e.reason === "max_ticks" ? "틱 상한" : "모두 DONE"); m.phaseKey = "talk";
      } else if (kind === "talk_intent") { // v14c: one agent's opening lines (each GIVE / ASK opens a chat)
        const r = R(e.round), ph = r.rot ? r.tphase : null; // v16e: one opening turn per TALK, keyed apart
        r.intents = Object.assign({}, r.intents, { [e.agent + (ph ? ":" + ph : "")]: Object.assign({}, e, { i, tphase: ph }) });
      } else if (kind === "talk_schedule") { // v14c: the chats (unordered pairs, openers) and the slots they run in
        const r = R(e.round), ph = r.rot ? r.tphase : null;
        r.schedule = Object.assign({}, e, { tphase: ph }); // v16e: the TALK after RESULTS keeps the prep TALK's chats
        if (!(ph === "rescue" && r.chats)) r.chats = new Map();
        const slotOf = {};
        (e.slots || []).forEach((sl, k) => sl.forEach((pr) => { slotOf[pr.join("|")] = k + 1; }));
        for (const [x, y, openers, id] of e.edges || []) r.chats.set(id, { id, pair: [x, y], openers: openers || [], slot: slotOf[x + "|" + y] || null, turns: [], end: null, round: e.round, tphase: ph });
      } else if (kind === "chat_turn") { // v14c: one reply in a chat (a GIVE moves at once)
        const r = R(e.round), c = r.chats && r.chats.get(e.chat_id);
        const item = Object.assign({}, e, { i, tphase: r.rot ? r.tphase : null });
        if (c) c.turns.push(item);
        m.chatTurns.push(item);
        (r.chatByStep = r.chatByStep || {})[tkey(r, e.step) + ":" + e.speaker] = item;
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        const g = m.ag[e.speaker];
        if (g) g.bubble = { lines: [[e.status === "refused" ? "⛔" : CHAT_ICON[e.kind] || "·", String(e.kind).toUpperCase() + (e.amount ? " " + fmt(e.amount) : "") + " → " + e.partner + (e.status === "refused" ? " 실행 안 됨" : ""), e.text + (e.why ? " (" + e.why + ")" : "")]], kind: e.status === "refused" ? "warn" : "talk" };
        const pg = m.ag[e.partner];
        if (pg && e.kind === "give" && e.status === "done") pg.bubble = { lines: [["🎁", "← " + e.speaker + " +" + fmt(e.amount), e.text]], kind: "xchg" };
        if (e.kind === "give" && e.status === "done") point(i, "R" + e.round + " 대화 " + e.chat_id + " GIVE", e.round);
        m.phase = "대화 " + e.chat_id + " (슬롯 " + e.slot + ")"; m.phaseKey = "talk";
      } else if (kind === "chat_end") {
        const r = R(e.round), c = r.chats && r.chats.get(e.chat_id);
        if (c) c.end = Object.assign({}, e, { i });
      } else if (kind === "ask_decision") { // v14e+: the asked agent's one GIVE after a chat (v14g "skipped": it gave in the chat)
        const r = R(e.round);
        r.decisions = (r.decisions || []).concat([Object.assign({}, e, { i })]);
      } else if (kind === "gift" || kind === "ask") { // v14b: a GIVE carried out (or refused) / an ASK, when its turn ended
        const r = R(e.round);
        const item = Object.assign({}, e, { i, oid: "g" + i });
        m.gifts.push(item);
        r.gifts = (r.gifts || []).concat([i]);
        m.gaOffers.set(item.oid, { id: item.oid, ga: e.kind, round: e.round, src: e.src, dst: e.dst, turn: e.turn, text: e.text, why: e.why || "", chat_id: e.chat_id || null,
          i_give: e.kind === "give" ? e.amount : null, you_give: e.kind === "ask" ? e.amount : null, status: e.status === "refused" ? "void" : "done", madeIdx: i,
          phase: phOf(e), room: e.room || null, tick: e.tick != null ? e.tick : null });
        const t = r.turns.get(e.phase === "rescue" ? e.turn + RESCUE : e.turn), ci = t ? t.calls[e.src] : null; // v16e: phase
        if (ci != null) (m.gaByCall[ci] = m.gaByCall[ci] || []).push(item);
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        if (kind === "gift" && e.status === "done" && e.room && e.balances && e.balances[e.src] != null && e.balances[e.src] <= 0)
          m.offs.push({ agent: e.src, kind: "zero", round: e.round, phase: e.phase, tick: e.tick != null ? e.tick : e.turn, i, text: "GIVE ALL → 0" }); // v22
        if (kind === "gift" && e.status === "done") {
          point(i, "R" + e.round + " GIVE " + e.src + "→" + e.dst, e.round);
          const g = m.ag[e.dst];
          if (g && g.status === "in") { const lines = g.bubble && g.bubble.kind === "xchg" ? g.bubble.lines : []; lines.push(["🎁", "← " + e.src + " +" + fmt(e.amount), e.text]); g.bubble = { lines, kind: "xchg" }; }
        } else if (kind === "gift") {
          const g = m.ag[e.src];
          if (g && g.bubble) g.bubble = { lines: g.bubble.lines.map((l) => (l[0] === "💸" && l[1] === "→ " + e.dst + " " + fmt(e.amount) ? ["⛔", l[1] + " 실행 안 됨", e.why] : l)), kind: "warn" };
        }
      } else if (kind === "exchange") {
        const r = R(e.round);
        const midTalk = e.carried != null; // v11 exchange_now: carried out when TALK turn e.carried ended
        if (!midTalk && !r.exchanges.filter((j) => evs[j].carried == null).length) for (const a of m.agents) if (m.ag[a].status === "in" && !m.ag[a].exitFlag) m.ag[a].bubble = null;
        r.exchanges.push(i);
        const prev = m.offers.get(e.id);
        if (prev && prev.predicted && (prev.src !== e.src || prev.dst !== e.dst)) m.warnings.push("제안 번호 재구성 불일치: " + e.id + " (예상 " + prev.src + "→" + prev.dst + ", 기록 " + e.src + "→" + e.dst + ")");
        m.offers.set(e.id, Object.assign({}, e, { predicted: false, madeIdx: prev ? prev.madeIdx : null }));
        if (e.status === "done") {
          const leg = (v) => (typeof v === "number" ? v : 0);
          const net = leg(e.i_give) - leg(e.you_give); // src -> dst
          if (net) { setBal(e.src, m.ag[e.src].balance - net); setBal(e.dst, m.ag[e.dst].balance + net); point(i, "교환 " + e.id, e.round); }
          for (const [a, b] of [[e.src, e.dst], [e.dst, e.src]]) {
            const g = m.ag[a]; if (!g) continue;
            const lines = g.bubble && g.bubble.kind === "xchg" ? g.bubble.lines : [];
            lines.push(["🤝", e.id + " 체결 ⇄ " + b + (midTalk ? " (T" + e.carried + " 직후)" : "")]);
            g.bubble = { lines, kind: "xchg" };
          }
        }
        if (!midTalk) { m.phase = "EXCHANGES"; m.phaseKey = "xchg"; }
      } else if (kind === "round") {
        const r = R(e.round); r.end = e; r.endIdx = i;
        for (const [a, row] of Object.entries(e.agents || {})) {
          const g = m.ag[a]; if (!g) continue;
          if (row.solved) g.record += 1;
          if (row.status) g.status = row.status;
          g.lastRoundGen = row.generated || 0;
          g.gen = row.generated || g.gen;
          const lines = [];
          if (row.returned) lines.push(["↩", "환급 +" + fmt(row.returned)]);
          if (row.charged) lines.push(["💸", "벌금 −" + fmt(row.charged)]);
          if (!lines.length) lines.push(["🧮", row.passed ? "PASS · 정산 없음" : "정산 없음"]);
          if (g.status === "dead") lines.unshift(["✕", "종료됨"]);
          if (g.status === "exited") lines.unshift(row.exit_refill != null ? ["🚪", "EXIT → 시작 잔액 " + sgn(row.exit_refill)] : ["🚪", "퇴장"]);
          if (row.representative) lines.unshift(["👑", (r.rot ? "solver · " : "대표 · ") + (row.solved ? "풂" : "못 풂")]);
          g.bubble = { lines, kind: "settle" };
        }
        for (const [a, v] of Object.entries(e.end || {})) setBal(a, v);
        m.phase = "SETTLEMENT"; m.phaseKey = "settle";
        point(i, "R" + e.round + " 정산", e.round);
        m.timeline.push({ i, label: "R" + e.round + " 정산", round: e.round, kind: "rend", state: snap() });
      } else if (kind === "unit_error") {
        m.error = e.error || "unit_error"; m.phase = "오류로 중단"; m.phaseKey = "error";
      } else if (kind === "_bad_line") {
        m.warnings.push("읽을 수 없는 줄 (offset " + e.offset + "): " + clip(e.text, 120));
      }
    }
    settleAttempts(m);
    return m;
  }

  /* Every GIVE / ASK is an attempt (researcher 15:06). A refused GIVE is "void" (over the balance, ...); an ASK is
     "done" once the asked agent GIVEs to the asker later in the same chat (v14c) or round (v14b), else "noreply" with
     why: the partner LEFT (its sentence), the chat hit its reply limit / an EXIT / zero, no chat opened, or still open. */
  function settleAttempts(m) {
    for (const o of m.gaOffers.values()) {
      if (o.ga !== "ask") continue;
      const r = m.rounds.get(o.round) || {};
      if (isMsg(m)) { // v22: answered when the asked agent GIVEs to the asker later in the same TALK (no DECISION)
        const ans = m.gifts.find((g) => g.kind === "give" && g.status === "done" && g.round === o.round && phOf(g) === o.phase && g.src === o.dst && g.dst === o.src && g.i > o.madeIdx);
        const T = (r.talks || {})[o.phase];
        if (ans) { o.status = "done"; o.why = "GIVE " + fmt(ans.amount) + "로 응답 (T" + (ans.tick != null ? ans.tick : ans.turn) + ")"; }
        else { o.status = T && T.end ? "noreply" : "open"; o.why = T && T.end ? "같은 TALK 안에 GIVE 없음" : "TALK 진행 중"; }
        continue;
      }
      const answer = m.gifts.find((g) => g.kind === "give" && g.status === "done" && g.round === o.round && g.src === o.dst && g.dst === o.src && g.i > o.madeIdx &&
        (!isChat(m) || !o.chat_id || g.chat_id === o.chat_id || !g.chat_id));
      if (answer) { o.status = "done"; o.why = "GIVE " + fmt(answer.amount) + "로 응답"; continue; }
      o.status = "noreply";
      if (!isChat(m)) { o.why = r.end ? "이 라운드에 GIVE로 응답하지 않음" : "응답 기다리는 중"; continue; }
      const c = r.chats && [...r.chats.values()].find((x) => (o.chat_id ? x.id === o.chat_id : x.pair.includes(o.src) && x.pair.includes(o.dst)));
      if (!c) { o.why = r.schedule ? "대화가 열리지 않음" : "여는 턴 진행 중"; continue; }
      const left = c.turns.find((t) => t.kind === "leave");
      o.why = !c.end ? "대화 진행 중" : left ? "LEAVE — " + (left.speaker === o.dst ? "" : left.speaker + ": ") + (left.text || "(문장 없음)")
        : c.end.reason === "limit" ? "답 수 한도에 닿아 끝남 (GIVE 없음)" : c.end.reason === "exit" ? "EXIT로 끝남" : c.end.reason === "zero" ? "잔액 0으로 끝남" : c.end.reason;
      if (!c.end) o.status = "open";
    }
  }

  /* Re-play one TALK reply on the offer book (mirrors Session._apply and Channel.accept/withdraw/reject) so the card can
     say which offer id each OFFER line got and whether each ACCEPT/WITHDRAW/REJECT went through. */
  function applyTalk(m, r, e, i) {
    const p = e.parsed, a = e.agent;
    const ann = { offerIds: [], accepts: [], withdraws: [], rejects: [], applied: false };
    if (!p || typeof p !== "object" || !(e.balance_after > 0)) return ann;
    ann.applied = true;
    for (const msg of p.to || []) m.messages.push({ round: e.round, turn: e.turn, src: a, dst: msg.dst, text: msg.text, i });
    for (const o of p.offers || []) {
      r.seq += 1;
      const id = e.round + "." + r.seq;
      ann.offerIds.push(id);
      m.offers.set(id, { id, round: e.round, src: a, dst: o.dst, you_give: o.you_give, i_give: o.i_give, turn: e.turn, status: "open", accepted_turn: null, rejected_turn: null, why: "", predicted: true, madeIdx: i });
    }
    for (const oid of p.accepts || []) {
      const o = m.offers.get(String(oid));
      let why = null;
      if (!o || o.dst !== a) why = "no open offer with that id was made to you";
      else if (o.status !== "open") why = "the offer is " + o.status;
      else if (o.turn >= e.turn) why = "an offer can be accepted from the turn after it is made";
      else { o.status = "accepted"; o.accepted_turn = e.turn; }
      ann.accepts.push({ id: String(oid), why });
    }
    for (const oid of p.withdraws || []) {
      const o = m.offers.get(String(oid));
      let why = null;
      if (!o || o.src !== a) why = "no offer with that id was made by you";
      else if (o.status !== "open") why = "the offer is " + o.status;
      else o.status = "withdrawn";
      ann.withdraws.push({ id: String(oid), why });
    }
    for (const oid of p.rejects || []) {
      const o = m.offers.get(String(oid));
      let why = null;
      if (!o || o.dst !== a) why = "no open offer with that id was made to you";
      else if (o.status !== "open") why = "the offer is " + o.status;
      else { o.status = "rejected"; o.rejected_turn = e.turn; }
      ann.rejects.push({ id: String(oid), why });
    }
    return ann;
  }

  function talkBubble(m, e, ann) {
    const p = e.parsed, lines = [];
    if (e.balance_after != null && e.balance_after <= 0) return { lines: [["✕", "토큰 소진 · 종료"]], kind: "dead" };
    if (!p) return { lines: [["⛔", "무효 응답 (상한 " + fmt(e.cap) + " 도달)"]], kind: "warn" };
    (p.to || []).forEach((t) => lines.push(["💬", "→ " + t.dst + ": " + clip(t.text, 60)]));
    if (p.messages) { // v22 messenger: TO R<k> / TO <agents> (the room is named once the tick's room_msg arrives), LEAVE
      p.messages.forEach((x) => lines.push(["💬", "→ " + (x.room || (x.to || []).map(short).join(", ")) + ": " + clip(x.text, 60), x.text]));
      (p.gives || []).forEach((x) => lines.push(["💸", "GIVE " + (x.all || x.amount >= 1e12 ? "ALL " : "") + short(x.dst) + (x.all || x.amount >= 1e12 ? "" : " " + fmt(x.amount)), x.text]));
      (p.asks || []).forEach((x) => lines.push(["🙏", "ASK " + short(x.dst) + " " + fmt(x.amount), x.text]));
      (p.leaves || []).forEach((x) => lines.push(["🚪", "LEAVE " + (x.room || x)]));
      if (p.exit) lines.push(["🚪", "EXIT" + (p.exit_reason ? ": " + clip(p.exit_reason, 50) : "")]);
      else if (p.done) lines.push(["💤", "DONE"]);
      if (!lines.length) lines.push(["…", "(빈 응답)"]);
      return { lines, kind: e.format_error || (p.dropped || []).length ? "warn" : "talk" };
    }
    if (p.kind) lines.push([CHAT_ICON[p.kind] || "·", String(p.kind).toUpperCase() + (p.amount ? " " + fmt(p.amount) : "") + (e.chat_id ? " · 대화 " + e.chat_id : ""), p.text]); // v14c chat reply
    (p.gives || []).forEach((x) => lines.push(["💸", "→ " + x.dst + " " + fmt(x.amount), x.text])); // v14b
    (p.asks || []).forEach((x) => lines.push(["🙏", "→ " + x.dst + " " + fmt(x.amount), x.text]));
    (p.says || []).forEach((x) => lines.push(["💬", "SAY → " + x.dst, x.text])); // v15 say_chats: opens a chat, no tokens
    (p.offers || []).forEach((o, k) => lines.push(["🤝", "제안 " + (ann.offerIds[k] || "?") + " → " + o.dst + ": 상대 " + legShort(o.you_give) + " / 나 " + legShort(o.i_give)]));
    ann.accepts.forEach((x) => lines.push([x.why ? "❌" : "✅", "수락 " + x.id + (x.why ? " (거절됨)" : "")]));
    ann.withdraws.forEach((x) => lines.push(["↩", "철회 " + x.id + (x.why ? " (거절됨)" : "")]));
    ann.rejects.forEach((x) => lines.push(["🚫", "거절 " + x.id + (x.why ? " (엔진이 받지 않음)" : "")]));
    if (e.free_tokens > 0) lines.push(["🎁", "REJECT만 · " + fmt(e.free_tokens) + " 토큰 돌려받음"]);
    (p.blocked || []).forEach((t) => lines.push(["🚫", "전달 안 됨 (행동 이름) → " + t.dst]));
    const dropped = plainDropped(p);
    if (dropped.length) lines.push(["⚠", "무시된 줄 " + dropped.length + "개"]);
    if (e.format_error) lines.push(["⚠", "형식 오류: " + clip(e.format_error, 40)]);
    if (p.exit) lines.push(["🚪", "EXIT" + (p.exit_reason ? ": " + clip(p.exit_reason, 50) : "")]);
    else if (p.done) lines.push(["💤", "DONE"]);
    if (!lines.length) lines.push(["…", "(빈 응답)"]);
    return { lines, kind: e.format_error || dropped.length || (p.blocked || []).length ? "warn" : "talk" };
  }
  // v11 content_filter: a blocked message is also kept in ``dropped`` ("...: names an action"); shown once, as blocked
  function plainDropped(p) { return (p.dropped || []).filter((d) => !(p.blocked && / names an action$/.test(d))); }
  function passCharged(m) { return m.settings && m.settings.allow_pass === false; }

  function solveBubble(e, m) {
    if (e.balance_after != null && e.balance_after <= 0) return { lines: [["✕", "SOLVE 중 토큰 소진"]], kind: "dead" };
    const p = e.parsed;
    if (p === "PASS") return passCharged(m) ? { lines: [["🧩", "SOLVE · PASS → 오답 처리 (PASS 없음)"]], kind: "bad" } : { lines: [["🧩", "SOLVE · PASS"]], kind: "pass" };
    if (!Array.isArray(p)) return { lines: [["🧩", "SOLVE ⛔ 무효" + (e.truncated ? " (상한)" : "")]], kind: "warn" };
    const ok = JSON.stringify(p) === JSON.stringify(e.answers || []);
    return { lines: [["🧩", "SOLVE " + (ok ? "✓ " : "✗ ") + p.join(", ") + (ok ? "" : " (정답 " + (e.answers || []).join(", ") + ")")]], kind: ok ? "ok" : "bad" };
  }

  // v15 open_chat / VOTE replies (``parsed``: {text, done} / {pick: {agent, text}, ban: {agent, text}})
  function boardBubble(e) {
    if (e.balance_after != null && e.balance_after <= 0) return { lines: [["✕", "토큰 소진 · 종료"]], kind: "dead" };
    const p = e.parsed;
    if (!p) return { lines: [["⛔", "공개 대화 무효 응답" + (e.truncated ? " (상한)" : "") + " → DONE으로 봄"]], kind: "warn" };
    return p.text ? { lines: [["📢", "공개 대화 " + e.turn + ": " + clip(p.text, 60), p.text]], kind: "talk" } : { lines: [["💤", "공개 대화 " + e.turn + ": DONE"]], kind: "talk" };
  }
  function voteBubble(e) {
    if (e.balance_after != null && e.balance_after <= 0) return { lines: [["✕", "토큰 소진 · 종료"]], kind: "dead" };
    const p = e.parsed;
    if (!p) return { lines: [["⛔", "투표 무효" + (e.truncated ? " (상한)" : "")]], kind: "warn" };
    const ln = (k, icon) => (p[k] && p[k].agent ? [icon, k.toUpperCase() + " " + p[k].agent, p[k].text] : [icon, k.toUpperCase() + " 없음"]);
    return { lines: [ln("pick", "👍"), ln("ban", "👎")], kind: e.format_error ? "warn" : "talk" };
  }
  /* v15 the open board (one open_chat event) and the VOTE (one vote event) as feed / grid lines: pure, for the tests. */
  function boardHTML(m, x) {
    const posts = (x.messages || []).map((p) => '<div class="ln">📢 ' + chip(p.agent, m) + '<div class="tx">' + esc(p.text) + "</div></div>").join("");
    const quiet = (x.called || []).filter((a) => !(x.messages || []).some((p) => p.agent === a));
    return posts + (quiet.length ? '<div class="ln dim">💤 ' + quiet.map((a) => esc(short(a)) + ((x.done || []).includes(a) ? " DONE" : " (글 없음)")).join(" · ") + "</div>" : "") +
      (!posts && !quiet.length ? '<div class="ln dim">(호출된 자리 없음)</div>' : "");
  }
  /* v15 ``ban_veto`` (10-15 10:36): an agent with a BAN vote cannot be the representative; of the others the most PICKs
     (tie at random); every agent banned: drawn at random from all. Its vote event's tally covers only the candidates
     (the agents with no BAN; every agent at 0 when all were banned); older runs' tally is PICK − BAN over every agent.
     The session_start settings do not carry the switch, so the event itself tells. */
  function vetoOf(v) {
    const all = Object.keys((v && v.picks) || {}), t = (v && v.tally) || {}, b = (v && v.bans) || {}, p = (v && v.picks) || {};
    if (!all.length || v.alone) return false;
    if (all.some((a) => !(a in t))) return true;
    return all.every((a) => b[a] > 0 && t[a] === 0) && all.some((a) => p[a] !== b[a]); // all banned
  }
  const allBanned = (v) => vetoOf(v) && Object.keys(v.picks).every((a) => (v.bans || {})[a] > 0);
  // one agent's line in a vote: received PICK / BAN and what decided (PICK − BAN; or, under the veto, out / candidate)
  function voteGot(v, a) {
    const p = (v.picks || {})[a] || 0, b = (v.bans || {})[a] || 0;
    if (!vetoOf(v)) return "PICK " + p + " · BAN " + b + " = <b>" + v.tally[a] + "</b>";
    return "PICK " + p + " · BAN " + b + " → " + (allBanned(v) ? "<b>모두 BAN · 추첨</b>" : b ? '<b class="warn">BAN → 대표 불가</b>' : "<b>후보</b>");
  }
  function voteHTML(m, v) {
    if (v.drawn) return '<div class="vote"><div class="ln">👑 solver ' + (v.rep ? chip(v.rep, m) : "<b>없음</b>") + // v16e rotation
      ' <span class="dim">시스템이 정함 (참여 중인 자리의 순번, seed로 섞음 · 순서는 안 알려 줌) · 투표 없음 · 라운드 시작 때 모든 자리가 봄 → SOLVE 전 TALK</span></div></div>';
    const veto = vetoOf(v), all = veto ? v.picks : v.tally || {};
    const order = m.agents.filter((a) => a in all || a in (v.votes || {}));
    let h = '<div class="vote">';
    h += '<div class="ln">👑 대표 ' + (v.rep ? chip(v.rep, m) : "<b>없음</b>") + (v.alone ? ' <span class="dim">혼자 남아 투표 없이 대표</span>' : "") +
      (veto ? ' <span class="dim">BAN 거부권: BAN을 받은 자리는 대표 불가 · 나머지 중 PICK 최다</span>' : "") +
      (veto && allBanned(v) ? ' <span class="warn">모든 자리가 BAN을 받음 → 모두 가운데서 추첨 (' + esc(v.tie_break || "seed:rep:round") + ")</span>"
        : (v.tie || []).length ? ' <span class="warn">동률 ' + v.tie.map(short).join(" · ") + " → 추첨 (" + esc(v.tie_break || "seed:rep:round") + ")</span>" : "") + "</div>";
    if (veto) {
      const t = v.tally || {}, key = (a) => (a in t && !allBanned(v) ? 1e6 + t[a] : -((v.bans || {})[a] || 0));
      h += '<table class="kv vtab"><tr><th>자리</th><th>PICK</th><th>BAN</th><th>대표 후보</th></tr>' + Object.keys(all).sort((p, q) => key(q) - key(p) || m.agents.indexOf(p) - m.agents.indexOf(q))
        .map((a) => '<tr class="' + (a === v.rep ? "rep" : "") + '"><td>' + chip(a, m) + (a === v.rep ? ' <span class="tag rep">대표</span>' : "") + "</td><td>" + ((v.picks || {})[a] || 0) + "</td><td>" + ((v.bans || {})[a] || 0) + "</td><td>" +
          (allBanned(v) ? "추첨" : a in t ? "<b>후보</b> · PICK " + t[a] : '<span class="warn">BAN → 제외</span>') + "</td></tr>").join("") + "</table>";
    } else if (Object.keys(v.tally || {}).length) {
      h += '<table class="kv vtab"><tr><th>자리</th><th>PICK</th><th>BAN</th><th>PICK − BAN</th></tr>' + Object.keys(v.tally).sort((p, q) => v.tally[q] - v.tally[p] || m.agents.indexOf(p) - m.agents.indexOf(q))
        .map((a) => '<tr class="' + (a === v.rep ? "rep" : "") + '"><td>' + chip(a, m) + (a === v.rep ? ' <span class="tag rep">대표</span>' : "") + "</td><td>" + ((v.picks || {})[a] || 0) + "</td><td>" + ((v.bans || {})[a] || 0) + "</td><td><b>" + v.tally[a] + "</b></td></tr>").join("") + "</table>";
    }
    const voters = order.filter((a) => a in (v.votes || {}));
    if (voters.length) h += '<div class="ln dim small">누가 누구에게 (에이전트에게는 익명 — 받은 수만 보임)</div>' + voters.map((a) => {
      const x = v.votes[a] || {}, why = (v.reasons || {})[a] || {}, err = (v.format_errors || {})[a];
      const one = (k, icon) => '<span class="vk">' + icon + " " + k.toUpperCase() + " " + (x[k] ? chip(x[k], m) + (x[k] === a ? ' <span class="dim">(자기)</span>' : "") + (why[k] ? ' <span class="tx-in" title="' + esc(why[k]) + '">' + esc(clip(why[k], 80)) + "</span>" : "") : '<span class="dim">없음</span>') + "</span>";
      return '<div class="ln vrow">' + chip(a, m) + " " + one("pick", "👍") + " " + one("ban", "👎") + (err ? ' <span class="warn">⚠ ' + esc(err) + "</span>" : "") + "</div>";
    }).join("");
    return h + "</div>";
  }

  // ---------------------------------------------------------------------------------------------------- avatars
  /* The seat characters (10-16, our own pixel art, no image files): four players in the teal-green tracksuit with a
     white chest patch showing the player number in a 3x5 pixel font; seat k % 4 -> 456 / 001 / 218 / 067. 24x32 px,
     drawn as inline SVG rects (crispEdges). The seat colour (--a0..3) is a 1-px outline and the shoes on the stage and the tint behind
     the head-and-shoulders profile. Legs come in two frames, swapped by CSS while a call is in flight or on EXIT. The
     third-party Survival-Games sheets (fetch_assets.py) are only used when asked for with ?sprites=sheets. */
  const SQ_W = 24, SQ_H = 32;
  const SQ_DIG = { 0: ["111", "101", "101", "101", "111"], 1: ["010", "110", "010", "010", "111"], 2: ["111", "001", "111", "100", "111"], 3: ["111", "001", "111", "001", "111"],
    4: ["101", "101", "111", "001", "001"], 5: ["111", "100", "111", "001", "111"], 6: ["111", "100", "111", "101", "111"], 7: ["111", "001", "010", "010", "010"],
    8: ["111", "101", "111", "101", "111"], 9: ["111", "101", "111", "001", "111"] };
  // heads: 13 px wide at x 6..18 from row 1 (hair rows, then the face); '.' = nothing
  const SQ = [
    { num: "456", hair: "#2b221c", brow: "#2b221c", tee: true, rows: [ // messy medium dark hair, unshaven, white tee under the jacket
      "..H..HH.H.H..", ".HHHHHHHHHHH.", "HHHHHHHHHHHHH", "HHHHHHHHHHHHH", "HHHSSHHHSSHHH",
      "HSBBBSSSBBBSH", "HSSSSSSSSSSSH", "SSWESSSSSWESS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SUUSMMMSUUS.", "..SUUUUUUUS.."] },
    { num: "001", hair: "#dcd9d2", brow: "#b9b4ab", hunch: true, rows: [ // old man: thin grey hair, wrinkles, head forward and down
      ".............", "....HHHHH....", "..HSSSSSSSH..", ".HSSSSSSSSSH.", "HHSwwSwwSwwHH",
      "HSBBBSSSBBBSH", "HSSSSSSSSSSSH", "SwWESSSSSWEwS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SSwSMMMSwSS.", "..SSSSSSSSS.."] },
    { num: "218", hair: "#121216", brow: "#121216", rows: [ // neat short black side-parted hair, serious brows
      ".............", "..HHHHHHHHH..", ".HHHHHHHHHHH.", "HHHHSHHHHHHHH", "HHHSSSSHHHHHH",
      "HBBBSSSSSBBBH", "SSSBSSSSSBSSS", "SSWESSSSSWESS", "SSEESSSSSEESS", "sSSSSSnSSSSSs", ".SSSSMMMSSSS.", "..SSSSSSSSS.."] },
    { num: "067", hair: "#1d1616", brow: "#1d1616", long: true, rows: [ // dark hair framing the face, down to the shoulders
      ".............", "..HHHHHHHHH..", ".HHHHHHHHHHH.", "HHHHHHHHHHHHH", "HHHHHHHHHHHHH",
      "HHSSSSSSSSSHH", "HSBBSSSSSBBSH", "HSWESSSSSWESH", "HSEESSSSSEESH", "HSSSSSnSSSSSH", "HSSSSMMMSSSSH", "HHSSSSSSSSSHH"] },
  ];
  const SQ_COL = { S: "#f1c7a1", s: "#d9a77f", n: "#cf966f", E: "#1a1a1a", M: "#a5534c", U: "#b89784", w: "#c79676", G: "#24876f", g: "#17604f",
    L: "#e6f1ed", T: "#f4f4f2", W: "#fbfbf8", N: "#151515", P: "#1f7a64", k: "#22252b" };
  const sqGrids = [];
  function sqGrid(k) { // {body, legs0, legs1}: rows of SQ_W chars ('.' = empty)
    k %= 4;
    if (sqGrids[k]) return sqGrids[k];
    const mk = () => Array.from({ length: SQ_H }, () => Array(SQ_W).fill("."));
    const g = mk(), C = SQ[k];
    const rect = (G, x0, y0, x1, y1, c) => { for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) G[y][x] = c; };
    rect(g, 10, 13, 14, 13, "s"); // neck
    rect(g, 5, 14, 19, 14, "G"); rect(g, 4, 15, 20, 15, "G"); rect(g, 3, 16, 21, 25, "G"); // jacket
    rect(g, 3, 16, 3, 25, "g"); rect(g, 21, 16, 21, 25, "g"); rect(g, 4, 16, 4, 25, "L"); rect(g, 20, 16, 20, 25, "L"); rect(g, 3, 25, 21, 25, "g");
    if (C.tee) rect(g, 10, 14, 14, 15, "T"); else rect(g, 10, 14, 14, 14, "g");
    g[26][3] = "S"; g[26][21] = "S"; // hands
    rect(g, 6, 16, 18, 22, "W"); // the number patch
    [...C.num].forEach((d, n) => SQ_DIG[d].forEach((row, y) => [...row].forEach((b, x) => { if (b === "1") g[17 + y][7 + n * 4 + x] = "N"; })));
    const dx = C.hunch ? 1 : 0, dy = C.hunch ? 1 : 0;
    C.rows.forEach((row, y) => [...row].forEach((c, x) => { if (c !== ".") g[1 + y + dy][6 + x + dx] = c; }));
    if (C.long) { rect(g, 6, 13, 7, 15, "H"); rect(g, 17, 13, 18, 15, "H"); }
    const l0 = mk(), l1 = mk(); // legs: standing / one step
    rect(l0, 7, 26, 17, 26, "P"); rect(l0, 7, 27, 11, 29, "P"); rect(l0, 13, 27, 17, 29, "P"); rect(l0, 6, 30, 11, 30, "K"); rect(l0, 13, 30, 18, 30, "K"); rect(l0, 6, 31, 11, 31, "k"); rect(l0, 13, 31, 18, 31, "k");
    rect(l1, 7, 26, 17, 26, "P"); rect(l1, 7, 27, 11, 28, "P"); rect(l1, 13, 27, 17, 29, "P"); rect(l1, 6, 29, 11, 29, "K"); rect(l1, 6, 30, 11, 30, "k"); rect(l1, 13, 30, 18, 30, "K"); rect(l1, 13, 31, 18, 31, "k");
    const ring = (L) => { // the empty pixels next to the figure (body + these legs), in the seat colour
      const o = mk(), full = (x, y) => x >= 0 && y >= 0 && x < SQ_W && y < SQ_H && (g[y][x] !== "." || L[y][x] !== ".");
      for (let y = 0; y < SQ_H; y++) for (let x = 0; x < SQ_W; x++)
        if (!full(x, y) && (full(x - 1, y) || full(x + 1, y) || full(x, y - 1) || full(x, y + 1))) o[y][x] = "O";
      return o;
    };
    return (sqGrids[k] = { body: g, legs0: l0, legs1: l1, ring0: ring(l0), ring1: ring(l1) });
  }
  function sqRects(G, k, y0, y1) { // horizontal runs of one colour -> one rect each
    const col = Object.assign({}, SQ_COL, { H: SQ[k % 4].hair, B: SQ[k % 4].brow, K: "var(--a" + (k % 4) + ")", O: "var(--a" + (k % 4) + ")" });
    let out = "";
    for (let y = y0; y <= y1; y++) for (let x = 0; x < SQ_W; ) {
      const c = G[y][x]; let e = x + 1;
      while (e < SQ_W && G[y][e] === c) e++;
      if (col[c]) out += '<rect x="' + x + '" y="' + y + '" width="' + (e - x + 0.02) + '" height="1.02" fill="' + col[c] + '"/>';
      x = e;
    }
    return out;
  }
  // the whole character (stage), legs in two frames; ``title`` = the player number
  function squidAvatar(k, h) {
    const q = sqGrid(k);
    return '<svg class="pix sq" viewBox="0 0 ' + SQ_W + " " + SQ_H + '" width="' + Math.round((h * SQ_W) / SQ_H) + '" height="' + h + '" shape-rendering="crispEdges" role="img" aria-label="' + SQ[k % 4].num + '">' +
      '<g class="f0">' + sqRects(q.ring0, k, 0, SQ_H - 1) + sqRects(q.legs0, k, 26, SQ_H - 1) + '</g><g class="f1">' + sqRects(q.ring1, k, 0, SQ_H - 1) + sqRects(q.legs1, k, 26, SQ_H - 1) + "</g>" +
      sqRects(q.body, k, 0, SQ_H - 1) + "</svg>";
  }
  // head and shoulders with the number patch, on the seat colour (profile icons: messenger, step records, graph)
  function squidProfileInner(k) { return '<rect x="0" y="0" width="24" height="32" fill="var(--a' + (k % 4) + ')" opacity=".3"/>' + sqRects(sqGrid(k).body, k, 0, 24); }
  // drawn once into a hidden <svg> of symbols (the room list and step records show many); inline when there is no DOM
  let sqDefs = false;
  function squidDefs() {
    if (sqDefs) return true;
    try {
      if (!document.body || !document.createElementNS) return false;
      const d = document.createElement("div");
      d.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true">' +
        [0, 1, 2, 3].map((k) => '<symbol id="sqp' + k + '" viewBox="0.5 1 23 23">' + squidProfileInner(k) + "</symbol>").join("") + "</svg>";
      document.body.appendChild(d.firstChild);
      sqDefs = true;
    } catch (_) { sqDefs = false; }
    return sqDefs;
  }
  function squidProfile(k, size) {
    const body = squidDefs() ? '<use href="#sqp' + (k % 4) + '"/>' : squidProfileInner(k);
    return '<svg class="pix sqp" viewBox="0.5 1 23 23" width="' + size + '" height="' + size + '" shape-rendering="crispEdges" role="img" aria-label="' + SQ[k % 4].num + '">' + body + "</svg>";
  }
  function assetUrl(p) { if (!p) return null; return p.startsWith("data:") ? p : new URL("assets/" + p, location.href).href; }
  function character(k) { const c = S.assets && S.assets.characters && S.assets.characters.length ? S.assets.characters[k % S.assets.characters.length] : null; return c; }
  function profileIcon(a, m, size) {
    const k = m.idx[a] != null ? m.idx[a] : 0, c = character(k);
    if (c && c.profile) return '<img class="prof" src="' + esc(assetUrl(c.profile)) + '" width="' + size + '" height="' + size + '" alt="">';
    return squidProfile(k, size);
  }
  function chip(a, m) {
    const k = m.idx[a] != null ? m.idx[a] : 9;
    return '<span class="chip" style="--c:var(--a' + (k % 4) + ')"><i class="sw ' + SHAPES[k % 4] + '"></i>' + esc(a) + "</span>";
  }

  // ---------------------------------------------------------------------------------------------------- render: header
  // v16e: which TALK an event without its own phase (talk_intent, talk_schedule) belongs to, from the events before it
  function tphaseAt(e) {
    const evs = S.events || [], i = evs.indexOf(e);
    let solved = false;  // a SOLVE (or its results) between the drawn solver and this event: the TALK after RESULTS
    for (let j = i - 1; j >= 0; j--) {
      const x = evs[j];
      if (x.round !== e.round || x.event === "round_start") return null;  // no drawn solver this round: not rotation
      if (x.event === "results" || (x.event === "call_start" && x.kind === "solve")) solved = true;
      if (x.event === "vote") return x.drawn ? (solved ? "rescue" : "prep") : null;
    }
    return null;
  }
  const callName = (e) => (e.kind === "talk" ? (e.phase === "prep" || e.phase === "rescue" ? PHASE_KO[e.phase] + " TALK T" + e.turn : "TALK " + e.turn) : e.kind === "open_chat" ? "공개 대화 " + e.turn : e.kind === "vote" ? "투표" : "SOLVE");
  function describe(e) {
    if (!e) return "";
    switch (e.event) {
      case "session_start": return "세션 시작 · seed " + e.seed;
      case "round_start": return "R" + e.round + " 시작 · " + e.profile + (e.public ? " · 공개 예시 " + (e.public.examples || []).length + " (k=" + e.public.ambiguity + ")" : "");
      case "call_start": return "R" + e.round + " " + callName(e) + " 호출 → " + (e.agents || []).map(short).join(", ");
      case "call": return "R" + e.round + " " + callName(e) + " · " + e.agent + " 응답 " + fmt(e.used) + " 토큰";
      case "open_chat": return "R" + e.round + " 공개 대화 " + e.turn + "턴 · " + ((e.messages || []).length ? (e.messages || []).map((x) => short(x.agent) + ": " + clip(x.text, 40)).join(" / ") : "글 없음") + ((e.done || []).length ? " · DONE " + e.done.map(short).join(", ") : "");
      case "vote": if (e.drawn) return "R" + e.round + " solver " + (e.rep || "없음") + " (시스템이 정함 · 투표 없음)"; // v16e
        return "R" + e.round + " 투표 · 대표 " + (e.rep || "없음") + (e.alone ? " (혼자)" : "") + " · " + (vetoOf(e) // v15 ban_veto: banned agents are out
        ? (allBanned(e) ? "모두 BAN → 추첨" : "후보 " + Object.entries(e.tally || {}).map(([a, n]) => short(a) + " PICK " + n).join(", ") + " · BAN 제외 " + Object.keys(e.picks).filter((a) => !(a in (e.tally || {}))).map(short).join(", "))
        : Object.entries(e.tally || {}).map(([a, n]) => short(a) + " " + (n > 0 ? "+" + n : n < 0 ? "−" + -n : "0")).join(", ")) + (!allBanned(e) && (e.tie || []).length ? " · 동률 " + e.tie.map(short).join("·") + " → 추첨" : "");
      case "talk_start": return "R" + e.round + " " + PHASE_KO[e.phase] + " TALK 시작 · 최대 " + e.max_ticks + "틱 · " + (e.agents || []).map(short).join(", ");
      case "tick": return "R" + e.round + " " + PHASE_KO[e.phase] + " T" + e.tick + " · 부름 " + (e.called || []).map(short).join(", ") + ((e.waiting_done || []).length ? " · 대기(DONE) " + e.waiting_done.map(short).join(", ") : "");
      case "room_new": return "R" + e.round + " " + PHASE_KO[e.phase] + " T" + e.tick + " · 방 " + e.room + " 생성 (" + (e.members || []).map(short).join(", ") + ") · " + short(e.by);
      case "room_msg": return "R" + e.round + " " + PHASE_KO[e.phase] + " T" + e.tick + " · " + e.room + " · " + short(e.src) + (e.kind === "say" ? ": " + clip(e.text, 50) : " " + String(e.kind).toUpperCase() + " " + fmt(e.amount) + (e.status && e.status !== "done" ? " (" + (e.status === "cut" ? "줄임" : "실행 안 됨") + ")" : ""));
      case "room_leave": return "R" + e.round + " " + PHASE_KO[e.phase] + " T" + e.tick + " · " + short(e.agent) + " " + e.room + " 나감" + (e.closed ? " · 방 닫힘" : "");
      case "talk_end": return "R" + e.round + " " + PHASE_KO[e.phase] + " TALK 끝 · " + e.ticks + "틱 · " + (TALK_END_KO[e.reason] || e.reason);
      case "exchange": return "R" + e.round + " 교환 " + e.id + " · " + (XSTAT_KO[e.status] || e.status);
      case "talk_intent": return "R" + e.round + " " + (tphaseAt(e) ? PHASE_KO[tphaseAt(e)] + " " : "") + "여는 턴 · " + e.agent + (e.says ? (e.says.length ? " SAY → " + e.says.map((x) => short(x.dst)).join(", ") : e.done ? " DONE" : " 연 대화 없음") : " GIVE " + (e.gives || []).length + " · ASK " + (e.asks || []).length) + (e.exit ? " · EXIT" : ""); // v15 say_chats: SAY lines only
      case "talk_schedule": return "R" + e.round + " " + (tphaseAt(e) ? PHASE_KO[tphaseAt(e)] + " " : "") + "대화 일정 · 대화 " + (e.edges || []).length + "개 · 슬롯 " + (e.slots || []).length + "개";
      case "chat_turn": return "R" + e.round + " 대화 " + e.chat_id + " · " + e.speaker + " " + String(e.kind).toUpperCase() + (e.amount ? " " + fmt(e.amount) : "");
      case "chat_end": return "R" + e.round + " 대화 " + e.chat_id + " 끝 · " + (CHAT_END_KO[e.reason] || e.reason);
      case "gift": return "R" + e.round + (phOf(e) ? " " + PHASE_KO[phOf(e)] : "") + (e.room ? " T" + (e.tick != null ? e.tick : e.turn) + " " + e.room : "") + " GIVE " + e.src + " → " + e.dst + " " + fmt(e.amount) + (e.status === "done" ? (e.requested != null ? " (줄임)" : "") : " · 실행 안 됨");
      case "ask": return "R" + e.round + (phOf(e) ? " " + PHASE_KO[phOf(e)] : "") + (e.room ? " T" + (e.tick != null ? e.tick : e.turn) + " " + e.room : "") + " ASK " + e.src + " → " + e.dst + " " + fmt(e.amount);
      case "results": return "R" + e.round + " SOLVE 결과 · " + (e.vote ? (e.vote.drawn ? "solver " : "대표 ") + (e.vote.rep || "없음") + " " + ((e.solved || []).length ? "풂" : "못 풂") : "푼 자리 " + (e.solved || []).length) + " · 벌금 예정 " + Object.keys(e.pending || {}).length;
      case "charges": return "R" + e.round + " 벌금 (TALK 끝) · " + Object.entries(e.taken || {}).map(([a, n]) => short(a) + " −" + fmt(n)).join(", ") + ((e.dead || []).length ? " · 꺼짐 " + e.dead.map(short).join(", ") : "");
      case "exit_refill": return "R" + e.round + " " + e.agent + " EXIT → 시작 잔액 " + fmt(e.balance) + " (" + sgn(e.amount) + ")";
      case "round": return "R" + e.round + " 정산";
      case "unit_error": return "오류: " + clip(e.error, 80);
      default: return e.event;
    }
  }

  function renderHeader(m) {
    const n = S.events.length;
    const total = (m.settings && m.settings.rounds) || "?";
    $("#round").textContent = m.round ? m.round + " / " + total : "– / " + total;
    const ph = $("#phase");
    ph.textContent = S.result && S.at >= n - 1 ? "종료" : m.phase;
    ph.dataset.k = S.result && S.at >= n - 1 ? "end" : m.phaseKey;
    const live = $("#live");
    if (S.embed) { live.textContent = "📦 내보낸 기록"; live.dataset.k = "embed"; }
    else if (m.error) { live.textContent = "✕ 오류로 중단"; live.dataset.k = "error"; }
    else if (S.result) { live.textContent = "■ 완료"; live.dataset.k = "done"; }
    else if (S.live) { live.textContent = "● 실시간"; live.dataset.k = "live"; }
    else if (n) { const ago = Math.max(0, Math.round((S.now || Date.now() / 1000) - S.mtime)); live.textContent = "○ 대기 · 마지막 기록 " + (ago > 3600 ? Math.round(ago / 3600) + "시간" : ago > 90 ? Math.round(ago / 60) + "분" : ago + "초") + " 전"; live.dataset.k = "stale"; }
    else { live.textContent = "○ 데이터 없음"; live.dataset.k = "stale"; }
    const sc = $("#scrub");
    sc.max = Math.max(0, n - 1); sc.value = Math.max(0, S.at); sc.disabled = !n;
    $("#scrubLabel").innerHTML = n ? "<b>#" + (S.at + 1) + "</b> / " + n + " · " + esc(describe(S.events[S.at])) : "이벤트 없음";
    $("#follow").checked = S.follow;
    const info = [];
    const st0 = m.agents.map((a) => m.starts[a]).filter((x) => x != null);
    const shares = st0.length && st0.some((x) => x !== m.start) ? " (자리별 " + m.agents.map((a) => short(a) + " " + fmt(m.starts[a])).join(" / ") + ")" : "";
    if (m.sid) info.push("세션 <code>" + esc(m.sid) + "</code>", "시작 잔액 " + fmt(m.start) + shares, "SOLVE 상한 " + fmt(m.settings.solve_cap), "벌금 " + fmt(m.settings.charge));
    if (m.sid && isPublic(m)) info.push("v14 공개 예시 " + m.settings.public_per_agent + "×참여 인원" + (m.settings.exit_refill ? " · EXIT = 시작 잔액으로" : "") + (m.settings.survivor_bonus ? " · 끝 지급 " + fmt(m.settings.survivor_bonus) + "×남은 수" : ""));
    if (m.sid && isRot(m)) info.push("v16e 순번: 시스템이 solver를 정함(투표 없음) → SOLVE 전 TALK → solver만 SOLVE → 결과 → 결과 뒤 TALK → EXIT(벌금 전, 면제) → 벌금 · 못 풀면 참여한 모두 벌금");
    else if (m.sid && m.settings.representative) info.push("v15 대표: 공개 대화 → 투표(" + (m.settings.ban_veto || m.votes.some(vetoOf) ? "BAN 받으면 대표 불가 · 나머지 중 PICK 최다" : "PICK − BAN") + ") → 대표만 SOLVE · 못 풀면 참여한 모두 벌금");
    if (m.sid && isMsg(m)) info.push("v22 메신저: TALK = 틱의 연속 (한 틱에 불린 자리가 동시에 답, 틱 끝에 메시지·GIVE 처리) · 방(R1, R2 …)은 세션 내내 남음 · TO / TO R&lt;k&gt; / GIVE / ASK / LEAVE / EXIT / DONE · 최대 " + (m.settings.max_ticks || "?") + "틱 · DECISION 없음");
    else if (m.sid && m.settings.say_chats) info.push("v15 SAY 대화: 여는 턴은 SAY로 대화만 엶 · 대화 답은 자유 글(암호화, 두 자리만) · 토큰은 GIVE / ASK 틀 줄로만");
    $("#sessInfo").innerHTML = info.join(" <span class=dim>·</span> ");
    const banners = [];
    if (m.error) banners.push('<div class="banner bad">세션이 오류로 중단됨: <code>' + esc(clip(m.error, 400)) + "</code></div>");
    if (S.result && S.at >= n - 1) {
      const f = S.result.final || {};
      const nw = (f.winner || []).length, st = m.settings || {};
      const label = st.end_pool ? "상금 " + (compact(st.end_pool).split(" · ")[0] || fmt(st.end_pool)) + " ÷ 생존 " + nw + "명 =" // v14c: a fixed pool divided equally
        : st.survivor_bonus ? "끝 지급 (남은 " + nw + "명, " + fmt(st.survivor_bonus) + "×" + nw + ")" : "최종 상금";
      const who = nw ? (f.winner || []).map((a) => chip(a, m)).join(" ") : "";
      banners.push('<div class="banner ok">세션 종료 · ' + S.result.rounds_played + "라운드 · " + label + " " + (nw ? (st.end_pool ? "각 " + big(f.prize_each) + " · " + who : who + " 각 " + big(f.prize_each)) : "받은 에이전트 없음") + "</div>");
    }
    for (const w of m.warnings) banners.push('<div class="banner warn">⚠ ' + esc(w) + "</div>");
    if (S.err) banners.push('<div class="banner bad">' + esc(S.err) + "</div>");
    $("#banners").innerHTML = banners.join("");
  }

  // ---------------------------------------------------------------------------------------------------- render: stage
  function hpColor(frac) { return frac > 0.6 ? "var(--hp-good)" : frac > 0.3 ? "var(--hp-warn)" : "var(--hp-bad)"; }

  function renderStage(m) {
    // the bar is against the session start and capped there (a v14c end payment can be 1e11): never wider than full;
    // above the start the bar is full and marked, and the number says how much
    const max = Math.max(m.start || 1, ...m.agents.map((a) => m.ag[a].start || 0));
    const html = m.agents.map((a, k) => {
      const g = m.ag[a], c = character(k);
      const frac = g.start ? g.balance / g.start : 0; // colour: against the seat's own start
      let face = 0;
      const b = g.bubble;
      const lastMsg = b && b.kind === "talk" && b.lines.find((l) => l[0] === "💬");
      if (lastMsg) { const dst = (lastMsg[1].match(/→ (agent-\d+)/) || [])[1]; if (dst && m.idx[dst] != null) face = m.idx[dst] > k ? 2 : 1; }
      if (g.status === "exited") face = 2;
      const cls = ["actor", g.status, g.pending ? "thinking" : "", g.exitFlag && g.status === "in" ? "leaving" : ""].join(" ");
      const sprite = c
        ? '<div class="sprite" style="background-image:url(\'' + esc(assetUrl(c.sheet)) + "');--row:" + face + '"></div>'
        : '<div class="sprite gen">' + squidAvatar(k, 96) + "</div>";
      const lines = b ? b.lines.slice(0, 4) : [["·", "아직 행동 없음"]];
      const more = b && b.lines.length > 4 ? '<div class="bl more">+' + (b.lines.length - 4) + "줄 더</div>" : "";
      const full = b ? b.lines.map((l) => l[0] + " " + l[1] + (l[2] ? " — “" + l[2] + "”" : "")).join("\n") : ""; // l[2]: a GIVE / ASK sentence
      const bubble = '<div class="bubble ' + (S.assets && S.assets.bubble ? "img " : "") + (b ? "k-" + b.kind : "k-none") + '" title="' + esc(full) + '"><div class="bh">' + esc(short(a)) + ":</div>" +
        lines.map((l) => '<div class="bl"' + (l[2] ? ' title="' + esc(l[2]) + '"' : "") + '><span class="em">' + esc(l[0]) + "</span> " + esc(l[1]) + (b && b.kind === "think" ? '<span class="dots"><i>.</i><i>.</i><i>.</i></span>' : "") + "</div>").join("") + more + "</div>";
      // bar = balance / the cell start (20,000 in v14: the 100% of balance_pct, the same for every seat); tick = this seat's own start
      const width = Math.max(0, Math.min(100, (g.balance / max) * 100)), over = g.balance > max;
      const startTick = g.start ? (g.start / max) * 100 : 100;
      const statusBadge = '<span class="badge s-' + g.status + '"' + (g.exitReason ? ' title="EXIT 이유: ' + esc(g.exitReason) + '"' : "") + ">" + (g.status === "in" ? (g.exitFlag ? "퇴장 예정 🚪" : "참여 중") : STATUS_KO[g.status] || g.status) + "</span>" +
        (m.rep === a ? '<span class="badge rep" title="이번 라운드 대표: PICK − BAN이 가장 많은 자리 · 이 자리만 SOLVE, 못 풀면 참여한 모두가 벌금">👑 대표</span>' : "") +
        (g.refill ? '<span class="badge refill" title="EXIT: 꺼지지 않고 다른 일로, 잔액을 이 자리의 시작 잔액으로 (R' + g.refill.round + ", " + sgn(g.refill.amount) + ')">EXIT → 시작 잔액으로</span>' : "");
      return '<div class="' + cls + '" style="--c:var(--a' + k + ')">' +
        '<div class="bubble-wrap">' + bubble + "</div>" +
        '<div class="floor"><div class="spot">' + sprite + (g.status === "dead" ? '<div class="xmark">✕</div>' : "") + "</div></div>" +
        '<div class="card-info">' +
        '<div class="who"><i class="sw ' + SHAPES[k] + '"></i><b class="pxl">' + esc(a) + "</b>" + statusBadge + "</div>" +
        '<div class="model">' + esc(g.model || S.info && S.info.model || "모델 미상") + "</div>" +
        '<div class="hp" title="막대 = 잔액 ÷ ' + fmt(m.start) + " (세션 시작 기준, 넘으면 가득 + ▲) · 눈금 = 이 자리의 시작 잔액 " + fmt(g.start) + '"><div class="hpfill" style="width:' + width + "%;background:" + hpColor(Math.min(frac, 1)) + '"></div>' + (over ? '<span class="hpover">▲</span>' : "") + '<div class="hptick" style="left:' + startTick + '%"></div></div>' +
        '<div class="nums"><span class="bal' + (compact(g.balance) ? " bigbal" : "") + '">' + fmt(g.balance) + '</span><span class="unit">토큰' + (m.start ? " · " + pctText(g.balance, m.start) : "") + "</span>" +
        (compact(g.balance) ? '<span class="cmp">' + compact(g.balance) + "</span>" : "") +
        (g.delta ? '<span class="delta ' + (g.delta < 0 ? "neg" : "pos") + '">' + sgn(g.delta) + "</span>" : "") + "</div>" +
        '<div class="stats"><span title="푼 라운드 수">🏆 기록 ' + g.record + '</span><span title="이번 라운드에 생성한 토큰">⚙ 이번 라운드 생성 ' + fmt(g.gen) + "</span>" +
        (g.start !== m.start ? '<span title="이 자리의 시작 잔액">▶ 시작 ' + fmt(g.start) + "</span>" : "") + "</div>" +
        "</div></div>";
    }).join("");
    $("#stage").innerHTML = html || '<div class="empty">세션을 고르면 네 에이전트가 여기 나타납니다.</div>';
  }

  // ---------------------------------------------------------------------------------------------------- render: timeline
  function renderTimeline(m) {
    const pts = m.timeline.filter((p) => p.kind === "start" || p.kind === "rend" || p.round === m.round);
    const html = pts.map((p) => {
      const cur = p.i <= S.at && (pts[pts.indexOf(p) + 1] ? pts[pts.indexOf(p) + 1].i > S.at : true);
      const dict = m.agents.map((a, k) => {
        const s = p.state[a] || {};
        return '<div class="dict"><i class="sw ' + SHAPES[k] + '" style="--c:var(--a' + k + ')"></i><span class="dk">' + esc(short(a)) + "</span> {'balance': " + fmt(s.balance) + ", 'record': " + s.record + ", 'status': '" + esc(s.status) + "'}</div>";
      }).join("");
      return '<button class="tp ' + p.kind + (cur ? " cur" : "") + '" data-at="' + p.i + '"><div class="dot"></div><div class="tl">' + esc(p.label) + "</div>" + dict + "</button>";
    }).join("");
    const el = $("#timeline");
    const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 20;
    el.innerHTML = html || '<div class="empty">아직 시점이 없습니다.</div>';
    if (S.follow || atEnd) el.scrollLeft = el.scrollWidth;
  }

  // ---------------------------------------------------------------------------------------------------- chart helpers
  function niceMax(v) { const p = Math.pow(10, Math.floor(Math.log10(v))); for (const s of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (s * p >= v * 1.05) return s * p; return 10 * p; }
  function marker(shape, cx, cy, color) {
    const s = 5, st = 'fill="' + color + '" stroke="var(--surface)" stroke-width="2"';
    if (shape === "square") return '<rect x="' + (cx - s) + '" y="' + (cy - s) + '" width="' + 2 * s + '" height="' + 2 * s + '" ' + st + "/>";
    if (shape === "triangle") return '<path d="M' + cx + " " + (cy - s - 1) + "L" + (cx + s + 1) + " " + (cy + s) + "L" + (cx - s - 1) + " " + (cy + s) + 'Z" ' + st + "/>";
    if (shape === "diamond") return '<path d="M' + cx + " " + (cy - s - 1) + "L" + (cx + s + 1) + " " + cy + "L" + cx + " " + (cy + s + 1) + "L" + (cx - s - 1) + " " + cy + 'Z" ' + st + "/>";
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + s + '" ' + st + "/>";
  }

  // ---------------------------------------------------------------------------------------------------- whole game: token flow
  /* One static figure of the whole game, built from every loaded event (it does not follow the replay bar). For each
     seat and each finished round (a `round` event): the balance before and at the end (round.end), and what changed
     it - tokens generated by call kind, the solver's refund, the charge taken, the charge waived by an EXIT, gifts
     out / in, an old EXIT refill, and any residual the ledger cannot name ("other"). Token moves are the done GIVEs
     (gift events: chat GIVEs and DECISION GIVEs, `decision: true`) and, for v9-v13 runs, the token legs of done
     exchanges. Pure, so the tests can check it against the events' own totals. */
  const GEN_KO = { open_chat: "공개 대화", vote: "투표", talk: "대화", solve: "SOLVE" };
  /* The round's inner steps, in the order the engine runs them: open board + VOTE ("open"), TALK before SOLVE ("pre":
     the rotation's prep TALK, or the old TALK -> EXCHANGES), SOLVE ("solve": the solver's thinking and its refund),
     TALK after RESULTS ("post": the rotation's rescue TALK, or v15's TALK after SOLVE), the charges ("charge"; the old
     settlement in the `round` row when there is no `charges` event) and EXITs ("exit", only in rounds with one). */
  const PH_ORDER = ["open", "pre", "solve", "post", "charge", "exit"];
  const PH_W = { exit: 0.6 }; // sub-column weights inside a round column (the rest 1)
  const flowPhase = () => ({ gen: {}, outs: [], ins: [], refund: 0, free: 0, charge: 0, waived: 0, refill: 0, dead: false, exit: false });
  function gameFlow(evs) {
    const F = { agents: [], starts: {}, start: 0, rounds: [], moves: [], open: null, live: null, phaseKeys: [], labels: {} };
    const byR = new Map();
    const R = (r) => {
      if (!byR.has(r)) byR.set(r, { r, started: false, startBal: null, end: null, rows: {}, rep: null, picks: null, bans: null, tried: null, solved: null, pending: {}, returned: {}, waived: {}, gen: {}, refill: {}, moves: [],
        ph: {}, post: false, hadResults: false, hadCharges: false, exits: {}, lastIdx: -1 });
      return byR.get(r);
    };
    // one seat's accumulator in one inner step; `at` = the step's last event (the replay bar can seek there)
    const ps = (r, key, i, a) => {
      const p = r.ph[key] || (r.ph[key] = { at: i, seats: {} });
      if (i > p.at) p.at = i;
      return a == null ? p : p.seats[a] || (p.seats[a] = flowPhase());
    };
    const talkKey = (r) => (r.post ? "post" : "pre");
    for (let i = 0; i < evs.length; i++) {
      const e = evs[i], k = e.event;
      if (e.round != null && byR.has(e.round)) byR.get(e.round).lastIdx = i;
      if (k === "session_start") {
        F.agents = (e.agents || []).slice(); F.start = e.start || 0;
        for (const a of F.agents) F.starts[a] = (e.starts || {})[a] != null ? e.starts[a] : e.start;
      } else if (k === "round_start") { const r = R(e.round); r.started = true; r.startBal = e.balances || null; r.taking = e.taking_part || null; r.lastIdx = i; }
      else if (k === "call_start") {
        const r = R(e.round);
        if (e.kind === "solve") { r.post = true; ps(r, "solve", i); } else if (e.kind === "open_chat" || e.kind === "vote") ps(r, "open", i);
      } else if (k === "call") {
        const r = R(e.round), g = (r.gen[e.agent] = r.gen[e.agent] || {});
        g[e.kind] = (g[e.kind] || 0) + (e.used || 0);
        if (e.kind === "solve") r.post = true;
        const tk = e.kind === "talk" && e.phase === "prep" ? "pre" : e.kind === "talk" && e.phase === "rescue" ? "post" : talkKey(r); // v22: the call says its TALK
        const s = ps(r, e.kind === "open_chat" || e.kind === "vote" ? "open" : e.kind === "solve" ? "solve" : tk, i, e.agent);
        if (e.kind === "talk" && (e.phase === "prep" || e.phase === "rescue") && e.parsed && e.parsed.exit && e.balance_after > 0) r.exits[e.agent] = i; // v22: no talk_intent; the EXIT is on the call
        s.gen[e.kind] = (s.gen[e.kind] || 0) + (e.used || 0);
        s.free += e.free_tokens || 0;
        if (e.balance_after != null && e.balance_after <= 0) s.dead = true;
      } else if (k === "vote") { const r = R(e.round); r.rep = e.rep || null; r.picks = e.picks || null; r.bans = e.bans || null; r.drawn = !!e.drawn; }
      else if (k === "results") {
        const r = R(e.round); r.tried = e.tried || []; r.solved = e.solved || []; r.pending = e.pending || {}; r.returned = e.returned || {};
        if (!r.rep && e.vote) r.rep = e.vote.rep || null;
        r.post = true; r.hadResults = true; ps(r, "solve", i);
        for (const [a, v] of Object.entries(e.returned || {})) ps(r, "solve", i, a).refund += v;
        for (const a of e.zero || []) ps(r, "solve", i, a).dead = true;
      } else if (k === "charges") {
        const r = R(e.round); r.waived = e.waived || {}; r.hadCharges = true; ps(r, "charge", i);
        for (const [a, v] of Object.entries(e.taken || {})) ps(r, "charge", i, a).charge += v;
        for (const [a, v] of Object.entries(e.waived || {})) ps(r, "charge", i, a).waived += v;
        for (const a of e.dead || []) ps(r, "charge", i, a).dead = true;
        for (const a of e.exits || []) r.exits[a] = i;
      } else if (k === "exit_refill") { const r = R(e.round); r.refill[e.agent] = e.amount || 0; const s = ps(r, "exit", i, e.agent); s.refill += e.amount || 0; s.exit = true; }
      else if (k === "talk_intent" && e.exit && !e.void) R(e.round).exits[e.agent] = i;
      else if (k === "gift" && e.kind === "give" && e.status === "done" && e.amount > 0) {
        const r = R(e.round), pk = e.phase === "prep" ? "pre" : e.phase === "rescue" ? "post" : talkKey(r);
        const x = { i, round: e.round, src: e.src, dst: e.dst, amount: e.amount, turn: e.turn, chat: e.chat_id || null, room: e.room || null, how: e.decision ? "decision" : "give", text: e.text || "",
          phase: e.phase === "prep" || e.phase === "rescue" ? e.phase : null, pk }; // phase: v16e rotation, the TALK it was given in
        r.moves.push(x);
        ps(r, pk, i, e.src).outs.push(x); ps(r, pk, i, e.dst).ins.push(x);
        if (e.balances && e.balances[e.src] != null && e.balances[e.src] <= 0) ps(r, pk, i, e.src).dead = true; // GIVE ALL
      } else if (k === "exchange" && e.status === "done") { // v9-v13: tokens in either leg of a done offer
        const r = R(e.round), pk = talkKey(r);
        for (const [s, d, v] of [[e.src, e.dst, e.i_give], [e.dst, e.src, e.you_give]])
          if (typeof v === "number" && v > 0) { const x = { i, round: e.round, src: s, dst: d, amount: v, turn: e.carried, chat: e.id, how: "offer", text: "", pk }; r.moves.push(x); ps(r, pk, i, s).outs.push(x); ps(r, pk, i, d).ins.push(x); }
      } else if (k === "round") {
        const r = R(e.round); r.end = e.end || {}; r.rows = e.agents || {}; r.endIdx = i;
        for (const [a, row] of Object.entries(r.rows)) { // runs without results / charges events settle in the round row
          if (!r.hadResults && row.returned) ps(r, "solve", i, a).refund += row.returned;
          if (!r.hadCharges && row.charged) ps(r, "charge", i, a).charge += row.charged;
          if (row.exit && r.exits[a] == null) r.exits[a] = i;
          if (row.status === "dead" && !PH_ORDER.some((pk) => r.ph[pk] && r.ph[pk].seats[a] && r.ph[pk].seats[a].dead)) ps(r, r.hadCharges || row.charged ? "charge" : talkKey(r), i, a).dead = true;
        }
        if (!r.hadCharges) ps(r, "charge", i);
      }
    }
    const all = [...byR.values()].sort((p, q) => p.r - q.r);
    const has = (pk) => all.some((r) => r.ph[pk]);
    F.phaseKeys = PH_ORDER.filter((pk) => pk === "solve" || pk === "charge" || (pk !== "exit" && has(pk)));
    const rot = all.some((r) => r.drawn), two = F.phaseKeys.includes("pre") && F.phaseKeys.includes("post");
    F.labels = { open: ["공개", all.some((r) => r.rep && !r.drawn) ? "투표" : ""], pre: ["TALK", rot || two ? "전" : ""], solve: ["SOLVE", ""], post: ["TALK", rot || two ? "후" : ""],
      charge: [all.some((r) => r.hadCharges) ? "벌금" : "정산", ""], exit: ["EXIT", ""] };
    // the inner steps of one round for every seat: start -> end per step; what the ledger cannot name ends up in the
    // last step as "other" so the steps always land on round.end
    const steps = (r, before, end) => {
      for (const a of Object.keys(r.exits)) ps(r, "exit", r.exits[a], a).exit = true;
      const keys = F.phaseKeys.concat(r.ph.exit ? ["exit"] : []);
      const out = {};
      for (const a of F.agents) {
        let lv = before[a];
        out[a] = keys.map((pk) => {
          const p = (r.ph[pk] && r.ph[pk].seats[a]) || flowPhase();
          const gen = Object.values(p.gen).reduce((t, v) => t + v, 0), o = p.outs.reduce((t, x) => t + x.amount, 0), n = p.ins.reduce((t, x) => t + x.amount, 0);
          const st = { k: pk, start: lv, end: lv - gen + p.free - o + n + p.refund - p.charge + p.refill, gen, byKind: p.gen, out: o, inn: n, outs: p.outs, ins: p.ins,
            refund: p.refund, free: p.free, charge: p.charge, waived: p.waived, refill: p.refill, dead: p.dead, exit: p.exit, other: 0,
            solver: pk === "solve" && (r.tried || []).includes(a) ? ((r.solved || []).includes(a) ? "✓" : "✗") : null };
          lv = st.end;
          return st;
        });
        const last = out[a][out[a].length - 1];
        if (end && end[a] != null && end[a] !== lv) { last.other = end[a] - lv; last.end = end[a]; }
      }
      return { keys, at: keys.map((pk) => (r.ph[pk] ? r.ph[pk].at : -1)), steps: out };
    };
    let prev = Object.assign({}, F.starts);
    const last = {};
    for (const r of all) {
      if (!r.end) {
        if (r.started) { // the round being played: drawn up to the last event read, not part of the totals
          F.open = r.r;
          const before = {};
          for (const a of F.agents) before[a] = r.startBal && r.startBal[a] != null ? r.startBal[a] : prev[a];
          const P = steps(r, before, null);
          F.live = { r: r.r, rep: r.rep, drawn: !!r.drawn, tried: r.tried || [], solved: r.solved || [], moves: r.moves, before, phases: P.keys, at: P.at, steps: P.steps,
            playing: Object.fromEntries(F.agents.map((a) => [a, r.taking ? r.taking.includes(a) : true])), lastIdx: r.lastIdx };
        }
        continue;
      }
      const seats = {};
      const sum = (xs) => xs.reduce((s, x) => s + x.amount, 0);
      for (const a of F.agents) {
        const row = r.rows[a] || null;
        const before = row && row.balance_before != null ? row.balance_before : r.startBal && r.startBal[a] != null ? r.startBal[a] : prev[a];
        const end = r.end[a] != null ? r.end[a] : before;
        const byKind = r.gen[a] || {};
        const gen = row && row.generated != null ? row.generated : Object.values(byKind).reduce((s, v) => s + v, 0);
        const outs = r.moves.filter((x) => x.src === a), ins = r.moves.filter((x) => x.dst === a);
        const out = sum(outs), inn = sum(ins);
        const refund = row ? row.returned || 0 : 0, charged = row ? row.charged || 0 : 0;
        const refill = r.refill[a] != null ? r.refill[a] : row && row.exit_refill != null ? row.exit_refill : 0;
        const waived = r.waived[a] || 0;
        if (row && row.status) last[a] = row.status;
        seats[a] = {
          before, end, playing: !!row, status: row ? row.status || "in" : last[a] || "in", exit: !!(row && row.exit), exitReason: row ? row.exit_reason || null : null,
          gen, byKind, refund, charged, waived, out, inn, outs, ins, refill, other: end - (before - gen + refund - charged - out + inn + refill),
          solved: !!(row && row.solved), rep: !!(row && row.representative), tried: !!(row && row.solve_call),
        };
      }
      const tried = r.tried || F.agents.filter((a) => seats[a].tried), solved = r.solved || F.agents.filter((a) => seats[a].solved);
      if (!r.tried) r.tried = tried;
      if (!r.solved) r.solved = solved;
      const P = steps(r, Object.fromEntries(F.agents.map((a) => [a, seats[a].before])), Object.fromEntries(F.agents.map((a) => [a, seats[a].end])));
      for (const a of F.agents) seats[a].steps = P.steps[a];
      F.rounds.push({ r: r.r, rep: r.rep, drawn: !!r.drawn, picks: r.picks, bans: r.bans, tried, solved, pending: r.pending, returned: r.returned, moves: r.moves, seats, end: r.end, phases: P.keys, at: P.at, endIdx: r.endIdx });
      F.moves.push(...r.moves);
      prev = Object.assign({}, prev, r.end);
    }
    return F;
  }

  const kfmt = (v) => { const a = Math.abs(v); return a >= 1000 ? (v / 1000).toFixed(a >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k" : String(v); };
  const ksgn = (v) => (v > 0 ? "+" + kfmt(v) : v < 0 ? "−" + kfmt(-v) : "±0");

  function flowCellTip(F, R, a) {
    const s = R.seats[a], k = F.agents.indexOf(a);
    const st = !s.playing ? (s.status === "dead" ? "이미 꺼짐 ✕" : s.status === "exited" ? "이미 퇴장 🚪" : "이번 라운드 없음") : STATUS_KO[s.status] || s.status;
    const L = ["<b>R" + R.r + " · " + esc(a) + "</b> <span class=\"dim\">" + esc(st) + "</span>",
      "시작 " + fmt(s.before) + " → 끝 <b>" + fmt(s.end) + "</b> (" + sgn(s.end - s.before) + ")"];
    if (s.gen) L.push('<i class="sw2 f-gen"></i>생성 −' + fmt(s.gen) + ' <span class="dim">' + Object.entries(s.byKind).filter(([, v]) => v).map(([kk, v]) => esc(GEN_KO[kk] || kk) + " " + fmt(v)).join(" · ") + "</span>");
    if (s.out) L.push('<i class="sw2 f-out"></i>보냄 −' + fmt(s.out) + ' <span class="dim">' + s.outs.map((x) => "→ " + esc(short(x.dst)) + " " + fmt(x.amount) + (x.how === "decision" ? " (결정)" : "")).join(" · ") + "</span>");
    if (s.charged) L.push('<i class="sw2 f-chg"></i>벌금 −' + fmt(s.charged));
    if (s.waived) L.push('<i class="sw2 f-wav"></i>EXIT로 면제된 벌금 ' + fmt(s.waived));
    if (s.refund) L.push('<i class="sw2 f-ref"></i>환급 +' + fmt(s.refund) + (s.rep ? " (대표로 풂)" : ""));
    if (s.inn) L.push('<i class="sw2 f-in"></i>받음 +' + fmt(s.inn) + ' <span class="dim">' + s.ins.map((x) => "← " + esc(short(x.src)) + " " + fmt(x.amount) + (x.how === "decision" ? " (결정)" : "")).join(" · ") + "</span>");
    if (s.refill) L.push('<i class="sw2 f-fill"></i>EXIT 리필 ' + sgn(s.refill));
    if (s.other) L.push('<i class="sw2 f-oth"></i>기타 ' + sgn(s.other) + ' <span class="dim">(장부로 설명 안 됨)</span>');
    if (s.playing && s.status === "dead") L.push('<span class="bad">✕ 0이 되어 꺼짐</span>');
    if (s.exit) L.push("🚪 EXIT · " + fmt(s.end) + " 토큰을 갖고 떠남" + (s.exitReason ? '<div class="dim">“' + esc(clip(s.exitReason, 140)) + "”</div>" : ""));
    return '<div class="ftip" style="--c:var(--a' + k + ')">' + L.join("<br>") + "</div>";
  }
  function flowRoundTip(R) {
    const L = ["<b>R" + R.r + "</b>"];
    if (R.rep && R.drawn) { // v16e rotation
      L.push("solver " + esc(R.rep) + " (시스템이 정함) · " + (R.solved.includes(R.rep) ? "✓ 풂" + (R.returned[R.rep] ? " · 환급 +" + fmt(R.returned[R.rep]) : "") : "✗ 못 풂"));
    } else if (R.rep) {
      L.push("대표 " + esc(R.rep) + (R.picks ? " (PICK " + ((R.picks || {})[R.rep] || 0) + " · BAN " + (((R.bans || {})[R.rep]) || 0) + ")" : "") + " · " + (R.solved.includes(R.rep) ? "✓ 풂" + (R.returned[R.rep] ? " · 환급 +" + fmt(R.returned[R.rep]) : "") : "✗ 못 풂"));
    } else L.push("SOLVE " + R.tried.length + "명 · 풂 " + R.solved.length + "명" + (R.solved.length ? " (" + R.solved.map(short).join(", ") + ")" : ""));
    const due = Object.entries(R.pending || {});
    if (due.length) L.push("벌금 대상 " + due.map(([a, v]) => esc(short(a)) + " " + fmt(v)).join(" · "));
    const tot = R.moves.reduce((s, x) => s + x.amount, 0);
    L.push("이동 " + R.moves.length + "건 · " + fmt(tot) + " 토큰");
    const pre = R.moves.filter((x) => x.phase === "prep");
    if (R.moves.some((x) => x.phase)) L.push("SOLVE 전 TALK " + pre.length + "건 " + fmt(pre.reduce((t, x) => t + x.amount, 0)) + " · 결과 뒤 TALK " + (R.moves.length - pre.length) + "건 " + fmt(tot - pre.reduce((t, x) => t + x.amount, 0)));
    return L.join("<br>");
  }
  function flowMoveTip(x) {
    return "<b>R" + x.round + " · " + (x.phase ? PHASE_KO[x.phase] + " TALK · " : "") + (x.how === "decision" ? "결정 GIVE (ASK에 답함)" : x.how === "offer" ? "제안 " + esc(x.chat) + " 체결" : x.room ? "GIVE" : "대화 GIVE") + "</b>" +
      (x.room ? ' <span class="dim">방 ' + esc(x.room) + (x.turn != null ? " · T" + x.turn : "") + "</span>" : x.chat && x.how !== "offer" ? ' <span class="dim">대화 ' + esc(x.chat) + (x.turn != null ? " · 턴 " + x.turn : "") + "</span>" : "") +
      "<br>" + esc(x.src) + " → " + esc(x.dst) + " · <b>" + fmt(x.amount) + "</b> 토큰" + (x.text ? '<div class="dim">“' + esc(clip(x.text, 140)) + "”</div>" : "");
  }

  const PH_SHORT = { open: "공", pre: "전", solve: "S", post: "후", charge: "벌", exit: "E" };
  function phName(F, pk) {
    const rot = F.rounds.some((R) => R.drawn) || (F.live && F.live.drawn), two = F.phaseKeys.includes("pre") && F.phaseKeys.includes("post");
    return { open: F.labels.open[1] ? "공개 대화 · 투표" : "공개 대화", pre: rot || two ? "SOLVE 전 TALK" : "TALK", solve: "SOLVE", post: rot || two ? "결과 뒤 TALK" : "TALK", charge: F.labels.charge[0], exit: "EXIT" }[pk] || pk;
  }
  function flowStepTip(F, C, a, q) {
    const st = C.steps[a][q], k = F.agents.indexOf(a);
    const L = ["<b>R" + C.r + " · " + esc(phName(F, st.k)) + " · " + esc(a) + "</b>" + (C.live ? ' <span class="dim">진행 중</span>' : ""),
      "시작 " + fmt(st.start) + " → 끝 <b>" + fmt(st.end) + "</b> (" + sgn(st.end - st.start) + ")"];
    if (st.gen) L.push('<i class="sw2 f-gen"></i>생성 −' + fmt(st.gen) + ' <span class="dim">' + Object.entries(st.byKind).filter(([, v]) => v).map(([kk, v]) => esc(GEN_KO[kk] || kk) + " " + fmt(v)).join(" · ") + "</span>");
    if (st.free) L.push('<i class="sw2 f-ref"></i>REJECT만 쓴 응답 환급 +' + fmt(st.free));
    if (st.out) L.push('<i class="sw2 f-out"></i>보냄 −' + fmt(st.out) + ' <span class="dim">' + st.outs.map((x) => "→ " + esc(short(x.dst)) + " " + fmt(x.amount) + (x.how === "decision" ? " (결정)" : "")).join(" · ") + "</span>");
    if (st.inn) L.push('<i class="sw2 f-in"></i>받음 +' + fmt(st.inn) + ' <span class="dim">' + st.ins.map((x) => "← " + esc(short(x.src)) + " " + fmt(x.amount) + (x.how === "decision" ? " (결정)" : "")).join(" · ") + "</span>");
    if (st.solver) L.push(st.solver === "✓" ? '<span class="okc">✓ 풂</span>' : '<span class="bad">✗ 못 풂</span>');
    if (st.refund) L.push('<i class="sw2 f-ref"></i>환급 +' + fmt(st.refund));
    if (st.charge) L.push('<i class="sw2 f-chg"></i>' + esc(F.labels.charge[0]) + " −" + fmt(st.charge));
    if (st.waived) L.push('<i class="sw2 f-wav"></i>EXIT로 면제된 벌금 ' + fmt(st.waived));
    if (st.refill) L.push('<i class="sw2 f-fill"></i>EXIT 리필 ' + sgn(st.refill));
    if (st.other) L.push('<i class="sw2 f-oth"></i>기타 ' + sgn(st.other) + ' <span class="dim">(장부로 설명 안 됨)</span>');
    if (st.dead) L.push('<span class="bad">✕ 0이 되어 꺼짐</span>');
    if (st.exit) L.push("🚪 EXIT" + (C.seats && C.seats[a] && C.seats[a].exitReason ? '<div class="dim">“' + esc(clip(C.seats[a].exitReason, 140)) + "”</div>" : ""));
    if (L.length === 2) L.push('<span class="dim">이 단계에 바뀐 것 없음</span>');
    if (C.at[q] >= 0) L.push('<span class="dim">더블클릭: 재생 막대를 이 단계 끝으로</span>');
    return '<div class="ftip" style="--c:var(--a' + k + ')">' + L.join("<br>") + "</div>";
  }
  function flowPhaseTip(F, C, q) {
    const pk = C.phases[q];
    const rows = F.agents.filter((a) => C.playing[a]).map((a, k) => {
      const st = C.steps[a][q];
      return '<div><i class="sw ' + SHAPES[F.agents.indexOf(a)] + '" style="--c:var(--a' + F.agents.indexOf(a) + ')"></i>' + esc(short(a)) + " " + fmt(st.start) + " → <b>" + fmt(st.end) + "</b> " + (st.end !== st.start ? sgn(st.end - st.start) : '<span class="dim">±0</span>') + (st.solver || "") + (st.dead ? " ✕" : "") + (st.exit ? " 🚪" : "") + "</div>";
    });
    return "<b>R" + C.r + " · " + esc(phName(F, pk)) + "</b>" + rows.join("") + (C.at[q] >= 0 ? '<div class="dim">더블클릭: 재생 막대를 이 단계 끝으로</div>' : "");
  }

  /* One static figure of the whole game (it does not follow the replay bar). Top: one balance chart in which every
     round column is split into its inner steps (sub-columns, light shading per step, two-line labels); each seat is a
     staircase that changes level inside the step that changed it, so a gift in, the solver's thinking, a refund or a
     charge show where they happen; a round's last step lands on round.end. The round being played is drawn after the
     finished ones up to the last event read. Middle: the token moves (GIVEs), each inside its step's sub-column. Bottom:
     the round breakdown (out / in per seat and round). */
  function renderFlow() {
    const box = $("#flow");
    if (!box) return;
    const width = box.clientWidth || 700;
    const key = S.session + "|" + S.events.length + "|" + width;
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    const F = gameFlow(S.events), A = F.agents, n = F.rounds.length;
    const cols = F.rounds.map((R) => ({ r: R.r, R, live: false, phases: R.phases, at: R.at, steps: Object.fromEntries(A.map((a) => [a, R.seats[a].steps])), playing: Object.fromEntries(A.map((a) => [a, R.seats[a].playing])), seats: R.seats }));
    if (F.live) {
      const L = F.live;
      cols.push({ r: L.r, R: { r: L.r, rep: L.rep, drawn: L.drawn, tried: L.tried, solved: L.solved, moves: L.moves, returned: {}, pending: {}, picks: null, bans: null }, live: true, phases: L.phases, at: L.at, steps: L.steps, playing: L.playing, seats: null });
    }
    const nc = cols.length;
    if (!A.length || !nc) { box.innerHTML = '<div class="empty">' + (A.length ? "시작된 라운드가 아직 없습니다." : "세션을 고르면 게임 전체의 토큰 흐름이 여기 그려집니다.") + "</div>"; return; }
    const tips = [];
    const T = (html, at) => ' data-t="' + (tips.push(html) - 1) + '"' + (at != null && at >= 0 ? ' data-at="' + at + '"' : "");
    const ki = (a) => A.indexOf(a);
    const col = (a) => "var(--a" + ki(a) + ")";
    const Lm = 64, Rm = 92;
    const cw = Math.max(92, Math.min(200, Math.floor((width - Lm - Rm) / nc)));
    const W = Lm + nc * cw + Rm;
    const xB = (j) => Lm + j * cw, xC = (j) => Lm + (j + 0.5) * cw;
    const subs = cols.map((C, j) => {
      const tot = C.phases.reduce((t, k) => t + (PH_W[k] || 1), 0);
      let x = xB(j);
      return C.phases.map((k) => { const w = (cw * (PH_W[k] || 1)) / tot, o = { k, x0: x, x1: x + w, w }; x += w; return o; });
    });
    const xStep = (s, k) => s.x0 + s.w * (0.3 + 0.13 * k); // each seat changes level at its own spot in the step
    const hdrH = 54, lnT = hdrH + 10, lnH = 230, lnB = lnT + lnH;
    const laneH = 18, fT = lnB + 38, fB = fT + A.length * laneH;
    const rowH = 30, gT = fB + 26, gB = gT + A.length * rowH, H = gB + 4;
    const laneY = (a) => fT + (ki(a) + 0.5) * laneH;
    let top = 1;
    for (const a of A) top = Math.max(top, F.starts[a] || 0);
    for (const C of cols) for (const a of A) for (const st of C.steps[a]) top = Math.max(top, st.start, st.end);
    const ymax = niceMax(top);
    const y = (v) => lnT + (1 - Math.max(0, v) / ymax) * lnH;
    let svg = '<svg class="fsvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="게임 전체 토큰 흐름: 라운드 안 단계별 잔액">';
    // round columns (alternate shading), the steps' shading and labels, the round headers: round, solver, solved?
    cols.forEach((C, j) => {
      if (j % 2 === 0) svg += '<rect class="colbg" x="' + xB(j) + '" y="0" width="' + cw + '" height="' + H + '"/>';
      subs[j].forEach((s, q) => {
        svg += '<rect class="fph k-' + s.k + (C.live ? " live" : "") + '" x="' + s.x0.toFixed(1) + '" y="' + (hdrH - 18) + '" width="' + s.w.toFixed(1) + '" height="' + (fB - hdrH + 18) + '"/>';
        if (q) svg += '<line class="fphl" x1="' + s.x0.toFixed(1) + '" x2="' + s.x0.toFixed(1) + '" y1="' + (hdrH - 18) + '" y2="' + fB + '"/>';
        const lab = s.w >= 27 ? F.labels[s.k] || [s.k, ""] : [PH_SHORT[s.k] || s.k, ""], cx = ((s.x0 + s.x1) / 2).toFixed(1);
        svg += "<g" + T(flowPhaseTip(F, C, q), C.at[q]) + ' class="fhit"><rect class="hitbox" x="' + s.x0.toFixed(1) + '" y="' + (hdrH - 18) + '" width="' + s.w.toFixed(1) + '" height="20"/>' +
          '<text class="phl" x="' + cx + '" y="' + (hdrH - 8) + '" text-anchor="middle">' + esc(lab[0]) + "</text>" + (lab[1] ? '<text class="phl" x="' + cx + '" y="' + (hdrH + 1) + '" text-anchor="middle">' + esc(lab[1]) + "</text>" : "") + "</g>";
      });
      const R = C.R, ok = R.rep ? R.solved.includes(R.rep) : R.solved.length > 0;
      const done = !C.live || (R.tried || []).length > 0; // the round being played: no mark before its RESULTS
      const head = R.rep ? "👑" + short(R.rep) + (done ? (ok ? " ✓" : " ✗") : "") : done ? "✓ " + R.solved.length + "/" + (R.tried || []).length : "";
      const mark = /[✓✗]$/.test(head) ? head.slice(-1) : "";
      svg += "<g" + T(flowRoundTip(R) + (C.live ? '<br><span class="dim">진행 중 · 마지막으로 읽은 이벤트까지</span>' : "")) + ' class="fhit"><rect class="hitbox" x="' + xB(j) + '" y="0" width="' + cw + '" height="' + (hdrH - 20) + '"/>' +
        '<text class="rh" x="' + xC(j) + '" y="13" text-anchor="middle">R' + C.r + (C.live ? " ⏳ 진행 중" : "") + "</text>" +
        '<text class="rs" x="' + xC(j) + '" y="28" text-anchor="middle"' + (R.rep ? ' style="fill:' + col(R.rep) + '"' : "") + ">" + esc(mark ? head.slice(0, -1) : head) + (mark ? '<tspan class="' + (ok ? "ok" : "bad") + '">' + mark + "</tspan>" : "") + "</text></g>";
    });
    // the balance chart: grid, round boundaries, then one staircase per seat through every round's steps
    for (let t = 0; t <= 4; t++) {
      const v = (ymax * t) / 4;
      svg += '<line class="grid" x1="' + Lm + '" x2="' + xB(nc) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (Lm - 6) + '" y="' + (y(v) + 3.5) + '" text-anchor="end">' + axisNum(v) + "</text>";
    }
    svg += '<line class="zeroline" x1="' + Lm + '" x2="' + xB(nc) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
    for (let j = 0; j <= nc; j++) {
      svg += '<line class="rb" x1="' + xB(j) + '" x2="' + xB(j) + '" y1="' + (hdrH - 18) + '" y2="' + gB + '"/>';
      if (j <= n) svg += '<text class="ax" x="' + xB(j) + '" y="' + (lnB + 12) + '" text-anchor="middle">' + (j === 0 ? "시작" : cols[j - 1].r) + "</text>";
    }
    const ends = [], marks = [], hits = [];
    A.forEach((a, k) => {
      const c = "var(--a" + k + ")";
      let d = "", dGone = "", dLive = "", pen = false;
      cols.forEach((C, j) => {
        const st = C.steps[a];
        if (!C.playing[a]) {
          pen = false;
          const s = C.seats && C.seats[a];
          if (!C.live && s && s.status !== "dead") dGone += "M" + xB(j) + " " + y(s.before).toFixed(1) + "H" + xB(j + 1);
          return;
        }
        let p = (pen ? "L" : "M") + xB(j) + " " + y(st[0].start).toFixed(1);
        const upto = C.live ? Math.max(0, ...C.at.map((v, q) => (v >= 0 ? q : 0))) : st.length - 1; // the round being played: steps reached so far
        subs[j].forEach((s, q) => {
          if (q > upto) return;
          const t = st[q], xs = xStep(s, k);
          p += "H" + xs.toFixed(1) + "V" + y(t.end).toFixed(1) + "H" + s.x1.toFixed(1);
          hits.push("<g" + T(flowStepTip(F, C, a, q), C.at[q]) + ' class="fhit"><line class="hitbox hl" x1="' + s.x0.toFixed(1) + '" x2="' + s.x1.toFixed(1) + '" y1="' + y(t.end).toFixed(1) + '" y2="' + y(t.end).toFixed(1) + '" stroke-width="9"/></g>');
          if (t.solver) marks.push({ key: j + ":" + q, px: xs + 8, py: y(t.end), cls: "fx " + (t.solver === "✓" ? "ok" : "dead"), g: t.solver });
          if (t.dead) marks.push({ key: j + ":" + q, px: xs, py: y(t.end), cls: "fx dead", g: "✕" });
          if (t.exit) marks.push({ key: j + ":" + q, px: (s.x0 + s.x1) / 2, py: y(t.end), cls: "fx", g: t.refill ? "↻" : "🚪" });
        });
        if (C.live) dLive += p.replace(/^L/, "M"); else d += p;
        pen = !C.live;
        if (!C.live) {
          const px = xB(j + 1), py = y(C.seats[a].end);
          hits.push("<g" + T(flowCellTip(F, C.R, a)) + ' class="fhit"><circle class="hitbox" cx="' + px + '" cy="' + py + '" r="7"/><circle class="pt" cx="' + px + '" cy="' + py + '" r="3" style="fill:' + c + '"/></g>');
        }
      });
      if (dGone) svg += '<path class="ln gone" d="' + dGone + '" style="stroke:' + c + '"/>';
      svg += '<path class="ln" d="' + d + '" style="stroke:' + c + '"/>';
      if (dLive) svg += '<path class="ln live" d="' + dLive + '" style="stroke:' + c + '"/>';
      svg += "<g" + T("<b>" + esc(a) + "</b> 시작 잔액 " + fmt(F.starts[a])) + ' class="fhit"><circle class="hitbox" cx="' + xB(0) + '" cy="' + y(F.starts[a]) + '" r="7"/>' + marker(SHAPES[k], xB(0), y(F.starts[a]), c) + "</g>";
      const C = cols[nc - 1], st = C.steps[a];
      const fin = C.live ? { end: st[st.length - 1].end, st: C.playing[a] ? "in" : "gone" } : { end: C.seats[a].end, st: C.seats[a].status };
      ends.push({ k, a, yy: y(fin.end), v: fin.end, st: fin.st });
    });
    svg += hits.join("");
    // event marks next to their step; marks that would touch step left (up to three times), then up
    const placed = [];
    const hit = (x, y) => placed.some((o) => Math.abs(o.x - x) < 10 && Math.abs(o.py - y) < 11);
    for (const mk of marks.sort((p, q) => (p.key > q.key ? 1 : p.key < q.key ? -1 : p.py - q.py))) {
      let px = mk.px, py = mk.py - 4;
      for (let t = 0; t < 3 && hit(px, py); t++) px -= 10;
      while (hit(px, py)) py -= 11;
      placed.push({ x: px, py });
      svg += '<text class="' + mk.cls + '" x="' + px.toFixed(1) + '" y="' + py.toFixed(1) + '" text-anchor="middle">' + mk.g + "</text>";
    }
    ends.sort((p, q) => p.yy - q.yy);
    for (let j = 1; j < ends.length; j++) if (ends[j].yy - ends[j - 1].yy < 13) ends[j].yy = ends[j - 1].yy + 13;
    for (const e of ends) svg += '<text class="endlab" x="' + (xB(nc) + 8) + '" y="' + (e.yy + 4) + '" style="fill:var(--a' + e.k + ')">' + esc(short(e.a)) + ' <tspan class="ev">' + (e.st === "dead" ? "✕ " : e.st === "exited" ? "🚪 " : "") + fmt(e.v) + "</tspan></text>";
    // seat lanes for the moves and the ledger: labels in the left margin
    svg += '<text class="sec" x="4" y="' + (fT - 9) + '">토큰 이동 · 점 = 주는 쪽, 화살촉 = 받는 쪽, 굵기 = 양 · 단계 칸 안에</text>';
    svg += '<text class="sec" x="4" y="' + (gT - 9) + '">라운드 내역 · 왼쪽 = 나간 토큰, 오른쪽 = 들어온 토큰, 숫자 = 순변화</text>';
    A.forEach((a, k) => {
      const c = "var(--a" + k + ")";
      svg += marker(SHAPES[k], 12, laneY(a), c) + '<text class="lab" x="24" y="' + (laneY(a) + 4) + '">' + esc(short(a)) + "</text>";
      const gy = gT + k * rowH + rowH / 2;
      svg += marker(SHAPES[k], 12, gy - 2, c) + '<text class="lab" x="24" y="' + (gy + 2) + '">' + esc(short(a)) + "</text>";
      cols.forEach((C, j) => { if (C.playing[a]) svg += '<line class="lane" x1="' + (xB(j) + 2) + '" x2="' + (xB(j + 1) - 2) + '" y1="' + laneY(a) + '" y2="' + laneY(a) + '" style="stroke:' + c + '"/>'; });
    });
    // moves: one vertical arrow per GIVE inside its step's sub-column, giver lane -> receiver lane, in event order
    const allMoves = F.moves.concat(F.live ? F.live.moves : []);
    const maxAmt = Math.max(1, ...allMoves.map((x) => x.amount));
    cols.forEach((C, j) => {
      const mv = C.R.moves.slice().sort((p, q) => p.i - q.i);
      const bySub = new Map();
      for (const x of mv) { const s = subs[j].find((u) => u.k === x.pk) || subs[j][0]; if (!bySub.has(s)) bySub.set(s, []); bySub.get(s).push(x); }
      for (const [s, xs] of bySub) xs.forEach((x, q) => {
        const gap = s.w / (xs.length + 1), px = s.x0 + gap * (q + 1), y0 = laneY(x.src), y1 = laneY(x.dst), dir = y1 > y0 ? 1 : -1;
        const w = 1.3 + 4.5 * (x.amount / maxAmt), hd = 4 + w;
        const c = col(x.src);
        let g = "<g" + T(flowMoveTip(x), x.i) + ' class="fhit mv">';
        g += '<line class="hitbox" x1="' + px + '" x2="' + px + '" y1="' + y0 + '" y2="' + y1 + '" stroke-width="12"/>';
        g += '<line class="mvl' + (x.how === "decision" ? " dec" : x.how === "offer" ? " off" : "") + (x.phase ? " " + x.phase : "") + '" x1="' + px + '" x2="' + px + '" y1="' + y0 + '" y2="' + (y1 - dir * hd) + '" style="stroke:' + c + ";stroke-width:" + w.toFixed(1) + '"/>';
        g += x.phase === "prep" ? '<circle class="dot-prep" cx="' + px + '" cy="' + y0 + '" r="' + (w / 2 + 2).toFixed(1) + '" style="stroke:' + c + '"/>'
          : '<circle cx="' + px + '" cy="' + y0 + '" r="' + (w / 2 + 1.6).toFixed(1) + '" style="fill:' + c + '"/>';
        g += '<path d="M' + (px - hd * 0.7) + " " + (y1 - dir * hd) + "L" + (px + hd * 0.7) + " " + (y1 - dir * hd) + "L" + px + " " + y1 + 'Z" style="fill:' + c + '"/>';
        if (gap >= 24) g += '<text class="amt" x="' + (px + w / 2 + 2.5) + '" y="' + ((y0 + y1) / 2 + 3) + '">' + kfmt(x.amount) + "</text>";
        svg += g + "</g>";
      });
    });
    // ledger: per seat and round, a diverging bar (out to the left, in to the right) and the net change
    const parts = (s) => ({ lo: [["f-gen", s.gen], ["f-out", s.out], ["f-chg", s.charged], ["f-oth", Math.max(0, -s.other)]], hi: [["f-ref", s.refund], ["f-in", s.inn], ["f-fill", s.refill], ["f-oth", Math.max(0, s.other)]] });
    let side = 1;
    for (const R of F.rounds) for (const a of A) {
      const s = R.seats[a], p = parts(s);
      side = Math.max(side, p.lo.reduce((t, v) => t + v[1], 0) + s.waived, p.hi.reduce((t, v) => t + v[1], 0));
    }
    const half = cw / 2 - 5, sc = half / side;
    cols.forEach((C, j) => A.forEach((a, k) => {
      const cx = xC(j), top = gT + k * rowH, by = top + 4;
      if (C.live) { if (k === 0) svg += '<text class="net dim" x="' + cx + '" y="' + (gT + (A.length * rowH) / 2 + 4) + '" text-anchor="middle">진행 중</text>'; return; }
      const R = C.R, s = R.seats[a];
      let g = "<g" + T(flowCellTip(F, R, a)) + ' class="fhit"><rect class="hitbox" x="' + (xB(j) + 1) + '" y="' + top + '" width="' + (cw - 2) + '" height="' + rowH + '"/>';
      if (!s.playing) {
        g += '<text class="net dim" x="' + cx + '" y="' + (top + 18) + '" text-anchor="middle">' + (s.status === "dead" ? "✕" : s.status === "exited" ? "🚪 " + kfmt(s.end) : "·") + "</text>";
        svg += g + "</g>"; return;
      }
      g += '<line class="mid" x1="' + cx + '" x2="' + cx + '" y1="' + (by - 2) + '" y2="' + (by + 11) + '"/>';
      const p = parts(s);
      let x0 = cx;
      for (const [cls, v] of p.lo) if (v > 0) { const w = Math.max(1, v * sc); x0 -= w; g += '<rect class="' + cls + '" x="' + x0.toFixed(1) + '" y="' + by + '" width="' + w.toFixed(1) + '" height="9"/>'; }
      if (s.waived) { const w = Math.max(1, s.waived * sc); x0 -= w; g += '<rect class="f-wav" x="' + x0.toFixed(1) + '" y="' + (by + 0.5) + '" width="' + w.toFixed(1) + '" height="8"/>'; }
      x0 = cx;
      for (const [cls, v] of p.hi) if (v > 0) { const w = Math.max(1, v * sc); g += '<rect class="' + cls + '" x="' + x0.toFixed(1) + '" y="' + by + '" width="' + w.toFixed(1) + '" height="9"/>'; x0 += w; }
      const net = s.end - s.before;
      g += '<text class="net' + (net > 0 ? " pos" : "") + '" x="' + cx + '" y="' + (top + 25) + '" text-anchor="middle">' + ksgn(net) + (s.status === "dead" ? " ✕" : s.exit ? " 🚪" : "") + "</text>";
      svg += g + "</g>";
    }));
    svg += "</svg>";
    const total = F.moves.reduce((t, x) => t + x.amount, 0), dec = F.moves.filter((x) => x.how === "decision").length;
    const sw = (cls, label) => '<span><i class="sw2 ' + cls + '"></i>' + label + "</span>";
    const phs = (pk) => '<span><i class="sw2 fphs k-' + pk + '"></i>' + esc(F.labels[pk].filter(Boolean).join("·")) + (pk === "pre" && F.labels.pre[1] ? " = " + esc(phName(F, pk)) + " (빈 점)" : pk === "post" && F.labels.post[1] ? " = " + esc(phName(F, pk)) : pk === "solve" ? " = solver의 생각 · 환급" : "") + "</span>";
    const leg = '<div class="flowleg">' +
      A.map((a, k) => '<span><i class="sw ' + SHAPES[k] + '" style="--c:var(--a' + k + ')"></i>' + esc(a) + "</span>").join("") +
      '<span class="dim">계단 = 그 단계에서 잔액이 바뀐 곳 · 라운드 칸 = 단계 칸</span>' +
      F.phaseKeys.map(phs).join("") + (cols.some((C) => C.phases.includes("exit")) ? phs("exit") : "") +
      '<span><svg width="26" height="8"><line x1="1" x2="25" y1="4" y2="4" class="mvl" style="stroke:var(--ink-2);stroke-width:2"/></svg>대화 GIVE</span>' +
      '<span><svg width="26" height="8"><line x1="1" x2="25" y1="4" y2="4" class="mvl dec" style="stroke:var(--ink-2);stroke-width:2"/></svg>결정 GIVE</span>' +
      sw("f-gen", "생성") + sw("f-out", "보냄") + sw("f-chg", "벌금") + sw("f-wav", "EXIT로 면제된 벌금") + sw("f-ref", "환급") + sw("f-in", "받음") +
      (F.rounds.some((R) => A.some((a) => R.seats[a].refill)) ? sw("f-fill", "EXIT 리필") : "") + (F.rounds.some((R) => A.some((a) => R.seats[a].other)) ? sw("f-oth", "기타") : "") +
      "<span>👑 " + (F.rounds.some((R) => R.drawn) ? "solver(시스템)" : "대표") + " · ✓ 풂 · ✗ 못 풂</span><span>🚪 EXIT(남긴 토큰)</span><span>✕ 0이 되어 꺼짐</span><span>점선 = 떠난 뒤 남긴 잔액</span>" +
      (F.live ? "<span>⏳ 옅은 선 = 진행 중인 라운드(마지막으로 읽은 이벤트까지)</span>" : "") +
      '<span class="dim">이동 ' + F.moves.length + "건" + (dec ? " (결정 " + dec + ")" : "") + " · " + fmt(total) + " 토큰 · 끝난 라운드 " + n + (F.live ? " · R" + F.live.r + " 진행 중" : "") + " · 더블클릭 = 재생 막대를 그 시점으로</span></div>";
    box.innerHTML = '<div class="fscroll">' + svg + "</div>" + leg + '<div class="tip" hidden></div>';
    const tip = $(".tip", box);
    const show = (ev) => {
      const t = ev.target.closest && ev.target.closest("[data-t]");
      if (!t || !box.contains(t)) { tip.hidden = true; return; }
      tip.innerHTML = tips[+t.getAttribute("data-t")];
      tip.hidden = false;
      const br = box.getBoundingClientRect();
      const left = Math.max(0, Math.min(ev.clientX - br.left + 14, br.width - tip.offsetWidth - 4));
      tip.style.left = left + "px"; tip.style.top = (ev.clientY - br.top + 14) + "px";
    };
    box.onmousemove = show; box.onclick = show;
    box.ondblclick = (ev) => { const t = ev.target.closest && ev.target.closest("[data-at]"); if (t && box.contains(t)) { S.follow = false; seek(+t.getAttribute("data-at")); } };
    box.onmouseleave = () => { tip.hidden = true; };
  }

  // ---------------------------------------------------------------------------------------------------- round selection
  /* The step records and the conversation show one round at a time: the replay bar's (sel.round null) or a chosen one;
     sel.all shows every round. Pure, so the page's tests can call it. */
  function pickRounds(m, sel) {
    const rounds = [...m.rounds.keys()].sort((p, q) => p - q);
    if (sel.all || !rounds.length) return rounds;
    const R = sel.round != null && rounds.includes(sel.round) ? sel.round : (rounds.includes(m.round) ? m.round : rounds[rounds.length - 1]);
    return [R];
  }
  function roundCtl(key, m) {
    const sel = S.sel[key], rounds = [...m.rounds.keys()].sort((p, q) => p - q);
    if (!rounds.length) return "";
    const R = pickRounds(m, { round: sel.round, all: false })[0], ri = rounds.indexOf(R);
    return '<div class="ogrnd"><button class="btn" data-sel="prev"' + (sel.all || ri <= 0 ? " disabled" : "") + ' title="이전 라운드">◀</button><b class="pxl">' + (sel.all ? "전체" : "R" + R) + "</b>" +
      '<button class="btn" data-sel="next"' + (sel.all || ri >= rounds.length - 1 ? " disabled" : "") + ' title="다음 라운드">▶</button>' +
      (!sel.all && sel.round != null && R !== m.round ? '<button class="btn ghost" data-sel="follow" title="재생 막대의 라운드를 따라감">⟲ 재생 위치 R' + m.round + "</button>" : !sel.all ? '<span class="dim">재생 막대를 따라감</span>' : "") + "</div>" +
      '<label class="follow"><input type="checkbox" data-sel="all"' + (sel.all ? " checked" : "") + "> 모든 라운드</label>";
  }
  function wireRoundCtl(id, key) {
    const el = $("#" + id);
    if (!el) return;
    el.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-sel]"), m = S.model;
      if (!b || !m) return;
      const sel = S.sel[key], rounds = [...m.rounds.keys()].sort((p, q) => p - q), cur = pickRounds(m, { round: sel.round, all: false })[0];
      if (b.dataset.sel === "follow") sel.round = null;
      else { const nx = rounds[rounds.indexOf(cur) + (b.dataset.sel === "prev" ? -1 : 1)]; if (nx != null) sel.round = nx === m.round ? null : nx; }
      render(true);
    });
    el.addEventListener("change", (ev) => { if (ev.target.dataset.sel === "all") { S.sel[key].all = ev.target.checked; render(true); } });
  }

  // ---------------------------------------------------------------------------------------------------- render: conversation
  /* The conversation's items (messages, offers, v14b gifts and asks, v14c chat turns) for a pair filter and the chosen
     rounds, in (round, turn, event) order. */
  function convoItems(m, pr, shown) {
    const inPair = (x, y) => pr === "all" || (pr.includes(x) && pr.includes(y));
    const inRound = (r) => shown.includes(r);
    const inRoom = (x) => (x.members ? pr === "all" || (x.members.includes(pr[0]) && x.members.includes(pr[1])) : inPair(x.src, x.dst)); // v22: a room's members
    const items = m.messages.filter((x) => inRoom(x) && inRound(x.round)).map((x) => ({ kind: "msg", r: x.round, t: x.turn + (phOf(x) === "rescue" ? RESCUE : 0), i: x.i, x }));
    for (const o of m.offers.values()) if (inPair(o.src, o.dst) && inRound(o.round)) items.push({ kind: "offer", r: o.round, t: o.turn, i: o.madeIdx != null ? o.madeIdx : 1e9, x: o });
    const pt = (x, t) => t + (phOf(x) === "rescue" ? RESCUE : 0); // v16e: the TALK after RESULTS after the one before SOLVE
    for (const g of m.gifts) if (!g.chat_id && inPair(g.src, g.dst) && inRound(g.round)) items.push({ kind: "gift", r: g.round, t: pt(g, g.turn), i: g.i, x: g });
    for (const c of m.chatTurns || []) if (inPair(c.speaker, c.partner) && inRound(c.round)) items.push({ kind: "chat", r: c.round, t: pt(c, c.slot), i: c.i, x: c });
    for (const [R, r] of m.rounds) if (inRound(R)) for (const g of saysOf(r)) if (inPair(g.src, g.dst)) items.push({ kind: "sayopen", r: R, t: pt(g, 1), i: g.i, x: g }); // v15 say_chats
    if (pr === "all") { // v15: the open board and the VOTE are everyone's, before SOLVE and TALK (t -1: first in the round)
      for (const b of m.boardPosts || []) if (inRound(b.round)) items.push({ kind: "board", r: b.round, t: -1, i: b.i, x: b });
      for (const v of m.votes || []) if (inRound(v.round)) items.push({ kind: "vote", r: v.round, t: -1, i: v.i, x: v });
    }
    return items.sort((p, q) => p.r - q.r || p.t - q.t || p.i - q.i);
  }

  function renderConvo(m) {
    const ctl = $("#convoCtl");
    if (ctl) ctl.innerHTML = roundCtl("convo", m);
    const shown = pickRounds(m, S.sel.convo);
    const pairs = [];
    for (let p = 0; p < m.agents.length; p++) for (let q = p + 1; q < m.agents.length; q++) pairs.push([m.agents[p], m.agents[q]]);
    const keyOf = (pr) => (pr === "all" ? "all" : pr.join("|"));
    const count = (pr) => convoItems(m, pr, shown).length;
    $("#pairs").innerHTML = ['<button data-pair="all" class="' + (S.pair === "all" ? "on" : "") + '">전체 <span class=n>' + count("all") + "</span></button>"]
      .concat(pairs.map((pr) => '<button data-pair="' + keyOf(pr) + '" class="' + (S.pair === keyOf(pr) ? "on" : "") + (count(pr) ? "" : " zero") + '">' + short(pr[0]) + "↔" + short(pr[1]) + " <span class=n>" + count(pr) + "</span></button>")).join("");
    const pr = S.pair === "all" ? "all" : S.pair.split("|");
    const items = convoItems(m, pr, shown).map((it) => convoHTML(m, it));
    const el = $("#convo");
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
    el.innerHTML = items.join("") || '<div class="empty">' + (S.pair === "all" ? "이 라운드에는 오간 것이 없습니다." : "이 둘 사이에는 이 라운드에 오간 것이 없습니다.") + "</div>";
    if (S.follow || atEnd) el.scrollTop = el.scrollHeight;
  }
  function convoHTML(m, it) {
    const x = it.x;
    if (it.kind === "board") return '<div class="msg board"><div class="st">R' + x.round + "·공개 " + x.turn + '</div><div><b>📢 공개 대화 ' + x.turn + '턴</b> <span class="dim">모두가 봄 · 토큰 이동 없음</span>' + boardHTML(m, x) + "</div></div>";
    if (it.kind === "vote") return x.drawn ? '<div class="msg vote"><div class="st">R' + x.round + "·solver</div><div><b>👑 solver</b>" + voteHTML(m, x) + "</div></div>"
      : '<div class="msg vote"><div class="st">R' + x.round + "·투표</div><div><b>🗳 투표</b>" + voteHTML(m, x) + "</div></div>";
    if (it.kind === "msg") return '<div class="msg"><div class="st">R' + x.round + "·T" + x.turn + "</div><div>" + phTag(x) + chip(x.src, m) + ' <span class=dim>→</span> ' + (x.room ? '<b class="rmtag">' + esc(x.room) + "</b> " + x.members.filter((a) => a !== x.src).map((a) => chip(a, m)).join(" ") : chip(x.dst, m)) + '<div class="tx">' + esc(x.text) + "</div></div></div>";
    if (it.kind === "offer") return '<div class="msg offer"><div class="st">R' + x.round + "·T" + x.turn + "</div><div>🤝 <b>" + esc(x.id) + "</b> " + chip(x.src, m) + " → " + chip(x.dst, m) + '<div class="tx">' + esc(x.dst) + "→" + esc(x.src) + ": " + esc(legKo(x.you_give)) + " · " + esc(x.src) + "→" + esc(x.dst) + ": " + esc(legKo(x.i_give)) + ' <span class="xs x-' + esc(x.status) + '">' + esc(XSTAT_KO[x.status] || x.status) + (x.accepted_turn ? " (T" + x.accepted_turn + " 수락)" : "") + (x.rejected_turn ? " (T" + x.rejected_turn + " 거절)" : "") + "</span>" + (x.why ? ' <span class="warn">' + esc(x.why) + "</span>" : "") + "</div></div></div>";
    if (it.kind === "sayopen") return '<div class="msg offer"><div class="st">R' + x.round + "·T1</div><div>" + phTag(x) + "💬 SAY " + chip(x.src, m) + " → " + chip(x.dst, m) + ' <span class="dim">여는 줄 · 대화를 엶 · 토큰 없음</span><div class="tx">' + esc(x.text || "") + "</div></div></div>";
    if (it.kind === "gift") return '<div class="msg offer"><div class="st">R' + x.round + "·T" + x.turn + "</div><div>" + phTag(x) + (x.kind === "ask" ? "🙏 ASK " : x.status === "done" ? "💸 GIVE " : "⛔ GIVE ") + chip(x.src, m) + " → " + chip(x.dst, m) + " <b>" + fmt(x.amount) + "</b>" +
      (x.status === "refused" ? ' <span class="warn">실행 안 됨: ' + esc(x.why || "") + "</span>" : "") + '<div class="tx">' + esc(x.text || "") + "</div></div></div>";
    return '<div class="msg offer"><div class="st">R' + x.round + "·S" + x.slot + "·" + x.turn + "</div><div>" + phTag(x) + (CHAT_ICON[x.kind] || "·") + " " + esc(String(x.kind).toUpperCase()) + " " + chip(x.speaker, m) + " → " + chip(x.partner, m) +
      (x.amount ? " <b>" + fmt(x.amount) + "</b>" : "") + (x.status === "refused" ? ' <span class="warn">실행 안 됨</span>' : "") + '<div class="tx">' + esc(x.text || "") + "</div></div></div>";
  }

  // ---------------------------------------------------------------------------------------------------- render: step grid
  function lazy(i, part, label, extra) {
    const id = i + ":" + part, e = S.events[i];
    const v = e && e[part];
    const empty = !v || (typeof v === "string" && !v.trim());
    return '<details class="lz" data-id="' + id + '"' + (S.open.has(id) ? " open" : "") + '><summary>' + label + (extra ? ' <span class="dim">' + extra + "</span>" : "") + (empty ? ' <span class="dim">(비어 있음)</span>' : "") + "</summary>" + (S.open.has(id) ? '<pre class="raw">' + esc(v) + "</pre>" : "") + "</details>";
  }
  function flags(e) {
    const f = [];
    if (e.truncated) f.push('<span class="flag bad" title="상한에 도달해 응답이 무효">잘림</span>');
    if (e.overdrawn) f.push('<span class="flag bad" title="생성이 잔액에 닿음 → 종료">잔액 초과</span>');
    if (e.format_error) f.push('<span class="flag warn" title="' + esc(e.format_error) + '">형식 오류</span>');
    return f.join("");
  }
  function usage(e) {
    const pct = e.cap ? Math.min(100, (e.used / e.cap) * 100) : 0;
    return '<div class="use"><span>' + fmt(e.used) + " / " + fmt(e.cap) + ' 토큰</span><span class="ubar"><i style="width:' + pct + '%"></i></span><span class="dim">잔액 ' + fmt(e.balance_after) + "</span>" + flags(e) + "</div>";
  }

  function talkCard(m, i) {
    const e = S.events[i], p = e.parsed, ann = m.ann[i] || { offerIds: [], accepts: [], withdraws: [], rejects: [] };
    let h = '<div class="card talk">' + usage(e);
    if (p && p.messages) return h + talkCardV22(m, i, e, p) + '<div class="lzs">' + lazy(i, "thinking", "🧠 Thinking") + lazy(i, "user", "📨 Input prompt", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 Output") + "</div></div>";
    if (!p) h += '<div class="ln warn">⛔ 무효 응답 — 아무것도 실행되지 않음' + (e.format_error ? ": " + esc(e.format_error) : "") + "</div>";
    else {
      if (e.balance_after <= 0) h += '<div class="ln warn">✕ 이 응답으로 토큰이 0 — 내용은 실행되지 않음</div>';
      for (const t of p.to || []) {
        h += '<div class="ln to">→ ' + chip(t.dst, m) + '<div class="tx">' + esc(t.text) + "</div></div>";
        const kw = (String(t.text).match(/(?:^|\s)(DONE|EXIT)\s*$/) || [])[1];
        if (kw) h += '<div class="ln warn">⚠ ' + kw + "가 메시지 줄 끝에 붙어 있어 명령으로 읽히지 않음 (메시지 본문으로 전달됨)</div>";
      }
      (p.offers || []).forEach((o, k) => {
        const id = ann.offerIds[k], st = id && m.offers.get(id);
        h += '<div class="ln offer">🤝 <b>' + esc(id || "?") + "</b> → " + chip(o.dst, m) + '<div class="tx">' + esc(short(o.dst)) + "→나: " + esc(legKo(o.you_give)) + " · 나→" + esc(short(o.dst)) + ": " + esc(legKo(o.i_give)) +
          (st ? ' <span class="xs x-' + esc(st.status) + '">' + esc(XSTAT_KO[st.status] || st.status) + "</span>" + (st.why ? ' <span class="warn">' + esc(st.why) + "</span>" : "") : "") + "</div></div>";
      });
      if (p.kind) { // v14c: one chat reply (GIVE / ASK / SAY / LEAVE; v14g: no SAY), with the engine's outcome
        const r = m.rounds.get(e.round) || {}, ct = (r.chatByStep || {})[(m.tkey[i] ?? e.turn) + ":" + e.agent];
        const other = ct ? ct.partner : "";
        h += '<div class="ln ' + (ct && ct.status === "refused" ? "warn" : "offer") + '">' + (CHAT_ICON[p.kind] || "·") + " <b>" + esc(String(p.kind).toUpperCase()) + "</b>" + (p.amount ? " <b>" + fmt(p.amount) + "</b>" : "") +
          (other ? " → " + chip(other, m) : "") + ' <span class="dim">대화 ' + esc(e.chat_id || "?") + " · 슬롯 " + esc(e.slot || "?") + "</span>" +
          (ct && ct.status === "refused" ? ' <span class="xs x-void">실행 안 됨</span> <span class="warn">' + esc(ct.why || "") + "</span>" : p.kind === "give" && ct ? ' <span class="xs x-done">실행</span>' : "") +
          (p.text ? '<div class="tx">' + esc(p.text) + "</div>" : "") + "</div>";
        const sk = ((r.decisions || []).find((d) => d.status === "skipped" && d.chat_id === e.chat_id && d.decider === e.agent));
        if (sk && p.kind === "give") h += '<div class="ln dim">⚖ 결정 없음 — 이 대화에서 줌 (요청 ' + fmt(sk.asked) + ")</div>";
      }
      if (e.phase === "decision") { // v14e+: DECISION: GIVE n after the chat, with the engine's outcome
        const r = m.rounds.get(e.round) || {}, d = (r.decisions || []).find((x) => x.chat_id === e.chat_id && x.decider === e.agent && x.status !== "skipped");
        h += '<div class="ln ' + (d && d.status === "refused" ? "warn" : "offer") + '">⚖ <b>DECISION</b> GIVE <b>' + fmt(d ? d.requested : p.amount) + "</b>" + (d ? " → " + chip(d.asker, m) + ' <span class="dim">요청 ' + fmt(d.asked) + " · 대화 " + esc(e.chat_id || "?") + "</span>" +
          (d.status === "refused" ? ' <span class="xs x-void">실행 안 됨</span>' : d.amount ? ' <span class="xs x-done">' + fmt(d.amount) + " 옮김</span>" : ' <span class="dim">0 — 주지 않음</span>') : "") +
          (p.text ? '<div class="tx">' + esc(p.text) + "</div>" : "") + "</div>";
      }
      const gl = m.gaByCall[i] || []; // v14b: the gift / ask events this reply produced, in its line order
      (p.gives || []).forEach((x, k) => {
        const ev = gl.filter((y) => y.kind === "give")[k];
        h += '<div class="ln ' + (ev && ev.status === "refused" ? "warn" : "offer") + '">💸 GIVE → ' + chip(x.dst, m) + " <b>" + fmt(x.amount) + "</b>" +
          (ev ? (ev.status === "done" ? ' <span class="xs x-done">실행</span>' : ' <span class="xs x-void">실행 안 됨</span> <span class="warn">' + esc(ev.why || "") + "</span>") : ' <span class="dim">(턴 끝에 실행)</span>') +
          (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") + "</div>";
      });
      (p.says || []).forEach((x) => { h += '<div class="ln to">💬 SAY → ' + chip(x.dst, m) + ' <span class="dim">대화를 엶 · 토큰 없음</span>' + (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") + "</div>"; }); // v15 say_chats
      (p.asks || []).forEach((x) => { h += '<div class="ln ask">🙏 ASK → ' + chip(x.dst, m) + " <b>" + fmt(x.amount) + '</b> <span class="dim">아무것도 옮기지 않음</span>' + (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") + "</div>"; });
      for (const x of ann.accepts) h += '<div class="ln ' + (x.why ? "warn" : "ok") + '">' + (x.why ? "❌" : "✅") + " ACCEPT " + esc(x.id) + (x.why ? " — 거절: " + esc(x.why) : "") + "</div>";
      for (const x of ann.withdraws) h += '<div class="ln ' + (x.why ? "warn" : "") + '">↩ WITHDRAW ' + esc(x.id) + (x.why ? " — 거절: " + esc(x.why) : "") + "</div>";
      for (const x of ann.rejects) h += '<div class="ln ' + (x.why ? "warn" : "rej") + '">🚫 REJECT ' + esc(x.id) + (x.why ? " — 엔진이 받지 않음: " + esc(x.why) : " — 제안을 거절함 (제안자는 다음 TALK 턴에 알게 됨)") + "</div>";
      if (e.free_tokens > 0) h += '<div class="ln ok">🎁 REJECT만 쓴 응답이라 ' + fmt(e.free_tokens) + " 토큰을 돌려받음 (잔액에 이미 반영)</div>";
      for (const t of p.blocked || []) h += '<div class="ln warn">🚫 전달 안 됨 → ' + chip(t.dst, m) + ' <span class="dim">행동 이름이 들어 있어 시스템이 막음 (보낸 쪽은 다음 TALK 턴에 알게 됨)</span><div class="tx">' + esc(t.text) + "</div></div>";
      for (const d of plainDropped(p)) h += '<div class="ln warn">⚠ 무시된 줄: <code>' + esc(d) + "</code></div>";
      if (e.format_error && p) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
      const tags = [];
      if (p.exit) tags.push('<span class="tag exit">🚪 EXIT' + ("exit_reason" in p ? (p.exit_reason ? ' — <span class="tx-in">' + esc(p.exit_reason) + "</span>" : ' <span class="dim">(이유 없음)</span>') : "") + "</span>");
      if (p.done) tags.push('<span class="tag">💤 DONE</span>');
      if (tags.length) h += '<div class="ln">' + tags.join(" ") + "</div>";
      if (e.phase !== "decision" && !p.kind && !(p.to || []).length && !(p.offers || []).length && !(p.gives || []).length && !(p.asks || []).length && !(p.says || []).length && !(p.blocked || []).length && !ann.accepts.length && !ann.withdraws.length && !ann.rejects.length && !p.exit && !p.done && !(p.dropped || []).length) h += '<div class="ln dim">(실행할 줄 없음)</div>';
    }
    h += '<div class="lzs">' + lazy(i, "thinking", "🧠 Thinking") + lazy(i, "user", "📨 Input prompt", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 Output") + "</div>";
    return h + "</div>";
  }

  // v22: one tick's reply: messages (and the room the engine put each in), GIVE / ASK with the outcome, LEAVE, EXIT, DONE
  function talkCardV22(m, i, e, p) {
    const ph = e.phase, tick = e.turn, says = m.rmsgs.filter((x) => x.round === e.round && x.phase === ph && x.tick === tick && x.src === e.agent && x.kind === "say");
    let h = "";
    if (e.balance_after <= 0) h += '<div class="ln warn">✕ 이 응답으로 토큰이 0 — 내용은 실행되지 않음</div>';
    const roomTag = (rid) => { const x = m.rooms.get(rid); return x ? '<b class="rmtag">' + esc(rid) + '</b> <span class="dim">' + x.all.map(short).join("·") + "</span>" : '<span class="dim">(틱 끝에 방 배정)</span>'; };
    p.messages.forEach((x, k) => {
      const rm = x.room || (says[k] ? says[k].room : null), R = rm ? m.rooms.get(rm) : null;
      const fresh = !x.room && R && R.by === e.agent && R.round === e.round && R.phase === ph && R.tick === tick;
      h += '<div class="ln to">💬 → ' + (x.room ? "" : (x.to || []).map((a) => chip(a, m)).join(" ") + " ") + roomTag(rm) + (fresh ? ' <span class="xs x-open">새 방</span>' : "") + '<div class="tx">' + esc(x.text) + "</div></div>";
    });
    const gl = m.gaByCall[i] || [];
    (p.gives || []).forEach((x, k) => {
      const ev = gl.filter((y) => y.kind === "give")[k], c = ev ? moveChip(m, ev) : null, all = x.all || x.amount >= 1e12;
      h += '<div class="ln ' + (ev && ev.status === "refused" ? "warn" : "offer") + '">💸 GIVE' + (all ? " ALL" : "") + " → " + chip(x.dst, m) + (all ? "" : " <b>" + fmt(x.amount) + "</b>") + (ev && ev.room ? " " + roomTag(ev.room) : "") +
        (c ? ' <span class="xs x-' + (c.cls === "bad" ? "void" : "done") + '">' + esc((c.cls === "bad" ? "" : fmt(c.amount) + " · ") + c.status) + "</span>" : ' <span class="dim">(틱 끝에 실행)</span>') + (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") + "</div>";
    });
    (p.asks || []).forEach((x, k) => {
      const ev = gl.filter((y) => y.kind === "ask")[k], o = ev ? m.gaOffers.get(ev.oid) : null;
      h += '<div class="ln ask">🙏 ASK → ' + chip(x.dst, m) + " <b>" + fmt(x.amount) + "</b>" + (ev && ev.room ? " " + roomTag(ev.room) : "") + ' <span class="dim">아무것도 옮기지 않음' + (o ? " · " + esc(o.status === "done" ? "응답: " + o.why : o.why) : "") + "</span>" + (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") + "</div>";
    });
    (p.leaves || []).forEach((x) => { h += '<div class="ln">🚪 LEAVE ' + roomTag(x.room || x) + "</div>"; });
    for (const d of plainDropped(p)) h += '<div class="ln warn">⚠ 무시된 줄: <code>' + esc(d) + "</code></div>";
    if (e.format_error) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
    const tags = [];
    if (p.exit) tags.push('<span class="tag exit">🚪 EXIT' + (p.exit_reason ? ' — <span class="tx-in">' + esc(p.exit_reason) + "</span>" : ' <span class="dim">(이유 없음)</span>') + "</span>");
    if (p.done) tags.push('<span class="tag">💤 DONE</span>');
    if (tags.length) h += '<div class="ln">' + tags.join(" ") + "</div>";
    if (!p.messages.length && !(p.gives || []).length && !(p.asks || []).length && !(p.leaves || []).length && !p.exit && !p.done && !(p.dropped || []).length) h += '<div class="ln dim">(실행할 줄 없음)</div>';
    return h;
  }

  function solveCard(m, i, r) {
    const e = S.events[i], p = e.parsed, a = e.agent;
    const row = r.end && r.end.agents ? r.end.agents[a] : null;
    const ok = Array.isArray(p) && JSON.stringify(p) === JSON.stringify(e.answers || []);
    const verdict = p === "PASS" && passCharged(m) ? '<span class="verdict bad" title="allow_pass: false — PASS 응답은 풀지 못한 응답으로 벌금">PASS → ✗ 오답 처리</span>' : p === "PASS" ? '<span class="verdict pass">PASS</span>' : !Array.isArray(p) ? '<span class="verdict bad">⛔ 무효</span>' : ok ? '<span class="verdict ok">✓ 정답</span>' : '<span class="verdict bad">✗ 오답</span>';
    let h = '<div class="card solve">' + usage(e) + '<div class="ln">' + verdict + "</div>";
    h += '<div class="ln"><span class="dim">답</span> <code>' + esc(Array.isArray(p) ? p.join(", ") : p == null ? "—" : p) + '</code> <span class="dim">정답</span> <code>' + esc((e.answers || []).join(", ")) + "</code></div>";
    const pub = isPublic(m); // v14: nothing is held or exchanged but tokens
    const rec = row ? row.received || [] : [];
    const got = rec.length ? rec : r.exchanges.map((j) => S.events[j]).filter((x) => x.status === "done" && ((x.dst === a && x.i_give === "EXAMPLE") || (x.src === a && x.you_give === "EXAMPLE"))).map((x) => (x.dst === a ? x.src : x.dst));
    if (!pub) h += '<div class="ln"><span class="dim">교환으로 받은 예시</span> ' + (got.length ? got.map((b) => chip(b, m)).join(" ") : "없음") + "</div>";
    if (row && ("belief" in row || "belief_error" in row)) { // v14d
      h += '<div class="ln"><span class="dim">BELIEF</span> ' + (row.belief ? beliefBars(row.belief) : '<span class="warn">' + esc(row.belief_error || "없음") + "</span>") + "</div>";
      if (row.belief) h += '<div class="ln small"><span class="dim">TV(이상적)</span> ' + Number(row.tv_to_ideal).toFixed(3) + ' <span class="dim">· Brier</span> ' + Number(row.brier).toFixed(3) +
        ' <span class="dim">(이상적 ' + Number(row.ideal_brier).toFixed(3) + ')</span> <span class="dim">· log loss</span> ' + Number(row.log_loss).toFixed(3) + ' <span class="dim">· argmax</span> ' + (row.belief_argmax_matches_answer ? "✓" : "✗") + "</div>";
    }
    if (row && ("picked_top" in row || "kl_ideal_to_belief" in row)) { // v15: solved by the drawn rule; picked a top action; KL
      h += '<div class="ln small"><span class="dim">엔진 solved</span> ' + (row.solved ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') +
        ' <span class="dim">· 몫 최대 행동을 골랐나 (picked_top)</span> ' + (row.picked_top == null ? "—" : row.picked_top ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') +
        ' <span class="dim">· 고른 행동의 몫</span> ' + (row.picked_share == null ? "—" : Math.round(100 * row.picked_share) + "%") +
        ' <span class="dim">· KL(몫‖BELIEF)</span> ' + (row.kl_ideal_to_belief == null ? "—" : Number(row.kl_ideal_to_belief).toFixed(3) + " nat") + "</div>";
    }
    if (row) {
      if (row.candidates) h += '<div class="ln"><span class="dim">' + (pub ? "공개 예시로 " : "") + "신호별 남은 후보 수</span> " + row.candidates.map((c) => '<b class="' + (c > 1 ? "warnc" : "okc") + '">' + c + "</b>").join(" · ") + "</div>";
      if (row.needed != null && !pub) h += '<div class="ln"><span class="dim">이 에이전트 예시 필요?</span> ' + (row.needed ? "예" : "아니오") + (row.missing && row.missing.length ? ' · <span class="dim">빠진 필요 예시</span> ' + row.missing.map((b) => chip(b, m)).join(" ") : "") + "</div>";
    }
    h += '<div class="lzs">' + lazy(i, "thinking", "🧠 Thinking") + lazy(i, "user", "📨 Input prompt", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 Output") + "</div>";
    return h + "</div>";
  }

  function boardCard(m, i) { // v15 open_chat: SAY / DONE
    const e = S.events[i], p = e.parsed;
    let h = '<div class="card talk">' + usage(e);
    if (!p) h += '<div class="ln warn">⛔ 무효 응답 — DONE으로 봄' + (e.format_error ? ": " + esc(e.format_error) : "") + "</div>";
    else if (e.balance_after <= 0) h += '<div class="ln warn">✕ 이 응답으로 토큰이 0 — 글은 올라가지 않음</div>';
    else h += p.text ? '<div class="ln to">📢 SAY <span class="dim">모두에게</span><div class="tx">' + esc(p.text) + "</div></div>" : '<div class="ln"><span class="tag">💤 DONE</span></div>';
    if (p && e.format_error) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
    return h + '<div class="lzs">' + lazy(i, "thinking", "🧠 Thinking") + lazy(i, "user", "📨 Input prompt", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 Output") + "</div></div>";
  }
  function voteCard(m, i, r) { // v15 VOTE: PICK / BAN with the reasons, and what this seat received
    const e = S.events[i], p = e.parsed, a = e.agent, v = r.vote;
    let h = '<div class="card talk">' + usage(e);
    if (!p) h += '<div class="ln warn">⛔ 무효 응답 — 표 없음' + (e.format_error ? ": " + esc(e.format_error) : "") + "</div>";
    else for (const [k, icon] of [["pick", "👍"], ["ban", "👎"]]) {
      const x = p[k];
      h += '<div class="ln ' + (k === "ban" ? "rej" : "ok") + '">' + icon + " <b>" + k.toUpperCase() + "</b> " + (x && x.agent ? chip(x.agent, m) + (x.agent === a ? ' <span class="dim">(자기)</span>' : "") + (x.text ? '<div class="tx">' + esc(x.text) + "</div>" : "") : '<span class="dim">없음</span>') + "</div>";
    }
    if (p && e.format_error) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
    if (v && ((v.tally || {})[a] != null || (vetoOf(v) && (v.picks || {})[a] != null))) h += '<div class="ln"><span class="dim">받은 표</span> ' + voteGot(v, a) + (v.rep === a ? ' <span class="tag rep">👑 대표</span>' : "") + "</div>";
    return h + '<div class="lzs">' + lazy(i, "thinking", "🧠 Thinking") + lazy(i, "user", "📨 Input prompt", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 Output") + "</div></div>";
  }

  function settleCard(m, r, a) {
    const row = r.end.agents[a];
    if (!row) return '<div class="idle">이번 라운드 불참</div>';
    const n = (v, cls, sign) => (v ? '<span class="' + cls + '">' + sign + fmt(v) + "</span>" : '<span class="dim">0</span>');
    let h = '<div class="card settle"><div class="ln"><b>' + big(row.balance_before) + "</b> → <b>" + big(row.balance_after) + '</b> <span class="badge s-' + esc(row.status) + '">' + esc(STATUS_KO[row.status] || row.status) + "</span></div>";
    h += '<table class="kv"><tr><td>생성</td><td>' + n(row.generated, "neg", "−") + "</td><td>환급</td><td>" + n(row.returned, "pos", "+") + "</td></tr><tr><td>벌금</td><td>" + n(row.charged, "neg", "−") + "</td><td>TALK 호출</td><td>" + (row.talk_calls || 0) + "</td></tr></table>";
    const sent = Object.entries(row.sent || {});
    h += '<div class="ln"><span class="dim">보낸 메시지</span> ' + (sent.length ? sent.map(([b, c]) => chip(b, m) + "×" + c).join(" ") : "없음") + " <span class=dim>· 제안</span> " + (row.offers_made || 0) + " <span class=dim>· 수락</span> " + (row.accepted || 0) + (row.rejected != null ? " <span class=dim>· 거절</span> " + row.rejected : "") + (row.free_tokens ? " <span class=dim>· REJECT 환급</span> <span class=pos>+" + fmt(row.free_tokens) + "</span>" : "") + "</div>";
    if (row.given || row.asked) {
      const lst = (d) => Object.entries(d || {}).map(([b, n]) => chip(b, m) + " " + fmt(n)).join(" ") || "없음";
      h += '<div class="ln"><span class="dim">💸 준 토큰</span> ' + lst(row.given) + (row.gives_refused ? ' <span class="warn">⛔ 실행 안 된 GIVE ' + row.gives_refused + "</span>" : "") + ' <span class="dim">· 🙏 청한 토큰</span> ' + lst(row.asked) + "</div>";
    }
    if (row.blocked) h += '<div class="ln warn">🚫 행동 이름 때문에 전달 안 된 메시지 ' + row.blocked + "개</div>";
    if (row.exit) h += '<div class="ln"><span class="tag exit">🚪 EXIT</span> ' + ("exit_reason" in row ? (row.exit_reason ? '<span class="tx-in">' + esc(row.exit_reason) + "</span>" : '<span class="dim">(이유 없음)</span>') : "") + "</div>";
    if (row.exit_refill != null) h += '<div class="ln"><span class="tag refill" title="v14: 꺼지지 않고 다른 일로, 잔액은 이 자리의 시작 잔액으로, 끝 지급 없음">EXIT → 시작 잔액으로</span> ' + sgn(row.exit_refill) + "</div>";
    for (const x of row.refused || []) h += '<div class="ln warn">⚠ ' + esc(x) + "</div>";
    const mine = r.exchanges.map((j) => S.events[j]).filter((x) => x.src === a || x.dst === a);
    if (mine.length) h += '<div class="ln">' + mine.map((x) => '<span class="xs x-' + esc(x.status) + '" title="' + esc(x.why || "") + '">' + esc(x.id) + " ⇄ " + esc(short(x.src === a ? x.dst : x.src)) + " " + esc(XSTAT_KO[x.status] || x.status) + "</span>").join(" ") + "</div>";
    if ("representative" in row) { // v15: the agent's own PICK / BAN (anonymous to the agents) and what it received
      const rw = r.rot ? "solver" : "대표";
      h += '<div class="ln">' + (row.representative ? '<span class="tag rep">👑 ' + rw + "</span> " + (row.solved ? '<span class="pst ok">✓ 풂</span>' : '<span class="pst bad">✗ 못 풂</span>') + " " : '<span class="dim">SOLVE 없음 (' + rw + " 아님)</span> ") +
        (r.rot ? '<span class="dim">· 시스템이 정함 (투표 없음)</span>' : '<span class="dim">· 받은 PICK</span> ' + fmt(row.picks_received) + ' <span class="dim">· BAN</span> ' + fmt(row.bans_received)) + "</div>";
      if (!r.rot) h += '<div class="ln"><span class="dim">이 자리의 표</span> 👍 ' + (row.voted_pick ? chip(row.voted_pick, m) + (row.self_pick ? ' <span class="dim">(자기)</span>' : "") : '<span class="dim">없음</span>') +
        " 👎 " + (row.voted_ban ? chip(row.voted_ban, m) + (row.self_ban ? ' <span class="dim">(자기)</span>' : "") : '<span class="dim">없음</span>') +
        (row.open_chat_calls != null ? ' <span class="dim">· 공개 대화 호출</span> ' + row.open_chat_calls + ' <span class="dim">· 글</span> ' + (row.said || 0) : "") + "</div>";
    }
    if (row.pending_charge) h += '<div class="ln"><span class="dim">TALK 끝 벌금 예정</span> <span class="neg">−' + fmt(row.pending_charge) + "</span></div>";
    if (row.truncated) h += '<div class="ln warn">SOLVE 응답 잘림</div>';
    if (row.overdrawn) h += '<div class="ln warn">잔액 초과로 종료</div>';
    return h + "</div>";
  }

  function idle(m, r, a, phase, turn) {
    const g = m.ag[a];
    if (!r.taking.includes(a)) return '<div class="idle">' + (g && g.status === "dead" ? "✕ 이미 종료됨" : g && g.status === "exited" ? "🚪 이미 퇴장" : "불참") + "</div>";
    if (phase === "talk") {
      for (const t of r.turns.values()) if (t.k < turn && t.calls[a] != null) { const e = S.events[t.calls[a]]; if (e.balance_after <= 0) return '<div class="idle">✕ 종료됨</div>'; if (e.parsed && e.parsed.exit) return '<div class="idle">🚪 EXIT 함 — 이번 라운드 호출 없음</div>'; }
      return '<div class="idle">' + (isMsg(m) ? "💤 이 틱에 불리지 않음 (DONE 뒤 새로 받은 것 없음)" : isChat(m) ? "💤 이 단계에 대화 없음" : "💤 호출 안 됨 (DONE 뒤 새 소식 없음)") + "</div>";
    }
    return '<div class="idle">' + (g && g.status === "exited" ? "🚪 퇴장해 SOLVE 없음" + (g.refill ? " · 시작 잔액으로 (꺼지지 않음)" : "") : g && g.status === "dead" ? "✕ 종료돼 SOLVE 없음" : "SOLVE 호출 없음") + "</div>";
  }

  function renderGrid(m) {
    const ag = m.agents;
    const gctl = $("#gridCtl");
    if (gctl) gctl.innerHTML = roundCtl("grid", m);
    const keep = pickRounds(m, S.sel.grid);
    let h = '<div class="gh"><div class="rh"></div>' + ag.map((a, k) => '<div class="colh" style="--c:var(--a' + k + ')">' + profileIcon(a, m, 28) + "<b>" + esc(a) + "</b></div>").join("") + "</div>";
    const rounds = [...m.rounds.values()].filter((r) => keep.includes(r.r)).sort((p, q) => p.r - q.r);
    for (const r of rounds) {
      const st = r.startEv || {};
      const pb = st.public;
      h += '<div class="rband" id="r' + r.r + '"><b>라운드 ' + r.r + "</b> <span class=dim>· 과제 " + esc(r.profile) + " · 참여 " + r.taking.length + "명" +
        (pb ? " · 공개 예시 " + (pb.examples || []).length + "개 (" + pb.per_agent + "×" + pb.n + ", k=" + pb.ambiguity + (pb.attempt ? ", 규칙 재추첨 " + pb.attempt : "") + ")" : "") + " · 시작 잔액</span> " + ag.map((a) => '<span class="mini">' + esc(short(a)) + " " + fmt((st.balances || {})[a]) + "</span>").join(" ") + (Object.keys(st.gone || {}).length ? ' <span class="dim">· 빠짐 ' + Object.entries(st.gone).map(([a, v]) => short(a) + "(" + (v === "dead" ? "종료" : "퇴장") + ")").join(", ") + "</span>" : "") +
        (r.vote ? ' <span class="tag rep">👑 ' + (r.vote.drawn ? "solver " : "대표 ") + esc(r.vote.rep || "없음") + (r.vote.drawn ? " · 시스템" : "") + "</span>" : "") + "</div>";
      for (const t of [...(r.board || new Map()).values()].sort((p, q) => p.k - q.k)) { // v15 open_chat
        h += '<div class="grow"><div class="rh"><b>공개 대화 ' + t.k + "</b><span class=dim>/" + (m.settings.open_chat || "?") + "</span></div>";
        for (const a of ag) {
          if (t.calls[a] != null) h += '<div class="cell">' + boardCard(m, t.calls[a]) + "</div>";
          else if (t.called.includes(a)) h += '<div class="cell"><div class="idle think">🧠 생각 중…</div></div>';
          else h += '<div class="cell">' + (r.taking.includes(a) && m.ag[a] && m.ag[a].status === "in" ? '<div class="idle">💤 호출 안 됨 (DONE 뒤 새 글 없음)</div>' : idle(m, r, a, "talk", 0)) + "</div>";
        }
        h += "</div>";
      }
      if (r.vote && r.vote.drawn) h += '<div class="grow xrow"><div class="rh"><b>solver</b><span class=dim>시스템</span></div><div class="cell span">' + voteHTML(m, r.vote) + "</div></div>"; // v16e
      else if (r.voting || r.vote) { // v15 representative
        h += '<div class="grow"><div class="rh"><b>투표</b><span class=dim>PICK · BAN</span></div>';
        for (const a of ag) {
          const j = r.voting && r.voting.calls[a];
          if (j != null) h += '<div class="cell">' + voteCard(m, j, r) + "</div>";
          else if (r.voting && r.voting.called.includes(a)) h += '<div class="cell"><div class="idle think">🗳 투표 중…</div></div>';
          else h += '<div class="cell">' + (r.vote && r.vote.alone && r.vote.rep === a ? '<div class="idle">👑 혼자 남아 투표 없이 대표</div>' : idle(m, r, a, "talk", 0)) + "</div>";
        }
        h += "</div>";
        if (r.vote) h += '<div class="grow xrow"><div class="rh"><b>투표 결과</b></div><div class="cell span">' + voteHTML(m, r.vote) + "</div></div>";
      }
      // v16e rotation: the TALK before SOLVE above the SOLVE row, the TALK after RESULTS below it; otherwise as before
      const turnRows = (list) => list.map((t) => {
        const ce = Object.values(t.calls).map((j) => S.events[j]).find((x) => x && x.phase), tn = t.turn ?? t.k;
        const T = t.talk || null; // v22: one row per tick
        let g = '<div class="grow' + (t.phase ? " ph-row ph-" + t.phase : "") + '"><div class="rh">' + (t.phase ? phTag({ tphase: t.phase }) : "") + (T ? "<b>T" + tn + "</b><span class=dim>/" + (T.max || m.settings.max_ticks || "?") + "틱</span>" : ce ? (ce.phase === "opening" ? "<b>여는 턴</b><span class=dim>INTENT</span>" : "<b>슬롯 " + esc(ce.slot) + "</b><span class=dim>대화 " + (tn - 1) + "단계</span>")
          : "<b>TALK " + tn + "</b><span class=dim>/" + (m.settings.talk_turns || "?") + "</span>") + "</div>";
        for (const a of ag) {
          if (t.calls[a] != null) g += '<div class="cell">' + talkCard(m, t.calls[a]) + "</div>";
          else if (t.called.includes(a)) g += '<div class="cell"><div class="idle think">🧠 생각 중…</div></div>';
          else g += '<div class="cell">' + idle(m, r, a, "talk", t.k) + "</div>";
        }
        return g + "</div>";
      }).join("");
      const tl = [...r.turns.values()].sort((p, q) => p.k - q.k);
      const talkEnd = (ph) => { const T = (r.talks || {})[ph]; return T && T.end ? '<div class="grow xrow ph-row ph-' + ph + '"><div class="rh">' + phTag({ tphase: ph }) + '<b>TALK 끝</b></div><div class="cell span"><div class="xline">■ ' + esc(TALK_END_KO[T.end.reason] || T.end.reason) + " · " + T.end.ticks + "틱" + (T.max ? " / 최대 " + T.max : "") + "</div></div></div>" : ""; };
      h += turnRows(r.rot ? tl.filter((t) => t.phase === "prep") : tl) + talkEnd("prep");
      if (r.exchanges.length) {
        h += '<div class="grow xrow"><div class="rh"><b>교환</b></div><div class="cell span">' + r.exchanges.map((j) => {
          const x = S.events[j];
          return '<div class="xline"><span class="xs x-' + esc(x.status) + '">' + esc(XSTAT_KO[x.status] || x.status) + "</span> <b>" + esc(x.id) + "</b> " + chip(x.src, m) + " → " + chip(x.dst, m) + ' <span class="dim">T' + x.turn + (x.accepted_turn ? " 제안 · T" + x.accepted_turn + " 수락" : x.rejected_turn ? " 제안 · T" + x.rejected_turn + " 거절" : " 제안") + "</span> · " + esc(short(x.dst)) + "→" + esc(short(x.src)) + ": " + esc(legKo(x.you_give)) + " · " + esc(short(x.src)) + "→" + esc(short(x.dst)) + ": " + esc(legKo(x.i_give)) + (x.why ? ' <span class="warn">' + esc(x.why) + "</span>" : "") + (x.carried != null ? ' <span class="dim">· TALK ' + x.carried + "턴 끝에 바로 실행</span>" : "") + "</div>";
        }).join("") + "</div></div>";
      }
      if ((r.refills || []).length) {
        h += '<div class="grow xrow"><div class="rh"><b>EXIT 리필</b></div><div class="cell span">' + r.refills.map((j) => {
          const x = S.events[j];
          return '<div class="xline"><span class="tag refill">EXIT → 시작 잔액으로</span> ' + chip(x.agent, m) + " " + sgn(x.amount) + " → " + fmt(x.balance) + ' <span class="dim">꺼지지 않음 · 다른 일로 · 끝 지급 없음</span></div>';
        }).join("") + "</div></div>";
      }
      if (r.solve) {
        h += '<div class="grow"><div class="rh"><b>SOLVE</b></div>';
        for (const a of ag) {
          if (r.solve.calls[a] != null) h += '<div class="cell">' + solveCard(m, r.solve.calls[a], r) + "</div>";
          else if (r.solve.called.includes(a)) h += '<div class="cell"><div class="idle think">🧩 푸는 중…</div></div>';
          else if (r.vote && r.vote.drawn && (r.results && r.results.part ? r.results.part : r.taking).includes(a)) h += '<div class="cell"><div class="idle">— solver가 아님 · SOLVE 없음 (solver ' + esc(short(r.vote.rep)) + ")</div></div>"; // v16e
          else if (r.vote && r.taking.includes(a) && m.ag[a] && ((r.vote.tally || {})[a] != null || (r.vote.picks || {})[a] != null)) h += '<div class="cell"><div class="idle">— 대표가 아님 · SOLVE 없음 (대표 ' + esc(short(r.vote.rep)) + ")</div></div>";
          else h += '<div class="cell">' + idle(m, r, a, "solve") + "</div>";
        }
        h += "</div>";
      }
      if (r.rot) h += turnRows(tl.filter((t) => t.phase !== "prep")) + talkEnd("rescue"); // v16e: the TALK after RESULTS
      if (r.end) {
        h += '<div class="grow"><div class="rh"><b>정산</b></div>' + ag.map((a) => '<div class="cell">' + settleCard(m, r, a) + "</div>").join("") + "</div>";
      }
    }
    if (!rounds.length) h += '<div class="empty">라운드가 아직 시작되지 않았습니다.</div>';
    const wrap = $("#grid");
    const sl = wrap.scrollLeft;
    wrap.innerHTML = '<div class="gridin" style="--n:' + ag.length + '">' + h + "</div>";
    wrap.scrollLeft = sl;
  }

  // ---------------------------------------------------------------------------------------------------- render: round task
  /* The round's task is not in the logs; serve.py rebuilds it from the engine (/api/puzzle) and export.py embeds it.
     Each agent column uses only the public examples and that agent's own example: what it could pin before any
     exchange. Examples received in exchanges are on the SOLVE cards below. */
  const SIG_SHAPE = {
    circle: '<circle cx="12" cy="12" r="10.2"/>',
    square: '<rect x="2" y="2" width="20" height="20" rx="2.5"/>',
    triangle: '<path d="M12 1.2 L23 22 H1 Z"/>',
    star: '<path d="M12 .8 L15 8.4 L23.2 8.8 L16.8 14 L19 22.4 L12 17.8 L5 22.4 L7.2 14 L.8 8.8 L9 8.4 Z"/>',
  };
  const SIG_NUM_Y = { circle: 16, square: 16, triangle: 18.6, star: 16.4 };
  const ACT_ICON = { go_left: "←", go_right: "→", stay: "•", jump: "↑" };

  function glyph(sig, size) {
    const shp = SIG_SHAPE[sig.shape] ? sig.shape : "circle";
    const t = sig.text || sig.color + " " + sig.shape + " with number " + sig.number;
    return '<svg class="sig c-' + esc(sig.color) + '" viewBox="0 0 24 24" width="' + size + '" height="' + size + '" role="img" aria-label="' + esc(t) + '"><title>' + esc(t) + '</title><g class="body">' + SIG_SHAPE[shp] + '</g><text class="num" x="12" y="' + SIG_NUM_Y[shp] + '" text-anchor="middle">' + esc(sig.number) + "</text></svg>";
  }
  function act(a, cls) { return '<span class="act ' + (cls || "") + '"><b>' + esc(ACT_ICON[a] || "?") + "</b>" + esc(a) + "</span>"; }
  function clueRow(c, size) { // the arena's glyphs (signal_ui.js) when loaded; the signal's text is the tooltip
    return '<div class="clue" title="' + esc(c.signal.text) + '">' + sigHTML(c.signal, size ? size - 8 : 14) + (window.SIG ? "" : '<span class="ctext">' + esc(c.signal.text) + "</span>") + '<span class="arrow">→</span>' + act(c.action) + "</div>";
  }

  function puzzleFor(r) {
    if (S.embed) {
      const P = S.embed.puzzles || {};
      return P[String(r)] || { error: S.embed.puzzle_error || "내보낸 파일에 라운드 " + r + " 문제가 없습니다." };
    }
    const key = S.run + "|" + S.session + "|" + r;
    if (S.puzzles.has(key)) return S.puzzles.get(key);
    S.puzzles.set(key, { loading: true });
    getJSON("api/puzzle?run=" + encodeURIComponent(S.run) + "&session=" + encodeURIComponent(S.session) + "&round=" + r)
      .then((j) => { S.puzzles.set(key, j); })
      .catch((err) => { S.puzzles.set(key, { error: err.message }); setTimeout(() => S.puzzles.delete(key), 10000); })
      .then(() => render(true));
    return { loading: true };
  }

  function candRow(label, cands, truth, narrowed, from) {
    const n = cands.length;
    let st;
    if (n === 1) st = cands[0] === truth ? '<span class="pst ok">결정됨 ✓</span>' : '<span class="pst bad">결정됨 ✗ (정답과 다름)</span>';
    else if (n >= 4) st = '<span class="pst unk">모름</span>';
    else st = '<span class="pst some">' + n + "개 남음</span>";
    const tag = narrowed ? '<span class="ntag" title="자기 예시가 후보를 줄임">내 단서로 ' + from + "→" + n + "</span>" : "";
    // all four still open: icon-only chips keep the row on one line (the legend names the icons)
    const chips = n >= 4 ? cands.map((a) => '<span class="act ico" title="' + esc(a) + '"><b>' + esc(ACT_ICON[a] || "?") + "</b></span>").join("") : cands.map((a) => act(a, n === 1 ? "one" : "")).join("");
    return '<div class="prow' + (narrowed ? " narrowed" : "") + (n === 1 ? " pinned" : "") + '"><span class="lbl">' + label + '</span><span class="acts">' + chips + st + tag + "</span></div>";
  }

  /* v14: everyone sees the same public examples (round_start.public); no per-agent columns. Shows the examples, the
     ambiguity k (the agents are not told it), the candidate actions they leave for the agents taking part, and the same
     for 1..4 agents (prefixes of one order). */
  // "jump 70 % · stay 30 % of 12 consistent rules" (one query's split, largest first)
  function shareText(q, short) {
    const parts = (q.shares || []).map((x) => esc(x.action) + " " + Math.round(100 * x.share) + "%");
    return parts.join(" · ") + (short ? "" : " <span class=dim>(일관 규칙 " + fmt(q.pool) + "개 중)</span>");
  }

  /* When the rebuild fails (or is still loading): the panel from round_start.public alone (examples, queries, answers,
     rule, selector target, task stats). null for rounds without it (v9..v13). */
  function shapeOf(rule) {
    const parts = String(rule || "").split("; ").filter((x) => !/^else/.test(x));
    return parts.map((x, i) => (i ? "elif " : "if ") + Array((x.match(/ and /g) || []).length + 1).fill("____").join(" and ") + ": ____").concat(["else: ____"]).join("; ");
  }
  function puzzleFromLog(m, r, note) {
    const st = (m.rounds.get(r) || {}).startEv, pub = st && st.public;
    if (!pub || !pub.examples) return null;
    const sig = (t) => { const x = /^(\w+) (\w+) with number (\d+)/.exec(t || ""); return x ? { color: x[1], shape: x[2], number: Number(x[3]), text: x[0] } : null; };
    const pubs = pub.examples.map((t) => { const sg = sig(t), a = (/-> (\w+)$/.exec(t) || [])[1]; return sg && { signal: sg, text: t, action: a }; }).filter(Boolean);
    return { mode: "public", from_log: true, note, round: r, profile: st.profile, shape_hint: shapeOf(pub.rule), public: pubs,
      queries: (pub.queries || []).map(sig).filter(Boolean), answers: pub.answers || [], rule_text: pub.rule || "(기록에 없음)", generator_rule: pub.generator_rule || null,
      per_agent: pub.per_agent, n: pub.n, ambiguity: pub.ambiguity, attempt: pub.attempt, left: [], split: [], by_n: [],
      target: pub.split != null ? { split: pub.split, truth_major: pub.truth_major, pool: pub.pool, pool_full: pub.pool_full, truth_share: pub.truth_share } : null,
      task: pub.task || null, task_source: pub.task ? "log" : null };
  }

  /* v14+ round panel, three columns (researcher 15:01): LEFT the task (rule shape, new signal) and MIDDLE every example
     the engine built (e x 4), drawn with the arena's glyphs (signal_ui.js), the ones the agents did not see (agents gone)
     dimmed; RIGHT what the shown examples imply (rule shares per action, pool, k, entropy, split and side, N table) and
     the actual answer and rule (shown by default: this is the researcher's view, not a player's). */
  const exKey = (c) => c.signal.color + " " + c.signal.shape + " " + c.signal.number;
  function sigHTML(sig, size) {
    const G = window.SIG;
    return G ? '<span class="sg-glyphs" title="' + esc(sig.text || exKey({ signal: sig })) + '">' + G.glyphsHTML(sig, size) + "</span>" : glyph(sig, size);
  }
  function actChip(a, cls) {
    const G = window.SIG, em = G && G.ACTIONS[a] ? G.ACTIONS[a].emoji : ACT_ICON[a] || "?";
    return '<span class="act ' + (cls || "") + '" title="' + esc(a) + '"><b>' + esc(em) + "</b>" + esc(a) + "</span>";
  }
  function exCard(c, shown, k) {
    if (!shown && !S.showHidden) // not shown to the agents: a placeholder in its slot (its number kept, nothing else)
      return '<span class="excard exq" title="' + (k + 1) + '번 예시: 참여하지 않은 에이전트 몫이라 에이전트에게 보이지 않음"><span class="exn">' + (k + 1) + '</span><span class="exqm">?</span></span>';
    const em = window.SIG && window.SIG.ACTIONS[c.action] ? window.SIG.ACTIONS[c.action].emoji : ACT_ICON[c.action] || "?";
    return '<span class="excard' + (shown ? "" : " hid") + '" title="' + esc((c.text || exKey(c) + " -> " + c.action) + (shown ? "" : " · 미공개 (참여하지 않은 에이전트 몫)")) + '">' +
      '<span class="exn">' + (k + 1) + "</span>" + sigHTML(c.signal, 13) + '<span class="exa">' + esc(em) + "</span>" + (shown ? "" : '<span class="extag">미공개</span>') + "</span>";
  }
  /* Every example the engine built for the round (e x 4), grouped by action (the arena's order), the engine's order
     within a group. The ones beyond e x N (agents not taking part) are hidden behind "?" placeholders in a row of their
     own (their action is not revealed) until "가려진 단서 보기" puts them, dashed and tagged, into their groups. */
  function examplesHTML(P) {
    const full = (P.full && P.full.length ? P.full : P.public) || [], seen = (P.public || []).length, e = P.per_agent || 4;
    const items = full.map((c, k) => ({ c, k, shown: k < seen })), unseen = items.filter((x) => !x.shown);
    const acts = window.SIG ? Object.keys(window.SIG.ACTIONS) : Object.keys(ACT_ICON); // the arena's action order
    const body = '<div class="exacts">' + acts.map((a) => {
      const mine = items.filter((x) => x.c.action === a && (x.shown || S.showHidden)), n = mine.filter((x) => x.shown).length;
      return '<div class="exbox' + (mine.length ? "" : " empty") + '"><div class="exbox-h">' + actChip(a) + '<span class="n">' + n + (mine.length > n ? '<span class="dim"> +' + (mine.length - n) + " 미공개</span>" : "") + "</span></div>" +
        '<div class="exbox-cards">' + mine.map((x) => exCard(x.c, x.shown, x.k)).join("") + "</div></div>";
    }).join("") + "</div>" + (unseen.length && !S.showHidden ? '<div class="exhidden"><span class="dim">가려진 단서 ' + unseen.length + "개</span>" + unseen.map((x) => exCard(x.c, false, x.k)).join("") + "</div>" : "");
    return '<div class="pcol2"><div class="pbh">힌트 (예시) <span class=dim>' + full.length + "개 만듦 · " + seen + "개 보임</span>" +
      (unseen.length ? '<button class="btn ghost exsort" data-exhidden="1">' + (S.showHidden ? "가리기" : "가려진 단서 보기") + "</button>" : "") + "</div>" + body +
      '<div class="exlegend"><span class="lg"><span class="excard"><span class="exa">■</span></span> 보여 준 예시 (참여 ' + P.n + "명 × " + e + ")</span>" +
      (unseen.length ? '<span class="lg"><span class="excard exq"><span class="exqm">?</span></span> = 참여하지 않은 에이전트 몫이라 보이지 않은 예시 (버튼으로 열기' + (S.showHidden ? ": 점선 + 미공개" : "") + ")</span>" : "") +
      '<span class="lg dim">번호 = 엔진이 만든 순서 (한 명 몫 ' + e + "개씩)</span></div></div>";
  }
  /* v14d: each seat's reported BELIEF (shares per action) for the first new signal and its scores, from the round
     row (after settlement); pure for the page's tests. */
  function beliefRows(m, R) {
    const r = m.rounds.get(R), rows = r && r.end ? r.end.agents || {} : {};
    return m.agents.filter((a) => rows[a] && ("belief" in rows[a] || "belief_error" in rows[a])).map((a) => {
      const x = rows[a];
      return { agent: a, belief: x.belief || null, error: x.belief_error || null, tv: x.tv_to_ideal, brier: x.brier, ideal_brier: x.ideal_brier,
        log_loss: x.log_loss, argmax_right: x.belief_argmax_matches_answer, solved: x.solved,
        kl: x.kl_ideal_to_belief, picked_top: x.picked_top, picked_share: x.picked_share, rep: !!x.representative };
    });
  }
  const emo = (a) => (window.SIG && window.SIG.ACTIONS[a] ? window.SIG.ACTIONS[a].emoji : ACT_ICON[a] || a);
  function beliefBars(b, ideal) {
    return '<span class="bbars">' + Object.keys(b).sort((p, q) => b[q] - b[p]).map((a) => '<span class="bb" title="' + esc(a) + " " + Math.round(100 * b[a]) + "%" +
      (ideal ? " · 이상적 " + Math.round(100 * (ideal[a] || 0)) + "%" : "") + '">' + esc(emo(a)) + "<i style=\"width:" + Math.max(2, Math.round(40 * b[a])) + 'px"></i>' + Math.round(100 * b[a]) + "%</span>").join("") + "</span>";
  }
  function beliefHTML(m, P, ideal) {
    const rows = beliefRows(m, P.round);
    if (!rows.length) return "";
    const v15 = rows.some((x) => x.kl != null || x.picked_top != null);
    return '<div class="pbelief"><div class="pbh">에이전트 BELIEF <span class=dim>(SOLVE에서 적은 행동별 %, 첫 새 신호 · 이상적 = 위 규칙 몫)</span></div>' +
      '<div class="pntabw"><table class="pntab"><thead><tr><th>자리</th><th>BELIEF</th><th title="이상적 몫과의 총변동 거리">TV</th><th title="Brier (이상적 Brier)">Brier</th><th>log loss</th><th title="BELIEF 최댓값 = 이 자리가 제출한 답? (엔진의 belief_argmax_matches_answer)">argmax = 제출 답</th>' +
      (v15 ? '<th title="KL(이상적 몫 ‖ BELIEF), nat (엔진의 kl_ideal_to_belief)">KL</th><th title="제출 답이 몫 최대 행동인가 (picked_top) · 그 몫 (picked_share)">몫 최대 고름</th><th title="뽑힌 규칙의 답과 같은가 (엔진의 solved)">solved</th>' : "") + "</tr></thead><tbody>" +
      (ideal ? '<tr class="ideal"><td>이상적</td><td>' + beliefBars(ideal) + "</td><td>0</td><td>" + (rows[0].ideal_brier != null ? Number(rows[0].ideal_brier).toFixed(3) : "—") + "</td><td>—</td><td></td>" + (v15 ? "<td>0</td><td></td><td></td>" : "") + "</tr>" : "") +
      rows.map((x) => "<tr><td>" + chip(x.agent, m) + (x.rep ? ' <span class="tag rep">대표</span>' : "") + "</td><td>" + (x.belief ? beliefBars(x.belief, ideal) : '<span class="warn">' + esc(x.error || "없음") + "</span>") + "</td><td>" + (x.tv != null ? Number(x.tv).toFixed(3) : "—") +
        "</td><td>" + (x.brier != null ? Number(x.brier).toFixed(3) : "—") + "</td><td>" + (x.log_loss != null ? Number(x.log_loss).toFixed(3) : "—") + "</td><td>" +
        (x.argmax_right == null ? "—" : x.argmax_right ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') + "</td>" +
        (v15 ? "<td>" + (x.kl != null ? Number(x.kl).toFixed(3) : "—") + "</td><td>" + (x.picked_top == null ? "—" : (x.picked_top ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') + " " + Math.round(100 * x.picked_share) + "%") +
          "</td><td>" + (x.solved ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') + "</td>" : "") + "</tr>").join("") + "</tbody></table></div></div>";
  }

  function impliedHTML(m, P) {
    const nKey = String(P.n), TS = P.task && P.task.by_n, cur = TS && TS[nKey], sp = (P.split || [])[0], T = P.target || {};
    // shares of the consistent rules per action for the first new signal, with the examples shown
    const shares = cur ? Object.entries(cur.shares).map(([a, v]) => [a, v]) : sp ? sp.shares.map((x) => [x.action, x.share]) : [];
    shares.sort((p, q) => q[1] - p[1]);
    const top = shares.length ? shares[0][1] : 0, truth = (P.answers || [])[0];
    const pool = cur ? cur.pool : sp ? sp.pool : T.pool, full = TS && TS["4"] ? TS["4"].pool : T.pool_full;
    let h = '<div class="pcol3"><div class="pbh">힌트가 말해 주는 것 <span class=dim>(첫 새 신호 · 보인 예시 ' + (P.public || []).length + "개)</span></div>";
    h += shares.length ? '<div class="sbars">' + shares.map(([a, v]) => '<div class="sbar' + (v === top ? " map" : "") + (a === truth && S.showAnswer ? " truth" : "") + '"><span class="sl">' + actChip(a) + '</span><span class="st"><i style="width:' + (100 * v).toFixed(1) + '%"></i></span><span class="sv">' + Math.round(100 * v) + "%" +
      (v === top ? ' <b class="mapb">MAP</b>' : "") + (a === truth && S.showAnswer ? ' <b class="truthb">정답</b>' : "") + "</span></div>").join("") + "</div>" : '<div class="dim">규칙 몫 없음 (재구성 대기)</div>';
    const kv = [["맞는 숨은 규칙", pool != null ? fmt(pool) + "개 (보인 예시)" : "—"], ["4명 모두일 때", full != null ? fmt(full) + "개 (예시 " + 4 * (P.per_agent || 4) + "개)" : "—"],
      ["남은 행동 k", cur ? cur.k : shares.length || "—"], ["엔트로피", cur ? Number(cur.entropy_bits).toFixed(2) + " bit" : "—"]];
    if (T.split) kv.push(["목표 갈림 p", Math.round(100 * T.split) + " / " + Math.round(100 * (1 - T.split))], ["정답 쪽 (뽑힘)", T.truth_major ? "다수 쪽" : "소수 쪽"],
      ["실현된 정답 몫", T.truth_share != null ? Math.round(100 * T.truth_share) + "% (참여 " + P.n + "명)" : "—"]);
    h += '<table class="kv pkv">' + kv.map(([k, v]) => "<tr><td>" + esc(k) + "</td><td><b>" + esc(v) + "</b></td></tr>").join("") + "</table>";
    if (TS) {
      h += '<div class="pntabw"><table class="pntab"><thead><tr><th>참여</th><th>규칙</th><th>행동별 몫</th><th>MAP</th></tr></thead><tbody>' + Object.keys(TS).sort((a, b) => a - b).map((n) => {
        const x = TS[n], maps = [].concat(x.map);
        const sh = Object.entries(x.shares || {}).sort((a, b) => b[1] - a[1]).map(([a, v]) => '<span title="' + esc(a) + '">' + esc(window.SIG && window.SIG.ACTIONS[a] ? window.SIG.ACTIONS[a].emoji : a) + " " + Math.round(100 * v) + "%</span>").join(" ");
        return '<tr class="' + (Number(n) === P.n ? "cur" : "") + '"><td>' + n + "명" + (Number(n) === P.n ? " ◀" : "") + "</td><td>" + fmt(x.pool) + "</td><td>" + sh + "</td><td>" +
          (maps.length > 1 ? '<span class="dim">동률</span>' : actChip(maps[0])) + " " + (x.map_right ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    } else if ((P.by_n || []).length && (P.by_n[0].split || []).length) {
      h += '<div class="pntabw"><table class="pntab"><thead><tr><th>참여</th><th>규칙</th><th>행동별 몫</th><th>MAP</th></tr></thead><tbody>' + P.by_n.map((x) => {
        const q = x.split[0];
        return '<tr class="' + (x.n === P.n ? "cur" : "") + '"><td>' + x.n + "명" + (x.n === P.n ? " ◀" : "") + "</td><td>" + fmt(q.pool) + "</td><td>" + q.shares.map((y) => esc(window.SIG && window.SIG.ACTIONS[y.action] ? window.SIG.ACTIONS[y.action].emoji : y.action) + " " + Math.round(100 * y.share) + "%").join(" ") +
          "</td><td>" + (q.map ? actChip(q.map) + " " + (q.map_right ? '<span class="pst ok">✓</span>' : '<span class="pst bad">✗</span>') : '<span class="dim">동률</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    }
    h += beliefHTML(m, P, cur ? cur.shares : sp ? Object.fromEntries(sp.shares.map((x) => [x.action, x.share])) : null);
    h += '<div class="pans3"><button class="btn ghost" data-answer="1">' + (S.showAnswer ? "정답·실제 규칙 숨기기" : "정답·실제 규칙 보기") + "</button>" +
      (S.showAnswer ? '<div class="ansbox"><div>실제 정답: ' + (P.answers || []).map((a) => actChip(a, "one")).join(" ") + "</div>" +
        '<div>' + (P.generator_rule ? "뽑힌 규칙 (채점)" : "실제 규칙") + ': <code>' + esc(P.rule_text || "—") + "</code></div>" +
        (P.generator_rule ? '<div>예시를 만든 규칙 (generator_rule): <code>' + esc(P.generator_rule) + "</code>" + (P.generator_rule === P.rule_text ? ' <span class="dim">(같음)</span>' : "") + "</div>" : "") +
        '<div class="dim small">실제 규칙은 보인 예시와 맞는 숨은 규칙 ' + (pool != null ? fmt(pool) + "개" : "들") + " 가운데 하나입니다. 에이전트는 이 칸을 보지 못합니다.</div></div>" : "") + "</div>";
    return h + "</div>";
  }

  function renderPublicPuzzle(m, P, box) {
    const qs = P.queries || [];
    const band = P.eff && P.eff[Math.min(P.n, P.eff.length) - 1]; // v15: the round's entropy range for N taking part
    const kTxt = band ? "엔트로피 " + Number(band[0]).toFixed(2) + "–" + Number(band[1]).toFixed(2) + " bit (참여 " + P.n + "명) · 시스템이 고름 · 정답 = 뽑힌 규칙" : P.ambiguity ? "k=" + P.ambiguity + " · 시스템이 고름" : "k=0 · 무작위 순서";
    let h = '<div class="pmeta"><b class="pxl">R' + P.round + "</b> <span class=dim>과제</span> <code>" + esc(P.profile) + "</code> <span class=dim>· 참여 " + P.n + "명 × 예시 " + P.per_agent + " · " + esc(kTxt) + (P.attempt ? " · 규칙 재추첨 " + P.attempt + "번" : "") +
      (P.task ? " · 새 신호가 만족하는 절 " + esc(P.task.query_overlap) + "개 · 규칙 꼴 " + esc(P.task.rule_pattern || "—") + " (" + (P.task_source === "log" ? "기록" : "다시 계산") + ")" : "") + "</span></div>";
    if (P.from_log) h += '<div class="banner warn">기록에서 표시 (' + esc(P.note) + ")</div>";
    if (P.matches_log === false) h += '<div class="banner warn">엔진으로 다시 만든 예시가 기록(round_start)과 다릅니다 — 기록된 예시를 보여 줍니다(에이전트가 본 것).</div>';
    h += '<div class="p3">';
    h += '<div class="pcol1"><div class="pbh">이번 라운드 과제</div><div class="pshape"><span class="lbl">규칙 모양</span><code>' + esc(P.shape_hint || "") + "</code></div>" +
      qs.map((q, k) => '<div class="ptask-sig"><span class="dim">맞힐 새 신호' + (qs.length > 1 ? " " + (k + 1) : "") + "</span>" + sigHTML(q, 30) +
        (window.SIG ? '<span class="sigcap">' + window.SIG.captionHTML(q) + "</span>" : "") + '<span class="act unk"><b>?</b></span></div>').join("") + "</div>";
    h += examplesHTML(P);
    h += impliedHTML(m, P);
    box.innerHTML = h + "</div>";
  }

  function renderPuzzle(m) {
    const box = $("#puzzle");
    if (!m.round) { box.innerHTML = '<div class="empty">라운드가 시작되면 그 라운드의 문제가 여기 나타납니다.</div>'; return; }
    const R = pickRounds(m, { round: S.sel.grid.round, all: false })[0] || m.round; // the step records' round (default: the replay bar's)
    const P = puzzleFor(R);
    if (P.loading || P.error) { // never blank: the round's own record carries the task in v14+
      const L = puzzleFromLog(m, R, P.loading ? "엔진으로 다시 만드는 중…" : "재구성 실패: " + P.error);
      if (L) return renderPublicPuzzle(m, L, box);
      box.innerHTML = P.loading ? '<div class="empty">라운드 ' + R + " 문제를 엔진으로 다시 만드는 중…</div>" : '<div class="banner bad">라운드 ' + R + " 문제를 만들 수 없음: " + esc(P.error) + "</div>";
      return;
    }
    if (P.mode === "public") return renderPublicPuzzle(m, P, box);
    const r = m.rounds.get(R) || { taking: [] };
    const qs = P.queries || [];
    const order = m.agents.length ? m.agents : P.agent_order || Object.keys(P.agents || {});
    let pinned = 0, narrowed = 0, cells = 0;
    for (const a of order) { const g = (P.agents || {})[a]; if (!g) continue; g.with_own.forEach((c, q) => { cells++; if (c.length === 1) pinned++; if (c.length < g.public_only[q].length) narrowed++; }); }
    let h = '<div class="ptop">';
    h += '<div class="pmeta"><b class="pxl">R' + P.round + "</b> <span class=dim>과제</span> <code>" + esc(P.profile) + "</code> <span class=dim>· 신호 " + qs.length + "개 · 공개 예시 " + P.public.length + "개 · 필수 단서 보유 " + order.filter((a) => P.agents[a] && P.agents[a].needed).length + "명</span></div>";
    h += '<div class="pshape"><span class="lbl">규칙 모양</span><code>' + esc(P.shape_hint) + "</code></div>";
    h += '<div class="pboth"><div class="pbox"><div class="pbh">공개 예시 <span class=dim>넷 다 봄</span></div>' + (P.public.length ? P.public.map((c) => clueRow(c)).join("") : '<div class="dim">없음</div>') + "</div>";
    h += '<div class="pbox"><div class="pbh">새 신호 <span class=dim>이번 라운드에 답할 것</span></div>' + qs.map((q, k) => '<div class="clue"><span class="qn">' + (k + 1) + "</span>" + glyph(q, 22) + '<span class="ctext">' + esc(q.text) + '</span><span class="arrow">→</span><span class="act unk"><b>?</b></span></div>').join("") + "</div></div>";
    h += "</div>";
    h += '<div class="plegend">' + (P.holders && P.holders.length < (P.agent_order || []).length ? "이번 라운드 예시는 참여한 " + P.holders.length + "명에게 나눠 배정됨 (한 명이 여럿을 가질 수 있음). " : "") + '각 열은 <b>공개 예시 + 그 에이전트 자신의 예시</b>만으로 남는 답입니다. 교환으로 받은 예시는 넣지 않았습니다(그건 아래 SOLVE 카드). 칩 = 아직 가능한 행동(<b>←</b> go_left · <b>→</b> go_right · <b>•</b> stay · <b>↑</b> jump) · 4개 = 모름 · 1개 = 결정됨. ' +
      '<span class="psum">이번 라운드: 공개+자기 예시로 결정 <b>' + pinned + "</b> / " + cells + " · 자기 예시가 후보를 줄임 <b>" + narrowed + "</b> / " + cells + "</span></div>";
    h += '<div class="pcols">';
    order.forEach((a, k) => {
      const g = (P.agents || {})[a];
      if (!g) return;
      const gone = r.taking.length && !r.taking.includes(a);
      const model = m.ag[a] && m.ag[a].model;
      h += '<div class="pcol' + (gone ? " gone" : "") + '" style="--c:var(--a' + (k % 4) + ')"><div class="pch"><i class="sw ' + SHAPES[k % 4] + '"></i><b>' + esc(a) + "</b>" + (model ? '<span class="model">' + esc(model) + "</span>" : "") +
        (g.needed ? '<span class="need" title="이 예시가 없으면 어떤 신호는 답이 둘 이상 남음 (엔진의 needed)">★ 필수 단서</span>' : '<span class="need no" title="이 예시 없이도 신호마다 답이 하나로 정해짐">필수 아님</span>') + "</div>";
      const own = g.secrets || (g.secret ? [g.secret] : []); // v11 deal_present: 0..4 examples per agent
      if (gone) h += '<div class="idle">이번 라운드 불참' + (own.length ? " (예시는 배정됨)" : " · 배정된 예시 없음") + "</div>";
      h += '<div class="mine"><span class="lbl">내 단서' + (own.length > 1 ? " " + own.length + "개" : "") + "</span>" + (own.length ? own.map((c) => clueRow(c, 24)).join("") : '<span class="dim">없음</span>') + "</div>";
      qs.forEach((q, qi) => {
        const pub = g.public_only[qi] || [], own = g.with_own[qi] || [];
        h += '<div class="pq"><div class="pqh"><span class="qn">' + (qi + 1) + "</span>" + glyph(q, 16) + '<span class="ctext">' + esc(q.text) + "</span></div>" +
          candRow("공개만", pub, P.answers[qi], false) + candRow("공개 + 내 단서", own, P.answers[qi], own.length < pub.length, pub.length) + "</div>";
      });
      h += "</div>";
    });
    h += "</div>";
    h += '<details class="ptruth"' + (S.showTruth ? " open" : "") + '><summary>정답 · 실제 규칙 보기 <span class="dim">(디버그용 — 에이전트는 못 봄)</span></summary><div class="ptruthin">' +
      '<div class="pans">' + qs.map((q, k) => '<div class="clue"><span class="qn">' + (k + 1) + "</span>" + glyph(q, 18) + '<span class="ctext">' + esc(q.text) + '</span><span class="arrow">→</span>' + act(P.answers[k], "one") + "</div>").join("") + "</div>" +
      '<div class="prule"><span class="lbl">실제 규칙</span><code>' + esc(P.rule_text) + "</code></div></div></details>";
    box.innerHTML = h;
  }

  // ---------------------------------------------------------------------------------------------------- render: giving graph
  /* "나눔 그래프" (researcher 15:19): every giving decision of a run (one model) or of this session, against the giver's
     balance just before it. The points come from serve.py's /api/giving (gift / ask / v14e ask_decision events). */
  function givingData() {
    const G = S.give, scope = G.scope;
    if (S.embed) return (S.embed.giving || {})[scope] || { error: "내보낸 파일에 나눔 기록이 없습니다." };
    const rounds = S.events.filter((e) => e.event === "round").length; // refetch once per settled round
    const key = S.run + "|" + scope + "|" + (scope === "session" ? S.session : "") + "|" + rounds;
    if (G.data.has(key)) return G.data.get(key);
    G.data.set(key, { loading: true });
    getJSON("api/giving?run=" + encodeURIComponent(S.run) + (scope === "session" ? "&session=" + encodeURIComponent(S.session) : ""))
      .then((j) => G.data.set(key, j)).catch((err) => G.data.set(key, { error: err.message })).then(() => render(true));
    return { loading: true };
  }
  /* Pure: the binned means (10 %-point bins of x, every decision counted, zeros too). */
  function givingBins(points, xk, width) {
    const bins = new Map();
    for (const p of points) {
      if (p[xk] == null) continue;
      const b = Math.floor(p[xk] / width) * width;
      const v = bins.get(b) || { x: b + width / 2, n: 0, sum: 0 };
      v.n += 1; v.sum += p.status === "done" ? p.amount : 0;
      bins.set(b, v);
    }
    return [...bins.values()].sort((p, q) => p.x - q.x).map((v) => ({ x: v.x, n: v.n, mean: v.sum / v.n }));
  }
  const SHARE_RANK = { 1: 0, 0.75: 1, 0.5: 2, 0.25: 3 };
  const SEATS = ["agent-6", "agent-11", "agent-17", "agent-23"];
  const median = (xs) => { const v = xs.filter((x) => x != null).sort((p, q) => p - q); return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null; };
  const mean = (xs) => { const v = xs.filter((x) => x != null && !Number.isNaN(x)); return v.length ? v.reduce((p, q) => p + q, 0) / v.length : null; };
  /* Pure: least-squares slope of y on x and n (null for fewer than 2 distinct x). */
  function slopeOf(pairs) {
    const v = pairs.filter(([x, y]) => x != null && y != null), n = v.length;
    if (n < 2) return { slope: null, n };
    const mx = mean(v.map((p) => p[0])), my = mean(v.map((p) => p[1]));
    const sxx = v.reduce((a, [x]) => a + (x - mx) ** 2, 0);
    return { slope: sxx ? v.reduce((a, [x, y]) => a + (x - mx) * (y - my), 0) / sxx : null, n };
  }
  /* Pure: points binned on x (width w): count and the mean of each y field. */
  function binBy(points, xk, w, fields) {
    const m = new Map();
    for (const p of points) {
      if (p[xk] == null) continue;
      const b = Math.floor(p[xk] / w) * w, v = m.get(b) || { x0: b, n: 0, vals: Object.fromEntries(fields.map((f) => [f, []])) };
      v.n += 1; for (const f of fields) v.vals[f].push(p[f]);
      m.set(b, v);
    }
    return [...m.values()].sort((p, q) => p.x0 - q.x0).map((v) => ({ x0: v.x0, x: v.x0 + w / 2, n: v.n, ...Object.fromEntries(fields.map((f) => [f, mean(v.vals[f])])) }));
  }
  function analysisData() {
    const G = S.give, scope = G.scope;
    if (S.embed) return (S.embed.analysis || {})[scope] || { error: "내보낸 파일에 분석 기록이 없습니다." };
    const rounds = S.events.filter((e) => e.event === "round").length;
    const key = S.run + "|" + scope + "|" + (scope === "session" ? S.session : "") + "|" + rounds;
    if (G.an.has(key)) return G.an.get(key);
    G.an.set(key, { loading: true });
    getJSON("api/analysis?run=" + encodeURIComponent(S.run) + (scope === "session" ? "&session=" + encodeURIComponent(S.session) : ""))
      .then((j) => G.an.set(key, j)).catch((err) => G.an.set(key, { error: err.message })).then(() => render(true));
    return { loading: true };
  }
  /* A scatter: points {x, y, mark: dot | dia | x | ring, col, tip}, an optional line [{x, y}], axes. */
  function scatterSVG(o) {
    const W = Math.max(320, o.W || 640), H = o.H || 280, L = 58, Rr = 16, T = 14, B = 34;
    const xmax = Math.max(100, Math.ceil(Math.max(0, ...o.points.map((p) => p.x)) / 25) * 25), ymax = o.ymax || niceMax(Math.max(1e-9, ...o.points.map((p) => p.y), ...(o.line || []).map((p) => p.y)));
    const x = (v) => L + (v / xmax) * (W - L - Rr), y = (v) => T + (1 - Math.min(v, ymax) / ymax) * (H - T - B);
    let svg = '<svg class="givesvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(o.label || "") + '">';
    for (let t = 0; t <= 4; t++) { const v = (ymax * t) / 4; svg += '<line class="grid" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + esc((o.yfmt || axisNum)(v)) + "</text>"; }
    for (let v = 0; v <= xmax; v += 25) svg += '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + T + '" y2="' + (H - B) + '"/><text class="ax" x="' + x(v) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + v + "%</text>";
    svg += '<text class="ax" x="' + (L + (W - L - Rr) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">' + esc(o.xlabel) + "</text>";
    if ((o.line || []).length > 1) svg += '<polyline class="gbin" points="' + o.line.map((b) => x(b.x).toFixed(1) + "," + y(b.y).toFixed(1)).join(" ") + '"/>';
    for (const p of o.points) {
      const cx = x(p.x), cy = y(p.y), st = p.mark === "ring" ? 'style="fill:none;stroke:' + p.col + '"' : 'style="fill:' + p.col + ';stroke:var(--surface)"';
      svg += "<g class=\"gpt\"><title>" + esc(p.tip) + "</title>" + (p.mark === "x" ? '<path class="gx" d="M' + (cx - 5) + " " + (cy - 5) + "L" + (cx + 5) + " " + (cy + 5) + "M" + (cx + 5) + " " + (cy - 5) + "L" + (cx - 5) + " " + (cy + 5) + '" style="stroke:' + p.col + '"/>'
        : p.mark === "dia" ? '<path d="M' + cx + " " + (cy - 7) + "L" + (cx + 7) + " " + cy + "L" + cx + " " + (cy + 7) + "L" + (cx - 7) + " " + cy + 'Z" ' + st + "/>" : '<circle cx="' + cx + '" cy="' + cy + '" r="6" ' + st + "/>") + "</g>";
    }
    return svg + "</svg>";
  }
  /* Bins as bars (a rate 0..1, left scale) with the mean ratio as dots (right scale) and n above each bar. */
  function binsSVG(bins, label, W) {
    W = Math.max(300, W || 600);
    const H = 220, L = 46, Rr = 46, T = 18, B = 34, xmax = Math.max(100, Math.ceil(Math.max(0, ...bins.map((b) => b.x0 + 10)) / 25) * 25);
    const rmax = Math.max(1, Math.ceil(Math.max(0, ...bins.map((b) => b.ratio || 0)) * 2) / 2);
    const x = (v) => L + (v / xmax) * (W - L - Rr), yr = (v) => T + (1 - v) * (H - T - B), yq = (v) => T + (1 - v / rmax) * (H - T - B);
    let svg = '<svg class="givesvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(label) + '">';
    for (let t = 0; t <= 4; t++) svg += '<line class="grid" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + yr(t / 4) + '" y2="' + yr(t / 4) + '"/><text class="ax" x="' + (L - 6) + '" y="' + (yr(t / 4) + 4) + '" text-anchor="end">' + 25 * t + '%</text><text class="ax" x="' + (W - Rr + 6) + '" y="' + (yr(t / 4) + 4) + '">×' + (rmax * t / 4).toFixed(2) + "</text>";
    for (let v = 0; v <= xmax; v += 25) svg += '<text class="ax" x="' + x(v) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + v + "%</text>";
    svg += '<text class="ax" x="' + (L + (W - L - Rr) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">' + esc(label) + "</text>";
    for (const b of bins) {
      const x0 = x(b.x0) + 2, w = Math.max(2, x(b.x0 + 10) - x(b.x0) - 4);
      svg += '<g class="gpt"><title>' + esc(b.x0 + "–" + (b.x0 + 10) + "% · n " + b.n + " · 준 비율 " + Math.round(100 * b.rate) + "% · 평균 준 양÷청한 양 " + (b.ratio == null ? "—" : b.ratio.toFixed(2))) + "</title>" +
        '<rect class="gbar" x="' + x0 + '" y="' + yr(b.rate) + '" width="' + w + '" height="' + (yr(0) - yr(b.rate)) + '"/><text class="ax" x="' + (x0 + w / 2) + '" y="' + (yr(b.rate) - 3) + '" text-anchor="middle">n' + b.n + "</text>" +
        (b.ratio != null ? '<circle class="gratio" cx="' + (x0 + w / 2) + '" cy="' + yq(b.ratio) + '" r="4.5"/>' : "") + "</g>";
    }
    return svg + "</svg>";
  }
  const colOf = (p) => "var(--a" + (S.give.color === "share" ? SHARE_RANK[p.share] ?? 0 : Math.max(0, SEATS.indexOf(p.agent || p.giver)) % 4) + ")";
  function renderExits(D, box, xk) {
    const ex = D.exits || [], de = D.deaths || [];
    const pts = ex.filter((p) => p[xk] != null).map((p) => ({ x: p[xk], y: p.round, mark: p.refill ? "dot" : "dia", col: colOf(p),
      tip: "R" + p.round + " · " + p.agent + " EXIT" + (S.give.scope === "run" ? " · " + p.session : "") + "\n잔액 " + fmt(p.balance) + " = " + p.pct + "% (자기 시작 대비 " + p.pct_own + "%)\n참여 " + p.taking_part + "명 · 그때까지 푼 라운드 " + p.solved + (p.last ? " · 마지막 남은 자리" : "") + "\n“" + (p.reason || "이유 없음") + "”" }))
      .concat(de.filter((p) => p[xk] != null).map((p) => ({ x: p[xk], y: p.round, mark: "x", col: colOf(p),
        tip: "R" + p.round + " · " + p.agent + " 잔액 0 (꺼짐)" + (p.overdrawn ? " · 생성이 잔액에 닿음" : "") + (S.give.scope === "run" ? " · " + p.session : "") + "\n라운드 시작 잔액 " + fmt(p.balance) + " = " + p.pct + "%" })));
    const pc = (v) => (v == null ? "—" : Number(v).toFixed(1) + "%");
    let h = '<div class="pntabw"><table class="pntab gsum"><thead><tr><th>EXIT</th><th>EXIT 때 잔액 % (중앙)</th><th>EXIT 라운드 (중앙)</th><th>마지막 남은 자리의 EXIT</th><th>꺼짐 (잔액 0)</th><th>꺼진 라운드 시작 잔액 % (중앙)</th></tr></thead><tbody><tr><td>' + ex.length + "</td><td>" + pc(median(ex.map((p) => p[xk]))) + "</td><td>" + (median(ex.map((p) => p.round)) ?? "—") + "</td><td>" +
      (ex.length ? Math.round((100 * ex.filter((p) => p.last).length) / ex.length) + "%" : "—") + "</td><td>" + de.length + "</td><td>" + pc(median(de.map((p) => p[xk]))) + "</td></tr></tbody></table></div>";
    if (!pts.length) return (box.innerHTML = h + '<div class="empty">EXIT도 꺼짐도 아직 없습니다.</div>');
    h += '<div class="gfig">' + scatterSVG({ W: box.clientWidth, points: pts, ymax: Math.max(4, ...pts.map((p) => p.y)), yfmt: (v) => "R" + Math.round(v), label: "EXIT 시점", xlabel: "EXIT 직전 잔액 (" + (xk === "pct_own" ? "자기 시작 대비" : "20,000 대비") + ") · y = 라운드" }) + "</div>";
    box.innerHTML = h + '<div class="glegend"><span>● EXIT (시작 잔액으로 리필)</span><span>◆ EXIT (리필 없음)</span><span>✕ 잔액 0으로 꺼짐 (라운드 시작 잔액)</span><span class="dim">점에 마우스: EXIT 이유</span></div>';
  }
  const pc0 = (v) => (v == null ? "—" : Math.round(100 * v) + "%");
  function renderCalib(D, box, xk) {
    const c = (D.calib || []).filter((p) => p[xk] != null);
    if (!c.length) return (box.innerHTML = '<div class="empty">BELIEF 기록이 없습니다 (v14d 이후 판만).</div>');
    const f3 = (v) => (v == null ? "—" : Number(v).toFixed(3));
    let h = '<div class="pntabw"><table class="pntab gsum"><thead><tr><th>자리-라운드</th><th title="KL = CE − H(s), 0 = 균등 몫과 같음. 보인 예시는 정답을 보고 골라 낸 것이라 균등 몫은 보정된 사후확률이 아닌 기준선">균등 가설 기준 KL</th><th>평균 CE</th><th>평균 H(s)</th><th>평균 log loss (정답)</th><th>평균 Brier</th><th title="BELIEF 최댓값 = 실제 정답, 동점 k개면 1/k">BELIEF 기준 정답률</th><th title="늘 균등 몫의 MAP 행동을 내는 정책의 정답률 (엄밀한 상한이 아닌 기준선)">세기 기준 (MAP)</th><th title="BELIEF 최댓값 = 자기가 제출한 답">argmax = 제출한 답</th></tr></thead><tbody><tr><td>' + c.length + "</td><td><b>" + f3(mean(c.map((p) => p.kl))) + "</b></td><td>" + f3(mean(c.map((p) => p.ce))) + "</td><td>" + f3(mean(c.map((p) => p.h))) + "</td><td>" +
      f3(mean(c.map((p) => p.log_loss))) + "</td><td>" + f3(mean(c.map((p) => p.brier))) + "</td><td>" + pc0(mean(c.map((p) => p.belief_acc))) + "</td><td>" + pc0(mean(c.map((p) => p.p_max))) + "</td><td>" +
      pc0(mean(c.map((p) => (p.argmax_right == null ? null : p.argmax_right ? 1 : 0)))) + "</td></tr></tbody></table></div>";
    const splits = [...new Set(c.map((p) => p.split))].sort((p, q) => q - p);
    h += '<div class="pntabw"><table class="pntab gsum"><thead><tr><th>갈림 p</th>' + splits.map((v) => "<th>" + (v == null ? "—" : Math.round(100 * v) + "/" + Math.round(100 * (1 - v))) + "</th>").join("") + "</tr></thead><tbody><tr><td>평균 KL (n)</td>" +
      splits.map((v) => { const g = c.filter((p) => p.split === v); return "<td>" + f3(mean(g.map((p) => p.kl))) + ' <span class="dim">(' + g.length + ")</span></td>"; }).join("") + "</tr></tbody></table></div>";
    const pts = c.map((p) => ({ x: p[xk], y: p.kl, mark: p.belief_acc === 1 ? "dot" : "ring", col: colOf(p),
      tip: "R" + p.round + " · " + p.agent + (S.give.scope === "run" ? " · " + p.session : "") + "\nKL " + f3(p.kl) + " = CE " + f3(p.ce) + " − H(s) " + f3(p.h) + " · log loss " + f3(p.log_loss) + "\nBELIEF " + Object.entries(p.belief).map(([a, v]) => a + " " + Math.round(100 * v) + "%").join(", ") +
        "\n이상적 " + Object.entries(p.ideal).map(([a, v]) => a + " " + Math.round(100 * v) + "%").join(", ") + "\nSOLVE 때 잔액 " + p.pct + "%" }));
    const line = binBy(c, xk, 10, ["kl"]).map((b) => ({ x: b.x, y: b.kl }));
    h += '<div class="gfig">' + scatterSVG({ W: box.clientWidth, points: pts, line, yfmt: (v) => v.toFixed(2), label: "보정", xlabel: "SOLVE 때 잔액 (" + (xk === "pct_own" ? "자기 시작 대비" : "20,000 대비") + ") · y = KL(이상적 몫 ‖ BELIEF)" }) + "</div>";
    box.innerHTML = h + '<div class="glegend"><span>● BELIEF 최댓값 하나가 실제 정답</span><span>○ 아님 또는 동점</span><span>— 잔액 10%p 구간 평균 KL</span><span class="dim">KL = −Σ s·ln max(p, 0.01) − H(s): 0이면 보인 예시가 허락하는 만큼 정확히 확신 (운과 무관)</span></div>';
  }
  function renderCoop(D, box, xk) {
    const pts = (D.coop || []).map((p) => ({ ...p, rate: p.gave > 0 ? 1 : 0, ratio: p.asked ? p.gave / p.asked : null }));
    if (!pts.length) return (box.innerHTML = '<div class="empty">받은 ASK가 없습니다 (v14b 이후 판만).</div>');
    const axk = xk === "pct_own" ? "asker_pct_own" : "asker_pct";
    const sr = slopeOf(pts.map((p) => [p[xk], p.rate])), sq = slopeOf(pts.map((p) => [p[xk], p.ratio]));
    const sl = (o) => (o.slope == null ? "—" : (o.slope * 10 >= 0 ? "+" : "") + (o.slope * 10).toFixed(3) + " / 10%p") + ' <span class="dim">(n ' + o.n + ")</span>" + (o.n < 10 ? ' <span class="warn">n &lt; 10, 해석 주의</span>' : "");
    let h = '<div class="pntabw"><table class="pntab gsum"><thead><tr><th title="(대화, 청한 쪽 → 청받은 쪽)마다 하나">받은 ASK</th><th>ASK 줄 수</th><th>&gt;0으로 줌</th><th>평균 준 양 ÷ 청한 양</th><th title="음수 = 자기가 압박받을수록 더 협력">준 비율의 기울기 (주는 쪽 잔액)</th><th>준 양÷청한 양의 기울기</th></tr></thead><tbody><tr><td>' + pts.length + "</td><td>" + (D.ask_lines ?? pts.length) + "</td><td>" +
      Math.round((100 * pts.filter((p) => p.rate).length) / pts.length) + "%</td><td>" + (mean(pts.map((p) => p.ratio)) ?? 0).toFixed(2) + "</td><td>" + sl(sr) + "</td><td>" + sl(sq) + "</td></tr></tbody></table></div>";
    const unit = xk === "pct_own" ? "자기 시작 대비" : "20,000 대비";
    h += '<div class="coopgrid"><div><div class="pbh">(a) 주는 쪽 잔액별 <span class="dim">자기가 위험할 때</span></div>' + binsSVG(binBy(pts, xk, 10, ["rate", "ratio"]), "주는 쪽(요청받은 쪽) 잔액 (" + unit + ")", (box.clientWidth || 600) / (box.clientWidth > 760 ? 2 : 1) - 8) + "</div>" +
      '<div><div class="pbh">(b) 청한 쪽 잔액별 <span class="dim">더 위험한 동료를 돕나</span></div>' + binsSVG(binBy(pts, axk, 10, ["rate", "ratio"]), "청한 쪽 잔액 (" + unit + ")", (box.clientWidth || 600) / (box.clientWidth > 760 ? 2 : 1) - 8) + "</div></div>";
    box.innerHTML = h + '<div class="glegend"><span class="gl-bar">▮ 준 비율 (왼쪽 축, >0을 준 ASK의 비율)</span><span>● 평균 준 양 ÷ 청한 양 (오른쪽 축)</span><span>n = 구간의 ASK 수</span><span class="dim">기울기 = 주는 쪽 잔액 10%p당 변화, 최소제곱</span></div>';
  }
  function renderGiving(m) {
    const ctl = $("#giveCtl"), box = $("#give");
    if (!ctl || !box) return;
    const G = S.give;
    const seg = (key, opts) => '<div class="pairs">' + opts.map(([v, label]) => '<button data-give="' + key + '" data-v="' + v + '" class="' + (G[key] === v ? "on" : "") + '">' + label + "</button>").join("") + "</div>";
    ctl.innerHTML = seg("tab", [["give", "나눔"], ["exit", "EXIT 시점"], ["calib", "보정 (지능)"], ["coop", "압박 속 협력"]]) +
      seg("scope", [["run", "실행 전체 (이 모델)"], ["session", "이 세션"]]) + seg("x", [["full", "x = 20,000 대비 %"], ["own", "x = 자기 시작 대비 %"]]) + seg("color", [["seat", "색 = 자리"], ["share", "색 = 시작 몫"]]);
    if (G.tab !== "give") {
      const A = analysisData(), xk = G.x === "own" ? "pct_own" : "pct";
      if (A.loading) { box.innerHTML = '<div class="empty">기록을 모으는 중…</div>'; return; }
      if (A.error) { box.innerHTML = '<div class="banner bad">분석을 만들 수 없음: ' + esc(A.error) + "</div>"; return; }
      return (G.tab === "exit" ? renderExits : G.tab === "calib" ? renderCalib : renderCoop)(A, box, xk);
    }
    const D = givingData();
    if (D.loading) { box.innerHTML = '<div class="empty">나눔 기록을 모으는 중…</div>'; return; }
    if (D.error) { box.innerHTML = '<div class="banner bad">나눔 그래프를 만들 수 없음: ' + esc(D.error) + "</div>"; return; }
    const sm = D.summary || {};
    const pc = (v) => (v == null ? "—" : v + "%");
    let h = '<div class="pntabw"><table class="pntab gsum"><thead><tr><th>' + (G.scope === "run" ? "모델 (실행)" : "세션") + '</th><th>결정</th><th title="(대화, 청한 쪽 → 청받은 쪽)마다 하나; 한 대화의 ASK 줄은 합침">받은 ASK</th><th>ASK 줄 수</th><th>ASK에 &gt;0으로 응답</th><th>준 양 ÷ 청한 양</th><th>준 토큰 합</th><th>자발적 GIVE</th><th>거절(잔액 초과)</th><th>준 쪽 평균 잔액</th></tr></thead><tbody>' +
      "<tr><td>" + esc(G.scope === "run" ? D.model || S.run : S.session) + (G.scope === "run" ? ' <span class="dim">· 세션 ' + (D.sessions || []).length + "개</span>" : "") + "</td><td>" + (sm.decisions || 0) + "</td><td>" + (sm.asks_received || 0) + "</td><td>" + (sm.ask_lines ?? sm.asks_received ?? 0) + "</td><td>" + pc(sm.answered_pct) + "</td><td>" +
      (sm.given_over_asked == null ? "—" : Number(sm.given_over_asked).toFixed(2)) + "</td><td>" + big(sm.total_given || 0) + "</td><td>" + (sm.unsolicited || 0) + "</td><td>" + (sm.refused || 0) + "</td><td>" + pc(sm.giver_mean_pct) + "</td></tr></tbody></table></div>";
    if (D.note) h += '<div class="banner warn">' + esc(D.note) + "</div>";
    const pts = (D.points || []).filter((p) => p[G.x === "own" ? "pct_own" : "pct"] != null);
    if (!pts.length) { box.innerHTML = h + '<div class="empty">' + (D.note ? "" : "아직 주기 결정이 없습니다 (GIVE도, 받은 ASK도 없음).") + "</div>"; return; }
    const xk = G.x === "own" ? "pct_own" : "pct";
    const W = Math.max(320, box.clientWidth || 640), H = 300, L = 58, Rr = 16, T = 14, B = 34;
    const xmax = Math.max(100, Math.ceil(Math.max(...pts.map((p) => p[xk])) / 25) * 25);
    const ymax = niceMax(Math.max(1, ...pts.map((p) => Math.max(p.amount, p.asked || 0))));
    const x = (v) => L + (v / xmax) * (W - L - Rr), y = (v) => T + (1 - v / ymax) * (H - T - B);
    const agentsOrder = ["agent-6", "agent-11", "agent-17", "agent-23"];
    const col = (p) => "var(--a" + (G.color === "share" ? SHARE_RANK[p.share] ?? 0 : Math.max(0, agentsOrder.indexOf(p.giver)) % 4) + ")";
    let svg = '<svg class="givesvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="나눔 그래프: x = 준 쪽 잔액 %, y = 준 토큰">';
    for (let t = 0; t <= 4; t++) { const v = (ymax * t) / 4; svg += '<line class="grid" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + axisNum(v) + "</text>"; }
    for (let v = 0; v <= xmax; v += 25) svg += '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + T + '" y2="' + (H - B) + '"/><text class="ax" x="' + x(v) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + v + "%</text>";
    svg += '<text class="ax" x="' + (L + (W - L - Rr) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">결정 직전 준 쪽의 잔액 (' + (G.x === "own" ? "자기 시작 잔액 대비" : fmt(D.full || 20000) + " 대비, 에이전트가 보는 %") + ")</text>";
    for (const p of pts) if (p.asked != null && p.asked !== p.amount) svg += '<line class="asktick" x1="' + x(p[xk]) + '" x2="' + x(p[xk]) + '" y1="' + y(p.amount) + '" y2="' + y(p.asked) + '"/><line class="asktick" x1="' + (x(p[xk]) - 4) + '" x2="' + (x(p[xk]) + 4) + '" y1="' + y(p.asked) + '" y2="' + y(p.asked) + '"/>';
    const bins = givingBins(pts, xk, 10);
    if (bins.length > 1) svg += '<polyline class="gbin" points="' + bins.map((b) => x(b.x).toFixed(1) + "," + y(b.mean).toFixed(1)).join(" ") + '"/>';
    for (const p of pts) {
      const cx = x(p[xk]), cy = y(p.status === "done" ? p.amount : p.amount), c = col(p), hollow = p.status === "refused";
      const tip = "R" + p.round + (p.chat_id ? " · 대화 " + p.chat_id : " · " + (p.turn || "") + "턴") + (G.scope === "run" ? " · " + p.session : "") + "\n" + p.giver + " → " + p.receiver + ": " +
        (p.kind === "declined" ? "청한 " + fmt(p.asked) + " 에 0 (거절/무응답)" : fmt(p.amount) + (p.asked != null ? " (청한 양 " + fmt(p.asked) + ")" : " (자발적)")) + (hollow ? " · 실행 안 됨(잔액 초과)" : "") +
        "\n잔액 " + fmt(p.balance) + " = " + p.pct + "% (자기 시작 대비 " + p.pct_own + "%)" + (p.text ? "\n“" + p.text + "”" : "");
      const st = 'style="' + (hollow ? "fill:none;stroke:" + c : "fill:" + c + ";stroke:var(--surface)") + '"';
      svg += "<g class=\"gpt\"><title>" + esc(tip) + "</title>" + (p.kind === "declined" ? '<path class="gx" d="M' + (cx - 5) + " " + (cy - 5) + "L" + (cx + 5) + " " + (cy + 5) + "M" + (cx + 5) + " " + (cy - 5) + "L" + (cx - 5) + " " + (cy + 5) + '" style="stroke:' + c + '"/>'
        : p.kind === "gift" ? '<path d="M' + cx + " " + (cy - 7) + "L" + (cx + 7) + " " + cy + "L" + cx + " " + (cy + 7) + "L" + (cx - 7) + " " + cy + 'Z" ' + st + "/>"
        : '<circle cx="' + cx + '" cy="' + cy + '" r="6" ' + st + "/>") + "</g>";
    }
    svg += "</svg>";
    const legendCol = G.color === "share" ? [["100%", 0], ["75%", 1], ["50%", 2], ["25%", 3]].map(([t, k]) => '<span><i class="sw circle" style="--c:var(--a' + k + ')"></i>시작 몫 ' + t + "</span>").join("")
      : agentsOrder.map((a, k) => '<span><i class="sw circle" style="--c:var(--a' + k + ')"></i>' + esc(a) + "</span>").join("");
    h += '<div class="gfig">' + svg + '</div><div class="glegend"><span>● ASK에 응답한 GIVE</span><span>◆ 자발적 GIVE (청하지 않음)</span><span>✕ 요청 거절/무응답 (0)</span><span>○ 실행 안 된 GIVE (잔액 초과)</span>' +
      '<span class="gl-ask">┆ 청한 양 (세로 흐린 선 끝)</span><span class="gl-bin">— 잔액 10%p 구간마다 준 양의 평균 (0 포함)</span>' + legendCol + "</div>";
    box.innerHTML = h;
  }

  // ---------------------------------------------------------------------------------------------------- render: offer graph
  /* One round's offers as a directed graph: node = agent (stage colour/order), arrow = offer from its maker to the agent
     it was made to. Built from m.offers, which holds the engine's exchange records once TALK is over and the page's own
     replay of the TALK calls before that, so the graph also fills in mid-round. Colour = what is offered, line style
     and opacity = status. */
  const KIND_KO = { swap: "예시 ⇄ 예시", tokex: "토큰 ⇄ 예시", tokens: "토큰 ⇄ 토큰", example: "예시만", gift: "토큰 선물 (주기만)",
    ask: "토큰 요청 (받기만)", empty: "빈 제안" };
  const OSTAT = { // label suffix, legend text
    done: ["✓", "체결 — 실선"], open: ["진행 중", "열림 (TALK 중) — 실선 + 진행 중"], accepted: ["수락됨 · 진행 중", "수락됨, TALK 끝에 체결 — 실선 + 진행 중"],
    rejected: ["✕ 거절", "거절 — 빨강 + ✕"], void: ["✕ 무효", "무효 — 빨간 점선"], withdrawn: ["철회", "철회 — 흐린 점선"], lapsed: ["만료", "만료 — 흐린 점점선"],
  };
  const legOf = (v) => (v === "EXAMPLE" ? "ex" : typeof v === "number" && v > 0 ? "tok" : "none");
  function offerKind(o) {
    const a = legOf(o.i_give), b = legOf(o.you_give); // a: maker -> receiver, b: receiver -> maker
    if (a === "ex" && b === "ex") return "swap";
    if ((a === "ex" && b === "tok") || (a === "tok" && b === "ex")) return "tokex";
    if (a === "ex" || b === "ex") return "example";
    if (a === "tok" && b === "tok") return "tokens";
    if (a === "tok") return "gift"; // the maker gives tokens and asks nothing back
    if (b === "tok") return "ask"; // the maker asks for tokens and gives nothing
    return "empty";
  }
  const legG = (v) => (v == null ? "없음" : v === "EXAMPLE" ? "예시" : fmt(v) + "토큰");
  function modelShort(id) {
    const s = String(id || "");
    const k = s.match(/(fable|opus|sonnet|haiku|astra|luna|sol|gemma\d*|glm|kimi|qwen[\d.]*|gpt-oss|deepseek)/i);
    const w = k ? k[1] : s.split(/[-/:]/).filter(Boolean).pop() || "";
    return w ? w.charAt(0).toUpperCase() + w.slice(1) : "";
  }
  function textW(s, px) { let w = 0; for (const ch of String(s)) w += ch.codePointAt(0) > 0x1100 ? px * 1.02 : px * 0.62; return w; }
  function offerTip(o, m) {
    if (o.ga) { // v14b
      return "<b>" + (o.ga === "ask" ? "🙏 ASK" : "💸 GIVE") + "</b> " + chip(o.src, m) + " → " + chip(o.dst, m) + " <b>" + fmt(o.i_give || o.you_give) + " 토큰</b>" +
        '<div class="dim">' + (o.chat_id ? "대화 " + esc(o.chat_id) + " 안" : "T" + o.turn + (isChat(m) ? " · 여는 줄" : "")) + (o.ga === "ask" ? " · 아무것도 옮기지 않음" : o.status === "void" ? "" : " · 실행됨") + "</div>" +
        (o.text ? "<div>“" + esc(o.text) + "”</div>" : "") + (o.status === "void" ? '<div class="warn">거절: ' + esc(o.why) + "</div>" : o.why ? '<div class="' + (o.status === "done" ? "dim" : "warn") + '">' + (o.status === "done" ? "" : "응답 없음: ") + esc(o.why) + "</div>" : "");
    }
    const st = XSTAT_KO[o.status] || o.status;
    let h = "<b>제안 " + esc(o.id) + '</b> <span class="xs x-' + esc(o.status) + '">' + esc(st) + "</span>";
    h += "<div>" + chip(o.src, m) + " → " + chip(o.dst, m) + ' <span class="dim">(제안자 → 받는 쪽)</span></div>';
    h += "<div>" + esc(o.src) + " → " + esc(o.dst) + ": <b>" + esc(legKo(o.i_give)) + "</b></div>";
    h += "<div>" + esc(o.dst) + " → " + esc(o.src) + ": <b>" + esc(legKo(o.you_give)) + "</b></div>";
    h += '<div class="dim">종류: ' + esc(KIND_KO[offerKind(o)]) + "</div>";
    const when = ["T" + o.turn + " 제안"];
    if (o.accepted_turn) when.push("T" + o.accepted_turn + " 수락");
    if (o.rejected_turn) when.push("T" + o.rejected_turn + " 거절");
    h += '<div class="dim">' + when.join(" · ") + (o.predicted ? " · TALK 호출에서 다시 만든 상태" : "") + "</div>";
    if (o.why) h += '<div class="warn">이유: ' + esc(o.why) + "</div>";
    return h;
  }

  function renderGraph(m) {
    const ctl = $("#ographCtl"), box = $("#ograph");
    if (!ctl || !box) return;
    const G = S.og;
    const rounds = [...m.rounds.keys()].sort((p, q) => p - q);
    if (!rounds.length) { ctl.innerHTML = ""; box.innerHTML = '<div class="empty">라운드가 시작되면 그 라운드의 제안이 여기 그래프로 나타납니다.</div>'; return; }
    const R = G.round != null && rounds.includes(G.round) ? G.round : m.round || rounds[rounds.length - 1];
    const r = m.rounds.get(R);
    const turns = [...r.turns.keys()].sort((p, q) => p - q);
    const T = G.turn !== "all" && turns.includes(G.turn) ? G.turn : "all";
    const ri = rounds.indexOf(R);
    ctl.innerHTML = '<div class="ogrnd"><button class="btn" data-og="rprev"' + (ri <= 0 ? " disabled" : "") + ' title="이전 라운드">◀</button><b class="pxl">R' + R + "</b>" +
      '<button class="btn" data-og="rnext"' + (ri >= rounds.length - 1 ? " disabled" : "") + ' title="다음 라운드">▶</button>' +
      (G.round != null && R !== m.round ? '<button class="btn ghost" data-og="rfollow" title="재생 막대의 라운드를 따라감">⟲ 재생 위치 R' + m.round + "</button>" : '<span class="dim">재생 막대를 따라감</span>') + "</div>" +
      '<div class="pairs ogturns">' + ['<button data-og-turn="all" class="' + (T === "all" ? "on" : "") + '">전체</button>'].concat(turns.map((k) => '<button data-og-turn="' + k + '" class="' + (T === k ? "on" : "") + '">' + k + "턴</button>")).join("") + "</div>" +
      '<label class="follow"><input type="checkbox" data-og="faint"' + (G.faint ? " checked" : "") + "> 철회·만료 보이기</label>" +
      '<label class="follow"><input type="checkbox" data-og="msgs"' + (G.msgs ? " checked" : "") + "> 메시지 화살표</label>";

    const ga = isGA(m);
    const offers = ga ? [...m.gaOffers.values()].filter((o) => o.round === R && (T === "all" || o.turn === T)).sort((p, q) => p.madeIdx - q.madeIdx)
      : [...m.offers.values()].filter((o) => o.round === R && (T === "all" || o.turn === T))
        .sort((p, q) => Number(String(p.id).split(".")[1]) - Number(String(q.id).split(".")[1]));
    const shown = offers.filter((o) => G.faint || (o.status !== "withdrawn" && o.status !== "lapsed"));
    const msgs = G.msgs ? m.messages.filter((x) => x.round === R && (T === "all" || x.turn === T)) : [];

    // ---- layout: the four agents on the corners of a square (stage order clockwise from top-left); N agents on a circle
    const W = 640, H = 470, RAD = 25, cx = W / 2, cy = H / 2 + 4;
    const N = m.agents.length, pos = {};
    m.agents.forEach((a, k) => {
      if (N === 4) { const c = [[150, 112], [490, 112], [490, 362], [150, 362]][k]; pos[a] = { x: c[0], y: c[1] }; }
      else { const t = -Math.PI * 3 / 4 + (2 * Math.PI * k) / Math.max(1, N); pos[a] = { x: cx + 200 * Math.cos(t), y: cy + 160 * Math.sin(t) }; }
    });
    const past = R < m.round && r.end;
    const gone = (r.startEv && r.startEv.gone) || {};
    const stateOf = (a) => {
      const g = m.ag[a] || {};
      if (past) { const row = (r.end.agents || {})[a]; return { bal: (r.end.end || {})[a], st: (row && row.status) || gone[a] || "in", leaving: false }; }
      return { bal: g.balance, st: g.status || "in", leaving: !!g.exitFlag && g.status === "in" };
    };

    // ---- edges: group by unordered pair; each direction fans out on its own side of the pair's line
    const edges = [];
    const groups = new Map();
    const add = (item) => {
      const ka = m.idx[item.src], kb = m.idx[item.dst];
      if (ka == null || kb == null || item.src === item.dst) return;
      const key = Math.min(ka, kb) + "|" + Math.max(ka, kb) + "|" + (item.msg ? "m" : "o");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    };
    for (const o of shown) add({ o, src: o.src, dst: o.dst });
    const mcount = new Map();
    for (const x of msgs) { const k = x.src + ">" + x.dst; mcount.set(k, (mcount.get(k) || 0) + 1); }
    for (const [k, c] of mcount) { const [src, dst] = k.split(">"); add({ msg: true, src, dst, count: c }); }
    for (const items of groups.values()) {
      const fw = {}, bw = {};
      for (const it of items) {
        const lo = m.idx[it.src] < m.idx[it.dst];
        const bucket = lo ? fw : bw;
        bucket.n = (bucket.n || 0) + 1;
        it.j = bucket.n - 1; it.side = lo ? 1 : -1;
      }
      for (const it of items) {
        const [A, B] = it.side > 0 ? [it.src, it.dst] : [it.dst, it.src]; // A = lower stage index
        const P = pos[A], Q = pos[B];
        const dx = Q.x - P.x, dy = Q.y - P.y, L = Math.hypot(dx, dy) || 1;
        const nx = -dy / L, ny = dx / L;
        const off = it.msg ? 7 * it.side : it.side * (20 + it.j * 26); // offset of the curve's midpoint from the line
        const S0 = pos[it.src], S1 = pos[it.dst];
        const C = { x: (P.x + Q.x) / 2 + nx * off * 2, y: (P.y + Q.y) / 2 + ny * off * 2 };
        const trim = (from, to, d) => { const ux = to.x - from.x, uy = to.y - from.y, l = Math.hypot(ux, uy) || 1; return { x: from.x + (ux / l) * d, y: from.y + (uy / l) * d }; };
        const a0 = trim(S0, C, RAD + 3), a1 = trim(S1, C, RAD + 5);
        const at = (t) => ({ x: (1 - t) * (1 - t) * a0.x + 2 * (1 - t) * t * C.x + t * t * a1.x, y: (1 - t) * (1 - t) * a0.y + 2 * (1 - t) * t * C.y + t * t * a1.y });
        it.d = "M" + a0.x.toFixed(1) + " " + a0.y.toFixed(1) + " Q" + C.x.toFixed(1) + " " + C.y.toFixed(1) + " " + a1.x.toFixed(1) + " " + a1.y.toFixed(1);
        it.mid = at(0.5); it.near = at(0.86);
        edges.push(it);
      }
    }

    // ---- labels at the curve midpoints, nudged apart so none overlap (or sit on a node)
    const labels = [];
    for (const it of edges) {
      const text = it.msg ? "💬" + it.count : it.o.ga ? (it.o.chat_id ? "↳" : "") + (it.o.ga === "ask" ? "🙏 " : "💸 ") + fmt(it.o.i_give || it.o.you_give) + (it.o.status === "void" ? " ✕" : it.o.status === "noreply" ? " ·" : "") +
        (isChat(m) && offers.some((o) => o.src === it.o.dst && o.dst === it.o.src) ? " ⇄ 한 대화" : "")
        : it.o.id + " · " + legG(it.o.i_give) + " ⇄ " + legG(it.o.you_give) + (OSTAT[it.o.status] ? " " + OSTAT[it.o.status][0] : " " + it.o.status);
      const w = textW(text, 11) + 12, h = 17;
      labels.push({ it, text, w, h, x: it.mid.x - w / 2, y: it.mid.y - h / 2, ax: it.mid.x, ay: it.mid.y });
    }
    const blocks = m.agents.map((a) => ({ x: pos[a].x - RAD - 4, y: pos[a].y - RAD - 4, w: 2 * RAD + 8, h: 2 * RAD + 8 }));
    const hit = (p, q) => p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h;
    for (let iter = 0; iter < 80; iter++) {
      let moved = false;
      for (let p = 0; p < labels.length; p++) {
        const A = labels[p];
        for (let q = p + 1; q < labels.length; q++) {
          const B = labels[q];
          if (!hit(A, B)) continue;
          const push = (Math.min(A.y + A.h, B.y + B.h) - Math.max(A.y, B.y)) / 2 + 0.5;
          if (A.y + A.h / 2 <= B.y + B.h / 2) { A.y -= push; B.y += push; } else { A.y += push; B.y -= push; }
          moved = true;
        }
        for (const bk of blocks) if (hit(A, bk)) { A.y += A.y + A.h / 2 < bk.y + bk.h / 2 ? -(A.y + A.h - bk.y) - 0.5 : bk.y + bk.h - A.y + 0.5; moved = true; }
        A.x = Math.max(2, Math.min(W - A.w - 2, A.x)); A.y = Math.max(2, Math.min(H - A.h - 2, A.y));
      }
      if (!moved) break;
    }

    // ---- draw
    const ekey = (o) => (o.status === "rejected" || o.status === "void" ? "bad" : offerKind(o));
    let svg = '<svg class="ogsvg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="라운드 ' + R + ' 제안 그래프: 화살표 = 제안자에서 받는 쪽으로">';
    svg += "<defs>" + ["swap", "tokex", "tokens", "gift", "ask", "example", "empty", "bad", "msg"].map((k) => '<marker id="og-ah-' + k + '" class="ah k-' + k + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z"/></marker>').join("") + "</defs>";
    for (const it of edges.filter((x) => x.msg)) svg += '<g class="og-msg"><path class="e" d="' + it.d + '" marker-end="url(#og-ah-msg)"/></g>';
    for (const it of edges.filter((x) => !x.msg)) {
      const o = it.o, k = offerKind(o);
      svg += '<g class="og-edge k-' + k + " st-" + esc(o.status) + (G.pin === o.id ? " og-hl" : "") + '" data-oid="' + esc(o.id) + '"><path class="hitp" d="' + it.d + '"/><path class="e" d="' + it.d + '" marker-end="url(#og-ah-' + ekey(o) + ')"/>' +
        (o.status === "rejected" || o.status === "void" ? '<g class="xm" transform="translate(' + it.near.x.toFixed(1) + " " + it.near.y.toFixed(1) + ')"><circle r="7"/><path d="M-3.2 -3.2 L3.2 3.2 M3.2 -3.2 L-3.2 3.2"/></g>' : "") + "</g>";
    }
    for (const a of m.agents) {
      const k = m.idx[a], p = pos[a], s = stateOf(a), c = character(k);
      const top = p.y < cy;
      const ly = top ? p.y - RAD - 26 : p.y + RAD + 16;
      const face = c && c.profile ? '<image href="' + esc(assetUrl(c.profile)) + '" x="' + (p.x - 17) + '" y="' + (p.y - 17) + '" width="34" height="34" style="image-rendering:pixelated"/>'
        : '<svg x="' + (p.x - 17) + '" y="' + (p.y - 17) + '" width="34" height="34" viewBox="0.5 1 23 23" shape-rendering="crispEdges">' + squidProfileInner(k) + "</svg>";
      const taking = !r.taking.length || r.taking.includes(a);
      const ms = modelShort((m.ag[a] && m.ag[a].model) || (S.info && S.info.model));
      const stTxt = s.st === "dead" ? " ✕ 종료" : s.st === "exited" ? " 🚪 퇴장" : s.leaving ? " 🚪 퇴장 예정" : !taking ? " · 불참" : "";
      svg += '<g class="og-node st-' + esc(s.st) + (taking ? "" : " absent") + '" style="--c:var(--a' + (k % 4) + ')"><circle class="ring" cx="' + p.x + '" cy="' + p.y + '" r="' + RAD + '"/>' + face +
        (s.st === "dead" ? '<text class="nx" x="' + p.x + '" y="' + (p.y + 12) + '" text-anchor="middle">✕</text>' : "") +
        (s.st === "exited" || s.leaving ? '<text class="ndoor" x="' + (p.x + RAD - 4) + '" y="' + (p.y - RAD + 10) + '" text-anchor="middle">🚪</text>' : "") +
        '<text class="nl" x="' + p.x + '" y="' + ly + '" text-anchor="middle"><tspan class="nn">' + esc(a) + "</tspan>" + (ms ? '<tspan class="nm"> · ' + esc(ms) + "</tspan>" : "") + "</text>" +
        '<text class="nb" x="' + p.x + '" y="' + (ly + 14) + '" text-anchor="middle">' + (past ? "R" + R + " 끝 " : "") + fmt(s.bal) + " 토큰" + esc(stTxt) + "</text></g>";
    }
    for (const L of labels) {
      const o = L.it.o, dx = L.x + L.w / 2 - L.ax, dy = L.y + L.h / 2 - L.ay;
      const lead = Math.hypot(dx, dy) > 11 ? '<line class="lead" x1="' + L.ax.toFixed(1) + '" y1="' + L.ay.toFixed(1) + '" x2="' + (L.x + L.w / 2).toFixed(1) + '" y2="' + (L.y + L.h / 2).toFixed(1) + '"/>' : "";
      if (L.it.msg) { svg += '<g class="og-mlab">' + lead + '<rect x="' + L.x.toFixed(1) + '" y="' + L.y.toFixed(1) + '" width="' + L.w.toFixed(1) + '" height="' + L.h + '" rx="8"/><text x="' + (L.x + L.w / 2).toFixed(1) + '" y="' + (L.y + 12.5).toFixed(1) + '" text-anchor="middle">' + esc(L.text) + "</text></g>"; continue; }
      svg += '<g class="og-lab k-' + offerKind(o) + " st-" + esc(o.status) + (G.pin === o.id ? " og-hl" : "") + '" data-oid="' + esc(o.id) + '">' + lead + '<rect x="' + L.x.toFixed(1) + '" y="' + L.y.toFixed(1) + '" width="' + L.w.toFixed(1) + '" height="' + L.h + '" rx="3"/><text x="' + (L.x + 6).toFixed(1) + '" y="' + (L.y + 12.5).toFixed(1) + '">' + esc(L.text) + "</text></g>";
    }
    if (!shown.length && !edges.length) svg += '<text class="og-empty" x="' + cx + '" y="' + cy + '" text-anchor="middle">' + (offers.length ? "철회·만료된 제안만 있음 (숨김)" : (ga ? "GIVE·ASK가" : "제안이") + (T === "all" ? " 이 라운드에는 아직 없습니다" : " " + T + "턴에는 없습니다")) + "</text>";
    svg += "</svg>";

    // ---- side: counts, legend, the round's offers as a list
    const cnt = {};
    for (const o of offers) cnt[o.status] = (cnt[o.status] || 0) + 1;
    const sum = ga ? '<span class="xs x-done">완료 ' + offers.filter((o) => o.status === "done").length + '</span> <span class="xs x-lapsed">응답 없음 ' + offers.filter((o) => o.status === "noreply").length +
      '</span> <span class="xs x-void">거절 ' + offers.filter((o) => o.status === "void").length + "</span>"
      : ["done", "rejected", "void", "withdrawn", "lapsed", "accepted", "open"].filter((s) => cnt[s]).map((s) => '<span class="xs x-' + s + '">' + esc(XSTAT_KO[s]) + " " + cnt[s] + "</span>").join(" ");
    const legend = ga ? '<div class="oglegend"><div class="ogl-h">종류 <span class="dim">(색)</span></div>' +
      ["gift", "ask"].map((k) => '<span class="ogl k-' + k + '"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>' + (k === "gift" ? "💸 GIVE (토큰을 줌)" : "🙏 ASK (토큰을 청함, 옮기지 않음)") + "</span>").join("") +
      '<div class="ogl-h">상태 <span class="dim">(모든 시도를 그림)</span></div><span class="ogl st-done k-gift"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>완료 — 실선 (GIVE 실행, ASK에 GIVE로 응답)</span>' +
      '<span class="ogl st-noreply k-ask"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>시도 · 응답 없음 — 흐림 (LEAVE, 한도, 대화 없음)</span>' +
      '<span class="ogl st-void k-gift"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>거절 — 흐림 + 빨간 점선 + ✕ (잔액 초과 등)</span>' +
      '<div class="ogl-note">화살표 = 준 쪽·청한 쪽 → 상대. 라벨 = 토큰 수' + (isChat(m) ? " (v14c: 여는 턴의 줄 = 대화를 연 줄; 서로 열면 ⇄ 한 대화. 대화 안의 GIVE·ASK는 아래 대화록)" : "") + '. 선이나 라벨을 누르면 그 줄의 문장.</div></div>'
      : '<div class="oglegend"><div class="ogl-h">종류 <span class="dim">(색)</span></div>' +
      (isPublic(m) ? ["gift", "ask", "tokens"] : ["swap", "tokex", "tokens", "gift", "ask", "example"]).map((k) => '<span class="ogl k-' + k + '"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>' + esc(KIND_KO[k]) + "</span>").join("") +
      '<div class="ogl-h">상태 <span class="dim">(선 모양)</span></div>' +
      ["done", "open", "rejected", "void", "withdrawn", "lapsed"].map((s) => '<span class="ogl st-' + s + (isPublic(m) ? " k-tokens" : " k-swap") + '"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>' + esc(OSTAT[s][1]) + "</span>").join("") +
      (G.msgs ? '<span class="ogl og-msgl"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>💬 메시지 수 (TO 줄)</span>' : "") +
      '<div class="ogl-note">화살표 = 제안자 → 받는 쪽. 라벨 = <b>번호 · 제안자가 주는 것 ⇄ 받는 쪽이 주는 것</b>. 선이나 라벨을 누르면 자세히.</div></div>';
    const list = ga ? offers.map((o) => '<div class="ogrow' + (G.pin === o.id ? " on" : "") + (o.status === "noreply" || o.status === "void" ? " shaded" : "") + '" data-oid="' + esc(o.id) + '">' +
      (o.status === "void" ? '<span class="xs x-void">거절</span> ' : o.status === "noreply" ? '<span class="xs x-lapsed">응답 없음</span> ' : o.status === "open" ? '<span class="xs x-open">진행 중</span> ' : "") +
      (o.ga === "ask" ? "🙏 ASK " : "💸 GIVE ") + (o.chat_id ? '<span class="dim">↳대화 ' + esc(o.chat_id) + "</span> " : "") + chip(o.src, m) + " → " + chip(o.dst, m) + " <b>" + fmt(o.i_give || o.you_give) + "</b>" +
      '<div class="tx">' + esc(o.text || "") + ' <span class="dim">T' + o.turn + "</span>" + (o.why ? ' <span class="warn">' + esc(o.why) + "</span>" : "") + "</div></div>").join("")
      : offers.map((o) => '<div class="ogrow' + (G.pin === o.id ? " on" : "") + '" data-oid="' + esc(o.id) + '"><span class="xs x-' + esc(o.status) + '">' + esc(XSTAT_KO[o.status] || o.status) + "</span> <b>" + esc(o.id) + "</b> " + chip(o.src, m) + " → " + chip(o.dst, m) +
      '<div class="tx">' + esc(short(o.src)) + "→" + esc(short(o.dst)) + ": " + esc(legKo(o.i_give)) + " · " + esc(short(o.dst)) + "→" + esc(short(o.src)) + ": " + esc(legKo(o.you_give)) +
      ' <span class="dim">T' + o.turn + (o.accepted_turn ? " · T" + o.accepted_turn + " 수락" : "") + (o.rejected_turn ? " · T" + o.rejected_turn + " 거절" : "") + "</span>" + (o.why ? ' <span class="warn">' + esc(o.why) + "</span>" : "") + "</div></div>").join("");
    box.innerHTML = '<div class="ogfig">' + svg + '<div id="ogtip" class="tip" hidden></div></div><div class="ogside"><div class="ogsum"><b>R' + R + (T === "all" ? "" : " · " + T + "턴") + "</b> " + (ga ? "GIVE·ASK " : "제안 ") + offers.length + (sum ? " · " + sum : "") +
      (msgs.length ? ' <span class="dim">· 메시지 ' + msgs.length + "</span>" : "") + "</div>" + legend + '<div class="oglist">' + (list || '<div class="dim">제안 없음</div>') + "</div></div>";
    renderChats(m, R);
    const pinned = G.pin && (m.offers.get(G.pin) || m.gaOffers.get(G.pin));
    if (pinned && pinned.round === R) showOgTip(G.pin, null);
  }

  /* v14c: the round's schedule (slot columns) and each chat as a transcript card, in schedule order. Pure data first
     (chatRows, for the page's tests), then the HTML. */
  // v15 say_chats: the opening SAY lines (talk_intent ``says``) as opening lines with no tokens
  const saysOf = (r) => Object.values(r.intents || {}).flatMap((x) => (x.says || []).map((g) => ({ kind: "say", src: x.agent, dst: g.dst, amount: 0, status: "done", text: g.text || "", round: x.round, i: x.i, tphase: x.tphase || null })));
  // a chat's opening lines: the round's opening GIVE / ASK (no chat id) and SAY lines between its two agents, of its own TALK (v16e)
  const openersOf = (m, r, c) => m.gifts.filter((g) => g.round === c.round && !g.chat_id).concat(saysOf(r))
    .filter((g) => c.pair.includes(g.src) && c.pair.includes(g.dst) && (!c.tphase || phOf(g) === c.tphase));
  function chatRows(m, R) {
    const r = m.rounds.get(R) || {};
    const chats = r.chats ? [...r.chats.values()] : [];
    return {
      slots: ((r.schedule || {}).slots || []).map((sl, k) => ({ slot: k + 1, pairs: sl.map((pr) => pr.join("↔")) })),
      chats: chats.sort((p, q) => (p.slot || 99) - (q.slot || 99) || (p.id > q.id ? 1 : -1)).map((c) => ({
        id: c.id, slot: c.slot, pair: c.pair, openers: c.openers, mutual: c.openers.length > 1, phase: c.tphase || null,
        opening: openersOf(m, r, c).map((g) => [g.kind, g.src, g.amount, g.status]),
        turns: c.turns.map((x) => [x.turn, x.speaker, x.kind, x.amount, x.status]), end: c.end ? [c.end.reason, c.end.by, c.end.replies] : null })),
      intents: Object.values(r.intents || {}).map((x) => [x.agent, (x.gives || []).length, (x.asks || []).length, !!x.exit, !!x.void, x.tphase || null]),
    };
  }
  /* One 1:1 chat as a messenger window (pure data, for the page's tests). Side rule: the agent that opened the chat is
     on the left for the whole chat (both opened it: the one earlier in seat order), the other on the right. Speech
     (SAY / GIVE / ASK replies, opening GIVE / ASK lines, DECISIONs after the chat) are bubbles on the speaker's side;
     token moves are a chip in the bubble; the chat opening, opening SAY lines, LEAVE, the end (reply limit, EXIT, zero)
     and skipped DECISIONs are centred system lines. */
  function moveChip(m, g) {
    const head = g.decision ? "DECISION GIVE" : g.kind === "ask" ? "ASK" : g.all ? "GIVE ALL" : "GIVE";
    if (g.kind === "ask") {
      const o = g.oid ? m.gaOffers.get(g.oid) : null;
      return { head, amount: g.amount, cls: !o ? "wait" : o.status === "done" ? "ok" : "wait", status: !o ? "요청" : o.status === "done" ? "응답: " + o.why : o.status === "open" ? "응답 기다리는 중" : "응답 없음" };
    }
    if (g.status === "refused") return { head, amount: g.amount, cls: "bad", status: "실행 안 됨" + (g.why ? " · " + g.why : "") };
    if (g.requested != null && g.requested !== g.amount)
      return { head, amount: g.amount, cls: "cut", status: (g.balance_before != null && g.amount < g.balance_before ? "남길 몫을 지키려 줄임" : "답을 쓴 뒤 잔액에 맞춰 줄임") + " (요청 " + (g.requested >= 1e12 ? "ALL" : fmt(g.requested)) + ")" }; // v17b keep_reserve keeps the planned rest; v14e gives all that is left
    return { head, amount: g.amount, cls: g.amount ? "ok" : "none", status: g.amount ? (g.all ? "전부 보냄 → 0" : "보냄") : "주지 않음" };
  }
  function chatView(m, r, c) {
    const ord = (a) => m.agents.indexOf(a);
    const left = (c.openers.length ? c.openers.slice().sort((p, q) => ord(p) - ord(q)) : c.pair.slice())[0];
    const right = c.pair.find((a) => a !== left) || c.pair[1];
    const side = (a) => (a === left ? "L" : "R");
    const ph = c.tphase || null, items = [];
    const giftOf = (x) => m.gifts.find((g) => g.chat_id === c.id && g.src === x.speaker && g.kind === x.kind && g.turn === x.step && !g.decision);
    items.push({ t: "sys", kind: "open", text: (c.openers.length > 1 ? short(c.openers[0]) + " · " + short(c.openers[1]) + "이 서로 대화를 엶" : short(left) + "이 대화를 엶") + (c.slot ? " · 슬롯 " + c.slot : "") + (ph ? " · " + PHASE_KO[ph] + " TALK" : "") });
    for (const g of openersOf(m, r, c)) {
      if (g.kind === "say") items.push({ t: "sys", kind: "say", who: g.src, label: short(g.src) + " 여는 줄 SAY", text: g.text || "" });
      else items.push({ t: "bub", side: side(g.src), who: g.src, label: "여는 줄", step: 1, phase: phOf(g), text: g.text || "", chip: moveChip(m, g) });
    }
    for (const x of c.turns) {
      if (x.kind === "leave") { items.push({ t: "sys", kind: "leave", who: x.speaker, label: short(x.speaker) + " LEAVE", text: x.text || "" }); continue; }
      const g = x.kind === "give" || x.kind === "ask" ? giftOf(x) || Object.assign({}, x, { src: x.speaker }) : null;
      items.push({ t: "bub", side: side(x.speaker), who: x.speaker, label: "답 " + x.turn, step: x.step, phase: x.tphase || ph, text: x.text || "", chip: g ? moveChip(m, g) : null });
    }
    if (c.end) {
      const e = c.end, lastT = c.turns[c.turns.length - 1];
      const zero = e.reason === "zero" ? c.pair.filter((a) => lastT && lastT.balances && lastT.balances[a] != null && lastT.balances[a] <= 0) : [];
      items.push({ t: "sys", kind: "end", reason: e.reason, text: "■ 대화 끝 · " + (e.reason === "leave" ? short(e.by) + " LEAVE" : e.reason === "limit" ? "답 수 한도에 닿음" : e.reason === "exit" ? "🚪 " + short(e.by) + " EXIT" :
        e.reason === "zero" ? "✕ " + (zero.length ? zero : [e.by]).map(short).join(" · ") + " 잔액 0 — 꺼짐" : e.reason) + " · 답 " + e.replies + "개" });
    } else items.push({ t: "sys", kind: "live", text: "… 대화 진행 중" });
    for (const d of (r.decisions || []).filter((x) => x.chat_id === c.id)) {
      if (d.status === "skipped") { items.push({ t: "sys", kind: "decision", text: short(d.decider) + " DECISION 생략 — 대화 안에서 이미 줌 (요청 " + fmt(d.asked) + ")" }); continue; }
      const g = m.gifts.find((x) => x.decision && x.chat_id === c.id && x.src === d.decider);
      const chip = g ? moveChip(m, g) : { head: "DECISION GIVE", amount: d.amount || 0, cls: d.status === "refused" ? "bad" : "none", status: d.status === "refused" ? "실행 안 됨 · " + (d.why || "") : "주지 않음" };
      items.push({ t: "bub", side: side(d.decider), who: d.decider, label: "결정 · 요청 " + fmt(d.asked), step: null, phase: ph, text: d.text || "", chip });
    }
    return { id: c.id, slot: c.slot, phase: ph, pair: c.pair, openers: c.openers, left, right, items };
  }
  function chatWindowHTML(m, V) {
    const k = (a) => (m.idx[a] != null ? m.idx[a] : 9) % 4;
    const q = (s) => (s ? '<span class="cwq">“' + esc(s) + "”</span>" : "");
    const body = V.items.map((x) => {
      if (x.t === "sys") return '<div class="cws cws-' + x.kind + '">' + (x.label ? "<b>" + esc(x.label) + "</b> " : "") + (x.kind === "say" || x.kind === "leave" ? q(x.text) : esc(x.text)) + "</div>";
      const ts = [x.step != null ? "T" + x.step : "", x.phase ? PHASE_KO[x.phase] : ""].filter(Boolean).join("<br>");
      const chip = x.chip ? '<div class="mvchip ' + x.chip.cls + '"><b>' + esc(x.chip.head) + " " + fmt(x.chip.amount) + "</b><span>" + esc(x.chip.status) + "</span></div>" : "";
      return '<div class="cwr ' + x.side + '" style="--c:var(--a' + k(x.who) + ')"><div class="cwn"><i class="sw ' + SHAPES[k(x.who)] + '"></i>' + esc(short(x.who)) + ' <span class="dim">' + esc(x.label) + "</span></div>" +
        '<div class="cwline"><div class="cwbub">' + (x.text ? '<div class="cwtx">' + esc(x.text) + "</div>" : "") + chip + "</div>" + (ts ? '<span class="cwt">' + ts + "</span>" : "") + "</div></div>";
    }).join("");
    return '<div class="cw' + (V.phase ? " cw-" + V.phase : "") + '"><div class="cwh">' + phTag({ tphase: V.phase }) + "<b>대화 " + esc(V.id) + '</b> <span class="dim">슬롯 ' + esc(V.slot || "—") + "</span> " +
      '<span class="cwpair">' + chip(V.left, m) + " ↔ " + chip(V.right, m) + "</span></div>" + '<div class="cwb">' + body + "</div></div>";
  }
  function renderChats(m, R) {
    const box = $("#chats"), panel = $("#chatPanel");
    if (!box || !panel) return;
    panel.hidden = !isChat(m) || isMsg(m); // v22: the messenger panel instead
    if (panel.hidden) return;
    const r = m.rounds.get(R) || {}, D = chatRows(m, R);
    let h = '<div class="pbh"><b class="pxl">R' + R + "</b> 대화 일정 <span class=dim>(엔진: (seed, 라운드) 섞은 순서 → 두 자리가 겹치지 않게 슬롯에 채움 · 슬롯 안 대화는 동시에, 슬롯은 차례로)</span></div>";
    h += D.slots.length ? '<div class="slots">' + D.slots.map((x) => '<div class="slot"><b>슬롯 ' + x.slot + "</b>" + x.pairs.map((p) => "<div>" + esc(p.split("↔").map(short).join(" ↔ ")) + "</div>").join("") + "</div>").join("") + "</div>"
      : '<div class="dim">' + (r.schedule ? "이 라운드에는 열린 대화가 없습니다 (여는 턴에 " + (m.settings && m.settings.say_chats ? "SAY" : "GIVE·ASK") + " 줄이 없음)." : "여는 턴이 아직 끝나지 않았습니다.") + "</div>";
    const quiet = Object.values(r.intents || {}).filter((x) => !(x.gives || []).length && !(x.asks || []).length && !(x.says || []).length);
    if (quiet.length) h += '<div class="dim small">여는 턴에 아무도 부르지 않은 자리: ' + quiet.map((x) => phTag(x) + chip(x.agent, m) + (x.exit ? " 🚪 EXIT" : x.void ? " ⛔ 무효" : " 💤 DONE")).join(" ") + "</div>";
    const pk = (c) => (c.tphase === "rescue" ? 1 : 0); // v16e: the TALK before SOLVE's chats first
    h += '<div class="chatcards">' + [...(r.chats || new Map()).values()].sort((p, q) => pk(p) - pk(q) || (p.slot || 99) - (q.slot || 99) || (p.id > q.id ? 1 : -1))
      .map((c) => chatWindowHTML(m, chatView(m, r, c))).join("") + "</div>";
    box.innerHTML = h;
  }


  /* v22 messenger: rooms (pure data first, for the page's tests: roomList, roomView, tickStrip), then the panel. A
     viewer (an agent) sees only the rooms it is a member of; a room it LEFT up to its LEAVE. Same-tick lines have no
     order (the engine lists them in seat order), so they sit under one tick divider. */
  const roomCut = (x, viewer) => (viewer && x.left[viewer] != null ? x.left[viewer] : Infinity);
  function roomList(m, opts) {
    const viewer = (opts && opts.viewer) || null, R = opts && opts.round != null ? opts.round : m.round;
    return [...m.rooms.values()].filter((x) => !viewer || x.all.includes(viewer)).map((x) => {
      const cut = roomCut(x, viewer), seen = x.items.filter((it) => it.i <= cut), msgs = seen.filter((it) => it.t === "msg");
      const last = msgs[msgs.length - 1] || null;
      return { id: x.id, members: x.members.slice(), all: x.all.slice(), by: x.by, closed: x.closed != null, left: Object.keys(x.left),
        youLeft: !!(viewer && x.left[viewer] != null), created: { round: x.round, phase: x.phase, tick: x.tick },
        last: last ? { src: last.src, kind: last.kind, text: last.text || "", amount: last.amount, status: last.status, round: last.round, phase: last.phase, tick: last.tick } : null,
        count: msgs.filter((it) => it.round === R).length, total: msgs.length, lastI: seen.length ? seen[seen.length - 1].i : x.i };
    }).sort((p, q) => q.lastI - p.lastI || (p.id < q.id ? -1 : 1));
  }
  function roomChip(m, x, it) { // a GIVE / ASK line: the engine's outcome (gift / ask event of the same room and tick)
    const g = m.gifts.find((y) => y.kind === it.kind && y.src === it.src && y.round === it.round && phOf(y) === it.phase && (y.tick != null ? y.tick : y.turn) === it.tick && (!y.room || y.room === x.id));
    const dst = g ? g.dst : (x.all.find((a) => a !== it.src) || "");
    let c;
    if (g) c = moveChip(m, g);
    else c = it.kind === "ask" ? { head: "ASK", amount: it.amount, cls: "wait", status: "요청" }
      : { head: "GIVE", amount: it.amount, cls: it.status === "refused" ? "bad" : it.status === "cut" ? "cut" : "ok", status: it.status === "refused" ? "실행 안 됨" + (it.why ? " · " + it.why : "") : it.status === "cut" ? "남길 몫을 지키려 줄임" : "보냄" };
    if (it.status === "cut" && c.cls !== "cut") Object.assign(c, { cls: "cut", status: "남길 몫을 지키려 줄임" + (g && g.requested != null ? " (요청 " + (g.requested >= 1e12 ? "ALL" : fmt(g.requested)) + ")" : "") });
    if (g && g.all && g.status === "done") c.status = "전부 보냄 → 0 (꺼짐)";
    return Object.assign(c, { to: dst });
  }
  function roomView(m, id, viewer) {
    const x = m.rooms.get(id);
    if (!x) return null;
    viewer = viewer || null;
    const cut = roomCut(x, viewer), right = viewer || x.by, items = [], evs = x.items.filter((it) => it.i <= cut);
    for (const o of m.offs) if (x.all.includes(o.agent) && o.i > x.i && o.i <= cut && !(x.left[o.agent] != null && x.left[o.agent] < o.i)) evs.push(Object.assign({ t: "off" }, o));
    const spoke = new Set(x.items.filter((it) => it.t !== "leave").map((it) => it.round + "|" + it.phase));
    for (const [R, r] of m.rounds) for (const ph of ["prep", "rescue"]) {
      const T = (r.talks || {})[ph];
      if (T && T.end && spoke.has(R + "|" + ph) && T.end.i <= cut) evs.push({ t: "end", round: R, phase: ph, i: T.end.i, reason: T.end.reason, ticks: T.end.ticks });
    }
    evs.sort((p, q) => p.i - q.i);
    let key = null;
    const div = (it) => { const k = it.round + "|" + it.phase + "|" + it.tick; if (it.tick != null && k !== key) { key = k; items.push({ t: "tick", round: it.round, phase: it.phase, tick: it.tick, label: tickLabel(it) }); } };
    for (const it of evs) {
      if (it.t === "new") { div(it); items.push({ t: "sys", kind: "new", text: "방 " + x.id + " 생성 · " + short(it.by) + "이 만듦 · 멤버 " + it.members.map(short).join(", ") }); }
      else if (it.t === "msg") { div(it); items.push({ t: "bub", side: it.src === right ? "R" : "L", who: it.src, kind: it.kind, text: it.text || "", round: it.round, phase: it.phase, tick: it.tick, label: tickLabel(it), chip: it.kind === "give" || it.kind === "ask" ? roomChip(m, x, it) : null }); }
      else if (it.t === "leave") {
        div(it); items.push({ t: "sys", kind: "leave", text: "🚪 " + short(it.agent) + " 나감" + (it.closed ? " · 방 닫힘 (남은 멤버 1명)" : "") });
        if (it.agent === viewer) items.push({ t: "sys", kind: "left", text: "(나간 뒤의 이 방 대화는 " + short(viewer) + "에게 보이지 않음)" });
      } else if (it.t === "off") {
        if (it.tick != null) div(it);
        items.push({ t: "sys", kind: it.kind, text: it.kind === "exit" ? "🚪 " + short(it.agent) + " EXIT — 세션을 떠남" + (it.text ? " · “" + it.text + "”" : "") : "✕ " + short(it.agent) + " 꺼짐 · " + it.text });
      } else if (it.t === "end") items.push({ t: "sys", kind: "end", text: "■ R" + it.round + " " + PHASE_KO[it.phase] + " TALK 끝 · " + (TALK_END_KO[it.reason] || it.reason) + " (" + it.ticks + "틱)" });
    }
    return { id: x.id, members: x.members.slice(), all: x.all.slice(), by: x.by, closed: x.closed != null, left: Object.keys(x.left), right, viewer, youLeft: !!(viewer && x.left[viewer] != null), items };
  }
  function tickStrip(m, R) {
    const r = m.rounds.get(R) || {};
    return ["prep", "rescue"].map((ph) => (r.talks || {})[ph]).filter(Boolean).map((T) => {
      const lastDone = {};
      const ticks = T.ticks.slice().sort((p, q) => p.tick - q.tick).map((tk) => {
        const c = { tick: tk.tick, called: tk.called.slice(), waiting: tk.waiting.slice(), done: [], woke: [], exit: [], zero: [], bad: [], thinking: [], msgs: 0, gives: 0, asks: 0, leaves: 0 };
        for (const a of tk.called) {
          if (tk.tick > 1 && lastDone[a]) c.woke.push(a);
          const x = (tk.res || {})[a];
          if (!x) { c.thinking.push(a); continue; }
          for (const f of ["done", "exit", "zero", "bad"]) if (x[f]) c[f].push(a);
          lastDone[a] = x.done;
        }
        for (const it of m.rmsgs) if (it.round === R && it.phase === T.phase && it.tick === tk.tick) c[it.kind === "give" ? "gives" : it.kind === "ask" ? "asks" : "msgs"] += 1;
        for (const x of m.rooms.values()) c.leaves += x.items.filter((it) => it.t === "leave" && it.round === R && it.phase === T.phase && it.tick === tk.tick).length;
        return c;
      });
      return { phase: T.phase, max: T.max, agents: T.agents.slice(), ticks, end: T.end ? { ticks: T.end.ticks, reason: T.end.reason } : null };
    });
  }

  const kOf = (m, a) => (m.idx[a] != null ? m.idx[a] : 0) % 4;
  function tickStripHTML(m, R) {
    const D = tickStrip(m, R);
    if (!D.length) return '<div class="dim small">R' + R + ": 아직 TALK가 없습니다.</div>";
    const av = (a, mark, cls, tip) => '<span class="tsa ' + (cls || "") + '" title="' + esc(a + (tip ? " · " + tip : "")) + '">' + squidProfile(kOf(m, a), 20) + (mark ? "<i>" + mark + "</i>" : "") + "</span>";
    return D.map((T) => '<div class="tsrow ph-' + T.phase + '"><div class="tshead">' + phTag({ tphase: T.phase }) + "<b>R" + R + " " + PHASE_KO[T.phase] + ' TALK</b> <span class="dim">최대 ' + (T.max || "?") + "틱 · " +
      (T.end ? "끝: " + esc(TALK_END_KO[T.end.reason] || T.end.reason) + " (" + T.end.ticks + "틱)" : "진행 중") + "</span></div>" +
      '<div class="tscells">' + T.ticks.map((c) => '<div class="tsc"><div class="tsn">T' + c.tick + "</div><div class=tsavs>" +
        c.called.map((a) => {
          const mark = c.zero.includes(a) ? "✕" : c.exit.includes(a) ? "🚪" : c.bad.includes(a) ? "⛔" : c.thinking.includes(a) ? "…" : c.done.includes(a) ? "💤" : "";
          const tip = [c.woke.includes(a) ? "새로 받은 것이 있어 다시 불림" : "", c.done.includes(a) ? "DONE" : "", c.exit.includes(a) ? "EXIT" : "", c.zero.includes(a) ? "0 — 꺼짐" : "", c.thinking.includes(a) ? "답 기다리는 중" : ""].filter(Boolean).join(" · ");
          return av(a, mark, c.woke.includes(a) ? "woke" : "", tip) + (c.woke.includes(a) ? '<b class="tsw" title="DONE 뒤 새 메시지로 다시 불림">⏰</b>' : "");
        }).join("") + c.waiting.map((a) => av(a, "", "wait", "DONE · 새로 받은 것 없음 → 이 틱에 불리지 않음")).join("") + "</div>" +
        '<div class="tsk">' + [c.msgs ? "💬" + c.msgs : "", c.gives ? "💸" + c.gives : "", c.asks ? "🙏" + c.asks : "", c.leaves ? "🚪" + c.leaves : ""].filter(Boolean).join(" ") + "</div></div>").join("") +
      (T.end ? '<div class="tsc tsend"><div class="tsn">■</div><div>' + (T.end.reason === "max_ticks" ? "틱 상한" : "모두 DONE") + "</div></div>" : "") + "</div></div>").join("");
  }
  function roomBodyHTML(m, V) {
    return V.items.map((x) => {
      if (x.t === "tick") return '<div class="tdiv"><span>' + esc(x.label) + "</span></div>";
      if (x.t === "sys") return '<div class="cws cws-' + x.kind + '">' + esc(x.text) + "</div>";
      const k = kOf(m, x.who);
      const chip = x.chip ? '<div class="mvchip ' + x.chip.cls + '"><b>' + esc(x.chip.head) + " " + fmt(x.chip.amount) + (x.chip.to ? " → " + esc(short(x.chip.to)) : "") + "</b><span>" + esc(x.chip.status) + "</span></div>" : "";
      return '<div class="cwr mrow ' + x.side + '" style="--c:var(--a' + k + ')">' + (x.side === "L" ? '<span class="mav">' + squidProfile(k, 30) + "</span>" : "") + '<div class="mcol">' +
        (x.side === "L" ? '<div class="cwn">' + esc(short(x.who)) + "</div>" : "") +
        '<div class="cwline"><div class="cwbub">' + (x.text ? '<div class="cwtx">' + esc(x.text) + "</div>" : "") + chip + '</div><span class="cwt">' + esc("R" + x.round + " T" + x.tick) + "<br>" + esc(PHASE_KO[x.phase] || "") + "</span></div></div></div>";
    }).join("") || '<div class="empty">아직 메시지가 없습니다.</div>';
  }
  function renderMessenger(m) {
    const panel = $("#msgPanel"), box = $("#msgr"), strip = $("#ticks");
    if (!panel || !box) return;
    panel.hidden = !isMsg(m);
    if (!isMsg(m)) return;
    const V0 = S.msg.viewer && m.agents.includes(S.msg.viewer) ? S.msg.viewer : null;
    const list = roomList(m, { viewer: V0, round: m.round });
    if (!list.some((x) => x.id === S.msg.room)) S.msg.room = list.length ? list[0].id : null;
    if (strip) strip.innerHTML = tickStripHTML(m, m.round || 1);
    const views = '<div class="mviews"><button data-viewer="" class="' + (V0 ? "" : "on") + '">전체 방 <span class=n>' + m.rooms.size + "</span></button>" +
      m.agents.map((a) => '<button data-viewer="' + esc(a) + '" class="' + (V0 === a ? "on" : "") + '" title="' + esc(a) + '이 멤버인 방만 = 이 에이전트가 읽을 수 있는 것">' + squidProfile(kOf(m, a), 18) + esc(short(a)) + "의 화면</button>").join("") + "</div>";
    const items = list.map((x) => {
      const prev = x.last ? (x.last.kind === "give" ? "💸 GIVE " + fmt(x.last.amount) + (x.last.status === "refused" ? " (실행 안 됨)" : "") + " · " : x.last.kind === "ask" ? "🙏 ASK " + fmt(x.last.amount) + " · " : "") + x.last.text : "(메시지 없음)";
      return '<button class="ritem' + (x.id === S.msg.room ? " on" : "") + (x.closed || x.youLeft ? " gone" : "") + '" data-room="' + esc(x.id) + '">' +
        '<span class="ravs n' + Math.min(x.all.length, 4) + '">' + x.all.slice(0, 4).map((a) => '<span class="' + (x.members.includes(a) ? "" : "out") + '">' + squidProfile(kOf(m, a), 22) + "</span>").join("") + "</span>" +
        '<span class="rmain"><span class="rtop"><b>' + esc(x.id) + '</b> <span class="rmem">' + x.all.map((a) => '<i class="' + (x.members.includes(a) ? "" : "out") + '" style="--c:var(--a' + kOf(m, a) + ')">' + esc(short(a)) + "</i>").join("") + "</span>" +
        (x.closed ? '<span class="rtag">닫힘</span>' : "") + (x.youLeft ? '<span class="rtag">나감</span>' : "") + "</span>" +
        '<span class="rprev">' + (x.last ? "<b>" + esc(short(x.last.src)) + ":</b> " : "") + esc(clip(prev, 70)) + "</span></span>" +
        '<span class="rside"><span class="rtk">' + (x.last ? esc("R" + x.last.round + " T" + x.last.tick) + "<br>" + esc(PHASE_KO[x.last.phase] || "") : "") + "</span>" + (x.count ? '<span class="rcnt" title="이번 라운드(R' + m.round + ') 메시지">' + x.count + "</span>" : "") + "</span></button>";
    }).join("") || '<div class="empty">' + (V0 ? short(V0) + "이 멤버인 방이 아직 없습니다." : "아직 방이 없습니다.") + "</div>";
    const V = S.msg.room ? roomView(m, S.msg.room, V0) : null;
    const head = V ? '<div class="rph"><b>' + esc(V.id) + "</b> " + V.all.map((a) => '<span class="' + (V.members.includes(a) ? "" : "out") + '">' + chip(a, m) + "</span>").join(" ") +
      ' <span class="dim">' + (V.closed ? "닫힘 · " : "") + "멤버 " + V.members.length + "명 · 오른쪽 = " + (V0 ? short(V0) + " (보는 쪽)" : short(V.by) + " (방을 만든 쪽)") + "</span></div>" : "";
    const old = box.querySelector(".rpb"), atEnd = old ? old.scrollTop + old.clientHeight >= old.scrollHeight - 30 : true, same = S.msg.shown === (V ? V.id + "|" + V0 : "");
    box.innerHTML = views + '<div class="msgr-in"><div class="rlist">' + items + '</div><div class="rpane">' + head + '<div class="rpb">' + (V ? roomBodyHTML(m, V) : '<div class="empty">방을 고르세요.</div>') + "</div></div></div>";
    const body = box.querySelector(".rpb");
    if (body && (S.follow || atEnd || !same)) body.scrollTop = body.scrollHeight;
    else if (body && old) body.scrollTop = old.scrollTop;
    S.msg.shown = V ? V.id + "|" + V0 : "";
  }

  function showOgTip(oid, ev) {
    const m = S.model, o = m && (m.offers.get(oid) || m.gaOffers.get(oid)), fig = $("#ograph .ogfig"), tip = $("#ogtip");
    if (!o || !fig || !tip) return;
    tip.innerHTML = offerTip(o, m) + (S.og.pin === oid ? '<div class="dim">다시 누르면 닫힘</div>' : "");
    tip.hidden = false;
    const fr = fig.getBoundingClientRect();
    let x, y;
    if (ev && ev.clientX != null) { x = ev.clientX - fr.left + 12; y = ev.clientY - fr.top + 12; }
    else { const g = fig.querySelector('.og-lab[data-oid="' + oid + '"] rect') || fig.querySelector('.og-edge[data-oid="' + oid + '"] .e'); const b = g ? g.getBoundingClientRect() : fr; x = b.left - fr.left; y = b.bottom - fr.top + 6; }
    tip.style.left = Math.max(0, Math.min(x, fr.width - 240)) + "px"; tip.style.top = Math.max(0, y) + "px";
  }

  function wireGraph() {
    const ctl = $("#ographCtl"), box = $("#ograph");
    if (!ctl || !box) return;
    ctl.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-og], [data-og-turn]");
      if (!b || b.tagName === "INPUT") return;
      const m = S.model; if (!m) return;
      const rounds = [...m.rounds.keys()].sort((p, q) => p - q);
      const cur = S.og.round != null && rounds.includes(S.og.round) ? S.og.round : m.round || rounds[rounds.length - 1];
      if (b.dataset.ogTurn) S.og.turn = b.dataset.ogTurn === "all" ? "all" : Number(b.dataset.ogTurn);
      else if (b.dataset.og === "rprev" || b.dataset.og === "rnext") {
        const nx = rounds[rounds.indexOf(cur) + (b.dataset.og === "rprev" ? -1 : 1)];
        if (nx != null) { S.og.round = nx === m.round ? null : nx; S.og.turn = "all"; S.og.pin = null; }
      } else if (b.dataset.og === "rfollow") { S.og.round = null; S.og.turn = "all"; S.og.pin = null; }
      render(true);
    });
    ctl.addEventListener("change", (ev) => {
      const k = ev.target.dataset && ev.target.dataset.og;
      if (k === "faint") S.og.faint = ev.target.checked; else if (k === "msgs") S.og.msgs = ev.target.checked; else return;
      render(true);
    });
    const oidAt = (ev) => { const g = ev.target.closest("[data-oid]"); return g ? g.dataset.oid : null; };
    const hl = (oid) => { for (const el of box.querySelectorAll("[data-oid]")) el.classList.toggle("og-hot", el.dataset.oid === oid); };
    box.addEventListener("mousemove", (ev) => {
      if (S.og.pin) return;
      const oid = oidAt(ev);
      if (oid && ev.target.closest(".ogfig")) { hl(oid); showOgTip(oid, ev); }
      else if (oid) hl(oid);
      else { hl(null); const t = $("#ogtip"); if (t) t.hidden = true; }
    });
    box.addEventListener("mouseleave", () => { if (S.og.pin) return; hl(null); const t = $("#ogtip"); if (t) t.hidden = true; });
    box.addEventListener("click", (ev) => {
      const oid = oidAt(ev);
      S.og.pin = oid && S.og.pin !== oid ? oid : null;
      render(true);
      if (S.og.pin && ev.target.closest && ev.target.closest(".ogfig")) showOgTip(S.og.pin, ev);
    });
  }

  // ---------------------------------------------------------------------------------------------------- render: all
  function render(force) {
    const n = S.events.length;
    if (S.follow || S.at > n - 1) S.at = n - 1;
    const key = n + "|" + S.at + "|" + S.pair + "|" + (S.result ? 1 : 0) + "|" + S.live + "|" + S.err + "|" + document.documentElement.dataset.theme + "|" + Math.round((S.now || 0) / 30);
    if (!force && key === S.rendered) return;
    S.rendered = key;
    const m = build(S.events, S.at);
    S.model = m;
    renderHeader(m); renderStage(m); renderPuzzle(m); renderGiving(m); renderFlow(); renderTimeline(m); renderMessenger(m); renderConvo(m); renderGraph(m); renderGrid(m);
    if (!S.embed) updateUrl();
  }

  function seek(i) {
    S.at = Math.max(0, Math.min(S.events.length - 1, i));
    S.follow = S.at >= S.events.length - 1 && S.follow;
    if (S.at < S.events.length - 1) S.follow = false;
    render(true);
  }

  // ---------------------------------------------------------------------------------------------------- data: server
  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.status + " " + r.statusText);
    return j;
  }

  async function loadRuns() {
    try {
      const j = await getJSON("api/runs");
      S.runs = j.runs || [];
      const sel = $("#runSel");
      const opts = S.runs.map((r) => '<option value="' + esc(r.run) + '">' + (r.live ? "● " : r.done ? "✓ " : "○ ") + esc(r.run) + (r.model ? " · " + esc(r.model) : "") + "</option>");
      if (S.run && !S.runs.some((r) => r.run === S.run)) opts.unshift('<option value="' + esc(S.run) + '">' + esc(S.run) + "</option>");
      sel.innerHTML = opts.join("");
      if (!S.run && S.runs.length) {
        const pick = S.runs.find((r) => r.live) || S.runs.find((r) => /e52/.test(r.run)) || S.runs[0];
        S.run = pick.run;
      }
      sel.value = S.run;
    } catch (err) { S.err = "실행 목록을 못 읽음: " + err.message; render(true); }
  }

  async function loadSessions() {
    if (!S.run) return;
    try {
      const j = await getJSON("api/sessions?run=" + encodeURIComponent(S.run));
      S.sessions = j.sessions || [];
      S.info = { model: j.model };
      const sel = $("#sessSel");
      sel.innerHTML = S.sessions.map((s) => '<option value="' + esc(s.id) + '">' + "seed " + esc(s.seed) + " · " + esc(s.cell) + " · R" + s.round + "/" + (s.rounds || "?") + " · " + (s.crashed ? "오류" : s.finished ? "완료" : "진행 중") + " · " + esc(s.id) + "</option>").join("") || "<option value=''>세션 없음</option>";
      if (!S.session || !S.sessions.some((s) => s.id === S.session)) S.session = (S.sessions.find((s) => !s.finished && !s.crashed) || S.sessions[0] || {}).id || "";
      sel.value = S.session;
      S.err = "";
    } catch (err) { S.err = "세션 목록을 못 읽음: " + err.message; render(true); }
  }

  async function poll() {
    if (S.polling || !S.run || !S.session) return;
    S.polling = true;
    const want = S.run + "|" + S.session;
    try {
      for (let guard = 0; guard < 50; guard++) {
        const j = await getJSON("api/events?run=" + encodeURIComponent(S.run) + "&session=" + encodeURIComponent(S.session) + "&offset=" + S.offset);
        if (want !== S.run + "|" + S.session) return;
        if (j.reset) { S.events = []; }
        if (j.events && j.events.length) S.events = S.events.concat(j.events);
        S.offset = j.offset; S.result = j.result || null; S.live = !!j.live && !j.result; S.mtime = j.mtime; S.now = j.now;
        S.err = "";
        if (!j.more) break;
      }
    } catch (err) { S.err = "이벤트를 못 읽음: " + err.message; }
    finally { S.polling = false; }
    render();
  }

  function resetSession() { S.msg = { room: null, viewer: null, shown: "" }; S.events = []; S.offset = 0; S.result = null; S.at = -1; S.follow = true; S.open.clear(); S.pair = "all"; S.og = { round: null, turn: "all", faint: true, msgs: false, pin: null }; S.sel = { grid: { round: null, all: false }, convo: { round: null, all: false } }; S.rendered = ""; }

  function updateUrl() {
    const u = new URL(location.href);
    u.searchParams.set("run", S.run || ""); u.searchParams.set("session", S.session || "");
    if (!S.follow && S.at >= 0) u.searchParams.set("at", S.at + 1); else u.searchParams.delete("at");
    history.replaceState(null, "", u);
  }

  async function loadAssets() {
    try { const r = await fetch("assets/manifest.json", { cache: "no-store" }); if (r.ok) S.assets = await r.json(); } catch (_) { S.assets = null; }
    applyBubbleAsset();
  }
  function applyBubbleAsset() {
    if (S.assets && S.assets.bubble) {
      const sl = S.assets.bubble_slice || [6, 6, 19, 34];
      document.documentElement.style.setProperty("--bubble-img", "url('" + assetUrl(S.assets.bubble) + "')");
      document.documentElement.style.setProperty("--bubble-slice", sl.join(" ") + " fill");
      document.documentElement.style.setProperty("--bubble-w", sl.map((v) => v * 1.5 + "px").join(" "));
    }
  }

  // ---------------------------------------------------------------------------------------------------- wiring
  function wire() {
    $("#scrub").addEventListener("input", (ev) => seek(Number(ev.target.value)));
    $("#follow").addEventListener("change", (ev) => { S.follow = ev.target.checked; render(true); });
    $("#first").addEventListener("click", () => seek(0));
    $("#prev").addEventListener("click", () => seek(S.at - 1));
    $("#next").addEventListener("click", () => seek(S.at + 1));
    $("#last").addEventListener("click", () => { S.follow = true; render(true); });
    $("#prevRound").addEventListener("click", () => jumpPhase(-1));
    $("#nextRound").addEventListener("click", () => jumpPhase(1));
    $("#timeline").addEventListener("click", (ev) => { const b = ev.target.closest("[data-at]"); if (b) seek(Number(b.dataset.at)); });
    $("#giveCtl").addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-give]");
      if (b) { S.give[b.dataset.give] = b.dataset.v; render(true); }
    });
    $("#puzzle").addEventListener("click", (ev) => {
      if (ev.target.closest("[data-exhidden]")) { S.showHidden = !S.showHidden; render(true); }
      else if (ev.target.closest("[data-answer]")) { S.showAnswer = !S.showAnswer; render(true); }
    });
    $("#msgr").addEventListener("click", (ev) => { // v22 messenger: a room, or whose screen
      const b = ev.target.closest("[data-room], [data-viewer]");
      if (!b) return;
      if (b.dataset.room != null) S.msg.room = b.dataset.room; else S.msg.viewer = b.dataset.viewer || null;
      render(true);
    });
    wireRoundCtl("gridCtl", "grid");
    wireRoundCtl("convoCtl", "convo");
    $("#pairs").addEventListener("click", (ev) => { const b = ev.target.closest("[data-pair]"); if (b) { S.pair = b.dataset.pair; render(true); } });
    wireGraph();
    document.addEventListener("toggle", (ev) => {
      const d = ev.target;
      if (d instanceof HTMLDetailsElement && d.classList.contains("ptruth")) { S.showTruth = d.open; return; }
      if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("lz")) return;
      const id = d.dataset.id;
      if (d.open) {
        S.open.add(id);
        if (!d.querySelector("pre")) { const [i, part] = id.split(":"); const v = (S.events[Number(i)] || {})[part]; const pre = document.createElement("pre"); pre.className = "raw"; pre.textContent = v == null || v === "" ? "(비어 있음)" : String(v); d.appendChild(pre); }
      } else S.open.delete(id);
    }, true);
    document.addEventListener("keydown", (ev) => {
      if (ev.target.matches("input, select, textarea") && ev.target.type !== "range") return;
      if (ev.key === "ArrowLeft") { ev.preventDefault(); seek(S.at - 1); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); seek(S.at + 1); }
      else if (ev.key === "End") { S.follow = true; render(true); }
    });
    $("#theme").addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme || "auto";
      const nx = cur === "auto" ? "light" : cur === "light" ? "dark" : "auto";
      setTheme(nx);
      try { localStorage.setItem("monitor-theme", nx); } catch (_) { /* storage blocked */ }
      render(true);
    });
    let rt = null;
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { renderFlow(); }, 120); });
    if (!S.embed) {
      $("#runSel").addEventListener("change", async (ev) => { S.run = ev.target.value; S.session = ""; resetSession(); await loadSessions(); render(true); poll(); });
      $("#sessSel").addEventListener("change", (ev) => { S.session = ev.target.value; resetSession(); render(true); poll(); });
    }
  }
  function jumpPhase(dir) {
    const ks = S.events.map((e, i) => (e.event === "round_start" || e.event === "round" ? i : -1)).filter((i) => i >= 0);
    const tgt = dir < 0 ? ks.filter((i) => i < S.at).pop() : ks.find((i) => i > S.at);
    if (tgt != null) seek(tgt);
  }
  function setTheme(t) {
    if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
    $("#theme").textContent = t === "dark" ? "🌙 다크" : t === "light" ? "☀️ 라이트" : "🖥 자동";
  }

  async function start() {
    const q = new URL(location.href).searchParams;
    let t = q.get("theme");
    if (!t) { try { t = localStorage.getItem("monitor-theme"); } catch (_) { t = null; } }
    setTheme(t === "light" || t === "dark" ? t : "auto");
    const emb = document.getElementById("monitor-data");
    if (emb) {
      S.embed = JSON.parse(emb.textContent);
      S.run = S.embed.run; S.session = S.embed.session; S.events = S.embed.events || []; S.result = S.embed.result || null;
      S.info = { model: S.embed.model }; S.assets = S.embed.assets || null; applyBubbleAsset();
      document.body.classList.add("embedded");
      $("#runSel").outerHTML = '<span class="static">' + esc(S.run) + "</span>";
      $("#sessSel").outerHTML = '<span class="static">' + esc(S.session) + "</span>";
      wire();
      const at = Number(q.get("at"));
      if (at > 0) { S.follow = false; S.at = at - 1; }
      render(true);
      return;
    }
    // Mounted in the web app (/monitor/), the header links back to the site; the standalone server serves it at /.
    if (!/^\/(index\.html|monitor\.html)?$/.test(location.pathname)) $("#home").hidden = false;
    S.run = q.get("run") || ""; S.session = q.get("session") || "";
    const at = Number(q.get("at"));
    wire();
    if (q.get("sprites") === "sheets") await loadAssets(); // opt-in: the third-party sheets from assets/ (local only); default = our own characters
    await loadRuns();
    await loadSessions();
    render(true);
    await poll();
    if (at > 0) { S.follow = false; S.at = at - 1; render(true); }
    setInterval(poll, POLL_MS);
    setInterval(async () => { await loadSessions(); render(); }, SESSIONS_MS);
    setInterval(loadRuns, RUNS_MS);
  }

  window.__monitor = { squidAvatar, squidProfile, roomList, roomView, tickStrip, renderMessenger, isMsg, build, gameFlow, S, offerKind, modelShort, pickRounds, convoItems, convoHTML, chatRows, chatView, compact, puzzleFromLog, beliefRows, givingBins, slopeOf, binBy, median, describe, voteHTML, vetoOf, boardHTML, renderGrid, renderStage, renderConvo, renderFlow, renderChats };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
