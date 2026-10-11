"""Write the e53-m6grid section (pre-generated game: round x agents-alive grid) into ../e53_template.html.

Input: s15_v14g_18_67.json and s15_M6_18_67.json from s15_grid.py (run in ~/squid5-runs/difficulty_v2_2026-10-11,
which holds the engine copy and the M6 selector msel.py). Each round row carries, per N = 1..4, the action counts
among the hypotheses consistent with the first 4N public examples, and the hypothesis-space size.
Usage: python3 build_section.py   then   python3 e53_build/build_e53.py e53_build .   (from the report folder).
Idempotent: replaces <!-- e53-m6grid:start --> ... <!-- e53-m6grid:end -->, or inserts it after e53-v14verify:end.
"""
import json
import pathlib
import statistics as st

HERE = pathlib.Path(__file__).resolve().parent
TPL = HERE.parent / "e53_template.html"
DATA = {m: json.load(open(HERE / f"s15_{m}_18_67.json")) for m in ("v14g", "M6")}
SPACE = DATA["M6"]["space"]
ACT = ("go_left", "go_right", "stay", "jump")
ACOL = ("var(--accent)", "var(--ok)", "var(--warn)", "var(--s-gpt)")
NS = (4, 3, 2, 1)
EXAMPLE_SEED = 18  # the first seed of the batch, not picked for its look
LEVELS = ((1, 3), (4, 6), (7, 9), (10, 12))
TARGET = {"M6": {0: {4: .80, 3: .65, 2: .50}, 1: {4: .75, 3: .60, 2: .45}, 2: {4: .65, 3: .50, 2: .40},
                 3: {4: .55, 3: .45, 2: .35}},
          "v14g": {0: {4: .8}, 1: {4: .7}, 2: {4: .6}, 3: {4: .5}}}


def pc(x):
    return "—" if x is None else f"{int(x * 100 + 0.5)}%"


def map_acc(cn, tr):
    top = max(cn)
    return (cn[tr] == top) / cn.count(top)


def cell_stats(rows, n):
    cs = [r["cells"][str(n)] for r in rows]
    trs = [r["truth"] for r in rows]
    ranked = [sorted((x / c["pool"] for x in c["cn"]), reverse=True) for c in cs]
    return dict(n=len(rows), acc=st.mean(map_acc(c["cn"], t) for c, t in zip(cs, trs)),
                tshare=st.mean(c["cn"][t] / c["pool"] for c, t in zip(cs, trs)),
                ranked=[st.mean(r[j] for r in ranked) for j in range(4)],
                k=st.mean(sum(x > 0 for x in c["cn"]) for c in cs),
                pool=st.median(c["pool"] for c in cs))


def rows_of(mode, lo, hi):
    return [r for r in DATA[mode]["rows"] if not r["fail"] and lo <= r["round"] <= hi]


def rank_bar(ranked, w=120):
    segs = "".join(f'<i style="display:inline-block;height:9px;width:{v * w:.1f}px;background:var(--accent);'
                   f'opacity:{1 - .25 * j:.2f}"></i>' for j, v in enumerate(ranked) if v > 0.004)
    return f'<span style="display:inline-flex;gap:1px;vertical-align:middle">{segs}</span>'


def act_bar(cn, tr, w=96):
    tot = sum(cn)
    segs = []
    for j, x in enumerate(cn):
        if not x:
            continue
        mark = "outline:2px solid var(--ink);outline-offset:-2px;" if j == tr else ""
        segs.append(f'<i title="{ACT[j]} {x}" style="display:inline-block;height:11px;width:{x / tot * w:.1f}px;'
                    f'background:{ACOL[j]};{mark}"></i>')
    return f'<span style="display:inline-flex;gap:1px;vertical-align:middle">{"".join(segs)}</span>'


def fmt_n(x):
    return f"{x:,}"


# ---- aggregate: level x N ----
def level_table():
    head = "".join(f"<th>N={n}</th>" for n in NS)
    body = []
    for li, (lo, hi) in enumerate(LEVELS):
        tds = []
        for n in NS:
            m6, old = cell_stats(rows_of("M6", lo, hi), n), cell_stats(rows_of("v14g", lo, hi), n)
            tg = TARGET["M6"][li].get(n)
            tg_old = TARGET["v14g"][li].get(n)
            tds.append(f'<td><b>{pc(m6["acc"])}</b> <span class="small">목표 {pc(tg) if tg else "없음"}</span><br>'
                       f'<span class="small">지금(v14g) {pc(old["acc"])}'
                       f'{" · 목표 " + pc(tg_old) if tg_old else ""}</span></td>')
        body.append(f"<tr><td>R{lo}–{hi}</td>{''.join(tds)}</tr>")
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def drop_table():
    body = []
    for li, (lo, hi) in enumerate(LEVELS):
        tds = []
        for mode in ("M6", "v14g"):
            a = {n: cell_stats(rows_of(mode, lo, hi), n)["acc"] for n in NS}
            tds.append(f"<td>{(a[4] - a[3]) * 100:+.0f}%p</td><td>{(a[4] - a[2]) * 100:+.0f}%p</td>".replace("-", "−"))
        body.append(f"<tr><td>R{lo}–{hi}</td>{''.join(tds)}</tr>")
    return ('<div class="tbl"><table><thead><tr><th rowspan="2">라운드</th><th colspan="2">M6 (제안)</th>'
            '<th colspan="2">지금 (v14g)</th></tr><tr><th>4명 − 3명</th><th>4명 − 2명</th><th>4명 − 3명</th>'
            f'<th>4명 − 2명</th></tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def round_table(mode):
    head = "".join(f"<th>N={n}</th>" for n in NS)
    body = []
    for r in range(1, 13):
        rows = rows_of(mode, r, r)
        li = (r - 1) // 3
        tds = []
        for n in NS:
            c = cell_stats(rows, n)
            tg = TARGET[mode][li].get(n)
            tds.append(f'<td><b>{pc(c["acc"])}</b>{" <span class=small>(" + pc(tg) + ")</span>" if tg else ""}<br>'
                       f'{rank_bar(c["ranked"])}<br><span class="small">'
                       f'{" / ".join(str(int(v * 100 + .5)) for v in c["ranked"])} · k {c["k"]:.1f}<br>'
                       f'맞는 규칙 {fmt_n(int(c["pool"]))}개 ({c["pool"] / SPACE * 100:.2g}%)</span></td>')
        body.append(f"<tr><td>R{r}</td>{''.join(tds)}</tr>")
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def example_table(mode):
    rows = sorted((r for r in DATA[mode]["rows"] if r["seed"] == EXAMPLE_SEED), key=lambda r: r["round"])
    head = "".join(f"<th>N={n}<br><span class='small'>공개 {4 * n}장</span></th>" for n in NS)
    body = []
    for r in rows:
        tds = []
        for n in NS:
            c = r["cells"][str(n)]
            tot = c["pool"]
            parts = " · ".join(f'{"<b>" if j == r["truth"] else ""}{ACT[j]} {x / tot * 100:.0f}%'
                               f'{"</b>" if j == r["truth"] else ""}' for j, x in
                               sorted(enumerate(c["cn"]), key=lambda t: -t[1]) if x)
            ok = map_acc(c["cn"], r["truth"])
            badge = "맞힘" if ok == 1 else "틀림" if ok == 0 else f"동점 {pc(ok)}"
            tds.append(f'<td>{act_bar(c["cn"], r["truth"])} <span class="small" style="white-space:nowrap">{badge}</span><br>'
                       f'<span class="small">{parts}<br>맞는 규칙 <b>{fmt_n(tot)}</b> / {fmt_n(SPACE)}'
                       f' ({tot / SPACE * 100:.2g}%)</span></td>')
        body.append(f'<tr><td>R{r["round"]}<br><span class="small">정답 {ACT[r["truth"]]}</span></td>'
                    f"{''.join(tds)}</tr>")
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def checks():
    """Numbers quoted in the text: N=4 top share vs target, honesty (acc vs target), monotone share of levels."""
    out = {}
    for li, (lo, hi) in enumerate(LEVELS):
        for n in (4, 3, 2):
            c = cell_stats(rows_of("M6", lo, hi), n)
            out[(li, n)] = (c["acc"], c["ranked"][0], TARGET["M6"][li][n])
    mono = {m: 0 for m in DATA}
    games = {m: 0 for m in DATA}
    for m in DATA:
        for r in DATA[m]["rows"]:
            if r["fail"]:
                continue
            cn = {n: r["cells"][str(n)] for n in NS}
            games[m] += 1
            sh = [cn[n]["cn"][r["truth"]] / cn[n]["pool"] for n in (4, 3, 2)]
            mono[m] += sh[0] >= sh[1] >= sh[2]
    return out, mono, games


def section():
    ck, mono, games = checks()
    worst = max(abs(a - t) for a, _, t in ck.values())
    worst_top = max(abs(tp - t) for _, tp, t in ck.values())
    fails = {m: sum(r["fail"] for r in DATA[m]["rows"]) for m in DATA}
    times = sorted(r["time"] for r in DATA["M6"]["rows"] if not r["fail"])
    m6_all = {n: cell_stats(rows_of("M6", 1, 12), n) for n in NS}
    old_all = {n: cell_stats(rows_of("v14g", 1, 12), n) for n in NS}
    return f"""<!-- e53-m6grid:start (generated by e53_build/m6_grid/build_section.py) -->
<h3 id="e53-m6grid">미리 만든 판 · 라운드 × 남은 인원 표 (M6 제안, 10-11)</h3>
<p><b>질문.</b> 판을 시작하기 전에 12라운드 문제와 공개 예시 16장의 순서를 미리 만들어 둡니다. 살아 있는 에이전트가 N명이면 앞에서부터 4N장이 공개됩니다. 그러면 <b>라운드 × 남은 인원</b> 칸마다, 똑똑한 추론기가 볼 수 있는 정보가 정해집니다. 이 추론기는 공개된 예시와 맞는 규칙을 가설 공간({fmt_n(SPACE)}개 규칙)에서 모두 세고, 네 행동이 각각 몇 개 규칙에서 나오는지 봅니다. 그 비율이 행동마다의 정답 확률입니다. 우리가 의도한 두 사다리가 이 표에 실제로 나타나는지 확인합니다. 첫째는 라운드가 갈수록 어려워지는 것이고, 둘째는 사람이 줄수록 어려워지는 것입니다.</p>

<div class="bluf"><span class="lbl">요약 · 판정</span>
<ul style="margin:0">
<li><b>지금(v14g)은 라운드 사다리만 있습니다.</b> 16장을 N=4에 맞춰 고르고, 3명 · 2명은 그 목록의 앞 12장 · 8장을 그대로 씁니다. 앞부분이 어떤 정보를 담을지는 아무도 고르지 않았습니다. 그래서 정답률이 N=4 {pc(old_all[4]["acc"])} → N=3 {pc(old_all[3]["acc"])} → N=2 {pc(old_all[2]["acc"])} → N=1 {pc(old_all[1]["acc"])}로 한 명당 약 6%p씩 완만하게 내려갑니다. 라운드 묶음마다 보면 들쭉날쭉합니다. R10–12는 3명일 때가 4명일 때보다 높고(58% 대 50%), R7–9는 2명일 때가 3명일 때보다 높습니다(60% 대 59%). 또 3명일 때 1등 몫은 평균 {pc(old_all[3]["ranked"][0])}인데 실제 정답률은 {pc(old_all[3]["acc"])}입니다. 정답 등수를 N=4에서만 정해서, N=3의 몫이 실제보다 높게 보입니다.</li>
<li><b>M6는 같은 16장의 순서를 고릅니다.</b> 앞 8장(2명)과 앞 12장(3명)이 각각 목표 몫에 맞게 순서를 정합니다. 라운드 사다리는 N=4 열에 그대로 남고, N=3 · N=2 열에 사다리가 하나씩 더 생깁니다. 전체 정답률은 N=4 {pc(m6_all[4]["acc"])} → N=3 {pc(m6_all[3]["acc"])} → N=2 {pc(m6_all[2]["acc"])} → N=1 {pc(m6_all[1]["acc"])}입니다.</li>
<li><b>목표대로 나왔습니다.</b> 12칸(라운드 묶음 4 × N=4 · 3 · 2) 모두에서 실제 정답률과 목표의 차가 최대 {worst * 100:.0f}%p, 1등 행동의 평균 몫과 목표의 차가 최대 {worst_top * 100:.0f}%p입니다(묶음당 150문제). 정답 행동의 몫이 4명 ≥ 3명 ≥ 2명 순으로 줄어드는 문제는 M6 {mono["M6"]}/{games["M6"]}, 지금 {mono["v14g"]}/{games["v14g"]}입니다. 생성 실패는 M6 {fails["M6"]}건, 라운드 준비 시간은 중앙값 {st.median(times):.1f}초 · 최대 {times[-1]:.0f}초입니다.</li>
</ul></div>

<h4>무엇을 미리 정하나</h4>
<ol>
<li><b>규칙과 질문.</b> 라운드마다 숨은 규칙 하나와 질문 신호 하나를 뽑습니다(지금과 같습니다).</li>
<li><b>16장 묶음.</b> 지금 선택기 그대로, 16장을 다 보면 맞는 규칙이 10–14개 남고 답이 두 행동으로 갈리게 고릅니다. 갈리는 비율이 라운드 사다리(N=4 목표)입니다.</li>
<li><b>순서 (새로 하는 일).</b> 같은 16장 안에서 "마지막 4장"과 "그 앞 4장"을 고릅니다. 앞 12장만 볼 때와 앞 8장만 볼 때 1등 · 2등 행동의 몫이 목표에 맞는 배치를 찾습니다. 카드는 하나도 바뀌지 않습니다.</li>
<li><b>정답의 등수 (정직성).</b> 라운드 시작 때 수 하나(u)를 뽑아 정답이 각 수준에서 1등인지 2등인지 정합니다. 예를 들어 N=4 목표가 80%면, 100라운드 중 약 80라운드에서 정답이 1등 쪽에 놓입니다. 세 수준이 같은 u를 쓰므로 서로 모순되지 않습니다. 3라운드 묶음 안에서는 u를 고르게 나눠 운의 몫을 줄입니다.</li>
<li><b>보여 줄 때는 섞습니다.</b> 어떤 카드가 공개되는지는 순서로 정하지만, 화면에는 섞은 순서로 나옵니다.</li>
</ol>

<h4>표 1 · 라운드 묶음 × 남은 인원 · 똑똑한 추론기의 정답률 (50판)</h4>
<p>칸 = 맞는 규칙을 모두 세고 가장 많은 쪽 행동을 답할 때 맞히는 비율입니다(동점이면 나눠 셈). 굵은 값이 M6, 아래가 지금(v14g)입니다. 같은 시드 18–67 · 12라운드 = 묶음당 150문제입니다. M6의 N=4 사다리는 0.80/0.75/0.65/0.55입니다(지금은 0.8/0.7/0.6/0.5. 0.5는 완벽한 추론기에게도 동전이라 올렸습니다). N=1은 겨냥하지 않습니다.</p>
{level_table()}
<p class="small">한 명이 빠질 때 정답률이 얼마나 떨어지나 (같은 표에서 계산):</p>
{drop_table()}

<h4>표 2 · 한 판을 미리 만든 모습 (시드 {EXAMPLE_SEED}, M6)</h4>
<p>실제로 판에 넣을 데이터입니다. 칸마다 막대는 맞는 규칙들이 고르는 네 행동의 비율입니다. 테두리가 있는 조각이 정답 행동입니다. 아래 글자는 행동별 확률(굵게 = 정답)과, 전체 {fmt_n(SPACE)}개 규칙 중 공개 예시와 맞는 규칙의 수입니다. "맞힘 / 틀림"은 똑똑한 추론기가 1등 행동을 골랐을 때의 결과입니다. 시드 {EXAMPLE_SEED}는 배치의 첫 시드이고, 보기 좋은 판을 고른 것이 아닙니다.</p>
<div class="e50-legend">{"".join(f'<span><i style="background:{c}"></i>{a}</span>' for a, c in zip(ACT, ACOL))}<span><i style="background:transparent;outline:2px solid var(--ink);outline-offset:-2px"></i>정답 행동</span></div>
{example_table("M6")}
<details class="more"><summary>같은 시드 {EXAMPLE_SEED}를 지금(v14g) 방식으로 만든 모습</summary>
<p class="small">문제는 시드 · 라운드 · 난이도 설정으로 정해집니다. M6는 N=4 사다리 값이 다르고(0.75 · 0.65 · 0.55), 정답 등수에 맞는 순서가 없으면 문제를 다시 뽑습니다. 그래서 같은 질문 신호로 시작한 라운드는 600개 중 287개뿐입니다. 이 표는 문제끼리의 대조가 아니라 방식끼리의 대조로 읽어야 합니다.</p>
{example_table("v14g")}
</details>

<h4>표 3 · 라운드별 × 남은 인원 · 50판 평균 (M6)</h4>
<p>칸 첫 줄 = 똑똑한 추론기의 정답률(괄호 = 목표). 막대와 그 아래 숫자 = 1등 / 2등 / 3등 / 4등 행동이 차지하는 평균 몫(%). k = 맞는 규칙이 하나라도 고르는 행동 수의 평균. 마지막 줄 = 맞는 규칙 수의 중앙값과 전체 가설 공간 대비 비율. 라운드당 50문제라 칸 하나의 정답률은 ±14%p 정도 흔들립니다. 판정은 표 1(묶음당 150문제)로 합니다.</p>
{round_table("M6")}
<details class="more"><summary>같은 표 · 지금(v14g)</summary>
{round_table("v14g")}
</details>

<div class="callout"><span class="lbl">읽기</span>
<ol>
<li><b>몫과 정답률은 다릅니다.</b> "1등 몫 80%"는 맞는 규칙의 80%가 그 행동을 고른다는 뜻입니다. 정답이 실제로 1등 쪽에 놓이는 비율도 80%가 되도록 등수를 뽑기 때문에, 추론기의 정답률이 몫과 같아집니다. 이 둘이 같다는 것이 "설계가 정직하다"는 뜻입니다. 등수를 뽑지 않고 늘 정답을 1등에 두면 정답률이 100%가 되고, 몫은 거짓 정보가 됩니다.</li>
<li><b>맞는 규칙 수는 N=4에서 일정하고 N이 줄면 커집니다.</b> 16장을 다 보면 어느 라운드든 10–14개입니다. 난이도는 규칙 수가 아니라 그 규칙들이 어떻게 갈리느냐(몫)로 조절합니다. N=2 · 1에서는 맞는 규칙이 수십~수천 개라, 세지 못하는 모델에게는 더 어렵습니다. 하지만 이 표는 완벽하게 세는 추론기 기준입니다.</li>
<li><b>남는 일.</b> M6를 쓰면 뒤 라운드는 4명이어도 정답률이 50%대입니다. 지금 경제(틀리면 벌금 2,000, 답 비용은 맞을 때만 환급)에서는 R7 이후 답할수록 기대 손해가 날 수 있습니다. PASS 또는 상금 · 벌금 조정은 따로 정해야 합니다. 규칙 문장은 바꾸지 않습니다("The system chooses which signals are shown").</li>
</ol></div>
<p class="small">데이터: <code>~/squid5-runs/difficulty_v2_2026-10-11/</code>(엔진 <code>puzzle.py</code> 사본 · 선택기 <code>msel.py</code> · <code>s15_grid.py</code>) → <code>e53_build/m6_grid/s15_v14g_18_67.json</code> · <code>s15_M6_18_67.json</code>. LLM 호출 없이 계산만 했고, 엔진 코드는 아직 바꾸지 않았습니다.</p>
<!-- e53-m6grid:end -->"""


if __name__ == "__main__":
    h = TPL.read_text()
    block = section()
    s, e = "<!-- e53-m6grid:start", "<!-- e53-m6grid:end -->"
    if s in h:
        i, j = h.index(s), h.index(e) + len(e)
        h = h[:i] + block + h[j:]
    else:
        k = h.index("<!-- e53-v14verify:end -->") + len("<!-- e53-v14verify:end -->")
        h = h[:k] + "\n\n" + block + h[k:]
    TPL.write_text(h)
    print("ok", len(block))
