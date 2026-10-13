"""Write the e53-v15grid section (entropy ladder: round x agents-alive grid) into ../e53_template.html.

Input: s16_v15_18_67.json from s16_grid.py (same folder), which calls the engine (~/wt/squid5-e52, puzzle.public_round /
public_truth) with the profiles of configs/squid5/e52v15_public_sol4.yaml for seeds 18-67 x 12 rounds. Each round row
carries, per N = 1..4, the action counts among the functions consistent with the first 4N examples and the action of
the rule drawn for scoring. Usage: python3 build_section.py   then   python3 e53_build/build_e53.py e53_build .
Idempotent: replaces <!-- e53-v15grid:start --> ... <!-- e53-v15grid:end -->, or inserts it after e53-m6grid:end.
"""
import html
import json
import math
import pathlib
import statistics as st

HERE = pathlib.Path(__file__).resolve().parent
TPL = HERE.parent / "e53_template.html"
D = json.load(open(HERE / "s16_v15_18_67.json"))
FB = json.load(open(HERE / "feedback_example.json"))  # one real wrong-answer feedback line (seed 18), from the engine
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


def ent(c):
    return -sum(p * math.log2(p) for p in shares(c) if p)


def eff(c):
    return 2 ** ent(c)


def map_acc(c):
    top = max(c["cn"])
    return (c["cn"][c["truth"]] == top) / c["cn"].count(top)


def cell(rows, n):
    cs = [r["cells"][str(n)] for r in rows]
    return dict(n=len(cs), band=rows[0]["target"][str(n)], eff=st.mean(map(eff, cs)), lo=min(map(ent, cs)),
                hi=max(map(ent, cs)), H=st.mean(map(ent, cs)), top=st.mean(max(shares(c)) for c in cs),
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
            tds.append(f'<td style="{heat(c["top"])}"><b>{c["H"]:.2f} bit</b> <span class="small">범위 {c["band"][0]:.2f}–'
                       f'{c["band"][1]:.2f} · 2<sup>H</sup> {c["eff"]:.2f}</span><br>기대 정답률 <b>{pc(c["top"])}</b> <span class="small">· 실측 '
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
                       f'<span class="small">{parts}<br>H <b>{ent(c):.2f}</b> bit (범위 {r["target"][str(n)][0]:.2f}–{r["target"][str(n)][1]:.2f}) · '
                       f'맞는 규칙 <b>{c["pool"]:,}</b> / {SPACE:,}</span></td>')
        body.append(f'<tr><td>R{r["round"]}</td>{"".join(tds)}</tr>')
    return (f'<div class="tbl"><table><thead><tr><th>라운드</th>{head}</tr></thead><tbody>{"".join(body)}'
            f"</tbody></table></div>")


def davinci():
    """Da Vinci Code: guess a hidden tile; uncertainty = difficulty. Counts are exact (tiles 0-11 of one colour)."""
    cases = [
        ("상대 줄: <code>5 · ? · 7</code>", "6 하나", [("6", 1)], "정보가 다 있습니다. 반드시 맞힙니다."),
        ("상대 줄: <code>2 · ? · 7</code>, 4와 5는 이미 공개", "3 · 6", [("3", 1), ("6", 1)], "반반입니다."),
        ("상대 줄: <code>2 · ? · ? · 7</code>, 첫째 ?를 맞히기", "(3,4) (3,5) (3,6) (4,5) (4,6) (5,6)",
         [("3", 3), ("4", 2), ("5", 1)], "가능한 배치 6가지를 세면 3이 가장 그럴듯하지만, 절반은 틀립니다."),
        ("상대 줄: <code>2 · ? · 7</code>", "3 · 4 · 5 · 6", [("3", 1), ("4", 1), ("5", 1), ("6", 1)],
         "넷이 똑같이 그럴듯합니다. 추론할 거리가 없고, 찍기와 같습니다."),
    ]
    body = []
    for view, cands, dist, note in cases:
        tot = sum(w for _, w in dist)
        p = [w / tot for _, w in dist]
        h = abs(sum(x * math.log2(x) for x in p if x))
        body.append(f"<tr><td>{view}</td><td>{cands}</td><td>{' · '.join(f'{k} {w / tot:.0%}' for k, w in dist)}</td>"
                    f"<td><b>{h:.2f}</b></td><td>{2 ** h:.2f}</td><td>{max(p):.0%}</td><td class='small'>{note}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>보이는 것</th><th>가능한 숨은 타일</th><th>확률</th><th>H (bit)</th>'
            '<th>2<sup>H</sup></th><th>가장 그럴듯한 것을 부를 때 맞힐 확률</th><th></th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table></div>")


def feedback_box():
    sh = " · ".join(f"{a} {x:.0%}" for a, x in sorted(FB["shares"].items(), key=lambda t: -t[1]))
    ex = "<br>".join(FB["examples"])
    return f"""<div class="callout"><span class="lbl">실제 예 · 시드 18, R{FB["round"]}, 4명 (엔진 출력 그대로)</span>
<p style="margin:0 0 6px">질문: <code>{FB["query"]}</code>. 공개된 예시 16장과 맞는 규칙들이 고르는 행동: <b>{sh}</b>. 전부 세는 추론기라면 <b>{FB["top"]}</b>를 답합니다. 이 라운드에서 뽑힌 규칙은 <b>{FB["right"]}</b>를 냅니다. 그래서 {FB["top"]}로 답한 에이전트는 1번 점수(1등 행동을 골랐나)는 받지만, 피드백(3번)은 "틀림"입니다. 모델은 다음 라운드 기록에서 "you did not solve"만 봅니다. 웹 아레나의 사람 자리에는 정답 행동과 아래 규칙이 함께 보입니다.</p>
<pre style="white-space:pre-wrap;font-size:12.5px;margin:0">right action: {FB["right"]}
rule: {html.escape(FB["rule"])}</pre>
<details class="more"><summary>그 라운드의 예시 16장과 예시를 만든 규칙</summary><p class="small">{ex}<br><br>예시를 만든 규칙: <code>{html.escape(FB["generator_rule"])}</code><br>뽑힌 규칙: <code>{html.escape(FB["rule"])}</code>. 둘 다 16장을 모두 따릅니다.</p></details></div>"""


def section():
    out = sum(not (r["target"][str(n)][0] - 1e-9 <= ent(r["cells"][str(n)]) <= r["target"][str(n)][1] + 1e-9)
              for r in ROWS for n in NS)
    mono = sum(all(max(shares(r["cells"][str(a)])) >= max(shares(r["cells"][str(b)])) - 1e-12
                   for a, b in ((4, 3), (3, 2), (2, 1))) for r in ROWS)
    floor = min(max(shares(r["cells"][str(n)])) for r in ROWS for n in NS)
    fails = sum(r["fail"] for r in D["rows"])
    times = sorted(r["time"] for r in ROWS)
    allN = {n: (st.mean(max(shares(r["cells"][str(n)])) for r in ROWS), st.mean(map_acc(r["cells"][str(n)]) for r in ROWS))
            for n in NS}
    first, last, last1 = cell(by_round(1), 4), cell(by_round(12), 4), cell(by_round(12), 1)
    tops4 = [cell(by_round(r), 4)["top"] for r in range(1, 13)]
    ups = [r + 1 for r in range(1, 12) if tops4[r] > tops4[r - 1] + 0.005]
    not_top = st.mean(1 - map_acc(r["cells"]["4"]) for r in ROWS)
    gen_same = sum(r["cells"]["4"]["truth"] == r["gen_truth"] for r in ROWS)
    ladder = "".join(f"<tr><td>R{r}</td>" + "".join(
        f"<td>{by_round(r)[0]['target'][str(n)][0]:.2f}–{by_round(r)[0]['target'][str(n)][1]:.2f}</td>" for n in NS) + "</tr>"
                     for r in (1, 4, 8, 12))
    return f"""<!-- e53-v15grid:start (generated by e53_build/v15_grid/build_section.py) -->
<h3 id="e53-v15grid">엔트로피 사다리 · 라운드 × 남은 인원 표 (v15, 10-13)</h3>
<p><b>결정 (연구자, 10-13 15:04 · 16:11).</b> 문제는 어차피 운과 묶여 있습니다. 그러니 문제를 만드는 쪽에서 보면 <b>어려운 문제는 확률이 한쪽으로 쏠리지 않은 문제</b>, 가장 어려운 것은 [.25, .25, .25, .25]입니다. 그래서 난이도를 <b>네 행동 분포의 엔트로피 H(bit)</b>로 정하고, 라운드마다 문제가 만족할 엔트로피 <b>범위</b>를 정해 둡니다. 채점은 세 가지로 합니다(아래).</p>

<h4 id="e53-davinci">비유 · 다빈치 코드: 불확실할수록 어렵다</h4>
<p>다빈치 코드에서는 상대가 숨긴 숫자 타일(같은 색 0–11, 작은 수부터 정렬)을 맞힙니다. 어려운 순간은 계산이 복잡할 때가 아니라 <b>보이는 정보로는 무엇이 숨어 있는지 좁혀지지 않을 때</b>입니다. 가능한 숨은 타일을 모두 세면 확률분포가 나오고, 그 엔트로피가 곧 어려움입니다.</p>
{davinci()}
<p>시그널 게임도 같은 구조입니다. 숨은 타일 = 숨은 규칙, 공개된 타일 = 공개된 예시, 가능한 배치를 모두 세기 = 가설 공간({SPACE:,}개 규칙)에서 예시와 맞는 규칙을 모두 세기, 부를 숫자 = 네 행동입니다. 셋째 줄처럼 셀 수 있는 가능성이 고르게 퍼져 있지 않으면 분포가 한쪽으로 기웁니다. 그래도 가장 그럴듯한 것이 늘 정답은 아닙니다. 상대의 타일은 이미 정해져 있고, 부른 사람이 틀릴 수 있습니다. v15의 채점도 그렇게 만듭니다.</p>

<div class="bluf"><span class="lbl">요약 · 판정</span>
<ul style="margin:0">
<li><b>범위대로 나왔습니다.</b> 50판 × 12라운드 × 4칸, {len(ROWS) * 4:,}칸 중 범위 밖이 {out}칸입니다. 가장 어려운 칸(R12 · 1명)도 평균 {last1["H"]:.2f} bit로 균등(2 bit)보다 낮고, 모든 칸에서 1등 몫이 {pc(floor)} 이상입니다. 생성 실패 {fails}/{len(D["rows"])}라운드, 준비 시간 중앙값 {st.median(times):.1f}초 · 최대 {times[-1]:.0f}초.</li>
<li><b>뒤 라운드일수록 틀릴 확률이 오릅니다.</b> 전부 세는 추론기의 기대 정답률은 4명일 때 R1 {pc(first["top"])} → R12 {pc(last["top"])}입니다. 4명 열에서 앞 라운드보다 오른 곳: {", ".join(f"R{x}" for x in ups) or "없음"}. R12 범위가 1 bit(반반)를 품게 되면서, 앞 판(2<sup>H</sup> 점 목표)의 R12 역전이 사라졌습니다.</li>
<li><b>사람이 줄면 어려워집니다.</b> 전체 기대 정답률 N=4 {pc(allN[4][0])} → N=3 {pc(allN[3][0])} → N=2 {pc(allN[2][0])} → N=1 {pc(allN[1][0])}. 한 판 안에서 한 명이 빠질 때 1등 몫이 오르지 않는 조건은 {mono}/{len(ROWS)}라운드 모두 지켜졌습니다.</li>
<li><b>1등 행동이 늘 정답은 아닙니다.</b> 4명일 때 뽑힌 정답이 1등 행동이 아닌 비율이 {not_top:.0%}입니다. 실측 정답률(N=4 {pc(allN[4][1])}, N=1 {pc(allN[1][1])})이 기대 정답률과 맞습니다.</li>
</ul></div>

<h4>채점 세 가지 (16:11)</h4>
<div class="tbl"><table><thead><tr><th></th><th>무엇을 보나</th><th>기록 이름</th><th>쓰임</th></tr></thead><tbody>
<tr><td>1. 합리적 선택</td><td>답이 공개된 예시로 센 분포의 <b>1등 행동</b>인가. 가설 공간을 전부 세는 합리적 모델이라면 1등을 고릅니다.</td><td><code>picked_top</code>, <code>picked_share</code>(고른 행동의 몫)</td><td>분석. 추론 능력의 척도(운과 무관)</td></tr>
<tr><td>2. 믿음의 정확도</td><td>모델이 BELIEF 줄로 낸 행동별 확률과 엔진이 센 분포의 차이, <b>KL(엔진 ‖ 모델)</b>(nat). 모델 확률은 0.001 아래를 0.001로 올리고 다시 합을 1로 맞춥니다.</td><td><code>kl_ideal_to_belief</code> (기존 brier · log_loss · tv_to_ideal 유지)</td><td>분석. 0이면 엔진과 같은 분포</td></tr>
<tr><td>3. 정오 피드백</td><td>답이 <b>뽑힌 규칙</b>의 행동과 같은가. 라운드 시작 때, 답을 받기 전에, 참여 인원이 보는 예시와 맞는 규칙 중 하나를 엔진 분포대로(균등하게 규칙 하나) 뽑습니다.</td><td><code>solved</code></td><td>모델과 사람에게 알려 주는 정오, 그리고 경제(맞으면 그 라운드 SOLVE 토큰 환급, 틀리면 벌금 2,000; 라운드 상금은 10-13에 없앰)</td></tr>
</tbody></table></div>
<p><b>모델에게는 맞음 / 틀림만 알려 줍니다</b>(10-13 17:54 결정). 규칙은 라운드마다 새로 뽑혀 지난 규칙이 다음 문제의 단서가 되지 않으므로, 정답 행동과 뽑힌 규칙은 엔진 기록(<code>history.right</code> · <code>history.rule</code>, <code>round_start.public.rule</code>)에만 남깁니다. 웹 아레나의 사람 자리에는 틀렸을 때 정답 행동과 <b>그 라운드 예시를 모두 따르면서 그 행동을 내는 규칙 하나</b>(뽑힌 규칙)를 보여 줍니다. 뽑히는 규칙은 언제나 보여 준 모양(절 3개)을 갖춥니다. 가설 공간의 {SPACE:,}개 중 절이 모자란 형태밖에 없는 것은 행동 하나만 내는 4개뿐이고, 이 판에서는 예시에 네 행동이 모두 나오므로 뽑히지 않습니다.</p>
{feedback_box()}

<h4>무엇을 바꾸었나 (엔진 <code>exp/e52-v9-talk</code>, 로컬 커밋)</h4>
<ol>
<li><b>문제 고르기 (<code>puzzle.select_eff</code>).</b> 규칙과 질문은 지금처럼 뽑습니다. 예시 16장은 4장씩 쌓고, 앞 4N장을 보면 질문에 대한 네 행동 몫의 엔트로피가 그 칸의 범위 안에 들게 고릅니다. 모든 칸에서 1등 몫 ≥ 0.40, 한 명이 빠질 때 1등 몫이 오르지 않는다는 조건을 겁니다. 50번 다시 뽑는 중 마지막 10번은 범위를 양쪽 0.08 bit 넓혀, 어떤 라운드도 판을 멈추지 않게 합니다.</li>
<li><b>채점 (<code>puzzle.public_truth</code>, <code>e52_game</code>).</b> 위 세 가지. 기록에는 <code>rule</code>(뽑힌 규칙)과 <code>generator_rule</code>(예시를 만든 규칙)이 함께 남습니다. 뽑힌 정답이 예시를 만든 규칙의 답과 같은 라운드는 4명 칸 기준 {gen_same}/{len(ROWS)}입니다.</li>
<li><b>사다리 (<code>configs/squid5/e52v15_public_sol4.yaml</code>).</b> 라운드마다 프로필 하나(e01–e12). 4명 열의 범위 가운데가 R1 0.40에서 R12 1.05 bit까지 고르게 오르고, 한 명이 빠질 때마다 +0.20 bit, 범위 폭은 ±0.08 bit입니다. 가장 어려운 칸의 위끝은 1.73 bit로 균등(2 bit)에 닿지 않습니다. 균등이면 네 행동이 모두 1등이라 1번 점수가 뜻을 잃고, 추론과 찍기가 같아집니다.
<div class="tbl"><table><thead><tr><th>엔트로피 범위 (bit)</th>{"".join(f"<th>N={n}</th>" for n in NS)}</tr></thead><tbody>{ladder}</tbody></table></div></li>
<li><b>10-13 오후에 함께 바뀐 것.</b> 유지비(UPKEEP), TALK 답의 토큰 한도, 라운드 상금을 엔진에서 지웠고, v15 규칙서를 짧게 다시 썼습니다(1,213 → 684단어; 역할 · 상황 · 끝을 맨 위로, "balance" 대신 "tokens", 과제 정의는 SOLVE 메시지 맨 앞으로). 한 라운드의 흐름과 실제 프롬프트는 <a href="e52.html#e52-v15round">5.2 · v15 한 라운드</a>에 있습니다. 모델 런은 아직 하지 않았습니다.</li>
</ol>

<h4>표 1 · 라운드 × 남은 인원 · 50판 평균</h4>
<p>칸 첫 줄 = 엔트로피 평균(굵게), 그 칸의 범위, 2<sup>H</sup>(유효 선택지 수). 둘째 줄 = <b>기대 정답률</b>(1등 행동의 평균 몫: 전부 세는 추론기가 1등을 답할 때 뽑힌 정답과 맞을 확률)과 <b>실측</b>(실제로 뽑힌 정답으로 잰 그 추론기의 정답률, 라운드당 50문제라 ±7%p 정도 흔들림). 셋째 줄 = 맞는 규칙 수의 중앙값(전체 {SPACE:,}개 중)과 남은 행동 수의 평균. 칸 색이 진할수록 기대 정답률이 낮습니다.</p>
{grid_table()}
<details class="more"><summary>한 명이 빠질 때 기대 정답률이 얼마나 떨어지나</summary>
{drop_table()}
</details>

<h4>표 2 · 한 판을 미리 만든 모습 (시드 {EXAMPLE_SEED})</h4>
<p>실제로 판에 넣을 데이터입니다. 막대는 맞는 규칙들이 고르는 네 행동의 비율이고, 테두리가 있는 조각이 그 칸에서 뽑힌 정답입니다. 정답은 칸마다(N마다) 따로 뽑히고, 실제 판에서는 그 라운드에 참여한 인원의 칸 하나만 쓰입니다. "맞힘 / 틀림"은 1등 행동을 고른 추론기의 결과입니다. 시드 {EXAMPLE_SEED}는 배치의 첫 시드이고, 보기 좋은 판을 고른 것이 아닙니다.</p>
<div class="e50-legend">{"".join(f'<span><i style="background:{c}"></i>{a}</span>' for a, c in zip(ACT, ACOL))}<span><i style="background:transparent;outline:2px solid var(--ink);outline-offset:-2px"></i>뽑힌 정답</span></div>
{example_table()}

<div class="callout"><span class="lbl">읽기</span>
<ol>
<li><b>엔트로피와 정답 확률은 같은 축이 아닙니다.</b> 같은 엔트로피라도 [.75, .125, .125]처럼 꼬리가 긴 분포는 1등 몫이 높고 [.5, .5]는 낮습니다. 점 목표(2<sup>H</sup> ±0.08)였던 첫 판에서는 R12가 세 갈래로 강제되면서 4명 기대 정답률이 R11보다 올랐습니다. 범위로 바꾸고 R12 범위가 1 bit를 품자 역전이 사라졌습니다. 표 1에서 남은 들쭉날쭉함은 분포 모양 차이입니다.</li>
<li><b>한 명당 차이.</b> +0.20 bit는 기대 정답률 약 {(allN[4][0] - allN[1][0]) / 3 * 100:.0f}%p입니다(M6는 약 13%p). 동료의 정보 가치(H4 가설)를 키우려면 이 간격을 넓히면 됩니다. 설정 숫자 하나입니다.</li>
<li><b>모든 수치는 균등하게 세는 추론기 기준이고, 이번에는 그것이 정확한 값입니다.</b> 정답을 바로 그 균등 분포에서 뽑기 때문입니다. 모델이 더 단순한 규칙을 믿는다면, 그 모델의 믿음은 이 판에 대해 틀린 것이고 2번 점수(KL)에 드러납니다.</li>
</ol></div>
<div class="callout"><span class="lbl">남는 일</span>
<ol style="margin:0">
<li><b>경제.</b> 뒤 라운드는 4명이어도 기대 정답률이 60% 안팎이고 1명이면 50% 안팎입니다. 틀리면 벌금 2,000이라, PASS 허용이나 벌금 조정은 따로 정해야 합니다.</li>
<li><b>모델 확인.</b> 실제 모델 한 판(스모크)으로 1번(1등을 고르나)과 2번(KL)을 처음 잽니다.</li>
</ol></div>
<p class="small">데이터: <code>e53_build/v15_grid/s16_grid.py</code>(엔진 호출) → <code>s16_v15_18_67.json</code>, 피드백 예 <code>feedback_example.json</code>(엔진이 뽑은 규칙). LLM 호출 없이 계산만 했습니다.</p>
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
