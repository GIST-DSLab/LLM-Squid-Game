// The signal task alone (signal.html): pick a round of the experiment schedule and answer it. v14 (the default): the
// public examples shown when N agents take part (4 x N, nested: switch N to see the prefix), the round's ambiguity k,
// and after answering which actions those examples leave, for N = 1..4. v13 / v12 (the mode switch): sit at one seat,
// open other seats' examples as accepted exchanges. Every puzzle and example comes from the engine through
// /api/signal/* (server/signal.py); nothing here decides what is right. Card boxes, the rule memo and the answer buttons
// are signal_ui.js's, the same as the arena's SOLVE screen.
(function () {
  "use strict";
  const API = (window.WEB5_API || "") + "/api";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let META = null, cur = null, got = {}, choice = [], memo = null, done = null;

  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(API + path, opt);
    let data = null;
    try { data = await r.json(); } catch { /* empty */ }
    if (!r.ok) throw new Error((data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail))) || r.statusText);
    return data;
  }
  function flash(msg) {
    const f = $("flash");
    f.textContent = msg; f.className = msg ? "flash" : "flash hidden";
  }
  const kText = (k, split) => (split ? `갈림 ${Math.round(100 * split)}/${Math.round(100 * (1 - split))} · 답 ${k}개` : k ? `k=${k} · 시스템이 고름` : "k=0 · 무작위");
  const pc = (x) => `${Math.round(100 * x)}%`;
  const specText = (sp) => `${sp.clauses}줄` + (sp.conjunctions ? ` · and ${sp.conjunctions}줄` : "") +
    (sp.trap_query ? " · 함정" : "") + (sp.ambiguity != null ? ` · ${kText(sp.ambiguity, sp.split)}` : "") +
    (sp.size_band ? ` · 규칙 ${sp.size_band[0]}–${sp.size_band[1]}개` : "") + (sp.min_per_action ? ` · 행동마다 예시 ≥${sp.min_per_action}` : "") +
    (sp.pool ? ` · 총 힌트 ${sp.pool}장` : sp.extra_clues ? ` · 추가 예시 ${sp.extra_clues}장` : "") +
    (sp.hand ? ` · 자리당 ${sp.hand}장` : "") + (sp.open_rate ? ` · 열림 ${sp.open_rate}` : "");
  const actEn = SIG.actEn;
  const mode = () => $("f-mode").value;
  const isPublic = () => mode() === "public";

  // --- setup ------------------------------------------------------------------------------------------------------
  function fillMode() {
    const m = mode(), sched = META.schedules[m];
    const own = Object.keys(META.profiles).filter((p) => (m === "public") === (META.profiles[p].ambiguity != null));
    const r = Math.min(Number($("f-round").value) || 1, sched.length);
    $("f-round").innerHTML = sched.map((p, i) => `<option value="${i + 1}"${i + 1 === r ? " selected" : ""}>R${i + 1} · ${esc(p)} (${esc(specText(META.profiles[p]))})</option>`).join("");
    $("f-profile").innerHTML = `<option value="">라운드 일정대로</option>` +
      own.map((p) => `<option value="${esc(p)}">${esc(p)} — ${esc(specText(META.profiles[p]))}</option>`).join("");
    document.querySelectorAll(".m-public").forEach((el) => el.classList.toggle("hidden", m !== "public"));
    document.querySelectorAll(".m-held").forEach((el) => el.classList.toggle("hidden", m === "public"));
    $("task-text").textContent = m === "public" ? META.task_chosen : META.task_v13;
    $("setup-note").textContent = `설정 파일: configs/squid5/${m === "public" ? META.config : META.config_v13}`;
  }

  function setup() {
    const f = $("form-setup");
    $("f-agents").innerHTML = [...Array(META.max_agents - 1).keys()].map((i) => i + 2)
      .map((n) => `<option value="${n}"${n === META.agents.length ? " selected" : ""}>${n}명${n === META.agents.length ? " (실험)" : ""}</option>`).join("");
    $("f-pool").innerHTML = `<option value="" selected>라운드 일정대로</option>` +
      [12, 16, 20, 26, 32, 39, 45, 52].filter((n) => n <= META.pool_max).map((n) => `<option value="${n}">${n}장</option>`).join("");
    const seats = () => {
      const n = Number($("f-agents").value);
      const names = n === META.agents.length ? META.agents : [...Array(n).keys()].map((i) => `agent-${i + 1}`);
      $("f-seat").innerHTML = names.map((a) => `<option>${esc(a)}</option>`).join("");
    };
    $("f-agents").addEventListener("change", seats);
    $("f-mode").addEventListener("change", () => { fillMode(); open(); });
    seats();
    fillMode();
    $("btn-random").addEventListener("click", () => { $("f-seed").value = Math.floor(Math.random() * 1e6); open(); });
    f.addEventListener("submit", (ev) => { ev.preventDefault(); open(); });
  }

  function params() {
    const base = { seed: Number($("f-seed").value || 0), round: Number($("f-round").value), profile: $("f-profile").value || null, mode: mode() };
    if (isPublic()) {
      return { ...base, agents: Number($("f-n").value), per_agent: Number($("f-e").value),
        ambiguity: $("f-k").value === "" ? null : Number($("f-k").value) };
    }
    return { ...base, deal: mode(), hand: $("f-hand").value === "" ? null : Number($("f-hand").value), seat: $("f-seat").value,
      agents: Number($("f-agents").value), pool: $("f-pool").value === "" ? null : Number($("f-pool").value) };
  }

  async function open() {
    flash("");
    $("board").classList.remove("hidden");
    $("board").innerHTML = `<p class="muted">문제를 만드는 중… (함정 라운드와 시스템이 고르는 예시는 처음 한 번 몇 초 걸립니다)</p>`;
    try {
      const req = params();
      cur = await api("POST", "/signal/view", req);
      cur.req = req;
    } catch (e) { $("board").classList.add("hidden"); return flash(`문제를 열지 못했습니다: ${e.message}`); }
    got = {}; choice = cur.queries.map(() => null); done = null; memo = null;
    render();
  }

  // --- cards ----------------------------------------------------------------------------------------------------------
  /** Every example the person can see in full, with where it sits: [{...example, key}] */
  function known() {
    const out = [];
    cur.public.forEach((t, i) => out.push({ ...SIG.parseExample(t), key: `pub:${i}` }));
    cur.mine.forEach((t, i) => out.push({ ...SIG.parseExample(t), key: `${cur.seat}:${i}` }));
    Object.entries(got).forEach(([a, ts]) => ts.forEach((t, i) => out.push({ ...SIG.parseExample(t), key: `${a}:${i}` })));
    return out;
  }
  function publicBoxHTML() {
    const c = cur;
    // the examples in shown order, each marked with the agent slot it belongs to (the nesting: slot j = examples j*e..)
    const items = c.public.map((t, i) => ({ e: SIG.parseExample(t), key: `pub:${i}` }));
    const switcher = `<div class="seg sg-n" role="group" aria-label="참여 인원">${[1, 2, 3, 4].map((n) =>
      `<button type="button" data-n="${n}" class="${n === c.n ? "on" : ""}"${done ? " disabled" : ""}>${n}명 · ${n * c.per_agent}장</button>`).join("")}</div>`;
    return `<div class="sg-seat pub"><div class="sg-seat-h"><b>공개 예시</b> <span class="muted small">${c.public.length}장 · 모두 봄 · 참여 ${c.n}명 × ${c.per_agent}장 · ${kText(c.ambiguity, c.ambiguity === c.spec.ambiguity && c.spec.split)}${c.attempt ? ` · 규칙 다시 뽑음 ${c.attempt}번` : ""}</span></div>
      ${switcher}${SIG.byActionHTML(items)}</div>`;
  }
  function seatsHTML() {
    if (cur.mode === "public") return publicBoxHTML();
    const boxes = [];
    if (cur.public.length) {
      boxes.push(`<div class="sg-seat pub"><div class="sg-seat-h"><b>공개</b> <span class="muted small">${cur.public.length}장 · 넷 모두 봄</span></div>
        ${SIG.byActionHTML(cur.public.map((t, i) => ({ e: SIG.parseExample(t), key: `pub:${i}` })))}</div>`);
    }
    boxes.push(`<div class="sg-seat mine"><div class="sg-seat-h"><b>나</b> <span class="mono small">${esc(cur.seat)}</span> <span class="muted small">${cur.mine.length}장</span></div>
      ${SIG.byActionHTML(cur.mine.map((t, i) => ({ e: SIG.parseExample(t), key: `${cur.seat}:${i}` })))}</div>`);
    Object.entries(cur.others).forEach(([a, fronts]) => {
      const open = got[a];
      const cards = open ? SIG.byActionHTML(open.map((t, i) => ({ e: SIG.parseExample(t), key: `${a}:${i}` })))
        : `<div class="sg-hand">${fronts.map((t) => SIG.backHTML(SIG.parseSignal(t))).join("")}</div>`;
      boxes.push(`<div class="sg-seat${open ? " open" : ""}"><div class="sg-seat-h"><b class="mono">${esc(a)}</b> <span class="muted small">${fronts.length}장</span></div>
        ${cards}
        <button type="button" class="ghost sg-take" data-who="${esc(a)}"${done ? " disabled" : ""}>${open ? "되돌리기" : "교환으로 받기"}</button></div>`);
    });
    return boxes.join("");
  }

  // --- answer + result --------------------------------------------------------------------------------------------------
  function renderAnswer() {
    $("answer").innerHTML = cur.queries.map((x, i) => SIG.answerRowHTML(i, META.actions, choice[i], done)).join("");
    $("btn-submit").disabled = !!done || choice.some((x) => !x);
  }

  function headHTML() {
    const c = cur;
    if (c.mode === "public") {
      return `<h2>R${c.round} · <span class="mono">${esc(c.profile)}</span> <span class="muted small">(${esc(specText(c.spec))}) · seed ${c.seed} · v14 공개 예시 · 참여 ${c.n}명</span></h2>
        <p class="small muted">이 라운드에 보이는 예시는 ${c.public.length}장입니다(참여 ${c.n}명 × ${c.per_agent}장). 한 명이 빠지면 맨 뒤 ${c.per_agent}장이 빠집니다.
          예시가 새 신호의 행동을 정할 수도 있고 정하지 못할 수도 있습니다. 아래 단추로 참여 인원을 바꾸면 같은 순서의 앞부분만 보입니다.</p>`;
    }
    const held = Object.values(c.others).reduce((n, v) => n + v.length, 0) + c.mine.length;
    return `<h2>R${c.round} · <span class="mono">${esc(c.profile)}</span> <span class="muted small">(${esc(specText(c.spec))}) · seed ${c.seed} · ${c.deal === "held" ? `모두 비밀${c.hand ? ` · 자리당 ${c.hand}장` : ""}` : "공개 + 비밀"} · ${c.agents.length}명 · 나는 ${esc(c.seat)}</span></h2>
      <p class="small muted">이 라운드의 예시는 모두 ${c.n_examples}장${c.public.length ? ` (공개 ${c.public.length}장 + 네 자리 ${held}장)` : c.hand ? ` (만든 예시 ${c.pool}장 중 ${c.n_examples}장이 ${c.agents.length}자리에 나감: 자리마다 ${c.hand}장, 최소 예시는 모두 나가고, 자리 칸이 예시보다 많을 때만 같은 카드가 여러 자리에 고르게 겹침)` : ` (네 자리가 나눠 가짐)`}.
        ${c.open ? "<b>열린 라운드</b>: 아무도 받지 않은 예시가 있어, 넷의 카드를 다 모아도 답이 둘 남습니다." : ""}</p>`;
  }

  function render() {
    const b = $("board"), c = cur;
    const sigs = c.queries.map((x) => SIG.parseSignal(x));
    b.innerHTML = `${headHTML()}
      ${c.queries.map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`) : `<div>새 신호: <b>${esc(x)}</b></div>`).join("")}
      <h4>규칙의 모양</h4><div class="shape mono">${esc(c.shape)}</div>
      ${c.distinct_actions ? `<p class="sg-rule-note">숨은 규칙의 action은 <b>서로 다른 action이 하나씩</b> 들어갑니다: if · elif · else가 모두 다른 action이고, 같은 action은 두 번 나오지 않습니다.</p>` : ""}
      <h4>${c.mode === "public" ? "예시" : `카드 <span class="muted small">(남의 카드는 앞면 = 신호만. 받으면 행동이 보입니다)</span>`}</h4>
      <div class="sg-seats">${seatsHTML()}</div>
      <div class="memo" id="memo"></div>
      <div id="answer"></div>
      <div class="sg-submit"><button type="button" class="primary big" id="btn-submit">답 제출</button>
        ${done ? `<button type="button" class="ghost big" id="btn-again">같은 문제 다시</button><button type="button" class="ghost big" id="btn-next">다음 라운드 →</button>` : ""}</div>
      <div id="result">${done ? resultHTML() : ""}</div>`;
    b.querySelectorAll(".sg-take").forEach((x) => x.addEventListener("click", () => take(x.dataset.who)));
    b.querySelectorAll(".sg-n button[data-n]").forEach((x) => x.addEventListener("click", () => { $("f-n").value = x.dataset.n; open(); }));
    $("answer").addEventListener("click", (ev) => {
      const t = ev.target.closest("button[data-val]");
      if (!t || done) return;
      choice[Number(t.closest(".sg-answer").dataset.q)] = t.dataset.val; renderAnswer();
    });
    $("btn-submit").addEventListener("click", submit);
    if (done) {
      $("btn-again").addEventListener("click", () => { got = {}; choice = cur.queries.map(() => null); done = null; render(); });
      $("btn-next").addEventListener("click", () => {
        const r = $("f-round"); if (r.selectedIndex < r.options.length - 1) r.selectedIndex += 1; open();
      });
    }
    memo = SIG.mountMemo($("memo"), { shape: c.shape, examples: known, queries: sigs, actions: META.actions, keep: memo && memo.guess,
      scope: b, disabled: () => !!done, distinct: !!c.distinct_actions, truth: () => done && done.truth, onUse: (i, a) => { if (!done) { choice[i] = a; renderAnswer(); } } });
    renderAnswer();
  }

  async function take(who) {
    if (done) return;
    if (got[who]) { delete got[who]; return render(); }
    try {
      const r = await api("POST", "/signal/reveal", { ...cur.req, seed: cur.seed, round: cur.round, profile: cur.profile, who });
      got[who] = r.examples; render();
    } catch (e) { flash(`받지 못했습니다: ${e.message}`); }
  }

  async function submit() {
    if (choice.some((x) => !x)) return;
    try {
      done = await api("POST", "/signal/solve", { ...cur.req, seed: cur.seed, round: cur.round, profile: cur.profile,
        seat: cur.seat, seen: Object.keys(got), actions: choice });
      render();
      $("result").scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (e) { flash(`제출하지 못했습니다: ${e.message}`); }
  }

  const leftHTML = (left) => left.map((x) => `<b>${x.length}개</b> (${x.map(actEn).join(" ")})`).join(" · ");
  function resultHTML() {
    const d = done;
    const guessP = d.left_seen.reduce((p, x) => p / x.length, 1);
    const head = `<h3>${d.solved ? "정답" : "오답"}</h3>
      <p>정답: ${d.answers.map(actEn).join(" · ")} · 내 답: ${d.actions.map(actEn).join(" · ")}</p>`;
    if (d.mode === "public") {
      const shares = (q) => q.shares.map((x) => `${actEn(x.action)} ${pc(x.share)}`).join(" · ");
      const rows = d.by_n.map((x) => { const q = x.split[0]; return `<tr class="${x.n === d.n ? "you" : ""}"><td>${x.n}명${x.n === d.n ? " (지금)" : ""}</td><td class="num">${x.examples}장</td>` +
        `<td class="num">${q.pool.toLocaleString("en-US")}</td><td>${shares(q)}</td><td>${q.map ? `${actEn(q.map)} ${q.map_right ? "✓" : "✗"}` : "동률"}</td></tr>`; }).join("");
      const T = d.target, q0 = d.split[0];
      const split = T && T.split ? `<p>이 라운드의 갈림 목표 p = <b>${pc(T.split)} / ${pc(1 - T.split)}</b> · 정답은 <b>${T.truth_major ? "다수" : "소수"} 쪽</b>(확률 ${pc(T.truth_major ? T.split : 1 - T.split)}로 뽑힘) ·
          실현된 정답 몫 <b>${pc(T.truth_share)}</b> · 맞는 규칙 <b>${T.pool}</b>개(참여 ${d.n}명) · <b>${T.pool_full}</b>개(4명)</p>` : "";
      return `<div class="sg-result ${d.solved ? "ok" : "bad"}">${head}
        <p>보인 예시(${cur.public.length}장)로 가능했던 답: ${leftHTML(d.left_seen)}
          ${d.determined ? " → 예시가 답을 하나로 정함" : ` → 예시로는 정해지지 않음 (찍기라면 맞힐 확률 ${(guessP * 100).toFixed(0)}%)`}</p>
        ${split}<p>예시와 맞는 규칙 ${q0.pool.toLocaleString("en-US")}개가 가리키는 행동: <b>${shares(q0)}</b>${q0.map ? ` → 가장 많은 쪽(MAP) ${actEn(q0.map)} ${q0.map_right ? "= 정답" : "≠ 정답"}` : " → 동률"}</p>
        <div class="tbl"><table><thead><tr><th>참여</th><th class="num">예시</th><th class="num">맞는 규칙</th><th>행동별 규칙 몫 (첫 새 신호)</th><th>MAP · 정답?</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="small muted">MAP = 맞는 규칙이 가장 많이 가리키는 행동(엔진의 가설 공간 기준). ${d.target && d.target.split ? "실험 라운드는 넷이 모두 참여할 때 답이 2개 남고 규칙이 p : 1−p로 갈리도록 시스템이 예시를 고릅니다." : `예시 고르기: ${kText(d.ambiguity)}.`} 규칙 메모의 줄마다 숨은 규칙과 비교한 결과(✓ / ✗와 정답 줄)를 표시했습니다.</p></div>`;
    }
    const all = d.left_all.map((x) => x.length);
    return `<div class="sg-result ${d.solved ? "ok" : "bad"}">${head}
      <p>내가 본 카드(${d.seen.length}자리${cur.public.length ? ` + 공개 ${cur.public.length}장` : ""})로 가능했던 답:
        ${leftHTML(d.left_seen)}
        ${guessP < 1 ? ` → 찍기라면 맞힐 확률 ${(guessP * 100).toFixed(0)}%` : " → 추론으로 하나로 정해짐"}</p>
      <p>네 자리 카드를 다 모으면: ${all.map((n) => `<b>${n}개</b>`).join(" · ")}${d.open ? " (열린 라운드)" : ""}</p>
      <p class="small muted">규칙 메모의 줄마다 숨은 규칙과 비교한 결과(✓ / ✗와 정답 줄)를 표시했습니다.</p></div>`;
  }

  api("GET", "/signal/meta").then((m) => { META = m; setup(); open(); })
    .catch((e) => flash(`서버에 연결하지 못했습니다(${e.message}). 백엔드: python3 -m uvicorn web.server.app:app --port 8600`));
})();
