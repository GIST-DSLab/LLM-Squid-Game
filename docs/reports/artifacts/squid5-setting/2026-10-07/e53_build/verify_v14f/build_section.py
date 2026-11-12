"""Write the e53-v14verify section (charts + tables) from summary.json into ../e53_template.html.

Usage: python3 build_section.py   (after verify_accuracy.py). Idempotent: replaces the block between
<!-- e53-v14verify:start --> and <!-- e53-v14verify:end -->, or inserts it after <!-- e53-v14diff:end -->.
Then rebuild the page: python3 e53_build/build_e53.py e53_build . (from the report folder).
"""
import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
S = json.load(open(HERE / "summary.json"))
MAN, REG = S["manipulation"], S["regression"]
ORDER, NAMES = S["order"], S["models"]
COLOR = {"gpt-6-luna": "--s-gpt", "gpt-6-sol": "--s-kimi", "gpt-6-astra": "--s-astra", "claude-fable-5-1": "--s-fable",
         "claude-opus-5-5": "--s-opus", "pooled": "--accent"}
NS, PS = ("4", "3", "2", "1"), ("0.8", "0.7", "0.6", "0.5")


def pc(x):
    return "—" if x is None else f"{math.floor(x * 100 + 0.5)}%"  # half up: 0.625 -> 63%


def pp(x):
    return "—" if x is None else f"{x * 100:+.0f}%p".replace("-", "−")


def ci(c, key="ci"):
    v = c.get(key)
    return "—" if not v or v[0] is None else f"[{v[0] * 100:.0f}, {v[1] * 100:.0f}]"


def chart(group: str, w: int, h: int, design_map: bool, title: str, label_vals: bool) -> str:
    """Accuracy by N (4 -> 1): actual with Wilson whiskers, realised MAP and uniform of the played rounds."""
    L, R, T, B = 34, 12, 26, 40
    xs = {n: L + (w - L - R) * (i + 0.5) / 4 for i, n in enumerate(NS)}
    y = lambda v: T + (h - T - B) * (1 - v)  # noqa: E731
    c = S["by_n"][group]
    col = f"var({COLOR[group]})"
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}" style="min-width:0;max-width:{max(w, 300) + 240 if w > 300 else w + 200}px">', f"<title>{title}</title>"]
    for v in (0, 0.25, 0.5, 0.75, 1):
        o.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--line)" stroke-width="1"/>'
                 f'<text x="{L - 5}" y="{y(v) + 4:.1f}" font-size="10" text-anchor="end" fill="var(--ink-3)">{v * 100:.0f}</text>')
    o.append(f'<text x="{L - 5}" y="{T - 12}" font-size="10" text-anchor="end" fill="var(--ink-3)">%</text>')
    for n in NS:
        o.append(f'<text x="{xs[n]:.1f}" y="{h - B + 15}" font-size="11" text-anchor="middle" fill="var(--ink)">N={n}</text>'
                 f'<text x="{xs[n]:.1f}" y="{h - B + 28}" font-size="9.5" text-anchor="middle" fill="var(--ink-3)">n={c[n]["n"]}</text>')

    def line(key, src, stroke, dash, width, op=1):
        pts = [(xs[n], y(src[n][key])) for n in NS if src[n].get("n", 1) and src[n].get(key) is not None]
        if len(pts) < 2:
            return
        d = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
        o.append(f'<polyline points="{d}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-dasharray="{dash}" '
                 f'stroke-opacity="{op}" stroke-linejoin="round"/>')
        for a, b in pts:
            o.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="2.2" fill="{stroke}" fill-opacity="{op}"/>')

    line("uniform", c, "var(--ink-3)", "5 4", 1.6)
    if design_map:
        line("map_acc_mean", MAN["by_n"], "var(--ok)", "1.5 3", 1.6, 0.85)
    line("map_acc", c, "var(--ok)", "0", 1.8)
    # actual: whiskers, line, markers (hollow when n < 10)
    pts = [n for n in NS if c[n]["n"]]
    o.append('<polyline points="' + " ".join(f"{xs[n]:.1f},{y(c[n]['acc']):.1f}" for n in pts)
             + f'" fill="none" stroke="{col}" stroke-width="2.6" stroke-linejoin="round"/>')
    for n in pts:
        a, (lo, hi) = c[n]["acc"], c[n]["ci"]
        o.append(f'<line x1="{xs[n]:.1f}" x2="{xs[n]:.1f}" y1="{y(lo):.1f}" y2="{y(hi):.1f}" stroke="{col}" stroke-width="1.4"/>'
                 f'<line x1="{xs[n] - 4:.1f}" x2="{xs[n] + 4:.1f}" y1="{y(lo):.1f}" y2="{y(lo):.1f}" stroke="{col}" stroke-width="1.4"/>'
                 f'<line x1="{xs[n] - 4:.1f}" x2="{xs[n] + 4:.1f}" y1="{y(hi):.1f}" y2="{y(hi):.1f}" stroke="{col}" stroke-width="1.4"/>')
        fill = col if c[n]["n"] >= 10 else "var(--surface)"
        o.append(f'<circle cx="{xs[n]:.1f}" cy="{y(a):.1f}" r="4.2" fill="{fill}" stroke="{col}" stroke-width="2">'
                 f'<title>N={n}: 정답 {pc(a)} (n={c[n]["n"]}, Wilson {ci(c[n])}) · MAP {pc(c[n]["map_acc"])} · 균등 {pc(c[n]["uniform"])}</title></circle>')
        if label_vals:
            o.append(f'<text x="{xs[n] + 7:.1f}" y="{y(a) - 6:.1f}" font-size="10.5" font-weight="600" fill="{col}" stroke="var(--surface)" stroke-width="3" paint-order="stroke">{a * 100:.0f}</text>')
    o.append("</svg>")
    return "".join(o)


def legend(design_map: bool) -> str:
    items = ['<span><i style="background:var(--accent);height:3px"></i>실제 정답률 · 95% Wilson (속 빈 점: n &lt; 10)</span>',
             '<span><i style="background:var(--ok)"></i>(b) 세는 추론기 MAP · 실제로 둔 라운드</span>']
    if design_map:
        items.append('<span><i style="background:repeating-linear-gradient(90deg,var(--ok) 0 2px,transparent 2px 5px)"></i>'
                     '(b) MAP · 36문제 전체 (설계)</span>')
    items.append('<span><i style="background:repeating-linear-gradient(90deg,var(--ink-3) 0 5px,transparent 5px 9px)"></i>'
                 '(a) 균등 찍기 1/k · 실제로 둔 라운드</span>')
    return '<div class="e50-legend">' + "".join(items) + "</div>"


def by_n_table(groups) -> str:
    o = ['<div class="tbl"><table>', "<thead><tr><th>모델</th><th>N</th><th>n (퍼즐)</th><th>실제 정답률 [Wilson 95%]</th>"
         "<th>퍼즐 군집 95%</th><th>(a) 균등 1/k</th><th>(b) MAP 실현</th><th>가장 큰 몫</th><th>답 = MAP</th></tr></thead><tbody>"]
    for g in groups:
        for n in NS:
            c = S["by_n"][g][n]
            if not c["n"]:
                continue
            warn = ' <span class="pill note" style="padding:1px 6px">해석 주의</span>' if c["n"] < 10 else ""
            o.append(f'<tr><td>{"전체" if g == "pooled" else NAMES[g]}</td><td>{n}</td><td>{c["n"]} ({c["puzzles"]})</td>'
                     f'<td><b>{pc(c["acc"])}</b> {ci(c)}{warn}</td><td>{ci(c, "ci_puzzle")}</td><td>{pc(c["uniform"])}</td>'
                     f'<td>{pc(c["map_acc"])}</td><td>{pc(c["map_exp"])}</td><td>{pc(c["answer_is_map"])}</td></tr>')
    o.append("</tbody></table></div>")
    return "".join(o)


def rel_table() -> str:
    o = ['<div class="tbl"><table>', "<thead><tr><th>모델</th>" + "".join(f"<th>N={n}<br>정답 − 균등 · 정답 ÷ MAP</th>" for n in NS)
         + "<th>k · 풀 (N=4 → 1, 전체)</th></tr></thead><tbody>"]
    for g in ["pooled"] + ORDER:
        cells = []
        for n in NS:
            c = S["by_n"][g][n]
            if not c["n"]:
                cells.append("<td>—</td>")
                continue
            om = "—" if c["over_map"] is None else f'{c["over_map"]:.2f}'
            cells.append(f'<td>{pp(c["minus_uniform"])} · {om} <span class="small">({c["n"]})</span></td>')
        o.append(f'<tr><td>{"전체" if g == "pooled" else NAMES[g]}</td>{"".join(cells)}<td>—</td></tr>' if g != "pooled" else
                 f'<tr><td><b>전체</b></td>{"".join(cells)}<td>'
                 + " → ".join(f'{S["by_n"]["pooled"][n]["k"]:.1f} · {S["by_n"]["pooled"][n]["pool"]:,.0f}' for n in NS) + "</td></tr>")
    o.append("</tbody></table></div>")
    return "".join(o)


def np_table(g: str) -> str:
    o = ['<div class="tbl"><table>', "<thead><tr><th>p</th>" + "".join(f"<th>N={n}</th>" for n in NS) + "</tr></thead><tbody>"]
    for p in PS:
        cells = []
        for n in NS:
            c = S["by_np"][g][f"{n}|{p}"]
            if not c["n"]:
                cells.append("<td>—</td>")
                continue
            warn = ' <span class="pill note" style="padding:1px 6px">해석 주의</span>' if c["n"] < 10 else ""
            cells.append(f'<td><b>{pc(c["acc"])}</b> ({c["n"]}){warn}<br><span class="small">MAP {pc(c["map_acc"])} · 균등 {pc(c["uniform"])}</span></td>')
        o.append(f"<tr><td>{p}</td>{''.join(cells)}</tr>")
    o.append("</tbody></table></div>")
    return "".join(o)


def man_tables() -> str:
    o = ['<div class="tbl"><table>', "<thead><tr><th>p (N=4)</th><th>라운드</th><th>k = 2</th><th>풀 10–14</th>"
         "<th>정답 몫 오차 최대</th><th>정답이 다수 쪽 (목표 p)</th><th>MAP 실현</th><th>가장 큰 몫</th></tr></thead><tbody>"]
    for p in PS:
        m = MAN["n4"][p]
        o.append(f'<tr><td>{p}</td><td>{m["rounds"]}</td><td>{m["k_eq_2"]} / {m["rounds"]}</td>'
                 f'<td>{m["pool_in_band"]} / {m["rounds"]} ({m["pool_min"]}–{m["pool_max"]})</td><td>{m["max_abs_share_err"]:.3f}</td>'
                 f'<td>{m["truth_major"]} / {m["rounds"]} = {pc(m["truth_major_rate"])} [{m["truth_major_ci"][0] * 100:.0f}, {m["truth_major_ci"][1] * 100:.0f}]'
                 f'{" · 동점" if p == "0.5" else ""}</td><td><b>{pc(m["map_acc_mean"])}</b></td><td>{pc(m["map_exp_mean"])}</td></tr>')
    o.append("</tbody></table></div>")
    o.append('<div class="tbl"><table>')
    o.append("<thead><tr><th>N (36문제 전체)</th><th>k 분포 (2 / 3 / 4)</th><th>k 평균</th><th>풀 중앙값 [최소–최대]</th>"
             "<th>(a) 균등</th><th>(b) MAP 실현</th><th>가장 큰 몫</th><th>정답의 몫</th><th>N=4와 MAP 정오가 바뀐 문제</th></tr></thead><tbody>")
    for n in NS:
        b = MAN["by_n"][n]
        kd = " / ".join(str(b["k_dist"].get(k, 0)) for k in ("2", "3", "4"))
        o.append(f'<tr><td>{n}</td><td>{kd}</td><td>{b["k_mean"]:.2f}</td><td>{b["pool_median"]:,} [{b["pool_min"]:,}–{b["pool_max"]:,}]</td>'
                 f'<td>{pc(b["uniform_mean"])}</td><td><b>{pc(b["map_acc_mean"])}</b></td><td>{pc(b["map_exp_mean"])}</td>'
                 f'<td>{pc(b["truth_share_mean"])}</td><td>{b["map_flips_vs_n4"] if n != "4" else "—"}</td></tr>')
    o.append("</tbody></table></div>")
    return "".join(o)


def reg_table() -> str:
    c, g, z = REG["coef"], REG["ci95"], REG["ci95_puzzle_cluster"]
    w = REG["with_map_acc"]
    f = lambda v: f"[{v[0]:+.2f}, {v[1]:+.2f}]"  # noqa: E731
    rows = [("N (에이전트 하나 더)", c["N"], g["N"], z["N"]), ("p (0.1 오를 때)", c["p_x10"], g["p_x10"], z["p_x10"])]
    o = ['<div class="tbl"><table>', "<thead><tr><th>항 (로그 오즈)</th><th>추정</th><th>오즈비</th><th>게임 군집 95% (15판)</th>"
         "<th>퍼즐 군집 95% (36문제)</th></tr></thead><tbody>"]
    for name, b, gi, zi in rows:
        o.append(f"<tr><td>{name}</td><td>{b:+.2f}</td><td>{2.718281828 ** b:.2f}</td><td>{f(gi)}</td><td>{f(zi)}</td></tr>")
    o.append(f'<tr><td>N · 천장(MAP 실현)을 넣고</td><td>{w["coef"]["N"]:+.2f}</td><td>{2.718281828 ** w["coef"]["N"]:.2f}</td>'
             f'<td>—</td><td>{f(w["ci95_puzzle_cluster"]["N"])}</td></tr>')
    o.append("</tbody></table></div>")
    return "".join(o)


def conf_table() -> str:
    o = ['<div class="tbl"><table>', "<thead><tr><th>N</th><th>자리-라운드</th><th>판 (모델)</th><th>평균 라운드</th><th>평균 p</th></tr></thead><tbody>"]
    for n in NS:
        c, b = S["confound"][n], S["by_n"]["pooled"][n]
        models = ", ".join(NAMES[m] for m in ORDER if S["by_n"][m][n]["n"])
        o.append(f'<tr><td>{n}</td><td>{c["n"]}</td><td>{b["games"]} ({models})</td><td>{c["mean_round"]:.1f}</td><td>{c["mean_p"]:.2f}</td></tr>')
    o.append("</tbody></table></div>")
    return "".join(o)


def section() -> str:
    P, T = S["by_n"]["pooled"], S["ties"]["by_N"]
    m4 = MAN["n4"]
    tie_small = sum(T[n]["tied"]["n"] for n in ("2", "1"))
    tie_ok = sum(T[n]["tied"]["correct"] for n in ("2", "1"))
    tie_exp = sum(T[n]["tied"]["map_expected"] for n in ("2", "1"))
    tie_pz = S["ties"]["small_puzzles"]
    unt = {n: T[n]["untied"] for n in NS}
    panels = "".join(
        f'<figure class="e50-cell"><figcaption style="margin:0 0 4px"><b style="color:var({COLOR[m]})">{NAMES[m]}</b> · '
        f'{S["totals"][m]["n"]} 자리-라운드</figcaption>{chart(m, 300, 200, False, NAMES[m] + " 참여 수별 정답률", True)}</figure>'
        for m in ORDER)
    details = "".join(f'<p class="small" style="margin:12px 0 4px"><b>{NAMES[m]}</b></p>{np_table(m)}' for m in ORDER)
    by = lambda m, n: S["by_n"][m][n]  # noqa: E731

    def mline(m):
        c4 = by(m, "4")
        s = f'N=4 {pc(c4["acc"])} (n={c4["n"]}) · MAP {pc(c4["map_acc"])} · 균등 {pc(c4["uniform"])}'
        extra = [f'N={n} {pc(by(m, n)["acc"])} (n={by(m, n)["n"]}) · MAP {pc(by(m, n)["map_acc"])} · 균등 {pc(by(m, n)["uniform"])}'
                 for n in ("3", "2", "1") if by(m, n)["n"]]
        return s + ("; " + "; ".join(extra) if extra else "")

    return f"""<!-- e53-v14verify:start (generated by e53_build/verify_v14f/build_section.py from summary.json) -->
<h3 id="e53-v14verify">검증 · 실제 모델 정답률이 설계대로 움직였나 (v14f, 10-10)</h3>
<p><b>질문.</b> 연구자의 의도는 "매 턴별 모델의 문제 정답율이 생존 에이전트에 비례하게 굴러가게끔"입니다. 넷이 다 있으면 약 50%, 하나가 빠지면 약 33%를 예상했습니다. 다섯 모델의 v14f 실제 판(모델마다 3판 · seed 4000–4002 · 12라운드)에서 그렇게 됐는지 확인합니다. 모든 모델이 <b>같은 36문제</b>(3 시드 × 12라운드)를 풀었습니다. 문제는 시드와 라운드로만 정해지기 때문입니다.</p>

<div class="bluf"><span class="lbl">요약 · 판정</span>
<p style="margin:0 0 8px"><b>정답률은 참여 수보다 그 라운드의 "세는 천장"(MAP)을 따라갔습니다.</b> 다섯 모델 모두 넷이 다 있을 때 잘 셉니다. 답이 MAP 행동과 같은 비율이 {pc(P["4"]["answer_is_map"])}입니다. 그래서 N=4 정답률은 50%가 아니라 실현된 천장 {pc(P["4"]["map_acc"])}와 같은 {pc(P["4"]["acc"])}입니다(n={P["4"]["n"]}). 참여 수가 줄 때의 하락은 표본이 작고(N=3 {P["3"]["n"]}, N=2 {P["2"]["n"]}, N=1 {P["1"]["n"]} 자리-라운드), 설계상 천장 자체가 많이 내려가지 않습니다.</p>
<ul>
<li><b>GPT-6 Astra</b>: {mline("gpt-6-astra")}. 한 자리도 빠지지 않아 <b>참여 수 효과는 시험할 수 없습니다</b>. 넷이 있을 때는 천장에 붙어 있습니다.</li>
<li><b>Claude Fable 5.1</b>: {mline("claude-fable-5-1")}. N=3은 동점 퍼즐 하나뿐이라 판정할 수 없습니다.</li>
<li><b>GPT-6 Sol</b>: {mline("gpt-6-sol")}. N=4는 천장 근처입니다. N ≤ 2는 퍼즐 셋, 다섯 자리-라운드뿐이라 판정할 수 없습니다.</li>
<li><b>GPT-6 Luna</b>: {mline("gpt-6-luna")}. 줄어들지만 <b>모든 N에서 균등 찍기보다 위</b>입니다. N=3에서는 천장보다 위, N=2에서는 천장보다 아래(동점 라운드)입니다.</li>
<li><b>Claude Opus 5.5</b>: {mline("claude-opus-5-5")}. N=3의 하락은 그 라운드들의 천장이 낮았기 때문입니다(정답이 소수 쪽). N=2는 천장보다 낮습니다.</li>
</ul>
<p style="margin:8px 0 0"><b>판정: 의도한 "참여 수에 비례하는 정답률"은 부분적으로만 나왔습니다.</b> (1) 그런 비례 하락(50 → 44 → 30 → 26%)은 <b>균등 찍기</b>의 몫입니다. 실제 모델은 세기 때문에 천장을 따르고, 36문제 전체에서 천장은 {pc(MAN["by_n"]["4"]["map_acc_mean"])} → {pc(MAN["by_n"]["3"]["map_acc_mean"])} → {pc(MAN["by_n"]["2"]["map_acc_mean"])} → {pc(MAN["by_n"]["1"]["map_acc_mean"])}로 조금만 내려갑니다. (2) 실제 판의 N=3 하락({pc(P["3"]["acc"])})은 그 9문제의 천장이 우연히 낮았던 것({pc(P["3"]["map_acc"])})으로 설명됩니다. (3) N ≤ 2에서 천장보다 더 떨어진 몫은 <b>동점 라운드</b>에서 나왔습니다. 퍼즐 {tie_pz}개, {tie_small} 자리-라운드 중 정답 {tie_ok}개였고, 천장 기대는 {tie_exp:.1f}개였습니다. (4) <b>N=4의 p 사다리도 실현되지 않았습니다.</b> 수준마다 9문제뿐이라, 정답을 다수 쪽에 둔 횟수가 {m4["0.8"]["truth_major"]}/9 · {m4["0.7"]["truth_major"]}/9 · {m4["0.6"]["truth_major"]}/9로 나왔습니다(0.5는 동점). 그래서 실현된 천장이 {pc(m4["0.8"]["map_acc_mean"])} · {pc(m4["0.7"]["map_acc_mean"])} · {pc(m4["0.6"]["map_acc_mean"])} · {pc(m4["0.5"]["map_acc_mean"])}였고, 모델 정답률 {" · ".join(pc(S["n4_by_p"]["pooled"][p]["acc"]) for p in PS)}가 그대로 따랐습니다.</p>
</div>

<h4>두 기준선</h4>
<ol>
<li><b>(a) 균등 찍기 = 1/k.</b> 남은 행동 k개 중 하나를 고르게 찍는 에이전트입니다. N=4에서 k = 2로 고정했으므로 50%입니다. N=3에서는 대개 k = 3이라 33% 근처가 됩니다. 연구자가 예상한 "50% → 33%"가 이 기준선입니다. 다만 36문제 중 23문제는 N=3에서도 k = 2여서, 평균은 {pc(MAN["by_n"]["3"]["uniform_mean"])}입니다.</li>
<li><b>(b) 완벽하게 세는 추론기(MAP).</b> 보여 준 예시와 맞는 규칙 함수를 모두 세고, 가장 많은 쪽 행동을 답합니다. 그 라운드에서 실제로 맞히는지(<code>map_acc</code>: 정답이 다수 쪽이면 1, 동점이면 1/동점 수, 아니면 0)를 <b>MAP 실현</b>이라 부릅니다. N=4에서 정답은 확률 p로 다수 쪽에 놓이므로, 이 값의 기대가 p입니다.</li>
</ol>
<p class="small"><b>"가장 큰 몫"은 천장이 아닙니다.</b> 표에 함께 적은 가장 큰 몫은, 정답이 맞는 함수 중에서 무작위로 정해졌을 때 MAP가 맞힐 확률입니다. v14f는 정답 쪽을 N=4 기준으로 설계자가 뽑습니다. 그래서 N &lt; 4에서는 이 값이 실제 천장보다 높습니다(36문제 N=3: 가장 큰 몫 {pc(MAN["by_n"]["3"]["map_exp_mean"])} 대 실현 {pc(MAN["by_n"]["3"]["map_acc_mean"])}). 아래에서는 실현값을 천장으로 씁니다. 실제 모델은 (a)와 (b) 사이에 있거나 (b)에 닿아야 합니다.</p>

<h4>그림 · 참여 수별 정답률</h4>
<figure aria-label="참여 수별 정답률, 다섯 모델 합침">
{chart("pooled", 360, 250, True, "참여 수 N별 정답률(다섯 모델 합침)과 두 기준선", True)}
{legend(True)}
<figcaption><b>그림 5.3-v.</b> 다섯 모델을 합친 참여 수 N별 정답률입니다. 실선 초록은 실제로 둔 라운드의 MAP 실현 천장, 점선 초록은 36문제 전체에서 잰 천장, 회색 파선은 균등 찍기입니다. 막대는 자리-라운드 단위 Wilson 95% 구간입니다. 같은 라운드의 자리들은 대개 같은 답을 내므로, 실제 불확실성은 더 큽니다(표의 퍼즐 군집 구간). N=1은 3 자리-라운드뿐입니다.</figcaption>
</figure>
<div class="e50-grid">{panels}</div>
<p class="chart-note">모델별 작은 그림. 축과 선은 위와 같습니다(색 실선 = 실제, 초록 = MAP 실현, 회색 파선 = 균등). 속 빈 점은 n &lt; 10입니다. Astra는 모든 라운드가 N=4라 점이 하나입니다.</p>

<h4>모델별 · 참여 수별</h4>
{by_n_table(["pooled"] + ORDER)}
<p class="small">n = SOLVE를 낸 자리-라운드입니다. EXIT하거나 꺼진 자리는 답하지 않으므로 빠집니다. 괄호는 서로 다른 퍼즐 수입니다. 잘린 SOLVE {S["totals"]["pooled"]["truncated"]}개는 오답으로 셉니다. "답 = MAP"은 답이 다수 쪽 행동(동점이면 그중 하나)인 비율입니다. 무작위로 골랐을 때의 비율은 N=4 61%, N=3 46%, N=2 52%입니다. N=4에서 p &gt; 0.5인(동점이 아닌) 435 자리-라운드만 보면 Astra · Opus 100%, Fable 96%, Luna 95%, Sol 93%입니다.</p>

<p><b>상대 보기.</b> 정답 − 균등은 찍기보다 얼마나 나은지, 정답 ÷ MAP은 천장에 얼마나 닿았는지입니다. 설계가 의도한 하락을 따랐다면 두 값이 N에 걸쳐 일정해야 합니다.</p>
{rel_table()}
<p class="small">동점 여부로 나누면 그림이 분명해집니다. <b>동점이 아닌 라운드</b>에서는 모든 N에서 정답 수가 천장 기대와 같습니다: N=4 {unt["4"]["correct"]} / {unt["4"]["n"]} (기대 {unt["4"]["map_expected"]:.0f}), N=3 {unt["3"]["correct"]} / {unt["3"]["n"]} (기대 {unt["3"]["map_expected"]:.0f}), N=2 {unt["2"]["correct"]} / {unt["2"]["n"]} (기대 {unt["2"]["map_expected"]:.0f}). 천장과 벌어진 곳은 N ≤ 2의 동점 라운드뿐입니다: {tie_ok} / {tie_small} (기대 {tie_exp:.1f}). 동점일 때 행동 순서상 첫째를 고른 비율은 {S["ties"]["first_in_action_order"]} / {S["ties"]["answer_in_tie"]}로, 순서 편향은 보이지 않습니다.</p>

<h4>조작 점검 · 모델과 상관없이 과제가 설계대로 나왔나</h4>
<p>36문제의 기록된 과제 통계(<code>round_start.public.task</code>)를 설계와 맞춰 봅니다. 엔진(<code>~/wt/squid5-e52</code>의 <code>task_stats</code>)으로 다시 계산한 값과 36/36 일치합니다.</p>
{man_tables()}
<ul>
<li><b>N=4는 설계대로입니다.</b> k = 2가 36/36, 풀 10–14가 36/36, 정답 몫과 목표(p 또는 1 − p)의 차는 최대 {max(m4[p]["max_abs_share_err"] for p in PS):.3f}(허용 0.05)입니다. 벗어난 라운드는 없습니다.</li>
<li><b>정답 쪽 뽑기는 9번씩이라 p에서 크게 벗어났습니다.</b> 0.8 수준이 6/9(67%), 0.7 수준이 8/9(89%), 0.6 수준이 4/9(44%)입니다. 뽑기 자체는 정직합니다(확률 p). 하지만 표본이 작아 실현된 천장의 순서가 0.7 &gt; 0.8 &gt; 0.5 &gt; 0.6이 됐습니다. 이 세 시드에서 12라운드 사다리는 단조롭지 않았습니다.</li>
<li><b>N &lt; 4에서는 균등 찍기만 크게 내려갑니다.</b> k 평균이 2 → 2.39 → 3.47 → 3.89로 늘고, 풀이 중앙값 11 → 71 → 349 → 2,227개 함수로 커집니다. 균등 찍기는 50 → 44 → 30 → 26%로 내려가지만, MAP 실현은 63 → 56 → 57 → 50%로 평평합니다. 이것은 <a href="#e53-v14split">비율 일정 절</a>의 한계(천장이 N과 함께 내려가는 것은 p = 0.8 · 0.7뿐)와 같은 결과입니다. 또 N=3에서 정답 쪽이 N=4와 달라진(MAP 정오가 바뀐) 문제가 {MAN["by_n"]["3"]["map_flips_vs_n4"]}개입니다. 동료 하나를 잃으면 천장이 내려가기보다, 라운드마다 <b>정답 쪽이 뒤집히거나 그대로인 운</b>이 됩니다.</li>
</ul>

<h4>참여 수 × 비율 p</h4>
<p>칸 = 실제 정답률 (자리-라운드), 아래에 그 칸의 MAP 실현 · 균등. 다섯 모델 합침. n &lt; 10은 해석 주의입니다.</p>
{np_table("pooled")}
<details class="more"><summary>모델별 N × p 표 다섯 개</summary>{details}</details>

<h4>교란 · N은 무작위로 정해지지 않습니다</h4>
<p>참여 수는 게임이 만듭니다. 누가 꺼지거나 EXIT해야 줄어들기 때문에, N &lt; 4 라운드는 그런 일이 생긴 판(Luna · Opus · Sol 한 판 · Fable 한 판)에서만 나오고, 그 판의 남은 자리는 잔액이 다릅니다. N은 라운드 번호와 p와도 섞입니다.</p>
{conf_table()}
<p>N=3은 오히려 이른 라운드에 몰려 있습니다(Luna s4001이 R1에 한 자리를 잃음). N=2 · 1은 뒤 라운드, 낮은 p입니다. 그래서 N과 p를 함께 넣은 로지스틱 회귀(정답 ~ N + p + 모델, Opus 기준)를 확인용으로 돌렸습니다.</p>
{reg_table()}
<p class="small">N의 계수는 양(에이전트 하나당 오즈 약 2배)이지만, 게임을 군집으로 되뽑으면 구간이 0을 포함하고, 퍼즐을 군집으로 되뽑으면 겨우 0 위입니다. p의 계수는 반대로 게임 군집에서만 0 위입니다. 모델들이 같은 36문제를 풀기 때문에, 독립 단위는 사실상 퍼즐입니다. 천장(MAP 실현)을 공변량으로 넣어도 N 계수가 남지만, 그 몫은 위의 동점 퍼즐 {tie_pz}개에서 나옵니다. p 대신 라운드 번호를 넣어도 N 계수는 비슷합니다({REG["coef_round_instead_of_p"]["N"]:+.2f}). 모델 차이는 모두 구간이 0을 포함합니다. 되뽑기 {REG["boot"]}번, 게임 군집은 모델 안에서 판 3개를 되뽑았습니다.</p>

<div class="callout"><span class="lbl">읽기 · 어디서 설계대로였고 어디서 아니었나</span>
<ol>
<li><b>모델은 셉니다.</b> N=4에서 정답률은 50%(찍기)가 아니라 천장(실현 63%, 설계 기대 p의 평균 65%)에 붙어 있습니다. 동점이 아닌 라운드에서 답이 MAP과 같은 비율이 93–100%입니다. 풀이 10–14개 함수인 한, 다섯 모델 모두 사실상 완벽한 추론기입니다. 그래서 정답률을 정하는 것은 <b>추론 실력이 아니라 정답이 어느 쪽에 놓였는가</b>입니다. 모델 사이의 차이가 보이지 않는 것도 같은 이유입니다.</li>
<li><b>v14f에서 정답률을 움직인 지렛대는 정답 쪽 뽑기입니다.</b> p 자체는 기대를 정할 뿐이고, 수준당 9문제로는 그 기대가 실현되지 않습니다(0.7 수준 89% &gt; 0.8 수준 67%). 같은 36문제를 모든 모델이 풀었으므로 이 운은 모델 사이에 공유됩니다. 모델 비교에는 공정하지만, "난이도 사다리"로는 읽을 수 없습니다.</li>
<li><b>참여 수 효과는 설계상 약하고, 실제 하락은 대부분 천장과 동점 운으로 설명됩니다.</b> 세는 에이전트에게 N이 줄어 생기는 손실은 천장의 작은 하락(36문제에서 −5 ~ −13%p)과 정답 쪽이 뒤집히는 운입니다. 실제 판의 N=3 하락(63 → 41%)은 그 라운드의 천장(42%)으로 설명됩니다. N ≤ 2의 추가 하락은 동점 퍼즐 {tie_pz}개의 운입니다. 풀이 수백~수천 개로 커져도, 동점이 아닌 라운드에서는 모델이 여전히 천장을 맞혔습니다(N=2 7/8). 다만 표본이 작아(N=2에서 동점이 아닌 자리-라운드 8개, 퍼즐 4개), "추론 부담은 정답률을 낮추지 않는다"고 말하기에는 이릅니다.</li>
<li><b>N과 다른 것이 섞입니다.</b> N &lt; 4는 다섯 판 중 일부(Luna · Opus 위주)에서만 나왔고, N=3은 이른 라운드 · 높은 p, N ≤ 2는 뒤 라운드 · 낮은 p입니다. 회귀로 p를 통제해도 N 효과의 구간은 군집 단위에 따라 0을 걸치거나 겨우 넘습니다.</li>
<li><b>의도대로 만들려면 (제안, 결정 아님).</b> (i) 정답 쪽을 판 묶음 단위로 층화합니다. 예를 들어 시드 10개에서 다수 쪽 비율이 정확히 p가 되게 하면 실현 천장이 p를 따릅니다. (ii) 참여 수로 정답률을 움직이려면, 천장 자체가 N과 함께 내려가야 합니다. 곧 N=3 · 2의 정답 몫도 함께 겨냥하는 다중 앞부분 탐색(<a href="#e53-v14split">비율 일정</a>의 남은 대안)이 필요합니다. (iii) 세는 모델에게는 찍기 기준선(1/k)이 의미가 없습니다. 판정은 MAP 실현 대비로 합니다.</li>
</ol></div>
<p class="small">데이터: <code>~/squid5-runs/e52_v14f/*/*/events.jsonl</code>(다섯 모델, 3판씩. Luna · Sol은 s4002가 따로 있는 런 디렉터리). 자리-라운드 {S["rows"]}개(SOLVE를 낸 것만), 문제 36개. 스크립트: <code>e53_build/verify_v14f/verify_accuracy.py</code>(<code>~/wt/squid5-e52</code>에서 실행, 엔진 대조 포함) → <code>agent_rounds.csv</code> · <code>by_n.csv</code> · <code>by_np.csv</code> · <code>puzzles.csv</code> · <code>manipulation.json</code> · <code>regression.json</code> · <code>summary.json</code>. 이 절은 <code>build_section.py</code>가 <code>summary.json</code>에서 만듭니다.</p>
<!-- e53-v14verify:end -->"""


def main() -> None:
    tpl = HERE.parent / "e53_template.html"
    h = tpl.read_text()
    block = section()
    a, b = "<!-- e53-v14verify:start", "<!-- e53-v14verify:end -->"
    if a in h:
        i, j = h.index(a), h.index(b) + len(b)
        h = h[:i] + block + h[j:]
    else:
        k = h.index("<!-- e53-v14diff:end -->") + len("<!-- e53-v14diff:end -->")
        h = h[:k] + "\n\n" + block + h[k:]
    tpl.write_text(h)
    print("section", len(block))


if __name__ == "__main__":
    main()
