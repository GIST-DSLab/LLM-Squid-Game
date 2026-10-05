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
  const XSTAT_KO = { done: "체결", void: "무효", lapsed: "만료", withdrawn: "철회", open: "열림", accepted: "수락됨" };

  // ---------------------------------------------------------------------------------------------------- app state
  const S = {
    embed: null, run: "", session: "", events: [], offset: 0, result: null, info: null,
    at: -1, follow: true, pair: "all", runs: [], sessions: [], assets: null, open: new Set(),
    live: false, mtime: 0, now: 0, rendered: "", polling: false, err: "",
    puzzles: new Map(), showTruth: false,
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
    return { id: a, balance: start, record: 0, status: "in", pending: null, bubble: null, delta: 0, gen: 0, model: null, exitFlag: false, face: 0, lastRoundGen: 0 };
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
          if (e.parsed && e.parsed.exit && e.balance_after > 0) g.exitFlag = true;
          m.phase = "TALK " + e.turn + "턴"; m.phaseKey = "talk";
          point(i, "R" + e.round + " T" + e.turn + " · " + a, e.round);
          const called = t.called.length ? t.called : Object.keys(t.calls);
          if (called.every((b) => t.calls[b] != null)) m.timeline.push({ i, label: "R" + e.round + " T" + e.turn, round: e.round, kind: "turn", state: snap() });
        } else {
          if (!r.solve) r.solve = { startIdx: i, called: [], calls: {} };
          r.solve.calls[a] = i;
          g.bubble = solveBubble(e);
          m.phase = "SOLVE"; m.phaseKey = "solve";
          point(i, "R" + e.round + " SOLVE · " + a, e.round);
        }
      } else if (kind === "exchange") {
        const r = R(e.round);
        if (!r.exchanges.length) for (const a of m.agents) if (m.ag[a].status === "in" && !m.ag[a].exitFlag) m.ag[a].bubble = null;
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
            lines.push(["🤝", e.id + " 체결 ⇄ " + b]);
            g.bubble = { lines, kind: "xchg" };
          }
        }
        m.phase = "EXCHANGES"; m.phaseKey = "xchg";
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

  /* Re-play one TALK reply on the offer book (mirrors Session._apply and Channel.accept/withdraw) so the card can say
     which offer id each OFFER line got and whether each ACCEPT/WITHDRAW went through. */
  function applyTalk(m, r, e, i) {
    const p = e.parsed, a = e.agent;
    const ann = { offerIds: [], accepts: [], withdraws: [], applied: false };
    if (!p || typeof p !== "object" || !(e.balance_after > 0)) return ann;
    ann.applied = true;
    for (const msg of p.to || []) m.messages.push({ round: e.round, turn: e.turn, src: a, dst: msg.dst, text: msg.text, i });
    for (const o of p.offers || []) {
      r.seq += 1;
      const id = e.round + "." + r.seq;
      ann.offerIds.push(id);
      m.offers.set(id, { id, round: e.round, src: a, dst: o.dst, you_give: o.you_give, i_give: o.i_give, turn: e.turn, status: "open", accepted_turn: null, why: "", predicted: true, madeIdx: i });
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
    if ((p.dropped || []).length) lines.push(["⚠", "무시된 줄 " + p.dropped.length + "개"]);
    if (e.format_error) lines.push(["⚠", "형식 오류: " + clip(e.format_error, 40)]);
    if (p.exit) lines.push(["🚪", "EXIT"]);
    else if (p.done) lines.push(["💤", "DONE"]);
    if (!lines.length) lines.push(["…", "(빈 응답)"]);
    return { lines, kind: e.format_error || (p.dropped || []).length ? "warn" : "talk" };
  }

  function solveBubble(e) {
    if (e.balance_after != null && e.balance_after <= 0) return { lines: [["✕", "SOLVE 중 토큰 소진"]], kind: "dead" };
    const p = e.parsed;
    if (p === "PASS") return { lines: [["🧩", "SOLVE · PASS"]], kind: "pass" };
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
      const statusBadge = '<span class="badge s-' + g.status + '">' + (g.status === "in" ? (g.exitFlag ? "퇴장 예정 🚪" : "참여 중") : STATUS_KO[g.status] || g.status) + "</span>";
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
      items.push({ r: o.round, t: o.turn, i: o.madeIdx != null ? o.madeIdx : 1e9, html: '<div class="msg offer"><div class="st">R' + o.round + "·T" + o.turn + "</div><div>🤝 <b>" + esc(o.id) + "</b> " + chip(o.src, m) + " → " + chip(o.dst, m) + '<div class="tx">' + esc(o.dst) + "→" + esc(o.src) + ": " + esc(legKo(o.you_give)) + " · " + esc(o.src) + "→" + esc(o.dst) + ": " + esc(legKo(o.i_give)) + ' <span class="xs x-' + esc(o.status) + '">' + esc(XSTAT_KO[o.status] || o.status) + (o.accepted_turn ? " (T" + o.accepted_turn + " 수락)" : "") + "</span>" + (o.why ? ' <span class="warn">' + esc(o.why) + "</span>" : "") + "</div></div></div>" });
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
    const e = S.events[i], p = e.parsed, ann = m.ann[i] || { offerIds: [], accepts: [], withdraws: [] };
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
      for (const d of p.dropped || []) h += '<div class="ln warn">⚠ 무시된 줄: <code>' + esc(d) + "</code></div>";
      if (e.format_error && p) h += '<div class="ln warn">⚠ 형식 오류: ' + esc(e.format_error) + "</div>";
      const tags = [];
      if (p.exit) tags.push('<span class="tag exit">🚪 EXIT</span>');
      if (p.done) tags.push('<span class="tag">💤 DONE</span>');
      if (tags.length) h += '<div class="ln">' + tags.join(" ") + "</div>";
      if (!(p.to || []).length && !(p.offers || []).length && !ann.accepts.length && !ann.withdraws.length && !p.exit && !p.done && !(p.dropped || []).length) h += '<div class="ln dim">(실행할 줄 없음)</div>';
    }
    h += '<div class="lzs">' + lazy(i, "thinking", "🧠 생각") + lazy(i, "user", "📨 받은 프롬프트", e.user ? fmt(e.user.length) + "자" : "") + lazy(i, "text", "📝 원문") + "</div>";
    return h + "</div>";
  }

  function solveCard(m, i, r) {
    const e = S.events[i], p = e.parsed, a = e.agent;
    const row = r.end && r.end.agents ? r.end.agents[a] : null;
    const ok = Array.isArray(p) && JSON.stringify(p) === JSON.stringify(e.answers || []);
    const verdict = p === "PASS" ? '<span class="verdict pass">PASS</span>' : !Array.isArray(p) ? '<span class="verdict bad">⛔ 무효</span>' : ok ? '<span class="verdict ok">✓ 정답</span>' : '<span class="verdict bad">✗ 오답</span>';
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
    h += '<div class="ln"><span class="dim">보낸 메시지</span> ' + (sent.length ? sent.map(([b, c]) => chip(b, m) + "×" + c).join(" ") : "없음") + " <span class=dim>· 제안</span> " + (row.offers_made || 0) + " <span class=dim>· 수락</span> " + (row.accepted || 0) + "</div>";
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
          return '<div class="xline"><span class="xs x-' + esc(x.status) + '">' + esc(XSTAT_KO[x.status] || x.status) + "</span> <b>" + esc(x.id) + "</b> " + chip(x.src, m) + " → " + chip(x.dst, m) + ' <span class="dim">T' + x.turn + (x.accepted_turn ? " 제안 · T" + x.accepted_turn + " 수락" : " 제안") + "</span> · " + esc(short(x.dst)) + "→" + esc(short(x.src)) + ": " + esc(legKo(x.you_give)) + " · " + esc(short(x.src)) + "→" + esc(short(x.dst)) + ": " + esc(legKo(x.i_give)) + (x.why ? ' <span class="warn">' + esc(x.why) + "</span>" : "") + "</div>";
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
    h += '<div class="plegend">각 열은 <b>공개 예시 + 그 에이전트 자신의 예시</b>만으로 남는 답입니다. 교환으로 받은 예시는 넣지 않았습니다(그건 아래 SOLVE 카드). 칩 = 아직 가능한 행동(<b>←</b> go_left · <b>→</b> go_right · <b>•</b> stay · <b>↑</b> jump) · 4개 = 모름 · 1개 = 결정됨. ' +
      '<span class="psum">이번 라운드: 공개+자기 예시로 결정 <b>' + pinned + "</b> / " + cells + " · 자기 예시가 후보를 줄임 <b>" + narrowed + "</b> / " + cells + "</span></div>";
    h += '<div class="pcols">';
    order.forEach((a, k) => {
      const g = (P.agents || {})[a];
      if (!g) return;
      const gone = r.taking.length && !r.taking.includes(a);
      const model = m.ag[a] && m.ag[a].model;
      h += '<div class="pcol' + (gone ? " gone" : "") + '" style="--c:var(--a' + (k % 4) + ')"><div class="pch"><i class="sw ' + SHAPES[k % 4] + '"></i><b>' + esc(a) + "</b>" + (model ? '<span class="model">' + esc(model) + "</span>" : "") +
        (g.needed ? '<span class="need" title="이 예시가 없으면 어떤 신호는 답이 둘 이상 남음 (엔진의 needed)">★ 필수 단서</span>' : '<span class="need no" title="이 예시 없이도 신호마다 답이 하나로 정해짐">필수 아님</span>') + "</div>";
      if (gone) h += '<div class="idle">이번 라운드 불참 (예시는 배정됨)</div>';
      h += '<div class="mine"><span class="lbl">내 단서</span>' + clueRow(g.secret, 24) + "</div>";
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

  // ---------------------------------------------------------------------------------------------------- render: all
  function render(force) {
    const n = S.events.length;
    if (S.follow || S.at > n - 1) S.at = n - 1;
    const key = n + "|" + S.at + "|" + S.pair + "|" + (S.result ? 1 : 0) + "|" + S.live + "|" + S.err + "|" + document.documentElement.dataset.theme + "|" + Math.round((S.now || 0) / 30);
    if (!force && key === S.rendered) return;
    S.rendered = key;
    const m = build(S.events, S.at);
    S.model = m;
    renderHeader(m); renderStage(m); renderPuzzle(m); renderTimeline(m); renderChart(m); renderConvo(m); renderGrid(m);
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

  function resetSession() { S.events = []; S.offset = 0; S.result = null; S.at = -1; S.follow = true; S.open.clear(); S.pair = "all"; S.rendered = ""; }

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

  window.__monitor = { build, S };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
