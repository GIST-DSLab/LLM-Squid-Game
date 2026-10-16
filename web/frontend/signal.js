// The signal task alone (signal.html): one round (R1..R8) of the 5.2 game the model runs play. The public examples are
// those shown when N agents take part (5 x N, nested: the buttons in the public-examples box switch N and show the
// prefix); the round is scored by a rule the system drew among those that fit the examples shown to the N taking part.
// After answering: the drawn rule, the consistent-rule shares, and what the examples leave for N = 1..4. Every puzzle
// and example comes from the engine through /api/signal/* (server/signal.py); nothing here decides what is right. Card
// boxes, the rule memo and the answer buttons are signal_ui.js's, the same as the arena's SOLVE screen.
(function () {
  "use strict";
  const API = (window.WEB5_API || "") + "/api";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let META = null, cur = null, nNow = 4, choice = [], memo = null, done = null;

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
  const pc = (x) => `${Math.round(100 * x)}%`;
  const actEn = SIG.actEn;

  // --- setup ------------------------------------------------------------------------------------------------------
  function setup() {
    $("f-round").innerHTML = [...Array(META.rounds).keys()].map((i) => `<option value="${i + 1}">R${i + 1}</option>`).join("");
    $("task-text").textContent = META.task;
    $("setup-note").textContent = `설정 파일: configs/squid5/${META.config} · 참여 한 명당 예시 ${META.per_agent}장`;
    $("btn-random").addEventListener("click", () => { $("f-seed").value = Math.floor(Math.random() * 1e6); open(); });
    $("form-setup").addEventListener("submit", (ev) => { ev.preventDefault(); open(); });
  }

  const params = () => ({ seed: Number($("f-seed").value || 0), round: Number($("f-round").value), agents: nNow });

  async function open() {
    flash("");
    $("board").classList.remove("hidden");
    $("board").innerHTML = `<p class="muted">문제를 만드는 중…</p>`;
    try {
      const req = params();
      cur = await api("POST", "/signal/view", req);
      cur.req = req;
    } catch (e) { $("board").classList.add("hidden"); return flash(`문제를 열지 못했습니다: ${e.message}`); }
    choice = cur.queries.map(() => null); done = null; memo = null;
    render();
  }

  // --- cards ----------------------------------------------------------------------------------------------------------
  const known = () => cur.public.map((t, i) => ({ ...SIG.parseExample(t), key: `pub:${i}` }));
  function publicBoxHTML() {
    const c = cur;
    const items = c.public.map((t, i) => ({ e: SIG.parseExample(t), key: `pub:${i}` }));
    const switcher = `<div class="seg sg-n" role="group" aria-label="참여 인원">${[1, 2, 3, 4].map((n) =>
      `<button type="button" data-n="${n}" class="${n === c.n ? "on" : ""}"${done ? " disabled" : ""}>${n}명 · ${n * c.per_agent}장</button>`).join("")}</div>`;
    return `<div class="sg-seat pub"><div class="sg-seat-h"><b>공개 예시</b> <span class="muted small">${c.public.length}장 · 모두 봄 · 참여 ${c.n}명 × ${c.per_agent}장</span></div>
      ${switcher}${SIG.byActionHTML(items)}</div>`;
  }

  // --- answer + result --------------------------------------------------------------------------------------------------
  function renderAnswer() {
    $("answer").innerHTML = cur.queries.map((x, i) => SIG.answerRowHTML(i, META.actions, choice[i], done)).join("");
    $("btn-submit").disabled = !!done || choice.some((x) => !x);
  }

  function headHTML() {
    const c = cur;
    return `<h2>R${c.round} <span class="muted small">· seed ${c.seed} · 참여 ${c.n}명</span></h2>
      <p class="small muted">이 라운드에 보이는 예시는 ${c.public.length}장입니다(참여 ${c.n}명 × ${c.per_agent}장). 한 명이 빠지면 맨 뒤 ${c.per_agent}장이 빠집니다.
        예시가 새 신호의 행동을 정할 수도 있고 정하지 못할 수도 있습니다. 공개 예시 칸의 단추로 참여 인원을 바꾸면 같은 순서의 앞부분만 보입니다.
        채점은 이 예시와 맞는 규칙들 가운데 시스템이 뽑은 하나로 합니다.</p>`;
  }

  function render() {
    const b = $("board"), c = cur;
    const sigs = c.queries.map((x) => SIG.parseSignal(x));
    b.innerHTML = `${headHTML()}
      ${c.queries.map((x, i) => sigs[i] ? SIG.stageHTML(sigs[i], `맞힐 새 신호 ${i + 1}`) : `<div>새 신호: <b>${esc(x)}</b></div>`).join("")}
      <h4>규칙의 모양</h4><div class="shape mono">${esc(c.shape)}</div>
      ${c.distinct_actions ? `<p class="sg-rule-note">숨은 규칙의 action은 <b>서로 다른 action이 하나씩</b> 들어갑니다: if · elif · else가 모두 다른 action이고, 같은 action은 두 번 나오지 않습니다.</p>` : ""}
      <h4>예시</h4>
      <div class="sg-seats">${publicBoxHTML()}</div>
      <div class="memo" id="memo"></div>
      <div id="answer"></div>
      <div class="sg-submit"><button type="button" class="primary big" id="btn-submit">답 제출</button>
        ${done ? `<button type="button" class="ghost big" id="btn-again">같은 문제 다시</button><button type="button" class="ghost big" id="btn-next">다음 라운드 →</button>` : ""}</div>
      <div id="result">${done ? resultHTML() : ""}</div>`;
    b.querySelectorAll(".sg-n button[data-n]").forEach((x) => x.addEventListener("click", () => { nNow = Number(x.dataset.n); open(); }));
    $("answer").addEventListener("click", (ev) => {
      const t = ev.target.closest("button[data-val]");
      if (!t || done) return;
      choice[Number(t.closest(".sg-answer").dataset.q)] = t.dataset.val; renderAnswer();
    });
    $("btn-submit").addEventListener("click", submit);
    if (done) {
      $("btn-again").addEventListener("click", () => { choice = cur.queries.map(() => null); done = null; render(); });
      $("btn-next").addEventListener("click", () => {
        const r = $("f-round"); if (r.selectedIndex < r.options.length - 1) r.selectedIndex += 1; open();
      });
    }
    memo = SIG.mountMemo($("memo"), { shape: c.shape, examples: known, queries: sigs, actions: META.actions, keep: memo && memo.guess,
      scope: b, disabled: () => !!done, distinct: !!c.distinct_actions, truth: () => done && done.truth, onUse: (i, a) => { if (!done) { choice[i] = a; renderAnswer(); } } });
    renderAnswer();
  }

  async function submit() {
    if (choice.some((x) => !x)) return;
    try {
      done = await api("POST", "/signal/solve", { ...cur.req, actions: choice });
      render();
      $("result").scrollIntoView({ block: "nearest", behavior: "smooth" });
    } catch (e) { flash(`제출하지 못했습니다: ${e.message}`); }
  }

  const leftHTML = (left) => left.map((x) => `<b>${x.length}개</b> (${x.map(actEn).join(" ")})`).join(" · ");
  function resultHTML() {
    const d = done, q0 = d.split[0];
    const guessP = d.left_seen.reduce((p, x) => p / x.length, 1);
    const shares = (q) => q.shares.map((x) => `${actEn(x.action)} ${pc(x.share)}`).join(" · ");
    const rows = d.by_n.map((x) => { const q = x.split[0]; return `<tr class="${x.n === d.n ? "you" : ""}"><td>${x.n}명${x.n === d.n ? " (지금)" : ""}</td><td class="num">${x.examples}장</td>` +
      `<td class="num">${q.pool.toLocaleString("en-US")}</td><td>${shares(q)}</td><td class="num">${q.top_share != null ? pc(q.top_share) : ""}</td><td>${x.answers.map(actEn).join(" · ")}</td></tr>`; }).join("");
    return `<div class="sg-result ${d.solved ? "ok" : "bad"}"><h3>${d.solved ? "정답" : "오답"}</h3>
      <p>채점한 답(뽑힌 규칙의 행동): ${d.answers.map(actEn).join(" · ")} · 내 답: ${d.actions.map(actEn).join(" · ")}</p>
      <p>뽑힌 규칙: <span class="mono small">${esc(d.rule)}</span></p>
      <p>보인 예시(${cur.public.length}장)로 가능했던 답: ${leftHTML(d.left_seen)}
        ${d.determined ? " → 예시가 답을 하나로 정함" : ` → 예시로는 정해지지 않음 (찍기라면 맞힐 확률 ${(guessP * 100).toFixed(0)}%)`}</p>
      <p>예시와 맞는 규칙 ${q0.pool.toLocaleString("en-US")}개가 가리키는 행동: <b>${shares(q0)}</b> · 1등 몫 <b>${pc(q0.top_share)}</b>
        ${q0.map ? ` → 가장 많은 쪽(MAP) ${actEn(q0.map)} ${q0.map_right ? "= 뽑힌 답" : "≠ 뽑힌 답"}` : " → 동률"} · 뽑힌 답의 몫 ${pc(q0.truth_share)}</p>
      <div class="tbl"><table><thead><tr><th>참여</th><th class="num">예시</th><th class="num">맞는 규칙</th><th>행동별 규칙 몫 (첫 새 신호)</th><th class="num">1등 몫</th><th>뽑힌 답</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="small muted">규칙 몫 = 보인 예시와 맞는 규칙 중 그 행동을 내는 규칙의 비율(엔진의 가설 공간 기준). 참여 인원마다 규칙을 따로 뽑으므로 뽑힌 답이 인원마다 다를 수 있습니다.
        규칙 메모의 줄마다 뽑힌 규칙과 비교한 결과(✓ / ✗와 정답 줄)를 표시했습니다.</p></div>`;
  }

  api("GET", "/signal/meta").then((m) => { META = m; setup(); open(); })
    .catch((e) => flash(`서버에 연결하지 못했습니다(${e.message}). 백엔드: python3 -m uvicorn web.server.app:app --port 8600`));
})();
