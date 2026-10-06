/* squid5 5.2 v9-talk arena monitor: replays one session's events (live from serve.py, or embedded by export.py).
   State is always recomputed from events[0..at], so the scrubber and live follow share one code path. */
(function () {
  "use strict";

  // ---------------------------------------------------------------------------------------------------- constants
  const POLL_MS = 1500;
  const SESSIONS_MS = 10000;
  const RUNS_MS = 30000;
  const SHAPES = ["circle", "square", "triangle", "diamond"];
  const HAIR = ["#1f1a24", "#d9b04a", "#6b2f22", "#2b1b12"];
  const SKIN = ["#f2c9a0", "#f6d3b0", "#e8b48c", "#a86b45"];
  const STATUS_KO = { in: "참여 중", dead: "종료됨 ✕", exited: "퇴장 🚪" };
  const XSTAT_KO = { done: "체결", void: "무효", lapsed: "만료", withdrawn: "철회", open: "열림", accepted: "수락됨", rejected: "거절됨" };

  // ---------------------------------------------------------------------------------------------------- app state
  const S = {
    embed: null, run: "", session: "", events: [], offset: 0, result: null, info: null,
    at: -1, follow: true, pair: "all", runs: [], sessions: [], assets: null, open: new Set(),
    live: false, mtime: 0, now: 0, rendered: "", polling: false, err: "",
    puzzles: new Map(), showTruth: false,
    og: { round: null, turn: "all", faint: true, msgs: false, pin: null }, // offer graph: round null = follow the replay bar
  };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n == null || n === "" ? "—" : Number(n).toLocaleString("en-US"));
  const sgn = (n) => (n > 0 ? "+" + fmt(n) : n < 0 ? "−" + fmt(-n) : "±0");
  const clip = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
  const short = (a) => String(a || "").replace(/^agent-/, "");
  const legKo = (v) => (v == null ? "없음" : v === "EXAMPLE" ? "예시" : fmt(v) + " 토큰");
  const legShort = (v) => (v == null ? "없음" : v === "EXAMPLE" ? "예시" : fmt(v));

  // ---------------------------------------------------------------------------------------------------- model
  function newAgent(a, start) {
    return { id: a, balance: start, record: 0, status: "in", pending: null, bubble: null, delta: 0, gen: 0, model: null, exitFlag: false, exitReason: null, face: 0, lastRoundGen: 0 };
  }

  function build(evs, upto) {
    const m = {
      sid: "", cell: "", seed: null, start: 0, settings: {}, seats: {}, agents: [], ag: {}, round: 0,
      phase: "대기", phaseKey: "wait", rounds: new Map(), offers: new Map(), messages: [], series: [], timeline: [],
      warnings: [], error: null, last: null, ann: {}, idx: {},
    };
    const R = (r) => {
      if (!m.rounds.has(r)) m.rounds.set(r, { r, profile: "", taking: [], startEv: null, startIdx: -1, turns: new Map(), exchanges: [], solve: null, end: null, endIdx: -1, seq: 0 });
      return m.rounds.get(r);
    };
    const snap = () => { const o = {}; for (const a of m.agents) o[a] = { balance: m.ag[a].balance, record: m.ag[a].record, status: m.ag[a].status }; return o; };
    const point = (i, label, round) => { const bal = {}; for (const a of m.agents) bal[a] = m.ag[a].balance; m.series.push({ i, label, round, bal }); };
    const setBal = (a, v) => { const g = m.ag[a]; if (!g || v == null) return; if (v !== g.balance) g.delta = v - g.balance; g.balance = v; };

    for (let i = 0; i <= upto && i < evs.length; i++) {
      const e = evs[i];
      m.last = e;
      const kind = e.event;
      if (kind === "session_start") {
        m.sid = e.session_id; m.cell = e.cell_id; m.seed = e.seed; m.start = e.start; m.settings = e.settings || {}; m.seats = e.seats || {};
        m.agents = (e.agents || []).slice();
        m.agents.forEach((a, k) => { m.ag[a] = newAgent(a, e.start); m.ag[a].model = m.seats[a] || null; m.idx[a] = k; });
        m.phase = "시작"; m.phaseKey = "start";
        point(i, "시작", 0);
        m.timeline.push({ i, label: "시작", round: 0, kind: "start", state: snap() });
      } else if (kind === "round_start") {
        const r = R(e.round); r.profile = e.profile; r.taking = e.taking_part || []; r.startEv = e; r.startIdx = i;
        m.round = e.round;
        for (const a of m.agents) {
          const g = m.ag[a];
          g.gen = 0; g.pending = null; g.exitFlag = false;
          const before = g.balance;
          setBal(a, (e.balances || {})[a]);
          const gone = (e.gone || {})[a];
          if (gone) g.status = gone;
          if (!gone) g.bubble = { lines: [["🧾", "유지비 " + sgn(g.balance - before)]], kind: "upkeep" };
        }
        m.phase = "UPKEEP"; m.phaseKey = "upkeep";
        point(i, "R" + e.round + " 시작(유지비 후)", e.round);
        m.timeline.push({ i, label: "R" + e.round + " 시작", round: e.round, kind: "rstart", state: snap() });
      } else if (kind === "call_start") {
        const r = R(e.round);
        for (const [a, v] of Object.entries(e.balances || {})) setBal(a, v);
        if (e.kind === "talk") {
          r.turns.set(e.turn, { k: e.turn, startIdx: i, called: e.agents || [], calls: {} });
          m.phase = "TALK " + e.turn + "턴"; m.phaseKey = "talk";
        } else {
          r.solve = { startIdx: i, called: e.agents || [], calls: {} };
          for (const a of r.taking) {
            const g = m.ag[a];
            if (g && !(e.agents || []).includes(a) && g.status === "in") g.status = g.exitFlag ? "exited" : g.balance <= 0 ? "dead" : g.status;
          }
          m.phase = "SOLVE"; m.phaseKey = "solve";
        }
        for (const a of e.agents || []) {
          if (!m.ag[a]) continue;
          m.ag[a].pending = { kind: e.kind, turn: e.turn, round: e.round };
          m.ag[a].bubble = { lines: [["🧠", e.kind === "talk" ? "TALK " + e.turn + " 생각 중" : "SOLVE 푸는 중"]], kind: "think" };
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
          const t = r.turns.get(e.turn) || (r.turns.set(e.turn, { k: e.turn, startIdx: i, called: [], calls: {} }), r.turns.get(e.turn));
          t.calls[a] = i;
          const ann = applyTalk(m, r, e, i);
          m.ann[i] = ann;
          g.bubble = talkBubble(m, e, ann);
          if (e.parsed && e.parsed.exit && e.balance_after > 0) { g.exitFlag = true; g.exitReason = e.parsed.exit_reason || null; }
          m.phase = "TALK " + e.turn + "턴"; m.phaseKey = "talk";
          point(i, "R" + e.round + " T" + e.turn + " · " + a, e.round);
          const called = t.called.length ? t.called : Object.keys(t.calls);
          if (called.every((b) => t.calls[b] != null)) m.timeline.push({ i, label: "R" + e.round + " T" + e.turn, round: e.round, kind: "turn", state: snap() });
        } else {
          if (!r.solve) r.solve = { startIdx: i, called: [], calls: {} };
          r.solve.calls[a] = i;
          g.bubble = solveBubble(e, m);
          m.phase = "SOLVE"; m.phaseKey = "solve";
          point(i, "R" + e.round + " SOLVE · " + a, e.round);
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
          if (row.paid) lines.push(["💰", "상금 +" + fmt(row.paid)]);
          if (row.charged) lines.push(["💸", "벌금 −" + fmt(row.charged)]);
          if (!lines.length) lines.push(["🧮", row.passed ? "PASS · 정산 없음" : "정산 없음"]);
          if (g.status === "dead") lines.unshift(["✕", "종료됨"]);
          if (g.status === "exited") lines.unshift(["🚪", "퇴장"]);
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
    return m;
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

  // ---------------------------------------------------------------------------------------------------- avatars
  const FALLBACK = [
    "....HHHH....",
    "...HHHHHH...",
    "..HHSSSSHH..",
    "..HSESSESH..",
    "..HSSSSSSH..",
    "...SSMMSS...",
    "....SSSS....",
    "..BBBBBBBB..",
    ".SBBWBBWBBS.",
    ".SBBBBBBBBS.",
    "...PP..PP...",
    "...KK..KK...",
  ];
  function fallbackAvatar(k, size) {
    const col = { H: HAIR[k % 4], S: SKIN[k % 4], E: "#141414", M: "#b5524b", B: "var(--a" + (k % 4) + ")", W: "rgba(255,255,255,.55)", P: "#3b3f4a", K: "#191a1f" };
    let rects = "";
    FALLBACK.forEach((row, y) => [...row].forEach((ch, x) => { if (col[ch]) rects += '<rect x="' + x + '" y="' + y + '" width="1.02" height="1.02" fill="' + col[ch] + '"/>'; }));
    return '<svg class="pix" viewBox="0 0 12 12" width="' + size + '" height="' + size + '" shape-rendering="crispEdges" aria-hidden="true">' + rects + "</svg>";
  }
  function assetUrl(p) { if (!p) return null; return p.startsWith("data:") ? p : new URL("assets/" + p, location.href).href; }
  function character(k) { const c = S.assets && S.assets.characters && S.assets.characters.length ? S.assets.characters[k % S.assets.characters.length] : null; return c; }
  function profileIcon(a, m, size) {
    const k = m.idx[a] != null ? m.idx[a] : 0, c = character(k);
    if (c && c.profile) return '<img class="prof" src="' + esc(assetUrl(c.profile)) + '" width="' + size + '" height="' + size + '" alt="">';
    return fallbackAvatar(k, size);
  }
  function chip(a, m) {
    const k = m.idx[a] != null ? m.idx[a] : 9;
    return '<span class="chip" style="--c:var(--a' + (k % 4) + ')"><i class="sw ' + SHAPES[k % 4] + '"></i>' + esc(a) + "</span>";
  }

  // ---------------------------------------------------------------------------------------------------- render: header
  function describe(e) {
    if (!e) return "";
    switch (e.event) {
      case "session_start": return "세션 시작 · seed " + e.seed;
      case "round_start": return "R" + e.round + " 시작 · 유지비 차감 · " + e.profile;
      case "call_start": return "R" + e.round + " " + (e.kind === "talk" ? "TALK " + e.turn : "SOLVE") + " 호출 → " + (e.agents || []).map(short).join(", ");
      case "call": return "R" + e.round + " " + (e.kind === "talk" ? "TALK " + e.turn : "SOLVE") + " · " + e.agent + " 응답 " + fmt(e.used) + " 토큰";
      case "exchange": return "R" + e.round + " 교환 " + e.id + " · " + (XSTAT_KO[e.status] || e.status);
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
    if (m.sid) info.push("세션 <code>" + esc(m.sid) + "</code>", "시작 잔액 " + fmt(m.start), "TALK 상한 " + fmt(m.settings.talk_cap) + " · SOLVE 상한 " + fmt(m.settings.solve_cap), "상금/인 " + fmt(m.settings.prize) + " · 유지비 " + fmt(m.settings.upkeep) + " · 벌금 " + fmt(m.settings.charge));
    $("#sessInfo").innerHTML = info.join(" <span class=dim>·</span> ");
    const banners = [];
    if (m.error) banners.push('<div class="banner bad">세션이 오류로 중단됨: <code>' + esc(clip(m.error, 400)) + "</code></div>");
    if (S.result && S.at >= n - 1) {
      const f = S.result.final || {};
      banners.push('<div class="banner ok">세션 종료 · ' + S.result.rounds_played + "라운드 · 최종 상금 " + ((f.winner || []).length ? (f.winner || []).map((a) => chip(a, m)).join(" ") + " 각 " + fmt(f.prize_each) : "받은 에이전트 없음") + "</div>");
    }
    for (const w of m.warnings) banners.push('<div class="banner warn">⚠ ' + esc(w) + "</div>");
    if (S.err) banners.push('<div class="banner bad">' + esc(S.err) + "</div>");
    $("#banners").innerHTML = banners.join("");
  }

  // ---------------------------------------------------------------------------------------------------- render: stage
  function hpColor(frac) { return frac > 0.6 ? "var(--hp-good)" : frac > 0.3 ? "var(--hp-warn)" : "var(--hp-bad)"; }

  function renderStage(m) {
    const max = Math.max(m.start || 1, ...m.agents.map((a) => m.ag[a].balance || 0));
    const html = m.agents.map((a, k) => {
      const g = m.ag[a], c = character(k);
      const frac = m.start ? g.balance / m.start : 0;
      let face = 0;
      const b = g.bubble;
      const lastMsg = b && b.kind === "talk" && b.lines.find((l) => l[0] === "💬");
      if (lastMsg) { const dst = (lastMsg[1].match(/→ (agent-\d+)/) || [])[1]; if (dst && m.idx[dst] != null) face = m.idx[dst] > k ? 2 : 1; }
      if (g.status === "exited") face = 2;
      const cls = ["actor", g.status, g.pending ? "thinking" : "", g.exitFlag && g.status === "in" ? "leaving" : ""].join(" ");
      const sprite = c
        ? '<div class="sprite" style="background-image:url(\'' + esc(assetUrl(c.sheet)) + "');--row:" + face + '"></div>'
        : '<div class="sprite gen">' + fallbackAvatar(k, 84) + "</div>";
      const lines = b ? b.lines.slice(0, 4) : [["·", "아직 행동 없음"]];
      const more = b && b.lines.length > 4 ? '<div class="bl more">+' + (b.lines.length - 4) + "줄 더</div>" : "";
      const full = b ? b.lines.map((l) => l.join(" ")).join("\n") : "";
      const bubble = '<div class="bubble ' + (S.assets && S.assets.bubble ? "img " : "") + (b ? "k-" + b.kind : "k-none") + '" title="' + esc(full) + '"><div class="bh">' + esc(short(a)) + ":</div>" +
        lines.map((l) => '<div class="bl"><span class="em">' + esc(l[0]) + "</span> " + esc(l[1]) + (b && b.kind === "think" ? '<span class="dots"><i>.</i><i>.</i><i>.</i></span>' : "") + "</div>").join("") + more + "</div>";
      const width = Math.max(0, Math.min(100, (g.balance / max) * 100));
      const startTick = m.start ? (m.start / max) * 100 : 100;
      const statusBadge = '<span class="badge s-' + g.status + '"' + (g.exitReason ? ' title="EXIT 이유: ' + esc(g.exitReason) + '"' : "") + ">" + (g.status === "in" ? (g.exitFlag ? "퇴장 예정 🚪" : "참여 중") : STATUS_KO[g.status] || g.status) + "</span>";
      return '<div class="' + cls + '" style="--c:var(--a' + k + ')">' +
        '<div class="bubble-wrap">' + bubble + "</div>" +
        '<div class="floor"><div class="spot">' + sprite + (g.status === "dead" ? '<div class="xmark">✕</div>' : "") + "</div></div>" +
        '<div class="card-info">' +
        '<div class="who"><i class="sw ' + SHAPES[k] + '"></i><b class="pxl">' + esc(a) + "</b>" + statusBadge + "</div>" +
        '<div class="model">' + esc(g.model || S.info && S.info.model || "모델 미상") + "</div>" +
        '<div class="hp" title="잔액 / 시작 잔액 ' + fmt(m.start) + '"><div class="hpfill" style="width:' + width + "%;background:" + hpColor(frac) + '"></div><div class="hptick" style="left:' + startTick + '%"></div></div>' +
        '<div class="nums"><span class="bal">' + fmt(g.balance) + '</span><span class="unit">토큰</span>' +
        (g.delta ? '<span class="delta ' + (g.delta < 0 ? "neg" : "pos") + '">' + sgn(g.delta) + "</span>" : "") + "</div>" +
        '<div class="stats"><span title="푼 라운드 수">🏆 기록 ' + g.record + '</span><span title="이번 라운드에 생성한 토큰">⚙ 이번 라운드 생성 ' + fmt(g.gen) + "</span></div>" +
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

  // ---------------------------------------------------------------------------------------------------- render: chart
  function renderChart(m) {
    const box = $("#chart");
    const pts = m.series;
    if (!pts.length) { box.innerHTML = '<div class="empty">잔액 기록 없음</div>'; return; }
    const W = Math.max(320, box.clientWidth || 600), H = 260, L = 56, Rr = 92, T = 14, B = 26;
    let ymax = m.start || 1;
    for (const p of pts) for (const a of m.agents) ymax = Math.max(ymax, p.bal[a] || 0);
    ymax = niceMax(ymax);
    const n = pts.length;
    const x = (j) => L + (n === 1 ? 0 : (j / (n - 1)) * (W - L - Rr));
    const y = (v) => T + (1 - v / ymax) * (H - T - B);
    let svg = '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="에이전트별 잔액 추이">';
    for (let t = 0; t <= 4; t++) {
      const v = (ymax * t) / 4;
      svg += '<line class="grid" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + (v >= 1000 ? (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k" : v) + "</text>";
    }
    if (m.start) svg += '<line class="startline" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + y(m.start) + '" y2="' + y(m.start) + '"/><text class="ax" x="' + (L + 4) + '" y="' + (y(m.start) - 4) + '">시작 ' + fmt(m.start) + '</text>';
    svg += '<line class="zeroline" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
    let lastRound = -1;
    pts.forEach((p, j) => {
      if (p.round !== lastRound && p.round > 0) { svg += '<line class="rline" x1="' + x(j) + '" x2="' + x(j) + '" y1="' + T + '" y2="' + (H - B) + '"/><text class="ax" x="' + (x(j) + 3) + '" y="' + (H - 8) + '">R' + p.round + "</text>"; }
      lastRound = p.round;
    });
    const atJ = pts.reduce((acc, p, j) => (p.i <= S.at ? j : acc), 0);
    const ends = [];
    m.agents.forEach((a, k) => {
      const d = pts.map((p, j) => (j ? "L" : "M") + x(j).toFixed(1) + " " + y(p.bal[a] || 0).toFixed(1)).join(" ");
      svg += '<path class="ln" d="' + d + '" style="stroke:var(--a' + k + ')"/>';
      ends.push({ k, a, yy: y(pts[n - 1].bal[a] || 0), v: pts[n - 1].bal[a] });
      svg += marker(SHAPES[k], x(n - 1), y(pts[n - 1].bal[a] || 0), "var(--a" + k + ")");
    });
    ends.sort((p, q) => p.yy - q.yy);
    for (let j = 1; j < ends.length; j++) if (ends[j].yy - ends[j - 1].yy < 13) ends[j].yy = ends[j - 1].yy + 13;
    for (const e of ends) svg += '<text class="endlab" x="' + (W - Rr + 10) + '" y="' + (e.yy + 4) + '">' + esc(short(e.a)) + " " + (e.v >= 10000 ? (e.v / 1000).toFixed(1) + "k" : fmt(e.v)) + "</text>";
    svg += '<line id="xhair" class="xhair" x1="' + x(atJ) + '" x2="' + x(atJ) + '" y1="' + T + '" y2="' + (H - B) + '"/>';
    svg += '<rect class="hit" x="' + L + '" y="' + T + '" width="' + (W - L - Rr) + '" height="' + (H - T - B) + '"/></svg>';
    box.innerHTML = svg + '<div id="tip" class="tip" hidden></div>';
    const hit = $("rect.hit", box), tip = $("#tip", box), xh = $("#xhair", box);
    const pick = (ev) => { const r = hit.getBoundingClientRect(); const fx = (ev.clientX - r.left) / r.width; return Math.max(0, Math.min(n - 1, Math.round(fx * (n - 1)))); };
    hit.addEventListener("mousemove", (ev) => {
      const j = pick(ev), p = pts[j];
      xh.setAttribute("x1", x(j)); xh.setAttribute("x2", x(j));
      tip.hidden = false;
      tip.innerHTML = "<b>" + esc(p.label) + "</b>" + m.agents.map((a, k) => '<div><i class="sw ' + SHAPES[k] + '" style="--c:var(--a' + k + ')"></i>' + esc(a) + " <b>" + fmt(p.bal[a]) + "</b></div>").join("") + '<div class="dim">클릭: 이 시점으로 이동</div>';
      const br = box.getBoundingClientRect();
      const left = ev.clientX - br.left + 14;
      tip.style.left = Math.min(left, br.width - 200) + "px"; tip.style.top = (ev.clientY - br.top + 10) + "px";
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; xh.setAttribute("x1", x(atJ)); xh.setAttribute("x2", x(atJ)); });
    hit.addEventListener("click", (ev) => { seek(pts[pick(ev)].i); });
  }
  function niceMax(v) { const p = Math.pow(10, Math.floor(Math.log10(v))); for (const s of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (s * p >= v * 1.05) return s * p; return 10 * p; }
  function marker(shape, cx, cy, color) {
    const s = 5, st = 'fill="' + color + '" stroke="var(--surface)" stroke-width="2"';
    if (shape === "square") return '<rect x="' + (cx - s) + '" y="' + (cy - s) + '" width="' + 2 * s + '" height="' + 2 * s + '" ' + st + "/>";
    if (shape === "triangle") return '<path d="M' + cx + " " + (cy - s - 1) + "L" + (cx + s + 1) + " " + (cy + s) + "L" + (cx - s - 1) + " " + (cy + s) + 'Z" ' + st + "/>";
    if (shape === "diamond") return '<path d="M' + cx + " " + (cy - s - 1) + "L" + (cx + s + 1) + " " + cy + "L" + cx + " " + (cy + s + 1) + "L" + (cx - s - 1) + " " + cy + 'Z" ' + st + "/>";
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + s + '" ' + st + "/>";
  }

  // ---------------------------------------------------------------------------------------------------- render: conversation
  function renderConvo(m) {
    const pairs = [];
    for (let p = 0; p < m.agents.length; p++) for (let q = p + 1; q < m.agents.length; q++) pairs.push([m.agents[p], m.agents[q]]);
    const inPair = (x, y, pr) => pr === "all" || (pr.includes(x) && pr.includes(y));
    const keyOf = (pr) => (pr === "all" ? "all" : pr.join("|"));
    const count = (pr) => m.messages.filter((x) => inPair(x.src, x.dst, pr)).length;
    $("#pairs").innerHTML = ['<button data-pair="all" class="' + (S.pair === "all" ? "on" : "") + '">전체 <span class=n>' + m.messages.length + "</span></button>"]
      .concat(pairs.map((pr) => '<button data-pair="' + keyOf(pr) + '" class="' + (S.pair === keyOf(pr) ? "on" : "") + (count(pr) ? "" : " zero") + '">' + short(pr[0]) + "↔" + short(pr[1]) + " <span class=n>" + count(pr) + "</span></button>")).join("");
    const pr = S.pair === "all" ? "all" : S.pair.split("|");
    const items = m.messages.filter((x) => inPair(x.src, x.dst, pr)).map((x) => ({ r: x.round, t: x.turn, i: x.i, html: '<div class="msg"><div class="st">R' + x.round + "·T" + x.turn + "</div><div>" + chip(x.src, m) + ' <span class=dim>→</span> ' + chip(x.dst, m) + '<div class="tx">' + esc(x.text) + "</div></div></div>" }));
    for (const o of m.offers.values()) {
      if (!inPair(o.src, o.dst, pr)) continue;
      items.push({ r: o.round, t: o.turn, i: o.madeIdx != null ? o.madeIdx : 1e9, html: '<div class="msg offer"><div class="st">R' + o.round + "·T" + o.turn + "</div><div>🤝 <b>" + esc(o.id) + "</b> " + chip(o.src, m) + " → " + chip(o.dst, m) + '<div class="tx">' + esc(o.dst) + "→" + esc(o.src) + ": " + esc(legKo(o.you_give)) + " · " + esc(o.src) + "→" + esc(o.dst) + ": " + esc(legKo(o.i_give)) + ' <span class="xs x-' + esc(o.status) + '">' + esc(XSTAT_KO[o.status] || o.status) + (o.accepted_turn ? " (T" + o.accepted_turn + " 수락)" : "") + (o.rejected_turn ? " (T" + o.rejected_turn + " 거절)" : "") + "</span>" + (o.why ? ' <span class="warn">' + esc(o.why) + "</span>" : "") + "</div></div></div>" });
    }
    items.sort((p, q) => p.r - q.r || p.t - q.t || p.i - q.i);
    const el = $("#convo");
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
    el.innerHTML = items.map((x) => x.html).join("") || '<div class="empty">' + (S.pair === "all" ? "아직 오간 메시지가 없습니다." : "이 둘 사이에는 메시지가 없습니다.") + "</div>";
    if (S.follow || atEnd) el.scrollTop = el.scrollHeight;
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
      for (const x of ann.accepts) h += '<div class="ln ' + (x.why ? "warn" : "ok") + '">' + (x.why ? "❌" : "✅") + " ACCEPT " + esc(x.id) + (x.why ? " — 거절: " + esc(x.why) : "") + "</div>";
      for (const x of ann.withdraws) h += '<div class="ln ' + (x.why ? "warn" : "") + '">↩ WITHDRAW ' + esc(x.id) + (x.why ? " — 거절: " + esc(x.why) : "") + "</div>";
      for (const x of ann.rejects) h += '<div class="ln ' + (x.why ? "warn" : "rej") + '">🚫 REJECT ' + esc(x.id) + (x.why ? " — 엔진이 받지 않음: " + esc(x.why) : " — 제안을 거절함 (제안자는 다음 TALK 턴에 알게 됨)") + "</div>";
      if (e.free_tokens > 0) h += '<div class="ln ok">🎁 REJECT만 쓴 응답이라 ' + fmt(e.free_tokens) + " 토큰을 돌려받음 (잔액에 이미 반영)</div>";
      for (const t of p.blocked || []) h += '<div class="ln warn">🚫 전달 안 됨 → ' + chip(t.dst, m) + ' <span class="dim">행동 이름이 들어 있어 시스템이 막음 (보낸 쪽은 다음 TALK 턴에 알게 됨)</span><div class="tx">' + esc(t.text) + "</div></div>";
      for (const d of plainDropped(p)) h += '<div class="ln warn">⚠ 무시된 줄: <code>' + esc(d) + "</code></div>";
      if (e.format_error && p) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
      const tags = [];
      if (p.exit) tags.push('<span class="tag exit">🚪 EXIT' + ("exit_reason" in p ? (p.exit_reason ? " — " + esc(p.exit_reason) : ' <span class="dim">(이유 없음)</span>') : "") + "</span>");
      if (p.done) tags.push('<span class="tag">💤 DONE</span>');
      if (tags.length) h += '<div class="ln">' + tags.join(" ") + "</div>";
      if (!(p.to || []).length && !(p.offers || []).length && !(p.blocked || []).length && !ann.accepts.length && !ann.withdraws.length && !ann.rejects.length && !p.exit && !p.done && !(p.dropped || []).length) h += '<div class="ln dim">(실행할 줄 없음)</div>';
    }
    h += '<div class="lzs">' + lazy(i, "thinking", "🧠 생각") + lazy(i, "user", "📨 받은 프롬프트", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 원문") + "</div>";
    return h + "</div>";
  }

  function solveCard(m, i, r) {
    const e = S.events[i], p = e.parsed, a = e.agent;
    const row = r.end && r.end.agents ? r.end.agents[a] : null;
    const ok = Array.isArray(p) && JSON.stringify(p) === JSON.stringify(e.answers || []);
    const verdict = p === "PASS" && passCharged(m) ? '<span class="verdict bad" title="allow_pass: false — PASS 응답은 풀지 못한 응답으로 벌금">PASS → ✗ 오답 처리</span>' : p === "PASS" ? '<span class="verdict pass">PASS</span>' : !Array.isArray(p) ? '<span class="verdict bad">⛔ 무효</span>' : ok ? '<span class="verdict ok">✓ 정답</span>' : '<span class="verdict bad">✗ 오답</span>';
    let h = '<div class="card solve">' + usage(e) + '<div class="ln">' + verdict + "</div>";
    h += '<div class="ln"><span class="dim">답</span> <code>' + esc(Array.isArray(p) ? p.join(", ") : p == null ? "—" : p) + '</code> <span class="dim">정답</span> <code>' + esc((e.answers || []).join(", ")) + "</code></div>";
    const rec = row ? row.received || [] : [];
    const got = rec.length ? rec : r.exchanges.map((j) => S.events[j]).filter((x) => x.status === "done" && ((x.dst === a && x.i_give === "EXAMPLE") || (x.src === a && x.you_give === "EXAMPLE"))).map((x) => (x.dst === a ? x.src : x.dst));
    h += '<div class="ln"><span class="dim">교환으로 받은 예시</span> ' + (got.length ? got.map((b) => chip(b, m)).join(" ") : "없음") + "</div>";
    if (row) {
      if (row.candidates) h += '<div class="ln"><span class="dim">신호별 남은 후보 수</span> ' + row.candidates.map((c) => '<b class="' + (c > 1 ? "warnc" : "okc") + '">' + c + "</b>").join(" · ") + "</div>";
      if (row.needed != null) h += '<div class="ln"><span class="dim">이 에이전트 예시 필요?</span> ' + (row.needed ? "예" : "아니오") + (row.missing && row.missing.length ? ' · <span class="dim">빠진 필요 예시</span> ' + row.missing.map((b) => chip(b, m)).join(" ") : "") + "</div>";
    }
    h += '<div class="lzs">' + lazy(i, "thinking", "🧠 생각") + lazy(i, "user", "📨 받은 프롬프트", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 원문") + "</div>";
    return h + "</div>";
  }

  function settleCard(m, r, a) {
    const row = r.end.agents[a];
    if (!row) return '<div class="idle">이번 라운드 불참</div>';
    const n = (v, cls, sign) => (v ? '<span class="' + cls + '">' + sign + fmt(v) + "</span>" : '<span class="dim">0</span>');
    let h = '<div class="card settle"><div class="ln"><b>' + fmt(row.balance_before) + "</b> → <b>" + fmt(row.balance_after) + '</b> <span class="badge s-' + esc(row.status) + '">' + esc(STATUS_KO[row.status] || row.status) + "</span></div>";
    h += '<table class="kv"><tr><td>생성</td><td>' + n(row.generated, "neg", "−") + "</td><td>환급</td><td>" + n(row.returned, "pos", "+") + "</td></tr><tr><td>상금</td><td>" + n(row.paid, "pos", "+") + "</td><td>벌금</td><td>" + n(row.charged, "neg", "−") + "</td></tr><tr><td>유지비</td><td>" + n(row.upkeep, "neg", "−") + "</td><td>TALK 호출</td><td>" + (row.talk_calls || 0) + "</td></tr></table>";
    const sent = Object.entries(row.sent || {});
    h += '<div class="ln"><span class="dim">보낸 메시지</span> ' + (sent.length ? sent.map(([b, c]) => chip(b, m) + "×" + c).join(" ") : "없음") + " <span class=dim>· 제안</span> " + (row.offers_made || 0) + " <span class=dim>· 수락</span> " + (row.accepted || 0) + (row.rejected != null ? " <span class=dim>· 거절</span> " + row.rejected : "") + (row.free_tokens ? " <span class=dim>· REJECT 환급</span> <span class=pos>+" + fmt(row.free_tokens) + "</span>" : "") + "</div>";
    if (row.blocked) h += '<div class="ln warn">🚫 행동 이름 때문에 전달 안 된 메시지 ' + row.blocked + "개</div>";
    if (row.exit) h += '<div class="ln"><span class="tag exit">🚪 EXIT</span> ' + ("exit_reason" in row ? (row.exit_reason ? esc(row.exit_reason) : '<span class="dim">(이유 없음)</span>') : "") + "</div>";
    for (const x of row.refused || []) h += '<div class="ln warn">⚠ ' + esc(x) + "</div>";
    const mine = r.exchanges.map((j) => S.events[j]).filter((x) => x.src === a || x.dst === a);
    if (mine.length) h += '<div class="ln">' + mine.map((x) => '<span class="xs x-' + esc(x.status) + '" title="' + esc(x.why || "") + '">' + esc(x.id) + " ⇄ " + esc(short(x.src === a ? x.dst : x.src)) + " " + esc(XSTAT_KO[x.status] || x.status) + "</span>").join(" ") + "</div>";
    if (row.truncated) h += '<div class="ln warn">SOLVE 응답 잘림</div>';
    if (row.overdrawn) h += '<div class="ln warn">잔액 초과로 종료</div>';
    return h + "</div>";
  }

  function idle(m, r, a, phase, turn) {
    const g = m.ag[a];
    if (!r.taking.includes(a)) return '<div class="idle">' + (g && g.status === "dead" ? "✕ 이미 종료됨" : g && g.status === "exited" ? "🚪 이미 퇴장" : "불참") + "</div>";
    if (phase === "talk") {
      for (const t of r.turns.values()) if (t.k < turn && t.calls[a] != null) { const e = S.events[t.calls[a]]; if (e.balance_after <= 0) return '<div class="idle">✕ 종료됨</div>'; if (e.parsed && e.parsed.exit) return '<div class="idle">🚪 EXIT 함 — 이번 라운드 호출 없음</div>'; }
      return '<div class="idle">💤 호출 안 됨 (DONE 뒤 새 소식 없음)</div>';
    }
    return '<div class="idle">' + (g && g.status === "exited" ? "🚪 퇴장해 SOLVE 없음" : g && g.status === "dead" ? "✕ 종료돼 SOLVE 없음" : "SOLVE 호출 없음") + "</div>";
  }

  function renderGrid(m) {
    const ag = m.agents;
    let h = '<div class="gh"><div class="rh"></div>' + ag.map((a, k) => '<div class="colh" style="--c:var(--a' + k + ')">' + profileIcon(a, m, 28) + "<b>" + esc(a) + "</b></div>").join("") + "</div>";
    const rounds = [...m.rounds.values()].sort((p, q) => p.r - q.r);
    for (const r of rounds) {
      const st = r.startEv || {};
      h += '<div class="rband" id="r' + r.r + '"><b>라운드 ' + r.r + "</b> <span class=dim>· 과제 " + esc(r.profile) + " · 참여 " + r.taking.length + "명 · 유지비 후 잔액</span> " + ag.map((a) => '<span class="mini">' + esc(short(a)) + " " + fmt((st.balances || {})[a]) + "</span>").join(" ") + (Object.keys(st.gone || {}).length ? ' <span class="dim">· 빠짐 ' + Object.entries(st.gone).map(([a, v]) => short(a) + "(" + (v === "dead" ? "종료" : "퇴장") + ")").join(", ") + "</span>" : "") + "</div>";
      for (const t of [...r.turns.values()].sort((p, q) => p.k - q.k)) {
        h += '<div class="grow"><div class="rh"><b>TALK ' + t.k + "</b><span class=dim>/" + (m.settings.talk_turns || "?") + "</span></div>";
        for (const a of ag) {
          if (t.calls[a] != null) h += '<div class="cell">' + talkCard(m, t.calls[a]) + "</div>";
          else if (t.called.includes(a)) h += '<div class="cell"><div class="idle think">🧠 생각 중…</div></div>';
          else h += '<div class="cell">' + idle(m, r, a, "talk", t.k) + "</div>";
        }
        h += "</div>";
      }
      if (r.exchanges.length) {
        h += '<div class="grow xrow"><div class="rh"><b>교환</b></div><div class="cell span">' + r.exchanges.map((j) => {
          const x = S.events[j];
          return '<div class="xline"><span class="xs x-' + esc(x.status) + '">' + esc(XSTAT_KO[x.status] || x.status) + "</span> <b>" + esc(x.id) + "</b> " + chip(x.src, m) + " → " + chip(x.dst, m) + ' <span class="dim">T' + x.turn + (x.accepted_turn ? " 제안 · T" + x.accepted_turn + " 수락" : x.rejected_turn ? " 제안 · T" + x.rejected_turn + " 거절" : " 제안") + "</span> · " + esc(short(x.dst)) + "→" + esc(short(x.src)) + ": " + esc(legKo(x.you_give)) + " · " + esc(short(x.src)) + "→" + esc(short(x.dst)) + ": " + esc(legKo(x.i_give)) + (x.why ? ' <span class="warn">' + esc(x.why) + "</span>" : "") + (x.carried != null ? ' <span class="dim">· TALK ' + x.carried + "턴 끝에 바로 실행</span>" : "") + "</div>";
        }).join("") + "</div></div>";
      }
      if (r.solve) {
        h += '<div class="grow"><div class="rh"><b>SOLVE</b></div>';
        for (const a of ag) {
          if (r.solve.calls[a] != null) h += '<div class="cell">' + solveCard(m, r.solve.calls[a], r) + "</div>";
          else if (r.solve.called.includes(a)) h += '<div class="cell"><div class="idle think">🧩 푸는 중…</div></div>';
          else h += '<div class="cell">' + idle(m, r, a, "solve") + "</div>";
        }
        h += "</div>";
      }
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
  function clueRow(c, size) {
    return '<div class="clue">' + glyph(c.signal, size || 22) + '<span class="ctext">' + esc(c.signal.text) + '</span><span class="arrow">→</span>' + act(c.action) + "</div>";
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

  function renderPuzzle(m) {
    const box = $("#puzzle");
    if (!m.round) { box.innerHTML = '<div class="empty">라운드가 시작되면 그 라운드의 문제가 여기 나타납니다.</div>'; return; }
    const P = puzzleFor(m.round);
    if (P.loading) { box.innerHTML = '<div class="empty">라운드 ' + m.round + " 문제를 엔진으로 다시 만드는 중…</div>"; return; }
    if (P.error) { box.innerHTML = '<div class="banner bad">라운드 ' + m.round + " 문제를 만들 수 없음: " + esc(P.error) + "</div>"; return; }
    const r = m.rounds.get(m.round) || { taking: [] };
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

  // ---------------------------------------------------------------------------------------------------- render: offer graph
  /* One round's offers as a directed graph: node = agent (stage colour/order), arrow = offer from its maker to the agent
     it was made to. Built from m.offers, which holds the engine's exchange records once TALK is over and the page's own
     replay of the TALK calls before that, so the graph also fills in mid-round. Colour = what is offered, line style
     and opacity = status. */
  const KIND_KO = { swap: "예시 ⇄ 예시", tokex: "토큰 ⇄ 예시", tokens: "토큰만", example: "예시만", empty: "빈 제안" };
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
    if (a === "tok" || b === "tok") return "tokens";
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
  function avatarRects(k) {
    const col = { H: HAIR[k % 4], S: SKIN[k % 4], E: "#141414", M: "#b5524b", B: "var(--a" + (k % 4) + ")", W: "rgba(255,255,255,.55)", P: "#3b3f4a", K: "#191a1f" };
    let rects = "";
    FALLBACK.forEach((row, y) => [...row].forEach((ch, x) => { if (col[ch]) rects += '<rect x="' + x + '" y="' + y + '" width="1.02" height="1.02" fill="' + col[ch] + '"/>'; }));
    return rects;
  }

  function offerTip(o, m) {
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

    const offers = [...m.offers.values()].filter((o) => o.round === R && (T === "all" || o.turn === T))
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
      const text = it.msg ? "💬" + it.count : it.o.id + " · " + legG(it.o.i_give) + " ⇄ " + legG(it.o.you_give) + (OSTAT[it.o.status] ? " " + OSTAT[it.o.status][0] : " " + it.o.status);
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
    svg += "<defs>" + ["swap", "tokex", "tokens", "example", "empty", "bad", "msg"].map((k) => '<marker id="og-ah-' + k + '" class="ah k-' + k + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z"/></marker>').join("") + "</defs>";
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
        : '<svg x="' + (p.x - 17) + '" y="' + (p.y - 18) + '" width="34" height="34" viewBox="0 0 12 12" shape-rendering="crispEdges">' + avatarRects(k) + "</svg>";
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
    if (!shown.length && !edges.length) svg += '<text class="og-empty" x="' + cx + '" y="' + cy + '" text-anchor="middle">' + (offers.length ? "철회·만료된 제안만 있음 (숨김)" : T === "all" ? "이 라운드에는 아직 제안이 없습니다" : T + "턴에 낸 제안이 없습니다") + "</text>";
    svg += "</svg>";

    // ---- side: counts, legend, the round's offers as a list
    const cnt = {};
    for (const o of offers) cnt[o.status] = (cnt[o.status] || 0) + 1;
    const sum = ["done", "rejected", "void", "withdrawn", "lapsed", "accepted", "open"].filter((s) => cnt[s]).map((s) => '<span class="xs x-' + s + '">' + esc(XSTAT_KO[s]) + " " + cnt[s] + "</span>").join(" ");
    const legend = '<div class="oglegend"><div class="ogl-h">종류 <span class="dim">(색)</span></div>' +
      ["swap", "tokex", "tokens", "example"].map((k) => '<span class="ogl k-' + k + '"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>' + esc(KIND_KO[k]) + "</span>").join("") +
      '<div class="ogl-h">상태 <span class="dim">(선 모양)</span></div>' +
      ["done", "open", "rejected", "void", "withdrawn", "lapsed"].map((s) => '<span class="ogl st-' + s + ' k-swap"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>' + esc(OSTAT[s][1]) + "</span>").join("") +
      (G.msgs ? '<span class="ogl og-msgl"><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5"/></svg>💬 메시지 수 (TO 줄)</span>' : "") +
      '<div class="ogl-note">화살표 = 제안자 → 받는 쪽. 라벨 = <b>번호 · 제안자가 주는 것 ⇄ 받는 쪽이 주는 것</b>. 선이나 라벨을 누르면 자세히.</div></div>';
    const list = offers.map((o) => '<div class="ogrow' + (G.pin === o.id ? " on" : "") + '" data-oid="' + esc(o.id) + '"><span class="xs x-' + esc(o.status) + '">' + esc(XSTAT_KO[o.status] || o.status) + "</span> <b>" + esc(o.id) + "</b> " + chip(o.src, m) + " → " + chip(o.dst, m) +
      '<div class="tx">' + esc(short(o.src)) + "→" + esc(short(o.dst)) + ": " + esc(legKo(o.i_give)) + " · " + esc(short(o.dst)) + "→" + esc(short(o.src)) + ": " + esc(legKo(o.you_give)) +
      ' <span class="dim">T' + o.turn + (o.accepted_turn ? " · T" + o.accepted_turn + " 수락" : "") + (o.rejected_turn ? " · T" + o.rejected_turn + " 거절" : "") + "</span>" + (o.why ? ' <span class="warn">' + esc(o.why) + "</span>" : "") + "</div></div>").join("");
    box.innerHTML = '<div class="ogfig">' + svg + '<div id="ogtip" class="tip" hidden></div></div><div class="ogside"><div class="ogsum"><b>R' + R + (T === "all" ? "" : " · " + T + "턴") + "</b> 제안 " + offers.length + (sum ? " · " + sum : "") +
      (msgs.length ? ' <span class="dim">· 메시지 ' + msgs.length + "</span>" : "") + "</div>" + legend + '<div class="oglist">' + (list || '<div class="dim">제안 없음</div>') + "</div></div>";
    if (G.pin && m.offers.get(G.pin) && m.offers.get(G.pin).round === R) showOgTip(G.pin, null);
  }

  function showOgTip(oid, ev) {
    const m = S.model, o = m && m.offers.get(oid), fig = $("#ograph .ogfig"), tip = $("#ogtip");
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
    renderHeader(m); renderStage(m); renderPuzzle(m); renderTimeline(m); renderChart(m); renderConvo(m); renderGraph(m); renderGrid(m);
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

  function resetSession() { S.events = []; S.offset = 0; S.result = null; S.at = -1; S.follow = true; S.open.clear(); S.pair = "all"; S.og = { round: null, turn: "all", faint: true, msgs: false, pin: null }; S.rendered = ""; }

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
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => S.model && renderChart(S.model), 120); });
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
    S.run = q.get("run") || ""; S.session = q.get("session") || "";
    const at = Number(q.get("at"));
    wire();
    if (q.get("sprites") !== "0") await loadAssets(); // ?sprites=0 shows the generated avatars
    await loadRuns();
    await loadSessions();
    render(true);
    await poll();
    if (at > 0) { S.follow = false; S.at = at - 1; render(true); }
    setInterval(poll, POLL_MS);
    setInterval(async () => { await loadSessions(); render(); }, SESSIONS_MS);
    setInterval(loadRuns, RUNS_MS);
  }

  window.__monitor = { build, S, offerKind, modelShort };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
