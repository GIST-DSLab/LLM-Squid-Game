"""Write the e53-v15grid section (entropy ladder: round x agents-alive grid) into ../e53_template.html.

Input: s16_v15_18_67.json from s16_grid.py (same folder), which calls the engine (~/wt/squid5-e52, puzzle.public_round /
public_truth) with the profiles of configs/squid5/e52v15_public_sol4.yaml for seeds 18-67 x 12 rounds. Each round row
carries, per N = 1..4, the action counts among the functions consistent with the first 4N examples and the action of
the rule drawn for scoring. Usage: python3 build_section.py   then   python3 e53_build/build_e53.py e53_build .
Idempotent: replaces <!-- e53-v15grid:start --> ... <!-- e53-v15grid:end -->, or inserts it after e53-m6grid:end.
"""
import json
import math
import pathlib
import statistics as st

HERE = pathlib.Path(__file__).resolve().parent
TPL = HERE.parent / "e53_template.html"
D = json.load(open(HERE / "s16_v15_18_67.json"))
SPACE = 25996
ACT = ("go_left", "go_right", "stay", "jump")
ACOL = ("var(--accent)", "var(--ok)", "var(--warn)", "var(--s-gpt)")
NS = (4, 3, 2, 1)
EXAMPLE_SEED = 18  # the first seed of the batch, not picked for its look
ROWS = [r for r in D["rows"] if not r["fail"]]


def pc(x):
    return f"{int(x * 100 + 0.5)}%"


def shares(c):
    return [x / c["pool"] for x in c["cn"]]


def eff(c):
    return 2 ** -sum(p * math.log2(p) for p in shares(c) if p)


def map_acc(c):
    top = max(c["cn"])
    return (c["cn"][c["truth"]] == top) / c["cn"].count(top)


def cell(rows, n):
    cs = [r["cells"][str(n)] for r in rows]
    return dict(n=len(cs), tgt=rows[0]["target"][str(n)], eff=st.mean(map(eff, cs)), lo=min(map(eff, cs)),
                hi=max(map(eff, cs)), H=st.mean(math.log2(eff(c)) for c in cs), top=st.mean(max(shares(c)) for c in cs),
                acc=st.mean(map(map_acc, cs)), pool=st.median(c["pool"] for c in cs),
                k=st.mean(sum(x > 0 for x in c["cn"]) for c in cs))


def by_round(r):
    return [x for x in ROWS if x["round"] == r]


def act_bar(c, w=96):
    segs = []
    for j, x in enumerate(c["cn"]):
        if x:
            mark = "outline:2px solid var(--ink);outline-offset:-2px;" if j == c["truth"] else ""
            segs.append(f'<i title="{ACT[j]} {x}" style="display:inline-block;height:11px;width:{x / c["pool"] * w:.1f}px;'
                        f'background:{ACOL[j]};{mark}"></i>')
    return f'<span style="display:inline-flex;gap:1px;vertical-align:middle">{"".join(segs)}</span>'


def heat(v, lo=0.45, hi=0.95):  # expected accuracy -> background: low = warm
    t = max(0, min(1, (v - lo) / (hi - lo)))
    return f"background:color-mix(in srgb, var(--warn) {int((1 - t) * 28)}%, transparent)"


def grid_table():
    head = "".join(f"<th>N={n}<br><span class='small'>공개 {4 * n}장</span></th>" for n in NS)
    body = []
    for r in range(1, 13):
        tds = []
        for n in NS:
            c = cell(by_round(r), n)
            tds.append(f'<td style="{heat(c["top"])}"><b>{c["eff"]:.2f}</b> <span class="small">목표 {c["tgt"]:.2f} · '
                       f'{c["H"]:.2f} bit</span><br>기대 정답률 <b>{pc(c["top"])}</b> <span class="small">· 실측 '
                       f'{pc(c["acc"])}</span><br><span class="small">맞는 규칙 {int(c["pool"]):,}개 · 행동 {c["k"]:.1f}개</span></td>')
        body.append(f"<tr><td>R{r}</td>{''.join(tds)}</tr>")
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def drop_table():
    body = []
    for r in range(1, 13):
        a = {n: cell(by_round(r), n)["top"] for n in NS}
        body.append(f"<tr><td>R{r}</td>" + "".join(f"<td>{(a[4] - a[n]) * 100:+.0f}%p</td>".replace("-", "−") for n in (3, 2, 1))
                    + "</tr>")
    return ('<div class="tbl"><table><thead><tr><th>라운드</th><th>4명 − 3명</th><th>4명 − 2명</th><th>4명 − 1명</th></tr>'
            f'</thead><tbody>{"".join(body)}</tbody></table></div>')


def example_table():
    rows = sorted((r for r in ROWS if r["seed"] == EXAMPLE_SEED), key=lambda r: r["round"])
    head = "".join(f"<th>N={n}<br><span class='small'>공개 {4 * n}장</span></th>" for n in NS)
    body = []
    for r in rows:
        tds = []
        for n in NS:
            c = r["cells"][str(n)]
            parts = " · ".join(f'{"<b>" if j == c["truth"] else ""}{ACT[j]} {x / c["pool"] * 100:.0f}%'
                               f'{"</b>" if j == c["truth"] else ""}' for j, x in
                               sorted(enumerate(c["cn"]), key=lambda t: -t[1]) if x)
            ok = map_acc(c)
            badge = "맞힘" if ok == 1 else "틀림" if ok == 0 else f"동점 {pc(ok)}"
            tds.append(f'<td>{act_bar(c)} <span class="small" style="white-space:nowrap">{badge}</span><br>'
                       f'<span class="small">{parts}<br>2<sup>H</sup> <b>{eff(c):.2f}</b> (목표 {r["target"][str(n)]:.2f}) · '
                       f'맞는 규칙 <b>{c["pool"]:,}</b> / {SPACE:,}</span></td>')
        body.append(f'<tr><td>R{r["round"]}</td>{"".join(tds)}</tr>')
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def section():
    worst = max(abs(eff(r["cells"][str(n)]) - r["target"][str(n)]) for r in ROWS for n in NS)
    mono = sum(all(max(shares(r["cells"][str(a)])) >= max(shares(r["cells"][str(b)])) - 1e-12
                   for a, b in ((4, 3), (3, 2), (2, 1))) for r in ROWS)
    floor = min(max(shares(r["cells"][str(n)])) for r in ROWS for n in NS)
    fails = sum(r["fail"] for r in D["rows"])
    times = sorted(r["time"] for r in ROWS)
    allN = {n: (st.mean(max(shares(r["cells"][str(n)])) for r in ROWS), st.mean(map_acc(r["cells"][str(n)]) for r in ROWS))
            for n in NS}
    first, last = cell(by_round(1), 4), cell(by_round(12), 4)
    first1, last1 = cell(by_round(1), 1), cell(by_round(12), 1)
    tops4 = [cell(by_round(r), 4)["top"] for r in range(1, 13)]
    ups = [r + 1 for r in range(1, 12) if tops4[r] > tops4[r - 1] + 0.02]
    gen_same = sum(r["cells"][str(4)]["truth"] == r["gen_truth"] for r in ROWS)
    ladder = "".join(f"<tr><td>R{r}</td>" + "".join(f"<td>{by_round(r)[0]['target'][str(n)]:.2f}</td>" for n in NS) + "</tr>"
                     for r in (1, 4, 8, 12))
    return f"""<!-- e53-v15grid:start (generated by e53_build/v15_grid/build_section.py) -->
<h3 id="e53-v15grid">엔트로피 사다리 · 라운드 × 남은 인원 표 (v15, 10-13)</h3>
<p><b>결정 (연구자, 10-13 15:04).</b> 난이도를 <b>네 행동 분포의 엔트로피</b>로 조절합니다. 다빈치 코드처럼, 어려운 상황은 정보가 부족해 무엇을 맞혀야 하는지 모르는 상황입니다. 축은 엔트로피 H(bit)와 2<sup>H</sup>(유효 선택지 수: 1이면 답이 정해져 있고 4면 네 행동이 똑같이 그럴듯함)입니다. 채점도 그 분포를 따릅니다. 라운드가 시작될 때, 답을 받기 전에, 공개된 예시와 맞는 규칙 중 하나를 무작위로 뽑아 그 규칙의 행동을 정답으로 삼습니다. 마지막 라운드도 [.25, .25, .25, .25]는 되지 않게 합니다. 그러면 찍기와 추론이 같아지기 때문입니다.</p>

<div class="bluf"><span class="lbl">요약 · 판정</span>
<ul style="margin:0">
<li><b>목표대로 나왔습니다.</b> 50판 × 12라운드 × 4칸, {len(ROWS) * 4:,}칸 모두 2<sup>H</sup>가 목표의 ±{worst:.2f} 안입니다. 가장 어려운 칸(R12 · 1명)도 2<sup>H</sup> {last1["eff"]:.2f}({last1["H"]:.2f} bit)로 균등(4.00, 2 bit)과 떨어져 있고, 모든 칸에서 1등 몫이 {pc(floor)} 이상입니다.</li>
<li><b>뒤 라운드일수록 틀릴 확률이 오릅니다(평균으로).</b> 똑똑한 추론기의 기대 정답률은 4명일 때 R1 {pc(first["top"])} → R12 {pc(last["top"])}, 1명일 때 R1 {pc(first1["top"])} → R12 {pc(last1["top"])}입니다. 다만 한 라운드씩 보면 꼭 단조롭지 않습니다(4명 열에서 앞 라운드보다 2%p 넘게 오른 곳: {", ".join(f"R{x}" for x in ups) or "없음"}). 엔트로피가 같아도 분포 모양에 따라 1등 몫이 다르기 때문입니다(아래 "읽기" 1).</li>
<li><b>사람이 줄면 어려워집니다.</b> 전체 기대 정답률은 N=4 {pc(allN[4][0])} → N=3 {pc(allN[3][0])} → N=2 {pc(allN[2][0])} → N=1 {pc(allN[1][0])}입니다. 한 판 안에서 한 명이 빠질 때 1등 몫이 오르지 않는 조건을 걸었고, {mono}/{len(ROWS)}라운드 모두 지켜졌습니다.</li>
<li><b>채점이 정직합니다.</b> 뽑힌 정답으로 잰 실제 정답률(N=4 {pc(allN[4][1])}, N=1 {pc(allN[1][1])})이 기대 정답률과 맞습니다. 정답이 맞는 규칙들의 몫대로 뽑히기 때문입니다.</li>
<li><b>생성.</b> 실패 {fails}/{len(D["rows"])}라운드, 준비 시간 중앙값 {st.median(times):.1f}초 · 최대 {times[-1]:.0f}초입니다.</li>
</ul></div>

<h4>무엇을 바꾸었나 (엔진 <code>exp/e52-v9-talk</code>, 로컬 커밋)</h4>
<ol>
<li><b>문제 고르기 (<code>puzzle.select_eff</code>).</b> 규칙과 질문은 지금처럼 뽑습니다. 예시 16장은 4장씩 쌓습니다. 앞 4N장을 보면 질문에 대한 네 행동의 몫(맞는 규칙 중 그 행동을 고르는 비율)의 2<sup>H</sup>가 목표 ±0.08 안에 들어오게 고릅니다. 조건 두 개를 더 겁니다. 모든 칸에서 1등 몫 ≥ 0.40, 그리고 한 명이 빠질 때 1등 몫이 오르지 않습니다. 16장 안에 행동마다 2장 이상을 보여 주는 것은 v14g와 같습니다. 맞는 규칙 수 범위(10–14)와 정답 등수 추첨은 없앴습니다.</li>
<li><b>채점 (<code>puzzle.public_truth</code>).</b> 라운드 시작 때, 그 라운드에 참여한 N명이 보는 예시와 맞는 규칙들 중 하나를 (시드, 라운드, N)으로 뽑습니다. 그 규칙이 질문에 내놓는 행동이 정답입니다. 답과 무관하게 미리 정해지므로, "숨은 규칙이 하나 있고 예시는 그 규칙을 따른다"는 규칙서 문장은 그대로 참입니다. 기록에는 <code>rule</code>(뽑힌 규칙)과 <code>generator_rule</code>(예시를 만든 규칙)이 함께 남습니다.</li>
<li><b>사다리 (<code>configs/squid5/e52v15_public_sol4.yaml</code>).</b> 라운드마다 프로필 하나(e01–e12). 4명 열은 R1 1.30에서 R12 2.10까지 고르게 오르고, 한 명이 빠질 때마다 +0.30입니다. 그래서 가장 어려운 칸(R12 · 1명)이 3.00입니다. 처음에는 끝을 2.20(가장 어려운 칸 3.10)으로 잡았는데, 600라운드 중 6라운드(R11 · R12)가 목표와 두 조건을 한꺼번에 맞추지 못해 0.10 내렸습니다. 또 50번 다시 뽑는 중 마지막 10번은 허용 오차를 0.16으로 넓혀, 어떤 라운드도 판을 멈추지 않게 했습니다.
<div class="tbl"><table><thead><tr><th>2<sup>H</sup> 목표</th>{"".join(f"<th>N={n}</th>" for n in NS)}</tr></thead><tbody>{ladder}</tbody></table></div></li>
<li><b>그대로인 것.</b> 모델이 읽는 문장, 경제(벌금 2,000 · 맞으면 환급 · 상금), 대화 규칙은 v14g와 같습니다. 엔진 코드 4,616 → 4,724줄, 테스트 101개 통과. 모델 런과 웹 아레나 전환은 아직 하지 않았습니다.</li>
</ol>

<h4>표 1 · 라운드 × 남은 인원 · 50판 평균</h4>
<p>칸 첫 줄 = 2<sup>H</sup> 평균(굵게)과 목표, 엔트로피(bit). 둘째 줄 = <b>기대 정답률</b>(1등 행동의 평균 몫: 맞는 규칙을 모두 세고 가장 많은 쪽을 답하는 추론기가 맞힐 확률)과 <b>실측</b>(실제로 뽑힌 정답으로 잰 그 추론기의 정답률, 라운드당 50문제라 ±7%p 정도 흔들림). 셋째 줄 = 맞는 규칙 수의 중앙값(전체 {SPACE:,}개 중)과, 하나라도 규칙이 남은 행동 수의 평균. 칸 색이 진할수록 기대 정답률이 낮습니다.</p>
{grid_table()}
<details class="more"><summary>한 명이 빠질 때 기대 정답률이 얼마나 떨어지나</summary>
{drop_table()}
</details>

<h4>표 2 · 한 판을 미리 만든 모습 (시드 {EXAMPLE_SEED})</h4>
<p>실제로 판에 넣을 데이터입니다. 막대는 맞는 규칙들이 고르는 네 행동의 비율이고, 테두리가 있는 조각이 그 칸에서 뽑힌 정답입니다. 정답은 칸마다(N마다) 따로 뽑히므로, 같은 라운드라도 인원에 따라 정답이 다를 수 있습니다. 실제 판에서는 그 라운드에 참여한 인원의 칸 하나만 쓰입니다. "맞힘 / 틀림"은 1등 행동을 고른 추론기의 결과입니다. 시드 {EXAMPLE_SEED}는 배치의 첫 시드이고, 보기 좋은 판을 고른 것이 아닙니다.</p>
<div class="e50-legend">{"".join(f'<span><i style="background:{c}"></i>{a}</span>' for a, c in zip(ACT, ACOL))}<span><i style="background:transparent;outline:2px solid var(--ink);outline-offset:-2px"></i>뽑힌 정답</span></div>
{example_table()}

<div class="callout"><span class="lbl">읽기</span>
<ol>
<li><b>엔트로피와 정답 확률은 같은 축이 아닙니다.</b> 2<sup>H</sup>가 같아도 [.75, .08, .08, .08]처럼 꼬리가 긴 분포는 1등 몫이 높고, [.5, .5]처럼 둘로 갈린 분포는 낮습니다. 두 갈래 분포의 2<sup>H</sup>는 2를 넘을 수 없어서, 목표가 2 근처(4명 R10–11)이면 거의 반반 [.5, .5]이 되고, 2를 넘는 R12(2.10)는 세 갈래가 되면서 [.75, .125, .125]처럼 1등 몫이 다시 높아질 수 있습니다. 그래서 라운드가 갈수록 평균 정답률은 내려가지만 라운드 하나하나는 들쭉날쭉합니다. 이 판은 맞음 / 틀림으로 채점하므로, 에이전트의 기대 손익을 정하는 것은 1등 몫입니다. 둘을 함께 맞추려면 1등 몫에 라운드별 범위를 하나 더 걸면 됩니다(생성 실패가 늘어남).</li>
<li><b>한 명당 차이가 M6보다 작습니다.</b> 2<sup>H</sup> +0.30이 기대 정답률 약 {(allN[4][0] - allN[1][0]) / 3 * 100:.0f}%p입니다(M6는 약 13%p). 동료의 정보 가치(H4 가설)를 키우려면 이 간격을 0.4–0.5로 넓히면 됩니다. 사다리 숫자 하나만 바꾸면 됩니다.</li>
<li><b>뽑힌 정답은 예시를 만든 규칙과 다를 수 있습니다.</b> 4명 칸에서 둘이 같은 행동인 라운드는 {gen_same}/{len(ROWS)}입니다. 예시는 처음 규칙으로 만들고, 정답은 그 예시와 맞는 모든 규칙 중에서 다시 뽑기 때문입니다. 두 규칙 모두 공개된 예시를 전부 따릅니다.</li>
<li><b>모든 수치는 균등하게 세는 추론기 기준입니다.</b> 이번 채점은 정답을 바로 그 균등 분포에서 뽑으므로, 이 기대 정답률은 근사가 아니라 정확한 값입니다. 다만 모델이 그 공간({SPACE:,}개, 같은 함수는 하나로 셈)을 모르고 단순한 규칙을 더 믿는다면, 모델에게 체감되는 난이도는 다릅니다.</li>
</ol></div>
<div class="callout"><span class="lbl">남는 일</span>
<ol style="margin:0">
<li><b>정답 확률도 라운드마다 내려가게 할지.</b> 지금은 엔트로피만 사다리를 따릅니다. 4명 열의 R12처럼 기대 정답률이 앞 라운드보다 오르는 곳을 없애려면 1등 몫에 라운드별 상한을 하나 더 겁니다. 이는 "난이도 = 엔트로피"에 "손익 = 1등 몫"을 더하는 결정이라 연구자 확인이 필요합니다.</li>
<li><b>경제.</b> 뒤 라운드는 4명이어도 기대 정답률이 70% 안팎이고 1명이면 50% 안팎입니다. 틀리면 벌금 2,000이라, PASS 허용이나 벌금 조정은 따로 정해야 합니다.</li>
<li><b>모델 확인.</b> 실제 모델 한 판(스모크)으로 정답률이 기대 정답률을 따라오는지 봐야 합니다.</li>
</ol></div>
<p class="small">데이터: <code>e53_build/v15_grid/s16_grid.py</code>(엔진 호출) → <code>s16_v15_18_67.json</code>. LLM 호출 없이 계산만 했습니다.</p>
<!-- e53-v15grid:end -->"""


if __name__ == "__main__":
    h = TPL.read_text()
    block = section()
    s, e = "<!-- e53-v15grid:start", "<!-- e53-v15grid:end -->"
    if s in h:
        i, j = h.index(s), h.index(e) + len(e)
        h = h[:i] + block + h[j:]
    else:
        k = h.index("<!-- e53-m6grid:end -->") + len("<!-- e53-m6grid:end -->")
        h = h[:k] + "\n\n" + block + h[k:]
    TPL.write_text(h)
    print("ok", len(block))
