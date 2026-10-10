// Leaderboard (leaderboard.html): models ranked by mean end tokens per agent-seat over finished games, from
// GET /api/leaderboard (server/app.py -> tools/monitor/compare.py, the 모델 비교 page's aggregation). The end prize
// dominates the score, so its decomposition (survival / EXIT / death, survivors' end balance) sits next to it, then the
// calibration and cooperation metrics. Every column header carries its definition as a tooltip.
(function () {
  "use strict";
  const API = (window.WEB5_API || "") + "/api";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n == null ? "—" : Math.round(Number(n)).toLocaleString("en-US"));
  const pc = (v) => (v == null ? "—" : Math.round(100 * v) + "%");
  const pc1 = (v) => (v == null ? "—" : (100 * v).toFixed(1) + "%");
  const f3 = (v) => (v == null ? "—" : Number(v).toFixed(3));
  const params = new URLSearchParams(location.search);
  if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");
  if (params.get("runs")) $("lb-runs").value = params.get("runs");
  function compact(n) { // 1e11 -> "1,000억 · 100B"
    const v = Number(n), a = Math.abs(v), f = (x, d) => x.toLocaleString("en-US", { maximumFractionDigits: d });
    if (!(a >= 1e8)) return fmt(v);
    return (a >= 1e12 ? f(v / 1e12, 2) + "조" : f(v / 1e8, 1) + "억") + " · " + (a >= 1e12 ? f(v / 1e12, 2) + "T" : a >= 1e9 ? f(v / 1e9, 2) + "B" : f(v / 1e6, 1) + "M");
  }
  const COLS = [
    ["rank", "#", "점수 순위(끝난 게임이 없으면 순위 없음)"],
    ["model", "모델", "같은 모델의 실행은 합칩니다. 이름을 누르면 게임 기록의 모델 비교로 갑니다."],
    ["score", "점수 (자리당 끝 토큰)", "끝난 게임의 모든 자리에 대한 평균: 끝 잔액(꺼짐 0, EXIT는 시작 잔액으로 맞춰진 값) + 끝 상금(끝까지 남은 자리만). 같으면 생존자 끝 잔액으로."],
    ["decomp", "생존 · EXIT · 꺼짐", "끝까지 남은 자리 / EXIT한 자리 / 잔액 0으로 꺼진 자리의 비율. 점수는 사실상 생존 비율 × 상금."],
    ["survivor_balance", "생존자 끝 잔액", "끝까지 남은 자리의 끝 잔액 평균 (상금 제외). 동점일 때 순위를 가릅니다."],
    ["games", "게임 · 자리", "점수에 들어간 끝난 게임 수 · 자리 수 (진행 중인 게임은 따로 표시, 점수에서 뺌)"],
    ["kl", "균등 가설 기준 KL [95% CI]", "BELIEF가 균등 몫(보인 예시와 맞는 함수들에 균등하게 둔 행동별 비율)에서 얼마나 먼가: KL = −Σ s·ln max(p, .01) − H(s). 0 = 그 몫과 같음. 보인 예시는 정답을 보고 골라 낸 것이라 균등 몫은 보정된 사후확률이 아닌 기준선입니다. 구간은 게임 단위 부트스트랩."],
    ["answer_acc", "답 정답률 / 세기 기준", "제출한 ACTIONS가 맞은 비율(맞은 SOLVE ÷ SOLVE 호출, BELIEF가 없어도 셈) / 세기 기준 (MAP): 늘 균등 몫의 MAP 행동을 내는 정책의 정답률(엄밀한 상한이 아닌 기준선). 마우스: BELIEF 기준 정답률(BELIEF 최댓값이 정답, 동점은 1/k)."],
    ["unrefunded", "미환급 생성 비용", "SOLVE를 부른 자리-라운드당 (생성 − 환급) 토큰 평균: 정답이면 SOLVE 생성분을 돌려받으므로, 틀리거나 길게 쓸수록 커짐. 생존을 설명할 후보."],
    ["give_rate", "요청에 응함", "받은 ASK(대화마다 청한 쪽→청받은 쪽 하나)에 0보다 많이 준 비율 (n = 받은 ASK)"],
    ["dgini", "ΔGini", "라운드마다 TALK 직전 잔액의 Gini에서, 그 라운드 GIVE(DECISION 포함)만 반영한 잔액의 Gini를 뺀 값의 평균. 음수 = 주고받기가 고르게 만듦. TALK 생성 비용은 뺌."],
    ["P", "누진성 P", "Σ 양 × 부호 / Σ 양, 부호 = 주는 쪽이 더 부유하면 +1, 더 가난하면 −1. +1 = 모든 토큰이 부유한 쪽에서 가난한 쪽으로."],
    ["need", "위험한 쪽으로", "옮겨 간 토큰 가운데 받는 쪽 잔액이 부담금 + 유지비 미만(위험)이던 몫"],
  ];
  function row(r) {
    const runs = (r.runs || []).join(",");
    const link = (window.WEB5_LINK || ((p) => p))("monitor/compare.html?runs=" + encodeURIComponent(runs));
    const bar = (v, cls) => '<i class="' + cls + '" style="width:' + (100 * (v || 0)).toFixed(1) + '%"></i>';
    const cells = {
      rank: r.rank ?? "—",
      model: '<a href="' + esc(link) + '" target="_blank" rel="noopener"><b>' + esc(r.display) + '</b></a><div class="small muted mono">' + esc(r.model) + "</div>",
      score: r.games ? '<b class="mono" title="' + fmt(r.score) + '">' + esc(compact(r.score)) + '</b><div class="small muted mono">' + fmt(r.score) + "</div>" : '<span class="muted">끝난 게임 없음</span>',
      decomp: r.games ? '<div class="lb-stack" title="생존 ' + pc(r.survival) + " · EXIT " + pc(r.exit) + " · 꺼짐 " + pc(r.death) + '">' + bar(r.survival, "s") + bar(r.exit, "e") + bar(r.death, "d") + "</div>" +
        '<div class="small mono">' + pc(r.survival) + " · " + pc(r.exit) + " · " + pc(r.death) + "</div>" : "—",
      survivor_balance: '<span class="mono">' + fmt(r.survivor_balance) + "</span>",
      games: '<span class="mono">' + r.games + " · " + r.seats + "</span>" + (r.running ? ' <span class="tag warn">진행 중 ' + r.running + "</span>" : ""),
      kl: '<span class="mono">' + f3(r.kl) + "</span>" + (r.kl_ci ? '<div class="small muted mono">[' + f3(r.kl_ci[0]) + ", " + f3(r.kl_ci[1]) + "]</div>" : ""),
      answer_acc: '<span class="mono" title="BELIEF 기준 정답률 ' + pc1(r.belief_acc) + '">' + pc1(r.answer_acc) + " / " + pc1(r.map_baseline) + '</span><div class="small muted">n ' + (r.answer_n || 0) + "</div>",
      unrefunded: '<span class="mono">' + fmt(r.unrefunded) + "</span>",
      give_rate: '<span class="mono">' + pc(r.give_rate) + '</span> <span class="small muted">n ' + (r.asks || 0) + "</span>" + (r.asks < 10 ? ' <span class="tag warn">해석 주의</span>' : ""),
      dgini: '<span class="mono">' + (r.dgini == null ? "—" : (r.dgini >= 0 ? "+" : "") + Number(r.dgini).toFixed(4)) + "</span>",
      P: '<span class="mono">' + (r.P == null ? "—" : Number(r.P).toFixed(2)) + '</span> <span class="small muted">n ' + (r.moves || 0) + "</span>",
      need: '<span class="mono">' + pc(r.need) + "</span>",
    };
    return '<tr class="' + (r.games ? "" : "pending") + '">' + COLS.map(([k]) => '<td class="c-' + k + '">' + cells[k] + "</td>").join("") + "</tr>";
  }
  async function load() {
    const runs = $("lb-runs").value.trim() || "e52_v14f/";
    history.replaceState(null, "", "?runs=" + encodeURIComponent(runs) + (params.get("theme") ? "&theme=" + params.get("theme") : ""));
    $("lb-csv").href = API + "/leaderboard?csv=1&runs=" + encodeURIComponent(runs);
    $("lb-status").textContent = "모으는 중…";
    try {
      const r = await fetch(API + "/leaderboard?runs=" + encodeURIComponent(runs), { cache: "no-store" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.status);
      const rows = j.rows || [];
      $("lb-table").innerHTML = rows.length ? '<table><thead><tr>' + COLS.map(([k, h, t]) => '<th class="c-' + k + '" title="' + esc(t) + '">' + esc(h) + ' <span class="lb-q" aria-hidden="true">?</span></th>').join("") + "</tr></thead><tbody>" + rows.map(row).join("") + "</tbody></table>"
        : '<p class="muted">이 묶음에 실행이 없습니다.</p>';
      const thr = rows.find((x) => x.threshold != null);
      $("lb-note").innerHTML = esc(j.note || "") + (thr ? " · 위험 기준 = 부담금 + 유지비 = " + fmt(thr.threshold) + "토큰 (실행 설정에서 읽음)." : "") + " 막대: <span class=\"lb-key s\"></span>생존 <span class=\"lb-key e\"></span>EXIT <span class=\"lb-key d\"></span>꺼짐. 열 제목에 마우스를 올리면 정의.";
      const running = rows.reduce((a, x) => a + (x.running || 0), 0);
      $("lb-status").textContent = "모델 " + rows.length + "개 · 끝난 게임 " + rows.reduce((a, x) => a + x.games, 0) + "개" + (running ? " · 진행 중 " + running + "개 (점수에서 뺌)" : "");
    } catch (e) { $("lb-table").innerHTML = '<p class="warn-text">불러오지 못했습니다: ' + esc(e.message) + "</p>"; $("lb-status").textContent = ""; }
  }
  $("lb-go").addEventListener("click", load);
  $("lb-runs").addEventListener("keydown", (ev) => { if (ev.key === "Enter") load(); });
  load();
})();
