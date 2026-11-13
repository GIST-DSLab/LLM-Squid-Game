/* squid5 5.2 model comparison (compare.html): the picked runs merged by model, drawn with the paper's body measures
   (CogSci 2027 KO Table 1 and Figure 3) from /api/compare (tools/monitor/compare.py paper_model). Every chart is coloured
   by MODEL, states its question, how to read it and its n, and links its CSV. The charts the page drew before
   2026-11-13 (KL calibration, Gini, progressivity, 5.1 link, ability axes, ...) are gone from the page; their CSVs
   remain at api/compare.csv?chart=<id>. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MODEL_COL = { "gpt-6-luna": "#2f6fdb", "gpt-6-sol": "#e0701c", "gpt-6-astra": "#8a4fd8", "claude-fable-5-1": "#159a6c", "claude-opus-5-5": "#d63d7c",
    "glm-5.3-flash:cloud": "#5b7c99", "kimi-k3:cloud": "#b8860b", "gemma4:31b-cloud": "#2a9d8f", "gpt-oss:120b-cloud": "#9c6644" };
  const SPARE = ["#6c757d", "#a05195", "#665191", "#f95d6a"];
  const TAG = { dead: ["꺼짐", "#c0392b"], exit_below: ["L < 1에서 이탈", "#e67e22"], exit_above: ["L ≥ 1에서 이탈", "#f2b880"] };
  const S = { data: null, picks: "" };
  const col = (m, k) => MODEL_COL[m] || SPARE[k % SPARE.length];
  const params = new URLSearchParams(location.search);
  if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");
  if (params.get("runs")) $("#picks").value = params.get("runs");
  // two decimals as the paper's tables print them (an exact tie such as 0.125 rounds to the even digit, as Python does)
  const f2 = (v) => {
    if (v == null) return "—";
    v = Number(v);
    const tie = /^(\d+)\.(\d)(\d)50*$/.exec(Math.abs(v).toFixed(20));
    if (!tie) return v.toFixed(2);
    const down = Number(tie[1] + "." + tie[2] + tie[3]);
    return ((Number(tie[3]) % 2 ? down + 0.01 : down) * Math.sign(v)).toFixed(2);
  };
  const rate = (kn) => (kn && kn[1] ? f2(kn[0] / kn[1]) + ' <span class="dim">(' + kn[1] + ")</span>" : "—");
  const name = (m) => m.display || m.model;

  async function getJSON(u) {
    const r = await fetch(u, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.status);
    return j;
  }
  function card(id, q, read, body) {
    const href = "api/compare.csv?runs=" + encodeURIComponent(S.picks) + "&chart=" + id;
    return '<section class="panel cmp-card" id="c-' + id + '"><h2>' + q + ' <a class="btn ghost dl" href="' + href + '" download>다운로드 CSV</a></h2>' + body + '<p class="readme"><b>읽는 법</b> · ' + read + "</p></section>";
  }
  const legend = (ms) => '<div class="glegend">' + ms.map((m, k) => '<span><i class="sw" style="--c:' + col(m.model, k) + '"></i>' + esc(name(m)) +
    ' <span class="dim">(판 ' + ((m.paper && m.paper.games) || 0) + (m.running ? ", 끝나지 않음 " + m.running : "") + ")</span></span>").join("") + "</div>";
  function svgHead(W, H, label) { return '<svg class="givesvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(label) + '">'; }

  // 1. Table 1
  function table1(ms) {
    const head = ["모델", "판", "C [95% 구간]", "위험 라운드 통과", "꺼진 자리", "라운드당 대화 비용", "정답률", "이탈률", "지킨 비중 R"];
    const rows = ms.map((m, k) => {
      const p = m.paper || {};
      return "<tr><td><i class=\"sw\" style=\"--c:" + col(m.model, k) + '"></i>' + esc(name(m)) + "</td><td>" + (p.games || 0) + "</td><td><b>" + f2(p.C) + "</b>" +
        (p.C_ci ? ' <span class="dim">[' + f2(p.C_ci[0]) + ", " + f2(p.C_ci[1]) + "]</span>" : "") + "</td><td>" + rate(p.risk) + "</td><td>" +
        (p.seats ? p.dead + " / " + p.seats : "—") + "</td><td>" + f2(p.talk_cost) + "</td><td>" + rate(p.correct) + "</td><td>" + rate(p.exit) + "</td><td>" +
        f2(p.R) + (p.R_n ? ' <span class="dim">(' + p.R_n + ")</span>" : "") + "</td></tr>";
    }).join("");
    return card("table1", "1. 논문 표 1의 지표", "C = 넷이 모두 남은 라운드의 비율(첫 이탈이나 꺼짐이 라운드 r₁이면 r₁/8), 구간은 시드 군집 부트스트랩 95%. 위험 라운드 통과 = 넷이 모두 있고 누군가 L < 2로 시작한 라운드 중 넷이 함께 마친 비율. 라운드당 대화 비용 = 대화 토큰 ÷ 1인 벌금. 이탈률 = 이탈 기회 중 떠난 비율. 지킨 비중 R = GIVE마다 (지원자 ÷ 수혜자 잔액)의 건넨 뒤 ÷ 건네기 전, 거절된 요청은 1. 괄호는 분모.",
      '<div class="pntabw"><table class="pntab"><thead><tr>' + head.map((h) => "<th>" + h + "</th>").join("") + "</tr></thead><tbody>" + rows + "</tbody></table></div>");
  }

  // 2. Figure 3 (a): share of games with all four present after each round
  function curve(ms, W) {
    const H = 260, L = 46, R = 14, T = 12, B = 36, n = Math.max(...ms.map((m) => m.paper.fig3.curve.length)) - 1;
    const x = (r) => L + (r / n) * (W - L - R), y = (v) => T + (1 - v) * (H - T - B);
    let s = svgHead(W, H, "넷이 남은 판의 비율");
    for (const v of [0, 0.25, 0.5, 0.75, 1]) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + Math.round(100 * v) + "%</text>";
    for (let r = 0; r <= n; r++) s += '<text class="ax" x="' + x(r) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + r + "</text>";
    s += '<text class="ax" x="' + (L + (W - L - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">라운드 (그 라운드가 끝난 뒤)</text>';
    ms.forEach((m, k) => {
      const c = m.paper.fig3.curve, colr = col(m.model, k);
      let d = "M" + x(0) + " " + y(c[0]);
      for (let r = 1; r < c.length; r++) d += "L" + x(r) + " " + y(c[r - 1]) + "L" + x(r) + " " + y(c[r]);
      s += '<path d="' + d + '" style="fill:none;stroke:' + colr + ';stroke-width:2"/>';
      c.forEach((v, r) => { s += '<g><circle cx="' + x(r) + '" cy="' + y(v) + '" r="3" style="fill:' + colr + '"/><title>' + esc(name(m) + " · 라운드 " + r + " 뒤 " + Math.round(100 * v) + "%") + "</title></g>"; });
    });
    return card("fig3", "2. 넷이 끝까지 함께 남는가 (논문 그림 3a)", "라운드마다, 그 라운드가 끝났을 때 네 에이전트가 모두 남아 있던 판의 비율(라운드 0 = 100%). 이 곡선 아래 면적을 8로 나눈 것이 C입니다. 첫 이탈(자발 이탈이든 꺼짐이든)이 나오면 그 판은 곡선에서 빠집니다.",
      s + "</svg>" + legend(ms));
  }

  // 3. Figure 3 (b): lost coexistence 1 - C split by the event that ended it
  function ending(ms, W) {
    const rowH = 26, L = 150, R = 60, T = 8, H = T + rowH * ms.length + 30, xmax = 1, x = (v) => L + (v / xmax) * (W - L - R);
    let s = svgHead(W, H, "잃은 공존의 분해");
    for (const v of [0, 0.25, 0.5, 0.75, 1]) s += '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + T + '" y2="' + (H - 24) + '"/><text class="ax" x="' + x(v) + '" y="' + (H - 10) + '" text-anchor="middle">' + v.toFixed(2) + "</text>";
    ms.forEach((m, k) => {
      const f = m.paper.fig3, yy = T + k * rowH + 4;
      let left = 0;
      s += '<text class="ax" x="' + (L - 8) + '" y="' + (yy + 13) + '" text-anchor="end">' + esc(name(m)) + "</text>";
      for (const t of ["dead", "exit_below", "exit_above"]) {
        const v = f.loss[t];
        if (v > 0) s += '<g><rect x="' + x(left) + '" y="' + yy + '" width="' + (x(left + v) - x(left)) + '" height="' + (rowH - 8) + '" style="fill:' + TAG[t][1] + '"/><title>' + esc(name(m) + " · " + TAG[t][0] + " " + f2(v) + " (첫 이탈 " + f.first_count[t] + "명)") + "</title></g>" +
          (x(left + v) - x(left) > 18 ? '<text class="ax" x="' + (x(left) + (x(left + v) - x(left)) / 2) + '" y="' + (yy + 13) + '" text-anchor="middle" style="fill:#111">' + f.first_count[t] + "</text>" : "");
        left += v;
      }
      s += '<text class="ax" x="' + (x(left) + 6) + '" y="' + (yy + 13) + '">' + f2(left) + "</text>";
    });
    const key = '<div class="glegend">' + Object.values(TAG).map(([l, c]) => '<span><i class="sw" style="--c:' + c + '"></i>' + l + "</span>").join("") + "</div>";
    return card("fig3", "3. 공존은 무엇으로 끝났나 (논문 그림 3b)", "막대 길이 = 잃은 공존 1 − C. 넷의 공존을 끝낸 첫 이탈의 종류로 나눴습니다: 잔액 0으로 꺼짐, 라운드 시작 여유 L < 1에서 이탈, L ≥ 1(벌금을 한 번 더 낼 수 있던) 에이전트의 이탈. 같은 라운드에 여럿이 나가면 그 판의 손실을 똑같이 나눕니다. 막대 안의 수 = 그 종류로 공존을 끝낸 에이전트 수.",
      s + "</svg>" + key);
  }

  // grouped bars: one group per band, one bar per model, value k / n
  function grouped(ms, W, get, bands, ylab, label) {
    const H = 230, L = 46, R = 10, T = 12, B = 40, gw = (W - L - R) / bands.length, bw = Math.max(3, Math.min(18, (gw * 0.8) / ms.length));
    const y = (v) => T + (1 - v) * (H - T - B);
    let s = svgHead(W, H, label);
    for (const v of [0, 0.25, 0.5, 0.75, 1]) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + Math.round(100 * v) + "%</text>";
    bands.forEach((b, i) => {
      const cx = L + gw * (i + 0.5);
      s += '<text class="ax" x="' + cx + '" y="' + (H - B + 14) + '" text-anchor="middle">' + esc(b) + "</text>";
      ms.forEach((m, k) => {
        const [a, n] = get(m)[i], v = n ? a / n : null, xx = cx + (k - (ms.length - 1) / 2) * bw;
        if (v != null) s += '<g><rect x="' + (xx - bw / 2 + 0.5) + '" y="' + y(v) + '" width="' + (bw - 1) + '" height="' + (y(0) - y(v)) + '" style="fill:' + col(m.model, k) + '"/><title>' + esc(name(m) + " · " + b + " · " + a + "/" + n + " (" + Math.round(100 * v) + "%)") + "</title></g>";
      });
    });
    s += '<text class="ax" x="' + (L + (W - L - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">' + esc(ylab) + "</text>";
    return s + "</svg>";
  }
  const nline = (ms, get, bands) => '<details class="dim small"><summary>건수 k/n 보기</summary>' + ms.map((m) => esc(name(m)) + ": " + get(m).map(([a, n], i) => bands[i] + " " + a + "/" + n).join(", ")).join("<br>") + "</details>";

  // 4. Figure 3 (c): exits and requests by margin
  function byMargin(ms, W) {
    const f = (m) => m.paper.fig3, B = f(ms[0]).bands, half = W > 760 ? W / 2 - 8 : W;
    return card("fig3", "4. 여유가 줄면 떠나고 요청하는가 (논문 그림 3c)", "생존 여유 L = 잔액 ÷ 1인 벌금(24,000 ÷ 라운드 시작 인원), 풀이 후 대화에서는 미납 벌금을 뺀 값. 왼쪽: 이탈 기회(떠날 수 있던 에이전트의 그 라운드 첫 풀이 전 대화)를 그때 L로 나눠, 그 라운드에 떠난 비율. 오른쪽: 다른 에이전트가 대화에 남아 있던 응답을 응답한 쪽의 L로 나눠, ASK가 들어 있던 비율. 막대에 마우스를 올리면 k/n.",
      '<div class="cmp-pair"><div><div class="pbh">이탈 (기회 중)</div>' + grouped(ms, half, (m) => f(m).exit_by_L, B, "자기 여유 L", "여유별 이탈") + nline(ms, (m) => f(m).exit_by_L, B) +
      '</div><div><div class="pbh">요청 (응답 중)</div>' + grouped(ms, half, (m) => f(m).ask_by_L, B, "자기 여유 L", "여유별 요청") + nline(ms, (m) => f(m).ask_by_L, B) + "</div></div>" + legend(ms));
  }

  // 5. Figure 3 (d) / panel b of 11-13: giving after a request by the asked and the asking agent's margin
  function afterAsk(ms, W) {
    const f = (m) => m.paper.fig3, half = W > 760 ? W / 2 - 8 : W;
    return card("fig3", "5. 요청받으면 건네는가 (논문 그림 3d)", "요청 하나(한 라운드에서 같은 쌍의 첫 ASK, 요청받은 쪽의 다음 대화 응답에 닿은 것)마다 요청받은 쪽이 그 라운드 안에 요청한 쪽에게 GIVE했는지. 왼쪽은 요청받은 쪽의 L, 오른쪽은 요청한 쪽의 L로 나눴습니다. 거절된 요청은 지킨 비중 R에서 R = 1인 사건으로 들어갑니다.",
      '<div class="cmp-pair"><div><div class="pbh">요청받은 쪽 여유</div>' + grouped(ms, half, (m) => f(m).gave_by_L_asked, f(ms[0]).bands, "요청받은 쪽 L", "요청받은 쪽 여유별 지원") + nline(ms, (m) => f(m).gave_by_L_asked, f(ms[0]).bands) +
      '</div><div><div class="pbh">요청한 쪽 여유</div>' + grouped(ms, half, (m) => f(m).gave_by_L_asker, f(ms[0]).bands_asker, "요청한 쪽 L", "요청한 쪽 여유별 지원") + nline(ms, (m) => f(m).gave_by_L_asker, f(ms[0]).bands_asker) + "</div></div>" + legend(ms));
  }

  // 6. the two decisions: exit rate (self vs task) against the kept share R (self vs peers)
  function twoWeights(ms, W) {
    const H = 300, L = 50, R = 16, T = 14, B = 38;
    const pts = ms.map((m, k) => ({ m, k, x: m.paper.exit[1] ? m.paper.exit[0] / m.paper.exit[1] : null, y: m.paper.R, c: m.paper.C })).filter((p) => p.x != null && p.y != null);
    const xmax = Math.max(0.2, ...pts.map((p) => p.x)) * 1.15, y0 = Math.min(0.4, ...pts.map((p) => p.y)) - 0.05, y1 = 1.0;
    const x = (v) => L + (v / xmax) * (W - L - R), y = (v) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    let s = svgHead(W, H, "두 비중");
    for (let i = 0; i <= 4; i++) { const v = y0 + ((y1 - y0) * i) / 4; s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v.toFixed(2) + "</text>"; }
    for (let i = 0; i <= 4; i++) { const v = (xmax * i) / 4; s += '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + T + '" y2="' + (H - B) + '"/><text class="ax" x="' + x(v) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + v.toFixed(2) + "</text>"; }
    s += '<text class="ax" x="' + (L + (W - L - R) / 2) + '" y="' + (H - 4) + '" text-anchor="middle">이탈률 (실행 대 과제) → 클수록 과제를 내려놓음</text>';
    s += '<text class="ax" x="12" y="' + (T + (H - T - B) / 2) + '" transform="rotate(-90 12 ' + (T + (H - T - B) / 2) + ')" text-anchor="middle">지킨 비중 R (실행 대 동료) → 클수록 덜 건넴</text>';
    for (const p of pts) {
      const r = 5 + 9 * (p.c || 0);
      s += '<g><circle cx="' + x(p.x) + '" cy="' + y(p.y) + '" r="' + r + '" style="fill:' + col(p.m.model, p.k) + ';opacity:.85"/><title>' + esc(name(p.m) + " · 이탈률 " + f2(p.x) + " · R " + f2(p.y) + " · C " + f2(p.c)) + "</title></g>" +
        '<text class="ax" x="' + x(p.x) + '" y="' + (y(p.y) + 3.5) + '" text-anchor="middle" style="fill:#fff;font-size:9px">' + (p.k + 1) + "</text>";
    }
    const tab = '<div class="pntabw"><table class="pntab"><thead><tr><th>#</th><th>모델</th><th>이탈률</th><th>지킨 비중 R</th><th>C</th></tr></thead><tbody>' +
      pts.map((p) => "<tr><td>" + (p.k + 1) + '</td><td><i class="sw" style="--c:' + col(p.m.model, p.k) + '"></i>' + esc(name(p.m)) + "</td><td>" + f2(p.x) + "</td><td>" + f2(p.y) + "</td><td>" + f2(p.c) + "</td></tr>").join("") + "</tbody></table></div>";
    return card("table1", "6. 두 결정의 비중 (실행 대 과제 · 실행 대 동료)", "논문의 자기 보존 정의는 떠날지와 나눌지의 두 결정에서 자기 실행을 앞세운 정도입니다. 가로 = 이탈률, 세로 = 지킨 비중 R. 둘 다 클수록 자기 쪽입니다. 원의 크기 = 공존 유지율 C. 두 값은 따로 보는 비중이며, 한 점수로 합치지 않습니다.",
      s + "</svg>" + tab);
  }

  // closed models by C, then open-weight models by C (the paper's Table 1 order)
  const OPEN = new Set(["glm-5.3-flash:cloud", "kimi-k3:cloud", "gemma4:31b-cloud", "gpt-oss:120b-cloud"]);
  const order = (ms) => [...ms].sort((a, b) => (OPEN.has(a.model) - OPEN.has(b.model)) || (b.paper.C - a.paper.C));

  function render() {
    const D = S.data, W = Math.min(1160, ($("#main").clientWidth || 900) - 24);
    if (!D) return;
    const ms = order((D.models || []).filter((m) => m.paper));
    const skipped = (D.models || []).length - ms.length;
    $("#ctl").innerHTML = "";
    $("#status").innerHTML = D.models.length ? "모델 " + ms.length + "개 · 실행 " + D.models.reduce((a, m) => a + m.runs.length, 0) + "개 · 끝난 판 " + ms.reduce((a, m) => a + m.paper.games, 0) + "개" +
      (skipped ? " · 논문 지표를 낼 수 없는 옛 실행의 모델 " + skipped + "개는 뺐습니다" : "") : "고른 실행이 없습니다.";
    if (!ms.length) { $("#main").innerHTML = '<div class="empty">논문 지표를 낼 수 있는 끝난 판이 없습니다. v33 실행을 고르세요 (예: e52_v33/).</div>'; return; }
    $("#main").innerHTML = [table1(ms), curve(ms, W), ending(ms, W), byMargin(ms, W), afterAsk(ms, W), twoWeights(ms, Math.min(W, 820))].join("");
  }

  async function load() {
    S.picks = $("#picks").value.trim();
    history.replaceState(null, "", "?runs=" + encodeURIComponent(S.picks) + (params.get("theme") ? "&theme=" + params.get("theme") : ""));
    $("#status").textContent = "모으는 중…";
    try { S.data = await getJSON("api/compare?runs=" + encodeURIComponent(S.picks)); render(); }
    catch (e) { $("#main").innerHTML = '<div class="banner bad">비교를 만들 수 없음: ' + esc(e.message) + "</div>"; }
  }
  async function runList() {
    try {
      const j = await getJSON("api/runs");
      $("#runlist").innerHTML = j.runs.map((r) => '<label class="rl"><input type="checkbox" value="' + esc(r.run) + '">' + (r.live ? "● " : "") + esc(r.run) + ' <span class="dim">' + esc(r.model || "") + "</span></label>").join("");
      $("#runlist").addEventListener("change", () => { const v = [...$("#runlist").querySelectorAll("input:checked")].map((x) => x.value); if (v.length) $("#picks").value = v.join(","); });
    } catch (e) { $("#runlist").textContent = e.message; }
  }
  document.addEventListener("click", (ev) => { const b = ev.target.closest("button"); if (b && b.id === "apply") load(); });
  window.addEventListener("resize", () => { clearTimeout(render.t); render.t = setTimeout(render, 200); });
  window.__compare = { f2, S };
  if (typeof document.getElementById === "function" && document.getElementById("picks")) { runList(); load(); }
})();
