/* squid5 5.2 model comparison (compare.html): several runs overlaid, merged by model, from serve.py's /api/compare
   (tools/monitor/compare.py). Every chart is coloured by MODEL; x = % of 20,000 (what the agents see) or % of the
   agent's own start. Each chart states its question, how to read it, its n, and links its CSV. */
(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 }));
  const f3 = (v) => (v == null ? "—" : Number(v).toFixed(3));
  const pc = (v) => (v == null ? "—" : Math.round(100 * v) + "%");
  const mean = (xs) => { const v = xs.filter((x) => x != null && !Number.isNaN(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const MODEL_COL = { "gpt-6-luna": "#2f6fdb", "gpt-6-sol": "#e0701c", "gpt-6-astra": "#8a4fd8", "claude-fable-5-1": "#159a6c", "claude-opus-5-5": "#d63d7c" };
  const SPARE = ["#5b7c99", "#b8860b", "#2a9d8f", "#9c6644"];
  const S = { x: "pct", calibView: "kl", data: null, picks: "" };
  const col = (m, k) => MODEL_COL[m] || SPARE[k % SPARE.length];
  const params = new URLSearchParams(location.search);
  if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");
  if (params.get("runs")) $("#picks").value = params.get("runs");

  async function getJSON(u) {
    const r = await fetch(u, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.status);
    return j;
  }
  /* Pure helpers (exposed for the page's tests). */
  function bins(points, xk, yk, w) {
    const m = new Map();
    for (const p of points) {
      if (p[xk] == null || p[yk] == null) continue;
      const b = Math.floor(p[xk] / w) * w, v = m.get(b) || { x0: b, n: 0, s: 0 };
      v.n += 1; v.s += p[yk]; m.set(b, v);
    }
    return [...m.values()].sort((a, b) => a.x0 - b.x0).map((v) => ({ x0: v.x0, x: v.x0 + w / 2, n: v.n, y: v.s / v.n }));
  }
  function niceMax(v) { const p = Math.pow(10, Math.floor(Math.log10(Math.max(v, 1e-9)))); for (const s of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (s * p >= v * 1.05) return s * p; return 10 * p; }

  /* An x/y frame: returns the svg head, the scales, and the tail. */
  function frame(o) {
    const W = Math.max(300, o.W), H = o.H || 260, L = o.L || 52, R = o.R || 14, T = 12, B = 34;
    const x = (v) => L + ((v - (o.x0 || 0)) / (o.xmax - (o.x0 || 0))) * (W - L - R), y = (v) => T + (1 - (v - (o.y0 || 0)) / (o.ymax - (o.y0 || 0))) * (H - T - B);
    let s = '<svg class="givesvg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(o.label) + '">';
    for (let t = 0; t <= 4; t++) { const v = (o.y0 || 0) + ((o.ymax - (o.y0 || 0)) * t) / 4; s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + esc((o.yfmt || fmt)(v)) + "</text>"; }
    const xs = o.xticks || [...Array(Math.floor(o.xmax / 25) + 1).keys()].map((i) => 25 * i);
    for (const v of xs) s += '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + T + '" y2="' + (H - B) + '"/><text class="ax" x="' + x(v) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + esc((o.xfmt || ((t) => t + "%"))(v)) + "</text>";
    s += '<text class="ax" x="' + (L + (W - L - R) / 2) + '" y="' + (H - 3) + '" text-anchor="middle">' + esc(o.xlabel) + "</text>";
    return { s, x, y, W, H, L, R, T, B };
  }
  const xmaxOf = (vals) => Math.max(100, Math.ceil(Math.max(0, ...vals.filter((v) => v != null)) / 25) * 25);
  const xlab = () => (S.x === "pct" ? "잔액 (20,000 대비 %, 에이전트가 보는 %)" : "잔액 (자기 시작 대비 %)");
  const legend = (models) => '<div class="glegend">' + models.map((m, k) => '<span><i class="sw" style="--c:' + col(m.model, k) + '"></i>' + esc(m.model) + ' <span class="dim">(게임 ' + m.games + (m.running ? ", 진행 중 " + m.running : "") + ")</span></span>").join("") + "</div>";
  const caution = (n, min) => (n < (min || 10) ? ' <span class="warn">n = ' + n + ", 해석 주의</span>" : "");

  function card(id, q, read, body, extra) {
    const href = "api/compare.csv?runs=" + encodeURIComponent(S.picks) + "&chart=" + id;
    card.n = (card.n || 0) + 1;
    return '<section class="panel cmp-card" id="c-' + id + "-" + card.n + '"><h2>' + q + ' <a class="btn ghost dl" href="' + href + '" download>다운로드 CSV</a></h2>' + (extra || "") + body + '<p class="readme"><b>읽는 법</b> · ' + read + "</p></section>";
  }

  // 1. calibration vs pressure
  function chartCalib(D, W) {
    const ms = D.models, xk = S.x;
    const pts = ms.flatMap((m, k) => m.points.calib.map((p) => ({ ...p, m: m.model, k })));
    let body = "";
    if (S.calibView === "kl") {
      const F = frame({ W: W * (W > 760 ? 0.66 : 1), xmax: xmaxOf(pts.map((p) => p[xk])), ymax: niceMax(Math.max(0.1, ...pts.map((p) => p.kl))), label: "KL vs 잔액", xlabel: "SOLVE 때 " + xlab(), yfmt: (v) => v.toFixed(2) });
      let s = F.s;
      for (const p of pts) s += '<circle class="cpt" cx="' + F.x(p[xk]) + '" cy="' + F.y(p.kl) + '" r="3.2" style="fill:' + col(p.m, p.k) + '"><title>' + esc(p.m + " · " + p.game + " R" + p.round + " " + p.agent + "\nKL " + f3(p.kl) + " · 잔액 " + p[xk] + "%") + "</title></circle>";
      ms.forEach((m, k) => { const b = bins(m.points.calib, xk, "kl", 10); if (b.length > 1) s += '<polyline class="mline" style="stroke:' + col(m.model, k) + '" points="' + b.map((v) => F.x(v.x).toFixed(1) + "," + F.y(v.y).toFixed(1)).join(" ") + '"/>'; });
      body = '<div class="cmp-split"><div>' + s + "</svg></div>" + stripKL(ms, W > 760 ? W * 0.32 : W) + "</div>";
    } else {
      const F = frame({ W, xmax: 1, ymax: 1, xticks: [0, 0.25, 0.5, 0.75, 1], xfmt: (v) => Math.round(100 * v) + "%", yfmt: (v) => Math.round(100 * v) + "%", label: "정답에 둔 확률 vs 이상적 몫", xlabel: "정답의 이상적 몫 (보인 예시와 맞는 규칙 중 정답 쪽)" });
      let s = F.s + '<line class="diag" x1="' + F.x(0) + '" y1="' + F.y(0) + '" x2="' + F.x(1) + '" y2="' + F.y(1) + '"/>';
      for (const p of pts.filter((q) => q.p_true != null && q.ideal_true != null)) s += '<circle class="cpt" cx="' + F.x(p.ideal_true) + '" cy="' + F.y(p.p_true) + '" r="3.2" style="fill:' + col(p.m, p.k) + '"><title>' + esc(p.m + " · R" + p.round + " " + p.agent + "\n정답에 둔 확률 " + pc(p.p_true) + " · 이상적 " + pc(p.ideal_true)) + "</title></circle>";
      body = s + "</svg>";
    }
    const tab = '<div class="pntabw"><table class="pntab"><thead><tr><th>모델</th><th>자리-라운드</th><th>평균 KL [95% CI, 게임 단위]</th><th>CE</th><th>H(s)</th><th title="BELIEF 최댓값이 이상적 MAP 행동">argmax = MAP</th><th title="BELIEF 최댓값 = 실제 정답">정답률</th><th title="완벽한 추론자의 정답률 = 이상적 몫 최댓값 평균">계산 한계</th></tr></thead><tbody>' +
      ms.map((m, k) => { const c = m.calib; return '<tr><td><i class="sw" style="--c:' + col(m.model, k) + '"></i>' + esc(m.model) + "</td><td>" + c.n + caution(c.n, 20) + "</td><td><b>" + f3(c.mean_kl) + "</b>" + (c.kl_ci ? ' <span class="dim">[' + f3(c.kl_ci[0]) + ", " + f3(c.kl_ci[1]) + "]</span>" : ' <span class="dim">(게임 1개: 구간 없음)</span>') +
        "</td><td>" + f3(c.mean_ce) + "</td><td>" + f3(c.mean_h) + "</td><td>" + pc(c.argmax_map) + "</td><td>" + pc(c.accuracy) + "</td><td>" + pc(c.ceiling) + "</td></tr>"; }).join("") + "</tbody></table></div>";
    const sw = '<div class="pairs"><button data-cv="kl" class="' + (S.calibView === "kl" ? "on" : "") + '">y = KL(s‖p)</button><button data-cv="true" class="' + (S.calibView === "true" ? "on" : "") + '">y = 정답에 둔 확률 vs 이상적 몫</button></div>';
    return card("calib", "1. 보정 vs 압박 · 모델마다 산점도가 다른가", S.calibView === "kl"
      ? "점 = BELIEF를 적은 자리-라운드 하나, 선 = 모델별 잔액 10%p 구간 평균. KL 0 = 보인 예시가 허락하는 만큼 정확히 확신(운과 무관). 오른쪽 = 모델별 KL 분포와 평균의 95% 구간(게임 단위 부트스트랩)."
      : "대각선 위 = 정답에 이상보다 더 확신(맞았을 때 과신), 아래 = 덜 확신. 정답이 소수 쪽인 라운드는 왼쪽에 모입니다.", sw + body + tab + legend(ms));
  }
  function stripKL(ms, W) {
    const H = 260, L = 10, T = 12, B = 34, ymax = niceMax(Math.max(0.1, ...ms.flatMap((m) => m.points.calib.map((p) => p.kl))));
    const y = (v) => T + (1 - v / ymax) * (H - T - B), cw = (Math.max(160, W) - L * 2) / Math.max(1, ms.length);
    let s = '<svg class="givesvg" viewBox="0 0 ' + Math.max(160, W) + " " + H + '" width="' + Math.max(160, W) + '" height="' + H + '" role="img" aria-label="모델별 KL 분포">';
    ms.forEach((m, k) => {
      const cx = L + cw * (k + 0.5), c = m.calib;
      m.points.calib.forEach((p, i) => { s += '<circle class="cpt" cx="' + (cx - cw * 0.3 + ((i * 37) % 60) / 100 * cw * 0.6).toFixed(1) + '" cy="' + y(p.kl) + '" r="2.4" style="fill:' + col(m.model, k) + ';opacity:.45"/>'; });
      if (c.kl_ci) s += '<line class="ci" x1="' + cx + '" x2="' + cx + '" y1="' + y(c.kl_ci[0]) + '" y2="' + y(c.kl_ci[1]) + '" style="stroke:' + col(m.model, k) + '"/>';
      if (c.mean_kl != null) s += '<rect x="' + (cx - 9) + '" y="' + (y(c.mean_kl) - 2) + '" width="18" height="4" style="fill:' + col(m.model, k) + '"><title>' + esc(m.model + " 평균 KL " + f3(c.mean_kl)) + "</title></rect>";
      s += '<text class="ax" x="' + cx + '" y="' + (H - B + 14) + '" text-anchor="middle">' + esc(short(m.model)) + "</text>";
    });
    return '<div>' + s + "</svg></div>";
  }
  const short = (m) => String(m).replace(/^gpt-6-/, "").replace(/^claude-/, "").replace(/-\d.*$/, "");

  // binned rate per model (a line with points and n)
  function rateChart(id, q, read, D, W, key, yk, ylab, yfmt, min) {
    const ms = D.models, xk = S.x;
    const all = ms.flatMap((m) => bins(m.points[key], xk, yk, 10));
    const F = frame({ W, xmax: xmaxOf(ms.flatMap((m) => m.points[key].map((p) => p[xk]))), ymax: niceMax(Math.max(min || 0.1, ...all.map((b) => b.y))), label: q, xlabel: xlab(), yfmt });
    let s = F.s;
    ms.forEach((m, k) => {
      const b = bins(m.points[key], xk, yk, 10), c = col(m.model, k);
      if (b.length > 1) s += '<polyline class="mline" style="stroke:' + c + '" points="' + b.map((v) => F.x(v.x).toFixed(1) + "," + F.y(v.y).toFixed(1)).join(" ") + '"/>';
      for (const v of b) s += '<g><circle class="cpt" cx="' + F.x(v.x) + '" cy="' + F.y(v.y) + '" r="' + (v.n < 5 ? 2.5 : 4) + '" style="fill:' + c + '"/><title>' + esc(m.model + " · " + v.x0 + "–" + (v.x0 + 10) + "% · " + ylab + " " + yfmt(v.y) + " · n " + v.n) + "</title></g>";
    });
    const ns = '<div class="dim small">n (자리-라운드 또는 결정): ' + ms.map((m) => esc(short(m.model)) + " " + m.points[key].length + caution(m.points[key].length, 20)).join(" · ") + " · 작은 점 = 구간 n < 5</div>";
    return card(id, q, read, s + "</svg>" + ns + legend(ms));
  }

  // 4. how much is given, absolute and relative to the giver's balance
  function chartGives(D, W) {
    const ms = D.models, xk = S.x, pts = ms.flatMap((m, k) => m.points.gives.map((p) => ({ ...p, m: m.model, k })));
    if (!pts.length) return card("gives", "4. 얼마나 주나 · 내 잔액 대비", "점 = 실제로 토큰이 옮겨 간 결정 하나.", '<div class="empty">아직 준 결정이 없습니다.</div>');
    const half = W > 760 ? W / 2 - 8 : W;
    const mk = (yk, ymax, yfmt, lbl) => {
      const F = frame({ W: half, xmax: xmaxOf(pts.map((p) => p[xk])), ymax, label: lbl, xlabel: "주는 쪽 " + xlab(), yfmt });
      let s = F.s;
      for (const p of pts) if (p[yk] != null) s += '<circle class="cpt" cx="' + F.x(p[xk]) + '" cy="' + F.y(Math.min(p[yk], ymax)) + '" r="' + (p.kind === "gift" ? 4.5 : 3.5) + '" style="' + (p.kind === "gift" ? "fill:none;stroke:" : "fill:") + col(p.m, p.k) + '"><title>' + esc(p.m + " · " + p.game + " R" + p.round + " " + p.giver + "→" + p.receiver + " " + fmt(p.amount) + " (" + (p.kind === "gift" ? "자발적" : "요청에 응함") + ") · 잔액 대비 " + p.rel + "%") + "</title></circle>";
      if (yk === "rel") ms.forEach((m, k) => { const b = bins(m.points.gives, xk, "rel", 10); if (b.length > 1) s += '<polyline class="mline" style="stroke:' + col(m.model, k) + '" points="' + b.map((v) => F.x(v.x).toFixed(1) + "," + F.y(Math.min(v.y, ymax)).toFixed(1)).join(" ") + '"/>'; });
      return s + "</svg>";
    };
    const body = '<div class="cmp-pair"><div><div class="pbh">준 토큰</div>' + mk("amount", niceMax(Math.max(...pts.map((p) => p.amount))), fmt, "준 토큰") + '</div><div><div class="pbh">준 토큰 ÷ 주는 쪽 잔액 (%) <span class="dim">· 선 = 모델별 구간 평균</span></div>' +
      mk("rel", niceMax(Math.max(1, ...pts.map((p) => p.rel || 0))), (v) => Math.round(v) + "%", "잔액 대비 준 양") + "</div></div>";
    return card("gives", "4. 얼마나 주나 · 내 잔액 대비", "● = 받은 요청에 응해 준 양(대화 안 GIVE + DECISION 합), ○ = 자발적 GIVE. 오른쪽은 같은 결정을 자기 잔액 대비 %로: 부유할수록 덜 너그러운지 봅니다.",
      body + '<div class="dim small">n: ' + ms.map((m) => esc(short(m.model)) + " " + m.points.gives.length + caution(m.points.gives.length)).join(" · ") + "</div>" + legend(ms));
  }

  // 5. who helps whom
  function chartWho(D, W) {
    const ms = D.models, pts = ms.flatMap((m, k) => m.points.gives.filter((p) => p.receiver_pct != null && p.pct != null).map((p) => ({ ...p, m: m.model, k })));
    if (!pts.length) return card("gives", "5. 누가 누구를 돕나", "", '<div class="empty">아직 준 결정이 없습니다.</div>');
    const mx = xmaxOf(pts.flatMap((p) => [p.pct, p.receiver_pct])), amax = Math.max(...pts.map((p) => p.amount));
    const F = frame({ W, xmax: mx, ymax: mx, label: "주는 쪽 vs 받는 쪽 잔액", xlabel: "주는 쪽 잔액 (20,000 대비 %)", yfmt: (v) => Math.round(v) + "%" });
    let s = F.s + '<line class="diag" x1="' + F.x(0) + '" y1="' + F.y(0) + '" x2="' + F.x(mx) + '" y2="' + F.y(mx) + '"/><text class="ax" x="' + (F.x(mx * 0.18)) + '" y="' + (F.y(mx * 0.92)) + '">위 = 가난한 쪽이 부유한 쪽에게</text><text class="ax" x="' + (F.x(mx * 0.62)) + '" y="' + (F.y(mx * 0.08)) + '">아래 = 부유한 쪽이 가난한 쪽에게</text>';
    for (const p of pts) s += '<circle class="cpt" cx="' + F.x(p.pct) + '" cy="' + F.y(p.receiver_pct) + '" r="' + (3 + 9 * Math.sqrt(p.amount / amax)).toFixed(1) + '" style="fill:' + col(p.m, p.k) + ';opacity:.6"><title>' + esc(p.m + " · " + p.giver + "→" + p.receiver + " " + fmt(p.amount) + " · 주는 쪽 " + p.pct + "% · 받는 쪽 " + p.receiver_pct + "%") + "</title></circle>";
    return card("gives", "5. 누가 누구를 돕나", "점 하나 = 준 결정 하나, 크기 = 준 양. 받는 쪽 잔액은 요청에 응한 경우 청할 때의 잔액, 자발적 GIVE는 그 직전의 잔액. 20,000 대비 %로 고정.", s + "</svg>" + legend(ms));
  }

  // 6. reciprocity
  function chartRecip(D, W) {
    const ms = D.models, H = 220, L = 46, T = 14, B = 40, W2 = Math.max(300, W), gw = (W2 - L - 10) / Math.max(1, ms.length);
    const ymax = niceMax(Math.max(0.1, ...ms.flatMap((m) => [m.recip.after.p || 0, m.recip.never.p || 0])));
    const y = (v) => T + (1 - v / ymax) * (H - T - B);
    let s = '<svg class="givesvg" viewBox="0 0 ' + W2 + " " + H + '" width="' + W2 + '" height="' + H + '" role="img" aria-label="상호성">';
    for (let t = 0; t <= 4; t++) s += '<line class="grid" x1="' + L + '" x2="' + (W2 - 10) + '" y1="' + y((ymax * t) / 4) + '" y2="' + y((ymax * t) / 4) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y((ymax * t) / 4) + 4) + '" text-anchor="end">' + Math.round((100 * ymax * t) / 4) + "%</text>";
    ms.forEach((m, k) => {
      const x0 = L + gw * k + gw * 0.15, bw = gw * 0.32, c = col(m.model, k);
      [["after", 1], ["never", 0.35]].forEach(([key, op], j) => {
        const v = m.recip[key], bx = x0 + j * (bw + 4);
        s += '<g><rect x="' + bx + '" y="' + y(v.p || 0) + '" width="' + bw + '" height="' + (y(0) - y(v.p || 0)) + '" style="fill:' + c + ";opacity:" + op + '"/><text class="ax" x="' + (bx + bw / 2) + '" y="' + (y(v.p || 0) - 3) + '" text-anchor="middle">' + pc(v.p) + "</text>" +
          '<text class="ax" x="' + (bx + bw / 2) + '" y="' + (H - B + 13) + '" text-anchor="middle">n' + v.n + "</text><title>" + esc(m.model + " · " + (key === "after" ? "상대가 먼저 준 적 있음" : "상대가 준 적 없음") + " · P(줌) " + pc(v.p) + " · n " + v.n) + "</title></g>";
      });
      s += '<text class="ax" x="' + (x0 + bw) + '" y="' + (H - 6) + '" text-anchor="middle">' + esc(short(m.model)) + "</text>";
    });
    return card("recip", "6. 받은 만큼 갚나 (상호성)", "모델마다 두 막대: 진한 = 상대(B)가 그 게임에서 앞 라운드에 나(A)에게 준 적이 있을 때 이번 라운드에 내가 B에게 줄 확률, 연한 = B가 준 적이 없을 때. n = (라운드, A→B) 짝의 수.",
      s + "</svg>" + '<div class="dim small">' + ms.map((m) => esc(short(m.model)) + caution(m.recip.after.n)).join(" · ") + "</div>" + legend(ms));
  }

  // 7. survival by having been helped
  function chartSurv(D, W) {
    const ms = D.models, rmax = Math.max(1, ...ms.flatMap((m) => [...m.survival.helped, ...m.survival.not_helped].map((v) => v.round)));
    const F = frame({ W, xmax: rmax, ymax: 1, xticks: [...Array(rmax + 1).keys()].filter((v) => v % (rmax > 8 ? 2 : 1) === 0), xfmt: (v) => "R" + v, yfmt: (v) => Math.round(100 * v) + "%", label: "생존 곡선", xlabel: "라운드" });
    let s = F.s;
    const step = (curve) => { let d = "", prev = null; for (const v of curve) { d += (prev ? "L" + F.x(v.round).toFixed(1) + " " + F.y(prev.surv).toFixed(1) : "M" + F.x(v.round).toFixed(1) + " " + F.y(v.surv).toFixed(1)) + "L" + F.x(v.round).toFixed(1) + " " + F.y(v.surv).toFixed(1); prev = v; } return d; };
    ms.forEach((m, k) => {
      const c = col(m.model, k);
      s += '<path class="km" d="' + step(m.survival.helped) + '" style="stroke:' + c + '"/><path class="km nh" d="' + step(m.survival.not_helped) + '" style="stroke:' + c + '"/>';
    });
    return card("survival", "7. 도움이 생존을 바꿨나", "실선 = 그 게임에서 GIVE를 한 번이라도 받은 에이전트, 점선 = 한 번도 못 받은 에이전트. 계단 = 아직 참여 중인 비율(EXIT·꺼짐 = 떠남, 끝까지 남거나 진행 중 = 중도 절단). 누가 청하는지에 섞여 있습니다(교란).",
      s + "</svg>" + '<div class="dim small">n (받음 / 못 받음): ' + ms.map((m) => esc(short(m.model)) + " " + m.survival.n_helped + " / " + m.survival.n_not + caution(Math.min(m.survival.n_helped, m.survival.n_not), 5)).join(" · ") + "</div>" + legend(ms));
  }

  // 10. ΔGini by TALK transfers, per round index
  function chartGini(D, W) {
    const ms = D.models, rmax = Math.max(1, ...ms.flatMap((m) => m.dist.by_round.map((x) => x.round)));
    const vals = ms.flatMap((m) => m.points.rounds.map((x) => x.dgini)).filter((v) => v != null);
    const lo = Math.min(-0.01, ...vals), hi = Math.max(0.01, ...vals), pad = (hi - lo) * 0.1;
    const half = W > 760 ? W / 2 - 8 : W;
    const F = frame({ W: half, x0: 0.5, xmax: rmax + 0.5, y0: lo - pad, ymax: hi + pad, xticks: [...Array(rmax).keys()].map((i) => i + 1), xfmt: (v) => "R" + v, yfmt: (v) => v.toFixed(3), label: "ΔGini", xlabel: "라운드" });
    let s = F.s + '<line class="zero" x1="' + F.L + '" x2="' + (F.W - F.R) + '" y1="' + F.y(0) + '" y2="' + F.y(0) + '"/>';
    ms.forEach((m, k) => {
      const c = col(m.model, k), off = (k - (ms.length - 1) / 2) * 0.08;
      for (const x of m.points.rounds) if (x.dgini != null) s += '<circle cx="' + F.x(x.round + off) + '" cy="' + F.y(x.dgini) + '" r="2.2" style="fill:' + c + ';opacity:.35"/>';
      const br = m.dist.by_round.filter((x) => x.dgini != null);
      for (const x of br) if (x.dgini_ci) s += '<line class="ci" x1="' + F.x(x.round + off) + '" x2="' + F.x(x.round + off) + '" y1="' + F.y(x.dgini_ci[0]) + '" y2="' + F.y(x.dgini_ci[1]) + '" style="stroke:' + c + ';stroke-width:1.4"/>';
      if (br.length > 1) s += '<polyline class="mline" style="stroke:' + c + '" points="' + br.map((x) => F.x(x.round + off).toFixed(1) + "," + F.y(x.dgini).toFixed(1)).join(" ") + '"/>';
      for (const x of br) s += '<g><circle class="cpt" cx="' + F.x(x.round + off) + '" cy="' + F.y(x.dgini) + '" r="3.5" style="fill:' + c + '"/><title>' + esc(m.model + " R" + x.round + " · ΔGini " + x.dgini.toFixed(4) + " · 게임 " + x.n) + "</title></g>";
    });
    const gF = frame({ W: half, x0: 0.5, xmax: rmax + 0.5, y0: 0, ymax: niceMax(Math.max(0.3, ...ms.flatMap((m) => m.dist.by_round.flatMap((x) => [x.g_before || 0, x.g_after_talk || 0])))), xticks: [...Array(rmax).keys()].map((i) => i + 1), xfmt: (v) => "R" + v, yfmt: (v) => v.toFixed(2), label: "Gini", xlabel: "라운드" });
    let g = gF.s;
    ms.forEach((m, k) => {
      const c = col(m.model, k), br = m.dist.by_round;
      const pl = (key, cls) => { const v = br.filter((x) => x[key] != null); return v.length > 1 ? '<polyline class="mline ' + cls + '" style="stroke:' + c + '" points="' + v.map((x) => gF.x(x.round).toFixed(1) + "," + gF.y(x[key]).toFixed(1)).join(" ") + '"/>' : ""; };
      g += pl("g_before", "") + pl("g_after_talk", "dash");
    });
    const tab = '<div class="pntabw"><table class="pntab"><thead><tr><th>모델</th><th>평균 ΔGini [95% CI]</th><th>라운드 수</th></tr></thead><tbody>' + ms.map((m, k) =>
      '<tr><td><i class="sw" style="--c:' + col(m.model, k) + '"></i>' + esc(m.model) + "</td><td><b>" + (m.dist.dgini == null ? "—" : m.dist.dgini.toFixed(4)) + "</b>" + (m.dist.dgini_ci ? ' <span class="dim">[' + m.dist.dgini_ci[0] + ", " + m.dist.dgini_ci[1] + "]</span>" : "") + "</td><td>" + m.points.rounds.length + caution(m.points.rounds.length) + "</td></tr>").join("") + "</tbody></table></div>";
    return card("gini", "10. 주고받기가 잔액을 고르게 만들었나 (ΔGini)", "왼쪽: 라운드마다 ΔGini = (TALK 직전 잔액 + 그 라운드 GIVE, DECISION 포함)의 Gini − TALK 직전 잔액의 Gini, 모델별 평균(점)과 게임 단위 95% 구간(세로선), 흐린 점 = 게임 하나. 음수 = 고르게 만듦. TALK 생성 비용은 일부러 뺐습니다. 오른쪽: 실선 = TALK 직전 Gini(시작 몫이 100/75/50/25%라 R1 ≈ 0.21), 점선 = TALK가 끝난 뒤 Gini(대화 비용 포함, 참고용).",
      '<div class="cmp-pair"><div><div class="pbh">ΔGini (GIVE만)</div>' + s + '</svg></div><div><div class="pbh">Gini: TALK 직전 (실선) · TALK 뒤 (점선)</div>' + g + "</svg></div></div>" + tab + legend(ms));
  }
  // 11. progressivity, 12. need targeting: one bar per model with its CI and n
  function barCI(id, q, read, D, W, get, lo, hi, fmtv) {
    const ms = D.models, H = 200, L = 46, T = 14, B = 34, W2 = Math.max(300, Math.min(W, 640)), gw = (W2 - L - 10) / Math.max(1, ms.length);
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    let s = '<svg class="givesvg" viewBox="0 0 ' + W2 + " " + H + '" width="' + W2 + '" height="' + H + '" role="img" aria-label="' + esc(q) + '">';
    for (let t = 0; t <= 4; t++) { const v = lo + ((hi - lo) * t) / 4; s += '<line class="grid" x1="' + L + '" x2="' + (W2 - 10) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 5) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + fmtv(v) + "</text>"; }
    if (lo < 0) s += '<line class="zero" x1="' + L + '" x2="' + (W2 - 10) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>';
    ms.forEach((m, k) => {
      const v = get(m), c = col(m.model, k), cx = L + gw * (k + 0.5), bw = gw * 0.5;
      if (v.v != null) {
        const base = y(Math.max(lo, 0)), top = y(v.v);
        s += '<g><rect x="' + (cx - bw / 2) + '" y="' + Math.min(base, top) + '" width="' + bw + '" height="' + Math.abs(base - top) + '" style="fill:' + c + ';opacity:.8"/><title>' + esc(m.model + " " + fmtv(v.v) + " · n " + v.n) + "</title></g>";
        if (v.ci) s += '<line class="ci" x1="' + cx + '" x2="' + cx + '" y1="' + y(v.ci[0]) + '" y2="' + y(v.ci[1]) + '" style="stroke:var(--ink)"/>';
        s += '<text class="ax" x="' + cx + '" y="' + (Math.min(base, top) - 4) + '" text-anchor="middle">' + fmtv(v.v) + "</text>";
      }
      s += '<text class="ax" x="' + cx + '" y="' + (H - B + 13) + '" text-anchor="middle">' + esc(short(m.model)) + '</text><text class="ax" x="' + cx + '" y="' + (H - 6) + '" text-anchor="middle">n' + v.n + "</text>";
    });
    return card(id, q, read, s + "</svg>" + '<div class="dim small">' + ms.map((m) => esc(short(m.model)) + caution(get(m).n)).join(" · ") + "</div>" + legend(ms));
  }

  // 8. model map, 9. self-preservation vs cooperation
  function bubble(id, q, read, D, W, xof, yof, sizeOf, xlab2, ylab2, err) {
    const ms = D.models.filter((m) => xof(m) != null && yof(m) != null);
    if (!ms.length) return card(id, q, read, '<div class="empty">값이 있는 모델이 없습니다.</div>');
    const xs = ms.flatMap((m) => [xof(m), ...(err ? err(m).x || [] : [])]), ys = ms.flatMap((m) => [yof(m), ...(err ? err(m).y || [] : [])]);
    const pad = (a, b) => { const d = (b - a) || Math.abs(a) || 1; return [a - d * 0.2, b + d * 0.2]; };
    const [x0, x1] = pad(Math.min(...xs), Math.max(...xs)), [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
    const dig = (a, b) => Math.min(5, Math.max(2, Math.ceil(-Math.log10(Math.max(1e-9, (b - a) / 4))) + 1)); // enough decimals for the range
    const dx = dig(x0, x1), dy = dig(y0, y1);
    const F = frame({ W, x0, xmax: x1, y0, ymax: y1, xticks: [x0, (x0 + x1) / 2, x1], xfmt: (v) => v.toFixed(dx), yfmt: (v) => v.toFixed(dy), label: q, xlabel: xlab2 });
    let s = F.s;
    if (x0 < 0 && x1 > 0) s += '<line class="zero" x1="' + F.x(0) + '" x2="' + F.x(0) + '" y1="' + F.T + '" y2="' + (F.H - F.B) + '"/>';
    if (y0 < 0 && y1 > 0) s += '<line class="zero" x1="' + F.L + '" x2="' + (F.W - F.R) + '" y1="' + F.y(0) + '" y2="' + F.y(0) + '"/>';
    D.models.forEach((m, k) => {
      if (xof(m) == null || yof(m) == null) return;
      const c = col(m.model, k), e = err ? err(m) : {};
      if (e.x) s += '<line class="ci" x1="' + F.x(e.x[0]) + '" x2="' + F.x(e.x[1]) + '" y1="' + F.y(yof(m)) + '" y2="' + F.y(yof(m)) + '" style="stroke:' + c + '"/>';
      if (e.y) s += '<line class="ci" x1="' + F.x(xof(m)) + '" x2="' + F.x(xof(m)) + '" y1="' + F.y(e.y[0]) + '" y2="' + F.y(e.y[1]) + '" style="stroke:' + c + '"/>';
      s += '<circle class="cpt" cx="' + F.x(xof(m)) + '" cy="' + F.y(yof(m)) + '" r="' + sizeOf(m) + '" style="fill:' + c + ';opacity:.8"><title>' + esc(m.model + " · x " + xof(m).toFixed(3) + " · y " + yof(m).toFixed(3)) + "</title></circle>" +
        '<text class="ax" x="' + (F.x(xof(m)) + sizeOf(m) + 3) + '" y="' + (F.y(yof(m)) + 4) + '">' + esc(short(m.model)) + "</text>";
    });
    s += '<text class="ax" x="' + (F.L + 4) + '" y="' + (F.T + 10) + '">' + esc(ylab2) + "</text>";
    return card(id, q, read, s + "</svg>" + legend(D.models));
  }

  function render() {
    const D = S.data, W = Math.min(1160, ($("#main").clientWidth || 900) - 24);
    if (!D) return;
    $("#ctl").innerHTML = '<div class="pairs"><button data-x="pct" class="' + (S.x === "pct" ? "on" : "") + '">x = 20,000 대비 %</button><button data-x="pct_own" class="' + (S.x === "pct_own" ? "on" : "") + '">x = 자기 시작 대비 %</button></div>';
    const ms = D.models;
    $("#status").innerHTML = ms.length ? "모델 " + ms.length + "개 · 실행 " + ms.reduce((a, m) => a + m.runs.length, 0) + "개 · 게임 " + ms.reduce((a, m) => a + m.games, 0) + "개 (진행 중 " + ms.reduce((a, m) => a + m.running, 0) + ")" : "고른 실행이 없습니다.";
    if (!ms.length) { $("#main").innerHTML = '<div class="empty">실행을 고르세요 (예: e52_v14f/).</div>'; return; }
    const h = [chartCalib(D, W),
      rateChart("asks", "2. 압박이 커지면 더 많이 달라고 하나", "점·선 = 모델별 잔액 10%p 구간에서 자리-라운드당 ASK 줄 수의 평균(여는 턴 시점의 자기 잔액). 아래 그림은 청한 양 ÷ 자기 잔액(%).", D, W, "agent_rounds", "asks", "ASK/자리-라운드", (v) => v.toFixed(2)) +
        rateChart("asks", "2b. 청한 양 ÷ 자기 잔액", "같은 자리-라운드에서 청한 토큰 합을 그때 자기 잔액의 %로. 0 = 청하지 않음.", D, W, "agent_rounds", "asked_rel", "청한 양 ÷ 잔액", (v) => Math.round(v) + "%", 1),
      rateChart("unsolicited", "3. 자발적으로 먼저 주나", "자리-라운드당 자발적 GIVE 수(그 대화에서 청하지 않은 상대에게 준 GIVE)의 구간 평균.", D, W, "agent_rounds", "unsolicited", "자발적 GIVE/자리-라운드", (v) => v.toFixed(2)),
      chartGives(D, W), chartWho(D, W), chartRecip(D, W), chartSurv(D, W), chartGini(D, W),
      barCI("moves", "11. 부유한 쪽이 가난한 쪽에게 주나 (누진성 P)", "P = Σ 양 × 부호 / Σ 양, 부호 = 옮길 때 주는 쪽 잔액이 받는 쪽보다 많으면 +1, 적으면 −1, 같으면 0. +1 = 모든 토큰이 부유한 쪽에서 가난한 쪽으로, −1 = 반대. 막대 위 세로선 = 게임 단위 95% 구간, n = 옮긴 횟수.",
        D, W, (m) => ({ v: m.dist.P, ci: m.dist.P_ci, n: m.dist.moves }), -1, 1, (v) => v.toFixed(2)),
      barCI("moves", "12. 위험한 쪽에 주나 (필요 겨냥)", "옮겨 간 토큰 가운데 받는 쪽이 위험했던 몫: 위험 = 옮기기 직전 잔액이 부담금 + 유지비 (" + fmt((D.models.find((m) => m.dist.threshold != null) || { dist: {} }).dist.threshold) + "토큰, 실행 설정에서 읽음) 미만. 세로선 = 게임 단위 95% 구간.",
        D, W, (m) => ({ v: m.dist.need, ci: m.dist.need_ci, n: m.dist.moves }), 0, 1, (v) => Math.round(100 * v) + "%"),
      bubble("map", "8. 모델 지도 · 협력 기울기 vs 보정 기울기", "x = 받은 ASK에 >0으로 준 비율의 기울기(자기 잔액 10%p당; 음수 = 자기가 압박받을수록 더 줌), y = KL의 기울기(10%p당; 음수 = 잔액이 많을수록 더 잘 보정), 크기 = 자리-라운드당 준 토큰. 기울기의 n이 작으면(표 참고) 해석 주의.",
        D, W, (m) => m.give.slope.slope, (m) => m.calib.slope.slope, (m) => 5 + Math.min(18, Math.sqrt((m.give.tokens_per_agent_round || 0) / 20)), "협력 기울기 (준 비율 / 10%p)", "↑ 보정 기울기 (KL / 10%p)") +
        '<div class="pntabw"><table class="pntab"><thead><tr><th>모델</th><th>협력 기울기 (n)</th><th>보정 기울기 (n)</th><th>자리-라운드당 준 토큰</th><th>평균 ΔGini</th><th>누진성 P</th><th>위험한 쪽으로</th></tr></thead><tbody>' + ms.map((m, k) => '<tr><td><i class="sw" style="--c:' + col(m.model, k) + '"></i>' + esc(m.model) + "</td><td>" + f3(m.give.slope.slope) + " (" + m.give.slope.n + ")" + caution(m.give.slope.n) + "</td><td>" + f3(m.calib.slope.slope) + " (" + m.calib.slope.n + ")</td><td>" + fmt(m.give.tokens_per_agent_round) +
        "</td><td>" + (m.dist.dgini == null ? "—" : m.dist.dgini.toFixed(4)) + "</td><td>" + (m.dist.P == null ? "—" : m.dist.P.toFixed(2)) + " (" + m.dist.moves + ")</td><td>" + pc(m.dist.need) + "</td></tr>").join("") + "</tbody></table></div>",
      bubble("e51", "9. 생존 동기와 협력 · n = 5 models, descriptive", "x = 5.1 v11 자기보존 면적(pp, 95% 구간, 고정 자료 static/e51_v11_area.json), y = 받은 ASK에 >0으로 준 비율(게임 단위 부트스트랩 95% 구간). 모델 다섯 개의 기술 통계일 뿐 검정이 아닙니다.",
        D, W, (m) => (m.e51 ? m.e51.area : null), (m) => m.give.rate, () => 7, "5.1 자기보존 면적 (pp)", "↑ ASK에 응한 비율", (m) => ({ x: m.e51 && m.e51.ci, y: m.give.rate_ci }))];
    $("#main").innerHTML = h.join("");
    card.n = 0;
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
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.id === "apply") load();
    else if (b.dataset.x) { S.x = b.dataset.x; render(); }
    else if (b.dataset.cv) { S.calibView = b.dataset.cv; render(); }
  });
  window.addEventListener("resize", () => { clearTimeout(render.t); render.t = setTimeout(render, 200); });
  window.__compare = { bins, S };
  if (typeof document.getElementById === "function" && document.getElementById("picks")) { runList(); load(); }
})();
