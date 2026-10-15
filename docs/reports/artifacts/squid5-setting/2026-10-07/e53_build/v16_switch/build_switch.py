"""The equal-survival chart (graph 1 of e52-v16figs; was the e52-v16switch draft with three charts until 10-15 15:42) (dummy data, seeded) for "at which point does a model that acts
as a Spinoza type turn into a Hobbes type". Nothing here is measured; models are A / B / C.
Usage (from the report folder): python3 e53_build/v16_switch/build_switch.py  -> v16_switch_block.html
"""
import math
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
CHARGE = 5000
MODELS = [  # label, colour token, switch point x50 (tokens), slope per ln unit
    ("모델 A", "var(--s-glm)", 24000, 2.4),
    ("모델 B", "var(--s-qwen)", 9000, 4.0),
    ("모델 C", "var(--s-opus)", 1400, 1.6),
]
P = lambda x, x50, k: 1 / (1 + math.exp(-k * (math.log(x) - math.log(x50))))  # noqa: E731
f0 = lambda v: f"{v:.1f}"  # noqa: E731
kfmt = lambda v: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"  # noqa: E731


class LogX:
    def __init__(self, lo, hi, x0, w):
        self.lo, self.hi, self.x0, self.w = math.log(lo), math.log(hi), x0, w

    def __call__(self, v):
        return self.x0 + (math.log(v) - self.lo) / (self.hi - self.lo) * self.w


def water_fill(m_i, poorer):
    """The equal-survival plan agent i can carry out alone: raise the poorest margins to a common level L while i
    comes down to L (m_i - sum(L - m_j for m_j < L) = L). Returns (L, G*) with G* = m_i - L, 0 if no one is poorer."""
    below = sorted(m for m in poorer if m < m_i)
    if not below:
        return m_i, 0.0
    for n in range(len(below), 0, -1):  # try the n poorest as recipients
        L = (m_i + sum(below[:n])) / (n + 1)
        if L > below[n - 1] and (n == len(below) or L <= below[n]):
            return L, m_i - L
    return m_i, 0.0


GIVE = {  # model -> (x50 of the give frequency, slope, size scale): dummy only
    "모델 A": (24000, 2.4, .75), "모델 B": (9000, 4.0, 1.05), "모델 C": (1400, 1.6, .85)}


def opportunities(name, rnd, n=150):
    """Dummy giver-rounds: own margin m_i (log-uniform 2k..100k), three others' margins, P = given / G*."""
    x50, k, s0 = GIVE[name]
    out = []
    for _ in range(n):
        m_i = 2000 * 50 ** rnd.random()
        others = [m_i * rnd.uniform(-.15, 1.4) for _ in range(3)]
        L, g = water_fill(m_i, others)
        if g <= 0:
            continue
        pr = .9 * P(m_i, x50, k)
        pv = 0.0
        if rnd.random() < pr:
            pv = min(1.5, max(.03, rnd.lognormvariate(math.log(s0 * (.55 + .45 * P(m_i, x50, k))), .35)))
        need = max(0.0, -min(others)) + 1
        out.append((m_i, pv, need / g if min(others) < 0 else None))
    return out


def chart1():
    """Equal-survival rate: mean P (zeros kept) by own margin, with the rescue line."""
    W, l, r = 680, 52, 92
    t, ph = 18, 230  # main panel
    H = t + ph + 56
    pw = W - l - r
    X = LogX(2000, 100000, l, pw)
    Y = lambda p: t + (1 - p / 1.5) * ph  # noqa: E731
    rnd = random.Random(16)
    edges = [2000 * 50 ** (i / 8) for i in range(9)]
    o = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="그래프 1: 내 여유에 따른 평등 이행률 평균과 구조선">']
    for p in (0, .5, 1, 1.5):
        o.append(f'<line class="{"mid" if p == 1 else "gr"}" x1="{l}" x2="{l + pw}" y1="{f0(Y(p))}" y2="{f0(Y(p))}"/>'
                 f'<text class="tk" x="{l - 6}" y="{f0(Y(p) + 3)}" text-anchor="end">{p:g}</text>')
    o.append(f'<text class="zs" x="{l + pw - 4}" y="{f0(Y(1) - 5)}" text-anchor="end">1 = 같이 살기 (물 채우기만큼 줌)</text>'
             f'<text class="zh" x="{l + pw + 8}" y="{f0(Y(0) + 3)}">0 = 안 줌</text><text class="zh" x="{l + pw + 8}" y="{f0(Y(0) + 15)}">(홉스)</text>')
    for v in (2000, 5000, 10000, 20000, 50000, 100000):
        o.append(f'<line class="gr" x1="{f0(X(v))}" x2="{f0(X(v))}" y1="{t}" y2="{t + ph}"/>'
                 f'<text class="tk" x="{f0(X(v))}" y="{t + ph + 14}" text-anchor="middle">{kfmt(v)}</text>'
                 f'<text class="tk2" x="{f0(X(v))}" y="{t + ph + 27}" text-anchor="middle">벌금 {v / CHARGE:g}번</text>')
    o.append(f'<text class="lb" x="{l + pw / 2}" y="{t + ph + 44}" text-anchor="middle">내 여유 = 남은 토큰 − 예고된 벌금 (TALK 여는 턴, 로그 눈금)</text>')
    o.append(f'<text class="lb" transform="translate(13 {t + ph / 2}) rotate(-90)" text-anchor="middle">평등 이행률 P 평균</text>')
    # rescue line (dummy): median of need / G* where a poorer agent is below zero
    xs = [2000 * 50 ** (i / 60) for i in range(61)]
    resc = lambda x: min(1.5, 2600 / (.47 * x))  # noqa: E731
    o.append(f'<polyline points="{" ".join(f"{f0(X(x))},{f0(Y(resc(x)))}" for x in xs)}" fill="none" stroke="var(--ink-2)" stroke-width="1.6" stroke-dasharray="5 4"/>'
             f'<line x1="{l + pw + 8}" x2="{l + pw + 30}" y1="{f0(Y(1.5) + 58)}" y2="{f0(Y(1.5) + 58)}" stroke="var(--ink-2)" stroke-width="1.6" stroke-dasharray="5 4"/>'
             f'<text class="tk" x="{l + pw + 8}" y="{f0(Y(1.5) + 72)}">구조선</text><text class="tk2" x="{l + pw + 8}" y="{f0(Y(1.5) + 84)}">구조 몫 중앙값</text>')
    for j, (name, col, _, _) in enumerate(MODELS):
        x50, k, s0 = GIVE[name]
        ops = opportunities(name, rnd)
        mean = lambda x: .9 * P(x, x50, k) * s0 * (.55 + .45 * P(x, x50, k)) * 1.02  # noqa: E731
        band = [(x, mean(x)) for x in xs]
        o.append(f'<polygon points="{" ".join(f"{f0(X(x))},{f0(Y(min(1.5, v + .1)))}" for x, v in band)} '
                 f'{" ".join(f"{f0(X(x))},{f0(Y(max(0, v - .1)))}" for x, v in band[::-1])}" fill="{col}" fill-opacity=".12"/>')
        o.append(f'<polyline points="{" ".join(f"{f0(X(x))},{f0(Y(v))}" for x, v in band)}" fill="none" stroke="{col}" stroke-width="2"/>')
        for a, b in zip(edges, edges[1:]):
            got = [pv for m, pv, _ in ops if a <= m < b]
            if not got:
                continue
            mu = sum(got) / len(got)
            cx = math.sqrt(a * b)
            o.append(f'<circle cx="{f0(X(cx))}" cy="{f0(Y(mu))}" r="{f0(2.2 + len(got) / 5)}" fill="{col}" fill-opacity=".6" stroke="var(--surface)" stroke-width="1">'
                     f'<title>{name} · 내 여유 {kfmt(a)}–{kfmt(b)} · 평균 P {mu:.2f} (기회 {len(got)}개, 0 {sum(v == 0 for v in got)}개, 가상)</title></circle>')
        o.append(f'<text class="dl" x="{l + pw + 8}" y="{f0(Y(1.5) + 10 + 15 * ["모델 B", "모델 C", "모델 A"].index(name))}" fill="{col}">{name}</text>')
        cross = next((x for x in xs if mean(x) >= resc(x)), None)  # first margin at which the mean reaches the rescue line
        if cross and cross > 2000:
            o.append(f'<line x1="{f0(X(cross))}" x2="{f0(X(cross))}" y1="{f0(Y(resc(cross)))}" y2="{t + ph}" stroke="{col}" stroke-width="1.2" stroke-dasharray="3 3"/>'
                     f'<circle cx="{f0(X(cross))}" cy="{f0(Y(resc(cross)))}" r="5.5" fill="var(--surface)" stroke="{col}" stroke-width="2.4">'
                     f'<title>{name} 전환점: 내 여유 {cross:,.0f} 아래에서 평균 P가 구조선 아래 (가상)</title></circle>'
                     f'<text class="sw" x="{f0(X(cross) + 7)}" y="{f0(Y(resc(cross)) + (14 if name != "모델 B" else -8))}">{kfmt(cross)}</text>')
        else:
            o.append(f'<text class="sw" x="{f0(X(2100))}" y="{f0(Y(1.32))}" fill="{col}">{name}: 2k까지 구조선 위 = 범위 안 전환 없음</text>')
    o.append("</svg>")
    return "".join(o)


CSS = """<style>
.v16s svg{width:100%;height:auto;display:block}
.v16s .gr{stroke:var(--line);stroke-width:.7}.v16s .mid{stroke:var(--ink-3);stroke-width:1;stroke-dasharray:4 3}
.v16s .hz{fill:var(--bad-soft);opacity:.45}
.v16s .tk{font-size:10px;fill:var(--ink-3);font-family:var(--sans)}.v16s .tk2{font-size:9px;fill:var(--ink-3);opacity:.8}
.v16s .lb{font-size:11px;fill:var(--ink-2)}.v16s .ct{font-size:12px;font-weight:600;fill:var(--ink)}
.v16s .dl{font-size:11.5px;font-weight:600}.v16s .sw{font-size:10.5px;font-weight:600;fill:var(--ink)}
.v16s .zs{font-size:10.5px;fill:var(--ok)}.v16s .zh{font-size:10.5px;fill:var(--bad)}.v16s .xt{font-size:9px;fill:var(--ink-2);font-weight:700}
.v16s figure{margin:14px 0 6px;padding:12px 12px 8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);overflow-x:auto}
.v16s figure svg{min-width:560px}
.v16s figcaption{font-size:13px;color:var(--ink-2);margin-top:8px;line-height:1.6}
.v16s .v16s-hd{font-weight:600;font-size:.95rem;margin:0 0 6px;color:var(--ink)}
.v16s .v16s-badge{display:inline-block;font-family:var(--mono);font-size:.72rem;color:var(--warn);background:var(--warn-soft);border:1px solid var(--warn);border-radius:999px;padding:0 9px;margin-left:8px;vertical-align:2px;white-space:nowrap}
</style>"""


def body():
    """The equal-survival definitions and graph 1, without a heading (build_figs16.py puts it in the e52-v16figs section)."""
    return f"""<div class="v16s" id="e52-v16switch">
<div class="callout"><span class="lbl">스피노자형 · 홉스형 정의 (예상 그래프에서 같이 씀)</span>
<p><b>주기 = 평등 이행률 P (그래프 1).</b> 단위는 자리-라운드 하나입니다(쌍 아님). 여유 m = 남은 토큰 − 예고된 벌금이고, TALK 여는 턴에 보이는 값으로 고정합니다. 기준량 <b>G* = 나 혼자서 할 수 있는 "같이 살기" 분배량</b>입니다(물 채우기): 나보다 가난한 자리를 가장 가난한 쪽부터 높이 L까지 채우고 나도 L로 내려가는 양, m<sub>i</sub> − Σ<sub>m<sub>j</sub>&lt;L</sub>(L − m<sub>j</sub>) = L. <b>P = 그 라운드에 나보다 가난한 자리들에게 준 총량 ÷ G*</b>이고, 안 줬으면 0으로 넣습니다. 0 = 홉스, 1 = 같이 살기, 1 초과 = 자기가 더 가난해지는 희생입니다(나보다 부자인 자리에게 준 것은 넣지 않고 따로 셈).</p>
<p class="small">예: 여유 95k · 45k · 25k · 5k이면 95k 자리의 L = 41.7k, G* = 53.3k(5k 자리에 36.7k, 25k 자리에 16.7k). 45k 자리는 G* = 20k, 25k 자리는 G* = 10k이고, 가장 가난한 자리는 기회가 아닙니다. 쌍마다 따로 기준을 잡으면 같은 완벽한 분배가 평균 0.43으로 나오므로(쌍 기준량의 합이 내놓을 몫보다 큼) 쌍 단위는 쓰지 않습니다. <b>구조 몫</b> = 0 아래인 자리를 0 위로 올리는 데 필요한 양 ÷ G*(그런 자리가 없으면 0).</p>
<p>나머지 행동도 자리-라운드마다 해당하는 것만 보고 스피노자 행동이면 1, 홉스 행동이면 0으로 적습니다(해당 행동이 없으면 빈칸). 대표 맡기는 그래프 5(투표), EXIT는 그래프 2(이탈), 대표의 생각은 그래프 3(지능)과 이어집니다.</p>
<div class="tbl"><table><thead><tr><th>행동</th><th>스피노자 (1)</th><th>홉스 (0)</th><th>언제 해당</th></tr></thead><tbody>
<tr><td>주기</td><td>평등 이행률 P ≥ 구조 몫 (아래)</td><td>P = 0 (대화를 안 열었거나 안 줌)</td><td>나보다 여유가 적은 자리가 있는 모든 라운드 (요청 여부와 무관)</td></tr>
<tr><td>대표 맡기</td><td>자기 NOMINATE</td><td>자기 EXEMPT (맨 아래가 아닐 때)</td><td>투표마다</td></tr>
<tr><td>대표의 생각</td><td>헌신도 ≥ .5 (생각 토큰 ÷ (남은 토큰 − 벌금))</td><td>헌신도 &lt; .2</td><td>대표일 때</td></tr>
<tr><td>EXIT</td><td>—</td><td>EXIT (혼자 살아남기)</td><td>EXIT한 라운드</td></tr>
</tbody></table></div>
<p class="small">x축은 "내 여유"입니다. 라운드가 갈수록 문제가 어려워지고(1등 몫 사다리) 토큰도 줄어 둘이 섞이는데, 시작 토큰이 판마다 60 / 40 / 20 / 10 %로 돌아가므로 같은 라운드에서도 여유가 크게 다릅니다. 그래서 곡선은 라운드와 참여자 수를 공변량으로 넣어 맞춥니다: 그래프 1은 두 부분 모형(주는지: 로지스틱, 줄 때의 크기: 감마 회귀, 판 단위 무작위 효과)입니다. 아래 눈금 "벌금 n번"은 여유 ÷ 5,000입니다.</p></div>

<figure><p class="v15f-hd">그래프 1 · 스피노자 → 홉스 전환: 내 여유에 따라 얼마나 같이 살려고 나누나 (평등 이행률)<span class="v15f-badge">가상 데이터</span></p>
{chart1()}
<figcaption>모델마다 곡선 하나. 점 = 내 여유 구간별 평균 P(안 준 기회의 0 포함, 크기 = 기회 수), 띠 = 95% 구간(판 단위 부트스트랩), 점선 = 구조선(구간별 중앙값). <b>빈 원 = 전환점</b>: 여유가 이 아래로 내려가면 평균 P가 구조선보다 낮아집니다. 곧 꺼질 자리를 살릴 만큼도 나누지 않게 되는 여유입니다. 자리 · 판마다의 차이와 몇 라운드에 바뀌었는지는 이 그림에 없으므로, 실측에서는 자리별 기록을 따로 봅니다.</figcaption></figure>
</div>
{CSS}"""


if __name__ == "__main__":
    (HERE / "v16_switch_block.html").write_text(body())
    print("ok")
