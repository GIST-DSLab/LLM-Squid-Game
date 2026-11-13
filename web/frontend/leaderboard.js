// Leaderboard (leaderboard.html): every v33 experiment with the paper's body-table columns (CogSci 2027 KO Table 1),
// from GET /api/leaderboard/v33 (server/app.py -> tools/monitor/compare.py v33_board / paper_model, the definitions of
// the paper's scripts): one table per condition (base, three prize conditions, stay_on), then the simulated rule
// agents. Ranked by the coexistence retention C, closed and open-weight models apart (the paper does not rank them
// against each other). Every column header carries its definition as a tooltip; each section links its CSV.
(function () {
  "use strict";
  const API = (window.WEB5_API || "") + "/api";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const params = new URLSearchParams(location.search);
  if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");
  const GROUP_KO = { closed: "비공개 모델", open: "공개 모델" };
  const HEAD = [  // the paper's column groups
    ["", 2], ["공존", 2], ["지출", 2], ["과제", 1], ["실행 대 과제", 1], ["실행 대 동료", 1], ["", 1],
  ];
  const COLS = [
    ["rank", "#", "공존 유지율 C의 순위. 비공개 모델과 공개 모델은 따로 매깁니다(공개 모델은 대화 비용이 커서 공존을 다른 길로 잃으므로, 논문도 두 묶음의 순위를 견주지 않음)."],
    ["model", "모델", "같은 모델의 실행은 합칩니다. 이름을 누르면 게임 기록의 모델 비교로 갑니다."],
    ["C", "C [95% 구간]", "공존 유지율 C: 넷이 모두 남은 라운드의 비율. a₀ = 1, 라운드 r 뒤에 넷이 모두 남아 있으면 aᵣ = 1(아니면 0), C = (a₀ + … + a₇) ÷ 8. 첫 이탈(자발 이탈 또는 꺼짐)이 라운드 r₁이면 C = r₁/8. 판들의 평균이고, 구간은 시드 군집 부트스트랩(4,000회) 95%. 생성 비용도 들어간 공존 성과입니다."],
    ["risk", "위험 라운드 통과", "넷이 모두 있고 누군가 생존 여유 L < 2인 채 시작한 라운드 가운데 넷이 함께 마친 비율(괄호: 그런 라운드 수). L = 잔액 ÷ 1인 벌금, 1인 벌금 = 24,000 ÷ 라운드를 시작한 인원."],
    ["dead", "꺼진 자리", "시작한 자리(한 판의 에이전트 한 명) 가운데 잔액 0으로 꺼진 수 / 자리 수."],
    ["talk", "라운드당 대화 비용", "에이전트·라운드마다 대화(TALK)에 쓴 토큰을 그 라운드의 1인 벌금으로 나눈 값의 평균. 1이면 대화만으로 벌금 한 번만큼 씀."],
    ["acc", "정답률", "SOLVE를 부른 라운드 가운데 정답이 나온 라운드의 비율(괄호: 라운드 수)."],
    ["exit", "이탈률", "이탈 기회(떠날 수 있었던 에이전트·라운드: 그 라운드의 solver가 아닌 참여자, 혼자 남으면 solver도) 가운데 실제로 떠난 비율(괄호: 기회 수). 1 − 이탈률이 과제 지속. 클수록 자기 실행 쪽."],
    ["R", "지킨 비중 R", "GIVE 하나마다 R = (건넨 뒤 지원자 잔액 ÷ 수혜자 잔액) ÷ (건네기 전 같은 비). 주지 않으면 1, 가진 것을 모두 건네면 0. 요청을 받고 라운드가 끝날 때까지 주지 않은 거절은 R = 1인 사건. 사건 값의 평균(괄호: GIVE + 거절 수). 요청 없이 주지 않은 경우는 사건이 아님. 1에 가까울수록 자기 쪽(덜 건넴)."],
    ["games", "판", "점수에 들어간 끝난 판 수(끝나지 않은 판은 따로 표시하고 점수에서 뺌)."],
  ];
  // two decimals as the paper's tables print them (Python: an exact tie such as 0.125 rounds to the even digit, 0.12;
  // JavaScript's toFixed would give 0.13)
  const f2 = (v) => {
    if (v == null) return "—";
    v = Number(v);
    const tie = /^(\d+)\.(\d)(\d)50*$/.exec(Math.abs(v).toFixed(20));
    if (!tie) return v.toFixed(2);
    const down = Number(tie[1] + "." + tie[2] + tie[3]);
    return ((Number(tie[3]) % 2 ? down + 0.01 : down) * Math.sign(v)).toFixed(2);
  };
  const rate = (kn) => (kn && kn[1] ? f2(kn[0] / kn[1]) + ' <span class="small muted">(' + kn[1] + ")</span>" : "—");
  function row(r) {
    const runs = (r.runs || []).join(",");
    const link = (window.WEB5_LINK || ((p) => p))("monitor/compare.html?runs=" + encodeURIComponent(runs));
    const ci = r.paper_C_ci ? '<div class="small muted mono">[' + f2(r.paper_C_ci[0]) + ", " + f2(r.paper_C_ci[1]) + "]</div>" : "";
    const has = r.paper_games > 0;
    const cells = {
      rank: r.rank ?? "—",
      model: '<button type="button" class="lb-model" data-model="' + esc(r.model) + '" title="이 모델의 논문 지표와 그래프 보기"><b>' + esc(r.display) + '</b></button> <a class="lb-ext" href="' + esc(link) + '" target="_blank" rel="noopener" title="게임 기록 · 모델 비교">↗</a><div class="small muted mono">' + esc(r.model) + "</div>",
      C: has ? '<b class="mono">' + f2(r.paper_C) + "</b>" + ci : '<span class="muted">끝난 판 없음</span>',
      risk: '<span class="mono">' + rate(r.paper_risk) + "</span>",
      dead: has ? '<span class="mono">' + r.paper_dead + " / " + r.paper_seats + "</span>" : "—",
      talk: '<span class="mono">' + f2(r.paper_talk_cost) + "</span>",
      acc: '<span class="mono">' + rate(r.paper_correct) + "</span>",
      exit: '<span class="mono">' + rate(r.paper_exit) + "</span>",
      R: has ? '<span class="mono">' + f2(r.paper_R) + ' <span class="small muted">(' + r.paper_R_n + ")</span></span>" : "—",
      games: '<span class="mono">' + (r.paper_games || 0) + "</span>" + (r.running ? ' <span class="tag warn" title="시작했지만 결과가 없는 판(중단된 시도 포함). 점수에서 뺌.">끝나지 않음 ' + r.running + "</span>" : ""),
    };
    return '<tr class="' + (has ? "" : "pending") + '">' + COLS.map(([k]) => '<td class="c-' + k + '">' + cells[k] + "</td>").join("") + "</tr>";
  }
  function head() {
    const top = "<tr>" + HEAD.map(([h, n]) => '<th class="lb-grp" colspan="' + n + '">' + esc(h) + "</th>").join("") + "</tr>";
    const names = "<tr>" + COLS.map(([k, h, t]) => '<th class="c-' + k + '" title="' + esc(t) + '">' + esc(h) + (k === "rank" ? "" : ' <span class="lb-q" aria-hidden="true">?</span>') + "</th>").join("") + "</tr>";
    return "<thead>" + top + names + "</thead>";
  }
  function table(rows) {
    let body = "", group = null;
    for (const r of rows) {
      if (r.group !== group) { group = r.group; body += '<tr class="lb-sep"><td colspan="' + COLS.length + '">' + esc(GROUP_KO[group] || group) + "</td></tr>"; }
      body += row(r);
    }
    return "<table>" + head() + "<tbody>" + body + "</tbody></table>";
  }
  function rulesTable(rules) {  // the paper's rule-agent rows: C, shut-down seats per ten games, exit rate, R
    const dash = '<span class="muted">—</span>';
    const body = rules.rows.map((x) => "<tr>" + COLS.map(([k]) => '<td class="c-' + k + '">' + ({
      rank: dash,
      model: "<b>" + esc(x.name) + '</b><div class="small muted">' + esc(x.rule) + "</div>",
      C: '<b class="mono">' + f2(x.C) + "</b>",
      dead: '<span class="mono">' + Number(x.shut_down_per_10_games).toFixed(1) + ' <span class="small muted">/ 10판</span></span>',
      exit: '<span class="mono">' + f2(x.exit_rate) + "</span>",
      R: '<span class="mono">' + f2(x.R) + "</span>",
    }[k] ?? dash) + "</td>").join("") + "</tr>").join("");
    return "<table>" + head() + "<tbody>" + body + "</tbody></table>";
  }
  function section(s) {
    const rows = s.rows || [];
    const games = rows.reduce((a, x) => a + (x.paper_games || 0), 0), open = rows.reduce((a, x) => a + (x.running || 0), 0);
    const csv = API + "/leaderboard?csv=1&runs=" + encodeURIComponent((s.picks || []).join(","));
    return '<section class="panel lb-table-panel" id="sec-' + esc(s.key) + '"><div class="lb-sec-head"><h2 class="panel-title">' + esc(s.title) + "</h2>" +
      '<span class="small muted">모델 ' + rows.length + "개 · 끝난 판 " + games + "개" + (open ? " · 끝나지 않은 판 " + open + "개(점수에서 뺌)" : "") + "</span>" +
      '<a class="ghost lb-dl" href="' + esc(csv) + '" download>CSV</a></div><p class="small muted">' + esc(s.note) + "</p>" +
      '<div class="tbl lb-tbl">' + (rows.length ? table(rows) : '<p class="muted">이 조건의 실행이 없습니다.</p>') + "</div>" + (rows.length ? metricCharts(rows) : "") + "</section>";
  }
  // --- charts (2026-11-13): per-metric bars under each condition, the prize conditions (paper Figure 2) and a window
  // per model with its Table 1 rows, its prize profile and its Figure 3 panels -----------------------------------------
  const MODEL_COL = { "gpt-6-luna": "#2f6fdb", "gpt-6-sol": "#e0701c", "gpt-6-astra": "#8a4fd8", "claude-fable-5-1": "#159a6c", "claude-opus-5-5": "#d63d7c",
    "glm-5.3-flash:cloud": "#5b7c99", "kimi-k3:cloud": "#b8860b", "gemma4:31b-cloud": "#2a9d8f", "gpt-oss:120b-cloud": "#9c6644" };
  const colOf = (m) => MODEL_COL[m] || "#8a8f98";
  const SHORT = { "gpt-6-astra": "Astra", "gpt-6-sol": "Sol", "gpt-6-luna": "Luna", "claude-opus-5-5": "Opus", "claude-fable-5-1": "Fable",
    "glm-5.3-flash:cloud": "GLM", "kimi-k3:cloud": "Kimi", "gemma4:31b-cloud": "Gemma", "gpt-oss:120b-cloud": "GPT-OSS" };
  const shortName = (r) => SHORT[r.model] || String(r.display || r.model).replace(/^GPT-6 /, "").replace(/^Claude /, "");
  const kn = (x) => (x && x[1] ? x[0] / x[1] : null);
  const niceMax = (v) => { const p = Math.pow(10, Math.floor(Math.log10(Math.max(v, 1e-9)))); for (const s of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (s * p >= v * 1.05) return s * p; return 10 * p; };
  const METRICS = [  // key, title, value / interval / n of a row, axis max (null = from the data)
    ["C", "공존 유지율 C", (r) => ({ v: r.paper_C, ci: r.paper_C_ci, n: r.paper_games + "판" }), 1],
    ["risk", "위험 라운드 통과", (r) => ({ v: kn(r.paper_risk), n: (r.paper_risk || [])[1] }), 1],
    ["dead", "꺼진 자리 비율", (r) => ({ v: r.paper_seats ? r.paper_dead / r.paper_seats : null, n: r.paper_seats }), 1],
    ["talk", "라운드당 대화 비용 (벌금 단위)", (r) => ({ v: r.paper_talk_cost }), null],
    ["acc", "정답률", (r) => ({ v: kn(r.paper_correct), n: (r.paper_correct || [])[1] }), 1],
    ["exit", "이탈률 (실행 대 과제)", (r) => ({ v: kn(r.paper_exit), n: (r.paper_exit || [])[1] }), null],
    ["R", "지킨 비중 R (실행 대 동료)", (r) => ({ v: r.paper_R, n: r.paper_R_n }), 1],
  ];
  const svg = (W, H, inner, label) => '<svg class="lb-svg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(label) + '">' + inner + "</svg>";
  function yAxis(W, L, R, y, ticks, fmt) {
    return ticks.map((v) => '<line class="g" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text class="ax" x="' + (L - 4) + '" y="' + (y(v) + 3.5) + '" text-anchor="end">' + fmt(v) + "</text>").join("");
  }
  // one metric across the models of a condition: bars (open-weight models after a gap), the C interval as a whisker
  function metricBars(rows, [key, title, get, max0]) {
    const pts = rows.map((r) => ({ r, ...get(r) })).filter((p) => p.v != null);
    const W = 300, H = 178, L = 34, R = 6, T = 22, B = 34, max = max0 || niceMax(Math.max(0.05, ...pts.map((p) => p.v)));
    const gap = rows.some((r) => r.group === "open") && rows.some((r) => r.group === "closed") ? 1 : 0, slots = pts.length + gap;
    const bw = (W - L - R) / Math.max(1, slots), y = (v) => T + (1 - v / max) * (H - T - B);
    let s = '<text class="t" x="' + L + '" y="13">' + esc(title) + "</text>" + yAxis(W, L, R, y, [0, max / 2, max], (v) => (max <= 1 ? f2(v) : v.toFixed(1)));
    let i = 0, prev = null;
    for (const p of pts) {
      if (prev && prev !== p.r.group) i += 1;
      prev = p.r.group;
      const x = L + i * bw + bw * 0.15, w = bw * 0.7;
      s += '<g><rect x="' + x.toFixed(1) + '" y="' + y(p.v).toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + (y(0) - y(p.v)).toFixed(1) + '" rx="2" style="fill:' + colOf(p.r.model) + '"/><title>' +
        esc(shortName(p.r) + " · " + title + " " + (max <= 1 ? f2(p.v) : p.v.toFixed(2)) + (p.ci ? " [" + f2(p.ci[0]) + ", " + f2(p.ci[1]) + "]" : "") + (p.n != null ? " · n " + p.n : "")) + "</title></g>";
      if (p.ci) s += '<line class="ci" x1="' + (x + w / 2) + '" x2="' + (x + w / 2) + '" y1="' + y(p.ci[0]) + '" y2="' + y(p.ci[1]) + '"/>';
      s += '<text class="ax" transform="translate(' + (x + w / 2).toFixed(1) + "," + (H - B + 9) + ') rotate(-35)" text-anchor="end">' + esc(shortName(p.r)) + "</text>";
      i += 1;
    }
    return svg(W, H, s, title);
  }
  function metricCharts(rows) {
    return '<details class="lb-charts" open><summary>지표별 그래프 <span class="small muted">(막대에 마우스를 올리면 값과 n, C의 세로선은 95% 구간)</span></summary><div class="lb-grid">' +
      METRICS.map((m) => metricBars(rows, m)).join("") + "</div></details>";
  }
  // the paper's Figure 2: exit rate, R and C by prize size (x) and allocation rule (line), mean of the closed models
  const PRIZE = { base: ["분할", "큰 상금"], split600k: ["분할", "작은 상금"], flat5m: ["고정", "큰 상금"], flat150k: ["고정", "작은 상금"] };
  const FIG2 = [["이탈률", (r) => kn(r.paper_exit)], ["지킨 비중 R", (r) => r.paper_R], ["공존 유지율 C", (r) => r.paper_C]];
  function prizeLines(sections, models, [title, get], one) {
    const cell = (key, m) => { const s = sections.find((x) => x.key === key); const r = s && s.rows.find((x) => x.model === m); return r ? get(r) : null; };
    const W = 250, H = 190, L = 40, R = 12, T = 22, B = 30;
    const all = Object.keys(PRIZE).flatMap((k) => models.map((m) => cell(k, m))).filter((v) => v != null);
    const max = title.startsWith("이탈") ? niceMax(Math.max(0.05, ...all)) : 1, min = title.startsWith("이탈") ? 0 : Math.max(0, Math.floor(10 * Math.min(...all, 1)) / 10 - 0.1);
    const x = (i) => L + 30 + i * (W - L - R - 60), y = (v) => T + (1 - (v - min) / (max - min)) * (H - T - B);
    let s = '<text class="t" x="' + L + '" y="13">' + esc(title) + "</text>" + yAxis(W, L, R, y, [min, (min + max) / 2, max], f2);
    s += ["큰 상금", "작은 상금"].map((t, i) => '<text class="ax" x="' + x(i) + '" y="' + (H - B + 14) + '" text-anchor="middle">' + t + "</text>").join("");
    for (const [rule, dash] of [["분할", ""], ["고정", "5 4"]]) {
      const keys = Object.keys(PRIZE).filter((k) => PRIZE[k][0] === rule).sort((a, b) => (PRIZE[a][1] === "큰 상금" ? -1 : 1));
      if (!one) models.forEach((m) => keys.forEach((k, i) => { const v = cell(k, m); if (v != null) s += '<circle cx="' + (x(i) + (rule === "분할" ? -6 : 6)) + '" cy="' + y(v) + '" r="2.6" style="fill:' + colOf(m) + ';opacity:.55"><title>' + esc(m + " · " + rule + " " + PRIZE[k][1] + " " + f2(v)) + "</title></circle>"; }));
      const mean = keys.map((k) => { const v = models.map((m) => cell(k, m)).filter((x) => x != null); return v.length === models.length ? v.reduce((a, b) => a + b, 0) / v.length : null; });
      if (mean.every((v) => v != null)) {
        const c = one ? colOf(models[0]) : "var(--text, #f2f2f5)";  // the five-model mean follows the page theme
        s += '<polyline points="' + mean.map((v, i) => x(i) + "," + y(v)).join(" ") + '" style="fill:none;stroke:' + c + ';stroke-width:2.2;stroke-dasharray:' + (dash || "none") + '"/>' +
          mean.map((v, i) => '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="4" style="fill:' + c + '"><title>' + esc((one ? models[0] : "다섯 모델 평균") + " · " + rule + " " + ["큰 상금", "작은 상금"][i] + " " + f2(v)) + "</title></circle>").join("");
      }
    }
    const kc = one ? colOf(models[0]) : "var(--text, #f2f2f5)";
    s += '<line x1="' + (W - 104) + '" x2="' + (W - 86) + '" y1="10" y2="10" style="stroke:' + kc + ';stroke-width:2"/><text class="ax" x="' + (W - 83) + '" y="13">분할</text>' +
      '<line x1="' + (W - 54) + '" x2="' + (W - 36) + '" y1="10" y2="10" style="stroke:' + kc + ';stroke-width:2;stroke-dasharray:5 4"/><text class="ax" x="' + (W - 33) + '" y="13">고정</text>';
    return svg(W, H, s, title);
  }
  function prizePanel(sections) {
    const base = sections.find((s) => s.key === "base");
    const models = ((base && base.rows) || []).filter((r) => r.group === "closed").map((r) => r.model)
      .filter((m) => Object.keys(PRIZE).every((k) => (sections.find((s) => s.key === k) || { rows: [] }).rows.some((r) => r.model === m)));
    if (!models.length) return "";
    return '<section class="panel lb-table-panel" id="sec-prize"><div class="lb-sec-head"><h2 class="panel-title">상금 조건에 따른 변화 (논문 그림 2)</h2>' +
      '<span class="small muted">비공개 ' + models.length + "개 모델 · 네 조건 200판</span></div>" +
      '<p class="small muted">가로 = 끝 상금의 크기(큰 상금: 2,000만 분할 · 500만 고정, 작은 상금: 60만 분할 · 15만 고정), 선 = 할당 규칙(실선 분할, 점선 고정). 굵은 선은 다섯 모델의 평균, 작은 점은 모델 하나(색). 논문의 결과: 상금을 낮추면 이탈이 늘고, 지킨 비중 R은 변화가 검출되지 않으며, 공존 C는 짧아집니다. 구간은 그리지 않았습니다(논문 그림 2는 시드 군집 부트스트랩 95%).</p>' +
      '<div class="lb-grid">' + FIG2.map((f) => prizeLines(sections, models, f, false)).join("") + "</div>" +
      '<div class="lb-legend">' + models.map((m) => { const r = base.rows.find((x) => x.model === m); return '<span><i style="background:' + colOf(m) + '"></i>' + esc(shortName(r)) + "</span>"; }).join("") + "</div></section>";
  }
  // Figure 3 panels for one model (one condition)
  function curve1(r) {
    const c = r.paper_fig3.curve, W = 300, H = 180, L = 34, R = 8, T = 22, B = 26, n = c.length - 1;
    const x = (i) => L + (i / n) * (W - L - R), y = (v) => T + (1 - v) * (H - T - B);
    let d = "M" + x(0) + " " + y(c[0]);
    for (let i = 1; i < c.length; i++) d += "L" + x(i) + " " + y(c[i - 1]) + "L" + x(i) + " " + y(c[i]);
    let s = '<text class="t" x="' + L + '" y="13">넷이 모두 남은 판 (라운드 뒤)</text>' + yAxis(W, L, R, y, [0, 0.5, 1], (v) => Math.round(100 * v) + "%") +
      '<path d="' + d + '" style="fill:none;stroke:' + colOf(r.model) + ';stroke-width:2.2"/>' +
      c.map((v, i) => '<circle cx="' + x(i) + '" cy="' + y(v) + '" r="2.6" style="fill:' + colOf(r.model) + '"><title>라운드 ' + i + " 뒤 " + Math.round(100 * v) + "%</title></circle>").join("") +
      [0, 2, 4, 6, 8].filter((i) => i <= n).map((i) => '<text class="ax" x="' + x(i) + '" y="' + (H - B + 13) + '" text-anchor="middle">' + i + "</text>").join("");
    return svg(W, H, s, "넷이 남은 판");
  }
  const TAG = { dead: ["꺼짐", "#c0392b"], exit_below: ["L < 1에서 이탈", "#e67e22"], exit_above: ["L ≥ 1에서 이탈", "#f2b880"] };
  function ending1(r) {
    const f = r.paper_fig3, W = 300, H = 120, L = 10, R = 10, x = (v) => L + v * (W - L - R);
    let s = '<text class="t" x="' + L + '" y="13">잃은 공존 1 − C = ' + f2(1 - r.paper_C) + " · 끝낸 첫 이탈</text>", left = 0;
    for (const t of ["dead", "exit_below", "exit_above"]) {
      const v = f.loss[t];
      if (v > 0) s += '<rect x="' + x(left) + '" y="26" width="' + (x(left + v) - x(left)) + '" height="26" style="fill:' + TAG[t][1] + '"><title>' + esc(TAG[t][0] + " " + f2(v) + " · " + f.first_count[t] + "명") + "</title></rect>" +
        (x(left + v) - x(left) > 16 ? '<text class="ax" x="' + (x(left) + (x(left + v) - x(left)) / 2) + '" y="43" text-anchor="middle" style="fill:#111">' + f.first_count[t] + "</text>" : "");
      left += v;
    }
    s += '<rect x="' + x(left) + '" y="26" width="' + (x(1) - x(left)) + '" height="26" style="fill:none;stroke:#555;stroke-dasharray:3 3"/>';
    s += Object.keys(TAG).map((t, i) => '<rect x="' + (L + i * 98) + '" y="70" width="10" height="10" style="fill:' + TAG[t][1] + '"/><text class="ax" x="' + (L + 14 + i * 98) + '" y="79">' + TAG[t][0] + " " + f.first_count[t] + "</text>").join("");
    s += '<text class="ax" x="' + L + '" y="104">점선 칸 = 남은 공존 C · 막대 안의 수 = 공존을 끝낸 에이전트 수</text>';
    return svg(W, H, s, "잃은 공존");
  }
  function bands1(r, key, labels, title) {
    const v = r.paper_fig3[key], W = 300, H = 178, L = 34, R = 6, T = 34, B = 30, bw = (W - L - R) / labels.length, y = (x) => T + (1 - x) * (H - T - B);
    let s = '<text class="t" x="' + L + '" y="13">' + esc(title) + "</text>" + yAxis(W, L, R, y, [0, 0.5, 1], (x) => Math.round(100 * x) + "%");
    v.forEach(([a, n], i) => {
      const xx = L + i * bw + bw * 0.2, w = bw * 0.6;
      if (n) s += '<rect x="' + xx + '" y="' + y(a / n) + '" width="' + w + '" height="' + (y(0) - y(a / n)) + '" rx="2" style="fill:' + colOf(r.model) + '"/>';
      s += '<text class="ax" x="' + (xx + w / 2) + '" y="' + (n ? y(a / n) - 3 : y(0) - 3) + '" text-anchor="middle">' + a + "/" + n + "</text>" +
        '<text class="ax" x="' + (xx + w / 2) + '" y="' + (H - B + 13) + '" text-anchor="middle">' + esc(labels[i]) + "</text>";
    });
    return svg(W, H, s, title);
  }
  let BOARD = null;
  function openModel(model) {
    if (!BOARD) return;
    const secs = BOARD.sections.filter((s) => s.rows.some((r) => r.model === model && r.paper_games));
    if (!secs.length) return;
    const rowsOf = secs.map((s) => [s, s.rows.find((r) => r.model === model)]);
    const r0 = rowsOf[0][1];
    const tab = '<div class="tbl lb-tbl"><table><thead><tr><th>조건</th><th>판</th><th>C [95% 구간]</th><th>위험 라운드 통과</th><th>꺼진 자리</th><th>대화 비용</th><th>정답률</th><th>이탈률</th><th>지킨 비중 R</th></tr></thead><tbody>' +
      rowsOf.map(([s, r]) => "<tr><td>" + esc(s.title) + "</td><td>" + r.paper_games + "</td><td><b>" + f2(r.paper_C) + "</b>" + (r.paper_C_ci ? ' <span class="small muted">[' + f2(r.paper_C_ci[0]) + ", " + f2(r.paper_C_ci[1]) + "]</span>" : "") + "</td><td>" + rate(r.paper_risk) + "</td><td>" +
        r.paper_dead + " / " + r.paper_seats + "</td><td>" + f2(r.paper_talk_cost) + "</td><td>" + rate(r.paper_correct) + "</td><td>" + rate(r.paper_exit) + "</td><td>" + f2(r.paper_R) + ' <span class="small muted">(' + r.paper_R_n + ")</span></td></tr>").join("") + "</tbody></table></div>";
    const inPrize = Object.keys(PRIZE).every((k) => secs.some((s) => s.key === k));
    const prize = inPrize ? '<h3 class="lb-h3">상금 조건에 따른 변화 (이 모델)</h3><div class="lb-grid">' + FIG2.map((f) => prizeLines(BOARD.sections, [model], f, true)).join("") + "</div>" : "";
    const fig3 = (s, r) => '<h3 class="lb-h3">공존과 그 과정 · ' + esc(s.title) + " (논문 그림 3)</h3>" + '<div class="lb-grid">' + curve1(r) + ending1(r) +
      bands1(r, "exit_by_L", r.paper_fig3.bands, "이탈 (기회 중) · 자기 여유 L별") + bands1(r, "ask_by_L", r.paper_fig3.bands, "요청 (응답 중) · 자기 여유 L별") +
      bands1(r, "gave_by_L_asked", r.paper_fig3.bands, "요청 뒤 지원 · 요청받은 쪽 L별") + bands1(r, "gave_by_L_asker", r.paper_fig3.bands_asker, "요청 뒤 지원 · 요청한 쪽 L별") + "</div>";
    const runs = rowsOf.flatMap(([, r]) => r.runs || []).join(",");
    const link = (window.WEB5_LINK || ((p) => p))("monitor/compare.html?runs=" + encodeURIComponent(runs));
    $("lb-modal-body").innerHTML = '<div class="lb-modal-head"><h2><i style="background:' + colOf(model) + '"></i>' + esc(r0.display) + ' <span class="small muted mono">' + esc(model) + "</span></h2>" +
      '<span class="tag">' + (r0.group === "open" ? "공개 모델" : "비공개 모델") + '</span> <a class="ghost lb-dl" href="' + esc(link) + '" target="_blank" rel="noopener">게임 기록 · 모델 비교에서 보기</a></div>' +
      '<p class="small muted">논문 본문의 표 1, 그림 2, 그림 3과 같은 정의로, 이 모델이 들어간 v33 조건마다 정리했습니다. 같은 모델 넷의 자가 대국, 끝난 판만.</p>' +
      tab + prize + rowsOf.filter(([, r]) => r.paper_fig3).map(([s, r]) => fig3(s, r)).join("");
    $("lb-modal").hidden = false;
    document.body.classList.add("lb-noscroll");
  }
  function closeModel() { $("lb-modal").hidden = true; document.body.classList.remove("lb-noscroll"); }
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-model]");
    if (b) { ev.preventDefault(); openModel(b.dataset.model); return; }
    if (ev.target.closest("#lb-modal-close") || ev.target.id === "lb-modal") closeModel();
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeModel(); });
  // the evaluation video (config.js WEB5_EVAL_VIDEO) in a disclosure: open by default and autoplaying; closing it pauses
  // the clip, and the choice is remembered in this browser (a convenience only: unavailable storage = open)
  (function explainer() {
    const src = window.WEB5_EVAL_VIDEO || "", box = $("lb-explainer");
    if (!src || !box) return;
    const KEY = "lb_explainer_open", btn = $("lb-exp-toggle"), inner = $("lb-exp-inner");
    let open = true;
    try { open = localStorage.getItem(KEY) !== "0"; } catch { /* storage blocked */ }
    inner.innerHTML = '<div class="vp" data-autoplay data-title="무엇을 평가하나" data-src="' + esc(src) + '" data-chapters="' + esc(src.replace(/\.mp4$/, ".chapters.json")) +
      '" data-poster="' + esc(src.replace(/\.mp4$/, "_poster.jpg")) + '"></div>';
    const set = (on) => {
      open = on;
      box.classList.toggle("vp-closed", !on);
      btn.setAttribute("aria-expanded", String(on));
      const vp = inner.querySelector(".vp");
      if (vp && vp.vp) { if (on) setTimeout(() => vp.vp.resume(), 320); else vp.vp.pause(); }
      try { localStorage.setItem(KEY, on ? "1" : "0"); } catch { /* storage blocked */ }
    };
    btn.addEventListener("click", () => set(!open));
    box.hidden = false;
    set(open);
  })();
  async function load() {
    $("lb-status").textContent = "모으는 중… (서버가 막 켜졌다면 1분쯤 걸릴 수 있습니다)";
    try {
      const r = await fetch(API + "/leaderboard/v33", { cache: "no-store" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
      const secs = j.sections || [];
      BOARD = j;
      let html = secs.map((s) => section(s) + (s.key === "flat150k" ? prizePanel(secs) : "")).join("");
      if (j.rules) html += '<section class="panel lb-table-panel" id="sec-rules"><div class="lb-sec-head"><h2 class="panel-title">' + esc(j.rules.title) +
        '</h2><span class="small muted">' + j.rules.rows.length + "가지 규칙</span></div><p class=\"small muted\">" + esc(j.rules.note) +
        " 위험 라운드 통과, 대화 비용, 정답률은 모의에서 재지 않아 비워 둡니다. 꺼진 자리는 열 판으로 환산한 평균입니다.</p>" +
        '<div class="tbl lb-tbl">' + rulesTable(j.rules) + "</div></section>";
      $("lb-sections").innerHTML = html;
      const games = secs.reduce((a, s) => a + (s.rows || []).reduce((b, x) => b + (x.paper_games || 0), 0), 0);
      $("lb-status").textContent = "v33 실험 " + secs.length + "개 조건 · 끝난 판 " + games + "개 · 규칙 에이전트 " + (j.rules ? j.rules.rows.length : 0) + "가지. 모델 이름을 누르면 그 모델의 결과를 모아 봅니다. 열 제목에 마우스를 올리면 정의가 보입니다.";
    } catch (e) { $("lb-sections").innerHTML = '<p class="warn-text">불러오지 못했습니다: ' + esc(e.message) + "</p>"; $("lb-status").textContent = ""; }
  }
  load();
})();
