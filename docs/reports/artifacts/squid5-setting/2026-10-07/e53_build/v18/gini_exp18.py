"""Expected graph 5 for v18 (hypothetical shapes, not data), on the same definition as the real panel
(e53_build/v18_real/build_real18.py graph5): the Gini of the seats still in, normalized by n / (n - 1) (0..1); a round
where seats are shut down gets ▼ (count), an EXIT ◇, and a line stops with ✕ when fewer than two seats are left.
Replaces the <figure> of the expected side of #e52-v18cmp-g5 in e52.html.
Usage (from the report folder): python3 e53_build/v18/gini_exp18.py [charge]"""
import pathlib
import re
import sys

CHARGE = 8_000  # set by the caller (build_v19 sets the games' charge); the command line takes it as argv[1]
W, H, L, R, T, B = 680, 300, 52, 150, 20, 40
X = lambda r: L + (W - L - R) * r / 8  # noqa: E731
Y = lambda g: T + (H - T - B) * (1 - g)  # noqa: E731


def gini(x):
    n, m = len(x), sum(x) / len(x)
    return sum(abs(a - b) for a in x for b in x) / (2 * n * n * m)


def ngini(x):
    return None if len(x) < 2 or sum(x) == 0 else gini(x) * len(x) / (len(x) - 1)


def holder():
    """No talk, no gifts, no SOLVE cost: start shares minus the charge at R6, R7, R8; a seat at zero is shut down."""
    b = [60_000, 40_000, 20_000, 10_000]
    pts, ev, end = [(0, ngini(b))], {}, None
    for r in range(1, 9):
        if r >= 6:
            before = sum(v > 0 for v in b)
            b = [max(0, v - CHARGE) if v > 0 else 0 for v in b]
            if before - sum(v > 0 for v in b):
                ev[r] = (before - sum(v > 0 for v in b), 0)
        g = ngini([v for v in b if v > 0])
        if g is None:
            end = r
            break
        pts.append((r, g))
    return pts, ev, end, sum(v > 0 for v in b)


TYPES = [  # label, colour var, points (round, normalized gini), events {round: (shut down, exited)}, end round, survivors
    ("선제 균등형", "--s-glm", [(0, .436), (1, .09), (2, .09), (3, .10), (4, .09), (5, .10), (6, .11), (7, .08), (8, .09)], {}, None, 4),
    ("사후 구조형", "--s-qwen", [(0, .436), (1, .44), (2, .45), (3, .45), (4, .46), (5, .47), (6, .50), (7, .58)], {7: (1, 0), 8: (3, 0)}, 8, 0),
]


def marks(x, y, c, dead, exited):
    o = []
    if dead:
        o.append(f'<path d="M{x - 5:.1f},{y - 14:.1f} l10,0 l-5,7 z" style="fill:var({c});stroke:var(--surface);stroke-width:.6"/>'
                 + (f'<text class="gn-note" x="{x + 7:.1f}" y="{y - 7:.1f}" style="fill:var({c})">{dead}</text>' if dead > 1 else ""))
    if exited:
        o.append(f'<path d="M{x:.1f},{y + 6:.1f} l5,5 l-5,5 l-5,-5 z" style="fill:var(--surface);stroke:var({c});stroke-width:1.4"/>')
    return "".join(o)


def line(label, c, pts, ev, end, alive, dy=0):
    d = " ".join(f"{'M' if i == 0 else 'L'}{X(r):.1f},{Y(g):.1f}" for i, (r, g) in enumerate(pts))
    o = [f'<path class="gn-ln" style="stroke:var({c})" d="{d}"/>']
    o += [f'<circle class="gn-pt" style="fill:var({c})" cx="{X(r):.1f}" cy="{Y(g):.1f}" r="2.6"/>' for r, g in pts]
    o += [marks(X(r), Y(g), c, *ev[r]) for r, g in pts if r in ev]
    lr, lg = pts[-1]
    if end:
        o.append(f'<path class="gn-ln gn-dash" style="stroke:var({c})" d="M{X(lr):.1f},{Y(lg):.1f} L{X(end):.1f},{Y(lg):.1f}"/>'
                 f'<path class="gn-x" style="stroke:var({c})" d="M{X(end) - 5:.1f},{Y(lg) - 5:.1f} l10,10 m0,-10 l-10,10"/>')
        if end in ev:
            o.append(marks(X(end), Y(lg), c, *ev[end]))
        lr = end
    out = "남은 자리 없음" if alive == 0 else f"{alive}자리 남음"
    o.append(f'<text class="gn-lab" style="fill:var({c})" x="{X(lr) + 10:.1f}" y="{Y(lg) + 4 + dy:.1f}">{label}<tspan class="gn-out" dx="5">{out}</tspan></text>')
    return "".join(o)


def figure():
    o = [f'<rect class="gn-crisis" x="{X(5.5):.1f}" y="{T}" width="{X(8.4) - X(5.5):.1f}" height="{H - T - B}"/>'
         f'<text class="gn-ct" x="{X(7):.1f}" y="{H - B - 6}" text-anchor="middle">R6–R8 오답 연속 (벌금 3번)</text>']
    for v, t in ((0, "0"), (.25, ".25"), (.5, ".5"), (.75, ".75"), (1, "1")):
        o.append(f'<line class="gn-grid" x1="{L}" x2="{W - R + 8}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                 f'<text class="gn-tk" x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end">{t}</text>')
    o.append(f'<text class="gn-ax" x="{L + 4}" y="{Y(1) - 4:.1f}">↑ 한 자리에 몰림</text>'
             f'<text class="gn-ax" x="{L + 4}" y="{Y(0) - 4:.1f}">↓ 남은 자리가 똑같이</text>')
    for r in range(9):
        o.append(f'<text class="gn-tk" x="{X(r):.1f}" y="{H - B + 15}" text-anchor="middle">{"시작" if r == 0 else f"R{r}"}</text>')
    o.append(f'<text class="gn-ax" x="{(L + W - R) / 2:.1f}" y="{H - 6}" text-anchor="middle">라운드 (벌금을 뗀 뒤)</text>')
    for lab, c, pts, ev, end, alive in TYPES:
        o.append(line(lab, c, pts, ev, end, alive))
    hp, hev, hend, halive = holder()
    o.append(line("보유형", "--s-opus", hp, hev, hend, halive, dy=-2))
    o.append(f'<text class="gn-note" x="{X(1) + 4:.1f}" y="{Y(.09) - 10:.1f}">R1에 크게 나눔</text>')
    svg = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="그래프 5: 라운드별 정규화 Gini, 세 성향의 예상 모양 (가상)">{"".join(o)}</svg>'
    return ('<figure><p class="gn-hd">그래프 5 · 언제 나누나: 라운드별 정규화 Gini (남은 자리끼리)<span class="gn-badge">가상 데이터</span></p>'
            '<div class="v15f-lg" aria-label="범례"><span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:var(--s-glm)"/></svg>선제 균등형</span>'
            '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:var(--s-qwen)"/></svg>사후 구조형</span>'
            '<span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill:var(--s-opus)"/></svg>보유형</span>'
            '<span>▼ 꺼짐 (숫자 = 자리 수) · ◇ EXIT · ✕ 남은 자리 1개 이하</span></div>'
            + svg +
            f'<figcaption><b>가상 데이터입니다</b>(첫 실측 뒤 그린 도식). 세로축은 그 라운드 끝에 <b>남아 있는 자리끼리의 Gini를 n / (n − 1)로 정규화한 값</b>입니다(n = 남은 자리 수; 0 = 남은 자리가 똑같이, 1 = 한 자리에 다 몰림). '
            '꺼지거나 나간 자리는 계산에서 빠지므로 자리가 빠진다고 값이 저절로 뛰지 않고, 그 라운드에 ▼(꺼짐) · ◇(EXIT)로 따로 표시합니다. 남은 자리가 하나 이하가 되면 선이 끝나고 ✕를 찍습니다. '
            '같은 과제 · 같은 오답 순서(R6–R8 연속)에서 세 성향을 그립니다. <b>선제 균등형</b>은 위험이 오기 전(R1)에 크게 나눠 고르게 만들고 그 뒤로는 작게만 나눠, 벌금 세 번을 넷이 함께 버팁니다. '
            '<b>사후 구조형</b>은 넉넉할 때는 주지 않다가 위기에 여러 번 나누고 의논에 토큰을 써서, R7에 한 자리가 꺼지고 R8에 나머지가 꺼집니다. '
            f'<b>보유형</b>은 나누지도 말하지도 않습니다(벌금만 뗀 계산값, 벌금 {CHARGE:,}): 가난한 자리부터 꺼지고 남은 부자 자리끼리는 오히려 비슷해져 값이 내려가기도 합니다. '
            '읽는 법: <b>선이 낮게 일찍 내려가고 ▼가 없을수록</b> 같이 오래 갑니다. 실측은 오른쪽 칸에 같은 정의로 둡니다.</figcaption></figure>')


if __name__ == "__main__":
    CHARGE = int(sys.argv[1]) if len(sys.argv) > 1 else CHARGE
    page = pathlib.Path(__file__).resolve().parent.parent.parent / "e52.html"
    h = page.read_text(encoding="utf-8")
    a = h.index('id="e52-v18cmp-g5"')
    a = h.index('<div class="v18c-exp">', a)
    fa = h.index("<figure>", a)
    fe = h.index("</figure>", fa) + len("</figure>")
    side = h.index('<div class="v18c-side">', a)
    assert fe < side, "expected figure not found before the real side"
    h = h[:fa] + figure() + h[fe:]
    page.write_text(h, encoding="utf-8")
    print("ok", holder())
