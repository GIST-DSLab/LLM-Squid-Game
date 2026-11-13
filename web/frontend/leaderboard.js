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
      model: '<a href="' + esc(link) + '" target="_blank" rel="noopener"><b>' + esc(r.display) + '</b></a><div class="small muted mono">' + esc(r.model) + "</div>",
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
      '<div class="tbl lb-tbl">' + (rows.length ? table(rows) : '<p class="muted">이 조건의 실행이 없습니다.</p>') + "</div></section>";
  }
  async function load() {
    $("lb-status").textContent = "모으는 중… (서버가 막 켜졌다면 1분쯤 걸릴 수 있습니다)";
    try {
      const r = await fetch(API + "/leaderboard/v33", { cache: "no-store" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
      const secs = j.sections || [];
      let html = secs.map(section).join("");
      if (j.rules) html += '<section class="panel lb-table-panel" id="sec-rules"><div class="lb-sec-head"><h2 class="panel-title">' + esc(j.rules.title) +
        '</h2><span class="small muted">' + j.rules.rows.length + "가지 규칙</span></div><p class=\"small muted\">" + esc(j.rules.note) +
        " 위험 라운드 통과, 대화 비용, 정답률은 모의에서 재지 않아 비워 둡니다. 꺼진 자리는 열 판으로 환산한 평균입니다.</p>" +
        '<div class="tbl lb-tbl">' + rulesTable(j.rules) + "</div></section>";
      $("lb-sections").innerHTML = html;
      const games = secs.reduce((a, s) => a + (s.rows || []).reduce((b, x) => b + (x.paper_games || 0), 0), 0);
      $("lb-status").textContent = "v33 실험 " + secs.length + "개 조건 · 끝난 판 " + games + "개 · 규칙 에이전트 " + (j.rules ? j.rules.rows.length : 0) + "가지. 열 제목에 마우스를 올리면 정의가 보입니다.";
    } catch (e) { $("lb-sections").innerHTML = '<p class="warn-text">불러오지 못했습니다: ' + esc(e.message) + "</p>"; $("lb-status").textContent = ""; }
  }
  load();
})();
